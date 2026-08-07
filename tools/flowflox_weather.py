"""Safe, read-only Open-Meteo weather helpers for the Dify toolbox."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class WeatherInputError(ValueError):
    """Raised when an Agent attempts a weather lookup without a usable place."""


WEATHER_CODE_LABELS: dict[int, str] = {
    0: "clear sky",
    1: "mainly clear",
    2: "partly cloudy",
    3: "overcast",
    45: "fog",
    48: "rime fog",
    51: "light drizzle",
    53: "moderate drizzle",
    55: "heavy drizzle",
    61: "slight rain",
    63: "moderate rain",
    65: "heavy rain",
    71: "slight snow",
    73: "moderate snow",
    75: "heavy snow",
    80: "rain showers",
    81: "moderate rain showers",
    82: "violent rain showers",
    95: "thunderstorm",
    96: "thunderstorm with slight hail",
    99: "thunderstorm with heavy hail",
}


def normalize_location(value: Any) -> str:
    """Keep the free-form place parameter compact and suitable for geocoding."""
    location = " ".join(str(value or "").split()).strip()
    if not location:
        raise WeatherInputError("A city, region, or location is required for a weather lookup.")
    if len(location) > 160:
        raise WeatherInputError("The weather location is too long.")
    return location


def weather_label(code: Any) -> str:
    """Translate the WMO code so the planner receives usable weather context."""
    try:
        normalized = int(code)
    except (TypeError, ValueError):
        return "unknown conditions"
    return WEATHER_CODE_LABELS.get(normalized, "unknown conditions")


def weather_result(location: Mapping[str, Any], forecast: Mapping[str, Any]) -> dict[str, Any]:
    """Return the small, structured tool result that the Agent may reason over."""
    current = forecast.get("current")
    if not isinstance(current, Mapping):
        raise WeatherInputError("The weather service did not return current conditions.")

    code = current.get("weather_code")
    return {
        "ok": True,
        "source": "Open-Meteo",
        "location": {
            "name": str(location.get("name") or ""),
            "region": str(location.get("admin1") or ""),
            "country": str(location.get("country") or ""),
            "latitude": location.get("latitude"),
            "longitude": location.get("longitude"),
        },
        "observed_at": str(current.get("time") or ""),
        "timezone": str(forecast.get("timezone") or ""),
        "conditions": {
            "summary": weather_label(code),
            "weather_code": code,
            "temperature_c": current.get("temperature_2m"),
            "apparent_temperature_c": current.get("apparent_temperature"),
            "relative_humidity_percent": current.get("relative_humidity_2m"),
            "precipitation_mm": current.get("precipitation"),
            "wind_speed_kmh": current.get("wind_speed_10m"),
        },
    }
