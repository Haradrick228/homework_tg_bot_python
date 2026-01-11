import logging
import html
from typing import Any, Dict, Optional

import requests


class FoodClient:
    #Клиент OpenFoodFacts для получения калорийности продуктов.

    def __init__(self) -> None:
        self.logger = logging.getLogger(self.__class__.__name__)

    def get_food_info(self, product_name: str) -> Optional[Dict[str, Any]]:
        #Ищем продукт в OpenFoodFacts с приоритетом русских названий и лучшего совпадения.
        
        try:
            resp = requests.get(
                "https://world.openfoodfacts.org/cgi/search.pl",
                params={
                    "action": "process",
                    "search_terms": product_name,
                    "json": True,
                    "page_size": 10,
                    "search_simple": 1,
                    "fields": "product_name,product_name_ru,nutriments",
                    "lang": "ru",
                },
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            products = data.get("products", [])
            if not products:
                return None

            query = product_name.lower()

            def pick_name(p: Dict[str, Any]) -> Optional[str]:
                name = p.get("product_name_ru") or p.get("product_name")
                return html.unescape(name) if name else None

            def score(p: Dict[str, Any]) -> int:
                # Ранжируем: точное начало совпадения > вхождение > остальное. Штраф за напитки.
                name = pick_name(p) or ""
                name_l = name.lower()
                s = 0
                if name_l.startswith(query):
                    s += 3
                elif query in name_l:
                    s += 1
                tags = p.get("categories_tags", []) or []
                if any("beverages" in t for t in tags):
                    s -= 2
                return s

            products.sort(key=score, reverse=True)
            best = products[0]
            best_name = pick_name(best)
            if not best_name:
                return None
            return self._build_product(best_name, best)
        except requests.RequestException as exc:
            self.logger.error("Food API request failed: %s", exc)
            return None

    def _build_product(self, name: str, product: Dict[str, Any]) -> Dict[str, Any]:
        calories = product.get("nutriments", {}).get("energy-kcal_100g")
        if calories is None:
            calories = product.get("nutriments", {}).get("energy_100g")
            if calories is not None:
                calories = calories / 4.184 
        return {
            "name": name,
            "calories": float(calories) if calories is not None else 0.0,
        }
