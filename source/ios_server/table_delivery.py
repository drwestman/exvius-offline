"""Serve exact verified tables/packs; ordinary asset routing stays with the engine."""


def serve(handler, snapshot, relative):
    if handler.command not in ('GET', 'HEAD'):
        return False
    if snapshot is None or snapshot.manifest['version'] not in (3, 4, 5):
        return False
    from ios_server.native_sounds import owns as sound_path
    if snapshot.sounds is not None and sound_path(relative):
        try:
            raw = snapshot.sounds.read(relative)
        except (OSError, ValueError):
            return _reply(handler, None, 500)
        return _reply(handler, raw)
    if not relative.startswith(('mst/', 'localized_texts/en/')):
        from ios_server.vortex_art import owns
        if 'packs' not in snapshot.manifest or not owns(relative):
            return False
    raw = snapshot.lookup(relative)
    return _reply(handler, raw)


def _reply(handler, raw, status=None):
    handler.send_response(status if status is not None else 200 if raw is not None else 404)
    handler.send_header('Content-Type', 'application/octet-stream')
    handler.send_header('Content-Length', str(len(raw)) if raw is not None else '0')
    handler.send_header('Cache-Control', 'no-store')
    handler.send_header('Connection', 'close')
    handler.end_headers()
    if raw is not None and handler.command != 'HEAD':
        handler.wfile.write(raw)
    handler.close_connection = True
    return True
