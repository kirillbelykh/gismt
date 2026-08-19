"""Application configuration"""
from typing import Optional, Dict, Any, ClassVar
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings"""

    # App
    APP_NAME: str = "Aggregation System"
    DEBUG: bool = Field(default=False, env="DEBUG") # type: ignore
    SECRET_KEY: str = Field(..., env="SECRET_KEY") # type: ignore
    API_SUPERUSER_TOKEN: Optional[str] = Field(default=None, env="API_SUPERUSER_TOKEN") # type: ignore

    # Task timeouts and retries
    TASK_TIMEOUTS: ClassVar[Dict[str, int]] = {
        'order_codes': 600,  # 10 minutes
        'apply_report': 300,  # 5 minutes
        'aggregation': 600,   # 10 minutes
        'introduction': 300,  # 5 minutes
    }

    TASK_RETRIES: ClassVar[Dict[str, Any]] = {
        'max_retries': 5,
        'retry_delay': 60,  # 1 minute
    }

    # CRPT configuration
    CRPT_CONFIG: ClassVar[Dict[str, Any]] = {
        'participant_id': '7843316794',
        'product_group': 'wheelchairs',
    }

    CRPT_SIGNER_MODE: str = "local"
    CRPT_SIGNER_URL: Optional[str] = None
    CRPT_SIGNER_TOKEN: Optional[str] = None

    # Database
    POSTGRES_USER: str = Field(default="postgres", env="POSTGRES_USER") # type: ignore
    POSTGRES_PASSWORD: str = Field(..., env="POSTGRES_PASSWORD") # type: ignore
    POSTGRES_DB: str = Field(default="aggr_system", env="POSTGRES_DB") # type: ignore
    POSTGRES_HOST: str = Field(default="localhost", env="POSTGRES_HOST") # type: ignore
    POSTGRES_PORT: int = Field(default=5432, env="POSTGRES_PORT") # type: ignore

    @property
    def database_url(self) -> str:
        """Get async database URL"""
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    @property
    def database_url_sync(self) -> str:
        """Get sync database URL for Alembic"""
        return f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    # Redis
    REDIS_URL: str = Field(default="redis://localhost:6379/0", env="REDIS_URL") # type: ignore

    # Celery
    CELERY_BROKER_URL: str = Field(default="redis://localhost:6379/1", env="CELERY_BROKER_URL") # type: ignore
    CELERY_RESULT_BACKEND: str = Field(default="redis://localhost:6379/2", env="CELERY_RESULT_BACKEND") # type: ignore

    # CRPT
    CRPT_THUMBPRINT: str = Field(..., env="CRPT_THUMBPRINT") # type: ignore
    OMS_ID: str = Field(..., env="OMS_ID") # type: ignore
    OMS_CONN_ID: str = Field(..., env="OMS_CONN_ID") # type: ignore
    CRPT_SANDBOX: bool = Field(default=True, env="CRPT_SANDBOX") # type: ignore
    CRPT_MOCK_MODE: bool = Field(default=False, env="CRPT_MOCK_MODE") # type: ignore

    # CRPT URLs
    @property
    def crpt_base_url(self) -> str:
        """SUZ base URL"""
        if self.CRPT_MOCK_MODE:
            return "http://mock-crpt:8000"
        if self.CRPT_SANDBOX:
            return "https://suz.sandbox.crptech.ru"
        return "https://suz.crptech.ru"

    @property
    def crpt_auth_url(self) -> str:
        """TRUE API auth URL"""
        if self.CRPT_MOCK_MODE:
            return "http://mock-crpt:8000/api/v3/true-api"
        if self.CRPT_SANDBOX:
            return "https://markirovka.sandbox.crptech.ru/api/v3/true-api"
        return "https://markirovka.crptech.ru/api/v3/true-api"

    # GS1
    GS1_PREFIX: str = Field(..., env="GS1_PREFIX") # type: ignore
    GS1_EXTENSION_DIGIT: int = Field(default=0, env="GS1_EXTENSION_DIGIT") # type: ignore

    # Printing
    LABELS_DIR: str = Field(default="./labels", env="LABELS_DIR") # type: ignore
    BARTENDER_PATH: Optional[str] = Field(default=None, env="BARTENDER_PATH") # type: ignore

    # Monitoring
    SENTRY_DSN: Optional[str] = Field(default=None, env="SENTRY_DSN") # type: ignore

    # Environment
    ENVIRONMENT: str = Field(default="development", env="ENVIRONMENT") # type: ignore

    # Logging
    LOG_DIR: str = Field(default="logs", env="LOG_DIR") # type: ignore
    LOG_FILE: str = Field(default="app.log", env="LOG_FILE") # type: ignore
    LOG_MAX_BYTES: int = Field(default=10 * 1024 * 1024, env="LOG_MAX_BYTES") # type: ignore # 10MB
    LOG_BACKUP_COUNT: int = Field(default=5, env="LOG_BACKUP_COUNT") # type: ignore

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings() # type: ignore