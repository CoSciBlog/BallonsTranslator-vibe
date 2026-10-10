import threading
import unittest

from ballontranslator.ui.module_manager import _run_translation_attempts
from ballontranslator.utils.config import ModuleConfig, TranslationFailurePolicy


class TranslationFailurePolicyTest(unittest.TestCase):
    def test_retry_runs_one_additional_attempt(self) -> None:
        attempts = []

        def translate() -> bool:
            attempts.append(None)
            return len(attempts) == 2

        self.assertTrue(_run_translation_attempts(
            translate,
            TranslationFailurePolicy.RETRY,
            threading.Event(),
        ))
        self.assertEqual(len(attempts), 2)

    def test_skip_does_not_retry(self) -> None:
        attempts = []
        self.assertFalse(_run_translation_attempts(
            lambda: attempts.append(None) is not None,
            TranslationFailurePolicy.SKIP,
            threading.Event(),
        ))
        self.assertEqual(len(attempts), 1)

    def test_stop_event_prevents_retry(self) -> None:
        event = threading.Event()
        attempts = []

        def translate() -> bool:
            attempts.append(None)
            event.set()
            return False

        self.assertFalse(_run_translation_attempts(
            translate,
            TranslationFailurePolicy.RETRY,
            event,
        ))
        self.assertEqual(len(attempts), 1)

    def test_invalid_saved_policy_falls_back_to_skip(self) -> None:
        config = ModuleConfig(translation_failure_policy='unknown')
        self.assertEqual(
            config.translation_failure_policy,
            TranslationFailurePolicy.SKIP,
        )


if __name__ == '__main__':
    unittest.main()
