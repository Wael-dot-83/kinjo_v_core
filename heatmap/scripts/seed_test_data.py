"""
Seed the heatmap pipeline with test data and print summary stats.

Usage:
    python scripts/seed_test_data.py
    python scripts/seed_test_data.py --csv path/to/file.csv
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

# Allow running from project root or scripts/ dir
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.etl.pipeline import run_pipeline
from backend.analytics.stats import compute_full_stats, stats_to_csv
from backend.etl.compute import INDICATOR_MAP
from backend.etl.ingest import ingest_csv


def main():
    parser = argparse.ArgumentParser(description="Seed heatmap with test data")
    parser.add_argument("--csv", default=str(Path(__file__).parent.parent / "data" / "test_data.csv"))
    args = parser.parse_args()

    csv_path = Path(args.csv)
    print(f"\n{'='*60}")
    print(f"  Jordan Heatmap ETL — Seed Run")
    print(f"  Source: {csv_path}")
    print(f"{'='*60}\n")

    # Run full pipeline
    result = run_pipeline(csv_path, source_type="csv")

    print(f"Rows processed : {result['rows_processed']}")
    print(f"Validation errors: {len(result['errors'])}")
    print(f"Alerts generated : {len(result['alerts'])}")

    # Print stats
    clean_df, errors = ingest_csv(csv_path)
    if not clean_df.empty:
        from backend.etl.compute import compute_dataframe, impute_missing
        computed = compute_dataframe(impute_missing(clean_df))
        stats = compute_full_stats(computed, INDICATOR_MAP)
        print("\n--- Correlation & OLS Summary ---")
        print(stats[["main_indicator","sub_indicator","pearson_r","p_value","beta_std","high_impact"]].to_string(index=False))
        print("\n--- CSV export preview ---")
        print(stats_to_csv(stats)[:800])

    if result['errors']:
        print("\n--- Validation Errors ---")
        for e in result['errors'][:5]:
            print(f"  [{e.get('admin_id')}] {e.get('error')}")

    if result['alerts']:
        print("\n--- Triggered Alerts ---")
        for a in result['alerts']:
            print(f"  [{a['severity']}] {a['admin_id']} — {a['rule']}")

    print("\nDone.\n")


if __name__ == "__main__":
    main()
