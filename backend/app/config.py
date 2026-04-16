"""Configuration centralisee via Pydantic Settings."""
from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    APP_NAME: str = "Usine Bombe Atomique"
    APP_VERSION: str = "0.1.0"
    ENV: str = "development"
    DEBUG: bool = False

    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    API_PREFIX: str = "/api/v1"

    POSTGRES_HOST: str = "postgres"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "uba"
    POSTGRES_USER: str = "uba"
    POSTGRES_PASSWORD: str = Field(default="changeme")
    POSTGRES_POOL_MIN: int = 5
    POSTGRES_POOL_MAX: int = 20

    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str = Field(default="")
    REDIS_DB: int = 0

    JWT_SECRET: str = Field(default="changeme-32-bytes-hex")
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60

    ANTHROPIC_API_KEY: str = Field(default="")
    ANTHROPIC_MODEL: str = "claude-sonnet-4-6"
    CLAUDE_CODE_PATH: str = "claude"
    CLAUDE_CODE_TIMEOUT: int = 900

    RATE_LIMIT_PER_MINUTE: int = 60
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    @property
    def postgres_dsn(self) -> str:
        return (
            f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def redis_url(self) -> str:
        auth = f":{self.REDIS_PASSWORD}@" if self.REDIS_PASSWORD else ""
        return f"redis://{auth}{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
