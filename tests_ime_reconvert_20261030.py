# -*- coding: utf-8 -*-
"""ime_reconvert（IME で変換し直して珍しい漢字の語を疑う段・2026-10-30）の試験。IME は読みの表を引く代わりの物で置き換える。"""
import unittest

import ime_language
import ime_reconvert as M
from morphology import tokenize


class _FakeIME:
    """解析の読みで逆変換し、行ぜんたいの読みだけを決めた行に変換する。"""
    available = True
    error = None

    def __init__(self, first=None):
        self.first = first
        self.phon = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def reverse_words(self, text):
        phon, words = '', []
        for t in tokenize(text):
            r = M._hira(t.reading) if t.has_reading else t.surface
            words.append((t.start, t.end, len(phon), len(phon) + len(r), 0, 0))
            phon += r
        self.phon = phon
        return phon, tuple(words)

    def convert(self, reading):
        return self.first if reading == self.phon else None


class ImeReconvertTests(unittest.TestCase):
    def test_correct_word_of_middling_rarity_is_kept(self):
        self.assertEqual(M.propose('出張の精算をする。', 'kana', _FakeIME('出張の生産をする。')), [])

    def test_rare_word_that_reconverts_to_a_common_one_is_purple(self):
        marks = M.propose('友達の烏賊に行く。', 'kana', _FakeIME('友達の以下に行く。'))
        self.assertEqual(marks, [(3, 5, None)])

    def test_word_outside_the_table_is_fixed_when_the_ime_gives_one_common_word(self):
        marks = M.propose('本の返却嘉言が明日までだ。', 'kana', _FakeIME('本の返却期限が明日までだ。'))
        self.assertEqual(len(marks), 1)

    def test_no_ime_means_no_change(self):
        self.assertEqual(M.propose('友達の烏賊に行く。', 'kana', None), [])

    def test_repair_line_marks_purple(self):
        saved = ime_language.JapaneseIME
        ime_language.JapaneseIME = lambda: _FakeIME('友達の以下に行く。')
        try:
            line = '友達の烏賊に行く。'
            out = M.repair_line(line, {'corrected': line, 'changed': False}, 'kana')
        finally:
            ime_language.JapaneseIME = saved
        self.assertIn((3, 5), [tuple(x[:2]) for x in out.get('odd_spans', ())])
        self.assertEqual(out['corrected'], line)

    def test_common_line_is_not_looked_up(self):
        class Boom(_FakeIME):
            def reverse_words(self, text):
                raise AssertionError('IME を引かない')
        self.assertEqual(M.propose('明日は雨が降るそうです。', 'kana', Boom()), [])

    def test_extra_key_into_kana_tail_is_fixed_in_romaji(self):
        # 作った例: れんらくください の s を2度押し（くだっさい）→ IME が珍しい漢字の語にした形
        class Reading(_FakeIME):
            def reverse_words(self, text):
                words = (('ご', 'ご'), ('連絡', 'れんらく'), ('く', 'く'), ('達采', 'だっさい'), ('。', '。'))
                phon, out, i = '', [], 0
                for face, r in words:
                    j = text.index(face, i)
                    out.append((j, j + len(face), len(phon), len(phon) + len(r), 0, 0))
                    phon += r
                    i = j + len(face)
                return phon, tuple(out)
        self.assertEqual(M.propose('ご連絡く達采。', 'romaji', Reading()), [(4, 6, 'ご連絡ください。')])
        self.assertEqual(M.propose('ご連絡く達采。', 'kana', Reading()), [])


    def test_vowel_slip_before_suru_is_fixed_to_the_table_noun(self):
        # 作った例: かくにん の に を ね と打って、IME が表に無い漢字の語にした形
        class Reading(_FakeIME):
            def reverse_words(self, text):
                words = (('郭稔', 'かくねん'), ('しました', 'しました'), ('。', '。'))
                phon, out, i = '', [], 0
                for face, r in words:
                    j = text.index(face, i)
                    out.append((j, j + len(face), len(phon), len(phon) + len(r), 0, 0))
                    phon += r
                    i = j + len(face)
                return phon, tuple(out)
        self.assertEqual(M.propose('郭稔しました。', 'romaji', Reading()), [(0, 2, '確認しました。')])
        self.assertTrue(M._vowel_slip('じゅけい', 'じゅきょう'))
        self.assertFalse(M._vowel_slip('かくにん', 'かくにん'))


    def test_wrong_split_is_resegmented(self):
        # 作った例: おきゃくさまよう を IME が 身近な語＋表に無い語 に区切った形
        class Reading(_FakeIME):
            def reverse_words(self, text):
                words = (('お客', 'おきゃく'), ('醒摩耀', 'さまよう'), ('の', 'の'), ('椅子', 'いす'), ('です', 'です'), ('。', '。'))
                phon, out, i = '', [], 0
                for face, r in words:
                    j = text.index(face, i)
                    out.append((j, j + len(face), len(phon), len(phon) + len(r), 0, 0))
                    phon += r
                    i = j + len(face)
                return phon, tuple(out)
        self.assertEqual(M.propose('お客醒摩耀の椅子です。', 'kana', Reading()), [(2, 5, 'お客様用の椅子です。')])


    def test_two_odd_words_are_reconverted_to_common_ones(self):
        # 作った例: しゅうせいあんです を IME が 身近でない語＋カタカナの語 にした形
        class Reading(_FakeIME):
            def reverse_words(self, text):
                words = (('秀星', 'しゅうせい'), ('アンデス', 'あんです'))
                phon, out, i = '', [], 0
                for face, r in words:
                    j = text.index(face, i)
                    out.append((j, j + len(face), len(phon), len(phon) + len(r), 0, 0))
                    phon += r
                    i = j + len(face)
                return phon, tuple(out)
        self.assertEqual(M.propose('秀星アンデス', 'romaji', Reading()), [(2, 6, '修正案です')])


    def _words_ime(self, words):
        class Reading(_FakeIME):
            def reverse_words(self, text):
                phon, out, i = '', [], 0
                for face, r in words:
                    j = text.index(face, i)
                    out.append((j, j + len(face), len(phon), len(phon) + len(r), 0, 0))
                    phon += r
                    i = j + len(face)
                return phon, tuple(out)
        return Reading()

    def test_char_readings_are_used_when_the_ime_reads_a_kun_reading(self):
        # 作った例: IME が 受 を うけ と逆変換しても、字ごとの読み（じゅ＋りょう）で表の語に届く
        ime = self._words_ime((('受', 'うけ'), ('稜', 'りょう'), ('し', 'し'), ('ました', 'ました')))
        self.assertEqual(M.propose('受稜しました', 'romaji', ime), [(0, 2, '受領しました')])

    def test_okurigana_split_by_the_ime_is_joined_for_resegmenting(self):
        # 作った例: IME が 醒摩｜う と送りがなを別の語にした形
        ime = self._words_ime((('お客', 'おきゃく'), ('醒摩', 'さまよ'), ('う', 'う')))
        self.assertEqual(M.propose('お客醒摩う', 'kana', ime), [(2, 5, 'お客様用')])


class MisreadTests(unittest.TestCase):
    def test_ime_misreading_a_written_word_is_found(self):
        # 作った例: 送りがなの在る正しい語を IME が辞書と違う読みで読んだ（深煎り を しんいり）。その所の直しは出さない
        self.assertEqual(M._misread_spans('深煎り', 'しんいり', ((0, 3, 0, 4, 0, 0),), list(tokenize('深煎り'))), [(0, 3)])
        self.assertEqual(M._misread_spans('深煎り', 'ふかいり', ((0, 3, 0, 4, 0, 0),), list(tokenize('深煎り'))), [])

    def test_ime_words_split_like_the_dictionary_are_compared_one_by_one(self):
        # 作った例: IME が 深｜煎り と2語に切って しん・いり と読んだ。辞書も 深｜煎り なので、読みの違う 深 の所を返す
        words = ((0, 1, 0, 2, 0, 0), (1, 3, 2, 4, 0, 0))
        self.assertEqual(M._misread_spans('深煎り', 'しんいり', words, list(tokenize('深煎り'))), [(0, 1)])
        self.assertEqual(M._misread_spans('深煎り', 'ふかいり', words, list(tokenize('深煎り'))), [])

    def test_fix_that_rewrites_a_misread_word_is_dropped(self):
        # 直しの印が 煎り だけでも、置く行が読み違えた 深 まで書き換えるなら出さない
        self.assertEqual(M._changed_span('深煎りブレンド', '真入りブレンド'), (0, 2))
        self.assertTrue(M._touches((1, 3, '真入りブレンド'), [(0, 1)], '深煎りブレンド'))
        self.assertFalse(M._touches((4, 6, '深煎りブランド'), [(0, 1)], '深煎りブレンド'))

    def test_kanji_split_one_by_one_is_not_compared(self):
        # 打ち違いで出来た珍しい字の組（字ごとに切れる）は、字ごとの読みが当てにならないので比べない
        self.assertEqual(M._misread_spans('達采', 'だっさい', ((0, 2, 0, 4, 0, 0),), list(tokenize('達采'))), [])

    def test_propose_drops_marks_on_misread_words(self):
        import inspect
        self.assertIn('_misread_spans', inspect.getsource(M.propose))

if __name__ == '__main__':
    unittest.main()
