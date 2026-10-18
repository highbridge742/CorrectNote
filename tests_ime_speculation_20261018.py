# -*- coding: utf-8 -*-
"""The row composed in the IME, sent ahead (ime_speculation): waiting, the
dropped request when another string is committed, and when its answer is used."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import analysis_async
import analysis_context
import ime_speculation


def host(text):
    app = SimpleNamespace(_analyze_text=text)
    app.editor_source_text = lambda: app.text
    app.text = text
    return app


def spec(source, text, row=0, value=None, state='S'):
    task = dict(kind='line', line=text.split('\n')[row], input_method='kana', keyboard='k',
                recent=(), readings=(), calculations=())
    return dict(text=text, source=source, row=row, state=state, scope=('speculate', text, row, state),
                task=task, value=value)


class WaitingTests(unittest.TestCase):
    def test_waits_while_composing_and_after_the_matching_commit(self):
        app = host('前の行\n資料')
        app._ime_speculation = spec('前の行\n資料', '前の行\n資料を')
        with patch.object(analysis_async, '_poll', return_value=(True, None)) as poll:
            self.assertTrue(ime_speculation.waiting(app))        # still composing
            app.text = '前の行\n資料を'                            # the composed string was committed
            self.assertTrue(ime_speculation.waiting(app))
        self.assertEqual(poll.call_count, 2)
        self.assertIsNotNone(app._ime_speculation)

    def test_another_commit_drops_the_composed_row_at_once(self):
        app = host('前の行\n資料')
        app._ime_speculation = spec('前の行\n資料', '前の行\n資料を')
        app.text = '前の行\n資料が'
        with patch.object(analysis_async, '_poll', return_value=(True, None)) as poll:
            self.assertFalse(ime_speculation.waiting(app))
        self.assertFalse(poll.called)
        self.assertIsNone(app._ime_speculation)
        self.assertIsNone(ime_speculation.context_for(app, '前の行\n資料が'))

    def test_the_answer_is_kept_when_it_comes(self):
        app = host('資料を')
        app._ime_speculation = spec('', '資料を')
        answer = dict(prepared=dict(context='C'))
        with patch.object(analysis_async, '_poll', return_value=(True, answer)):
            self.assertFalse(ime_speculation.waiting(app))
        self.assertIs(app._ime_speculation['value'], answer)
        with patch.object(ime_speculation, 'state_key', return_value='S'):
            self.assertEqual(ime_speculation.context_for(app, '資料を'), dict(context='C'))
            self.assertIsNone(ime_speculation.context_for(app, '資料が'))

    def test_a_superseded_request_is_forgotten(self):
        app = host('資料を')
        app._ime_speculation = spec('', '資料を')
        with patch.object(analysis_async, '_poll', return_value=(False, None)):
            self.assertFalse(ime_speculation.waiting(app))
        self.assertIsNone(app._ime_speculation)


class TakeTests(unittest.TestCase):
    def answer_for(self, task):
        return dict(prepared=dict(context=task.get('context')),
                    input_signature=analysis_context.signature(task.get('nearby', ()), task.get('readings', ()),
                                                               task.get('calculations', ())))

    def test_used_only_for_the_same_row_text_and_inputs(self):
        app = host('資料を')
        s = spec('', '資料を')
        task = dict(s['task'], nearby=(), context='C')
        s['value'] = self.answer_for(task)
        with patch.object(ime_speculation, 'result_compatible', return_value=True), \
                patch.object(analysis_context, 'completed', side_effect=lambda v: v):
            for index, change in ((1, {}), (0, dict(line='資料が')), (0, dict(readings=(('x', 'y'),))),
                                  (0, dict(context='D'))):
                app._ime_speculation = dict(s)
                self.assertIsNone(ime_speculation.take(app, index, dict(task, **change)), (index, change))
            app._ime_speculation = dict(s)
            app._analyze_text = '資料をさがす'
            self.assertIsNone(ime_speculation.take(app, 0, task))
            app._analyze_text = '資料を'
            self.assertIs(ime_speculation.take(app, 0, task), s['value'])
            self.assertIsNone(app._ime_speculation)


if __name__ == '__main__':
    unittest.main()
