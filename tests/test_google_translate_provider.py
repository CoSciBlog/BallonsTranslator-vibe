import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modules.translators.trans_google import GoogleTranslateProviderPython


class GoogleTranslateProviderTest(unittest.TestCase):
    def test_text_endpoint_joins_segments_and_uses_auto_detection(self):
        provider = GoogleTranslateProviderPython()
        response = Mock(status_code=200)
        response.json.return_value = [
            [
                ["Because people call me ", "source", None, None],
                ["a genius, I can't win any battles.", "source", None, None],
            ],
            None,
            "zh-TW",
        ]
        provider.requests_session.get = Mock(return_value=response)

        result = provider.translate(["source"], target_language="en", source_language="auto")

        self.assertEqual(
            result["translations"],
            ["Because people call me a genius, I can't win any battles."],
        )
        params = provider.requests_session.get.call_args.kwargs["params"]
        self.assertEqual(params["sl"], "auto")
        self.assertEqual(params["tl"], "en")
        self.assertEqual(params["client"], "gtx")


if __name__ == "__main__":
    unittest.main()
