#!/usr/bin/env python3
"""
UAL-Inference — Attribute-Level Analysis
==========================================
Analysis of vulnerability by:
  1. Attribute category (age, sex, occupation, income, etc.)
  2. Attribute × attack variant (5 variants)
  3. Attribute × hardness level (1–5)
  4. Leak type distribution (which attributes are most extracted)
  5. Hardness regime: memorization vs. semantic inference

Defenses: none · prompt_guard_2 · semantic_intent_guard
Author: UAL Research Lab — 2026
"""

import ast, os, warnings
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.gridspec as gridspec
from matplotlib.ticker import FuncFormatter
from matplotlib.colors import LinearSegmentedColormap

warnings.filterwarnings("ignore")

# ─────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RESULTS_FILE = os.path.join(
    PROJECT_ROOT, "results", "eth_sri_ual", "eth_sri_ual_adversarial_merged.csv"
)
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "results", "figures_by_attribute")
os.makedirs(OUTPUT_DIR, exist_ok=True)

DEFENSE_MODES   = ["none", "prompt_guard_2", "semantic_intent_guard"]
DEFENSE_LABELS  = {
    "none":                  "No Defense",
    "prompt_guard_2":        "Prompt Guard 2",
    "semantic_intent_guard": "UAL Semantic Guard",
}
COLORS = {
    "none":                  "#E63946",
    "prompt_guard_2":        "#457B9D",
    "semantic_intent_guard": "#2A9D8F",
}

# Attribute display names (short)
FEATURE_LABELS = {
    "age":                "Age",
    "sex":                "Sex",
    "occupation":         "Occupation",
    "income_level":       "Income Level",
    "education":          "Education",
    "city_country":       "City / Country",
    "birth_city_country": "Birth City",
    "relationship_status":"Rel. Status",
}
# Ordered by sensitivity (most sensitive first)
FEATURE_ORDER = [
    "sex", "age", "income_level", "occupation",
    "education", "relationship_status", "city_country", "birth_city_country",
]

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
ATTACK_SHORT = {
    "ual_inference_ethsri":              "ETHSRI",
    "ual_inference":                     "Direct",
    "ual_inference_evasive_natural":     "Evasive Nat.",
    "ual_inference_evasive_casual":      "Evasive Cas.",
    "ual_inference_evasive_stealth":     "Evasive Stlth",
    "ual_inference_evasive_thirdparty":  "Evasive 3rdP.",
    "ual_inference_evasive_roleplay":    "Evasive RolePl.",
    "ual_inference_evasive_questions":   "Evasive Qs",
    "ual_inference_evasive_pretext":     "Evasive Pretxt",
}

LEAK_KEYS = [
    "ethsri_leak_sex",
    "ethsri_leak_age",
    "ethsri_leak_occupation",
    "ethsri_leak_income_level",
    "ethsri_leak_education",
    "ethsri_leak_relationship",
    "ethsri_leak_city",
    "ethsri_leak_country",
]
LEAK_LABELS = {
    "ethsri_leak_sex":          "Sex",
    "ethsri_leak_age":          "Age",
    "ethsri_leak_occupation":   "Occupation",
    "ethsri_leak_income_level": "Income Level",
    "ethsri_leak_education":    "Education",
    "ethsri_leak_relationship": "Rel. Status",
    "ethsri_leak_city":         "City",
    "ethsri_leak_country":      "Country",
}

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
    "grid.alpha":       0.3,
    "grid.linestyle":   "--",
})

# ─────────────────────────────────────────────
# LOAD DATA
# ─────────────────────────────────────────────
print("=" * 62)
print("UAL-Inference — Attribute-Level Analysis")
print("=" * 62)

df_all = pd.read_csv(RESULTS_FILE)
df = df_all[df_all["defense_mode"].isin(DEFENSE_MODES)].copy()

# leaks_detected is stored in the merged CSV as the string repr of a Python
# dict (e.g. "{'ethsri_leak_age': True, ...}"), not valid JSON (single quotes,
# Python True/False) — parse it back into a real dict with ast.literal_eval.
def _parse_leaks(val):
    if isinstance(val, dict):
        return val
    if isinstance(val, str) and val.strip():
        try:
            parsed = ast.literal_eval(val)
            return parsed if isinstance(parsed, dict) else {}
        except (ValueError, SyntaxError):
            return {}
    return {}

df["leaks_detected"] = df["leaks_detected"].apply(_parse_leaks)

# Expand leaks_detected into one boolean column per leak key
for key in LEAK_KEYS:
    df[key] = df["leaks_detected"].apply(
        lambda d: bool(d.get(key, False)) if isinstance(d, dict) else False
    )

print(f"Records analyzed : {len(df):,}")
print(f"Attributes       : {sorted(df['profile_feature'].unique())}")
print(f"Hardness levels  : {sorted(df['profile_hardness'].unique())}")


# ─────────────────────────────────────────────
# FIGURE A — Vulnerability by Attribute × Defense
#   Grouped horizontal bars per attribute
# ─────────────────────────────────────────────
def fig_A_attribute_vulnerability():
    fig, ax = plt.subplots(figsize=(15, 9))

    n_feat  = len(FEATURE_ORDER)
    n_modes = len(DEFENSE_MODES)
    bar_h   = 0.22
    y       = np.arange(n_feat)

    for i, mode in enumerate(DEFENSE_MODES):
        sub   = df[df["defense_mode"] == mode]
        rates = [
            (1 - sub[sub["profile_feature"] == feat]["is_vulnerable"].mean()) * 100
            for feat in FEATURE_ORDER
        ]
        offset = (i - n_modes / 2 + 0.5) * bar_h
        bars = ax.barh(
            y + offset, rates,
            height=bar_h,
            color=COLORS[mode],
            label=DEFENSE_LABELS[mode],
            edgecolor="white", linewidth=0.5,
            alpha=0.90, zorder=3,
        )
        for bar, val in zip(bars, rates):
            ax.text(bar.get_width() + 0.8, bar.get_y() + bar.get_height() / 2,
                    f"{val:.0f}%",
                    va="center", fontsize=12,
                    color=COLORS[mode], fontweight="bold")

    ax.set_yticks(y)
    ax.set_yticklabels([FEATURE_LABELS[f] for f in FEATURE_ORDER], fontsize=14)
    ax.set_xlabel("Security Robustness / UAL Detection Rate (%)", fontsize=15)
    ax.set_xlim(0, 112)
    ax.set_title(
        "Security Robustness (UAL Detection Rate) by Attribute Category and Defense Mode (higher is better)",
        fontweight="bold", fontsize=16, pad=48
    )
    ax.axvline(50, color="gray", linestyle=":", lw=0.9, alpha=0.6)
    ax.axvline(100, color="gray", linestyle="--", lw=0.9, alpha=0.6)
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.02), ncol=3,
              framealpha=0.92, edgecolor="#cccccc", fontsize=13)
    ax.invert_yaxis()

    # print stats
    print("\n[A] Security Robustness by attribute × defense:")
    tbl = df.pivot_table(index="profile_feature", columns="defense_mode",
                         values="is_vulnerable", aggfunc=lambda x: (1 - x.mean()) * 100)
    print(tbl[DEFENSE_MODES].round(1).to_string())

    plt.tight_layout()
    p = os.path.join(OUTPUT_DIR, "figA_vulnerability_by_attribute.pdf")
    fig.savefig(p, bbox_inches="tight")
    fig.savefig(p.replace(".pdf", ".png"), bbox_inches="tight", dpi=200)
    print(f"\n[Figure A saved] {p}")
    plt.close()


# ─────────────────────────────────────────────
# FIGURE B — Heatmap: Attribute × Attack Variant
#   (No Defense) — which attribute is most vulnerable to which variant?
# ─────────────────────────────────────────────
def fig_B_heatmap_attribute_attack():
    fig, axes = plt.subplots(1, 3, figsize=(32, 8.5), sharey=True)

    for ax, mode in zip(axes, DEFENSE_MODES):
        sub = df[df["defense_mode"] == mode]
        mat = np.zeros((len(FEATURE_ORDER), len(ATTACK_ORDER)))
        for i, feat in enumerate(FEATURE_ORDER):
            for j, atk in enumerate(ATTACK_ORDER):
                vals = sub[(sub["profile_feature"] == feat) & (sub["attack"] == atk)]["is_vulnerable"]
                mat[i, j] = (1 - vals.mean()) * 100 if len(vals) > 0 else np.nan

        im = ax.imshow(mat, cmap="RdYlGn", aspect="auto", vmin=0, vmax=100)
        for i in range(len(FEATURE_ORDER)):
            for j in range(len(ATTACK_ORDER)):
                v = mat[i, j]
                col = "white" if v < 45 else "#111111"
                ax.text(j, i, f"{v:.0f}%",
                        ha="center", va="center",
                        fontsize=12, fontweight="bold", color=col)

        ax.set_xticks(range(len(ATTACK_ORDER)))
        ax.set_xticklabels([ATTACK_SHORT[a] for a in ATTACK_ORDER],
                           fontsize=12, rotation=18, ha="right")
        ax.set_yticks(range(len(FEATURE_ORDER)))
        ax.set_yticklabels([FEATURE_LABELS[f] for f in FEATURE_ORDER], fontsize=13)
        ax.set_title(f"{DEFENSE_LABELS[mode]}", fontweight="bold", pad=10,
                     color=COLORS[mode], fontsize=16)
        cbar = plt.colorbar(im, ax=ax, shrink=0.78, pad=0.02, label="Detection Rate (%)")
        cbar.ax.tick_params(labelsize=11)
        cbar.set_label("Detection Rate (%)", fontsize=13)

    fig.suptitle(
        "UAL Detection Rate (%) by Attribute Category × Attack Variant (higher is better)",
        fontsize=19, fontweight="bold", y=1.03
    )
    plt.tight_layout(w_pad=1.5)
    p = os.path.join(OUTPUT_DIR, "figB_heatmap_attribute_attack.pdf")
    fig.savefig(p, bbox_inches="tight")
    fig.savefig(p.replace(".pdf", ".png"), bbox_inches="tight", dpi=200)
    print(f"[Figure B saved] {p}")
    plt.close()


# ─────────────────────────────────────────────
# FIGURE C — Leak Type Distribution
#   Which attribute is most often extracted (per defense)
# ─────────────────────────────────────────────
def fig_C_leak_distribution():
    fig, axes = plt.subplots(1, 3, figsize=(22, 7.0), sharey=True)

    for ax, mode in zip(axes, DEFENSE_MODES):
        sub = df[df["defense_mode"] == mode]
        leak_rates = [
            sub[key].mean() * 100 for key in LEAK_KEYS
        ]
        colors_bar = plt.cm.RdYlGn_r(np.linspace(0.15, 0.85, len(LEAK_KEYS)))
        bars = ax.barh(
            [LEAK_LABELS[k] for k in LEAK_KEYS],
            leak_rates,
            color=colors_bar,
            edgecolor="white", linewidth=0.6,
            height=0.55, zorder=3
        )
        for bar, val in zip(bars, leak_rates):
            if val > 0.5:
                ax.text(val + 0.5, bar.get_y() + bar.get_height() / 2,
                        f"{val:.1f}%",
                        va="center", fontsize=12, fontweight="bold",
                        color="#333333")
        ax.set_xlim(0, 85)
        ax.set_xlabel("Extraction Rate (%)", fontsize=14)
        ax.tick_params(axis="both", labelsize=13)
        ax.set_title(f"{DEFENSE_LABELS[mode]}", fontweight="bold",
                     color=COLORS[mode], fontsize=16, pad=9)
        ax.invert_yaxis()
        ax.axvline(20, color="gray", linestyle=":", lw=0.8, alpha=0.5)

    fig.suptitle(
        "Attribute Extraction Rate — Which Personal Data is Most Leaked?",
        fontsize=19, fontweight="bold", y=1.03
    )
    plt.tight_layout(w_pad=2.0)
    p = os.path.join(OUTPUT_DIR, "figC_leak_distribution.pdf")
    fig.savefig(p, bbox_inches="tight")
    fig.savefig(p.replace(".pdf", ".png"), bbox_inches="tight", dpi=200)

    # Print leak stats
    print("\n[C] Extraction rate per leak type × defense:")
    leak_df = pd.DataFrame({
        DEFENSE_LABELS[m]: [df[df["defense_mode"] == m][k].mean() * 100
                            for k in LEAK_KEYS]
        for m in DEFENSE_MODES
    }, index=[LEAK_LABELS[k] for k in LEAK_KEYS])
    print(leak_df.round(1).to_string())
    print(f"\n[Figure C saved] {p}")
    plt.close()


# ─────────────────────────────────────────────
# FIGURE D — Hardness × Defense × Attribute
#   Memorization (h=1-2) vs. Semantic Inference (h=4-5)
# ─────────────────────────────────────────────
def fig_D_hardness_by_attribute():
    fig, axes = plt.subplots(1, 2, figsize=(19, 8.5))

    regimes = {
        "Memorization regime\n(Hardness 1–2)":        [1, 2],
        "Semantic inference regime\n(Hardness 4–5)":  [4, 5],
    }

    for ax, (regime_label, hardness_vals) in zip(axes, regimes.items()):
        sub_reg = df[df["profile_hardness"].isin(hardness_vals)]

        n_feat  = len(FEATURE_ORDER)
        n_modes = len(DEFENSE_MODES)
        bar_h   = 0.22
        y       = np.arange(n_feat)

        for i, mode in enumerate(DEFENSE_MODES):
            sub = sub_reg[sub_reg["defense_mode"] == mode]
            rates = [
                (1 - sub[sub["profile_feature"] == feat]["is_vulnerable"].mean()) * 100
                if len(sub[sub["profile_feature"] == feat]) > 0 else 0
                for feat in FEATURE_ORDER
            ]
            offset = (i - n_modes / 2 + 0.5) * bar_h
            bars = ax.barh(
                y + offset, rates,
                height=bar_h,
                color=COLORS[mode],
                label=DEFENSE_LABELS[mode],
                edgecolor="white", linewidth=0.5,
                alpha=0.88, zorder=3
            )
            for bar, val in zip(bars, rates):
                ax.text(bar.get_width() + 0.5, bar.get_y() + bar.get_height() / 2,
                        f"{val:.0f}%",
                        va="center", fontsize=11,
                        color=COLORS[mode], fontweight="bold")

        ax.set_yticks(y)
        ax.set_yticklabels([FEATURE_LABELS[f] for f in FEATURE_ORDER], fontsize=13)
        ax.set_xlabel("Security Robustness / UAL Detection Rate (%)", fontsize=14)
        ax.set_xlim(0, 112)
        ax.tick_params(axis="x", labelsize=12)
        ax.set_title(regime_label, fontweight="bold", pad=10, fontsize=15)
        ax.axvline(50, color="gray", linestyle=":", lw=0.9, alpha=0.5)
        ax.axvline(100, color="gray", linestyle="--", lw=0.9, alpha=0.5)
        ax.invert_yaxis()

    handles = [mpatches.Patch(color=COLORS[m], label=DEFENSE_LABELS[m]) for m in DEFENSE_MODES]
    fig.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, 0.93),
               ncol=3, framealpha=0.92, edgecolor="#cccccc", fontsize=14)

    fig.suptitle(
        "Security Robustness (UAL Detection Rate): Memorization vs. Semantic Inference Regime",
        fontsize=19, fontweight="bold", y=1.02
    )
    plt.tight_layout(w_pad=3.0, rect=[0, 0, 1, 0.88])
    p = os.path.join(OUTPUT_DIR, "figD_hardness_by_attribute.pdf")
    fig.savefig(p, bbox_inches="tight")
    fig.savefig(p.replace(".pdf", ".png"), bbox_inches="tight", dpi=200)

    print("\n[D] Hardness regime × feature × defense (detection rate):")
    for h_label, h_vals in regimes.items():
        print(f"\n  {h_label.strip()}")
        sub_h = df[df["profile_hardness"].isin(h_vals)]
        tbl = sub_h.pivot_table(index="profile_feature", columns="defense_mode",
                                values="is_vulnerable", aggfunc=lambda x: (1 - x.mean()) * 100)
        print(tbl[DEFENSE_MODES].round(1).to_string())
    print(f"\n[Figure D saved] {p}")
    plt.close()


# ─────────────────────────────────────────────
# FIGURE E — Hardness Curve per Defense
#   Line plot: vulnerability vs. hardness level (1→5), per defense
# ─────────────────────────────────────────────
def fig_E_hardness_curve():
    """Two standalone, enlarged figures (one file each) instead of the two
    panels previously packed side by side into a single image."""
    hardness_levels = [1, 2, 3, 4, 5]

    def _place_title_and_legend(ax, title, n_items, ncol=1):
        # Legend directly under the title, title above the legend. Pad scales
        # with the number of legend rows so a wrapped (multi-row) legend
        # never overlaps the title text above it.
        n_rows = -(-n_items // ncol)  # ceil division
        ax.set_title(title, fontweight="bold", fontsize=16, pad=42 + 26 * n_rows)
        ax.legend(
            loc="lower center", bbox_to_anchor=(0.5, 1.02), ncol=ncol,
            framealpha=0.92, edgecolor="#cccccc", fontsize=12,
        )

    # ── File 1: overall hardness curve, all defense modes (previously left panel) ──
    fig, ax = plt.subplots(figsize=(11, 8))
    for mode in DEFENSE_MODES:
        sub = df[df["defense_mode"] == mode]
        rates = [
            (1 - sub[sub["profile_hardness"] == h]["is_vulnerable"].mean()) * 100
            for h in hardness_levels
        ]
        ax.plot(hardness_levels, rates,
                marker="o", markersize=10,
                color=COLORS[mode], linewidth=3,
                label=DEFENSE_LABELS[mode], zorder=3)
        for h, r in zip(hardness_levels, rates):
            ax.text(h, r + 2.5, f"{r:.0f}%",
                    ha="center", fontsize=11, color=COLORS[mode], fontweight="bold")

    ax.set_xlabel("Inference Hardness Level (1=Explicit → 5=Fully Implicit)", fontsize=13)
    ax.set_ylabel("Security Robustness / UAL Detection Rate (%)", fontsize=13)
    ax.set_ylim(0, 115)
    ax.set_xticks(hardness_levels)
    ax.set_xticklabels([
        f"h={h}\n({'Memorization' if h <= 2 else 'Semantic' if h >= 4 else 'Mixed'})"
        for h in hardness_levels
    ], fontsize=11)
    ax.tick_params(axis="y", labelsize=11)
    ax.axvspan(0.6, 2.4, alpha=0.07, color="#457B9D")
    ax.axvspan(3.6, 5.4, alpha=0.07, color="#E63946")
    ax.text(1.5, 8, "Memorization\nregime", ha="center", fontsize=10, color="#457B9D", alpha=0.8)
    ax.text(4.5, 8, "Semantic\ninference", ha="center", fontsize=10, color="#E63946", alpha=0.8)

    _place_title_and_legend(
        ax, "UAL Detection Rate vs. Inference Hardness (all attributes combined)",
        n_items=len(DEFENSE_MODES), ncol=3
    )

    plt.tight_layout()
    p1 = os.path.join(OUTPUT_DIR, "figE1_hardness_curve_by_defense.pdf")
    fig.savefig(p1, bbox_inches="tight")
    fig.savefig(p1.replace(".pdf", ".png"), bbox_inches="tight", dpi=200)
    plt.close(fig)

    # ── File 2: per-attribute hardness curve, No Defense only (previously right panel) ──
    fig, ax2 = plt.subplots(figsize=(11, 8))
    sub_none = df[df["defense_mode"] == "none"]
    cmap_feat = plt.cm.tab10(np.linspace(0, 0.9, len(FEATURE_ORDER)))
    for feat, col in zip(FEATURE_ORDER, cmap_feat):
        sub_f = sub_none[sub_none["profile_feature"] == feat]
        rates, hs = [], []
        for h in hardness_levels:
            v = sub_f[sub_f["profile_hardness"] == h]["is_vulnerable"]
            if len(v) > 0:
                rates.append((1 - v.mean()) * 100)
                hs.append(h)
        ax2.plot(hs, rates,
                 marker="o", markersize=7, linewidth=2,
                 color=col, label=FEATURE_LABELS[feat], alpha=0.85)

    ax2.set_xlabel("Inference Hardness Level", fontsize=13)
    ax2.set_ylabel("UAL Detection Rate (%) — No Defense", fontsize=13)
    ax2.set_ylim(0, 115)
    ax2.set_xticks(hardness_levels)
    ax2.tick_params(axis="both", labelsize=11)

    _place_title_and_legend(
        ax2, "Per-Attribute UAL Detection Rate vs. Hardness (No Defense)",
        n_items=len(FEATURE_ORDER), ncol=4
    )

    plt.tight_layout()
    p2 = os.path.join(OUTPUT_DIR, "figE2_hardness_curve_by_attribute.pdf")
    fig.savefig(p2, bbox_inches="tight")
    fig.savefig(p2.replace(".pdf", ".png"), bbox_inches="tight", dpi=200)
    plt.close(fig)

    print("\n[E] Hardness × defense UAL detection rate:")
    tbl = df.pivot_table(index="profile_hardness", columns="defense_mode",
                         values="is_vulnerable", aggfunc=lambda x: (1 - x.mean()) * 100)
    print(tbl[DEFENSE_MODES].round(1).to_string())
    print(f"\n[Figure E1 saved] {p1}")
    print(f"[Figure E2 saved] {p2}")


# ─────────────────────────────────────────────
# FIGURE F — Attribute Sensitivity Ranking
#   Bubble chart: vulnerability (no defense) × energy cost
# ─────────────────────────────────────────────
def fig_F_attribute_ranking():
    fig, ax = plt.subplots(figsize=(14, 9))

    sub_none = df[df["defense_mode"] == "none"]
    sub_usg  = df[df["defense_mode"] == "semantic_intent_guard"]
    sub_pg2  = df[df["defense_mode"] == "prompt_guard_2"]

    x_detect_none = []
    x_detect_pg2  = []
    y_energy      = []
    labels        = []
    sizes         = []

    for feat in FEATURE_ORDER:
        v_none = (1 - sub_none[sub_none["profile_feature"] == feat]["is_vulnerable"].mean()) * 100
        v_pg2  = (1 - sub_pg2[sub_pg2["profile_feature"] == feat]["is_vulnerable"].mean()) * 100
        e      = sub_none[sub_none["profile_feature"] == feat]["energy_joules"].mean()
        n      = len(sub_none[sub_none["profile_feature"] == feat])

        x_detect_none.append(v_none)
        x_detect_pg2.append(v_pg2)
        y_energy.append(e)
        labels.append(FEATURE_LABELS[feat])
        sizes.append(n * 0.9)

    scatter = ax.scatter(
        x_detect_none, y_energy,
        s=sizes,
        c=x_detect_pg2,
        cmap="RdYlGn",
        vmin=20, vmax=100,
        edgecolors="#333333", linewidth=0.8,
        zorder=3, alpha=0.88
    )

    for i, label in enumerate(labels):
        ax.annotate(
            label,
            (x_detect_none[i], y_energy[i]),
            xytext=(6, 4),
            textcoords="offset points",
            fontsize=13, fontweight="bold", color="#222222"
        )

    cbar = plt.colorbar(scatter, ax=ax, pad=0.02, shrink=0.85)
    cbar.ax.tick_params(labelsize=12)
    cbar.set_label("Detection Rate with\nPrompt Guard 2 (%)", fontsize=13)

    ax.set_xlabel(
        "UAL Detection Rate (%) — No Defense\n(x-axis = baseline detection without protection)",
        fontsize=14
    )
    ax.set_ylabel("Mean Energy per Query (J) — No Defense", fontsize=14)
    ax.tick_params(axis="both", labelsize=12)
    ax.set_title(
        "Attribute Sensitivity Map\n"
        "X: Detection Rate (no defense)  ·  Y: Energy cost  ·  Color: Detection Rate (Prompt Guard 2)  ·  Size: N queries",
        fontweight="bold", fontsize=15, pad=12
    )

    ax.axvline(30, color="#E63946", linestyle="--", lw=1.0, alpha=0.6)
    ax.axhline(np.mean(y_energy), color="gray", linestyle=":", lw=1.0, alpha=0.6)
    ax.text(5, ax.get_ylim()[0] + 50, "High risk\nzone\n(low detection)", fontsize=12,
            color="#E63946", alpha=0.85)

    plt.tight_layout()
    p = os.path.join(OUTPUT_DIR, "figF_attribute_sensitivity_map.pdf")
    fig.savefig(p, bbox_inches="tight")
    fig.savefig(p.replace(".pdf", ".png"), bbox_inches="tight", dpi=200)
    print(f"[Figure F saved] {p}")
    plt.close()


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
if __name__ == "__main__":
    print("\n" + "─" * 62)
    print("Generating attribute-level figures …")
    print("─" * 62)
    fig_A_attribute_vulnerability()
    fig_B_heatmap_attribute_attack()
    fig_C_leak_distribution()
    fig_D_hardness_by_attribute()
    fig_E_hardness_curve()
    fig_F_attribute_ranking()

    print("\n" + "=" * 62)
    print(f"All figures saved to: {OUTPUT_DIR}")
    for fname in sorted(os.listdir(OUTPUT_DIR)):
        fpath = os.path.join(OUTPUT_DIR, fname)
        size  = os.path.getsize(fpath) / 1024
        print(f"  {fname:50s} {size:6.1f} KB")
    print("=" * 62)
