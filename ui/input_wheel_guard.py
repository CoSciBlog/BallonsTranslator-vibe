from qtpy.QtCore import QObject, QEvent
from qtpy.QtWidgets import QAbstractScrollArea, QAbstractSpinBox, QComboBox, QWidget

from utils.config import pcfg

WHEEL_EVENT = QEvent.Type.Wheel if hasattr(QEvent, "Type") else QEvent.Wheel


class InputWheelGuard(QObject):
    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() != WHEEL_EVENT:
            return False

        if not pcfg.prevent_input_wheel_changes:
            return False

        if isinstance(watched, QComboBox):
            if watched.view() is not None and watched.view().isVisible():
                return False
            self._forward_to_scroll_area(watched, event)
            return True

        if isinstance(watched, QAbstractSpinBox):
            self._forward_to_scroll_area(watched, event)
            return True

        return False

    @staticmethod
    def _forward_to_scroll_area(widget: QWidget, event: QEvent) -> None:
        parent = widget.parentWidget()
        while parent is not None:
            if isinstance(parent, QAbstractScrollArea):
                parent.wheelEvent(event)
                return
            parent = parent.parentWidget()
        event.ignore()
