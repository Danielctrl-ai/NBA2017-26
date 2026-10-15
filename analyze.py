"""
Analyzes output/nba_top10_salary_performance.csv (built by merge_export.py):
cost per point, best/worst value contracts, and how well salary predicts
on-court impact among each season's 10 highest-paid players.

Writes:
  images/salary_vs_impact.png   chart used in the README
  output/player_season_value.csv per player-season value metrics
"""

import os

import matplotlib.pyplot as plt
import pandas as pd

MERGED_PATH = os.path.join("output", "nba_top10_salary_performance.csv")
CHART_PATH = os.path.join("images", "salary_vs_impact.png")
VALUE_PATH = os.path.join("output", "player_season_value.csv")

# Missing half an 82-game season or more
LOW_AVAILABILITY_GP = 41

# Palette (light surface)
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
BLUE = "#2a78d6"
ORANGE = "#eb6834"


def season_label(season: int) -> str:
    return f"{season}-{str(season + 1)[-2:]}"


def load() -> pd.DataFrame:
    df = pd.read_csv(MERGED_PATH)
    # The latest season's salaries are scraped before any games are played
    df = df[df["season"] < df["season"].max()].copy()
    df["season_label"] = df["season"].apply(season_label)
    df["salary_m"] = df["salary_usd"] / 1e6
    df["total_pts"] = df["pts"] * df["gp"]
    df["cost_per_point"] = df["salary_usd"] / df["total_pts"]
    df["cost_per_game"] = df["salary_usd"] / df["gp"]
    # Salary as a multiple of that season's top-10 average, so 2017 and
    # 2025 contracts are comparable despite cap growth
    df["salary_rel"] = df["salary_usd"] / df.groupby("season")["salary_usd"].transform("mean")
    return df


def spearman(a: pd.Series, b: pd.Series) -> float:
    return a.rank().corr(b.rank())


def report(df: pd.DataFrame, played: pd.DataFrame) -> None:
    pd.set_option("display.width", 200)
    cols = ["season_label", "player_name", "salary_m", "gp", "pts", "dpm", "cost_per_point"]

    print("== Cost per point by season (median, top-10 earners who played) ==")
    by_season = played.groupby("season_label").agg(
        players=("gp", "size"),
        median_salary_m=("salary_m", "median"),
        avg_gp=("gp", "mean"),
        median_cost_per_point=("cost_per_point", "median"),
    )
    print(by_season.round(1).to_string(), "\n")

    zero = df[df["gp"].isna()]
    print(f"== Player-seasons with no games played: {len(zero)} "
          f"(${zero['salary_usd'].sum() / 1e6:.1f}M) ==")
    print(zero[["season_label", "player_name", "salary_m"]].round(1).to_string(index=False), "\n")

    print("== Best value (lowest cost per point) ==")
    print(played.nsmallest(5, "cost_per_point")[cols].round(1).to_string(index=False), "\n")
    print("== Worst value (highest cost per point) ==")
    print(played.nlargest(5, "cost_per_point")[cols].round(1).to_string(index=False), "\n")
    print("== Lowest impact (DPM) ==")
    print(played.nsmallest(5, "dpm")[cols].round(1).to_string(index=False), "\n")

    print("== Does salary predict performance? (salary vs. season top-10 avg) ==")
    for metric in ["dpm", "pts", "ts_pct", "gp"]:
        r = played["salary_rel"].corr(played[metric])
        print(f"  {metric:7s} pearson r={r:+.2f}  r^2={r * r:.2f}  "
              f"spearman={spearman(played['salary_rel'], played[metric]):+.2f}")
    print()


def plot(played: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(9, 5.6), dpi=150)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)

    healthy = played[played["gp"] >= LOW_AVAILABILITY_GP]
    hurt = played[played["gp"] < LOW_AVAILABILITY_GP]
    ax.scatter(healthy["salary_rel"], healthy["dpm"], s=46, color=BLUE,
               edgecolor=SURFACE, linewidth=1.5, zorder=3,
               label=f"Played {LOW_AVAILABILITY_GP}+ games")
    ax.scatter(hurt["salary_rel"], hurt["dpm"], s=46, color=ORANGE,
               edgecolor=SURFACE, linewidth=1.5, zorder=3,
               label=f"Played under {LOW_AVAILABILITY_GP} games")

    # Least-squares trend line
    x, y = played["salary_rel"], played["dpm"]
    slope = x.cov(y) / x.var()
    intercept = y.mean() - slope * x.mean()
    xs = pd.Series([x.min(), x.max()])
    ax.plot(xs, intercept + slope * xs, color=INK_2, linewidth=1.5,
            linestyle="--", zorder=2)
    r = x.corr(y)
    ax.text(0.99, 0.02, f"Dashed line: linear trend\nr = {r:.2f}, R² = {r * r:.2f}",
            transform=ax.transAxes, ha="right", va="bottom", fontsize=9, color=INK_2)

    callouts = {
        ("Bradley Beal", 2024): (8, -4),
        ("Russell Westbrook", 2021): (8, -4),
        ("Nikola Jokic", 2023): (8, 2),
        ("LeBron James", 2017): (-8, 2),
        ("James Harden", 2018): (8, -10),
        ("Stephen Curry", 2019): (8, 2),
    }
    for (name, season), (dx, dy) in callouts.items():
        row = played[(played["player_name"] == name) & (played["season"] == season)]
        if row.empty:
            continue
        row = row.iloc[0]
        ax.annotate(f"{name} {season_label(season)}",
                    (row["salary_rel"], row["dpm"]), xytext=(dx, dy),
                    textcoords="offset points", fontsize=8.5, color=INK,
                    ha="left" if dx > 0 else "right")

    ax.axhline(0, color=MUTED, linewidth=1, zorder=1)
    ax.grid(True, color=GRID, linewidth=0.8, zorder=0)
    for side in ["top", "right", "left"]:
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(MUTED)
    ax.tick_params(colors=INK_2, length=0, labelsize=9)
    ax.xaxis.set_major_formatter(lambda v, _: f"{v:.2f}×")

    ax.set_xlabel("Salary relative to that season's top-10 average", color=INK_2, fontsize=10)
    ax.set_ylabel("DPM (on-court impact)", color=INK_2, fontsize=10)
    fig.suptitle("Among the NBA's 10 highest-paid players, salary barely predicts impact",
                 x=0.06, ha="left", fontsize=13, color=INK, fontweight="bold")
    ax.set_title("Each dot is one player-season, 2017-18 to 2025-26",
                 loc="left", fontsize=10, color=INK_2, pad=10)
    ax.legend(loc="lower left", frameon=False, fontsize=9, labelcolor=INK_2)

    fig.tight_layout()
    os.makedirs(os.path.dirname(CHART_PATH), exist_ok=True)
    fig.savefig(CHART_PATH, facecolor=SURFACE)
    print(f"[analyze] Saved chart to {CHART_PATH}")


def main():
    if not os.path.exists(MERGED_PATH):
        raise FileNotFoundError("Run merge_export.py first to build " + MERGED_PATH)

    df = load()
    played = df[df["gp"].notna()].copy()

    report(df, played)
    plot(played)

    played.sort_values("cost_per_point")[
        ["season_label", "player_name", "team", "salary_usd", "gp", "pts",
         "dpm", "salary_rel", "cost_per_point", "cost_per_game"]
    ].round(2).to_csv(VALUE_PATH, index=False)
    print(f"[analyze] Saved value table to {VALUE_PATH}")


if __name__ == "__main__":
    main()
