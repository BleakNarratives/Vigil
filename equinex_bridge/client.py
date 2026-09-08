
import logging
import os
import time
import requests
from typing import Dict, Any, Optional
from dotenv import load_dotenv
from .exceptions import AuthenticationError, EquiNexException

class EquiNexClient:
    """
    Hardened client for interacting with EquiNex services.
    """

    BASE_URL = "https://api.equinex.bridge" # Placeholder URL

    def __init__(self, gemini_api_key: Optional[str] = None, youtube_api_key: Optional[str] = None):
        load_dotenv()
        self.GEMINI_API_KEY = gemini_api_key or os.getenv("GEMINI_API_KEY")
        self.YOUTUBE_API_KEY = youtube_api_key or os.getenv("YOUTUBE_API_KEY")

        if not self.GEMINI_API_KEY:
            raise AuthenticationError("GEMINI_API_KEY is required.")

        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.GEMINI_API_KEY}",
            "Content-Type": "application/json",
            "X-EquiNex-License": "Valid_Commercial_Token"
        })

    def _make_api_call(self, endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Authenticated API request handler with error handling."""
        url = f"{self.BASE_URL}{endpoint}"
        try:
            response = self.session.post(url, json=payload, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logging.error(f"API call failed: {e}")
            raise EquiNexException(f"Network error: {e}")

    def steer_lyria(self, prompt: str, energy_level: float) -> Dict[str, Any]:
        """Steer the Lyria real-time model."""
        endpoint = "/lyria/v1/steer"
        payload = {
            "prompt": prompt,
            "energy_level": energy_level,
            "timestamp": time.time()
        }
        return self._make_api_call(endpoint, payload)
