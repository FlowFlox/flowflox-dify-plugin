import pathlib
import sys
import unittest


PLUGIN_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN_ROOT))

from flowflox_actions import (  # noqa: E402
    FlowFloxActionInputError,
    action_context_text,
    action_failure,
    action_result,
    parse_action_arguments,
)
from flowflox_app_connection import (  # noqa: E402
    APP_CONTEXT_PARAMETER,
    FlowFloxAppConnection,
    app_connection_storage_key,
    load_app_connection,
    require_dify_app_id,
    save_app_connection,
)
from flowflox_errors import FlowFloxMcpError  # noqa: E402
from flowflox_weather import (  # noqa: E402
    WeatherInputError,
    normalize_location,
    weather_label,
    weather_result,
)


class FlowFloxActionContractTests(unittest.TestCase):
    def test_tool_labels_identify_the_mcp_contract(self) -> None:
        catalog = (PLUGIN_ROOT / "tools" / "discover_approved_apis.yaml").read_text()
        gateway = (PLUGIN_ROOT / "tools" / "call_approved_api.yaml").read_text()

        self.assertIn("FlowFlox MCP tool catalog", catalog)
        self.assertIn("FlowFlox MCP action gateway", gateway)

    def test_provider_has_no_global_flowflox_key_authorization(self) -> None:
        provider = (PLUGIN_ROOT / "provider" / "flowflox-tools.yaml").read_text()
        setup_tool = (PLUGIN_ROOT / "tools" / "connect_app.yaml").read_text()
        client = (PLUGIN_ROOT / "flowflox_mcp.py").read_text()
        self.assertNotIn("credentials_schema", provider)
        self.assertNotIn("flowflox_service_key", provider)
        self.assertIn("tools/connect_app.yaml", provider)
        self.assertIn("tools/conditional_api_action.yaml", provider)
        self.assertIn("flowflox_authorization_code", setup_tool)
        self.assertIn("ffx_dac_", setup_tool)
        self.assertNotIn("ffx_svc_", setup_tool)
        self.assertIn("/v1/dify/app-connections/exchange", client)
        self.assertNotIn("APP_CONNECTION_URL", client)

    def test_conditional_action_is_explicitly_branch_first(self) -> None:
        definition = (PLUGIN_ROOT / "tools" / "conditional_api_action.yaml").read_text()
        self.assertIn("only when a workflow branch reaches this node", definition)
        self.assertIn("not a default action", definition)
        self.assertIn("another FlowFlox conditional API action", definition)

    def test_app_connection_storage_is_namespaced_to_one_dify_app(self) -> None:
        first = app_connection_storage_key("51611764-abe4-49bf-b4c4-707205e89be5")
        second = app_connection_storage_key("f80566c1-513d-4041-8c12-03f912b4e2db")
        self.assertNotEqual(first, second)
        self.assertIn("51611764-abe4-49bf-b4c4-707205e89be5", first)

    def test_agent_tool_uses_dify_system_app_context_when_session_context_is_missing(self) -> None:
        """Dify's stock Agent tool invocation omits session.app_id."""

        class Session:
            app_id = None

        self.assertEqual(
            require_dify_app_id(
                Session(),
                {APP_CONTEXT_PARAMETER: "51611764-abe4-49bf-b4c4-707205e89be5"},
            ),
            "51611764-abe4-49bf-b4c4-707205e89be5",
        )

    def test_host_app_context_wins_when_dify_provides_it(self) -> None:
        class Session:
            app_id = "51611764-abe4-49bf-b4c4-707205e89be5"

        self.assertEqual(
            require_dify_app_id(
                Session(),
                {APP_CONTEXT_PARAMETER: "f80566c1-513d-4041-8c12-03f912b4e2db"},
            ),
            "51611764-abe4-49bf-b4c4-707205e89be5",
        )

    def test_agent_tool_rejects_missing_or_invalid_app_context(self) -> None:
        class Session:
            app_id = None

        with self.assertRaises(FlowFloxMcpError):
            require_dify_app_id(Session(), {})
        with self.assertRaises(FlowFloxMcpError):
            require_dify_app_id(Session(), {APP_CONTEXT_PARAMETER: "not-an-app-id"})

    def test_app_connection_storage_never_contains_a_setup_or_service_key(self) -> None:
        class Storage:
            def __init__(self) -> None:
                self.values: dict[str, bytes] = {}

            def set(self, key: str, value: bytes) -> None:
                self.values[key] = value

        class Session:
            app_id = "51611764-abe4-49bf-b4c4-707205e89be5"
            storage = Storage()

        session = Session()
        save_app_connection(
            session,
            FlowFloxAppConnection(
                id="connection_123",
                app_id=session.app_id,
                runtime_token="ffx_app_only_this_dify_app",
            ),
        )
        stored = next(iter(session.storage.values.values())).decode("utf-8")
        self.assertIn("ffx_app_", stored)
        self.assertNotIn("ffx_svc_", stored)
        self.assertNotIn("ffx_dac_", stored)

    def test_agent_loads_only_the_capability_for_its_system_bound_app(self) -> None:
        class Storage:
            def __init__(self) -> None:
                self.values: dict[str, bytes] = {}

            def set(self, key: str, value: bytes) -> None:
                self.values[key] = value

            def get(self, key: str) -> bytes:
                return self.values[key]

        class DirectSession:
            app_id = "51611764-abe4-49bf-b4c4-707205e89be5"
            storage = Storage()

        direct_session = DirectSession()
        save_app_connection(
            direct_session,
            FlowFloxAppConnection(
                id="connection_123",
                app_id=direct_session.app_id,
                runtime_token="ffx_app_only_this_dify_app",
            ),
        )

        class AgentSession:
            app_id = None
            storage = direct_session.storage

        connection = load_app_connection(
            AgentSession(),
            {APP_CONTEXT_PARAMETER: direct_session.app_id},
        )
        self.assertEqual(connection.app_id, direct_session.app_id)
        self.assertTrue(connection.runtime_token.startswith("ffx_app_"))

    def test_accepts_an_upstream_object_without_stringifying_it(self) -> None:
        self.assertEqual(parse_action_arguments({"order_id": "order_123"}), {"order_id": "order_123"})

    def test_rejects_non_object_action_input(self) -> None:
        with self.assertRaises(FlowFloxActionInputError):
            parse_action_arguments("[\"not-an-object\"]")

    def test_preserves_structured_output_for_a_later_action(self) -> None:
        output = action_result(
            "flowflox_test_hello_world",
            {
                "content": [{"type": "text", "text": '{"message":"Hello"}'}],
                "structuredContent": {"message": "Hello"},
            },
            title="Hello World",
        )
        self.assertTrue(output["ok"])
        self.assertEqual(output["action"]["title"], "Hello World")
        self.assertEqual(output["data"], {"message": "Hello"})
        self.assertIsNone(output["error"])

    def test_keeps_expected_failures_in_the_action_contract(self) -> None:
        output = action_failure("flowflox_test_hello_world", "Not permitted")
        self.assertFalse(output["ok"])
        self.assertEqual(output["operation"], "flowflox_test_hello_world")
        self.assertEqual(output["error"], "Not permitted")

    def test_serializes_the_safe_envelope_for_a_downstream_llm(self) -> None:
        output = action_result(
            "flowflox_test_hello_world",
            {"structuredContent": {"message": "Hello"}},
        )
        context = action_context_text(output)
        self.assertIn('"operation": "flowflox_test_hello_world"', context)
        self.assertIn('"message": "Hello"', context)

    def test_weather_location_requires_a_real_place(self) -> None:
        with self.assertRaises(WeatherInputError):
            normalize_location("   ")
        self.assertEqual(normalize_location("  Edmonton,   Alberta "), "Edmonton, Alberta")

    def test_weather_result_is_small_and_structured_for_the_agent(self) -> None:
        output = weather_result(
            {
                "name": "Edmonton",
                "admin1": "Alberta",
                "country": "Canada",
                "latitude": 53.5461,
                "longitude": -113.4938,
            },
            {
                "timezone": "America/Edmonton",
                "current": {
                    "time": "2026-08-07T12:00",
                    "weather_code": 2,
                    "temperature_2m": 19.4,
                    "apparent_temperature": 18.8,
                    "relative_humidity_2m": 42,
                    "precipitation": 0,
                    "wind_speed_10m": 18.2,
                },
            },
        )
        self.assertTrue(output["ok"])
        self.assertEqual(output["location"]["name"], "Edmonton")
        self.assertEqual(output["conditions"]["summary"], "partly cloudy")
        self.assertEqual(weather_label(999), "unknown conditions")


if __name__ == "__main__":
    unittest.main()
