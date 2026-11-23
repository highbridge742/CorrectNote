# -*- coding: utf-8 -*-
"""再入力変換で一字の漢字を単独で平仮名に開く時、促音で終わる読み（「一個」の「いっ」）を使わない（2026-11-22 02:33Z うにさん
「IMEが一に変換した。それを再変換入力で平仮名に開いた。いっ　になった」）。IME で確定した時の読みがあればそれを最優先。
CN_REINPUT_NO_SOKUON_SINGLE=0 で前の形。作り物のアプリと作った字だけ（うにさんの読みの控えは使わない）。"""
import os
import unittest
from types import SimpleNamespace as NS
from unittest import mock

import reinput


def tokenizer(line):
    # 解析が「一」に促音の読みを付けた形（janome がこう付けることがある）
    out = []
    at = 0
    for surface, reading in (('一', 'イッ'), ('が', 'ガ'), ('動く', 'ウゴク')):
        if line.startswith(surface, at):
            out.append((surface, '名詞', reading, at, at + len(surface)))
            at += len(surface)
    return out


class FakeIndex:
    def readings_for_surface(self, ch):
        return {'一': ['いっ', 'いち', 'ひと']}.get(ch, [])


def make(records=()):
    r = reinput.ReInput.__new__(reinput.ReInput)
    r.app = NS(store=NS(_tokenize_fn=tokenizer), ime_readings=None, dict_index=FakeIndex())
    r.widget = NS(get=lambda a, b: '一が動く')
    r.quick = False
    r._line_readings = lambda row: list(records)
    r._reverse = lambda text: None
    return r


class Standalone(unittest.TestCase):
    def test_single_kanji_opens_without_sokuon(self):
        self.assertEqual(make().reading_of(1, 0, '一'), 'いち')

    def test_typed_reading_comes_first(self):
        # IME で確定した時の読み（打った読み）があれば、それをそのまま使う
        rec = NS(start=0, end=4, surface='一が動く', reading='いちがうごく')
        self.assertEqual(make([rec]).reading_of(1, 0, '一'), 'いち')
        rec = NS(start=0, end=1, surface='一', reading='いっ')
        self.assertEqual(make([rec]).reading_of(1, 0, '一'), 'いっ')          # 打った読みが「いっ」ならそのまま

    def test_keys_come_first(self):
        # 02:51Z うにさん「実際にどのキーを押したかという情報から、平仮名にしてください」（CN_REINPUT_FROM_KEYS）
        keys = tuple((k, i) for i, k in enumerate('eat@4b@h'))                        # い ち か゛ う こ゛ く
        rec = NS(start=0, end=4, surface='一が動く', reading='いつがうごく', strokes=keys, shifts=())
        self.assertEqual(make([rec]).reading_of(1, 0, '一'), 'いち')                 # 打ったキーのかなを最優先
        with mock.patch.dict(os.environ, {'CN_REINPUT_FROM_KEYS': '0'}):
            self.assertEqual(make([rec]).reading_of(1, 0, '一'), 'いつ')             # 前の形: IME の読み
        # 打ち直し（BackSpace は記録で見分けられない）で字数が合わない時は IME の読み
        keys2 = tuple((k, i) for i, k in enumerate('eaat@4b@h'))
        rec2 = NS(start=0, end=4, surface='一が動く', reading='いちがうごく', strokes=keys2, shifts=())
        self.assertEqual(make([rec2]).reading_of(1, 0, '一'), 'いち')
        # 2026-11-22 からの記録は BackSpace の種類が残る（stroke_keys.NonChar）: 消した字を除いた打ったかなを使う
        import stroke_keys
        keys3 = tuple((k, i) for i, k in enumerate('eaz')) + ((stroke_keys.NonChar('BackSpace'), 3),) + \
            tuple((k, 4 + i) for i, k in enumerate('t@4b@h'))
        rec3 = NS(start=0, end=4, surface='一が動く', reading='いつがうごく', strokes=keys3, shifts=())
        self.assertEqual(make([rec3]).reading_of(1, 0, '一'), 'いち')                # い ち つ BS か゛ う こ゛ く → いちがうごく

    def test_typed_kana_from_keys(self):
        import typed_kana as T
        self.assertEqual(T.from_keys([('e', 1), ('a', 2), ('t', 3), ('@', 4)]), 'いちが')    # ゛ は前の字と組む
        self.assertEqual(T.from_keys([('z', 5)], [(4, 6)]), 'っ')                          # Shift の面
        self.assertEqual(T.from_keys([('i', 1), ('t', 2), ('i', 3)], (), 'romaji'), 'いち')
        self.assertIsNone(T.from_keys([('k', 1), ('y', 2)], (), 'romaji'))               # かなにできない
        self.assertIsNone(T.from_keys([('@', 1)]))                                      # 前の字の無い ゛

    def test_longer_words_unchanged(self):
        self.assertEqual(make().reading_of(1, 2, '動く'), 'うごく')

    def test_switch_back(self):
        with mock.patch.dict(os.environ, {'CN_REINPUT_NO_SOKUON_SINGLE': '0'}):
            self.assertEqual(make().reading_of(1, 0, '一'), 'いっ')


if __name__ == '__main__':
    unittest.main()
