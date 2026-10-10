import os
import sys
import unittest
from types import SimpleNamespace

import numpy as np

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from qtpy.QtWidgets import QApplication, QHBoxLayout, QWidget

from ballontranslator.ui.canvas import Canvas


def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


_APP = qapp()


class CanvasPageFitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.host = QWidget()
        self.host.resize(800, 600)
        self.canvas = Canvas(self.host)
        self.canvas.imgtrans_proj = SimpleNamespace(
            img_valid=True,
            inpainted_valid=True,
            mask_valid=False,
            inpainted_array=np.zeros((1200, 600, 3), dtype=np.uint8),
            img_array=np.zeros((1200, 600, 3), dtype=np.uint8),
        )
        layout = QHBoxLayout(self.host)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.canvas.gv)
        self.host.show()
        _APP.processEvents()

    def tearDown(self) -> None:
        self.host.close()
        self.host.deleteLater()
        _APP.processEvents()

    def _assert_page_fits_viewport(self) -> None:
        viewport = self.canvas.gv.viewport().size()
        page = self.canvas.baseLayer.sceneBoundingRect().size()
        # QGraphicsRectItem includes half of its transparent one-pixel pen in
        # the scene bounds; the actual page pixels still retain the full margin.
        self.assertLessEqual(page.width(), viewport.width() - 24 + 1)
        self.assertLessEqual(page.height(), viewport.height() - 24 + 1)

    def test_loaded_portrait_page_fits_height_and_width(self) -> None:
        self.canvas.reset_auto_fit_zoom()
        self.canvas.updateCanvas()
        _APP.processEvents()

        viewport = self.canvas.gv.viewport().size()
        expected = min(
            (viewport.width() - 24) / 600,
            (viewport.height() - 24) / 1200,
        )
        self.assertAlmostEqual(self.canvas.scale_factor, expected, places=5)
        self._assert_page_fits_viewport()

    def test_new_page_refits_after_manual_zoom(self) -> None:
        self.canvas.reset_auto_fit_zoom()
        self.canvas.updateCanvas()
        _APP.processEvents()
        self.canvas.scaleImage(1.5)
        manual_scale = self.canvas.scale_factor

        self.host.resize(900, 650)
        _APP.processEvents()
        self.assertEqual(self.canvas.scale_factor, manual_scale)

        self.canvas.imgtrans_proj.inpainted_array = np.zeros(
            (400, 1200, 3), dtype=np.uint8,
        )
        self.canvas.imgtrans_proj.img_array = np.zeros(
            (400, 1200, 3), dtype=np.uint8,
        )
        self.canvas.reset_auto_fit_zoom()
        self.canvas.updateCanvas()
        _APP.processEvents()

        viewport = self.canvas.gv.viewport().size()
        expected = min(
            (viewport.width() - 24) / 1200,
            (viewport.height() - 24) / 400,
        )
        self.assertNotEqual(self.canvas.scale_factor, manual_scale)
        self.assertAlmostEqual(self.canvas.scale_factor, expected, places=5)
        self._assert_page_fits_viewport()


if __name__ == '__main__':
    unittest.main()
