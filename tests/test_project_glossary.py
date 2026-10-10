import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from ballontranslator.glossary import (
    GLOSSARY_SCHEMA_VERSION,
    DuplicateGlossaryEntryError,
    GlossaryCategory,
    GlossaryConflictError,
    GlossaryCorruptError,
    GlossaryOrigin,
    GlossaryProtectedError,
    GlossaryRepository,
    GlossaryService,
    GlossaryStatus,
    UnsupportedGlossarySchemaError,
)
from ballontranslator.utils.proj_imgtrans import ProjImgTrans
from ballontranslator.utils.config import pcfg


class ProjectGlossaryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.directory = Path(self.temp_dir.name)
        self.path = self.directory / 'glossary.json'

    def service(self, *, autosave: bool = True) -> GlossaryService:
        service = GlossaryService.for_project(
            self.directory, autosave=autosave
        )
        self.addCleanup(service.close)
        return service

    def test_missing_glossary_is_created_as_readable_utf8_json(self) -> None:
        service = self.service()

        entry = service.create_entry(
            original='魔王',
            translation='Dämonenkönig',
            source_language='ja',
            target_language='de',
            category=GlossaryCategory.CHARACTER.value,
            aliases=['魔王さま'],
            description='Unicode ✓',
            status=GlossaryStatus.CONFIRMED.value,
            confidence=0.98,
        )

        payload = json.loads(self.path.read_text(encoding='utf-8'))
        self.assertEqual(payload['schema_version'], GLOSSARY_SCHEMA_VERSION)
        self.assertEqual(payload['entries'][0]['original'], '魔王')
        self.assertEqual(payload['entries'][0]['translation'], 'Dämonenkönig')
        self.assertEqual(service.get_entry(entry.id).aliases, ('魔王さま',))
        self.assertIn('\n  "entries": [', self.path.read_text(encoding='utf-8'))

    def test_existing_glossary_loads_without_rewriting(self) -> None:
        first = self.service()
        created = first.create_entry(original='Hero', translation='Held')
        first.close()
        before = self.path.read_bytes()
        before_mtime = self.path.stat().st_mtime_ns

        second = GlossaryService.for_project(self.directory)
        self.addCleanup(second.close)

        self.assertEqual(second.get_entry(created.id).translation, 'Held')
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.path.stat().st_mtime_ns, before_mtime)

    def test_crud_search_confirmation_and_alias_management(self) -> None:
        service = self.service()
        entry = service.create_entry(
            original='Sir Lancelot',
            translation='Sir Lanzelot',
            category=GlossaryCategory.CHARACTER.value,
        )
        entry = service.add_alias(entry.id, 'ランスロット')
        entry = service.update_entry(entry.id, description='Knight')
        entry = service.confirm_entry(entry.id)

        self.assertEqual(entry.status, GlossaryStatus.CONFIRMED)
        self.assertEqual(service.search('ランスロット'), (entry,))
        self.assertEqual(
            service.search(category=GlossaryCategory.CHARACTER), (entry,)
        )
        entry = service.remove_alias(entry.id, 'ランスロット')
        self.assertEqual(entry.aliases, ())
        service.delete_entry(entry.id)
        self.assertEqual(service.entries, ())

    def test_aliases_participate_in_duplicate_detection(self) -> None:
        service = self.service()
        first = service.create_entry(
            original='アルトリア', aliases=['Artoria', 'Altria']
        )

        self.assertEqual(service.find_duplicates('ARTORIA'), (first,))
        with self.assertRaises(DuplicateGlossaryEntryError):
            service.create_entry(original='Different', aliases=['Ａｌｔｒｉａ'])
        normalized = service.create_entry(
            original='Excalibur', aliases=['Ｅｘｃａｌｉｂｕｒ']
        )
        self.assertEqual(normalized.aliases, ())

    def test_noop_edits_do_not_write_the_glossary_again(self) -> None:
        service = self.service()
        entry = service.create_entry(original='Hero')

        with patch.object(
            service.repository, 'save', wraps=service.repository.save
        ) as save:
            self.assertEqual(
                service.update_entry(entry.id, translation=''), entry
            )
            self.assertEqual(service.add_alias(entry.id, 'Hero'), entry)

        save.assert_not_called()

    def test_protected_entry_rejects_automatic_changes_only(self) -> None:
        service = self.service()
        entry = service.create_entry(original='Hero', protected=True)

        with self.assertRaises(GlossaryProtectedError):
            service.update_entry(entry.id, automatic=True, translation='Changed')
        with self.assertRaises(GlossaryProtectedError):
            service.delete_entry(entry.id, automatic=True)

        updated = service.update_entry(entry.id, translation='Manual change')
        self.assertEqual(updated.translation, 'Manual change')

    def test_export_and_import_report_duplicates_and_conflicts(self) -> None:
        source = self.service()
        source.create_entry(original='Hero', translation='Held')
        source.create_entry(original='Mage', translation='Magier')
        source.create_entry(original='Sword', translation='Schwert')
        export_path = self.directory / 'export.json'
        source.export_file(export_path)

        target_dir = self.directory / 'target'
        target = GlossaryService.for_project(target_dir)
        self.addCleanup(target.close)
        target.create_entry(original='Hero', translation='Held')
        target.create_entry(original='Mage', translation='Zauberer')
        result = target.import_file(export_path)

        self.assertEqual(result.added, 1)
        self.assertEqual(result.duplicates, 1)
        self.assertEqual(result.conflicts, 1)
        self.assertEqual(target.search('Sword')[0].translation, 'Schwert')

    def test_legacy_14_glossary_is_migrated_with_metadata(self) -> None:
        self.path.write_text(
            json.dumps(
                {
                    'entries': (
                        'Hero => Held [character] # protagonist\n'
                        '王都 => Königsstadt [place]'
                    ),
                    'prompt': 'Keep names consistent.',
                },
                ensure_ascii=False,
            ),
            encoding='utf-8',
        )

        service = self.service()
        payload = json.loads(self.path.read_text(encoding='utf-8'))

        self.assertEqual(payload['schema_version'], GLOSSARY_SCHEMA_VERSION)
        self.assertEqual(len(service.entries), 2)
        self.assertEqual(service.entries[0].origin, GlossaryOrigin.IMPORT)
        self.assertEqual(service.entries[0].category, GlossaryCategory.CHARACTER)
        self.assertEqual(
            service.document.metadata['legacy_prompt'], 'Keep names consistent.'
        )

    def test_current_v15_array_glossary_can_be_imported(self) -> None:
        import_path = self.directory / 'v15-glossary.json'
        import_path.write_text(
            json.dumps(
                [{'src': '勇者', 'dst': 'Hero', 'info': 'main character'}],
                ensure_ascii=False,
            ),
            encoding='utf-8',
        )
        service = self.service()

        result = service.import_file(import_path)

        self.assertEqual(result.added, 1)
        imported = service.search('勇者')[0]
        self.assertEqual(imported.translation, 'Hero')
        self.assertEqual(imported.description, 'main character')
        self.assertEqual(imported.origin, GlossaryOrigin.IMPORT)

    def test_corrupt_and_future_schema_files_are_never_overwritten(self) -> None:
        corrupt = b'{not valid json'
        self.path.write_bytes(corrupt)
        with self.assertRaises(GlossaryCorruptError):
            GlossaryRepository(self.path).load()
        self.assertEqual(self.path.read_bytes(), corrupt)

        future = json.dumps(
            {'schema_version': 999, 'glossary_id': 'project', 'entries': []}
        ).encode('utf-8')
        self.path.write_bytes(future)
        with self.assertRaises(UnsupportedGlossarySchemaError):
            GlossaryRepository(self.path).load()
        self.assertEqual(self.path.read_bytes(), future)

        malformed_legacy = json.dumps(
            {'entries': 'Hero => Held\nthis line is not an entry'}
        ).encode('utf-8')
        self.path.write_bytes(malformed_legacy)
        with self.assertRaises(GlossaryCorruptError):
            GlossaryRepository(self.path).load()
        self.assertEqual(self.path.read_bytes(), malformed_legacy)

    def test_atomic_save_uses_replace_and_leaves_no_temp_file(self) -> None:
        service = self.service(autosave=False)
        service.create_entry(original='Hero')

        with patch(
            'ballontranslator.glossary.persistence.os.replace', wraps=os.replace
        ) as replace_file:
            self.assertTrue(service.save())

        replace_file.assert_called_once()
        self.assertEqual(list(self.directory.glob('glossary.json.*.tmp')), [])
        self.assertEqual(
            json.loads(self.path.read_text(encoding='utf-8'))['entries'][0][
                'original'
            ],
            'Hero',
        )

    def test_external_changes_block_overwrite_and_can_be_reloaded(self) -> None:
        service = self.service()
        service.create_entry(original='Hero', translation='Held')
        external = json.loads(self.path.read_text(encoding='utf-8'))
        external['metadata'] = {'edited_elsewhere': True}
        self.path.write_text(
            json.dumps(external, ensure_ascii=False, indent=2) + '\n',
            encoding='utf-8',
        )

        self.assertTrue(service.has_external_changes())
        with self.assertRaises(GlossaryConflictError):
            service.create_entry(original='Mage', translation='Magier')
        self.assertTrue(
            json.loads(self.path.read_text(encoding='utf-8'))['metadata'][
                'edited_elsewhere'
            ]
        )
        service.load(create=False, discard_unsaved=True)
        self.assertFalse(service.dirty)

    def test_project_open_creates_loads_and_closes_standalone_glossary(self) -> None:
        Image.new('RGB', (4, 4), 'white').save(self.directory / '001.png')
        project = ProjImgTrans(str(self.directory))
        self.assertIsNotNone(project.glossary_service)
        self.assertTrue(self.path.exists())
        project.glossary_service.autosave = False
        entry = project.glossary_service.create_entry(
            original='勇者', translation='Held'
        )
        self.assertEqual(
            json.loads(self.path.read_text(encoding='utf-8'))['entries'], []
        )
        project.close_project_glossary()
        self.assertIsNone(project.glossary_service)

        reopened = ProjImgTrans(str(self.directory))
        self.addCleanup(reopened.close_project_glossary)
        self.assertEqual(reopened.glossary_service.get_entry(entry.id).original, '勇者')
        project_payload = json.loads(Path(reopened.proj_path).read_text('utf-8'))
        self.assertNotIn('glossary', project_payload)

    def test_project_open_preserves_broken_glossary_and_reports_error(self) -> None:
        Image.new('RGB', (4, 4), 'white').save(self.directory / '001.png')
        broken = b'not-json'
        self.path.write_bytes(broken)

        project = ProjImgTrans(str(self.directory))

        self.assertIsNone(project.glossary_service)
        self.assertIsNotNone(project.glossary_load_error)
        self.assertEqual(self.path.read_bytes(), broken)

    def test_auto_creation_can_be_disabled_without_affecting_project_open(self) -> None:
        Image.new('RGB', (4, 4), 'white').save(self.directory / '001.png')
        with patch.object(pcfg.module, 'project_glossary_auto_create', False):
            project = ProjImgTrans(str(self.directory))
        self.addCleanup(project.close_project_glossary)
        self.assertIsNone(project.glossary_workspace)
        self.assertFalse(self.path.exists())


if __name__ == '__main__':
    unittest.main()
