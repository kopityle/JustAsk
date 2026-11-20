import os
import re
import secrets
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = PROJECT_ROOT / ".env"
ENV_EXAMPLE = PROJECT_ROOT / ".env.example"

FALLBACK_ENV_TEMPLATE = """# Создано автоматически: при необходимости заполните ключи Moodle.
JWT_SECRET={jwt_secret}
LTI_CONSUMER_KEY=replace_with_moodle_consumer_key
LTI_SHARED_SECRET=replace_with_random_string

OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2:3b
EMBED_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
DISTANCE_THRESHOLD=0.50

ALLOW_GUEST_WRITES=false
MAX_UPLOAD_SIZE=52428800
MAX_CONCURRENT_REQUESTS=2
"""


def _ensure_env_file():
    """Создаёт .env на чистом клоне, чтобы обязательные переменные всегда были заданы."""
    if ENV_FILE.exists():
        return

    template = (
        ENV_EXAMPLE.read_text(encoding="utf-8")
        if ENV_EXAMPLE.exists()
        else FALLBACK_ENV_TEMPLATE
    )
    generated_secret = secrets.token_urlsafe(32)
    jwt_line = re.compile(r"^(\s*JWT_SECRET\s*=\s*).*$", re.MULTILINE)

    if jwt_line.search(template):
        content = jwt_line.sub(
            lambda match: f"{match.group(1)}{generated_secret}", template, count=1
        )
    else:
        content = template.rstrip() + f"\nJWT_SECRET={generated_secret}\n"

    ENV_FILE.write_text(content, encoding="utf-8")
    print(
        "[CONFIG] Файл .env не найден. Автоматически создан новый .env "
        "со сгенерированным JWT_SECRET."
    )


_ensure_env_file()

# Load environment variables from .env file
load_dotenv()


def required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(
            f"Не задана обязательная переменная окружения {name}. "
            "Скопируйте .env.example в .env и заполните значения."
        )
    return value


class Settings(BaseModel):
    PROJECT_NAME: str = "justask"
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
    EMBED_MODEL: str = os.getenv(
        "EMBED_MODEL",
        "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    )
    CHROMA_DIR: str = os.path.join(os.getcwd(), "data", "chroma")
    DOCS_DIR: str = os.path.join(os.getcwd(), "data", "docs")
    FEEDBACK_FILE: str = os.path.join(os.getcwd(), "data", "feedback.jsonl")
    MAX_CONCURRENT_REQUESTS: int = 2
    LTI_CONSUMER_KEY: str = Field(default_factory=lambda: required_env("LTI_CONSUMER_KEY"))
    LTI_SHARED_SECRET: str = Field(default_factory=lambda: required_env("LTI_SHARED_SECRET"))
    JWT_SECRET: str = Field(default_factory=lambda: required_env("JWT_SECRET"))
    DISTANCE_THRESHOLD: float = float(os.getenv("DISTANCE_THRESHOLD", "0.50"))
    ALLOW_GUEST_WRITES: bool = os.getenv("ALLOW_GUEST_WRITES", "false").strip().lower() in {"1", "true", "yes", "on"}
    MAX_UPLOAD_SIZE: int = int(os.getenv("MAX_UPLOAD_SIZE", str(50 * 1024 * 1024)))

settings = Settings()