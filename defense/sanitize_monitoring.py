"""
Mode M2+M3 — Sanitize & Monitoring Defense (Without M1 Guardrail)
================================================================
Orchestre les 2 couches de défense post/pre-génération :

  1. M3 Pre-Strike    → Analyse comportementale AVANT génération (filtrage intention)
  2. M3 Sanitization  → Streaming check + repair
  3. M2 Auto-Audit    → Auto-surveillance JSON de la réponse APRÈS génération
"""

from typing import Dict, Any
from defense.self_sanitize import SelfSanitizeLLM, HierarchicalClassifier
from defense.self_monitoring import SelfMonitoringLLM


class SanitizeMonitoringLLM:
    """
    Mode M2+M3 — Défense Sanitize + Monitoring (sans M1).
    Combine M3 (Pre-Strike + Sanitization) et M2 (Auto-Audit JSON) en cascade.
    """

    def __init__(self, provider):
        self.provider = provider
        # M3 sans Guardrail M1
        self.m3 = SelfSanitizeLLM(
            provider,
            guardrail_prompt=None
        )
        # M2 : Auto-Surveillance JSON sur la sortie
        self.m2 = SelfMonitoringLLM(provider, mode="self_monitoring_only")
        self.classifier = HierarchicalClassifier()

    def generate_with_self_check(self, prompt: str, system_prompt: str = None) -> Dict[str, Any]:
        """
        Pipeline M2+M3 :
          1. M3 Pre-Strike : Vérifie l'intention de la requête AVANT génération.
          2. M3 Génération : Génère avec Streaming sanitizer (sans guardrail).
          3. M2 Post-Audit : Audit JSON sur la réponse finale.
        """

        # ── COUCHE 1 : M3 Pre-Strike + M3 Sanitizer ────
        m3_result = self.m3.generate_with_self_check(prompt, system_prompt)

        # Si M3 a déjà bloqué (Pre-Strike), on ne va pas plus loin
        leak_type = m3_result.get("leak_type")
        if m3_result.get("was_corrected") and leak_type and "INTENT:" in leak_type:
            return {
                "response": m3_result["response"],
                "is_safe": True,
                "was_corrected": True,
                "reflection": f"[M3 PRE-STRIKE] {m3_result.get('reflection', '')}",
                "layer_blocked": "M3"
            }

        intermediate_response = m3_result.get("response", "")

        # ── COUCHE 2 : M2 Auto-Audit JSON sur la réponse intermédiaire ────────
        m2_result = self.m2._run_self_reflection(prompt, intermediate_response)

        final_response = m2_result.get("response", intermediate_response)
        was_corrected = m3_result.get("was_corrected", False) or m2_result.get("was_corrected", False)
        layer_blocked = None
        if m3_result.get("was_corrected"):
            layer_blocked = "M3"
        elif m2_result.get("was_corrected"):
            layer_blocked = "M2"

        return {
            "response": final_response,
            "is_safe": True,
            "was_corrected": was_corrected,
            "layer_blocked": layer_blocked,
            "reflection": (
                f"[M3]: {m3_result.get('reflection', 'OK')} | "
                f"[M2]: {m2_result.get('reflection', 'OK')}"
            )
        }

    def generate_response(self, prompt: str) -> str:
        """Passe-plat pour les étapes d'injection de scénario (non auditées)."""
        return self.provider.generate_response(prompt)

    def clear_history(self):
        if hasattr(self.provider, "clear_history"):
            self.provider.clear_history()
