"""
Scrapes performance metrics from databallr.com/stats for each (player, season)
found in data/salaries_raw.csv.

databallr's script:
  1. Loads the stats page
  2. For each season, picks it in the season filter
  3. Types each player's name into the search box
  4. Waits for that player's row (for that season) to render
  5. Extracts GP, MIN, PTS, TS%, OnBall % and DPM by column header

Season mapping: Spotrac's "2020" is the 2020-21 salary year, while databallr
labels seasons by the year they end ("2021" = 2020-21). So Spotrac season Y
is looked up as databallr season Y + 1. Seasons databallr doesn't list yet
(e.g. one that hasn't been played) are skipped.

Output: data/performance_raw.csv
"""

import csv
import os
import re
import time
import random
import unicodedata

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException

from driver_setup import get_driver

STATS_URL = "https://databallr.com/stats"

# ---------------------------------------------------------------------------
# robots.txt compliance (User-agent: * group on databallr.com)
# — this list is a guardrail if the script is extended to call an API
# endpoint directly.
DISALLOWED_PATH_FRAGMENTS = [
    "/admin/",
    "/adminfeedback",
    "/ops/",
    "/ops-status",
    "/api/private/",
    "/auth/",
    "/payment-",
    "/subscription",
    "/preview-images",
    "/sixrings/profile",
    "/intern-",
    "/test-",
]


def assert_path_allowed(url: str) -> None:
    for fragment in DISALLOWED_PATH_FRAGMENTS:
        if fragment in url:
            raise ValueError(
                f"URL '{url}' matches a path disallowed by databallr.com/robots.txt "
                f"('{fragment}'). Refusing to request it."
            )


SELECTORS = {
    "search_box": "input[placeholder='Search players...']",
    "season_button": "button[aria-label^='Season filter']",
    "season_select": "select#showcase-single-season",
    "table_row": "table tbody tr",
}

# databallr column header -> (output field, which whitespace-separated token to keep).
# Most cells hold "value percentile" (e.g. "26.6 97"), so token 0 is the value.
# "MIN (mpg)" holds "total_minutes mpg", so the last token is minutes per game.
STAT_COLUMNS = {
    "GP": ("gp", 0),
    "MIN (mpg)": ("min_per_game", -1),
    "PTS": ("pts", 0),
    "TS%": ("ts_pct", 0),
    "OnBall %": ("onball_pct", 0),
    "DPM": ("dpm", 0),
}

# databallr season = Spotrac season + SEASON_OFFSET (see module docstring).
SEASON_OFFSET = 1

INPUT_PATH = os.path.join("data", "salaries_raw.csv")
OUTPUT_PATH = os.path.join("data", "performance_raw.csv")
FIELDNAMES = ["season", "stats_season", "player_name"] + [f for f, _ in STAT_COLUMNS.values()]

# Reads the column headers and every real data row in one pass, so a table
# re-render between Selenium calls can't leave us holding stale elements.
# Rows with only a few cells are the virtual-scroll spacer rows — skip them.
READ_TABLE_JS = r"""
const headRows = document.querySelectorAll('table thead tr');
const headers = headRows.length
    ? [...headRows[headRows.length - 1].querySelectorAll('th')].map(th => th.innerText.replace(/\s+/g, ' ').trim())
    : [];
const rows = [...document.querySelectorAll('table tbody tr')]
    .filter(r => r.querySelectorAll('td').length > 5)
    .map(r => [...r.querySelectorAll('td')].map(td => td.innerText.replace(/\s+/g, ' ').trim()));
return {headers, rows};
"""


def normalize_name(name: str) -> str:
    """'Nikola Jokić' -> 'nikola jokic' so accents/punctuation don't block a match."""
    stripped = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z ]", "", stripped.lower()).strip()


def load_player_list(path: str) -> list[dict]:
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"{path} not found. Run scrape_salaries.py first, or manually "
            "create this CSV with 'season' and 'player_name' columns."
        )
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def available_seasons(driver) -> set[int]:
    select = driver.find_element(By.CSS_SELECTOR, SELECTORS["season_select"])
    return {int(o.get_attribute("value")) for o in Select(select).options if o.get_attribute("value").isdigit()}


def open_season_filter(driver) -> None:
    driver.find_element(By.CSS_SELECTOR, SELECTORS["season_button"]).click()
    WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, SELECTORS["season_select"]))
    )


def select_season(driver, stats_season: int) -> None:
    open_season_filter(driver)
    select = driver.find_element(By.CSS_SELECTOR, SELECTORS["season_select"])
    Select(select).select_by_value(str(stats_season))
    WebDriverWait(driver, 10).until(
        EC.presence_of_element_located(
            (By.CSS_SELECTOR, f"button[aria-label='Season filter: {stats_season}']")
        )
    )
    # Close the filter dialog so the search box is usable again.
    driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
    WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, SELECTORS["table_row"]))
    )


def search_for(driver, text: str) -> None:
    box = driver.find_element(By.CSS_SELECTOR, SELECTORS["search_box"])
    # Ctrl+A / Delete (rather than .clear()) so the React input sees the change.
    box.send_keys(Keys.CONTROL, "a")
    box.send_keys(Keys.DELETE)
    box.send_keys(text)


def find_player_row(driver, player_name: str, stats_season: int) -> dict | None:
    """
    Returns {header: cell_text} for the player's row in stats_season, or None
    if it isn't rendered (yet). The first cell reads like
    "Stephen Curry GSW • PG • 2020", so we match on name prefix and season suffix.
    """
    table = driver.execute_script(READ_TABLE_JS)
    target = normalize_name(player_name)
    for cells in table["rows"]:
        name_cell = cells[0]
        season_match = re.search(r"(\d{4})\s*$", name_cell)
        if not season_match or int(season_match.group(1)) != stats_season:
            continue
        if normalize_name(name_cell).startswith(target):
            return dict(zip(table["headers"], cells))
    return None


def extract_stats(row: dict) -> dict:
    stats = {}
    for header, (field, token_index) in STAT_COLUMNS.items():
        tokens = row.get(header, "").split()
        stats[field] = tokens[token_index] if tokens else ""
    return stats


def scrape_player_stats(driver, player_name: str, stats_season: int) -> dict | None:
    # databallr's search is accent-sensitive ("Jokic" won't find "Jokić"), so if
    # the full name finds nothing, retry with just the first name, then just the
    # last name — find_player_row's accent-insensitive match picks the right row.
    parts = player_name.split()
    queries = [player_name] + ([parts[0], parts[-1]] if len(parts) > 1 else [])
    for query, timeout in zip(queries, (10, 6, 6)):
        search_for(driver, query)
        try:
            # Wait for *this* player's row for *this* season — not just any row,
            # since unfiltered rows are already present before the filter applies.
            row = WebDriverWait(driver, timeout).until(
                lambda d: find_player_row(d, player_name, stats_season)
            )
            return extract_stats(row)
        except TimeoutException:
            continue
    print(f"[performance]  ! No {stats_season} row for {player_name} (didn't play, or name mismatch)")
    return None


def load_stats_page(driver) -> None:
    assert_path_allowed(STATS_URL)
    print(f"[performance] Loading {STATS_URL}")
    driver.get(STATS_URL)
    WebDriverWait(driver, 20).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, SELECTORS["search_box"]))
    )
    WebDriverWait(driver, 20).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, SELECTORS["table_row"]))
    )


def scrape_season(season: int, stats_season: int, names: list[str]) -> list[dict]:
    """
    Scrapes one season in a fresh browser. databallr's page is heavy enough
    that a single headless Chrome crashes after ~60 lookups, so we restart
    per season rather than reusing one driver for the whole run.
    """
    driver = get_driver(headless=True)
    rows = []
    try:
        load_stats_page(driver)
        select_season(driver, stats_season)
        for name in names:
            stats = scrape_player_stats(driver, name, stats_season)
            if stats:
                rows.append({"season": season, "stats_season": stats_season, "player_name": name, **stats})
                print(f"[performance]   {name}: {stats}")
            time.sleep(random.uniform(1.5, 3))
    finally:
        driver.quit()
    return rows


def get_available_seasons() -> set[int]:
    driver = get_driver(headless=True)
    try:
        load_stats_page(driver)
        open_season_filter(driver)
        return available_seasons(driver)
    finally:
        driver.quit()


def save_results(results: list[dict]) -> None:
    os.makedirs("data", exist_ok=True)
    with open(OUTPUT_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(results)


def main():
    players = load_player_list(INPUT_PATH)
    by_season: dict[int, list[str]] = {}
    for p in players:
        if p.get("player_name") and p.get("season"):
            by_season.setdefault(int(p["season"]), []).append(p["player_name"])

    seasons_on_site = get_available_seasons()
    results = []

    for season in sorted(by_season):
        stats_season = season + SEASON_OFFSET
        if stats_season not in seasons_on_site:
            print(
                f"[performance] Skipping {season}: databallr has no {stats_season} "
                "season yet (not played)"
            )
            continue

        print(f"[performance] Season {season} -> databallr {stats_season}")
        for attempt in (1, 2):
            try:
                results.extend(scrape_season(season, stats_season, by_season[season]))
                break
            except WebDriverException as e:
                print(f"[performance]  ! Browser failed on {season} (attempt {attempt}): {e.msg}")
        # Save after every season so a later crash can't lose finished work.
        if results:
            save_results(results)

    if not results:
        print("[performance] No data collected. Fix selectors and re-run.")
        return

    print(f"[performance] Saved {len(results)} rows to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
