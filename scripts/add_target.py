"""Scaffold a new target: register it in targets.json and set up its docs/ folder.

Usage:
  python scripts/add_target.py <id> <name> <listing_date> [--split-date YYYY-MM-DD --split-ratio N]

Example:
  python scripts/add_target.py 00670L "富邦台灣加權正2" 2019-04-01

After this script finishes, backfill history and generate the first JSON output with:
  python -m src.main_p1 --ticker <id>
  python -m src.main_p2 --ticker <id>
  python -m src.main_p3 --ticker <id>

From then on, the daily GitHub Actions workflow picks up the new target
automatically -- no new repo, folder, or frontend code needed.
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TARGETS_JSON = PROJECT_ROOT / "targets.json"
SHARED_DOCS = PROJECT_ROOT / "docs" / "_shared"
DOCS_TARGETS_JSON = PROJECT_ROOT / "docs" / "targets.json"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("id", help="Ticker id, e.g. 00631L")
    parser.add_argument("name", help="Chinese display name, e.g. 元大台灣50正2")
    parser.add_argument("listing_date", help="YYYY-MM-DD")
    parser.add_argument("--split-date", default=None, help="YYYY-MM-DD, omit if the target never split")
    parser.add_argument("--split-ratio", type=float, default=1.0)
    args = parser.parse_args()

    config = json.loads(TARGETS_JSON.read_text(encoding="utf-8"))
    if any(t["id"] == args.id for t in config["targets"]):
        raise SystemExit(f"'{args.id}' already exists in targets.json")

    config["targets"].append({
        "id": args.id,
        "name": args.name,
        "listing_date": args.listing_date,
        "split_date": args.split_date,
        "split_ratio": args.split_ratio,
    })
    TARGETS_JSON.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"已加入 targets.json：{args.id}")

    dest = PROJECT_ROOT / "docs" / args.id
    dest.mkdir(parents=True, exist_ok=True)
    for item in SHARED_DOCS.iterdir():
        if item.is_file():
            text = item.read_text(encoding="utf-8")
            text = text.replace("__TARGET_ID__", args.id)
            (dest / item.name).write_text(text, encoding="utf-8")
    print(f"已建立前端頁面：docs/{args.id}/")

    DOCS_TARGETS_JSON.write_text(TARGETS_JSON.read_text(encoding="utf-8"), encoding="utf-8")
    print("已同步 docs/targets.json")

    print("\n接下來請執行（依序）：")
    print(f"  python -m src.main_p1 --ticker {args.id}")
    print(f"  python -m src.main_p2 --ticker {args.id}")
    print(f"  python -m src.main_p3 --ticker {args.id}")
    print("完成後 commit + push，之後每日排程會自動更新這個標的。")


if __name__ == "__main__":
    main()
