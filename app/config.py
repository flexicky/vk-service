from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VK_")
    token: str = ""
    api_version: str = "5.199"
    database: str = "vk_service.db"
    poll_interval: float = 30.0
    grpc_host: str = "0.0.0.0"
    grpc_port: int = 50051
    request_timeout: float = 10.0

    def model_post_init(self, __context):
        if self.poll_interval <= 0 or self.request_timeout <= 0:
            raise ValueError("poll_interval and request_timeout must be positive")
