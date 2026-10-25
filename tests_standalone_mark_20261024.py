"""単独で残った ゛゜ の1打の戻し（かな入力・2026-10-24・間違えやすいキーの傾向）。

゛゜キーは小指の端にあり、隣のキー（せ・け・へ・ほ・゜）との打ち違いや余分な1打が起きやすい。
前の字に付かずに残った印は打ち間違いの確かな跡なので、抜く・隣のキーの字に替える・
（゜のときは）前の字に゛を付ける、の1打の戻しを試す。例は作った文。
"""
import unittest

from tests_analysis_async import initial
from correction_entry import correct_line
import last_keystroke as L


class StandaloneMarkTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.st = initial()

    def correct(self, text):
        st = self.st
        return correct_line(text, st.store, context_vocab={}, input_method='kana', dict_index=st.dict_index,
                            decisions=st.decisions, context_vec=st.context_vec)

    def test_variants(self):
        # ゜のつもりの ゛（前の字に ゛ を付ける）
        self.assertEqual(L._standalone_mark_variants('かき゜く', 2), ['かぎく'])
        # 印のキーに触れるキー（け）の後ろの余分な印は抜く
        self.assertIn('かけた', L._standalone_mark_variants('かけ゜た', 2))
        # 印がもう付いた字の後ろの印も抜く
        self.assertEqual(L._standalone_mark_variants('たべ゜た', 2), ['たべた'])
        # 印のキーから遠い字（あ）の後ろの印は、その字が紛れ込んだ打鍵のことが多いので1字では戻さない
        self.assertEqual(L._standalone_mark_variants('かあ゛た', 2), [])

    def test_extra_mark_is_removed(self):
        self.assertEqual(self.correct('窓を開け゛て空気を入れる')['corrected'], '窓を開けて空気を入れる')
        self.assertEqual(self.correct('山へ行くのが゜楽しみだ')['corrected'], '山へ行くのが楽しみだ')

    def test_quoted_mark_is_kept(self):
        self.assertEqual(self.correct('この印は「゛」です')['corrected'], 'この印は「゛」です')


if __name__ == '__main__':
    unittest.main()
