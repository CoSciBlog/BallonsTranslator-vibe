import json
import os
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from qtpy.QtWidgets import QApplication

from ballontranslator.ui.pipeline_history_window import PipelineHistoryWindow
from ballontranslator.ui.mainwindow import MainWindow
from ballontranslator.utils.config import pcfg
from ballontranslator.utils.llm_profiles import LLMProfile, LLM_TRANSLATOR_KEY
from ballontranslator.utils.pipeline_history import PipelineHistoryStore


def test_history_start_and_finish_use_separate_versioned_json(tmp_path):
    store = PipelineHistoryStore(str(tmp_path))
    entry_id = store.start(
        'pipeline',
        {
            'pages': ['001.png'],
            'translation_llm': {
                'profile_name': 'Ollama',
                'model': 'qwen3:8b',
            },
        },
    )
    assert store.finish(entry_id, 'completed') is True

    payload = json.loads((tmp_path / 'pipeline_history.json').read_text('utf-8'))
    assert payload['schema_version'] == 1
    assert len(payload['entries']) == 1
    entry = payload['entries'][0]
    assert entry['status'] == 'completed'
    assert entry['duration_seconds'] >= 0
    assert entry['details']['translation_llm']['model'] == 'qwen3:8b'
    assert not list(tmp_path.glob('.pipeline_history.*.tmp'))


def test_malformed_history_is_not_overwritten(tmp_path):
    path = tmp_path / 'pipeline_history.json'
    path.write_text('{broken', encoding='utf-8')
    store = PipelineHistoryStore(str(tmp_path))

    with pytest.raises(json.JSONDecodeError):
        store.start('pipeline')

    assert path.read_text('utf-8') == '{broken'


def test_history_window_shows_duration_and_llm_model(tmp_path):
    app = QApplication.instance() or QApplication([])
    store = PipelineHistoryStore(str(tmp_path))
    entry_id = store.start(
        'batch_task',
        {
            'pipeline': {
                'stages': ['translate'],
                'modules': {'translator': 'LLMTranslator'},
            },
            'translation_llm': {'model': 'gpt-6.1-sol'},
        },
    )
    store.finish(entry_id, 'completed')

    window = PipelineHistoryWindow()
    window.set_directory(str(tmp_path))
    assert window.table.rowCount() == 1
    assert window.table.item(0, 2).text() == 'Completed'
    assert window.table.item(0, 6).text() == 'gpt-6.1-sol'

    window.deleteLater()
    app.processEvents()


def test_pipeline_metadata_records_selected_translation_llm():
    profile = LLMProfile(
        id='ollama-test',
        name='Ollama local',
        backend='openai',
        model='qwen3:14b',
        model_options=['qwen3:14b'],
        require_api_key=False,
    )
    module = SimpleNamespace(
        enable_detect=False,
        enable_ocr=False,
        enable_inpaint=False,
        enable_translate=True,
        textdetector='ctd',
        ocr='manga_ocr',
        inpainter='lama_large_512px',
        translator=LLM_TRANSLATOR_KEY,
        llm_profiles=[profile],
        translator_llm_id=profile.id,
    )
    owner = SimpleNamespace(
        imgtrans_proj=SimpleNamespace(directory='chapter-01'),
        _batch_id='',
        _batch_task=None,
    )

    with patch.object(pcfg, 'module', module):
        details = MainWindow._history_details(owner, ['001.png'])

    assert details['translation_llm'] == {
        'profile_id': 'ollama-test',
        'profile_name': 'Ollama local',
        'backend': 'openai',
        'model': 'qwen3:14b',
    }
