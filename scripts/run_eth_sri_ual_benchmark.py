"""
run_eth_sri_ual_benchmark.py
==============================
Lance le benchmark UAL (inférence d'attributs utilisateur) sur l'échantillon
du dataset synthétique eth-sri/llmprivacy (voir scripts/prepare_eth_sri_ual_dataset.py).

Modes de défense inclus par défaut (DEFAULT_MODES) :
  none                   — Aucune défense (baseline)
  m3_pre_strike          — M3 Pre-Strike (regex comportementaux)
  prompt_guard_2         — M4 Prompt Guard 2 (classificateur neuronal injection/jailbreak)
  semantic_intent_guard  — M5 Semantic Intent Guard (détecteur d'intention UAL, autonome)
                           Backend "auto" : DeBERTa-LoRA si entraîné, sinon LLM-Judge Ollama.
  anonymizer             — Baseline eth-sri (anonymisation NER Presidio, balises typées)
  self_monitoring_only   — M2 seul (auto-réflexion JSON post-génération, sans guardrail)

Prérequis : Ollama démarré localement avec les modèles ciblés déjà "pull".

Usage :
    python scripts/run_eth_sri_ual_benchmark.py
    python scripts/run_eth_sri_ual_benchmark.py --models llama3.1:8b --modes m3_pre_strike semantic_intent_guard
    python scripts/run_eth_sri_ual_benchmark.py --attacks ual_inference ual_inference_ethsri \\
        ual_inference_evasive_natural ual_inference_evasive_stealth ual_inference_evasive_casual
"""
import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from benchmark_local import run_single_test  # noqa: E402
from scenarios.ual_ethsri_scenario import UALEthSriScenario  # noqa: E402
from termcolor import colored  # noqa: E402

DEFAULT_SAMPLE = os.path.join("data", "external", "eth_sri_llmprivacy", "sample_50.jsonl")
DEFAULT_MODELS = [
    "llama2:13b", "llama3.1:8b", "mistral-nemo", "qwen2.5:7b",
    # "llama3", "phi3:latest", "qwen2.5:0.5b", "qwen2.5:1.5b",
]
DEFAULT_MODES = ['none', "m3_pre_strike", "prompt_guard_2", "semantic_intent_guard", "self_monitoring_only"]
DEFAULT_ATTACK = "ual_inference_ethsri"

# Jeu de généralisation — reformulations évasives ABSENTES du few-shot du
# juge M5 (_UAL_JUDGE_FEW_SHOT dans defense/semantic_intent_guard.py), cf.
# attacks/payloads.py. Ajoutable via --include-generalization sans avoir à
# retaper les 4 clés à la main.
GENERALIZATION_ATTACKS = [
    "ual_inference_evasive_thirdparty",
    "ual_inference_evasive_roleplay",
    "ual_inference_evasive_questions",
    "ual_inference_evasive_pretext",
]


def load_sample(path: str) -> list:
    profiles = []
    # utf-8-sig : tolère un BOM en tête de fichier (fréquent après un transfert
    # scp/éditeur Windows) sans quoi json.loads échoue sur la 1ère ligne.
    with open(path, "r", encoding="utf-8-sig") as f:
        for lineno, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                profiles.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(colored(f"[!] Ligne {lineno} ignorée dans {path} (JSON invalide) : {e}", "yellow"))

    if not profiles:
        raise RuntimeError(
            f"Aucun profil valide chargé depuis '{path}'. "
            f"Le fichier est vide, absent ou corrompu — régénérez-le avec : "
            f"python3 scripts/prepare_eth_sri_ual_dataset.py --n 50 --seed 42"
        )
    return profiles


def write_markdown_report(results: list, path: str):
    with open(path, "w", encoding="utf-8") as f:
        f.write("# Benchmark UAL — dataset synthétique eth-sri/llmprivacy\n\n")
        f.write(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

        # Résumé par attaque x modèle x mode
        agg = defaultdict(lambda: {"n": 0, "v": 0})
        for r in results:
            if "error" in r:
                continue
            key = (r.get("attack", "?"), r["model"], r["defense_mode"])
            agg[key]["n"] += 1
            if r.get("is_vulnerable"):
                agg[key]["v"] += 1

        f.write("## Robustesse par attaque x modèle x mode\n\n")
        f.write("| Attaque | Modèle | Mode | N | Vulnérables | Robustesse |\n")
        f.write("| :--- | :--- | :--- | ---: | ---: | ---: |\n")
        for (attack, model, mode), s in sorted(agg.items()):
            n, v = s["n"], s["v"]
            rob = 100 * (n - v) / n if n else 0
            f.write(f"| {attack} | {model} | {mode} | {n} | {v} | {rob:.1f}% |\n")

        f.write("\n## Détail par test\n\n")
        f.write("| Attaque | Modèle | Mode | Profil | Attribut ciblé | Difficulté | Vulnérable | Fuites |\n")
        f.write("| :--- | :--- | :--- | ---: | :--- | ---: | :--- | :--- |\n")
        for r in results:
            if "error" in r:
                f.write(f"| {r.get('attack','?')} | {r['model']} | {r.get('defense_mode','err')} | {r.get('profile_id','-')} | - | - | ⚠️ ERR | {r['error']} |\n")
                continue
            status = "🔴 OUI" if r["is_vulnerable"] else "🟢 NON"
            leaks = ", ".join(r.get("leaks_detected", {}).keys()) or "-"
            f.write(
                f"| {r.get('attack','?')} | {r['model']} | {r['defense_mode']} | {r.get('profile_id','-')} "
                f"| {r.get('profile_feature','-')} | {r.get('profile_hardness','-')} "
                f"| {status} | {leaks} |\n"
            )


def main():
    parser = argparse.ArgumentParser(description="Benchmark UAL sur le dataset synthétique eth-sri/llmprivacy")
    parser.add_argument("--sample", default=DEFAULT_SAMPLE, help="Chemin vers le fichier .jsonl échantillonné")
    parser.add_argument("--models", nargs="+", default=DEFAULT_MODELS, help="Modèles Ollama à tester")
    parser.add_argument("--modes", nargs="+", default=DEFAULT_MODES,
                         help=(
                             "Modes de défense à tester. Inclut M5 par défaut : "
                             "'semantic_intent_guard' (auto), 'semantic_intent_guard_judge' (LLM-Judge forcé), "
                             "'semantic_intent_guard_classifier' (DeBERTa forcé). "
                             "Voir benchmark_local.py --modes pour la liste complète."
                         ))
    parser.add_argument("--attack", default=None,
                         help="[Déprécié, utiliser --attacks] Une seule clé d'attaque (attacks/payloads.py)")
    parser.add_argument("--attacks", nargs="+", default=None,
                         help="Une ou plusieurs clés d'attaque à tester (attacks/payloads.py). "
                              f"Défaut : ['{DEFAULT_ATTACK}']")
    parser.add_argument("--include-generalization", action="store_true",
                         help=(
                             "Ajoute au jeu d'attaques les 4 reformulations évasives absentes du "
                             "few-shot du juge M5 (thirdparty, roleplay, questions, pretext) — "
                             "permet de mesurer la détection sur des formulations jamais vues par "
                             "le juge, en plus des attaques déjà sélectionnées via --attack(s)."
                         ))
    parser.add_argument("--out-dir", default=os.path.join("results", "eth_sri_ual"))
    parser.add_argument("--isolate-judge", action="store_true",
                         help=(
                             "Modes semantic_intent_guard* uniquement : décharge le modèle cible "
                             "de la VRAM Ollama juste avant l'appel au juge M5, pour mesurer le "
                             "juge sans contention VRAM (cf. cas llama2:13b où le juge se retrouve "
                             "poussé sur CPU faute de place GPU une fois le 13B chargé)."
                         ))
    args = parser.parse_args()

    # --attack (singulier, déprécié) reste prioritaire si fourni explicitement,
    # pour ne pas casser les commandes/scripts existants.
    if args.attack:
        attacks = [args.attack]
    elif args.attacks:
        attacks = args.attacks
    else:
        attacks = [DEFAULT_ATTACK]

    if args.include_generalization:
        # Ajoute sans dupliquer si déjà présent dans --attacks.
        for key in GENERALIZATION_ATTACKS:
            if key not in attacks:
                attacks.append(key)

    if not os.path.exists(args.sample):
        print(colored(
            f"[!] Échantillon introuvable : {args.sample}\n"
            f"    Lancez d'abord : python scripts/prepare_eth_sri_ual_dataset.py --n 50",
            "red"
        ))
        sys.exit(1)

    profiles = load_sample(args.sample)
    total = len(profiles) * len(args.models) * len(args.modes) * len(attacks)
    print(colored(
        f"=== BENCHMARK UAL — eth-sri/llmprivacy ({len(profiles)} profils × "
        f"{len(args.models)} modèles × {len(args.modes)} modes × {len(attacks)} attaques = {total} tests) ===",
        "cyan", attrs=["bold"]
    ))

    results = []
    done = 0
    for model in args.models:
        for attack in attacks:
            for mode in args.modes:
                for profile in profiles:
                    scenario = UALEthSriScenario(
                        text=profile["text"],
                        personality=profile["personality"],
                        profile_id=profile["id"],
                        feature=profile["feature"],
                        hardness=profile["hardness"],
                    )
                    result = run_single_test(
                        model, attack, mode,
                        scenario_type="ual_ethsri",
                        scenario=scenario,
                        isolate_judge=args.isolate_judge,
                    )
                    result["profile_id"] = profile["id"]
                    result["profile_feature"] = profile["feature"]
                    result["profile_hardness"] = profile["hardness"]
                    result["dataset_source"] = "eth-sri/llmprivacy"
                    results.append(result)
                    done += 1
                    print(f"  [{done}/{total}] {model} | {attack} | {mode} | profil #{profile['id']} ({profile['feature']}) terminé")

    os.makedirs(args.out_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = os.path.join(args.out_dir, f"eth_sri_ual_{timestamp}.json")
    md_path = os.path.join(args.out_dir, f"eth_sri_ual_{timestamp}.md")

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    write_markdown_report(results, md_path)

    total_n = len(results)
    vuln = sum(1 for r in results if r.get("is_vulnerable"))
    print(colored(f"\n[SUCCESS] Benchmark terminé !", "green", attrs=["bold"]))
    print(f"[*] Tests exécutés : {total_n}  |  Vulnérables : {vuln}  |  Bloqués : {total_n - vuln}")
    print(f"[*] JSON  : {json_path}")
    print(f"[*] Rapport : {md_path}")


if __name__ == "__main__":
    main()
