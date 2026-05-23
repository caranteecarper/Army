"""
Run NanmiCoder/MediaCrawler for Douyin and return JSON to the parent pipeline.

The parent project remains Python 3.8 compatible. This bridge is executed by a
separate Python environment configured in source_registry.yaml.
"""
import asyncio
import json
import os
import sys
import traceback
from pathlib import Path
from typing import Any, Dict, List


def _read_payload() -> Dict[str, Any]:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("Douyin bridge payload must be a JSON object")
    return payload


def _project_path(base_dir: Path, value: Any) -> Path:
    path = Path(str(value))
    if path.is_absolute():
        return path
    return (base_dir / path).resolve()


def _publish_time_value(value: Any) -> int:
    text = str(value or "").strip().lower()
    mapping = {
        "": 1,
        "one_day": 1,
        "1": 1,
        "一天内": 1,
        "一天": 1,
        "latest_day": 1,
        "one_week": 7,
        "7": 7,
        "一周内": 7,
        "six_month": 180,
        "180": 180,
        "半年内": 180,
        "unlimited": 0,
        "0": 0,
        "不限": 0,
    }
    return mapping.get(text, 1)


def _crawler_type(payload: Dict[str, Any]) -> str:
    mode = str(payload.get("mode") or "keyword_search").strip()
    mapping = {
        "keyword_search": "search",
        "search": "search",
        "video_detail": "detail",
        "detail": "detail",
        "user_profile": "creator",
        "creator": "creator",
    }
    if mode not in mapping:
        raise ValueError("unsupported Douyin mode {}".format(mode))
    return mapping[mode]


def _load_jsonl(path: Path) -> List[Dict[str, Any]]:
    items = []
    if not path.exists():
        return items
    with path.open("r", encoding="utf-8") as file_obj:
        for line in file_obj:
            line = line.strip()
            if not line:
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                items.append(parsed)
    return items


def _read_output(save_path: Path) -> List[Dict[str, Any]]:
    jsonl_dir = save_path / "douyin" / "jsonl"
    items = []
    for path in sorted(jsonl_dir.glob("*_contents_*.jsonl")):
        items.extend(_load_jsonl(path))

    seen = set()
    deduped = []
    for item in items:
        aweme_id = str(item.get("aweme_id") or "")
        key = aweme_id or json.dumps(item, ensure_ascii=False, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


async def _run_mediacrawler(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    base_dir = Path(__file__).resolve().parents[1]
    tool_dir = _project_path(base_dir, payload.get("tool_dir"))
    if not tool_dir.exists():
        raise ValueError("MediaCrawler tool_dir does not exist: {}".format(tool_dir))

    save_path = _project_path(base_dir, payload.get("save_path"))
    save_path.mkdir(parents=True, exist_ok=True)

    sys.path.insert(0, str(tool_dir))
    old_cwd = Path.cwd()
    os.chdir(str(tool_dir))
    try:
        import config  # type: ignore
        from media_platform.douyin import DouYinCrawler  # type: ignore

        crawler_type = _crawler_type(payload)
        config.PLATFORM = "dy"
        config.CRAWLER_TYPE = crawler_type
        config.LOGIN_TYPE = str(payload.get("login_type") or "qrcode")
        config.COOKIES = str(payload.get("cookies") or "")
        config.KEYWORDS = str(payload.get("keyword") or "")
        config.START_PAGE = int(payload.get("start_page") or 1)
        config.CRAWLER_MAX_NOTES_COUNT = int(payload.get("limit") or 10)
        config.MAX_CONCURRENCY_NUM = int(payload.get("max_concurrency") or 1)
        config.SAVE_DATA_OPTION = "jsonl"
        config.SAVE_DATA_PATH = str(save_path)
        config.ENABLE_GET_COMMENTS = bool(payload.get("fetch_comments", False))
        config.ENABLE_GET_SUB_COMMENTS = bool(payload.get("fetch_sub_comments", False))
        config.CRAWLER_MAX_COMMENTS_COUNT_SINGLENOTES = int(
            payload.get("max_comments_per_video") or 10
        )
        config.ENABLE_GET_MEIDAS = bool(payload.get("download_video", False))
        config.ENABLE_GET_WORDCLOUD = False
        config.ENABLE_IP_PROXY = False
        config.HEADLESS = bool(payload.get("headless", False))
        config.CDP_HEADLESS = bool(payload.get("headless", False))
        config.ENABLE_CDP_MODE = bool(payload.get("enable_cdp", True))
        config.CDP_CONNECT_EXISTING = bool(payload.get("cdp_connect_existing", False))
        config.AUTO_CLOSE_BROWSER = bool(payload.get("auto_close_browser", True))
        config.PUBLISH_TIME_TYPE = _publish_time_value(payload.get("publish_time"))
        config.DY_SPECIFIED_ID_LIST = list(payload.get("specified_ids") or [])
        config.DY_CREATOR_ID_LIST = list(payload.get("creator_ids") or [])

        crawler = DouYinCrawler()
        await crawler.start()
        await crawler.close()
    finally:
        os.chdir(str(old_cwd))

    return _read_output(save_path)


def main() -> None:
    original_stdout = sys.stdout
    sys.stdout = sys.stderr
    try:
        payload = _read_payload()
        result = asyncio.run(_run_mediacrawler(payload))
        output = result
    except Exception as exc:
        traceback.print_exc(file=sys.stderr)
        output = {"error": str(exc)}
    finally:
        sys.stdout = original_stdout

    json.dump(output, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
