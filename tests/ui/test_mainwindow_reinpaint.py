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

    def test_post_merge_config_uses_settings_values(self):
        module_config = ui.module_manager.pcfg.module
        original_values = (
            module_config.post_merge_mode,
            module_config.post_merge_max_vertical_gap,
            module_config.post_merge_max_horizontal_gap,
            module_config.post_merge_min_width_overlap_ratio,
            module_config.post_merge_min_height_overlap_ratio,
        )
        try:
            module_config.post_merge_mode = "HORIZONTAL_THEN_VERTICAL"
            module_config.post_merge_max_vertical_gap = 41
            module_config.post_merge_max_horizontal_gap = 52
            module_config.post_merge_min_width_overlap_ratio = 63
            module_config.post_merge_min_height_overlap_ratio = 74

            method = ui.module_manager.ModuleManager.post_merge_config_from_settings
            config = method(None)

            self.assertEqual(config["MERGE_MODE"], "HORIZONTAL_THEN_VERTICAL")
            self.assertEqual(config["VERTICAL_MERGE_PARAMS"]["max_vertical_gap"], 41)
            self.assertEqual(config["HORIZONTAL_MERGE_PARAMS"]["max_horizontal_gap"], 52)
            self.assertEqual(config["VERTICAL_MERGE_PARAMS"]["min_width_overlap_ratio"], 63)
            self.assertEqual(config["HORIZONTAL_MERGE_PARAMS"]["min_height_overlap_ratio"], 74)
        finally:
            (
                module_config.post_merge_mode,
                module_config.post_merge_max_vertical_gap,
                module_config.post_merge_max_horizontal_gap,
                module_config.post_merge_min_width_overlap_ratio,
                module_config.post_merge_min_height_overlap_ratio,
            ) = original_values

    def test_translator_setting_updates_visible_profile_during_async_switch(self):
        module_config = ui.module_manager.cfg_module
        original_params = module_config.translator_params.get("LLM_API_Translator")
        visible_params = {
            "num ctx": {"value": 0, "data_type": int},
        }
        module_config.translator_params["LLM_API_Translator"] = visible_params
        try:
            dummy_manager = type("DummyManager", (), {})()
            dummy_manager.translator_panel = MagicMock()
            dummy_manager.translator_panel.module_combobox.currentText.return_value = (
                "LLM_API_Translator"
            )
            dummy_manager.translator = MagicMock()
            dummy_manager.translator.name = "Two-Step Translator"

            method = ui.module_manager.ModuleManager.on_translatorparam_edited.__get__(
                dummy_manager, ui.module_manager.ModuleManager
            )
            method("num ctx", {"content": "32768"})

            self.assertEqual(visible_params["num ctx"]["value"], 32768)
        finally:
            if original_params is None:
                module_config.translator_params.pop("LLM_API_Translator", None)
            else:
                module_config.translator_params["LLM_API_Translator"] = original_params

    def test_sidebar_region_merge_uses_settings_config(self):
        config = {"MERGE_MODE": "VERTICAL"}
        dummy_window = type("DummyWindow", (), {})()
        dummy_window.module_manager = MagicMock()
        dummy_window.module_manager.post_merge_config_from_settings.return_value = config
        dummy_window.run_merge_task = MagicMock()

        method = ui.mainwindow.MainWindow.run_merge_current_page_using_settings.__get__(
            dummy_window, ui.mainwindow.MainWindow
        )
        method()

        dummy_window.run_merge_task.assert_called_once_with(on_current=True, config=config)

if __name__ == '__main__':
    unittest.main()
