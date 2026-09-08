
import os
from dotenv import load_dotenv

class EquiNexException(Exception):
    """Base exception for EquiNex SDK."""
    pass

class AuthenticationError(EquiNexException):
    """Raised when authentication fails."""
    pass
