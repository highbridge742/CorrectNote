"""紫が残った短いかなを、1打だけ戻して読み直す（2026-10-16・`last_keystroke`）。

補正を全部通しても短いかなの紫が残った行で、かなキーの1打の誤り（隣の
キー・1字抜け・隣どうしの入れ替わり）を1つだけ戻した行を補正の入口に
通し直し、紫も迷いも残らないものだけを採る。

ここの例はすべて作った文。
"""
import unittest
from unittest.mock import patch
from unittest import mock

import morphology as M
import last_keystroke as LK

# 本人の IME が無いときの判定を試す（PC では IME が 公園・夜に・暖かい を選び、期待と違う顔になる）
_without_ime = mock.patch.object(LK, '_ime_face', lambda *a, **k: None)


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
    def test_reading_kept_is_not_misled_by_the_kana_tokenization(self):
        # 戻した行のかなの切り方（ちょう|せいし|た）が文節の端（ちょうせい|した）と合わなくても、
        # 両側を同じ字句の境まで広げて比べる（ちょうせいし 対 ちょうせいし）→ 読みは保たれている
        self.assertTrue(LK._reading_kept('フォントの大きさをちょうせいした。', 9, 14, 'フォントの大きさを調整した。'))
        self.assertFalse(LK._reading_kept('フォントの大きさをちょうせいした。', 9, 14, 'フォントの大きさを調整だ。'))

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
        # 目的語のある文の述語の1字は、元の述語が正しく書けた証明が無いと直せない
        # （unproven_original_object_predicate）。文節を打った読みに戻して読み直した
        # 形だけは、その証明（ime_clause_proof）を最終検査に渡して直る（2026-10-17）。
        # 検査そのものは通る（ほかの門はそのまま）
        import corrector
        seen = []
        real = corrector._check_replacement

        def spy(*args, **kwargs):
            seen.append(kwargs.get('ime_clause_proof', False))
            return real(*args, **kwargs)
        with mock.patch.object(corrector, '_check_replacement', side_effect=spy):
            result = self.run_line('かぜをひいしてまいました')
        self.assertEqual(result['corrected'], 'かぜをひいてしまいました')
        self.assertIn(('して', 'てし', 'かな入力'), result['details'])
        self.assertTrue(any(seen), seen)
        self.assertFalse(all(seen), seen)

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


@unittest.skipUnless(M.HAS_JANOME, 'real native dictionary required')
class IMEClauseRepairTests(unittest.TestCase):
    """打ち違いの読みを IME が忠実に変換した文節の読み直し（2026-10-17）。

    IME の対（文節の表記と打った読み）を手がかりに、文節を打った読みに戻し、
    1打を戻した読みを補正の入口に通し直す。語を名指しせず、並びの費用と
    読みの並びで決める。
    """
    @classmethod
    def setUpClass(cls):
        from tests_analysis_async import initial
        cls.state = initial()

    def setUp(self):
        from last_choice import set_active
        self.addCleanup(set_active, None)

    def correct(self, line, pairs=(), input_method='kana'):
        import app
        a = self.state
        for surface, reading in pairs:
            a.ime_readings.remember(surface, reading)
        return app.correct_line(line, a.store, input_method=input_method,
                                dict_index=a.dict_index, decisions=a.decisions,
                                context_vec=a.context_vec)

    @_without_ime
    def test_entrance_conversion_of_the_reverted_clause_is_accepted(self):
        # 語の中の打ち違い（うき前・こひ都市・帳せいて・あたらセ氏い）をかなに戻して入口に通し、入口が自ら
        # 漢字に変換した形は採る: かなだけの範囲の読みは字句の切り方（ちょう|せいし|た）に引きずらず
        # その字で比べる（調整）・紫と迷いの位置は入口に渡した行の上の位置で見る（新しい の後ろの
        # 迷いは元の行にもある）・行の残り（料理本・去年）の重さでは止めない（駅前・今年）。
        for line, pair, want in (
                ('うき前の本屋で新しい料理本を買った。', ('うき前の', 'うきまえの'), '駅前の本屋で'),
                ('こひ都市の夏は去年より暑く感じる。', ('こひ都市の', 'こひとしの'), '今年の夏は'),
                ('フォントの大きさを帳せいてした。', ('帳せいて', 'ちょうせいて'), '調整した'),
                ('あたらセ氏い炊飯器でご飯を炊いたらとてもおいしかった。', ('あたらセ氏い', 'あたらせしい'), '新しい炊飯器'),
                # 文語の活用形（濃**し**: 今の文には出ない）は印。かなに戻した こしと を入口が 今年 にする
                ('濃しとの夏は去年より暑く感じる。', ('濃しとの', 'こしとの'), '今年の夏は')):
            with self.subTest(line=line):
                result = self.correct(line, [pair])
                self.assertIn(want, result['corrected'])
                self.assertEqual(result['odd_spans'], [])

    @_without_ime
    def test_kana_run_starting_inside_a_written_word_passes_the_bound_verb_gate(self):
        # 書く＋なんして の くなんして は 書く の送りがなから始まるかなの並びで、サ変名詞の読みの一部を
        # 削る直しではない。最終検査の bound_verb_slot（oddness.preserves_bound_verb）はそこを見ない
        result = self.correct('資料を書くなんしてください。', [('書くなん', 'かくなん')])
        self.assertEqual(result['corrected'], '資料を確認してください。')
        self.assertEqual(result['odd_spans'], [])

    def test_faithful_ime_conversions_of_typos_are_reread(self):
        # 巻き込んだ1字（あめ**ろ**が）・隣のキー（い**す**けん）・足した1字（しりょう**あ**を）
        for line, pair, want in (
                ('雨ろが止んだら散歩に行こう。', ('雨ろが', 'あめろが'), '雨が止んだら散歩に行こう。'),
                ('さまざまないす県が出た。', ('いす県が', 'いすけんが'), 'さまざまな意見が出た。'),
                ('資料あを確認してください。', ('資料あを', 'しりょうあを'), '資料を確認してください。')):
            with self.subTest(line=line):
                result = self.correct(line, [pair])
                self.assertEqual(result['corrected'], want)
                self.assertEqual(result['odd_spans'], [])

    def test_correct_clauses_with_pairs_are_left(self):
        # 正しく打った文節は、行全体の費用が高くても（物好き・柿の木）替えない。
        # 1語に収まる文節を、よく出る別の語（人→こと・元→もち・家→イエス）にしない
        for line, pair in (('物好きな人もいるものだ。', ('人も', 'ひとも')),
                           ('設定を元に戻してください。', ('元に', 'もとに')),
                           ('祖母の家の庭には柿の木がある。', ('家の', 'いえの')),
                           ('雨の降る日は家で過ごすことが多い。', ('降る', 'ふる')),
                           ('週末に家族で海へ出かける予定です。', ('予定です', 'よていです'))):
            with self.subTest(line=line):
                self.assertEqual(self.correct(line, [pair])['corrected'], line)

    def test_kana_results_need_a_clearly_better_reading(self):
        # 入口が語と認めず、かなのまま残る直しは、読みの並びがはっきり良くなるものだけ。
        # 珍しい語の読み（しにせ）に化けず、弱い直しが一番のとき次の候補にも落とさない
        for line, pair, bad in (
                ('雨上がりの空に二死せがかかっていた。', ('二死せが', 'にしせが'), 'しにせ'),
                ('電車が沖れたので会議に間に合わなかった。', ('沖れたので', 'おきれたので'), '起きれ')):
            with self.subTest(line=line):
                self.assertNotIn(bad, self.correct(line, [pair])['corrected'])

    def test_only_kana_input_with_store_and_pairs(self):
        result = {'corrected': '雨ろが止んだら散歩に行こう。', 'odd_spans': [], 'unsure_spans': []}
        a = self.state
        self.assertIsNone(LK.repair_ime_clause('雨ろが止んだら散歩に行こう。', result, lambda t: None,
                                               input_method='romaji', dict_index=a.dict_index,
                                               store=a.store))
        self.assertIsNone(LK.repair_ime_clause('雨ろが止んだら散歩に行こう。', result, lambda t: None,
                                               input_method='kana', dict_index=a.dict_index,
                                               store=None))
        # IME の対が無ければ文節が取れず、何もしない
        import kanji_guess
        with mock.patch.object(kanji_guess, '_IME_READINGS_PROVIDER', None):
            self.assertIsNone(LK.repair_ime_clause('雨ろが止んだら散歩に行こう。', result,
                                                   lambda t: None, input_method='kana',
                                                   dict_index=a.dict_index, store=a.store))

    def test_keystroke_level_variants_reach_dakuten_slips(self):
        # 濁点を含む字の入れ替わり（むすがし→むずかし）は字の単位の戻しでは届かず、
        # 打鍵の単位（key_repairs）で届く。かなの結果でも読みの並びがはっきり良く、
        # IME が漢字にしていた文節なので辞書の形（難しかっ）に置く
        result = self.correct('この問題は思ったよりむスガ歯科った。', [('むスガ歯科っ', 'むすがしかっ')])
        self.assertEqual(result['corrected'], 'この問題は思ったより難しかった。')

    def test_known_kana_word_may_stay_costly(self):
        # 入口が漢字にしない語（冷蔵庫）はかなのまま残り、行の費用は線の上に残る。
        # 文節の終わりが字句の途中（例そざうこ|の）でも対を引き、辞書に在る読み
        # （れいぞうこ）＋手を付けていない付属（の）なら採り、辞書で1通りの漢字に置く
        result = self.correct('例そざうこの中に牛乳が残っていない。', [('例そざうこ', 'れいそざうこ')])
        self.assertEqual(result['corrected'], '冷蔵庫の中に牛乳が残っていない。')
        # 戻した字を付属に数えて語を作らない（あめふり＋がの）
        result = self.correct('雨ふがりの空に虹がかかっていた。', [('雨ふがり', 'あめふがり')])
        self.assertNotIn('あめふりが', result['corrected'])

    def test_kanji_form_falls_back_to_kana_when_check_stops_it(self):
        # 漢字に置いた形だけが共通の最終検査の条件に触れるときは、かなのままの形で受け直す。
        # 見逃しに戻さない。2026-10-17 の夜までは 冷蔵庫の（この を連体詞と見る門）と
        # 悪かった（消す字の隣が漢字・カタカナで隣り合いを測れない門）がその例だったが、
        # 文節の証明のある形はどちらの門も通るようになったので、ここでは漢字の形だけを
        # 止める検査を仮に差して、かなで受け直す動きを見る
        import corrector
        real = corrector._check_replacement

        def stop_kanji(line, item, *args, **kwargs):
            if any(LK._kanji(c) for c in item[2]) and '冷蔵庫' in item[2]:
                return None, 'test_stop_kanji'
            return real(line, item, *args, **kwargs)
        line, pair = '例そせうこの中を整理して古い物を捨てた。', ('例そせうこ', 'れいそせうこ')
        with mock.patch.object(corrector, '_check_replacement', side_effect=stop_kanji):
            self.assertEqual(self.correct(line, [pair])['corrected'], 'れいぞうこの中を整理して古い物を捨てた。')
        # 門に触れなければ漢字の形がそのまま通る
        for line, pair, want in (
                ('例そせうこの中を整理して古い物を捨てた。', ('例そせうこ', 'れいそせうこ'),
                 '冷蔵庫の中を整理して古い物を捨てた。'),
                ('朝は霧が出ていて視界が悪メカった。', ('悪メカっ', 'わるめかっ'),
                 '朝は霧が出ていて視界が悪かった。')):
            with self.subTest(line=line):
                self.assertEqual(self.correct(line, [pair])['corrected'], want)

    @_without_ime
    def test_kanji_placement_uses_dictionary_and_store(self):
        # かなで直った語を漢字に置く：表記が1通り（休み・正月）。表記が並んで文脈にも本人の IME にも
        # 決め手が無い2字漢語（こうえん: 公園・講演・後援）は、同梱の表の費用では絞らず（費用は使われ方を
        # 映さない）、最も身近な表記（公園: 身近さの表 everyday_faces → kango_tier の段）に決めて、迷いの印（紫）
        # を元の行の文節に残す（うに 10-18: 迷ったら何もしない はしない・迷うなら紫）
        for line, pair, want, purple in (
                ('部長がやす意味なので承認は明日になります。', ('やす意味なので', 'やすいみなので'),
                 '部長が休みなので承認は明日になります。', []),
                ('親戚が集まって賑やかなしょ上がつを過ごした。', ('しょ上がつを', 'しょうえがつを'),
                 '親戚が集まって賑やかな正月を過ごした。', []),
                ('この道をまっすぐ行くとこみ上んに出ます。', ('こみ上んに', 'こみうえんに'),
                 'この道をまっすぐ行くと公園に出ます。', [(11, 15)])):
            with self.subTest(line=line):
                result = self.correct(line, [pair])
                self.assertEqual(result['corrected'], want)
                self.assertEqual(result['odd_spans'], purple)

    @_without_ime
    def test_kanji_choices_do_not_narrow_by_seed_cost(self):
        # 同梱の表の費用で表記を絞らない（返る 134・変える 135・帰る 135）。
        # 並んだ表記は呼ぶ側が文脈と行の費用で決め、決め手が無ければ置かない
        a = self.state
        faces = LK._kanji_choices('かえる', a.store, a.dict_index)
        self.assertGreater(len(faces), 2)
        self.assertIsNone(LK._place_kanji('予定をかえることにした。', 3, 6, '替ある', 'かあえる',
                                          a.store, a.dict_index, None, []))
        self.assertEqual(LK._kanji_choices('れいぞうこ', a.store, a.dict_index), ['冷蔵庫'])
        # 読み2字の語（なつ・よる）も手を付けていない付属が付いていれば語と見るが、
        # 置くのは表記が1通り（夏）か文脈に決め手があるときだけ。同じ読みの語が多く
        # 行の費用の差は書かれた語を映さない（ちょう: 兆された を置いた）
        placed = LK._place_kanji('今年のなつは去年より暑く感じる。', 3, 6, '何つは', 'なにつは',
                                 a.store, a.dict_index, None, [])
        self.assertEqual(placed[:2], ('今年の夏は去年より暑く感じる。', '夏は'))
        self.assertIsNone(LK._place_kanji('子どもの宿題を見ていたらよるになってしまった。', 12, 15,
                                          'よ悪に', 'よわるに', a.store, a.dict_index, None, []))
        self.assertIsNone(LK._place_kanji('先生にちょうされた。', 3, 8, '帳いされた', 'ちょういされた',
                                          a.store, a.dict_index, None, []))

    def test_kanji_choices_keep_common_okurigana_and_dictionary_homographs(self):
        # 送りがな違いは漢字の並びごとに1つ残す（懐かしく・可懐しく）。漢字の多い表記に
        # まとめると珍しい表記だけが残り、行の費用で負けてかなのまま残った
        from types import SimpleNamespace
        a = self.state
        faces = LK._kanji_choices('なつかしく', a.store, a.dict_index)
        self.assertEqual(faces[0], '懐かしく')
        placed = LK._place_kanji('古い写真を整理していたらなつかしくなった。', 12, 17, '懐かしはく',
                                 'なつかしはく', a.store, a.dict_index, None, [])
        self.assertEqual(placed[:2], ('古い写真を整理していたら懐かしくなった。', '懐かしく'))
        # 本人の語彙にある読みでも、辞書の同じ読みの別の語（うえ: 上・植え）は候補に残す。
        # 費用が並んだときは本人の表記（上）
        store = SimpleNamespace(lookup=lambda w: [dict(surface='上', count=5)] if w == 'うえ' else [])
        faces = LK._kanji_choices('うえ', store, a.dict_index)
        self.assertEqual(faces[0], '上')
        self.assertIn('植え', faces)
        placed = LK._place_kanji('机のうえに本を置いた。', 2, 5, '上えに', 'うえに',
                                 store, a.dict_index, None, [])
        self.assertEqual(placed[:2], ('机の上に本を置いた。', '上に'))

    def test_retried_lines_do_not_stack_distant_or_two_key_slips(self):
        # 1打を戻した行を入口に通すあいだ、入口は離れたキーや2打の滑りを重ねない
        # （読みが変わるうえ、その探索が通し直しの時間の大半だった）
        import contextual_repair, corrector
        seen = []
        def fn(line, **kw):
            seen.append((line, contextual_repair.SLIP_REVERTED.get()))
            return dict(original=line, corrected=line, changed=False, odd_spans=[], details=[],
                        analysis_status='complete')
        wrapped = LK.with_last_keystroke_repair(fn)
        def fake_repair(line, result, retry, **kw):
            retry('もどしたぎょう')
            return None
        with patch.object(LK, 'repair', fake_repair), \
                patch.object(LK, 'repair_ime_clause', lambda *a, **k: None), \
                patch.object(corrector, 'correct_line', fn):
            wrapped('もとのぎょう', store=None)
        self.assertEqual(seen, [('もとのぎょう', False), ('もどしたぎょう', True)])
        self.assertFalse(contextual_repair.SLIP_REVERTED.get())

    def test_tie_between_rereadings_is_settled_by_context_only(self):
        # 費用の下がりも読みの並びも並んだ候補（わるいので・わするので）は、周りの語との
        # 馴染みに決め手があるときだけ採り、顔はかなを漢字に置いた形（悪い）で比べる。
        # 決め手が無ければ何も採らない（行をそのまま残す）
        a = self.state
        line = '印刷機の調子が悪すので業者に連絡しておきます。'
        s, e = 7, 11
        clauses = [(s, e, 'わるすので')]
        rows = []
        for text in ('印刷機の調子がわるいので業者に連絡しておきます。',
                     '印刷機の調子がわするので業者に連絡しておきます。'):
            rows.append((9000, s, e, text, {'corrected': text}, 6.0, False))
        seen = []

        class Ctx:
            def __init__(self, answer):
                self.answer = answer

            def pick_best_by_context(self, faces, words):
                seen.append((list(faces), list(words)))
                return self.answer
        pick = LK._tie_by_context(rows, line, e, clauses, a.store, a.dict_index,
                                  Ctx('悪いので'), ['印刷機', '調子', '業者'])
        self.assertIs(pick, rows[0])
        self.assertIn('悪いので', seen[-1][0])
        self.assertEqual(seen[-1][1], ['印刷機', '調子', '業者'])
        self.assertIsNone(LK._tie_by_context(rows, line, e, clauses, a.store, a.dict_index,
                                             Ctx(None), ['印刷機', '調子', '業者']))
        self.assertIsNone(LK._tie_by_context(rows, line, e, clauses, a.store, a.dict_index,
                                             Ctx('悪いので'), []))

    def test_stacked_reading_changes_are_not_taken(self):
        # 1打を戻した行に、入口が読みの変わる直し（した→だ）を重ねた結果
        # （にんした→にしんだ・しょうえがを→生姜を）は、2つの直しの積み重なりなので採らない。
        # かな→漢字の変換（とった→撮った）や、範囲の前の直し（にもつ→荷物）は読みが同じなので通る
        result = self.correct('資料の数字に誤りがないか二人で書くまにんした。', [('書くまにんした', 'かくまにんした')])
        self.assertNotIn('しんだ', result['corrected'])
        result = self.correct('夕焼けがきれいだったので思わず写真を都市った。', [('都市った', 'としった')])
        self.assertEqual(result['corrected'], '夕焼けがきれいだったので思わず写真を撮った。')
        self.assertTrue(LK._reading_kept('にもつがとどきました', 6, 10, '荷物が届きました'))
        self.assertFalse(LK._reading_kept('書くまにしんた。', 3, 6, '書くまにしんだ。'))
        self.assertTrue(LK._reading_kept('書くまにしんた。', 3, 6, '書くまにしんだ。',
                                         base={'details': [('た', 'だ', 'かな入力')]}))

    def test_existing_kanji_fix_is_not_replaced_by_kana(self):
        # 入口がすでに直した行（洗濯物）を、かなに戻すだけの読み直しで潰さない
        result = self.correct('雨の日はせ欄たく物が乾きにくい。', [('せ欄たく', 'せらんたく')])
        self.assertEqual(result['corrected'], '雨の日は洗濯物が乾きにくい。')

    def test_kana_results_need_dictionary_evidence(self):
        # かなのまま残す直しは、辞書に読みの在る語＋手を付けていない付属であること。
        # 語でないかなの並び（しきゅうでん）には替えない
        result = self.correct('しはゅ腕んを逃してタクシーで帰った。', [('しはゅ腕んを', 'しはゅうでんを')])
        self.assertNotIn('しきゅうでん', result['corrected'])

    def test_clause_result_is_checked_as_a_clause(self):
        # 文節の読み直しは置く範囲（文節）の単位で最終検査を受ける。差分の切れ端で
        # 受けると、切れ端が語でないために正しい直しが止まる
        result = self.correct('研修の申し込みは金曜日がしめ聞くりです。', [('しめ聞くりです', 'しめきくりです')])
        self.assertEqual(result['corrected'], '研修の申し込みは金曜日が締め切りです。')

    def test_clause_local_cost_triggers_rereading(self):
        # 長めの行では、余分な1字（保存**な**しました）が行全体の費用を上げず疑いの印も
        # 立たない。文節だけの費用（1字あたり CLAUSE_LOCAL_COST 以上）でも疑う
        result = self.correct('ファイルを保存なしました。', [('保存な', 'ほぞんな')])
        self.assertEqual(result['corrected'], 'ファイルを保存しました。')

    def test_ime_conversion_decides_among_dictionary_faces(self):
        # 同じ読みの表記が並んで文脈にも費用にも決め手が無いとき、本人の IME が打ち直しで
        # 出す顔を聞く。選ぶのは辞書で許した表記の中だけ（IME の顔が表記の外なら かなのまま）。
        # IME が無ければ最も身近な表記に決めて迷いの印を残す（雲の測定はこの道）
        import ime_language
        a = self.state

        class FakeIME:
            def __init__(self, table, available=True):
                self.table, self.available = table, available

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def convert(self, reading):
                return self.table.get(reading)
        line = 'この道をまっすぐ行くとこうえんに出ます。'
        s, e = line.index('こうえん'), line.index('こうえん') + 4
        args = (line, s, e, 'こみ上ん', 'こみうえん', a.store, a.dict_index, a.context_vec, [])
        with mock.patch.object(ime_language, 'JapaneseIME', lambda: FakeIME({'こうえん': '公園'})):
            self.assertEqual(LK._place_kanji(*args)[:2], (line.replace('こうえん', '公園'), '公園'))
        with mock.patch.object(ime_language, 'JapaneseIME', lambda: FakeIME({'こうえん': '講演'})):
            self.assertEqual(LK._place_kanji(*args)[1], '講演')
        # IME の顔が表記の外、または IME が無ければ（雲の測定はこの道）、最も身近な表記（公園）に決めて迷いの印を返す
        # （3つ目の要素 True。うに 10-18: 迷ったら何もしない はしない・迷うなら紫）
        with mock.patch.object(ime_language, 'JapaneseIME', lambda: FakeIME({'こうえん': 'コウエン'})):
            self.assertEqual(LK._place_kanji(*args), (line.replace('こうえん', '公園'), '公園', True))
        with mock.patch.object(ime_language, 'JapaneseIME', lambda: FakeIME({'こうえん': '公園'}, available=False)):
            self.assertEqual(LK._place_kanji(*args), (line.replace('こうえん', '公園'), '公園', True))
        # 付属の付いた語は付属ごと聞く（うえ＋た → 植えた）。語だけ（うえ → 上）では聞かない
        line = '庭にうえたトマトが赤く色づいてきた。'
        s, e = line.index('うえた'), line.index('うえた') + 3
        args = (line, s, e, '上うた', 'うえうた', a.store, a.dict_index, a.context_vec, [])
        with mock.patch.object(ime_language, 'JapaneseIME', lambda: FakeIME({'うえた': '植えた', 'うえ': '上'})):
            self.assertEqual(LK._place_kanji(*args)[:2], (line.replace('うえた', '植えた'), '植えた'))
        with mock.patch.object(ime_language, 'JapaneseIME', lambda: FakeIME({'うえ': '上'})):
            self.assertIsNone(LK._place_kanji(*args))

    @_without_ime
    def test_stray_kana_after_converted_word_is_removed(self):
        # 変換した語の直後に余った1打が残る形（確定の前に1つ余分に打った）。
        # 名詞＋1字のフィラー・な＋の以外の助詞・名詞＋終助詞＋の を疑いの印にし、
        # 戻した形は文節の証明で、元の行で測れない隣り合い（今日**え**: 隣が漢字）の門を通る。
        # 入口が IME と同じ漢字を置いた迷いは許す（約束の）。
        # 語の漢字と付属の間の1字なら、語は IME の漢字のまま余った字だけ抜いた形で入口に通す
        # （_ime_word_kept: かなに戻すと前後のかなと長い連なりになって入口が崩れる 保存なして）
        for line, pair, want in (
                ('写真なをクラウドに保存しておくと安心だ。', ('写真な', 'しゃしんな'), '写真を'),
                ('健康え診断の結果が届いたので確認した。', ('健康え', 'けんこうえ'), '健康診断'),
                ('子供ねの頃に遊んだ川は今も変わらず流れている。', ('子供ね', 'こどもね'), '子供の頃'),
                ('残業が続いたので今日えは早く帰る。', ('今日え', 'きょうえ'), '今日は'),
                ('電車が遅れて約束まの時間に遅刻しそうだ。', ('約束ま', 'やくそくま'), '約束の時間'),
                ('写真をクラウドに保存なしておくと安心だ。', ('保存なして', 'ほぞんなして'), '保存して'),
                ('契約書の内容を法務に確認なしてもらった。', ('確認な', 'かくにんな'), '確認して'),
                ('動く歩道に乗って移動あした。', ('移動あした', 'いどうあした'), '移動した'),
                ('趣味で始めた写真なが思ったより楽しい。', ('写真なが', 'しゃしんなが'), '写真が思った'),
                ('半分なくらい残っている。', ('半分な', 'はんぶんな'), '半分くらい'),
                ('夜更かしをすると翌日の仕事しに響く。', ('仕事しに', 'しごとしに'), '仕事に響く'),
                # 名詞＋か＋格助詞（時間**か**に）・形容詞の活用形＋接尾 さ（甘**く**さ）の印
                ('電車が遅れて約束の時間かに遅刻しそうだ。', ('時間かに', 'じかんかに'), '時間に遅刻'),
                ('このケーキは甘くさ控えめでおいしい。', ('甘く', 'あまく'), '甘さ控えめ'),
                # 動詞の基本形＋ながら は文法で確かな印: 付属の中の1打の置き換え（聞く→聞き。語幹は IME の漢字のまま）
                ('大好きな曲を聞くながら歩く。', ('聞くながら', 'きくながら'), '聞きながら'),
                # 語の読み（あけ）に辞書の漢字が複数あり IME に聞けないときは、かなに戻した形も入口に通し、
                # 入口が文の中で自ら別の漢字（窓を→開け）に変換するならそちら（IME の 明け は あけむたら の変換）
                ('窓を明けむたら涼しい風が入った。', ('明けむたら', 'あけむたら'), '開けたら'),
                # 紫の1打の直し（前おが→前えが）が名詞＋1字フィラーの印を残すなら、文節の読み直し（前が）と費用で比べる
                ('今朝は霧が濃くて前おがよく見えなかった。', ('前お', 'まえお'), '前がよく'),
                # 付属の中の1打の置き換え（寒**す**→寒い・温か**て**→温かい）: 語幹は IME の漢字のまま（_ime_stem_kept）
                ('寒す日は鍋料理が食べたくなる。', ('寒す', 'さむす'), '寒い日'),
                ('眠れない夜は温かて飲み物を飲む。', ('温かて', 'あたたかて'), '温かい飲み物'),
                # かなに戻した文節（どようび）に入口が紫を付けても、辞書の漢字に置ければ採る
                ('来週の土曜びせなら空いています。', ('土曜びせ', 'どようびせ'), '土曜日なら'),
                # 文法で確かな印（形容詞の基本形＋て）の文節では、費用の下がりが小さくても IME の語を残した形を採る
                ('新しいてスマートフォンの使い方がよく分からない。', ('新しいて', 'あたらしいて'), '新しいスマートフォン')):
            with self.subTest(line=line):
                result = self.correct(line, pairs=[pair])
                self.assertIn(want, result['corrected'])
                self.assertEqual(result['odd_spans'], [])

    @_without_ime
    def test_kept_ime_word_form_needs_dictionary_face_after_the_word(self):
        # 語＋余った字＋付属 の形だけ（保存**な**して→保存して・新しい**す**→新しい）。
        # IME の漢字が打ち違いの読みの変換なら形にしない（い**す**県→い県・**し**半分→半分）
        a = self.state
        for face, reading, want in (('保存なして', 'ほぞんして', '保存して'),
                                    ('移動あした', 'いどうした', '移動した'),
                                    ('今日えは', 'きょうは', '今日は'),
                                    ('新しいす', 'あたらしい', '新しい'),
                                    ('いす県が', 'いけんが', None),
                                    ('し半分', 'はんぶん', None),
                                    ('確認', 'かくに', None)):
            with self.subTest(face=face):
                self.assertEqual(LK._ime_word_kept(face, reading, a.store, a.dict_index), want)

    @_without_ime
    def test_kept_ime_stem_with_a_retyped_tail(self):
        # 語幹の漢字＋付属 の顔で、付属の中だけ1打戻る形（寒**す**→寒い・温か**て**→温かい）。
        # 語幹の読みが変わる形（寒たい→さけたい）や、辞書の表記にならない形（良いて→良てい）は無し
        a = self.state
        for face, reading, new_reading, want in (('寒す', 'さむす', 'さむい', '寒い'),
                                                 ('温かて', 'あたたかて', 'あたたかい', '温かい'),
                                                 ('寒たい', 'さむたい', 'さけたい', None),
                                                 ('良いて', 'よいて', 'よてい', None),
                                                 ('寒す', 'さむす', 'さむ', None)):
            with self.subTest(face=face):
                self.assertEqual(LK._ime_stem_kept(face, reading, new_reading, a.store, a.dict_index), want)

    def test_kept_ime_word_defers_to_the_ime_conversion_of_the_clean_reading(self):
        # 余った字を抜いた読みを本人の IME が別の語にするなら、IME の元の漢字を残さずそちら
        # （機器**く**ながら: きき は 機器 だったが、ききながら なら 聞きながら）。
        # IME の顔が辞書の表記の外（カタカナ）なら、または IME が無ければ、IME の漢字のまま
        import ime_language
        a = self.state

        class FakeIME:
            def __init__(self, table, available=True):
                self.table, self.available = table, available

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def convert(self, reading):
                return self.table.get(reading)
        args = ('機器くながら', 'ききながら', a.store, a.dict_index)
        with mock.patch.object(ime_language, 'JapaneseIME', lambda: FakeIME({'ききながら': '聞きながら'})):
            self.assertEqual(LK._ime_word_kept(*args), '聞きながら')
        with mock.patch.object(ime_language, 'JapaneseIME', lambda: FakeIME({'ききながら': 'キキながら'})):
            self.assertEqual(LK._ime_word_kept(*args), '機器ながら')
        with mock.patch.object(ime_language, 'JapaneseIME', lambda: FakeIME({}, available=False)):
            self.assertEqual(LK._ime_word_kept(*args), '機器ながら')

    @_without_ime
    def test_one_key_fix_that_leaves_a_suspect_mark_is_compared_with_the_clause_reading(self):
        # 紫の1打の直し（repair）の直した所の前後に疑いの印が残る形（前**え**が: 名詞＋1字フィラー）は、
        # IME の文節の読み直しも試す印。印の残らない直し（前が）は試さない
        line = '今朝は霧が濃くて前えがよく見えなかった。'
        self.assertTrue(LK._suspect_left((line, {'corrected': line}, (8, 9, 'え'))))
        clean = '今朝は霧が濃くて前がよく見えなかった。'
        self.assertFalse(LK._suspect_left((clean, {'corrected': clean}, (8, 8, ''))))
        # 直した所から離れた印は数えない（行の頭の1字かな自立語は直しと無関係）
        far = 'えは今朝は霧が濃くて前がよく見えなかった。'
        self.assertFalse(LK._suspect_left((far, {'corrected': far}, (10, 10, ''))))

    @_without_ime
    def test_purple_on_reverted_kana_needs_a_dictionary_kanji(self):
        # かなに戻した文節に入口が紫を付けた形は、辞書の漢字に置けなければ採らない（かなのままも置かない）。
        # てちょう は 手帳 に1通りで置けないので、行はそのまま
        line = '来月の予定をて帳あに書き込んだ。'
        result = self.correct(line, pairs=[('て帳あ', 'てちょうあ')])
        self.assertEqual(result['corrected'], line)
        # 置けても、戻した読みの並び（yomigram）が打った読みより十分に良くなければ採らない
        # （そえじ→添え乳 のような辞書の珍しい語を紫のかなに置かない）
        line = 'そ上じをしていたら昔の手帳が出てきた。'
        result = self.correct(line, pairs=[('そ上じ', 'そうえじ')])
        self.assertNotIn('添え乳', result['corrected'])
        # 文法で確かな印の文節でも、かなに戻して辞書の漢字に置いた形（始めた）の方が IME の語を残した形
        # （初めた）よりずっと安いなら、IME の漢字そのものが疑わしいので費用の線は外さない（雲では行はそのまま）
        line = '趣味で初めるた写真が思ったより楽しい。'
        result = self.correct(line, pairs=[('初めるた', 'はじめるた')])
        self.assertNotIn('初めた', result['corrected'])
        # 紫の付いたかなに置いた形（ぶんちゅう→文中に）が、入口が自ら変換した形（ぶんしゅう→文集に）と
        # 費用で並んだら退く（紫は入口がその並びを語と認めなかった印。決め手なしで行を残さない）
        line = '卒業文とゅうに将来の夢を書いた。'
        result = self.correct(line, pairs=[('文とゅうに', 'ぶんとゅうに')])
        self.assertEqual(result['corrected'], '卒業文集に将来の夢を書いた。')

    @_without_ime
    def test_adnominal_in_clause_is_not_an_extra_key(self):
        # 名詞の直後の連体詞（昨日**あの**店・先生**あの**件）は余った字と見ない
        # （連体詞は独立した語で、名詞の直後に来るのもふつう）。研修あの申し込み も直さない
        for line, pair in (('昨日あの店に行った。', ('昨日あの', 'きのうあの')),
                           ('先生あの件ですが。', ('先生あの', 'せんせいあの')),
                           ('研修あの申し込みは金曜日が締め切りです。', ('研修あの', 'けんしゅうあの'))):
            with self.subTest(line=line):
                self.assertEqual(self.correct(line, pairs=[pair])['corrected'], line)

    def test_conjugation_mismatch_is_a_suspect_mark(self):
        # 活用の形が合わない続きは印: 形容詞の基本形＋て（新しい**て**靴）、形容詞の語幹＋助詞（楽し**は**そう）、
        # 動詞の基本形＋た（初める**た**）、形容動詞の語幹＋て（温か**て**）。正しい活用の続きには付けない
        for line, want in (('新しいて靴を買った。', {0, 1}), ('雨で良いてが流れた。', {2, 3}),
                           ('趣味で初めるた写真。', {2, 3}), ('隣から楽しはそうな声。', {2, 3}),
                           ('夜は温かて飲み物を飲む。', {2, 3}),
                           # 動詞の基本形＋連用形に付く助詞（聞く**ながら**・歩く**つつ**・読む**たり**・行く**て**）
                           ('曲を聞くながら歩く。', {2, 3}), ('歩くつつ考える。', {0, 1}),
                           ('本を読むたり映画を見たり。', {2, 3}), ('行くて帰る。', {0, 1}),
                           # 形容詞の語幹でない形＋接尾の さ（甘**く**さ・楽し**い**さ。さ が付くのは語幹: 甘さ）
                           ('甘くさ控えめでおいしい。', {0, 1}), ('楽しいさを知る。', {0, 1})):
            with self.subTest(line=line):
                toks = list(M.tokenize(line))
                spots = LK._suspect_tokens(toks)
                self.assertTrue(want <= spots, (spots, [(x.surface, x.pos, x.infl_form) for x in toks]))
        for line in ('新しくて軽い靴。', '良くて助かる。', '趣味で始めた写真。', '楽しそうな声がする。',
                     '嬉しさが増す。', '嬉しがる子。', '行くべきだ。', '来るだろう。', '食べるな。',
                     '見るに耐えない。', '高いので買わない。', '静かで広い。', '元気って言った。',
                     '曲を聴きながら歩く。', '歩きつつ考える。', '見たり聞いたり。', '食べて寝る。',
                     '聞くと分かる。', '聞くのが好き。', '行くと言った。', '甘さ控えめ。', '嬉しさと楽しさ。',
                     '高みを目指す。'):
            with self.subTest(line=line):
                toks = list(M.tokenize(line))
                self.assertEqual(LK._suspect_tokens(toks), set(), [(x.surface, x.pos, x.infl_form) for x in toks])

    def test_stray_kana_marks_leave_ordinary_sequences_alone(self):
        # な＋の・だけ・ので・のに、形容詞＋ね＋の、同じ字の重なり は印にしない
        for line in ('静かなので助かる。', '大切なのは続けることだ。', '好きなだけ食べて。',
                     'きれいなのに安い。', 'いいねの数が増えた。', '便利なものを買った。'):
            with self.subTest(line=line):
                toks = list(M.tokenize(line))
                self.assertEqual(LK._suspect_tokens(toks), set(), line)
        toks = list(M.tokenize('写真なをクラウドに保存しておくと安心だ。'))
        spots = LK._suspect_tokens(toks)
        self.assertTrue({0, 1} <= spots, spots)
        # 代名詞でない名詞＋か＋格助詞（時間**か**に）は印。何かが・誰かに・どこかで（代名詞）、本かノートを（並立）は印にしない
        toks = list(M.tokenize('約束の時間かに遅刻した。'))
        self.assertTrue({2, 3} <= LK._suspect_tokens(toks), [(x.surface, x.pos) for x in toks])
        for line in ('何かが落ちた。', '誰かに頼む。', 'どこかで会った。', '本かノートを買う。'):
            with self.subTest(line=line):
                toks = list(M.tokenize(line))
                self.assertEqual(LK._suspect_tokens(toks), set(), line)

    def test_literary_forms_particle_runs_and_fillers_are_suspect_marks(self):
        # 文語の活用形（濃**し**と・深**し**は: 今の文には出ない）、体言接続に直に付いた助詞（良き**が**: 後ろは名詞）、
        # 形容詞の連用形に直に付いた ない 以外の助動詞（良く**まじ**）、は・が・を に続く が・を・は・も（深しは**を**）、
        # 文節の中の1字のかなのフィラー（運ど**え**かいで: 名詞の直後でなくても）は印。
        # 正しい形（若き日・命をも・良くない・良くなる・今この瞬間・今日この頃）には付けない
        for line, want in (('濃しとの夏は暑い。', {0}), ('夜深しはをすると眠い。', {1, 2, 3}),
                           ('良きが降った。', {0, 1}), ('良くまじつの仕事。', {0, 1}),
                           ('運どえかいで走った。', {1, 2})):
            with self.subTest(line=line):
                toks = list(M.tokenize(line))
                spots = LK._suspect_tokens(toks)
                self.assertTrue(want <= spots, (spots, [(x.surface, x.pos, x.infl_form) for x in toks]))
        for line in ('若き日の思い出を語る。', '命をも惜しまない覚悟だ。', '良くない結果だった。', '良くなる見込みだ。',
                     '今この瞬間を大事に思う。', '今日この頃は寒い日が続く。', '健康のために歩く。'):
            with self.subTest(line=line):
                toks = list(M.tokenize(line))
                self.assertEqual(LK._suspect_tokens(toks), set(), [(x.surface, x.pos, x.infl_form) for x in toks])

    @_without_ime
    def test_placed_familiar_word_is_not_stopped_by_the_weight_of_the_rest_of_the_line(self):
        # かなに戻した文節を辞書の漢字に置いた形（翌日の・大切だ・挑戦した）は、戻した読みが打った読みより十分に
        # 通りのよい並び（CLAUSE_KANA_YOMI 以上）で、置いた語がふつうの語（漢語の層1）なら、行の残り
        # （夜更かし・響く）の字あたりの費用では止めない（費用の絶対値は正しい語でも線を超える）。
        # 珍しい語（如何・定見: 層2・3）は読みの並びが良くても置かない（しいか・いてけん は元のまま）
        for line, pair, want in (
                ('夜更かしをすると良くまじつの仕事に響く。', ('良くまじつの', 'よくまじつの'), '翌日の仕事'),
                ('人の話を最後まで聞くのは縦せつだ。', ('縦せつだ', 'たてせつだ'), '大切だ'),
                ('料理の本を見ながら新しいおかずに帳せかした。', ('帳せか', 'ちょうせか'), '挑戦した')):
            with self.subTest(line=line):
                result = self.correct(line, [pair])
                self.assertIn(want, result['corrected'])
                self.assertEqual(result['odd_spans'], [])
        for line, pair in (('朝は霧が出ていてし医科が悪かった。', ('し医科が', 'しいかが')),):
            with self.subTest(line=line):
                self.assertEqual(self.correct(line, [pair])['corrected'], line)
        # いて県には: 定見（層2）には置かず、入口が自ら漢字にした 意見 を迷いの印（紫）付きで採る（うに 10-18: 迷うなら紫）
        result = self.correct('彼のいて県にはおおむね賛成だ。', [('いて県には', 'いてけんには')])
        self.assertEqual(result['corrected'], '彼の意見にはおおむね賛成だ。')
        self.assertEqual(result['odd_spans'], [(2, 5)])
        self.assertTrue(LK._familiar_kango('翌日の'))
        self.assertFalse(LK._familiar_kango('如何'))
        self.assertFalse(LK._familiar_kango('よくじつ'))

    @_without_ime
    def test_katakana_compound_unknown_to_the_world_is_rewritten_to_the_known_one(self):
        # 確定の前の余分な1字を IME が隣の片仮名の語に巻き込んだ形（新しい**す**ぱんや→新しいスパン屋）。
        # 費用も読みの並びも スパン屋 を良いと見るので、「そういう組み立ての語が世の中に在るか」（辞書の
        # 読みの表: すぱんや 無し・ぱんや 在り）だけで決める。表に無い組み立て（らーめんや）や、接尾の
        # 付かない片仮名の語（パンダを）は触らない（本人の語彙は決め手にしない: パンダを→パンを）
        a = self.state
        line = '駅前の新しいスパン屋に行ってみたい。'
        for pair in (('スパン屋に', 'すぱんやに'), ('新しいスパン屋に', 'あたらしいすぱんやに')):
            with self.subTest(pair=pair):
                result = self.correct(line, [pair])
                self.assertEqual(result['corrected'], '駅前の新しいパン屋に行ってみたい。')
                self.assertEqual(result['odd_spans'], [])
        toks = list(M.tokenize(line))
        self.assertEqual({toks[i].surface: rows for i, rows in LK._foreign_swaps(toks, a.dict_index).items()},
                         {'スパン': [('ぱん', 'パン')]})
        a.store.add('ぱん', 'パン', 'その他')
        self.addCleanup(a.store.remove, 'ぱん', 'パン')
        for line, pair in (('駅前のラーメン屋に行った。', ('ラーメン屋に', 'らーめんやに')),
                           ('動物園でパンダを見た。', ('パンダを', 'ぱんだを'))):
            with self.subTest(line=line):
                self.assertEqual(self.correct(line, [pair])['corrected'], line)
                self.assertEqual(LK._foreign_swaps(list(M.tokenize(line)), a.dict_index), {})

    @_without_ime
    def test_mismatched_noun_particle_clause_is_reread_to_the_persons_verb(self):
        # 閑雅＋て（名詞＋接続助詞: 続きが合わない文節）。かんが**え**て→考えて。行の残り（どうしたらいいか）の
        # 字あたりの費用は正しい文でも線を超えるので、置いた形が珍しい漢語でなければ行の重さでは止めない。
        # 語と付属を両方捨てる戻し（かんが**い**→潅漑: 層3）は見ない。辞書の費用は 鑑みて の方が安いので、
        # 並んだら本人の使った語（考え）を採り、使った語が無ければ変えない
        a = self.state
        line = 'どうしたらいいか閑雅て'
        for pair in (('閑雅て', 'かんがて'), ('閑雅', 'かんが')):
            with self.subTest(pair=pair, seeded=False):
                # 考え を使ったことが無ければ、鑑みて（辞書の費用はこちらが安い）にも 潅漑 にも置かない
                # （並んで文脈に決め手があれば 考えて、無ければそのまま）
                got = self.correct(line, [pair])['corrected']
                self.assertIn(got, (line, 'どうしたらいいか考えて'))
        a.store.add('かんがえ', '考え', 'その他')
        self.addCleanup(a.store.remove, 'かんがえ', '考え')
        for pair in (('閑雅て', 'かんがて'), ('閑雅', 'かんが')):
            with self.subTest(pair=pair, seeded=True):
                result = self.correct(line, [pair])
                self.assertEqual(result['corrected'], 'どうしたらいいか考えて')
                self.assertEqual(result['odd_spans'], [])
        self.assertTrue(LK._rare_kango('潅漑'))
        self.assertFalse(LK._rare_kango('考えて'))
        self.assertFalse(LK._rare_kango('駅前の'))

    @_without_ime
    def test_long_compound_is_assembled_from_dictionary_parts_and_joined_clauses(self):
        # 索引に表記の無い長い語（修学旅行: 費用で索引から落ちた）は、辞書の語の組み立て（修学＋旅行）から置く。
        # 巻き込んだ1打（と）が IME の切れ目を作る形（詩と｜ゅうがく旅行の）は、隣り合う文節をつないだ読みでも読み直す
        # （うにの実打ち 2026-10-18: しとゅうがくりょこう → IME 詩とゅうがく旅行 → 詩と修学旅行 と直していた。詩と が余分）
        line = 'しとゅうガク旅行の班を決めるのに時間がかかった。'
        want = '修学旅行の班を決めるのに時間がかかった。'
        self.assertEqual(self.correct(line, [('しとゅうガク旅行の', 'しとゅうがくりょこうの')])['corrected'], want)
        line = '詩とゅうがく旅行の班を決めるのに時間がかかった。'
        for pairs in ([('詩と', 'しと'), ('ゅうがく旅行の', 'ゅうがくりょこうの')],
                      [('詩', 'し'), ('とゅうがく旅行の', 'とゅうがくりょこうの')]):
            with self.subTest(pairs=pairs):
                result = self.correct(line, pairs)
                self.assertEqual(result['corrected'], want)
                self.assertEqual(result['odd_spans'], [])
        a = self.state
        self.assertEqual(LK._compound_faces('しゅうがくりょこう', a.store, a.dict_index)[:1], ['修学旅行'])

    @_without_ime
    def test_entrance_convertible_clauses_are_ranked_by_the_cheapest_face(self):
        # 置く表記に決め手が無い語（玄関/厳寒・掃除/相似・手帳/手帖・駅）でも、費用の見込みは並ぶ表記の中で最も安い形で
        # 測る（見込みが悪いと正しい戻しが試行の枠に入らず、入口は自ら漢字にできるのに読み直せなかった）
        for line, pair, want, purple in (
                ('写真をクラウドに保存しておくと穴しんだ。', ('穴しんだ', 'あなしんだ'), '写真をクラウドに保存しておくと安心だ。', []),
                ('昼休みに夕ぞん局へ行って書類を送った。', ('夕ぞん', 'ゆうぞん'), '昼休みに郵便局へ行って書類を送った。', []),
                ('そ上じをしていたら昔の手帳が出てきた。', ('そ上じを', 'そうえじを'), '掃除をしていたら昔の手帳が出てきた。', []),
                ('掃除をしていたら昔のてた帳が出てきた。', ('てた帳が', 'てたちょうが'), '掃除をしていたら昔の手帳が出てきた。', []),
                ('え聞くの改札口で待ち合わせしましょう。', ('え聞くの', 'えきくの'), '駅の改札口で待ち合わせしましょう。', []),
                ('電気代のせい今日が先月より高かった。', ('せい今日が', 'せいきょうが'), '電気代の請求が先月より高かった。', []),
                # 入口が自ら漢字にしたが迷いを残した形（玄関）は、疑いの印のある文節なら採る。身近さの表で 玄関 が
                # 抜けている（玄関 ≫ 厳寒）ので迷いの印（紫）は付かない
                ('荷物は外科かんの前に置いておきます。', ('外科かんの', 'げかかんの'), '荷物は玄関の前に置いておきます。', [])):
            with self.subTest(line=line):
                result = self.correct(line, [pair])
                self.assertEqual(result['corrected'], want)
                self.assertEqual(result['odd_spans'], purple)
        # 身近さの表が無ければ（玄関/厳寒 に決め手が無い）: 疑いの印の無い文節（外科かんの は印が付かない）では、表記が
        # 並んで決め手の無い弱い置き方はせず、入口が迷いを残して変換した形も採らない（異様の判定が先。正しい 今日中に を
        # きょうちょうに→強調に に替えないため）。印の無い文節の弱い置き方は、かなの形がそれだけで通るときだけ（公園）
        with mock.patch.object(LK, '_everyday_order', lambda reading: ((), False)):
            result = self.correct('荷物は外科かんの前に置いておきます。', [('外科かんの', 'げかかんの')])
            self.assertEqual(result['corrected'], '荷物は外科かんの前に置いておきます。')
            self.assertEqual(result['odd_spans'], [])

    def test_rare_word_clause_with_a_kana_fragment_is_reread_to_the_everyday_word(self):
        # IME が明示的に稀と判定された語（稀代）を出し、その前にかなの切れ端（でんな）が残る形は異様。切れ端をつないだ
        # 読み（でんなきだいの）で読み直し、同梱の表にしか無い語（電気代）を置く。稀な語の印だけの文節なので迷いの印（紫）
        # を残す（うに 2026-10-18 実打ち: でんなきだいのせいきゅうが → IME でんな稀代の請求が。迷うなら紫）
        a = self.state
        self.assertTrue(LK._restricted_face('稀代'))
        line = 'でんな稀代の請求が先月より高かった。'
        with mock.patch.object(LK, '_ime_face', lambda *x, **k: None):
            for pairs in ([('稀代の', 'きだいの'), ('請求が', 'せいきゅうが')], [('でんな稀代の', 'でんなきだいの')]):
                with self.subTest(pairs=pairs):
                    result = self.correct(line, pairs)
                    self.assertEqual(result['corrected'], '電気代の請求が先月より高かった。')
                    self.assertEqual(result['odd_spans'], [(0, 4)])
            # 稀な語の印も語でない切れ端も無い文節（でん鳴き: 副詞＋名詞の形）は、費用が高くても読み直さない（2026-10-18:
            # 正しい複合語 文字列と・タブ移動時に を本人の語彙で軽くなる別の語に替えないため。この直しは失う）
            result = self.correct('でん鳴き代の請求が先月より高かった。', [('でん鳴き', 'でんなき')])
            self.assertEqual(result['corrected'], 'でん鳴き代の請求が先月より高かった。')
        # 本人の IME が 電気 と変換するなら迷いは無い（同じ読みの表記の費用の差 電気代 17001・電機代 15618 は根拠にしない）。
        # 切れ端（1字のかなの感動詞 う）の在る文節で
        with mock.patch.object(LK, '_ime_face', lambda word, rest, faces: '電気' if '電気' in faces else None):
            result = self.correct('でんき代うの請求が先月より高かった。', [('でんき代う', 'でんきだいう')])
            self.assertEqual(result['corrected'], '電気代の請求が先月より高かった。')
            self.assertEqual(result['odd_spans'], [])
        # 同梱の表の語は引いた分だけ覚える（_SEED_CACHE）: 覚える前は辞書の語の切り方だけ（でんきだい は索引に無い）
        LK._SEED_CACHE.pop('でんきだい', None)
        self.assertEqual(LK._kana_word_split('でんきだいの', 'でんな稀代の', 'でんなきだいの', a.dict_index), None)
        LK._seed_prefetch(['でんきだい'])
        self.assertEqual(LK._kana_word_split('でんきだいの', 'でんな稀代の', 'でんなきだいの', a.dict_index), ('でんきだい', 'の'))

    def test_everyday_table_is_in_the_bundle_manifest(self):
        # 身近さの表は同梱の名簿（bundle_manifest）に在る（EXE に入らないと、表記が並んだときの決め手が段だけに戻る）
        import os
        with open(os.path.join(os.path.dirname(__file__), 'bundle_manifest.py'), encoding='utf-8') as fh:
            bm = fh.read()
        self.assertIn("Item('everyday_faces.json', 'everyday_faces'", bm)
        self.assertTrue(os.path.exists(os.path.join(os.path.dirname(__file__), 'everyday_faces.json')))

    def test_most_familiar_face_comes_from_the_everyday_table(self):
        # 身近さの表（everyday_faces・AI 判定）: 読み → 身近な順の表記、先頭に ! が付けば抜けている（電気 ≫ 伝記・電機）。
        # 表に無い読みで用言の表記が並ぶとき（返る・変える・帰る）は身近さでは決めない（かなのまま）
        import everyday_faces
        self.assertEqual(everyday_faces.order('でんき'), (('電気', '伝記', '電機'), True))
        self.assertEqual(everyday_faces.order('こうえん')[1], False)
        self.assertEqual(everyday_faces.order('こうえん')[0][0], '公園')
        self.assertEqual(everyday_faces.order('ぱんや'), ((), False))
        self.assertTrue(everyday_faces.available())
        self.assertEqual(LK._most_familiar('でんき', ['伝記', '電機', '電気']), ('電気', True))
        self.assertEqual(LK._most_familiar('こうえん', ['講演', '公園']), ('公園', False))
        self.assertEqual(LK._most_familiar('かえる', ['返る', '変える', '帰る']), (None, False))

    @_without_ime
    def test_the_persons_established_word_is_not_replaced_by_her_other_word_with_a_long_vowel(self):
        # 入口の 48-KU（語幹の長音の脱字を戻す）は、書かれている語幹が本人の立っている語（補正・候補）なら働かない
        # （うに 2026-10-18 実機: 正しい補正分と → 正しい方正分と・候補づくり → 後方づくり。本人の語彙に ほうせい=方正・
        # こうほう=後方 が立っていた）。立っていない語幹は従来どおり（tests_mock_words の 48-KU）
        a = self.state
        for r, f in (('ほせい', '補正'), ('ほうせい', '方正'), ('こうほ', '候補'), ('こうほう', '後方')):
            a.store.add(r, f, 'その他')
            a.store.add(r, f, 'その他')
            self.addCleanup(a.store.remove, r, f)
        for line in ('正しい補正分と', '候補づくり（candidates.py）は補正エンジンから'):
            with self.subTest(line=line):
                self.assertEqual(self.correct(line)['corrected'], line)

    def test_predicate_suru_forms_are_words_and_literary_auxiliaries_are_marks(self):
        # する の活用形が述語の形（追加**し**ました・補正**さ**れない・確認**せ**ず・登録**し**て）は語で印にしない
        # （印にすると、本人の語彙で軽くなる別の語に替わった: うに 2026-10-18 実機 追加しました→活かしました）。
        # 格助詞が直に続く し（仕事**し**に響く）、文語の す（悪**す**ので）・つ（**つ**枠）・き（夕**し**どんの）、
        # 形容詞の基本形に直に付いた を（て良い**を**）は印
        for line in ('単語帳を追加しました。', 'それでは補正されない場合がある。', '内容を確認せず進めた。', '単語を登録して使う。'):
            with self.subTest(line=line):
                toks = list(M.tokenize(line))
                self.assertEqual(LK._suspect_tokens(toks), set(), [(x.surface, x.pos, x.base_form) for x in toks])
        for line, want in (('翌日の仕事しに響く。', 'し'), ('調子が悪すので連絡する。', 'す'), ('風がつ枠なった。', 'つ'),
                           ('夕しどんの結婚式に出る。', 'し'), ('来週のて良いを教えてください。', '良い')):
            with self.subTest(line=line):
                toks = list(M.tokenize(line))
                self.assertIn(want, [toks[i].surface for i in LK._suspect_tokens(toks)],
                              [(x.surface, x.pos, x.base_form) for x in toks])

    def test_unmarked_clause_is_reread_only_where_a_fragment_remains(self):
        # 印の無い文節は、費用が高くても、語でない切れ端（かなの名詞・本人の使っていない短い片仮名・世の中に無い1字漢字の組・
        # 付く先の無い付属語…）が在るときだけ読み直す（_clause_fragments）。1語に収まる文節（の判定を・に戻る・を追加しました）、
        # 正しい複合語（文字列と・文字列一致は）、助詞を挟んで立つかなの名詞（ひとつの行に）、お＋名詞、1字漢字の名詞（人・母子）
        # には切れ端が無い（うに 2026-10-18 実機: の判定を→反対を・文字列と→捩れと・の行に→今日に・タブ移動時に→舞台同時に）
        from vocabulary import VocabularyStore
        a = self.state
        for line, clause in (('設定の判定を強化する。', 'の判定を'), ('文字列と数値を比べる。', '文字列と'),
                             ('文字列一致は特に見ない。', '文字列一致は'), ('元の位置に戻るボタンを足す。', 'に戻る'),
                             ('単語帳を追加しました。', 'を追加しました'), ('それでは補正されない場合がある。', '補正されない'),
                             ('ひとつの行に長い文を入れる。', 'ひとつの行に'), ('お弁当を持って出かける。', 'お弁当を'),
                             ('人の話を最後まで聞く。', '人の話を'), ('母子の健康を守る。', '母子の')):
            with self.subTest(clause=clause):
                toks = list(M.tokenize(line))
                s = line.index(clause)
                self.assertEqual(LK._clause_fragments(toks, s, s + len(clause), a.store), set(),
                                 [(x.surface, x.pos, x.pos_sub) for x in toks])
        for line, clause, want in (('しゃ歯科を撮ってもらった。', 'しゃ歯科を', 'しゃ'), ('うき前の本屋で買った。', 'うき前の', 'うき'),
                                   ('沖前の新しいパン屋に行く。', '沖前の', '沖'), ('県こえ診断の結果を見る。', '県こえ診断の', 'こえ'),
                                   ('ファイルを保存なしました。', '保存なしました', 'なし'), ('や意味の日は本を読む。', 'や意味の日は', 'や'),
                                   ('薬のを飲み忘れた。', '薬のを', 'の'), ('作業あの途中でも保存できる。', '作業あの', 'あの'),
                                   ('幸せらな気分になった。', '幸せらな', 'ら'), ('県なこうのために歩く。', '県なこうの', 'な'),
                                   ('旅行に行くけて書くを立てる。', 'けて書くを', 'け'), ('電気代のせい今日が高かった。', 'のせい今日が', 'せい'),
                                   ('お祭りでや基礎サバを売る。', 'や基礎サバを', 'サバ'), ('終電をノリ餓死てタクシーで帰った。', 'ノリ餓死て', 'ノリ')):
            with self.subTest(clause=clause):
                toks = list(M.tokenize(line))
                s = line.index(clause)
                frags = LK._clause_fragments(toks, s, s + len(clause), a.store)
                self.assertIn(want, [toks[i].surface for i in frags], [(x.surface, x.pos, x.pos_sub) for x in toks])
        # 本人の使った短い片仮名（タブ）は語: 語彙に無ければ切れ端、在れば切れ端でない
        line, clause = 'タブ移動時に表示が消える。', 'タブ移動時に'
        toks = list(M.tokenize(line))
        s = line.index(clause)
        empty = VocabularyStore()
        self.assertIn('タブ', [toks[i].surface for i in LK._clause_fragments(toks, s, s + len(clause), empty)])
        empty.add('たぶ', 'タブ', 'IT・PC操作')
        self.assertEqual(LK._clause_fragments(toks, s, s + len(clause), empty), set())

    @_without_ime
    def test_one_key_fix_inside_an_ime_clause_also_tries_the_clause_reread(self):
        # 1打の直し（夕し**どん**の→夕し**んど**の）が IME の文節の中に掛かるときは、直した所に疑いの印が残らなくても
        # （し は述語の形で印でない）文節の読み直し（友人の）も試し、費用で比べる
        line = '夕しどんの結婚式に招待されて服を新調した。'
        self.assertTrue(LK._fix_in_ime_clause(line, ('夕しんどの結婚式に招待されて服を新調した。', {}, (2, 4, 'んど')),
                                              self.state.dict_index) or True)
        result = self.correct(line, [('夕しどんの', 'ゆうしどんの')])
        self.assertEqual(result['corrected'], '友人の結婚式に招待されて服を新調した。')
        self.assertTrue(LK._fix_in_ime_clause(line, ('夕しんどの結婚式に招待されて服を新調した。', {}, (2, 4, 'んど')),
                                              self.state.dict_index))


if __name__ == '__main__':
    unittest.main()
