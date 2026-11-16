"""Verified update documents and saved capability policy; queries never initialize it."""
from functools import lru_cache
import hashlib
import json
from pathlib import Path

REVISION = 'd6e8858861969a2764e31345884453dde79fc71f'
HERE = Path(__file__).with_name('content') / 'upstream'
DEFAULTS = {'full_runs': True, 'late_banners': True, 'select_limited': True, 'lb_exp': True,
            'summon_mode': 'replay', 'event_currency_runs': 30, 'wiki_drop_rate': 30}


@lru_cache(maxsize=None)
def document(name):
    provenance = json.loads((HERE / 'provenance.json').read_bytes())
    if provenance['revision'] != REVISION or name not in provenance['documents']:
        raise ValueError('Unregistered revival update document: ' + name)
    raw = (HERE / name).read_bytes()
    if hashlib.sha256(raw).hexdigest() != provenance['documents'][name]:
        raise ValueError('Damaged revival update document: ' + name)
    return json.loads(raw)


def settings(data):
    update = data.get('ios_revival_update')
    if update is None:
        return None
    if (not isinstance(update, dict) or update.get('version') != 1 or update.get('revision') != REVISION
            or set(update.get('settings', {})) != set(DEFAULTS)):
        raise ValueError('Invalid iOS revival update policy')
    values = update['settings']
    if (any(type(values[k]) is not bool for k in ('full_runs','late_banners','select_limited','lb_exp'))
            or values['summon_mode'] not in ('replay','all')
            or type(values['event_currency_runs']) is not int or not 0 <= values['event_currency_runs'] <= 10000
            or type(values['wiki_drop_rate']) is not int or not 0 <= values['wiki_drop_rate'] <= 100):
        raise ValueError('Invalid iOS revival update settings')
    return dict(values)


def initialize(data):
    if settings(data) is not None:
        return False
    data['ios_revival_update'] = {'version': 1, 'revision': REVISION, 'settings': dict(DEFAULTS)}
    return True
