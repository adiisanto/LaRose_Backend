from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application Settings and Environment Configurations."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    APP_NAME: str = "LaRose Floral Studio Backend"
    APP_VERSION: str = "0.1.0"
    API_V1_PREFIX: str = "/api/v1"

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/larose_db"
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 5
    DATABASE_POOL_TIMEOUT: int = 30

    # Security & JWT
    JWT_SECRET_KEY: str = "change_this_to_a_super_secret_key_at_least_32_characters_long"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # CORS
    ALLOWED_CORS_ORIGINS: str = (
        "http://localhost:3000,http://127.0.0.1:3000,https://larose.vercel.app"
    )

    @property
    def cors_origins(self) -> list[str]:
        """Parse comma-separated CORS origins into a list of strings."""
        if not self.ALLOWED_CORS_ORIGINS:
            return ["*"]
        return [origin.strip() for origin in self.ALLOWED_CORS_ORIGINS.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Singleton getter for cached settings."""
    return Settings()


settings = get_settings()
