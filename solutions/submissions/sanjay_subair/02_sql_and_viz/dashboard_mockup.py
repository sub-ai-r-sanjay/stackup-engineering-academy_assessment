"""Generate the one-page executive spend dashboard as a PDF."""

from __future__ import annotations

import os
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.ticker import FuncFormatter

REPO_ROOT = Path(__file__).resolve().parents[4]
INPUT_DIR = Path(os.getenv("OUTPUT_DIR", REPO_ROOT / "outputs" / "results" / "sanjay_subair" / "02_sql_and_viz"))
OUTPUT_PATH = INPUT_DIR / "dashboard_mockup.pdf"
AED = FuncFormatter(lambda value, _: f"AED {value / 1_000_000:.1f}M")
COLORS = {"budget": "#2B4C7E", "spend": "#E07A5F", "accent": "#2A9D8F", "ink": "#1F2933"}


def _load_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    projects = pd.read_csv(INPUT_DIR / "projects_clean.csv", parse_dates=["start_date", "end_date"])
    transactions = pd.read_csv(INPUT_DIR / "transactions_clean.csv", parse_dates=["transaction_date"])
    return projects, transactions


def generate_dashboard() -> None:
    projects, transactions = _load_data()
    total_budget = projects["budget"].sum()
    total_spend = projects["actual_cost"].sum()
    over_budget_pct = 100 * projects["is_over_budget"].mean()

    department = projects.groupby("department", as_index=False)[["budget", "actual_cost"]].sum()
    monthly = (
        transactions.assign(month=transactions["transaction_date"].dt.to_period("M").dt.to_timestamp())
        .groupby(["month", "category"], as_index=False)["amount_aed"].sum()
    )
    leading_categories = transactions.groupby("category")["amount_aed"].sum().nlargest(5).index
    monthly = monthly[monthly["category"].isin(leading_categories)]
    top_projects = projects.nlargest(10, "budget_variance")[
        ["project_name", "department", "budget_variance"]
    ]
    vendors = transactions.groupby("vendor_name")["amount_aed"].sum().sort_values(ascending=False)
    vendor_pie = vendors.head(5).copy()
    vendor_pie.loc["Other"] = vendors.iloc[5:].sum()

    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 8, "axes.titleweight": "bold"})
    figure = plt.figure(figsize=(16, 9), facecolor="#F7F8FA")
    grid = figure.add_gridspec(12, 24, hspace=1.4, wspace=1.8)
    figure.suptitle("Presight Project Spend Performance", x=0.04, y=0.975, ha="left", fontsize=19, color=COLORS["ink"], weight="bold")
    figure.text(0.04, 0.942, "Sanjay Subair | Executive view", color="#667085", fontsize=9)
    figure.text(0.96, 0.952, "FILTERS   Region: All   |   Project status: All   |   Year: All", ha="right", color="#475467", fontsize=8, weight="bold")

    metrics = [
        ("TOTAL BUDGET", f"AED {total_budget / 1_000_000:,.1f}M"),
        ("ACTUAL SPEND", f"AED {total_spend / 1_000_000:,.1f}M"),
        ("OVER-BUDGET PROJECTS", f"{over_budget_pct:.1f}%"),
        ("TRANSACTIONS", f"{len(transactions):,}"),
    ]
    for index, (label, value) in enumerate(metrics):
        axis = figure.add_subplot(grid[1:3, index * 6:(index + 1) * 6])
        axis.set_facecolor("white")
        axis.text(0.04, 0.72, label, transform=axis.transAxes, fontsize=8, color="#667085", weight="bold")
        axis.text(0.04, 0.20, value, transform=axis.transAxes, fontsize=18, color=COLORS["ink"], weight="bold")
        axis.set_xticks([]); axis.set_yticks([])
        for spine in axis.spines.values(): spine.set_color("#E4E7EC")

    bar = figure.add_subplot(grid[3:8, :10])
    positions = range(len(department))
    bar.barh([position + 0.18 for position in positions], department["budget"], height=0.34, color=COLORS["budget"], label="Budget")
    bar.barh([position - 0.18 for position in positions], department["actual_cost"], height=0.34, color=COLORS["spend"], label="Actual")
    bar.set_yticks(list(positions), department["department"]); bar.invert_yaxis(); bar.xaxis.set_major_formatter(AED)
    bar.set_title("Budget vs actual by department\nGrouped bars make variance directly comparable", loc="left"); bar.legend(frameon=False, ncol=2); bar.grid(axis="x", alpha=0.2)

    line = figure.add_subplot(grid[3:8, 10:19])
    for category, values in monthly.groupby("category"):
        line.plot(values["month"], values["amount_aed"], marker="o", linewidth=1.5, markersize=2.5, label=category)
    line.set_title("Monthly spend by leading categories\nLines reveal trend and seasonality", loc="left"); line.yaxis.set_major_formatter(AED)
    line.tick_params(axis="x", rotation=35); line.grid(alpha=0.2); line.legend(frameon=False, fontsize=6, ncol=2)

    pie = figure.add_subplot(grid[3:8, 19:24])
    pie.pie(vendor_pie, labels=vendor_pie.index, autopct="%1.0f%%", startangle=90, textprops={"fontsize": 6})
    pie.set_title("Vendor concentration\nTop five plus Other shows share risk", loc="left")

    table_axis = figure.add_subplot(grid[8:12, :])
    table_axis.axis("off"); table_axis.set_title("Top 10 projects by budget variance | Ranked detail directs management attention", loc="left", pad=8)
    table_values = top_projects.copy()
    table_values["budget_variance"] = table_values["budget_variance"].map(lambda value: f"AED {value:,.0f}")
    table = table_axis.table(cellText=table_values.values, colLabels=["Project", "Department", "Budget variance"], cellLoc="left", colLoc="left", loc="upper left", bbox=[0, 0, 1, 0.9])
    table.auto_set_font_size(False); table.set_fontsize(7)
    for (row, _), cell in table.get_celld().items():
        cell.set_edgecolor("#E4E7EC"); cell.set_facecolor("#EEF2F6" if row == 0 else "white")

    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    with PdfPages(OUTPUT_PATH) as pdf:
        pdf.savefig(figure, bbox_inches="tight")
    plt.close(figure)


if __name__ == "__main__":
    generate_dashboard()
