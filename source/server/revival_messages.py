"""Request-local native refusal envelope; no process-global pending message."""
from contextvars import ContextVar

_message = ContextVar('ios_action_message', default=None)


def clear():
    _message.set(None)


def refuse(text):
    _message.set({'D8aznm56': '1', '5oHZM9zK': '6', 'Wk1v6upb': str(text).replace('@', ' ')})


def take():
    value = _message.get()
    clear()
    return value
