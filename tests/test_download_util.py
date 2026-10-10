import os
import shutil
import tempfile
import unittest
import zipfile

from ballontranslator.utils.download_util import prepare_archive_for_extraction


class SplitArchiveTest(unittest.TestCase):
    def test_numbered_zip_volumes_are_combined_for_extraction(self) -> None:
        with tempfile.TemporaryDirectory(dir='.') as directory:
            archive = os.path.join(directory, 'model.zip')
            with zipfile.ZipFile(archive, 'w') as output:
                output.writestr('model/data.txt', 'payload')
            with open(archive, 'rb') as source:
                payload = source.read()
            os.remove(archive)
            midpoint = len(payload) // 2
            volumes = [f'{archive}.001', f'{archive}.002']
            for path, data in zip(volumes, (payload[:midpoint], payload[midpoint:])):
                with open(path, 'wb') as output:
                    output.write(data)

            combined, cleanup = prepare_archive_for_extraction(volumes)
            self.assertEqual(combined, cleanup)
            extract_dir = os.path.join(directory, 'extract')
            shutil.unpack_archive(combined, extract_dir)
            with open(os.path.join(extract_dir, 'model', 'data.txt'), encoding='utf8') as result:
                self.assertEqual(result.read(), 'payload')
            os.remove(cleanup)

    def test_split_volumes_must_be_contiguous(self) -> None:
        with self.assertRaisesRegex(ValueError, 'contiguous'):
            prepare_archive_for_extraction(['model.zip.001', 'model.zip.003'])


if __name__ == '__main__':
    unittest.main()
