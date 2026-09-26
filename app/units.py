"""Unit conversion helpers — one canonical place for every measurement assumption.

Verdant stores values in the unit they were recorded in and converts at read
time. Anything that sums or compares measurements MUST go through here so a
grams entry can never silently corrupt an ounces total.
"""

from typing import Optional

# Conversion factors to ounces (avoirdupois).
_TO_OZ: dict[str, float] = {
    "oz": 1.0,
    "ounce": 1.0,
    "ounces": 1.0,
    "g": 0.035274,
    "gram": 0.035274,
    "grams": 0.035274,
    "lb": 16.0,
    "lbs": 16.0,
    "pound": 16.0,
    "pounds": 16.0,
    "kg": 35.274,
    "kilo": 35.274,
    "kilos": 35.274,
    "kilogram": 35.274,
    "kilograms": 35.274,
}

# Canonical display unit for each accepted spelling.
_CANONICAL: dict[str, str] = {
    "oz": "oz", "ounce": "oz", "ounces": "oz",
    "g": "g", "gram": "g", "grams": "g",
    "lb": "lb", "lbs": "lb", "pound": "lb", "pounds": "lb",
    "kg": "kg", "kilo": "kg", "kilos": "kg", "kilogram": "kg", "kilograms": "kg",
}

WEIGHT_UNITS = frozenset(_CANONICAL.keys())


def is_weight_unit(unit: Optional[str]) -> bool:
    """True if the unit string names a weight (as opposed to a count like 'fruit')."""
    return bool(unit) and unit.strip().lower() in WEIGHT_UNITS


def normalize_weight_unit(unit: Optional[str], default: str = "oz") -> str:
    """Canonicalize a weight unit spelling ('Ounces' -> 'oz'); unknown -> default."""
    if not unit:
        return default
    return _CANONICAL.get(unit.strip().lower(), default)


def to_oz(value: Optional[float], unit: Optional[str]) -> Optional[float]:
    """Convert a weight to ounces. Returns None for missing values or unknown units."""
    if value is None:
        return None
    factor = _TO_OZ.get((unit or "").strip().lower())
    if factor is None:
        return None
    return value * factor


# Volume conversions to gallons (for watering amounts).
_TO_GAL: dict[str, float] = {
    "gal": 1.0,
    "gallon": 1.0,
    "gallons": 1.0,
    "l": 0.264172,
    "liter": 0.264172,
    "liters": 0.264172,
    "litre": 0.264172,
    "litres": 0.264172,
    "qt": 0.25,
    "quart": 0.25,
    "quarts": 0.25,
    "ml": 0.000264172,
    "milliliter": 0.000264172,
    "milliliters": 0.000264172,
    "cup": 0.0625,
    "cups": 0.0625,
    "tbsp": 0.00390625,
    "tablespoon": 0.00390625,
    "tsp": 0.00130208,
    "teaspoon": 0.00130208,
}

VOLUME_UNITS = frozenset(_TO_GAL.keys())


def to_gal(value: Optional[float], unit: Optional[str]) -> Optional[float]:
    """Convert a volume to gallons. Returns None for missing values or unknown units."""
    if value is None:
        return None
    factor = _TO_GAL.get((unit or "").strip().lower())
    if factor is None:
        return None
    return value * factor


def c_to_f(celsius: float) -> float:
    return celsius * 9.0 / 5.0 + 32.0
