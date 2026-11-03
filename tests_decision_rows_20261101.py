# -*- coding: utf-8 -*-
"""補正の判断を取り消しても、関係の無い行は解析し直さない（2026-11-01 うにさん「覚えている補正の判断の項目を
開いて、ひとつ消すと、すべての解析がやり直しになって困る。無関係の行は再解析しない」）。

判断の版（decisions.revision）は解析の状態の鍵の選び直しの欄に入り、変わった語（used_changes）を元の文字列に
含む行だけが合わなくなる（analysis_worker._keys_unchanged）。"""
import unittest
from types import SimpleNamespace

import analysis_worker
import decisions
import used_changes


def _key(choice, decided):
    return ('store', 1, (choice, decided), 0, 'index', True, 'context', ('kana', 'jis'), (), ('ime', 0))


def _row(original):
    return dict(original=original, corrected=original,
                used_keys=dict(vocab=[], choice=[], recent=False, whole=False, loan=False),
                _context_evidence=dict(whole=False, keys=[]))


class DecisionRowsTests(unittest.TestCase):
    def setUp(self):
        used_changes.install()
        self.store = decisions.DecisionStore()
        self.app = SimpleNamespace(decisions=self.store, choices=None, store=None)

    def test_each_change_moves_the_revision_and_names_its_words(self):
        before = self.store.revision()
        self.store.protect('資料')
        self.store.reject('普通', '不通')
        self.store.unprotect('資料')
        after = self.store.revision()
        self.assertEqual(after - before, 3)
        self.assertEqual(used_changes.changed(self.store, before, after), {'資料', '普通', '不通'})
        self.assertFalse(self.store.unprotect('資料'))           # 無いものを消しても版は動かない
        self.assertEqual(self.store.revision(), after)

    def test_only_rows_with_the_word_are_redone(self):
        self.store.protect('資料')
        before = self.store.revision()
        self.store.unprotect('資料')
        old, new = _key(0, before), _key(0, self.store.revision())
        self.assertTrue(analysis_worker.same_model_state(old, new))
        self.assertFalse(analysis_worker.result_compatible(self.app, _row('会議の資料を作成した。'), old, new))
        self.assertTrue(analysis_worker.result_compatible(self.app, _row('明日は公園に行く。'), old, new))

    def test_a_context_choice_names_only_its_word(self):
        # 前後の語ごとの選び直しを一覧から消すとき、変わったのはその語と選んだ語だけ（前後の語は含めない）
        rec = {'kind': 'context', 'key': ['・', '連接', 'キー'], 'original': '・連接キー', 'chosen': '・連接様キー'}
        self.assertEqual(set(used_changes._record_keys(rec)), {'連接', '連接様'})

    def test_an_unknown_change_redoes_every_row(self):
        before = self.store.revision()
        self.store.load('存在しないファイル.json')             # 読み込みは何が変わったか分からない（ここでは無い）
        self.store._revision += 1                              # 記録の無い変化
        old, new = _key(0, before), _key(0, self.store.revision())
        self.assertFalse(analysis_worker.result_compatible(self.app, _row('明日は公園に行く。'), old, new))


if __name__ == '__main__':
    unittest.main()
