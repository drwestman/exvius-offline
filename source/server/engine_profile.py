"""Immutable behavior profiles, selected once before the engine binds its modules.

The iOS defaults are derived from revival commit
47a13c084f42cf1b83b53173d0c21065c78fc2de (ios-server/serve.py,
source/server/replay.py and gacha_rotation.py). No I/O occurs here.
"""
from dataclasses import dataclass
from datetime import date
import os
from types import MappingProxyType

REVIVAL_COMMIT = '47a13c084f42cf1b83b53173d0c21065c78fc2de'


@dataclass(frozen=True)
class ReplaySettings:
    start: date = date(2016, 12, 16)
    nv_era: date = date(2020, 8, 20)
    timezone: str = 'America/New_York'
    weekday: int = 6
    hour: int = 22
    initial_pace: int = 3
    nv_pace: int = 2


@dataclass(frozen=True)
class EngineProfile:
    name: str
    anniversary_ticket: bool = True
    replay: ReplaySettings | None = None


LEGACY = EngineProfile('legacy')
IOS_REVIVAL = EngineProfile('ios-revival', anniversary_ticket=False, replay=ReplaySettings())
PROFILES = MappingProxyType({p.name: p for p in (LEGACY, IOS_REVIVAL)})
_active: EngineProfile | None = None


def select_profile(name: str) -> EngineProfile:
    """Composition-root command; switching a bound interpreter is an error."""
    global _active
    try:
        profile = PROFILES[name]
    except KeyError:
        raise ValueError(f'Unknown engine profile: {name!r}') from None
    if _active is not None and _active != profile:
        raise RuntimeError(f'Engine profile is already bound to {_active.name!r}; use a separate process.')
    _active = profile
    return profile


def current_profile() -> EngineProfile:
    """Bind the default when the first engine module imports it; later env edits cannot switch it."""
    if _active is None:
        return select_profile(os.environ.get('EXVIUS_ENGINE_PROFILE', 'legacy'))
    return _active
