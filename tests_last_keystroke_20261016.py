"""紫が残った短いかなを、1打だけ戻して読み直す（2026-10-16・`last_keystroke`）。

補正を全部通しても短いかなの紫が残った行で、かなキーの1打の誤り（隣の
キー・1字抜け・隣どうしの入れ替わり）を1つだけ戻した行を補正の入口に
通し直し、紫も迷いも残らないものだけを採る。

ここの例はすべて作った文。
"""
import unittest
from unittest import mock

import morphology as M
import last_keystroke as LK


class _NoWords:
    def is_world_reading(self, word):
        return False


class CandidateTests(unittest.TestCase):
    def test_one_keystroke_candidates(self):
        # は と き は隣のキー
        self.assertEqual(LK.candidates('とどはました', 2, 6).get('とどきました'), ('sub', 2))
        self.assertEqual(LK.candidates('まよました', 1, 5).get('まよいました'), ('ins', 2))
        self.assertEqual(LK.candidates('ひいしてまう', 1, 4).get('ひいてしまう'), ('swap', 2))

    def test_small_kana_and_n_need_a_kana_before(self):
        for text in LK.candidates('きょう', 0, 3):
            with self.subTest(text=text):
                self.assertNotIn(text[0], 'ぁぃぅぇぉゃゅょっゎんー')

    def test_small_and_large_kana_are_not_swapped(self):
        # 小書きと並の大きさは書き方の好み（すごぃ・きてねぇ）。打ち違いにしない
        self.assertNotIn('すごい', LK.candidates('すごぃ', 0, 3))
        self.assertNotIn('きてねえ', LK.candidates('きてねぇ', 0, 4))

    def test_purple_needs_read_words_in_the_same_sentence(self):
        # 文が丸ごと紫なら、読み直しが通っても証拠にならない
        self.assertFalse(LK._anchored('ふらをたぬ。', [(0, 5)]))
        self.assertFalse(LK._anchored('きのう「ふらをたぬ」と言った。', [(4, 9)]))
        self.assertTrue(LK._anchored('みちにまよました', [(4, 8)]))
        self.assertTrue(LK._anchored('ふらをたぬ、きのう見た。', [(0, 5)]))


@unittest.skipUnless(M.HAS_JANOME, 'real native dictionary required')
class RepairGateTests(unittest.TestCase):
    def test_predicate_must_follow_in_the_same_sentence(self):
        # 述語の無い言いさしは、どの読みでも紫が付かない
        self.assertFalse(LK._predicate_follows('あのようにも、', 3, 4))
        self.assertFalse(LK._predicate_follows('「あのようにも」と書いた。', 4, 5))
        self.assertTrue(LK._predicate_follows('あのようにも見える。', 3, 4))
        self.assertTrue(LK._predicate_follows('みちにまよいました', 5, 6))

    def test_kana_input_and_dictionary_index_are_required(self):
        result = {'odd_spans': [(4, 8)]}
        never = lambda text: self.fail('retried ' + text)
        self.assertIsNone(LK.repair('みちにまよました', result, never,
                                    input_method='romaji', dict_index=_NoWords()))
        self.assertIsNone(LK.repair('みちにまよました', result, never, dict_index=None))

    def test_long_or_non_kana_purple_is_left(self):
        never = lambda text: self.fail('retried ' + text)
        self.assertIsNone(LK.repair('みちにまよいましたよね', {'odd_spans': [(0, 7)]},
                                    never, dict_index=_NoWords()))
        self.assertIsNone(LK.repair('道にまよました', {'odd_spans': [(0, 3)]},
                                    never, dict_index=_NoWords()))
        # 紫が2つあって、片方が長いときも見ない
        self.assertIsNone(LK.repair('みちにまよましたがあれこれなにやら', {'odd_spans': [(3, 7), (8, 16)]},
                                    never, dict_index=_NoWords()))

    def test_line_final_double_is_left(self):
        # 行末の重なり打ちは別の字に置き換えて読ませない（重なり打ちの直しは切ってある）
        never = lambda text: self.fail('retried ' + text)
        self.assertIsNone(LK.repair('ねていますす', {'odd_spans': [(3, 6)]},
                                    never, dict_index=_NoWords()))
        self.assertIsNone(LK.repair('けしてくださいい。', {'odd_spans': [(3, 8)]},
                                    never, dict_index=_NoWords()))
        self.assertFalse(LK._doubled_tail('ばすにののおくれました', [(4, 5)]))

    def test_long_vowel_mark_is_left(self):
        # ー は遠いキー。ー を含む紫は見ない（伸ばし棒の打ち間違いは別の道）
        never = lambda text: self.fail('retried ' + text)
        self.assertIsNone(LK.repair('へんこうさーた', {'odd_spans': [(5, 7)]},
                                    never, dict_index=_NoWords()))
        self.assertFalse(any(op != 'ins' and line[i] == 'ー'
                             for line in ('さーた',)
                             for _text, (op, i) in LK.candidates(line, 0, 3).items()))

    def test_retry_with_marks_left_is_not_taken(self):
        marked = lambda text: {'original': text, 'corrected': text, 'odd_spans': [(0, 1)]}
        unsure = lambda text: {'original': text, 'corrected': text, 'odd_spans': [],
                               'unsure_spans': [(0, 1)]}
        for retry in (marked, unsure):
            self.assertIsNone(LK.repair('みちにまよました', {'odd_spans': [(4, 8)]},
                                        retry, dict_index=_NoWords()))

    def test_clean_retry_is_taken(self):
        clean = lambda text: {'original': text, 'corrected': text, 'odd_spans': [],
                              'unsure_spans': []}
        found = LK.repair('みちにまよました', {'odd_spans': [(4, 8)]}, clean,
                          dict_index=_NoWords())
        self.assertIsNotNone(found)
        self.assertEqual(found[0], 'みちにまよいました')
        self.assertEqual(found[2], (5, 5, 'い'))


@unittest.skipUnless(M.HAS_JANOME, 'real native dictionary required')
class LastKeystrokeLineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests_analysis_async import initial
        cls.state = initial()

    def setUp(self):
        from last_choice import set_active
        self.addCleanup(set_active, None)

    def run_line(self, line, decisions=None, input_method='kana'):
        from correction_entry import correct_line
        a = self.state
        return correct_line(line, a.store, context_vocab={}, input_method=input_method,
                            dict_index=a.dict_index,
                            decisions=a.decisions if decisions is None else decisions,
                            context_vec=a.context_vec)

    def test_one_keystroke_typos_are_repaired(self):
        for line, expected in (('にもつがとどはました', ('届きました', 'とどきました')),
                               ('みちにまよました', ('まよいました', '迷いました')),
                               ('ばすにののおくれました', ('のりおくれました', '乗り遅れました')),
                               ('ふまをせんたくしました', ('服を', 'ふくを'))):
            with self.subTest(line=line):
                result = self.run_line(line)
                self.assertTrue(any(x in result['corrected'] for x in expected), result['corrected'])
                self.assertEqual(result['odd_spans'], [])
                self.assertEqual(result['diagnosis']['language_state'], 'anomaly_repaired')

    def test_transposition_is_one_replacement(self):
        result = self.run_line('うこほうにいきます')
        self.assertIn(('うこ', 'こう', 'かな入力'), result['details'])
        self.assertFalse(any(not typed or not fixed for typed, fixed, _ in result['details']))

    def test_common_final_check_is_not_bypassed(self):
        # 置く直しも、ほかの直しと同じ最終検査を通る（2026-10-16）
        import corrector
        with mock.patch.object(corrector, '_check_replacement',
                               return_value=(None, 'test_common_gate')):
            result = self.run_line('みちにまよました')
        self.assertNotIn('まよいました', result['corrected'])
        self.assertTrue(result['odd_spans'])
        # 目的語と述語の門で止まる形（目的語のある文の述語の1字）は直さない
        result = self.run_line('かぜをひいしてまいました')
        self.assertNotIn('ひいてしまいました', result['corrected'])

    def test_sentences_without_evidence_are_left(self):
        for line in ('あのようなも、', '「あのようなも」と書いた。', 'まどをあけてくださぃ。'):
            with self.subTest(line=line):
                result = self.run_line(line)
                self.assertEqual(result['corrected'], line)

    def test_unclear_repairs_are_not_made(self):
        # とりました（り の抜け）と しました（と → し）が並ぶ。印は残す
        self.assertNotIn('しました', self.run_line('しゃしんをとました')['corrected'])
        # だら を足すと読めるが、読みの並びは悪くなる
        self.assertNotIn('だら', self.run_line('びょういんらいきます')['corrected'])
        # 行末の重なり打ちを ますか と読まない
        self.assertFalse(self.run_line('こどもがねていますす')['corrected'].endswith('ますか'))
        # ー と た を入れ替えて さたー と読まない
        self.assertNotIn('さたー', self.run_line('変更さーた')['corrected'])

    def test_correct_lines_with_purple_are_not_changed(self):
        # 正しい文に紫が付いていても、1打を戻した行が通らなければ元のまま
        for line in ('きょうはいいてんきです', 'あさからあめがふる', 'かわるきせつをたのしむ',
                     'みちにまよいました'):
            with self.subTest(line=line):
                with mock.patch.object(LK, 'repair', lambda *a, **k: None):
                    before = self.run_line(line)
                after = self.run_line(line)
                self.assertEqual(after['corrected'], before['corrected'])
                self.assertEqual(after['odd_spans'], before['odd_spans'])

    def test_rejected_repair_is_not_made_again(self):
        from decisions import DecisionStore
        decisions = DecisionStore()
        decisions.reject('とどは', '届き')
        decisions.reject('とどは', 'とどき')
        result = self.run_line('にもつがとどはました', decisions=decisions)
        self.assertNotIn('届き', result['corrected'])
        self.assertNotIn('とどき', result['corrected'])

    def test_repair_runs_once_per_line(self):
        calls = []
        real = LK.repair

        def counted(line, *args, **kwargs):
            calls.append(line)
            return real(line, *args, **kwargs)

        with mock.patch.object(LK, 'repair', counted):
            self.run_line('にもつがとどはました')
        self.assertEqual(calls, ['にもつがとどはました'])

    def test_romaji_input_is_left_to_the_romaji_path(self):
        calls = []
        real = LK.repair

        def counted(line, result, retry, **kwargs):
            calls.append(kwargs.get('input_method'))
            return real(line, result, retry, **kwargs)

        with mock.patch.object(LK, 'repair', counted):
            result = self.run_line('にもつがとどはました', input_method='romaji')
        self.assertEqual(calls, ['romaji'] if calls else [])
        self.assertNotIn(('とどは', '届き', 'かな入力'), result['details'])


if __name__ == '__main__':
    unittest.main()
