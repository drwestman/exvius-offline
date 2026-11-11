"""Compose public setup routes with the canonical encrypted game handler."""
from urllib.parse import unquote, urlsplit

from ios_server.http import PublicHandler

PUBLIC = frozenset(('/', '/__exvius/hello', '/ca.mobileconfig', '/__exvius/ca.mobileconfig',
                    '/ca.crt', '/__exvius/ca.crt'))
MAX_BODY = 4 * 1024 * 1024


def handler(base):
    class GameHandler(base, PublicHandler):
        def end_headers(self):
            self.send_header('Connection', 'close')
            self.close_connection = True
            super().end_headers()

        def route(self):
            try:
                return unquote(urlsplit(self.path).path)
            except ValueError:
                return ''

        def do_GET(self):
            route = self.route()
            if route in PUBLIC:
                return PublicHandler.do_GET(self)
            if not route.startswith('/') or route.startswith('/__exvius/'):
                return self.send_body(404, b'Not found.', 'text/plain')
            return base.do_HEAD(self) if self.command == 'HEAD' else base.do_GET(self)

        do_HEAD = do_GET

        def body_length(self):
            values = self.headers.get_all('Content-Length', [])
            if (len(values) != 1 or self.headers.get('Transfer-Encoding') is not None
                    or not values[0].isascii() or not values[0].isdigit()):
                self.send_body(400, b'Expected one Content-Length.', 'text/plain')
                return False
            if int(values[0]) > MAX_BODY:
                self.send_body(413, b'Request body too large.', 'text/plain')
                return False
            return True

        def handle_expect_100(self):
            return super().handle_expect_100() if self.body_length() else False

        def do_POST(self):
            route = self.route()
            if route in PUBLIC or not route.startswith('/') or route.startswith('/__exvius/'):
                return self.send_body(404, b'Not found.', 'text/plain')
            if not self.body_length():
                return
            return base.do_POST(self)

    return GameHandler
