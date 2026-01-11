import math
from typing import Tuple

from app.models import UserProfile


def _cap_activity(minutes: float) -> float:
    #Ограничиваем активность адекватным диапазоном.
    return max(0.0, min(minutes, 720.0))


def calculate_water_goal(profile: UserProfile) -> int:
    #Считаем норму воды с учетом веса, активности, жары и тренировок.
    base = profile.weight * 30
    activity = _cap_activity(profile.activity)
    activity_bonus = (activity / 30) * 500
    temp_bonus = 0
    if profile.temperature is not None:
        if profile.temperature > 30:
            temp_bonus = 1000
        elif profile.temperature > 25:
            temp_bonus = 500
    total = base + activity_bonus + temp_bonus + profile.workout_water_bonus
    #защита от нереалистично больших значений
    return int(min(max(total, 1500), 5000))


def calculate_calorie_goal(profile: UserProfile) -> int:
    #Формула Миффлина-Джеора + бонус за активность.
    bmr = 10 * profile.weight + 6.25 * profile.height - 5 * profile.age
    if profile.gender == "male":
        bmr += 5
    elif profile.gender == "female":
        bmr -= 161

    activity_minutes = _cap_activity(profile.activity)
    activity_bonus = min(400, (activity_minutes / 30) * 200)
    return int(bmr + activity_bonus)


def estimate_workout_calories(workout_type: str, minutes: float, weight: float) -> Tuple[float, int]:
    #Оцениваем калории по MET и добавляем бонус воды за тренировку.
    workout = workout_type.lower()
    met_values = {
        "бег": 9.8,
        "run": 9.8,
        "running": 9.8,
        "ходьба": 3.5,
        "walk": 3.5,
        "вело": 7.5,
        "bike": 7.5,
        "cycling": 7.5,
        "йога": 3,
        "yoga": 3,
        "силовая": 6,
        "strength": 6,
        "swim": 8,
        "плавание": 8,
    }
    met = met_values.get(workout, 6)
    calories = 0.0175 * met * weight * minutes
    water_bonus = math.ceil(minutes / 30) * 200 if minutes > 0 else 0
    return calories, water_bonus
