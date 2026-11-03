# -*- coding: utf-8 -*-
"""紫の所の読みに一般の打ち違いの戻しを当てて、はっきり自然になる形を1つ選ぶ（odd_respell・2026-11-01）。作った文だけ。"""
import unittest
from tests_analysis_async import initial
import odd_respell as O
import correction_entry as CE


class OddRespellTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.st = initial()

    def run_line(self, line, input_method='kana'):
        st = self.st
        return CE.correct_line(line, st.store, context_vocab={}, input_method=input_method, dict_index=st.dict_index,
                               decisions=st.decisions, context_vec=st.context_vec)

    def test_rolled_extra_key_in_purple_verb_is_removed(self):
        r = self.run_line('これから仕事に取り掛かする。')
        self.assertEqual(r['corrected'], 'これから仕事に取り掛かる。')
        self.assertFalse(r.get('odd_spans'))

    def test_correct_lines_untouched(self):
        for line in ['これから仕事に取り掛かる。', '資料の数字に誤りがないか二人で確認した。']:
            self.assertEqual(self.run_line(line)['corrected'], line, line)

    def test_only_kana_input(self):
        res = {'corrected': 'x', 'odd_spans': [(0, 1)]}
        self.assertIs(O.repair_line('x', res, lambda t: {}, None, None, input_method='romaji'), res)

    def test_overlapping_purple_is_one_place(self):
        # 内側の小さな紫だけを直して外側の迷いを残したまま決めない
        seen = []
        orig = O._choose

        def spy(done, a, b, rd, *rest):
            seen.append((a, b))
            return None
        O._choose = spy
        try:
            O.repair_line('あいうえおかき', {'corrected': 'あいうえおかき', 'odd_spans': [(1, 5), (2, 3)]},
                          lambda t: {}, None, None)
        finally:
            O._choose = orig
        self.assertTrue(all(a <= 1 and b >= 5 for a, b in seen), seen)

    def test_typed_reading_of_the_clause_comes_first(self):
        # PC で打った読みの記録が在れば、その読みから戻す（解析の読みは打った読みと違うことがある）
        import kanji_guess
        old = kanji_guess._IME_READINGS_PROVIDER
        kanji_guess._IME_READINGS_PROVIDER = lambda s: {'漢字語': ['かんじご']}.get(s, [])
        try:
            got = O._span_reading('漢字語です', 0, 3, self.st.dict_index)
        finally:
            kanji_guess._IME_READINGS_PROVIDER = old
        self.assertIsNotNone(got)
        self.assertEqual(got[2][0], 'かんじご')

    def test_part_of_kanji_run_is_not_replaced(self):
        # 漢字の並びの一部だけを1打違いの漢字に替える形は採らない（並びは打った読みから IME が変換したもの）
        self.assertTrue(O._splits_kanji_run('誤変換です', '小変換です'))
        self.assertFalse(O._splits_kanji_run('四ゆう末は', '週末は'))
        self.assertFalse(O._splits_kanji_run('取り掛かする', '取り掛かる'))
        # 打った読みの記録から1文節ごと戻すときは、紫の所の中の漢字は読み直してよい
        self.assertTrue(O._splits_kanji_run('誤変換です', '小変換です', 0, 1))
        self.assertFalse(O._splits_kanji_run('デ゜ン和番号を', '電話番号を', 0, 6))

    def test_rolled_mark_in_typed_reading_of_converted_clause(self):
        # 濁点と一緒に半濁点を巻き込み、IME が記号まじりに変換した1文節は、打った読みの記録から ゜ を抜いて戻す
        import kanji_guess
        st = self.st
        old = kanji_guess._IME_READINGS_PROVIDER
        kanji_guess._IME_READINGS_PROVIDER = lambda s: {'デ゜ン和番号': ['で゜んわばんごう']}.get(s, [])
        run = lambda t: CE._correct_line_halfwidth(t, st.store, context_vocab={}, decisions=st.decisions,
                                                   input_method='kana', context_vec=st.context_vec,
                                                   dict_index=st.dict_index)
        try:
            res = O.repair_line('デ゜ン和番号を', {'corrected': 'デ゜ン和番号を', 'odd_spans': [(0, 6)]}, run,
                                st.store, st.dict_index, st.context_vec)
        finally:
            kanji_guess._IME_READINGS_PROVIDER = old
        self.assertEqual(res['corrected'], '電話番号を')

    def test_stray_mark_seen_without_purple(self):
        # 紫が無くても、付く先の無い ゜ の所は打った読みから戻す（作った例）
        import kanji_guess
        st = self.st
        old = kanji_guess._IME_READINGS_PROVIDER
        kanji_guess._IME_READINGS_PROVIDER = lambda s: {'デ゜ン和番号': ['で゜んわばんごう']}.get(s, [])
        run = lambda t: CE._correct_line_halfwidth(t, st.store, context_vocab={}, decisions=st.decisions,
                                                   input_method='kana', context_vec=st.context_vec,
                                                   dict_index=st.dict_index)
        try:
            res = O.repair_line('デ゜ン和番号を', {'corrected': 'デ゜ン和番号を', 'odd_spans': []}, run,
                                st.store, st.dict_index, st.context_vec)
        finally:
            kanji_guess._IME_READINGS_PROVIDER = old
        self.assertEqual(res['corrected'], '電話番号を')

    def test_stray_mark_clause_read_from_surface(self):
        # 打った読みの記録が無くても、記号まじりの1文節は表記から読み直す（記号は同じキーのかな・作った例）
        self.assertEqual(O._key_kana('）')[0], 'ょ')
        st = self.st
        run = lambda t: CE._correct_line_halfwidth(t, st.store, context_vocab={}, decisions=st.decisions,
                                                   input_method='kana', context_vec=st.context_vec,
                                                   dict_index=st.dict_index)
        res = O.repair_line('デ゜ン和番号を', {'corrected': 'デ゜ン和番号を', 'odd_spans': []}, run,
                            st.store, st.dict_index, st.context_vec)
        self.assertEqual(res['corrected'], '電話番号を')

    def test_combining_and_spaced_marks(self):
        # 結合用の半濁点・空白＋結合用の半濁点（NFKC の形）も ゛゜ と同じに見る（作った例）
        st = self.st
        run = lambda t: CE._correct_line_halfwidth(t, st.store, context_vocab={}, decisions=st.decisions,
                                                   input_method='kana', context_vec=st.context_vec,
                                                   dict_index=st.dict_index)
        for line in ('デ\u309aン和番号を', 'デ \u309aン和番号を'):
            res = O.repair_line(line, {'corrected': line, 'odd_spans': []}, run, st.store, st.dict_index, st.context_vec)
            self.assertEqual(res['corrected'], '電話番号を', repr(line))
        self.assertEqual(O._spacing_marks('か\u3099'), 'か\u3099')   # 合成できる形は変えない

    def test_ime_reading_keeps_stray_mark(self):
        # 半角カタカナの読みの付く先の無い ﾟ は、NFKC で空白・結合文字になって捨てられていた
        import ime_readings as IR
        self.assertEqual(IR.reading_to_hiragana('ﾃﾞﾟﾝﾜ'), 'で゜んわ')
        self.assertTrue(IR.is_kana_reading(IR.reading_to_hiragana('ﾃﾞﾟﾝﾜ')))
        self.assertEqual(IR.reading_to_hiragana('ｻﾞｲﾘｮｳ'), 'ざいりょう')


if __name__ == '__main__':
    unittest.main()
