"""Pure native table codecs: CBC JSON masters and ECB localized text records.

Wire facts follow the pinned revival ios_tables/ios_texts implementations.
Preserve each source line's padding shape and emit LF between encrypted lines.
"""
import base64
import copy
import json

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from ffbe_crypto import cbc_decrypt, cbc_encrypt, key16


def master_rows(raw, key):
    rows = []
    for line in raw.decode('ascii').splitlines():
        if not line.strip():
            continue
        base64.b64decode(line.strip(), validate=True)
        plain = cbc_decrypt(key16(key), line.strip())
        pad = plain[-1] if plain else 0
        double = 1 <= pad <= 16 and plain[-pad:] == bytes([pad]) * pad
        row = json.loads(plain[:-pad] if double else plain)
        if not isinstance(row, dict):
            raise ValueError('Native master row must be a JSON object.')
        rows.append((line.strip(), row, double))
    if not rows:
        raise ValueError('Native master table has no rows.')
    return rows


def patch_master(raw, key, transform):
    out, changed = [], 0
    for line, row, double in master_rows(raw, key):
        result = transform(copy.deepcopy(row))
        if result != row:
            changed += 1
            if result is None:
                continue
            line = cbc_encrypt(key16(key), json.dumps(result, ensure_ascii=False,
                separators=(',', ':')).encode(), double_pad=double)
        out.append(line)
    return ('\n'.join(out) + '\n').encode('ascii'), changed


def _ecb(key, data, encrypt=False):
    cipher = Cipher(algorithms.AES(key16(key)), modes.ECB())
    op = cipher.encryptor() if encrypt else cipher.decryptor()
    return op.update(data) + op.finalize()


def _pad(data, layers):
    for _ in range(layers):
        n = 16 - len(data) % 16
        data += bytes([n]) * n
    return data


def text_lines(raw, key):
    rows = []
    for line in raw.decode('ascii').splitlines():
        if not line.strip():
            continue
        plain = _ecb(key, base64.b64decode(line.strip(), validate=True))
        layers = 0
        while plain and 1 <= plain[-1] <= 16 and plain[-plain[-1]:] == bytes([plain[-1]]) * plain[-1]:
            plain = plain[:-plain[-1]]
            layers += 1
        if layers not in (1, 2):
            raise ValueError('Unsupported native text padding.')
        records = plain.decode('utf-8').splitlines()
        if not records or any(len(record.split('^')) < 2 or not record.split('^')[0] for record in records):
            raise ValueError('Invalid native text record.')
        rows.append((line.strip(), records, layers))
    if not rows:
        raise ValueError('Native text table has no records.')
    return rows


def patch_text(raw, key, entries):
    """Apply explicit text replacements/additions while retaining native columns."""
    out, seen, changed = [], set(), 0
    columns, shape_layers = None, None
    for line, records, layers in text_lines(raw, key):
        touched = False
        for index, record in enumerate(records):
            fields = record.split('^')
            seen.add(fields[0])
            if columns is None:
                columns, shape_layers = len(fields) - 1, layers
            if fields[0] in entries:
                entry = entries[fields[0]]
                value, replace = entry if isinstance(entry, tuple) else (entry, True)
                replacement = [value] * (len(fields) - 1)
                if replace and fields[1:] != replacement:
                    records[index] = '^'.join([fields[0], *replacement])
                    touched = True
                    changed += 1
        if touched:
            line = base64.b64encode(_ecb(key, _pad(('\n'.join(records)+'\n').encode(), layers), True)).decode()
        out.append(line)
    missing = sorted(entries.keys() - seen)
    if missing:
        plain = ''.join('^'.join([name] + [entries[name][0] if isinstance(entries[name], tuple) else entries[name]] * columns)
                        + '\n' for name in missing).encode()
        out.append(base64.b64encode(_ecb(key, _pad(plain, shape_layers), True)).decode())
        changed += len(missing)
    return ('\n'.join(out) + '\n').encode('ascii'), changed
