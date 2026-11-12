"""Pure replay home-carousel policy over saved settings and prepared artwork."""
from datetime import timedelta, timezone
import os

import revival_events
import revival_summons

STATE_KEY = 'ios_marquee'
ID_BASE = 7000000
HOST = 'https://v900-lapis.gumi.sg'


def settings(data):
    if STATE_KEY not in data:
        return None
    try:
        state = data[STATE_KEY]
        values = state['settings']
        if (type(state['version']) is not int or state['version'] != 1
                or set(values) != {'enabled', 'limit', 'tap'}
                or type(values['enabled']) is not bool or type(values['tap']) is not bool
                or type(values['limit']) is not int or not 1 <= values['limit'] <= 52):
            raise ValueError('unsupported settings')
        return values
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f'Invalid iOS home carousel: {exc}') from exc


def initialize(data):
    if settings(data) is not None:
        return False
    try:
        values = {'enabled': os.environ.get('EXVIUS_REPLAY_MARQUEE', '1') == '1',
                  'limit': int(os.environ.get('EXVIUS_REPLAY_MARQUEE_MAX', '6')),
                  'tap': os.environ.get('EXVIUS_REPLAY_MARQUEE_TAP', '1') == '1'}
        state = {'version': 1, 'settings': values}
        settings({STATE_KEY: state})
    except (TypeError, ValueError) as exc:
        raise ValueError(f'Invalid iOS home carousel defaults: {exc}') from exc
    data[STATE_KEY] = state
    return True


def event_link(event):
    """Pinned native type-6 stage-list link; native modes retain the Vortex link."""
    if (event.get('native_mode') or not all(isinstance(event.get(key), (str, int))
            and str(event[key]).isascii() and str(event[key]).isdigit() and int(event[key]) > 0
            for key in ('area', 'first_dungeon', 'first_mission'))):
        return None
    return f"6:2,0,{event['area']},{event['first_dungeon']},{event['first_mission']}"


def entries(data, artwork, *, now=None, events=None, summons=None):
    """None selects the legacy era; [] means an active replay week has no usable art."""
    policy = settings(data)
    if policy is None or not policy['enabled'] or artwork is None:
        return None
    moment = now if now is not None else revival_summons.clock()
    selected = summons if summons is not None else revival_summons.plan(data, moment)
    if not selected.anchored or selected.finished:
        return None
    events = events if events is not None else revival_events.plan(data, moment, summons=selected).events
    result, seen = [], set()
    candidates = [row for row in events if row.get('release')
                  and (row.get('group') != 'permanent' or row.get('windows'))]
    for event in sorted(candidates, key=lambda row: (str(row['release']), str(row.get('area'))), reverse=True):
        image = artwork.image(str(event.get('area')))
        if image is None or image['source'] in seen:
            continue
        seen.add(image['source'])
        result.append({'event': event, 'image': image, 'link': event_link(event) if policy['tap'] else None})
        if len(result) >= policy['limit']:
            break
    return result


def rows(data, artwork, *, now=None, window_days=21, location='10:601', events=None, summons=None):
    moment = now if now is not None else revival_summons.clock()
    chosen = entries(data, artwork, now=moment, events=events, summons=summons)
    if chosen is None:
        return None
    first = (moment - timedelta(days=1)).astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
    last = (moment + timedelta(days=window_days)).astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
    return [{'nZfbucEw': str(ID_BASE + int(row['event']['area'])),
             'JZryxaYY': str(artwork.manifest['generation']), 'twb8TQPx': first, 'ZkGp8XbQ': last,
             'TsZhcqbT': HOST + '/' + row['image']['url'], 'zRZY8dcE': '0', '3c8348af': '0',
             'uP4695k3': row['link'] or location} for row in chosen]
