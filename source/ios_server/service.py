"""Foreground connectivity lifecycle: bind everything, start, report ready, then stop together."""
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import socketserver
import ssl
import stat
import threading

from dnslib.server import DNSServer, DNSLogger

from ios_server.certificates import CertificateStore, HELLO_HOST
from ios_server.dns import Handler as DnsHandler, Resolver, RestrictedTCP, RestrictedUDP
from ios_server.http import ControlHandler, PublicHandler, Server
from ios_server.runtime import InstanceLock, private_path


class Listener:
    def __init__(self, name, server):
        self.name, self.server, self.thread = name, server, None

    def start(self):
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       kwargs={'poll_interval': .05}, name='ios-' + self.name, daemon=True)
        self.thread.start()

    def stop(self):
        if self.thread is not None and self.thread.is_alive():
            self.server.shutdown()
            self.thread.join(timeout=2)

    def close(self):
        self.stop()
        self.server.server_close()
        if self.thread is not None:
            self.thread.join(timeout=2)


class ControlServer(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True

    def get_request(self):
        request, address = super().get_request()
        request.settimeout(3)
        return request, address

    def handle_error(self, *_):
        pass


class Service:
    def __init__(self, root, network, *, forward=None, application=None):
        self.root, self.network = Path(root).resolve(), network
        if application is not None and application.config.root != self.root:
            raise ValueError('Gameplay and transport must share the same private runtime.')
        self.application = application
        self.store = CertificateStore(self.root)
        self.stop_event = threading.Event()
        self.listeners = []
        self.ports = {}
        self.lock = None
        self.logger = None
        self.log_handler = None
        self.forward = forward
        self.resolver = None
        self.ready = False
        self.owns_control = False

    def log(self, message):
        if self.logger:
            self.logger.warning(message)

    def _context(self):
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(str(self.store.leaf))
        return context

    def _bind(self, name):
        server = None
        try:
            if name.startswith('DNS'):
                tcp = name == 'DNS TCP'
                port = self.network.dns_port if tcp else self.ports['dns']
                server = DNSServer(self.resolver, address=self.network.bind, port=port, tcp=tcp,
                                   handler=DnsHandler, logger=DNSLogger(log='error', logf=self.log),
                                   server=RestrictedTCP if tcp else RestrictedUDP).server
                server.daemon_threads = True
                self.ports['dns'] = server.server_address[1]
            elif name in ('HTTP', 'HTTPS'):
                secure = name == 'HTTPS'
                port = self.network.https_port if secure else self.network.http_port
                server = Server((self.network.bind, port), PublicHandler)
                server.network = self.network
                server.tls_context = self.context if secure else None
                server.snapshot = self.snapshot
                server.profile = self.profile
                server.ca_der = self.ca_der
                server.log = self.log
                if self.application is not None:
                    server.daemon_threads = False  # server_close drains game requests before the lease is released
                    server.request_timeout = 30
                self.ports[name.lower()] = server.server_address[1]
            else:
                path = private_path(self.root, 'control.sock')
                if path.exists():
                    if not stat.S_ISSOCK(path.lstat().st_mode):
                        raise ValueError(f'The private control path contains a non-socket file: {path}')
                    path.unlink()  # stale socket; the instance lock is already exclusively held
                server = ControlServer(str(path), ControlHandler)
                self.owns_control = True
                path.chmod(0o600)
                server.snapshot = self.snapshot
                server.stop_event = self.stop_event
            return Listener(name, server)
        except BaseException:
            if server is not None:
                server.server_close()
            raise

    def _prepare(self):
        certificates = self.store.inspect()
        if not certificates['ok']:
            raise ValueError('iOS certificates are missing or invalid. Run macos_ios_server.py setup first.')
        self.context = self._context()
        self.profile = self.store.profile.read_bytes()
        self.ca_der = self.store.path('ca.crt').read_bytes()
        folder = private_path(self.root, 'logs')
        folder.mkdir(exist_ok=True, mode=0o700)
        log_file = private_path(self.root, 'logs/connectivity.log')
        self.logger = logging.Logger('exvius-ios-connectivity')
        self.log_handler = RotatingFileHandler(log_file, maxBytes=1024 * 1024, backupCount=2)
        self.log_handler.setFormatter(logging.Formatter('%(asctime)s %(message)s'))
        self.logger.addHandler(self.log_handler)
        self.resolver = Resolver(self.network, forward=self.forward, log=self.log)

    def start(self):
        if self.ready:
            return self.snapshot()
        self.lock = InstanceLock(self.root)
        self.lock.__enter__()
        try:
            self._prepare()
            # Constructors bind synchronously. No readiness announcement until all succeed.
            for name in ('DNS TCP', 'DNS UDP', 'HTTP', 'HTTPS', 'control'):
                try:
                    listener = self._bind(name)
                except OSError as exc:
                    raise OSError(f'{name} listener could not bind: {exc}. Stop the conflicting service or choose another port.') from exc
                self.listeners.append(listener)
            if self.application is not None:
                handler = self.application.start(self.lock)
                for listener in self.listeners:
                    if listener.name in ('HTTP', 'HTTPS'):
                        listener.server.RequestHandlerClass = handler
            for listener in self.listeners:
                listener.start()
            self.ready = True
            return self.snapshot()
        except BaseException:
            self.close()
            raise

    def snapshot(self):
        ready = self.ready and all(listener.thread and listener.thread.is_alive() for listener in self.listeners)
        http_port, https_port = self.ports.get('http', self.network.http_port), self.ports.get('https', self.network.https_port)
        http_suffix, https_suffix = ('' if http_port == 80 else f':{http_port}'), ('' if https_port == 443 else f':{https_port}')
        return {'mode': 'gameplay' if self.application is not None else 'connectivity-check',
                'ready': bool(ready), 'hosting': 'running' if ready else 'stopped',
                'lan_address': self.network.address, 'lan_subnet': self.network.subnet,
                'upstream_dns': self.network.upstream, 'ports': dict(self.ports),
                'configuration': self.configuration(),
                'setup_url': f'http://{self.network.address}{http_suffix}/',
                'hello_url': f'https://{HELLO_HOST}{https_suffix}/__exvius/hello',
                'dns_failures': self.resolver.failures if self.resolver else 0,
                'certificates': self.store.inspect(),
                **({'gameplay': self.application.describe()} if self.application is not None else {})}

    def configuration(self):
        return {**self.network.configuration(),
                **({'gameplay': self.application.configuration()} if self.application is not None else {})}

    def maintain(self, *, now=None):
        if self.application is not None:
            self.application.maintain()
        info = self.store.inspect(now=now)
        if not info['ok'] or info.get('renewal_due'):
            self.store.prepare(now=now)
            context = self._context()
            for listener in self.listeners:
                if listener.name == 'HTTPS':
                    listener.server.tls_context = context
            self.context = context
            self.log('Renewed and reloaded the server certificate; the trusted root is unchanged.')
        if not self.snapshot()['ready']:
            raise RuntimeError('A required iOS listener stopped unexpectedly.')

    def close(self):
        self.ready = False
        # Stop every accept loop before any server_close waits for game responses.
        for listener in reversed(self.listeners):
            listener.stop()
        for listener in reversed(self.listeners):
            try:
                listener.close()
            except OSError as exc:
                self.log(f'Listener cleanup failed ({listener.name}): {exc}')
        self.listeners.clear()
        if self.owns_control:
            private_path(self.root, 'control.sock').unlink(missing_ok=True)
            self.owns_control = False
        if self.log_handler:
            self.log_handler.close()
            self.logger.removeHandler(self.log_handler)
            self.log_handler = None
        if self.application is not None:
            self.application.close()
        if self.lock:
            self.lock.__exit__()
            self.lock = None
