"""Read-only weekly news over the pinned iOS replay policies; no engine imports."""
from collections.abc import Mapping
import copy
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import json
import os
from typing import Any, Protocol

from replay_calendar import read_anchor, rotation_week
import revival_summons as summons
import revival_events as events
import revival_economy as economy
import revival_mail_rewards as mail

STATE_KEY = 'ios_notices'
TAG = 'tN8f0PSB'
GROUPS = ('tN8f0PSB', 'R17unt2e', '3BI1xSGW', 'VKA5urE1', 'oUk10RXm', 'fzm3je8p')
NOTICE_ID_BASE, INDEX_BASE = 880000, 500
MAX_INDEX = 65535 - INDEX_BASE
HOST = 'https://v900-lapis.gumi.sg'


@dataclass(frozen=True)
class NoticeWindow:
    """Calendar facts for one retained weekly replay notice."""

    index: int
    start: datetime
    end: datetime


@dataclass(frozen=True)
class NoticeIdentity:
    """Native wire identity paired with its calendar window."""

    notice_id: str
    window: NoticeWindow
    flag: int


@dataclass(frozen=True)
class NativeNoticeCaption:
    """Projected native list caption for one notice window."""

    text: str


class NativeCaptionProjector(Protocol):
    """Read-only caption projection contract for one retained notice window."""

    def project(self, data: Mapping[str, Any], window: NoticeWindow) -> NativeNoticeCaption:
        ...


def clock():
    return summons.clock()


def settings(data):
    if STATE_KEY not in data:
        return None
    try:
        state = data[STATE_KEY]
        values = state['settings']
        if (type(state['version']) is not int or state['version'] != 1
                or set(values) != {'enabled', 'weeks'} or type(values['enabled']) is not bool
                or type(values['weeks']) is not int or not 1 <= values['weeks'] <= 52):
            raise ValueError('unsupported settings')
        return values
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f'Invalid iOS notices: {exc}') from exc


def initialize(data):
    if settings(data) is not None:
        return False
    try:
        values = {'enabled': os.environ.get('EXVIUS_REPLAY_NOTICES', '1') == '1',
                  'weeks': int(os.environ.get('EXVIUS_REPLAY_NOTICE_WEEKS', '8'))}
        candidate = {STATE_KEY: {'version': 1, 'settings': values}}
        settings(candidate)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'Invalid iOS notice defaults: {exc}') from exc
    data[STATE_KEY] = candidate[STATE_KEY]
    return True


def _context_state(data, now):
    saved, config = read_anchor(data), settings(data)
    if saved is None or config is None or not config['enabled']:
        return None
    anchor, replay = saved
    week = rotation_week(now if now is not None else clock(), replay)
    return week, week.number - anchor, config


def _context(data, now):
    state = _context_state(data, now)
    return None if state is None else state[:2]


def _identity_for(week, current, index):
    start = week.starts + timedelta(weeks=index - current)
    end = start + timedelta(weeks=1)
    return NoticeIdentity(str(NOTICE_ID_BASE + index), NoticeWindow(index, start, end), INDEX_BASE + index)


def indices(data, now=None):
    state = _context_state(data, now)
    if state is None or state[1] < 0:
        return ()
    _week, current, config = state
    capped = min(current, MAX_INDEX)
    return tuple(range(max(0, capped - config['weeks'] + 1), capped + 1))


def identity(data, index, now=None):
    context = _context(data, now)
    if context is None or type(index) is not int or not 0 <= index <= min(context[1], MAX_INDEX):
        return None
    ident = _identity_for(context[0], context[1], index)
    return ident.notice_id, ident.window.start, ident.window.end, ident.flag


def _in_window(day, window):
    return bool(day) and window['from'] <= day < window['to']


def _permanent_deal_start(banner, window):
    span = banner.get('permanent')
    first = span.get('from') if isinstance(span, dict) else None
    return first if _in_window(first, window) else None


def _window_bundles(window):
    return [b for b in economy.bundles() if _in_window(b.get('from'), window)]


def _window_mails(data, window):
    config = mail.read_state(data)
    if not (config and config['settings']['replay_mails']):
        return []
    return [row for row in mail.catalogue() if _in_window(row['date'], window)]


def _format_caption(start, holiday, names):
    caption = f'{start:%b} {start.day}: '
    if holiday:
        caption += holiday + ' summons! '
    return caption + ((names[0] + (f' and {len(names) - 1} more' if len(names) > 1 else ''))
                      if names else 'This week in history')


class PolicyNativeCaptionProjector:
    """Pure read-only caption projector over pinned summon, bundle, and mail policies."""

    def project(self, data: Mapping[str, Any], window: NoticeWindow) -> NativeNoticeCaption:
        selected = summons.plan(data, window.start + timedelta(hours=1))
        span = selected.window
        names, deals = [], []
        for release, members in selected.sets:
            for bid in members:
                banner = selected.by_id[bid]
                if banner.get('deal'):
                    deals.append((release, banner['name']))
                else:
                    names.append(banner['name'].replace(' Featured Summon', ''))
        for bid in selected.permanent:
            banner = selected.by_id[bid]
            first = _permanent_deal_start(banner, span)
            if first:
                deals.append((first, banner['name']))
        deals.sort()
        names.extend(name for _released, name in deals)
        names.extend(b['name'] for b in _window_bundles(span))
        names.extend(m['title'] for m in _window_mails(data, span))
        return NativeNoticeCaption(_format_caption(window.start, selected.holiday, names))


_DEFAULT_PROJECTOR = PolicyNativeCaptionProjector()


def summary(data, index, now=None):
    fact = identity(data, index, now)
    if fact is None:
        return None
    _id, start, _end, _flag = fact
    selected = summons.plan(data, start + timedelta(hours=1))
    window = selected.window
    regular, deals = [], []
    holiday_keys = {key for keys in selected.holiday_sets.values() for key, _members in keys}
    for release, members in selected.sets:
        banners = []
        for bid in members:
            row = copy.deepcopy(selected.by_id[bid])
            row['released'] = release
            (deals if row.get('deal') else banners).append(row)
        if banners:
            regular.append({'released': release, 'holiday': release in holiday_keys, 'banners': banners})
    for bid in selected.permanent:
        banner = selected.by_id[bid]
        first = _permanent_deal_start(banner, window)
        if first:
            deals.append(dict(copy.deepcopy(banner), released=first, stays=True))
    deals.sort(key=lambda row: (row['released'], row['name']))
    bundles = [copy.deepcopy(b) for b in _window_bundles(window)]
    delivered = [dict(copy.deepcopy(row), items=mail.items_for(row, read_anchor(data)[1].start))
                 for row in _window_mails(data, window)]
    selected_events, seen = [], set()
    for row in sorted(events.plan(data, start, summons=selected, until=_end).events,
                      key=lambda row: (str(row.get('release')), str(row.get('area')))):
        if not row.get('event_windows'):
            continue
        key = row.get('release'), row['name'], tuple((w['starts_at'], w['ends_at']) for w in row['event_windows'])
        if key not in seen:
            seen.add(key)
            selected_events.append(copy.deepcopy(row))
    names = [b['name'].replace(' Featured Summon', '') for group in regular for b in group['banners']]
    names += [b['name'] for b in deals] + [b['name'] for b in bundles] + [m['title'] for m in delivered]
    caption = _format_caption(start, selected.holiday, names)
    return {'index': index, 'start': start, 'from': window['from'],
            'to': (date.fromisoformat(window['to']) - timedelta(days=1)).isoformat(),
            'finished': selected.finished, 'holiday': selected.holiday, 'summons': regular,
            'deals': deals, 'bundles': bundles, 'mails': delivered, 'events': selected_events, 'caption': caption}


def _format_native_row(ident: NoticeIdentity, caption: str):
    begin = ident.window.start.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
    new_end = ident.window.end.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
    return {'td06MKEX': ident.notice_id, '5GNraZM0': '0', 'i4Bb9ySk': '1', '1fKgZk2I': '1',
            '15Y3fBmF': json.dumps({'en': caption}, ensure_ascii=False), 'w7VR6ypY': str(ident.window.index),
            '1d8R5ajV': begin, 'VjJQ51uG': begin, 'm8ivD4NX': '2099-12-31 23:59:59',
            'o6n5aQ8C': begin, '9miE75sp': new_end, '5r8HSq1N': begin, 'M9ZKJY3w': '2099-12-31 23:59:59',
            'DSJpb89M': '', 'oIra47LK': '1', '1X65WPLU': f'{HOST}/exvius/notices/{ident.window.index}.html',
            'QLfe23bu': str(ident.flag), '8amsKpQ2': '0', 'I2PbiZ1f': '', 'GTESVt57': '',
            '7DUC49n8': '', 'qo3PECw6': '0', '52ihocTI': '0'}


def native_row(data, index, content, *, now=None):
    notice_id, start, end, flag = identity(data, index, now)
    return _format_native_row(NoticeIdentity(notice_id, NoticeWindow(index, start, end), flag), content['caption'])


def _digits(value):
    return isinstance(value, str) and value.isascii() and value.isdigit()


def ledger(data):
    saved = data.get('notices', {'index': {}, 'read': []})
    try:
        index, read = saved.get('index', {}), saved.get('read', [])
        if not isinstance(index, dict) or not isinstance(read, list) or any(not _digits(i) for i in read):
            raise ValueError('invalid read receipts')
        for key, value in index.items():
            year, flag = value
            if (not _digits(key) or not _digits(year) or len(year) != 4 or not 1 <= int(year) <= 9999
                    or type(flag) is not int or not 0 <= flag < 65536):
                raise ValueError('invalid native read index')
        return index, set(read)
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError(f'Invalid iOS notice receipts: {exc}') from exc


def catalogue(spec):
    out = {}
    if isinstance(spec, dict):
        for group in GROUPS:
            for row in spec.get(group) or []:
                nid = str(row.get('td06MKEX', ''))
                year = str(row.get('1d8R5ajV', '')).split('-', 1)[0].split('/', 1)[0]
                flag = str(row.get('QLfe23bu', ''))
                if (_digits(nid) and _digits(year) and len(year) == 4 and int(year) > 0
                        and _digits(flag) and int(flag) < 65536):
                    out[nid] = [year, int(flag)]
    return out


def replay_identity(data, notice_id, now=None):
    if not _digits(notice_id) or len(notice_id) > 6:
        return None
    fact = identity(data, int(notice_id) - NOTICE_ID_BASE, now)
    if fact:
        return [fact[1].astimezone(timezone.utc).strftime('%Y'), fact[3]]
    return None


def project(spec, data):
    settings(data)
    index, read = ledger(data)
    index = {**catalogue(spec), **index}
    masks = {}
    for nid in read.intersection(index):
        year, flag = index[nid]
        nibbles = masks.setdefault(year, [])
        if flag // 4 >= len(nibbles):
            nibbles.extend([0] * (flag // 4 + 1 - len(nibbles)))
        nibbles[flag // 4] |= 8 >> flag % 4
    out = dict(spec) if isinstance(spec, dict) else {}
    # Always replace captured masks: an old client receipt is not this campaign's.
    out['Z53gL0RU'] = [{'Gs6BT8n5': year, 'goAiX84L': ''.join(format(n, 'x') for n in mask)}
                      for year, mask in sorted(masks.items())]
    return out


def add_rows(spec, data, now=None, *, projector: NativeCaptionProjector | None = None):
    now = now if now is not None else clock()
    out = dict(spec) if isinstance(spec, dict) else {}
    # Captured/generated replay rows must not survive a rollover or disabled policy.
    for group in GROUPS:
        if group in out:
            out[group] = [row for row in out[group] if not (_digits(str(row.get('td06MKEX', '')))
                and NOTICE_ID_BASE <= int(row['td06MKEX']) <= NOTICE_ID_BASE + MAX_INDEX)]
    state = _context_state(data, now)
    rows = list(out.get(TAG) or [])
    if state is not None and state[1] >= 0:
        week, current, config = state
        active_projector = _DEFAULT_PROJECTOR if projector is None else projector
        capped = min(current, MAX_INDEX)
        for index in range(max(0, capped - config['weeks'] + 1), capped + 1):
            ident = _identity_for(week, current, index)
            caption = active_projector.project(data, ident.window)
            rows.append(_format_native_row(ident, caption.text))
    out[TAG] = rows
    return out


def project_query(spec, data, reply_id, now=None, *, projector: NativeCaptionProjector | None = None):
    """Engine-free read-only query projection for native news lists and notice read masks."""
    settings(data)
    if reply_id == 'CQ4jTm2F':
        spec = add_rows(spec, data, now, projector=projector)
    return project(spec, data)
