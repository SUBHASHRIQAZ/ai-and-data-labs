"""Regenerates architecture.png from scratch.

    pip install matplotlib
    python render_diagram.py

Kept alongside the image it produces rather than in a general scripts/
folder — it's a one-off diagram generator, not part of the pipeline, and
easiest to find when it lives right next to what it renders. Edit the box
text/arrows below directly when the pipeline changes enough to redraw.
"""

import pathlib

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
from matplotlib.lines import Line2D

# ---- palette -----------------------------------------------------------
INK = "#1f2430"
MUTED = "#5c6370"
BG = "#fbfbfa"

SOURCE = "#e9e6e1"
LANDING = "#dfe7f0"
BRONZE_BG, BRONZE_BORDER = "#f3e2d3", "#b3703c"
SILVER_BG, SILVER_BORDER = "#e6e8ec", "#7b8494"
GOLD_BG, GOLD_BORDER = "#faedc4", "#b8860b"
PROC = "#ffffff"
PROC_BORDER = "#9aa0ab"
DASH = "#4c6ef5"
QUALITY = "#c94f4f"

fig_w, fig_h = 16, 12
fig, ax = plt.subplots(figsize=(fig_w, fig_h), dpi=170)
ax.set_xlim(0, 160)
ax.set_ylim(0, 120)
ax.axis("off")
fig.patch.set_facecolor(BG)
ax.set_facecolor(BG)


def box(x, y, w, h, text, face, edge, fontsize=9.3, weight="bold", textcolor=INK,
        lw=1.6, style="round,pad=0.35,rounding_size=3.5", zorder=3):
    b = FancyBboxPatch((x, y), w, h, boxstyle=style, linewidth=lw,
                        edgecolor=edge, facecolor=face, zorder=zorder)
    ax.add_patch(b)
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center",
             fontsize=fontsize, color=textcolor, weight=weight, zorder=zorder + 1,
             linespacing=1.35)
    return (x, y, w, h)


def label(x, y, text, fontsize=8.3, color=MUTED, ha="center", style="italic", weight="normal"):
    ax.text(x, y, text, ha=ha, va="center", fontsize=fontsize, color=color,
             style=style, weight=weight, zorder=4)


def arrow(p_from, p_to, color=MUTED, lw=1.6, style="-|>", ls="solid", connectionstyle="arc3,rad=0.0",
          zorder=2):
    a = FancyArrowPatch(p_from, p_to, arrowstyle=style, mutation_scale=14,
                         linewidth=lw, color=color, linestyle=ls,
                         connectionstyle=connectionstyle, zorder=zorder,
                         shrinkA=2, shrinkB=2)
    ax.add_patch(a)


def top(b):
    x, y, w, h = b
    return (x + w / 2, y + h)


def bottom(b):
    x, y, w, h = b
    return (x + w / 2, y)


def left(b):
    x, y, w, h = b
    return (x, y + h / 2)


def right(b):
    x, y, w, h = b
    return (x + w, y + h / 2)


# ---- title ---------------------------------------------------------------
ax.text(80, 116.5, "RidePulse — Real-Time Ride Analytics Lakehouse", ha="center", va="center",
        fontsize=19, weight="bold", color=INK)
ax.text(80, 112.3, "NYC TLC High Volume FHV data  •  Bronze / Silver / Gold on Delta Lake  •  Unity Catalog: ridepulse",
        ha="center", va="center", fontsize=10.3, color=MUTED)

# ---- Phase headers ---------------------------------------------------------
phase_y, phase_h = 103.5, 6.2
p1 = box(4, phase_y, 47, phase_h, "PHASE 1 — Batch", SOURCE, "#a89f8f", fontsize=10.5)
p2 = box(56.5, phase_y, 47, phase_h, "PHASE 2 — Auto Loader / Structured Streaming", SOURCE, "#a89f8f", fontsize=10.5)
p3 = box(109, phase_y, 47, phase_h, "PHASE 3 — Kafka", SOURCE, "#a89f8f", fontsize=10.5)

# ---- Phase 1 column --------------------------------------------------------
s1 = box(9, 92.5, 37, 7, "NYC TLC HVFHV parquet\n(downloaded manually,\nno outbound internet on Free Edition)",
          SOURCE, "#a89f8f", fontsize=8.0, weight="normal")
n1 = box(9, 81.5, 37, 7.5,
          "01_bronze_ingestion.py\nread parquet → tag ingestion_timestamp,\nsource_file → skip already-ingested files",
          PROC, PROC_BORDER, fontsize=8.0, weight="normal")
arrow(bottom(s1), top(n1))

# ---- Phase 2 column --------------------------------------------------------
s2 = box(61.5, 92.5, 37, 7,
          "06_simulate_batches.py\nsplits one month of HVFHV into\nbatch_000.parquet, batch_001.parquet …",
          SOURCE, "#a89f8f", fontsize=7.7, weight="normal")
n2 = box(61.5, 81.5, 37, 7.5,
          "05_streaming_ingestion.py\nAuto Loader (cloudFiles) → checkpoint →\nschema evolution (addNewColumns)",
          PROC, PROC_BORDER, fontsize=8.0, weight="normal")
arrow(bottom(s2), top(n2))
label(80, 79.8, "bronze.trips_stream", fontsize=7.4)

# ---- Phase 3 column --------------------------------------------------------
s3 = box(114, 92.5, 37, 7,
          "kafka/ride_producer.py\nreplays trips as JSON events\n(--late-rate, --duplicate-rate)",
          SOURCE, "#a89f8f", fontsize=7.8, weight="normal")
n3 = box(114, 81.5, 37, 7.5,
          "07_kafka_streaming_ingestion.py\nreadStream(kafka) → withWatermark +\ndropDuplicates → checkpoint",
          PROC, PROC_BORDER, fontsize=7.7, weight="normal")
arrow(bottom(s3), top(n3))
label(132.5, 79.8, "bronze.ride_events", fontsize=7.4)

# ---- Bronze -----------------------------------------------------------
bronze = box(30, 68.5, 100, 9, "BRONZE\nridepulse.bronze.*\nraw, append-only, minimally transformed",
              BRONZE_BG, BRONZE_BORDER, fontsize=10.5)
arrow(bottom(n1), top(bronze), color=BRONZE_BORDER, connectionstyle="arc3,rad=0.0")
arrow(bottom(n2), top(bronze), color=BRONZE_BORDER, connectionstyle="arc3,rad=-0.05")
arrow(bottom(n3), top(bronze), color=BRONZE_BORDER, connectionstyle="arc3,rad=-0.08")

# ---- idempotency callout (phase 1 only — the streaming paths' equivalent
# ---- note lives in the footnote at the bottom of the figure) -----------
label(9, 78.6, "idempotent:\nsource_file check", fontsize=6.9, ha="left", color=BRONZE_BORDER)

# ---- Silver -------------------------------------------------------------
silver_proc = box(30, 57, 100, 8,
                    "02_silver_transformations.py  —  clean_trips / enrich_trips / add_zone_names (transformations.py)\n"
                    "drop NULL/negative/zero-distance/invalid-duration/duplicate rows → pickup_date, pickup_hour, day_of_week,\n"
                    "trip_duration_minutes, average_speed → broadcast join taxi_zone_lookup → repartition + MERGE (upsert)",
                    PROC, PROC_BORDER, fontsize=7.6, weight="normal")
arrow(bottom(bronze), top(silver_proc), color=SILVER_BORDER)

silver = box(45, 46.5, 70, 7.5, "SILVER\nridepulse.silver.trips\ncleaned, deduplicated, enriched — partitioned by pickup_date",
              SILVER_BG, SILVER_BORDER, fontsize=10)
arrow(bottom(silver_proc), top(silver), color=SILVER_BORDER)

# ---- Gold -----------------------------------------------------------------
gold_proc = box(30, 35, 100, 7.5,
                  "03_gold_aggregations.py  —  groupBy aggregations + window function (revenue_rank) → liquid clustering (CLUSTER BY)",
                  PROC, PROC_BORDER, fontsize=8.3, weight="normal")
arrow(bottom(silver), top(gold_proc), color=GOLD_BORDER)

gold_tables = ["gold.hourly_demand", "gold.zone_revenue", "gold.trip_kpis", "gold.peak_demand"]
gx0, gw, ggap = 20, 27, 4
gold_boxes = []
for i, t in enumerate(gold_tables):
    gb = box(gx0 + i * (gw + ggap), 24, gw, 7, t, GOLD_BG, GOLD_BORDER, fontsize=8.6)
    gold_boxes.append(gb)
    arrow(bottom(gold_proc), top(gb), color=GOLD_BORDER)

# ---- Dashboard --------------------------------------------------------
dash = box(38, 10.5, 84, 8,
            "SQL Warehouse  —  sql/dashboard.sql, demand_analysis.sql, revenue_analysis.sql\n"
            "busiest zones • peak hours • top-revenue zones • weekday vs weekend • trip KPIs",
            "#eef1fb", DASH, fontsize=8.4, weight="normal")
for gb in gold_boxes:
    arrow(bottom(gb), top(dash), color=DASH, lw=1.3)

# ---- maintenance callout -------------------------------------------------
maint = box(130, 46.5, 26, 7.5, "sql/maintenance.sql\nOPTIMIZE • VACUUM\ntime travel", "#f2f2f2", PROC_BORDER, fontsize=7.6)
arrow(right(silver), left(maint), color=PROC_BORDER, ls=(0, (4, 2)), connectionstyle="arc3,rad=0.12")

# ---- Data quality gate --------------------------------------------------
dq = box(130, 35, 26, 7.5, "04_data_quality.py\nPASS/FAIL gate", "#fbe9e9", QUALITY, fontsize=8.2)
arrow(right(silver), left(dq), color=QUALITY, ls=(0, (4, 2)), connectionstyle="arc3,rad=-0.12")
label(143, 33.2, "checks Bronze/Silver/Gold,\ngates the Workflow run", fontsize=7.0, color=QUALITY)

# ---- legend ---------------------------------------------------------------
legend_items = [
    ("Bronze", BRONZE_BORDER),
    ("Silver", SILVER_BORDER),
    ("Gold", GOLD_BORDER),
    ("Notebook / process", PROC_BORDER),
    ("Data quality", QUALITY),
]
handles = [Line2D([0], [0], color=c, lw=3.4) for _, c in legend_items]
labels_ = [t for t, _ in legend_items]
ax.legend(handles, labels_, loc="lower left", bbox_to_anchor=(0.003, 0.045), fontsize=8.3,
          frameon=False, ncol=5, handlelength=1.6, columnspacing=1.3)

ax.text(80, 2.6,
        "Phase 1 (batch) checks source_file before appending to stay idempotent; Phase 2 and 3 (streaming) get idempotency\n"
        "and failure recovery for free from their checkpoints — same property, two different mechanisms.",
        ha="center", va="center", fontsize=7.6, color=MUTED, style="italic", linespacing=1.5)

plt.tight_layout()
out_path = pathlib.Path(__file__).resolve().parent / "architecture.png"
fig.savefig(out_path, facecolor=BG, bbox_inches="tight")
print("saved", out_path)
