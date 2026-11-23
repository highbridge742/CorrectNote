# -*- coding: utf-8 -*-
"""タブを戻した後の左右の行のそろいを守る試験（2026-11-23）。見えている行の解析と品詞のフォントが済むまで待ってから
（決まった時間ではなく）、大きいタブ・小さいタブ・統合へ戻した後・素早く続けて替えた後・ホイールの直後で、
・見えている行の左右のずれが残らない（ずれ0行。解析がフォントを付けている最中の一瞬のずれは、落ち着くまで待つ）
・解析の済んだ見えている行には品詞のフォントが付いている（塗り漏れ0）
・表示・カーソルの位置が、今夜の直しを切った形（CN_TAB_PAINT_AFTER_VIEW=0・CN_DISK_CACHE_ONE_TAB=0）と同じ
を見る。

★ CN_RENDER_PAINT_BEFORE_ALIGN=1（補正欄のフォントを、左右の高さをそろえる前に付ける形）は見ない。その形では、
見えている行の解析が済んだ大きいタブ（分割・400行）へ戻ると、左右の高さが6行ずれたまま5秒たっても残った（既定の形は
0行）。フォントが付く前の姿を比べていたので、はじめは「ずれ0行」と誤って測っていた（2026-11-23）。そのため既定は切り。
作った文だけ。run_on_desktop で回す。"""
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
    import app
    from session import new_tab
    rows = int(os.environ.get('ROWS', '400'))
    words = ['会議', '資料', '確認', '連絡', '予定', '作業', '準備', '報告', '検討', '変更']
    big = chr(10).join('%d行目は%sの%sを%sするための作った文です。' % (i + 1, words[i % 10], words[(i * 3 + 1) % 10],
                       words[(i * 7 + 2) % 10]) if i % 9 else '' for i in range(rows))
    small = chr(10).join('別のタブの%d行目です。' % i for i in range(1, 40))
    (here / 'settings.json').write_text(json.dumps(dict(layout=os.environ.get('LAYOUT', 'split'), input_method='kana',
                                                        input_method_auto=False)), encoding='utf-8')
    (here / 'session.json').write_text(json.dumps(dict(version=1, active=0, tabs=[new_tab(text=big), new_tab(text=small)]),
                                                  ensure_ascii=False), encoding='utf-8')
    root = tk.Tk(); errors = []
    root.report_callback_exception = lambda *e: errors.append(''.join(traceback.format_exception(*e))[-500:])
    def pump(s):
        end = time.monotonic() + s
        while time.monotonic() < end:
            root.update(); time.sleep(0.003)
    out = {}
    with patch.object(app, 'GlobalHotkeys', return_value=Mock()), patch.object(app.CorrectNoteApp, '_learn_now', lambda *a: None), \
            patch.object(app.CorrectNoteApp, '_first_run_setup', lambda *a: None):
        a = app.CorrectNoteApp(root)
        root.geometry('1300x900+40+40')
        pump(6)
        ed, rv = a.editor, a.result_view
        unified = a._layout_is_unified()
        def around(bad_rows):
            if not bad_rows:
                return []
            first = bad_rows[0]['row']
            got = []
            ne = [str(t) for t in ed.tag_names() if str(t).startswith(('pos_font', 'navigation', 'cn_', 'end_rule', 'ws_', 'paired_row_pad_'))]
            nr = [str(t) for t in rv.tag_names() if str(t).startswith(('pos_font', 'navigation', 'cn_', 'end_rule', 'ws_', 'paired_row_pad_'))]
            for r in range(first - 4, first + 1):
                d1, d2 = ed.dlineinfo('%d.0' % r), rv.dlineinfo('%d.0' % r)
                got.append(dict(row=r, e=list(d1) if d1 else None, r=list(d2) if d2 else None,
                                etags=sorted(t for t in ne if ed.tag_nextrange(t, '%d.0' % r, '%d.0 lineend+1c' % r)),
                                rtags=sorted(t for t in nr if rv.tag_nextrange(t, '%d.0' % r, '%d.0 lineend+1c' % r)),
                                elen=len(ed.get('%d.0' % r, '%d.end' % r)), rlen=len(rv.get('%d.0' % r, '%d.end' % r))))
            return got

        def state():
            top = int(ed.index('@0,0').split('.')[0])
            bad = 0
            bad_rows = []
            fonts = 0
            names = [str(t) for t in rv.tag_names() if str(t).startswith('pos_font')]
            for r in range(top, top + 20):
                if not unified:
                    d1, d2 = ed.dlineinfo('%d.0' % r), rv.dlineinfo('%d.0' % r)
                    if d1 and d2 and abs(d1[1] - d2[1]) > 1:
                        bad += 1
                        names_e = [str(t) for t in ed.tag_names() if str(t).startswith('pos_font')]
                        bad_rows.append(dict(row=r, ey=d1[1], eh=d1[3], ry=d2[1], rh=d2[3],
                                             efont=any(ed.tag_nextrange(t, '%d.0' % r, '%d.end' % r) for t in names_e),
                                             rfont=any(rv.tag_nextrange(t, '%d.0' % r, '%d.end' % r) for t in names)))
                    res = a.line_results[r - 1] if 0 < r <= len(a.line_results or ()) else None
                    done = isinstance(res, dict) and not res.get('pending')        # 解析の済んだ行だけを数える（済んだかは時間次第）
                    if done and rv.get('%d.0' % r, '%d.end' % r).strip() and any(rv.tag_nextrange(t, '%d.0' % r, '%d.end' % r) for t in names):
                        fonts += 1
                    elif done and rv.get('%d.0' % r, '%d.end' % r).strip():
                        fonts -= 100                                                # 済んだ行なのにフォントが無い（塗り漏れ）
            d = ed.dlineinfo('insert')
            ins = int(ed.index('insert').split('.')[0])
            names_e2 = [str(t) for t in ed.tag_names() if str(t).startswith(('pos_font', 'paired_row_pad_'))]
            rows_seen = []
            for r in range(top, ins + 1):
                d3 = ed.dlineinfo('%d.0' % r)
                rows_seen.append((r, d3[3] if d3 else None, ''.join(t[-1] if t.startswith('paired') else 'f' for t in names_e2
                                                                     if ed.tag_nextrange(t, '%d.0' % r, '%d.0 lineend+1c' % r))[:3]))
            return dict(rows_seen=rows_seen, top=str(ed.index('@0,0')), insert=str(ed.index('insert')), insert_y=d[1] if d else None,
                        rtop=None if unified else str(rv.index('@0,0')), misaligned=bad, right_fonts=fonts, bad_rows=bad_rows[:6], around=around(bad_rows))
        ed.mark_set('insert', '%d.4' % (rows // 2)); ed.see('insert'); pump(1.0)
        # 見えている行の解析が済んで補正欄に品詞のフォントが付くまで待つ（決まった時間ではなく・比べる意味のある形）
        end = time.monotonic() + 60
        while time.monotonic() < end and not unified and state()['right_fonts'] < 5:
            pump(0.5)
        # 替える前にうにさんが見ていた位置: 左の欄にもフォントが付き終わって、カーソルの高さが1秒動かなくなるまで待つ
        last, still = None, time.monotonic()
        end = time.monotonic() + 30
        while time.monotonic() < end:
            got = state()
            key = (got['top'], got['insert_y'])
            if key != last:
                last, still = key, time.monotonic()
            elif time.monotonic() - still > 1.0:
                break
            pump(0.2)
        out['before'] = state()
        a._switch_tab(1); pump(1.5)
        a._switch_tab(0); pump(2.5)
        def settled():
            # 解析がフォントを付けている最中は一瞬ずれることがある: 残り続けるずれだけを見る（最長5秒・決まった時間ではなく）
            end2 = time.monotonic() + 5
            got = state()
            while time.monotonic() < end2 and got['misaligned']:
                pump(0.2)
                got = state()
            return got
        out['back'] = settled()
        for _ in range(3):                     # 素早く続けて替える
            a._switch_tab(1); pump(0.05)
            a._switch_tab(0); pump(0.05)
        pump(2.5)
        out['rapid'] = settled()
        a._on_wheel_units(-3); pump(0.05)      # ホイールの直後に替える
        a._switch_tab(1); pump(0.3)
        a._switch_tab(0); pump(2.5)
        out['after_wheel'] = settled()
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
    d = Path(tempfile.mkdtemp(prefix='cn-renderpaint-'))
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


class AfterSwitchingBack(unittest.TestCase):
    def check(self, got, layout):
        self.assertEqual(got['errors'], [], got)
        if layout == 'split':
            self.assertGreater(got['back']['right_fonts'], 0, got)        # 補正欄にフォントが付いた形で見ている
        for key in ('back', 'rapid', 'after_wheel'):
            self.assertEqual(got[key]['misaligned'], 0, (key, got))       # 左右のずれが残らない
            self.assertGreaterEqual(got[key]['right_fonts'], 0, (key, got))   # 解析の済んだ行の塗り漏れ0

    def test_split_big(self):
        self.check(run_child(self, {'LAYOUT': 'split', 'ROWS': '400'}), 'split')

    def test_split_small(self):
        self.check(run_child(self, {'LAYOUT': 'split', 'ROWS': '60'}), 'split')

    def test_unified_big(self):
        self.check(run_child(self, {'LAYOUT': 'unified', 'ROWS': '400'}), 'unified')

    def test_back_where_it_was(self):
        # 戻した後、カーソルの行が替える前と同じ高さに見える（上下に動いて見えない）
        got = run_child(self, {'LAYOUT': 'split', 'ROWS': '400'})
        print('PROBE', {k: (got[k]['top'], got[k]['insert_y'], got[k]['rows_seen']) for k in ('before', 'back')}, file=sys.stderr)
        self.check(got, 'split')
        for key in ('back', 'rapid'):
            self.assertEqual(got[key]['insert'], got['before']['insert'], (key, got))
            self.assertLessEqual(abs(got[key]['insert_y'] - got['before']['insert_y']), 12, (key, got))

    def test_back_where_it_was_switch(self):
        # CN_TAB_TOP_PIXELS=0（前の形）: 行の途中までのスクロールは行の頭へ揃えられ、カーソルの行が下がって見えた
        got = run_child(self, {'LAYOUT': 'split', 'ROWS': '400', 'CN_TAB_TOP_PIXELS': '0'})
        self.assertGreater(got['back']['insert_y'] - got['before']['insert_y'], 12, got)

    def test_same_place_as_without_tonights_tab_changes(self):
        # 今夜のタブの直し（位置を戻してから塗る・ディスクの控えはそのタブだけ）を切った形と、位置が同じ
        new = run_child(self, {'LAYOUT': 'split', 'ROWS': '400'})
        old = run_child(self, {'LAYOUT': 'split', 'ROWS': '400', 'CN_TAB_PAINT_AFTER_VIEW': '0', 'CN_DISK_CACHE_ONE_TAB': '0'})
        print('PROBE', {k: (new[k]['top'], new[k]['insert_y'], old[k]['top'], old[k]['insert_y'])
                        for k in ('before', 'back', 'rapid', 'after_wheel')}, file=sys.stderr)
        short = {k: dict(new=(new[k]['top'], new[k]['rtop'], new[k]['insert_y'], new[k]['misaligned'], new[k]['right_fonts']),
                         old=(old[k]['top'], old[k]['rtop'], old[k]['insert_y'], old[k]['misaligned'], old[k]['right_fonts']))
                 for k in ('before', 'back', 'rapid', 'after_wheel')}
        self.assertEqual(new['errors'] + old['errors'], [], short)
        for got in (new, old):
            for key in ('back', 'rapid', 'after_wheel'):
                self.assertEqual(got[key]['misaligned'], 0, (key, short))
        for key in ('back', 'rapid', 'after_wheel'):
            self.assertEqual(new[key]['insert'], old[key]['insert'], (key, short))
            if key == 'after_wheel':
                # ホイールの直後（0.05秒）に替えると、滑らかなスクロールの途中で位置を控えるので、どこまで進んでいたかは
                # その時の速さ次第（測り方の揺れ）。1行までの違いは見ず、左右の一番上が同じことだけを見る
                # （back・rapid は止まった位置から替えるので厳しく見る）
                for got in (new, old):
                    self.assertEqual(got[key]['top'], got[key]['rtop'], (key, short))
                self.assertLessEqual(abs(float(new[key]['top']) - float(old[key]['top'])), 1, (key, short))
                continue
            for field in ('top', 'rtop'):
                self.assertEqual(new[key][field], old[key][field], (key, field, short))
            # カーソルの高さは、品詞のフォントがどこまで付いたか（解析の進み・時間次第）で数 px 動くので、近いことだけ見る
            self.assertLessEqual(abs(new[key]['insert_y'] - old[key]['insert_y']), 12, (key, short))


if __name__ == '__main__':
    unittest.main()
