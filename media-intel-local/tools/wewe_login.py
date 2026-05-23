import argparse
import json
from pathlib import Path
import sys
import time
import webbrowser

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from core.wewe_rss_client import WeweRssClient



def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Login WeWe RSS reader account.")
    parser.add_argument("--base-url", default="http://127.0.0.1:4000")
    parser.add_argument("--auth-code", default="")
    parser.add_argument("--tool-dir", default="../external-tools/wewe-rss")
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument(
        "--no-open-browser",
        action="store_true",
        help="Only print the scan URL instead of opening it.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    client = WeweRssClient(
        project_root=PROJECT_ROOT,
        base_url=args.base_url,
        auth_code=args.auth_code,
        tool_dir=args.tool_dir,
    )
    print("starting or checking WeWe RSS at {}".format(args.base_url))
    client.ensure_running()
    login_data = client.create_login_url()
    scan_url = str(login_data.get("scanUrl") or "")
    print("scan URL: {}".format(scan_url))
    if scan_url and not args.no_open_browser:
        webbrowser.open(scan_url)

    deadline = time.time() + args.timeout
    last_result = {}
    while time.time() < deadline:
        last_result = client.get_login_result(str(login_data.get("uuid") or ""))
        if last_result.get("vid") and last_result.get("token"):
            account = client.add_account(last_result)
            print(json.dumps({"login": last_result, "account": account}, ensure_ascii=False, indent=2))
            return
        if last_result.get("message"):
            print("waiting: {}".format(last_result["message"]))
        time.sleep(3)
    raise SystemExit(
        "login timed out. scan URL: {}, last result: {}".format(
            scan_url, json.dumps(last_result, ensure_ascii=False)
        )
    )


if __name__ == "__main__":
    main()
