"""
Простые тесты для logic/control.py
Запуск: python -m pytest backend/logic/test_control.py -v
"""
import pytest
from logic.control import PlantRules


class TestPlantRules:
    def setup_method(self):
        self.rules = PlantRules("tomato")

    def test_loads_csv(self):
        """CSV загружается и содержит ожидаемые стадии"""
        assert "seedling" in self.rules._table
        assert "vegetative" in self.rules._table
        assert "default" in self.rules._table

    def test_get_bounds_known_stage(self):
        bounds = self.rules.get_bounds("seedling")
        assert bounds["temp_min"] == 22
        assert bounds["temp_max"] == 26

    def test_get_bounds_unknown_stage_falls_back_to_default(self):
        """Неизвестная стадия → default границы"""
        bounds = self.rules.get_bounds("unknown_stage_xyz")
        default = self.rules._table.get("default", self.rules._defaults()["default"])
        assert bounds == default

    def test_clamp_within_bounds(self):
        """Значение в пределах → не меняется"""
        params = {"temp": 24, "humidity": 75, "ec": 1.1, "ph": 6.2}
        result = self.rules.adjust_ai_params(params, "seedling")
        assert result["temp"] == 24
        assert result["humidity"] == 75

    def test_clamp_above_max(self):
        """Значение выше максимума → зажимается до max"""
        params = {"temp": 99, "humidity": 60, "ec": 1.1, "ph": 6.2}
        result = self.rules.adjust_ai_params(params, "seedling")
        assert result["temp"] == 26  # seedling temp_max = 26

    def test_clamp_below_min(self):
        """Значение ниже минимума → зажимается до min"""
        params = {"temp": 1, "humidity": 60, "ec": 1.1, "ph": 6.2}
        result = self.rules.adjust_ai_params(params, "seedling")
        assert result["temp"] == 22  # seedling temp_min = 22

    def test_adjust_does_not_mutate_input(self):
        """adjust_ai_params не меняет входной словарь"""
        params = {"temp": 99, "humidity": 60, "ec": 1.1, "ph": 6.2}
        original = params.copy()
        self.rules.adjust_ai_params(params, "seedling")
        assert params == original

    def test_missing_param_uses_default(self):
        """Если AI не вернул параметр → используется дефолт"""
        result = self.rules.adjust_ai_params({}, "seedling")
        assert "temp" in result
        assert "humidity" in result
        assert "ec" in result
        assert "ph" in result
