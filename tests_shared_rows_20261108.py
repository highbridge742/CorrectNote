# -*- coding: utf-8 -*-
"""A finished row is taken for the same row elsewhere only with the same text, inputs, read context, kana state and
model state (shared_rows, 2026-11-08: about a tenth of うにさんの rows of 20+ characters are copies of another row).
Made-up rows, no window."""
import unittest

import shared_rows


def row(text='かいぎにでる', signature=((), (), ()), keys=('k',), deferred=False, kana=True, unit_keys=()):
    r = dict(original=text, corrected='会議に出る', spans=[], details=[], odd_spans=[],
             _input_signature=signature, _tab_has_kana=kana,
             _context_evidence=dict(version=1, keys=tuple(keys), truth=None, whole=False, unit_keys=tuple(unit_keys)),
             used_keys={'vocab': ()})
    if deferred:
        r['deferred_stages'] = ['heavy']
    return r


VALUE = dict(corrected_units=('会議に出る', []), original_units=('かいぎにでる', []), navigation=None)
STATE = (1, 0, (0, 0), 0, 2, True, 3, ('kana', None), (), (4, 0))


def task(text='かいぎにでる', nearby=(), previous=None):
    return dict(kind='line', line=text, nearby=nearby, readings=(), calculations=(), previous_line=previous,
                tab_has_kana=True)


class App:
    def __init__(self, state=STATE):
        self.state = state


class SharedRowsTest(unittest.TestCase):
    def setUp(self):
        import analysis_worker
        self.real = analysis_worker.state_key
        self.app = App()
        analysis_worker.state_key = lambda app: app.state

    def tearDown(self):
        import analysis_worker
        analysis_worker.state_key = self.real

    def put(self, r, context=None, state=STATE):
        shared_rows.remember(self.app, r, VALUE, {'k': 1} if context is None else context, state)

    def test_same_inputs_are_taken(self):
        self.put(row())
        got = shared_rows.take_for(self.app, task(), {'k': 1, 'other': 2}, {})
        self.assertIsNotNone(got)
        self.assertEqual(got['result']['corrected'], '会議に出る')
        self.assertEqual(got['corrected_units'], VALUE['corrected_units'])
        self.assertTrue(got['shared'])

    def test_what_differs_is_not_taken(self):
        self.put(row())
        self.assertIsNone(shared_rows.take_for(self.app, task(text='かいぎにでた'), {'k': 1}, {}))      # another text
        self.assertIsNone(shared_rows.take_for(self.app, task(nearby=('会議',)), {'k': 1}, {}))         # other nearby words
        self.assertIsNone(shared_rows.take_for(self.app, task(), {'k': 9}, {}))                        # the context it read
        t = task(); t['tab_has_kana'] = False
        self.assertIsNone(shared_rows.take_for(self.app, t, {'k': 1}, {}))                             # the kana of the tab
        self.app.state = (9,) + STATE[1:]                                                              # another model
        self.assertIsNone(shared_rows.take_for(self.app, task(), {'k': 1}, {}))

    def test_attested_words_it_used_must_match(self):
        self.put(row(unit_keys=(('会議', True),)))
        self.assertIsNone(shared_rows.take_for(self.app, task(), {'k': 1}, {}))
        self.assertIsNotNone(shared_rows.take_for(self.app, task(), {'k': 1}, {'会議': 1}))

    def test_light_answers_and_whole_reads_are_not_kept(self):
        self.put(row(deferred=True))
        r = row(); r['_context_evidence'] = dict(r['_context_evidence'], whole=True)
        self.put(r)
        self.assertIsNone(shared_rows.take_for(self.app, task(), {'k': 1}, {}))

    def test_an_answer_taken_here_is_not_kept_again_and_the_store_is_bounded(self):
        rows = shared_rows.for_app(self.app)
        shared_rows.remember(self.app, row(), dict(VALUE, shared=True), {'k': 1}, STATE)
        self.assertEqual(len(rows.rows), 0)
        for k in range(shared_rows.LIMIT + 5):
            self.put(row(text='ぎょう%d' % k))
        self.assertEqual(len(rows.rows), shared_rows.LIMIT)
        self.assertFalse(rows.has_text('ぎょう0'))
        self.assertTrue(rows.has_text('ぎょう%d' % (shared_rows.LIMIT + 4)))

    def test_off_switch(self):
        self.put(row())
        old = shared_rows.ENABLED
        shared_rows.ENABLED = False
        try:
            self.assertIsNone(shared_rows.take_for(self.app, task(), {'k': 1}, {}))
        finally:
            shared_rows.ENABLED = old


if __name__ == '__main__':
    unittest.main()
