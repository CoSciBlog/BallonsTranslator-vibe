import unittest
from unittest.mock import MagicMock, patch
import sys
import os

APP_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(APP_ROOT)

# We import the file to make sure 'np' is defined in the module space
import ui.mainwindow

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

if __name__ == '__main__':
    unittest.main()
