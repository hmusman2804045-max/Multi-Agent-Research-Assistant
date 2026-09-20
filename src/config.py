import os
from pathlib import Path
from dotenv import load_dotenv
from pydantic import BaseModel, Field

from src.logger import setup_logging

# Load .env from project root directory
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=BASE_DIR / ".env")

# Initialize logging
setup_logging()


import secrets

# Known insecure placeholder patterns
INSECURE_SECRET_PATTERNS = [
    "your_jwt_secret",
    "change-this",
    "dev-insecure",
    "replace-in-production",
    "secret-key",
]


def _get_jwt_secret() -> str:
    """Retrieve JWT secret from environment or load/generate a secure local gitignored secret."""
    env_secret = os.getenv("JWT_SECRET_KEY", "").strip()
    if env_secret:
        return env_secret

    secret_file = BASE_DIR / ".jwt_secret"
    if secret_file.exists():
        try:
            cached_secret = secret_file.read_text(encoding="utf-8").strip()
            if len(cached_secret) >= 32:
                return cached_secret
        except Exception:
            pass

    # In absence of configured secret, generate a cryptographically strong local secret and save to .jwt_secret
    new_secret = secrets.token_urlsafe(32)
    try:
        secret_file.write_text(new_secret, encoding="utf-8")
    except Exception:
        pass
    return new_secret


class Settings(BaseModel):
    """Application Settings and Configuration."""
    groq_api_key: str = Field(default_factory=lambda: os.getenv("GROQ_API_KEY", ""))
    tavily_api_key: str = Field(default_factory=lambda: os.getenv("TAVILY_API_KEY", ""))
    groq_model: str = Field(default_factory=lambda: os.getenv("GROQ_MODEL", "openai/gpt-oss-20b"))
    max_search_results: int = Field(default_factory=lambda: int(os.getenv("MAX_SEARCH_RESULTS", "5")))
    max_sub_queries: int = Field(default_factory=lambda: int(os.getenv("MAX_SUB_QUERIES", "3")))
    max_results_per_subquery: int = Field(default_factory=lambda: int(os.getenv("MAX_RESULTS_PER_SUBQUERY", "3")))
    temperature: float = Field(default_factory=lambda: float(os.getenv("TEMPERATURE", "0.2")))
    max_tokens: int = Field(default_factory=lambda: int(os.getenv("MAX_TOKENS", "1024")))
    planner_temperature: float = Field(default_factory=lambda: float(os.getenv("PLANNER_TEMPERATURE", "0.1")))
    planner_max_tokens: int = Field(default_factory=lambda: int(os.getenv("PLANNER_MAX_TOKENS", "500")))
    summarizer_temperature: float = Field(default_factory=lambda: float(os.getenv("SUMMARIZER_TEMPERATURE", "0.1")))
    summarizer_max_tokens: int = Field(default_factory=lambda: int(os.getenv("SUMMARIZER_MAX_TOKENS", "2048")))
    fact_checker_temperature: float = Field(default_factory=lambda: float(os.getenv("FACT_CHECKER_TEMPERATURE", "0.1")))
    fact_checker_max_tokens: int = Field(default_factory=lambda: int(os.getenv("FACT_CHECKER_MAX_TOKENS", "2048")))
    # Security & Content Limits (Phase 3)
    max_query_length: int = Field(default_factory=lambda: int(os.getenv("MAX_QUERY_LENGTH", "500")))
    max_content_chars_per_source: int = Field(default_factory=lambda: int(os.getenv("MAX_CONTENT_CHARS_PER_SOURCE", "1500")))

    # Database & Authentication (Phase 5)
    mongodb_uri: str = Field(default_factory=lambda: os.getenv("MONGODB_URI", ""))
    mongodb_db_name: str = Field(default_factory=lambda: os.getenv("MONGODB_DB_NAME", "research_assistant"))
    jwt_secret_key: str = Field(default_factory=_get_jwt_secret)
    jwt_algorithm: str = Field(default_factory=lambda: os.getenv("JWT_ALGORITHM", "HS256"))
    auth_token_expire_minutes: int = Field(default_factory=lambda: int(os.getenv("AUTH_TOKEN_EXPIRE_MINUTES", "1440")))

    # Rate Limiting & User Quotas (Phase 6)
    daily_query_limit: int = Field(default_factory=lambda: int(os.getenv("DAILY_QUERY_LIMIT", "10")))
    global_daily_query_limit: int = Field(default_factory=lambda: int(os.getenv("GLOBAL_DAILY_QUERY_LIMIT", "100")))
    requests_per_minute_limit: int = Field(default_factory=lambda: int(os.getenv("REQUESTS_PER_MINUTE_LIMIT", "3")))
    auth_max_failed_attempts: int = Field(default_factory=lambda: int(os.getenv("AUTH_MAX_FAILED_ATTEMPTS", "5")))
    auth_lockout_minutes: int = Field(default_factory=lambda: int(os.getenv("AUTH_LOCKOUT_MINUTES", "15")))
    # Password Reset & Email Configuration
    resend_api_key: str = Field(default_factory=lambda: os.getenv("RESEND_API_KEY", ""))
    resend_from_email: str = Field(default_factory=lambda: os.getenv("RESEND_FROM_EMAIL", "onboarding@resend.dev"))
    password_reset_token_expire_minutes: int = Field(default_factory=lambda: int(os.getenv("PASSWORD_RESET_TOKEN_EXPIRE_MINUTES", "15")))
    password_reset_limit_per_hour: int = Field(default_factory=lambda: int(os.getenv("PASSWORD_RESET_LIMIT_PER_HOUR", "3")))
    password_reset_timing_floor_seconds: float = Field(default_factory=lambda: float(os.getenv("PASSWORD_RESET_TIMING_FLOOR_SECONDS", "0.35")))

    def validate_keys(self) -> None:
        """Ensure required API keys and security credentials are valid."""
        missing = []
        if not self.groq_api_key or self.groq_api_key == "your_groq_api_key_here":
            missing.append("GROQ_API_KEY")
        if not self.tavily_api_key or self.tavily_api_key == "your_tavily_api_key_here":
            missing.append("TAVILY_API_KEY")
        
        # Check for weak or placeholder JWT secret if explicitly set in environment
        env_jwt = os.getenv("JWT_SECRET_KEY", "").strip()
        if env_jwt:
            if len(env_jwt) < 32:
                raise ValueError(
                    f"Insecure JWT_SECRET_KEY: Key length is only {len(env_jwt)} characters (must be >= 32)."
                )
            if any(p in env_jwt.lower() for p in INSECURE_SECRET_PATTERNS):
                raise ValueError(
                    "Insecure placeholder detected in JWT_SECRET_KEY. Please provide a secure random key."
                )

        if missing:
            raise ValueError(
                f"Missing or placeholder API keys found for: {', '.join(missing)}.\n"
                f"Please update your .env file located at: {BASE_DIR / '.env'}"
            )

    def validate_resend_key(self) -> None:
        """Ensure Resend API key is configured when sending emails."""
        if not self.resend_api_key or self.resend_api_key == "your_resend_api_key_here":
            raise ValueError(
                "RESEND_API_KEY is not configured or is a placeholder.\n"
                f"Please set a valid RESEND_API_KEY in your .env file: {BASE_DIR / '.env'}"
            )


settings = Settings()
