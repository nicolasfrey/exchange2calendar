#!/usr/bin/env python3
"""Tests de l'orchestration : validation, codes de sortie, pings, notifications."""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
import exchange_sync

COMPLETE_ENV = {
    "EXCHANGE_USERNAME": "GROUPE\\u",
    "EXCHANGE_EMAIL": "u@x.y",
    "EXCHANGE_PASSWORD": "secret",
    "GOOGLE_CALENDAR_ID": "cal@group.calendar.google.com",
}


class MainHarness(unittest.TestCase):
    """Neutralise tout ce qui sort du process, et capture pings/notifications."""

    def setUp(self):
        self.pings = []
        self.notifications = []

        patches = [
            patch.object(exchange_sync, 'load_dotenv'),
            patch.object(exchange_sync, 'configure_logging'),
            patch.object(exchange_sync, 'send_healthcheck_ping',
                         side_effect=lambda status=None, message=None: self.pings.append(status)),
            patch.object(exchange_sync, 'notify_error',
                         side_effect=lambda msg, details=None: self.notifications.append(msg)),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def run_main(self, argv=(), env=None):
        env = COMPLETE_ENV if env is None else env
        with patch.dict(os.environ, env, clear=True), \
             patch.object(sys, 'argv', ['exchange_sync.py', *argv]):
            return exchange_sync.main()

    def stub_services(self, connect=True, stats=(1, 2, 3), sync_error=None,
                      auth_error=None):
        exchange = MagicMock()
        exchange.connect.return_value = connect

        google = MagicMock()
        if auth_error:
            google.authenticate.side_effect = auth_error

        synchronizer = MagicMock()
        if sync_error:
            synchronizer.synchronize.side_effect = sync_error
        else:
            synchronizer.synchronize.return_value = stats

        return (patch.object(exchange_sync, 'ExchangeCalendarService', return_value=exchange),
                patch.object(exchange_sync, 'GoogleCalendarService', google),
                patch.object(exchange_sync, 'CalendarSynchronizer', return_value=synchronizer))


class TestConfigurationValidation(MainHarness):

    def test_incomplete_configuration_exits_with_an_error(self):
        with self.assertRaises(SystemExit) as exit_info:
            self.run_main(env={"EXCHANGE_USERNAME": "u"})

        self.assertEqual(exit_info.exception.code, 1)

    def test_incomplete_configuration_reports_a_failure(self):
        with self.assertRaises(SystemExit):
            self.run_main(env={"EXCHANGE_USERNAME": "u"})

        self.assertEqual(self.pings, ["start", "fail"])
        self.assertEqual(len(self.notifications), 1)


class TestExchangeConnectionFailure(MainHarness):

    def test_a_failed_connection_exits_and_reports(self):
        a, b, c = self.stub_services(connect=False)
        with a, b, c, self.assertRaises(SystemExit) as exit_info:
            self.run_main()

        self.assertEqual(exit_info.exception.code, 1)
        self.assertEqual(self.pings, ["start", "fail"])


class TestGoogleAuthFailure(MainHarness):

    def test_an_auth_error_exits_and_reports(self):
        a, b, c = self.stub_services(auth_error=RuntimeError("token révoqué"))
        with a, b, c, self.assertRaises(SystemExit) as exit_info:
            self.run_main()

        self.assertEqual(exit_info.exception.code, 1)
        self.assertEqual(self.pings, ["start", "fail"])


class TestSuccessPath(MainHarness):

    def test_a_successful_run_pings_success(self):
        a, b, c = self.stub_services(stats=(1, 2, 3))
        with a, b, c:
            self.run_main()

        self.assertEqual(self.pings, ["start", "success"])
        self.assertEqual(self.notifications, [])

    def test_the_stats_are_reported_to_healthchecks(self):
        messages = []
        with patch.object(exchange_sync, 'send_healthcheck_ping',
                          side_effect=lambda status=None, message=None: messages.append((status, message))):
            a, b, c = self.stub_services(stats=(4, 5, 6))
            with a, b, c:
                self.run_main()

        success = [m for s, m in messages if s == "success"]
        self.assertIn("4 créés", success[0])
        self.assertIn("5 mis à jour", success[0])
        self.assertIn("6 supprimés", success[0])

    def test_days_argument_is_forwarded(self):
        synchronizer = MagicMock()
        synchronizer.synchronize.return_value = (0, 0, 0)
        exchange = MagicMock()
        exchange.connect.return_value = True

        with patch.object(exchange_sync, 'ExchangeCalendarService', return_value=exchange), \
             patch.object(exchange_sync, 'GoogleCalendarService'), \
             patch.object(exchange_sync, 'CalendarSynchronizer', return_value=synchronizer):
            self.run_main(argv=['--days', '90', '--dry-run'])

        self.assertEqual(synchronizer.synchronize.call_args.kwargs,
                         {'days_ahead': 90, 'dry_run': True})


class TestOptOutFlags(MainHarness):

    def test_no_healthcheck_sends_no_ping(self):
        a, b, c = self.stub_services()
        with a, b, c:
            self.run_main(argv=['--no-healthcheck'])

        self.assertEqual(self.pings, [])

    def test_no_notify_silences_notifications_on_error(self):
        a, b, c = self.stub_services(connect=False)
        with a, b, c, self.assertRaises(SystemExit):
            self.run_main(argv=['--no-notify'])

        self.assertEqual(self.notifications, [])


class TestUnexpectedError(MainHarness):

    def test_an_unexpected_error_exits_and_reports(self):
        a, b, c = self.stub_services(sync_error=RuntimeError("boum"))
        with a, b, c, self.assertRaises(SystemExit) as exit_info:
            self.run_main()

        self.assertEqual(exit_info.exception.code, 1)
        self.assertEqual(self.pings, ["start", "fail"])
        self.assertEqual(len(self.notifications), 1)


if __name__ == '__main__':
    unittest.main()
