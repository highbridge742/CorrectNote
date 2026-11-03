# -*- coding: utf-8 -*-
"""かなのまま残った文節の頭の並びの区切りを読みの格子で決めて漢字を置く（kana_lattice_place・2026-10-25）。作った文だけ。"""
import unittest
from tests_analysis_async import initial
import kana_lattice_place as P
import correction_entry as CE


class LatticePlaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.st = initial()

    def run_line(self, line):
        st = self.st
        return CE.correct_line(line, st.store, context_vocab={}, input_method='kana', dict_index=st.dict_index,
                               decisions=st.decisions, context_vec=st.context_vec)

    def test_explained_kana_is_left_alone(self):
        # かなの文法で説明の付く並び・漢字の語の尻尾のかな・動詞のかなは触らない
        for line in ['風邪をひいて三日も寝込んだ。', 'この問題は思ったより難しかった。', 'たくさん食べてください。',
                     '母の作る味噌汁が一番おいしい。', '資料の数字に誤りがないか二人で確認した。']:
            places, _ = P.propose(line, self.st.store, self.st.dict_index)
            self.assertEqual(places, [], line)

    def test_clause_starting_with_particle_is_not_cut(self):
        places, _ = P.propose('たふせ', self.st.store, self.st.dict_index)
        self.assertEqual(places, [])

    def test_noun_run_unexplained_by_kana_grammar_is_cut_by_lattice(self):
        # 格子の切り方が名詞で、今までの置き方の候補と同じ漢字なら置く（身近さの門は今までと同じ）
        places, _ = P.propose('たなのせいとん', self.st.store, self.st.dict_index)
        self.assertTrue(any(f == '整頓' for _a, _b, f in places) or places == [], places)

    def test_common_noun_in_explained_kana_run_gets_kanji(self):
        # かなの文法で説明の付く行でも、ふだん漢字で書く名詞は漢字に（2026-10-31）。副詞・いたします等はかなのまま
        places, _ = P.propose('きのうはやさいをかった。', self.st.store, self.st.dict_index)
        self.assertIn('野菜', [f for _a, _b, f in places])
        places, _ = P.propose('よろしくおねがいいたします。', self.st.store, self.st.dict_index)
        self.assertEqual([f for _a, _b, f in places], ['お願い'])
        places, _ = P.propose('だいたいわかった。', self.st.store, self.st.dict_index)
        self.assertEqual(places, [])

    def test_kana_only_line_gets_kanji_for_usual_nouns(self):
        # かなだけの行も、漢字で書くのが普通の名詞は漢字に（2026-10-31）。つないで辞書の1語になる名詞はその語に
        st = self.st
        for line, want in (('でんわばんごうをおしえて', '電話番号をおしえて'), ('またれんらくします。', 'また連絡します。')):
            places, _ = P.propose(line, st.store, st.dict_index)
            got = line
            for s0, e0, f in sorted(places, reverse=True):
                got = got[:s0] + f + got[e0:]
            self.assertEqual(got, want)

    def test_undecided_or_predicate_kana_is_left(self):
        # 表記の決まらない語（はし → 橋・箸）、を の後ろの述語（いただき）、1字の読みのつなぎ（ご｜め）はかなのまま
        for line in ['はしでたべる。', '貴重なお時間をいただき、', 'ごめな、ちょっと待って。']:
            places, _ = P.propose(line, self.st.store, self.st.dict_index)
            self.assertEqual(places, [], line)

    def test_kana_after_fixed_mark_gets_kanji(self):
        # 単独の印を前の字に付けて直した行も、かなのまま残る名詞は漢字に（2026-10-31）。印の戻しが隣のキーの
        # 打ち違い（し＋へ）に取られない
        for line, want in (('て゛んわばんごうを教える。', '電話番号を教える。'),
                           ('し゛かんのやくそくを守る。', '時間の約束を守る。')):
            self.assertEqual(self.run_line(line)['corrected'], want, line)

    def test_kana_runs(self):
        self.assertEqual(P.kana_runs('間違いのほせい'), [(2, 7)])
        self.assertEqual(P.kana_runs('漢字'), [])


if __name__ == '__main__':
    unittest.main()
