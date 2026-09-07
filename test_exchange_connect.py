#!/usr/bin/env python3
"""Tests de la connexion Exchange : cache d'endpoint et résilience."""

import json
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from src.exchange_service import ExchangeCalendarService

ENDPOINT = "https://mail.lacooperativewelcoop.com/EWS/Exchange.asmx"


def make_service(cache_path):
    return ExchangeCalendarService(username="GROUPE\\u", email="u@x.y", password="p",
                                   endpoint_cache_path=cache_path)


def account_stub(endpoint=ENDPOINT, auth_type="NTLM"):
    account = MagicMock()
    account.primary_smtp_address = "u@x.y"
    account.protocol.service_endpoint = endpoint
    account.protocol.auth_type = auth_type
    return account


class TestEndpointCache(unittest.TestCase):

    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.cache = os.path.join(self._dir.name, 'endpoint.json')
        self.addCleanup(self._dir.cleanup)

    def test_autodiscover_result_is_cached(self):
        with patch('src.exchange_service.Account', return_value=account_stub()) as Account:
            self.assertTrue(make_service(self.cache).connect())
            self.assertTrue(Account.call_args.kwargs['autodiscover'])

        with open(self.cache) as fh:
            self.assertEqual(json.load(fh)['service_endpoint'], ENDPOINT)

    def test_cached_endpoint_avoids_autodiscover(self):
        with open(self.cache, 'w') as fh:
            json.dump({'service_endpoint': ENDPOINT, 'auth_type': 'NTLM'}, fh)

        with patch('src.exchange_service.Account', return_value=account_stub()) as Account, \
             patch('src.exchange_service.Configuration') as Configuration:
            self.assertTrue(make_service(self.cache).connect())

        self.assertFalse(Account.call_args.kwargs['autodiscover'])
        self.assertEqual(Configuration.call_args.kwargs['service_endpoint'], ENDPOINT)

    def test_a_stale_cached_endpoint_falls_back_to_autodiscover(self):
        with open(self.cache, 'w') as fh:
            json.dump({'service_endpoint': "https://ancien/EWS/Exchange.asmx",
                       'auth_type': 'NTLM'}, fh)

        calls = []

        def account(**kwargs):
            calls.append(kwargs)
            if not kwargs['autodiscover']:
                raise ConnectionError("endpoint obsolète")
            return account_stub()

        with patch('src.exchange_service.Account', side_effect=account), \
             patch('src.exchange_service.Configuration'), \
             patch('src.utils.retry_utils.time.sleep'):
            self.assertTrue(make_service(self.cache).connect())

        self.assertEqual([c['autodiscover'] for c in calls], [False, True])
        with open(self.cache) as fh:
            self.assertEqual(json.load(fh)['service_endpoint'], ENDPOINT)


class TestConnectRetries(unittest.TestCase):

    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.cache = os.path.join(self._dir.name, 'endpoint.json')
        self.addCleanup(self._dir.cleanup)

    def test_a_transient_autodiscover_failure_is_retried(self):
        # Cas réel dans sync.log : "All steps in the autodiscover protocol failed",
        # 6 fois, toujours au premier run après un réveil de la machine.
        attempts = []

        def account(**kwargs):
            attempts.append(kwargs)
            if len(attempts) < 2:
                raise ConnectionError("autodiscover indisponible")
            return account_stub()

        with patch('src.exchange_service.Account', side_effect=account), \
             patch('src.utils.retry_utils.time.sleep'):
            self.assertTrue(make_service(self.cache).connect())

        self.assertEqual(len(attempts), 2)

    def test_connect_still_returns_false_when_everything_fails(self):
        with patch('src.exchange_service.Account', side_effect=ConnectionError("ko")), \
             patch('src.utils.retry_utils.time.sleep'):
            self.assertFalse(make_service(self.cache).connect())


class TestGetEventsRetries(unittest.TestCase):

    def test_a_read_timeout_is_retried(self):
        # Cas réel dans sync.log : "Read timed out. (read timeout=120)".
        import datetime
        import pytz

        service = ExchangeCalendarService(username="u", email="u@x.y", password="p")
        service.account = MagicMock()
        views = [TimeoutError("read timed out"), MagicMock(**{'order_by.return_value': []})]
        service.account.calendar.view.side_effect = views

        with patch('src.utils.retry_utils.time.sleep'):
            events = service.get_events(datetime.datetime.now(pytz.UTC),
                                        datetime.datetime.now(pytz.UTC))

        self.assertEqual(events, [])
        self.assertEqual(service.account.calendar.view.call_count, 2)


if __name__ == '__main__':
    unittest.main()
