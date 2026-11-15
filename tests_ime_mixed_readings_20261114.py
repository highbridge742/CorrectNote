# -*- coding: utf-8 -*-
"""英字まじりの打った読み（ime_readings._mixed・2026-11-14）。ローマ字入力で母音の付かない子音が英字のまま残った確定
（作った例: 田m者 ← でんmしゃ）を、かなだけの表とは別に覚え、mixed_readings_for で引き、typed_back へ渡す。
作った例だけを使い、本物の IME・個人ファイルは使わない。"""
import json
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

import ime_readings as R


class MixedReadings(unittest.TestCase):
    def test_shape_and_normalising(self):
        self.assertTrue(R.is_mixed_reading('でんmしゃ'))
        self.assertFalse(R.is_mixed_reading('でんしゃ'))      # 英字が無い（かなの表の受け持ち）
        self.assertFalse(R.is_mixed_reading('abc'))           # かなが無い
        self.assertFalse(R.is_mixed_reading('でん m しゃ'))   # 空白・記号は入れない
        self.assertEqual(R.to_mixed_reading('ﾃﾞﾝｍｼｬ'), 'でんmしゃ')   # 半角カタカナ＋全角英字 → ひらがな＋半角小文字

    def test_remember_and_read_without_touching_kana_pairs(self):
        ime = R.IMEReadings()
        self.assertFalse(ime.remember('田m者', 'ﾃﾞﾝmｼｬ'))      # かなだけの表は覚えない（今までどおり）
        self.assertTrue(ime.remember_mixed('田m者', 'ﾃﾞﾝmｼｬ'))
        self.assertEqual(ime.mixed_readings_for('田m者'), ['でんmしゃ'])
        self.assertEqual(ime.readings_for('田m者'), [])       # 今の読み手には出ない
        self.assertEqual(ime.pairs(), {})
        rev = ime.revision()
        self.assertFalse(ime.remember_mixed('田m者', 'でんmしゃ'))   # 同じ読みの打ち直しは版を進めない
        self.assertEqual(ime.revision(), rev)

    def test_switch_off(self):
        ime = R.IMEReadings()
        with mock.patch.dict(os.environ, {'CN_IME_MIXED': '0'}):
            self.assertFalse(ime.remember_mixed('田m者', 'でんmしゃ'))
        ime.remember_mixed('田m者', 'でんmしゃ')
        with mock.patch.dict(os.environ, {'CN_IME_MIXED': '0'}):
            self.assertEqual(ime.mixed_readings_for('田m者'), [])

    def test_save_load_trim_keep_forget_stamp(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'ime_readings.json')
            ime = R.IMEReadings(path)
            ime.remember('資料', 'ｼﾘｮｳ')
            before = ime.stamp()
            ime.remember_mixed('田m者', 'でんmしゃ')
            self.assertNotEqual(ime.stamp(), before)          # 解析の控えの見分けに混ざる
            self.assertTrue(ime.save())
            data = json.load(open(path, encoding='utf-8'))
            self.assertEqual(data['version'], R.VERSION)
            self.assertEqual(data['mixed'], {'田m者': ['でんmしゃ']})
            again = R.IMEReadings(path).load()
            self.assertEqual(again.mixed_readings_for('田m者'), ['でんmしゃ'])
            self.assertEqual(again.readings_for('資料'), ['しりょう'])
            # 本文に無い表記は落とす（かなの表と同じ）
            self.assertEqual(again.keep_only_in(['資料だけの本文']), 1)
            self.assertEqual(again.mixed_readings_for('田m者'), [])
            # 上限は別（1,000）
            small = R.IMEReadings()
            small.mixed_limit = 2
            for i, s in enumerate(('a田', 'b田', 'c田')):
                small.remember_mixed(s, 'で%sしゃ' % 'xyz'[i])
            self.assertEqual(list(small._mixed), ['b田', 'c田'])
            # 消す: 表記ごと（画面）と、読みを指定した forget
            self.assertEqual(small.forget_mixed('b田'), 1)
            self.assertEqual(small.forget('c田', 'でzしゃ'), 1)
            self.assertEqual(small._mixed, {})

    def test_old_file_without_mixed_still_loads(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'ime_readings.json')
            json.dump({'version': 1, 'pairs': {'資料': ['しりょう']}}, open(path, 'w', encoding='utf-8'),
                      ensure_ascii=False)
            ime = R.IMEReadings(path).load()
            self.assertEqual(ime.readings_for('資料'), ['しりょう'])
            self.assertEqual(ime._mixed, {})
            self.assertEqual(ime.stamp(), [1, 1, ime.stamp()[2]])   # 英字まじりが無ければ前と同じ形の値

    def test_app_remembers_mixed_only_for_romaji(self):
        import app
        for method, expected in (('romaji', ['でんmしゃ']), ('kana', [])):
            ime = R.IMEReadings()
            fake = SimpleNamespace(settings=SimpleNamespace(get=lambda k, m=method: m), _ime_origin_work=None,
                                   ime_readings=ime, _ime_pairs_dirty=False)
            app.CorrectNoteApp._remember_ime_pair(fake, '田m者', 'ﾃﾞﾝmｼｬ')
            self.assertEqual(ime.mixed_readings_for('田m者'), expected, method)
            self.assertEqual(fake._ime_pairs_dirty, bool(expected))

    def test_worker_carries_mixed_and_sets_typed_back(self):
        import analysis_worker, typed_back
        ime = R.IMEReadings()
        ime.remember_mixed('田m者', 'でんmしゃ')
        snap = {'ime_mixed': {k: list(v) for k, v in ime._mixed.items()}}
        rt = SimpleNamespace(ime=R.IMEReadings())
        saved = typed_back._provider[0]
        try:
            analysis_worker.Runtime._set_ime_mixed(rt, snap)
            self.assertEqual(typed_back._provider[0]('田m者'), ['でんmしゃ'])
        finally:
            typed_back.set_provider(saved)


if __name__ == '__main__':
    unittest.main()
