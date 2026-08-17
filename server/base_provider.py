from abc import ABC, abstractmethod
from typing import List, Dict, Any

class BaseLLMProvider(ABC):
    """
    Classe de base abstraite pour tous les fournisseurs de LLM.
    Garantit une interface cohérente pour les conversations multi-tours.
    """
    
    def __init__(self, model_name: str, options: Dict[str, Any] = None):
        self.model_name = model_name
        self.options = options or {}
        self.history: List[Dict[str, str]] = []

    @abstractmethod
    def generate_response(self, prompt: str, system_prompt: str = None) -> str:
        """
        Envoie un prompt au LLM et retourne la réponse textuelle.
        Doit gérer l'historique en interne si le fournisseur le supporte.
        """
        pass

    def add_message(self, role: str, content: str):
        """Ajoute un message à l'historique de la conversation."""
        self.history.append({"role": role, "content": content})

    def clear_history(self):
        """Réinitialise l'historique de la conversation."""
        self.history = []

    def get_history(self) -> List[Dict[str, str]]:
        """Retourne l'historique actuel de la conversation."""
        return self.history
