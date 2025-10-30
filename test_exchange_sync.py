#!/usr/bin/env python3
import unittest
from datetime import datetime, timezone, date, time, timedelta
import pytz
from unittest.mock import patch, MagicMock, mock_open
import os
import sys

# Import du module à tester
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from exchange_sync import clean_subject, get_exchange_uid, normalize_str, to_utc_datetime, datetimes_equal, parse_google_start, to_py_datetime

class TestExchangeSync(unittest.TestCase):

    def test_clean_subject(self):
        self.assertEqual(clean_subject("[MAIL EXTERNE] Réunion"), "Réunion")
        self.assertEqual(clean_subject("  Réunion  avec  espaces  "), "Réunion avec espaces")
        self.assertEqual(clean_subject(None), "Sans titre")
        self.assertEqual(clean_subject(""), "Sans titre")
        self.assertEqual(clean_subject("[MAIL EXTERNE][MAIL EXTERNE] Test"), "Test")

    def test_get_exchange_uid(self):
        # Test avec extendedProperties
        event = {
            'extendedProperties': {
                'private': {
                    'exchange_uid': '12345'
                }
            }
        }
        self.assertEqual(get_exchange_uid(event), '12345')

        # Test avec description comme fallback
        event = {'description': 'abc123'}
        self.assertEqual(get_exchange_uid(event), 'abc123')

        # Test sans propriétés
        event = {}
        self.assertEqual(get_exchange_uid(event), '')

        # Test avec exception
        event = {'extendedProperties': None}
        self.assertEqual(get_exchange_uid(event), '')

    def test_normalize_str(self):
        self.assertEqual(normalize_str("  test  multiple    spaces  "), "test multiple spaces")
        self.assertEqual(normalize_str(None), "")
        self.assertEqual(normalize_str(""), "")

    def test_to_utc_datetime(self):
        # Test avec dateTime
        dt, all_day = to_utc_datetime({'dateTime': '2023-06-15T10:00:00+02:00'})
        self.assertEqual(dt.hour, 8)  # 10:00 CEST = 08:00 UTC
        self.assertEqual(dt.tzinfo, timezone.utc)
        self.assertFalse(all_day)

        # Test avec date (all-day)
        dt, all_day = to_utc_datetime({'date': '2023-06-15'})
        self.assertEqual(dt.date(), date(2023, 6, 15))
        self.assertEqual(dt.time(), time(0, 0))
        self.assertEqual(dt.tzinfo, timezone.utc)
        self.assertTrue(all_day)

        # Test avec format invalide
        dt, all_day = to_utc_datetime({})
        self.assertIsNone(dt)
        self.assertFalse(all_day)

    def test_datetimes_equal(self):
        dt1 = datetime(2023, 6, 15, 10, 0, 0, tzinfo=timezone.utc)
        dt2 = datetime(2023, 6, 15, 10, 0, 30, tzinfo=timezone.utc)
        dt3 = datetime(2023, 6, 15, 10, 2, 0, tzinfo=timezone.utc)

        # Test avec tolérance par défaut (60 secondes)
        self.assertTrue(datetimes_equal(dt1, dt2))
        self.assertFalse(datetimes_equal(dt1, dt3))

        # Test avec tolérance personnalisée
        self.assertTrue(datetimes_equal(dt1, dt3, tolerance=120))
        self.assertFalse(datetimes_equal(dt1, dt3, tolerance=30))

        # Test avec None
        self.assertFalse(datetimes_equal(None, dt1))
        self.assertFalse(datetimes_equal(dt1, None))
        self.assertFalse(datetimes_equal(None, None))

    def test_parse_google_start(self):
        # Test avec dateTime
        dt = parse_google_start({'start': {'dateTime': '2023-06-15T10:00:00+02:00'}})
        self.assertEqual(dt.year, 2023)
        self.assertEqual(dt.month, 6)
        self.assertEqual(dt.day, 15)
        self.assertEqual(dt.hour, 10)
        self.assertEqual(dt.minute, 0)

        # Test avec date (all-day)
        dt = parse_google_start({'start': {'date': '2023-06-15'}})
        self.assertEqual(dt.date(), date(2023, 6, 15))
        self.assertEqual(dt.time(), time(0, 0))
        self.assertEqual(dt.tzinfo, timezone.utc)

        # Test sans start
        self.assertIsNone(parse_google_start({}))

        # Test avec start vide
        self.assertIsNone(parse_google_start({'start': {}}))

    def test_to_py_datetime(self):
        # Mock pour simuler EWSDateTime sans utiliser patch
        class MockEWSDateTime:
            def __init__(self):
                self.year = 2023
                self.month = 6
                self.day = 15
                self.hour = 10
                self.minute = 0
                self.second = 0
                self.tzinfo = None

            def replace(self, **kwargs):
                # Simuler la méthode replace
                return datetime(self.year, self.month, self.day,
                               self.hour, self.minute, self.second,
                               tzinfo=kwargs.get('tzinfo'))

            def astimezone(self, tz):
                raise Exception("Erreur de conversion")

        # Test avec une date simple
        d = date(2023, 6, 15)
        dt = to_py_datetime(d)
        self.assertEqual(dt.date(), date(2023, 6, 15))
        self.assertEqual(dt.time(), time(0, 0))
        # Vérification de l'attribut tzinfo différemment pour gérer pytz.UTC et timezone.utc
        self.assertTrue(dt.tzinfo is not None)
        self.assertEqual(dt.tzname(), 'UTC')  # Les deux types de timezone ont le même nom

        # Test avec datetime Python
        dt_py = datetime(2023, 6, 15, 10, 0, tzinfo=timezone.utc)
        dt = to_py_datetime(dt_py)
        self.assertEqual(dt, dt_py)

        # Test avec type inconnu
        self.assertIsNone(to_py_datetime("2023-06-15"))

if __name__ == '__main__':
    unittest.main()