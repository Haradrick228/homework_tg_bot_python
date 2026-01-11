from app.models import UserProfile


def format_progress(profile: UserProfile) -> str:
    water_left = max(profile.water_goal - profile.logged_water, 0)
    calorie_balance = profile.logged_calories - profile.burned_calories
    calories_left = max(profile.calorie_goal - calorie_balance, 0)

    parts = [
        "Прогресс:",
        "Вода:",
        f"- Выпито: {profile.logged_water:.0f} мл из {profile.water_goal:.0f} мл.",
        f"- Осталось: {water_left:.0f} мл.",
        "Калории:",
        f"- Потреблено: {profile.logged_calories:.0f} ккал из {profile.calorie_goal:.0f} ккал.",
        f"- Сожжено: {profile.burned_calories:.0f} ккал.",
        f"- Баланс: {calorie_balance:.0f} ккал. Осталось до цели: {calories_left:.0f} ккал.",
    ]
    if profile.temperature is not None:
        parts.append(f"Температура в {profile.city}: {profile.temperature:.1f} °C.")
    return "\n".join(parts)
