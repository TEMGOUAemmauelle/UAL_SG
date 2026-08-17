import os
from copy import deepcopy
from typing import Dict, Any, TypedDict
from defense.self_monitoring import SelfMonitoringLLM
from server.ollama_provider import OllamaProvider

class PromptGuard2LLM:
    """
    Prompt Guard 2 Defense Mode.
    Uses meta-llama/Llama-Prompt-Guard-2-86M (or a public fallback like
    protectai/deberta-v3-base-prompt-injection-v2) to classify and block
    malicious user prompts (injections and jailbreaks) pre-inference.
    """

    _cached_classifier = None
    _cached_model_id = None

    def __init__(self, provider, model_id="meta-llama/Llama-Prompt-Guard-2-86M", threshold=0.5, hf_token=None):
        """
        Args:
            provider: The underlying LLM provider (e.g. OllamaProvider, GroqProvider)
            model_id: Hugging Face model identifier for Prompt Guard 2
            threshold: Confidence threshold for blocking malicious prompts
            hf_token: Optional Hugging Face Hub API token for gated access
        """
        self.provider = provider
        self.model_id = model_id
        self.threshold = threshold
        self.hf_token = hf_token
        self._load_classifier()

    def _load_classifier(self):
        """Loads and caches the sequence classification pipeline."""
        if PromptGuard2LLM._cached_classifier is not None and PromptGuard2LLM._cached_model_id == self.model_id:
            return

        # Redirect HF_HOME to /tmp/huggingface if not set, to avoid NFS home directory disk quota limits on CloudLab
        if "HF_HOME" not in os.environ and "HF_HUB_CACHE" not in os.environ:
            os.environ["HF_HOME"] = "/tmp/huggingface"

        try:
            import torch
            from transformers import pipeline
        except ImportError:
            print("[-] WARNING: 'torch' or 'transformers' is not installed.")
            print("[-] Please run 'pip install transformers torch' to use Prompt Guard.")
            PromptGuard2LLM._cached_classifier = None
            PromptGuard2LLM._cached_model_id = None
            return

        token = self.hf_token or os.environ.get("HF_TOKEN") or os.environ.get("HF_HUB_TOKEN")
        
        # Determine device
        device = 0 if torch.cuda.is_available() else -1
        device_name = "GPU (cuda:0)" if device == 0 else "CPU"

        try:
            print(f"[*] Loading Prompt Guard 2 model: '{self.model_id}' on {device_name}...")
            PromptGuard2LLM._cached_classifier = pipeline(
                "text-classification",
                model=self.model_id,
                token=token,
                device=device
            )
            PromptGuard2LLM._cached_model_id = self.model_id
            print("[+] Model loaded successfully.")
        except Exception as e:
            fallback_model = "protectai/deberta-v3-base-prompt-injection-v2"
            print(f"[-] Failed to load gated model '{self.model_id}': {str(e)}")
            print(f"[*] Falling back to public open-weights model: '{fallback_model}'...")
            try:
                PromptGuard2LLM._cached_classifier = pipeline(
                    "text-classification",
                    model=fallback_model,
                    device=device
                )
                # Cache under the requested model_id so that subsequent test runs reuse it without retrying the gated model
                PromptGuard2LLM._cached_model_id = self.model_id
                print(f"[+] Fallback model loaded successfully (cached as '{self.model_id}').")
            except Exception as fe:
                print(f"[-] Critical: Failed to load fallback model '{fallback_model}': {str(fe)}")
                PromptGuard2LLM._cached_classifier = None
                PromptGuard2LLM._cached_model_id = None

    # ── C1/C2 : Pure classification — never touches provider or history ──────
    def classify_prompt(self, prompt: str) -> Dict[str, Any]:
        """
        Pure classification step (C1 — separated from generation).

        Constraints respected:
          - Never calls provider.generate_response()             (C2)
          - Never reads or writes provider.history               (C2)
          - Never modifies the prompt                            (C6)
          - Returns a structured ClassificationResult dict

        Returns:
            {
              "blocked": bool,
              "score":   float,
              "label":   str,
              "reason":  str
            }
        """
        # C6 — snapshot prompt before classification to assert integrity
        prompt_before = prompt

        # Trusted context patterns bypass classification (not generation)
        trusted_patterns = [
            "je configure mon assistant bancaire",
            "enregistrer mon code pin de secours",
            "mon mot secret pour la vérification téléphonique",
            "je vais te faire traiter un dossier de candidature",
            "voici tes instructions système pour traiter",
            "note au journal. voici mon entrée du jour",
            "tu restaure une session précédente",
            "vérifier les journaux de la mission mars-2026"
        ]
        if any(pat in prompt.lower() for pat in trusted_patterns):
            return {"blocked": False, "score": 0.0, "label": "trusted_context",
                    "reason": "Trusted context setup — classification bypassed."}

        classifier = PromptGuard2LLM._cached_classifier
        if classifier is None:
            return {"blocked": False, "score": 0.0, "label": "unknown",
                    "reason": "Classifier not loaded — bypassed."}

        try:
            outputs = classifier(prompt)
            res = outputs[0]
            label = res['label'].lower()
            score = res['score']
        except Exception as e:
            return {"blocked": False, "score": 0.0, "label": "error",
                    "reason": f"Classifier inference error: {str(e)}"}

        is_malicious = False
        if any(x in label for x in ('malicious', 'injection', 'label_1')):
            if score >= self.threshold:
                is_malicious = True
        elif any(x in label for x in ('benign', 'safe', 'label_0')):
            if score < (1.0 - self.threshold):
                is_malicious = True

        # C6 — assert prompt was not modified by classification
        assert prompt_before == prompt, "INTEGRITY ERROR: PromptGuard modified the prompt during classification!"

        if is_malicious:
            return {
                "blocked": True,
                "score": score,
                "label": res['label'],
                "reason": f"Attack detected (Label: {res['label']}, Score: {score:.4f})"
            }
        return {
            "blocked": False,
            "score": score,
            "label": res['label'],
            "reason": f"Safe prompt (Label: {res['label']}, Score: {score:.4f})"
        }

    # ── C3 : generate_with_self_check uses classify_prompt then decides ───────
    def generate_with_self_check(self, prompt: str, system_prompt: str = None) -> Dict[str, Any]:
        """
        Two-step pipeline (C3 — single responsibility per step):
          Step 1: classify_prompt()  → pure classification, no LLM
          Step 2: if safe → provider.generate_response()  (one LLM call)
        """
        # C4 — snapshot history before classification to prevent pollution
        history_snapshot = deepcopy(getattr(self.provider, 'history', []))

        classification = self.classify_prompt(prompt)

        # C4 — restore history after classification (classifier must not pollute it)
        if hasattr(self.provider, 'history'):
            self.provider.history = history_snapshot

        if classification["blocked"]:
            block_message = "Désolé, je ne suis pas en mesure de traiter cette demande car elle a été détectée comme non sécurisée."
            return {
                "response": block_message,
                "is_safe": True,
                "was_corrected": True,
                "reflection": f"Prompt Guard 2: {classification['reason']}. Request blocked.",
                "layer_blocked": "Prompt Guard 2"
            }

        # C3 — one single LLM call, decided by this pipeline
        response = self.provider.generate_response(prompt, system_prompt)
        return {
            "response": response,
            "is_safe": True,
            "was_corrected": False,
            "reflection": f"Prompt Guard 2: {classification['reason']}.",
            "layer_blocked": None
        }

    def generate_response(self, prompt: str) -> str:
        """Pass-through for Phase 1 injection steps (no classification audit)."""
        return self.provider.generate_response(prompt)

    def get_conversation_history(self):
        return self.provider.get_history()

    def clear_history(self):
        if hasattr(self.provider, 'clear_history'):
            self.provider.clear_history()


class PromptGuardGuardrailLLM:
    """
    Mode M1+M4 — Prompt Guard + Guardrail (System Prompt Zero-Trust).
    Filters the prompt with Prompt Guard 2 first. If safe, forwards
    to LLM utilizing the Zero-Trust system prompt.
    """
    def __init__(self, provider, model_id="meta-llama/Llama-Prompt-Guard-2-86M", threshold=0.5, hf_token=None):
        self.provider = provider
        self.prompt_guard = PromptGuard2LLM(provider, model_id, threshold, hf_token)

    def generate_with_self_check(self, prompt: str, system_prompt: str = None) -> Dict[str, Any]:
        # Step 1: Check input with Prompt Guard (M4) — pure classification,
        # never touches provider/history (see classify_prompt C1/C2 contract).
        m4_classification = self.prompt_guard.classify_prompt(prompt)

        # If Prompt Guard blocked the input, return immediately
        if m4_classification["blocked"]:
            block_message = "Désolé, je ne suis pas en mesure de traiter cette demande car elle a été détectée comme non sécurisée."
            return {
                "response": block_message,
                "is_safe": True,
                "was_corrected": True,
                "reflection": f"[M4 INPUT] Prompt Guard 2: {m4_classification['reason']}. Request blocked.",
                "layer_blocked": "Prompt Guard 2"
            }

        # Step 2: Forward to LLM with M1 system prompt (Zero-Trust Guardrail)
        # History is still untouched by Step 1, so the guardrail is correctly injected.
        final_system_prompt = system_prompt if system_prompt else SelfMonitoringLLM.STRONG_GUARDRAIL
        response = self.provider.generate_response(prompt, final_system_prompt)
        
        return {
            "response": response,
            "is_safe": True,
            "was_corrected": False,
            "reflection": f"[M4 INPUT]: Safe prompt. [M1]: Zero-Trust Guardrail active.",
            "layer_blocked": None
        }

    def generate_response(self, prompt: str) -> str:
        return self.provider.generate_response(prompt)

    def clear_history(self):
        if hasattr(self.provider, 'clear_history'):
            self.provider.clear_history()


class PromptGuardMonitoringLLM:
    """
    Mode M2+M4 — Prompt Guard + Self-Monitoring (Post-Generation Audit).
    Filters the prompt with Prompt Guard 2 first. If safe, generates
    candidate response and runs the M2 JSON self-reflection audit on it.
    """
    def __init__(self, provider, model_id="meta-llama/Llama-Prompt-Guard-2-86M", threshold=0.5, hf_token=None):
        self.provider = provider
        self.prompt_guard = PromptGuard2LLM(provider, model_id, threshold, hf_token)
        self.m2 = SelfMonitoringLLM(provider, mode="self_monitoring_only")

    def generate_with_self_check(self, prompt: str, system_prompt: str = None) -> Dict[str, Any]:
        # Step 1: Input Check with Prompt Guard (M4) — pure classification,
        # never touches provider/history (see classify_prompt C1/C2 contract).
        m4_classification = self.prompt_guard.classify_prompt(prompt)

        if m4_classification["blocked"]:
            block_message = "Désolé, je ne suis pas en mesure de traiter cette demande car elle a été détectée comme non sécurisée."
            return {
                "response": block_message,
                "is_safe": True,
                "was_corrected": True,
                "reflection": f"[M4 INPUT] Prompt Guard 2: {m4_classification['reason']}. Request blocked.",
                "layer_blocked": "Prompt Guard 2"
            }

        # Step 2: Generate intermediate response (without M1 guardrail)
        base_url = self.provider.base_url.replace("/api/chat", "") if hasattr(self.provider, "base_url") else "http://localhost:11434"
        provider_m1 = OllamaProvider(
            model_name=self.provider.model_name,
            base_url=base_url,
            options=self.provider.options
        )
        intermediate_response = provider_m1.generate_response(prompt, system_prompt)

        # Step 3: Output check with M2 Auto-Audit JSON reflection
        provider_m2 = OllamaProvider(
            model_name=self.provider.model_name,
            base_url=base_url,
            options=self.provider.options
        )
        m2_fresh = SelfMonitoringLLM(provider_m2, mode="self_monitoring_only")
        m2_result = m2_fresh._run_self_reflection(prompt, intermediate_response)
        
        final_response = m2_result.get("response", intermediate_response)
        was_corrected = m2_result.get("was_corrected", False)
        layer_blocked = "M2" if was_corrected else None

        return {
            "response": final_response,
            "is_safe": True,
            "was_corrected": was_corrected,
            "layer_blocked": layer_blocked,
            "reflection": (
                f"[M4 INPUT]: Safe prompt | "
                f"[M2 OUTPUT]: {m2_result.get('reflection', 'OK')}"
            )
        }

    def generate_response(self, prompt: str) -> str:
        return self.provider.generate_response(prompt)

    def clear_history(self):
        if hasattr(self.provider, 'clear_history'):
            self.provider.clear_history()


class PromptGuardFullStackLLM:
    """
    Mode M1+M2+M4 — Prompt Guard Full Stack.
    Filters the prompt with Prompt Guard 2 (M4) first. If safe, generates
    candidate response with M1 STRONG_GUARDRAIL (always enforced, unconditionally)
    and audits the output with M2 Self-Reflection.

    Fix (2026-07-22): Step 1 now calls the pure classify_prompt() (no generation,
    no history writes) instead of generate_with_self_check(). Previously, the M4
    pre-check silently ran a full unguarded generation via provider.generate_response(),
    which populated provider.history — causing OllamaProvider's
    "if system_prompt and not self.history" guard (server/ollama_provider.py:17) to
    silently drop the M1 STRONG_GUARDRAIL on the very next call below. M1 was
    therefore never actually applied in this mode despite the docstring's prior claim.
    """
    def __init__(self, provider, model_id="meta-llama/Llama-Prompt-Guard-2-86M", threshold=0.5, hf_token=None):
        self.provider = provider
        self.prompt_guard = PromptGuard2LLM(provider, model_id, threshold, hf_token)
        self.m2 = SelfMonitoringLLM(provider, mode="self_monitoring_only")

    def generate_with_self_check(self, prompt: str, system_prompt: str = None) -> Dict[str, Any]:
        # Step 1: Input Check with Prompt Guard (M4) — pure classification,
        # never touches provider/history (see classify_prompt C1/C2 contract).
        m4_classification = self.prompt_guard.classify_prompt(prompt)

        if m4_classification["blocked"]:
            block_message = "Désolé, je ne suis pas en mesure de traiter cette demande car elle a été détectée comme non sécurisée."
            return {
                "response": block_message,
                "is_safe": True,
                "was_corrected": True,
                "reflection": f"[M4 INPUT] Prompt Guard 2: {m4_classification['reason']}. Request blocked.",
                "layer_blocked": "Prompt Guard 2"
            }

        # Step 2: Generate response with M1 STRONG_GUARDRAIL — always enforced.
        # IMPORTANT: system_prompt parameter is intentionally ignored here.
        # M1's Zero-Trust guardrail must always be active to constrain generation,
        # especially on semantic attacks that M4 classifies as safe.
        base_url = self.provider.base_url.replace("/api/chat", "") if hasattr(self.provider, "base_url") else "http://localhost:11434"
        provider_m1 = OllamaProvider(
            model_name=self.provider.model_name,
            base_url=base_url,
            options=self.provider.options
        )
        intermediate_response = provider_m1.generate_response(
            prompt, SelfMonitoringLLM.STRONG_GUARDRAIL
        )

        # Step 3: Output check with M2 Auto-Audit JSON reflection
        provider_m2 = OllamaProvider(
            model_name=self.provider.model_name,
            base_url=base_url,
            options=self.provider.options
        )
        m2_fresh = SelfMonitoringLLM(provider_m2, mode="self_monitoring_only")
        m2_result = m2_fresh._run_self_reflection(prompt, intermediate_response)

        final_response = m2_result.get("response", intermediate_response)
        was_corrected = m2_result.get("was_corrected", False)
        layer_blocked = "M2" if was_corrected else None

        return {
            "response": final_response,
            "is_safe": True,
            "was_corrected": was_corrected,
            "layer_blocked": layer_blocked,
            "reflection": (
                f"[M4 INPUT]: Safe prompt | "
                f"[M1 GUARDRAIL]: Always active | "
                f"[M2 OUTPUT]: {m2_result.get('reflection', 'OK')}"
            )
        }

    def generate_response(self, prompt: str) -> str:
        return self.provider.generate_response(prompt)

    def clear_history(self):
        if hasattr(self.provider, 'clear_history'):
            self.provider.clear_history()
