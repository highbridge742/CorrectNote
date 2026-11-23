# -*- coding: utf-8 -*-
"""v1.20.0 のデバッグメニュー（2026-11-23 うにさん）。
「デバッグメニューから俯瞰の項目を削除し、チェックオンとして以降処理します。行の状態と、解析の記録のボタンもリリースでは
消してください。このボタンは開発のほうは残します」。画面は使わない（決まりと、デバッグメニューの作りの文字だけを見る）。"""
import ast
import os
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent


class ReleaseButtons(unittest.TestCase):
    def test_overview_item_removed_and_always_on(self):
        import overview_fast as O

        class App:
            settings = {'overview_fast': False}       # 前に切って保存した人も速い形
        self.assertTrue(O.enabled(App(), {}))
        self.assertFalse(O.enabled(App(), {'CN_OVERVIEW_FAST': '0'}))
        src = (HERE / 'debug_menu.py').read_text(encoding='utf-8')
        self.assertNotIn('を速い形で出す', src)
        self.assertNotIn("settings.set('overview_fast'", src)

    def test_row_state_button_only_in_development(self):
        import row_state as RS
        self.assertTrue(RS.enabled({}, frozen=False))
        self.assertFalse(RS.enabled({}, frozen=True))
        self.assertFalse(RS.enabled({'CN_ROW_STATE_TOOL': '0'}, frozen=False))
        self.assertTrue(RS.enabled({'CN_ROW_STATE_TOOL': '1'}, frozen=True))

    def test_freeze_log_only_in_development(self):
        # 固まりの記録（freeze_log.txt）もリリース（EXE）では取らない
        # 2026-11-24 から開発の PC の印（freeze_log.enable）がある時だけ。公開のリポジトリ・試験の写しには印が無い
        import tempfile
        import freeze_log as F
        with tempfile.TemporaryDirectory() as d:
            self.assertFalse(F.enabled({}, frozen=False, folder=d))        # 印が無い（公開・試験の写し）
            open(os.path.join(d, F.MARKER), 'w').close()
            self.assertTrue(F.enabled({}, frozen=False, folder=d))         # 開発の PC
            self.assertFalse(F.enabled({}, frozen=True, folder=d))         # EXE
        self.assertFalse(F.enabled({'CN_FREEZE_LOG': '0'}, frozen=False))
        self.assertTrue(F.enabled({'CN_FREEZE_LOG': '1'}, frozen=True))

    def test_other_logs_off_in_release(self):
        # 解析のやり直し・表示準備中・俯瞰の記録（app.redo_trace_on）と、デバッグの道具（debug_tools_on）は EXE では切り
        src = (HERE / 'app.py').read_text(encoding='utf-8')
        tree = ast.parse(src)
        ns = {'os': os, 'sys': __import__('sys')}
        funcs = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in ('redo_trace_on', 'debug_tools_on')]
        exec(compile(ast.Module(body=funcs, type_ignores=[]), 'app.py', 'exec'), ns)
        self.assertFalse(ns['redo_trace_on']({}, True))
        self.assertTrue(ns['redo_trace_on']({}, False))
        saved = os.environ.pop('CN_DEBUG_TOOLS', None)
        try:
            self.assertFalse(ns['debug_tools_on']())
        finally:
            if saved is not None:
                os.environ['CN_DEBUG_TOOLS'] = saved

    def test_trace_button_only_in_development(self):
        # 「解析の記録…」は frozen でない時（か CN_DEBUG_TOOLS=1）だけ出す
        src = (HERE / 'debug_menu.py').read_text(encoding='utf-8')
        tree = ast.parse(src)
        found = []
        for node in ast.walk(tree):
            if isinstance(node, ast.If) and '解析の記録…' in ast.get_source_segment(src, node):
                test = ast.get_source_segment(src, node.test)
                if 'frozen' in test:
                    found.append(test)
        self.assertTrue(found)
        self.assertTrue(any("CN_DEBUG_TOOLS" in t and 'not getattr' in t for t in found), found)


if __name__ == '__main__':
    unittest.main()
