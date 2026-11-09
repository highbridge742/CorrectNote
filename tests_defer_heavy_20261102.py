# -*- coding: utf-8 -*-
"""The typed row's first answer leaves the heavy step out, and is redone when the typing stops (2026-11-02)."""
import time
import unittest
import unittest.mock
from types import SimpleNamespace
import analysis_async
from analysis_cache import reusable_result
from analysis_context import reuse_rows


def app_for(row, priority=None, **extra):
    token = analysis_async.input_work.token
    a = SimpleNamespace(_prev_lines=['one', 'two'], _analyze_ctx={}, settings={}, recent_words=None,
                        _nearby_words_for=lambda i: (), _analyze_text='one\ntwo', NEIGHBOR_DEFER=True, **extra)
    a._priority_input_row = (token(a), row) if priority is None else priority
    return a


class Task(unittest.TestCase):
    def task(self, a, i, units_only=False):
        with unittest.mock.patch.object(analysis_async.input_work, 'line_readings', return_value=()), \
             unittest.mock.patch.object(analysis_async.input_work, 'line_calculations', return_value=()):
            return analysis_async.line_task(a, i, {}, units_only)

    def test_only_the_typed_row(self):
        a = app_for(1)
        self.assertTrue(self.task(a, 1)['defer_heavy'])
        self.assertFalse(self.task(a, 0)['defer_heavy'])
        self.assertFalse(self.task(a, 1, True)['defer_heavy'])

    def test_not_when_redoing_or_not_typing(self):
        self.assertFalse(self.task(app_for(1, _heavy_redo={1}), 1)['defer_heavy'])
        self.assertFalse(self.task(app_for(1, priority=('other', 1)), 1)['defer_heavy'])
        a = app_for(1); a.NEIGHBOR_DEFER = False
        self.assertFalse(self.task(a, 1)['defer_heavy'])


class NotKept(unittest.TestCase):
    ROW = dict(original='two', corrected='two', _input_signature=((), (), ()))

    def test_not_reusable(self):
        self.assertTrue(reusable_result(self.ROW))
        self.assertFalse(reusable_result(dict(self.ROW, deferred_stages=['odd_respell_two'])))

    def test_not_saved(self):
        import analysis_cache, json, os, tempfile
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, 'c.json')
            analysis_cache.save(path, 'fp', {'two': [dict(self.ROW, deferred_stages=['odd_respell_two'])]})
            if os.path.exists(path):
                with open(path, encoding='utf-8') as f:
                    self.assertEqual(json.load(f).get('tabs') or [], [])

    def test_not_reused_by_a_row(self):
        results = [dict(original='two', corrected='two', pending=True)]
        row = dict(self.ROW, deferred_stages=['odd_respell_two'])
        with unittest.mock.patch('analysis_context.compatible', return_value=True):
            self.assertEqual(reuse_rows(results, [0], [row], {0: ((), (), ())}, {}, {}, ()), [0])


class Worker(unittest.TestCase):
    def run_row(self, answer, **extra):
        import analysis_worker
        import correction_entry
        seen = {}
        def fake(line, store, defer_heavy=False, **kw):
            seen['defer_heavy'] = defer_heavy
            return dict(dict(original=line, corrected=line, details=[], spans=[], unsure_spans=[], original_spans=[],
                             odd_spans=[], odd_reasons=[], changed=False, used_keys={}), **answer)
        runtime = analysis_worker.Runtime.__new__(analysis_worker.Runtime)
        runtime.store = runtime.decisions = runtime.context_vec = runtime.index = runtime.choices = None
        runtime.tokenize = lambda text: []
        task = dict(kind='line', line='two', context={}, nearby=(), input_method='kana', attested=(),
                    readings=(), calculations=(), recent=(), keyboard=None, **extra)
        with unittest.mock.patch.object(correction_entry, 'correct_line', fake):
            value = runtime._line_task(task)
        return seen, value['result']

    def test_passed_only_when_asked(self):
        self.assertFalse(self.run_row({})[0]['defer_heavy'])
        self.assertTrue(self.run_row({}, defer_heavy=True)[0]['defer_heavy'])

    def test_used_keys_are_not_kept(self):
        self.assertIn('used_keys', self.run_row({})[1])
        self.assertNotIn('used_keys', self.run_row(dict(deferred_stages=['odd_respell_two']), defer_heavy=True)[1])


class Redo(unittest.TestCase):
    def app(self, **extra):
        import app
        a = SimpleNamespace(root=SimpleNamespace(after=lambda ms, fn: 'job', after_cancel=lambda job: None),
                            NEIGHBOR_DEFER_MS=1200, _heavy_redo_job=None, _closing=False, _neighbor_defer_job=None,
                            line_results=[dict(original='one'), dict(original='two', deferred_stages=['x'])],
                            _foreground_analysis_pending=lambda: False, _last_edit_at=0.0, scheduled=[])
        a._schedule_analysis_chunk = lambda: a.scheduled.append(1)
        a._arm_heavy_redo = lambda: setattr(a, 'armed', True)
        a.__dict__.update(extra)
        return app.CorrectNoteApp._flush_heavy_redo, a

    def test_redoes_the_row_when_idle(self):
        flush, a = self.app()
        flush(a)
        self.assertEqual((a._analyze_todo, a._analyze_pos, a._heavy_redo, a.scheduled), ([1], 0, {1}, [1]))

    def test_waits_while_typing_or_analysing(self):
        for extra in (dict(_last_edit_at=time.monotonic()), dict(_foreground_analysis_pending=lambda: True)):
            flush, a = self.app(**extra)
            flush(a)
            self.assertTrue(a.armed)
            self.assertEqual(a.scheduled, [])

    def test_goes_before_the_neighbours(self):
        # 2026-11-07: the neighbours' redo waits for this one (tests_redo_wait_20261107), not the other way round
        flush, a = self.app(_neighbor_defer_job='job')
        flush(a)
        self.assertEqual(a.scheduled, [1])

    def test_nothing_to_do(self):
        flush, a = self.app(line_results=[dict(original='one')])
        flush(a)
        self.assertEqual(a.scheduled, [])


class Typing(unittest.TestCase):
    def test_says_whether_the_edit_is_being_typed(self):
        import app
        from analysis_work_app import token
        a = SimpleNamespace(NEIGHBOR_DEFER=True, NEIGHBOR_DEFER_MS=1200, _neighbor_defer_job=None, _flush_deferred_neighbors=None,
                            root=SimpleNamespace(after=lambda ms, fn: 'job', after_cancel=lambda job: None))
        a._priority_input_row = (token(a), 0)
        app.CorrectNoteApp._defer_neighbor_rows(a, [1], ['x', 'y'], ['z', 'y'], 0, 1)
        self.assertTrue(a._neighbor_typing)
        a._neighbor_force = True
        app.CorrectNoteApp._defer_neighbor_rows(a, [1], ['x', 'y'], ['z', 'y'], 0, 1)
        self.assertFalse(a._neighbor_typing)


if __name__ == '__main__':
    unittest.main()
