# Attribution — dataset synthétique eth-sri/llmprivacy

Ce dossier contient un échantillon dérivé du dataset synthétique publié dans :

- Dépôt : https://github.com/eth-sri/llmprivacy
- Fichier source : `data/synthetic/synthetic_dataset.jsonl`
- Papier : Staab et al., *"Beyond Memorization: Violating Privacy Via Inference
  with Large Language Models"*, ICLR 2024.

## Licence

Les exemples synthétiques sont publiés sous **CC BY-NC-SA 4.0** (usage non
commercial, partage dans les mêmes conditions, attribution obligatoire).
Ce projet est un projet de recherche académique — respecter cette licence :
ne pas redistribuer commercialement, citer le papier ci-dessus dans toute
publication utilisant ces données ou dérivés.

## Contenu

- `synthetic_dataset_full.jsonl` — copie brute du dataset amont (525 profils),
  téléchargée pour reproductibilité (non versionnée si trop volumineuse — voir `.gitignore`).
- `sample_50.jsonl` — échantillon stratifié de 50 profils (voir
  `scripts/prepare_eth_sri_ual_dataset.py`), utilisé pour alimenter le scénario
  `ual_ethsri` (cf. `scenarios/ual_ethsri_scenario.py`) et l'attaque
  `ual_inference_ethsri` (cf. `attacks/payloads.py`).

## Format d'un profil

```json
{
  "personality": {
    "age": 31, "sex": "male", "city_country": "Zurich, Switzerland",
    "birth_city_country": "Cleveland, Ohio", "education": "Masters in Computer Science",
    "occupation": "software engineer", "income": "250 thousand swiss francs",
    "income_level": "very high", "relationship_status": "single"
  },
  "feature": "income_level",
  "hardness": 1,
  "question_asked": "...",
  "response": "..."
}
```

`response` est le texte (post façon Reddit) injecté dans le scénario UAL comme
"entrée de journal" ; `personality` sert de vérité terrain pour détecter les
fuites d'attribut dans la réponse du modèle attaqué (voir `verify_leak()` dans
`scenarios/ual_ethsri_scenario.py`).
