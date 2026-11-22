"""Serve exact verified tables/packs; ordinary asset routing stays with the engine."""
CHUNK = 256 * 1024


def serve(handler, snapshot, relative):
    if handler.command not in ('GET', 'HEAD'):
        return False
    if snapshot is None or snapshot.manifest['version'] not in (3, 4, 5, 6):
        return False
    if getattr(snapshot, 'upfront', None) is not None and snapshot.upfront.owns(relative):
        return _serve_upfront(handler, snapshot.upfront, relative)
    from ios_server.native_sounds import owns as sound_path
    if snapshot.sounds is not None and sound_path(relative):
        return _serve_sound(handler, snapshot.sounds, relative)
    if not relative.startswith(('mst/', 'localized_texts/en/')):
        from ios_server.vortex_art import owns
        if 'packs' not in snapshot.manifest or not owns(relative):
            return False
    raw = snapshot.lookup(relative)
    return _reply(handler, raw)


def _serve_upfront(handler, upfront, relative):
    if handler.command == 'HEAD':
        try:
            size = upfront.verified_size(relative)
        except (OSError, ValueError):
            return _reply(handler, None, 500)
        return _reply_head(handler, 404 if size is None else 200, size or 0)
    try:
        ctx = upfront.open_verified(relative)
        opened = ctx.__enter__()
    except (OSError, ValueError):
        return _reply(handler, None, 500)
    try:
        if opened is None:
            return _reply(handler, None, 404)
        stream, size = opened
        handler.send_response(200)
        handler.send_header('Content-Type', 'application/octet-stream')
        handler.send_header('Content-Length', str(size))
        handler.send_header('Cache-Control', 'no-store')
        handler.send_header('Connection', 'close')
        handler.end_headers()
        while True:
            block = stream.read(CHUNK)
            if not block:
                break
            handler.wfile.write(block)
        handler.close_connection = True
        return True
    finally:
        ctx.__exit__(None, None, None)


def _serve_sound(handler, sounds, relative):
    head = handler.command == 'HEAD'
    try:
        result = sounds.verified_size(relative) if head else sounds.read(relative)
    except (OSError, ValueError):
        return _reply(handler, None, 500)
    if head:
        return _reply_head(handler, 404 if result is None else 200, result or 0)
    return _reply(handler, result)


def _reply_head(handler, status, length):
    return _send(handler, status, length, None)


def _reply(handler, raw, status=None):
    return _send(handler, status if status is not None else 200 if raw is not None else 404,
                 len(raw) if raw is not None else 0, raw)


def _send(handler, status, length, raw):
    handler.send_response(status)
    handler.send_header('Content-Type', 'application/octet-stream')
    handler.send_header('Content-Length', str(length))
    handler.send_header('Cache-Control', 'no-store')
    handler.send_header('Connection', 'close')
    handler.end_headers()
    if raw is not None and handler.command != 'HEAD':
        handler.wfile.write(raw)
    handler.close_connection = True
    return True
