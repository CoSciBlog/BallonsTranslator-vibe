import os
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from ballontranslator.ui.module_manager import ModuleManager
from ballontranslator.utils.config import ModuleConfig
from ballontranslator.utils.merger import perform_configured_merge
from ballontranslator.utils.config import pcfg
from ballontranslator.utils.textblock import TextBlock


def merge_config(mode: str = 'HORIZONTAL') -> dict:
    return {
        'MERGE_MODE': mode,
        'READING_DIRECTION': 'LTR',
        'PER_LABEL_DIRECTIONS': {},
        'LABELS_TO_EXCLUDE_FROM_MERGE': set(),
        'LABEL_MERGE_STRATEGY': 'PREFER_SHORTER',
        'REQUIRE_SAME_LABEL': False,
        'USE_SPECIFIC_MERGE_GROUPS': False,
        'SPECIFIC_MERGE_GROUPS': [],
        'VERTICAL_MERGE_PARAMS': {
            'max_vertical_gap': 30,
            'min_width_overlap_ratio': 50,
            'overlap_epsilon': 1e-6,
        },
        'HORIZONTAL_MERGE_PARAMS': {
            'max_horizontal_gap': 30,
            'min_height_overlap_ratio': 50,
            'overlap_epsilon': 1e-6,
        },
        'ADVANCED_MERGE_OPTIONS': {
            'allow_negative_gap': True,
            'debug_mode': False,
        },
        'OUTPUT_SHAPE_TYPE': 'rectangle',
    }


class RegionMergeTests(unittest.TestCase):
    def test_merge_preserves_source_and_translation_content(self):
        shapes = [
            {
                'xyxy': [0, 0, 20, 20],
                'lines': [[[0, 0], [20, 0], [20, 20], [0, 20]]],
                'text': ['What'],
                'translation': 'What',
                'rich_text': '<p>What</p>',
                'label': 'balloon',
            },
            {
                'xyxy': [25, 0, 45, 20],
                'lines': [[[25, 0], [45, 0], [45, 20], [25, 20]]],
                'text': ['now?'],
                'translation': 'now?',
                'rich_text': '<p>now?</p>',
                'label': 'balloon',
            },
        ]

        merged, removed = perform_configured_merge(shapes, merge_config())

        self.assertEqual(removed, 1)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]['text'], ['What', 'now?'])
        self.assertEqual(merged[0]['translation'], 'What now?')
        self.assertEqual(merged[0]['rich_text'], '')

    def test_merge_avoids_artificial_cjk_spacing(self):
        shapes = [
            {
                'xyxy': [0, 0, 20, 20],
                'lines': [[[0, 0], [20, 0], [20, 20], [0, 20]]],
                'translation': 'こん',
            },
            {
                'xyxy': [25, 0, 45, 20],
                'lines': [[[25, 0], [45, 0], [45, 20], [25, 20]]],
                'translation': 'にちは',
            },
        ]

        merged, _ = perform_configured_merge(shapes, merge_config())

        self.assertEqual(merged[0]['translation'], 'こんにちは')

    def test_compact_auto_reading_order_follows_merge_direction(self):
        shapes = [
            {
                'xyxy': [0, 25, 20, 45],
                'lines': [[[0, 25], [20, 25], [20, 45], [0, 45]]],
                'translation': 'second',
            },
            {
                'xyxy': [0, 0, 20, 20],
                'lines': [[[0, 0], [20, 0], [20, 20], [0, 20]]],
                'translation': 'first',
            },
        ]
        config = merge_config('VERTICAL')
        config['READING_DIRECTION'] = 'AUTO'

        merged, _ = perform_configured_merge(shapes, config)

        self.assertEqual(merged[0]['translation'], 'first second')

    def test_invalid_persisted_settings_fall_back_safely(self):
        config = ModuleConfig(
            post_merge_textboxes='yes',
            post_merge_mode='DIAGONAL',
            post_merge_max_vertical_gap=-1,
            post_merge_max_horizontal_gap=1001,
            post_merge_min_width_overlap_ratio=101,
            post_merge_min_height_overlap_ratio=False,
        )

        self.assertFalse(config.post_merge_textboxes)
        self.assertEqual(config.post_merge_mode, 'VERTICAL_THEN_HORIZONTAL')
        self.assertEqual(config.post_merge_max_vertical_gap, 30)
        self.assertEqual(config.post_merge_max_horizontal_gap, 30)
        self.assertEqual(config.post_merge_min_width_overlap_ratio, 50)
        self.assertEqual(config.post_merge_min_height_overlap_ratio, 50)

    def test_post_pipeline_merge_only_changes_processed_pages(self):
        class Project:
            def __init__(self):
                self.pages = {
                    'processed.png': self._blocks(),
                    'untouched.png': self._blocks(),
                }

            @staticmethod
            def _blocks():
                return [
                    TextBlock(
                        xyxy=[0, 0, 20, 20],
                        lines=[[[0, 0], [20, 0], [20, 20], [0, 20]]],
                        translation='Hello',
                    ),
                    TextBlock(
                        xyxy=[25, 0, 45, 20],
                        lines=[[[25, 0], [45, 0], [45, 20], [25, 20]]],
                        translation='there',
                    ),
                ]

            def pipeline_pages(self, requested=None):
                if requested is None:
                    return list(self.pages)
                return [name for name in requested if name in self.pages]

            def pagename2idx(self, page_name):
                return list(self.pages).index(page_name)

        project = Project()
        processed_list = project.pages['processed.png']
        manager = ModuleManager(project)
        manager._pipeline_pages_to_process = ['processed.png']
        manager._post_pipeline_merge_done = False
        changed_pages = []
        manager.page_trans_finished.connect(changed_pages.append)

        with (
            patch.object(pcfg.module, 'post_merge_textboxes', True),
            patch.object(pcfg.module, 'post_merge_mode', 'HORIZONTAL'),
        ):
            removed = manager.apply_post_pipeline_textbox_merge()

        self.assertEqual(removed, 1)
        self.assertIs(project.pages['processed.png'], processed_list)
        self.assertEqual(len(project.pages['processed.png']), 1)
        self.assertEqual(len(project.pages['untouched.png']), 2)
        self.assertEqual(changed_pages, [0])


if __name__ == '__main__':
    unittest.main()
