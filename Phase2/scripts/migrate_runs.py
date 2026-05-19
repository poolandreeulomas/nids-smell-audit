#!/usr/bin/env python3
"""Migration helper: update saved run JSON files to include new schema defaults.

Usage examples:
  # dry-run: write migrated files to logs/runs/migrated/
  python nids-smell-audit/scripts/migrate_runs.py --out-dir logs/runs/migrated logs/runs/*.json

  # in-place (creates .bak backups)
  python nids-smell-audit/scripts/migrate_runs.py --in-place logs/runs/*.json
"""
from state.schema import AgentState
import argparse
import glob
import json
import os
import sys

# Make sure the package root (nids-smell-audit) is importable when running this script
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


def migrate_file(fp: str, in_place: bool = False, out_dir: str | None = None) -> bool:
    with open(fp, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except Exception as e:
            print(f"[ERR] failed to read JSON {fp}: {e}")
            return False

    # Detect wrapped payloads that hold a 'state' key (common run payloads)
    if isinstance(data, dict) and "state" in data:
        state_payload = data["state"]
        wrapped = True
    else:
        state_payload = data
        wrapped = False

    try:
        state_obj = AgentState.from_dict(state_payload)
    except Exception as e:
        print(f"[ERR] failed to parse state for {fp}: {e}")
        return False

    new_state = state_obj.to_dict()

    if wrapped:
        data["state"] = new_state
    else:
        data = new_state

    if in_place:
        bak = fp + ".bak"
        os.replace(fp, bak)
        out_fp = fp
    else:
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
            out_fp = os.path.join(out_dir, os.path.basename(fp))
        else:
            out_fp = fp.replace(".json", ".migrated.json")

    with open(out_fp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    print(f"[OK] wrote {out_fp}")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Migrate saved run JSON files to include new schema defaults")
    parser.add_argument(
        "paths", nargs="*", default=["logs/runs/*.json"], help="glob(s) matching files to migrate")
    parser.add_argument("--in-place", action="store_true",
                        help="Replace original files (creates .bak backups)")
    parser.add_argument("--out-dir", type=str, default=None,
                        help="Write migrated files to this directory")
    args = parser.parse_args()

    matched = 0
    for pattern in args.paths:
        for fp in glob.glob(pattern):
            matched += 1
            migrate_file(fp, in_place=args.in_place, out_dir=args.out_dir)

    if matched == 0:
        print("No files matched the given patterns. Nothing to do.")


if __name__ == "__main__":
    main()
