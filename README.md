# UAL Attack Lab 🛡️⚡

Ce dossier est un **extrait autonome et minimal** du dépôt de recherche complet, contenant uniquement ce qui est nécessaire pour reproduire le pipeline **User Attribute Inference (UAL-Inference)** utilisé dans l'article `UAL_Rapport/` : inférence non autorisée d'attributs personnels (âge, sexe, localisation, profession, etc.) à partir d'un texte en apparence anodin, et évaluation de deux défenses en amont du LLM cible — **Prompt Guard 2** (baseline) et **UAL Semantic Guard** (contribution proposée).

Les autres familles de scénarios du dépôt d'origine (Bank, CV, PDL, PCL) ne sont **pas exploitables** depuis ce dossier — voir [Fichiers non utilisés](#-fichiers-non-utilisés-mais-présents) plus bas.

---

## 🎯 Ce que couvre ce pipeline

- **9 variantes d'attaque UAL** (5 "core", explicite → évasif ; 4 "generalization", stratégies d'évasion hors du few-shot du juge) contre 4 LLM open-weight locaux (Llama 2-13B, Llama 3.1-8B, Mistral-Nemo, Qwen 2.5-7B).
- **8 tâches bénignes** (résumé, sentiment, réponse, paraphrase, traduction, relecture, mots-clés, titre) pour mesurer le taux de faux positifs.
- **3 conditions de défense** : `none` (sans défense), `prompt_guard_2`, `semantic_intent_guard` (UAL Semantic Guard, LLM-as-a-Judge local Qwen2.5-1.5B).
- **Mesure d'impact opérationnel** : latence et consommation énergétique (CPU via `perf`/RAPL, GPU via NVML) par requête.
- Échantillon actuel : **100 profils** SynthPAI (`data/external/eth_sri_llmprivacy/sample_100.jsonl`), stratifiés pour une distribution de hardness équilibrée (20 profils par niveau $h\in\{1,\ldots,5\}$).

---

## 📊 Aperçu des résultats

![Dashboard UAL-Inference — robustesse, latence, énergie](results/figures/fig4_dashboard.png)

Tableau de bord généré par `scripts/analyze_ual_results.py` à partir de `results/eth_sri_ual/eth_sri_ual_adversarial_merged.csv` (100 profils × 4 modèles × 9 variantes × 3 modes) : **(A)** taux de détection par attaque × défense, **(B)** taux de détection global (No Defense 29,8 % · Prompt Guard 2 46,2 % · UAL Semantic Guard 100 %), **(C)** distribution de latence, **(D)** consommation énergétique moyenne, **(E)** détection par variante d'attaque. Se régénère avec :
```bash
python3 scripts/analyze_ual_results.py
```

---

## 📂 Structure du dossier

```
UAL_Attack_Lab/
├── README.md
├── requirements.txt
├── benchmark_local.py          # Moteur d'exécution partagé (run_single_test)
│
├── attacks/
│   └── payloads.py              # Tous les payloads d'attaque, dont get_ual_attacks()
├── defense/
│   ├── prompt_guard.py          # M4 — Prompt Guard 2 (DeBERTa-v3)
│   ├── semantic_intent_guard.py # M5 — UAL Semantic Guard (LLM-as-a-Judge)
│   ├── self_monitoring.py, self_sanitize.py, sanitize_monitoring.py,
│   └── full_stack.py, anonymizer.py   # Chargés par defense/__init__.py, non utilisés par UAL
├── scenarios/
│   ├── ual_ethsri_scenario.py         # Scénario adversarial UAL (utilisé)
│   ├── ual_ethsri_benign_scenario.py  # Scénario bénin UAL (utilisé)
│   └── bank_scenario.py, cv_extraction_scenario.py, pdl_scenario.py,
│       ual_scenario.py, pcl_scenario.py   # Importés par benchmark_local.py, non utilisés par UAL
├── server/
│   └── ollama_provider.py       # Client Ollama (http://localhost:11434)
├── utils/
│   └── monitoring.py            # ResourceMonitor (énergie/latence)
│
├── scripts/
│   ├── prepare_eth_sri_ual_dataset.py   # Télécharge le corpus SynthPAI + échantillonne
│   ├── extend_eth_sri_sample.py         # Ajoute un lot équilibré en hardness
│   ├── run_eth_sri_ual_benchmark.py     # Lance le volet adversarial
│   ├── run_eth_sri_ual_benign_benchmark.py  # Lance le volet bénin (faux positifs)
│   ├── analyze_ual_results.py           # Figures : robustesse, latence, énergie
│   ├── analyze_ual_by_attribute.py      # Figures : détail par attribut / hardness
│   └── analyze_ual_benign.py            # Figures : préservation d'utilité, tradeoff
│
├── data/external/eth_sri_llmprivacy/
│   ├── synthetic_dataset_full.jsonl     # Corpus SynthPAI complet (525 profils)
│   ├── sample_50.jsonl                  # 1er lot (16/12/4/12/6 par hardness)
│   ├── sample_50_batch2.jsonl           # 2e lot, équilibrant le 1er
│   ├── sample_100.jsonl                 # Combiné, 20 profils par niveau de hardness
│   └── ATTRIBUTION.md                   # Licence SynthPAI (CC BY-NC-SA 4.0)
│
├── models/ual_intent_detector_lora/     # Checkpoint DeBERTa+LoRA (backend "classifier" optionnel de M5)
│
├── results/
│   ├── eth_sri_ual/            # Runs adversariaux bruts (.json/.md) + eth_sri_ual_adversarial_merged.csv
│   ├── eth_sri_ual_benign/     # Runs bénins bruts (.json/.md) + eth_sri_ual_benign_merged_v2.csv
│   ├── figures/                # Sorties de analyze_ual_results.py
│   ├── figures_by_attribute/   # Sorties de analyze_ual_by_attribute.py
│   └── figures_benign/         # Sorties de analyze_ual_benign.py
│
└── UAL_Rapport/                # Article LaTeX complet (main.tex + sections + figures/ + references.bib)
```

---

## 🛠️ Installation & prérequis

- Python 3.8+
- [Ollama](https://ollama.com/) démarré localement, avec les 5 modèles suivants déjà tirés :
  ```bash
  ollama pull llama2:13b
  ollama pull llama3.1:8b
  ollama pull mistral-nemo
  ollama pull qwen2.5:7b
  ollama pull qwen2.5:1.5b   # modèle du Juge (UAL Semantic Guard)
  ```
- (Linux, pour la mesure d'énergie CPU) :
  ```bash
  sudo apt update
  sudo apt install linux-tools-common linux-tools-generic linux-tools-$(uname -r)
  sudo sysctl -w kernel.perf_event_paranoid=-1
  ```

```bash
pip install -r requirements.txt
```

---

## ⚔️ Utilisation

### 1. Préparer / étendre le jeu de profils
```bash
# Génère data/external/eth_sri_llmprivacy/sample_50.jsonl (déjà présent)
python3 scripts/prepare_eth_sri_ual_dataset.py --n 50 --seed 42

# Ajoute un second lot équilibrant la hardness (déjà présent : sample_50_batch2.jsonl / sample_100.jsonl)
python3 scripts/extend_eth_sri_sample.py --n 50 --seed 123
```

### 2. Lancer le benchmark adversarial (9 variantes × 4 modèles × 3 modes)
```bash
python3 scripts/run_eth_sri_ual_benchmark.py \
    --sample data/external/eth_sri_llmprivacy/sample_100.jsonl \
    --modes none prompt_guard_2 semantic_intent_guard \
    --attacks ual_inference_ethsri ual_inference ual_inference_evasive_natural ual_inference_evasive_stealth ual_inference_evasive_casual \
    --include-generalization
```

### 3. Lancer le benchmark bénin (faux positifs)
```bash
python3 scripts/run_eth_sri_ual_benign_benchmark.py \
    --sample data/external/eth_sri_llmprivacy/sample_100.jsonl \
    --modes none prompt_guard_2 semantic_intent_guard
```

Chaque run écrit un `.json`/`.md` timestampé dans `results/eth_sri_ual/` ou `results/eth_sri_ual_benign/`. Les CSV fusionnés (`eth_sri_ual_adversarial_merged.csv`, `eth_sri_ual_benign_merged_v2.csv`) doivent être mis à jour manuellement après un nouveau run (aucun script de fusion automatique n'est fourni dans ce dossier).

### 4. Générer les figures
```bash
python3 scripts/analyze_ual_results.py        # → results/figures/
python3 scripts/analyze_ual_by_attribute.py   # → results/figures_by_attribute/
python3 scripts/analyze_ual_benign.py         # → results/figures_benign/
```

### 5. Compiler l'article
```bash
cd UAL_Rapport
pdflatex main.tex && bibtex main && pdflatex main.tex && pdflatex main.tex
```

---

## ⚠️ Fichiers non utilisés mais présents

`benchmark_local.py` importe systématiquement les scénarios Bank/CV/PDL/PCL, et `defense/__init__.py` importe systématiquement tous les modes de défense (dont `anonymizer.py`) — ces fichiers doivent donc rester présents pour que les imports ne cassent pas, même s'ils ne sont jamais invoqués par les scripts UAL ci-dessus.

---

> [!WARNING]
> **Avertissement de sécurité** : ce projet est développé strictement à des fins de recherche académique et d'évaluation défensive. Ne pas utiliser ces payloads sur des systèmes en production tiers sans autorisation explicite.
