# -*- coding: utf-8 -*-
"""解析の子が働いている間は、オンマウスの一覧を出さない（2026-11-22・うに 11-21 16:55Z「文字を打ってると応答がなくなる。
右の補正欄が空欄になって動かないが待つと動く」）。オンマウスの一覧は解析の子に作らせ、子が忙しいと本体が最大8秒＋待っていた。
CN_HOVER_SKIP_WHEN_BUSY=0 で前の形。Tk の窓は作らない（作り物のアプリ）。"""
import os
import unittest
from types import SimpleNamespace as NS
from unittest import mock

import auto_candidates as AC
import analysis_async


def fake_app(pending=False, request=None, background=None):
    return NS(_foreground_analysis_pending=lambda: pending, _async_request=request, _async_background_request=background,
              _closing=False)


class AnalysisBusy(unittest.TestCase):
    def test_busy_while_analysis_waits_or_child_works(self):
        with mock.patch.object(analysis_async, 'child_alive', lambda app: True):
            # 2026-11-22 うにさん「オンマウスしても候補が出ません」（CN_HOVER_ASYNC）: 解析が待っているだけなら出してよい
            # （子が空いていれば答えはすぐ返る）。子が実際に解いている間だけ出さない
            self.assertFalse(AC.analysis_busy(fake_app(pending=True)))
            with mock.patch.dict(os.environ, {'CN_HOVER_ASYNC': '0'}):
                self.assertTrue(AC.analysis_busy(fake_app(pending=True)))             # 前の形: 解析が待っている間は出さない
            self.assertTrue(AC.analysis_busy(fake_app(request=(('line',), None))))     # 子が他を解いている
            self.assertFalse(AC.analysis_busy(fake_app()))                           # 空いている
        with mock.patch.object(analysis_async, 'child_alive', lambda app: False):
            self.assertTrue(AC.analysis_busy(fake_app()))                            # 子がいない（作り直すと待つ）

    # 次の2件は前の形（CN_HOVER_ASYNC=0: 子が働いている間は出さず、行と行の間に出す）。2026-11-22 から既定は、子への頼みを
    # 待たずに出す形（tests_hover_async_20261122）
    @mock.patch.dict(os.environ, {'CN_HOVER_ASYNC': '0'})
    def test_hover_show_does_not_ask_the_child_while_busy(self):
        app = fake_app(request=(('line',), 1))
        app.root = NS(after=lambda ms, fn: 'job', after_cancel=lambda job: None)
        asked = []
        with mock.patch.object(AC, 'hover_on', lambda app: True), mock.patch.object(AC, 'busy', lambda app, w: False), \
                mock.patch.object(analysis_async, 'ask_child', lambda *a, **k: asked.append(1)), \
                mock.patch.object(AC, '_hit', lambda *a: asked.append('hit')):
            self.assertFalse(AC.hover_show(app, object(), ('editor', 1, 0, 1, 'x'), dict(x=0, y=0, x_root=0, y_root=0)))
        self.assertEqual(asked, [])                                                  # 語も探さず、子にも尋ねない

    def test_waiting_hover_runs_between_rows(self):
        # 打った直後（1秒たつまで）は作らずに待ちの印を立て、子が1行を解き終えて次を頼む前（run_waiting_hover）に見直す
        # （2026-11-22・CN_HOVER_TYPED_QUIET。子が今の行を解いている間は見直さない）
        import time as _time
        app = fake_app(request=(('line',), 1))
        app._last_edit_at = _time.monotonic()
        app.root = NS(after=lambda ms, fn: 'job', after_cancel=lambda job: None)
        shown = []
        with mock.patch.object(AC, 'hover_on', lambda app: True), mock.patch.object(AC, 'busy', lambda app, w: False), \
                mock.patch.object(analysis_async, 'child_alive', lambda app: True), \
                mock.patch.object(AC, '_hit', lambda *a: None):
            AC.hover_show(app, 'w', ('editor', 1, 0, 1, 'x'), dict(x=0, y=0, x_root=0, y_root=0))
            self.assertIsNotNone(getattr(app, '_hover_waiting', None))               # 待ちの印
            self.assertFalse(AC.run_waiting_hover(app))                             # まだ子が解いている
            app._async_request = None                                               # 1行を解き終えた
            with mock.patch.object(AC, 'hover_show', lambda *a, **k: shown.append(k) or True):
                self.assertTrue(AC.run_waiting_hover(app))
        self.assertEqual(shown, [dict(between_rows=True, idle_child=True)])     # 行と行の間は本体で待つ形（CN_HOVER_ASK_NO_SUPERSEDE）
        self.assertIsNone(app._hover_waiting)

    def test_switch_back(self):
        with mock.patch.dict(os.environ, {'CN_HOVER_SKIP_WHEN_BUSY': '0'}):
            self.assertFalse(AC.analysis_busy(fake_app(pending=True)))


if __name__ == '__main__':
    unittest.main()
