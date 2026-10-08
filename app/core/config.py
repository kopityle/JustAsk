import os
from dotenv import load_dotenv
from pydantic import BaseModel, Field

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