# -*- coding: utf-8 -*-
"""The background tabs' answer is looked for less often while a long row is computed (2026-11-08, load): a tenth of
the time since it was asked, 25-100 ms; 25 ms with nothing asked, and always 25 ms with CN_BG_POLL_FIXED=1."""
import time
import unittest
from types import SimpleNamespace


class BgPollGap(unittest.TestCase):
    def gap(self, asked_ago=None, fixed=False):
        import app
        a = SimpleNamespace(BG_POLL_MIN_MS=25, BG_POLL_MAX_MS=100, BG_POLL_FIXED=fixed, ANALYZE_POLL_MS=20,
                            _async_background_request=None if asked_ago is None else (('background',), 1),
                            _async_background_request_at=time.monotonic() - (asked_ago or 0))
        return app.CorrectNoteApp._bg_poll_gap(a)

    def test_gap(self):
        self.assertEqual(self.gap(), 25)
        self.assertEqual(self.gap(0.05), 25)
        self.assertTrue(45 <= self.gap(0.5) <= 55)
        self.assertEqual(self.gap(5.0), 100)
        self.assertEqual(self.gap(5.0, fixed=True), 25)


if __name__ == '__main__':
    unittest.main()
