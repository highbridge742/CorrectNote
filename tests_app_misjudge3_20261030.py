"""アプリでだけ崩れた3つの誤判定の直し（2026-10-30・補正担当。例文は作った文）

- 依頼の動詞（〜てください）の根拠は、直す範囲がその動詞に届くときだけ使う
- 並立の や の直後に係助詞・格助詞が来る形は異様（や は次の名詞を要る）
- 助動詞の語幹の よう の直後に係助詞・並立助詞は来ない（雨のようも）
- コロンの直前の全角数字は見出しの番号で、同じキーの ！ にしない
"""
import unittest
from tests_analysis_async import initial
from correction_entry import correct_line


class RequestEvidenceReachTests(unittest.TestCase):
    def test_far_request_is_not_evidence(self):
        from semantic_roles import request_action_evidence
        source = '昔についてを目につく所に書き足してください。'
        self.assertIsNone(request_action_evidence(source, 5, 7, 'われ'))

    def test_request_on_the_verb_itself_still_counts(self):
        from semantic_roles import request_action_evidence
        source = 'ここに書けてください。'
        got = request_action_evidence(source, 3, 5, '書い')
        self.assertIsNotNone(got)
        self.assertEqual(got['relation'], 'requested_action')


class ParallelYaTests(unittest.TestCase):
    def odd(self, text):
        from oddness import is_odd_run
        from morphology import tokenize
        def tk(s):
            return [(t.surface, t.pos + (':' + t.pos_sub if t.pos_sub else ''), t.reading,
                     t.start, t.end, t.has_reading) for t in tokenize(s)]
        return is_odd_run(text, tk, with_spans=True)

    def test_ya_before_particle_is_odd(self):
        self.assertTrue(any(a == 'や' for a, *_ in self.odd('本やも読む。')))

    def test_ya_between_nouns_is_fine(self):
        self.assertFalse(any(a == 'や' for a, *_ in self.odd('本やノートも読む。')))

    def test_auxiliary_you_before_particle_is_odd(self):
        self.assertTrue(any(a == 'よう' for a, *_ in self.odd('雨のようも降る。')))

    def test_you_kept_where_natural(self):
        for text in ('雨のようにも見える。', 'できそうもない。', '知りようもない。'):
            self.assertFalse(any(a in ('よう', 'そう') for a, *_ in self.odd(text)), text)


class ColonNumberTests(unittest.TestCase):
    def run_line(self, face):
        st = initial()
        return correct_line(face, st.store, context_vocab={}, input_method='kana', dict_index=st.dict_index,
                            decisions=st.decisions, context_vec=st.context_vec)['corrected']

    def test_number_before_colon_is_kept(self):
        self.assertEqual(self.run_line('見出し１：'), '見出し１：')


if __name__ == '__main__':
    unittest.main()
