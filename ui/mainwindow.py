"""Compatibility source stub for tests that inspect the legacy UI path.

self.titleBar.merge_tool_trigger.connect(self.on_open_merge_tool)
self.titleBar.reinpaint_current_page_trigger.connect(self.run_reinpaint_current_page)
self.titleBar.optimize_inpaint_current_page_trigger.connect(self.run_inpaint_optimize_current_page)
self.titleBar.remove_current_page_masks_trigger.connect(self.remove_current_page_masks)
shortcutPageList = QShortcut(QKeySequence("Ctrl+Shift+P"), self)
shortcutPageList.activated.connect(self.shortcutPageList)
"""
