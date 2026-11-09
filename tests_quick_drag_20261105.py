# -*- coding: utf-8 -*-
"""Dragging the quick window prepares what the first character would wait for (2026-11-05). No window."""
import unittest
from types import SimpleNamespace
from unittest import mock

import app as app_module
import memory_usage
import quick_analysis as Q


class FakeWorker:
    def __init__(self):
        self.tasks = []
        self.process = SimpleNamespace(is_alive=lambda: True)

    def submit(self, task, state=None):
        self.tasks.append(task['kind'])
        return len(self.tasks)


def fake(tier='high', **more):
    jobs = []
    a = SimpleNamespace(_quick_text=object(), _quick_job=None, _closing=False, _quick_worker=FakeWorker(), _quick_worker_state='s',
                        jobs=jobs, root=SimpleNamespace(after=lambda ms, f: jobs.append(f) or 'j', after_cancel=lambda j: None))
    a.settings = {'memory_usage': tier}
    a.__dict__.update(more)
    return a


class Moved(unittest.TestCase):
    def run_moved(self, a, tier):
        with mock.patch.object(Q, 'state_key', return_value='s'), mock.patch.object(Q, 'snapshot', return_value={}), \
                mock.patch.object(memory_usage, 'low', return_value=tier == 'low'), mock.patch.object(memory_usage, 'quick_prepare', return_value=tier == 'high'), \
                mock.patch.object(memory_usage, 'cancel_release'), mock.patch.object(memory_usage, 'queue_release') as queued, mock.patch.object(memory_usage, 'retains', return_value=False):
            Q.window_moved(a)
            Q.window_moved(a)
            for job in list(a.jobs):
                job()
        return queued

    def test_the_tables_are_asked_for_once_in_any_tier_but_low(self):
        for tier in ('high', 'mid'):
            a = fake(tier)
            queued = self.run_moved(a, tier)
            self.assertEqual(a._quick_worker.tasks.count('quick_prepare'), 1, tier)
            self.assertEqual(a._quick_worker.tasks.count('warmup'), 1, tier)
            self.assertTrue(queued.called)

    def test_low_keeps_to_itself(self):
        a = fake('low')
        self.run_moved(a, 'low')
        self.assertEqual(a._quick_worker.tasks, [])

    def test_a_real_request_is_left_alone(self):
        a = fake('high', _quick_job=dict(scope=1))
        self.run_moved(a, 'high')
        self.assertEqual(a._quick_worker.tasks, [])


class Configure(unittest.TestCase):
    def events(self, *places):
        win = object()
        a = SimpleNamespace(_quick_win=win)
        with mock.patch.object(Q, 'window_moved') as moved:
            for x, y, w, h in places:
                app_module.CorrectNoteApp._on_quick_window_configure(a, SimpleNamespace(widget=win, x=x, y=y, width=w, height=h))
        return moved.call_count

    def test_only_a_new_place_at_the_same_size_counts(self):
        self.assertEqual(self.events((1, 1, 300, 100)), 0)                       # the first look
        self.assertEqual(self.events((1, 1, 300, 100), (5, 5, 300, 100)), 1)     # moved
        self.assertEqual(self.events((1, 1, 300, 100), (1, 1, 300, 140)), 0)     # grew as the text grew
        self.assertEqual(self.events((1, 1, 300, 100), (1, 1, 300, 100)), 0)     # nothing



class FocusOut(unittest.TestCase):
    def leave(self, focus):
        win = SimpleNamespace(winfo_exists=lambda: True, focus_displayof=lambda: focus)
        a = SimpleNamespace(_quick_win=win, root=SimpleNamespace(after_idle=lambda run: run()))
        with mock.patch.object(Q, 'window_moved') as moved:
            app_module.CorrectNoteApp._on_quick_window_focus_out(a)
        return moved.call_count

    def test_only_when_the_whole_app_lost_the_focus(self):
        self.assertEqual(self.leave(None), 1)          # another application is active now
        self.assertEqual(self.leave(object()), 0)      # the focus only moved inside this app


if __name__ == '__main__':
    unittest.main()
