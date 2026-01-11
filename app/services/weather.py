import logging
from typing import Optional

import requests


class WeatherClient:
    #Клиент OpenWeather для получения температуры.

    def __init__(self, api_key: Optional[str]) -> None:
        self.api_key = api_key
        self.logger = logging.getLogger(self.__class__.__name__)

    def fetch_temperature(self, city: str) -> Optional[float]:
        if not self.api_key or not city:
            return None
        try:
            resp = requests.get(
                "https://api.openweathermap.org/data/2.5/weather",
                params={"q": city, "appid": self.api_key, "units": "metric"},
                timeout=10,
            )
            if resp.status_code != 200:
                self.logger.warning("Weather API error (%s): %s", resp.status_code, resp.text)
                return None
            data = resp.json()
            return data.get("main", {}).get("temp")
        except requests.RequestException as exc:
            self.logger.error("Weather request failed: %s", exc)
            return None
