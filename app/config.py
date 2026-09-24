from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    stacks_api_base: str = "https://stacksja.com/api/v1/public"
    stacks_api_key: str = ""

    anthropic_api_key: str = ""

    live_cache_ttl: int = 15
    static_cache_ttl: int = 3600

    cors_origins: str = "http://localhost:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
