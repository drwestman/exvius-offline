"""Public hello/profile routes only. This transport has no game-engine or file-serving adapter."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from urllib.parse import urlsplit

from ios_server.certificates import ROOT_NAME


def pages(snapshot, secure):
    http = snapshot['setup_url']
    https = snapshot['hello_url']
    if secure:
        title = 'Secure connection successful'
        gameplay = snapshot.get('mode') == 'gameplay'
        readiness = ('Gameplay hosting is ready. You can open the game.' if gameplay else
                     'Your iPhone-to-Mac connection is ready. Gameplay is still being integrated.')
        content = f'''<span class="badge success">HTTPS · Connected</span>
<h1>{title}</h1>
<p>HTTPS reached your Mac.</p>
<p>If Safari opened this page without a certificate warning, your certificate
trust check is complete.</p>
<dl><dt>Connection</dt><dd>Encrypted HTTPS</dd>
<dt>Mac address</dt><dd>{snapshot['lan_address']}</dd></dl>
<p>{readiness}</p>
<p><a href="{http}">Review the setup instructions</a></p>'''
    else:
        title = 'Set up your iPhone connection'
        content = f'''<span class="badge">HTTP · Setup</span>
<h1>{title}</h1><p>Your iPhone reached the Mac over HTTP.</p>
<ol><li>In your iPhone’s Wi-Fi settings, set Configure DNS to Manual and use only
<strong>{snapshot['lan_address']}</strong> for this home network.</li>
<li><a href="/ca.mobileconfig">Download the certificate profile</a>, then open Settings →
General → VPN &amp; Device Management and install “Exvius Offline iPhone Connection”.</li>
<li>Open Settings → General → About → Certificate Trust Settings and enable full trust for
<strong>{ROOT_NAME}</strong>.</li></ol>
<a class="button" href="{https}">Check the secure connection</a>
<p>The secure page will show <strong>Secure connection successful</strong>.</p>'''
    return (f'''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} · Exvius</title>
<style>body{{font:17px -apple-system,BlinkMacSystemFont,sans-serif;background:#101b2c;color:#edf4ff;
max-width:640px;margin:48px auto;padding:0 24px;line-height:1.6}}h1{{line-height:1.2}}
a{{color:#85d9ff}}.button{{display:block;background:#245780;border-radius:10px;padding:14px;
margin:16px 0;color:white;text-decoration:none}}small{{color:#b6c8dc}}li{{margin-bottom:12px}}
.badge{{display:inline-block;border-radius:6px;padding:4px 10px;background:#24364e;font-weight:600}}
.success{{background:#163d32;color:#86efac}}dl{{border-left:3px solid #86efac;padding-left:18px}}
dt{{color:#b6c8dc;font-size:14px}}dd{{margin:0 0 12px}}</style>
{content}
<small>Keep the Mac awake and this server running. When you stop it, restore the iPhone’s
Wi-Fi DNS to Automatic. Setup page: {http}</small></html>''').encode()


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def get_request(self):
        peer, address = super().get_request()
        peer.settimeout(getattr(self, 'request_timeout', 3))
        try:
            # Defer the handshake to the request thread so a slow client cannot block accepts.
            if self.tls_context is not None:
                peer = self.tls_context.wrap_socket(peer, server_side=True, do_handshake_on_connect=False)
            return peer, address
        except BaseException:
            peer.close()
            raise

    def verify_request(self, request, address):
        return self.network.allows(address[0])

    def handle_error(self, request, client_address):
        self.log('HTTP/TLS client connection failed; check certificate trust and the requested hostname.')


class PublicHandler(BaseHTTPRequestHandler):
    server_version = 'ExviusConnectivity/1'

    def log_message(self, *_):
        pass  # No request bodies, host headers or browsing history in logs.

    def send_body(self, status, body, content_type, filename=None):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        if filename:
            self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(body)
        self.close_connection = True

    def do_GET(self):
        path = urlsplit(self.path).path
        if path in ('/', '/__exvius/hello'):
            body = pages(self.server.snapshot(), self.server.tls_context is not None)
            self.send_body(200, body, 'text/html; charset=utf-8')
        elif path in ('/ca.mobileconfig', '/__exvius/ca.mobileconfig'):
            self.send_body(200, self.server.profile, 'application/x-apple-aspen-config', 'exvius-ios.mobileconfig')
        elif path in ('/ca.crt', '/__exvius/ca.crt'):
            self.send_body(200, self.server.ca_der, 'application/x-x509-ca-cert', 'exvius-ios-root.cer')
        else:
            self.send_body(404, b'Not found.', 'text/plain')

    do_HEAD = do_GET

    def do_POST(self):
        self.send_body(503, b'Connection check only. Gameplay is not enabled yet.', 'text/plain')


class ControlHandler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def respond(self, body):
        data = json.dumps(body).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == '/status':
            self.respond(self.server.snapshot())
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path == '/stop':
            self.server.stop_event.set()
            self.respond({'stopping': True})
        else:
            self.send_error(404)
