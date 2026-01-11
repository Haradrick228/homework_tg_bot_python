from io import BytesIO

import matplotlib.pyplot as plt

from app.models import UserProfile


class ProgressPlotter:
    # Строит графики прогресса по воде и калориям.

    def build_plot(self, profile: UserProfile) -> BytesIO:
        water_goal = max(profile.water_goal, 1)
        calorie_goal = max(profile.calorie_goal, 1)
        water = profile.logged_water
        calories_in = profile.logged_calories
        calories_out = profile.burned_calories

        fig, axes = plt.subplots(1, 2, figsize=(10, 4))
        fig.suptitle("Прогресс дня", fontsize=12)

        axes[0].bar(["Выпито", "Цель"], [water, water_goal], color=["#4ba3fa", "#9ecdfc"])
        axes[0].set_ylim(0, max(water, water_goal) * 1.2 + 1)
        axes[0].set_title("Вода (мл)")
        axes[0].grid(axis="y", alpha=0.2)

        axes[1].bar(["Потреблено", "Сожжено", "Цель"], [calories_in, calories_out, calorie_goal], color=["#f0a202", "#f18805", "#f7c873"])
        axes[1].set_ylim(0, max(calories_in, calorie_goal) * 1.2 + 1)
        axes[1].set_title("Калории (ккал)")
        axes[1].grid(axis="y", alpha=0.2)

        for ax in axes:
            for spine in ["top", "right"]:
                ax.spines[spine].set_visible(False)

        buf = BytesIO()
        plt.tight_layout()
        plt.savefig(buf, format="png")
        plt.close(fig)
        buf.seek(0)
        return buf
