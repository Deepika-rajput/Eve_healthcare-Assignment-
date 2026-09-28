from dotenv import load_dotenv

load_dotenv()

import os


class Settings:
    """
    Centralised config, read from environment variables so nothing
    sensitive is hardcoded. See .env.example for the variables this
    project expects.
    """

    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", "mysql+pymysql://root:root@localhost:3306/eve_healthcare"
    )
    SECRET_KEY: str = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))


settings = Settings()
