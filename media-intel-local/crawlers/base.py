import json
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Dict, List


class BaseCrawler:
    source_type = ""

    def __init__(self, project_root: Path) -> None:
        self.project_root = Path(project_root)

    def fetch(self, source: Dict[str, Any], target_date: str) -> List[Dict[str, Any]]:
        """
        source: source_registry.yaml 中的单个源配置
        target_date: YYYY-MM-DD
        return: 原始 item 列表，尚未统一格式化
        """
        raise NotImplementedError

    def _read_mock_items(self, source: Dict[str, Any]) -> List[Dict[str, Any]]:
        mock_file = source.get("mock_file")
        if not mock_file:
            raise ValueError("source {} is missing mock_file".format(source.get("id", "")))

        mock_path = self.project_root / Path(str(mock_file))
        try:
            with mock_path.open("r", encoding="utf-8") as file_obj:
                items = json.load(file_obj)
        except OSError as exc:
            raise RuntimeError("cannot read mock data {}: {}".format(mock_path, exc))
        except json.JSONDecodeError as exc:
            raise RuntimeError("invalid mock JSON {}: {}".format(mock_path, exc))

        if not isinstance(items, list):
            raise ValueError("mock data {} must contain a JSON list".format(mock_path))
        if not all(isinstance(item, dict) for item in items):
            raise ValueError("mock data {} must contain JSON objects only".format(mock_path))
        return items

    def _filter_by_date(
        self, items: List[Dict[str, Any]], date_field: str, target_date: str
    ) -> List[Dict[str, Any]]:
        return [
            item
            for item in items
            if self._date_part(item.get(date_field)) == target_date
        ]

    def _is_mock_source(self, source: Dict[str, Any]) -> bool:
        fetch_mode = str(source.get("fetch_mode") or source.get("crawl_mode") or "").lower()
        return fetch_mode == "mock" or (not fetch_mode and bool(source.get("mock_file")))

    def _date_part(self, value: Any) -> str:
        return self._normalized_datetime(value)[:10]

    def _normalized_datetime(self, value: Any) -> str:
        if value is None or value == "":
            return ""

        if isinstance(value, (int, float)):
            seconds = float(value)
            if seconds > 100000000000:
                seconds = seconds / 1000.0
            china_timezone = timezone(timedelta(hours=8), name="Asia/Shanghai")
            return datetime.fromtimestamp(seconds, china_timezone).isoformat()

        text = str(value).strip()
        if not text:
            return ""
        if text.isdigit():
            return self._normalized_datetime(int(text))
        if len(text) >= 10 and text[:4].isdigit() and text[4] == "-":
            return text.replace(" ", "T", 1)

        chinese_datetime = re.match(
            r"^(\d{4})年(\d{1,2})月(\d{1,2})日(?:\s+(\d{1,2}):(\d{2})(?::(\d{2}))?)?",
            text,
        )
        if chinese_datetime:
            year, month, day, hour, minute, second = chinese_datetime.groups()
            china_timezone = timezone(timedelta(hours=8), name="Asia/Shanghai")
            return datetime(
                int(year),
                int(month),
                int(day),
                int(hour or 0),
                int(minute or 0),
                int(second or 0),
                tzinfo=china_timezone,
            ).isoformat()

        try:
            parsed = parsedate_to_datetime(text)
            if parsed.tzinfo is not None:
                china_timezone = timezone(timedelta(hours=8), name="Asia/Shanghai")
                parsed = parsed.astimezone(china_timezone)
            return parsed.isoformat()
        except (TypeError, ValueError, IndexError, OverflowError):
            return text
