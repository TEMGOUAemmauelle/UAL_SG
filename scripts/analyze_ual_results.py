#!/usr/bin/env python3
"""
UAL-Inference Defense Analysis
================================
Expert analysis of benchmark results for three defense modes:
  - none               (no defense, baseline)
  - prompt_guard_2     (Prompt Guard 2 — state-of-practice)
  - semantic_intent_guard (UAL Semantic Guard — proposed)

Metrics analyzed:
  1. Security robustness  — bypass rate per attack variant
  2. Inference latency    — execution time distribution
  3. Energy consumption   — energy (Joules) per query
  4. Combined figures     — publication-ready scientific plots

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
from scipy import stats

warnings.filterwarnings("ignore")

# ─────────────────────────────────────────────
# 0.  CONFIGURATION
# ─────────────────────────────────────────────
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RESULTS_FILE = os.path.join(
    PROJECT_ROOT,
    "results", "eth_sri_ual", "eth_sri_ual_adversarial_merged.csv"
)
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "results", "figures")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ── Defense modes to analyze (exactly three, as requested)
DEFENSE_MODES = ["none", "prompt_guard_2", "semantic_intent_guard"]
DEFENSE_LABELS = {
    "none":                 "No Defense",
    "prompt_guard_2":       "Prompt Guard 2",
    "semantic_intent_guard":"UAL Semantic Guard",
}

# ── Attack variants (5, ordered explicit → evasive)
ATTACK_ORDER = [
    "ual_inference_ethsri",
    "ual_inference",
    "ual_inference_evasive_natural",
    "ual_inference_evasive_casual",
    "ual_inference_evasive_stealth",
    # Generalization set (attacks/payloads.py) — evasive reformulations absent
    # from the M5 judge's few-shot demonstrations.
    "ual_inference_evasive_thirdparty",
    "ual_inference_evasive_roleplay",
    "ual_inference_evasive_questions",
    "ual_inference_evasive_pretext",
]
ATTACK_LABELS = {
    "ual_inference_ethsri":              "ETHSRI\n(Structured)",
    "ual_inference":                     "Direct\n(Explicit)",
    "ual_inference_evasive_natural":     "Evasive\nNatural",
    "ual_inference_evasive_casual":      "Evasive\nCasual",
    "ual_inference_evasive_stealth":     "Evasive\nStealth",
    "ual_inference_evasive_thirdparty":  "Evasive\nThird-Party",
    "ual_inference_evasive_roleplay":    "Evasive\nRoleplay",
    "ual_inference_evasive_questions":   "Evasive\nQuestions",
    "ual_inference_evasive_pretext":     "Evasive\nPretext",
}

# ── Scientific color palette (colorblind-safe)
COLORS = {
    "none":                 "#E63946",   # red
    "prompt_guard_2":       "#457B9D",   # steel blue
    "semantic_intent_guard":"#2A9D8F",   # teal
}
HATCHES = {
    "none":                 "",
    "prompt_guard_2":       "//",
    "semantic_intent_guard":"xx",
}

# ── Plot style
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
# 1.  DATA LOADING & PREPARATION
# ─────────────────────────────────────────────
print("=" * 60)
print("UAL-Inference Defense Benchmark — Expert Analysis")
print("=" * 60)

df_all = pd.read_csv(RESULTS_FILE)
df = df_all[df_all["defense_mode"].isin(DEFENSE_MODES)].copy()
df["attack"] = pd.Categorical(df["attack"], categories=ATTACK_ORDER, ordered=True)

print(f"\nTotal records loaded : {len(df_all):,}")
print(f"Records analyzed     : {len(df):,}")
print(f"Defense modes        : {df['defense_mode'].unique().tolist()}")
print(f"Attack variants      : {df['attack'].unique().tolist()}")
print(f"Models               : {df['model'].unique().tolist()}")


# ─────────────────────────────────────────────
# 2.  DESCRIPTIVE STATISTICS
# ─────────────────────────────────────────────
print("\n" + "─" * 60)
print("SECTION 1 — Descriptive Statistics per Defense Mode")
print("─" * 60)

for mode in DEFENSE_MODES:
    sub = df[df["defense_mode"] == mode]
    label = DEFENSE_LABELS[mode]
    vuln_rate = sub["is_vulnerable"].mean() * 100
    bypass_rate = (1 - sub["is_vulnerable"].mean()) * 100
    print(f"\n[{label}]")
    print(f"  N records          : {len(sub):,}")
    print(f"  Vulnerability rate : {vuln_rate:.1f}%")
    print(f"  Bypass rate (safe) : {bypass_rate:.1f}%")
    print(f"  Exec time (s)  mean±std : {sub['execution_time'].mean():.2f} ± {sub['execution_time'].std():.2f}")
    print(f"  Exec time (s)  [min, P25, P50, P75, max] : "
          f"[{sub['execution_time'].min():.2f}, "
          f"{sub['execution_time'].quantile(0.25):.2f}, "
          f"{sub['execution_time'].median():.2f}, "
          f"{sub['execution_time'].quantile(0.75):.2f}, "
          f"{sub['execution_time'].max():.2f}]")
    print(f"  Energy (J)  mean±std : {sub['energy_joules'].mean():.1f} ± {sub['energy_joules'].std():.1f}")
    print(f"  Power (W)   mean     : {sub['power_avg'].mean():.1f}")

# Per-attack vulnerability table
print("\n" + "─" * 60)
print("SECTION 2 — Bypass Rate per Attack Variant × Defense Mode (%)")
print("─" * 60)
pivot_vuln = df.pivot_table(
    index="attack", columns="defense_mode",
    values="is_vulnerable", aggfunc="mean"
) * 100
pivot_vuln = pivot_vuln[DEFENSE_MODES]
pivot_vuln.index = [ATTACK_LABELS[a].replace("\n", " ") for a in ATTACK_ORDER]
pivot_vuln.columns = [DEFENSE_LABELS[m] for m in DEFENSE_MODES]
print(pivot_vuln.round(1).to_string())

# Energy comparison
print("\n" + "─" * 60)
print("SECTION 3 — Energy Overhead (Joules) per Defense Mode")
print("─" * 60)
energy_pivot = df.groupby("defense_mode")["energy_joules"].agg(["mean", "std", "median"])
for mode in DEFENSE_MODES:
    r = energy_pivot.loc[mode]
    baseline = energy_pivot.loc["none", "mean"]
    overhead = (r["mean"] / baseline - 1) * 100
    print(f"  {DEFENSE_LABELS[mode]:30s}  mean={r['mean']:.1f} J  std={r['std']:.1f} J  "
          f"median={r['median']:.1f} J  overhead vs none={overhead:+.1f}%")

# Statistical tests
print("\n" + "─" * 60)
print("SECTION 4 — Statistical Significance (Mann-Whitney U, energy)")
print("─" * 60)
ref = df[df["defense_mode"] == "none"]["energy_joules"].dropna()
for mode in ["prompt_guard_2", "semantic_intent_guard"]:
    alt = df[df["defense_mode"] == mode]["energy_joules"].dropna()
    stat, p = stats.mannwhitneyu(ref, alt, alternative="two-sided")
    sig = "***" if p < 0.001 else ("**" if p < 0.01 else ("*" if p < 0.05 else "ns"))
    print(f"  None vs {DEFENSE_LABELS[mode]:30s}: U={stat:.0f}, p={p:.4e} {sig}")

stat, p = stats.mannwhitneyu(
    df[df["defense_mode"] == "prompt_guard_2"]["energy_joules"].dropna(),
    df[df["defense_mode"] == "semantic_intent_guard"]["energy_joules"].dropna(),
    alternative="two-sided"
)
sig = "***" if p < 0.001 else ("**" if p < 0.01 else ("*" if p < 0.05 else "ns"))
print(f"  PG2  vs {DEFENSE_LABELS['semantic_intent_guard']:30s}: U={stat:.0f}, p={p:.4e} {sig}")


# ─────────────────────────────────────────────
# 3.  FIGURE 1 — Security Robustness
#     Vulnerability rate per attack × defense, one figure per target model
# ─────────────────────────────────────────────
def fig1_robustness():
    n_attacks = len(ATTACK_ORDER)
    n_modes   = len(DEFENSE_MODES)
    bar_w     = 0.22
    x         = np.arange(n_attacks)

    for model in MODEL_ORDER:
        df_model = df[df["model"] == model]
        fig, ax = plt.subplots(figsize=(16, 5.5))

        for i, mode in enumerate(DEFENSE_MODES):
            sub = df_model[df_model["defense_mode"] == mode]
            rates = [
                (1 - sub[sub["attack"] == atk]["is_vulnerable"].mean()) * 100
                for atk in ATTACK_ORDER
            ]
            offset = (i - n_modes / 2 + 0.5) * bar_w
            bars = ax.bar(
                x + offset, rates,
                width=bar_w,
                color=COLORS[mode],
                hatch=HATCHES[mode],
                label=DEFENSE_LABELS[mode],
                edgecolor="white",
                linewidth=0.6,
                alpha=0.92,
                zorder=3,
            )
            for bar, val in zip(bars, rates):
                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + 1.2,
                    f"{val:.0f}%",
                    ha="center", va="bottom",
                    fontsize=11, fontweight="bold",
                    color=COLORS[mode],
                )

        ax.set_xticks(x)
        ax.set_xticklabels(
            [ATTACK_LABELS[a] for a in ATTACK_ORDER],
            fontsize=13, ha="center"
        )
        ax.set_ylabel("Security Robustness / Detection Rate (%)", fontsize=15)
        ax.set_xlabel("Attack Variant", fontsize=15)
        ax.set_ylim(0, 115)
        ax.set_title(
            f"Security Robustness: UAL Detection Rate per Attack Variant — {model} (higher is better)",
            fontsize=17, fontweight="bold", pad=48
        )
        ax.axhline(50, color="gray", linestyle=":", linewidth=0.9, alpha=0.6, zorder=2)
        ax.axhline(100, color="gray", linestyle="--", linewidth=0.9, alpha=0.6, zorder=2)
        ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.02), ncol=3,
                  framealpha=0.9, edgecolor="#cccccc", fontsize=13)
        ax.yaxis.set_major_formatter(FuncFormatter(lambda y, _: f"{y:.0f}%"))

        # Annotation: stealth variant (recomputed from the merged CSV, not hardcoded)
        stealth_pg2 = df_model[(df_model["defense_mode"] == "prompt_guard_2") &
                                (df_model["attack"] == "ual_inference_evasive_stealth")]
        if len(stealth_pg2) > 0:
            stealth_rate = (1 - stealth_pg2["is_vulnerable"].mean()) * 100
            stealth_idx = ATTACK_ORDER.index("ual_inference_evasive_stealth")
            ax.annotate(
                f"Evasive Stealth:\n{stealth_rate:.1f}% Detection (PG2)",
                xy=(stealth_idx + bar_w * 0.5, stealth_rate),
                xytext=(stealth_idx - 0.7, 45),
                arrowprops=dict(arrowstyle="->", color="#333333", lw=1.2),
                fontsize=12, color="#333333",
                bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="#cccccc", lw=0.8),
            )

        plt.tight_layout()
        model_slug = model.replace(":", "_").replace(".", "_")
        path = os.path.join(OUTPUT_DIR, f"fig1_security_robustness_{model_slug}.pdf")
        fig.savefig(path, bbox_inches="tight")
        fig.savefig(path.replace(".pdf", ".png"), bbox_inches="tight", dpi=200)
        print(f"\n[Figure 1 — {model}] saved: {path}")
        plt.close()


# ─────────────────────────────────────────────
# 4.  FIGURE 2 — Inference Latency
#     Boxplot of execution_time per defense mode (2a) and mean latency per
#     attack variant (2b) — two standalone files.
# ─────────────────────────────────────────────
def fig2a_latency_boxplot():
    fig, ax = plt.subplots(figsize=(9, 7.5))

    data_by_mode = [
        df[df["defense_mode"] == m]["execution_time"].dropna().values
        for m in DEFENSE_MODES
    ]
    bp = ax.boxplot(
        data_by_mode,
        patch_artist=True,
        notch=True,
        bootstrap=1000,
        widths=0.45,
        medianprops=dict(color="white", linewidth=2.2),
        whiskerprops=dict(linewidth=1.2),
        capprops=dict(linewidth=1.2),
        flierprops=dict(marker="o", markersize=4, alpha=0.4, linestyle="none"),
        zorder=3,
    )
    for patch, mode in zip(bp["boxes"], DEFENSE_MODES):
        patch.set_facecolor(COLORS[mode])
        patch.set_alpha(0.85)
    for flier, mode in zip(bp["fliers"], DEFENSE_MODES):
        flier.set_markerfacecolor(COLORS[mode])

    ax.set_xticks([1, 2, 3])
    ax.set_xticklabels([DEFENSE_LABELS[m] for m in DEFENSE_MODES], fontsize=14)
    ax.set_ylabel("Execution Time (seconds)", fontsize=15)
    ax.set_title("Inference Latency Distribution per Defense Mode",
                 fontsize=17, fontweight="bold", pad=14)

    # significance brackets
    pairs = [(1, 2), (1, 3), (2, 3)]
    y_max = df["execution_time"].quantile(0.97)
    for k, (a, b) in enumerate(pairs):
        s1 = df[df["defense_mode"] == DEFENSE_MODES[a - 1]]["execution_time"].dropna()
        s2 = df[df["defense_mode"] == DEFENSE_MODES[b - 1]]["execution_time"].dropna()
        _, p = stats.mannwhitneyu(s1, s2, alternative="two-sided")
        sig = "***" if p < 0.001 else ("**" if p < 0.01 else ("*" if p < 0.05 else "ns"))
        y = y_max + 1.5 + k * 2.8
        ax.plot([a, a, b, b], [y - 0.8, y, y, y - 0.8], color="#555555", lw=1.0)
        ax.text((a + b) / 2, y + 0.1, sig, ha="center", va="bottom", fontsize=13)

    plt.tight_layout()
    path = os.path.join(OUTPUT_DIR, "fig2a_latency_boxplot.pdf")
    fig.savefig(path, bbox_inches="tight")
    fig.savefig(path.replace(".pdf", ".png"), bbox_inches="tight", dpi=200)
    print(f"[Figure 2a saved] {path}")
    plt.close()


def fig2b_latency_by_variant():
    fig, ax2 = plt.subplots(figsize=(18, 7))

    x = np.arange(len(ATTACK_ORDER))
    bar_w = 0.22
    for i, mode in enumerate(DEFENSE_MODES):
        sub = df[df["defense_mode"] == mode]
        means, cis = [], []
        for atk in ATTACK_ORDER:
            vals = sub[sub["attack"] == atk]["execution_time"].dropna()
            means.append(vals.mean())
            ci = stats.sem(vals) * stats.t.ppf(0.975, df=len(vals) - 1)
            cis.append(ci)
        offset = (i - len(DEFENSE_MODES) / 2 + 0.5) * bar_w
        ax2.bar(
            x + offset, means,
            width=bar_w,
            yerr=cis,
            color=COLORS[mode],
            hatch=HATCHES[mode],
            label=DEFENSE_LABELS[mode],
            edgecolor="white",
            linewidth=0.6,
            alpha=0.92,
            error_kw=dict(elinewidth=1.2, capsize=3, ecolor="#333333"),
            zorder=3,
        )

    ax2.set_xticks(x)
    ax2.set_xticklabels([ATTACK_LABELS[a] for a in ATTACK_ORDER], fontsize=13, ha="center")
    ax2.set_ylabel("Mean Execution Time (s)", fontsize=15)
    ax2.set_title("Mean Latency per Attack Variant (95% CI error bars)",
                  fontsize=17, fontweight="bold", pad=48)
    ax2.legend(loc="lower center", bbox_to_anchor=(0.5, 1.02), ncol=3,
               framealpha=0.9, edgecolor="#cccccc", fontsize=13)

    plt.tight_layout()
    path = os.path.join(OUTPUT_DIR, "fig2b_latency_by_variant.pdf")
    fig.savefig(path, bbox_inches="tight")
    fig.savefig(path.replace(".pdf", ".png"), bbox_inches="tight", dpi=200)
    print(f"[Figure 2b saved] {path}")
    plt.close()


# ─────────────────────────────────────────────
# 5.  FIGURE 3 — Energy Consumption
#     Violin + mean per defense; heat map per attack
# ─────────────────────────────────────────────
def fig3_energy():
    fig, axes = plt.subplots(1, 2, figsize=(15, 7.0))

    # ─ Left: violin per defense mode
    ax = axes[0]
    data_by_mode = [
        df[df["defense_mode"] == m]["energy_joules"].dropna().values
        for m in DEFENSE_MODES
    ]
    parts = ax.violinplot(
        data_by_mode,
        positions=[1, 2, 3],
        showmeans=True,
        showmedians=True,
        widths=0.55,
    )
    for i, (pc, mode) in enumerate(zip(parts["bodies"], DEFENSE_MODES)):
        pc.set_facecolor(COLORS[mode])
        pc.set_alpha(0.65)
        pc.set_edgecolor(COLORS[mode])
    parts["cmeans"].set_color("#333333")
    parts["cmeans"].set_linewidth(2)
    parts["cmedians"].set_color("white")
    parts["cmedians"].set_linewidth(1.5)
    for k in ["cmins", "cmaxes", "cbars"]:
        parts[k].set_color("#555555")
        parts[k].set_linewidth(1.0)

    ax.set_xticks([1, 2, 3])
    ax.set_xticklabels([DEFENSE_LABELS[m] for m in DEFENSE_MODES], fontsize=13)
    ax.set_ylabel("Energy Consumption (Joules)", fontsize=15)
    ax.set_title("Energy Distribution per Defense Mode\n(violin: KDE; line: mean)", fontsize=16, fontweight="bold")

    # overhead annotations
    baseline_mean = df[df["defense_mode"] == "none"]["energy_joules"].mean()
    for pos, mode in zip([1, 2, 3], DEFENSE_MODES):
        m = df[df["defense_mode"] == mode]["energy_joules"].mean()
        overhead = (m / baseline_mean - 1) * 100
        prefix = "+" if overhead > 0 else ""
        ax.text(pos, ax.get_ylim()[1] * 0.97,
                f"{prefix}{overhead:.1f}%",
                ha="center", va="top", fontsize=13,
                color=COLORS[mode], fontweight="bold")

    # ─ Right: heatmap — mean energy per (attack × defense)
    ax2 = axes[1]
    heat_data = np.zeros((len(ATTACK_ORDER), len(DEFENSE_MODES)))
    for j, mode in enumerate(DEFENSE_MODES):
        for i, atk in enumerate(ATTACK_ORDER):
            vals = df[(df["defense_mode"] == mode) & (df["attack"] == atk)]["energy_joules"]
            heat_data[i, j] = vals.mean() if len(vals) > 0 else np.nan

    im = ax2.imshow(heat_data, cmap="RdYlGn_r", aspect="auto",
                    vmin=np.nanmin(heat_data) * 0.95,
                    vmax=np.nanmax(heat_data) * 1.02)
    for i in range(len(ATTACK_ORDER)):
        for j in range(len(DEFENSE_MODES)):
            val = heat_data[i, j]
            txt_color = "white" if val > np.nanpercentile(heat_data, 60) else "#222222"
            ax2.text(j, i, f"{val:.0f} J",
                     ha="center", va="center",
                     fontsize=12, fontweight="bold", color=txt_color)

    ax2.set_xticks(range(len(DEFENSE_MODES)))
    ax2.set_xticklabels([DEFENSE_LABELS[m] for m in DEFENSE_MODES], fontsize=13)
    ax2.set_yticks(range(len(ATTACK_ORDER)))
    ax2.set_yticklabels([ATTACK_LABELS[a].replace("\n", " ") for a in ATTACK_ORDER], fontsize=13)
    ax2.set_title("Mean Energy (J) per Attack × Defense\n(heatmap)", fontsize=16, fontweight="bold")
    cbar = fig.colorbar(im, ax=ax2, shrink=0.85, pad=0.02)
    cbar.ax.tick_params(labelsize=11)
    cbar.set_label("Mean Energy (J)", fontsize=13)

    plt.tight_layout(w_pad=3)
    path = os.path.join(OUTPUT_DIR, "fig3_energy_consumption.pdf")
    fig.savefig(path, bbox_inches="tight")
    fig.savefig(path.replace(".pdf", ".png"), bbox_inches="tight", dpi=200)
    print(f"[Figure 3 saved] {path}")
    plt.close()


# ─────────────────────────────────────────────
# 6.  FIGURE 4 — Summary Dashboard
#     Multi-panel: security + latency + energy
# ─────────────────────────────────────────────
def fig4_dashboard():
    fig = plt.figure(figsize=(18, 13))
    gs = gridspec.GridSpec(2, 3, figure=fig, hspace=0.55, wspace=0.4, top=0.85)

    # ── (A) Detection rate heatmap (top-left, wide)
    ax_a = fig.add_subplot(gs[0, :2])
    vuln_data = np.zeros((len(ATTACK_ORDER), len(DEFENSE_MODES)))
    for j, mode in enumerate(DEFENSE_MODES):
        for i, atk in enumerate(ATTACK_ORDER):
            vals = df[(df["defense_mode"] == mode) & (df["attack"] == atk)]["is_vulnerable"]
            vuln_data[i, j] = (1 - vals.mean()) * 100 if len(vals) > 0 else np.nan

    im_a = ax_a.imshow(vuln_data, cmap="RdYlGn", aspect="auto", vmin=0, vmax=100)
    for i in range(len(ATTACK_ORDER)):
        for j in range(len(DEFENSE_MODES)):
            v = vuln_data[i, j]
            col = "white" if v < 45 else "#111111"
            ax_a.text(j, i, f"{v:.0f}%",
                      ha="center", va="center",
                      fontsize=13, fontweight="bold", color=col)
    ax_a.set_xticks(range(len(DEFENSE_MODES)))
    ax_a.set_xticklabels([DEFENSE_LABELS[m] for m in DEFENSE_MODES], fontsize=13)
    ax_a.set_yticks(range(len(ATTACK_ORDER)))
    ax_a.set_yticklabels([ATTACK_LABELS[a].replace("\n", " ") for a in ATTACK_ORDER], fontsize=13)
    ax_a.set_title("(A) Detection Rate (%) per Attack × Defense (higher is better)",
                    fontweight="bold", fontsize=15, pad=10)
    cbar_a = fig.colorbar(im_a, ax=ax_a, shrink=0.85, label="Detection Rate (%)")
    cbar_a.ax.tick_params(labelsize=11)
    cbar_a.set_label("Detection Rate (%)", fontsize=13)

    # ── (B) Overall detection rate bar (top-right)
    ax_b = fig.add_subplot(gs[0, 2])
    detect_rates = [
        (1 - df[df["defense_mode"] == m]["is_vulnerable"].mean()) * 100
        for m in DEFENSE_MODES
    ]
    bars = ax_b.barh(
        [DEFENSE_LABELS[m] for m in reversed(DEFENSE_MODES)],
        list(reversed(detect_rates)),
        color=[COLORS[m] for m in reversed(DEFENSE_MODES)],
        height=0.5, edgecolor="white", linewidth=0.7, zorder=3
    )
    for bar, val in zip(bars, reversed(detect_rates)):
        ax_b.text(val + 1.5, bar.get_y() + bar.get_height() / 2,
                  f"{val:.1f}%",
                  va="center", ha="left", fontsize=12, fontweight="bold",
                  color=COLORS[DEFENSE_MODES[2 - list(reversed(detect_rates)).index(val)]])
    ax_b.set_xlim(0, 125)
    ax_b.set_xlabel("Detection Rate (%)", fontsize=13)
    ax_b.tick_params(axis="both", labelsize=12)
    ax_b.set_title("(B) Overall\nDetection Rate", fontweight="bold", fontsize=15, pad=10)
    ax_b.axvline(100, color="gray", linestyle=":", lw=0.8)

    # ── (C) Latency violin (bottom-left)
    ax_c = fig.add_subplot(gs[1, 0])
    data_lat = [df[df["defense_mode"] == m]["execution_time"].dropna().values for m in DEFENSE_MODES]
    parts = ax_c.violinplot(data_lat, positions=[1, 2, 3], showmeans=True, widths=0.5)
    for pc, mode in zip(parts["bodies"], DEFENSE_MODES):
        pc.set_facecolor(COLORS[mode]); pc.set_alpha(0.7)
    parts["cmeans"].set_color("#333333"); parts["cmeans"].set_linewidth(2)
    ax_c.set_xticks([1, 2, 3])
    ax_c.set_xticklabels([DEFENSE_LABELS[m] for m in DEFENSE_MODES], fontsize=11, rotation=8)
    ax_c.tick_params(axis="y", labelsize=11)
    ax_c.set_ylabel("Execution Time (s)", fontsize=13)
    ax_c.set_title("(C) Inference Latency\nDistribution", fontweight="bold", fontsize=15)

    # ── (D) Energy bar + overhead (bottom-center)
    ax_d = fig.add_subplot(gs[1, 1])
    energy_means = [df[df["defense_mode"] == m]["energy_joules"].mean() for m in DEFENSE_MODES]
    energy_stds  = [df[df["defense_mode"] == m]["energy_joules"].std() for m in DEFENSE_MODES]
    xs = np.arange(len(DEFENSE_MODES))
    brs = ax_d.bar(xs, energy_means, yerr=energy_stds,
                   color=[COLORS[m] for m in DEFENSE_MODES],
                   width=0.45, edgecolor="white", linewidth=0.7,
                   error_kw=dict(elinewidth=1.2, capsize=4, ecolor="#333333"),
                   zorder=3)
    baseline = energy_means[0]
    for i, (bar, mean) in enumerate(zip(brs, energy_means)):
        overhead = (mean / baseline - 1) * 100
        prefix = "+" if overhead > 0 else ""
        ax_d.text(bar.get_x() + bar.get_width() / 2,
                  bar.get_height() + energy_stds[i] + 5,
                  f"{prefix}{overhead:.1f}%",
                  ha="center", va="bottom", fontsize=11, fontweight="bold",
                  color=COLORS[DEFENSE_MODES[i]])
    ax_d.set_xticks(xs)
    ax_d.set_xticklabels([DEFENSE_LABELS[m] for m in DEFENSE_MODES], fontsize=11, rotation=8)
    ax_d.tick_params(axis="y", labelsize=11)
    ax_d.set_ylabel("Mean Energy (J)", fontsize=13)
    ax_d.set_title("(D) Energy Consumption\n(mean ± std, overhead vs. none)", fontweight="bold", fontsize=15)

    # ── (E) Radar/spider — per-attack detection rate (bottom-right)
    ax_e = fig.add_subplot(gs[1, 2], polar=True)
    N = len(ATTACK_ORDER)
    angles = np.linspace(0, 2 * np.pi, N, endpoint=False).tolist()
    angles += angles[:1]
    ax_e.set_theta_offset(np.pi / 2)
    ax_e.set_theta_direction(-1)
    ax_e.set_xticks(angles[:-1])
    ax_e.set_xticklabels([ATTACK_LABELS[a].replace("\n", " ") for a in ATTACK_ORDER], fontsize=10)
    ax_e.set_ylim(0, 100)
    ax_e.set_yticks([25, 50, 75, 100])
    ax_e.set_yticklabels(["25%", "50%", "75%", "100%"], fontsize=9, color="gray")
    for mode in DEFENSE_MODES:
        sub = df[df["defense_mode"] == mode]
        vals = [(1 - sub[sub["attack"] == atk]["is_vulnerable"].mean()) * 100 for atk in ATTACK_ORDER]
        vals += vals[:1]
        ax_e.plot(angles, vals, color=COLORS[mode], linewidth=1.8, linestyle="solid")
        ax_e.fill(angles, vals, color=COLORS[mode], alpha=0.12)
    ax_e.set_title("(E) Detection Radar\nper Attack Variant", fontweight="bold", fontsize=15, pad=20)

    # Legend — placed at the very top, directly under the suptitle
    handles = [mpatches.Patch(color=COLORS[m], label=DEFENSE_LABELS[m]) for m in DEFENSE_MODES]
    fig.legend(handles=handles, loc="upper center", ncol=3,
               bbox_to_anchor=(0.5, 0.93),
               framealpha=0.9, edgecolor="#cccccc", fontsize=14)

    fig.suptitle(
        "UAL-Inference Defense Benchmark — Analysis Summary\n"
        "Robustness · Latency · Energy",
        fontsize=18, fontweight="bold", y=0.985
    )

    path = os.path.join(OUTPUT_DIR, "fig4_dashboard.pdf")
    fig.savefig(path, bbox_inches="tight")
    fig.savefig(path.replace(".pdf", ".png"), bbox_inches="tight", dpi=200)
    print(f"[Figure 4 saved] {path}")
    plt.close()


# ─────────────────────────────────────────────
# 7.  FIGURE 5 — Semantic Evasion Gap
#     Bilan across all 9 attack variants (previously stealth-only),
#     split into two standalone files: detection rate / operational cost.
# ─────────────────────────────────────────────
def fig5a_detection_rate_all_variants():
    """Bilan: overall detection rate per defense mode, averaged across all
    9 attack variants — exactly 3 bars (one per mode), mirroring fig5b's
    aggregate structure for operational cost."""
    modes_plot = ["none", "prompt_guard_2", "semantic_intent_guard"]
    rates = [
        (1 - df[df["defense_mode"] == m]["is_vulnerable"].mean()) * 100
        for m in modes_plot
    ]

    fig, ax = plt.subplots(figsize=(9, 7.5))
    xs = np.arange(len(modes_plot))
    bars = ax.bar(
        xs, rates,
        width=0.5,
        color=[COLORS[m] for m in modes_plot],
        hatch=[HATCHES[m] for m in modes_plot],
        edgecolor="white", linewidth=0.8,
        alpha=0.92, zorder=3,
    )
    for bar, val in zip(bars, rates):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 2,
                f"{val:.1f}%", ha="center", va="bottom",
                fontsize=15, fontweight="bold", color="#222222")

    ax.set_xticks(xs)
    ax.set_xticklabels([DEFENSE_LABELS[m] for m in modes_plot], fontsize=14)
    ax.set_ylabel("Detection Rate (%)", fontsize=15)
    ax.set_ylim(0, 115)
    ax.axhline(100, color="gray", linestyle=":", lw=0.9, alpha=0.6)
    ax.set_title(
        "Detection Rate — Bilan Across All 9 Attack Variants",
        fontsize=17, fontweight="bold", pad=14
    )

    plt.tight_layout()
    path = os.path.join(OUTPUT_DIR, "fig5a_detection_rate_all_variants.pdf")
    fig.savefig(path, bbox_inches="tight")
    fig.savefig(path.replace(".pdf", ".png"), bbox_inches="tight", dpi=200)
    print(f"[Figure 5a saved] {path}")
    plt.close()


def fig5b_operational_cost_all_variants():
    """Energy + latency per defense mode, averaged across all 9 attack variants."""
    modes_plot = ["none", "prompt_guard_2", "semantic_intent_guard"]
    energy_m = [df[df["defense_mode"] == m]["energy_joules"].mean() for m in modes_plot]
    time_m   = [df[df["defense_mode"] == m]["execution_time"].mean() for m in modes_plot]

    fig, ax2 = plt.subplots(figsize=(9, 6.5))
    xs = np.arange(len(modes_plot))
    ax2b = ax2.twinx()
    ax2.bar(xs - 0.18, energy_m, width=0.34,
            color=[COLORS[m] for m in modes_plot],
            edgecolor="white", linewidth=0.6, alpha=0.85,
            label="Energy (J)", zorder=3)
    ax2b.bar(xs + 0.18, time_m, width=0.34,
             color=[COLORS[m] for m in modes_plot],
             edgecolor="white", linewidth=0.6, alpha=0.45,
             hatch="//", label="Latency (s)", zorder=3)

    for i, (e, t) in enumerate(zip(energy_m, time_m)):
        ax2.text(i - 0.18, e + max(energy_m) * 0.015, f"{e:.0f} J",
                  ha="center", va="bottom", fontsize=9, fontweight="bold")
        ax2b.text(i + 0.18, t + max(time_m) * 0.015, f"{t:.1f} s",
                   ha="center", va="bottom", fontsize=9, fontweight="bold")

    ax2.set_xticks(xs)
    ax2.set_xticklabels([DEFENSE_LABELS[m] for m in modes_plot], fontsize=14)
    ax2.tick_params(axis="y", labelsize=12)
    ax2b.tick_params(axis="y", labelsize=12)
    ax2.set_ylabel("Mean Energy (J)", fontsize=15, color="#333333")
    ax2b.set_ylabel("Mean Latency (s)", fontsize=15, color="#555555")
    ax2.set_title(
        "Operational Cost — Bilan Across All 9 Attack Variants\n(Energy vs. Latency)",
        fontsize=16, fontweight="bold", pad=48
    )

    h1 = mpatches.Patch(color="gray", label="Energy (J)")
    h2 = mpatches.Patch(color="gray", alpha=0.45, hatch="//", label="Latency (s)")
    ax2.legend(handles=[h1, h2], loc="lower center", bbox_to_anchor=(0.5, 1.02),
               ncol=2, fontsize=13)

    plt.tight_layout()
    path = os.path.join(OUTPUT_DIR, "fig5b_operational_cost_all_variants.pdf")
    fig.savefig(path, bbox_inches="tight")
    fig.savefig(path.replace(".pdf", ".png"), bbox_inches="tight", dpi=200)
    print(f"[Figure 5b saved] {path}")
    plt.close()


# ─────────────────────────────────────────────
# 8.  FIGURE 6 — Per-Model Breakdown
#     Detection rate, latency, and energy broken down by target LLM —
#     no prior figure sliced the results this way.
# ─────────────────────────────────────────────
MODEL_ORDER = ["llama2:13b", "llama3.1:8b", "mistral-nemo", "qwen2.5:7b"]


def fig6a_detection_rate_by_model():
    fig, ax = plt.subplots(figsize=(14, 7.5))
    n_models = len(MODEL_ORDER)
    n_modes = len(DEFENSE_MODES)
    bar_w = 0.24
    x = np.arange(n_models)

    for i, mode in enumerate(DEFENSE_MODES):
        sub = df[df["defense_mode"] == mode]
        rates = [
            (1 - sub[sub["model"] == m]["is_vulnerable"].mean()) * 100
            for m in MODEL_ORDER
        ]
        offset = (i - n_modes / 2 + 0.5) * bar_w
        bars = ax.bar(
            x + offset, rates,
            width=bar_w,
            color=COLORS[mode],
            hatch=HATCHES[mode],
            label=DEFENSE_LABELS[mode],
            edgecolor="white", linewidth=0.6,
            alpha=0.92, zorder=3,
        )
        for bar, val in zip(bars, rates):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1.2,
                    f"{val:.0f}%", ha="center", va="bottom",
                    fontsize=11, fontweight="bold", color=COLORS[mode])

    ax.set_xticks(x)
    ax.set_xticklabels(MODEL_ORDER, fontsize=14)
    ax.set_ylabel("Detection Rate (%)", fontsize=15)
    ax.set_xlabel("Target LLM", fontsize=15)
    ax.set_ylim(0, 115)
    ax.axhline(100, color="gray", linestyle=":", lw=0.9, alpha=0.6)
    ax.set_title(
        "Detection Rate per Target Model — No Defense vs. Prompt Guard 2 vs. UAL Semantic Guard",
        fontsize=16, fontweight="bold", pad=48
    )
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.02), ncol=3,
              framealpha=0.9, edgecolor="#cccccc", fontsize=13)

    plt.tight_layout()
    path = os.path.join(OUTPUT_DIR, "fig6a_detection_rate_by_model.pdf")
    fig.savefig(path, bbox_inches="tight")
    fig.savefig(path.replace(".pdf", ".png"), bbox_inches="tight", dpi=200)
    print(f"[Figure 6a saved] {path}")
    plt.close()


def fig6b_latency_by_model():
    fig, ax = plt.subplots(figsize=(14, 7.5))
    n_models = len(MODEL_ORDER)
    n_modes = len(DEFENSE_MODES)
    bar_w = 0.24
    x = np.arange(n_models)

    for i, mode in enumerate(DEFENSE_MODES):
        sub = df[df["defense_mode"] == mode]
        means, cis = [], []
        for m in MODEL_ORDER:
            vals = sub[sub["model"] == m]["execution_time"].dropna()
            means.append(vals.mean())
            ci = stats.sem(vals) * stats.t.ppf(0.975, df=len(vals) - 1)
            cis.append(ci)
        offset = (i - n_modes / 2 + 0.5) * bar_w
        ax.bar(
            x + offset, means,
            width=bar_w,
            yerr=cis,
            color=COLORS[mode],
            hatch=HATCHES[mode],
            label=DEFENSE_LABELS[mode],
            edgecolor="white", linewidth=0.6,
            alpha=0.92,
            error_kw=dict(elinewidth=1.2, capsize=3, ecolor="#333333"),
            zorder=3,
        )

    ax.set_xticks(x)
    ax.set_xticklabels(MODEL_ORDER, fontsize=14)
    ax.set_ylabel("Mean Execution Time (s)", fontsize=15)
    ax.set_xlabel("Target LLM", fontsize=15)
    ax.set_title(
        "Mean Inference Latency per Target Model (95% CI error bars)",
        fontsize=16, fontweight="bold", pad=48
    )
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.02), ncol=3,
              framealpha=0.9, edgecolor="#cccccc", fontsize=13)

    plt.tight_layout()
    path = os.path.join(OUTPUT_DIR, "fig6b_latency_by_model.pdf")
    fig.savefig(path, bbox_inches="tight")
    fig.savefig(path.replace(".pdf", ".png"), bbox_inches="tight", dpi=200)
    print(f"[Figure 6b saved] {path}")
    plt.close()


def fig6c_energy_by_model():
    fig, ax = plt.subplots(figsize=(14, 7.5))
    n_models = len(MODEL_ORDER)
    n_modes = len(DEFENSE_MODES)
    bar_w = 0.24
    x = np.arange(n_models)

    for i, mode in enumerate(DEFENSE_MODES):
        sub = df[df["defense_mode"] == mode]
        means = [sub[sub["model"] == m]["energy_joules"].mean() for m in MODEL_ORDER]
        stds = [sub[sub["model"] == m]["energy_joules"].std() for m in MODEL_ORDER]
        offset = (i - n_modes / 2 + 0.5) * bar_w
        ax.bar(
            x + offset, means,
            width=bar_w,
            yerr=stds,
            color=COLORS[mode],
            hatch=HATCHES[mode],
            label=DEFENSE_LABELS[mode],
            edgecolor="white", linewidth=0.6,
            alpha=0.92,
            error_kw=dict(elinewidth=1.0, capsize=3, ecolor="#333333"),
            zorder=3,
        )

    ax.set_xticks(x)
    ax.set_xticklabels(MODEL_ORDER, fontsize=14)
    ax.set_ylabel("Mean Energy (J)", fontsize=15)
    ax.set_xlabel("Target LLM", fontsize=15)
    ax.set_title(
        "Mean Energy Consumption per Target Model (± std)",
        fontsize=16, fontweight="bold", pad=48
    )
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.02), ncol=3,
              framealpha=0.9, edgecolor="#cccccc", fontsize=13)

    plt.tight_layout()
    path = os.path.join(OUTPUT_DIR, "fig6c_energy_by_model.pdf")
    fig.savefig(path, bbox_inches="tight")
    fig.savefig(path.replace(".pdf", ".png"), bbox_inches="tight", dpi=200)
    print(f"[Figure 6c saved] {path}")
    plt.close()


# ─────────────────────────────────────────────
# 9.  MAIN — Generate all figures
# ─────────────────────────────────────────────
if __name__ == "__main__":
    print("\n" + "─" * 60)
    print("Generating publication-ready figures …")
    print("─" * 60)
    fig1_robustness()
    fig2a_latency_boxplot()
    fig2b_latency_by_variant()
    fig3_energy()
    fig4_dashboard()
    fig5a_detection_rate_all_variants()
    fig5b_operational_cost_all_variants()
    fig6a_detection_rate_by_model()
    fig6b_latency_by_model()
    fig6c_energy_by_model()

    print("\n" + "=" * 60)
    print(f"All figures saved to: {OUTPUT_DIR}")
    print("Files generated:")
    for f in sorted(os.listdir(OUTPUT_DIR)):
        fpath = os.path.join(OUTPUT_DIR, f)
        size  = os.path.getsize(fpath) / 1024
        print(f"  {f:45s} {size:6.1f} KB")
    print("=" * 60)
