#!/usr/bin/env python3
"""analyse.py - summarise results/transfers.csv per tag.
    python3 tests/analyse.py [--tag-prefix E2_] [--csv path]
"""
import argparse, csv, os
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=os.path.join(HERE, "..", "results", "transfers.csv"))
    ap.add_argument("--tag-prefix", default="")
    args = ap.parse_args()

    groups = defaultdict(list)
    with open(args.csv, newline="") as f:
        for r in csv.DictReader(f):
            if r["tag"].startswith(args.tag_prefix):
                groups[r["tag"]].append(r)
    if not groups:
        raise SystemExit("no rows found in " + args.csv)

    print(f"{'tag':<16}{'runs':>5}{'fail':>5}{'min s':>8}{'avg s':>8}{'max s':>8}"
          f"{'avg Mbps':>10}{'slowest':>9}{'aggr Mbps':>11}")
    for tag in sorted(groups):
        rows = groups[tag]
        good = [r for r in rows if r["ok"] == "1"]
        if not good:
            print(f"{tag:<16}{len(rows):>5}{len(rows):>5}   (all failed)")
            continue
        secs = [float(r["seconds"]) for r in good]
        mbps = [float(r["mbps"]) for r in good]
        start = min(float(r["time"]) for r in good)
        end = max(float(r["time"]) + float(r["seconds"]) for r in good)
        aggr = sum(int(r["size_bytes"]) for r in good) * 8 / (end - start) / 1e6
        print(f"{tag:<16}{len(rows):>5}{len(rows) - len(good):>5}"
              f"{min(secs):>8.2f}{sum(secs) / len(secs):>8.2f}{max(secs):>8.2f}"
              f"{sum(mbps) / len(mbps):>10.2f}{min(mbps):>9.2f}{aggr:>11.2f}")


if __name__ == "__main__":
    main()
