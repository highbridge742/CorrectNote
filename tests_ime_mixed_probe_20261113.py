# -*- coding: utf-8 -*-
"""確かめ用の読むだけの記録 ime_mixed_probe（2026-11-13）。既定はオフ、CN_IME_MIXED_PROBE=1 の時だけ書く。
記録に打った文字が入らないこと、英字の有無と長さだけが残ること、_remember_ime_pair から呼ばれ、覚え方は変えないこと。
作った例だけを使い、本物の IME・個人ファイルは使わない。"""
import json
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

import ime_mixed_probe as P


class ImeMixedProbe(unittest.TestCase):
    def test_off_by_default(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertFalse(P.note(d, '田m者', 'ﾀmｼｬ', 'romaji', environ={}))
            self.assertFalse(os.path.exists(os.path.join(d, P.FOLDER)))

    def test_record_has_no_text(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertTrue(P.note(d, '田m者', 'ﾀmｼｬ', 'romaji', environ={P.ENV: '1'}))
            self.assertTrue(P.note(d, '予定', 'ﾖﾃｲ', 'romaji', environ={P.ENV: '1'}))
            self.assertTrue(P.note(d, '田ｍ者', 'たｍしゃ', 'kana', fallback=True, environ={P.ENV: '1'}))
            path = os.path.join(d, P.FOLDER, 'log.jsonl')
            raw = open(path, encoding='utf-8').read()
            for text in ('田', '者', '予定', 'ﾀ', 'ｼｬ', 'たｍしゃ'):
                self.assertNotIn(text, raw)
            rows = [json.loads(l) for l in raw.splitlines()]
            self.assertEqual([(r['surface_letter'], r['reading_letter'], r['surface_len'], r['reading_len'], r['via'])
                              for r in rows],
                             [(True, True, 3, 4, 'result'), (False, False, 2, 3, 'result'), (True, True, 3, 4, 'fallback')])
            s = P.summary(path)
            self.assertEqual((s['rows'], s['romaji'], s['both'], s['reading_only'], s['surface_only']), (3, 2, 1, 0, 0))

    def test_called_from_remember_ime_pair_without_changing_memory(self):
        import app
        got = []
        fake = SimpleNamespace(settings=SimpleNamespace(get=lambda k: 'romaji'), _ime_origin_work=None,
                               ime_readings=SimpleNamespace(remember=lambda s, r: got.append((s, r)) or False))
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {P.ENV: '1'}), \
                mock.patch.object(app, 'app_dir', lambda: d):
            app.CorrectNoteApp._remember_ime_pair(fake, '田m者', 'ﾀmｼｬ')
            rows = open(os.path.join(d, P.FOLDER, 'log.jsonl'), encoding='utf-8').read().splitlines()
        self.assertEqual(len(rows), 1)
        self.assertEqual(got, [('田m者', 'ﾀmｼｬ')])        # 覚える道はそのまま呼ばれる
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {}, clear=False), \
                mock.patch.object(app, 'app_dir', lambda: d):
            os.environ.pop(P.ENV, None)
            app.CorrectNoteApp._remember_ime_pair(fake, '田m者', 'ﾀmｼｬ')
            self.assertFalse(os.path.exists(os.path.join(d, P.FOLDER)))


if __name__ == '__main__':
    unittest.main()
