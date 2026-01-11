from enum import IntEnum


class ProfileState(IntEnum):
    WEIGHT = 0
    HEIGHT = 1
    AGE = 2
    ACTIVITY = 3
    CITY = 4
    GENDER = 5
    CUSTOM_CALORIES = 6


class FoodState(IntEnum):
    NAME = 7
    GRAMS = 8


class WaterState(IntEnum):
    AMOUNT = 9


class WorkoutState(IntEnum):
    TYPE = 10
    MINUTES = 11
