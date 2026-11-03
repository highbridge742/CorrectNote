# -*- coding: utf-8 -*-
"""手分け C（2026-11-01）: ゛ の前の字との並べ違い・疑問の文の終わりの か・名詞＋名詞の表記の迷い・
形式名詞＋名詞＋用言・か の無い疑問の言い切り。作った文だけ。"""
import unittest
from tests_analysis_async import initial
import correction_entry as CE
import question_ka as Q
import formal_noun_gap as F
import made_word_check as M


class SplitCTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.st = initial()

    def run_line(self, line, input_method='kana'):
        st = self.st
        return CE.correct_line(line, st.store, context_vocab={}, input_method=input_method, dict_index=st.dict_index,
                               decisions=st.decisions, context_vec=st.context_vec)

    def test_mark_swapped_with_previous_kana(self):
        # し・へ・ら・゛・る と打った（ら を へ と ゛ の間に打った）。前の段が ゛ の後ろだけを直しても、前の字まで広げて戻す
        self.assertEqual(self.run_line('辞書でしへら゛る')['corrected'], '辞書で調べる')
        self.assertIn('調べて', self.run_line('言葉をしへら゛手から書く')['corrected'])

    def test_question_ka_suffix(self):
        self.assertEqual(self.run_line('どこが原因化？')['corrected'], 'どこが原因か？')
        self.assertEqual(Q.propose('温暖化が進む'), [])
        self.assertEqual(Q.propose('いつ実用化'), [])
        self.assertEqual(Q.propose('何を自動化するか'), [])
        # 1行にタブで左右の欄が並ぶ行も、タブを文の切れ目として見る（右の欄の か を左の文のものと見ない）
        self.assertEqual(Q.propose('どこが原因化\t\tどこが原因か'), [(5, 6, 'か')])
        self.assertEqual(Q.unanswered_question_spans('どこにいます\tどこにいますか'), [(0, 6)])

    def test_unanswered_question_purple(self):
        self.assertTrue(Q.unanswered_question_spans('どこにいます'))
        for ok in ['どこにいますか', '何でもできます', 'いつも行きます', 'どう見ても無理です', 'どこにいるか分かります',
                   '何回も行きます', 'いつ来ますか？']:
            self.assertEqual(Q.unanswered_question_spans(ok), [], ok)

    def test_formal_noun_gap(self):
        self.assertTrue(F.spans('話すこと本あります'))
        for ok in ['することがあります', 'やること一覧', 'やること一覧を見る', 'することリストを作る', '見るもの全てが良い',
                   'できる限り努力いたします', '言われたとおり作業します', '念のため確認します']:
            self.assertEqual(F.spans(ok), [], ok)

    def test_undecided_suffix_noun_purple_not_respelled(self):
        # 名詞＋1字の名詞（けん: 券・権・件・県）で表記が決まらない所は紫。打ち違いの戻しで別の語にしない
        r = self.run_line('がくせいけんがある')
        self.assertEqual(r['corrected'], 'がくせいけんがある')
        self.assertTrue(r.get('odd_spans'))

    def test_made_word_check(self):
        # 前の段が読みを1打替えて 知る・気付くの動きの名詞＋での にした直しは採らず、元のかなに紫
        res = {'original': 'よしでのはなし', 'corrected': '予知でのはなし', 'changed': True,
               'details': [['よし', '予知', 'かな入力']], 'odd_spans': []}
        got = M.repair_line('よしでのはなし', res)
        self.assertEqual(got['corrected'], 'よしでのはなし')
        self.assertEqual(got['odd_spans'], [(0, 2)])
        # 読みを変えずに漢字にしただけ（よち → 予知）は見ない・計算や審査の名詞＋での は見ない
        res2 = {'original': 'よちでのはなし', 'corrected': '予知でのはなし', 'changed': True, 'odd_spans': []}
        self.assertIs(M.repair_line('よちでのはなし', res2), res2)
        self.assertEqual(M._bad_spans('計算での誤り'), [])
        # 1字足すと本人の語（単語帳）の読みになり、表記が1つに決まればそれに直す（脱字に届く）
        import vocabulary
        own = vocabulary.VocabularyStore.__new__(vocabulary.VocabularyStore)
        own.__dict__.update(self.st.store.__dict__)

        class Own:
            def lookup(_s, reading):
                return [{'surface': '吉野', 'count': 2}] if reading == 'よしの' else []
        got3 = M.repair_line('よしでのはなし', dict(res), (), Own(), self.st.dict_index)
        self.assertEqual(got3['corrected'], '吉野でのはなし')
        self.assertFalse(got3.get('odd_spans'))
        self.assertEqual(M._bad_spans('審査での指摘'), [])

    def test_typed_record_of_garbled_clause_keeps_surface_reading(self):
        # 記号まじりの1文節の打った読みの記録が別の打鍵の読み（作った記録）でも、表記から読み直した読みも試す
        import kanji_guess
        import odd_respell as O
        st = self.st
        run = lambda t: CE._correct_line_halfwidth(t, st.store, context_vocab={}, decisions=st.decisions,
                                                   input_method='kana', context_vec=st.context_vec,
                                                   dict_index=st.dict_index)
        old = kanji_guess._IME_READINGS_PROVIDER
        kanji_guess._IME_READINGS_PROVIDER = lambda x: {'デ゜ン和番号': ['てなる゛゜んわばんごう']}.get(x, [])
        try:
            got = O._typed_run('デ゜ン和番号を', 1, 2)
            self.assertIn('で゜んわばんごう', got[2])
            res = O.repair_line('デ゜ン和番号を', {'corrected': 'デ゜ン和番号を', 'odd_spans': []}, run,
                                st.store, st.dict_index, st.context_vec)
            self.assertEqual(res['corrected'], '電話番号を')
            # 記号の無い所は記録の読みだけ（今までどおり）
            kanji_guess._IME_READINGS_PROVIDER = lambda x: {'漢字語': ['かんじご']}.get(x, [])
            self.assertEqual(O._typed_run('漢字語です', 0, 3)[2], ['かんじご'])
        finally:
            kanji_guess._IME_READINGS_PROVIDER = old

    def test_te_dropped(self):
        # 動詞の連用形＋補助の動詞の間の て の抜け・する の連用＋た の間の ま の抜け（作った文）
        self.assertEqual(self.run_line('宿題を忘れしまった')['corrected'], '宿題を忘れてしまった')
        self.assertEqual(self.run_line('道を教えくれた')['corrected'], '道を教えてくれた')
        self.assertEqual(self.run_line('予定が変わりした')['corrected'], '予定が変わりました')
        # 語幹が漢字1字だけの動詞は決めずに紫だけ（別の動詞の打ち違いとも読める）
        import te_dropped as TD
        self.assertEqual([x[3] for x in TD.propose('写真を見して')], [None])
        self.assertEqual([x[3] for x in TD.propose('早く寝しまった')], [None])
        for ok in ['宿題を忘れてしまった', '道を教えてくれた', '見入る', '予定が変わりました', '書き置きを残す']:
            self.assertFalse(self.run_line(ok).get('odd_spans'), ok)

    def test_broken_shape_purple(self):
        import broken_shape as BS
        # 1打違いが別の字に変換されて残った形（作った文）には紫だけ付ける
        for bad in ['手紙を書きまし歯', '書類を提出捨てた', '机の上ミ本がある', '窓をあけた手', '本棚の上にネ箱がある',
                    '荷物が=届いた', '書類を提出やした', '本を読みうと思う', '箱に荷物がれない', '゜ん号を書く', '書類を作成五送る', 'え駅で待つ', '写真を撮ってカメル', '会議が延期なりました']:
            self.assertTrue(BS.spans(bad), bad)
        for ok in ['手紙を書きました', '書類を提出し直した', 'メモ帳に書く', 'ガス代が上がった', '牛乳+パンを買う',
                   '東京~大阪の新幹線', 'いいよ行こう', '行きます明日', '左手で持つ', '毎朝歯を磨く',
                   '大きすぎる箱', '3ヶ月ぶり', 'あしたはがっこうです', '「゛」の記号', '本を読もうと思う', '言われる', 'と言った', 'は無理です', '病気になりました', '静かなる夜', 'あ、雨だ', 'お茶を手渡す', '鍋料理が恋しい', '長い間お世話になりました']:
            self.assertEqual(BS.spans(ok), [], ok)
        # かな入力で、隣のキーを一緒に押した1字の足しと見える漢字1字（言い終わりの後ろ）は除いて直す
        self.assertEqual(BS.repair_line('窓をあけた手', {'corrected': '窓をあけた手', 'odd_spans': []})['corrected'], '窓をあけた')
        self.assertEqual(BS.repair_line('窓をあけた手', {'corrected': '窓をあけた手', 'odd_spans': []}, (), 'romaji')['corrected'],
                         '窓をあけた手')
        # 前の段の直しで崩れた形になった所は、直しはそのままで元の行の範囲に紫
        got = BS.repair_line('手紙を書き増戸た', {'corrected': '手紙を書きましとた', 'odd_spans': []})
        self.assertEqual(got['corrected'], '手紙を書きましとた')
        self.assertEqual(got['odd_spans'], [(5, 7)])
        r = self.run_line('手紙を書きまし歯')
        self.assertEqual(r['corrected'], '手紙を書きまし歯')
        self.assertTrue(r.get('odd_spans'))

    def test_keep_converted_words(self):
        import keep_converted as KC
        # 打ち違いの直しのついでに、離れた所の変換済みの語を読みの同じ別の表記にした所は戻す（作った例）
        res = {'corrected': 'こうえんで本をよんだ', 'odd_spans': []}
        self.assertEqual(KC.repair_line('公園で本およんだ', res)['corrected'], '公園で本をよんだ')
        res = {'corrected': '紙面を読みました', 'odd_spans': []}
        self.assertEqual(KC.repair_line('誌面を読みまひた', res)['corrected'], '誌面を読みました')
        # 読みの同じ語だけの直し（選び違いの直し）・打ち違いの所と続いた所は戻さない
        res = {'corrected': '資料を送ります', 'odd_spans': []}
        self.assertEqual(KC.repair_line('死霊を送ります', res)['corrected'], '資料を送ります')
        res = {'corrected': '本を読みました', 'odd_spans': []}
        self.assertEqual(KC.repair_line('本を読み真下', res)['corrected'], '本を読みました')
        # 選び違いを直す段が替えた所（details に その段の名）は、別の所に打ち違いの直しがあっても戻さない
        res = {'corrected': '資料を送りました', 'odd_spans': [], 'details': [['死霊', '資料', '語の組'], ['ひ', 'し', 'かな入力']]}
        self.assertEqual(KC.repair_line('死霊を送りまひた', res)['corrected'], '資料を送りました')
        res = {'corrected': '紙面を読みました', 'odd_spans': [], 'details': [['誌面を読みまひた', '紙面を読みました', 'かな入力']]}
        self.assertEqual(KC.repair_line('誌面を読みまひた', res)['corrected'], '誌面を読みました')

    def test_correct_lines_untouched(self):
        for line in ['辞書で調べてください。', 'どこが原因かを話し合いました。', '話すことがあります。',
                     'でんわばんごうをおしえてください。']:
            got = self.run_line(line)
            self.assertFalse(got.get('odd_spans'), line)


if __name__ == '__main__':
    unittest.main()
