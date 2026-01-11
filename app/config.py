import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class Config:
    bot_token: str
    openweather_api_key: Optional[str] = None
    webhook_url: Optional[str] = None
    webhook_port: Optional[int] = None
    webhook_path: str = "/webhook"

    @staticmethod
    def from_env() -> "Config":
        token = os.getenv("BOT_TOKEN")
        if not token:
            raise RuntimeError("Укажите токен бота в переменной окружения BOT_TOKEN.")
        webhook_url = os.getenv("WEBHOOK_URL")
        webhook_port = os.getenv("WEBHOOK_PORT")
        webhook_path = os.getenv("WEBHOOK_PATH", "/webhook")
        webhook_port_int = int(webhook_port) if webhook_port else None
        return Config(
            bot_token=token,
            openweather_api_key=os.getenv("OPENWEATHER_API_KEY"),
            webhook_url=webhook_url,
            webhook_port=webhook_port_int,
            webhook_path=webhook_path,
        )
