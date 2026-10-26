import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from ballontranslator.ui.mainwindow import MainWindow
from ballontranslator.utils.batch_processing import (
    BatchResumeStore,
    BatchOptions,
    ORDER_STAGED,
    batch_resume_plan,
    batch_task_key,
    build_batch_tasks,
    collect_batch_project_dirs,
    windows_completion_command,
)
from ballontranslator.utils.config import pcfg
from ballontranslator.utils.llm_profiles import LLMProfile, LLM_TRANSLATOR_KEY


def _options(**overrides):
    values = dict(
        root_directory='root',
        textdetector='detector',
        ocr='primary',
        fallback_ocr='fallback',
        inpainter='inpainter',
        translator='translator',
    )
    values.update(overrides)
    return BatchOptions(**values)


def test_collect_batch_projects_uses_direct_children_only(tmp_path: Path):
    chapter_10 = tmp_path / 'chapter10'
    chapter_2 = tmp_path / 'chapter2'
    nested = chapter_2 / 'nested'
    empty = tmp_path / 'empty'
    generated = tmp_path / 'result'
    for directory in (chapter_10, nested, empty, generated):
        directory.mkdir(parents=True, exist_ok=True)
    (chapter_10 / '001.png').write_bytes(b'image')
    (chapter_2 / 'cover.jpg').write_bytes(b'image')
    (nested / '001.png').write_bytes(b'image')
    (generated / '001.png').write_bytes(b'image')

    assert collect_batch_project_dirs(str(tmp_path)) == [
        str(chapter_2),
        str(chapter_10),
    ]


def test_complete_order_upscales_every_project_before_any_pipeline():
    tasks = build_batch_tasks(['a', 'b'], _options(upscale_first=True))

    assert [task.phase for task in tasks] == [
        'upscale', 'upscale', 'complete', 'complete'
    ]
    assert [task.project_directory for task in tasks] == ['a', 'b', 'a', 'b']
    assert [task.upscale_first for task in tasks] == [True, True, False, False]
    assert all(not task.enable_translate for task in tasks[:2])
    assert all(task.enable_translate for task in tasks[2:])


def test_complete_order_can_request_reinpainting_after_pipeline():
    tasks = build_batch_tasks(['a'], _options(rerun_inpaint=True))

    assert len(tasks) == 1
    assert tasks[0].rerun_inpaint is True


def test_staged_order_keeps_translation_model_phase_contiguous():
    tasks = build_batch_tasks(
        ['a', 'b'],
        _options(order=ORDER_STAGED, upscale_first=True),
    )

    assert [task.phase for task in tasks] == [
        'upscale', 'upscale', 'local', 'local', 'translation', 'translation'
    ]
    assert [task.project_directory for task in tasks] == [
        'a', 'b', 'a', 'b', 'a', 'b'
    ]
    assert [task.upscale_first for task in tasks] == [
        True, True, False, False, False, False
    ]
    assert all(not task.enable_translate for task in tasks[:4])
    assert all(task.enable_translate for task in tasks[4:])
    assert all(
        not (task.enable_detect or task.enable_ocr or task.enable_inpaint)
        for task in tasks[4:]
    )


def test_staged_translation_only_upscales_once():
    tasks = build_batch_tasks(
        ['a'],
        _options(
            order=ORDER_STAGED,
            enable_detect=False,
            enable_ocr=False,
            enable_inpaint=False,
            upscale_first=True,
        ),
    )

    assert [task.phase for task in tasks] == ['upscale', 'translation']
    assert [task.upscale_first for task in tasks] == [True, False]


def test_staged_reinpaint_only_uses_local_phase():
    tasks = build_batch_tasks(
        ['a', 'b'],
        _options(
            order=ORDER_STAGED,
            enable_detect=False,
            enable_ocr=False,
            enable_inpaint=False,
            enable_translate=False,
            rerun_inpaint=True,
        ),
    )

    assert [task.phase for task in tasks] == ['local', 'local']
    assert all(task.rerun_inpaint for task in tasks)
    assert all(
        not (task.enable_detect or task.enable_ocr or task.enable_inpaint)
        for task in tasks
    )


def test_windows_completion_commands_are_argument_lists():
    assert windows_completion_command('hibernate') == ['shutdown', '/h']
    assert windows_completion_command('shutdown') == [
        'shutdown', '/s', '/t', '0'
    ]
    assert windows_completion_command('restart') == [
        'shutdown', '/r', '/t', '0'
    ]
    assert windows_completion_command('none') == []


def test_batch_resume_checkpoint_round_trips_only_for_matching_plan(tmp_path: Path):
    projects = [str(tmp_path / 'chapter1'), str(tmp_path / 'chapter2')]
    options = _options(root_directory=str(tmp_path), upscale_first=True)
    tasks = build_batch_tasks(projects, options)
    plan = batch_resume_plan(options, projects, tasks)
    store = BatchResumeStore(str(tmp_path))

    assert store.prepare(plan, resume=True) == set()
    completed_key = batch_task_key(tasks[0])
    store.mark_completed(plan, completed_key)

    assert store.prepare(plan, resume=True) == {completed_key}
    changed_plan = batch_resume_plan(
        _options(root_directory=str(tmp_path), enable_translate=False),
        projects,
        build_batch_tasks(
            projects,
            _options(root_directory=str(tmp_path), enable_translate=False),
        ),
    )
    assert store.prepare(changed_plan, resume=True) == set()


def test_batch_resume_can_explicitly_start_over_and_clear_checkpoint(tmp_path: Path):
    projects = [str(tmp_path / 'chapter')]
    options = _options(root_directory=str(tmp_path))
    tasks = build_batch_tasks(projects, options)
    plan = batch_resume_plan(options, projects, tasks)
    store = BatchResumeStore(str(tmp_path))
    store.prepare(plan, resume=True)
    store.mark_completed(plan, batch_task_key(tasks[0]))

    assert store.prepare(plan, resume=False) == set()
    assert store.prepare(plan, resume=True) == set()
    store.clear()
    assert not store.path.exists()


def test_batch_resume_plan_distinguishes_selected_llm_profile():
    first = _options(
        translator='LLMTranslator',
        translator_llm_id='profile-a',
    )
    second = _options(
        translator='LLMTranslator',
        translator_llm_id='profile-b',
    )

    first_plan = batch_resume_plan(
        first,
        ['chapter'],
        build_batch_tasks(['chapter'], first),
    )
    second_plan = batch_resume_plan(
        second,
        ['chapter'],
        build_batch_tasks(['chapter'], second),
    )

    assert first_plan['pipeline']['translator_llm_id'] == 'profile-a'
    assert first_plan != second_plan


def test_batch_uses_selected_llm_profile_and_restores_previous_one(tmp_path: Path):
    previous = LLMProfile(id='previous', name='Previous', model='old-model')
    selected = LLMProfile(id='selected', name='Selected', model='new-model')
    project = tmp_path / 'chapter'
    project.mkdir()
    options = _options(
        root_directory=str(tmp_path),
        translator=LLM_TRANSLATOR_KEY,
        translator_llm_id=selected.id,
        enable_detect=False,
        enable_ocr=False,
        enable_inpaint=False,
    )
    manager = SimpleNamespace(
        selectTextDetector=Mock(),
        selectOCR=Mock(),
        selectInpainter=Mock(),
        selectTranslator=Mock(),
        configure_ocr_fallback=Mock(),
    )
    owner = SimpleNamespace(
        module_manager=manager,
        conditional_save=Mock(),
        _run_next_batch_task=Mock(),
        _batch_options=None,
        _batch_config_snapshot=None,
    )

    with patch.multiple(
        pcfg.module,
        llm_profiles=[previous, selected],
        translator='google',
        translator_llm_id=previous.id,
    ), patch('ballontranslator.ui.mainwindow.QTimer.singleShot') as schedule:
        MainWindow.start_batch_processing(owner, options, [str(project)])

        assert pcfg.module.translator_llm_id == selected.id
        assert owner._batch_config_snapshot['translator_llm_id'] == previous.id
        manager.selectTranslator.assert_called_once_with(LLM_TRANSLATOR_KEY)
        schedule.assert_called_once_with(0, owner._run_next_batch_task)
        payload = json.loads(
            (tmp_path / 'pipeline_history.json').read_text(encoding='utf-8')
        )
        assert payload['entries'][0]['details']['translation_llm'] == {
            'profile_id': selected.id,
            'profile_name': selected.name,
            'backend': selected.backend,
            'model': selected.model,
        }

        MainWindow._restore_batch_config(owner)
        assert pcfg.module.translator_llm_id == previous.id
