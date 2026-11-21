"""BDD for Finder/Terminal gameplay data selection, without starting a server."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


LAUNCHER = Path(__file__).resolve().parents[2] / 'Play Exvius on iPhone.command'
UPDATER = Path(__file__).resolve().parents[2] / 'Update Exvius iOS Data.command'


class IPhoneLauncher(unittest.TestCase):
    def setUp(self):
        work = tempfile.TemporaryDirectory(prefix='ios launcher ')
        self.addCleanup(work.cleanup)
        self.checkout = Path(work.name) / 'checkout with spaces'
        self.entrypoint = self.checkout / 'source/exvius/macos_ios_server.py'
        self.entrypoint.parent.mkdir(parents=True)
        self.entrypoint.write_text(
            'import argparse, json\n'
            'parser = argparse.ArgumentParser()\n'
            'parser.add_argument("command")\n'
            'parser.add_argument("--data")\n'
            'args, extra = parser.parse_known_args()\n'
            'print(json.dumps(dict(command=args.command, data=args.data, extra=extra)))\n')
        self.launcher = self.checkout / LAUNCHER.name
        shutil.copy2(LAUNCHER, self.launcher)
        self.updater = self.checkout / UPDATER.name
        shutil.copy2(UPDATER, self.updater)
        self.data = self.checkout / 'data'
        self.data.mkdir()
        (self.data / 'latest.json').write_text('{}')
        self.prepared = self.checkout / 'source/out/browser-data'

    def marker(self, root, relative):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('fixture')

    def launch(self, *args, data_env=None):
        env = dict(os.environ)
        env.pop('FFBE_IOS_DATA', None)
        if data_env is not None:
            env['FFBE_IOS_DATA'] = str(data_env)
        result = subprocess.run([str(self.launcher), *map(str, args)], cwd=self.checkout.parent,
                                env=env, input='', text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        reply = json.loads(result.stdout)
        self.assertEqual(reply['command'], 'start')
        return reply

    def test_given_only_release_metadata_when_launched_then_reuse_prepared_host_assets(self):
        self.marker(self.prepared, 'client/shared_prefs/gamedata.xml')
        self.assertEqual(self.launch()['data'], str(self.prepared))

    def test_given_repository_installation_when_launched_then_keep_it_ahead_of_host_assets(self):
        self.marker(self.prepared, 'client/shared_prefs/gamedata.xml')
        for marker in ('ios-current.json', 'static/client/shared_prefs/gamedata.xml',
                       'client/shared_prefs/gamedata.xml'):
            with self.subTest(marker=marker):
                shutil.rmtree(self.data)
                self.data.mkdir()
                self.marker(self.data, marker)
                self.assertEqual(self.launch()['data'], str(self.data))

    def test_given_incomplete_repository_installation_when_launched_then_do_not_switch_content(self):
        self.marker(self.prepared, 'client/shared_prefs/gamedata.xml')
        pointer = self.data / 'ios-current.json'
        pointer.symlink_to('missing-generation.json')
        self.assertEqual(self.launch()['data'], str(self.data))
        pointer.unlink()
        (self.data / 'static').mkdir()
        self.assertEqual(self.launch()['data'], str(self.data))

    def test_given_explicit_data_when_launched_then_override_environment_and_forward_options(self):
        self.marker(self.prepared, 'client/shared_prefs/gamedata.xml')
        explicit = self.checkout / 'chosen data'
        reply = self.launch('--data', explicit, '--slot', 'other', data_env=self.checkout / 'env data')
        self.assertEqual(reply['data'], str(explicit))
        self.assertEqual(reply['extra'], ['--slot', 'other'])

    def test_given_environment_data_when_launched_then_honor_it_even_when_missing(self):
        self.marker(self.prepared, 'client/shared_prefs/gamedata.xml')
        selected = self.checkout / 'chosen data'
        self.assertEqual(self.launch(data_env=selected)['data'], str(selected))

    def test_given_no_installed_assets_when_launched_then_keep_repository_default(self):
        self.prepared.mkdir(parents=True)
        self.assertEqual(self.launch()['data'], str(self.data))

    def _install_recording_entrypoint(self, *, check_code: int, update_code: int = 0):
        self.calls_log = self.checkout / 'calls.log'
        self.entrypoint.write_text(
            'import argparse, json, sys\n'
            'from pathlib import Path\n'
            'parser = argparse.ArgumentParser()\n'
            'parser.add_argument("command")\n'
            'parser.add_argument("--data")\n'
            'args, extra = parser.parse_known_args()\n'
            f'log = Path({repr(str(self.calls_log))})\n'
            'with log.open("a") as f:\n'
            '    f.write(json.dumps(dict(command=args.command, data=args.data, extra=extra)) + "\\n")\n'
            'if args.command == "check-update":\n'
            '    if "--summary" in extra:\n'
            '        print("iOS data update needed", file=sys.stderr)\n'
            f'    raise SystemExit({check_code})\n'
            'if args.command == "update":\n'
            f'    raise SystemExit({update_code})\n'
            'print(json.dumps(dict(command=args.command, data=args.data, extra=extra)))\n'
        )

    def _run_script(self, script: Path, *args, user_input: str = ''):
        env = dict(os.environ)
        env.pop('FFBE_IOS_DATA', None)
        return subprocess.run(
            [str(script), *map(str, args)],
            cwd=self.checkout.parent,
            env=env,
            input=user_input,
            text=True,
            capture_output=True,
            timeout=10,
        )

    def test_given_up_to_date_check_when_launched_then_start_directly_without_prompt(self):
        self.marker(self.prepared, 'client/shared_prefs/gamedata.xml')
        self._install_recording_entrypoint(check_code=0)
        res = self._run_script(self.launcher, user_input='')
        self.assertEqual(res.returncode, 0, res.stderr + res.stdout)
        self.assertNotIn('Update now?', res.stderr + res.stdout)
        calls = [json.loads(line) for line in self.calls_log.read_text().splitlines()]
        self.assertEqual([c['command'] for c in calls], ['check-update', 'start'])

    def test_given_update_needed_and_user_accepts_when_launched_then_update_then_start(self):
        self.marker(self.prepared, 'client/shared_prefs/gamedata.xml')
        for answer in ('y\n', '\n'):
            with self.subTest(answer=repr(answer)):
                if (self.checkout / 'calls.log').exists():
                    (self.checkout / 'calls.log').unlink()
                self._install_recording_entrypoint(check_code=2, update_code=0)
                res = self._run_script(self.launcher, user_input=answer)
                self.assertEqual(res.returncode, 0, res.stderr + res.stdout)
                self.assertIn('Update now?', res.stderr)
                self.assertEqual(json.loads(res.stdout)['command'], 'start')
                calls = [json.loads(line) for line in self.calls_log.read_text().splitlines()]
                self.assertEqual([c['command'] for c in calls], ['check-update', 'update', 'start'])

    def test_given_update_needed_and_user_declines_or_eof_when_launched_then_exit_without_start(self):
        self.marker(self.prepared, 'client/shared_prefs/gamedata.xml')
        for answer in ('n\n', ''):
            with self.subTest(answer=repr(answer)):
                if (self.checkout / 'calls.log').exists():
                    (self.checkout / 'calls.log').unlink()
                self._install_recording_entrypoint(check_code=2)
                res = self._run_script(self.launcher, user_input=answer)
                self.assertEqual(res.returncode, 0, res.stderr + res.stdout)
                self.assertIn('Update Exvius iOS Data.command', res.stderr)
                calls = [json.loads(line) for line in self.calls_log.read_text().splitlines()]
                self.assertEqual([c['command'] for c in calls], ['check-update'])

    def test_given_update_needed_and_update_fails_when_launched_then_do_not_start_and_exit_nonzero(self):
        self.marker(self.prepared, 'client/shared_prefs/gamedata.xml')
        self._install_recording_entrypoint(check_code=2, update_code=1)
        res = self._run_script(self.launcher, user_input='y\n')
        self.assertNotEqual(res.returncode, 0)
        calls = [json.loads(line) for line in self.calls_log.read_text().splitlines()]
        self.assertEqual([c['command'] for c in calls], ['check-update', 'update'])

    def test_given_update_launcher_when_invoked_then_run_update_with_resolved_data(self):
        self.marker(self.prepared, 'client/shared_prefs/gamedata.xml')
        self._install_recording_entrypoint(check_code=0, update_code=0)
        res = self._run_script(self.updater, '--archive-dir', self.checkout / 'archives')
        self.assertEqual(res.returncode, 0, res.stderr + res.stdout)
        calls = [json.loads(line) for line in self.calls_log.read_text().splitlines()]
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]['command'], 'update')
        self.assertEqual(calls[0]['data'], str(self.prepared))
        self.assertEqual(calls[0]['extra'], ['--archive-dir', str(self.checkout / 'archives')])


if __name__ == '__main__':
    unittest.main()
