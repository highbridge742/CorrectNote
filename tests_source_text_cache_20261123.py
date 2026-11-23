# -*- coding: utf-8 -*-
"""文書の全体の原文（editor_source_text）を、編集の世代ごとに1回だけ読む（2026-11-23 CN_SOURCE_TEXT_CACHE・うにさん
「打つたびに1秒～3秒の塊が起きてます」: 紫のある行で1打ごとに 31〜38 回、文書の全体を Tcl から写して割り直していた）。
・返す字は控え無しの形（CN_SOURCE_TEXT_CACHE=0）と完全に同じ: 打つ・消す・置き換える・元に戻す・まとめての書き換え・
  IME の確定が通る道（tk::TextInsert）・反映した控えが増える／消える／行が書き換わる
・IME の未確定の字は Text の中に無い（読む前も今も同じ）。確定した字は次の呼び出しから入る
・同じ世代の間は Text を読まない
自分の Text の窓だけ・作った文。"""
import os
import tkinter as tk
import unittest
from unittest import mock

import analysis_work
import app


class Fake:
    """editor_source_text が使う物だけを持つ形（控えは mark と applied/original）。"""
    def __init__(self, root):
        self.editor = tk.Text(root, undo=True)
        analysis_work.observe_text(self.editor)
        self.recs = []
        self.live_calls = 0

    def _autofix_live_records(self):
        self.live_calls += 1
        live = []
        for rec in list(self.recs):
            try:
                row = int(self.editor.index(rec['mark']).split('.')[0])
            except Exception:
                self.recs.remove(rec)
                continue
            if self.editor.get(f'{row}.0', f'{row}.end') != rec['applied']:
                self.recs.remove(rec)
                continue
            live.append((rec, row))
        return live

    def source(self):
        return app.CorrectNoteApp.editor_source_text(self)

    def plain(self):
        with mock.patch.dict(os.environ, {'CN_SOURCE_TEXT_CACHE': '0'}):
            return app.CorrectNoteApp.editor_source_text(self)


class SourceTextCache(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.f = Fake(self.root)
        self.f.editor.insert('1.0', '\n'.join('%d行目は会議の資料を確認するための作った文です。' % i for i in range(1, 30)))

    def same(self, note):
        got = self.f.source()
        self.assertEqual(got, self.f.plain(), note)
        self.assertEqual(self.f.source(), got, note)           # 2回目（控え）も同じ
        return got

    def add_rec(self, row, original):
        name = 'zz_rec_%d_%d' % (row, len(self.f.recs))
        self.f.editor.mark_set(name, f'{row}.0')
        self.f.recs.append(dict(mark=name, applied=self.f.editor.get(f'{row}.0', f'{row}.end'), original=original))

    def test_results_equal_the_uncached_form(self):
        f, ed = self.f, self.f.editor
        self.same('はじめ')
        ed.insert('3.4', 'あいう');                  self.same('打つ')
        ed.delete('5.0', '5.3');                     self.same('消す')
        ed.replace('7.0', '7.2', 'XYZ');             self.same('置き換える')
        ed.edit_separator(); ed.insert('2.0', '新しい'); ed.edit_separator()
        self.same('打つ2')
        ed.edit_undo();                               self.same('元に戻す')
        with analysis_work.bulk_edits(ed):
            ed.replace('9.0', '9.end', 'まとめて書き換えた行')
        self.same('まとめての書き換え')
        self.root.tk.call('tk::TextInsert', ed._w, '確定した字')
        got = self.same('IME の確定の道')
        self.assertIn('確定した字', got)

    def test_autofix_records_change_the_result(self):
        f, ed = self.f, self.f.editor
        before = self.same('控え無し')
        self.add_rec(4, '元の字の行')
        got = self.same('控えが増えた')
        self.assertEqual(got.split('\n')[3], '元の字の行')
        self.assertNotEqual(got, before)
        self.add_rec(6, '六の元')
        self.assertEqual(self.same('もう1つ').split('\n')[5], '六の元')
        f.recs.pop(0)                                   # 控えが消えた（字は同じ）
        got = self.same('控えが消えた')
        self.assertNotEqual(got.split('\n')[3], '元の字の行')
        ed.insert('6.end', '足した')                    # 控えの行を自分で書き換えた → 控えは落ちる
        got = self.same('控えの行を書き換えた')
        self.assertTrue(got.split('\n')[5].endswith('足した'))
        self.assertEqual(f.recs, [])
        self.add_rec(2, '二の元')
        ed.insert('1.0', '頭の行\n')                    # 行が下へずれても、控えの行に合う
        got = self.same('行がずれた')
        self.assertEqual(got.split('\n')[2], '二の元')

    def test_the_composition_is_not_in_the_text(self):
        # 未確定の字は Tk の Text に入らない（Windows の IME の窓に出る）。読む前も今も Text の字だけを返す
        f, ed = self.f, self.f.editor
        before = self.same('未確定の間')
        ed.mark_set('insert', '3.2')                    # カーソルの移動だけ（字は変わらない）
        self.assertEqual(self.f.source(), before)
        for ch in 'かいぎ':                              # 確定の字が1字ずつ届く
            self.root.tk.call('tk::TextInsert', ed._w, ch)
            got = self.same('確定 ' + ch)
        self.assertIn('かいぎ', got.split('\n')[2])

    def test_one_read_per_generation(self):
        f, ed = self.f, self.f.editor
        reads = []
        real_get = ed.get
        def counting(*a):
            if a == ('1.0', 'end-1c'):
                reads.append(a)
            return real_get(*a)
        ed.get = counting
        self.add_rec(3, '三の元')
        for _ in range(40):
            f.source()
        self.assertLessEqual(len(reads), 1, len(reads))
        ed.insert('end', 'あ')
        n = len(reads)
        for _ in range(40):
            f.source()
        self.assertLessEqual(len(reads) - n, 1, len(reads) - n)
        self.assertEqual(f.source(), f.plain())
        with mock.patch.dict(os.environ, {'CN_SOURCE_TEXT_CACHE': '0'}):
            n = len(reads)
            for _ in range(5):
                f.source()
            self.assertEqual(len(reads) - n, 5)          # 前の形: 毎回読む

    def test_the_records_are_asked_every_time(self):
        f = self.f
        f.source(); n = f.live_calls
        f.source(); f.source()
        self.assertEqual(f.live_calls - n, 2)            # 片付けの働き（控えを落とす）は今までどおり毎回


if __name__ == '__main__':
    unittest.main()
