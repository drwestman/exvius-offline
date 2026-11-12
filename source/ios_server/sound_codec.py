"""Bounded, size-preserving HCA fixes from the pinned revival sound_compat.

No audio decoding, key guessing, environment switches or filesystem access.
Validate every archive/header/frame before returning a converted bank.
"""
import struct

from fastcrc.crc16 import umts as crc16
from ios_server import cpk

PIPELINE = 1


def _type1():
    table, value = bytearray(256), 0
    for index in range(1, 255):
        value = (value * 13 + 11) & 255
        if value in (0, 255):
            value = (value * 13 + 11) & 255
        table[index] = value
    table[255] = 255
    return bytes(table)


TYPE1 = _type1()


class Utf:
    """Validated native UTF view with absolute offsets for in-place byte patches."""
    def __init__(self, raw, base=0, length=None):
        end = len(raw) if length is None else base + length
        if base < 0 or end > len(raw) or base + 32 > end or raw[base:base + 4] != b'@UTF':
            raise ValueError('Invalid sound UTF header')
        size = struct.unpack_from('>I', raw, base + 4)[0] + 8
        if base + size > end:
            raise ValueError('Sound UTF exceeds its blob')
        _, self.columns, rows = cpk.table(raw[base:base + size])
        self.count = len(rows)
        self.base, self.raw = base, raw
        _, row_at, _, data_at, _, _, row_size, _ = struct.unpack_from('>HHIIIHHI', raw, base + 8)
        self.data_at = base + 8 + data_at
        cursor, offset, self.cells = base + 32, 0, {}
        for name, storage, kind, _ in self.columns:
            cursor += 5
            size = struct.calcsize(cpk.FORMATS[kind])
            if storage == 0x30:
                positions = [cursor] if self.count else []
                cursor += size
            elif storage == 0x50:
                positions = [base + 8 + row_at + index * row_size + offset for index in range(self.count)]
                offset += size
            else:
                positions = []
            self.cells[name] = (kind, positions)

    def blob(self, name):
        kind, positions = self.cells.get(name, (11, []))
        if kind != 11:
            raise ValueError('Invalid sound blob type: ' + name)
        if not positions:
            return 0, 0
        if self.count != 1:
            raise ValueError('Sound header must contain one row')
        offset, length = struct.unpack_from('>II', self.raw, positions[0])
        return self.data_at + offset, length


def afs2(raw, base, length):
    """Return disjoint, aligned payload spans; never clamp malformed offsets."""
    end = base + length
    if base < 0 or end > len(raw) or length < 16 or raw[base:base + 4] != b'AFS2':
        raise ValueError('Invalid sound AFS2 header')
    width, id_size = raw[base + 5], struct.unpack_from('<H', raw, base + 6)[0]
    count, alignment = struct.unpack_from('<II', raw, base + 8)
    alignment &= 65535  # Upper half is the AWB subkey, not part of alignment.
    if width not in (2, 4, 8) or id_size not in (1, 2, 4, 8) or not alignment:
        raise ValueError('Unsupported sound AFS2 layout')
    table = base + 16 + count * id_size
    table_end = table + (count + 1) * width
    if table_end > end:
        raise ValueError('Truncated sound AFS2 offsets')
    ids = [int.from_bytes(raw[base + 16 + i * id_size:base + 16 + (i + 1) * id_size], 'little') for i in range(count)]
    if len(set(ids)) != count:
        raise ValueError('Duplicate sound AFS2 IDs')
    offsets = [int.from_bytes(raw[table + i * width:table + (i + 1) * width], 'little') for i in range(count + 1)]
    if not table_end - base <= offsets[0] <= offsets[-1] <= length:
        raise ValueError('Invalid sound AFS2 offset range')
    spans = []
    for begin, finish in zip(offsets, offsets[1:]):
        start = base + -(-begin // alignment) * alignment
        stop = base + finish
        if not table_end <= base + begin <= start < stop <= end:
            raise ValueError('Invalid sound AFS2 payload bounds')
        spans.append((start, stop))
    return spans


def hca(raw, begin, end):
    """Validate one HCA and return its frame layout and cipher field."""
    if end - begin < 10 or struct.unpack_from('>I', raw, begin)[0] & 0x7f7f7f7f != 0x48434100:
        raise ValueError('Unsupported non-HCA sound payload')
    header = struct.unpack_from('>H', raw, begin + 6)[0]
    limit = begin + header - 2
    if header < 10 or begin + header > end or crc16(memoryview(raw)[begin:begin + header]):
        raise ValueError('Invalid HCA header checksum or bounds')
    cursor, chunks = begin + 8, {}
    sizes = {b'fmt\0': 16, b'comp': 16, b'dec\0': 12, b'vbr\0': 8,
             b'ath\0': 6, b'loop': 16, b'ciph': 6, b'rva\0': 8}
    while cursor + 4 <= limit:
        tag = bytes(value & 127 for value in raw[cursor:cursor + 4])
        if tag in (b'pad\0', b'comm'):
            if tag == b'comm' and (cursor + 5 > limit or cursor + 5 + raw[cursor + 4] > limit):
                raise ValueError('Truncated HCA comment')
            break
        size = sizes.get(tag)
        if size is None or tag in chunks or cursor + size > limit:
            raise ValueError('Unsupported or truncated HCA chunk')
        chunks[tag] = cursor
        cursor += size
    if b'fmt\0' not in chunks or (b'comp' in chunks) == (b'dec\0' in chunks):
        raise ValueError('Missing HCA frame layout')
    frames = struct.unpack_from('>I', raw, chunks[b'fmt\0'] + 8)[0]
    frame = struct.unpack_from('>H', raw, chunks.get(b'comp', chunks.get(b'dec\0')) + 4)[0]
    cipher_at = chunks[b'ciph'] + 4 if b'ciph' in chunks else None
    cipher = struct.unpack_from('>H', raw, cipher_at)[0] if cipher_at is not None else 0
    if cipher not in (0, 1):
        raise ValueError('Unsupported keyed HCA cipher: ' + str(cipher))
    if not frames or frame < 2 or begin + header + frames * frame > end:
        raise ValueError('Invalid HCA frame bounds')
    for index in range(frames):
        start = begin + header + index * frame
        if crc16(memoryview(raw)[start:start + frame]):
            raise ValueError('Invalid HCA frame checksum')
    return header, frame, frames, cipher_at, cipher


def inspect(raw):
    """Return validated layouts and the waveform flag cells, without mutation."""
    flags, waveforms = [], None
    if raw[:4] == b'AFS2':
        base, length = 0, len(raw)
    else:
        table = Utf(raw)
        base, length = table.blob('AwbFile')
        wave_at, wave_size = table.blob('WaveformTable')
        if wave_size:
            waves = Utf(raw, wave_at, wave_size)
            waveforms = waves.count
            kind, flags = waves.cells.get('EncodeType', (None, []))
            if kind not in (0, 1) or any(raw[at] not in (2, 6) for at in flags):
                raise ValueError('Unsupported sound waveform encoding')
            if waveforms and not flags:
                raise ValueError('Missing HCA waveform encoding')
        if not length:
            if waveforms:
                raise ValueError('External AWB sound banks are unsupported')
            return [], flags, waveforms or 0
    spans = afs2(raw, base, length)
    layouts = [(start, hca(raw, start, end)) for start, end in spans]
    if waveforms is not None and waveforms != len(layouts):
        raise ValueError('Sound waveform and AWB counts disagree')
    return layouts, flags, len(layouts)


def prepare(raw, *, native=False):
    """Return a new bank and counts; native iOS sources pass through unchanged."""
    layouts, flags, count = inspect(raw)
    plain = sum(layout[-1] == 1 for _, layout in layouts) if not native else 0
    changed = sum(raw[at] == 6 for at in flags) if not native else 0
    if changed and len(flags) == 1:
        changed = count  # Constant EncodeType represents every waveform.
    facts = {'waveforms': count, 'decrypted': plain, 'reflagged': changed}
    if not plain and not changed:
        return raw, facts
    out = bytearray(raw)
    for begin, (header, frame, frames, cipher_at, cipher) in layouts:
        if cipher != 1:
            continue
        for index in range(frames):
            start = begin + header + index * frame
            end = start + frame - 2
            out[start:end] = bytes(out[start:end]).translate(TYPE1)
            struct.pack_into('>H', out, end, crc16(memoryview(out)[start:end]))
        struct.pack_into('>H', out, cipher_at, 0)
        struct.pack_into('>H', out, begin + header - 2, crc16(memoryview(out)[begin:begin + header - 2]))
    for at in flags:
        if out[at] == 6:
            out[at] = 2
    return bytes(out), facts


def validate(raw, *, native=False):
    layouts, flags, count = inspect(raw)
    if not native and (any(layout[-1] != 0 for _, layout in layouts) or any(raw[at] != 2 for at in flags)):
        raise ValueError('Prepared Android sound still needs compatibility conversion')
    return count
