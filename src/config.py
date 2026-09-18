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
    max_query_length: int = Field(default_factory=lambda: int(os.getenv("MAX_QUERY_LENGTH", "500")))
    max_content_chars_per_source: int = Field(default_factory=lambda: int(os.getenv("MAX_CONTENT_CHARS_PER_SOURCE", "1500")))

    def validate_keys(self) -> None:
        """Ensure required API keys are populated."""
        missing = []
        if not self.groq_api_key or self.groq_api_key == "your_groq_api_key_here":
            missing.append("GROQ_API_KEY")
        if not self.tavily_api_key or self.tavily_api_key == "your_tavily_api_key_here":
            missing.append("TAVILY_API_KEY")
        
        if missing:
            raise ValueError(
                f"Missing or placeholder API keys found for: {', '.join(missing)}.\n"
                f"Please update your .env file located at: {BASE_DIR / '.env'}"
            )


settings = Settings()
