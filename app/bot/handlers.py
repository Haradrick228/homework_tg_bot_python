import logging
from typing import Optional

from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from app.bot.formatters import format_progress
from app.bot.state import FoodState, ProfileState, WaterState, WorkoutState
from app.models import FoodLogEntry, UserProfile, WorkoutLogEntry
from app.services.calculations import estimate_workout_calories
from app.services.food import FoodClient
from app.services.plotter import ProgressPlotter
from app.services.storage import InMemoryStorage
from app.services.weather import WeatherClient


class BotHandlers:

    WORKOUT_TYPES_RU = ["бег", "ходьба", "вело", "йога", "силовая", "плавание"]
    WORKOUT_SYNONYMS = {
        "бег": "бег",
        "run": "бег",
        "running": "бег",
        "ходьба": "ходьба",
        "walk": "ходьба",
        "вело": "вело",
        "велосипед": "вело",
        "bike": "вело",
        "cycling": "вело",
        "йога": "йога",
        "yoga": "йога",
        "силовая": "силовая",
        "strength": "силовая",
        "сила": "силовая",
        "плавание": "плавание",
        "swim": "плавание",
    }
    BUTTON_PATTERNS = {
        "profile": r"Настроить профиль",
        "water": r"Добавить воду",
        "food": r"Лог еды",
        "workout": r"Тренировка",
        "progress": r"Прогресс",
        "plots": r"Графики",
    }
    BUTTON_REGEX = r"^(Настроить профиль|Добавить воду|Лог еды|Тренировка|Прогресс|Графики)$"

    def __init__(
        self,
        storage: InMemoryStorage,
        weather: WeatherClient,
        food: FoodClient,
        plotter: ProgressPlotter,
    ) -> None:
        self.storage = storage
        self.weather = weather
        self.food = food
        self.plotter = plotter
        self.logger = logging.getLogger(self.__class__.__name__)

    #Утилиты 
    @staticmethod
    def parse_float(text: str) -> Optional[float]:
        try:
            return float(text.replace(",", "."))
        except (TypeError, ValueError):
            return None

    def ensure_profile(self, update: Update) -> UserProfile:
        user = update.effective_user
        return self.storage.get_or_create_user(user.id)

    @staticmethod
    def main_keyboard() -> ReplyKeyboardMarkup:
        return ReplyKeyboardMarkup(
            [
                ["Настроить профиль", "Добавить воду"],
                ["Лог еды", "Тренировка"],
                ["Прогресс", "Графики"],
            ],
            resize_keyboard=True,
        )

    @classmethod
    def workout_keyboard(cls) -> ReplyKeyboardMarkup:
        rows = [
            ["бег", "ходьба", "вело"],
            ["йога", "силовая", "плавание"],
        ]
        return ReplyKeyboardMarkup(rows, resize_keyboard=True)

    def normalize_workout_type(self, raw: str) -> str:
        return self.WORKOUT_SYNONYMS.get(raw.strip().lower(), raw.strip())

    @staticmethod
    def in_profile(context: ContextTypes.DEFAULT_TYPE) -> bool:
        return bool(context.user_data.get("profile_in_progress"))

    @staticmethod
    def require_no_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        if context.user_data.get("profile_in_progress"):
            text = "Сначала завершите настройку профиля или введите /cancel."
            if update.message:
                update.message.reply_text(text)
            return True
        return False

    @property
    def button_filter(self):
        return filters.Regex(self.BUTTON_REGEX)

    def is_button(self, update: Update) -> bool:
        msg = update.message
        return bool(msg and msg.text and self.button_filter.filter(msg))

    @staticmethod
    def is_number(text: str) -> bool:
        try:
            float(text.replace(",", "."))
            return True
        except Exception:
            return False

    #Общие команды
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        self.ensure_profile(update)
        await update.message.reply_text(
            "Привет! Я помогу считать воду и калории.\n"
            "Настрой профайл через /set_profile, записывай воду через /log_water 250,\n"
            "еду через /log_food <продукт>, тренировки через /log_workout <тип> <минуты>.\n"
            "Типы тренировок: бег, ходьба, вело, йога, силовая, плавание.\n"
            "Посмотреть прогресс: /check_progress. Графики: /plot_progress.\n"
            "Можешь пользоваться кнопками ниже или командами. Подсказки: /help",
            reply_markup=self.main_keyboard(),
        )

    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text(
            "Доступные команды:\n"
            "/set_profile — шаг за шагом настроить вес, активность, город.\n"
            "/log_water <мл> — записать воду.\n"
            "/log_food <название> — найти калорийность продукта и ввести граммы.\n"
            "/log_workout <тип> <минуты> — записать тренировку и расход. Доступные типы: бег, ходьба, вело, йога, силовая, плавание.\n"
            "/check_progress — текущие итоги по воде и калориям.\n"
            "/plot_progress — отправить графики прогресса.\n"
            "/cancel — выйти из текущего диалога.",
            reply_markup=self.main_keyboard(),
        )

    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        context.user_data.pop("profile_draft", None)
        context.user_data.pop("food_context", None)
        context.user_data.pop("workout_context", None)
        context.user_data["profile_in_progress"] = False
        await update.message.reply_text("Диалог отменен.", reply_markup=self.main_keyboard())
        return ConversationHandler.END

    #Профиль
    async def set_profile_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        context.user_data["profile_draft"] = {}
        context.user_data["profile_in_progress"] = True
        await update.message.reply_text(
            "Введите ваш вес (в кг):", reply_markup=ReplyKeyboardRemove()
        )
        return ProfileState.WEIGHT

    async def set_weight(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        value = self.parse_float(update.message.text)
        if value is None or value < 20 or value > 400:
            await update.message.reply_text("Введите вес в кг (20-400).")
            return ProfileState.WEIGHT
        context.user_data["profile_draft"]["weight"] = value
        await update.message.reply_text("Введите ваш рост (в см):")
        return ProfileState.HEIGHT

    async def set_height(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        value = self.parse_float(update.message.text)
        if value is None or value < 100 or value > 250:
            await update.message.reply_text("Введите рост в см (100-250).")
            return ProfileState.HEIGHT
        context.user_data["profile_draft"]["height"] = value
        await update.message.reply_text("Введите ваш возраст:")
        return ProfileState.AGE

    async def set_age(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        value = self.parse_float(update.message.text)
        if value is None or value < 10 or value > 100:
            await update.message.reply_text("Введите возраст (10-100).")
            return ProfileState.AGE
        context.user_data["profile_draft"]["age"] = value
        await update.message.reply_text("Сколько минут активности у вас в день (не считая тренировок)?")
        return ProfileState.ACTIVITY

    async def set_activity(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        value = self.parse_float(update.message.text)
        if value is None or value < 0 or value > 720:
            await update.message.reply_text("Введите время активности в минутах (0-720).")
            return ProfileState.ACTIVITY
        context.user_data["profile_draft"]["activity"] = value
        await update.message.reply_text("В каком городе вы находитесь?")
        return ProfileState.CITY

    async def set_city(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        context.user_data["profile_draft"]["city"] = update.message.text.strip()
        await update.message.reply_text("Ваш пол? Напишите m/f или пропустите.")
        return ProfileState.GENDER

    async def set_gender(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        gender_raw = update.message.text.strip().lower()
        if gender_raw.startswith("m") or "м" == gender_raw:
            gender = "male"
        elif gender_raw.startswith("f") or "ж" == gender_raw:
            gender = "female"
        else:
            gender = "unspecified"
        context.user_data["profile_draft"]["gender"] = gender
        await update.message.reply_text(
            "Цель по калориям (ккал). Напишите число или 'авто'/'auto'/'skip', чтобы рассчитать автоматически."
        )
        return ProfileState.CUSTOM_CALORIES

    async def finish_profile(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        text = (update.message.text or "").strip()
        draft = context.user_data.get("profile_draft", {})
        if text and text.lower() not in {"авто", "auto", "skip", "пропустить"}:
            calorie_goal = self.parse_float(text)
            if calorie_goal is None or calorie_goal < 1000 or calorie_goal > 6000:
                await update.message.reply_text("Введите число 1000-6000 или напишите 'авто', чтобы рассчитать.")
                return ProfileState.CUSTOM_CALORIES
            draft["calorie_goal_manual"] = calorie_goal
        else:
            draft["calorie_goal_manual"] = None

        profile = self.ensure_profile(update)
        profile.weight = draft.get("weight", profile.weight)
        profile.height = draft.get("height", profile.height)
        profile.age = draft.get("age", profile.age)
        profile.activity = draft.get("activity", profile.activity)
        profile.city = draft.get("city", profile.city)
        profile.gender = draft.get("gender", profile.gender)
        profile.calorie_goal_manual = draft.get("calorie_goal_manual")

        temperature = self.weather.fetch_temperature(profile.city)
        if temperature is not None:
            profile.temperature = temperature
        self.storage.recalc_goals(profile)

        context.user_data.pop("profile_draft", None)
        context.user_data["profile_in_progress"] = False
        await update.message.reply_text(
            "Профиль обновлен.\n"
            f"Вода в день: {profile.water_goal:.0f} мл.\n"
            f"Калории в день: {profile.calorie_goal:.0f} ккал.",
            reply_markup=self.main_keyboard(),
        )
        return ConversationHandler.END

    #Вода
    async def log_water_entry(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        if self.require_no_profile(update, context):
            return ConversationHandler.END
        context.user_data.pop("food_context", None)
        if context.args:
            amount = self.parse_float(" ".join(context.args))
            if amount is None or amount <= 0:
                await update.message.reply_text(
                    "Укажите объем воды в мл, например: /log_water 300",
                    reply_markup=self.main_keyboard(),
                )
                return ConversationHandler.END
            profile = self.ensure_profile(update)
            profile.logged_water += amount
            water_left = max(profile.water_goal - profile.logged_water, 0)
            await update.message.reply_text(
                f"Записано {amount:.0f} мл. Осталось {water_left:.0f} мл до цели {profile.water_goal:.0f} мл.",
                reply_markup=self.main_keyboard(),
            )
            return ConversationHandler.END

        await update.message.reply_text(
            "Укажите объем воды в мл, например: /log_water 300 или введите число.",
            reply_markup=self.main_keyboard(),
        )
        return WaterState.AMOUNT

    async def log_water_amount(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        if self.is_button(update):
            await update.message.reply_text(
                "Сначала введите объем воды в мл или /cancel.",
                reply_markup=self.main_keyboard(),
            )
            return WaterState.AMOUNT
        amount = self.parse_float(update.message.text)
        if amount is None or amount <= 0:
            await update.message.reply_text(
                "Введите объем воды в мл или /cancel.",
                reply_markup=self.main_keyboard(),
            )
            return WaterState.AMOUNT

        profile = self.ensure_profile(update)
        profile.logged_water += amount
        water_left = max(profile.water_goal - profile.logged_water, 0)
        await update.message.reply_text(
            f"Записано {amount:.0f} мл. Осталось {water_left:.0f} мл до цели {profile.water_goal:.0f} мл.",
            reply_markup=self.main_keyboard(),
        )
        return ConversationHandler.END

    #Еда
    async def log_food_entry(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        if self.require_no_profile(update, context):
            return ConversationHandler.END
        if context.args:
            product_name = " ".join(context.args)
            return await self.search_food(update, context, product_name)
        await update.message.reply_text("Что вы съели? Напишите название продукта.", reply_markup=self.main_keyboard())
        return FoodState.NAME

    async def food_name_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        if self.is_button(update):
            await update.message.reply_text("Введите название продукта или /cancel.", reply_markup=self.main_keyboard())
            return FoodState.NAME
        product_name = update.message.text.strip()
        if not product_name or self.is_number(product_name):
            await update.message.reply_text("Введите название продукта (не число) или /cancel.", reply_markup=self.main_keyboard())
            return FoodState.NAME
        return await self.search_food(update, context, product_name)

    async def search_food(self, update: Update, context: ContextTypes.DEFAULT_TYPE, product_name: str) -> int:
        info = self.food.get_food_info(product_name)
        if not info or info.get("calories", 0) <= 0:
            await update.message.reply_text("Не нашел продукт. Попробуйте уточнить название.", reply_markup=self.main_keyboard())
            return FoodState.NAME
        context.user_data["food_context"] = info
        await update.message.reply_text(
            f"{info['name']} — {info['calories']:.0f} ккал на 100 г. Сколько грамм вы съели?",
            reply_markup=self.main_keyboard(),
        )
        return FoodState.GRAMS

    async def food_grams_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        if self.is_button(update):
            await update.message.reply_text("Сначала введите массу в граммах или /cancel.", reply_markup=self.main_keyboard())
            return FoodState.GRAMS
        grams = self.parse_float(update.message.text)
        if grams is None or grams <= 0:
            await update.message.reply_text("Введите массу в граммах или /cancel.", reply_markup=self.main_keyboard())
            return FoodState.GRAMS
        info = context.user_data.get("food_context")
        if not info:
            await update.message.reply_text("Начните заново с /log_food.")
            return ConversationHandler.END

        calories = info["calories"] * grams / 100
        profile = self.ensure_profile(update)
        profile.logged_calories += calories
        profile.food_log.append(FoodLogEntry(name=info["name"], grams=grams, calories=calories))
        await update.message.reply_text(
            f"Записано: {info['name']} — {calories:.0f} ккал ({grams:.0f} г).",
            reply_markup=self.main_keyboard(),
        )
        context.user_data.pop("food_context", None)
        return ConversationHandler.END

    #Тренировки
    async def log_workout_entry(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        if self.require_no_profile(update, context):
            return ConversationHandler.END
        args = context.args or []
        if len(args) >= 2:
            return await self.log_workout_direct(update, context, args)
        await update.message.reply_text(
            "Укажите тип тренировки. Выберите кнопку или напишите свой вариант.\n"
            "Доступные варианты: бег, ходьба, вело, йога, силовая, плавание.",
            reply_markup=self.workout_keyboard(),
        )
        return WorkoutState.TYPE

    async def log_workout_type(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        if self.is_button(update):
            await update.message.reply_text("Введите тип тренировки текстом или /cancel.", reply_markup=self.main_keyboard())
            return WorkoutState.TYPE
        workout_type = self.normalize_workout_type(update.message.text)
        context.user_data["workout_context"] = {"type": workout_type}
        await update.message.reply_text(
            "Укажите длительность в минутах:",
            reply_markup=self.main_keyboard(),
        )
        return WorkoutState.MINUTES

    async def log_workout_minutes(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        if self.is_button(update):
            await update.message.reply_text("Введите длительность в минутах или /cancel.", reply_markup=self.main_keyboard())
            return WorkoutState.MINUTES
        minutes = self.parse_float(update.message.text)
        if minutes is None or minutes <= 0:
            await update.message.reply_text("Укажите длительность числом, например 30.", reply_markup=self.main_keyboard())
            return WorkoutState.MINUTES
        workout_ctx = context.user_data.get("workout_context", {})
        workout_type = workout_ctx.get("type") or "тренировка"
        await self.log_workout_direct(update, context, [workout_type, str(minutes)])
        context.user_data.pop("workout_context", None)
        return ConversationHandler.END

    async def log_workout_direct(self, update: Update, context: ContextTypes.DEFAULT_TYPE, args: list[str]) -> int:
        *workout_parts, minutes_text = args
        workout_type_raw = " ".join(workout_parts) or "тренировка"
        workout_type = self.normalize_workout_type(workout_type_raw)
        minutes = self.parse_float(minutes_text)
        if minutes is None or minutes <= 0:
            await update.message.reply_text("Укажите длительность в минутах числом, например 30.", reply_markup=self.main_keyboard())
            return ConversationHandler.END

        profile = self.ensure_profile(update)
        calories, water_bonus = estimate_workout_calories(workout_type, minutes, profile.weight)
        profile.burned_calories += calories
        profile.workout_water_bonus += water_bonus
        profile.workout_log.append(
            WorkoutLogEntry(workout_type=workout_type, minutes=minutes, calories=calories, water_bonus=water_bonus)
        )
        self.storage.recalc_goals(profile)

        await update.message.reply_text(
            f"Тренировка '{workout_type}' {minutes:.0f} мин — {calories:.0f} ккал. "
            f"Дополнительно выпейте {water_bonus} мл воды. "
            f"Новая цель по воде: {profile.water_goal:.0f} мл.",
            reply_markup=self.main_keyboard(),
        )
        return ConversationHandler.END

    #Прогресс
    async def check_progress(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if self.require_no_profile(update, context):
            return
        profile = self.ensure_profile(update)
        temperature = self.weather.fetch_temperature(profile.city)
        if temperature is not None:
            profile.temperature = temperature
        self.storage.recalc_goals(profile)
        message = update.effective_message
        if not message:
            return
        await message.reply_text(format_progress(profile), reply_markup=self.main_keyboard())

    async def plot_progress(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if self.require_no_profile(update, context):
            return
        profile = self.ensure_profile(update)
        temperature = self.weather.fetch_temperature(profile.city)
        if temperature is not None:
            profile.temperature = temperature
        self.storage.recalc_goals(profile)
        img = self.plotter.build_plot(profile)
        message = update.effective_message
        if not message:
            return
        await message.reply_photo(
            photo=img,
            caption="Графики прогресса по воде и калориям.",
            reply_markup=self.main_keyboard(),
        )

    #Регистрация хэндлеров
    def register(self, app: Application) -> None:
        profile_conv = ConversationHandler(
            entry_points=[
                CommandHandler("set_profile", self.set_profile_start),
                MessageHandler(filters.TEXT & filters.Regex(f"^{self.BUTTON_PATTERNS['profile']}$"), self.set_profile_start),
            ],
            states={
                ProfileState.WEIGHT: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND & ~self.button_filter, self.set_weight),
                    CommandHandler("check_progress", self.check_progress),
                ],
                ProfileState.HEIGHT: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND & ~self.button_filter, self.set_height),
                    CommandHandler("check_progress", self.check_progress),
                ],
                ProfileState.AGE: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND & ~self.button_filter, self.set_age),
                    CommandHandler("check_progress", self.check_progress),
                ],
                ProfileState.ACTIVITY: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND & ~self.button_filter, self.set_activity),
                    CommandHandler("check_progress", self.check_progress),
                ],
                ProfileState.CITY: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND & ~self.button_filter, self.set_city),
                    CommandHandler("check_progress", self.check_progress),
                ],
                ProfileState.GENDER: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND & ~self.button_filter, self.set_gender),
                    CommandHandler("check_progress", self.check_progress),
                ],
                ProfileState.CUSTOM_CALORIES: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND & ~self.button_filter, self.finish_profile),
                    CommandHandler("check_progress", self.check_progress),
                ],
            },
            fallbacks=[CommandHandler("cancel", self.cancel)],
            allow_reentry=True,
        )

        food_conv = ConversationHandler(
            entry_points=[
                CommandHandler("log_food", self.log_food_entry),
                MessageHandler(filters.TEXT & filters.Regex(f"^{self.BUTTON_PATTERNS['food']}$"), self.log_food_entry),
            ],
            states={
                FoodState.NAME: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND & ~self.button_filter, self.food_name_handler),
                    CommandHandler("check_progress", self.check_progress),
                    MessageHandler(filters.COMMAND, self.cancel),
                ],
                FoodState.GRAMS: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND & ~self.button_filter, self.food_grams_handler),
                    CommandHandler("check_progress", self.check_progress),
                    MessageHandler(filters.COMMAND, self.cancel),
                ],
            },
            fallbacks=[CommandHandler("cancel", self.cancel)],
            allow_reentry=True,
        )

        water_conv = ConversationHandler(
            entry_points=[
                CommandHandler("log_water", self.log_water_entry),
                MessageHandler(filters.TEXT & filters.Regex(f"^{self.BUTTON_PATTERNS['water']}$"), self.log_water_entry),
            ],
            states={
                WaterState.AMOUNT: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND & ~self.button_filter, self.log_water_amount),
                    CommandHandler("check_progress", self.check_progress),
                    MessageHandler(filters.COMMAND, self.cancel),
                ],
            },
            fallbacks=[CommandHandler("cancel", self.cancel)],
            allow_reentry=True,
        )

        workout_conv = ConversationHandler(
            entry_points=[
                CommandHandler("log_workout", self.log_workout_entry),
                MessageHandler(filters.TEXT & filters.Regex(f"^{self.BUTTON_PATTERNS['workout']}$"), self.log_workout_entry),
            ],
            states={
                WorkoutState.TYPE: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND & ~self.button_filter, self.log_workout_type),
                    CommandHandler("check_progress", self.check_progress),
                    MessageHandler(filters.COMMAND, self.cancel),
                ],
                WorkoutState.MINUTES: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND & ~self.button_filter, self.log_workout_minutes),
                    CommandHandler("check_progress", self.check_progress),
                    MessageHandler(filters.COMMAND, self.cancel),
                ],
            },
            fallbacks=[CommandHandler("cancel", self.cancel)],
            allow_reentry=True,
        )

        app.add_handler(CommandHandler("start", self.start))
        app.add_handler(CommandHandler("help", self.help))
        app.add_handler(profile_conv)
        app.add_handler(food_conv)
        app.add_handler(water_conv)
        app.add_handler(workout_conv)
        app.add_handler(CommandHandler("check_progress", self.check_progress))
        app.add_handler(CommandHandler("plot_progress", self.plot_progress))
        app.add_handler(CommandHandler("cancel", self.cancel))

        #Поддержка кнопок (текст без слэша) для простых команд
        app.add_handler(MessageHandler(filters.TEXT & filters.Regex(f"^{self.BUTTON_PATTERNS['progress']}$"), self.check_progress))
        app.add_handler(MessageHandler(filters.TEXT & filters.Regex(f"^{self.BUTTON_PATTERNS['plots']}$"), self.plot_progress))
