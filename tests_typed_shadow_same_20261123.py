# -*- coding: utf-8 -*-
"""「打った」印の突き合わせ（_mark_typed_from_shadow）は、前に突き合わせた時から字が変わっていなければ読まない（2026-11-23
CN_TYPED_SHADOW_SAME・うにさんの記録で、確定の1回に約 2,500 回呼ばれ、そのたびに文書の全体を写して行に割っていた）。
・付く印は前の形（CN_TYPED_SHADOW_SAME=0）と同じ: 打つ・消す・改行・置き換える・まとめての書き換え・IME の確定の道
・字が変わっていない間は Text を読まない。影が差し替わった（_sync_typed_shadow）時は読む
自分の Text の窓だけ・作った文。"""
import os
import tkinter as tk
import unittest
from unittest import mock

import analysis_work
import app


class Fake:
    TYPED_TAG = app.CorrectNoteApp.TYPED_TAG

    def __init__(self, root, body):
        self.editor = tk.Text(root, undo=True)
        analysis_work.observe_text(self.editor)
        self.editor.insert('1.0', body)
        self._typed_shadow = None

    _sync_typed_shadow = app.CorrectNoteApp._sync_typed_shadow
    _changed_span = staticmethod(app.CorrectNoteApp._changed_span)

    def mark(self):
        return app.CorrectNoteApp._mark_typed_from_shadow(self)

    def ranges(self):
        return [str(x) for x in self.editor.tag_ranges(self.TYPED_TAG)]


BODY = '\n'.join('%d行目は会議の資料を確認するための作った文です。' % i for i in range(1, 40))


class TypedShadowSame(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.a = Fake(self.root, BODY)      # 控えあり
        self.b = Fake(self.root, BODY)      # 前の形
        self.both(lambda f: f.mark())

    def both(self, fn):
        fn(self.a)
        with mock.patch.dict(os.environ, {'CN_TYPED_SHADOW_SAME': '0'}):
            fn(self.b)

    def step(self, fn, note):
        self.both(fn)
        self.both(lambda f: f.mark())
        self.both(lambda f: f.mark())                       # 2回目（字は変わっていない）
        self.assertEqual(self.a.ranges(), self.b.ranges(), note)
        self.assertEqual(self.a._typed_shadow, self.b._typed_shadow, note)

    def test_marks_equal_the_previous_form(self):
        self.step(lambda f: f.editor.insert('3.4', 'あいう'), '打つ')
        self.step(lambda f: f.editor.delete('5.0', '5.3'), '消す')
        self.step(lambda f: f.editor.insert('7.end', '\n新しい行'), '改行')
        self.step(lambda f: f.editor.replace('9.0', '9.2', 'XYZ'), '置き換える')
        def bulk(f):
            with analysis_work.bulk_edits(f.editor):
                f.editor.replace('11.0', '11.end', 'まとめて書き換えた行')
        self.step(bulk, 'まとめての書き換え')
        self.step(lambda f: self.root.tk.call('tk::TextInsert', f.editor._w, '確定'), 'IME の確定の道')
        self.assertTrue(self.a.ranges())

    def test_no_read_while_unchanged(self):
        f = self.a
        reads = []
        real_get = f.editor.get
        def counting(*args):
            if args == ('1.0', 'end-1c'):
                reads.append(args)
            return real_get(*args)
        f.editor.get = counting
        f.mark()
        n = len(reads)
        for _ in range(50):
            f.mark()
        self.assertEqual(len(reads) - n, 0)
        f.editor.insert('2.0', 'い')
        f.mark()
        self.assertEqual(len(reads) - n, 1)                 # 変わったら読む
        self.assertIn('2.0', f.ranges())
        f._sync_typed_shadow()                               # 影が差し替わった
        n = len(reads)
        f.mark()
        self.assertEqual(len(reads) - n, 1)
        with mock.patch.dict(os.environ, {'CN_TYPED_SHADOW_SAME': '0'}):
            n = len(reads)
            for _ in range(3):
                f.mark()
            self.assertEqual(len(reads) - n, 3)              # 前の形: 毎回読む


if __name__ == '__main__':
    unittest.main()
