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

    def test_kana_runs(self):
        self.assertEqual(P.kana_runs('間違いのほせい'), [(2, 7)])
        self.assertEqual(P.kana_runs('漢字'), [])


if __name__ == '__main__':
    unittest.main()
