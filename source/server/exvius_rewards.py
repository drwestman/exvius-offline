"""Decode native reward tuples against canonical unit masters."""
from player_state import unit_mst
from reward_tuples import parse as parse_tuples


def parse(raw):
    return parse_tuples(raw, unit_mst)
