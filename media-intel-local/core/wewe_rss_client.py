import json
import os
import subprocess
import time
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urljoin
from urllib.request import Request, urlopen


class WeweRssError(RuntimeError):
    pass


class WeweRssClient:
    def __init__(
        self,
        project_root: Path,
        base_url: str = "http://127.0.0.1:4000",
        auth_code: str = "",
        tool_dir: str = "../external-tools/wewe-rss",
        auto_start: bool = True,
        startup_timeout_seconds: int = 30,
    ) -> None:
        self.project_root = project_root
        self.base_url = base_url.rstrip("/")
        self.auth_code = auth_code
        self.tool_dir = self._project_path(tool_dir)
        self.auto_start = auto_start
        self.startup_timeout_seconds = startup_timeout_seconds
        self.runtime_dir = self.project_root / ".runtime" / "wewe_rss"
        self.cache_path = self.runtime_dir / "feeds_cache.json"

    def resolve_article_link(self, article_link: str, limit: int = 50) -> Dict[str, Any]:
        article_link = article_link.strip()
        if not article_link:
            raise WeweRssError("empty WeWe article link")
        if not article_link.startswith("https://mp.weixin.qq.com/s/"):
            raise WeweRssError(
                "WeWe auto add only accepts mp.weixin.qq.com article links"
            )

        self.ensure_running()
        cache = self._load_cache()
        cached = cache.get(article_link)
        if isinstance(cached, dict) and cached.get("feed_url"):
            return cached

        info = self._get_mp_info(article_link)
        if not info:
            raise WeweRssError("WeWe did not return mp info for {}".format(article_link))

        self._add_feed(info)
        self._refresh_articles(str(info["id"]))

        feed_url = self.feed_url(str(info["id"]), limit=limit)
        record = {
            "id": info.get("id", ""),
            "mpName": info.get("name", ""),
            "mpCover": info.get("cover", ""),
            "mpIntro": info.get("intro", ""),
            "updateTime": info.get("updateTime"),
            "feed_url": feed_url,
            "article_link": article_link,
            "resolved_at": datetime.now().isoformat(timespec="seconds"),
        }
        cache[article_link] = record
        self._save_cache(cache)
        return record

    def login_with_scan(
        self,
        open_browser: bool = True,
        timeout_seconds: int = 180,
        poll_interval_seconds: int = 3,
    ) -> Dict[str, Any]:
        self.ensure_running()
        login_data = self.create_login_url()
        if not isinstance(login_data, dict) or not login_data.get("uuid"):
            raise WeweRssError("WeWe did not return a login uuid")

        scan_url = str(login_data.get("scanUrl") or "")
        if open_browser and scan_url:
            webbrowser.open(scan_url)

        deadline = time.time() + timeout_seconds
        last_message = ""
        while time.time() < deadline:
            result = self.get_login_result(str(login_data["uuid"]))
            if isinstance(result, dict):
                if result.get("vid") and result.get("token"):
                    account = self.add_account(result)
                    return {
                        "scanUrl": scan_url,
                        "login": result,
                        "account": account,
                    }
                last_message = str(result.get("message") or "")
            time.sleep(poll_interval_seconds)

        raise WeweRssError(
            "WeWe login timed out. scanUrl={}, last_message={}".format(
                scan_url, last_message
            )
        )

    def create_login_url(self) -> Dict[str, Any]:
        result = self._trpc_mutation("platform.createLoginUrl", {})
        if isinstance(result, dict):
            return result
        return {}

    def get_login_result(self, login_id: str) -> Dict[str, Any]:
        result = self._trpc_query("platform.getLoginResult", {"id": login_id})
        if isinstance(result, dict):
            return result
        return {}

    def add_account(self, login_result: Dict[str, Any]) -> Dict[str, Any]:
        return self._add_account(login_result)

    def feed_url(self, mp_id: str, limit: int = 50) -> str:
        query = urlencode({"limit": int(limit), "mode": "list"})
        return "{}/feeds/{}.rss?{}".format(self.base_url, mp_id, query)

    def ensure_running(self) -> None:
        if self._is_running():
            return
        if not self.auto_start:
            raise WeweRssError(
                "WeWe RSS is not running at {} and auto_start is false".format(
                    self.base_url
                )
            )
        self._start_server()
        deadline = time.time() + self.startup_timeout_seconds
        while time.time() < deadline:
            if self._is_running():
                return
            time.sleep(1)
        raise WeweRssError(
            "WeWe RSS did not become ready at {} within {} seconds".format(
                self.base_url, self.startup_timeout_seconds
            )
        )

    def _is_running(self) -> bool:
        try:
            self._request("GET", "/", timeout_seconds=3, parse_json=False)
            return True
        except WeweRssError:
            return False

    def _start_server(self) -> None:
        server_dir = self.tool_dir / "apps" / "server"
        dist_main = server_dir / "dist" / "main.js"
        if not dist_main.exists():
            raise WeweRssError(
                "WeWe RSS server build not found at {}; run pnpm build first".format(
                    dist_main
                )
            )

        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        stdout_path = self.runtime_dir / "server.stdout.log"
        stderr_path = self.runtime_dir / "server.stderr.log"
        stdout_file = stdout_path.open("ab")
        stderr_file = stderr_path.open("ab")

        env = os.environ.copy()
        env.setdefault("HOST", "127.0.0.1")
        env.setdefault("PORT", "4000")
        env.setdefault("DATABASE_TYPE", "sqlite")
        env.setdefault(
            "DATABASE_URL",
            "file:{}".format((server_dir / "data" / "wewe-rss-abs.db").as_posix()),
        )
        env.setdefault("SERVER_ORIGIN_URL", self.base_url)
        env.setdefault("FEED_MODE", "fulltext")

        creationflags = 0
        if os.name == "nt":
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP
            if hasattr(subprocess, "DETACHED_PROCESS"):
                creationflags |= subprocess.DETACHED_PROCESS

        subprocess.Popen(
            [str(self._node_command()), str(dist_main)],
            cwd=str(server_dir),
            env=env,
            stdout=stdout_file,
            stderr=stderr_file,
            stdin=subprocess.DEVNULL,
            creationflags=creationflags,
        )

    def _get_mp_info(self, article_link: str) -> Dict[str, Any]:
        result = self._trpc_mutation("platform.getMpInfo", {"wxsLink": article_link})
        if isinstance(result, list) and result:
            first = result[0]
            if isinstance(first, dict):
                return first
        return {}

    def _add_feed(self, info: Dict[str, Any]) -> Dict[str, Any]:
        payload = {
            "id": str(info.get("id") or ""),
            "mpName": str(info.get("name") or ""),
            "mpCover": str(info.get("cover") or ""),
            "mpIntro": str(info.get("intro") or ""),
            "updateTime": int(info.get("updateTime") or int(time.time())),
            "status": 1,
        }
        return self._trpc_mutation("feed.add", payload)

    def _refresh_articles(self, mp_id: str) -> Any:
        return self._trpc_mutation("feed.refreshArticles", {"mpId": mp_id})

    def _add_account(self, login_result: Dict[str, Any]) -> Dict[str, Any]:
        payload = {
            "id": str(login_result.get("vid") or ""),
            "name": str(login_result.get("username") or ""),
            "token": str(login_result.get("token") or ""),
            "status": 1,
        }
        return self._trpc_mutation("account.add", payload)

    def _trpc_mutation(self, path: str, payload: Dict[str, Any]) -> Any:
        response = self._request(
            "POST",
            "/trpc/{}".format(path),
            body=payload,
            timeout_seconds=180,
        )
        return self._unwrap_trpc_response(response)

    def _trpc_query(self, path: str, payload: Dict[str, Any]) -> Any:
        encoded = quote(json.dumps(payload, ensure_ascii=False), safe="")
        response = self._request(
            "GET",
            "/trpc/{}?input={}".format(path, encoded),
            timeout_seconds=130,
        )
        return self._unwrap_trpc_response(response)

    def _request(
        self,
        method: str,
        path: str,
        body: Optional[Dict[str, Any]] = None,
        timeout_seconds: int = 30,
        parse_json: bool = True,
    ) -> Any:
        url = urljoin(self.base_url + "/", path.lstrip("/"))
        data = None
        headers = {"User-Agent": "media-intel-local/1.0 WeWe client"}
        if self.auth_code:
            headers["authorization"] = self.auth_code
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = Request(url, data=data, headers=headers, method=method)
        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                raw = response.read().decode("utf-8", errors="replace")
        except HTTPError as exc:
            raw_error = exc.read().decode("utf-8", errors="replace")
            message = self._error_message(raw_error) or raw_error
            raise WeweRssError(
                "WeWe request {} {} failed with HTTP {}: {}".format(
                    method, url, exc.code, message
                )
            )
        except URLError as exc:
            raise WeweRssError(
                "WeWe request {} {} failed: {}".format(method, url, exc)
            )
        if not parse_json:
            return raw
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise WeweRssError("WeWe returned non-JSON response: {}".format(exc))

    def _unwrap_trpc_response(self, payload: Any) -> Any:
        if isinstance(payload, list):
            if not payload:
                return None
            payload = payload[0]
        if not isinstance(payload, dict):
            return payload
        if payload.get("error"):
            error = payload["error"]
            if isinstance(error, dict):
                raise WeweRssError(error.get("message") or json.dumps(error))
            raise WeweRssError(str(error))
        result = payload.get("result")
        if isinstance(result, dict):
            data = result.get("data")
            if isinstance(data, dict) and "json" in data:
                return data["json"]
            return data
        return payload

    def _error_message(self, raw_error: str) -> str:
        try:
            payload = json.loads(raw_error)
        except json.JSONDecodeError:
            return ""
        if isinstance(payload, dict):
            error = payload.get("error")
            if isinstance(error, dict):
                return str(error.get("message") or "")
        return ""

    def _load_cache(self) -> Dict[str, Any]:
        try:
            with self.cache_path.open("r", encoding="utf-8") as file_obj:
                payload = json.load(file_obj)
            if isinstance(payload, dict):
                return payload
        except (OSError, json.JSONDecodeError):
            pass
        return {}

    def _save_cache(self, cache: Dict[str, Any]) -> None:
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        with self.cache_path.open("w", encoding="utf-8") as file_obj:
            json.dump(cache, file_obj, ensure_ascii=False, indent=2)
            file_obj.write("\n")

    def _project_path(self, value: str) -> Path:
        path = Path(str(value))
        if path.is_absolute():
            return path
        return (self.project_root / path).resolve()

    def _node_command(self) -> Path:
        packaged_node = (self.project_root / ".." / "nodejs" / "node.exe").resolve()
        if packaged_node.exists():
            return packaged_node
        return Path("node")
