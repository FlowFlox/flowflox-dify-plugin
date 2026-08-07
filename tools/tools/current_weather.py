"""Read-only weather capability available to an app's Dify Agent toolbox."""

from __future__ import annotations

import json
from collections.abc import Generator
from typing import Any

import requests
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from flowflox_weather import WeatherInputError, normalize_location, weather_result


GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
REQUEST_TIMEOUT_SECONDS = 12
CURRENT_FIELDS = (
    "temperature_2m,apparent_temperature,relative_humidity_2m,"
    "precipitation,weather_code,wind_speed_10m"
)


class CurrentWeatherTool(Tool):
    """Let an Agent obtain current weather once it has a location to use."""

    def _emit(self, payload: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        # The JSON message keeps the result structured.  The text message is
        # non-user-facing context for the Agent's next planning turn.
        yield self.create_json_message(payload)
        yield self.create_text_message(json.dumps(payload, ensure_ascii=False, sort_keys=True))

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        try:
            query = normalize_location(tool_parameters.get("location"))
            location = self._geocode(query)
            forecast = self._forecast(location)
            payload = weather_result(location, forecast)
        except WeatherInputError as error:
            payload = {"ok": False, "error": str(error)}
        except requests.RequestException:
            payload = {"ok": False, "error": "The weather service is temporarily unavailable."}
        except (TypeError, ValueError):
            payload = {"ok": False, "error": "The weather service returned an invalid response."}

        yield from self._emit(payload)

    @staticmethod
    def _geocode(query: str) -> dict[str, Any]:
        response = requests.get(
            GEOCODING_URL,
            params={"name": query, "count": 1, "language": "en", "format": "json"},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
        matches = payload.get("results") if isinstance(payload, dict) else None
        if not isinstance(matches, list) or not matches or not isinstance(matches[0], dict):
            raise WeatherInputError("I could not find that location. Ask the user for a city and country or region.")
        return matches[0]

    @staticmethod
    def _forecast(location: dict[str, Any]) -> dict[str, Any]:
        latitude = location.get("latitude")
        longitude = location.get("longitude")
        if not isinstance(latitude, (int, float)) or not isinstance(longitude, (int, float)):
            raise WeatherInputError("The weather service returned an unusable location.")
        response = requests.get(
            FORECAST_URL,
            params={
                "latitude": latitude,
                "longitude": longitude,
                "current": CURRENT_FIELDS,
                "timezone": "auto",
            },
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise WeatherInputError("The weather service returned an invalid response.")
        return payload
