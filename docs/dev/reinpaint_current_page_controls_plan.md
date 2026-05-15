# Re-Inpaint Current Page Controls Plan

## Existing Flow

- The left sidebar is built in `ui/mainwindowbars.py::LeftBar`, which already owns `Gloss`, `Dc`, `Run`, and `Trans` buttons.
- The top `Tools` menu is built in `ui/mainwindowbars.py::TitleBar`; `Region Merge Tool` is registered there with its shortcut and signal.
- Drawboard image-edit settings live in `ui/drawingpanel.py`. The rectangle tool already has an inpainter selector, a `Dilate` slider, and `Inpaint`/`Delete` actions.
- Canvas inpainting runs through `ui.module_manager.ModuleManager.canvas_inpaint`, which delegates to `InpaintThread` and emits `canvas_inpaint_finished`.
- Undo/redo for image repair is handled by `ui.drawing_commands.InpaintUndoCommand`, which stores the previous inpainted image and mask region before applying the new result.

## Implementation

- Add a left-sidebar `Ri` button directly below `Dc`.
- Add `Tools -> Re-run Inpainting Current Page` with `Ctrl+Shift+I`.
- Add a Drawboard Re-Inpaint tab using the existing inpainter selector and a dedicated `Dilate` slider.
- Combine the current page's saved text/manual inpaint mask with the current page's explicit decensor mask, ignoring all other pages and debug/result/thumbnail outputs.
- Re-run the current inpainter on the original current-page image inside the combined mask bounding box.
- Let the existing canvas inpaint completion path push `InpaintUndoCommand`; then save the current page and refresh the canvas/list view.

## Risks

- Re-running inpainting with a larger dilate value intentionally expands the stored page mask.
- If no inpainter is loaded yet, the UI asks the user to wait for the fallback inpainter to load and run the action again.
- Result quality depends on the selected inpainter and existing mask fidelity.
