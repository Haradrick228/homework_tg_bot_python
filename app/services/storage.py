import datetime as dt
from typing import Dict

from app.models import UserProfile
from app.services.calculations import calculate_calorie_goal, calculate_water_goal


class InMemoryStorage:

    def __init__(self) -> None:
        self.users: Dict[int, UserProfile] = {}

    def get_or_create_user(self, user_id: int) -> UserProfile:
        if user_id not in self.users:
            self.users[user_id] = UserProfile(user_id=user_id)
            self.recalc_goals(self.users[user_id])
        profile = self.users[user_id]
        self.reset_daily_if_needed(profile)
        return profile

    def reset_daily_if_needed(self, profile: UserProfile) -> None:
        today = dt.date.today()
        if not profile.last_reset or profile.last_reset.date() != today:
            profile.logged_water = 0.0
            profile.logged_calories = 0.0
            profile.burned_calories = 0.0
            profile.food_log.clear()
            profile.workout_log.clear()
            profile.workout_water_bonus = 0
            profile.last_reset = dt.datetime.now()
            self.recalc_goals(profile)

    def recalc_goals(self, profile: UserProfile) -> None:
        profile.water_goal = calculate_water_goal(profile)
        if profile.calorie_goal_manual:
            profile.calorie_goal = int(profile.calorie_goal_manual)
        else:
            profile.calorie_goal = max(1200, calculate_calorie_goal(profile))
