"""Pure CPK foreground classification and upfront audit policy.

No filesystem, network, or engine-state imports.
"""
from dataclasses import dataclass
import re

POLICY_VERSION = 2

EARLY_PACKS = frozenset(('resources_common.cpk', 'resources.cpk'))
# Gacha detail opens synchronously: its UI and default Ochu preview cannot wait
# behind the background queue (confirmed by native reports on 2026-11-11).
MENU_PACKS = frozenset(('gacha1_common.cpk', 'gacha1.cpk', 'monster3_common.cpk'))
UPFRONT_PACKS = EARLY_PACKS | MENU_PACKS
# Unit list, party, equip, and unit detail scenes load unit icons/illustrations
# synchronously from the `unit` CPK group without triggering on-demand downloads.
UNIT_ART_PACK = re.compile(r'^unit[0-9]+(?:_sg)?(?:_common)?\.cpk$')


@dataclass(frozen=True)
class ForegroundCpkPolicy:
    """Policy descriptor controlling which F_RESOURCE_MST CPK rows block in foreground."""

    name: str
    promote_empty_phase: bool
    promote_define_phase: bool = False
    audit_all_cpks: bool = False


ALL_CPKS = ForegroundCpkPolicy(
    name='all-cpks',
    promote_empty_phase=True,
    promote_define_phase=True,
    audit_all_cpks=True,
)
ALL_EMPTY_CPKS = ForegroundCpkPolicy(
    name='all-empty-cpks',
    promote_empty_phase=True,
    promote_define_phase=False,
    audit_all_cpks=True,
)
LEGACY_MENU_AND_UNITS = ForegroundCpkPolicy(
    name='legacy-menu-and-units',
    promote_empty_phase=False,
    promote_define_phase=False,
    audit_all_cpks=False,
)


def is_cpk_row(row) -> bool:
    """Return True when the F_RESOURCE_MST row identifies a .cpk archive."""
    name = row.get('pJ56sAEo', '')
    return isinstance(name, str) and name.endswith('.cpk')


def is_promoted_menu_pack(row) -> bool:
    """Return True for legacy synchronous menu and non-movie unit artwork CPKs."""
    name = row.get('pJ56sAEo', '')
    if not isinstance(name, str):
        return False
    if name in MENU_PACKS:
        return True
    return row.get('3LHdc6Qa') == 'unit' and bool(UNIT_ART_PACK.fullmatch(name))


def is_upfront_pack(row) -> bool:
    """Return True for legacy early tutorial, menu, and unit artwork CPKs."""
    name = row.get('pJ56sAEo', '')
    return name in EARLY_PACKS or is_promoted_menu_pack(row)


def target_phase(row, policy: ForegroundCpkPolicy | None = None) -> str:
    """Compute the F_RESOURCE_MST download phase (81fTkEDP) for a resource row."""
    active = ALL_CPKS if policy is None else policy
    phase = row.get('81fTkEDP', '')
    if not is_cpk_row(row):
        return phase
    upper = str(phase or '').upper()
    if upper in ('PRE_TUTO', 'TUTO'):
        return phase
    if upper == 'DEFINE':
        return 'TUTO' if active.promote_define_phase else phase
    if upper == '':
        if active.promote_empty_phase or is_upfront_pack(row):
            return 'TUTO'
        return phase
    if is_upfront_pack(row):
        return 'TUTO'
    return phase


def should_audit_upfront(
    row,
    policy: ForegroundCpkPolicy | None = None,
    *,
    exclude_resources=(),
) -> bool:
    """Return True when upfront_resources.collect should audit size and drift for row."""
    active = ALL_CPKS if policy is None else policy
    if not is_cpk_row(row):
        return False
    if row.get('9ZCEWn0z', '') in exclude_resources:
        return False
    if active.audit_all_cpks:
        return True
    return str(target_phase(row, active) or '').upper() in ('TUTO', 'PRE_TUTO') or is_upfront_pack(row)
