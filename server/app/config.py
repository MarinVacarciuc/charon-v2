"""Settings, loaded once from server/.env.

Only bootstrap values live here: where things are, and what a *fresh* database should be
seeded with. Anything an operator can change at runtime lives in the config_kv table
instead, because a value that can be changed from the UI has to survive a restart, and a
value read from the environment does not.
"""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

SERVER_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=SERVER_DIR / ".env",
        env_prefix="CHARON_",
        extra="ignore",
    )

    host: str = "0.0.0.0"
    port: int = 8770

    # Shared secret for mutating endpoints. Read-only routes (SSE, frames, the gate
    # terminal) stay open on the LAN so a phone propped at the gate needs no login.
    admin_token: str = ""

    tg_token: str = ""

    # Seeds for a fresh database only; the live values come from config_kv.
    sim_threshold: float = 0.45
    confirm_frames: int = 3
    dwell_ms: int = 2000

    @property
    def db_path(self) -> Path:
        return SERVER_DIR / "data" / "charon.db"

    @property
    def models_dir(self) -> Path:
        return SERVER_DIR / "models"

    @property
    def voice_dir(self) -> Path:
        return SERVER_DIR / "voice"

    @property
    def migrations_dir(self) -> Path:
        return SERVER_DIR / "app" / "db" / "migrations"


@lru_cache
def get_settings() -> Settings:
    return Settings()
