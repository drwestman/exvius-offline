"""Pure weekly/replay mail policy from revival 47a13c084f42.

The command adapter owns delivery and persistence. Issued logical keys survive
mail deletion. Numeric inbox IDs are allocated downwards in a private range:
the fork's fixed IDs collide with canonical catch-up mail, while increasing IDs
would collide with the canonical automatic allocator on later deliveries.
"""
from dataclasses import dataclass
from datetime import date, datetime, timezone
from functools import lru_cache
import json
import os
from pathlib import Path
import re

from replay_calendar import preview, read_anchor, rotation_week

ID_TOP = 940000000000
ID_BOTTOM = 939000000000
STATE_KEY = 'ios_mail_rewards'


def clock():
    return datetime.now(timezone.utc)


def _items(raw):
    if not isinstance(raw, (list, tuple)):
        raise ValueError('mail items must be triples')
    out = []
    for row in raw:
        if (not isinstance(row, (list, tuple)) or len(row) != 3 or
                any(type(n) is not int or n < 0 for n in row) or row[2] <= 0):
            raise ValueError('mail items must be nonnegative integer triples with positive counts')
        out.append(tuple(row))
    return tuple(out)


@lru_cache(maxsize=1)
def catalogue():
    try:
        rows = json.loads(Path(__file__).with_name('content').joinpath('replay_mails.json').read_text())['mails']
        if not isinstance(rows, list) or not rows:
            raise ValueError('the pinned mail catalogue is empty')
        seen = set()
        for row in rows:
            if (type(row['id']) is not int or row['id'] <= 0 or row['id'] in seen or
                    not isinstance(row['title'], str) or not row['title'] or
                    not isinstance(row.get('message', ''), str)):
                raise ValueError('mail IDs must be unique and titles present')
            seen.add(row['id'])
            date.fromisoformat(row['date'])
            if row.get('items'):
                _items(row['items'])
            else:
                _items([(*row['item'], 1)])
                brackets = row['by_days']
                if not brackets or brackets[-1][0] is not None:
                    raise ValueError('appreciation brackets must end with an unlimited tier')
                previous = -1
                for index, (limit, count) in enumerate(brackets):
                    if type(count) is not int or count <= 0 or (limit is not None and
                            (type(limit) is not int or limit <= previous)) or (limit is None and index != len(brackets) - 1):
                        raise ValueError('invalid appreciation bracket')
                    if limit is not None:
                        previous = limit
        return tuple(rows)
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f'Invalid pinned replay mail metadata: {exc}') from exc


def items_for(mail, start):
    if mail.get('items'):
        return _items(mail['items'])
    days = (date.fromisoformat(mail['date']) - start).days + 1
    for limit, count in mail['by_days']:
        if limit is None or days <= limit:
            return ((int(mail['item'][0]), int(mail['item'][1]), count),)
    return ()


def read_state(data):
    mailbox = data.get('mailbox', [])
    if not isinstance(mailbox, list) or any(not isinstance(mail, dict) for mail in mailbox):
        raise ValueError('Invalid iOS mail rewards: mailbox must contain mail records.')
    if STATE_KEY not in data:
        if any('ios_reward_key' in mail for mail in mailbox):
            raise ValueError('Invalid iOS mail rewards: issued reward mail has no delivery ledger.')
        return None
    try:
        state = data[STATE_KEY]
        if type(state['version']) is not int or state['version'] != 1:
            raise ValueError('unsupported version')
        settings = state['settings']
        if set(settings) != {'weekly_gift', 'replay_mails'} or type(settings['replay_mails']) is not bool:
            raise ValueError('invalid settings')
        _items(settings['weekly_gift'])
        if type(state['next_id']) is not int or not ID_BOTTOM <= state['next_id'] <= ID_TOP:
            raise ValueError('invalid inbox ID cursor')
        issued = state['issued']
        if not isinstance(issued, dict) or any(not re.fullmatch(r'(weekly:-?\d+|replay:\d+)', key)
                                               for key in issued):
            raise ValueError('invalid issue keys')
        for key in issued:
            kind, value = key.split(':')
            if value != str(int(value)) or (kind == 'replay' and int(value) <= 0):
                raise ValueError('issue keys must use canonical numeric identifiers')
        ids = list(issued.values())
        if (any(not isinstance(mid, str) or not mid.isascii() or not mid.isdigit() or
                str(int(mid)) != mid or not state['next_id'] < int(mid) <= ID_TOP for mid in ids) or
                len(ids) != len(set(ids))):
            raise ValueError('invalid issued inbox IDs')
        weeks = [int(key.split(':')[1]) for key in issued if key.startswith('weekly:')]
        last = state['weekly_last']
        if (last is not None and type(last) is not int) or last != (max(weeks) if weeks else None):
            raise ValueError('invalid recorded weekly delivery')
        for mail in mailbox:
            if 'ios_reward_key' in mail and issued.get(mail['ios_reward_key']) != mail.get('mail_id'):
                raise ValueError('issued reward mail disagrees with the delivery ledger')
        return state
    except (KeyError, AttributeError, TypeError, ValueError) as exc:
        raise ValueError(f'Invalid iOS mail rewards: {exc}') from exc


def initialize(data):
    """Configure a candidate once. No delivery, masters, engine imports or I/O."""
    if read_state(data) is not None:
        return False
    text = os.environ.get('EXVIUS_WEEKLY_GIFT', '23:50:10,23:70:1')
    try:
        raw = []
        for entry in filter(None, text.split(',')):
            parts = entry.strip().split(':')
            if len(parts) != 3 or not all(part.isascii() and part.isdigit() for part in parts):
                raise ValueError('use kind:id:count triples')
            raw.append(tuple(map(int, parts)))
        items = _items(raw)
    except ValueError as exc:
        raise ValueError(f'Invalid iOS weekly gift: {exc}') from exc
    data[STATE_KEY] = {'version': 1, 'settings': {'weekly_gift': [list(row) for row in items],
                         'replay_mails': os.environ.get('EXVIUS_REPLAY_MAILS', '1') == '1'},
                       'weekly_last': None, 'issued': {}, 'next_id': ID_TOP}
    return True


@dataclass(frozen=True)
class MailGrant:
    key: str
    title: str
    message: str
    items: tuple


def plan(data, now=None):
    state = read_state(data)
    saved = read_anchor(data)
    if state is None or saved is None:
        return ()
    now = now if now is not None else clock()
    number = rotation_week(now, saved[1]).number
    settings, out = state['settings'], []
    last = state['weekly_last']
    if settings['weekly_gift'] and (last is None or number > last):
        out.append(MailGrant(f'weekly:{number}', 'Weekly Summon Gift',
            "This week's summon gift: a 10+1's worth of tickets. Use them with any banner's Ticket Summon button.",
            _items(settings['weekly_gift'])))
    if settings['replay_mails']:
        reached = preview(data, now)['windows'][0]['to']
        for mail in catalogue():
            key = 'replay:' + str(mail['id'])
            if mail['date'] < reached and key not in state['issued']:
                out.append(MailGrant(key, mail['title'], mail.get('message', ''), items_for(mail, saved[1].start)))
    return tuple(out)
