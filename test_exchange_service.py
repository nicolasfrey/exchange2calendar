#!/usr/bin/env python3
"""Tests du service Exchange : normalisation des dates et identité des événements."""

import datetime
import os
import sys
import unittest

import pytz
from exchangelib.ewsdatetime import EWSDate, EWSDateTime, EWSTimeZone

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from src.exchange_service import ExchangeCalendarService


class FakeOrganizer:
    def __init__(self, email):
        self.email_address = email


class FakeItem:
    """Imite un exchangelib.CalendarItem tel que renvoyé par CalendarView.

    Rappel exchangelib (fields.py:704) : pour les journées entières, `start` et
    `end` sont des EWSDate et les deux bornes sont INCLUSIVES.
    """

    def __init__(self, start, end, subject="Réunion", item_id="AAA",
                 uid="040000008200E00074C5B7101A82E008", location="",
                 body="", organizer="a@b.c", recurrence_id=None,
                 is_cancelled=False):
        self.start = start
        self.end = end
        self.subject = subject
        self.id = item_id
        self.uid = uid
        self.recurrence_id = recurrence_id
        self.is_cancelled = is_cancelled
        self.location = location
        self.text_body = body
        self.organizer = FakeOrganizer(organizer)
        self.is_all_day = isinstance(start, datetime.date) and not isinstance(start, datetime.datetime)


class FakeQuerySet(list):
    def order_by(self, *_args):
        return self


class FakeCalendar:
    def __init__(self, items):
        self.items = items
        self.view_calls = []

    def view(self, start, end):
        self.view_calls.append((start, end))
        return FakeQuerySet(self.items)


class FakeAccount:
    def __init__(self, items):
        self.calendar = FakeCalendar(items)
        self.primary_smtp_address = "test@example.com"


def build_service(items):
    service = ExchangeCalendarService(username="u", email="e@x.y", password="p")
    service.account = FakeAccount(items)
    return service


WINDOW_START = datetime.datetime(2026, 9, 4, 8, 0, tzinfo=pytz.UTC)
WINDOW_END = WINDOW_START + datetime.timedelta(days=60)


class TestAllDayEndIsExclusive(unittest.TestCase):
    """Google Calendar attend un `end.date` EXCLUSIF, Exchange le donne INCLUSIF."""

    def test_single_day_all_day_event_ends_the_next_day(self):
        # Le cas réel : "Namirial - Fix stamps Production", journée entière du 09/09.
        # Exchange renvoie start == end == 2026-09-09.
        items = [FakeItem(start=EWSDate(2026, 9, 9), end=EWSDate(2026, 9, 9))]

        event = build_service(items).get_events(WINDOW_START, WINDOW_END)[0]

        self.assertTrue(event['all_day'])
        self.assertEqual(event['start'].date(), datetime.date(2026, 9, 9))
        self.assertEqual(event['end'].date(), datetime.date(2026, 9, 10))

    def test_multi_day_all_day_event_keeps_its_last_day(self):
        # Le cas réel : congés du lundi 07/09 au vendredi 11/09 inclus.
        items = [FakeItem(start=EWSDate(2026, 9, 7), end=EWSDate(2026, 9, 11),
                          subject="Absence : Congés Payés (CP)")]

        event = build_service(items).get_events(WINDOW_START, WINDOW_END)[0]

        self.assertEqual(event['start'].date(), datetime.date(2026, 9, 7))
        self.assertEqual(event['end'].date(), datetime.date(2026, 9, 12))

    def test_timed_event_end_is_untouched(self):
        utc = EWSTimeZone('UTC')
        start = EWSDateTime(2026, 9, 7, 8, 0, tzinfo=utc)
        end = EWSDateTime(2026, 9, 7, 9, 0, tzinfo=utc)
        items = [FakeItem(start=start, end=end)]

        event = build_service(items).get_events(WINDOW_START, WINDOW_END)[0]

        self.assertFalse(event['all_day'])
        self.assertEqual(event['end'], datetime.datetime(2026, 9, 7, 9, 0, tzinfo=pytz.UTC))


class TestCancelledMeetings(unittest.TestCase):
    """Une réunion annulée côté Exchange n'a pas à occuper le calendrier."""

    def test_a_cancelled_meeting_is_not_returned(self):
        utc = EWSTimeZone('UTC')
        cancelled = FakeItem(start=EWSDateTime(2026, 9, 14, 8, 0, tzinfo=utc),
                             end=EWSDateTime(2026, 9, 14, 9, 0, tzinfo=utc),
                             subject="Annulé: Suivi, pilotage et coordination de projets",
                             is_cancelled=True)

        events = build_service([cancelled]).get_events(WINDOW_START, WINDOW_END)

        self.assertEqual(events, [])

    def test_an_active_meeting_is_still_returned(self):
        utc = EWSTimeZone('UTC')
        active = FakeItem(start=EWSDateTime(2026, 9, 14, 8, 0, tzinfo=utc),
                          end=EWSDateTime(2026, 9, 14, 9, 0, tzinfo=utc))

        events = build_service([active]).get_events(WINDOW_START, WINDOW_END)

        self.assertEqual(len(events), 1)

    def test_a_declined_meeting_is_kept(self):
        # Décision produit : on garde la visibilité sur ce qui se passe sans nous.
        utc = EWSTimeZone('UTC')
        declined = FakeItem(start=EWSDateTime(2026, 9, 14, 8, 0, tzinfo=utc),
                            end=EWSDateTime(2026, 9, 14, 9, 0, tzinfo=utc))
        declined.my_response_type = 'Decline'

        events = build_service([declined]).get_events(WINDOW_START, WINDOW_END)

        self.assertEqual(len(events), 1)


class TestStableSyncKey(unittest.TestCase):
    """L'identité d'un événement doit survivre à un changement d'ItemId.

    Constaté sur les données réelles : `uid` (iCalUID) est partagé par toutes les
    occurrences d'une série (7 uid pour 18 items), donc insuffisant seul ;
    `uid` + `recurrence_id` donne bien 18 clés distinctes pour 18 items.
    """

    def test_recurring_occurrences_get_distinct_keys(self):
        utc = EWSTimeZone('UTC')
        occ1 = FakeItem(start=EWSDateTime(2026, 9, 7, 8, 0, tzinfo=utc),
                        end=EWSDateTime(2026, 9, 7, 9, 0, tzinfo=utc),
                        item_id="ID-1", uid="SERIE-A",
                        recurrence_id=EWSDateTime(2026, 9, 7, 8, 0, tzinfo=utc))
        occ2 = FakeItem(start=EWSDateTime(2026, 9, 14, 8, 0, tzinfo=utc),
                        end=EWSDateTime(2026, 9, 14, 9, 0, tzinfo=utc),
                        item_id="ID-2", uid="SERIE-A",
                        recurrence_id=EWSDateTime(2026, 9, 14, 8, 0, tzinfo=utc))

        events = build_service([occ1, occ2]).get_events(WINDOW_START, WINDOW_END)

        self.assertNotEqual(events[0]['uid'], events[1]['uid'])

    def test_key_survives_an_item_id_change(self):
        # Le cas réel des absences RH : l'outil recrée l'élément côté serveur,
        # l'ItemId change, mais l'iCalUID reste le même.
        before = FakeItem(start=EWSDate(2026, 9, 9), end=EWSDate(2026, 9, 9),
                          item_id="ITEM-ID-AVANT", uid="ICAL-STABLE")
        after = FakeItem(start=EWSDate(2026, 9, 9), end=EWSDate(2026, 9, 9),
                         item_id="ITEM-ID-APRES", uid="ICAL-STABLE")

        key_before = build_service([before]).get_events(WINDOW_START, WINDOW_END)[0]['uid']
        key_after = build_service([after]).get_events(WINDOW_START, WINDOW_END)[0]['uid']

        self.assertEqual(key_before, key_after)

    def test_falls_back_to_item_id_when_ical_uid_is_missing(self):
        item = FakeItem(start=EWSDate(2026, 9, 9), end=EWSDate(2026, 9, 9),
                        item_id="ITEM-ID-SEUL", uid=None)

        event = build_service([item]).get_events(WINDOW_START, WINDOW_END)[0]

        self.assertEqual(event['uid'], "ITEM-ID-SEUL")

    def test_item_id_is_still_exposed_for_migration(self):
        item = FakeItem(start=EWSDate(2026, 9, 9), end=EWSDate(2026, 9, 9),
                        item_id="ITEM-ID-X", uid="ICAL-Y")

        event = build_service([item]).get_events(WINDOW_START, WINDOW_END)[0]

        self.assertEqual(event['item_id'], "ITEM-ID-X")


if __name__ == '__main__':
    unittest.main()
