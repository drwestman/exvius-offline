"""Read-only native fitted-image delivery; never load sources or resize on a GET."""
from ios_server.banner_snapshots import owned_name


def serve(handler, snapshot, relative):
    if snapshot is None or handler.command not in ('GET', 'HEAD'):
        return False
    from ios_server.home_banners import owns
    if owned_name(relative) is None and not (getattr(snapshot, 'home', None) is not None and owns(relative)):
        return False
    raw = snapshot.lookup(relative)
    handler.send_response(200 if raw is not None else 404)
    handler.send_header('Content-Type', 'image/png')
    handler.send_header('Content-Length', str(len(raw)) if raw is not None else '0')
    handler.send_header('Cache-Control', 'public, max-age=31536000, immutable' if raw is not None else 'no-store')
    handler.send_header('Connection', 'close')
    handler.end_headers()
    if raw is not None and handler.command == 'GET':
        handler.wfile.write(raw)
    handler.close_connection = True
    return True
