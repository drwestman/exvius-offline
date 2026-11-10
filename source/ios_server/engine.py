"""Command adapter for the canonical engine; hosting owns this adapter for its lifetime.

Configuration/queries do not import this module. Initialization takes the private
instance lock before importing modules that bind paths or loading any campaign.
"""
import importlib
import os
import sys

from engine_profile import select_profile
from ios_server.runtime import InstanceLock


class Engine:
    def __init__(self, config, *, prepared=False, import_module=importlib.import_module):
        if type(prepared) is not bool:
            raise ValueError('Prepared engine delivery must be explicitly enabled or disabled.')
        self.config = config
        self.import_module = import_module
        self.server = None
        self._lock = None
        self.prepared = prepared
        self.tables = None
        self.banners = None

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
        self._lock = InstanceLock(self.config.root)
        self._lock.__enter__()
        try:
            if self.prepared:
                from ios_server.preparation import open_prepared
                self.tables = open_prepared(self.config)
                from ios_server.banner_snapshots import current
                self.banners = current(self.config)
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
            if self.tables is not None:
                server.State.native_tables = self.tables
                server.State.native_banners = self.banners
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
        if self.server is not None and self.tables is not None:
            self.server.State.native_tables = None
            self.server.State.native_banners = None
        self.tables = None
        self.banners = None
        if self._lock is not None:
            self._lock.__exit__()
            self._lock = None
        self.server = None
