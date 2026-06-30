import os

class Settings:
    YASNO_BASE_URL: str = os.getenv("APP_YASNO_BASE_URL", "https://app.yasno.ua/api/blackout-service")
    TIMEOUT_SECONDS: int = int(os.getenv("APP_TIMEOUT_SECONDS", "30"))
    DEFAULT_REGION_ID: int = int(os.getenv("APP_DEFAULT_REGION_ID", "25"))  # Kyiv
    DEFAULT_DSO_ID: int = int(os.getenv("APP_DEFAULT_DSO_ID", "902"))    # DTEK Kyiv Grids
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

settings = Settings()
