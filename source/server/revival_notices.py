"""Read-only weekly news over the pinned iOS replay policies; no engine imports."""
import copy
from datetime import date, timedelta, timezone
import json
import os

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


def _context(data, now):
    saved, config = read_anchor(data), settings(data)
    if saved is None or config is None or not config['enabled']:
        return None
    anchor, replay = saved
    week = rotation_week(now if now is not None else clock(), replay)
    return week, week.number - anchor


def indices(data, now=None):
    context = _context(data, now)
    if context is None or context[1] < 0:
        return ()
    current = min(context[1], MAX_INDEX)
    return tuple(range(max(0, current - settings(data)['weeks'] + 1), current + 1))


def identity(data, index, now=None):
    context = _context(data, now)
    if context is None or type(index) is not int or not 0 <= index <= min(context[1], MAX_INDEX):
        return None
    week, current = context
    start = week.starts + timedelta(weeks=index - current)
    end = start + timedelta(weeks=1)
    return str(NOTICE_ID_BASE + index), start, end, INDEX_BASE + index


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
        span = banner.get('permanent')
        first = span.get('from') if isinstance(span, dict) else None
        if first and window['from'] <= first < window['to']:
            deals.append(dict(copy.deepcopy(banner), released=first, stays=True))
    deals.sort(key=lambda row: (row['released'], row['name']))
    bundles = [copy.deepcopy(b) for b in economy.bundles()
               if b.get('from') and window['from'] <= b['from'] < window['to']]
    delivered = []
    config = mail.read_state(data)
    if config and config['settings']['replay_mails']:
        for row in mail.catalogue():
            if window['from'] <= row['date'] < window['to']:
                delivered.append(dict(copy.deepcopy(row), items=mail.items_for(row, read_anchor(data)[1].start)))
    selected_events, seen = [], set()
    for row in sorted(events.plan(data, start + timedelta(hours=1), summons=selected).events,
                      key=lambda row: (str(row.get('release')), str(row.get('area')))):
        if not row.get('release') or row.get('group') == 'permanent' and not row.get('windows'):
            continue
        key = row['release'], row['name']
        if key not in seen:
            seen.add(key)
            selected_events.append(copy.deepcopy(row))
    names = [b['name'].replace(' Featured Summon', '') for group in regular for b in group['banners']]
    names += [b['name'] for b in deals] + [b['name'] for b in bundles] + [m['title'] for m in delivered]
    caption = f'{start:%b} {start.day}: '
    if selected.holiday:
        caption += selected.holiday + ' summons! '
    caption += (names[0] + (f' and {len(names) - 1} more' if len(names) > 1 else '')) if names else 'This week in history'
    return {'index': index, 'start': start, 'from': window['from'],
            'to': (date.fromisoformat(window['to']) - timedelta(days=1)).isoformat(),
            'finished': selected.finished, 'holiday': selected.holiday, 'summons': regular,
            'deals': deals, 'bundles': bundles, 'mails': delivered, 'events': selected_events, 'caption': caption}


def native_row(data, index, content, *, now=None):
    notice_id, start, end, flag = identity(data, index, now)
    begin = start.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
    new_end = end.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
    return {'td06MKEX': notice_id, '5GNraZM0': '0', 'i4Bb9ySk': '1', '1fKgZk2I': '1',
            '15Y3fBmF': json.dumps({'en': content['caption']}, ensure_ascii=False), 'w7VR6ypY': str(index),
            '1d8R5ajV': begin, 'VjJQ51uG': begin, 'm8ivD4NX': '2099-12-31 23:59:59',
            'o6n5aQ8C': begin, '9miE75sp': new_end, '5r8HSq1N': begin, 'M9ZKJY3w': '2099-12-31 23:59:59',
            'DSJpb89M': '', 'oIra47LK': '1', '1X65WPLU': f'{HOST}/exvius/notices/{index}.html',
            'QLfe23bu': str(flag), '8amsKpQ2': '0', 'I2PbiZ1f': '', 'GTESVt57': '',
            '7DUC49n8': '', 'qo3PECw6': '0', '52ihocTI': '0'}


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


def add_rows(spec, data, now=None):
    now = now if now is not None else clock()
    out = dict(spec) if isinstance(spec, dict) else {}
    # Captured/generated replay rows must not survive a rollover or disabled policy.
    for group in GROUPS:
        if group in out:
            out[group] = [row for row in out[group] if not (_digits(str(row.get('td06MKEX', '')))
                and NOTICE_ID_BASE <= int(row['td06MKEX']) <= NOTICE_ID_BASE + MAX_INDEX)]
    out[TAG] = list(out.get(TAG) or []) + [native_row(data, i, summary(data, i, now), now=now)
                                         for i in indices(data, now)]
    return out
