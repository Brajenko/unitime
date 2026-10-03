from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_secret: str = "change-me-to-a-long-random-string"
    database_url: str = "postgresql+psycopg://slot:slot@localhost:5432/slot"
    redis_url: str = "redis://localhost:6379/0"
    public_url: str = "http://localhost:3000"
    cors_origins: str = "http://localhost:3000,http://localhost:5173"

    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:3000/api/auth/google/callback"

    yandex_client_id: str = ""
    yandex_client_secret: str = ""
    yandex_redirect_uri: str = "http://localhost:3000/api/auth/yandex/callback"

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]


settings = Settings()
