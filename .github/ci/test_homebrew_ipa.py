import hashlib
from pathlib import Path
import struct
import tempfile
import unittest

import homebrew_ipa as homebrew


class OriginalPayload(unittest.TestCase):
    def test_unencrypted_nso_has_valid_segment_hashes_and_build_id(self):
        raw, build_id = homebrew.original_nso()
        self.assertEqual(raw[:4], b'NSO0')
        self.assertEqual(struct.unpack_from('<I', raw, 12)[0], 0x38)
        self.assertEqual(raw[0x40:0x50].hex(), build_id)
        for i in range(3):
            offset, address, size = struct.unpack_from('<III', raw, 0x10 + i * 16)
            self.assertEqual(address % 0x1000, 0)
            segment = raw[offset:offset + size]
            self.assertEqual(hashlib.sha256(segment).digest(), raw[0xa0 + i * 32:0xc0 + i * 32])
        self.assertEqual(homebrew.original_nso(), (raw, build_id))

    def test_generated_dump_has_original_identity_and_no_keys(self):
        with tempfile.TemporaryDirectory() as temp:
            root = homebrew.generate(Path(temp) / 'fixture')
            npdm = (root / 'dump/base/exefs/main.npdm').read_bytes()
            self.assertEqual(struct.unpack_from('<Q', npdm, 0x90)[0], int(homebrew.TITLE, 16))
            self.assertEqual(npdm[12] & 1, 1)
            self.assertEqual({p.name for p in (root / 'dump/base/exefs').iterdir()}, {'main', 'main.npdm'})
            self.assertEqual(list(root.rglob('*.keys')), [])
            self.assertIn(homebrew.MESSAGE.decode(), (root / 'dump/base/romfs/homebrew.txt').read_text())
            with self.assertRaises(FileExistsError):
                homebrew.generate(root)

    def test_upstream_loader_reads_payload_and_capstone_finds_both_svcs(self):
        import sys
        sys.path.insert(0, str(homebrew.REPO / 'engine/dm/tools'))
        import nso
        import nso_syms
        import capstone
        raw, _ = homebrew.original_nso()
        image = nso.load(raw)
        symbols = nso_syms.dynsyms(bytes(image.image))
        self.assertEqual({name for name, defined, _ in symbols if defined}, set(homebrew.EXPORTS))
        self.assertEqual({name for name, defined, _ in symbols if not defined}, {'vkCreateInstance'})
        instructions = list(capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM).disasm(bytes(image.image[0x80:0x9c]), 0x80))
        self.assertEqual([(i.mnemonic, i.op_str) for i in instructions if i.mnemonic == 'svc'],
                         [('svc', '#0x27'), ('svc', '#0xb')])
        self.assertIn('0x4400', instructions[0].op_str)

    def test_bundled_romfs_matches_sources_and_rejects_missing_or_changed_data(self):
        import sys
        sys.path.insert(0, str(homebrew.REPO / 'engine/dm/tools'))
        import romfs_image
        with tempfile.TemporaryDirectory() as temp:
            root = homebrew.generate(Path(temp) / 'fixture')
            original = root / 'dump/base/romfs'
            for stage in ('vert', 'frag'):
                (original / f'triangle.{stage}.spv').write_bytes(b'original shader test data')
            packed = root / 'test.img'
            romfs_image.pack(original, packed)
            image = packed.read_bytes()
            homebrew.validate_romfs(image, original)
            with self.assertRaises(RuntimeError):
                homebrew.validate_romfs(b'', original)
            changed = image.replace(homebrew.MESSAGE, b'X' * len(homebrew.MESSAGE))
            with self.assertRaises(RuntimeError):
                homebrew.validate_romfs(changed, original)


if __name__ == '__main__':
    unittest.main()
