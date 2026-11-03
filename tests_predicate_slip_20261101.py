# -*- coding: utf-8 -*-
"""述語の打ち違いが IME で辞書の語の並びになった所（predicate_slip）と、odd_respell・pair_choice の手直し
（2026-11-01 B）。作った文だけ。"""
import unittest
from tests_analysis_async import initial
import correction_entry as CE
import odd_respell as O
import pair_choice as PC
import predicate_slip as P


def _line(st, line):
    return CE.correct_line(line, st.store, context_vocab={}, input_method='kana', dict_index=st.dict_index,
                           decisions=st.decisions, context_vec=st.context_vec)


class PredicateSlipTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.st = initial()

    def test_verb_plus_auxiliary_from_slip_is_restored(self):
        # とりかかった を さりかかった と打ち（と の隣のキー）、IME が 去り＋かかっ＋た にした形
        r = _line(self.st, '部屋の片付けに去りかかった。')
        self.assertEqual(r['corrected'], '部屋の片付けに取り掛かった。')

    def test_auxiliary_cut_as_adnominal(self):
        # 後ろの名詞に付いて かかる が連体詞に切れた形
        r = _line(self.st, '明日から引っ越しの準備に去りかかる予定です。')
        self.assertEqual(r['corrected'], '明日から引っ越しの準備に取り掛かる予定です。')

    def test_correct_compound_verbs_untouched(self):
        for line in ['彼は言いかけてやめた。', '子どもが泣き出しそうになった。', '書きかけの手紙を引き出しにしまった。',
                     '雪が降りかかる道を歩いた。', '来月から新しい仕事に取り掛かる予定です。', '明日は工事に着手する。',
                     '会議の日程を再調整する。']:
            r = _line(self.st, line)
            self.assertEqual(r['corrected'], line, line)
            self.assertFalse(r.get('odd_spans'), line)

    def test_dropped_particle_lines_untouched(self):
        for line in ['ご飯食べた。', '映画見に行った。', '母と一日過ごした。', '毎日日記を書く。']:
            r = _line(self.st, line)
            self.assertEqual(r['corrected'], line, line)

    def test_known_form(self):
        wf = P._wordfreq()
        pv, v_all, nouns = P._pairs()
        self.assertTrue(P._known('取り掛かる', wf, v_all, nouns))
        self.assertFalse(P._known('去りかかる', wf, v_all, nouns))

    def test_runs(self):
        from morphology import tokenize
        toks = list(tokenize('部屋の片付けに去りかかった。'))
        self.assertIn('去りかかる', [r[2] for r in P._runs(toks)])


class OddRespellReadingTests(unittest.TestCase):
    def test_placed_kanji_must_read_as_repair(self):
        # 生きた の読みは いきた。なまきた の戻しとして置いた形ではない
        self.assertFalse(O._reads_as('生きた', 'なまきた'))
        self.assertTrue(O._reads_as('生きた', 'いきた'))
        # 二度押しの字を1つにまとめた置き方は通す
        self.assertTrue(O._reads_as('生きた', 'いききた'))

    def test_typed_run_starts_before_purple(self):
        # 打った読みの記録が、紫の漢字より前の字から始まる確定
        import kanji_guess
        old = kanji_guess._IME_READINGS_PROVIDER
        kanji_guess._IME_READINGS_PROVIDER = lambda s: {'でも席': ['でもせき']}.get(s, [])
        try:
            got = O._typed_run('朝はでも席。', 4, 5)
        finally:
            kanji_guess._IME_READINGS_PROVIDER = old
        self.assertEqual(got, (2, 5, ['でもせき']))

    def test_further_changed_rival_does_not_tie(self):
        seen = O._Seen()
        seen['あ'] = (1000, True)
        seen['い'] = (2000, True)
        seen.further.add('い')
        self.assertEqual(O._pick(seen), ('あ', 1000))
        seen.further.clear()
        self.assertIsNone(O._pick(seen))

    def test_stray_long_mark_span(self):
        # 助詞のすぐ後ろで1語に切れた ー
        self.assertEqual([sp[0] for sp in O._stray_long_marks('メールを読んでーん信を')], [7])
        self.assertEqual(O._stray_long_marks('わーい、やったー。'), [])


class Batch3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.st = initial()

    def test_fresh_kana_verb_run(self):
        # 前の段が直した所に残った かなの動詞＋動詞 も述語の並びとして見る
        from morphology import tokenize
        toks = list(tokenize('部屋の片付けにとれかかった。'))
        self.assertIn('とれかかる', [r[2] for r in P._runs(toks, [(7, 12)])])
        self.assertNotIn('とれかかる', [r[2] for r in P._runs(toks)])

    def test_org_span_covers_earlier_fix(self):
        self.assertEqual(P._org_span('あいうえお', 'あかえお', 1, 2), (1, 3))
        self.assertEqual(P._org_span('あいう', 'あいう', 0, 2), (0, 2))

    def test_same_reading_rival_is_same_answer(self):
        seen = O._Seen()
        seen['でかけた'] = (1000, True)
        seen['出掛けた'] = (2000, True)
        self.assertEqual(O._pick(seen), ('出掛けた', 2000))

    def test_reading_table_accepts_misread_stem(self):
        # 解析は 曲が を 曲＋が と切って きょくが と読むが、読みの表には まが の表記として在る
        self.assertTrue(O._reads_as('曲が', 'まが'))

    def test_typed_record_with_period(self):
        import kanji_guess
        old = kanji_guess._IME_READINGS_PROVIDER
        kanji_guess._IME_READINGS_PROVIDER = lambda s: {'でも席。': ['でもせき。']}.get(s, [])
        try:
            got = O._typed_run('朝はでも席。', 4, 5)
        finally:
            kanji_guess._IME_READINGS_PROVIDER = old
        self.assertEqual(got, (2, 5, ['でもせき']))

    def test_undecided_line_stays_purple(self):
        r = _line(self.st, '変化なが遅い')
        self.assertEqual(r['corrected'], '変化なが遅い')


class StrayLongMarkLineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.st = initial()

    def test_colloquial_long_marks_untouched(self):
        for line in ['わーい、やったー。', 'もーいいよ。']:
            self.assertEqual(_line(self.st, line)['corrected'], line, line)


class CutObjectTests(unittest.TestCase):
    def test_rare_noun_at_line_end_is_fixed_when_one_common_neighbor(self):
        self.assertEqual(PC.propose('夜は家で単軌を'), [(4, 6, '天気')])

    def test_common_lines_ending_with_object(self):
        for line in ['明日の会議の資料を', '週末に部屋の掃除を', '文章の誤字を', '駅前で友人と']:
            self.assertEqual(PC.propose(line), [], line)


if __name__ == '__main__':
    unittest.main()
