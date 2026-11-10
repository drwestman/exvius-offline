"""Serve exact verified table bytes; ordinary asset routing stays with the engine."""


def serve(handler, snapshot, relative):
    if handler.command not in ('GET', 'HEAD'):
        return False
    if snapshot is None or snapshot.manifest['version'] != 3:
        return False
    if not relative.startswith(('mst/', 'localized_texts/en/')):
        return False
    raw = snapshot.lookup(relative)
    handler.send_response(200 if raw is not None else 404)
    handler.send_header('Content-Type', 'application/octet-stream')
    handler.send_header('Content-Length', str(len(raw)) if raw is not None else '0')
    handler.send_header('Cache-Control', 'no-store')
    handler.send_header('Connection', 'close')
    handler.end_headers()
    if raw is not None and handler.command != 'HEAD':
        handler.wfile.write(raw)
    handler.close_connection = True
    return True
