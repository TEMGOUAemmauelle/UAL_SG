"""
extend_eth_sri_sample.py
==========================
Ajoute un second lot de profils au dessus de data/external/eth_sri_llmprivacy/sample_50.jsonl,
choisi pour equilibrer la distribution de hardness (1-5) du jeu de test COMBINE
(existant + nouveau lot), sans jamais reselectionner un profil deja present
dans le premier lot (exclusion par correspondance exacte sur le champ 'text').

Usage :
    python scripts/extend_eth_sri_sample.py --n 50 --seed 123

Produit :
    data/external/eth_sri_llmprivacy/sample_50_batch2.jsonl   (nouveau lot, id 50..99)
    data/external/eth_sri_llmprivacy/sample_100.jsonl         (lot 1 + lot 2 concatenes)
"""
import argparse
import json
import os
import random
from collections import Counter, defaultdict

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "data", "external", "eth_sri_llmprivacy")
FULL_PATH = os.path.join(DATA_DIR, "synthetic_dataset_full.jsonl")
EXISTING_SAMPLE_PATH = os.path.join(DATA_DIR, "sample_50.jsonl")


def load_jsonl(path):
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def main():
    parser = argparse.ArgumentParser(description="Genere un 2e lot de profils equilibre en hardness")
    parser.add_argument("--n", type=int, default=50, help="Taille du nouveau lot")
    parser.add_argument("--seed", type=int, default=123, help="Graine de tirage (differente du lot 1)")
    parser.add_argument("--existing-sample", default=EXISTING_SAMPLE_PATH)
    parser.add_argument("--full-corpus", default=FULL_PATH)
    args = parser.parse_args()

    full = load_jsonl(args.full_corpus)
    existing = load_jsonl(args.existing_sample)
    print(f"[*] Corpus complet : {len(full)} profils")
    print(f"[*] Lot existant   : {len(existing)} profils")

    existing_texts = {p["text"] for p in existing}
    pool = [p for p in full if p.get("response") not in existing_texts]
    print(f"[*] Pool disponible apres exclusion du lot existant : {len(pool)} profils")

    existing_hardness = Counter(p["hardness"] for p in existing)
    print(f"[*] Repartition hardness lot existant : {dict(sorted(existing_hardness.items()))}")

    # Cible : equilibrer le total combine (existant + nouveau) a n_total/len(levels)
    # par niveau de hardness, borne par la disponibilite reelle du pool restant.
    levels = [1, 2, 3, 4, 5]
    n_total = len(existing) + args.n
    target_per_level = n_total / len(levels)

    pool_by_hardness = defaultdict(list)
    for p in pool:
        pool_by_hardness[p.get("hardness")].append(p)

    raw_need = {h: max(0, round(target_per_level - existing_hardness.get(h, 0))) for h in levels}
    # Plafonner par la disponibilite du pool restant pour ce niveau.
    need = {h: min(raw_need[h], len(pool_by_hardness.get(h, []))) for h in levels}

    diff = args.n - sum(need.values())
    # Ajuste le reliquat (arrondis / plafonds) en ajoutant/retirant sur les
    # niveaux les moins/les plus deja representes dans le total combine projete.
    rng = random.Random(args.seed)
    levels_cycle = levels[:]
    i = 0
    while diff != 0 and i < 10000:
        h = levels_cycle[i % len(levels_cycle)]
        projected = existing_hardness.get(h, 0) + need[h]
        if diff > 0 and need[h] < len(pool_by_hardness.get(h, [])):
            need[h] += 1
            diff -= 1
        elif diff < 0 and need[h] > 0:
            need[h] -= 1
            diff += 1
        i += 1

    print(f"[*] Profils a tirer par niveau de hardness : {dict(sorted(need.items()))}")

    new_batch = []
    for h in levels:
        bucket = pool_by_hardness.get(h, [])[:]
        rng.shuffle(bucket)
        new_batch.extend(bucket[:need[h]])
    rng.shuffle(new_batch)
    new_batch = new_batch[:args.n]

    start_id = len(existing)
    out_records = []
    for offset, p in enumerate(new_batch):
        out_records.append({
            "id": start_id + offset,
            "feature": p.get("feature"),
            "hardness": p.get("hardness"),
            "personality": p.get("personality"),
            "text": p.get("response"),
        })

    batch2_path = os.path.join(DATA_DIR, "sample_50_batch2.jsonl")
    with open(batch2_path, "w", encoding="utf-8") as f:
        for r in out_records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    combined_path = os.path.join(DATA_DIR, "sample_100.jsonl")
    with open(combined_path, "w", encoding="utf-8") as f:
        for r in existing + out_records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    new_hardness = Counter(r["hardness"] for r in out_records)
    combined_hardness = Counter([p["hardness"] for p in existing] + [r["hardness"] for r in out_records])
    print(f"\n[*] Nouveau lot ({len(out_records)} profils) ecrit dans : {batch2_path}")
    print(f"[*] Repartition hardness nouveau lot : {dict(sorted(new_hardness.items()))}")
    print(f"[*] Fichier combine (100 profils) ecrit dans : {combined_path}")
    print(f"[*] Repartition hardness COMBINEE : {dict(sorted(combined_hardness.items()))}")


if __name__ == "__main__":
    main()
