import pathlib
import sys
import unittest


PLUGIN_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN_ROOT))

from flowflox_actions import (  # noqa: E402
    FlowFloxActionInputError,
    action_failure,
    action_result,
    parse_action_arguments,
)


class FlowFloxActionContractTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
