# -*- coding: utf-8 -*-
"""タブを替えた時、品詞のフォントは表示の位置を戻してから、見えている行に1回だけ塗る（2026-11-22・軽量化）。前は本文を
入れた所で1行目からの行を塗り、位置を戻した所でまた塗っていた（戻した先が1行目でなければ最初の塗りは捨てる仕事。
200行のタブへ戻る本体の時間 278ms → 156ms）。塗った結果（見えている行のフォント）は同じ。CN_TAB_PAINT_AFTER_VIEW=0 で
前の形。作った例文だけ。run_on_desktop で回す。"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

CHILD = r'''
import json, os, sys, time, traceback
from pathlib import Path
def main():
    here = Path.cwd().resolve()
    assert not (here / 'vocabulary.json').exists()
    import tkinter as tk
    from unittest.mock import Mock, patch
    import app, boundary_colors as BC
    from session import new_tab
    # 作った文は紫にならない自然な文にする（2026-11-23: 前の「確認する作った文」は不自然で1行ごとに補正の探索が走り、子が
    # 1行に約4.5秒かかって、解析の済みを待つ所で最長200秒を使い切り、ファイルごと回すと子が時間切れになっていた。
    # 自然な文なら1行約0.6秒）
    big = chr(10).join('%d行目は会議の資料を確認するための作った文です。' % i for i in range(1, 61))
    small = chr(10).join('別のタブの%d行目です。' % i for i in range(1, 6))
    (here / 'settings.json').write_text(json.dumps(dict(layout='split', input_method='kana', input_method_auto=False)), encoding='utf-8')
    (here / 'session.json').write_text(json.dumps(dict(version=1, active=0, tabs=[new_tab(text=big), new_tab(text=small)]), ensure_ascii=False), encoding='utf-8')
    root = tk.Tk(); errors = []
    root.report_callback_exception = lambda *e: errors.append(''.join(traceback.format_exception(*e)))
    def pump(s):
        end = time.monotonic() + s
        while time.monotonic() < end:
            root.update(); time.sleep(0.003)
    out = {}
    with patch.object(app, 'GlobalHotkeys', return_value=Mock()), patch.object(app.CorrectNoteApp, '_learn_now', lambda *a: None), \
            patch.object(app.CorrectNoteApp, '_first_run_setup', lambda *a: None):
        a = app.CorrectNoteApp(root)
        root.geometry('1100x700+40+40')
        ed = a.editor
        end = time.monotonic() + 200
        while time.monotonic() < end:
            pump(1.0)
            todo = getattr(a, '_analyze_todo', None) or ()
            if todo and a._analyze_pos >= len(todo) and a._async_request is None:
                break
        ed.mark_set('insert', '50.0'); ed.yview('40.0'); pump(1.0)
        a._switch_tab(1); pump(2.0)
        rows = []
        real = BC.BoundaryColors.paint_row
        def counted(self, row, bare=False, draw=True):
            import traceback as _tb
            if any(f.name == '_paint_visible_now' for f in _tb.extract_stack()[-6:]):   # 見えている行の塗り（裏の全部の行の塗りは数えない）
                rows.append((self.widget is ed, row))
            return real(self, row, bare, draw)
        BC.BoundaryColors.paint_row = counted
        a._switch_tab(0)
        pump(1.0)                                    # 補正欄は少し後に描く（split_right_later）
        BC.BoundaryColors.paint_row = real
        top = int(ed.index('@0,0').split('.')[0])
        out['top'] = top
        out['rows_far_above'] = sum(1 for left, r in rows if left and r < top - 10)            # 位置を戻す前の1行目あたりの塗り
        rtop = int(a.result_view.index('@0,0').split('.')[0])
        out['rtop'] = rtop
        out['right_far_above'] = sum(1 for left, r in rows if not left and r < rtop - 10)
        pump(1.5)
        bottom = int(ed.index('@0,%d' % (ed.winfo_height() - 1)).split('.')[0])
        last = int(ed.index('end-1c').split('.')[0])
        names = [str(t) for t in ed.tag_names() if str(t).startswith('pos_font')]
        texts = [r for r in range(top, min(bottom, last) + 1) if ed.get('%d.0' % r, '%d.end' % r).strip()]
        out['painted_visible'] = sum(1 for r in texts if any(ed.tag_nextrange(t, '%d.0' % r, '%d.end' % r) for t in names))
        out['visible'] = len(texts)
        out['errors'] = errors
        open('child_out.json', 'w', encoding='utf-8').write(json.dumps(out, ensure_ascii=False))
        os._exit(0)
if __name__ == '__main__':
    try:
        main()
    except Exception:
        open('child_out.json', 'w', encoding='utf-8').write(json.dumps({'error': traceback.format_exc()}))
        os._exit(1)
'''


def run_child(case, env_extra=None):
    here = Path(__file__).resolve().parent
    if here == Path(r'C:\CorrectNote') or (here / 'vocabulary.json').exists():
        case.skipTest('写しの中で回す')
    d = Path(tempfile.mkdtemp(prefix='cn-tabpaint-'))
    for e in here.iterdir():
        if e.is_file() and e.name not in ('settings.json', 'session.json', 'vocabulary.json', 'last_choice.json'):
            shutil.copy2(e, d / e.name)
    (d / 'zz_child.py').write_text(CHILD, encoding='utf-8')
    env = dict(os.environ); env.pop('PYTHONPATH', None); env.update(env_extra or {})
    subprocess.run([sys.executable, '-B', '-X', 'utf8', 'zz_child.py'], cwd=d, env=env, timeout=300,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    got = json.loads((d / 'child_out.json').read_text(encoding='utf-8'))
    shutil.rmtree(d, ignore_errors=True)
    case.assertNotIn('error', got, got.get('error'))
    return got


class InTheApp(unittest.TestCase):
    def test_paint_once_after_the_view(self):
        got = run_child(self)
        self.assertEqual(got['errors'], [], got)
        self.assertGreater(got['top'], 20, got)                                  # 戻した先は1行目ではない
        self.assertEqual(got['rows_far_above'], 0, got)                          # 1行目あたりを塗る捨て仕事が無い
        self.assertGreater(got['rtop'], 20, got)
        self.assertEqual(got['right_far_above'], 0, got)                         # 補正欄も
        self.assertEqual(got['painted_visible'], got['visible'], got)            # 見えている行は塗ってある

    def test_switch_back(self):
        got = run_child(self, {'CN_TAB_PAINT_AFTER_VIEW': '0', 'CN_RESTORE_SCROLL_PAINT_ONCE': '0'})   # 前の形（11-23 の直しも切る）
        self.assertGreater(got['rows_far_above'], 0, got)                        # 前の形: 1行目あたりも塗っていた
        self.assertGreater(got['right_far_above'], 0, got)


    def test_switch_back_restore_paint(self):
        # 位置を戻す間の塗りを止めない形（CN_RESTORE_SCROLL_PAINT_ONCE=0）: 戻す途中の補正欄の位置で、見えない上の行を塗っていた
        got = run_child(self, {'CN_RESTORE_SCROLL_PAINT_ONCE': '0'})
        self.assertGreater(got['right_far_above'], 0, got)


if __name__ == '__main__':
    unittest.main()
