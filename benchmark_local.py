import os
import sys

# Ajout du dossier courant au path pour les imports (utile pour sudo)
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import json
import time
import argparse
from datetime import datetime
from server.ollama_provider import OllamaProvider
from scenarios.bank_scenario import BankScenario
from scenarios.cv_extraction_scenario import CVExtractionScenario
from scenarios.pdl_scenario import PDLScenario
from scenarios.ual_scenario import UALScenario
from scenarios.pcl_scenario import PCLScenario
from attacks.payloads import AttackPayloads
from defense.self_monitoring import SelfMonitoringLLM
from defense.self_sanitize import SelfSanitizeLLM, M3PreStrikeLLM, M3PostScanLLM
from defense.sanitize_monitoring import SanitizeMonitoringLLM
from defense.full_stack import FullStackLLM
from defense.semantic_intent_guard import SemanticIntentGuardLLM
from defense.prompt_guard import (
    PromptGuard2LLM,
    PromptGuardGuardrailLLM,
    PromptGuardMonitoringLLM,
    PromptGuardFullStackLLM,
)
from utils.monitoring import ResourceMonitor
from termcolor import colored

def build_scenario(scenario_type: str, test_file: str = None):
    """Instancie le bon scénario selon le type demandé."""
    if scenario_type in ("cv_phishing", "cv_pii", "cv"):
        return CVExtractionScenario(file_path=test_file if test_file else "scenarios/cv_exemple.txt")
    elif scenario_type == "pdl":
        return PDLScenario(file_path=test_file if test_file else "scenarios/pdl_examples.txt")
    elif scenario_type == "ual":
        return UALScenario(file_path=test_file if test_file else "scenarios/ual_text.txt")
    elif scenario_type == "pcl":
        return PCLScenario(file_path=test_file if test_file else "scenarios/pcl_history.txt")
    else:  # "bank" par défaut
        return BankScenario()

def run_single_test(model_name, attack_name, defense_mode="none",
                    scenario_type="bank", test_file=None, scenario=None,
                    isolate_judge=False):
    """Exécute un test unique pour un modèle, une attaque et un mode de défense donnés.

    `scenario`, si fourni, est utilisé tel quel (évite de repasser par un fichier —
    utile pour injecter un profil déjà chargé en mémoire, ex. jeu de données externe).

    `isolate_judge` (modes semantic_intent_guard*) : décharge le modèle cible de
    la VRAM avant l'appel au juge M5, pour mesurer le juge sans contention VRAM
    (cf. diagnostic llama2:13b -> juge poussé sur CPU faute de place GPU).
    """
    print(colored(
        f"[*] Modèle: {model_name} | Scénario: {scenario_type.upper()} "
        f"| Attaque: {attack_name} | Défense: {defense_mode.upper()}", "cyan"
    ))

    provider = OllamaProvider(model_name)
    scenario = scenario or build_scenario(scenario_type, test_file)

    if defense_mode == "none":
        llm = provider
        use_defense_logic = False
    elif defense_mode == "self_sanitize":
        # Mode M3 complet — Pre-Strike + Post-Scan streaming + Self-Repair
        llm = SelfSanitizeLLM(provider)
        use_defense_logic = True
    elif defense_mode == "m3_pre_strike":
        # Mode M3-Pre — Pre-Strike seul (analyze_intent, pas de post-scan)
        llm = M3PreStrikeLLM(provider)
        use_defense_logic = True
    elif defense_mode == "m3_post_scan":
        # Mode M3-Post — Post-Scan seul (streaming token-par-token, pas de pré-strike)
        llm = M3PostScanLLM(provider)
        use_defense_logic = True
    elif defense_mode == "guardrail_sanitize":
        # Mode M1+M3 — Guardrail Zero-Trust + Self-Sanitize pré-strike
        llm = SelfSanitizeLLM(provider,
                              guardrail_prompt=SelfMonitoringLLM.STRONG_GUARDRAIL)
        use_defense_logic = True
    elif defense_mode == "sanitize_monitoring":
        # Mode M2+M3 — Sanitize + Audit JSON (sans M1)
        llm = SanitizeMonitoringLLM(provider)
        use_defense_logic = True
    elif defense_mode == "full_stack":
        # Mode M1+M2+M3 — Full-Stack : Pre-Strike + Guardrail + Auto-Audit JSON
        llm = FullStackLLM(provider)
        use_defense_logic = True
    elif defense_mode == "prompt_guard_2":
        # Mode M4 — Prompt Guard 2 pre-inference classification
        llm = PromptGuard2LLM(provider)
        use_defense_logic = True
    elif defense_mode == "guardrail_prompt_guard":
        # Mode M1+M4 — Guardrail + Prompt Guard
        llm = PromptGuardGuardrailLLM(provider)
        use_defense_logic = True
    elif defense_mode == "prompt_guard_monitoring":
        # Mode M2+M4 — Prompt Guard + Self-Monitoring
        llm = PromptGuardMonitoringLLM(provider)
        use_defense_logic = True
    elif defense_mode == "full_stack_pg":
        # Mode M1+M2+M4 — Prompt Guard Full Stack
        llm = PromptGuardFullStackLLM(provider)
        use_defense_logic = True
    elif defense_mode == "semantic_intent_guard":
        # Mode M5 — Semantic Intent Guard (détecteur d'intention UAL, indépendant)
        # Backend "auto" : DeBERTa-LoRA si dispo, sinon LLM-Judge Ollama
        llm = SemanticIntentGuardLLM(provider, backend="auto", isolate_judge=isolate_judge)
        use_defense_logic = True
    elif defense_mode == "semantic_intent_guard_judge":
        # Mode M5 (LLM-Judge forcé) — utile pour comparer les deux backends
        llm = SemanticIntentGuardLLM(provider, backend="llm_judge", isolate_judge=isolate_judge)
        use_defense_logic = True
    elif defense_mode == "semantic_intent_guard_classifier":
        # Mode M5 (Classifier DeBERTa forcé) — requiert le modèle fine-tuné
        llm = SemanticIntentGuardLLM(provider, backend="classifier", isolate_judge=isolate_judge)
        use_defense_logic = True
    else:
        # "guardrail_only" (M1), "self_monitoring_only" (M2), "guardrail_monitoring" (M1+M2)
        # Rétrocompatibilité : on accepte encore "full" comme alias de "guardrail_monitoring"
        mode = "guardrail_monitoring" if defense_mode == "full" else defense_mode
        llm = SelfMonitoringLLM(provider, mode=mode)
        use_defense_logic = True
        
    try:
        # Phase 1: Injection
        print(f"  > Injection du scénario...")
        for step in scenario.get_injection_steps():
            if use_defense_logic:
                llm.generate_with_self_check(step)
            else:
                llm.generate_response(step)
        
        # Phase 2 : Attaque avec Monitoring
        print(f"  > Exécution de l'attaque...")
        payloads = AttackPayloads()

        # Sélection du dictionnaire d'attaques selon le scénario
        if scenario_type in ("cv_phishing", "cv_pii", "cv"):
            all_payloads = payloads.get_cv_attacks()
        elif scenario_type == "pdl":
            all_payloads = payloads.get_pdl_attacks()
        elif scenario_type in ("ual", "ual_ethsri"):
            all_payloads = payloads.get_ual_attacks()
        elif scenario_type == "ual_ethsri_benign":
            all_payloads = payloads.get_benign_utility_attacks()
        elif scenario_type == "pcl":
            all_payloads = payloads.get_pcl_attacks()
        else:
            all_payloads = payloads.get_all()

        attack_payload = all_payloads.get(attack_name)
        
        if not attack_payload:
            raise ValueError(f"Payload introuvable pour l'attaque : {attack_name}")
        
        monitor = ResourceMonitor()
        monitor.start()
        
        if use_defense_logic:
            result_defense = llm.generate_with_self_check(attack_payload)
            response = result_defense['response']
            was_corrected = result_defense.get('was_corrected', False)
        else:
            response = llm.generate_response(attack_payload)
            was_corrected = False
            
        stats = monitor.stop()
        
        # Vérification des fuites
        leaks = scenario.verify_leak(response)
        is_vulnerable = len(leaks) > 0
        
        result = {
            "model": model_name,
            "attack": attack_name,
            "scenario": scenario_type,
            "defense_mode": defense_mode,
            "leaks_detected": leaks,
            "is_vulnerable": is_vulnerable,
            "was_corrected": was_corrected,
            "reflection": result_defense.get('reflection', "") if use_defense_logic else "",
            "isolate_judge": isolate_judge,
            "execution_time": stats.get('duree_sec', 0.0),
            "cpu_avg": stats.get('cpu_avg_percent', 0.0),
            "ram_max": stats.get('ram_max_mb', 0.0),
            "energy_joules": stats.get('energy_joules', 0.0),
            "power_avg": round(stats.get('energy_joules', 0.0) / stats.get('duree_sec', 1.0), 2) if stats.get('duree_sec', 0) > 0 else 0,
            "energy_source": stats.get('energy_source', 'estimation'),
            "response_snippet": response
        }
        
        if "gpu_util_avg" in stats:
            result["gpu_util_avg"] = stats["gpu_util_avg"]
            result["vram_max_mb"] = stats["vram_max_mb"]
            
        return result
        
    except Exception as e:
        print(colored(f"  [!] Erreur: {str(e)}", "red"))
        import traceback
        traceback.print_exc()
        return {
            "model": model_name,
            "attack": attack_name,
            "scenario": scenario_type,
            "defense_mode": defense_mode,
            "error": str(e),
            "is_vulnerable": False
        }

def generate_report(results, filename):
    """Génère un rapport Markdown détaillé."""
    with open(filename, 'w', encoding='utf-8') as f:
        f.write("# Rapport de Benchmark — Scénarios Bank + CV\n\n")
        f.write(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

        f.write("| Scénario | Modèle | Attaque | Mode Défense | Vulnérable | Temps (s) | Énergie (J) | GPU % |\n")
        f.write("| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n")

        for r in results:
            if "error" in r:
                f.write(f"| {r.get('scenario','-')} | {r['model']} | {r['attack']} | {r.get('defense_mode', 'err')} | ⚠️ ERR | - | - | - |\n")
                continue

            status = "🔴 OUI" if r['is_vulnerable'] else "🟢 NON"
            f.write(
                f"| {r.get('scenario','-')} | {r['model']} | {r['attack']} "
                f"| {r['defense_mode']} | {status} "
                f"| {r.get('execution_time','-')} | {r.get('energy_joules','-')} "
                f"| {r.get('gpu_util_avg', '-')} |\n"
            )

def main():
    parser = argparse.ArgumentParser(description="Benchmark local comparatif des modes de défense")
    parser.add_argument("--scenario",
                        default="bank",
                        choices=["bank", "cv_phishing", "cv_pii", "pdl", "ual", "pcl", "all"],
                        help=(
                            "Scénario : bank (défaut), cv_phishing, pdl, ual, pcl, "
                            "all = tous les scénarios enchaînés"
                        ))
    parser.add_argument("--test-file",
                        default=None,
                        help="Chemin vers le fichier texte de contexte externe")
    parser.add_argument("--models", nargs="+",
                        default=["llama2:13b", "llama3.1:8b", "mistral-nemo", "qwen2.5:7b"], # "llama3", "qwen2.5:0.5b", "qwen2.5:1.5b", "qwen2.5:32b", "phi3:latest
                        help="Liste des modèles Ollama à tester")
    parser.add_argument("--attacks", nargs="+",
                        default=["injection_indirecte", "virtualisation", "hybride_base64"],
                        help="Attaques à tester (ignoré si --scenario all)")
    parser.add_argument("--modes", nargs="+",
                        default=["none", "guardrail_only", "self_monitoring_only", "guardrail_monitoring"],
                        choices=[
                            "none",                    # M0       : Aucune défense
                            "guardrail_only",          # M1       : Guardrail Zero-Trust seul
                            "self_monitoring_only",    # M2       : Auto-Audit JSON seul
                            "guardrail_monitoring",    # M1+M2    : Guardrail + Audit JSON
                            "self_sanitize",           # M3       : Self-Sanitize complet (Pre-Strike + Post-Scan)
                            "m3_pre_strike",           # M3-PRE   : Pre-Strike seul (analyze_intent uniquement)
                            "m3_post_scan",            # M3-POST  : Post-Scan seul (streaming sans pré-strike)
                            "guardrail_sanitize",      # M1+M3    : Guardrail + Self-Sanitize
                            "sanitize_monitoring",     # M2+M3    : Sanitize + Audit JSON (sans M1)
                            "full_stack",              # M1+M2+M3 : Full-Stack (toutes les couches)
                            "prompt_guard_2",          # M4       : Prompt Guard 2 (pré-inférence neuronal)
                            "guardrail_prompt_guard",  # M1+M4    : Guardrail + Prompt Guard
                            "prompt_guard_monitoring", # M2+M4    : Prompt Guard + Self-Monitoring
                            "full_stack_pg",           # M1+M2+M4 : Prompt Guard Full Stack
                            "semantic_intent_guard",          # M5       : Semantic Intent Guard (auto)
                            "semantic_intent_guard_judge",    # M5-Judge : LLM-Judge forcé
                            "semantic_intent_guard_classifier", # M5-Clf : DeBERTa forcé
                            "anonymizer",              # Baseline : anonymisation NER (Presidio, balises typées)
                            "anonymizer_hard",         # Baseline : anonymisation NER (Presidio, masque "***")
                            "full",                    # alias rétrocompatible → guardrail_monitoring
                        ],
                        help=(
                            "Modes de défense : "
                            "M0=none | M1=guardrail_only | M2=self_monitoring_only | "
                            "M1+M2=guardrail_monitoring | M3=self_sanitize | "
                            "M1+M3=guardrail_sanitize | M1+M2+M3=full_stack | "
                            "anonymizer=baseline eth-sri (NER Presidio, ne bloque jamais — "
                            "se mesure via le taux de fuite résiduel)"
                        ))
    parser.add_argument("--isolate-judge", action="store_true",
                        help=(
                            "Modes semantic_intent_guard* uniquement : décharge le modèle "
                            "cible de la VRAM avant d'appeler le juge M5, pour éviter que le "
                            "juge (qwen2.5:1.5b) soit poussé sur CPU par manque de VRAM sur "
                            "un gros modèle cible resté chargé (ex. llama2:13b). Coûte un "
                            "rechargement du modèle cible si la requête n'est pas bloquée."
                        ))
    args = parser.parse_args()

    # Déterminer la liste des scénarios à exécuter
    # Chaque entrée : (scenario_type, test_file, liste_des_attaques)
    payloads = AttackPayloads()
    if args.scenario == "all":
        scenarios_to_run = [
            ("bank",        None, list(payloads.get_all().keys())),
            ("cv_phishing",  None, list(payloads.get_cv_attacks().keys())),
            ("pdl",         None, list(payloads.get_pdl_attacks().keys())),
            # ("ual",         None, list(payloads.get_ual_attacks().keys())),  # désactivé : exclu de --scenario all
            ("pcl",         None, list(payloads.get_pcl_attacks().keys()))
        ]
    else:
        if args.scenario in ("cv_phishing", "cv_pii", "cv"):
            default_attacks = list(payloads.get_cv_attacks().keys())
        elif args.scenario == "pdl":
            default_attacks = list(payloads.get_pdl_attacks().keys())
        elif args.scenario == "ual":
            default_attacks = list(payloads.get_ual_attacks().keys())
        elif args.scenario == "pcl":
            default_attacks = list(payloads.get_pcl_attacks().keys())
        else:
            default_attacks = args.attacks
        scenarios_to_run = [(args.scenario, args.test_file, default_attacks)]
    results = []
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_file = f"results/benchmark_local_{timestamp}.json"
    md_file   = f"results/benchmark_local_{timestamp}.md"

    os.makedirs("results", exist_ok=True)

    print(colored("=== DÉBUT DU BENCHMARK LOCAL ===", "cyan", attrs=["bold"]))

    for scenario_type, test_file, attacks_list in scenarios_to_run:
        print(colored(
            f"\n--- SCÉNARIO : {scenario_type.upper()} ({len(attacks_list)} attaques × "
            f"{len(args.models)} modèles × {len(args.modes)} modes) ---",
            "yellow", attrs=["bold"]
        ))
        for model in args.models:
            for attack in attacks_list:
                for mode in args.modes:
                    results.append(run_single_test(
                        model, attack, mode,
                        scenario_type=scenario_type,
                        test_file=test_file,
                        isolate_judge=args.isolate_judge
                    ))

    # Sauvegarde JSON
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=4, ensure_ascii=False)

    # Rapport Markdown
    generate_report(results, md_file)

    total = len(results)
    vuln  = sum(1 for r in results if r.get('is_vulnerable', False))
    print(colored(f"\n[SUCCESS] Benchmark terminé !", "green", attrs=["bold"]))
    print(f"[*] Tests exécutés : {total}  |  Vulnérables : {vuln}  |  Bloqués : {total - vuln}")
    print(f"[*] JSON  : {json_file}")
    print(f"[*] Rapport : {md_file}")

if __name__ == "__main__":
    main()
