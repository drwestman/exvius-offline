"""BDD for Finder/Terminal gameplay data selection, without starting a server."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


LAUNCHER = Path(__file__).resolve().parents[2] / 'Play Exvius on iPhone.command'


class IPhoneLauncher(unittest.TestCase):
    def setUp(self):
        work = tempfile.TemporaryDirectory(prefix='ios launcher ')
        self.addCleanup(work.cleanup)
        self.checkout = Path(work.name) / 'checkout with spaces'
        entrypoint = self.checkout / 'source/exvius/macos_ios_server.py'
        entrypoint.parent.mkdir(parents=True)
        entrypoint.write_text(
            'import argparse, json\n'
            'parser = argparse.ArgumentParser()\n'
            'parser.add_argument("command")\n'
            'parser.add_argument("--data")\n'
            'args, extra = parser.parse_known_args()\n'
            'print(json.dumps(dict(command=args.command, data=args.data, extra=extra)))\n')
        self.launcher = self.checkout / LAUNCHER.name
        shutil.copy2(LAUNCHER, self.launcher)
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


if __name__ == '__main__':
    unittest.main()
