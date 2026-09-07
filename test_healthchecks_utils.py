#!/usr/bin/env python3
"""Tests des pings healthchecks.io : confiance TLS et résilience réseau."""

import os
import sys
import unittest
from unittest.mock import patch

import requests

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from src.utils.healthchecks_utils import resolve_ssl_verify, send_healthcheck_ping

ENV = {"HEALTHCHECK_URL": "https://hc-ping.com/abc"}


class FakeResponse:
    def __init__(self, status_code=200, text="ok"):
        self.status_code = status_code
        self.text = text


class TestResolveSslVerify(unittest.TestCase):
    """Le pare-feu Fortinet réémet les certificats : sa CA est dans le magasin
    système, mais `requests` utilise le bundle certifi par défaut."""

    def test_defaults_to_verification_enabled(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertIs(resolve_ssl_verify(), True)

    def test_uses_the_ca_bundle_when_provided(self):
        with patch.dict(os.environ, {"CA_BUNDLE": "/etc/ssl/certs/ca-certificates.crt"}, clear=True):
            self.assertEqual(resolve_ssl_verify(), "/etc/ssl/certs/ca-certificates.crt")

    def test_verify_ssl_false_still_disables_verification(self):
        with patch.dict(os.environ, {"VERIFY_SSL": "false"}, clear=True):
            self.assertIs(resolve_ssl_verify(), False)

    def test_verify_ssl_false_wins_over_the_ca_bundle(self):
        with patch.dict(os.environ, {"VERIFY_SSL": "false", "CA_BUNDLE": "/x.crt"}, clear=True):
            self.assertIs(resolve_ssl_verify(), False)


class TestPingUsesResolvedVerify(unittest.TestCase):

    def test_ca_bundle_is_passed_to_requests(self):
        env = dict(ENV, CA_BUNDLE="/etc/ssl/certs/ca-certificates.crt")
        with patch.dict(os.environ, env, clear=True), \
             patch.object(requests, 'get', return_value=FakeResponse()) as fake_get:
            send_healthcheck_ping("start")

        self.assertEqual(fake_get.call_args.kwargs['verify'],
                         "/etc/ssl/certs/ca-certificates.crt")


class TestPingRetries(unittest.TestCase):

    def test_a_transient_dns_failure_is_retried(self):
        # Cas réel dans sync.log : "Failed to resolve 'hc-ping.com'" au réveil.
        responses = [requests.ConnectionError("dns"), FakeResponse()]
        with patch.dict(os.environ, ENV, clear=True), \
             patch('src.utils.retry_utils.time.sleep'), \
             patch.object(requests, 'get', side_effect=responses) as fake_get:
            result = send_healthcheck_ping("start")

        self.assertTrue(result)
        self.assertEqual(fake_get.call_count, 2)

    def test_returns_false_when_every_attempt_fails(self):
        with patch.dict(os.environ, ENV, clear=True), \
             patch('src.utils.retry_utils.time.sleep'), \
             patch.object(requests, 'get', side_effect=requests.ConnectionError("dns")):
            result = send_healthcheck_ping("start")

        self.assertFalse(result)


if __name__ == '__main__':
    unittest.main()
