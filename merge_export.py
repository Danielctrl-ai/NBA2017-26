"""
Merges data/salaries_raw.csv and data/performance_raw.csv on player_name + season,
cleans up salary/number formatting, and exports a final combined
CSV + Excel file to output/.
"""

import os
import re
import pandas as pd

SALARIES_PATH = os.path.join("data", "salaries_raw.csv")
PERFORMANCE_PATH = os.path.join("data", "performance_raw.csv")
OUTPUT_DIR = "output"

# If databallr and Spotrac spell a player's name differently
# (e.g. "Steph Curry" vs "Stephen Curry"), map it here.
# NAME_NORMALIZATION = {
#     # "Spotrac Name": "databallr Name",
# }

NAME_NORMALIZATION = {
    "Steph Curry": "Stephen Curry",
    "P.J. Tucker": "PJ Tucker",
}


def clean_salary(value: str) -> float | None:
    if not isinstance(value, str):
        return None
    digits = re.sub(r"[^\d.]", "", value)
    return float(digits) if digits else None


def clean_percent(value: str) -> float | None:
    if not isinstance(value, str):
        return None
    digits = re.sub(r"[^\d.]", "", value)
    return float(digits) if digits else None


def main():
    if not os.path.exists(SALARIES_PATH) or not os.path.exists(PERFORMANCE_PATH):
        raise FileNotFoundError(
            "Run scrape_salaries.py and scrape_performance.py first — "
            "both data/salaries_raw.csv and data/performance_raw.csv are required."
        )

    salaries = pd.read_csv(SALARIES_PATH)
    performance = pd.read_csv(PERFORMANCE_PATH)

    # Normalize names so they match across sources
    salaries["player_name"] = salaries["player_name"].replace(NAME_NORMALIZATION)

    merged = salaries.merge(performance, on=["player_name", "season"], how="left")

    # Clean numeric columns
    merged["salary_usd"] = merged["salary"].apply(clean_salary)
    for col in ["ts_pct", "onball_pct"]:
        if col in merged.columns:
            merged[col] = merged[col].apply(clean_percent)

    merged = merged.sort_values(["season", "salary_usd"], ascending=[True, False])

    missing = merged[merged["gp"].isna()]
    if not missing.empty:
        print(
            f"[merge]  ! {len(missing)} rows have no matching performance data "
            "(unplayed season, player missed the season, or a name mismatch — "
            "add name mismatches to NAME_NORMALIZATION):"
        )
        for _, r in missing.iterrows():
            print(f"    - {r['season']} {r['player_name']}")

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    csv_path = os.path.join(OUTPUT_DIR, "nba_top10_salary_performance.csv")
    xlsx_path = os.path.join(OUTPUT_DIR, "nba_top10_salary_performance.xlsx")

    merged.to_csv(csv_path, index=False)
    merged.to_excel(xlsx_path, index=False, sheet_name="Salary & Performance")

    print(f"[merge] Saved {len(merged)} rows to:\n  {csv_path}\n  {xlsx_path}")


if __name__ == "__main__":
    main()
