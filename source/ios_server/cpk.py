"""Pure flat banner CPK codec, based on the pinned revival ios_art layout.

Preserve original compressed payloads; additions use the native masked @UTF TOC,
case-insensitive name order, TOC-relative offsets and eight-byte file alignment.
"""
import struct

FORMATS = {0: '>B', 1: '>b', 2: '>H', 3: '>h', 4: '>I', 5: '>i',
           6: '>Q', 7: '>q', 8: '>f', 10: '>I', 11: '>II'}


def mask(raw):
    result, seed = bytearray(len(raw)), 0x655F
    for index, value in enumerate(raw):
        result[index] = value ^ (seed & 255)
        seed = seed * 0x4115 & 0xffffffff
    return bytes(result)


def table(raw):
    """Decode one bounded @UTF table, including zero and constant columns."""
    raw = raw if raw[:4] == b'@UTF' else mask(raw)
    if raw[:4] != b'@UTF' or len(raw) < 32 or struct.unpack_from('>I', raw, 4)[0] + 8 != len(raw):
        raise ValueError('Invalid CPK UTF header')
    _, rows_at, strings_at, data_at, name_at, count, row_size, rows = struct.unpack_from('>HHIIIHHI', raw, 8)
    rows_at += 8; strings_at += 8; data_at += 8
    if not 32 <= rows_at <= strings_at <= data_at <= len(raw) or rows_at + rows * row_size > strings_at:
        raise ValueError('Invalid CPK UTF bounds')

    def string(offset):
        begin = strings_at + offset
        if not strings_at <= begin < data_at:
            raise ValueError('Invalid CPK string offset')
        return raw[begin:raw.index(b'\0', begin, data_at)].decode('utf-8')

    def value(kind, offset, end):
        size = struct.calcsize(FORMATS[kind])
        if offset + size > end:
            raise ValueError('Truncated CPK cell')
        result = struct.unpack_from(FORMATS[kind], raw, offset)
        if kind == 10:
            result = string(result[0])
        elif kind == 11:
            begin, length = result
            if data_at + begin + length > len(raw):
                raise ValueError('Invalid CPK data offset')
            result = raw[data_at + begin:data_at + begin + length]
        else:
            result = result[0]
        return result, size

    columns, cursor = [], 32
    for _ in range(count):
        if cursor + 5 > rows_at:
            raise ValueError('Truncated CPK schema')
        flags, offset = struct.unpack_from('>BI', raw, cursor); cursor += 5
        storage, kind = flags & 0xf0, flags & 15
        if storage not in (0x10, 0x30, 0x50) or kind not in FORMATS:
            raise ValueError('Unsupported CPK column')
        constant = 0
        if storage == 0x30:
            constant, size = value(kind, cursor, rows_at); cursor += size
        name = string(offset)
        if name in {column[0] for column in columns}:
            raise ValueError('Duplicate CPK column')
        columns.append((name, storage, kind, constant))
    if cursor != rows_at or sum(struct.calcsize(FORMATS[kind]) for _, storage, kind, _ in columns if storage == 0x50) != row_size:
        raise ValueError('Invalid CPK row layout')
    result = []
    for index in range(rows):
        cursor = rows_at + index * row_size
        row = {}
        for name, storage, kind, constant in columns:
            if storage == 0x50:
                row[name], size = value(kind, cursor, rows_at + (index + 1) * row_size); cursor += size
            else:
                row[name] = constant
        result.append(row)
    return string(name_at), columns, result


def encode_table(name, columns, rows):
    """Encode the native schema; strings/data are pooled without changing cells."""
    strings, offsets, blobs = bytearray(b'<NULL>\0'), {}, bytearray()
    def string(text):
        if not isinstance(text, str) or '\0' in text:
            raise ValueError('Invalid CPK string')
        if text not in offsets:
            offsets[text] = len(strings); strings.extend(text.encode() + b'\0')
        return offsets[text]
    def cell(kind, item):
        if kind == 10:
            return struct.pack('>I', string(item))
        if kind == 11:
            offset = len(blobs); blobs.extend(item)
            return struct.pack('>II', offset, len(item))
        return struct.pack(FORMATS[kind], item)
    name_at = string(name)
    schema = bytearray()
    for column, storage, kind, constant in columns:
        schema.extend(struct.pack('>BI', storage | kind, string(column)))
        if storage == 0x30:
            schema.extend(cell(kind, constant))
    body = bytearray()
    for row in rows:
        for column, storage, kind, _ in columns:
            if storage == 0x50:
                body.extend(cell(kind, row[column]))
    row_size = sum(struct.calcsize(FORMATS[kind]) for _, storage, kind, _ in columns if storage == 0x50)
    rows_at = 24 + len(schema); strings_at = rows_at + len(body)
    data_at = strings_at + len(strings)
    padding = -data_at % 8; data_at += padding
    header = struct.pack('>HHIIIHHI', 0, rows_at, strings_at, data_at, name_at, len(columns), row_size, len(rows))
    result = header + schema + body + strings + b'\0' * padding + blobs
    return b'@UTF' + struct.pack('>I', len(result)) + result


def inspect(raw):
    """Validate the supported flat banner pack without extracting or writing it."""
    try:
        def chunk(offset, tag):
            if offset < 0 or raw[offset:offset + 4] != tag or offset + 16 > len(raw):
                raise ValueError('Invalid CPK chunk')
            size = struct.unpack_from('<Q', raw, offset + 8)[0]
            if offset + 16 + size > len(raw):
                raise ValueError('Truncated CPK chunk')
            return table(raw[offset + 16:offset + 16 + size])
        name, columns, headers = chunk(0, b'CPK ')
        if name != 'CpkHeader' or len(headers) != 1:
            raise ValueError('Invalid CPK header table')
        header = headers[0]
        toc, start, size = (header[key] for key in ('TocOffset', 'ContentOffset', 'ContentSize'))
        if (header.get('Align') != 8 or any(header.get(key) for key in
                ('EtocOffset', 'ItocOffset', 'GtocOffset', 'HtocOffset', 'HgtocOffset', 'EnableTocCrc', 'EnableFileCrc', 'CrcMode'))
                or start + size < len(raw) or not 0 <= start + size - len(raw) <= 8
                or header.get('FileSize', 0) not in (0, len(raw))
                or header.get('TotalDataSize', 0) not in (0, size)):
            raise ValueError('Unsupported CPK layout or size')
        name, toc_columns, entries = chunk(toc, b'TOC ')
        header_end = 16 + struct.unpack_from('<Q', raw, 8)[0]
        toc_end = toc + 16 + struct.unpack_from('<Q', raw, toc + 8)[0]
        if name != 'CpkTocInfo' or header['Files'] != len(entries) or not header_end <= toc < toc_end <= start:
            raise ValueError('Invalid CPK TOC layout')
        if header['TocSize'] != toc_end - toc:
            raise ValueError('Invalid CPK TOC size')
        expected = {'DirName', 'FileName', 'FileSize', 'ExtractSize', 'FileOffset', 'ID', 'UserString'}
        if {column[0] for column in toc_columns} != expected:
            raise ValueError('Unsupported CPK TOC columns')
        mutable = {'FileName': 10, 'FileSize': 4, 'ExtractSize': 4, 'FileOffset': 6, 'ID': 4}
        if any(storage != 0x50 or kind != mutable[column] for column, storage, kind, _ in toc_columns if column in mutable):
            raise ValueError('Unsupported CPK TOC storage')
        for row in entries:
            name = row['FileName']
            begin = toc + row['FileOffset']; end = begin + row['FileSize']
            if (row['DirName'] or not isinstance(name, str) or not name or any(c in name for c in '/\\\0')
                    or name in ('.', '..') or not start <= begin <= end <= len(raw) or begin % 8
                    or row['ExtractSize'] < row['FileSize']):
                raise ValueError('Invalid CPK file entry')
        return header, columns, toc_columns, entries
    except (KeyError, TypeError, IndexError, struct.error, UnicodeError, ValueError) as exc:
        raise ValueError(f'Invalid banner CPK: {exc}') from exc


def rebuild(raw, additions):
    """Return (pack, added names); original payload bytes and duplicate names survive."""
    header, columns, toc_columns, original = inspect(raw)
    header = dict(header)
    entries = [dict(row) for row in original]
    names = {row['FileName'].upper() for row in entries}
    if len({name.upper() for name in additions}) != len(additions):
        raise ValueError('Duplicate CPK additions')
    content = bytearray(raw[header['ContentOffset']:])
    content.extend(b'\0' * (header['ContentSize'] - len(content)))
    appended = []
    for name, blob in sorted(additions.items()):
        if not name or name in ('.', '..') or any(c in name for c in '/\\\0'):
            raise ValueError('Invalid CPK addition name')
        if name.upper() in names:
            continue
        content.extend(b'\0' * (-len(content) % 8))
        entries.append({'DirName': '', 'FileName': name, 'FileSize': len(blob), 'ExtractSize': len(blob),
                        'FileOffset': len(content) + header['ContentOffset'] - header['TocOffset'],
                        'ID': max((row['ID'] for row in entries), default=-1) + 1, 'UserString': '<NULL>'})
        content.extend(blob); appended.append(name)
    entries.sort(key=lambda row: row['FileName'].upper())
    toc = encode_table('CpkTocInfo', toc_columns, entries)
    start = header['TocOffset'] + 16 + len(toc); start += -start % 2048
    shift = start - header['ContentOffset']
    for row in entries:
        row['FileOffset'] += shift
    toc = encode_table('CpkTocInfo', toc_columns, entries)
    header.update(ContentOffset=start, ContentSize=len(content), TotalDataSize=len(content),
                  TocSize=16 + len(toc), Files=len(entries), FileSize=start + len(content),
                  EnabledPackedSize=2 * sum(row['ExtractSize'] for row in entries),
                  EnabledDataSize=sum(row['FileSize'] + row['ExtractSize'] for row in entries))
    columns = [(name, 0x50 if name in ('FileSize', 'TotalDataSize') else storage, kind, constant)
               for name, storage, kind, constant in columns]
    built_header = encode_table('CpkHeader', columns, [header])
    result = bytearray(b'CPK ' + raw[4:8] + struct.pack('<Q', len(built_header)) + mask(built_header))
    padding = header['TocOffset'] - len(result)
    if padding < 0:
        raise ValueError('CPK header exceeds its reserved space')
    result.extend(b'\0' * (padding - 6) + b'(c)CRI' if padding >= 6 else b'\0' * padding)
    result.extend(b'TOC ' + struct.pack('<IQ', 0, len(toc)) + mask(toc))
    result.extend(b'\0' * (start - len(result))); result.extend(content)
    built = bytes(result)
    inspect(built)
    return built, appended
