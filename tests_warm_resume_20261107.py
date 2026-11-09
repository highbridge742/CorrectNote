# -*- coding: utf-8 -*-
"""A warmup a newer request took over runs again once the child is idle (2026-11-07, speed).

The app's prewarm is followed within 0.5 s by its first request: the warmup was dropped before it read a
table and the child paid about 7 s on its first row. These run the child's request loop with a stand-in runtime."""
import queue
import threading
import time
import unittest
from unittest.mock import patch

import analysis_worker as W
from analysis_context import check_current_request


class Owner:
    def pump(self):
        return True

    def get(self, inbox):
        return inbox.get()


class FakeRuntime:
    log = []
    steps = 40          # a warmup made of this many checkpoints, 5 ms each

    def set_state(self, state):
        pass

    def execute(self, task):
        kind = task['kind']
        if kind == 'warmup':
            FakeRuntime.log.append('warmup begin')
            for _ in range(self.steps):
                check_current_request()
                time.sleep(0.005)
            FakeRuntime.log.append('warmup end')
            return dict(ready=True)
        FakeRuntime.log.append(kind)
        if kind == 'line':
            return dict(line=task.get('text'))
        return dict(kind=kind)


def run(requests, wait=1.2, later=()):
    """Feed the requests (all queued before the loop starts), then the later ones after a pause."""
    FakeRuntime.log = []
    inbox, outbox = queue.Queue(), queue.Queue()
    for r in requests:
        inbox.put(r)
    with patch.object(W, 'Runtime', FakeRuntime):
        th = threading.Thread(target=W._serve_requests, args=(inbox, outbox, Owner()), daemon=True)
        th.start()
        for delay, r in later:
            time.sleep(delay)
            inbox.put(r)
        time.sleep(wait)
        inbox.put(None)
        th.join(5)
    answers = []
    while True:
        try:
            answers.append(outbox.get_nowait())
        except queue.Empty:
            break
    return FakeRuntime.log, answers


def req(i, kind, **task):
    return dict(id=i, task=dict(kind=kind, **task), state=None)


class WarmResume(unittest.TestCase):
    def test_a_warmup_taken_over_before_it_ran_runs_after(self):
        log, answers = run([req(1, 'warmup'), req(2, 'plans')])
        self.assertEqual(log[0], 'plans')
        self.assertIn('warmup end', log)
        self.assertEqual([a[0] for a in answers], [2])          # the resumed warmup sends nothing

    def test_interrupted_midway_it_runs_again(self):
        log, answers = run([req(1, 'warmup')], later=[(0.05, req(2, 'line', text='あ'))])
        self.assertEqual(log[:3], ['warmup begin', 'line', 'warmup begin'])
        self.assertEqual(log[-1], 'warmup end')
        self.assertEqual([a[0] for a in answers], [2])

    def test_a_row_in_the_quiet_time_is_not_delayed(self):
        # the row comes 0.1 s after the last answer: it is served first, the warmup waits for quiet again
        log, answers = run([req(1, 'warmup'), req(2, 'plans')], later=[(0.1, req(3, 'line', text='い'))])
        self.assertEqual(log[:2], ['plans', 'line'])
        self.assertIn('warmup end', log)

    def test_one_that_ran_to_its_end_is_not_run_again(self):
        FakeRuntime.steps = 2
        try:
            log, answers = run([req(1, 'warmup')], later=[(0.05, req(2, 'line', text='う'))])
        finally:
            FakeRuntime.steps = 40
        self.assertEqual(log.count('warmup begin'), 1)

    def test_it_gives_up_after_a_few_tries(self):
        later = [(W.WARM_IDLE_S + 0.08, req(10 + k, 'line', text=str(k))) for k in range(W.WARM_AGAIN_MAX + 3)]
        FakeRuntime.steps = 400
        try:
            log, answers = run([req(1, 'warmup')], later=later, wait=0.3)
        finally:
            FakeRuntime.steps = 40
        self.assertLessEqual(log.count('warmup begin'), W.WARM_AGAIN_MAX + 1)
        self.assertEqual(log.count('line'), W.WARM_AGAIN_MAX + 3)

    def test_english_relearn_warms_only_when_asked(self):
        with patch.object(FakeRuntime, 'execute', lambda self, task: FakeRuntime.log.append(task['kind']) or dict(record=1)):
            log, answers = run([req(1, 'english_relearn')])
        self.assertEqual(log, ['english_relearn'])
        log, answers = run([req(1, 'english_relearn', warm_after=True)])
        self.assertEqual(log, ['english_relearn', 'warmup begin', 'warmup end'])
        self.assertEqual([a[0] for a in answers], [1])             # only the relearning answer


class PollGap(unittest.TestCase):
    """The pipe is looked at most every POLL_GAP_S while a row is solved (2026-11-07, speed)."""

    def test_checks_do_not_each_poll_the_pipe(self):
        polls = []

        class Counted(queue.Queue):
            def get_nowait(self):
                polls.append(1)
                return queue.Queue.get_nowait(self)

        class Busy(FakeRuntime):
            def execute(self, task):
                t = time.monotonic()
                n = 0
                while time.monotonic() - t < 0.2:
                    check_current_request()
                    n += 1
                FakeRuntime.log.append(n)
                return dict(n=n)

        FakeRuntime.log = []
        inbox, outbox = Counted(), queue.Queue()
        inbox.put(req(1, 'line', text='え'))
        with patch.object(W, 'Runtime', Busy):
            th = threading.Thread(target=W._serve_requests, args=(inbox, outbox, Owner()), daemon=True)
            th.start()
            time.sleep(0.5)
            inbox.put(None)
            th.join(5)
        checks = FakeRuntime.log[0]
        self.assertGreater(checks, 2000)
        self.assertLess(len(polls), 0.2 / W.POLL_GAP_S + 20, (len(polls), checks))
        self.assertEqual(outbox.get_nowait()[0], 1)

    def test_a_newer_request_still_stops_the_row(self):
        class Long(FakeRuntime):
            def execute(self, task):
                FakeRuntime.log.append(task['kind'] + ' begin')
                t = time.monotonic()
                while time.monotonic() - t < 2:
                    check_current_request()
                FakeRuntime.log.append(task['kind'] + ' end')
                return {}

        FakeRuntime.log = []
        inbox, outbox = queue.Queue(), queue.Queue()
        inbox.put(req(1, 'line', text='お'))
        with patch.object(W, 'Runtime', Long):
            th = threading.Thread(target=W._serve_requests, args=(inbox, outbox, Owner()), daemon=True)
            th.start()
            time.sleep(0.1)
            t = time.monotonic()
            inbox.put(req(2, 'plans'))
            while 'plans begin' not in FakeRuntime.log and time.monotonic() - t < 3:
                time.sleep(0.001)
            took = time.monotonic() - t
            inbox.put(None)
            th.join(5)
        self.assertNotIn('line end', FakeRuntime.log)
        self.assertLess(took, 0.1)


if __name__ == '__main__':
    unittest.main()
