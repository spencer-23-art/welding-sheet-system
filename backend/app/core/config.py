"""Application settings; environment variables override local defaults."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    PROJECT_NAME: str = "焊接在线表格平台"
    DATABASE_URL: str = "sqlite:///./app.db"

    JWT_SECRET: str = "dev-secret-change-me-please-change-in-prod-32b+"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    SUPERADMIN_USERNAME: str = "admin"
    SUPERADMIN_PASSWORD: str = "Admin@123456"
    SUPERADMIN_EMAIL: str = "admin@example.com"

    CORS_ORIGINS: list[str] = ["*"]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
