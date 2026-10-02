# NBA Salary + Performance Scraper — Setup Guide (VS Code)

This project scrapes:
1. Top-10 highest-paid NBA players per season (last 10 years) from Spotrac
2. Matching performance metrics for those players from databallr
3. Merges both into one clean CSV/Excel file

---

## ⚠️ Before you start: read this

Both sites render data with JavaScript and Spotrac actively blocks simple bots,
which is why Selenium (a real browser) is required instead of `requests`.
Before scraping at scale:

- Check each site's **Terms of Service** and **robots.txt**
  (`spotrac.com/robots.txt`, `databallr.com/robots.txt`) for scraping restrictions.
- Add delays between requests (already built into the scripts below) so you
  don't hammer their servers.
- Scrape only what you need (10 years × top 10 = 100 rows) — don't crawl the
  entire site.
- This is intended for personal/analytical use. If you plan to publish or
  redistribute the data commercially, check licensing terms first.
- **Site layouts change.** The CSS selectors in these scripts are starting
  points — you WILL need to open DevTools (see Step 5) and adjust them to
  match the current live HTML before this will reliably work.

---

## Step 1 — Install prerequisites

1. Install **Python 3.10+**: https://www.python.org/downloads/
   - On Windows, check "Add Python to PATH" during install.
2. Install **VS Code**: https://code.visualstudio.com/
3. Install **Google Chrome** (the script uses ChromeDriver): https://www.google.com/chrome/
4. In VS Code, install the **Python extension** (Microsoft) from the
   Extensions panel (`Ctrl+Shift+X` / `Cmd+Shift+X`).

---

## Step 2 — Open the project in VS Code

1. Unzip/copy this project folder somewhere, e.g. `~/nba_scraper`.
2. In VS Code: `File → Open Folder…` → select `nba_scraper`.
3. Open a terminal inside VS Code: `Terminal → New Terminal`.

---

## Step 3 — Create a virtual environment

In the VS Code terminal:

```bash
# Mac/Linux
python3 -m venv venv
source venv/bin/activate

# Windows
python -m venv venv
venv\Scripts\activate
```

You should see `(venv)` appear in your terminal prompt.

In VS Code, also select this interpreter: `Ctrl+Shift+P` → "Python: Select
Interpreter" → choose the one inside `./venv`.

---

## Step 4 — Install dependencies

```bash
pip install -r requirements.txt
```

This installs: `selenium`, `webdriver-manager`, `pandas`, `openpyxl`.

`webdriver-manager` automatically downloads the right ChromeDriver version for
your installed Chrome, so you don't have to manage that manually.

---

## Step 5 — Inspect the live page and fix selectors (IMPORTANT)

Site HTML changes over time, and I can't guarantee the selectors in
`scrape_salaries.py` / `scrape_performance.py` match what's live today. Do
this once before running:

1. Open the target page in Chrome (e.g. `spotrac.com/nba/rankings`).
2. Right-click the data table → **Inspect**.
3. Hover over the row/column elements in DevTools to find the actual CSS
   class names or table structure (e.g. `table.rankings tbody tr`).
4. Update the `SELECTORS` dictionary at the top of each script to match.
5. Do the same for `databallr.com/stats` (look for the table, and note that
   it likely needs a filter/search box interaction to find a specific player
   — the script includes a search-box example you'll need to adjust).

This step is unavoidable with browser scraping — sites don't publish stable
scraping APIs, so selectors are the one part you must verify yourself.

---

## Step 6 — Run the scrapers

```bash
python scrape_salaries.py       # -> data/salaries_raw.csv
python scrape_performance.py    # -> data/performance_raw.csv
python merge_export.py          # -> output/nba_top10_salary_performance.xlsx
```

Run them one at a time so you can fix selector issues before moving to the
next stage. Each script prints progress and errors per season/player so you
can see exactly where it fails.

---

## Step 7 — Check the output

Open `output/nba_top10_salary_performance.xlsx` in Excel, or the `.csv`
version, and confirm:
- 10 seasons × 10 players = up to 100 rows
- Salary + performance columns are both populated
- No duplicate players/seasons

---

## Troubleshooting

| Problem | Likely cause | Fix |
|---|---|---|
| `selenium.common.exceptions.NoSuchElementException` | Selector is outdated | Redo Step 5 for that page |
| Script hangs / times out | Page hasn't finished loading JS | Increase `WebDriverWait` timeout in the script |
| Chrome closes immediately | Bot-detection triggered | Try `headless=False` to watch it happen, add longer random delays, avoid running too many iterations back-to-back |
| Missing players in performance data | Name mismatch (e.g. "Steph Curry" vs "Stephen Curry") | Add name normalization mapping in `merge_export.py` |

