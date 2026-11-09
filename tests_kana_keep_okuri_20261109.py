# -*- coding: utf-8 -*-
"""batch426: 送り仮名を挟んで漢字にした和語の名詞（とりたて → 取り立て）もかなに戻す（kana_keep）。"""
import unittest

import kana_keep as K


class KanaKeepOkuri(unittest.TestCase):
    def test_okuri_noun_kept(self):
        line = 'のりかえの案内'
        out = K.repair_line(line, {'corrected': '乗り換えの案内'})
        self.assertEqual(out['corrected'], line)

    def test_kango_kept_kanji(self):
        out = K.repair_line('じょしの使い方', {'corrected': '助詞の使い方'})
        self.assertEqual(out['corrected'], '助詞の使い方')


if __name__ == '__main__':
    unittest.main()
