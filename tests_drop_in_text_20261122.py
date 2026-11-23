# -*- coding: utf-8 -*-
"""外の窓からドラッグした文字を、落とした所へ取り込む（2026-11-21 17:20Z うにさん「ブラウザの文字をドラッグして、アプリ本体か
簡易入力にドロップしたら、取り込む」・drop_in）。本物のドラッグはせず、OLE の受け口（IDropTarget）の DragEnter・DragOver・
Drop を vtable から直接呼ぶ。渡す字は drag_out の IDataObject（CF_UNICODETEXT）。CN_DROP_IN_TEXT=0 で前の形。
作った例文だけ。tools_local/run_on_desktop.py で回す。"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

CHILD = r'''
import json, os, sys, time, traceback, ctypes
from ctypes import wintypes as W
from pathlib import Path
def main():
    here = Path.cwd().resolve()
    assert not (here / 'vocabulary.json').exists()
    import tkinter as tk
    from unittest.mock import Mock, patch
    import app, drop_in, drag_out
    from session import new_tab
    body = chr(10).join(['一行目の本文です。', '二行目です', '三行目'])
    (here / 'settings.json').write_text(json.dumps(dict(layout='split', input_method='kana', input_method_auto=False)), encoding='utf-8')
    (here / 'session.json').write_text(json.dumps(dict(version=1, active=0, tabs=[new_tab(text=body)]), ensure_ascii=False), encoding='utf-8')
    root = tk.Tk(); errors = []
    root.report_callback_exception = lambda *e: errors.append(''.join(traceback.format_exception(*e)))
    def pump(s):
        end = time.monotonic() + s
        while time.monotonic() < end:
            root.update(); time.sleep(0.005)
    out = {}
    with patch.object(app, 'GlobalHotkeys', return_value=Mock()), patch.object(app.CorrectNoteApp, '_learn_now', lambda *a: None), \
            patch.object(app.CorrectNoteApp, '_first_run_setup', lambda *a: None):
        a = app.CorrectNoteApp(root)
        root.geometry('1000x500+-4000+40')
        pump(3)
        targets = getattr(a, '_text_drop_targets', None) or {}
        out['registered'] = sorted(targets)
        if not targets:
            open('child_out.json', 'w', encoding='utf-8').write(json.dumps(out, ensure_ascii=False)); os._exit(0)
        ed, rv = a.editor, a.result_view
        P = ctypes.c_int64
        def vt(target, index, *types):
            vtbl = ctypes.cast(ctypes.cast(target.pointer, ctypes.POINTER(ctypes.c_void_p))[0], ctypes.POINTER(ctypes.c_void_p))
            return drag_out._proto(*types)(vtbl[index])
        def pt(widget, index):
            widget.see(index); root.update_idletasks()
            x, y, w_, h = widget.bbox(index)
            sx, sy = widget.winfo_rootx() + x + 1, widget.winfo_rooty() + y + 2
            return ctypes.c_int64(((sy & 0xFFFFFFFF) << 32) | (sx & 0xFFFFFFFF)).value
        def drag(name, widget, index, text, drop=True):
            target = targets[name][1]
            data = drag_out.DataObject(text)
            eff = W.DWORD(0)
            point = pt(widget, index)                     # 位置は先に（Tk を呼ぶ所は測らない）
            t = time.perf_counter()
            vt(target, 3, ctypes.c_void_p, W.DWORD, P, ctypes.POINTER(W.DWORD))(target.pointer, data.pointer, 1, point, ctypes.byref(eff))
            vt(target, 4, W.DWORD, P, ctypes.POINTER(W.DWORD))(target.pointer, 1, point, ctypes.byref(eff))
            calls = time.perf_counter() - t
            effect_over = eff.value
            pump(1.2)                                   # ふだんの時計は1秒ごと（上に来たのを見てから速める）
            shown = str(ed.index('insert'))
            if drop:
                point = pt(widget, index)
                t = time.perf_counter()
                vt(target, 6, ctypes.c_void_p, W.DWORD, P, ctypes.POINTER(W.DWORD))(target.pointer, data.pointer, 0, point, ctypes.byref(eff))
                calls += time.perf_counter() - t
                t = time.perf_counter(); pump(0.3)
            else:
                vt(target, 5)(target.pointer)
                pump(0.15)
            return dict(effect=effect_over, shown=shown, ole_calls_ms=round(calls * 1000, 2))
        def _undo(w):
            w.event_generate('<<Undo>>'); pump(0.15)      # Ctrl+Z と同じ道（TabUndo）
            return True
        ed.mark_set('insert', '3.end')
        r = drag('editor', ed, '1.2', '取り込む字')
        out['editor'] = r
        out['line1'] = ed.get('1.0', '1.end')
        out['insert_after'] = str(ed.index('insert'))
        _undo(ed)
        out['undone'] = ed.get('1.0', '1.end')
        r = drag('editor', ed, '2.1', 'A' + chr(9) + 'B' + chr(12288) + 'C' + chr(10) + '次の行')
        out['multi'] = ed.get('2.0', '3.end')
        out['multi_undo'] = _undo(ed)
        r = drag('result', rv, '2.2', '右から')
        out['from_result'] = ed.get('2.0', '2.end')
        out['result_undo'] = _undo(ed)
        ed.mark_set('insert', '3.end')
        r = drag('editor', ed, '1.3', '入れない', drop=False)
        out['leave_line1'] = ed.get('1.0', '1.end')
        out['leave_insert'] = str(ed.index('insert'))
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
    if sys.platform != 'win32':
        case.skipTest('Windows だけ')
    d = Path(tempfile.mkdtemp(prefix='cn-dropin-'))
    for e in here.iterdir():
        if e.is_file() and e.name not in ('settings.json', 'session.json', 'vocabulary.json', 'last_choice.json'):
            shutil.copy2(e, d / e.name)
    (d / 'zz_child.py').write_text(CHILD, encoding='utf-8')
    env = dict(os.environ); env.pop('PYTHONPATH', None); env.update(env_extra or {})
    subprocess.run([sys.executable, '-B', '-X', 'utf8', 'zz_child.py'], cwd=d, env=env, timeout=240,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    got = json.loads((d / 'child_out.json').read_text(encoding='utf-8'))
    shutil.rmtree(d, ignore_errors=True)
    case.assertNotIn('error', got, got.get('error'))
    return got


class InTheApp(unittest.TestCase):
    def test_drop_text_from_outside(self):
        got = run_child(self)
        self.assertEqual(got['errors'], [], got)
        self.assertEqual(got['registered'], ['editor', 'result'], got)
        self.assertEqual(got['editor']['effect'], 1, got)                       # DROPEFFECT_COPY
        self.assertEqual(got['editor']['shown'], '1.2', got)                    # ドラッグ中は落とす所にカーソル
        self.assertEqual(got['line1'], '一行取り込む字目の本文です。', got)       # 落とした所へ
        self.assertEqual(got['insert_after'], '1.7', got)
        self.assertEqual(got['undone'], '一行目の本文です。', got)               # 1回の「元に戻す」で戻る
        self.assertEqual(got['multi'], '二A' + chr(9) + 'B' + chr(12288) + 'C' + chr(10) + '次の行行目です', got)   # 改行・タブ・全角空白そのまま
        self.assertEqual(got['from_result'], '二行右から目です', got)            # 補正欄に落とした時はメモ欄の同じ行・位置へ
        self.assertEqual(got['leave_line1'], '一行目の本文です。', got)          # 落とさずに出たら入れない
        self.assertEqual(got['leave_insert'], '3.3', got)                       # カーソルも元へ
        self.assertLess(got['editor']['ole_calls_ms'], 20, got)                 # OLE の手続きは積むだけ（主スレッドを塞がない）

    def test_switch_off(self):
        got = run_child(self, {'CN_DROP_IN_TEXT': '0'})
        self.assertEqual(got['registered'], [], got)


if __name__ == '__main__':
    unittest.main()
