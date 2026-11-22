"""Serve exact verified tables/packs; ordinary asset routing stays with the engine."""
from contextlib import ExitStack

from ios_server.verified_blob import CHUNK


def serve(handler, snapshot, relative):
    if handler.command not in ('GET', 'HEAD'):
        return False
    if snapshot is None or snapshot.manifest['version'] not in (3, 4, 5, 6):
        return False
    if getattr(snapshot, 'upfront', None) is not None and snapshot.upfront.owns(relative):
        return _serve_verified(handler, snapshot.upfront, relative)
    from ios_server.native_sounds import owns as sound_path
    if snapshot.sounds is not None and sound_path(relative):
        return _serve_verified(handler, snapshot.sounds, relative)
    if not relative.startswith(('mst/', 'localized_texts/en/')):
        from ios_server.vortex_art import owns
        if 'packs' not in snapshot.manifest or not owns(relative):
            return False
    raw = snapshot.lookup(relative)
    return _reply(handler, raw)


def _serve_verified(handler, source, relative):
    """One delivery path for every VerifiedBlobSource (upfront CPKs, sound banks)."""
    if handler.command == 'HEAD':
        try:
            size = source.verified_size(relative)
        except (OSError, ValueError):
            return _reply(handler, None, 500)
        return _reply_head(handler, 404 if size is None else 200, size or 0)
    return _stream_verified(handler, source.open_verified(relative))


def _stream_verified(handler, context):
    """Verify before headers, then write bounded chunks from the verified descriptor."""
    with ExitStack() as stack:
        try:
            opened = stack.enter_context(context)
        except (OSError, ValueError):
            return _reply(handler, None, 500)
        if opened is None:
            return _reply(handler, None, 404)
        stream, size = opened
        handler.send_response(200)
        handler.send_header('Content-Type', 'application/octet-stream')
        handler.send_header('Content-Length', str(size))
        handler.send_header('Cache-Control', 'no-store')
        handler.send_header('Connection', 'close')
        handler.end_headers()
        remaining = size
        while remaining:
            block = stream.read(min(CHUNK, remaining))
            if not block:
                break
            handler.wfile.write(block)
            remaining -= len(block)
        handler.close_connection = True
        return True


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
