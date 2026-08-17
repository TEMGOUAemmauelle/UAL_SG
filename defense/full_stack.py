"""
Mode M1+M2+M3 — FullStack Defense (All Layers Combined)
========================================================
Orchestre les 3 couches de défense en cascade :

  1. M3 Pre-Strike    → Analyse comportementale AVANT génération (filtrage intention)
  2. M1 Guardrail     → System Prompt Zero-Trust injecté pendant la génération
  3. M2 Auto-Audit    → Auto-surveillance JSON de la réponse APRÈS génération

Si M3 bloque → aucune inférence GPU (économie maximale).
Si M3 laisse passer → M1 guide le modèle.
Si M1+M3 laissent passer → M2 audite la sortie finale.
"""

from typing import Dict, Any
from defense.self_sanitize import SelfSanitizeLLM, HierarchicalClassifier
from defense.self_monitoring import SelfMonitoringLLM


class FullStackLLM:
    """
    Mode M1+M2+M3 — Défense Full-Stack.
    Combine les trois couches indépendantes de SENTINEL en pipeline séquentiel.
    """

    def __init__(self, provider):
        self.provider = provider
        # M3 avec Guardrail M1 injecté comme system prompt
        self.m3_m1 = SelfSanitizeLLM(
            provider,
            guardrail_prompt=SelfMonitoringLLM.STRONG_GUARDRAIL
        )
        # M2 : Auto-Surveillance JSON sur la sortie
        self.m2 = SelfMonitoringLLM(provider, mode="self_monitoring_only")
        self.classifier = HierarchicalClassifier()

    def generate_with_self_check(self, prompt: str, system_prompt: str = None) -> Dict[str, Any]:
        """
        Pipeline Full-Stack M1+M2+M3 :
          1. M3 Pre-Strike : Vérifie l'intention de la requête AVANT génération.
          2. M1+M3 Génération : Génère avec Guardrail + Streaming sanitizer.
          3. M2 Post-Audit : Audit JSON sur la réponse finale.
        """

        # ── COUCHE 1 : M3 Pre-Strike + M1 Guardrail (génération sécurisée) ────
        m3_result = self.m3_m1.generate_with_self_check(prompt, system_prompt)

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
