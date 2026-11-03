# -*- coding: utf-8 -*-
"""さっきまでの行の答えを、同じ行が戻った時に使う（作った例・2026-11-03）。"""
import unittest
from analysis_context import Reads
from row_memo import LIMIT, RowMemo


def row(text, signature=('n',), reads=None, **more):
    proof = Reads({'語': 1})
    for key in reads or ():
        proof.get(key)
    return dict(original=text, corrected=text + '!', _input_signature=signature, _context_evidence=proof.evidence(), **more)


class Memo(unittest.TestCase):
    def setUp(self):
        self.m = RowMemo()
        self.m.check('tab', 's')

    def back(self, text, signature=('n',), context=None, tab_kana=None):
        results = [dict(original=text, pending=True)]
        left = self.m.take_back(results, [0], {0: signature}, context or {'語': 1}, set(), tab_kana)
        return results[0], left

    def test_the_same_row_comes_back(self):
        self.m.put(row('字'), {'語': 1})
        got, left = self.back('字')
        self.assertEqual((got['corrected'], left), ('字!', []))

    def test_other_inputs_do_not(self):
        self.m.put(row('字'), {'語': 1})
        self.assertEqual(self.back('字', signature=('m',))[1], [0])
        self.assertEqual(self.back('別')[1], [0])

    def test_a_context_it_read_that_moved_does_not(self):
        self.m.put(row('字', reads=['語']), {'語': 1})
        self.assertEqual(self.back('字', context={'語': 2})[1], [0])

    def test_a_context_it_did_not_read_may_move(self):
        self.m.put(row('字'), {'語': 1})
        self.assertEqual(self.back('字', context={'語': 2})[1], [])

    def test_unfinished_rows_are_not_kept(self):
        plain = row('字')
        plain['_input_signature'] = None
        for bad in (row('字', pending=True), row('字', deferred_stages=['x']), row('字', analysis_error=True), plain, None):
            self.m.put(bad, {})
        self.assertEqual(self.m.rows, {})

    def test_another_tab_or_state_clears(self):
        self.m.put(row('字'), {})
        self.m.check('tab', 's')
        self.assertTrue(self.m.rows)
        self.m.check('tab2', 's')
        self.assertFalse(self.m.rows)
        self.m.put(row('字'), {})
        self.m.check('tab2', 's2')
        self.assertFalse(self.m.rows)

    def test_keeps_only_what_the_row_read(self):
        self.m.put(row('字', reads=['語']), {'語': 1, '他': 2, 'ほか': 3})
        self.assertEqual(next(iter(self.m.rows.values()))[1], {'語': 1})

    def test_a_row_that_read_all_of_the_context_is_not_kept(self):
        r = row('字')
        r['_context_evidence'] = dict(r['_context_evidence'], whole=True)
        self.m.put(r, {'語': 1})
        self.assertFalse(self.m.rows)

    def test_small(self):
        for i in range(LIMIT + 50):
            self.m.put(row('字%d' % i), {})
        self.assertEqual(len(self.m.rows), LIMIT)
        self.assertNotIn('字0', self.m.texts())

    def test_tab_kana_must_match(self):
        self.m.put(row('字', _tab_has_kana=False), {'語': 1})
        self.assertEqual(self.back('字', tab_kana=True)[1], [0])
        self.assertEqual(self.back('字', tab_kana=False)[1], [])


if __name__ == '__main__':
    unittest.main()
