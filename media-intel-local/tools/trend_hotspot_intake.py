import argparse
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from core.intake_schema import (  # noqa: E402
    deduplicate_intake_items,
    normalize_intake_item,
    should_keep_intake_item,
)


DEFAULT_INPUT_PATH = PROJECT_ROOT / "config" / "trend_hotspot_intake.yaml"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "inbox"


def parse_target_date(value: str) -> str:
    if value == "today":
        return today_for_shanghai().isoformat()
    if value == "yesterday":
        return (today_for_shanghai() - timedelta(days=1)).isoformat()
    try:
        return datetime.strptime(value, "%Y-%m-%d").date().isoformat()
    except ValueError:
        raise ValueError("--date must be today, yesterday or YYYY-MM-DD")


def today_for_shanghai() -> date:
    china_timezone = timezone(timedelta(hours=8), name="Asia/Shanghai")
    return datetime.now(china_timezone).date()


def load_input(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as file_obj:
        payload = yaml.safe_load(file_obj)
    if not isinstance(payload, dict):
        raise ValueError("intake input must be a YAML mapping")
    return payload


def collect_input_items(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    items = []
    for source_type, section_key in (
        ("platform_trend", "platform_trends"),
        ("social_hotspot", "social_hotspots"),
    ):
        section = payload.get(section_key) or []
        if not isinstance(section, list):
            raise ValueError("{} must be a list".format(section_key))
        for raw_item in section:
            if not isinstance(raw_item, dict):
                continue
            if not raw_item.get("enabled", True):
                continue
            item = dict(raw_item)
            item["source_type"] = source_type
            items.append(item)
    return items


def write_jsonl(path: Path, items: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file_obj:
        for item in items:
            json.dump(item, file_obj, ensure_ascii=False, separators=(",", ":"))
            file_obj.write("\n")


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file_obj:
        json.dump(payload, file_obj, ensure_ascii=False, indent=2)
        file_obj.write("\n")


def run_intake(input_path: Path, output_dir: Path, target_date: str) -> Dict[str, Any]:
    started_at = datetime.now().isoformat(timespec="seconds")
    payload = load_input(input_path)
    raw_items = collect_input_items(payload)
    normalized = []
    filtered = []

    for raw_item in raw_items:
        item = normalize_intake_item(raw_item)
        keep, reason = should_keep_intake_item(item)
        if keep:
            normalized.append(item)
        else:
            filtered.append(
                {
                    "source_type": item.get("source_type", ""),
                    "platform": item.get("platform", ""),
                    "title": item.get("title", ""),
                    "reason": reason,
                }
            )

    platform_items = deduplicate_intake_items(
        [item for item in normalized if item.get("source_type") == "platform_trend"]
    )
    social_items = deduplicate_intake_items(
        [item for item in normalized if item.get("source_type") == "social_hotspot"]
    )

    stamp = target_date.replace("-", "")
    platform_path = output_dir / "platform_trends_{}.jsonl".format(stamp)
    social_path = output_dir / "social_hotspots_{}.jsonl".format(stamp)
    log_path = output_dir / "trend_hotspot_run_log_{}.json".format(stamp)

    write_jsonl(platform_path, platform_items)
    write_jsonl(social_path, social_items)
    run_log = {
        "date": target_date,
        "input_path": str(input_path),
        "output_dir": str(output_dir),
        "started_at": started_at,
        "ended_at": datetime.now().isoformat(timespec="seconds"),
        "items_raw": len(raw_items),
        "items_kept_before_dedup": len(normalized),
        "platform_trends": len(platform_items),
        "social_hotspots": len(social_items),
        "items_filtered": len(filtered),
        "filtered": filtered,
        "outputs": {
            "platform_trends": str(platform_path),
            "social_hotspots": str(social_path),
            "run_log": str(log_path),
        },
    }
    write_json(log_path, run_log)
    return run_log


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Normalize platform trends and social hotspots into JSONL inbox files."
    )
    parser.add_argument("--date", default="today", help="today, yesterday or YYYY-MM-DD")
    parser.add_argument("--input", default=str(DEFAULT_INPUT_PATH), help="Input YAML file")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Output directory")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    input_path = Path(args.input)
    output_dir = Path(args.output_dir)
    if not input_path.is_absolute():
        input_path = PROJECT_ROOT / input_path
    if not output_dir.is_absolute():
        output_dir = PROJECT_ROOT / output_dir
    target_date = parse_target_date(args.date)
    log = run_intake(input_path, output_dir, target_date)
    print(
        "wrote platform_trends={}, social_hotspots={}, filtered={}".format(
            log["platform_trends"], log["social_hotspots"], log["items_filtered"]
        )
    )
    print("output_dir {}".format(output_dir))


if __name__ == "__main__":
    main()
