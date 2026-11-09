import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(os.environ.get("WOW_PROJECT_ROOT", Path(__file__).resolve().parents[2])).resolve()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    database_url: str = "postgresql+psycopg://azeroth:azeroth@127.0.0.1:5439/azeroth_knowledge"
    hf_home: str = str(ROOT / ".cache" / "huggingface")
    wow_embeddings_enabled: bool = True
    wow_embedding_model: str = "intfloat/multilingual-e5-small"
    wow_max_download_bytes: int = 2_097_152
    wow_user_agent: str = "AzerothCompanion/0.1 (personal research; local indexing)"


settings = Settings()
