from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    STRAVA_CLIENT_ID: str
    STRAVA_CLIENT_SECRET: str
    STRAVA_VERIFY_TOKEN: str
    STRAVA_ACCESS_TOKEN: str | None = None
    STRAVA_REFRESH_TOKEN: str | None = None
    STRAVA_EXPIRES_AT: int | None = None
    HEVY_API_KEY: str
    SYNC_WINDOW_SECONDS: int = 1800
    STRAVA_API_BASE_URL: str = "https://www.strava.com/api/v3"
    STRAVA_OAUTH_URL: str = "https://www.strava.com/api/v3/oauth/token"
    HEVY_API_BASE_URL: str = "https://api.hevyapp.com"
    WEBHOOK_CALLBACK_URL: str | None = None
    STRAVA_REDIRECT_URI: str = "http://localhost:8888/callback"
    DASHBOARD_USERNAME: str
    DASHBOARD_PASSWORD: str

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()