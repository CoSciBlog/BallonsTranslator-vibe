from pathlib import Path

from ballontranslator.utils.batch_processing import (
    BatchOptions,
    ORDER_STAGED,
    build_batch_tasks,
    collect_batch_project_dirs,
    windows_completion_command,
)


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


def test_complete_order_builds_one_task_per_project():
    tasks = build_batch_tasks(['a', 'b'], _options(upscale_first=True))

    assert [task.phase for task in tasks] == ['complete', 'complete']
    assert all(task.upscale_first for task in tasks)
    assert all(task.enable_translate for task in tasks)


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
        'local', 'local', 'translation', 'translation'
    ]
    assert [task.project_directory for task in tasks] == ['a', 'b', 'a', 'b']
    assert [task.upscale_first for task in tasks] == [True, True, False, False]
    assert all(not task.enable_translate for task in tasks[:2])
    assert all(task.enable_translate for task in tasks[2:])
    assert all(
        not (task.enable_detect or task.enable_ocr or task.enable_inpaint)
        for task in tasks[2:]
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

    assert len(tasks) == 1
    assert tasks[0].phase == 'translation'
    assert tasks[0].upscale_first is True


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
