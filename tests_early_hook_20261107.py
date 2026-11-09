# -*- coding: utf-8 -*-
"""The early purple is sent from correction_entry's on_early_odd hook (batch275, 2026-11-07): right after the entry
decides the purple, before the repair stages. The payload is the one first_answer sends."""
import os
import queue
import unittest
from unittest.mock import patch

import analysis_worker as W


class Hook(unittest.TestCase):
    def setUp(self):
        self.outbox = queue.Queue()
        W._EARLY['sink'] = (self.outbox, 7)
        W._EARLY.update(line='あいう', row=3, sent=False)

    def tearDown(self):
        W._EARLY['sink'] = None
        W._EARLY['sent'] = True

    def sent(self):
        out = []
        while True:
            try:
                out.append(self.outbox.get_nowait())
            except queue.Empty:
                return out

    def test_a_correct_line_with_the_hook_gets_it_and_sends_once(self):
        def correct_line(line, store, on_early_odd=None):
            on_early_odd(line, [(0, 2, 'odd'), [1, 3]])
            on_early_odd(line, [(0, 1)])
            return {}
        extra = W._early_hook(correct_line)
        self.assertEqual(list(extra), ['on_early_odd'])
        correct_line('あいう', None, **extra)
        self.assertEqual(self.sent(), [(('partial', 7), dict(line='あいう', row=3, odd=[(0, 2), (1, 3)]), None)])
        self.assertTrue(W._EARLY['sent'])          # first_answer sends nothing more

    def test_an_older_correct_line_gets_nothing(self):
        self.assertEqual(W._early_hook(lambda line, store: {}), {})

    def test_other_lines_and_no_purple_send_nothing(self):
        W._early_send('ちがう', [(0, 1)])
        self.assertEqual(self.sent(), [])
        W._early_send('あいう', [])
        self.assertEqual(self.sent(), [])

    def test_switched_off(self):
        with patch.dict(os.environ, {'CN_EARLY_ODD': '0'}):
            self.assertEqual(W._early_hook(lambda line, store, on_early_odd=None: {}), {})


if __name__ == '__main__':
    unittest.main()
