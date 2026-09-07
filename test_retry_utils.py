#!/usr/bin/env python3
"""Tests du helper de réessai avec backoff exponentiel."""

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from src.utils.retry_utils import retry_call


class Recorder:
    """Remplace time.sleep pour observer les délais sans attendre."""

    def __init__(self):
        self.delays = []

    def __call__(self, seconds):
        self.delays.append(seconds)


class TestRetryCall(unittest.TestCase):

    def test_returns_the_result_without_sleeping_when_it_works(self):
        sleeper = Recorder()

        result = retry_call(lambda: "ok", sleep=sleeper)

        self.assertEqual(result, "ok")
        self.assertEqual(sleeper.delays, [])

    def test_retries_until_success(self):
        attempts = []

        def flaky():
            attempts.append(1)
            if len(attempts) < 3:
                raise ConnectionError("réseau indisponible")
            return "ok"

        result = retry_call(flaky, attempts=3, sleep=Recorder())

        self.assertEqual(result, "ok")
        self.assertEqual(len(attempts), 3)

    def test_backoff_is_exponential(self):
        sleeper = Recorder()

        with self.assertRaises(ConnectionError):
            retry_call(lambda: (_ for _ in ()).throw(ConnectionError("ko")),
                       attempts=4, base_delay=5, sleep=sleeper)

        # Un délai entre chaque tentative, mais pas après la dernière.
        self.assertEqual(sleeper.delays, [5, 10, 20])

    def test_reraises_the_last_error_when_attempts_run_out(self):
        def always_fails():
            raise TimeoutError("délai dépassé")

        with self.assertRaises(TimeoutError):
            retry_call(always_fails, attempts=2, sleep=Recorder())

    def test_does_not_retry_an_unlisted_exception(self):
        attempts = []

        def bad_config():
            attempts.append(1)
            raise ValueError("configuration invalide")

        with self.assertRaises(ValueError):
            retry_call(bad_config, attempts=3, retry_on=(ConnectionError,), sleep=Recorder())

        self.assertEqual(len(attempts), 1, "une erreur non transitoire ne doit pas être réessayée")

    def test_reports_each_retry(self):
        messages = []

        def flaky():
            if len(messages) < 1:
                raise ConnectionError("boom")
            return "ok"

        retry_call(flaky, attempts=3, label="ping",
                   on_retry=lambda attempt, delay, error: messages.append((attempt, delay)),
                   sleep=Recorder())

        self.assertEqual(messages, [(1, 5)])


if __name__ == '__main__':
    unittest.main()
