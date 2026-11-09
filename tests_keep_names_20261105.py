# -*- coding: utf-8 -*-
"""2026-11-05 うに「さん付けの前の名前が補正されている」「名前の前に引用（>・＞）」「@ の後ろに名前」:
名前と見る所（敬称の前・@ の後ろ）の直しと紫は外す。例はすべて作った例。"""
import unittest

import correction_entry as C


class NameSpanTests(unittest.TestCase):
    def test_spans(self):
        cases = {
            '明日はゆかりさんと話す': ['ゆかり'],
            '>田中さん、了解です': ['田中'],
            '＞高梨さん、ありがとう': ['高梨'],
            '@sato_k 確認お願いします': ['sato_k'],
            '＠佐々木 よろしく': ['佐々木'],
            '鈴木先生の授業': ['鈴木'],
            'ちゃんとやる': [],
            '散歩に行く': [],
            '学校の先生に聞く': [],
            'Mr.Kato に送る': ['Kato'],
            'Dr. Emily Brown が来る': ['Emily Brown'],
            'Ms Tanaka と話した': ['Tanaka'],
            'Ｍｒ．山本 へ': ['山本'],
            'Prof.佐藤の講義': ['佐藤'],
            'mister は無い': [],
            'dream drive': [],
            'ミスター田中が来た': ['田中'],
            'ドクター・スミスの話': ['スミス'],
            'ミス・ブラウンと会う': ['ブラウン'],
            '入力ミスを直す': [],
            '昨日 John Smith に送った': ['John Smith'],
            'I met Mary Ann Lee today': ['Mary Ann Lee'],
            'The Cat sat': [],
            'NASA の発表': [],
            'ミスが多い': [],
        }
        for line, want in cases.items():
            self.assertEqual([line[a:b] for a, b in C._name_spans(line)], want, line)

    def test_fix_on_a_name_is_undone(self):
        line = '＞高梨さんに渡した'
        res = {'corrected': '＞高橋さんに渡した', 'changed': True, 'details': [['梨', '橋', 'x']],
               'odd_spans': [(1, 3)], 'odd_reasons': [(1, 3, 'x')]}
        out = C._keep_names(line, res)
        self.assertEqual(out['corrected'], line)
        self.assertEqual(out['odd_spans'], [])
        self.assertFalse(out['changed'])

    def test_fix_outside_the_name_stays(self):
        line = '@yamada 明日わ休みです'
        res = {'corrected': '@yamada 明日は休みです', 'changed': True, 'details': [['わ', 'は', 'x']]}
        self.assertEqual(C._keep_names(line, res)['corrected'], '@yamada 明日は休みです')


if __name__ == '__main__':
    unittest.main()
