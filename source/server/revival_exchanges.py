"""Read-only exchange eligibility; commands still use the canonical payment transaction."""
from dataclasses import dataclass
from datetime import timedelta, timezone
from functools import lru_cache
import copy
import json
from pathlib import Path

import revival_events
import revival_summons


@lru_cache(maxsize=1)
def event_shops():
    return json.loads(Path(__file__).with_name('content').joinpath('event_shops.json').read_text(encoding='utf-8'))['shops']


@dataclass(frozen=True)
class ExchangePolicy:
    data: dict
    events: revival_events.EventPlan

    @property
    def anchored(self):
        return self.events.context['summons'].anchored

    def held(self, kind, currency):
        return sum(int(row['count']) for row in self.data.get('inventory', {}).get('items', [])
                   if str(row['item_type']) == str(kind) and str(row['item_id']) == str(currency))

    def rewards_allowed(self, rewards):
        current = self.events.context['summons']
        if current.finished:
            return True
        cutoff = current.window['to']  # Exclusive, with no summon-ticket or featured-unit exemption.
        dates = revival_summons.unit_dates()
        return all(int(row['kind']) != 10 or dates.get(str(row['id']), '') < cutoff for row in rewards)

    def detail_open(self, offer):
        areas = offer.get('event_areas')
        if areas is None:
            return True
        return bool(self.events.areas.intersection(map(str, areas)) or self.held(*offer['cost']))

    def merchant_open(self, banners, currencies):
        return not banners or bool(set(map(str, banners)).intersection(self.events.context['summons'].ids) or
                                    any(self.held(20, currency) for currency in currencies))

    def filter_catalogue(self, raw):
        details, products, offers = raw
        kept = {pid: offer for pid, offer in offers.items()
                if self.detail_open(offer) and self.rewards_allowed(offer['rewards'])}
        detail_ids = {offer['detail'] for offer in kept.values()}
        shown_details = [copy.deepcopy(row) for row in details if row['3X1gLufw'] in detail_ids]
        shown_products = [copy.deepcopy(row) for row in products if row['jPV7Xc4N'] in kept]
        event_ids = {offer['detail'] for offer in kept.values() if offer.get('event_areas') is not None}
        week = self.events.context['week']
        first = week.starts.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
        last = (week.ends.astimezone(timezone.utc) - timedelta(seconds=1)).strftime('%Y-%m-%d %H:%M:%S')
        for row in shown_details + shown_products:
            if row['3X1gLufw'] in event_ids:
                row.update(VjJQ51uG=first, m8ivD4NX=last)
        return shown_details, shown_products, copy.deepcopy(kept)

    def describe(self):
        return [{'id': str(850002000 + index), 'name': shop['name'], 'currency': shop['currency'],
                 'held_currency': self.held(*shop['currency'])}
                for index, shop in enumerate(event_shops())
                if self.detail_open({'event_areas': shop['event_areas'], 'cost': shop['currency']})]


def policy(data, now=None, *, events=None):
    return ExchangePolicy(data, events if events is not None else revival_events.plan(data, now))
