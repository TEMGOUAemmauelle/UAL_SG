import requests
import json
from .base_provider import BaseLLMProvider
from typing import Dict, Any, Generator

class OllamaProvider(BaseLLMProvider):
    """
    Fournisseur pour les modèles Ollama locaux.
    """
    
    def __init__(self, model_name: str, base_url: str = "http://localhost:11434", options: Dict[str, Any] = None):
        super().__init__(model_name, options)
        self.base_url = f"{base_url}/api/chat"

    def generate_response(self, prompt: str, system_prompt: str = None) -> str:
        # Ajouter le prompt système s'il s'agit du premier message
        if system_prompt and not self.history:
            self.add_message("system", system_prompt)
        
        self.add_message("user", prompt)
        
        payload = {
            "model": self.model_name,
            "messages": self.history,
            "stream": False,
            "options": self.options
        }
        
        try:
            response = requests.post(self.base_url, json=payload)
            response.raise_for_status()
            data = response.json()
            
            message = data.get("message", {})
            content = message.get("content", "")
            
            self.add_message("assistant", content)
            return content
            
        except requests.exceptions.RequestException as e:
            return f"Erreur de connexion à Ollama : {str(e)}"

    def unload(self):
        """
        Décharge immédiatement ce modèle de la VRAM Ollama (keep_alive=0).
        Utile pour isoler la mesure d'un autre modèle (ex: le juge M5) de la
        contention VRAM causée par ce modèle resté chargé.
        """
        try:
            requests.post(
                self.base_url,
                json={"model": self.model_name, "messages": [], "stream": False, "keep_alive": 0},
                timeout=30,
            )
        except requests.exceptions.RequestException:
            pass

    def generate_stream(self, prompt: str, system_prompt: str = None) -> Generator[str, None, None]:
        """
        Composant 1 (Self-Sanitize) — Representation Hook.
        Retourne un générateur de tokens (strings) via le mode stream:True d'Ollama.
        Permet à SelfSanitizeLLM d'intercepter chaque token avant diffusion.
        """
        if system_prompt and not self.history:
            self.add_message("system", system_prompt)

        self.add_message("user", prompt)

        payload = {
            "model": self.model_name,
            "messages": self.history,
            "stream": True,
            "options": self.options
        }

        try:
            response = requests.post(self.base_url, json=payload, stream=True)
            response.raise_for_status()

            full_response = []
            for line in response.iter_lines():
                if not line:
                    continue
                try:
                    chunk = json.loads(line.decode("utf-8"))
                    token = chunk.get("message", {}).get("content", "")
                    if token:
                        full_response.append(token)
                        yield token
                    # Arrêt quand Ollama signale la fin de génération
                    if chunk.get("done", False):
                        break
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue

            # Enregistrer la réponse complète dans l'historique
            self.add_message("assistant", "".join(full_response))

        except requests.exceptions.RequestException as e:
            yield f"Erreur de connexion à Ollama (stream) : {str(e)}"

