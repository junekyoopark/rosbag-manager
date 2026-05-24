from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://user:pass@postgres/rosbag_viewer"
    SYNC_DATABASE_URL: str = "postgresql://user:pass@postgres/rosbag_viewer"
    REDIS_URL: str = "redis://redis:6379/0"
    DATA_DIR: str = "/data"
    UPLOADS_DIR: str = "/data/uploads"
    RRD_DIR: str = "/data/rrd"
    THUMB_DIR: str = "/data/thumb"
    PUBLIC_HOST: str = "localhost"
    MAX_UPLOAD_SIZE_GB: int = 50
    STORAGE_BACKEND: str = "local"
    S3_BUCKET: str = ""
    S3_ENDPOINT: str = ""
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    RERUN_VERSION: str = "0.22.1"
    SECRET_KEY: str = "change-me-in-production-use-a-long-random-string"
    INITIAL_ADMIN_USERNAME: str = "admin"
    INITIAL_ADMIN_PASSWORD: str = ""

    class Config:
        env_file = ".env"


settings = Settings()
