import logging
import time
from typing import Optional

from telegram import Update
from telegram.error import NetworkError
from telegram.ext import Application

from app.bot.handlers import BotHandlers
from app.config import Config
from app.services.food import FoodClient
from app.services.plotter import ProgressPlotter
from app.services.storage import InMemoryStorage
from app.services.weather import WeatherClient


def build_application(config: Config) -> Application:
    storage = InMemoryStorage()
    weather = WeatherClient(api_key=config.openweather_api_key)
    food = FoodClient()
    plotter = ProgressPlotter()
    handlers = BotHandlers(storage=storage, weather=weather, food=food, plotter=plotter)

    application = (
        Application.builder()
        .token(config.bot_token)
        .connect_timeout(20)
        .read_timeout(60)
        .write_timeout(60)
        .pool_timeout(20)
        .get_updates_connect_timeout(20)
        .get_updates_read_timeout(60)
        .get_updates_write_timeout(60)
        .get_updates_pool_timeout(20)
        .build()
    )
    # Ошибки сети не должны валить приложение
    async def on_error(update, context):
        if context.error:
            logging.getLogger("bot.error").warning("Network/handler error: %s", context.error)
    application.add_error_handler(on_error)
    handlers.register(application)
    # Глушим шум httpx (чтобы токен не светился в URL логах)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    return application


def main() -> None:
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        level=logging.INFO,
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpx").propagate = False
    config = Config.from_env()
    use_webhook = bool(config.webhook_url)

    while True:
        application = build_application(config)
        try:
            if use_webhook:
                application.run_webhook(
                    listen="0.0.0.0",
                    port=config.webhook_port or 8443,
                    url_path=config.webhook_path,
                    webhook_url=(config.webhook_url.rstrip("/") + config.webhook_path),
                    drop_pending_updates=True,
                    allowed_updates=Update.ALL_TYPES,
                    stop_signals=None,
                )
                logging.getLogger("bot.error").warning("run_webhook завершился, перезапускаю...")
            else:
                application.run_polling(
                    allowed_updates=Update.ALL_TYPES,
                    timeout=10,
                    drop_pending_updates=True,
                    stop_signals=None,
                )
                logging.getLogger("bot.error").warning("run_polling завершился без исключения, перезапускаю...")
        except KeyboardInterrupt:
            raise
        except NetworkError as exc:
            logging.getLogger("bot.error").warning("Network error, retrying: %s", exc)
            time.sleep(3)
        except Exception as exc:  # защита от неожиданных падений
            logging.getLogger("bot.error").exception("Unexpected error, restarting: %s", exc)
            time.sleep(3)
        finally:
            try:
                application.shutdown()
            except Exception:
                pass
        # маленькая пауза перед новым циклом, чтобы не спамить запросами при проблемах сети
        time.sleep(2)


if __name__ == "__main__":
    main()
