from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class FoodLogEntry:
    name: str
    grams: float
    calories: float
    timestamp: dt.datetime = field(default_factory=dt.datetime.now)


@dataclass
class WorkoutLogEntry:
    workout_type: str
    minutes: float
    calories: float
    water_bonus: int
    timestamp: dt.datetime = field(default_factory=dt.datetime.now)


@dataclass
class UserProfile:
    user_id: int
    weight: float = 70.0
    height: float = 170.0
    age: int = 30
    activity: float = 30.0  # минут в день
    city: str = "Moscow"
    gender: str = "unspecified"
    calorie_goal_manual: Optional[float] = None
    temperature: Optional[float] = None

    water_goal: int = 2100
    calorie_goal: int = 2000
    workout_water_bonus: int = 0

    logged_water: float = 0.0
    logged_calories: float = 0.0
    burned_calories: float = 0.0
    food_log: List[FoodLogEntry] = field(default_factory=list)
    workout_log: List[WorkoutLogEntry] = field(default_factory=list)

    last_reset: dt.datetime = field(default_factory=dt.datetime.now)
