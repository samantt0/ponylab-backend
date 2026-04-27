import csv
import os
import json
from pathlib import Path
import trace
from typing import Any, Optional
from ai.analyze import AnalysisResult
import data
from data.models import Timer, TimerData, TableItem
from data.yieldizer import set_parameter, send_timers
import traceback

PLANT_DATA_DIR = Path(__file__).parent.parent / "data" / "plants"


class PlantRules:
    def __init__(self, plant_type: str = "tomato"):
        self.plant_type = plant_type
        self._table: dict = self._load_table(plant_type)

    def _load_table(self, plant_type: str) -> dict:
        path = PLANT_DATA_DIR / f"{plant_type}.csv"
        if not path.exists():
            print(f"[PlantRules] CSV not found: {path}, using defaults")
            return self._defaults()

        rules = {}
        with open(path, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                param = row["param"]
                rules[param] = {
                    "value": float(row["value"]),
                    "min":   float(row["min"]),
                    "max":   float(row["max"]),
                }
        print(f"[PlantRules] Loaded params: {list(rules.keys())}")
        return rules

    def _defaults(self) -> dict:
        return {
            "temp":           {"value": 24, "min": 20, "max": 28},
            "humidity":       {"value": 60, "min": 50, "max": 70},
            "ec":             {"value": 1.8, "min": 1.2, "max": 2.5},
            "ph":             {"value": 6.2, "min": 5.8, "max": 6.5},
            "light_duration": {"value": 16, "min": 12, "max": 18},
        }

    def get_default(self, param: str) -> float:
        """Дефолтное значение параметра из CSV."""
        return self._table.get(param, self._defaults().get(param, {})).get("value", 0)

    def get_bounds(self, param: str) -> tuple[float, float]:
        """Возвращает (min, max) для параметра."""
        entry = self._table.get(param, self._defaults().get(param, {"min": 0, "max": 9999}))
        return entry["min"], entry["max"]

    def adjust_ai_params(self, ai_params: dict) -> dict:
        """
        Зажимает каждый параметр AI в допустимые границы из CSV.
        stage больше не используется — диапазоны единые.
        """
        adjusted = {}
        params_to_clamp = ["temp", "humidity", "ec", "ph", "light_duration"]

        for key in params_to_clamp:
            lo, hi = self.get_bounds(key)
            default = self.get_default(key)
            raw = ai_params.get(key, default)
            clamped = self._clamp(raw, lo, hi)
            adjusted[key] = clamped
            if raw != clamped:
                print(f"[PlantRules] '{key}' clamped: {raw} -> {clamped} (bounds: {lo} – {hi})")

        return adjusted

    @staticmethod
    def _clamp(val: float, min_val: float, max_val: float) -> float:
        return max(min_val, min(max_val, float(val)))


# Маппинг наших параметров на namespace/key в Yieldizer REST API
# Структура: param_name -> (namespace, key)
YIELDIZER_PARAM_MAP = {
    "temp": ("climate", "temp_target"),
    "humidity": ("climate", "humidity_target"),
    "ec": ("nsolution", "ec_target"),
    "ph": ("nsolution", "ph_target"),
}


class Controller:
    """
    Центральный логический модуль.

    Получает результат анализа AI, корректирует рекомендации
    по таблице допустимых значений и отправляет их в теплицу.
    """

    def __init__(self, plant_type: str = "tomato"):
        self.rules = PlantRules(plant_type)
        self._last_params: dict[Any, Any] | None = None
        self._last_stage: str | None = None

    async def process(self, ai_result: AnalysisResult, current_sensors: dict) -> dict:
        stage = ai_result.growth_stage or "default"
        ai_params = ai_result.recommended_params
    
        print(f"[Controller] Stage: '{stage}'")
        print(f"[Controller] AI recommended: {ai_params}")
    
        # stage теперь только для логирования, clamp по единым границам CSV
        adjusted = self.rules.adjust_ai_params(ai_params)
        print(f"[Controller] Adjusted params: {adjusted}")
    
        await self._apply_params(adjusted)
    
        self._last_params = adjusted
        self._last_stage = stage
        return adjusted

    async def _apply_params(self, params: dict) -> None:
        try:
            raw_duration = params.get("light_duration", 16)
            # clamp на случай прямого вызова минуя adjust_ai_params
            light_hours = self._clamp_light(raw_duration)
            light_seconds = int(light_hours) * 3600
    
            _ = await send_timers(
                [
                    Timer(
                        m=3,
                        data=TimerData(
                            dbegin=0,
                            dskip=0,
                            table=[TableItem(t1=25200, t2=light_seconds)],
                        ),
                    )
                ]
            )
        except Exception:
            traceback.print_exc()
    
        for param_name, value in params.items():
            if param_name not in YIELDIZER_PARAM_MAP:
                # light_duration не в MAP — это нормально, уже обработан выше
                if param_name != "light_duration":
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
    
    @staticmethod
    def _clamp_light(val: float) -> float:
        """light_duration: от 12 до 18 часов."""
        return max(12.0, min(18.0, float(val)))

    def get_last_params(self) -> Optional[dict]:
        return self._last_params

    def get_last_stage(self) -> Optional[str]:
        return self._last_stage
