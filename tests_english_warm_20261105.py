# -*- coding: utf-8 -*-
"""The first English word of a session: the tables are read on another thread, then the words are learned as before."""
import time
import unittest
from types import SimpleNamespace
from unittest import mock

import app
import loanword


class Warm(unittest.TestCase):
    def fake(self):
        jobs = []
        a = SimpleNamespace(store=object(), _closing=False, learned=[], jobs=jobs,
                            root=SimpleNamespace(after=lambda ms, f: jobs.append(f) or 'job'))
        a._learn_english_now = a.learned.append
        return a

    def run_jobs(self, a):
        end = time.monotonic() + 5
        while a.jobs and time.monotonic() < end:
            a.jobs.pop(0)()
            time.sleep(.01)

    def test_no_english_word_goes_straight(self):
        a = self.fake()
        app.CorrectNoteApp._learn_english_soon(a, '日本語だけの文 abc')
        self.assertEqual(a.learned, ['日本語だけの文 abc'])
        self.assertFalse(a.jobs)

    def test_the_first_word_waits_for_the_tables_then_the_next_goes_straight(self):
        a = self.fake()
        with mock.patch.object(loanword, 'fix_english_word', return_value=None) as read:
            app.CorrectNoteApp._learn_english_soon(a, 'Planetarium one')
            app.CorrectNoteApp._learn_english_soon(a, 'Planetarium two')    # still reading: the latest counts
            self.assertEqual(a.learned, [])
            self.run_jobs(a)
        read.assert_called_once()
        self.assertTrue(read.call_args.kwargs['for_learning'])
        self.assertEqual(a.learned, ['Planetarium two'])
        app.CorrectNoteApp._learn_english_soon(a, 'Planetarium three')
        self.assertEqual(a.learned, ['Planetarium two', 'Planetarium three'])

    def test_closing_learns_what_waits(self):
        a = self.fake()
        a._english_waiting = 'Planetarium'
        a._learn_queue = []
        app.CorrectNoteApp._finish_learning_now(a)
        self.assertEqual(a.learned, ['Planetarium'])
        self.assertIsNone(a._english_waiting)


if __name__ == '__main__':
    unittest.main()
