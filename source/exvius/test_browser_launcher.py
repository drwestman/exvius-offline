"""Given/When/Then boundary checks: no real Android, certificates, or downloads."""
import io
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch
import macos_emulator as app
import browser_launcher as browser


class BrowserLauncherBehavior(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory()
        self.addCleanup(self.work.cleanup)
        self.paths = app.Locations(Path(self.work.name), Path(self.work.name) / 'sdk')
        self.emulator = app.Emulator(self.paths)
        self.browser = browser.BrowserLauncher(self.emulator)

    def test_given_missing_bridge_when_querying_status_then_no_files_or_adb_started(self):
        before = list(self.paths.home.rglob('*'))
        with patch.object(self.emulator, 'run', side_effect=AssertionError('No subprocess allowed')):
            self.assertIsNone(self.browser.query())
            with redirect_stdout(io.StringIO()):
                self.assertFalse(self.browser.doctor())
        self.assertEqual(list(self.paths.home.rglob('*')), before)

    def test_given_invalid_lan_addresses_when_configuring_then_reject(self):
        for address in ('127.0.0.1', '0.0.0.0', '8.8.8.8', '169.254.2.1', '224.0.0.1', 'not-an-ip'):
            with self.assertRaises(ValueError):
                browser.addresses(True, address)
        hosts, names = browser.addresses(True, '192.168.1.15')
        self.assertEqual(hosts, ['127.0.0.1', '192.168.1.15'])
        self.assertIn('192.168.1.15', names)

    def test_given_certificate_for_different_ip_when_launching_then_preserve_android(self):
        self.browser.root.mkdir(parents=True)
        (self.browser.root / 'certificate.json').write_text(json.dumps({'names':['127.0.0.1']}))
        with patch.object(self.browser, 'doctor', return_value=True), patch.object(self.emulator, 'boot') as boot:
            with self.assertRaisesRegex(ValueError, 'address changed'):
                self.browser.preflight(['192.168.1.15'])
            boot.assert_not_called()

    def test_given_existing_avd_when_browser_boots_then_never_spawn_second_process(self):
        with patch.object(self.emulator, 'validate_avd'), patch.object(self.emulator, 'target', return_value='emulator-5556'), patch.object(self.emulator, 'adb', side_effect=['1','arm64-v8a','33']), patch.object(app.socket,'socket'), patch.object(app.subprocess,'Popen') as spawn:
            for path in (self.paths.adb, self.paths.emulator):
                path.parent.mkdir(parents=True,exist_ok=True);path.touch()
            self.assertEqual(self.emulator.boot(headless=True),'emulator-5556')
            spawn.assert_not_called()

    def test_given_stopped_avd_when_booting_browser_then_only_add_headless_flag(self):
        for headless in (False,True):
            for path in (self.paths.adb,self.paths.emulator):
                path.parent.mkdir(parents=True,exist_ok=True);path.touch()
            with patch.object(self.emulator,'validate_avd'), patch.object(self.emulator,'run'), patch.object(self.emulator,'target',side_effect=[None,'emulator-5554']), patch.object(self.emulator,'adb',side_effect=['1','arm64-v8a','33']), patch.object(app.socket,'socket'), patch.object(app.subprocess,'Popen') as spawn:
                spawn.return_value.poll.return_value=None
                self.emulator.boot(headless=headless)
                args=spawn.call_args.args[0]
                self.assertEqual('-no-window' in args,headless)
                self.assertNotIn('-wipe-data',args)
                self.assertIn(app.AVD,args)

    def test_given_running_bridge_when_reopening_then_restore_game_without_booting(self):
        status = {'urls': ['https://127.0.0.1:8443', 'https://localhost:8443'],
                  'code': '12345678', 'serial': 'emulator-5556'}
        with patch.object(self.emulator, 'require_host'), \
                patch.object(self.browser, 'query', return_value=status), \
                patch.object(self.emulator, 'target', return_value='emulator-5556'), \
                patch.object(self.browser, 'ensure_game_visible') as restore, \
                patch.object(self.browser, 'show') as show, \
                patch.object(self.emulator, 'boot') as boot:
            self.browser.launch(open_browser=False)
            boot.assert_not_called()
            restore.assert_called_once_with('emulator-5556')
            show.assert_called_once_with(status, False)

    def test_given_game_already_visible_when_ensuring_visibility_then_no_activity_commands(self):
        activity = ('topResumedActivity=ActivityRecord{abc u0 '
                    + app.PACKAGE + '/com.square_enix.android_googleplay.FFBEWW.Lapis t14}')
        with patch.object(self.emulator, 'adb', side_effect=['versionCode=9065', activity]) as adb:
            self.browser.ensure_game_visible('emulator-5556')
        self.assertFalse(any('am' in call.args for call in adb.call_args_list))

    def test_given_background_game_task_when_ensuring_visibility_then_focus_existing_task(self):
        activities = ('topResumedActivity=ActivityRecord{abc u0 com.android.launcher/.Launcher t12}\n'
                      '    * Hist  #0: ActivityRecord{def u0 ' + app.PACKAGE
                      + '/com.square_enix.android_googleplay.FFBEWW.Lapis t14}')
        with patch.object(self.emulator, 'adb', side_effect=[
                'versionCode=9065', activities, 'Setting focus to task 14']) as adb:
            self.browser.ensure_game_visible('emulator-5556')
        self.assertEqual(adb.call_args.args,
                         ('emulator-5556', 'shell', 'am', 'task', 'focus', '14'))
        self.assertEqual(adb.call_count, 3)
        self.assertTrue(all(call.args[0] == 'emulator-5556' for call in adb.call_args_list))
        self.assertFalse(any('start' in call.args for call in adb.call_args_list))

    def test_given_no_valid_game_task_when_ensuring_visibility_then_start_launcher(self):
        home = 'topResumedActivity=ActivityRecord{abc u0 com.android.launcher/.Launcher t12}'
        game_record = ('    * Hist  #0: ActivityRecord{def u0 ' + app.PACKAGE
                       + '/com.square_enix.android_googleplay.FFBEWW.Lapis')
        records = {
            'no activity': '',
            'unrelated package': '    * Hist  #0: ActivityRecord{def u0 com.android.settings/.Settings t14}',
            'similar package': '    * Hist  #0: ActivityRecord{def u0 ' + app.PACKAGE + '.extra/.Lapis t14}',
            'task outside record': game_record + '} t14}',
            'missing task': game_record + '}',
            'task across newline': game_record + '\n t14}',
        }
        for case, record in records.items():
            with self.subTest(case=case):
                with patch.object(self.emulator, 'adb', side_effect=[
                        'versionCode=9065', home + '\n' + record, 'Status: ok']) as adb:
                    self.browser.ensure_game_visible('emulator-5556')
                self.assertEqual(adb.call_args.args,
                                 ('emulator-5556', 'shell', 'am', 'start', '-W',
                                  '-a', 'android.intent.action.MAIN',
                                  '-c', 'android.intent.category.LAUNCHER',
                                  '-f', '0x10000000', '-n', app.ACTIVITY))
                self.assertEqual(adb.call_count, 3)
                self.assertFalse(any('focus' in call.args for call in adb.call_args_list))

    def test_given_task_focus_failure_when_restoring_game_then_report_without_starting_activity(self):
        activities = ('    * Hist  #0: ActivityRecord{def u0 ' + app.PACKAGE
                      + '/com.square_enix.android_googleplay.FFBEWW.Lapis t14}')
        for message in ('Error: task not found', 'Status: timeout'):
            with self.subTest(message=message):
                with patch.object(self.emulator, 'adb', side_effect=[
                        'versionCode=9065', activities, message]) as adb:
                    with self.assertRaises(ValueError) as error:
                        self.browser.ensure_game_visible('emulator-5556')
                self.assertEqual(str(error.exception), message)
                self.assertEqual(adb.call_args.args,
                                 ('emulator-5556', 'shell', 'am', 'task', 'focus', '14'))
                self.assertEqual(adb.call_count, 3)
                self.assertFalse(any('start' in call.args for call in adb.call_args_list))

    def test_given_activity_start_error_when_restoring_game_then_report_failure(self):
        with patch.object(self.emulator, 'adb', side_effect=[
                'versionCode=9065', '', 'Error: activity not found']):
            with self.assertRaisesRegex(ValueError, 'activity not found'):
                self.browser.ensure_game_visible('emulator-5556')

    def test_given_browser_stop_when_emulator_stop_requested_then_bridge_is_stopped_first(self):
        calls=[]
        with patch.object(self.emulator,'require_host'), patch.object(self.emulator,'target',return_value='emulator-5554'), patch.object(browser.BrowserLauncher,'stop',side_effect=lambda:calls.append('bridge')), patch.object(self.emulator,'adb',side_effect=lambda *a:calls.append(a)):
            self.paths.adb.parent.mkdir(parents=True);self.paths.adb.touch()
            self.emulator.stop()
        self.assertEqual(calls,['bridge',('emulator-5554','emu','kill')])

    def run_certificate_setup(self, install_error=None, generation_error=None):
        calls = []
        self.browser.root.mkdir(parents=True)
        ca = self.browser.root / 'ca'
        ca.mkdir()
        (ca / 'rootCA.pem').write_bytes(b'existing project CA')
        (ca / 'rootCA-key.pem').write_bytes(b'existing project private key')

        def run(args, **kwargs):
            args = [str(arg) for arg in args]
            calls.append((args, kwargs))
            if args[:2] == ['mkcert', '-install'] and install_error:
                raise app.SetupError(install_error)
            if args[:2] == ['mkcert', '-cert-file']:
                if generation_error:
                    raise app.SetupError(generation_error)
                Path(args[2]).write_bytes(b'certificate')
                Path(args[4]).write_bytes(b'key')
            return ''

        output = io.StringIO()
        with patch.object(self.emulator, 'require_host'), \
                patch.object(self.emulator, 'run', side_effect=run), \
                patch.object(browser.shutil, 'which', return_value='/installed/tool'), \
                patch.object(self.browser, 'valid_server', return_value=True), \
                redirect_stdout(output):
            self.browser.setup()
        return calls, output.getvalue()

    def test_given_macos_cannot_authorize_trust_when_setup_then_prepare_files_and_explain_pending_trust(self):
        error = ('mkcert failed (1). ERROR: failed to execute "security add-trusted-cert": exit status 1\n'
                 'SecTrustSettingsSetTrustSettings: The authorization was denied since no user interaction was possible.')
        calls, output = self.run_certificate_setup(install_error=error)
        self.assertTrue((self.browser.root / 'cert.pem').is_file())
        self.assertTrue((self.browser.root / 'key.pem').is_file())
        self.assertTrue((self.browser.root / 'certificate.json').is_file())
        self.assertEqual((self.browser.root / 'ca/rootCA.pem').read_bytes(), b'existing project CA')
        self.assertEqual((self.browser.root / 'ca/rootCA-key.pem').read_bytes(), b'existing project private key')
        self.assertIn('Mac CA trust is pending', output)
        self.assertIn('Keychain Access', output)
        self.assertIn('Always Trust', output)
        self.assertNotIn('Browser setup complete', output)
        install = next(options for args, options in calls if args[:2] == ['mkcert', '-install'])
        self.assertTrue(install.get('capture', True))

    def test_given_trust_authorization_succeeds_when_setup_then_certificates_exist_before_install(self):
        calls, output = self.run_certificate_setup()
        generation = next(i for i, (args, _) in enumerate(calls) if args[:2] == ['mkcert', '-cert-file'])
        install = next(i for i, (args, _) in enumerate(calls) if args[:2] == ['mkcert', '-install'])
        self.assertLess(generation, install)
        self.assertIn('Browser setup complete', output)
        self.assertNotIn('trust is pending', output)
        self.assertEqual((self.browser.root / 'key.pem').stat().st_mode & 0o777, 0o600)

    def test_given_sudo_has_no_terminal_when_setup_then_report_pending_trust(self):
        _, output = self.run_certificate_setup(install_error=(
            'mkcert failed (1). ERROR: failed to execute "security add-trusted-cert": exit status 1\n'
            'sudo: a terminal is required to read the password; either use the -S option '
            'to read from standard input or configure an askpass helper\n'
            'sudo: a password is required'))
        self.assertIn('Mac CA trust is pending', output)
        self.assertIn('Keychain Access', output)
        self.assertTrue((self.browser.root / 'certificate.json').is_file())

    def test_given_explicit_trust_refusal_when_setup_then_preserve_the_failure(self):
        with self.assertRaisesRegex(app.SetupError, 'authorization was denied'):
            self.run_certificate_setup(install_error=(
                'mkcert failed (1). SecTrustSettingsSetTrustSettings: The authorization was denied.'))

    def test_given_unrelated_trust_error_when_setup_then_do_not_suppress_it(self):
        with self.assertRaisesRegex(app.SetupError, 'certificate parse error'):
            self.run_certificate_setup(install_error='mkcert failed (1). certificate parse error')

    def test_given_certificate_generation_error_when_setup_then_report_failure(self):
        with self.assertRaisesRegex(app.SetupError, 'certificate generation failed'):
            self.run_certificate_setup(generation_error='certificate generation failed')
