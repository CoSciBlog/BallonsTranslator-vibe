import unittest
from unittest.mock import MagicMock, patch
import sys
import os

APP_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(APP_ROOT)

# We import the file to make sure 'np' is defined in the module space
import ui.mainwindow
import ui.module_manager

class TestMainWindowReInpaint(unittest.TestCase):
    def test_np_is_defined(self):
        self.assertTrue(hasattr(ui.mainwindow, 'np'), "numpy should be imported as np in ui.mainwindow")

    @patch('ui.mainwindow.create_info_dialog')
    def test_run_reinpaint_current_page_no_mask(self, mock_create_info_dialog):
        # Create a dummy object mimicking the MainWindow structure needed for this method
        class DummyMainWindow:
            def __init__(self):
                self.imgtrans_proj = MagicMock()
                self.imgtrans_proj.is_empty = False
                self.imgtrans_proj.current_img = "test_page.png"
                self.imgtrans_proj.pages = {"test_page.png": []}
                self.module_manager = MagicMock()
                self.module_manager.inpainterBusy.return_value = False
                self.module_manager.inpainter = MagicMock()
                
            def tr(self, text):
                return text
                
            def _current_page_reinpaint_mask(self, page_name):
                return None

        # Bind the method to our dummy instance
        dummy_window = DummyMainWindow()
        method = ui.mainwindow.MainWindow.run_reinpaint_current_page.__get__(dummy_window, ui.mainwindow.MainWindow)
        
        # Call the method
        method()
        
        # Assert that create_info_dialog was called due to no mask
        mock_create_info_dialog.assert_called_with('No inpaint masks found for the current page.')

    def test_module_manager_forwards_canvas_inpaint_metadata(self):
        class DummyInpaintThread:
            def __init__(self):
                self.calls = []

            def isRunning(self):
                return False

            def inpaint(self, *args, **kwargs):
                self.calls.append((args, kwargs))

        dummy_manager = type("DummyManager", (), {})()
        dummy_manager.inpaint_thread = DummyInpaintThread()

        method = ui.module_manager.ModuleManager.inpaint.__get__(dummy_manager, ui.module_manager.ModuleManager)
        method("img", "mask", operation="reinpaint_current_page", page_name="page.png")

        self.assertEqual(dummy_manager.inpaint_thread.calls[0][1]["operation"], "reinpaint_current_page")
        self.assertEqual(dummy_manager.inpaint_thread.calls[0][1]["page_name"], "page.png")

if __name__ == '__main__':
    unittest.main()
