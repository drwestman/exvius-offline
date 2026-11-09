"""Command adapter for the canonical engine; hosting owns this adapter for its lifetime.

Configuration/queries do not import this module. Initialization takes the private
instance lock before importing modules that bind paths or loading any campaign.
"""
import errno
import fcntl
import importlib
import os
import sys

from engine_profile import select_profile


class Engine:
    def __init__(self, config, *, import_module=importlib.import_module):
        self.config = config
        self.import_module = import_module
        self.server = None
        self._lock = None

    def initialize(self):
        if self.server is not None:
            return self.server
        if sys.version_info[:2] != (3, 12):
            raise RuntimeError('The iOS engine requires Python 3.12; use the prepared iOS environment.')
        missing = self.config.missing_data()
        if missing:
            raise ValueError('Game data is missing: ' + ', '.join(missing))
        if 'data_paths' in sys.modules:
            raise RuntimeError('The engine paths are already bound; initialize iOS in a fresh process.')
        select_profile('ios-revival')
        env = self.config.engine_environment()
        self.config.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        lock_path = self.config.root / 'instance.lock'
        if not lock_path.resolve().is_relative_to(self.config.root):
            raise ValueError('The iOS instance lock escapes the private runtime root.')
        lock = lock_path.open('a+b')
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            lock.close()
            if exc.errno in (errno.EAGAIN, errno.EACCES):
                raise RuntimeError('Another iOS instance owns this runtime; stop it before changing the campaign.') from None
            raise
        self._lock = lock
        try:
            os.environ.update(env)
            # These catalogue defaults are already supported by the canonical engine.
            # Later ports add revival families behind the immutable iOS profile.
            os.environ.update({
                'GACHA_ONLY': 'all', 'GACHA_CAMPAIGN': 'all',
                'EXVIUS_SUMMON_ARCHIVE': '1', 'EXVIUS_EVENT_ARCHIVE': '1',
                'GACHA_STANDARD': '1', 'GACHA_CATALOGUE': '1', 'ANNIVERSARY_TICKET': '0', 'STATE': '1',
            })
            server = self.import_module('capture_server')
            result = server.main(['--data', str(self.config.root), '--state', self.config.slot,
                                  '--state-file', str(self.config.state_file), '--state-mode', 'live'],
                                 in_process=True)
            if result != 0:
                raise RuntimeError(f'Game engine initialization failed ({result}).')
            self.server = server
            return server
        except BaseException:
            self.close()
            raise

    def initialize_campaign(self) -> bool:
        server = self.initialize()
        from revival_campaign import initialize_campaign
        with server.STATE_LOCK:
            return initialize_campaign(server.State, self.config.state_file)

    def close(self):
        """Release resources; the bound engine still requires a fresh process to reconfigure."""
        if self._lock is not None:
            self._lock.close()
            self._lock = None
        self.server = None
