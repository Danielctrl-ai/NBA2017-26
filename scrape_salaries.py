"""
Scrapes the top-10 highest-paid NBA players for each of the last 10 seasons
from Spotrac rankings pages.

Output: data/salaries_raw.csv
"""

import csv
import os
import time
import random

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

from driver_setup import get_driver

# ---------------------------------------------------------------------------
# robots.txt compliance (User-agent: * group on spotrac.com)
# ---------------------------------------------------------------------------
# Spotrac's robots.txt specifies "Crawl-delay: 5" for general user agents.
# floor of 5 seconds between page loads — never go below this.
CRAWL_DELAY_SECONDS = 5

# Paths disallowed for general crawlers per spotrac.com/robots.txt. This
# script never touches any of these, but they're listed here as a guardrail
# and a reference if you extend the script later.
DISALLOWED_PATH_FRAGMENTS = [
    "/nba/trade-machine/",
    "/application/",
    "/system/",
    "/vendor/",
    "/assets/",
    "/login/",
    "/dashboard/",
    "filter=",
    "page=",
    "search=",
]


def assert_path_allowed(url: str) -> None:
    """Hard stop if a constructed URL touches a disallowed path/param."""
    for fragment in DISALLOWED_PATH_FRAGMENTS:
        if fragment in url:
            raise ValueError(
                f"URL '{url}' matches a path disallowed by spotrac.com/robots.txt "
                f"('{fragment}'). Refusing to request it."
            )

# ---------------------------------------------------------------------------
# CONFIG — adjust these after inspecting the live page
# ---------------------------------------------------------------------------

# The "FULL RANKS" page behind the Cap Hit box on /nba/rankings/{year}/.
# The summary page itself only lists the top 5, so we go straight here.
BASE_URL_TEMPLATE = "https://www.spotrac.com/nba/rankings/player/_/year/{year}/sort/cap_total"

# Last 10 seasons, including the current one (adjust as needed)
CURRENT_SEASON = 2026
SEASONS = list(range(CURRENT_SEASON - 9, CURRENT_SEASON + 1))  # e.g. 2017-2026

TOP_N = 10

# SELECTORS = {
#     # The table row that holds one player's ranking data.
#     "row": "table.rankings tbody tr",
#     # Relative-to-row selectors for each column — VERIFY these class names.
#     "rank": "td.rank",
#     "player_name": "td.player a",
#     "team": "td.team",
#     "salary": "td.cap span, td.salary",
# }
SELECTORS = {
    # One player row on the full Cap Hit rankings page, already sorted by cap hit.
    "row": "ul.list-group li.list-group-item",
    # Relative-to-row selectors (all verified on the live page).
    "player_name": "div.link a",
    "team": "small",  # Holds "GSW, PG"; split on ", " to get team and position.
    "salary": "span.medium",
}

OUTPUT_PATH = os.path.join("data", "salaries_raw.csv")


def scrape_season(driver, season: int) -> list[dict]:
    url = BASE_URL_TEMPLATE.format(year=season)
    assert_path_allowed(url)
    print(f"[salaries] Loading {url}")
    driver.get(url)

    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, SELECTORS["row"]))
        )
    except TimeoutException:
        print(f"[salaries]  ! Table not found for season {season} — check selector/URL")
        return []

    rows = driver.find_elements(By.CSS_SELECTOR, SELECTORS["row"])
    results = []

    for row in rows[:TOP_N]:
        try:
            player = row.find_element(By.CSS_SELECTOR, SELECTORS["player_name"]).text.strip()
            team_position = row.find_element(By.CSS_SELECTOR, SELECTORS["team"]).text.strip()
            salary = row.find_element(By.CSS_SELECTOR, SELECTORS["salary"]).text.strip()
        except Exception as e:
            print(f"[salaries]  ! Skipping a row (selector mismatch): {e}")
            continue

        team, _, position = team_position.partition(", ")
        results.append(
            {
                "season": season,
                "player_name": player,
                "team": team,
                "position": position,
                "salary": salary,
            }
        )

    print(f"[salaries]  -> collected {len(results)} players for {season}")
    return results


def main():
    os.makedirs("data", exist_ok=True)
    driver = get_driver(headless=True)
    all_rows = []

    try:
        for season in SEASONS:
            all_rows.extend(scrape_season(driver, season))
            # robots.txt requires Crawl-delay: 5 for general user agents.
            # Add a little jitter on top so requests don't look robotically
            # uniform, but never dip below the mandated 5-second floor.
            time.sleep(CRAWL_DELAY_SECONDS + random.uniform(0, 1.5))
    finally:
        driver.quit()

    if not all_rows:
        print("[salaries] No data collected. Fix selectors/URL and re-run.")
        return

    with open(OUTPUT_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["season", "player_name", "team", "position", "salary"])
        writer.writeheader()
        writer.writerows(all_rows)

    print(f"[salaries] Saved {len(all_rows)} rows to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
