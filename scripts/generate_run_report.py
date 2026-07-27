#!/usr/bin/env python3
"""Generate run report for a decomposition pipeline run."""

import argparse
import os
import sys
from datetime import datetime, timezone

import yaml

sys.path.insert(0, os.path.dirname(__file__))
from artifact_utils import read_frontmatter


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-time", required=True)
    parser.add_argument("--batch-size", type=int, default=25)
    parser.add_argument("ids", nargs="*")
    opts = parser.parse_args()

    ids = opts.ids
    if not ids:
        ids_file = "tmp/pipeline-all-ids.txt"
        if os.path.exists(ids_file):
            with open(ids_file) as f:
                ids = [line.strip() for line in f if line.strip()]

    if not ids:
        print("No IDs to report on", file=sys.stderr)
        sys.exit(1)

    end_time = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    results = []
    criterion_violations = {}   # criterion -> total issue count across batch
    criterion_affected = {}     # criterion -> count of strategies with this criterion violated
    review_count = 0

    for strat_id in ids:
        entry = {"strat_id": strat_id, "status": "missing"}
        decomp = f"artifacts/epic-tasks/{strat_id}-decomposition.md"
        review = f"artifacts/epic-reviews/{strat_id}-decomp-review.md"

        if os.path.exists(decomp):
            data, _ = read_frontmatter(decomp)
            entry["epic_count"] = data.get("epic_count", 0)
            entry["status"] = "decomposed"

        if os.path.exists(review):
            review_count += 1
            data, _ = read_frontmatter(review)
            if data.get("error"):
                entry["status"] = "error"
                entry["error"] = data["error"]
            elif data.get("pass"):
                entry["status"] = "passed"
                entry["score"] = data.get("score")
            else:
                entry["status"] = "failed"
                entry["score"] = data.get("score")

            # Accumulate per-criterion violation stats from the structured issues list.
            seen_criteria = set()
            for issue in (data.get("issues") or []):
                crit = issue.get("criterion", "") if isinstance(issue, dict) else ""
                if crit:
                    criterion_violations[crit] = criterion_violations.get(crit, 0) + 1
                    seen_criteria.add(crit)
            for crit in seen_criteria:
                criterion_affected[crit] = criterion_affected.get(crit, 0) + 1

        results.append(entry)

    # Compute per-criterion pass rate: fraction of reviewed strategies with no
    # violation for that criterion.
    per_criterion_stats = {}
    for crit in sorted(criterion_violations):
        total_v = criterion_violations[crit]
        affected = criterion_affected.get(crit, 0)
        pass_rate = round(1.0 - (affected / review_count), 4) if review_count > 0 else 0.0
        per_criterion_stats[crit] = {
            "violation_count": total_v,
            "pass_rate": pass_rate,
        }

    report = {
        "started": opts.start_time,
        "completed": end_time,
        "batch_size": opts.batch_size,
        "total": len(ids),
        "results": results,
        "per_criterion_stats": per_criterion_stats,
        # C2 placeholder keys — populated by Issue 5 (triage) and Issue 6
        # (signal_consistency).  Rendered as the string "not collected" (not
        # null, not absent) so downstream code that keys into these fields
        # does not raise KeyError.
        "triage": {
            "abstention_rate": "not collected",
            "abstained_count": "not collected",
        },
        "signal_consistency": {
            "tier_distribution": {
                "high": "not collected",
                "medium": "not collected",
                "unresolved": "not collected",
            }
        },
    }

    os.makedirs("artifacts/decompose-runs", exist_ok=True)
    ts = opts.start_time.replace(":", "-")
    report_path = f"artifacts/decompose-runs/{ts}.yaml"
    with open(report_path, "w") as f:
        yaml.dump(report, f, default_flow_style=False, sort_keys=False)

    print(f"Report written to {report_path}")


if __name__ == "__main__":
    main()
