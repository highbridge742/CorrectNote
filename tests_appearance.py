# -*- coding: utf-8 -*-
"""外見（配色・装飾・裏の絵）の確かめ（appearance.py・2026-10-15）。

    Python39 -X utf8 tests_appearance.py

- 配色の値の決まり（重ならない・小文字・固定の色とぶつからない・見分けられる明るさ）
- 設定の読み込み（古いファイルはダークモードから配色を決める）
- 文字の裏の絵（Paper）: タグはいちばん下・選択などは塗りつぶしの模様・
  スクロールと改行のあとも表示行ごとに正しい切れ端・「なし」で消える
- 最後の行より下の Canvas: 大きさを変えている間も字を隠さない・ダブル／トリプルクリック・
  右ダブルクリックが Text に届く・打っている間はマウスポインタを隠す
- 中央寄せの余白の覆い（Paper.cover）・flush・長い段落・一時フォルダの片付け
- 行番号の欄の模様: 引き直しても消えない・行番号の項目は今までどおり・ファイルが消えても戻る
- 本体ごと（一時フォルダで起動）: 配色を抹茶→夜→標準と切り替えて前の色が残らない、
  ダークモードの切り替えが最後の配色へ戻る、装飾の選択が保存される
"""
from pathlib import Path
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
import unittest

import appearance as ap


def _lum(h):
    r, g, b = (int(h[i:i + 2], 16) for i in (1, 3, 5))
    return 0.299 * r + 0.587 * g + 0.114 * b


class AppearanceDataTests(unittest.TestCase):
    def test_theme_palettes_follow_the_standard_rules(self):
        import re
        src = Path(__file__).with_name('app.py').read_text(encoding='utf-8')
        keys = re.findall(r"'(\w+)'", re.search(r"_PALETTE_KEYS = \[(.*?)\]", src, re.S).group(1))
        start, end = src.index("BG = '#f6f4ee'"), src.index('_STANDARD_FIXED_FG')
        fixed = set(h.lower() for h in re.findall(r"#[0-9a-fA-F]{6}\b", src[:start] + src[end:]))
        self.assertEqual(ap.THEME_ORDER, tuple(ap.THEME_NAMES))
        self.assertEqual(set(ap.DARK_THEMES) | set(ap.LIGHT_THEMES), set(ap.THEME_ORDER))
        for name, spec in ap.THEMES.items():
            pal = spec['palette']
            self.assertEqual(sorted(pal), sorted(keys), name)
            values = list(pal.values()) + [spec['fixed_fg']]
            for v in values:
                self.assertRegex(v, r'^#[0-9a-f]{6}$', name)
            # 塗り替えは色の文字列で突き合わせるので、1つの案の中で重ねない
            self.assertEqual(len(set(pal.values())), len(pal), name)
            self.assertNotIn(spec['fixed_fg'], pal.values(), name)
            # 固定の色（検索の「見つからない」・ブックマークの丸など）とぶつからない
            self.assertFalse(set(pal.values()) & fixed, name)
            # 行番号: 今の行は地より明るい（tests_gui_gutter と同じ決まり）
            a, b = pal['LINE_NUM_ACTIVE_BG'], pal['LINE_NUM_BG']
            self.assertTrue(all(int(a[i:i + 2], 16) > int(b[i:i + 2], 16) for i in (1, 3, 5)), name)
            if spec['dark']:
                bg = _lum(pal['PANEL'])
                # ダークの見分け（tests_mock_ui の標準ダークと同じ数）
                self.assertGreaterEqual(abs(_lum(pal['UNSURE_BG']) - bg), 20, name)
                self.assertGreaterEqual(abs(_lum(pal['UNSURE_BG']) - _lum(pal['INK'])), 60, name)
                self.assertGreaterEqual(abs(_lum(pal['SUSPECT_BG']) - bg), 12, name)
                self.assertGreaterEqual(abs(_lum(pal['HOVER_BG']) - bg), 12, name)
            # 文字は地とはっきり違う
            self.assertGreaterEqual(abs(_lum(pal['INK']) - _lum(pal['PANEL'])), 120, name)

    def test_theme_palette_fills_standard_and_unknown(self):
        light = {'BG': '#f6f4ee', 'INK': '#2b2b2b'}
        dark = {'BG': '#1e2124', 'INK': '#e6e4dd'}
        pal, is_dark = ap.theme_palette('dark', light, dark, '#c4564a')
        self.assertEqual((pal['BG'], pal['FIXED_FG'], is_dark), ('#1e2124', '#c4564a', True))
        pal, is_dark = ap.theme_palette('nothing', light, dark, '#c4564a')
        self.assertEqual((pal['BG'], is_dark), ('#f6f4ee', False))
        pal, is_dark = ap.theme_palette('yoru', light, dark, '#c4564a')
        self.assertEqual((pal['BG'], pal['FIXED_FG'], is_dark), ('#0f1624', '#f08a7a', True))

    def test_every_decoration_has_art_and_gutter_pattern(self):
        import appearance_art as aa
        for decor in ap.DECOR_ORDER[1:]:
            w, h, _data = aa.ART[decor]
            bits = ap._art('art', decor)
            self.assertEqual((bits.w, bits.h), (w, h))
            self.assertTrue(any(bits.rows), decor)
            # 絵の左と上は、枠に達しないうちは切れない（形を描き終えるか薄れて消える）
            self.assertFalse(any(r & 0xF for r in bits.rows), decor)
            self.assertFalse(any(bits.rows[:4]), decor)
            g = ap._art('gutter', decor)
            self.assertTrue(any(g.rows), decor)
            # 行番号の欄の左（ブックマークの丸の所）には模様を置かない
            self.assertFalse(any(r & ((1 << (g.w - 37)) - 1) for r in g.rows), decor)
        self.assertIsNone(ap._art('art', 'none'))

    def test_settings_derive_theme_and_dark_mode(self):
        import settings
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, 'settings.json')

            def load(data):
                with open(path, 'w', encoding='utf-8') as f:
                    json.dump(data, f)
                return settings.Settings(path)

            # 既定: 標準のライト・波・薄い（うにさん 2026-10-15「デフォルトを、波、薄いにする」）
            s = settings.Settings(None)
            self.assertEqual((s.get('theme'), s.get('dark_mode'), s.get('decor'),
                              s.get('decor_strength')), ('light', False, 'nami', 'faint'))
            self.assertEqual((ap.DEFAULT_DECOR, ap.DEFAULT_STRENGTH), ('nami', 'faint'))
            s = load(dict(dark_mode=True))            # 外見より前のファイル
            self.assertEqual((s.get('theme'), s.get('dark_mode'), s.get('theme_dark')),
                             ('dark', True, 'dark'))
            s = load(dict(dark_mode=False, theme='yoru'))
            self.assertEqual((s.get('theme'), s.get('dark_mode'), s.get('theme_dark')),
                             ('yoru', True, 'yoru'))
            s = load(dict(dark_mode=True, theme='matcha', theme_dark='sumi'))
            self.assertEqual((s.get('theme'), s.get('dark_mode'), s.get('theme_light'),
                              s.get('theme_dark')), ('matcha', False, 'matcha', 'sumi'))
            s = load(dict(theme='nothing', theme_light='yoru', decor='nothing',
                          decor_strength=2, dark_mode=False))
            self.assertEqual((s.get('theme'), s.get('theme_light'), s.get('decor'),
                              s.get('decor_strength')), ('light', 'light', 'nami', 'faint'))
            # 外した装飾（洋書など）が保存してあった人も既定へ
            s = load(dict(decor='yosho'))
            self.assertEqual(s.get('decor'), 'nami')
            # 「なし」を選んだ人は「なし」のまま
            s = load(dict(decor='none', decor_strength='normal'))
            self.assertEqual((s.get('decor'), s.get('decor_strength')), ('none', 'normal'))
            s = load(dict(decor='sakura', decor_strength='strong'))
            self.assertEqual((s.get('decor'), s.get('decor_strength')), ('sakura', 'strong'))


class SliceFileTests(unittest.TestCase):
    def test_trim_forgets_old_slices_and_removes_files_little_by_little(self):
        files = ap._SliceFiles()
        files.LIMIT = 50
        names = [files.get(('t', i), lambda i=i: bytes([i % 250 + 1]) * 8, 8, 8)
                 for i in range(120)]
        # 作っている間は忘れない（その回に作った切れ端を消さない）
        self.assertEqual(len(files.paths), 120)
        files.trim()
        # LIMIT の 8 割まで、古いものから忘れる
        self.assertEqual(list(files.paths.values()), names[-40:])
        # ファイルは一度に 40 枚まで消す（一度に何千も消すと止まる）
        self.assertEqual(sum(not os.path.exists(n[1:]) for n in names), 40)
        while files.trash:
            files.drain()
        self.assertTrue(all(not os.path.exists(n[1:]) for n in names[:-40]))
        self.assertTrue(all(os.path.exists(n[1:]) for n in names[-40:]))
        shutil.rmtree(files.dir, True)

    def test_old_left_over_folders_are_swept(self):
        base = tempfile.mkdtemp(prefix='cn-appearance-sweep-')
        try:
            old = os.path.join(base, ap.DIR_PREFIX + 'old')
            new = os.path.join(base, ap.DIR_PREFIX + 'new')
            other = os.path.join(base, 'other_old')
            for path in (old, new, other):
                os.makedirs(path)
                with open(os.path.join(path, 'p1.xbm'), 'w') as f:
                    f.write('x')
            past = time.time() - ap.DIR_SWEEP_AGE - 60
            os.utime(old, (past, past))
            os.utime(other, (past, past))
            ap._sweep_old_dirs(base)
            self.assertEqual(sorted(os.listdir(base)), sorted(['other_old', ap.DIR_PREFIX + 'new']))
        finally:
            shutil.rmtree(base, True)


class PaperTkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import tkinter as tk
        cls.tk = tk
        try:
            cls.root = tk.Tk()
        except tk.TclError as error:
            raise unittest.SkipTest(f'Tk なし: {error}')
        cls.root.geometry('700x520+0+0')

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def setUp(self):
        from analysis_work import observe_text
        tk = self.tk
        self.t = tk.Text(self.root, wrap='word', padx=14, pady=12, spacing1=2, spacing3=4,
                         font=('TkFixedFont', 11), bg='#f0f0ed', width=1, height=1)
        self.t.pack(fill='both', expand=True)
        observe_text(self.t)
        self.t.insert('1.0', ''.join(f'{i}行目の文。' * (1 + i % 3) + '\n' for i in range(1, 80)))
        self.paper = ap.Paper(self.t)
        self.settle()

    def tearDown(self):
        self.t.destroy()
        self.settle()

    def settle(self, seconds=0.05):
        end = time.monotonic() + seconds
        while True:
            self.root.update()
            if time.monotonic() >= end:
                return
            time.sleep(0.005)

    def paper_tags(self):
        return [str(t) for t in self.t.tag_names() if str(t).startswith(ap.PAPER_PREFIX)]

    def check_slices(self, geom=None):
        """付いている切れ端が、その表示行の y と高さのものであること。
        geom=(x, y, 幅) は絵の位置（幅を変えている間の、前の位置）。"""
        p, t = self.paper, self.t
        bits = ap._art('art', p.decor)
        if geom is None:
            ox, oy, _bd = p._origin(t.winfo_width(), t.winfo_height(), bits)
            W = t.winfo_width()
        else:
            ox, oy, W = geom
        checked = 0
        for tag, name, rng in p._slots:
            if rng is None:
                continue
            ranges = [str(x) for x in t.tag_ranges(tag)]
            self.assertEqual(ranges, list(rng))
            info = t.dlineinfo(rng[0])
            self.assertIsNotNone(info)
            self.assertEqual(t.index(f'{rng[0]} display linestart'), t.index(rng[0]))
            # 行の終わりは次の表示行の始まり。窓の下の縁に掛かる行は、続きが画面の外
            # なので段落の終わりまで（画面に出る前に描き直す）
            ends = {t.index(f'{rng[0]} display lineend +1c')}
            if info[1] + info[3] >= t.winfo_height() - int(t.cget('pady')) - 2:
                ends.add(t.index(f'{rng[0]} lineend +1c'))
            self.assertIn(t.index(rng[1]), ends, (rng, info))
            want = p._slice(bits, ox, oy, W, info[1], info[3])
            self.assertEqual(name, want, (tag, rng, info))
            self.assertEqual(str(t.tag_cget(tag, 'bgstipple')), name)
            checked += 1
        return checked

    def test_tags_follow_scroll_and_edits(self):
        self.paper.set('sakura', '#d0d0cc', '#f0f0ed')
        self.settle()
        self.assertGreater(self.check_slices(), 5)
        # いちばん下・選択には塗りつぶしの模様
        names = [str(x) for x in self.t.tag_names()]
        self.assertTrue(all(n.startswith(ap.PAPER_PREFIX) for n in names[:len(self.paper_tags())]))
        self.assertEqual(str(self.t.tag_cget('sel', 'bgstipple')), ap._SLICES.solid())
        for step in (37, 5, -12):
            self.t.yview_scroll(step, 'units')
            self.settle()
            self.check_slices()
        self.t.yview_scroll(9, 'pixels')
        self.settle()
        self.check_slices()
        # 行の境目で改行・字を足す（両隣のタグを引き継がないように付け直す）
        tag, _name, rng = next(s for s in self.paper._slots if s[2])
        self.t.insert(rng[1], 'あ\n')
        self.t.insert(rng[0], 'い')
        self.settle()
        self.check_slices()
        for s in self.paper._slots:
            if s[2]:
                self.assertEqual(len(self.t.tag_ranges(s[0])), 2)
        # 全部消して入れ直しても（タブの切り替え）
        text = self.t.get('1.0', 'end-1c')
        self.t.delete('1.0', 'end')
        self.t.insert('1.0', text)
        self.settle()
        self.assertGreater(self.check_slices(), 5)

    def test_other_tags_stay_above_and_solid(self):
        self.paper.set('wamon', '#d0d0cc', '#f0f0ed')
        self.settle()
        self.t.tag_configure('mark_bg', background='#ffd9a0')
        self.t.tag_add('mark_bg', '5.0', '5.3')
        self.t.tag_lower('mark_bg')         # 絵より下へ潜らせる（空白の印と同じ）
        self.settle()
        names = [str(x) for x in self.t.tag_names()]
        self.assertGreater(names.index('mark_bg'), max(names.index(n) for n in self.paper_tags()))
        self.assertEqual(str(self.t.tag_cget('mark_bg', 'bgstipple')), ap._SLICES.solid())
        # なし: 絵のタグも、塗りつぶしの模様も外す
        self.paper.set('none', '#d0d0cc', '#f0f0ed')
        self.settle()
        self.assertEqual(self.paper_tags(), [])
        self.assertEqual(str(self.t.tag_cget('mark_bg', 'bgstipple')), '')
        self.assertEqual(str(self.t.tag_cget('sel', 'bgstipple')), '')

    def test_area_below_the_last_line_and_colour_change(self):
        self.t.delete('1.0', 'end')
        self.t.insert('1.0', '短い文。\n')
        self.paper.set('nami', '#d0d0cc', '#f0f0ed')
        self.settle()
        cv = self.paper._below
        self.assertIsNotNone(cv)
        self.assertTrue(cv.winfo_ismapped())
        self.assertEqual(str(cv.cget('cursor')), '')
        self.assertEqual(str(cv.cget('bg')), '#f0f0ed')
        self.paper.set('nami', '#c0c0bb', '#e0e0dd')
        self.settle()
        self.assertEqual(str(cv.itemcget('art', 'foreground')), '#c0c0bb')
        for tag, _n, _r in self.paper._slots:
            self.assertEqual(str(self.t.tag_cget(tag, 'background')), '#c0c0bb')
        # 長くすると Canvas は消える
        self.t.insert('end', '長い文。\n' * 60)
        self.settle()
        self.assertFalse(cv.winfo_ismapped())

    def test_long_paragraph_lines(self):
        # 長い段落の奥でも、表示行ごとの切れ端（行の終わりは次の表示行の始まり）
        self.t.delete('1.0', 'end')
        self.t.insert('1.0', '前の行。\n' * 5 + '長い段落の文。' * 600 + '\n' + '後の行。\n' * 5)
        self.paper.set('sakura', '#d0d0cc', '#f0f0ed')
        for fraction in (0.0, 0.3, 0.6, 0.97):
            self.t.yview_moveto(fraction)
            self.settle()
            self.assertGreater(self.check_slices(), 3, fraction)
        self.t.yview_moveto(0.5)
        self.settle()
        self.paper._last = None
        t0 = time.perf_counter()
        self.paper.redraw()
        took = (time.perf_counter() - t0) * 1000
        self.assertLess(took, 60, took)      # 段落の頭から並べ直していたころは 10ms 以上

    def test_flush_runs_the_pending_redraw(self):
        self.paper.set('wamon', '#d0d0cc', '#f0f0ed')
        self.settle()
        self.t.insert('3.0', '足した行。\n')
        self.assertIsNotNone(self.paper._job)
        self.paper.flush()
        self.assertIsNone(self.paper._job)
        self.assertGreater(self.check_slices(), 3)

    def test_scrolling_retags_at_once(self):
        # スクロールはその場で付け直す（画面を描く前に別の処理が回っても、絵が文字と動かない）
        self.paper.set('sakura', '#d0d0cc', '#f0f0ed')
        self.settle()
        for step, what in ((11, 'units'), (7, 'pixels'), (-3, 'units'), (5, 'pixels')):
            self.t.yview_scroll(step, what)
            self.assertIsNone(self.paper._job)
            self.assertGreater(self.check_slices(), 3, (step, what))
        self.t.yview_moveto(0.4)
        self.assertGreater(self.check_slices(), 3)

    def test_height_change_does_not_wait(self):
        # 高さだけの変化（見出しを隠す・出す）は待たずに新しい位置へ（右下に付いたまま）
        self.paper.set('nami', '#d0d0cc', '#f0f0ed')
        self.settle(0.3)
        try:
            for size in ('700x470', '700x520'):
                self.root.geometry(size)
                self.root.update()
                self.assertIsNone(self.paper._settle, size)
                self.assertGreater(self.check_slices(), 3, size)
                self.t.yview_scroll(4, 'pixels')
                self.assertGreater(self.check_slices(), 3, size)
        finally:
            self.root.geometry('700x520')
            self.settle(0.3)

    def test_scrolling_while_the_width_settles_keeps_the_art_still(self):
        t = self.t
        self.paper.set('sakura', '#d0d0cc', '#f0f0ed')
        self.settle(0.3)
        geom = self.paper._geom_used
        self.assertEqual(geom[2], t.winfo_width())
        try:
            self.root.geometry('660x520')
            self.root.update()
            self.assertNotEqual(t.winfo_width(), geom[2])
            self.assertIsNotNone(self.paper._settle)
            for step in (6, 9, -4):
                t.yview_scroll(step, 'pixels')
                # 前の位置・前の幅の絵のまま、行ごとに付け直している（文字と一緒に動かない）
                self.assertGreater(self.check_slices(geom), 3, step)
            self.settle(0.3)
            self.assertIsNone(self.paper._settle)
            self.assertGreater(self.check_slices(), 3)
            self.assertEqual(self.paper._geom_used[2], t.winfo_width())
        finally:
            self.root.geometry('700x520')
            self.settle(0.3)

    def test_widening_while_the_width_settles_does_not_tile_the_art(self):
        t = self.t
        self.paper.set('sakura', '#d0d0cc', '#f0f0ed')
        self.settle(0.3)
        try:
            self.root.geometry('900x520')
            self.root.update()
            self.assertIsNotNone(self.paper._settle)
            t.yview_scroll(5, 'pixels')
            W = t.winfo_width()
            widths = set()
            for _tag, name, rng in self.paper._slots:
                if rng is not None and name:
                    with open(name[1:], encoding='ascii') as f:
                        widths.add(int(f.readline().split()[2]))
            # 切れ端が欄より狭いと、Tk は模様を横に繰り返して絵が2つ出る
            self.assertTrue(widths and min(widths) >= W, (widths, W))
        finally:
            self.root.geometry('700x520')
            self.settle(0.3)

    def wait_prewarm(self):
        end = time.monotonic() + 20
        self.settle(0.1)
        while (self.paper._prewarm_todo or self.paper._prewarm_job) and time.monotonic() < end:
            self.settle(0.05)
        self.assertEqual(self.paper._prewarm_todo, [])

    def test_prewarm_runs_again_when_the_decor_comes_back(self):
        p = self.paper
        p.set('ikimono', '#d0d0cc', '#f0f0ed')
        self.wait_prewarm()
        first = len(ap._keeper(self.t).items)
        p.set('none', '#d0d0cc', '#f0f0ed')
        self.settle(0.1)
        p.set('ikimono', '#d0d0cc', '#f0f0ed')
        self.wait_prewarm()
        self.assertGreater(len(ap._keeper(self.t).items), 150)
        self.assertGreaterEqual(len(ap._keeper(self.t).items), first - 20)

    def test_dragging_out_of_the_art_strip_scrolls_like_the_text(self):
        p, t = self.paper, self.t
        p.set('sakura', '#d0d0cc', '#f0f0ed')
        self.settle(0.3)
        t.yview_moveto(0)
        self.settle(0.1)
        cv = p._edges.get('bottom')
        self.assertTrue(cv is not None and cv.winfo_ismapped())
        top = t.yview()[0]
        x0, y0 = cv.winfo_rootx() + 30, cv.winfo_rooty() + 3

        def send(seq, dy, **extra):
            cv.event_generate(seq, x=30, y=3 + dy, rootx=x0, rooty=y0 + dy, **extra)

        send('<ButtonPress-1>', 0)
        # 押したまま欄の下へ出る → Text と同じく自動でスクロールして選択を広げる
        send('<Motion>', 60, state=0x100)
        self.settle(0.4)
        self.assertGreater(t.yview()[0], top)
        self.assertTrue(t.tag_ranges('sel'))
        # 欄の中へ戻ると止まる
        send('<Motion>', -30, state=0x100)
        self.settle(0.06)
        moved = t.yview()[0]
        self.settle(0.3)
        self.assertEqual(t.yview()[0], moved)
        send('<ButtonRelease-1>', -30, state=0x100)
        self.settle(0.05)

    def test_prewarm_makes_the_slices_for_scrolling(self):
        self.paper.set('ikimono', '#d0d0cc', '#f0f0ed')
        end = time.monotonic() + 20
        self.settle(0.1)
        while self.paper._prewarm_todo and time.monotonic() < end:
            self.settle(0.05)
        self.assertEqual(self.paper._prewarm_todo, [])
        keeper = ap._keeper(self.t)
        self.assertGreater(len(keeper.items), 150)    # 点の無い切れ端は作らない
        made = len(ap._SLICES.paths)
        for _ in range(25):
            self.t.yview_scroll(3, 'pixels')
            self.check_slices()
        self.assertEqual(len(ap._SLICES.paths), made)    # 新しく作った切れ端は無い

    def test_scroll_hide_mode(self):
        p, t = self.paper, self.t
        p.SCROLL_HIDE = True
        try:
            p.set('kusaki', '#d0d0cc', '#f0f0ed')
            self.settle()
            self.assertGreater(self.check_slices(), 3)
            t.yview_scroll(5, 'pixels')
            self.assertIsNotNone(p._rest_job)
            self.assertTrue(all(t.tag_ranges(tag) == () for tag in self.paper_tags()))
            t.yview_scroll(5, 'pixels')
            t.insert('end', '足した。')
            self.settle(0.05)
            self.assertTrue(all(t.tag_ranges(tag) == () for tag in self.paper_tags()))
            self.settle(0.3)
            self.assertIsNone(p._rest_job)
            self.assertGreater(self.check_slices(), 3)
            # 動かないスクロール（see で今見えている所）は外さない
            t.see('@0,40')
            self.assertIsNone(p._rest_job)
        finally:
            p.SCROLL_HIDE = False

    def test_below_canvas_never_covers_text_while_resizing(self):
        t = self.t
        t.delete('1.0', 'end')
        t.insert('1.0', '短い文。\n')
        self.paper.set('nami', '#d0d0cc', '#f0f0ed')
        self.settle()
        cv = self.paper._below
        self.assertTrue(cv.winfo_ismapped())

        def text_bottom():
            info = t.dlineinfo('end-1c')
            return info[1] + info[3]

        self.root.geometry('640x520')
        for _ in range(6):
            t.insert('end', '大きさを変えている間に足した行。\n')
            self.root.update()
            self.assertLess(time.monotonic() - self.paper._size_at, 1.0)
            if cv.winfo_ismapped():
                self.assertGreaterEqual(cv.winfo_y(), text_bottom() - 1)
        self.settle(0.3)
        self.assertTrue(cv.winfo_ismapped())
        self.assertGreaterEqual(cv.winfo_y(), text_bottom() - 1)
        bits = ap._art('art', 'nami')
        ox, oy, bd = self.paper._origin(t.winfo_width(), t.winfo_height(), bits)
        hl = int(t.cget('highlightthickness'))
        self.assertEqual([round(v) for v in cv.coords('art')], [ox - hl, oy - cv.winfo_y()])
        self.root.geometry('700x520')
        self.settle(0.3)

    def test_art_reaches_the_frame_through_the_padding(self):
        # 絵の右下は枠の内側の角。行が描かれない余白（padx・pady）には同じ絵の Canvas を置く
        t, p = self.t, self.paper
        p.set('wamon', '#d0d0cc', '#f0f0ed')
        self.settle(0.3)
        W, H = t.winfo_width(), t.winfo_height()
        bits = ap._art('art', 'wamon')
        hl = int(t.cget('highlightthickness'))
        ox, oy, _bd = p._origin(W, H, bits)
        self.assertEqual((ox + bits.w, oy + bits.h), (W - hl, H - hl))

        def shown():
            out = {}
            for side, box in p._edge_boxes(t.winfo_width(), t.winfo_height()):
                cv = p._edges.get(side)
                if cv is not None and cv.winfo_ismapped():
                    out[side] = (cv, box)
            return out

        edges = shown()
        self.assertEqual(sorted(edges), ['bottom', 'right'])
        for side, (cv, (x0, y0, x1, y1)) in edges.items():
            self.assertEqual((cv.winfo_x(), cv.winfo_y(), cv.winfo_width(), cv.winfo_height()),
                             (x0, y0, x1 - x0, y1 - y0), side)
            self.assertEqual([round(v) for v in cv.coords('art')], [ox - x0, oy - y0], side)
            self.assertTrue(cv._correctnote_paper_below)
        # 余白の帯は Text の行の外（右の帯の左の端＝行の右の端）
        right = edges['right'][1]
        self.assertEqual(right[0], W - int(t.cget('borderwidth')) - hl - int(t.cget('padx')))
        # スクロールしても動かない
        before = {side: (cv.winfo_x(), cv.winfo_y(), tuple(cv.coords('art'))) for side, (cv, _b) in edges.items()}
        t.yview_scroll(5, 'units')
        self.settle()
        self.assertEqual(before, {side: (cv.winfo_x(), cv.winfo_y(), tuple(cv.coords('art')))
                                  for side, (cv, _b) in shown().items()})
        # 色を変えると帯の色も
        p.set('wamon', '#b0b0aa', '#e0e0dd')
        for cv, _box in edges.values():
            self.assertEqual(str(cv.itemcget('art', 'foreground')), '#b0b0aa')
            self.assertEqual(str(cv.cget('bg')), '#e0e0dd')
        # 右の帯を押すと、Text のその場所を押したのと同じ（帯が無いときと同じ所にカーソル）
        cv = edges['right'][0]
        x, y = right[0] + 3, 60

        def press(widget, wx, wy):
            for seq in ('<ButtonPress-1>', '<ButtonRelease-1>'):
                widget.event_generate(seq, x=wx, y=wy, rootx=widget.winfo_rootx() + wx,
                                      rooty=widget.winfo_rooty() + wy)
            self.settle(0.6)        # ダブルクリックと数えないだけ空ける

        t.mark_set('insert', '1.0')
        press(t, x, y)
        want = t.index('insert')
        t.mark_set('insert', '1.0')
        press(cv, x - cv.winfo_x(), y - cv.winfo_y())
        self.assertEqual(t.index('insert'), want)
        self.assertNotEqual(want, '1.0')
        # 小さい窓: 絵が左と上の余白にも掛かる
        try:
            self.root.geometry('330x260')
            self.settle(0.4)
            self.assertEqual(sorted(shown()), ['bottom', 'left', 'right', 'top'])
            self.check_slices()
        finally:
            self.root.geometry('700x520')
            self.settle(0.4)
        self.assertEqual(sorted(shown()), ['bottom', 'right'])
        # なし: 帯も消える
        p.set('none', '#b0b0aa', '#e0e0dd')
        self.settle()
        self.assertEqual(shown(), {})

    def test_clicks_on_the_art_below_reach_the_text(self):
        t = self.t
        t.delete('1.0', 'end')
        t.insert('1.0', '一行目の文\n二行目 last word')
        calls = []
        t.bind('<Double-Button-3>', lambda e: calls.append(('d3', e.widget, e.x, e.y)))
        self.paper.set('sakura', '#d0d0cc', '#f0f0ed')
        self.settle()
        cv = self.paper._below
        self.assertTrue(cv.winfo_ismapped())
        x, y = 60, 40
        stamp = [int(time.monotonic() * 1000) & 0x7fffffff]

        def click(button, n):
            for _ in range(n):
                stamp[0] += 60
                cv.event_generate(f'<ButtonPress-{button}>', x=x, y=y, time=stamp[0],
                                  rootx=cv.winfo_rootx() + x, rooty=cv.winfo_rooty() + y)
                cv.event_generate(f'<ButtonRelease-{button}>', x=x, y=y, time=stamp[0] + 10,
                                  rootx=cv.winfo_rootx() + x, rooty=cv.winfo_rooty() + y)
            stamp[0] += 2000
            self.root.update()

        click(1, 1)
        self.assertEqual(t.index('insert'), t.index('end-1c'))
        click(1, 2)
        self.assertEqual(t.get('sel.first', 'sel.last'), 'word')
        click(1, 3)
        self.assertEqual(t.get('sel.first', 'sel.last').rstrip('\n'), '二行目 last word')
        click(3, 2)
        self.assertEqual(len(calls), 1, calls)
        self.assertIs(calls[0][1], t)
        self.assertEqual((calls[0][2], calls[0][3]), (cv.winfo_x() + x, cv.winfo_y() + y))
        t.unbind('<Double-Button-3>')

    def test_the_art_canvases_pass_the_time_to_the_text(self):
        """押す・離す・動かす・ホイールを Text へ渡すとき、時刻も渡す（渡さないと 0 になり、
        app の右の二度押しの見分けが狂う）。"""
        t = self.t
        t.delete('1.0', 'end')
        t.insert('1.0', '短い文。\n')
        self.paper.set('sakura', '#d0d0cc', '#f0f0ed')
        self.settle(0.3)
        got = []
        seqs = ('<ButtonPress-3>', '<ButtonRelease-3>', '<Motion>', '<MouseWheel>')
        for seq in seqs:
            t.bind(seq, lambda e, s=seq: got.append((s, e.widget, int(e.time))))
        try:
            strips = [cv for cv in [self.paper._below] + list(self.paper._edges.values())
                      if cv is not None and cv.winfo_ismapped()]
            self.assertGreaterEqual(len(strips), 2, strips)
            stamp = int(time.monotonic() * 1000) & 0x3fffffff
            for i, cv in enumerate(strips):
                want = []
                for seq in seqs:
                    stamp += 2000
                    extra = dict(delta=120) if seq == '<MouseWheel>' else {}
                    cv.event_generate(seq, x=5, y=5, rootx=cv.winfo_rootx() + 5,
                                      rooty=cv.winfo_rooty() + 5, time=stamp, **extra)
                    want.append((seq, t, stamp))
                self.root.update()
                self.assertEqual(got, want, (i, cv))
                del got[:]
        finally:
            for seq in seqs:
                t.unbind(seq)

    def test_typing_hides_the_pointer_over_the_art_below(self):
        import typing_pointer
        t = self.t
        t.delete('1.0', 'end')
        t.insert('1.0', '短い文。\n')
        self.paper.set('kusaki', '#d0d0cc', '#f0f0ed')
        self.settle()
        cv = self.paper._below
        cv.event_generate('<Motion>', warp=True, x=40, y=40)
        self.settle()
        under = self.root.winfo_containing(*self.root.winfo_pointerxy())
        if under is not cv:
            self.skipTest('ポインタを動かせない画面')
        tp = typing_pointer.TypingPointer(self.root, lambda: [t], lambda e: True)
        old = str(t.cget('cursor'))
        tp.hide(t)
        self.assertEqual(str(t.cget('cursor')), 'none')
        tp.restore()
        self.assertEqual(str(t.cget('cursor')), old)

    def test_cover_for_the_centring_margin_shows_the_same_art(self):
        t = self.t
        self.paper.set('hoshizora', '#d0d0cc', '#f0f0ed')
        self.settle()
        cv = self.paper.cover(30, 80, 2)
        self.assertIsNotNone(cv)
        cv.place(x=2, y=30, width=200, height=80)
        ox, oy = self.paper._origin_used
        self.assertEqual([round(v) for v in cv.coords('art')], [ox - 2, oy - 30])
        self.assertEqual(str(cv.cget('bg')), '#f0f0ed')
        self.assertTrue(cv._correctnote_paper_below)
        self.paper.set('hoshizora', '#b0b0aa', '#e0e0dd')
        self.assertEqual(str(cv.itemcget('art', 'foreground')), '#b0b0aa')
        self.assertEqual(str(cv.cget('bg')), '#e0e0dd')
        self.paper.set('none', '#b0b0aa', '#e0e0dd')
        self.assertEqual(cv.find_withtag('art'), ())
        self.assertIsNone(self.paper.cover(30, 80, 2))
        cv.destroy()

    def test_held_slices_and_pruned_files(self):
        self.paper.set('kusaki', '#d0d0cc', '#f0f0ed')
        self.settle()
        for _ in range(30):
            self.t.yview_scroll(3, 'pixels')
            self.settle(0.01)
        self.assertLessEqual(len(ap._keeper(self.t).items), ap._Keeper.KEEP)
        in_use = self.paper.names_in_use()
        ap._SLICES.prune()
        for name in in_use:
            self.assertTrue(os.path.exists(name[1:]), name)
        self.settle()
        self.check_slices()
        # 一時フォルダが丸ごと消されても（掃除ソフトなど）、書き直して続く
        shutil.rmtree(ap._SLICES.dir)
        ap._keeper(self.t).clear()
        for _ in range(20):
            self.t.yview_scroll(7, 'pixels')
            self.settle(0.01)
        self.settle(0.1)
        self.assertTrue(os.path.isdir(ap._SLICES.dir))
        self.assertGreater(self.check_slices(), 3)


class GutterBackdropTests(unittest.TestCase):
    def test_backdrop_survives_redraw_and_keeps_number_items(self):
        import tkinter as tk
        try:
            root = tk.Tk()
        except tk.TclError as error:
            raise unittest.SkipTest(f'Tk なし: {error}')
        try:
            import app
            frame = tk.Frame(root)
            frame.pack(fill='both', expand=True)
            text = tk.Text(frame, width=40, height=20)
            gutter = app.LineNumberGutter(frame, text)
            gutter.pack(side='left', fill='y')
            text.pack(side='left', fill='both', expand=True)
            text.insert('1.0', '行\n' * 50)
            root.update()
            gutter.redraw()
            self.assertEqual(gutter.find_withtag('cn_backdrop'), ())
            gutter.backdrop = ap.GutterBackdrop()
            gutter.backdrop.set('sakura', '#d6d3cb')
            gutter.redraw()
            items = gutter.find_withtag('cn_backdrop')
            self.assertTrue(items)
            self.assertEqual(gutter.find_all()[0], items[0])      # いちばん下
            numbers = len(gutter.find_withtag('num'))
            gutter.redraw()
            self.assertEqual(gutter.find_withtag('cn_backdrop'), items)   # 作り直さない
            self.assertEqual(len(gutter.find_withtag('num')), numbers)
            self.assertEqual(str(gutter.itemcget(items[0], 'state')), 'disabled')
            gutter.backdrop.set('sakura', '#c6c3bb')
            gutter.redraw()
            self.assertEqual(str(gutter.itemcget(gutter.find_withtag('cn_backdrop')[0],
                                                 'foreground')), '#c6c3bb')
            # 模様のファイルが消されても（一時フォルダの掃除など）、引き直しで戻る
            os.remove(gutter.backdrop._name[1:])
            text.configure(height=16)
            root.update()
            gutter.redraw()
            self.assertTrue(gutter.find_withtag('cn_backdrop'))
            gutter.backdrop.set('none', '#c6c3bb')
            gutter.redraw()
            self.assertEqual(gutter.find_withtag('cn_backdrop'), ())
        finally:
            root.destroy()

    def test_a_new_tk_gets_the_procedures_again(self):
        import tkinter as tk
        from analysis_work import observe_text
        for _ in range(2):
            try:
                root = tk.Tk()
            except tk.TclError as error:
                raise unittest.SkipTest(f'Tk なし: {error}')
            try:
                root.geometry('500x400')
                text = tk.Text(root)
                text.pack(fill='both', expand=True)
                observe_text(text)
                text.insert('1.0', '行\n' * 60)
                paper = ap.Paper(text)
                root.update()
                paper.set('nami', '#d0d0cc', '#ffffff')
                root.update()
                self.assertTrue(any(s[2] for s in paper._slots))
            finally:
                root.destroy()


def child():
    import tkinter as tk
    from unittest.mock import Mock, patch
    import app
    assert Path('.appearance-isolated').exists()
    Path('settings.json').write_text(json.dumps(dict(
        layout='split', input_method='kana', input_method_auto=False,
        theme='matcha', decor='sakura')), encoding='utf8')
    root = tk.Tk()
    root.withdraw()
    errors = []
    root.report_callback_exception = lambda *e: errors.append(''.join(traceback.format_exception(*e)))
    a = None

    def settle(seconds=0.2):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            root.update()
            assert not errors, errors
            time.sleep(0.005)

    def colours(widget, found):
        for opt in ('bg', 'fg', 'background', 'foreground', 'insertbackground',
                    'selectbackground', 'activebackground', 'activeforeground',
                    'highlightbackground', 'selectcolor', 'inactiveselectbackground'):
            try:
                found.add(str(widget.cget(opt)).lower())
            except Exception:
                pass
        for child in widget.winfo_children():
            colours(child, found)
        return found

    def only(theme):
        """その案にしか無い色（標準と共有しない値）。"""
        others = set()
        for name in ap.THEME_ORDER:
            if name != theme:
                pal, _d = ap.theme_palette(name, app.LIGHT_PALETTE, app.DARK_PALETTE, '#c4564a')
                others |= set(pal[k] for k in app._PALETTE_KEYS)
        pal, _d = ap.theme_palette(theme, app.LIGHT_PALETTE, app.DARK_PALETTE, '#c4564a')
        return set(pal[k] for k in app._PALETTE_KEYS) - others

    try:
        with patch.object(app, 'GlobalHotkeys', return_value=Mock()), \
                patch.object(app.CorrectNoteApp, '_learn_now', lambda *v: None), \
                patch.object(app.CorrectNoteApp, '_first_run_setup', lambda *v: None):
            a = app.CorrectNoteApp(root)
            root.geometry('1100x700+0+0')
            root.deiconify()
            a.editor.insert('1.0', '外見の確かめに使う作り話の文です。\n' * 40)
            settle(0.6)
            matcha = ap.THEMES['matcha']['palette']
            assert a.editor.cget('bg') == matcha['PANEL'], a.editor.cget('bg')
            assert app.BG == matcha['BG'] and app.FIXED_FG == ap.THEMES['matcha']['fixed_fg']
            assert a.editor.tag_cget('autofixed', 'foreground') == app.FIXED_FG
            assert a.theme_var.get() == 'matcha' and a.decor_var.get() == 'sakura'
            assert a.editor._correctnote_paper.decor == 'sakura'
            assert a.editor_gutter.find_withtag('cn_backdrop')
            assert any(s[2] for s in a.editor._correctnote_paper._slots)
            # 外見のメニューは色の塗り直しの名簿に入っている（チェックの印が見える）
            labels = []
            for menu in a._menus:
                last = menu.index('end')
                for i in range(0 if last is None else last + 1):
                    if menu.type(i) == 'cascade':
                        labels.append(menu.entrycget(i, 'label'))
            assert {'外見', '配色', '装飾', '装飾の濃さ'} <= set(labels), labels
            # 抹茶 → 夜: 抹茶にしか無い色が、どの部品にも残らない
            a._toggle_word_book()
            settle()
            book = a._word_book
            header_before = str(book.header.cget('bg')) if book.window is not None else None
            a.theme_var.set('yoru')
            a._choose_theme()
            settle()
            if header_before is not None:
                # 単語帳の見出し（欄の色から計算した色）も新しい配色で塗り直す
                assert str(book.header.cget('bg')) != header_before, header_before
                a._toggle_word_book()
                settle()
            left = colours(root, set()) & only('matcha')
            assert not left, left
            assert a.settings.get('dark_mode') is True and a.dark_mode_var.get() is True
            assert a.editor.cget('bg') == ap.THEMES['yoru']['palette']['PANEL']
            paper = a.editor._correctnote_paper
            assert paper.bg == a.editor.cget('bg')
            # 濃さを保存していない（既定の 薄い）
            assert paper.color == ap.paper_color(paper.bg, app.INK, ap.DEFAULT_STRENGTH)
            # ダークモードを切る → 最後のライト系（抹茶）へ戻る
            a.dark_mode_var.set(False)
            a._on_toggle_dark_mode()
            settle()
            assert a.settings.get('theme') == 'matcha', a.settings.get('theme')
            left = colours(root, set()) & only('yoru')
            assert not left, left
            # 標準へ
            a.theme_var.set('light')
            a._choose_theme()
            settle()
            left = colours(root, set()) & only('matcha')
            assert not left, left
            assert app.BG == app.LIGHT_PALETTE['BG'] and app.FIXED_FG == '#c4564a'
            # 装飾と濃さ
            a.decor_var.set('none')
            a._choose_decor()
            settle()
            assert not [t for t in a.editor.tag_names() if str(t).startswith(ap.PAPER_PREFIX)]
            assert not a.editor_gutter.find_withtag('cn_backdrop')
            a.decor_var.set('nami')
            a.decor_strength_var.set('strong')
            a._choose_decor()
            settle()
            assert a.editor._correctnote_paper.decor == 'nami'
            # 1行目へ飛んで中央に寄せた余白の覆いにも、同じ絵を描く
            a._goto_line(1, centered=True)
            settle()
            masks = a.editor._correctnote_navigation_masks
            assert masks and all(m.winfo_class() == 'Canvas' and m.find_withtag('art')
                                 for m in masks), masks
            a._clear_navigation_padding()
            a.decor_var.set('none')
            a._choose_decor()
            a._goto_line(1, centered=True)
            settle()
            masks = a.editor._correctnote_navigation_masks
            assert masks and all(m.winfo_class() == 'Frame' for m in masks), masks
            a._clear_navigation_padding()
            a.decor_var.set('nami')
            a._choose_decor()
            settle()
            # 絵の帯（欄の余白）の上の右の二度押し（縮小）。押した時刻を Text へ渡すので、
            # 本文とまたいでも二度押しになり、間をあけた2回は二度押しにならない
            # （前は時刻 0 で渡り、逆になっていた）
            paper = a.editor._correctnote_paper
            strip = next((cv for cv in [paper._below] + list(paper._edges.values())
                          if cv is not None and cv.winfo_ismapped()), None)
            assert strip is not None, (paper._below, paper._edges)
            entered = []
            a._on_right_double = lambda e, w: (entered.append(w), 'break')[1]
            sx, sy = 4, 4
            rx, ry = strip.winfo_rootx() + sx, strip.winfo_rooty() + sy
            ex, ey = rx - a.editor.winfo_rootx(), ry - a.editor.winfo_rooty()
            stamp = [int(time.monotonic() * 1000) & 0x3fffffff]

            def right(widget, gap, x, y):
                stamp[0] += gap
                widget.event_generate('<ButtonPress-3>', x=x, y=y, rootx=rx, rooty=ry,
                                      time=stamp[0])
                widget.event_generate('<ButtonRelease-3>', x=x, y=y, rootx=rx, rooty=ry,
                                      time=stamp[0] + 20)
                settle(0.05)
                a._close_dropdown()

            # Windows では app が OS の押下時刻（GetMessageTime）でも見るが、event generate は
            # OS の知らせを通らないので、試験の時刻に揃える
            with patch.object(app, '_input_message_time', lambda: stamp[0]):
                right(strip, 0, sx, sy)
                right(strip, 3000, sx, sy)
                assert entered == [], entered
                right(strip, 3000, sx, sy)
                right(a.editor, 150, ex, ey)
                assert entered == [a.editor], entered
            del a._on_right_double
            settle()
            # 外見のメニュー: マウスを乗せると一時的に当て、離れる（閉じる）と戻す
            menus = dict((kind, menu) for menu, kind in a._look_menus)
            m_look = root.nametowidget(menus['theme'].winfo_parent())
            x11 = root.tk.call('tk', 'windowingsystem') == 'x11'

            def select(menu):
                """メニューの項目へ移った知らせ。Tk は窓がまだ無いと event generate を
                捨てる（Windows では開いたことの無いメニューに窓が無い）。本物の知らせ
                （Windows の WM_MENUSELECT）は Tk が窓を作ってから送るので、ここでも作る。"""
                menu.winfo_id()
                menu.event_generate('<<MenuSelect>>')

            def hover(kind, value):
                menu = menus[kind]
                # X11 では開いているメニューだけを見る（Windows ではメニューを開くと
                # 閉じるまで戻ってこないので、開かずに試す）
                if x11 and not menu.winfo_ismapped():
                    menu.post(root.winfo_rootx() + 60, root.winfo_rooty() + 60)
                if value is None:
                    menu.activate('none')
                else:
                    last = menu.index('end')
                    index = next(i for i in range(last + 1) if menu.type(i) == 'radiobutton'
                                 and str(menu.entrycget(i, 'value')) == value)
                    menu.activate(index)
                select(menu)
                settle(0.4)

            from pos_font import POS_COLOR_TAGS, colors_key, normalize_colors

            def pos_fg():
                colors = getattr(a.editor, '_correctnote_boundary_colors', None)
                assert colors is not None
                colors._configure_pos_fonts()       # 裏の解析が終わって塗り直すのと同じ
                return str(a.editor.tag_cget(POS_COLOR_TAGS['名詞'], 'foreground'))

            def pos_want(dark):
                return normalize_colors(a.settings.get(colors_key(dark)), dark)['名詞']

            assert pos_want(True) != pos_want(False)
            light_bg = app.LIGHT_PALETTE['BG']
            assert app.BG == light_bg
            hover('theme', 'sora')
            assert app.BG == ap.THEMES['sora']['palette']['BG'], app.BG
            assert a.settings.get('theme') == 'light' and a.theme_var.get() == 'light'
            hover('theme', 'yoru')
            assert app.BG == ap.THEMES['yoru']['palette']['BG'], app.BG
            # 試しの間、dark_mode（品詞の色などが読む）は試している配色の値。メニューの印は変えない
            assert a.settings.get('dark_mode') is True and a.dark_mode_var.get() is False
            # 裏の解析が終わって品詞の色を塗り直しても、試している配色（ダーク系）の色
            assert pos_fg() == pos_want(True), (pos_fg(), pos_want(True))
            # 試しの間に設定が保存されても、次の起動では保存してある配色（標準）から決め直す
            a.settings.save()
            assert type(a.settings)(a.settings.path).get('dark_mode') is False
            # 補正欄（右）も。前は試しを当てた後の描き直しで、保存してある配色の色に戻っていた
            settle(0.6)
            right = str(a.result_view.tag_cget(POS_COLOR_TAGS['名詞'], 'foreground'))
            assert right == pos_want(True), (right, pos_want(True))
            hover('theme', None)
            assert a.settings.get('dark_mode') is False
            assert pos_fg() == pos_want(False), (pos_fg(), pos_want(False))
            right = str(a.result_view.tag_cget(POS_COLOR_TAGS['名詞'], 'foreground'))
            assert right == pos_want(False), (right, pos_want(False))
            assert app.BG == light_bg, app.BG
            left = colours(root, set()) & only('yoru')
            assert not left, left
            paper = a.editor._correctnote_paper
            hover('decor', 'sakura')
            assert paper.decor == 'sakura' and a.settings.get('decor') == 'nami'
            hover('decor', None)
            assert paper.decor == 'nami'
            hover('strength', 'faint')
            assert paper.color == ap.paper_color(paper.bg, app.INK, 'faint')
            hover('strength', None)
            assert paper.color == ap.paper_color(paper.bg, app.INK, 'strong')
            # 試しの途中で選ぶ: 選んだものが残る
            hover('decor', 'kusaki')
            a.decor_var.set('kusaki')
            a._choose_decor()
            hover('decor', None)
            assert paper.decor == 'kusaki' and a.settings.get('decor') == 'kusaki'
            # 配色を試している間に装飾を選ぶ: 配色は戻る
            hover('theme', 'matcha')
            assert app.BG == ap.THEMES['matcha']['palette']['BG']
            a.decor_var.set('nami')
            a._choose_decor()
            settle()
            assert app.BG == light_bg and paper.decor == 'nami'
            menus['theme'].activate('none')
            settle(0.4)
            assert app.BG == light_bg
            # 別のメニューへ移る: 前のメニューに選んでいた項目が残っていても、移った先を当てる
            hover('theme', 'sora')
            assert app.BG == ap.THEMES['sora']['palette']['BG'], app.BG
            hover('decor', 'sakura')
            assert app.BG == light_bg and paper.decor == 'sakura', (app.BG, paper.decor)
            # 外見のメニュー（配色・装飾…の並び）へ戻ると、試しを戻す
            m_look.activate(1)
            select(m_look)
            settle(0.4)
            assert paper.decor == 'nami', paper.decor
            # 試しの間、メニューは塗らない（Windows では開いているメニューが組み直される）
            hover('theme', 'yoru')
            assert app.BG == ap.THEMES['yoru']['palette']['BG'], app.BG
            for menu in list(menus.values()) + [m_look]:
                assert str(menu.cget('bg')) == app.LIGHT_PALETTE['PANEL'], menu
            assert a.theme_var.get() == 'light' and a.dark_mode_var.get() is False
            # 閉じる（X11 はメニューが消えても選んでいた項目が残る・Windows は消える）と戻す
            if x11:
                for menu in menus.values():
                    menu.unpost()
            else:
                menus['theme'].activate('none')
            settle(0.6)
            assert app.BG == light_bg, app.BG
            # 外見と関係の無いメニュー（ファイルなど）の項目へ移ったら、待たずにその場で戻す
            hover('theme', 'yoru')
            assert app.BG == ap.THEMES['yoru']['palette']['BG'], app.BG
            other = next(m for m in a._menus if str(m) not in a._look_menu_names)
            select(other)
            assert app.BG == light_bg and a.settings.get('dark_mode') is False, app.BG
            if x11:
                for menu in menus.values():
                    menu.unpost()
            menus['theme'].activate('none')
            settle(0.4)
            assert app.BG == light_bg, app.BG
            # 配色を当てたら（戻したときも）、品詞の色を塗り直す（色を付けない配色の間に
            # 解析が済んだ行のため）
            queued = []
            for pane in (a.editor, a.result_view):
                colors = pane._correctnote_boundary_colors
                colors.queue = (lambda q=colors.queue, p=pane: (queued.append(p), q())[1])
            hover('theme', 'yoru')
            hover('theme', None)
            assert a.editor in queued and a.result_view in queued, queued
            for pane in (a.editor, a.result_view):
                del pane._correctnote_boundary_colors.queue
            # 夜を試している間に、保存してある標準を選ぶ: 標準に戻り、dark_mode も戻る
            hover('theme', 'yoru')
            a.theme_var.set('light')
            a._choose_theme()
            settle()
            assert app.BG == light_bg and a.settings.get('dark_mode') is False, app.BG
            if x11:
                for menu in menus.values():
                    menu.unpost()
            menus['theme'].activate('none')
            # 試した配色を選ぶ: メニューも新しい配色になる。標準へ戻すと何も残らない
            hover('theme', 'yoru')
            a.theme_var.set('yoru')
            a._choose_theme()
            settle()
            for menu in list(menus.values()) + [m_look]:
                assert str(menu.cget('bg')) == ap.THEMES['yoru']['palette']['PANEL'], menu
            if x11:
                for menu in menus.values():
                    menu.unpost()
            menus['theme'].activate('none')
            hover('theme', 'sora')
            a.theme_var.set('light')
            a._choose_theme()
            settle(0.4)
            assert app.BG == light_bg, app.BG
            left = colours(root, set()) & (only('yoru') | only('sora'))
            assert not left, left
            if x11:
                for menu in menus.values():
                    menu.unpost()
            # 今までの呼び方（真偽値だけ）も動く。ダーク系の最後の配色（夜）になる
            a._apply_theme(True)
            settle()
            assert app.BG == ap.THEMES['yoru']['palette']['BG'], app.BG
            a._apply_theme(False)
            settle()
            a._on_close()
            a = None
            saved = json.loads(Path('settings.json').read_text(encoding='utf8'))
            assert (saved['theme'], saved['decor'], saved['decor_strength'],
                    saved['dark_mode']) == ('light', 'nami', 'strong', False), saved
            print('APPEARANCE_APP_OK', flush=True)
    finally:
        if a is not None:
            a._on_close()
        else:
            try:
                root.destroy()
            except tk.TclError:
                pass
    assert not errors, errors


class AppAppearanceTests(unittest.TestCase):
    def test_switching_themes_leaves_no_old_colour(self):
        from bundle_manifest import NAMES
        src = Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory(prefix='correctnote-appearance-') as folder:
            dest = Path(folder)
            for p in src.iterdir():
                if p.is_file() and (p.suffix == '.py' or p.name in NAMES):
                    shutil.copyfile(p, dest / p.name)
            (dest / '.appearance-isolated').touch()
            run = subprocess.run([sys.executable, '-B', '-u', '-X', 'utf8',
                                  str(dest / Path(__file__).name), '--child'],
                                 cwd=dest, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 encoding='utf8', errors='replace', timeout=240)
            print(run.stdout[-4000:], flush=True)
            self.assertEqual(run.returncode, 0, run.stdout[-4000:])
            self.assertIn('APPEARANCE_APP_OK', run.stdout)


if __name__ == '__main__':
    child() if '--child' in sys.argv else unittest.main()
