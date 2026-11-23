# -*- coding: utf-8 -*-
"""英語で動かした時に、画面に日本語が残らない（2026-11-23 うにさん「ボタンなど英語になってないところを翻訳して」）。
アプリを試しの写し（プログラムと同梱の物だけ・作った例文）で、言語 en の子として起こし、
・メニュー（入れ子も）の項目を全部たどり、窓を開く項目は開いて（ファイルの窓・お知らせは作り物で受ける。終了・再起動・
  言語の切り替えは押さない）、開いた窓の中の「…」のボタンも1段だけ押す
・F5 予測のカスタム（行頭・文末）・デバッグメニューも開く
・ボタン・ラベル・窓の題・メニューの項目・タブの名前・お知らせの文の字を集め、かな・漢字を含むものを数える
（編集欄の中身は集めない）。ui_lang の訳に無い日本語の記録（CN_UI_LANG_LOG_MISS）も合わせる。
日本語で起こした時は、ui_lang.tr が字を変えない（今のまま）ことも見る。run_on_desktop で回す。"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

# 理由があって日本語のまま残す字
#  ・書体の名前（「游ゴシック」など。書体の選択の窓の一覧・その見本の字）：書体の名前そのもの
#  ・ひらがなのまま通す語の窓の語（「ありがとう」など）と、その前の「Words (view only): 」「Includes: 」の後の語の並び：
#    日本語の語そのもの（訳すと意味が無い）
#  ・かな・漢字を含まない記号だけの字（括弧のボタン「」『』・＋ －）：日本語の文を打つための記号
import re
_LETTERS = re.compile(r'[ぁ-ゖァ-ヺ一-鿿]')
ALLOWED_WHERE = ('menu:種類・サイズを選択…:canvas', 'menu:ひらがなのまま通す語…:Checkbutton')
ALLOWED_PREFIX = ('Words (view only): ', 'Includes: ')
ALLOWED = ('あいうえお　漢字 ABC 123',)


def allowed(text, where=()):
    if text in ALLOWED or text.startswith(ALLOWED_PREFIX) or not _LETTERS.search(text):
        return True
    return bool(where) and all(w.startswith(ALLOWED_WHERE) for w in where)

CHILD = r'''
import json, os, re, sys, time, traceback
from pathlib import Path
def main():
    here = Path.cwd().resolve()
    assert not (here / 'vocabulary.json').exists()
    lang = os.environ.get('LANG_UI', 'en')
    os.environ['CN_UI_LANG_LOG_MISS'] = str(here / 'miss.log')
    import tkinter as tk
    from tkinter import messagebox, filedialog, simpledialog, ttk
    from unittest.mock import Mock, patch
    JA = re.compile(r'[぀-ヿ㐀-鿿！-～　-〿]')
    boxes = []
    def box(kind):
        def f(title=None, message=None, **kw):
            boxes.append((kind, str(title or ''), str(message or '')))
            return False if kind.startswith('ask') else None
        return f
    for name in ('showinfo', 'showwarning', 'showerror', 'askyesno', 'askokcancel', 'askyesnocancel', 'askquestion', 'askretrycancel'):
        setattr(messagebox, name, box(name))
    for name in ('askopenfilename', 'asksaveasfilename', 'askdirectory', 'askopenfilenames'):
        setattr(filedialog, name, lambda *a, **k: '')
    simpledialog.askstring = lambda *a, **k: None
    simpledialog.askinteger = lambda *a, **k: None
    tk.Misc.wait_window = lambda self, window=None: None
    tk.Misc.wait_variable = lambda self, name='PY_VAR': None
    tk.Misc.waitvar = tk.Misc.wait_variable
    tk.Misc.wait_visibility = lambda self, window=None: None
    tk.Misc.mainloop = lambda self, n=0: None
    tk.Misc.grab_set = lambda self: None
    import webbrowser
    webbrowser.open = lambda *a, **k: True
    os.startfile = lambda *a, **k: None
    import app, ui_lang, f5_predict_window, debug_menu
    from session import new_tab
    text = chr(10).join('%d行目は会議の資料を確認するための作った文です。' % i for i in range(1, 30))
    (here / 'settings.json').write_text(json.dumps(dict(layout='split', input_method='kana', input_method_auto=False, language=lang)), encoding='utf-8')
    (here / 'session.json').write_text(json.dumps(dict(version=1, active=0, tabs=[new_tab(text=text), new_tab(text='別のタブです。')]), ensure_ascii=False), encoding='utf-8')
    root = tk.Tk(); errors = []
    root.report_callback_exception = lambda *e: errors.append(''.join(traceback.format_exception(*e))[-400:])
    def pump(s):
        end = time.monotonic() + s
        while time.monotonic() < end:
            try:
                root.update()
            except tk.TclError:
                return
            time.sleep(0.003)
    found = {}
    short = set()
    def note(s, where):
        s = str(s)
        if JA.search(s):
            found.setdefault(s, set()).add(where)
    def raw(w, opt):
        try:
            return str(w.tk.call(w._w, 'cget', opt))
        except Exception:
            return ''
    def walk(w, where):
        try:
            cls = w.winfo_class()
        except Exception:
            return
        if cls in ('Toplevel', 'Tk'):
            try:
                note(w.tk.call('wm', 'title', w._w), where + ':title')
            except Exception:
                pass
        if cls in ('Label', 'Button', 'Checkbutton', 'Radiobutton', 'Labelframe', 'Menubutton', 'TLabel', 'TButton',
                   'TCheckbutton', 'TRadiobutton', 'TLabelframe', 'TMenubutton'):
            t = raw(w, '-text')
            note(t, where + ':' + cls)
            if cls in ('Button', 'Menubutton', 'TButton') and t and len(t) <= 3 and where == 'main':
                short.add(t)
        if cls == 'Menu':
            menu_texts(w, where)
        if cls == 'TNotebook':
            try:
                for tab in w.tabs():
                    note(w.tab(tab, 'text'), where + ':tab')
            except Exception:
                pass
        if cls == 'Treeview':
            try:
                for col in ('#0',) + tuple(w['columns']):
                    note(w.heading(col, 'text'), where + ':heading')
            except Exception:
                pass
        if cls == 'Canvas':
            try:
                for item in w.find_all():
                    if w.type(item) == 'text':
                        note(w.itemcget(item, 'text'), where + ':canvas')
            except Exception:
                pass
        if cls == 'Listbox' and where != 'main':
            try:
                for item in w.get(0, 'end'):
                    note(item, where + ':list')
            except Exception:
                pass
        for c in w.winfo_children():
            walk(c, where)
    def menu_texts(m, where):
        try:
            last = m.index('end')
        except Exception:
            return
        if last is None:
            return
        for i in range(last + 1):
            try:
                kind = m.type(i)
            except Exception:
                continue
            if kind in ('command', 'checkbutton', 'radiobutton', 'cascade'):
                note(m.tk.call(m._w, 'entrycget', i, '-label'), where + ':menu')
    def post(m):
        try:
            pc = m.tk.call(m._w, 'cget', '-postcommand')
            if pc:
                m.tk.call(pc)
        except Exception:
            pass
    def all_menus(w, out):
        for c in w.winfo_children():
            if c.winfo_class() == 'Menu':
                out.append(c)
            all_menus(c, out)
        return out
    def toplevels():
        return [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)]
    def collect_new(before, label):
        for t in toplevels():
            if t not in before:
                walk(t, label)
    def close_new(before):
        for t in toplevels():
            if t not in before:
                try:
                    t.destroy()
                except Exception:
                    pass
    SKIP = ('終了', '再起動', '日本語', 'English', '言語', 'アンインストール', 'ホットキー')   # ホットキーの切り替えは本物の登録で試しの子が止まる
    SKIP_ALSO = set(x for x in os.environ.get('CN_UI_LANG_SKIP', '').split('|') if x)
    with patch.object(app, 'GlobalHotkeys', return_value=Mock()), patch.object(app.CorrectNoteApp, '_learn_now', lambda *a: None), \
            patch.object(app.CorrectNoteApp, '_first_run_setup', lambda *a: None):
        a = app.CorrectNoteApp(root)
        root.geometry('1300x900+40+40')
        pump(5)
        a._reopen_menu_if_closed = lambda *x: None     # チェックの項目の後にメニューを開き直す（開くと Windows のメニューの輪で止まる）
        a._post_menu_bar = lambda *x: None
        a.root.destroy_real = root.destroy
        root.destroy = lambda: None            # 押した項目で閉じない
        walk(root, 'main')
        menus = all_menus(root, [])
        done_entries = 0
        seen = set()
        queue = list(menus)
        while queue:
            m = queue.pop(0)
            if str(m) in seen:
                continue
            seen.add(str(m))
            post(m)
            menu_texts(m, 'main')
            try:
                last = m.index('end')
            except Exception:
                last = None
            if last is None:
                continue
            for i in range(last + 1):
                try:
                    kind = m.type(i)
                except Exception:
                    continue
                if kind == 'cascade':
                    try:
                        sub = m.nametowidget(m.entrycget(i, 'menu'))
                        queue.append(sub)
                    except Exception:
                        pass
                    continue
                if kind not in ('command', 'checkbutton', 'radiobutton'):
                    continue
                try:
                    label = str(m.tk.call(m._w, 'entrycget', i, '-label'))
                    state = str(m.entrycget(i, 'state'))
                except Exception:
                    continue
                orig = ui_lang.original(label)
                if any(k in orig for k in SKIP) or any(k in label for k in SKIP) or state == 'disabled':
                    continue
                before = toplevels()
                prog = os.environ.get('CN_UI_LANG_PROGRESS')
                if prog:
                    with open(prog, 'a', encoding='utf-8') as pf:
                        pf.write('%d %.1f %s%s' % (done_entries, time.monotonic(), orig, chr(10)))
                if orig in SKIP_ALSO:
                    continue
                if prog:
                    import faulthandler
                    global _fh
                    try:
                        _fh
                    except NameError:
                        _fh = open(prog + '.stack', 'w')
                    faulthandler.dump_traceback_later(25, repeat=False, file=_fh)
                try:
                    m.invoke(i)
                except Exception as e:
                    errors.append('invoke %s: %r' % (orig, e))
                done_entries += 1
                pump(0.4)
                if prog:
                    import faulthandler
                    faulthandler.cancel_dump_traceback_later()
                for t in toplevels():
                    if t in before:
                        continue
                    walk(t, 'menu:' + orig)
                    # 窓の中の「…」のボタンを1段だけ
                    btns = []
                    def find(w):
                        for c in w.winfo_children():
                            if c.winfo_class() in ('Button', 'TButton') and raw(c, '-text').rstrip().endswith(('…', '...')):
                                btns.append(c)
                            find(c)
                    find(t)
                    for b in btns[:4]:
                        inner = toplevels()
                        try:
                            b.invoke()
                        except Exception:
                            pass
                        pump(0.2)
                        collect_new(inner, 'button:' + ui_lang.original(raw(b, '-text')))
                        close_new(inner)
                close_new(before)
                try:
                    a._close_dropdown()
                except Exception:
                    pass
                walk(root, 'main')
        # マウスを載せた時だけ出る説明（ツールバー・タブなど。欄の上の見出しに出す）
        header = getattr(a, 'editor_header', None)
        hovered = []
        def hover_walk(w):
            for c in w.winfo_children():
                try:
                    if c.bind('<Enter>') and c.winfo_ismapped():
                        hovered.append(c)
                except Exception:
                    pass
                if not isinstance(c, tk.Toplevel):
                    hover_walk(c)
        hover_walk(root)
        for c in hovered[:200]:
            try:
                c.event_generate('<Enter>', x=2, y=2)
                pump(0.03)
                if header is not None:
                    note(raw(header, '-text'), 'hover')
                c.event_generate('<Leave>', x=2, y=2)
            except Exception:
                pass
        # 右クリックの一覧（本文・補正欄・行番号・タブ）
        targets = [('editor', a.editor, a.editor.bbox('2.3')), ('result', a.result_view, a.result_view.bbox('2.3')),
                   ('gutter', a.editor_gutter, (5, 30, 1, 1))]
        for i, t in enumerate(getattr(a, '_tab_widgets', []) or []):
            try:
                tw = t if hasattr(t, 'event_generate') else t[0]
                targets.append(('tab%d' % i, tw, (5, 5, 1, 1)))
            except Exception:
                pass
        stamp = int(time.monotonic() * 1000)
        right_opened = []
        a._warp_pointer = lambda widget, x, y: 'sync'      # 本物のマウスは動かさない
        root.focus_get = lambda: a.editor
        pump(1.0)
        for k, (name, w, box) in enumerate(targets):
            if not box:
                continue
            before = toplevels()
            x, y = box[0] + 2, box[1] + max(1, box[3] // 2)
            try:
                w.event_generate('<ButtonPress-3>', x=x, y=y, time=stamp + 3000 * k)
                w.event_generate('<ButtonRelease-3>', x=x, y=y, time=stamp + 3000 * k + 50)
            except Exception as e:
                errors.append('right %s %r' % (name, e))
            end_wait = time.monotonic() + 3.0
            while time.monotonic() < end_wait and not [t for t in toplevels() if t not in before]:
                pump(0.1)
            pump(0.3)
            new_tops = [t for t in toplevels() if t not in before]
            items = 0
            for t in new_tops:
                for c in t.winfo_children():
                    if c.winfo_class() == 'Listbox':
                        items += c.size()
            right_opened.append((name, len(new_tops), items, getattr(a, '_dropdown', None) is not None))
            collect_new(before, 'right:' + name)
            for m in all_menus(root, []):
                menu_texts(m, 'right:' + name)
            try:
                a._close_dropdown()
            except Exception:
                pass
            close_new(before)
        # 右クリックの一覧の中身を、一覧を作る手続きから直に開く（作った押し下げでは開かない机があるため）
        units = []
        end_units = time.monotonic() + 30          # 2行目の解析が済むまで待つ（語の一覧は解析の答えから作る）
        while time.monotonic() < end_units and not units:
            try:
                units = list(a._units_for_row(2) or [])[:4]
            except Exception:
                units = []
            if not units:
                pump(0.5)
        right_opened.append(('units', len(units)))
        line2 = a.editor.get('2.0', '2.end')
        # 作り物の語の区切りも足す（解析の答えが無くても、一覧の固定の項目・組み立て文を出す）
        made = [dict(start=0, end=2, text=line2[:2], base=line2[:2], reading='', prev='', next=line2[2:4], kind=kind, detail=None)
                for kind in ('plain', 'typo', 'homophone', 'suspect')]
        units = units + made
        builders = [('gutter', lambda: a._gutter_menu_items(2)), ('tab', lambda: a._tab_menu_items(0)),
                    ('tab_backup', lambda: a._tab_backup_items(0)), ('odd', lambda: a._odd_menu_items(2, 0, 3))]
        for k, u in enumerate(units):
            builders += [('editor%d' % k, lambda u=u: a._editor_dropdown_items(2, u)),
                         ('result%d' % k, lambda u=u: a._result_correction_menu_items(2, u)),
                         ('analysis%d' % k, lambda u=u: a._analysis_items(2, u)),
                         ('autofix%d' % k, lambda u=u: a._autofix_menu_items(2, (0, 2), unit=u))]
        for name, build in builders:
            before = toplevels()
            try:
                items = build()
                if items:
                    a._make_dropdown(items, 200, 200)
            except Exception as e:
                errors.append('build %s %r' % (name, e))
                continue
            pump(0.3)
            dd = getattr(a, '_dropdown', None)
            right_opened.append((name, len(items or ()), dd is not None))
            for t in [getattr(a, '_dropdown', None)] + [t for t in toplevels() if t not in before]:
                if t is not None:
                    try:
                        walk(t, 'list:' + name)
                    except Exception:
                        pass
            try:
                a._close_dropdown()
            except Exception:
                pass
            close_new(before)
        for kind in ('head', 'end'):
            before = toplevels()
            try:
                f5_predict_window.open_window(a, kind)
            except Exception as e:
                errors.append('f5 window %r' % e)
            pump(0.3)
            collect_new(before, 'f5_window:' + kind)
            close_new(before)
        before = toplevels()
        try:
            a.open_debug_menu()
        except Exception as e:
            errors.append('debug %r' % e)
        pump(0.4)
        collect_new(before, 'debug_menu')
        close_new(before)
        for kind, title, message in boxes:
            # お知らせは作り物で受けたので、画面に出す時の訳（ui_lang.tr）で見る
            note(ui_lang.tr(title), 'box:' + kind)
            note(ui_lang.tr(message), 'box:' + kind)
        miss = []
        try:
            miss = sorted(set((here / 'miss.log').read_text(encoding='utf-8').splitlines()))
        except Exception:
            pass
        same_in_ja = None
        if lang == 'ja':
            same_in_ja = all(ui_lang.tr(s) == s for s in found)
        out = dict(found={k: sorted(v) for k, v in found.items()}, miss=miss, short=sorted(short), entries=done_entries,
                   errors=errors[:20], same_in_ja=same_in_ja, right_opened=locals().get('right_opened'))
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
    d = Path(tempfile.mkdtemp(prefix='cn-uilang-'))
    for e in here.iterdir():
        if e.is_file() and e.name not in ('settings.json', 'session.json', 'vocabulary.json', 'last_choice.json'):
            shutil.copy2(e, d / e.name)
    (d / 'zz_child.py').write_text(CHILD, encoding='utf-8')
    env = dict(os.environ); env.pop('PYTHONPATH', None); env.update(env_extra or {})
    subprocess.run([sys.executable, '-B', '-X', 'utf8', 'zz_child.py'], cwd=d, env=env, timeout=600,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    got = json.loads((d / 'child_out.json').read_text(encoding='utf-8'))
    shutil.rmtree(d, ignore_errors=True)
    case.assertNotIn('error', got, got.get('error'))
    return got


class Remaining(unittest.TestCase):
    def test_english_has_no_japanese_left(self):
        got = run_child(self, {'LANG_UI': 'en'})
        dump = os.environ.get('CN_UI_LANG_DUMP')
        if dump:
            Path(dump).write_text(json.dumps(got, ensure_ascii=False, indent=1), encoding='utf-8')
        found = got['found']
        kept = {t for t, where in found.items() if allowed(t, where)}
        miss = {__import__('ast').literal_eval(m) for m in got['miss']}
        left = sorted(t for t in set(found) | miss if t not in kept and not allowed(t))
        self.assertGreater(got['entries'], 50, got)                 # メニューをたどれた
        self.assertEqual(left, [], (len(left), left[:40]))

    def test_japanese_is_unchanged(self):
        got = run_child(self, {'LANG_UI': 'ja'})
        self.assertGreater(len(got['found']), 50, got)              # 日本語で出ている
        self.assertTrue(got['same_in_ja'], got)                    # 日本語の時は tr が字を変えない


if __name__ == '__main__':
    unittest.main()
