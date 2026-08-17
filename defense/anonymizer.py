"""
Mode Anonymizer — Défense de comparaison (baseline eth-sri/llmprivacy)
========================================================================
Reproduit la seule contre-mesure testée dans le papier de référence
(Staab et al., ICLR 2024, "Beyond Memorization") et son code associé
(https://github.com/eth-sri/llmprivacy, src/utils/anonymization.py) :
masquage des entités nommées (NER) dans le texte AVANT qu'il n'atteigne
le modèle cible, via Microsoft Presidio.

Différence structurelle avec M3 / Prompt Guard 2 / M5 :
  Ces trois défenses classifient la CONSIGNE d'attaque (le prompt envoyé
  en phase 2, ex. "dresse le profil de l'auteur") et bloquent ou laissent
  passer la requête.
  L'Anonymizer, lui, ne bloque jamais rien : il transforme le CONTENU
  analysé (le texte injecté en phase 1, ex. l'entrée de journal contenant
  les indices personnels) avant que ce contenu n'entre dans le contexte
  du modèle. Son effet ne se mesure donc pas sur le taux de blocage, mais
  sur le taux de fuite résiduel (verify_leak) après anonymisation —
  exactement la métrique utilisée dans le Tableau 3 du papier de référence.

Deux modes, calqués sur les deux configurations testées par eth-sri :
  "tagged" (configs/reddit/running/reddit_gpt4_anonymized.yaml)
      → chaque entité détectée est remplacée par une balise typée,
        ex. "<LOCATION>", "<PERSON>", "<DATE_TIME>".
  "hard"   (configs/reddit/running/reddit_gpt4_anonymized_hard.yaml)
      → toute entité détectée est remplacée par un masque générique "***",
        sans indice de type (condition plus stricte).

Limite connue (documentée par les auteurs eux-mêmes) : ce type d'anonymiseur
NER ne couvre que les mentions EXPLICITES d'une entité. Les attributs déduits
du style, du contexte ou de connaissances implicites (ex. "je finis mes cours
dans 2 ans" → niveau d'études) ne sont pas détectés et donc jamais masqués.
Prérequis :
    pip install presidio-analyzer presidio-anonymizer
    python -m spacy download en_core_web_lg
"""

from typing import Any, Dict, List, Optional


# ──────────────────────────────────────────────────────────────────────────────
#  Entités par défaut — identiques à src/utils/anonymization.py (eth-sri/llmprivacy)
#  DATE_TIME est ajouté car plusieurs attributs UAL (âge, ancienneté) transitent
#  souvent par des dates relatives ("il y a 5 ans", "en 2019").
# ──────────────────────────────────────────────────────────────────────────────
DEFAULT_ENTITIES = ["PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER", "LOCATION", "NRP", "DATE_TIME"]


def anonymize_presidio(text: str, entities: Optional[List[str]] = None, mode: str = "tagged") -> str:
    """
    Anonymise `text` via Presidio. Fonction bas niveau, sans état ni cache —
    utilisée directement pour des tests ponctuels. `AnonymizerLLM` (plus bas)
    est la classe à utiliser dans le pipeline de benchmark (cache les moteurs).
    """
    from presidio_analyzer import AnalyzerEngine
    from presidio_anonymizer import AnonymizerEngine
    from presidio_anonymizer.entities import OperatorConfig

    analyzer = AnalyzerEngine()
    anonymizer = AnonymizerEngine()
    results = analyzer.analyze(text=text, entities=entities or DEFAULT_ENTITIES, language="en")

    operators = None
    if mode == "hard":
        operators = {"DEFAULT": OperatorConfig("replace", {"new_value": "***"})}

    anon_result = anonymizer.anonymize(text=text, analyzer_results=results, operators=operators)
    return anon_result.text


# ──────────────────────────────────────────────────────────────────────────────
#  CLASSE PRINCIPALE — AnonymizerLLM
#  Interface compatible avec le reste du pipeline de défense
#  (generate_with_self_check / generate_response / clear_history).
# ──────────────────────────────────────────────────────────────────────────────

class AnonymizerLLM:
    """
    Défense par anonymisation NER pré-inférence (baseline de comparaison).

    Args:
        provider  : Le provider LLM sous-jacent (ex. OllamaProvider).
        entities  : Liste des types d'entités Presidio à masquer
                    (défaut : DEFAULT_ENTITIES, identique à eth-sri/llmprivacy).
        mode      : "tagged" (balises <ENTITY_TYPE>) ou "hard" (masque "***").

    Ne bloque jamais une requête (is_safe=True, layer_blocked=None) : son
    effet se mesure via le taux de fuite résiduel (scenario.verify_leak())
    après transmission du texte anonymisé, pas via un taux de blocage.
    """

    _cached_analyzer = None
    _cached_anonymizer_engine = None
    _presidio_available: Optional[bool] = None

    def __init__(self, provider, entities: Optional[List[str]] = None, mode: str = "tagged"):
        self.provider = provider
        self.entities = entities or DEFAULT_ENTITIES
        self.mode = mode
        self._load_engines()

    def _load_engines(self):
        """Charge et met en cache les moteurs Presidio (une seule fois par process)."""
        if AnonymizerLLM._presidio_available is not None:
            return
        try:
            from presidio_analyzer import AnalyzerEngine
            from presidio_anonymizer import AnonymizerEngine

            print("[Anonymizer] Chargement des moteurs Presidio (NER)...")
            AnonymizerLLM._cached_analyzer = AnalyzerEngine()
            AnonymizerLLM._cached_anonymizer_engine = AnonymizerEngine()
            AnonymizerLLM._presidio_available = True
            print("[Anonymizer] Moteurs Presidio chargés.")
        except Exception as e:
            print(
                f"[Anonymizer] WARNING: Presidio indisponible ({e}). "
                f"Installez : pip install presidio-analyzer presidio-anonymizer "
                f"&& python -m spacy download en_core_web_lg. "
                f"Fail-open : le texte ne sera PAS anonymisé."
            )
            AnonymizerLLM._presidio_available = False

    def anonymize_text(self, text: str) -> str:
        """Anonymise `text` si Presidio est disponible ; sinon le renvoie inchangé (fail-open)."""
        if not AnonymizerLLM._presidio_available:
            return text

        from presidio_anonymizer.entities import OperatorConfig

        try:
            results = AnonymizerLLM._cached_analyzer.analyze(
                text=text, entities=self.entities, language="en"
            )
            operators = None
            if self.mode == "hard":
                operators = {"DEFAULT": OperatorConfig("replace", {"new_value": "***"})}
            anon_result = AnonymizerLLM._cached_anonymizer_engine.anonymize(
                text=text, analyzer_results=results, operators=operators
            )
            return anon_result.text
        except Exception as e:
            print(f"[Anonymizer] Erreur d'anonymisation ({e}). Texte transmis inchangé.")
            return text

    # ── Pipeline principal : anonymise puis transmet, ne bloque jamais ────────
    def generate_with_self_check(self, prompt: str, system_prompt: str = None) -> Dict[str, Any]:
        anonymized_prompt = self.anonymize_text(prompt)
        was_modified = anonymized_prompt != prompt

        response = self.provider.generate_response(anonymized_prompt, system_prompt)

        mode_label = "hard" if self.mode == "hard" else "tagged"
        return {
            "response": response,
            "is_safe": True,
            "was_corrected": was_modified,
            "reflection": (
                f"[ANONYMIZER ({mode_label})] "
                + (
                    f"Entités PII détectées et masquées ({', '.join(self.entities)}) "
                    f"avant transmission au modèle."
                    if was_modified
                    else "Aucune entité PII détectée par Presidio dans ce message — texte transmis inchangé."
                )
            ),
            "layer_blocked": None,
        }

    def generate_response(self, prompt: str) -> str:
        """Passe-plat pour les étapes d'injection de scénario (Phase 1), anonymisé."""
        return self.provider.generate_response(self.anonymize_text(prompt))

    def get_conversation_history(self):
        return self.provider.get_history() if hasattr(self.provider, "get_history") else []

    def clear_history(self):
        if hasattr(self.provider, "clear_history"):
            self.provider.clear_history()
