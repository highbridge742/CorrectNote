# -*- coding: utf-8 -*-
"""Quick input answers without the heavy step while typing, and solves it when the hands stop (2026-11-05). No window."""
import unittest

import quick_analysis as Q
import quick_row_reuse
import tests_quick_async as base


class Defer(base.QuickAsyncTests):
    def deferred(self):
        value = self.completed()
        value['results'][0]['deferred_stages'] = ['two']
        return value

    def heavy_timer(self):
        for call in self.app.root.after.call_args_list:
            if call.args[0] == Q.HEAVY_AFTER_MS and call.args[1].__qualname__.startswith('_queue_heavy'):
                return call.args[1]
        return None

    def test_typing_asks_for_the_light_answer_then_the_real_one_when_the_hands_stop(self):
        Q.start(self.app)
        self.assertTrue(self.worker.submit.call_args[0][0].get('defer_heavy'))
        self.worker.poll.return_value = self.deferred()
        Q.start(self.app)
        self.app._finish_quick_analysis.assert_called_once()    # the light answer is shown
        ready = self.heavy_timer()
        self.assertIsNotNone(ready)
        self.worker.poll.return_value = None
        ready()
        Q.start(self.app)
        self.assertFalse(self.worker.submit.call_args[0][0].get('defer_heavy'))
        self.assertEqual(self.worker.submit.call_count, 2)
        self.app.root.after.reset_mock()
        self.worker.poll.return_value = self.completed()
        Q.start(self.app)
        self.assertIsNone(self.heavy_timer())       # a real answer: nothing more to do

    def test_an_answer_with_nothing_put_off_needs_no_second_run(self):
        Q.start(self.app)
        self.worker.poll.return_value = self.completed()
        Q.start(self.app)
        self.assertIsNone(self.heavy_timer())

    def test_a_new_edit_drops_the_heavy_run(self):
        Q.start(self.app)
        self.worker.poll.return_value = self.deferred()
        Q.start(self.app)
        ready = self.heavy_timer()
        self.worker.poll.return_value = None
        count = self.worker.submit.call_count
        self.edit('別の文')
        self.app.root.after.reset_mock()
        ready()
        self.app.root.after.assert_not_called()
        self.assertEqual(self.worker.submit.call_count, count)
        self.assertNotEqual(getattr(self.app, '_quick_heavy_scope', None), Q._scope(self.app))

    def test_it_waits_while_composing(self):
        Q.start(self.app)
        self.worker.poll.return_value = self.deferred()
        Q.start(self.app)
        ready = self.heavy_timer()
        self.composing.return_value = True
        self.app.root.after.reset_mock()
        ready()
        self.assertIsNotNone(self.heavy_timer())    # asked again later
        self.assertIsNone(getattr(self.app, '_quick_heavy_scope', None))

    def test_a_waiting_f2_gets_the_real_answer_at_once(self):
        Q.defer_f2(self.app)
        Q.start(self.app)
        self.assertFalse(self.worker.submit.call_args[0][0].get('defer_heavy'))

    def test_closing_cancels_the_timer(self):
        Q.start(self.app)
        self.worker.poll.return_value = self.deferred()
        Q.start(self.app)
        identifier = self.app._quick_heavy_after_id
        self.app.root.after_cancel.reset_mock()
        Q.close(self.app)
        self.app.root.after_cancel.assert_any_call(identifier)
        self.assertIsNone(self.app._quick_heavy_after_id)

    def test_a_light_answer_is_not_kept_for_reuse(self):
        row = dict(original='あ', corrected='あ', analysis_status='complete')
        self.assertTrue(quick_row_reuse.completed_row(row, 'あ'))
        self.assertFalse(quick_row_reuse.completed_row(dict(row, deferred_stages=['two']), 'あ'))


# only the tests above, not the ones inherited from the base class
def load_tests(loader, tests, pattern):
    names = [n for n in Defer.__dict__ if n.startswith('test_')]
    suite = unittest.TestSuite(Defer(n) for n in names)
    suite.addTests(loader.loadTestsFromTestCase(HeavyWait))
    return suite


class HeavyWait(unittest.TestCase):
    """The heavy redo waits HEAVY_AFTER_MS from the last change, not from the light answer (2026-11-07, speed)."""

    def test_counts_from_the_last_change(self):
        import time
        from types import SimpleNamespace
        self.assertEqual(Q._heavy_delay(SimpleNamespace()), Q.HEAVY_AFTER_MS)            # no change seen: as before
        self.assertEqual(Q._heavy_delay(SimpleNamespace(_quick_changed_at=time.monotonic() - 5)), 20)
        self.assertEqual(Q._heavy_delay(SimpleNamespace(_quick_changed_at=time.monotonic() - 5), floor=100), 100)
        left = Q._heavy_delay(SimpleNamespace(_quick_changed_at=time.monotonic() - 0.4))
        self.assertTrue(750 <= left <= 800, left)
        self.assertEqual(Q._heavy_delay(SimpleNamespace(_quick_changed_at=time.monotonic())), Q.HEAVY_AFTER_MS)


if __name__ == '__main__':
    unittest.main()
