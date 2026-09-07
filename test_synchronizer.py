#!/usr/bin/env python3
"""Tests du synchroniseur Exchange -> Google Calendar."""

import contextlib
import datetime
import io
import itertools
import os
import sys
import unittest
import unittest.mock

import pytz

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from src.synchronizer import CalendarSynchronizer

TZ = pytz.timezone('Europe/Paris')
CALENDAR_ID = 'cal@group.calendar.google.com'

# Valeur par défaut réelle de l'API Google Calendar pour events.list.
GOOGLE_DEFAULT_MAX_RESULTS = 250


# --------------------------------------------------------------------------- #
# Faux service Google Calendar
# --------------------------------------------------------------------------- #

def google_bounds(event, tz=TZ):
    """Bornes absolues d'un événement Google, comme les calcule l'API.

    Pour une journée entière, les dates sont interprétées dans le fuseau du
    calendrier et `end.date` est EXCLUSIF.
    """
    start, end = event['start'], event['end']

    if 'date' in start:
        s = datetime.date.fromisoformat(start['date'])
        e = datetime.date.fromisoformat(end['date'])
        return (tz.localize(datetime.datetime.combine(s, datetime.time.min)),
                tz.localize(datetime.datetime.combine(e, datetime.time.min)))

    return (datetime.datetime.fromisoformat(start['dateTime'].replace('Z', '+00:00')),
            datetime.datetime.fromisoformat(end['dateTime'].replace('Z', '+00:00')))


class _Request:
    def __init__(self, fn):
        self._fn = fn

    def execute(self):
        return self._fn()


class FakeGoogleEventsResource:
    def __init__(self, service):
        self._s = service

    def list(self, calendarId, timeMin, timeMax, singleEvents=True,
             maxResults=None, pageToken=None, **_kwargs):
        def run():
            if self._s.fail_list_times > 0:
                self._s.fail_list_times -= 1
                raise ConnectionError('googleapis injoignable')
            self._s.list_calls.append({'timeMin': timeMin, 'timeMax': timeMax,
                                       'maxResults': maxResults, 'pageToken': pageToken})
            lo = datetime.datetime.fromisoformat(timeMin.replace('Z', '+00:00'))
            hi = datetime.datetime.fromisoformat(timeMax.replace('Z', '+00:00'))

            # Sémantique documentée : timeMin est une borne basse EXCLUSIVE sur la
            # fin de l'événement, timeMax une borne haute exclusive sur son début.
            matching = []
            for ev in self._s.store.values():
                s, e = google_bounds(ev)
                if e > lo and s < hi:
                    matching.append(ev)
            matching.sort(key=lambda ev: google_bounds(ev)[0])

            page_size = min(maxResults or GOOGLE_DEFAULT_MAX_RESULTS,
                            self._s.page_size_limit)
            offset = int(pageToken) if pageToken else 0
            page = matching[offset:offset + page_size]
            result = {'items': page}

            if offset + page_size < len(matching):
                result['nextPageToken'] = str(offset + page_size)

            return result

        return _Request(run)

    def insert(self, calendarId, body):
        def run():
            assert calendarId == CALENDAR_ID
            event = dict(body)
            event['id'] = f"g{next(self._s.ids)}"
            self._s.store[event['id']] = event
            self._s.inserted.append(event)
            return event

        return _Request(run)

    def update(self, calendarId, eventId, body):
        def run():
            assert calendarId == CALENDAR_ID
            if eventId not in self._s.store:
                raise AssertionError(f"update sur un id inconnu: {eventId}")
            event = dict(body)
            event['id'] = eventId
            self._s.store[eventId] = event
            self._s.updated.append(eventId)
            return event

        return _Request(run)

    def delete(self, calendarId, eventId):
        def run():
            assert calendarId == CALENDAR_ID
            if eventId not in self._s.store:
                raise AssertionError(f"delete sur un id inconnu: {eventId}")
            del self._s.store[eventId]
            self._s.deleted.append(eventId)
            return None

        return _Request(run)


class FakeGoogleService:
    def __init__(self, events=(), page_size_limit=2500, fail_list_times=0):
        self.fail_list_times = fail_list_times
        # L'API peut renvoyer moins que `maxResults` et poser malgré tout un
        # nextPageToken : le client doit suivre la pagination dans tous les cas.
        self.page_size_limit = page_size_limit
        self.ids = itertools.count(1)
        self.store = {}
        self.inserted, self.updated, self.deleted, self.list_calls = [], [], [], []
        for ev in events:
            ev = dict(ev)
            ev.setdefault('id', f"g{next(self.ids)}")
            self.store[ev['id']] = ev

    def events(self):
        return FakeGoogleEventsResource(self)

    def summaries(self):
        return sorted(ev.get('summary', '') for ev in self.store.values())


# --------------------------------------------------------------------------- #
# Faux service Exchange
# --------------------------------------------------------------------------- #

class FakeExchangeService:
    def __init__(self, events=()):
        self._events = list(events)
        self.windows = []

    def get_events(self, start, end):
        self.windows.append((start, end))
        # Imite CalendarView : renvoie les éléments qui CHEVAUCHENT la fenêtre.
        return [e for e in self._events if e['end'] > start and e['start'] < end]


# --------------------------------------------------------------------------- #
# Fabriques
# --------------------------------------------------------------------------- #

def exchange_all_day(uid, first_day, nb_days=1, subject="Journée entière", body=""):
    """Événement Exchange journée entière, `end` déjà en convention EXCLUSIVE."""
    start = datetime.datetime.combine(first_day, datetime.time.min, tzinfo=pytz.UTC)
    return {'uid': uid, 'item_id': uid, 'subject': subject, 'location': '',
            'start': start, 'end': start + datetime.timedelta(days=nb_days),
            'all_day': True, 'body': body, 'organizer': ''}


def exchange_timed(uid, start, minutes=60, subject="Réunion", body="", location=""):
    return {'uid': uid, 'item_id': uid, 'subject': subject, 'location': location,
            'start': start, 'end': start + datetime.timedelta(minutes=minutes),
            'all_day': False, 'body': body, 'organizer': ''}


def google_all_day(uid, start_date, end_date, subject="Journée entière", body="", eid=None):
    ev = {'summary': subject, 'location': '', 'description': body,
          'start': {'date': start_date.isoformat()},
          'end': {'date': end_date.isoformat()},
          'extendedProperties': {'private': {'exchange_uid': uid}}}
    if eid:
        ev['id'] = eid
    return ev


def google_timed(uid, start, minutes=60, subject="Réunion", body="", eid=None, location=""):
    end = start + datetime.timedelta(minutes=minutes)
    ev = {'summary': subject, 'location': location, 'description': body,
          'start': {'dateTime': start.isoformat(), 'timeZone': 'Europe/Paris'},
          'end': {'dateTime': end.isoformat(), 'timeZone': 'Europe/Paris'},
          'extendedProperties': {'private': {'exchange_uid': uid}}}
    if eid:
        ev['id'] = eid
    return ev


def google_manual(start, minutes=60, subject="Événement à moi", body="", eid=None):
    """Événement créé à la main dans Google : aucune propriété de synchro."""
    end = start + datetime.timedelta(minutes=minutes)
    ev = {'summary': subject, 'location': '', 'description': body,
          'start': {'dateTime': start.isoformat(), 'timeZone': 'Europe/Paris'},
          'end': {'dateTime': end.isoformat(), 'timeZone': 'Europe/Paris'}}
    if eid:
        ev['id'] = eid
    return ev


def run_sync(exchange_events, google_events, now, days_ahead=60, dry_run=False,
             page_size_limit=2500, fail_list_times=0):
    """Exécute une synchronisation à un instant donné et renvoie (google, stats)."""
    google = FakeGoogleService(google_events, page_size_limit=page_size_limit,
                               fail_list_times=fail_list_times)
    exchange = FakeExchangeService(exchange_events)
    sync = CalendarSynchronizer(exchange_service=exchange, google_service=google,
                                calendar_id=CALENDAR_ID, timezone='Europe/Paris',
                                clock=lambda: now)
    with contextlib.redirect_stdout(io.StringIO()):
        stats = sync.synchronize(days_ahead=days_ahead, dry_run=dry_run)
    return google, exchange, stats


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #

class TestAllDayDuplication(unittest.TestCase):
    """Régression du bug constaté : all-day du jour recréé à chaque run."""

    def test_zero_length_all_day_event_is_repaired_not_duplicated(self):
        # État laissé par l'ancien code buggé : start == end (longueur zéro).
        # Le 09/09 à 10h, l'API Google ne renvoie plus cet événement si on
        # interroge avec timeMin=maintenant -> l'ancien code en recréait un.
        day = datetime.date(2026, 9, 9)
        exchange_events = [exchange_all_day('UID-A', day, subject="Namirial - Fix stamps Production")]
        google_events = [google_all_day('UID-A', day, day, subject="Namirial - Fix stamps Production")]
        now = TZ.localize(datetime.datetime(2026, 9, 9, 10, 2)).astimezone(pytz.UTC)

        google, _, (created, updated, deleted) = run_sync(exchange_events, google_events, now)

        self.assertEqual(len(google.store), 1, f"doublon créé : {google.summaries()}")
        self.assertEqual(created, 0)
        self.assertEqual(updated, 1)
        remaining = next(iter(google.store.values()))
        self.assertEqual(remaining['end']['date'], '2026-09-10')

    def test_all_day_event_of_the_day_is_stable_across_two_runs(self):
        day = datetime.date(2026, 9, 9)
        exchange_events = [exchange_all_day('UID-A', day)]
        morning = TZ.localize(datetime.datetime(2026, 9, 9, 8, 2)).astimezone(pytz.UTC)
        evening = TZ.localize(datetime.datetime(2026, 9, 9, 20, 2)).astimezone(pytz.UTC)

        google, _, _ = run_sync(exchange_events, [], morning)
        synced = list(google.store.values())

        google2, _, (created, updated, deleted) = run_sync(exchange_events, synced, evening)

        self.assertEqual(len(google2.store), 1)
        self.assertEqual((created, updated, deleted), (0, 0, 0))


class TestDuplicateCleanup(unittest.TestCase):
    """Les doublons déjà présents doivent être supprimés, pas ignorés."""

    def test_existing_duplicates_are_deleted(self):
        day = datetime.date(2026, 9, 9)
        exchange_events = [exchange_all_day('UID-A', day)]
        google_events = [google_all_day('UID-A', day, day + datetime.timedelta(days=1), eid=f"dup{i}")
                         for i in range(5)]
        now = TZ.localize(datetime.datetime(2026, 9, 9, 10, 2)).astimezone(pytz.UTC)

        google, _, (created, updated, deleted) = run_sync(exchange_events, google_events, now)

        self.assertEqual(len(google.store), 1, f"doublons restants : {list(google.store)}")
        self.assertEqual(created, 0)
        self.assertEqual(deleted, 4)


class TestDryRun(unittest.TestCase):
    """--dry-run doit rapporter le diff réel sans rien modifier."""

    def test_dry_run_reports_changes_without_touching_google(self):
        day = datetime.date(2026, 9, 9)
        now = TZ.localize(datetime.datetime(2026, 9, 9, 10, 2)).astimezone(pytz.UTC)
        exchange_events = [
            exchange_all_day('UID-A', day),
            exchange_timed('UID-B', now + datetime.timedelta(days=1)),
        ]

        google, _, (created, updated, deleted) = run_sync(
            exchange_events, [], now, dry_run=True)

        self.assertEqual((created, updated, deleted), (2, 0, 0))
        self.assertEqual(google.inserted, [])
        self.assertEqual(len(google.store), 0)

    def test_dry_run_reports_deletions_without_touching_google(self):
        day = datetime.date(2026, 9, 9)
        now = TZ.localize(datetime.datetime(2026, 9, 9, 10, 2)).astimezone(pytz.UTC)
        orphan = google_all_day('UID-DISPARU', day, day + datetime.timedelta(days=1), eid='orphan')

        google, _, (created, updated, deleted) = run_sync([], [orphan], now, dry_run=True)

        self.assertEqual((created, updated, deleted), (0, 0, 1))
        self.assertEqual(google.deleted, [])
        self.assertIn('orphan', google.store)


class TestGooglePagination(unittest.TestCase):
    """Sans suivre nextPageToken, tout ce qui dépasse une page est recréé."""

    def test_events_beyond_the_first_page_are_not_recreated(self):
        now = TZ.localize(datetime.datetime(2026, 9, 9, 10, 2)).astimezone(pytz.UTC)
        base = now + datetime.timedelta(days=1)
        exchange_events = [exchange_timed(f'UID-{i}', base + datetime.timedelta(hours=i))
                           for i in range(5)]
        google_events = [google_timed(f'UID-{i}', base + datetime.timedelta(hours=i), eid=f'g{i}')
                         for i in range(5)]

        google, _, (created, updated, deleted) = run_sync(
            exchange_events, google_events, now, page_size_limit=2)

        self.assertEqual((created, updated, deleted), (0, 0, 0))
        self.assertEqual(len(google.store), 5)


class TestManualEventsArePreserved(unittest.TestCase):
    """La synchro ne doit toucher qu'aux événements qu'elle a elle-même créés."""

    def test_manual_event_with_a_description_is_not_deleted(self):
        # get_exchange_uid retombait sur `description` : un événement manuel
        # décrit se voyait attribuer un UID absent d'Exchange, donc supprimé.
        now = TZ.localize(datetime.datetime(2026, 9, 9, 10, 2)).astimezone(pytz.UTC)
        manual = google_manual(now + datetime.timedelta(days=2),
                               subject="Dentiste", body="ne pas oublier la carte vitale",
                               eid='manuel')

        google, _, (created, updated, deleted) = run_sync([], [manual], now)

        self.assertIn('manuel', google.store, "un événement manuel a été supprimé")
        self.assertEqual((created, updated, deleted), (0, 0, 0))

    def test_manual_event_is_never_updated(self):
        now = TZ.localize(datetime.datetime(2026, 9, 9, 10, 2)).astimezone(pytz.UTC)
        manual = google_manual(now + datetime.timedelta(days=2), body="note perso", eid='manuel')

        google, _, _ = run_sync([], [manual], now)

        self.assertEqual(google.updated, [])


class TestLongDescription(unittest.TestCase):
    """Le corps est tronqué à l'écriture : la comparaison doit l'être aussi."""

    def test_long_body_does_not_trigger_an_update_on_every_run(self):
        now = TZ.localize(datetime.datetime(2026, 9, 9, 10, 2)).astimezone(pytz.UTC)
        long_body = "x" * 20000
        exchange_events = [exchange_timed('UID-LONG', now + datetime.timedelta(days=1),
                                          body=long_body)]

        google, _, _ = run_sync(exchange_events, [], now)
        synced = list(google.store.values())

        google2, _, (created, updated, deleted) = run_sync(exchange_events, synced, now)

        self.assertEqual((created, updated, deleted), (0, 0, 0))


class TestLegacyKeyMigration(unittest.TestCase):
    """Le passage de l'ancienne clé (ItemId) à la nouvelle ne doit pas tout recréer."""

    def test_event_stored_under_the_legacy_item_id_is_reused(self):
        now = TZ.localize(datetime.datetime(2026, 9, 9, 10, 2)).astimezone(pytz.UTC)
        start = now + datetime.timedelta(days=1)
        event = exchange_timed('ICAL-1|2026-09-10T12:00:00+00:00', start)
        event['item_id'] = 'ANCIEN-ITEM-ID'
        legacy = google_timed('ANCIEN-ITEM-ID', start, eid='legacy')

        google, _, (created, updated, deleted) = run_sync([event], [legacy], now)

        self.assertEqual((created, deleted), (0, 0))
        self.assertIn('legacy', google.store)

    def test_legacy_event_is_rekeyed_to_the_new_uid(self):
        now = TZ.localize(datetime.datetime(2026, 9, 9, 10, 2)).astimezone(pytz.UTC)
        start = now + datetime.timedelta(days=1)
        new_uid = 'ICAL-1|2026-09-10T12:00:00+00:00'
        event = exchange_timed(new_uid, start, subject="Titre modifié")
        event['item_id'] = 'ANCIEN-ITEM-ID'
        legacy = google_timed('ANCIEN-ITEM-ID', start, subject="Ancien titre", eid='legacy')

        google, _, _ = run_sync([event], [legacy], now)

        stored = google.store['legacy']
        self.assertEqual(
            stored['extendedProperties']['private']['exchange_uid'], new_uid)

    def test_legacy_event_is_rekeyed_even_when_nothing_else_changed(self):
        now = TZ.localize(datetime.datetime(2026, 9, 9, 10, 2)).astimezone(pytz.UTC)
        start = now + datetime.timedelta(days=1)
        new_uid = 'ICAL-1|2026-09-10T12:00:00+00:00'
        event = exchange_timed(new_uid, start)
        event['item_id'] = 'ANCIEN-ITEM-ID'
        legacy = google_timed('ANCIEN-ITEM-ID', start, eid='legacy')

        google, _, (created, updated, deleted) = run_sync([event], [legacy], now)

        self.assertEqual((created, updated, deleted), (0, 1, 0))
        self.assertEqual(
            google.store['legacy']['extendedProperties']['private']['exchange_uid'],
            new_uid)


class TestDeletionWindow(unittest.TestCase):
    """Bornes de la passe de suppression."""

    def test_event_cancelled_earlier_today_is_deleted(self):
        # L'ancien garde-fou (`start > maintenant`) laissait ces événements en place.
        now = TZ.localize(datetime.datetime(2026, 9, 9, 16, 2)).astimezone(pytz.UTC)
        this_morning = TZ.localize(datetime.datetime(2026, 9, 9, 10, 0)).astimezone(pytz.UTC)
        stale = google_timed('UID-ANNULE', this_morning, eid='stale')

        google, _, (created, updated, deleted) = run_sync([], [stale], now)

        self.assertNotIn('stale', google.store)
        self.assertEqual(deleted, 1)

    def test_past_event_outside_the_window_is_preserved(self):
        # Hors fenêtre Exchange : son absence ne prouve pas une suppression.
        now = TZ.localize(datetime.datetime(2026, 9, 9, 10, 2)).astimezone(pytz.UTC)
        yesterday = TZ.localize(datetime.datetime(2026, 9, 8, 10, 0)).astimezone(pytz.UTC)
        old = google_timed('UID-HIER', yesterday, eid='hier')

        google, _, (created, updated, deleted) = run_sync([], [old], now)

        self.assertIn('hier', google.store)
        self.assertEqual(deleted, 0)

    def test_exchange_window_starts_at_local_midnight(self):
        now = TZ.localize(datetime.datetime(2026, 9, 9, 16, 2)).astimezone(pytz.UTC)

        _, exchange, _ = run_sync([], [], now)

        window_start = exchange.windows[0][0].astimezone(TZ)
        self.assertEqual(window_start.date(), datetime.date(2026, 9, 9))
        self.assertEqual((window_start.hour, window_start.minute), (0, 0))


class TestGoogleReadRetries(unittest.TestCase):

    def test_a_transient_failure_while_listing_is_retried(self):
        now = TZ.localize(datetime.datetime(2026, 9, 9, 10, 2)).astimezone(pytz.UTC)
        start = now + datetime.timedelta(days=1)
        exchange_events = [exchange_timed('UID-A', start)]
        google_events = [google_timed('UID-A', start, eid='g1')]

        with unittest.mock.patch('src.utils.retry_utils.time.sleep'):
            google, _, (created, updated, deleted) = run_sync(
                exchange_events, google_events, now, fail_list_times=1)

        # Sans réessai, la liste vide ferait recréer l'événement.
        self.assertEqual((created, updated, deleted), (0, 0, 0))
        self.assertEqual(len(google.store), 1)


if __name__ == '__main__':
    unittest.main()
