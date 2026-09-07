#!/usr/bin/env python3
"""Tests du service Google : résilience de l'authentification."""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from src.google_service import GoogleCalendarService


class TestAuthenticateRetries(unittest.TestCase):

    def _valid_creds(self):
        creds = MagicMock()
        creds.valid = True
        return creds

    def test_a_transient_dns_failure_on_build_is_retried(self):
        # Cas réel dans sync.log : "Unable to find the server at www.googleapis.com".
        service = object()
        with patch('src.google_service.os.path.exists', return_value=True), \
             patch('src.google_service.Credentials.from_authorized_user_file',
                   return_value=self._valid_creds()), \
             patch('src.utils.retry_utils.time.sleep'), \
             patch('src.google_service.build',
                   side_effect=[ConnectionError("dns"), service]) as build:
            result = GoogleCalendarService.authenticate()

        self.assertIs(result, service)
        self.assertEqual(build.call_count, 2)

    def test_the_error_is_propagated_when_every_attempt_fails(self):
        with patch('src.google_service.os.path.exists', return_value=True), \
             patch('src.google_service.Credentials.from_authorized_user_file',
                   return_value=self._valid_creds()), \
             patch('src.utils.retry_utils.time.sleep'), \
             patch('src.google_service.build', side_effect=ConnectionError("dns")):
            with self.assertRaises(ConnectionError):
                GoogleCalendarService.authenticate()


if __name__ == '__main__':
    unittest.main()
