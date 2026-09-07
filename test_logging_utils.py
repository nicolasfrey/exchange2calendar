#!/usr/bin/env python3
"""Tests de la configuration du journal."""

import io
import logging
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from src.utils.logging_utils import configure_logging

TIMESTAMPED = r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} '


class TestConfigureLogging(unittest.TestCase):

    def tearDown(self):
        logging.getLogger().handlers.clear()

    def test_each_line_carries_a_timestamp_and_a_level(self):
        stream = io.StringIO()
        configure_logging(stream=stream)

        logging.getLogger('src.exemple').info("synchronisation démarrée")

        self.assertRegex(stream.getvalue(), TIMESTAMPED + r'INFO\s+synchronisation démarrée')

    def test_warnings_are_labelled(self):
        stream = io.StringIO()
        configure_logging(stream=stream)

        logging.getLogger('src.exemple').warning("endpoint inutilisable")

        self.assertRegex(stream.getvalue(), TIMESTAMPED + r'WARNING\s+endpoint inutilisable')

    def test_configuring_twice_does_not_duplicate_lines(self):
        stream = io.StringIO()
        configure_logging(stream=stream)
        configure_logging(stream=stream)

        logging.getLogger('src.exemple').info("une seule fois")

        self.assertEqual(stream.getvalue().count("une seule fois"), 1)


class TestThirdPartyNoise(unittest.TestCase):
    """googleapiclient bavarde en INFO (« file_cache is only supported... ») :
    ce bruit noierait le journal de synchronisation."""

    def tearDown(self):
        logging.getLogger().handlers.clear()

    def test_third_party_info_is_dropped(self):
        stream = io.StringIO()
        configure_logging(stream=stream)

        logging.getLogger('googleapiclient.discovery_cache').info(
            "file_cache is only supported with oauth2client<4.0.0")

        self.assertEqual(stream.getvalue(), "")

    def test_third_party_warnings_still_get_through(self):
        stream = io.StringIO()
        configure_logging(stream=stream)

        logging.getLogger('googleapiclient.http').warning("quota bientôt atteint")

        self.assertIn("quota bientôt atteint", stream.getvalue())

    def test_our_own_info_is_kept(self):
        stream = io.StringIO()
        configure_logging(stream=stream)

        logging.getLogger('src.synchronizer').info("synchronisation terminée")

        self.assertIn("synchronisation terminée", stream.getvalue())


class TestModulesUseLogging(unittest.TestCase):
    """Le diagnostic d'un run échoué a besoin de l'heure de chaque étape ;
    `print` ne la fournit pas."""

    def test_the_synchronizer_reports_through_logging(self):
        import datetime
        import pytz
        from test_synchronizer import TZ, exchange_timed, run_sync

        now = TZ.localize(datetime.datetime(2026, 9, 9, 10, 2)).astimezone(pytz.UTC)
        events = [exchange_timed('UID-A', now + datetime.timedelta(days=1))]

        with self.assertLogs('src.synchronizer', level='INFO') as captured:
            run_sync(events, [], now)

        self.assertTrue(any('Nouveau' in line for line in captured.output),
                        f"aucune trace de création : {captured.output}")

    def test_the_exchange_service_reports_through_logging(self):
        from unittest.mock import MagicMock, patch
        from src.exchange_service import ExchangeCalendarService

        account = MagicMock()
        account.primary_smtp_address = "u@x.y"
        account.protocol.service_endpoint = "https://x/EWS/Exchange.asmx"
        account.protocol.auth_type = "NTLM"

        with patch('src.exchange_service.Account', return_value=account), \
             self.assertLogs('src.exchange_service', level='INFO') as captured:
            ExchangeCalendarService("u", "u@x.y", "p",
                                    endpoint_cache_path="/dev/null").connect()

        self.assertTrue(any('Connecté' in line for line in captured.output),
                        f"aucune trace de connexion : {captured.output}")


if __name__ == '__main__':
    unittest.main()
