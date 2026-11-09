# -*- coding: utf-8 -*-
"""One IME commit runs the change handler once, at its last letter (2026-11-05). No window, no IME."""
import time
import unittest
from types import SimpleNamespace
from unittest import mock

import analysis_work_app as work
import ime_burst as B


class Editor:
    def __init__(self):
        self.text = ''
        self.draws = 0

    def get(self, first, last):
        if first == 'insert-1c':
            return self.text[-1:]
        n = int(first[len('insert-'):-1])
        return self.text[-n:]

    def update_idletasks(self):
        self.draws += 1


class Root:
    def __init__(self):
        self.jobs = {}
        self.n = 0

    def after(self, ms, run):
        self.n += 1
        self.jobs[self.n] = run
        return self.n

    def after_cancel(self, job):
        self.jobs.pop(job, None)


def make():
    watch = B.Watch(0)
    app = SimpleNamespace(editor=Editor(), root=Root(), _ime_burst_watch=watch, changes=[])
    app._on_change = lambda event=None: app.changes.append(event)
    return app, watch


class Hold(unittest.TestCase):
    def test_every_letter_but_the_last_waits(self):
        app, watch = make()
        watch.arriving = 'あいう'; watch._at = time.monotonic()
        app.editor.text = '前あ'
        self.assertTrue(B.hold(app))
        app.editor.text = '前あい'
        self.assertTrue(B.hold(app))
        app.editor.text = '前あいう'
        self.assertFalse(B.hold(app))           # the last letter goes on, drawn once
        self.assertEqual(app.editor.draws, 1)
        self.assertEqual(app.root.jobs, {})
        self.assertFalse(B.holding(app))
        self.assertFalse(B.hold(app))           # the rest of the releases are ordinary

    def test_a_letter_that_never_comes_still_finishes(self):
        app, watch = make()
        watch.arriving = 'あいう'; watch._at = time.monotonic()
        app.editor.text = 'あ'
        event = object()
        self.assertTrue(B.hold(app, event))
        (run,) = app.root.jobs.values()
        run()
        self.assertEqual(app.changes, [event])
        self.assertEqual(app.editor.draws, 1)
        self.assertFalse(B.holding(app))

    def test_ordinary_typing_is_not_held(self):
        app, watch = make()
        app.editor.text = 'あ'
        self.assertFalse(B.hold(app))
        self.assertFalse(B.holding(app))
        self.assertEqual(app.root.jobs, {})
        self.assertEqual(app.editor.draws, 0)

    def test_a_commit_elsewhere_does_not_delay_later_typing(self):
        app, watch = make()
        watch.arriving = 'あいう'; watch._at = time.monotonic() - B.MAX_AGE_S - .01
        app.editor.text = 'か'
        self.assertFalse(B.hold(app))
        self.assertFalse(B.holding(app))

    def test_states_that_look_at_each_letter_are_not_held(self):
        for attribute in (dict(_pick_mode='list'), dict(_bracket_exit=(1, 2)), dict(_f2_focus_target=object())):
            app, watch = make()
            watch.arriving = 'あいう'; watch._at = time.monotonic()
            app.editor.text = 'あ'
            for name, value in attribute.items():
                setattr(app, name, value)
            self.assertFalse(B.hold(app), attribute)

    def test_an_equals_sign_is_seen_when_it_comes(self):
        for sign in ('＝', '='):
            app, watch = make()
            watch.arriving = 'あ' + sign + 'う'; watch._at = time.monotonic()
            app.editor.text = 'あ' + sign
            self.assertFalse(B.hold(app), sign)

    def test_no_watch_at_all(self):
        app = SimpleNamespace(editor=Editor(), root=Root())
        self.assertFalse(B.hold(app))
        self.assertFalse(B.holding(app))


class DrawSoon(unittest.TestCase):
    def test_no_draw_is_queued_inside_a_commit(self):
        app, watch = make()
        watch.arriving = 'あいう'; watch._at = time.monotonic()
        work.draw_soon(app)
        self.assertEqual(app.root.jobs, {})
        watch.arriving = None
        work.draw_soon(app)
        self.assertEqual(len(app.root.jobs), 1)


if __name__ == '__main__':
    unittest.main()
