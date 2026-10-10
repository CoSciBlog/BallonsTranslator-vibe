from types import SimpleNamespace

import numpy as np

from ballontranslator.utils.reinpaint import reinpaint_project_page


class _Project:
    def __init__(self, mask):
        self.pages = {'001.png': [SimpleNamespace(text='hello')]}
        self.current_img = '001.png'
        self.inpainted_array = None
        self._mask = mask
        self.saved = None

    def read_img(self, page_name):
        assert page_name == '001.png'
        return np.full((4, 5, 3), 7, dtype=np.uint8)

    def load_mask_by_imgname(self, page_name):
        assert page_name == '001.png'
        return self._mask

    def save_inpainted(self, page_name, image):
        self.saved = (page_name, image.copy())


class _Inpainter:
    def __init__(self):
        self.calls = []

    def inpaint(self, image, mask, blocks):
        self.calls.append((image.copy(), mask, blocks))
        return np.full_like(image, 23)


def test_reinpaint_uses_original_image_mask_and_existing_blocks():
    mask = np.zeros((4, 5), dtype=np.uint8)
    mask[1:3, 2:4] = 255
    project = _Project(mask)
    inpainter = _Inpainter()

    assert reinpaint_project_page(project, inpainter, '001.png') is True
    source, used_mask, blocks = inpainter.calls[0]
    assert np.all(source == 7)
    assert used_mask is mask
    assert blocks is project.pages['001.png']
    assert project.saved[0] == '001.png'
    assert np.all(project.saved[1] == 23)
    assert np.all(project.inpainted_array == 23)


def test_reinpaint_skips_missing_mask_without_overwriting_result():
    project = _Project(None)
    inpainter = _Inpainter()

    assert reinpaint_project_page(project, inpainter, '001.png') is False
    assert inpainter.calls == []
    assert project.saved is None


def test_maskless_inpainter_can_use_existing_text_regions():
    project = _Project(None)
    inpainter = _Inpainter()

    assert reinpaint_project_page(
        project,
        inpainter,
        '001.png',
        allow_maskless=True,
    ) is True
    assert inpainter.calls[0][1] is None
