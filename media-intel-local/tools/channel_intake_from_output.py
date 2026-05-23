import argparse
import json
import sys
from pathlib import Path
from typing import Any, List, Dict

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from core.channel_intake import write_channel_intake_outputs  # noqa: E402


def load_normalized_items(path: Path) -> List[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as file_obj:
        payload = json.load(file_obj)
    if not isinstance(payload, list):
        raise ValueError("normalized_items.json must contain a JSON list")
    return [item for item in payload if isinstance(item, dict)]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build trend/hotspot inbox JSONL from an existing normalized_items.json."
    )
    parser.add_argument("--date", required=True, help="Output date in YYYY-MM-DD format")
    parser.add_argument(
        "--input",
        default="",
        help="Path to normalized_items.json. Defaults to output/YYYY-MM-DD/normalized_items.json.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(PROJECT_ROOT / "data" / "inbox"),
        help="Inbox output directory.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    input_path = Path(args.input) if args.input else PROJECT_ROOT / "output" / args.date / "normalized_items.json"
    output_dir = Path(args.output_dir)
    if not input_path.is_absolute():
        input_path = PROJECT_ROOT / input_path
    if not output_dir.is_absolute():
        output_dir = PROJECT_ROOT / output_dir
    items = load_normalized_items(input_path)
    log = write_channel_intake_outputs(items, output_dir, args.date)
    print(
        "wrote platform_trends={}, social_hotspots={}".format(
            log["platform_trends"], log["social_hotspots"]
        )
    )
    print("output_dir {}".format(output_dir))


if __name__ == "__main__":
    main()
