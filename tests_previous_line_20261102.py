# -*- coding: utf-8 -*-
"""The row above reaches correct_line, and a row is not reused once the part it reads changed (2026-11-02)."""
import unittest
from types import SimpleNamespace
from analysis_context import previous_line_of, previous_part, reuse_rows, signature


class RowAbove(unittest.TestCase):
    def test_row_above(self):
        lines = ['one', '', 'two', 'three\tfour', 'five']
        self.assertIsNone(previous_line_of(lines, 0))
        self.assertEqual(previous_line_of(lines, 1), 'one')
        self.assertIsNone(previous_line_of(lines, 2))          # empty row above
        self.assertIsNone(previous_line_of(lines, 3))          # this row has columns
        self.assertIsNone(previous_line_of(lines, 4))          # the row above has columns
        self.assertIsNone(previous_line_of(lines, 5))

    def test_same_marks_as_the_entry(self):
        import ast, analysis_context
        tree = ast.parse(open('correction_entry.py', encoding='utf-8').read())
        found = {n.targets[0].id: ast.literal_eval(n.value) for n in tree.body
                 if isinstance(n, ast.Assign) and getattr(n.targets[0], 'id', '') in ('_SENTENCE_END', '_CLAUSE_CUT')}
        self.assertEqual(found['_SENTENCE_END'], analysis_context._SENTENCE_END)
        self.assertEqual(found['_CLAUSE_CUT'], analysis_context._CLAUSE_CUT)

    def test_part(self):
        self.assertEqual(previous_part(None), '')
        self.assertEqual(previous_part('駅まで歩いた。'), '')
        self.assertEqual(previous_part('駅まで歩いた、'), '')
        self.assertEqual(previous_part('はじめに、駅まで'), '駅まで')
        self.assertEqual(previous_part('駅まで'), '駅まで')

    def test_signature_without_part_is_as_before(self):
        self.assertEqual(signature(('a',), (1,), (2,)), (('a',), (1,), (2,)))
        self.assertEqual(signature(('a',), (1,), (2,), '終わり。'), (('a',), (1,), (2,)))
        self.assertNotEqual(signature((), (), (), '駅まで'), signature((), (), (), '家まで'))
        # the same last phrase: the same row, whatever came before it
        self.assertEqual(signature((), (), (), 'はじめに、駅まで'), signature((), (), (), 'つぎに、駅まで'))

    def test_row_is_not_reused_across_a_changed_part(self):
        row = dict(original='に行く', corrected='に行く', _input_signature=signature((), (), (), '駅まで'))
        results = [dict(original='に行く', corrected='に行く', pending=True)]
        with unittest.mock.patch('analysis_context.compatible', return_value=True):
            self.assertEqual(reuse_rows(results, [0], [row], {0: signature((), (), (), '家まで')}, {}, {}, ()), [0])
            self.assertEqual(reuse_rows(results, [0], [row], {0: signature((), (), (), '駅まで')}, {}, {}, ()), [])


class Worker(unittest.TestCase):
    def run_row(self, **extra):
        import analysis_worker
        import correction_entry
        seen = {}
        def fake(line, store, previous_line=None, **kw):
            seen.update(kw)
            if previous_line is not None:seen['previous_line'] = previous_line
            return dict(original=line, corrected=line, details=[], spans=[], unsure_spans=[], original_spans=[],
                        odd_spans=[], odd_reasons=[], changed=False)
        runtime = analysis_worker.Runtime.__new__(analysis_worker.Runtime)
        runtime.store = runtime.decisions = runtime.context_vec = runtime.index = runtime.choices = None
        runtime.tokenize = lambda text: []
        task = dict(kind='line', line='に行く', context={}, nearby=(), input_method='kana', attested=(),
                    readings=(), calculations=(), recent=(), keyboard=None, **extra)
        with unittest.mock.patch.object(correction_entry, 'correct_line', fake):
            try:
                value = runtime._line_task(task)
            except Exception:
                value = None
        return seen, value

    def test_passed_only_when_there_is_one(self):
        self.assertNotIn('previous_line', self.run_row()[0])
        self.assertNotIn('previous_line', self.run_row(previous_line=None)[0])
        self.assertEqual(self.run_row(previous_line='駅まで')[0].get('previous_line'), '駅まで')


class Task(unittest.TestCase):
    def test_line_task_carries_it(self):
        import analysis_async
        app = SimpleNamespace(_prev_lines=['駅まで', 'に行く'], _analyze_ctx={}, settings={}, recent_words=None,
                              _nearby_words_for=lambda i: (), _analyze_text='駅まで\nに行く')
        with unittest.mock.patch.object(analysis_async.input_work, 'line_readings', return_value=()), \
             unittest.mock.patch.object(analysis_async.input_work, 'line_calculations', return_value=()):
            self.assertEqual(analysis_async.line_task(app, 1, None, False)['previous_line'], '駅まで')
            self.assertIsNone(analysis_async.line_task(app, 0, None, False)['previous_line'])
            self.assertIsNone(analysis_async.line_task(app, 1, {}, True)['previous_line'])


import unittest.mock
if __name__ == '__main__':
    unittest.main()
