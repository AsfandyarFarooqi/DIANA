"""Runtime settings.

Every secret and option comes from environment variables, loaded from the `.env`
file at the project root (see `.env.example`). Nothing sensitive lives in code.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")


def _env(name, default=""):
    return os.getenv(name, "").strip() or default


# --- API keys (secrets) ---
GROQ_API_KEY = _env("GROQ_API_KEY")
SERPER_API_KEY = _env("SERPER_API_KEY")

# --- Language + speech models ---
GROQ_MODEL = _env("GROQ_MODEL", "openai/gpt-oss-120b")
GROQ_REASONING_EFFORT = _env("GROQ_REASONING_EFFORT", "low")
GROQ_STT_MODEL = _env("GROQ_STT_MODEL", "whisper-large-v3-turbo")

# --- Voice output ---
TTS_VOICE = _env("TTS_VOICE", "en-GB-RyanNeural")
TTS_VOICE_UR = _env("TTS_VOICE_UR", "ur-PK-AsadNeural")
TTS_RATE = _env("TTS_RATE", "+4%")
TTS_PITCH = _env("TTS_PITCH", "-6Hz")

# --- Server ---
HOST = _env("HOST", "127.0.0.1")
PORT = int(_env("PORT", "5000"))
DEBUG = _env("FLASK_DEBUG", "0") == "1"
MAX_UPLOAD_MB = 25
