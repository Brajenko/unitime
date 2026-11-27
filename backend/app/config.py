from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_secret: str = ""
    database_url: str = "postgresql+psycopg://slot:slot@localhost:5432/slot"
    redis_url: str = "redis://localhost:6379/0"
    public_url: str = "http://localhost:3000"
    sync_interval_seconds: int = 900
    sync_visibility_timeout: int = 3600
    sync_on_worker_start: bool = True
    grid_cache_enabled: bool = True
    cors_origins: str = "http://localhost:3000,http://localhost:5173"

    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:3000/api/auth/google/callback"

    yandex_client_id: str = ""
    yandex_client_secret: str = ""
    yandex_redirect_uri: str = "http://localhost:3000/api/auth/yandex/callback"

    def require_secret(self) -> None:
        """Без нормального ключа шифрования сервис не стартует: иначе токены лежали бы под известным ключом."""
        value = self.app_secret.strip()
        if not value or value in Constants.PLACEHOLDER_SECRETS:
            raise RuntimeError(
                "APP_SECRET не задан. Сгенерируйте ключ: echo \"APP_SECRET=$(openssl rand -hex 32)\" >> .env"
            )
        if len(value) < Constants.MIN_SECRET_LENGTH:
            raise RuntimeError(f"APP_SECRET слишком короткий: нужно не меньше {Constants.MIN_SECRET_LENGTH} символов")

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]


class Constants:
    MIN_SECRET_LENGTH = 32
    PLACEHOLDER_SECRETS = ("change-me-to-a-long-random-string",)


settings = Settings()
