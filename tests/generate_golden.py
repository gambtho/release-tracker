#!/usr/bin/env python3
"""Generate the platform golden fixture from build_site.py.

Run this EXACTLY ONCE, against the pre-refactor build_site.py. The committed
output is the byte-for-byte contract that the metric-parameterization refactor
must preserve. If tests/test_build_site_refactor.py ever fails, the refactor is
wrong -- do NOT re-run this script to make the failure go away.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import build_site  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SNAPSHOT_DIR = os.path.join(HERE, "fixtures", "platform_snapshots")
GOLDEN = os.path.join(HERE, "fixtures", "golden_history.json")


def main():
    snapshots = build_site.load_all_snapshots(SNAPSHOT_DIR)
    weekly = build_site.compute_weekly_history(snapshots)
    history = build_site.build_history_json(weekly)
    with open(GOLDEN, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2)
    print("Wrote {}".format(GOLDEN))


if __name__ == "__main__":
    main()
