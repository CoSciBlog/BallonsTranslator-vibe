import unittest

from ballontranslator.modules.inpaint.base import InpainterBase


class InpainterBaseTest(unittest.TestCase):
    def test_default_device_move_reports_unsupported_operation(self) -> None:
        with self.assertRaises(NotImplementedError):
            InpainterBase.moveToDevice(None, 'cpu')


if __name__ == '__main__':
    unittest.main()
