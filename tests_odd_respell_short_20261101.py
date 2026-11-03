# -*- coding: utf-8 -*-
"""短い行の紫の所の打ち違いの戻し（odd_respell・2026-11-01・短い行）。作った文だけ。"""
import unittest
from tests_analysis_async import initial
import odd_respell as O
import correction_entry as CE


class OddRespellShortTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.st = initial()

    def run_plain(self, text):
        st = self.st
        return CE._correct_line_halfwidth(text, st.store, context_vocab={}, decisions=st.decisions,
                                          input_method='kana', context_vec=st.context_vec, dict_index=st.dict_index)

    def repair(self, line, spans, readings=None):
        import kanji_guess
        st = self.st
        old = kanji_guess._IME_READINGS_PROVIDER
        if readings is not None:
            kanji_guess._IME_READINGS_PROVIDER = lambda s: readings.get(s, [])
        try:
            return O.repair_line(line, {'corrected': line, 'odd_spans': spans}, self.run_plain,
                                 st.store, st.dict_index, st.context_vec)
        finally:
            kanji_guess._IME_READINGS_PROVIDER = old

    def test_typed_reading_of_whole_commit_with_leading_kana(self):
        # 1回の確定（あれの＋方向）の打った読みを、紫の漢字の所から前の平仮名まで広げて引く
        import kanji_guess
        old = kanji_guess._IME_READINGS_PROVIDER
        kanji_guess._IME_READINGS_PROVIDER = lambda s: {'あれの方向': ['あれのほうこう']}.get(s, [])
        try:
            got = O._typed_run('あれの方向', 3, 5)
        finally:
            kanji_guess._IME_READINGS_PROVIDER = old
        self.assertEqual(got, (0, 5, ['あれのほうこう']))

    def test_unchanged_words_keep_their_spelling(self):
        # 読みの変わらない語（方向）は変換した表記のまま、変わった所だけかなにする
        alts = [x[0] for x in O._aligned('あれの方向', 0, 5, 'あれのほうこう', 'あれにほうこう')]
        self.assertIn('あれに方向', alts)

    def test_rolled_extra_key_in_one_kanji_word(self):
        # 1字の漢字の語の辞書の別の読み（蓋＝ふた）から、巻き込んだ1打（ふ）を抜く
        got = self.repair('見せ蓋ら', [(2, 4)])
        self.assertEqual(got['corrected'], '見せたら')

    def test_short_line_gain_is_a_share_of_cost(self):
        # 短い行は並びの費用が小さく、一定の差（GAIN）に届かない。元の行の費用の割合で見る（GAIN を超えては求めない）
        self.assertLess(O.GAIN_SHARE * 10000, O.GAIN)
        self.assertEqual(min(O.GAIN, O.GAIN_SHARE * 40000), O.GAIN)

    def test_one_kanji_word_readings(self):
        # 1字の漢字の語は、辞書にその字1字の語として在る読みも見る（上＝うえ/かみ）
        self.assertTrue(set(O._one_kanji_readings('上')) & {'うえ', 'かみ'})
        self.assertEqual(O._one_kanji_readings('上下'), ())

    def test_kana_word_respelled(self):
        got = self.repair('へおじを書く', [(0, 3)])
        self.assertEqual(got['corrected'], '返事を書く')

    def test_correct_short_lines_untouched(self):
        st = self.st
        for line in ['短い手紙', '資料はどこ', '保存された', '写真を撮った', '会議の資料', '計算が合わない', '野外活動']:
            r = CE.correct_line(line, st.store, context_vocab={}, input_method='kana', dict_index=st.dict_index,
                                decisions=st.decisions, context_vec=st.context_vec)
            self.assertEqual(r['corrected'], line, line)
            self.assertFalse(r.get('odd_spans'), line)

    def test_kanji_placed_by_rerun_is_not_a_second_fix(self):
        # 補正し直しが読みを替えずに漢字を置いただけの行は、もう1か所の直しを重ねた形ではない（作った例）
        self.assertTrue(O._same_reading('ほかにした場合', 'ほかにしたばあい'))
        self.assertFalse(O._same_reading('ほかにした場合', 'ほかのしたばあい'))

    def test_two_key_only_path_runs(self):
        # 2打の戻しだけで見る道が、名前の誤りで黙って止まらないこと
        import inspect
        src = inspect.getsource(O._two_only)
        for name in ('MARGIN_SHARE',):
            if name in src:
                self.assertTrue(hasattr(O, name), name)

    def test_tab_ends_the_field(self):
        # 打った行＋タブ＋メモ の行は、紫の所のある欄の中だけで読み直して比べる（メモは替えない・作った例）
        self.assertEqual(O._field('あい\tうえ\tお', 3, 4), (3, 5))
        self.assertEqual(O._field('あいう', 1, 2), (0, 3))
        line = '見せ蓋ら\t\t（見せたら）'
        got = self.repair(line, [(2, 4)])
        self.assertEqual(got['corrected'], '見せたら\t\t（見せたら）')

    def test_record_of_inner_clause_in_wide_purple(self):
        # 紫が欄全体でも、中の文節に打った読みの記録が在れば、その文節は記録の読みだけで見る（作った例）
        got = self.repair('見せ蓋ら\t（見せたら）', [(0, 4)], {'蓋ら': ['ふたら']})
        self.assertNotEqual(got['corrected'][:4], '魅せたら')
        import kanji_guess
        old = kanji_guess._IME_READINGS_PROVIDER
        kanji_guess._IME_READINGS_PROVIDER = lambda s: {'蓋ら': ['ふたら']}.get(s, [])
        try:
            span = O._span_reading('見せ蓋ら', 0, 4)
        finally:
            kanji_guess._IME_READINGS_PROVIDER = old
        self.assertEqual(span[2], ['みせふたら'])

    def test_unchanged_kanji_word_is_not_respelled(self):
        # 読みの変わらない前の語（見せ）の表記
        self.assertEqual(O._kept_edges('見せ蓋ら', 0, 4, 'みせふたら', 'みせたら')[0], '見せ')


if __name__ == '__main__':
    unittest.main()
