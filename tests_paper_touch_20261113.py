# -*- coding: utf-8 -*-
"""背景の絵（paper_window）の後ろの Canvas が、タッチの1本指のなぞり（パンのジェスチャー）を本文の欄のホイールに
変えて送る（2026-11-13 うにさん「タッチモニター1本指でスクロールができなくなっている。背景イラストの影響と思われる」）。

透かした画素のタッチは OS が後ろの Canvas へ渡す。前はマウスの知らせだけを本文の欄へ送り直していたので、なぞりは
Canvas で止まり、本文はスクロールしなかった。タッチの元の知らせ（WM_POINTER*）は PostMessage で送り直せない
（ERROR_INVALID_MESSAGE）ので、Canvas でパン（WM_GESTURE・GID_PAN）を受け、指の縦の動きをホイールにして送る。

本物のタッチは使わない（作ったジェスチャーの知らせは OS が受け付けない: WM_GESTURE の lParam は OS の持つ
ハンドル）。ここで確かめるのは、指の動き→ホイールの量の換算（向き・端数の持ち越し）、切り替え、
この試験の窓の中で Canvas から本文の欄へホイールが届くこと（ホイールは前から送り直していた道）。
"""
import sys
import unittest

import paper_window


class PanToWheel(unittest.TestCase):
    def test_direction_and_amount(self):
        px = paper_window.PAN_WHEEL_PX
        # 指を上へ（y が減る）＝本文を下へ送る＝ホイールの負の量
        self.assertEqual(paper_window.pan_wheel(500, 500 - px, 0.0), (-120, 0.0))
        self.assertEqual(paper_window.pan_wheel(500, 500 + px, 0.0), (120, 0.0))
        self.assertEqual(paper_window.pan_wheel(500, 500, 0.0), (0, 0.0))

    def test_slow_pan_keeps_the_remainder(self):
        # 1画素ずつ動いても、端数を持ち越して止まらない。送るのは1目盛り（120）の倍数だけ
        # （本体は 120 未満の量を、下へは1行・上へは0行に丸める）
        px = paper_window.PAN_WHEEL_PX
        for step in (-1, 1):
            total, rest, y, sent = 0, 0.0, 300, []
            for _ in range(px * 2):
                delta, rest = paper_window.pan_wheel(y, y + step, rest)
                if delta:
                    sent.append(delta)
                total += delta
                y += step
            self.assertEqual(total, 240 * step)
            self.assertTrue(all(abs(d) % 120 == 0 for d in sent), sent)

    def test_switch(self):
        self.assertTrue(paper_window.touch_enabled({}))
        self.assertFalse(paper_window.touch_enabled({'CN_PAPER_TOUCH': '0'}))

    @unittest.skipUnless(sys.platform == 'win32' and paper_window.available(), 'Windows 8 以降の窓が要る')
    def test_back_canvas_still_forwards_the_wheel_to_the_text(self):
        import ctypes
        import ctypes.wintypes as wt
        import tkinter as tk
        root = tk.Tk()
        try:
            root.geometry('300x200+0+0')
            back = tk.Canvas(root, highlightthickness=0)
            back.place(x=0, y=0, relwidth=1, relheight=1)
            text = tk.Text(root)
            text.place(x=0, y=0, relwidth=1, relheight=1)
            root.update()
            api = paper_window._load()
            self.assertIsNotNone(api)
            _c, user32, comctl = api
            self.assertTrue(hasattr(user32, 'GetGestureInfo'))
            got = []
            PROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wt.HWND, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t,
                                      ctypes.c_size_t, ctypes.c_size_t)

            def record(hwnd, msg, wparam, lparam, uid, data):
                if msg == paper_window.WM_MOUSEWHEEL:
                    got.append(ctypes.c_short((wparam >> 16) & 0xFFFF).value)
                    return 0
                return comctl.DefSubclassProc(hwnd, msg, wparam, lparam)
            recorder = PROC(record)
            text_hwnd, back_hwnd = int(text.winfo_id()), int(back.winfo_id())
            self.assertTrue(comctl.SetWindowSubclass(text_hwnd, recorder, 0x5445, 0))
            try:
                self.assertTrue(paper_window.attach_back(back_hwnd, text_hwnd))
                user32.PostMessageW(back_hwnd, paper_window.WM_MOUSEWHEEL, (ctypes.c_ushort(-120).value) << 16, 0)
                for _ in range(20):
                    root.update()
                self.assertEqual(got, [-120])
            finally:
                paper_window.detach_back(back_hwnd)
                comctl.RemoveWindowSubclass(text_hwnd, recorder, 0x5445)
        finally:
            root.destroy()


if __name__ == '__main__':
    unittest.main()
