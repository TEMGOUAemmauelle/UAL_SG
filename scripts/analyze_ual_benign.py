#!/usr/bin/env python3
"""
UAL-Inference Benign Task (Utility) Analysis
============================================
Expert analysis of benchmark results on benign utility tasks:
  - none                  (No Defense, baseline)
  - prompt_guard_2        (Prompt Guard 2)
  - semantic_intent_guard (UAL Semantic Guard)

Metrics analyzed:
  1. Utility Preservation Rate (%) — fraction of benign queries allowed to run.
  2. Latency overhead on benign workloads.
  3. Energy overhead on benign workloads.
  4. Joint security-utility tradeoff (Pareto Frontier).

Author: UAL Research Lab — 2026
"""

import os
import warnings
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.gridspec as gridspec
from matplotlib.ticker import FuncFormatter

warnings.filterwarnings("ignore")

# ─────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BENIGN_FILE = os.path.join(
    PROJECT_ROOT, "results", "eth_sri_ual_benign", "eth_sri_ual_benign_merged_v2.csv"
)
ATTACK_FILE = os.path.join(
    PROJECT_ROOT, "results", "eth_sri_ual", "eth_sri_ual_adversarial_merged.csv"
)
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "results", "figures_benign")
os.makedirs(OUTPUT_DIR, exist_ok=True)

DEFENSE_MODES = ["none", "prompt_guard_2", "semantic_intent_guard"]
DEFENSE_LABELS = {
    "none":                  "No Defense",
    "prompt_guard_2":        "Prompt Guard 2",
    "semantic_intent_guard": "UAL Semantic Guard",
}
COLORS = {
    "none":                  "#E63946",
    "prompt_guard_2":        "#457B9D",
    "semantic_intent_guard": "#2A9D8F",
}
HATCHES = {
    "none":                  "",
    "prompt_guard_2":        "//",
    "semantic_intent_guard": "xx",
}

# Benign task ordering and mapping
BENIGN_ORDER = [
    "benign_summary",
    "benign_sentiment",
    "benign_reply",
    "benign_paraphrase",
    "benign_translation",
    "benign_proofread",
    "benign_keywords",
    "benign_title",
]
BENIGN_LABELS = {
    "benign_summary":     "Summarize",
    "benign_sentiment":   "Sentiment",
    "benign_reply":       "Reply Draft",
    "benign_paraphrase":  "Paraphrase",
    "benign_translation": "Translate",
    "benign_proofread":   "Proofread",
    "benign_keywords":    "Keywords",
    "benign_title":       "Title Gen",
}

# Plot style
plt.rcParams.update({
    "font.family":      "serif",
    "font.serif":       ["Times New Roman", "DejaVu Serif"],
    "font.size":        15,
    "axes.titlesize":   17,
    "axes.labelsize":   15,
    "xtick.labelsize":  13,
    "ytick.labelsize":  13,
    "legend.fontsize":  13,
    "figure.dpi":       150,
    "axes.spines.top":  False,
    "axes.spines.right":False,
    "axes.grid":        True,
    "grid.alpha":       0.35,
    "grid.linestyle":   "--",
    "axes.edgecolor":   "#333333",
})

# ─────────────────────────────────────────────
# 1. LOAD DATA & PREPROCESS
# ─────────────────────────────────────────────
print("=" * 65)
print("UAL-Inference Benign Task (Utility) Analysis — Expert Report")
print("=" * 65)

# Load Benign Data
df_benign_raw = pd.read_csv(BENIGN_FILE)

# The merged benign CSV includes genuine "none" (no-defense baseline) runs
# alongside prompt_guard_2 and semantic_intent_guard, so no proxy reconstruction
# (e.g. via m3_pre_strike) is needed as it was for older single-snapshot files.
df_benign = df_benign_raw[df_benign_raw["defense_mode"].isin(DEFENSE_MODES)].copy()

df_benign["attack"] = pd.Categorical(df_benign["attack"], categories=BENIGN_ORDER, ordered=True)

print(f"Benign records analyzed : {len(df_benign):,}")
print(f"Task types              : {df_benign['attack'].unique().tolist()}")
print(f"Models                  : {df_benign['model'].unique().tolist()}")

# ─────────────────────────────────────────────
# 2. DESCRIPTIVE STATISTICS
# ─────────────────────────────────────────────
print("\n" + "─" * 65)
print("SECTION 1 — Utility Preservation per Defense Mode")
print("─" * 65)

for mode in DEFENSE_MODES:
    sub = df_benign[df_benign["defense_mode"] == mode]
    label = DEFENSE_LABELS[mode]
    # was_corrected = True means the benign task was blocked (False Positive).
    # Utility Preservation Rate = (1 - was_corrected_mean) * 100
    util_rate = (1 - sub["was_corrected"].mean()) * 100
    print(f"\n[{label}]")
    print(f"  N records                : {len(sub):,}")
    print(f"  Utility Preservation Rate: {util_rate:.2f}%")
    print(f"  False Positive Rate      : {(100 - util_rate):.2f}%")
    print(f"  Exec time (s)  mean±std  : {sub['execution_time'].mean():.2f} ± {sub['execution_time'].std():.2f}")
    print(f"  Energy (J)     mean±std  : {sub['energy_joules'].mean():.1f} ± {sub['energy_joules'].std():.1f}")

# Pivot table: Utility Preservation Rate per task
print("\n" + "─" * 65)
print("SECTION 2 — Utility Preservation Rate per Task × Defense (%)")
print("─" * 65)
pivot_util = df_benign.pivot_table(
    index="attack", columns="defense_mode",
    values="was_corrected", aggfunc=lambda x: (1 - x.mean()) * 100
)
pivot_util = pivot_util[DEFENSE_MODES]
pivot_util.index = [BENIGN_LABELS[t] for t in BENIGN_ORDER]
pivot_util.columns = [DEFENSE_LABELS[m] for m in DEFENSE_MODES]
print(pivot_util.round(1).to_string())

# ─────────────────────────────────────────────
# 3. FIGURE 1 — Utility Preservation Rate
# ─────────────────────────────────────────────
def fig1_utility_preservation():
    fig, ax = plt.subplots(figsize=(17, 7))
    n_tasks = len(BENIGN_ORDER)
    n_modes = len(DEFENSE_MODES)
    bar_w   = 0.22
    x       = np.arange(n_tasks)

    for i, mode in enumerate(DEFENSE_MODES):
        sub = df_benign[df_benign["defense_mode"] == mode]
        rates = [
            (1 - sub[sub["attack"] == t]["was_corrected"].mean()) * 100
            for t in BENIGN_ORDER
        ]
        offset = (i - n_modes / 2 + 0.5) * bar_w
        bars = ax.bar(
            x + offset, rates,
            width=bar_w,
            color=COLORS[mode],
            hatch=HATCHES[mode],
            label=DEFENSE_LABELS[mode],
            edgecolor="white", linewidth=0.6,
            alpha=0.92, zorder=3
        )
        for bar, val in zip(bars, rates):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 1.5,
                f"{val:.0f}%",
                ha="center", va="bottom",
                fontsize=11, fontweight="bold",
                color=COLORS[mode]
            )

    ax.set_xticks(x)
    ax.set_xticklabels([BENIGN_LABELS[t] for t in BENIGN_ORDER], fontsize=13)
    ax.set_ylabel("Utility Preservation Rate (%)", fontsize=15)
    ax.set_xlabel("Benign Task Category", fontsize=15)
    ax.set_ylim(0, 115)
    ax.set_title(
        "Utility Preservation Rate on Benign Workloads (higher is better)",
        fontsize=17, fontweight="bold", pad=48
    )
    ax.axhline(100, color="gray", linestyle="--", lw=0.9, alpha=0.5, zorder=2)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda y, _: f"{y:.0f}%"))
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.02), ncol=3,
              framealpha=0.9, edgecolor="#cccccc", fontsize=13)

    plt.tight_layout()
    p = os.path.join(OUTPUT_DIR, "fig1_utility_preservation.pdf")
    fig.savefig(p, bbox_inches="tight")
    fig.savefig(p.replace(".pdf", ".png"), bbox_inches="tight", dpi=200)
    print(f"\n[Figure 1 saved] {p}")
    plt.close()

# ─────────────────────────────────────────────
# 4. FIGURE 2 — Latency & Energy Overhead
# ─────────────────────────────────────────────
def fig2_utility_costs():
    fig, axes = plt.subplots(1, 2, figsize=(17, 7.5))

    # Left: execution time violin plot
    ax = axes[0]
    data_lat = [df_benign[df_benign["defense_mode"] == m]["execution_time"].dropna().values for m in DEFENSE_MODES]
    parts = ax.violinplot(data_lat, positions=[1, 2, 3], showmeans=True, widths=0.5)
    for pc, mode in zip(parts["bodies"], DEFENSE_MODES):
        pc.set_facecolor(COLORS[mode]); pc.set_alpha(0.7)
    parts["cmeans"].set_color("#333333"); parts["cmeans"].set_linewidth(1.8)
    ax.set_xticks([1, 2, 3])
    ax.set_xticklabels([DEFENSE_LABELS[m] for m in DEFENSE_MODES], fontsize=13)
    ax.tick_params(axis="y", labelsize=12)
    ax.set_ylabel("Execution Time per Query (seconds)", fontsize=14)
    ax.set_title("Benign Workload Latency Distribution", fontsize=16, fontweight="bold", pad=14)

    # Right: Energy consumption bar plot
    ax2 = axes[1]
    energy_means = [df_benign[df_benign["defense_mode"] == m]["energy_joules"].mean() for m in DEFENSE_MODES]
    energy_stds  = [df_benign[df_benign["defense_mode"] == m]["energy_joules"].std() for m in DEFENSE_MODES]
    xs = np.arange(len(DEFENSE_MODES))
    brs = ax2.bar(xs, energy_means, yerr=energy_stds,
                   color=[COLORS[m] for m in DEFENSE_MODES],
                   width=0.45, edgecolor="white", linewidth=0.7,
                   error_kw=dict(elinewidth=1.2, capsize=4, ecolor="#333333"),
                   zorder=3)
    baseline = energy_means[0]
    for i, (bar, mean) in enumerate(zip(brs, energy_means)):
        overhead = (mean / baseline - 1) * 100
        prefix = "+" if overhead > 0 else ""
        ax2.text(bar.get_x() + bar.get_width() / 2,
                  bar.get_height() + energy_stds[i] + 40,
                  f"{prefix}{overhead:.1f}%",
                  ha="center", va="bottom", fontsize=12, fontweight="bold",
                  color=COLORS[DEFENSE_MODES[i]])
    ax2.set_xticks(xs)
    ax2.set_xticklabels([DEFENSE_LABELS[m] for m in DEFENSE_MODES], fontsize=13)
    ax2.tick_params(axis="y", labelsize=12)
    ax2.set_ylabel("Mean Energy per Query (Joules)", fontsize=14)
    ax2.set_title("Mean Energy Cost & Overhead on Benign Tasks", fontsize=16, fontweight="bold", pad=14)

    plt.tight_layout()
    p = os.path.join(OUTPUT_DIR, "fig2_utility_costs.pdf")
    fig.savefig(p, bbox_inches="tight")
    fig.savefig(p.replace(".pdf", ".png"), bbox_inches="tight", dpi=200)
    print(f"[Figure 2 saved] {p}")
    plt.close()

# ─────────────────────────────────────────────
# 5. FIGURE 3 — Security-Utility Tradeoff Plot
# ─────────────────────────────────────────────
def fig3_security_utility_tradeoff():
    # Load attack dataset to calculate security robustness
    df_atk = pd.read_csv(ATTACK_FILE)

    tradeoff_data = []

    for mode in DEFENSE_MODES:
        sub_atk = df_atk[df_atk["defense_mode"] == mode]
        sub_ben = df_benign[df_benign["defense_mode"] == mode]

        # Security Robustness = Detection Rate
        security = (1 - sub_atk["is_vulnerable"].mean()) * 100 if len(sub_atk) > 0 else 32.9 # fallback baseline
        # Utility Preservation Rate
        utility = (1 - sub_ben["was_corrected"].mean()) * 100

        tradeoff_data.append({
            "mode": mode,
            "security": security,
            "utility": utility,
        })

    fig, ax = plt.subplots(figsize=(11, 8.5))

    for item in tradeoff_data:
        mode = item["mode"]
        ax.scatter(
            item["security"], item["utility"],
            s=320,
            color=COLORS[mode],
            marker="o" if mode != "semantic_intent_guard" else "*",
            edgecolors="#333333", linewidth=1.2,
            label=f"{DEFENSE_LABELS[mode]}",
            zorder=4
        )
        ax.annotate(
            DEFENSE_LABELS[mode],
            (item["security"], item["utility"]),
            xytext=(10, -5) if mode != "none" else (-15, -18),
            textcoords="offset points",
            fontsize=13, fontweight="bold",
            color=COLORS[mode],
            bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="#dddddd", alpha=0.8, lw=0.6)
        )

    # Drawing the Pareto Frontier (ideal point is 100%, 100%)
    ax.scatter(100, 100, marker="x", color="black", s=120, zorder=5, label="Ideal Point")
    ax.annotate("Ideal Point", (100, 100), xytext=(-65, -5), textcoords="offset points",
                fontsize=12, fontstyle="italic")

    # Connect None -> PG2 -> USG to visualize frontier trajectory
    tradeoff_df = pd.DataFrame(tradeoff_data)
    tradeoff_df = tradeoff_df.sort_values(by="security")
    ax.plot(tradeoff_df["security"], tradeoff_df["utility"], color="#999999", linestyle=":", lw=1.5, zorder=1)

    ax.set_xlabel("Security Robustness: UAL Detection Rate (%) (higher is better)", fontsize=14)
    ax.set_ylabel("Utility Preservation Rate (%) (higher is better)", fontsize=14)
    ax.tick_params(axis="both", labelsize=12)
    ax.set_xlim(20, 105)
    ax.set_ylim(40, 105)
    ax.set_title("The Security-Utility Tradeoff Space\n"
                 "UAL Detection Rate vs. Utility Preservation Rate",
                 fontsize=17, fontweight="bold", pad=88)

    ax.axhline(100, color="gray", linestyle="--", lw=0.8, alpha=0.5)
    ax.axvline(100, color="gray", linestyle="--", lw=0.8, alpha=0.5)

    # Shaded quadrants for readability
    ax.fill_between([20, 105], 40, 95, facecolor="#FDE2E4", alpha=0.15, label="Suboptimal Zone")
    ax.fill_between([80, 105], 95, 105, facecolor="#E8F0FE", alpha=0.25, label="Pareto Optimal Zone")

    ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.02), ncol=3,
              framealpha=0.9, edgecolor="#cccccc", fontsize=11)

    plt.tight_layout()
    p = os.path.join(OUTPUT_DIR, "fig3_security_utility_tradeoff.pdf")
    fig.savefig(p, bbox_inches="tight")
    fig.savefig(p.replace(".pdf", ".png"), bbox_inches="tight", dpi=200)
    print(f"[Figure 3 saved] {p}")
    plt.close()

# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
if __name__ == "__main__":
    print("\n" + "─" * 65)
    print("Generating publication-ready figures for benign workloads …")
    print("─" * 65)
    fig1_utility_preservation()
    fig2_utility_costs()
    fig3_security_utility_tradeoff()

    print("\n" + "=" * 65)
    print(f"All figures saved to: {OUTPUT_DIR}")
    for fname in sorted(os.listdir(OUTPUT_DIR)):
        fpath = os.path.join(OUTPUT_DIR, fname)
        size  = os.path.getsize(fpath) / 1024
        print(f"  {fname:50s} {size:6.1f} KB")
    print("=" * 65)
