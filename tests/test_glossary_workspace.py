import json
import tempfile
import unittest
from pathlib import Path

from ballontranslator.glossary import (
    GlossaryConflictError,
    GlossaryOrigin,
    GlossaryStatus,
    GlossaryWorkspace,
    project_prompt_entries,
)


class GlossaryWorkspaceTests(unittest.TestCase):
    def setUp(self) -> None:
        workspace_tmp = Path(__file__).resolve().parents[1] / 'tmp'
        workspace_tmp.mkdir(exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=workspace_tmp)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.chapter = self.root / 'Chapter_01'
        self.chapter.mkdir()
        self.workspace = GlossaryWorkspace.for_project(self.chapter)
        self.addCleanup(self.workspace.close)

    def test_source_assignments_survive_project_reopen(self) -> None:
        series = self.root / 'series_glossary.json'
        reference = self.root / 'reference.json'
        reference.write_text(json.dumps({
            'schema_version': 1,
            'glossary_id': 'reference',
            'entries': [],
        }), encoding='utf-8')
        self.workspace.assign_series(series)
        self.workspace.add_reference(reference)
        self.workspace.close()

        reopened = GlossaryWorkspace.for_project(self.chapter)
        self.addCleanup(reopened.close)
        self.assertEqual(Path(reopened.series.path), series)
        self.assertEqual(Path(reopened.references[0].path), reference)

    def test_effective_priority_and_conflict_visibility(self) -> None:
        series = self.workspace.assign_series(self.root / 'series_glossary.json')
        series.service.create_entry(
            original='Sakura', translation='Series Sakura',
            status=GlossaryStatus.CONFIRMED.value,
        )
        self.workspace.project.create_entry(
            original='Sakura', translation='Project Sakura',
            status=GlossaryStatus.CONFIRMED.value,
        )
        effective = self.workspace.effective_entries()
        self.assertEqual(effective[0].entry.translation, 'Project Sakura')
        conflicts = self.workspace.conflicts()
        self.assertEqual(conflicts[0].winner.source_kind, 'project')
        self.assertEqual(conflicts[0].alternatives[0].source_kind, 'series')

    def test_reference_is_read_only_and_used_in_prompt(self) -> None:
        reference_workspace = GlossaryWorkspace.for_project(self.root / 'reference-source')
        reference_workspace.project.create_entry(
            original='勇者', translation='Hero',
            status=GlossaryStatus.CONFIRMED.value,
        )
        reference_path = Path(reference_workspace.project.repository.path)
        reference_workspace.close()
        source = self.workspace.add_reference(reference_path)
        self.assertFalse(source.writable)
        prompt = project_prompt_entries(self.workspace, ['勇者が来た'])
        self.assertEqual([(entry.source, entry.translation) for entry in prompt], [('勇者', 'Hero')])

    def test_promote_confirmed_project_entries_only(self) -> None:
        series = self.workspace.assign_series(self.root / 'series_glossary.json')
        self.workspace.project.create_entry(
            original='Alice', translation='Alice',
            status=GlossaryStatus.CONFIRMED.value,
        )
        self.workspace.project.create_entry(
            original='Maybe', translation='Vielleicht',
            origin=GlossaryOrigin.LLM.value,
        )
        result = self.workspace.promote_confirmed_to_series()
        self.assertEqual(result.added, 1)
        self.assertEqual([entry.original for entry in series.service.entries], ['Alice'])

    def test_completion_callback_and_context_switch_contract(self) -> None:
        completed = []
        self.workspace.on_project_completed(lambda workspace: completed.append(workspace))
        self.workspace.complete_project()
        self.assertEqual(completed, [self.workspace])

    def test_series_is_reused_by_next_chapter(self) -> None:
        series_path = self.root / 'series_glossary.json'
        self.workspace.assign_series(series_path)
        self.workspace.project.create_entry(
            original='Guild', translation='Gilde', status='Confirmed'
        )
        self.workspace.promote_confirmed_to_series()
        second = self.root / 'Chapter_02'
        second.mkdir()
        next_chapter = GlossaryWorkspace.for_project(second)
        self.addCleanup(next_chapter.close)
        next_chapter.assign_series(series_path, create=False)
        self.assertEqual(next_chapter.effective_entries()[0].entry.translation, 'Gilde')

    def test_parallel_writer_is_detected_without_lost_update(self) -> None:
        other = GlossaryWorkspace.for_project(self.chapter)
        self.addCleanup(other.close)
        self.workspace.project.autosave = False
        self.workspace.project.create_entry(original='Local', translation='Lokal')
        other.project.create_entry(original='External', translation='Extern')
        with self.assertRaises(GlossaryConflictError):
            self.workspace.project.save()
        self.workspace.project.load(discard_unsaved=True)


if __name__ == '__main__':
    unittest.main()
