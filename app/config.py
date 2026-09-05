"""
Application configuration.

All settings can be overridden with environment variables (or a .env file
in the project root, since we use pydantic-settings which reads it
automatically).
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # --- General ---
    APP_NAME: str = "Exam Seat & Hall Allocation System"
    ENV: str = "development"

    # --- Database ---
    # Defaults to a local SQLite file. Point this at Postgres/MySQL in
    # production, e.g. postgresql+psycopg2://user:pass@host:5432/dbname
    DATABASE_URL: str = "sqlite:///./exam_allocation.db"

    # --- Security / JWT ---
    SECRET_KEY: str = "CHANGE_ME_SUPER_SECRET_KEY_IN_PRODUCTION"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 12  # 12 hours

    # --- CORS ---
    # Comma-separated list of allowed frontend origins, e.g.
    # "https://my-app.vercel.app,http://localhost:5173". Defaults to "*"
    # for local development; set this explicitly in production (Render).
    ALLOWED_ORIGINS: str = "*"

    @property
    def cors_origins(self) -> list[str]:
        if self.ALLOWED_ORIGINS.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]

    # --- Default admin (used by seed.py) ---
    DEFAULT_ADMIN_USERNAME: str = "admin"
    DEFAULT_ADMIN_EMAIL: str = "admin@mapoly.edu.ng"
    DEFAULT_ADMIN_PASSWORD: str = "ChangeMe123!"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
