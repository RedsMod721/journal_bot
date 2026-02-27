"""
Configuration settings for the Status Window application
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Project paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
VOICE_UPLOADS_DIR = DATA_DIR / "voice_uploads"
BACKUPS_DIR = DATA_DIR / "backups"

# Ensure directories exist
DATA_DIR.mkdir(exist_ok=True)
VOICE_UPLOADS_DIR.mkdir(exist_ok=True)
BACKUPS_DIR.mkdir(exist_ok=True)

# Database settings
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR}/database.db")

# API settings
API_VERSION = "0.1.0"
API_TITLE = "Status Window API"
API_DESCRIPTION = "Gamified life-tracking system for neurodivergent users"

# CORS settings
ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:8000",
    "http://localhost:8000",
]

# Ollama settings
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")

# Whisper settings (for voice input)
WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE", "base")  # tiny, base, small, medium, large

# Application settings
DEBUG = os.getenv("DEBUG", "true").lower() == "true"
