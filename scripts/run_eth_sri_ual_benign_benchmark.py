"""
run_eth_sri_ual_benign_benchmark.py
=====================================
Volet BÉNIN du benchmark UAL eth-sri/llmprivacy : mesure l'utilité de la
défense (faux positifs) en réutilisant les mêmes profils/textes que
run_eth_sri_ual_benchmark.py, mais avec des tâches neutres (résumé, sentiment,
réponse conversationnelle, paraphrase) à la place de la demande d'inférence.

La métrique clé n'est PAS is_vulnerable (toujours False ici, cf.
UALEthSriBenignScenario) mais was_corrected : chaque True est un FAUX POSITIF
— une requête légitime bloquée à tort par la défense.

Modes de défense inclus par défaut (DEFAULT_MODES) :
  m3_pre_strike          — M3 Pre-Strike (regex comportementaux)
  prompt_guard_2         — M4 Prompt Guard 2
  semantic_intent_guard  — M5 Semantic Intent Guard (autonome, spécialisé UAL)
                           Crucial : vérifie que M5 ne bloque PAS les tâches bénignes.

Usage :
    python scripts/run_eth_sri_ual_benign_benchmark.py
    python scripts/run_eth_sri_ual_benign_benchmark.py --tasks benign_summary
    python scripts/run_eth_sri_ual_benign_benchmark.py --modes m3_pre_strike semantic_intent_guard
"""
import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from benchmark_local import run_single_test  # noqa: E402
from scenarios.ual_ethsri_benign_scenario import UALEthSriBenignScenario  # noqa: E402
from attacks.payloads import AttackPayloads  # noqa: E402
from termcolor import colored  # noqa: E402

DEFAULT_SAMPLE = os.path.join("data", "external", "eth_sri_llmprivacy", "sample_50.jsonl")
DEFAULT_MODELS = [
    "llama2:13b", "llama3.1:8b", "mistral-nemo", "qwen2.5:7b",
    # "llama3", "phi3:latest", "qwen2.5:0.5b", "qwen2.5:1.5b",
]
DEFAULT_MODES = ["m3_pre_strike", "prompt_guard_2", "semantic_intent_guard"]
DEFAULT_TASKS = list(AttackPayloads().get_benign_utility_attacks().keys())


def load_sample(path: str) -> list:
    profiles = []
    with open(path, "r", encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if line:
                profiles.append(json.loads(line))
    if not profiles:
        raise RuntimeError(
            f"Aucun profil valide chargé depuis '{path}'. "
            f"Régénérez-le avec : python3 scripts/prepare_eth_sri_ual_dataset.py --n 50 --seed 42"
        )
    return profiles


def write_markdown_report(results: list, path: str):
    with open(path, "w", encoding="utf-8") as f:
        f.write("# Benchmark UTILITÉ (bénin) — dataset synthétique eth-sri/llmprivacy\n\n")
        f.write(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(
            "Toute ligne `was_corrected=True` est un **faux positif** : une requête "
            "légitime bloquée à tort par la défense.\n\n"
        )

        agg = defaultdict(lambda: {"n": 0, "blocked": 0})
        for r in results:
            if "error" in r:
                continue
            key = (r["model"], r["defense_mode"])
            agg[key]["n"] += 1
            if r.get("was_corrected"):
                agg[key]["blocked"] += 1

        f.write("## Taux de faux positifs par modèle x mode\n\n")
        f.write("| Modèle | Mode | N | Bloqués (FP) | Taux FP |\n")
        f.write("| :--- | :--- | ---: | ---: | ---: |\n")
        for (model, mode), s in sorted(agg.items()):
            n, b = s["n"], s["blocked"]
            rate = 100 * b / n if n else 0
            f.write(f"| {model} | {mode} | {n} | {b} | {rate:.1f}% |\n")

        f.write("\n## Détail par test\n\n")
        f.write("| Modèle | Mode | Tâche | Profil | Bloqué (FP) | Reflection |\n")
        f.write("| :--- | :--- | :--- | ---: | :--- | :--- |\n")
        for r in results:
            if "error" in r:
                f.write(f"| {r['model']} | {r.get('defense_mode','err')} | {r['attack']} | {r.get('profile_id','-')} | ⚠️ ERR | {r['error']} |\n")
                continue
            status = "🔴 OUI" if r.get("was_corrected") else "🟢 non"
            f.write(
                f"| {r['model']} | {r['defense_mode']} | {r['attack']} "
                f"| {r.get('profile_id','-')} | {status} | {r.get('reflection','')[:120]} |\n"
            )


def main():
    parser = argparse.ArgumentParser(description="Benchmark d'utilité (bénin) sur le dataset eth-sri/llmprivacy")
    parser.add_argument("--sample", default=DEFAULT_SAMPLE)
    parser.add_argument("--models", nargs="+", default=DEFAULT_MODELS)
    parser.add_argument("--modes", nargs="+", default=DEFAULT_MODES)
    parser.add_argument("--tasks", nargs="+", default=DEFAULT_TASKS,
                         help="Sous-ensemble de tâches bénignes (défaut : toutes)")
    parser.add_argument("--out-dir", default=os.path.join("results", "eth_sri_ual_benign"))
    parser.add_argument("--isolate-judge", action="store_true",
                         help=(
                             "Modes semantic_intent_guard* uniquement : décharge le modèle cible "
                             "de la VRAM Ollama juste avant l'appel au juge M5, pour mesurer le "
                             "juge sans contention VRAM (cf. cas llama2:13b)."
                         ))
    args = parser.parse_args()

    if not os.path.exists(args.sample):
        print(colored(
            f"[!] Échantillon introuvable : {args.sample}\n"
            f"    Lancez d'abord : python scripts/prepare_eth_sri_ual_dataset.py --n 50",
            "red"
        ))
        sys.exit(1)

    profiles = load_sample(args.sample)
    total = len(profiles) * len(args.models) * len(args.modes) * len(args.tasks)
    print(colored(
        f"=== BENCHMARK UTILITÉ (bénin) — eth-sri/llmprivacy ({len(profiles)} profils × "
        f"{len(args.models)} modèles × {len(args.modes)} modes × {len(args.tasks)} tâches = {total} tests) ===",
        "cyan", attrs=["bold"]
    ))

    results = []
    done = 0
    for model in args.models:
        for mode in args.modes:
            for task in args.tasks:
                for profile in profiles:
                    scenario = UALEthSriBenignScenario(
                        text=profile["text"],
                        personality=profile["personality"],
                        profile_id=profile["id"],
                        feature=profile["feature"],
                        hardness=profile["hardness"],
                    )
                    result = run_single_test(
                        model, task, mode,
                        scenario_type="ual_ethsri_benign",
                        scenario=scenario,
                        isolate_judge=args.isolate_judge,
                    )
                    result["profile_id"] = profile["id"]
                    result["profile_feature"] = profile["feature"]
                    result["dataset_source"] = "eth-sri/llmprivacy"
                    results.append(result)
                    done += 1
                    print(f"  [{done}/{total}] {model} | {mode} | {task} | profil #{profile['id']} terminé")

    os.makedirs(args.out_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = os.path.join(args.out_dir, f"eth_sri_ual_benign_{timestamp}.json")
    md_path = os.path.join(args.out_dir, f"eth_sri_ual_benign_{timestamp}.md")

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    write_markdown_report(results, md_path)

    total_n = len(results)
    fp = sum(1 for r in results if r.get("was_corrected"))
    print(colored(f"\n[SUCCESS] Benchmark utilité terminé !", "green", attrs=["bold"]))
    print(f"[*] Tests exécutés : {total_n}  |  Faux positifs (bloqués à tort) : {fp} ({100*fp/total_n:.1f}%)")
    print(f"[*] JSON  : {json_path}")
    print(f"[*] Rapport : {md_path}")


if __name__ == "__main__":
    main()
