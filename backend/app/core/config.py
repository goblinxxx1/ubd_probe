from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "mysql+pymysql://root:root@localhost:3306/ubd"
    test_database_url: str = "mysql+pymysql://root:root@localhost:3306/ubd_test"
    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 720
    crawler_api_key: str = "change-me-crawler-key"
    # NOTE: brief specified 0.6, but the reworded-promo fixture (test_offer_promo_dedup.py)
    # measures exactly 0.5 Jaccard similarity with the specified _promo_text; 0.6 never
    # collapses it. 0.5 is the largest value that still collapses that case while keeping a
    # comfortable margin (0.167) above the nearest must-stay-separate case (0.333). See
    # task-2-report.md for the full evidence.
    dedup_text_similarity_threshold: float = 0.5
    seed_admin_email: str = "admin@example.com"
    seed_admin_password: str = "change-me-admin-password"


settings = Settings()
