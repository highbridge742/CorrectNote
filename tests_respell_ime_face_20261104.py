# -*- coding: utf-8 -*-
"""2026-11-04: 1打違いの戻しで決める（ime_reconvert）・読み直した所の表記を IME に任せる（ime_face）・
敬いの お が動詞のて形に直に付く所の紫（pos_grammar）。IME は表で置き換える。例はすべて作った例。"""
import unittest

import ime_reconvert as M
from pos_grammar import _impossible_connection_spans


class _KeyIME:
    available = True
    error = None

    def __init__(self, words, table):
        self.words, self.table = words, table

    def reverse_words(self, text):
        phon, out, i = '', [], 0
        for face, r in self.words:
            j = text.index(face, i)
            out.append((j, j + len(face), len(phon), len(phon) + len(r), 0, 0))
            phon += r
            i = j + len(face)
        return phon, tuple(out)

    def convert(self, reading):
        return self.table.get(reading)


class _FaceIME:
    available = True

    def __init__(self, reads, convs):
        self.reads, self.convs = reads, convs

    def phonetic(self, text):
        return self.reads.get(text)

    def convert(self, reading):
        return self.convs.get(reading)


class KeyFixTests(unittest.TestCase):
    def test_one_key_slip_to_common_words_is_fixed(self):
        ime = _KeyIME((('会議', 'かいぎ'), ('の', 'の'), ('補遺', 'ほい'), ('国書', 'こくしょ')),
                      {'かいぎのほいこくしょ': '会議の補遺国書', 'かいぎのほうこくしょ': '会議の報告書'})
        marks = M.propose('会議の補遺国書', 'romaji', ime)
        self.assertEqual(marks, [(3, 7, '会議の報告書')])

    def test_middling_rare_word_one_key_from_a_business_word_is_fixed(self):
        ime = _KeyIME((('会議', 'かいぎ'), ('の', 'の'), ('密偵', 'みってい')),
                      {'かいぎのみってい': '会議の密偵', 'かいぎのにってい': '会議の日程'})
        self.assertEqual([m[2] for m in M.propose('会議の密偵', 'romaji', ime)], ['会議の日程'])

    def test_fix_leaving_kana_scraps_stays_purple(self):
        self.assertTrue(M._kana_scraps('会議に参加左飛ます', '会議に参加差へいます'))
        self.assertFalse(M._kana_scraps('会議の補遺国書', '会議の報告書'))

    def test_fix_rewriting_outside_the_slip_stays_purple(self):
        self.assertTrue(M._key_fix_overreach('部長にきんいおくしょをてお移出した', '部長にきんい億書を提出した'))
        self.assertTrue(M._key_fix_overreach('節女辞書を読む', '節おんなじショーを読む'))
        self.assertFalse(M._key_fix_overreach('会議の補遺国書', '会議の報告書'))

    def test_switch_keeps_purple(self):
        import os
        os.environ['CN_RECONVERT_KEY_FIX'] = '0'
        try:
            ime = _KeyIME((('会議', 'かいぎ'), ('の', 'の'), ('補遺', 'ほい'), ('国書', 'こくしょ')),
                          {'かいぎのほいこくしょ': '会議の補遺国書', 'かいぎのほうこくしょ': '会議の報告書'})
            self.assertEqual(M.propose('会議の補遺国書', 'romaji', ime), [(3, 7, None)])
        finally:
            del os.environ['CN_RECONVERT_KEY_FIX']


class SingleKanjiRunTests(unittest.TestCase):
    def test_run_of_one_kanji_nouns_with_an_extra_kana_is_fixed(self):
        ime = _KeyIME((('集亜量', 'しゅうありょう'), ('が', 'が')),
                      {'しゅうありょうが': '集亜量が', 'しゅうりょうが': '終了が'})
        self.assertEqual(M.propose('集亜量が', 'kana', ime), [(0, 3, '終了が')])

    def test_usual_one_kanji_nouns_are_not_doubted(self):
        from morphology import tokenize
        for line in ('日米の会談', '大小の箱', '手と足を洗う', '水道代'):
            ts = list(tokenize(line))
            self.assertLess(max(M._token_rarity(t, ts) for t in ts), M.DOUBT, line)


class LineKeyTests(unittest.TestCase):
    class _Conv:
        available = True

        def __init__(self, table):
            self.table = table

        def convert(self, reading):
            return self.table.get(reading)

    def test_one_key_slip_of_the_whole_line_is_fixed(self):
        ime = self._Conv({'ごごのかいぎにさんかします': '午後の会議に参加します'})
        self.assertEqual(M.line_key_propose('午後の会卯木に参加します', 'ごごのかいうぎにさんかします', ime),
                         '午後の会議に参加します')

    def test_correct_line_is_kept(self):
        ime = self._Conv({'きょうはおらがとてもあおい': '今日はおらがとても青い'})
        self.assertIsNone(M.line_key_propose('今日は空がとても青い', 'きょうはそらがとてもあおい', ime))

    def test_only_romaji_lines_with_a_record(self):
        res = {'corrected': '午後の会卯木に参加します'}
        self.assertIs(M.line_key_repair('午後の会卯木に参加します', res, 'kana'), res)


class ImeFaceTests(unittest.TestCase):
    def test_respelled_word_takes_the_ime_face(self):
        ime = _FaceIME({'教えて下さい': 'おしえてください', '教えてください': 'おしえてください'},
                       {'おしえてください': '教えてください'})
        self.assertEqual(M.ime_face('お朱得て下し亜', '教えて下さい', ime), '教えてください')

    def test_kana_typed_part_is_left_to_kana_keep(self):
        ime = _FaceIME({}, {})
        self.assertEqual(M.ime_face('くたせさい', 'ください', ime), 'ください')

    def test_other_words_of_the_clause_are_kept(self):
        ime = _FaceIME({'明日は晴れ下さい': 'あしたははれください', '明日波晴れください': 'あしたははれください'},
                       {'あしたははれください': '明日波晴れください'})
        # 句のほかの所（は）を替える変換は、読み直した語の所だけ採る
        self.assertEqual(M.ime_face('明日は晴れ下し亜', '明日は晴れ下さい', ime), '明日は晴れ下さい')


class HonorificVerbTests(unittest.TestCase):
    def test_o_on_te_form_is_purple(self):
        self.assertEqual(_impossible_connection_spans('お据えて下さい'), ((0, 4),))

    def test_honorific_forms_are_kept(self):
        for line in ('お待ちしてください', 'お書きになって', 'ご覧になった', 'お越しください', '本をおいて出た',
                     '朝おきて顔を洗う', 'お手伝いして', 'お困りでしたら'):
            self.assertEqual(_impossible_connection_spans(line), (), line)


if __name__ == '__main__':
    unittest.main()
