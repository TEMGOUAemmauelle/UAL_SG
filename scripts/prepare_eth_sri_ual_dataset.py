"""
prepare_eth_sri_ual_dataset.py
================================
Télécharge (si nécessaire) le dataset synthétique de eth-sri/llmprivacy et en
extrait un échantillon stratifié pour alimenter l'attaque `ual_inference_ethsri`
(voir scenarios/ual_ethsri_scenario.py). Licence CC BY-NC-SA 4.0 — cf.
data/external/eth_sri_llmprivacy/ATTRIBUTION.md.

Usage :
    python scripts/prepare_eth_sri_ual_dataset.py --n 50 --seed 42

Produit :
    data/external/eth_sri_llmprivacy/synthetic_dataset_full.jsonl  (cache brut, 525 profils)
    data/external/eth_sri_llmprivacy/sample_<n>.jsonl              (échantillon stratifié)
"""
import argparse
import json
import os
import random
import urllib.request
from collections import defaultdict

SOURCE_URL = "https://raw.githubusercontent.com/eth-sri/llmprivacy/main/data/synthetic/synthetic_dataset.jsonl"
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "data", "external", "eth_sri_llmprivacy")
FULL_PATH = os.path.join(DATA_DIR, "synthetic_dataset_full.jsonl")


def download_full_dataset(force: bool = False) -> str:
    os.makedirs(DATA_DIR, exist_ok=True)
    if os.path.exists(FULL_PATH) and not force:
        print(f"[*] Dataset déjà présent : {FULL_PATH}")
        return FULL_PATH
    print(f"[*] Téléchargement depuis {SOURCE_URL} ...")
    urllib.request.urlretrieve(SOURCE_URL, FULL_PATH)
    print(f"[*] Sauvegardé : {FULL_PATH}")
    return FULL_PATH


def load_profiles(path: str) -> list:
    profiles = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            profiles.append(json.loads(line))
    return profiles


def stratified_sample(profiles: list, n: int, seed: int) -> list:
    """Échantillonne n profils en respectant (au prorata) la répartition
    par 'feature' du dataset source, pour couvrir tous les types d'attributs."""
    rng = random.Random(seed)
    by_feature = defaultdict(list)
    for p in profiles:
        by_feature[p.get("feature", "unknown")].append(p)

    total = len(profiles)
    features = sorted(by_feature.keys())

    # Allocation proportionnelle avec arrondi, puis ajustement du reliquat.
    alloc = {feat: max(1, round(n * len(by_feature[feat]) / total)) for feat in features}
    diff = n - sum(alloc.values())
    i = 0
    feats_cycle = features[:]
    rng.shuffle(feats_cycle)
    while diff != 0 and feats_cycle:
        feat = feats_cycle[i % len(feats_cycle)]
        if diff > 0 and alloc[feat] < len(by_feature[feat]):
            alloc[feat] += 1
            diff -= 1
        elif diff < 0 and alloc[feat] > 0:
            alloc[feat] -= 1
            diff += 1
        i += 1
        if i > 10000:
            break

    sample = []
    for feat in features:
        pool = by_feature[feat][:]
        rng.shuffle(pool)
        sample.extend(pool[:alloc[feat]])
    rng.shuffle(sample)
    return sample[:n]


def main():
    parser = argparse.ArgumentParser(description="Prépare un échantillon du dataset eth-sri/llmprivacy pour ual_inference_ethsri")
    parser.add_argument("--n", type=int, default=50, help="Nombre de profils à échantillonner")
    parser.add_argument("--seed", type=int, default=42, help="Graine pour la reproductibilité")
    parser.add_argument("--force-download", action="store_true", help="Force le retéléchargement du dataset complet")
    args = parser.parse_args()

    full_path = download_full_dataset(force=args.force_download)
    profiles = load_profiles(full_path)
    print(f"[*] {len(profiles)} profils chargés depuis le dataset complet.")

    sample = stratified_sample(profiles, args.n, args.seed)

    out_path = os.path.join(DATA_DIR, f"sample_{args.n}.jsonl")
    with open(out_path, "w", encoding="utf-8") as f:
        for idx, p in enumerate(sample):
            record = {
                "id": idx,
                "feature": p.get("feature"),
                "hardness": p.get("hardness"),
                "personality": p.get("personality"),
                "text": p.get("response"),
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    from collections import Counter
    feat_counts = Counter(p["feature"] for p in sample)
    print(f"[*] Échantillon de {len(sample)} profils écrit dans : {out_path}")
    print(f"[*] Répartition par attribut cible : {dict(feat_counts)}")


if __name__ == "__main__":
    main()
