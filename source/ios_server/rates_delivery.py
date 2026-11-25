"""Bounded native WebView transport for the existing read-only rates renderer."""
from urllib.parse import parse_qs, urlsplit

from ios_server.native_tables import RATE_URL

PATH = urlsplit(RATE_URL).path
MAX_FORM = 64 * 1024


def owns(path):
    return urlsplit(path).path == PATH


def banner_id(handler):
    """Read this request only; never retain form fields on a reused handler."""
    query = urlsplit(handler.path).query
    if len(query) > MAX_FORM:
        raise OverflowError('Rates query too large')
    fields = parse_qs(query, keep_blank_values=True, max_num_fields=128)
    if handler.command == 'POST':
        sizes = handler.headers.get_all('Content-Length', [])
        if (len(sizes) != 1 or not sizes[0].isascii() or not sizes[0].isdigit()
                or handler.headers.get('Transfer-Encoding') is not None):
            raise ValueError('Invalid rates body length')
        length = int(sizes[0])
        if length + len(query) > MAX_FORM:
            raise OverflowError('Rates form too large')
        # Match the native/reference form reader; its fields need no MIME label.
        raw = handler.rfile.read(length)
        if len(raw) != length:
            raise ValueError('Truncated rates form')
        for key, values in parse_qs(raw.decode('utf-8'), keep_blank_values=True, max_num_fields=128).items():
            fields.setdefault(key, []).extend(values)
    values = {value for value in fields.get('gacha_id', []) if value}
    if not values:
        return None
    if len(values) != 1:
        raise ValueError('Conflicting rates banner IDs')
    value = values.pop()
    if len(value) > 20 or not value.isascii() or not value.isdigit():
        raise ValueError('Invalid rates banner ID')
    return value


def serve(handler):
    """Called under the canonical state lock; no command dispatch or persistence."""
    from gacha_rates import index_page, page
    selected = None
    try:
        selected = banner_id(handler)
    except (ValueError, OverflowError) as exc:
        code = 413 if isinstance(exc, OverflowError) else 400
        html = '<!doctype html><html><body><p>Drop rates could not be loaded.</p></body></html>'
    else:
        html = index_page() if selected is None else page(selected)
        code = 200 if html is not None else 404
        if html is None:
            html = '<!doctype html><html><body><p>This summon is unavailable.</p></body></html>'
    data = html.encode('utf-8')
    handler.send_response(code)
    handler.send_header('Content-Type', 'text/html; charset=utf-8')
    handler.send_header('Cache-Control', 'no-store')
    handler.send_header('Content-Length', str(len(data)))
    handler.end_headers()
    if handler.command != 'HEAD':
        handler.wfile.write(data)
    print(f'DROP-RATES {handler.command} banner={selected or "index"} -> {code} {len(data)} B', flush=True)
