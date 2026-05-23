from pathlib import Path
from typing import Any, Dict, List

from crawlers.base import BaseCrawler
from crawlers.external import ExternalCommandError, python_command, run_json_command


class XiaohongshuCrawler(BaseCrawler):
    source_type = "xiaohongshu"

    def fetch(self, source: Dict[str, Any], target_date: str) -> List[Dict[str, Any]]:
        if self._is_mock_source(source):
            items = self._read_mock_items(source)
            return self._filter_by_date(items, "time", target_date)

        candidates = self._load_candidates(source)
        items = [
            self._candidate_to_item(candidate, source, target_date)
            for candidate in candidates
        ]
        if source.get("require_content"):
            items = [item for item in items if str(item.get("desc") or "").strip()]
        return self._filter_by_date(items, "time", target_date)

    def _load_candidates(self, source: Dict[str, Any]) -> List[Dict[str, Any]]:
        mode = str(source.get("mode") or "").strip()
        if mode == "keyword_search":
            payload = self._run_skill(
                source,
                self._search_args(source),
                timeout_seconds=int(source.get("search_timeout_seconds") or 300),
            )
            results = payload.get("results", []) if isinstance(payload, dict) else []
            return [item for item in results if isinstance(item, dict)]
        if mode == "user_profile":
            user_id = str(source.get("user_id") or "").strip()
            if not user_id:
                raise ValueError("xiaohongshu source {} is missing user_id".format(source.get("id", "")))
            args = ["user", user_id]
            if source.get("xsec_token"):
                args.append(str(source["xsec_token"]))
            payload = self._run_skill(
                source,
                args,
                timeout_seconds=int(source.get("profile_timeout_seconds") or 300),
            )
            feeds = payload.get("feeds", []) if isinstance(payload, dict) else []
            return [item for item in feeds if isinstance(item, dict)]
        raise ValueError(
            "xiaohongshu source {} has unsupported mode {}".format(
                source.get("id", ""), mode
            )
        )

    def _search_args(self, source: Dict[str, Any]) -> List[str]:
        keyword = str(source.get("keyword") or "").strip()
        if not keyword:
            raise ValueError("xiaohongshu keyword source {} is missing keyword".format(source.get("id", "")))
        args = ["search", keyword, "--limit={}".format(int(source.get("limit") or 20))]
        option_map = {
            "sort_by": "--sort-by={}",
            "note_type": "--note-type={}",
            "publish_time": "--publish-time={}",
            "search_scope": "--search-scope={}",
            "location": "--location={}",
        }
        for key, template in option_map.items():
            if source.get(key):
                args.append(template.format(source[key]))
        if not source.get("publish_time"):
            args.append("--publish-time=一天内")
        return args

    def _candidate_to_item(
        self, candidate: Dict[str, Any], source: Dict[str, Any], target_date: str
    ) -> Dict[str, Any]:
        detail = candidate
        if source.get("fetch_detail", True):
            feed_id = self._candidate_id(candidate)
            xsec_token = self._candidate_token(candidate)
            if feed_id:
                try:
                    detail = self._run_skill(
                        source,
                        self._detail_args(source, candidate, feed_id, xsec_token),
                        timeout_seconds=int(source.get("detail_timeout_seconds") or 300),
                    )
                except ExternalCommandError as exc:
                    detail = {
                        "detail_error": str(exc),
                        "note": {},
                    }
        return self._to_raw_item(candidate, detail, target_date)

    def _detail_args(
        self,
        source: Dict[str, Any],
        candidate: Dict[str, Any],
        feed_id: str,
        xsec_token: str,
    ) -> List[str]:
        xsec_source = str(
            candidate.get("xsec_source")
            or candidate.get("xsecSource")
            or source.get("xsec_source")
            or "pc_search"
        )
        fallback_sources = source.get("fallback_xsec_sources") or [
            "pc_search",
            "pc_feed",
            "pc_note",
        ]
        if isinstance(fallback_sources, list):
            fallback_value = ",".join(str(item) for item in fallback_sources)
        else:
            fallback_value = str(fallback_sources)
        return [
            "feed",
            feed_id,
            xsec_token,
            "--xsec-source={}".format(xsec_source),
            "--fallback-sources={}".format(fallback_value),
        ]

    def _to_raw_item(
        self, candidate: Dict[str, Any], detail: Dict[str, Any], target_date: str = ""
    ) -> Dict[str, Any]:
        note = detail.get("note") if isinstance(detail, dict) else {}
        if not isinstance(note, dict):
            note = {}
        card = candidate.get("noteCard") if isinstance(candidate, dict) else {}
        if not isinstance(card, dict):
            card = {}
        interact = note.get("interactInfo") or card.get("interactInfo") or {}
        if not isinstance(interact, dict):
            interact = {}
        feed_id = self._candidate_id(candidate) or note.get("noteId") or note.get("id") or ""
        image_list = note.get("imageList") or note.get("images") or []
        raw_time_value = (
            note.get("time")
            or note.get("createTime")
            or detail.get("time")
            or candidate.get("time", "")
        )
        raw_publish_time = self._normalized_datetime(raw_time_value)
        if target_date and candidate.get("xsec_token"):
            normalized_time = target_date
            time_source = "search_window"
        elif raw_publish_time:
            normalized_time = raw_publish_time
            time_source = "raw"
        else:
            normalized_time = target_date
            time_source = "target_date_fallback" if target_date else "missing"

        return {
            "note_title": note.get("title")
            or note.get("displayTitle")
            or candidate.get("title")
            or card.get("displayTitle")
            or self._fallback_title(candidate),
            "note_url": note.get("url")
            or (
                "https://www.xiaohongshu.com/explore/{}".format(feed_id)
                if feed_id
                else ""
            ),
            "time": normalized_time,
            "time_source": time_source,
            "raw_publish_time": raw_publish_time,
            "detail_status": self._detail_status(detail),
            "detail_source": detail.get("detail_source", "") if isinstance(detail, dict) else "",
            "desc": note.get("desc")
            or note.get("description")
            or note.get("content")
            or candidate.get("desc")
            or candidate.get("description")
            or "",
            "likes": self._metric(interact, "likedCount", candidate.get("liked_count")),
            "favorites": self._metric(
                interact, "collectedCount", candidate.get("collected_count")
            ),
            "comments": self._metric(
                interact, "commentCount", candidate.get("comment_count")
            ),
            "images": self._images(image_list, candidate, card),
            "skill_raw": {"candidate": candidate, "detail": detail},
        }

    def _detail_status(self, detail: Dict[str, Any]) -> str:
        if not isinstance(detail, dict):
            return "missing"
        if detail.get("detail_error"):
            return "error"
        if detail.get("detail_status"):
            return str(detail["detail_status"])
        note = detail.get("note")
        if isinstance(note, dict):
            desc = str(note.get("desc") or note.get("description") or note.get("content") or "").strip()
            title = str(note.get("title") or note.get("displayTitle") or "").strip()
            if desc:
                return "content"
            if title:
                return "metadata_only"
        return "card_only"

    def _fallback_title(self, candidate: Dict[str, Any]) -> str:
        user = str(candidate.get("user") or "").strip()
        if user:
            return "小红书笔记 - {}".format(user)
        return "小红书笔记"

    def _candidate_id(self, candidate: Dict[str, Any]) -> str:
        return str(candidate.get("id") or candidate.get("noteId") or "")

    def _candidate_token(self, candidate: Dict[str, Any]) -> str:
        return str(candidate.get("xsec_token") or candidate.get("xsecToken") or "")

    def _metric(self, metrics: Dict[str, Any], key: str, fallback: Any) -> Any:
        value = metrics.get(key)
        if value in (None, ""):
            value = fallback
        if isinstance(value, str):
            digits = value.replace(",", "").strip()
            if digits.isdigit():
                return int(digits)
        return value

    def _images(
        self,
        image_list: Any,
        candidate: Dict[str, Any],
        card: Dict[str, Any],
    ) -> List[Any]:
        images = []
        if isinstance(image_list, list):
            for image in image_list:
                if isinstance(image, str):
                    images.append(image)
                elif isinstance(image, dict):
                    info_list = image.get("infoList") or [{}]
                    image_url = (
                        image.get("urlDefault")
                        or image.get("url")
                        or image.get("urlPre")
                        or info_list[0].get("url", "")
                    )
                    if image_url:
                        images.append(image_url)
        cover = candidate.get("cover_url")
        if not cover and isinstance(card.get("cover"), dict):
            cover = card["cover"].get("urlDefault")
        if cover and cover not in images:
            images.append(cover)
        return images

    def _run_skill(
        self, source: Dict[str, Any], args: List[str], timeout_seconds: int
    ) -> Dict[str, Any]:
        skill_dir = source.get("skill_dir")
        if not skill_dir:
            raise ValueError("xiaohongshu source {} is missing skill_dir".format(source.get("id", "")))
        command = python_command(source.get("skill_python"), self.project_root)
        command.extend(["-m", "scripts"])
        if source.get("cookie_path"):
            command.append("--cookie={}".format(self._project_path(source["cookie_path"])))
        if source.get("headless") is not None:
            command.append("--headless={}".format(str(source["headless"]).lower()))
        command.extend(args)
        payload = run_json_command(
            command,
            cwd=self.project_root / str(skill_dir),
            timeout_seconds=timeout_seconds,
        )
        if not isinstance(payload, dict):
            raise ValueError("xiaohongshu-skill must return a JSON object")
        return payload

    def _project_path(self, value: Any) -> Path:
        path = Path(str(value))
        if path.is_absolute():
            return path
        return self.project_root / path
