"""BDD for explicit, size-preserving sound preparation and read-only verification."""
import copy
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import test_ios_preparation as harness
from ios_server import cpk, sound_codec as codec, sound_inputs as inputs, sound_snapshots as sounds
from ios_server.config import Configuration
from ios_server.runtime import InstanceLock


def slow_crc(raw):
    """Independent bitwise oracle for polynomial 0x8005, no reflection or xor."""
    value = 0
    for byte in raw:
        value ^= byte << 8
        for _ in range(8):
            value = ((value << 1) ^ (0x8005 if value & 0x8000 else 0)) & 65535
    return value


def checked(raw):
    return bytes(raw) + struct.pack('>H', slow_crc(raw))


def hca(cipher=1, *, frames=2, masked=False, dec=False):
    fmt = b'fmt\0' + bytes([2]) + (44100).to_bytes(3, 'big') + struct.pack('>IHH', frames, 0, 0)
    comp = (b'dec\0' if dec else b'comp') + struct.pack('>H', 16) + bytes(6 if dec else 10)
    chunks = fmt + comp + b'ciph' + struct.pack('>H', cipher) + b'pad\0'
    raw = b'HCA\0' + struct.pack('>HH', 0x200, len(chunks) + 10) + chunks
    if masked:
        raw = bytearray(raw)
        for at in (0, 8, 24, 36 if dec else 40, 42 if dec else 46):
            raw[at:at + 4] = bytes(byte | 128 for byte in raw[at:at + 4])
    header = checked(raw)
    return header + b''.join(checked(b'\xff\xff' + bytes((index + j) % 256 for j in range(12))) for index in range(frames))


def awb(payloads, *, width=4, id_size=2, alignment=32, subkey=0):
    header = b'AFS2' + bytes([1, width]) + struct.pack('<HII', id_size, len(payloads), alignment | (subkey << 16))
    ids = b''.join(index.to_bytes(id_size, 'little') for index in range(len(payloads)))
    start = 16 + len(ids) + width * (len(payloads) + 1)
    offsets, body = [start], bytearray()
    for raw in payloads:
        body.extend(bytes(-(start + len(body)) % alignment))
        body.extend(raw)
        offsets.append(start + len(body))
    return header + ids + b''.join(offset.to_bytes(width, 'little') for offset in offsets) + body


def acb(payloads=None, *, encoding=0x50, blob_storage=0x50, masked=False):
    payloads = [hca(masked=masked), hca(0)] if payloads is None else payloads
    columns = [('EncodeType', encoding, 0, 6 if encoding == 0x30 else 0), ('Untouched', 0x30, 4, 123)]
    wave = cpk.encode_table('Waveform', columns, [{'EncodeType': 6 if i % 2 == 0 else 2} for i in range(len(payloads))])
    bank = awb(payloads)
    columns = [('WaveformTable', blob_storage, 11, wave if blob_storage == 0x30 else 0),
               ('AwbFile', blob_storage, 11, bank if blob_storage == 0x30 else 0), ('Keep', 0x30, 10, 'original')]
    return cpk.encode_table('Header', columns, [{'WaveformTable': wave, 'AwbFile': bank}])


class SoundCodec(unittest.TestCase):
    def test_given_crc_oracle_when_accelerated_then_match_known_and_random_vectors(self):
        for raw in (b'', b'123456789', bytes(range(256)), hashlib.sha256(b'fixture').digest() * 100):
            self.assertEqual(codec.crc16(raw), slow_crc(raw))
            self.assertEqual(codec.crc16(checked(raw)), 0)

    def test_given_type1_hca_when_prepared_then_decrypt_exact_payload_and_rewrite_crcs(self):
        raw = awb([hca()]); out, facts = codec.prepare(raw)
        self.assertEqual(facts, {'waveforms': 1, 'decrypted': 1, 'reflagged': 0})
        self.assertEqual(len(out), len(raw))
        start, end = codec.afs2(raw, 0, len(raw))[0]
        header, frame, count, cipher_at, _ = codec.hca(raw, start, end)
        self.assertEqual(out[cipher_at:cipher_at + 2], b'\0\0')
        for index in range(count):
            at = start + header + frame * index
            self.assertEqual(out[at:at + frame - 2], raw[at:at + frame - 2].translate(codec.TYPE1))
            self.assertEqual(slow_crc(out[at:at + frame]), 0)
        self.assertEqual(slow_crc(out[start:start + header]), 0)
        self.assertEqual(codec.validate(out), 1)
        self.assertEqual(codec.prepare(out)[0], out)

    def test_given_mixed_waveforms_when_prepared_then_only_convert_hcamx_and_cipher1(self):
        raw = acb(); out, facts = codec.prepare(raw)
        self.assertEqual(facts, {'waveforms': 2, 'decrypted': 1, 'reflagged': 1})
        self.assertEqual(len(out), len(raw)); codec.validate(out)
        original = codec.Utf(raw); converted = codec.Utf(out)
        self.assertEqual(original.blob('AwbFile'), converted.blob('AwbFile'))
        a, n = converted.blob('WaveformTable')
        self.assertEqual([row['EncodeType'] for row in cpk.table(out[a:a + n])[2]], [2, 2])
        spans = codec.afs2(raw, *original.blob('AwbFile'))
        self.assertEqual(raw[slice(*spans[1])], out[slice(*spans[1])])
        self.assertEqual(cpk.table(out)[2][0]['Keep'], 'original')

    def test_given_constant_native_utf_columns_when_prepared_then_patch_once_and_count_all_rows(self):
        raw = acb(encoding=0x30, blob_storage=0x30)
        out, facts = codec.prepare(raw)
        self.assertEqual(facts['reflagged'], 2); codec.validate(out)

    def test_given_masked_tags_or_dec_header_when_prepared_then_keep_supported_layout(self):
        for dec in (False, True):
            raw = awb([hca(masked=True, dec=dec)])
            out, facts = codec.prepare(raw)
            self.assertEqual(facts['decrypted'], 1); codec.validate(out)

    def test_given_varied_afs2_widths_and_subkeys_when_prepared_then_keep_spans_and_sizes(self):
        for width in (2, 4, 8):
            for ids in (1, 2, 4, 8):
                raw = awb([hca(), hca(0)], width=width, id_size=ids, subkey=37)
                out, _ = codec.prepare(raw)
                self.assertEqual(len(out), len(raw)); codec.validate(out)

    def test_given_native_ios_source_when_prepared_then_keep_every_byte(self):
        raw = acb(); out, facts = codec.prepare(raw, native=True)
        self.assertEqual(out, raw)
        self.assertEqual(facts, {'waveforms': 2, 'decrypted': 0, 'reflagged': 0})
        codec.validate(out, native=True)

    def test_given_already_plain_hca_when_prepared_then_keep_every_byte(self):
        raw = awb([hca(0)])
        self.assertEqual(codec.prepare(raw), (raw, {'waveforms': 1, 'decrypted': 0, 'reflagged': 0}))

    def test_given_bad_header_or_last_frame_crc_when_prepared_then_fail_without_mutating_source(self):
        for index in (20, -1):
            raw = bytearray(awb([hca(), hca()])); raw[index] ^= 1; before = bytes(raw)
            with self.assertRaises(ValueError): codec.prepare(raw)
            self.assertEqual(bytes(raw), before)

    def test_given_keyed_or_non_hca_payload_when_prepared_then_refuse_unsupported_streams(self):
        for payload in (hca(56), b'not an HCA payload'):
            with self.assertRaises(ValueError): codec.prepare(awb([payload]))

    def test_given_bad_afs2_offsets_ids_or_alignment_when_prepared_then_reject(self):
        original = awb([hca(), hca()])
        for at, value in ((5, 3), (6, 3), (12, 0), (18, 0), (24, 255), (28, 0)):
            raw = bytearray(original); raw[at] = value
            with self.subTest(at=at), self.assertRaises(ValueError): codec.prepare(raw)

    def test_given_truncated_utf_or_hca_when_prepared_then_reject(self):
        for raw in (b'@UTF', acb()[:-1], awb([hca()[:-3]])):
            with self.assertRaises(ValueError): codec.prepare(raw)

    def test_given_missing_encoding_or_external_awb_when_prepared_then_reject(self):
        raw = acb(); outer = cpk.table(raw)[2][0]
        for wave, bank in ((cpk.encode_table('Waveform', [('EncodeType', 0x10, 0, 0)], [{}]), outer['AwbFile']),
                           (outer['WaveformTable'], b'')):
            bad = cpk.encode_table('Header', [('WaveformTable', 0x30, 11, wave), ('AwbFile', 0x30, 11, bank)], [{}])
            with self.assertRaises(ValueError): codec.prepare(bad)

    def test_given_empty_native_bank_when_prepared_then_remain_empty(self):
        raw = cpk.encode_table('Header', [('AwbFile', 0x10, 11, 0)], [{}])
        self.assertEqual(codec.prepare(raw), (raw, {'waveforms': 0, 'decrypted': 0, 'reflagged': 0}))


class SoundPreparation(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='ios-sounds-')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.config = Configuration(self.base / 'runtime', self.base / 'data')
        self.config.data.mkdir()
        self.bank = acb()
        self.relative = 'common_lang/sound/se/ios/Ver2_System.acb'
        self.android = self.config.data / 'client/files' / self.relative.replace('/ios/', '/android/')
        self.android.parent.mkdir(parents=True)
        self.android.write_bytes(self.bank)
        self.rows = {}
        for prefix, idcol in inputs.FAMILIES:
            values = {'_MST': [{idcol: '12', '3LHdc6Qa': 'sound/se', 'pJ56sAEo': 'System.acb'},
                               {idcol: '99', '3LHdc6Qa': 'area', 'pJ56sAEo': 'unrelated.cpk'}],
                      '_VERSION_MST_LOCALIZE': [{idcol: '12', 'OzT5lSz3': '2', '86SWOBTb': '97'}],
                      '_CHECKSUM_MST': [{idcol: '12', 'JwbkKrjA': '0', 'mYtcPkQQ': str(len(self.bank))}]}
            for suffix, rows in values.items(): self.rows[prefix + suffix] = rows
        self.write_tables()

    def write_tables(self):
        for table in inputs.TABLES:
            path = self.config.data / 'client/files' / table.path(1)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(harness.master(table.key, self.rows[table.name], mode=table.cipher))

    def tree(self):
        return {str(f.relative_to(self.base)): f.read_bytes() for f in self.base.rglob('*') if f.is_file()}

    def test_given_shared_android_bank_when_prepared_then_publish_one_bank_for_two_resource_facts(self):
        before = {str(p): p.read_bytes() for p in self.config.data.rglob('*') if p.is_file()}
        result = sounds.prepare(self.config)
        self.assertTrue(result['prepared_now']); self.assertFalse(result['delivery_ready'])
        self.assertEqual((result['banks'], result['resources'], result['ios_size_updates']), (1, 2, 2))
        snapshot = sounds.load(self.config)
        entry = snapshot.manifest['banks'][self.relative]
        codec.validate((snapshot.directory / entry['path']).read_bytes())
        self.assertEqual(before, {str(p): p.read_bytes() for p in self.config.data.rglob('*') if p.is_file()})
        self.assertFalse(self.config.state_file.exists())
        self.assertFalse((self.config.root / 'assets/tables').exists())

    def test_given_current_snapshot_when_prepared_again_then_keep_generation_and_files(self):
        sounds.prepare(self.config); before = self.tree()
        self.assertFalse(sounds.prepare(self.config)['prepared_now'])
        self.assertEqual(self.tree(), before)

    def test_given_missing_snapshot_when_verified_then_report_without_writes(self):
        before = self.tree()
        self.assertFalse(sounds.verify(self.config)['ok']); self.assertEqual(self.tree(), before)
        self.assertFalse(self.config.root.exists())

    def test_given_current_snapshot_when_verified_then_do_not_convert_write_or_import_engine(self):
        sounds.prepare(self.config); before = self.tree(); modules = set(sys.modules)
        with patch.object(codec, 'prepare', side_effect=AssertionError('query conversion')):
            self.assertTrue(sounds.verify(self.config)['ok'])
        self.assertEqual(self.tree(), before)
        self.assertNotIn('ffbe_state', set(sys.modules) - modules)

    def test_given_exact_native_overlay_when_prepared_then_preserve_it_and_prefer_over_android(self):
        native = self.config.data / 'overlay' / self.relative
        native.parent.mkdir(parents=True); native.write_bytes(acb([hca(0)]))
        result = sounds.prepare(self.config)
        self.assertEqual((result['native_banks'], result['decrypted'], result['reflagged']), (1, 0, 0))
        snapshot = sounds.load(self.config)
        entry = snapshot.manifest['banks'][self.relative]
        self.assertEqual((snapshot.directory / entry['path']).read_bytes(), native.read_bytes())

    def test_given_missing_exact_version_when_prepared_then_refuse_highest_version_fallback(self):
        self.android.rename(self.android.with_name('Ver99_System.acb'))
        with self.assertRaisesRegex(ValueError, 'Missing exact'): sounds.prepare(self.config)
        self.assertFalse((self.config.root / sounds.POINTER).exists())

    def test_given_escaping_source_symlink_when_prepared_then_reject(self):
        outside = self.base / 'outside.acb'; outside.write_bytes(self.bank)
        self.android.unlink(); self.android.symlink_to(outside)
        with self.assertRaisesRegex(ValueError, 'escapes shared'): sounds.prepare(self.config)

    def test_given_busy_runtime_when_prepared_then_refuse(self):
        with InstanceLock(self.config.root), self.assertRaises(RuntimeError): sounds.prepare(self.config)

    def test_given_managed_static_native_layout_when_prepared_then_resolve_the_same_resources(self):
        native = self.config.data / 'native'
        (self.config.data / 'client/files').rename(native)
        (self.config.data / 'static').mkdir()
        self.assertEqual(sounds.prepare(self.config)['banks'], 1)
        self.assertTrue(sounds.verify(self.config)['ok'])

    def test_given_source_hash_change_at_same_size_when_verified_then_report_stale_without_writes(self):
        sounds.prepare(self.config)
        raw = bytearray(self.bank); raw[-1] ^= 1; self.android.write_bytes(raw); before = self.tree()
        self.assertFalse(sounds.verify(self.config)['ok']); self.assertEqual(self.tree(), before)

    def test_given_source_change_when_refreshed_then_advance_and_preserve_previous_generation(self):
        sounds.prepare(self.config); old = sounds.load(self.config)
        self.android.write_bytes(acb([hca(0), hca(0)]))
        result = sounds.prepare(self.config)
        self.assertEqual(result['generation'], 2); self.assertTrue(old.directory.is_dir())
        self.assertTrue(sounds.verify(self.config)['ok'])

    def test_given_corrupt_output_when_verified_or_prepared_then_fail_visibly(self):
        sounds.prepare(self.config); snapshot = sounds.load(self.config)
        path = snapshot.directory / snapshot.manifest['banks'][self.relative]['path']
        raw = bytearray(path.read_bytes()); raw[-1] ^= 1; path.write_bytes(raw)
        self.assertFalse(sounds.verify(self.config)['ok'])
        with self.assertRaisesRegex(ValueError, 'checksum'): sounds.prepare(self.config)

    def test_given_escaping_output_symlink_when_loaded_then_reject(self):
        sounds.prepare(self.config); snapshot = sounds.load(self.config)
        path = snapshot.directory / snapshot.manifest['banks'][self.relative]['path']
        outside = self.base / 'outside.acb'; outside.write_bytes(path.read_bytes()); path.unlink(); path.symlink_to(outside)
        with self.assertRaisesRegex(ValueError, 'escapes'): sounds.load(self.config)

    def test_given_failed_pointer_replacement_when_retried_then_keep_old_pointer_and_reuse_complete_build(self):
        sounds.prepare(self.config); pointer = self.config.root / sounds.POINTER; old = pointer.read_bytes()
        self.android.write_bytes(acb([hca(0), hca(0)]))
        replace = os.replace
        def fail(source, target):
            if Path(target) == pointer: raise OSError('publication interrupted')
            return replace(source, target)
        with patch.object(sounds.os, 'replace', side_effect=fail), self.assertRaises(OSError): sounds.prepare(self.config)
        self.assertEqual(pointer.read_bytes(), old)
        self.assertEqual(sounds.load(self.config).manifest['generation'], 1)
        self.assertEqual(sounds.prepare(self.config)['generation'], 2)
        self.assertFalse(list(pointer.parent.glob('.building-*')))
        self.assertFalse(list(pointer.parent.glob('.current-*')))

    def test_given_build_failure_when_prepared_then_preserve_pointer_and_clean_stage(self):
        sounds.prepare(self.config); pointer = self.config.root / sounds.POINTER; old = pointer.read_bytes()
        self.android.write_bytes(acb([hca(56)]))
        with self.assertRaisesRegex(ValueError, 'keyed'): sounds.prepare(self.config)
        self.assertEqual(pointer.read_bytes(), old); self.assertFalse(list(pointer.parent.glob('.building-*')))

    def test_given_changed_input_during_build_when_prepared_then_refuse_publication(self):
        build = sounds._build
        def changed(*args):
            result = build(*args); self.android.write_bytes(acb([hca(0)])); return result
        with patch.object(sounds, '_build', side_effect=changed), self.assertRaisesRegex(ValueError, 'changed during'):
            sounds.prepare(self.config)
        self.assertFalse((self.config.root / sounds.POINTER).exists())

    def test_given_zero_stale_size_metadata_when_prepared_then_record_originals_and_measure_output(self):
        self.rows['F_RESOURCE_MAP_CHECKSUM_MST'][0]['mYtcPkQQ'] = '1'; self.write_tables()
        result = sounds.prepare(self.config); snapshot = sounds.load(self.config)
        self.assertEqual(result['android_size_disagreements'], 1)
        self.assertEqual(snapshot.manifest['sources']['resources']['F_RESOURCE_MAP:12']['android_size'], 1)
        self.assertEqual(snapshot.manifest['banks'][self.relative]['size'], len(self.bank))

    def test_given_corrupt_pointer_or_manifest_when_loaded_then_report_without_repair(self):
        sounds.prepare(self.config); pointer = self.config.root / sounds.POINTER; ref = pointer.read_bytes()
        snapshot = sounds.load(self.config); manifest = snapshot.directory / 'manifest.json'; original = manifest.read_bytes()
        for contents in (b'{bad json', inputs.encoded({**json.loads(ref), 'directory': '../elsewhere'})):
            pointer.write_bytes(contents)
            with self.assertRaises(ValueError): sounds.load(self.config)
            self.assertEqual(pointer.read_bytes(), contents)
        pointer.write_bytes(ref)
        for kind in ('size', 'path', 'count', 'inventory', 'native'):
            doc = json.loads(original)
            if kind == 'size': doc['banks'][self.relative]['size'] += 1
            if kind == 'path': doc['banks'][self.relative]['path'] = '../elsewhere'
            if kind == 'count': doc['banks'][self.relative]['waveforms'] += 1
            if kind == 'inventory': doc['banks'].clear()
            if kind == 'native':
                doc['sources']['banks'][self.relative]['native'] = True
                doc['fingerprint'] = inputs.digest(inputs.encoded(doc['sources']))
            raw = inputs.encoded(doc); manifest.write_bytes(raw)
            pointer.write_bytes(inputs.encoded({**json.loads(ref), 'manifest_sha256': inputs.digest(raw)}))
            with self.subTest(kind=kind), self.assertRaises(ValueError): sounds.load(self.config)
        pointer.write_bytes(ref); manifest.write_bytes(original)

    def test_given_changed_resource_metadata_when_verified_then_report_stale(self):
        sounds.prepare(self.config)
        self.rows['F_RESOURCE_VERSION_MST_LOCALIZE'][0]['86SWOBTb'] = '98'
        self.write_tables(); before = self.tree()
        self.assertFalse(sounds.verify(self.config)['ok']); self.assertEqual(self.tree(), before)

    def test_given_invalid_version_duplicate_identity_or_path_when_prepared_then_reject(self):
        original = copy.deepcopy(self.rows)
        for kind in ('version', 'duplicate', 'path'):
            self.rows = copy.deepcopy(original)
            if kind == 'version': self.rows['F_RESOURCE_VERSION_MST_LOCALIZE'][0]['OzT5lSz3'] = '0'
            if kind == 'duplicate': self.rows['F_RESOURCE_MST'].append(copy.deepcopy(self.rows['F_RESOURCE_MST'][0]))
            if kind == 'path': self.rows['F_RESOURCE_MST'][0]['3LHdc6Qa'] = 'sound/../../outside'
            self.write_tables()
            with self.subTest(kind=kind), self.assertRaises(ValueError): sounds.prepare(self.config)

    def test_given_cli_commands_when_run_then_emit_one_json_document_and_keep_queries_read_only(self):
        # Exercise the installer-facing launcher from outside the isolated venv.
        command = [str(Path(sys.base_prefix) / 'bin/python3.12'), '-B', str(harness.SOURCE / 'exvius/macos_ios_server.py')]
        options = ['--root', str(self.config.root), '--data', str(self.config.data)]
        env = {**os.environ, 'PYTHONPATH': str(harness.SOURCE) + ':' + str(harness.SOURCE / 'server')}
        result = subprocess.run([*command, 'prepare-sounds', *options], env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(json.loads(result.stdout)['prepared_now'])
        before = self.tree()
        result = subprocess.run([*command, 'verify-sounds', *options], env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(json.loads(result.stdout)['ok']); self.assertEqual(self.tree(), before)
        result = subprocess.run([*command, 'verify-banners', *options], env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('No summon artwork', json.loads(result.stdout)['error'])
        self.assertEqual(self.tree(), before)


if __name__ == '__main__':
    unittest.main()
