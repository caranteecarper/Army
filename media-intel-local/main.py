import argparse
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List

import yaml

from adapters.wechat_adapter import adapt as adapt_wechat
from adapters.website_adapter import adapt as adapt_website
from adapters.xhs_adapter import adapt as adapt_xhs
from core.deduplicate import deduplicate_items
from core.normalize import normalize_item
from crawlers.wechat_crawler import WechatCrawler
from crawlers.website_crawler import WebsiteCrawler
from crawlers.xhs_crawler import XiaohongshuCrawler


PROJECT_ROOT = Path(__file__).resolve().parent
REGISTRY_PATH = PROJECT_ROOT / "config" / "source_registry.yaml"

CRAWLER_CLASSES = {
    "wechat": WechatCrawler,
    "website": WebsiteCrawler,
    "xiaohongshu": XiaohongshuCrawler,
}

ADAPTERS = {
    "wechat": adapt_wechat,
    "website": adapt_website,
    "xiaohongshu": adapt_xhs,
}  # type: Dict[str, Callable[[Dict[str, Any], Dict[str, Any]], Dict[str, Any]]]


def load_registry(registry_path: Path) -> Dict[str, Any]:
    with registry_path.open("r", encoding="utf-8") as file_obj:
        registry = yaml.safe_load(file_obj)
    if not isinstance(registry, dict):
        raise ValueError("source registry must contain a YAML mapping")
    return registry


def collect_sources(registry: Dict[str, Any]) -> List[Dict[str, Any]]:
    sources = []
    for key, value in registry.items():
        if key == "project":
            continue
        if isinstance(value, list):
            sources.extend(source for source in value if isinstance(source, dict))
    return sources


def parse_target_date(date_value: str, timezone_name: str) -> str:
    if date_value == "yesterday":
        target_day = today_for_timezone(timezone_name) - timedelta(days=1)
        return target_day.isoformat()

    try:
        return datetime.strptime(date_value, "%Y-%m-%d").date().isoformat()
    except ValueError:
        raise ValueError("--date must be yesterday or YYYY-MM-DD")


def today_for_timezone(timezone_name: str) -> date:
    if timezone_name == "Asia/Shanghai":
        china_timezone = timezone(timedelta(hours=8), name="Asia/Shanghai")
        return datetime.now(china_timezone).date()
    return date.today()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file_obj:
        json.dump(payload, file_obj, ensure_ascii=False, indent=2)
        file_obj.write("\n")


def raw_record(raw_item: Dict[str, Any], source: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "source_id": source.get("id", ""),
        "source_name": source.get("name", ""),
        "source_type": source.get("type", ""),
        "raw": raw_item,
    }


def run_pipeline(registry: Dict[str, Any], target_date: str) -> Dict[str, Any]:
    start_time = datetime.now().isoformat(timespec="seconds")
    project_config = registry.get("project") or {}
    output_root = PROJECT_ROOT / Path(str(project_config.get("output_dir") or "output"))
    output_dir = output_root / target_date

    raw_items = []  # type: List[Dict[str, Any]]
    normalized_items = []  # type: List[Dict[str, Any]]
    errors = []  # type: List[Dict[str, str]]
    sources = collect_sources(registry)
    enabled_sources = [source for source in sources if source.get("enabled", True)]
    sources_success = 0
    sources_failed = 0

    crawlers = {
        source_type: crawler_class(PROJECT_ROOT)
        for source_type, crawler_class in CRAWLER_CLASSES.items()
    }

    for source in sources:
        if not source.get("enabled", True):
            print("skip disabled source {}".format(source.get("id", "")))
            continue

        source_type = str(source.get("type") or "")
        try:
            crawler = crawlers[source_type]
            adapter = ADAPTERS[source_type]
            fetched_items = crawler.fetch(source, target_date)
            raw_items.extend(raw_record(item, source) for item in fetched_items)
            normalized_items.extend(
                normalize_item(adapter(item, source)) for item in fetched_items
            )
            sources_success += 1
            print(
                "source {} ({}) fetched {} item(s)".format(
                    source.get("id", ""), source_type, len(fetched_items)
                )
            )
        except Exception as exc:
            sources_failed += 1
            errors.append(
                {
                    "source_id": str(source.get("id") or ""),
                    "source_name": str(source.get("name") or ""),
                    "error": str(exc),
                }
            )
            print("source {} failed: {}".format(source.get("id", ""), exc))

    deduplicated_items = deduplicate_items(normalized_items)
    write_json(output_dir / "raw_items.json", raw_items)
    write_json(output_dir / "normalized_items.json", deduplicated_items)

    run_log = {
        "date": target_date,
        "start_time": start_time,
        "end_time": datetime.now().isoformat(timespec="seconds"),
        "sources_total": len(enabled_sources),
        "sources_skipped_disabled": len(sources) - len(enabled_sources),
        "sources_success": sources_success,
        "sources_failed": sources_failed,
        "items_raw": len(raw_items),
        "items_normalized": len(normalized_items),
        "items_after_dedup": len(deduplicated_items),
        "errors": errors,
    }
    write_json(output_dir / "run_log.json", run_log)
    print("wrote {}".format(output_dir))
    print(
        "raw={}, normalized={}, after_dedup={}, failed_sources={}".format(
            len(raw_items),
            len(normalized_items),
            len(deduplicated_items),
            sources_failed,
        )
    )
    return run_log


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Collect configured media items and normalize them to one JSON schema."
    )
    parser.add_argument(
        "--date",
        default="yesterday",
        help="Target date in YYYY-MM-DD format, or yesterday.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    registry = load_registry(REGISTRY_PATH)
    project_config = registry.get("project") or {}
    target_date = parse_target_date(
        args.date, str(project_config.get("timezone") or "Asia/Shanghai")
    )
    print("target date {}".format(target_date))
    run_pipeline(registry, target_date)


if __name__ == "__main__":
    main()
