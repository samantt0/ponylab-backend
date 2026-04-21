import csv
import os
import json
from pathlib import Path
from typing import Optional
from data.yieldizer import set_parameter


PLANT_DATA_DIR = Path(__file__).parent.parent.parent / "data" / "plants"


class PlantRules:
    def __init__(self, plant_type: str = "tomato"):
        self.plant_type = plant_type
        self._table: dict = self._load_table(plant_type)

    def _load_table(self, plant_type: str) -> dict:
        path = PLANT_DATA_DIR / f"{plant_type}.csv"
        if not path.exists():
            return self._defaults()

        rules = {}
        with open(path) as f:
            reader = csv.DictReader(f)
            for row in reader:
                stage = row.get("stage", "default")
                rules[stage] = {
                    "temp_min": float(row.get("temp_min", 20)),
                    "temp_max": float(row.get("temp_max", 28)),
                    "humidity_min": float(row.get("humidity_min", 50)),
                    "humidity_max": float(row.get("humidity_max", 70)),
                    "ec_min": float(row.get("ec_min", 1.2)),
                    "ec_max": float(row.get("ec_max", 2.5)),
                    "ph_min": float(row.get("ph_min", 5.8)),
                    "ph_max": float(row.get("ph_max", 6.5)),
                }
        return rules

    def _defaults(self) -> dict:
        return {
            "default": {
                "temp_min": 20,
                "temp_max": 28,
                "humidity_min": 50,
                "humidity_max": 70,
                "ec_min": 1.2,
                "ec_max": 2.5,
                "ph_min": 5.8,
                "ph_max": 6.5,
            }
        }

    def get_bounds(self, stage: str = "default") -> dict:
        return self._table.get(
            stage, self._table.get("default", self._defaults()["default"])
        )

    def adjust_ai_params(self, ai_params: dict, stage: str = "default") -> dict:
        bounds = self.get_bounds(stage)

        adjusted = ai_params.copy()
        adjusted["temp"] = self._clamp(
            ai_params.get("temp", 25), bounds["temp_min"], bounds["temp_max"]
        )
        adjusted["humidity"] = self._clamp(
            ai_params.get("humidity", 60),
            bounds["humidity_min"],
            bounds["humidity_max"],
        )
        adjusted["ec"] = self._clamp(
            ai_params.get("ec", 1.8), bounds["ec_min"], bounds["ec_max"]
        )
        adjusted["ph"] = self._clamp(
            ai_params.get("ph", 6.0), bounds["ph_min"], bounds["ph_max"]
        )

        return adjusted

    def _clamp(self, val: float, min_val: float, max_val: float) -> float:
        return max(min_val, min(max_val, val))


# Маппинг наших параметров на namespace/key в Yieldizer REST API
# Структура: param_name -> (namespace, key)
YIELDIZER_PARAM_MAP = {
    "temp":     ("climate", "temp_target"),
    "humidity": ("climate", "humidity_target"),
    "ec":       ("nsolution", "ec_target"),
    "ph":       ("nsolution", "ph_target"),
}


class Controller:
    """
    Центральный логический модуль.

    Получает результат анализа AI, корректирует рекомендации
    по таблице допустимых значений и отправляет их в теплицу.
    """

    def __init__(self, plant_type: str = "tomato"):
        self.rules = PlantRules(plant_type)
        self._last_params: Optional[dict] = None
        self._last_stage: Optional[str] = None

    async def process(self, ai_result, current_sensors: dict) -> dict:
        """
        Основной метод обработки:
        1. Берёт стадию роста и рекомендации от AI
        2. Корректирует по таблице границ
        3. Отправляет скорректированные параметры в теплицу
        4. Возвращает итоговые параметры

        Args:
            ai_result: AnalysisResult из ai.analyze
            current_sensors: текущие показания датчиков (для логирования)
        """
        stage = ai_result.growth_stage or "default"
        ai_params = ai_result.recommended_params

        print(f"[Controller] Stage: '{stage}'")
        print(f"[Controller] AI recommended: {ai_params}")

        # Корректируем параметры по таблице
        adjusted = self.rules.adjust_ai_params(ai_params, stage)
        print(f"[Controller] Adjusted params: {adjusted}")

        # Отправляем в теплицу
        await self._apply_params(adjusted)

        self._last_params = adjusted
        self._last_stage = stage
        return adjusted

    async def _apply_params(self, params: dict) -> None:
        """
        Отправляет каждый параметр в теплицу через DATA модуль.
        Ошибки не останавливают обработку остальных параметров.
        """
        for param_name, value in params.items():
            if param_name not in YIELDIZER_PARAM_MAP:
                print(f"[Controller] Unknown param '{param_name}', skipping")
                continue

            ns, key = YIELDIZER_PARAM_MAP[param_name]
            try:
                success = await set_parameter(ns, key, value)
                if success:
                    print(f"[Controller] Set {ns}/{key} = {value} ✓")
                else:
                    print(f"[Controller] Failed to set {ns}/{key} = {value}")
            except Exception as e:
                print(f"[Controller] Error setting {ns}/{key}: {e}")

    def get_last_params(self) -> Optional[dict]:
        return self._last_params

    def get_last_stage(self) -> Optional[str]:
        return self._last_stage
