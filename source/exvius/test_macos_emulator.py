"""Behavioral checks for the host/device boundary, with no Android installation."""
from contextlib import redirect_stdout
import hashlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import macos_emulator as app


class MacEmulatorBehavior(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory()
        self.addCleanup(self.work.cleanup)
        self.home = Path(self.work.name)
        self.paths = app.Locations(self.home, self.home / 'sdk')
        self.calls = []
        self.controller = app.Emulator(self.paths, self.boundary)
        for key in ('ANDROID_AVD_HOME',):
            self.env_patch = patch.dict(app.os.environ)
            self.env_patch.start()
            self.addCleanup(self.env_patch.stop)
            app.os.environ.pop(key, None)

    def boundary(self, args, **kwargs):
        args = [str(x) for x in args]
        self.calls.append(args)
        if args[1:] == ['devices']:
            return ('List of devices attached\nphysical-phone\tdevice\n'
                    'emulator-5554\tdevice\nemulator-5556\tdevice\n')
        if args[-3:] == ['emu', 'avd', 'name']:
            return (app.AVD if args[2] == 'emulator-5556' else 'Other_AVD') + '\nOK'
        if args[-2:] == ['getprop', 'sys.boot_completed']:
            return '1'
        if args[-2:] == ['getprop', 'ro.product.cpu.abi']:
            return 'arm64-v8a'
        if args[-2:] == ['getprop', 'ro.build.version.sdk']:
            return '33'
        if 'dumpsys' in args:
            return self.installed
        if 'install' in args:
            return 'Success'
        return ''

    def existing_avd(self):
        self.paths.avd.mkdir(parents=True)
        (self.paths.avd / 'config.ini').write_text(
            'abi.type=arm64-v8a\nimage.sysdir.1=system-images/android-33/google_apis/arm64-v8a/\n'
            'disk.dataPartition.size=32G\nhw.ramSize=4096\n')
        (self.paths.avd / 'userdata-qemu.img').write_bytes(b'precious guest save')

    def test_given_missing_tools_when_doctor_then_report_without_writes_or_subprocesses(self):
        before = set(self.home.rglob('*'))
        with patch.object(app.platform, 'system', return_value='Darwin'), \
                patch.object(app.platform, 'machine', return_value='arm64'), redirect_stdout(io.StringIO()) as out:
            self.assertFalse(self.controller.doctor())
        self.assertIn('MISSING', out.getvalue())
        self.assertIn('setup', out.getvalue())
        self.assertEqual(set(self.home.rglob('*')), before)
        self.assertEqual(self.calls, [])

    def test_given_existing_save_when_setup_reuses_avd_then_no_config_or_userdata_changes(self):
        self.existing_avd()
        before = {p.name: p.read_bytes() for p in self.paths.avd.iterdir()}
        self.controller.create_avd()
        self.controller.create_avd()
        self.assertEqual({p.name: p.read_bytes() for p in self.paths.avd.iterdir()}, before)
        self.assertEqual(self.calls, [])

    def test_given_incompatible_avd_when_setup_then_fail_and_preserve_userdata(self):
        self.existing_avd()
        config = self.paths.avd / 'config.ini'
        config.write_text(config.read_text().replace('arm64-v8a', 'x86_64'))
        with self.assertRaises(app.SetupError):
            self.controller.create_avd()
        self.assertEqual((self.paths.avd / 'userdata-qemu.img').read_bytes(), b'precious guest save')
        self.assertEqual(self.calls, [])

    def test_given_storage_units_when_validate_then_require_at_least_32_gib(self):
        self.existing_avd()
        config = self.paths.avd / 'config.ini'
        original = config.read_text()
        for size in ('32G', '32768M', '34359738368'):
            config.write_text(original.replace('32G', size))
            self.controller.validate_avd()
        config.write_text(original.replace('32G', '8G'))
        with self.assertRaises(app.SetupError):
            self.controller.validate_avd()

    def test_given_connected_phone_and_other_avd_when_install_then_only_target_named_avd(self):
        self.installed = ''
        serial = self.controller.target()
        self.assertEqual(serial, 'emulator-5556')
        self.controller.install(serial, self.home / 'game.apk', {'versionCode': 9025})
        writes = [c for c in self.calls if 'install' in c]
        self.assertEqual(writes, [[str(self.paths.adb), '-s', 'emulator-5556',
                                  'install', '-r', str(self.home / 'game.apk')]])
        self.assertFalse(any('physical-phone' in c for c in self.calls))

    def test_given_same_or_newer_app_when_setup_then_no_reinstall_or_downgrade(self):
        for code in (9025, 9026):
            self.installed = f'versionCode={code} minSdk=24'
            self.controller.install('emulator-5556', self.home / 'game.apk', {'versionCode': 9025})
        self.assertFalse(any('install' in c for c in self.calls))

    def test_given_signing_failure_when_install_then_do_not_uninstall_clear_or_retry(self):
        self.installed = 'versionCode=9023 minSdk=24'
        def failing(args, **kwargs):
            if 'install' in args:
                self.calls.append([str(x) for x in args])
                raise app.SetupError('INSTALL_FAILED_UPDATE_INCOMPATIBLE')
            return self.boundary(args, **kwargs)
        self.controller.run = failing
        with self.assertRaisesRegex(app.SetupError, 'existing app data was preserved'):
            self.controller.install('emulator-5556', self.home / 'game.apk', {'versionCode': 9025})
        self.assertEqual(len([c for c in self.calls if 'install' in c]), 1)
        self.assertFalse(any('uninstall' in c or 'clear' in c for c in self.calls))

    def test_given_corrupted_download_when_fetch_then_reject_before_any_device_mutation(self):
        manifest = {'version': 'test', 'size': 4, 'sha256': hashlib.sha256(b'good').hexdigest(),
                    'url': 'https://example.invalid/game.apk'}
        with patch.object(app.urllib.request, 'urlopen', return_value=io.BytesIO(b'evil')):
            with self.assertRaisesRegex(app.SetupError, 'SHA-256 mismatch'):
                self.controller.fetch_apk(manifest)
        self.assertEqual(list(self.paths.cache.glob('*.apk*')), [])
        self.assertEqual(self.calls, [])

    def test_given_already_running_avd_when_boot_then_reuse_without_duplicate_process(self):
        self.existing_avd()
        for path in (self.paths.adb, self.paths.emulator):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch()
        with patch.object(app.subprocess, 'Popen') as spawn:
            self.assertEqual(self.controller.boot(), 'emulator-5556')
        spawn.assert_not_called()

    def test_given_concurrent_launcher_when_acquiring_lock_then_reject_second_command(self):
        other = app.Emulator(self.paths, self.boundary)
        with self.controller.lock():
            with self.assertRaisesRegex(app.SetupError, 'Another Exvius'):
                with other.lock():
                    self.fail('A second command acquired the same lock')
        with other.lock():
            pass  # The first command released the lock normally.

    def test_given_verified_cached_apk_when_setup_repeats_then_reuse_without_network(self):
        manifest = {'version': 'test', 'size': 4, 'sha256': hashlib.sha256(b'good').hexdigest(),
                    'url': 'https://example.invalid/game.apk'}
        self.paths.cache.mkdir(parents=True)
        cached = self.paths.cache / 'exvius-offline-vtest.apk'
        cached.write_bytes(b'good')
        with patch.object(app.urllib.request, 'urlopen') as request:
            self.assertEqual(self.controller.fetch_apk(manifest), cached)
        request.assert_not_called()

    def test_given_sdk_local_tools_when_selecting_avdmanager_then_use_selected_sdk_root(self):
        local = self.paths.sdk / 'cmdline-tools/latest/bin'
        local.mkdir(parents=True)
        (local / 'sdkmanager').touch()
        self.assertEqual(self.paths.tools / 'avdmanager', local / 'avdmanager')


if __name__ == '__main__':
    unittest.main()
