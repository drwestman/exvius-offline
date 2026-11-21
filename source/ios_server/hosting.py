"""Prepared gameplay application; transport owns its runtime lease and listeners."""
from contextlib import redirect_stdout
import sys


class Gameplay:
    def __init__(self, config):
        self.config = config
        self.engine = None
        self.handler = None

    def configuration(self):
        return {'data': str(self.config.data), 'content': str(self.config.content_root), 'slot': self.config.slot}

    def preflight(self):
        """Reject uninitialized saves before engine import; Engine owns asset validation."""
        from ios_server.queries import _saved
        from replay_calendar import read_anchor
        data = _saved(self.config)
        if data is None or read_anchor(data) is None:
            raise ValueError('Initialize this iOS campaign with init-campaign before gameplay hosting.')

    def start(self, lease):
        self.preflight()
        from ios_server.engine import Engine
        from ios_server.game_http import handler
        self.engine = Engine(self.config, prepared=True)
        with redirect_stdout(sys.stderr):
            server = self.engine.initialize(lease=lease)
        self.handler = handler(server.Handler, reports=self.engine.reports)
        self.maintain()
        return self.handler

    def maintain(self):
        if self.engine is not None and self.engine.server is not None:
            from ios_server.request_retention import prune
            with self.engine.server.STATE_LOCK:
                prune(self.config.root)
                self.engine.reports.prune()

    def describe(self):
        if self.engine is None or self.engine.tables is None:
            return {}
        return {'slot': self.config.slot, 'content_root': str(self.config.content_root),
                'table_generation': self.engine.tables.manifest['generation'],
                'client_reports': self.engine.reports.enabled}

    def close(self):
        if self.engine is not None:
            self.engine.close()
            self.engine = None
        self.handler = None
