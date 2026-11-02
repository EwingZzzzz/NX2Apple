import contextlib
import io
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import apple_ci as ci


class InputTests(unittest.TestCase):
    def test_only_direct_https_urls(self):
        self.assertEqual(ci.validate_url('https://example.com/file?signature=test'),
                         'https://example.com/file?signature=test')
        for url in ('http://example.com', 'https://user:pass@example.com',
                    'https://example.com/#fragment', 'https://example.com/\nsecret'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                ci.validate_url(url)

    def test_redirects_never_forward_signed_urls(self):
        with self.assertRaises(ValueError):
            ci.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://other.example')

    def test_zip_rejects_paths_links_keys_duplicates_and_bombs(self):
        cases = [('../a.nsp', 0), ('/a.nsp', 0), ('a/b.nsp', 0),
                 ('a\\b.nsp', 0), ('prod.keys', 0), ('a.nsp', stat.S_IFLNK | 0o777)]
        for name, mode in cases:
            with self.subTest(name=name, mode=mode), tempfile.TemporaryDirectory() as tmp:
                archive = Path(tmp) / 'input.zip'
                with zipfile.ZipFile(archive, 'w') as z:
                    entry = zipfile.ZipInfo(name)
                    entry.external_attr = mode << 16
                    z.writestr(entry, b'test')
                with self.assertRaises(ValueError):
                    ci.unpack(archive, Path(tmp) / 'out', 1024)
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / 'input.zip'
            with zipfile.ZipFile(archive, 'w') as z:
                z.writestr('a.nsp', b'0123456789')
                z.writestr('A.nsp', b'0')
            with self.assertRaises(ValueError):
                ci.unpack(archive, Path(tmp) / 'out', 1024)
            with self.assertRaises(ValueError):
                ci.unpack(archive, Path(tmp) / 'out', 1)

    def test_synthetic_container_extracts(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / 'input.zip'
            with zipfile.ZipFile(archive, 'w') as z:
                z.writestr('synthetic.nsp', b'not a game')
            ci.unpack(archive, Path(tmp) / 'out', 1024)
            self.assertEqual((Path(tmp) / 'out/synthetic.nsp').read_bytes(), b'not a game')

    def test_capacity_fails_before_build(self):
        with patch.object(ci.shutil, 'disk_usage') as usage:
            usage.return_value.free = ci.GIB
            with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(RuntimeError):
                ci.disk(8, '.')

    def test_cleanup_rejects_workspace_or_parent(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(ci.os.environ, {'RUNNER_TEMP': tmp, 'PRIVATE_ROOT': tmp}):
                with self.assertRaises(ValueError):
                    ci.cleanup()

    def test_private_failure_does_not_print_exception_secrets(self):
        output = io.StringIO()
        with patch.object(ci, 'private_root', side_effect=RuntimeError('signed-url-and-key')):
            with patch.object(ci, 'cleanup') as cleanup, contextlib.redirect_stdout(output):
                previous = ci.os.umask(0o077)
                try:
                    self.assertEqual(ci.private_build(), 1)
                finally:
                    ci.os.umask(previous)
                cleanup.assert_called_once()
        self.assertNotIn('signed-url-and-key', output.getvalue())
        self.assertIn('input validation', output.getvalue())

    def test_download_limit_before_writing_excess_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(ci.urllib.request, 'build_opener') as opener:
                opener.return_value.open.return_value.__enter__.return_value.read.return_value = b'1234'
                with self.assertRaises(ValueError):
                    ci.transfer('https://example.com/private', destination=Path(tmp) / 'input.zip', limit=3)
                self.assertEqual((Path(tmp) / 'input.zip').stat().st_size, 0)


if __name__ == '__main__':
    unittest.main()
