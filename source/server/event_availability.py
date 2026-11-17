"""Per-edition Vortex event availability: one strategy per engine profile.

Callers (command guards, listings, the gate reply) ask `current()` instead of
branching on a profile name, so a new edition adds a strategy here and edits
no caller. Strategies are stateless; every query takes its instant explicitly.
"""
from dataclasses import dataclass
from typing import Callable, Optional


@dataclass
class GateSource:
    """Everything serve_event_gate needs from an edition, resolved for one response."""
    facts: list                    # [(area, first_dungeon, first_mission)]
    archive_events: Optional[list]  # catalogue rows backing the facts; None = shipped-table facts
    serve_when_empty: bool          # keep processing when no event is selected
    rewrites: bool                  # the edition always republishes the gate rows
    prune: Callable                 # rows -> rows the carrier may keep
    order: Callable                 # rows -> rows in served order
    window: Callable                # (spec, facts) -> spec carrying the date bounds


def _legacy_gate_policy():
    """(policy, archive_events) for the legacy edition; raises OSError/ValueError when unreadable."""
    import os
    from data_paths import DATA_ROOT
    from exvius_events import load_policy, policy_path
    from ffbe_config import EVENT_GATE_AREAS
    policy = load_policy(DATA_ROOT, EVENT_GATE_AREAS)
    archive_events = None
    saved_policy = policy_path(DATA_ROOT)
    if (os.environ.get('EXVIUS_EVENT_ARCHIVE') == '1' and
            not (saved_policy is not None and saved_policy.exists())):
        from event_archive import area_ids, events
        archive_events = events()
        policy = dict(policy, areas=area_ids(), permanent=True)
    return policy, archive_events


class AnnualAvailability:
    """Legacy edition: dated events follow their annual America/New_York dates."""

    def now(self):
        from event_calendar import clock
        return clock()

    def can_enter(self, data, mission, *, now, resume=False):
        if not mission:
            return True
        from event_archive import document
        from event_calendar import Availability
        row = next((r for r in document()['events'] if str(r['area']) == str(mission.get('uv60hgDW'))), None)
        if row is None:
            return True
        if resume:
            attempt = data.get('exvius_repeat', {}).get('attempt', {})
            if attempt.get('mid') == str(mission.get('qo3PECw6')) and attempt.get('status') == 'pending':
                return True
        return Availability.at([row], now).is_open(row['area'])

    def weekly_events(self, player, now):
        from event_archive import events
        from event_calendar import select
        return list(select(events(), now))

    def gate_source(self, player):
        import ffbe_player
        from event_archive import document
        from event_calendar import Availability
        from exvius_events import apply_availability
        from ffbe_state import _note
        moment = self.now()
        try:
            policy, archive_events = _legacy_gate_policy()
        except (OSError, ValueError) as exc:
            _note("event policy invalid; no extra gates served: " + str(exc))
            return None
        facts = ([(row['area'], row['first_dungeon'], row['first_mission']) for row in archive_events]
                 if archive_events is not None else ffbe_player._event_area_facts(policy['areas']))
        try:
            catalogue = document()['events']
            availability = Availability.at(catalogue, moment)  # one snapshot for this response
        except (OSError, ValueError, KeyError) as exc:
            _note("annual event dates unavailable; no extra gates served: " + str(exc))
            return None
        known = {str(row['area']) for row in catalogue}
        facts = [fact for fact in facts if fact[0] not in known or availability.is_open(fact[0])]
        return GateSource(
            facts, archive_events, serve_when_empty=False, rewrites=False,
            prune=lambda rows: rows, order=lambda rows: rows,
            window=lambda spec, chosen: apply_availability(
                spec, policy, now=moment.timestamp(), resolved_areas=[f[0] for f in chosen],
                availability=availability))


class ReplayAvailability:
    """iOS revival edition: annual dates plus the saved campaign's dungeon rotation."""

    def now(self):
        import revival_summons
        return revival_summons.clock()

    def can_enter(self, data, mission, *, now, resume=False):
        from revival_events import plan
        return plan(data, now).can_enter(data, mission, resume=resume)

    def weekly_events(self, player, now):
        from revival_events import plan
        if player is None:
            from ffbe_state import State
            player = State.player
        return list(plan(player.data if player else {}, now).events)

    def gate_source(self, player):
        from revival_events import plan
        revival = plan(player.data)
        events = revival.events
        missions = {mid for event in events for mid in event['missions']}
        order = {str(row['area']): index for index, row in enumerate(events)}
        return GateSource(
            [(row['area'], row['first_dungeon'], row['first_mission']) for row in events], events,
            serve_when_empty=True, rewrites=True,
            prune=lambda rows: [row for row in rows if str(row.get('uv60hgDW')) not in revival.known_areas or
                                (str(row.get('uv60hgDW')) in revival.areas and str(row.get('qo3PECw6')) in missions)],
            order=lambda rows: sorted(rows, key=lambda row: order.get(str(row.get('uv60hgDW')), len(order))),
            window=lambda spec, chosen: revival.gate_windows(spec))


ANNUAL = AnnualAvailability()
_BY_PROFILE = {'ios-revival': ReplayAvailability()}


def current():
    from engine_profile import current_profile
    return _BY_PROFILE.get(current_profile().name, ANNUAL)
