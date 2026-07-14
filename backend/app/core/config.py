"""全局配置（环境变量优先，本地开发默认 SQLite）。"""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    PROJECT_NAME: str = "焊接在线表格平台"
    API_V1_PREFIX: str = "/api"

    # 数据库：本地开发用 SQLite，Docker 内用 PostgreSQL（见 .env / docker-compose）
    DATABASE_URL: str = "sqlite:///./app.db"

    # JWT
    JWT_SECRET: str = "dev-secret-change-me-please-change-in-prod-32b+"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Redis（第二阶段协作 / 令牌黑名单使用）
    REDIS_URL: str = "redis://localhost:6379/0"

    # 超级管理员初始账号（首次启动 seed 用，生产请改）
    SUPERADMIN_USERNAME: str = "admin"
    SUPERADMIN_PASSWORD: str = "Admin@123456"
    SUPERADMIN_EMAIL: str = "admin@example.com"

    CORS_ORIGINS: list[str] = ["*"]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
