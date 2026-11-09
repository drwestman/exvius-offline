"""Read-only path configuration, independent of engine imports and legacy env overrides."""
from dataclasses import dataclass
from pathlib import Path
import re


def default_root() -> Path:
    return Path.home() / 'Library/Application Support/Exvius Offline/iOS'


def default_data() -> Path:
    return Path(__file__).resolve().parents[2] / 'data'


@dataclass(frozen=True)
class Configuration:
    root: Path
    data: Path
    slot: str = 'campaign'

    def __post_init__(self):
        object.__setattr__(self, 'root', Path(self.root).expanduser().resolve())
        object.__setattr__(self, 'data', Path(self.data).expanduser().resolve())
        if self.root.is_relative_to(self.data) or self.data.is_relative_to(self.root):
            raise ValueError('Private iOS runtime and shared game data must use separate directory trees.')
        if not re.fullmatch(r'[A-Za-z0-9_-]+', self.slot):
            raise ValueError('Invalid iOS save slot; use letters, numbers, underscores or hyphens.')

    @property
    def state_file(self) -> Path:
        path = self.root / 'state' / (self.slot + '.json')
        if not path.resolve().is_relative_to(self.root):
            raise ValueError('The iOS save path escapes the private runtime root.')
        return path

    @property
    def managed(self) -> bool:
        return (self.data / 'static').is_dir()

    def engine_environment(self) -> dict[str, str]:
        """Resolve either supported content layout; creating directories is a command's job."""
        static = self.data / 'static' if self.managed else self.data
        native = self.data / 'native' if self.managed else static / 'client/files'
        paths = {
            'MST_DIR': static / 'mst_decoded', 'TEXT_DIR': static / 'text_decoded',
            'ART_ROOT': static / 'cpk_extract', 'COMMUNITY_ART_ROOT': static / 'gacha_community/art',
            'VERSION_TABLE_XML': static / 'client/shared_prefs/gamedata.xml',
            'CDN_ROOT': native, 'CDN_OVERLAY': native if self.managed else static / 'overlay',
        }
        for path in paths.values():
            if not path.resolve().is_relative_to(self.data):
                raise ValueError(f'Content path escapes the shared data root: {path}')
        private = {'FFBE_IOS_ROOT': self.root, 'STATE_FILE': self.state_file,
                   'OUT_REQUESTS': self.root / 'requests'}
        for path in private.values():
            if not path.resolve().is_relative_to(self.root):
                raise ValueError(f'Private iOS path escapes the runtime root: {path}')
        return {'FFBE_DATA': str(self.root), 'FFBE_IOS_CONTENT_ROOT': str(self.data),
                **{k: str(v) for k, v in paths.items()},
                **{k: str(v) for k, v in private.items()}}

    def missing_data(self) -> list[str]:
        env = self.engine_environment()
        directories = [Path(env[key]) for key in ('MST_DIR', 'TEXT_DIR')]
        directories += [Path(env['CDN_ROOT']) / relative for relative in ('mst', 'common_lang')]
        missing = [str(path) for path in directories if not path.is_dir()]
        version = Path(env['VERSION_TABLE_XML'])
        if not version.is_file():
            missing.append(str(version))
        return missing
