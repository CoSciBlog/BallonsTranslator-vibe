from types import SimpleNamespace

import numpy as np
import pytest

from ballontranslator.utils.reinpaint import reinpaint_project_page


class _Project:
    def __init__(self, mask, image=None):
        self.pages = {'001.png': [SimpleNamespace(text='hello')]}
        self.current_img = '001.png'
        self.inpainted_array = None
        self._mask = mask
        self.saved = None
        self.saved_mask = None
        self._image = image

    def read_img(self, page_name):
        assert page_name == '001.png'
        if self._image is not None:
            return self._image.copy()
        return np.full((4, 5, 3), 7, dtype=np.uint8)

    def load_mask_by_imgname(self, page_name):
        assert page_name == '001.png'
        return self._mask

    def save_inpainted(self, page_name, image):
        self.saved = (page_name, image.copy())

    def save_mask(self, page_name, mask):
        self.saved_mask = (page_name, mask.copy())


class _Inpainter:
    def __init__(self):
        self.calls = []

    def inpaint(self, image, mask, blocks):
        self.calls.append((image.copy(), mask, blocks))
        return np.full_like(image, 23)


def test_reinpaint_uses_original_image_and_complete_saved_mask():
    mask = np.zeros((4, 5), dtype=np.uint8)
    mask[1:3, 2:4] = 255
    project = _Project(mask)
    inpainter = _Inpainter()

    assert reinpaint_project_page(project, inpainter, '001.png') is True
    source, used_mask, blocks = inpainter.calls[0]
    assert np.all(source == 7)
    np.testing.assert_array_equal(used_mask, mask)
    assert blocks is None
    assert project.saved[0] == '001.png'
    expected = np.full((4, 5, 3), 7, dtype=np.uint8)
    expected[mask > 0] = 23
    np.testing.assert_array_equal(project.saved[1], expected)
    np.testing.assert_array_equal(project.inpainted_array, expected)


def test_reinpaint_splits_distant_mask_areas_into_local_high_resolution_calls():
    image = np.full((600, 900, 3), 7, dtype=np.uint8)
    mask = np.zeros(image.shape[:2], dtype=np.uint8)
    mask[80:120, 70:100] = 255
    mask[470:520, 780:825] = 255
    project = _Project(mask, image)
    inpainter = _Inpainter()

    assert reinpaint_project_page(project, inpainter, '001.png') is True

    assert len(inpainter.calls) == 2
    assert all(call_image.shape[0] < image.shape[0] for call_image, _, _ in inpainter.calls)
    assert all(call_image.shape[1] < image.shape[1] for call_image, _, _ in inpainter.calls)
    assert sum(np.count_nonzero(call_mask) for _, call_mask, _ in inpainter.calls) == np.count_nonzero(mask)
    assert all(blocks is None for _, _, blocks in inpainter.calls)


def test_reinpaint_groups_nearby_character_masks_into_one_local_call():
    image = np.full((600, 900, 3), 7, dtype=np.uint8)
    mask = np.zeros(image.shape[:2], dtype=np.uint8)
    mask[100:125, 100:120] = 255
    mask[140:165, 102:122] = 255
    mask[180:205, 98:118] = 255
    project = _Project(mask, image)
    inpainter = _Inpainter()

    assert reinpaint_project_page(project, inpainter, '001.png') is True

    assert len(inpainter.calls) == 1
    call_image, call_mask, blocks = inpainter.calls[0]
    assert call_image.shape[0] < image.shape[0]
    assert call_image.shape[1] < image.shape[1]
    assert np.count_nonzero(call_mask) == np.count_nonzero(mask)
    assert blocks is None


def test_reinpaint_does_not_chain_separate_groups_through_context_overlap():
    image = np.full((600, 900, 3), 7, dtype=np.uint8)
    mask = np.zeros(image.shape[:2], dtype=np.uint8)
    mask[200:225, 100:120] = 255
    mask[200:225, 180:200] = 255
    mask[200:225, 260:280] = 255
    project = _Project(mask, image)
    inpainter = _Inpainter()

    assert reinpaint_project_page(project, inpainter, '001.png') is True

    assert len(inpainter.calls) == 3
    assert sum(
        np.count_nonzero(call_mask)
        for _, call_mask, _ in inpainter.calls
    ) == np.count_nonzero(mask)


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


def test_reinpaint_expands_mask_and_preserves_the_stored_input():
    mask = np.zeros((4, 5), dtype=np.uint8)
    mask[1, 2] = 255
    project = _Project(mask)
    inpainter = _Inpainter()

    assert reinpaint_project_page(project, inpainter, '001.png', dilate=1)

    used_mask = inpainter.calls[0][1]
    assert used_mask[0, 2] == used_mask[1, 1] == used_mask[2, 2] == 255
    assert used_mask[0, 0] == 0
    assert np.count_nonzero(mask) == 1
    np.testing.assert_array_equal(project.saved_mask[1], used_mask)
    np.testing.assert_array_equal(project.mask_array, used_mask)


def test_reinpaint_applies_inpainter_mask_preparation_to_the_composite():
    mask = np.zeros((7, 7), dtype=np.uint8)
    mask[3, 3] = 255
    project = _Project(mask, np.full((7, 7, 3), 7, dtype=np.uint8))

    class DilatingInpainter:
        def __init__(self):
            self.prepared_flags = []

        def prepare_inpaint_mask(self, source_mask):
            prepared = np.zeros_like(source_mask)
            prepared[2:5, 2:5] = 255
            return prepared

        def inpaint(self, image, used_mask, blocks, *, mask_prepared=False):
            self.prepared_flags.append(mask_prepared)
            return np.full_like(image, 23)

    inpainter = DilatingInpainter()
    assert reinpaint_project_page(project, inpainter, '001.png')

    result = project.saved[1]
    assert np.count_nonzero(np.all(result == 23, axis=2)) == 9
    assert inpainter.prepared_flags == [True]
    assert project.saved_mask is None


def test_reinpaint_saves_stable_mask_repairs_before_temporary_dilation():
    mask = np.zeros((7, 7), dtype=np.uint8)
    mask[2:5, 2:5] = 255
    mask[3, 3] = 0
    project = _Project(mask, np.full((7, 7, 3), 7, dtype=np.uint8))

    class RepairingInpainter:
        def __init__(self):
            self.repair_calls = 0

        def repair_inpaint_mask(self, source_mask):
            self.repair_calls += 1
            repaired = source_mask.copy()
            repaired[3, 3] = 255
            return repaired

        def dilate_inpaint_mask(self, source_mask):
            prepared = source_mask.copy()
            prepared[1:6, 1:6] = 255
            return prepared

        def prepare_inpaint_mask(self, source_mask):
            raise AssertionError(
                'The repaired full-page mask must not be repaired twice.'
            )

        def inpaint(self, image, used_mask, blocks, *, mask_prepared=False):
            assert mask_prepared
            return np.full_like(image, 23)

    inpainter = RepairingInpainter()
    assert reinpaint_project_page(project, inpainter, '001.png')

    saved_mask = project.saved_mask[1]
    assert saved_mask[3, 3] == 255
    assert saved_mask[1, 1] == 0
    assert np.count_nonzero(np.all(project.saved[1] == 23, axis=2)) == 25
    assert mask[3, 3] == 0
    assert inpainter.repair_calls == 1


def test_reinpaint_detects_residual_text_and_preserves_the_combined_mask():
    mask = np.zeros((4, 5), dtype=np.uint8)
    mask[0, 0] = 255
    residual = np.zeros_like(mask)
    residual[3, 4] = 255  # Outside the existing text region.
    project = _Project(mask)
    inpainter = _Inpainter()
    seen = []

    class Detector:
        def detect(self, image, imgtrans_proj):
            seen.append(image.copy())
            assert imgtrans_proj is project
            return residual, [SimpleNamespace(text='residual')]

    assert reinpaint_project_page(
        project, inpainter, '001.png', textdetector=Detector(),
    )

    assert len(seen) == 1
    assert np.all(seen[0][0, 0] == 23)
    assert np.all(seen[0][mask == 0] == 7)
    assert len(inpainter.calls) == 2
    source, used_mask, blocks = inpainter.calls[1]
    assert np.all(inpainter.calls[0][0] == 7)
    assert np.all(source[0, 0] == 23)
    assert np.all(source[3, 4] == 7)
    assert blocks is None
    assert used_mask[0, 0] == 0
    assert used_mask[3, 4] == 255
    assert project.saved_mask[1][0, 0] == project.saved_mask[1][3, 4] == 255
    assert project.pages['001.png'][0].text == 'hello'


def test_residual_repair_retains_the_first_result_when_residual_is_inside_saved_mask():
    project = _Project(np.full((4, 5), 255, dtype=np.uint8))

    class Painter:
        calls = 0

        def inpaint(self, image, mask, blocks):
            self.calls += 1
            result = image.copy()
            if self.calls == 1:
                result[0, 0] = 99  # A successfully reconstructed detail.
            else:
                result[3, 4] = 42  # Repair only the residual text.
            return result

    residual = np.zeros((4, 5), dtype=np.uint8)
    residual[3, 4] = 255
    detector = SimpleNamespace(detect=lambda *args: (residual, []))
    assert reinpaint_project_page(project, Painter(), '001.png', textdetector=detector)
    assert np.all(project.saved[1][0, 0] == 99)
    assert np.all(project.saved[1][3, 4] == 42)


@pytest.mark.parametrize('residual', [None, np.zeros((4, 5), dtype=np.uint8)])
def test_reinpaint_does_not_repeat_inference_without_residual_text(residual):
    project = _Project(np.full((4, 5), 255, dtype=np.uint8))
    inpainter = _Inpainter()
    detector = SimpleNamespace(detect=lambda *args: (residual, []))

    assert reinpaint_project_page(project, inpainter, '001.png', textdetector=detector)
    assert len(inpainter.calls) == 1


def test_reinpaint_normalizes_mask_size_channels_and_values():
    project = _Project(np.ones((2, 3, 3), dtype=np.uint8))
    inpainter = _Inpainter()

    assert reinpaint_project_page(project, inpainter, '001.png')
    np.testing.assert_array_equal(inpainter.calls[0][1], np.full((4, 5), 255, np.uint8))


def test_reinpaint_failure_does_not_save_optimized_mask_or_result():
    project = _Project(np.ones((4, 5), dtype=np.uint8))
    inpainter = _Inpainter()

    class Detector:
        def detect(self, *args):
            raise RuntimeError('Detection failed')

    with pytest.raises(RuntimeError, match='Detection failed'):
        reinpaint_project_page(project, inpainter, '001.png', dilate=1, textdetector=Detector())
    assert project.saved is None
    assert project.saved_mask is None


def test_failed_residual_inpainting_keeps_previous_result_and_mask():
    project = _Project(np.full((4, 5), 255, dtype=np.uint8))

    class Painter(_Inpainter):
        def inpaint(self, image, mask, blocks):
            if self.calls:
                raise RuntimeError('Repair failed')
            return super().inpaint(image, mask, blocks)

    detector = SimpleNamespace(detect=lambda *args: (np.ones((4, 5), np.uint8), []))
    with pytest.raises(RuntimeError, match='Repair failed'):
        reinpaint_project_page(project, Painter(), '001.png', textdetector=detector)
    assert project.saved is None
    assert project.saved_mask is None


def test_reinpaint_cancellation_after_detection_does_not_start_second_inference():
    project = _Project(np.ones((4, 5), dtype=np.uint8))
    inpainter = _Inpainter()
    stopped = []

    class Detector:
        def detect(self, *args):
            stopped.append(True)
            return np.ones((4, 5), dtype=np.uint8), []

    assert not reinpaint_project_page(
        project, inpainter, '001.png', textdetector=Detector(),
        stop_requested=lambda: bool(stopped),
    )
    assert len(inpainter.calls) == 1
    assert project.saved is None
    assert project.saved_mask is None
