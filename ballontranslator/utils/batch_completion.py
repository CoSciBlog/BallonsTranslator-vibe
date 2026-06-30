import subprocess
import sys


COMPLETION_ACTION_NONE = 'none'
COMPLETION_ACTION_SHUTDOWN = 'shutdown'
COMPLETION_ACTION_RESTART = 'restart'
COMPLETION_ACTION_HIBERNATE = 'hibernate'
COMPLETION_ACTION_SLEEP = 'sleep'
COMPLETION_ACTION_CUSTOM = 'custom'


def build_completion_action_command(action: str, platform_name: str = None):
    platform_name = platform_name or sys.platform
    if action in ('', COMPLETION_ACTION_NONE, None):
        return None

    if platform_name.startswith('win'):
        commands = {
            COMPLETION_ACTION_SHUTDOWN: ['shutdown', '/s', '/t', '0'],
            COMPLETION_ACTION_RESTART: ['shutdown', '/r', '/t', '0'],
            COMPLETION_ACTION_HIBERNATE: ['shutdown', '/h'],
            COMPLETION_ACTION_SLEEP: ['rundll32.exe', 'powrprof.dll,SetSuspendState', '0,1,0'],
        }
    elif platform_name == 'darwin':
        commands = {
            COMPLETION_ACTION_SHUTDOWN: [
                'osascript',
                '-e',
                'tell application "System Events" to shut down',
            ],
            COMPLETION_ACTION_RESTART: [
                'osascript',
                '-e',
                'tell application "System Events" to restart',
            ],
            COMPLETION_ACTION_HIBERNATE: ['pmset', 'sleepnow'],
            COMPLETION_ACTION_SLEEP: ['pmset', 'sleepnow'],
        }
    else:
        commands = {
            COMPLETION_ACTION_SHUTDOWN: ['systemctl', 'poweroff'],
            COMPLETION_ACTION_RESTART: ['systemctl', 'reboot'],
            COMPLETION_ACTION_HIBERNATE: ['systemctl', 'hibernate'],
            COMPLETION_ACTION_SLEEP: ['systemctl', 'suspend'],
        }

    if action not in commands:
        raise ValueError(f'Unsupported batch completion action: {action}')
    return commands[action]


def run_completion_action(
    action: str,
    custom_command: str = '',
    platform_name: str = None,
    popen_factory=subprocess.Popen,
    logger=None,
) -> bool:
    if action in ('', COMPLETION_ACTION_NONE, None):
        return False

    if action == COMPLETION_ACTION_CUSTOM:
        command = (custom_command or '').strip()
        if not command:
            raise ValueError('A custom batch completion command is required.')
        if logger:
            logger.info(f'Running batch completion command: {command}')
        popen_factory(command, shell=True)
        return True

    command = build_completion_action_command(action, platform_name)
    if logger:
        logger.info(f'Running batch completion action {action}: {command}')
    popen_factory(command, shell=False)
    return True
