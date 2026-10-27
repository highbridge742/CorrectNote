"""半角のまま打った文の補正（半角→全角）は、ファイルタブに平仮名か片仮名が1字以上あるときだけ（2026-10-26）。

うに 2026-10-26「半角のまま打った文を全角に補正するのは、ファイルタブ内に、平仮名か片仮名が1文字以上ある
場合にする。完全英語環境での誤検知を防ぐため。絵文字が2バイト以上かもしれないので、バイトでは判断しない。」

tab_context.tab_has_kana は字で数える。correction_entry.correct_line(tab_has_kana=False) で半角の段は掛からず、
True／None（渡されない）では今まで通り。ここの例はすべて作ったもの。
"""
import unittest

import tab_context as T


class TabHasKanaTest(unittest.TestCase):
    def test_counts_characters_not_bytes(self):
        # 絵文字（4バイト）や漢字だけではかな無し。かな1字で有り。半角の片仮名も数える
        self.assertFalse(T.tab_has_kana(''))
        self.assertFalse(T.tab_has_kana('The build passed 🎉🎉 on node 7'))
        self.assertFalse(T.tab_has_kana('東京 2026'))
        self.assertTrue(T.tab_has_kana('build passed\nメモ'))
        self.assertTrue(T.tab_has_kana('note: ok\n\nあ'))
        self.assertTrue(T.tab_has_kana('ﾃｽﾄ'))
        self.assertTrue(T.tab_has_kana('ー'))

    def test_context_default_allows(self):
        self.assertTrue(T.halfwidth_correction_allowed())
        with T.tab_kana(False):
            self.assertFalse(T.halfwidth_correction_allowed())
            with T.tab_kana(True):
                self.assertTrue(T.halfwidth_correction_allowed())
            self.assertFalse(T.halfwidth_correction_allowed())
        with T.tab_kana(None):
            self.assertTrue(T.halfwidth_correction_allowed())
        self.assertTrue(T.halfwidth_correction_allowed())


class HalfwidthGateTest(unittest.TestCase):
    def _run(self, line, **kw):
        import app
        from tests_analysis_async import initial
        from last_choice import set_active
        a = initial()
        self.addCleanup(set_active, None)
        if not a.store.lookup('もじにゅうりょく'):
            a.store.add('もじにゅうりょく', '文字入力', solid=True)
        return app.correct_line(line, a.store, input_method='kana', dict_index=a.dict_index,
                                decisions=a.decisions, context_vec=a.context_vec, **kw)

    def test_halfwidth_run_is_corrected_when_tab_has_kana(self):
        # 作った例: かな入力のまま半角で打った もじにゅうりょく
        line = 'md@i(4l)h'
        with_kana = self._run(line, tab_has_kana=True)
        default = self._run(line)
        self.assertEqual(with_kana.get('corrected'), default.get('corrected'))
        self.assertNotEqual(default.get('corrected'), line, default)

    def test_halfwidth_run_is_left_alone_when_tab_has_no_kana(self):
        line = 'md@i(4l)h'
        r = self._run(line, tab_has_kana=False)
        self.assertEqual(r.get('corrected'), line, r)
        self.assertFalse(r.get('changed'), r)

    def test_gate_does_not_leak_after_the_call(self):
        self._run('md@i(4l)h', tab_has_kana=False)
        self.assertTrue(T.halfwidth_correction_allowed())


if __name__ == '__main__':
    unittest.main()
