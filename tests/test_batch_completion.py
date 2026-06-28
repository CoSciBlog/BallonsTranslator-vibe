import os.path as osp
import sys
import unittest

APP_ROOT = osp.dirname(osp.dirname(osp.abspath(__file__)))
sys.path.append(APP_ROOT)

from utils.batch_completion import (
    COMPLETION_ACTION_CUSTOM,
    COMPLETION_ACTION_HIBERNATE,
    COMPLETION_ACTION_RESTART,
    COMPLETION_ACTION_SHUTDOWN,
    COMPLETION_ACTION_SLEEP,
    build_completion_action_command,
    run_completion_action,
)


class BatchCompletionActionTest(unittest.TestCase):
    def test_builds_windows_power_actions(self):
        self.assertEqual(
            build_completion_action_command(COMPLETION_ACTION_SHUTDOWN, 'win32'),
            ['shutdown', '/s', '/t', '0'],
        )
        self.assertEqual(
            build_completion_action_command(COMPLETION_ACTION_RESTART, 'win32'),
            ['shutdown', '/r', '/t', '0'],
        )
        self.assertEqual(
            build_completion_action_command(COMPLETION_ACTION_HIBERNATE, 'win32'),
            ['shutdown', '/h'],
        )
        self.assertEqual(
            build_completion_action_command(COMPLETION_ACTION_SLEEP, 'win32'),
            ['rundll32.exe', 'powrprof.dll,SetSuspendState', '0,1,0'],
        )

    def test_builds_linux_power_actions(self):
        self.assertEqual(
            build_completion_action_command(COMPLETION_ACTION_SHUTDOWN, 'linux'),
            ['systemctl', 'poweroff'],
        )
        self.assertEqual(
            build_completion_action_command(COMPLETION_ACTION_SLEEP, 'linux'),
            ['systemctl', 'suspend'],
        )

    def test_custom_command_uses_shell_and_is_not_executed_in_tests(self):
        calls = []

        def fake_popen(command, shell):
            calls.append((command, shell))

        self.assertTrue(
            run_completion_action(
                COMPLETION_ACTION_CUSTOM,
                'echo done',
                popen_factory=fake_popen,
            )
        )
        self.assertEqual(calls, [('echo done', True)])

    def test_blank_custom_command_is_rejected(self):
        with self.assertRaises(ValueError):
            run_completion_action(COMPLETION_ACTION_CUSTOM, '   ', popen_factory=lambda *args, **kwargs: None)


if __name__ == '__main__':
    unittest.main()
