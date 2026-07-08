from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "mysql+pymysql://root:root@localhost:3306/ubd"
    test_database_url: str = "mysql+pymysql://root:root@localhost:3306/ubd_test"
    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 720
    crawler_api_key: str = "change-me-crawler-key"
    seed_admin_email: str = "admin@example.com"
    seed_admin_password: str = "change-me-admin-password"


settings = Settings()
