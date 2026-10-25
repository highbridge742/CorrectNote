# -*- coding: utf-8 -*-
"""外見（配色・装飾）。うにさん 2026-10-14〜15 の依頼:

- 「このアプリについての中に、外見のメニューを追加し、アプリ全体のテーマを切り替える」
- 配色: 標準（ライト）・標準（ダーク）に、抹茶・空（ライト系）と夜・炭（ダーク系）を足す。
- 装飾: 本文の欄の裏に、装飾ごとの絵を薄く敷く。「右下アンカーのように置きます」
  「裏に絵があって、絵の上に文字がある」「枠を枠としてそこで絵が途切れる」。
  行番号の欄の裏にも、同じ装飾の模様を薄く敷く（「行番号の枠の裏に半透明で」）。

**文字の裏に絵を敷く仕組み（Tk の Text は背景に画像を置けない）**:
タグの背景（background）に点の模様（bgstipple=@ファイル.xbm）を付けると、その字の後ろが
「模様の点だけ背景色で塗られた」状態になる。Tk はこの模様の原点を**表示行ごとに**行の上端へ
戻す（行ごとに別の画面で描いてから貼るため。X11 と Windows の両方で確かめた・2026-10-15）。
そこで表示行ごとに別のタグ（PAPER_PREFIX で始まる）を作り、「その行の高さぶんの絵の
切れ端」を別の xbm にして付ける。こうすると絵は欄に対して動かず、スクロールしても右下に
留まる。模様は1色なので、絵は1色の点の濃淡になる（うにさん了承済み）。

守ること（Tk の決まりから来るもの・項目は試した結果）:

1. **絵のタグはいちばん下に置く**。網掛け・選択・検索などの色は絵より上に出る。
   ほかのコードが自分のタグを tag lower すると絵より下に潜るので、描くたびに確かめて
   絵のタグを下げ直す（cn_paper_guard）。
2. **背景色を持つほかのタグには、塗りつぶしの模様（SOLID）を付ける**。Tk は background と
   bgstipple を**別々に**いちばん上のタグから取るので、模様を持たないタグ（選択など）は
   絵の模様を借りて、点の所だけ塗られてしまう（試した）。
3. タグの操作は**元の Tk の命令へ直接**送る（`<窓>_correctnote_work`）。app の包み
   （analysis_work.observe_text）を通すと tagged の知らせが回り、絵文字の重ね描きなどが
   動き直す。
4. 描き直しは `after(0)` で予約する。Tk は画面を「手が空いたとき（idle）」に描くので、
   それより先に回る after(0) で付け直せば、ずれた絵が一瞬も出ない。
5. xbm のファイル名は**中身ごとに別**にする（Tk は名前で覚えるので、同じ名前を書き換えても
   古い絵のまま）。Tk はどこにも使われなくなった絵を忘れ、次はファイルから読み直す
   （1枚 0.3ms・スクロールの1歩で30枚ほど）。最近使った切れ端は、画面に出さない Canvas に
   持たせておいて、読み直さずに済ませる（_Keeper、窓1つにつき KEEP 枚まで・両方の欄で共有）。
   装飾を選んだときと幅が変わったときは、今の行の高さぶんの切れ端を、手が空いている間に
   少しずつ作って持たせておく（prewarm。スクロールを始めた最初の1歩が重くならないように）。
6. 最後の行より下（字の無い所）はタグが塗れないので、絵を丸ごと描いた Canvas を
   Text の中に place で置く（Canvas が欄の外を切る）。マウスの操作は Text へそのまま渡す。
   ダブル・トリプルクリックは、Text の bind をそのまま呼ぶ（cn_paper_click）。
   カーソルの形は Text に従う。1行目・最終行へ飛んだときの中央寄せの余白の覆いも、
   装飾があるときは同じ絵の Canvas にする（Paper.cover）。
7. スクロール（yview・see）の知らせを受けたら、その場で描き直す（after(0) を待たない）。
   慣性スクロールの次の1歩・絵文字の重ね描きの update_idletasks などが先に回ると、
   Tk が古いタグのまま行を写して、絵が文字と一緒に動いて見える（PC で確かめた・2026-10-15）。
   app が update_idletasks で画面を先に描かせる所（行への移動・左右の行合わせ）の前にも
   Paper.flush() を呼んで、予約した描き直しを先に済ませる。
   欄の**幅**が変わったときだけ、止まるまで（SETTLE_MS）新しい切れ端を作らずに前の位置の絵を
   付け直す。高さだけの変化（見出しが隠れる・状態の行が出る）は待たずに新しい位置で描く。
8. 切れ端の一時フォルダは起動ごとに作り、終わるときに消す。落ちて残ったものは、
   次に起動したとき2日より古ければ消す。
"""
import atexit
import base64
import os
import shutil
import tempfile
import time
import weakref
import zlib
from collections import OrderedDict

PAPER_PREFIX = 'cn_paper_'
DIR_PREFIX = 'correctnote_paper_'
DIR_SWEEP_AGE = 2 * 24 * 3600    # 落ちて残った一時フォルダは、これより古ければ消す

# --------------------------------------------------------------------- 配色
THEME_ORDER = ('light', 'matcha', 'sora', 'dark', 'yoru', 'sumi')
DARK_THEMES = ('dark', 'yoru', 'sumi')
LIGHT_THEMES = tuple(t for t in THEME_ORDER if t not in DARK_THEMES)
THEME_NAMES = {
    'light': '標準（ライト）', 'matcha': '抹茶', 'sora': '空',
    'dark': '標準（ダーク）', 'yoru': '夜', 'sumi': '炭',
}
# 標準の2つは app.py の LIGHT_PALETTE / DARK_PALETTE をそのまま使う（ここには持たない）。
# 残りの4つは /mnt/project-files/themes/themes.json（2026-10-14 うにさん採用）の値。
# 名前は app.py の _PALETTE_KEYS と同じ27色。FIXED_FG（自動で直した字の色）も案ごとに持つ。
# **値は小文字の #rrggbb で、1つの案の中で重ねない**（app の塗り替えは色の文字列で
# 突き合わせるので、同じ値が2つあるとどちらに直すか決まらない）。
THEMES = {
    'matcha': dict(dark=False, fixed_fg='#bf4b3f', palette={
        'BG': '#e3eadb', 'PANEL': '#f2f6ec', 'INK': '#223127', 'RULE': '#c7d3bb',
        'ACCENT': '#4a7a3d', 'MUTED': '#75856e', 'LINE_NUM_BG': '#e8eee0', 'LINE_NUM_FG': '#94a18e',
        'LINE_NUM_ACTIVE_BG': '#f9fbf6', 'LINE_NUM_PENDING': '#d8c7a2', 'RESULT_BG': '#eef2e7', 'RESULT_GUTTER_BG': '#eaefe2',
        'SUSPECT_BG': '#f0d5c7', 'EDITOR_SEL_BG': '#dae5d3', 'RESULT_SEL_BG': '#cddac5', 'HOVER_BG': '#f0f4ea',
        'FOUND_BG': '#f3e7ab', 'FOUND_CUR_BG': '#f1c360', 'UNSURE_BG': '#e1d4e8', 'HISTORY_HINT_BG': '#ddecea',
        'HISTORY_HINT_LINE': '#ae5719', 'QUICK_SENT_BG_A': '#c6e3db', 'QUICK_SENT_BG_B': '#a1beee', 'WS_LINE_A': '#d3d8ce',
        'WS_LINE_B': '#dee3d9', 'WS_TAB_A': '#eef2e8', 'WS_TAB_B': '#e9ede3',
    }),
    'sora': dict(dark=False, fixed_fg='#c4564a', palette={
        'BG': '#e2eaf3', 'PANEL': '#f4f7fb', 'INK': '#1c2a3a', 'RULE': '#c4d2e0',
        'ACCENT': '#2c6bb3', 'MUTED': '#72829a', 'LINE_NUM_BG': '#e7eef5', 'LINE_NUM_FG': '#929fb2',
        'LINE_NUM_ACTIVE_BG': '#fafbfd', 'LINE_NUM_PENDING': '#d8c8af', 'RESULT_BG': '#eff3f9', 'RESULT_GUTTER_BG': '#e9f0f6',
        'SUSPECT_BG': '#f1d7d3', 'EDITOR_SEL_BG': '#dae4f1', 'RESULT_SEL_BG': '#cbdaec', 'HOVER_BG': '#f1f5fa',
        'FOUND_BG': '#f4e7b5', 'FOUND_CUR_BG': '#f2c366', 'UNSURE_BG': '#e2d5f4', 'HISTORY_HINT_BG': '#dfedf7',
        'HISTORY_HINT_LINE': '#b05819', 'QUICK_SENT_BG_A': '#cce8d4', 'QUICK_SENT_BG_B': '#a2bff7', 'WS_LINE_A': '#d5dadf',
        'WS_LINE_B': '#dfe3e7', 'WS_TAB_A': '#f0f3f7', 'WS_TAB_B': '#ebeef3',
    }),
    'yoru': dict(dark=True, fixed_fg='#f08a7a', palette={
        'BG': '#0f1624', 'PANEL': '#172035', 'INK': '#e3e8f2', 'RULE': '#2b3650',
        'ACCENT': '#7fc4f7', 'MUTED': '#8794ab', 'LINE_NUM_BG': '#111929', 'LINE_NUM_FG': '#6b778e',
        'LINE_NUM_ACTIVE_BG': '#2f384c', 'LINE_NUM_PENDING': '#7e5f37', 'RESULT_BG': '#151d30', 'RESULT_GUTTER_BG': '#121a2b',
        'SUSPECT_BG': '#553338', 'EDITOR_SEL_BG': '#344d6a', 'RESULT_SEL_BG': '#385573', 'HOVER_BG': '#2b405a',
        'FOUND_BG': '#4f492b', 'FOUND_CUR_BG': '#75571e', 'UNSURE_BG': '#673c98', 'HISTORY_HINT_BG': '#224868',
        'HISTORY_HINT_LINE': '#e07020', 'QUICK_SENT_BG_A': '#224b3b', 'QUICK_SENT_BG_B': '#20458e', 'WS_LINE_A': '#3c4557',
        'WS_LINE_B': '#2b3447', 'WS_TAB_A': '#1e273b', 'WS_TAB_B': '#283045',
    }),
    'sumi': dict(dark=True, fixed_fg='#f0806a', palette={
        'BG': '#191715', 'PANEL': '#23201d', 'INK': '#ebe3d6', 'RULE': '#3c3631',
        'ACCENT': '#e2a550', 'MUTED': '#9b9184', 'LINE_NUM_BG': '#1c1a17', 'LINE_NUM_FG': '#7d756a',
        'LINE_NUM_ACTIVE_BG': '#3b3733', 'LINE_NUM_PENDING': '#825f30', 'RESULT_BG': '#201d1b', 'RESULT_GUTTER_BG': '#1d1b18',
        'SUSPECT_BG': '#5a3227', 'EDITOR_SEL_BG': '#5d482c', 'RESULT_SEL_BG': '#664e2f', 'HOVER_BG': '#4a3c28',
        'FOUND_BG': '#584919', 'FOUND_CUR_BG': '#7c5710', 'UNSURE_BG': '#6c3c8e', 'HISTORY_HINT_BG': '#2a4857',
        'HISTORY_HINT_LINE': '#e07020', 'QUICK_SENT_BG_A': '#2a4b2a', 'QUICK_SENT_BG_B': '#264582', 'WS_LINE_A': '#484440',
        'WS_LINE_B': '#37332f', 'WS_TAB_A': '#2a2723', 'WS_TAB_B': '#34312d',
    }),
}


def mix(a, b, t):
    """色 a から色 b へ t の割合だけ寄せた色（'#rrggbb'）。"""
    a = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return '#%02x%02x%02x' % tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def theme_palette(theme_id, light_palette, dark_palette, light_fixed_fg):
    """(配色の27色＋FIXED_FG の dict, ダーク系か) を返す。知らない id は標準ライト。"""
    if theme_id == 'dark':
        pal = dict(dark_palette)
        pal['FIXED_FG'] = light_fixed_fg
        return pal, True
    spec = THEMES.get(theme_id)
    if spec is None:
        pal = dict(light_palette)
        pal['FIXED_FG'] = light_fixed_fg
        return pal, False
    pal = dict(dark_palette if spec['dark'] else light_palette)   # 欠けた色の控え
    pal.update(spec['palette'])
    pal['FIXED_FG'] = spec['fixed_fg']
    return pal, spec['dark']


# --------------------------------------------------------------------- 装飾
# 洋書・手描きノート・線は外した（うにさん 2026-10-15）
DECOR_ORDER = ('none', 'wamon', 'genko', 'hoshizora', 'sakura', 'kusaki', 'sumi',
               'artdeco', 'ikimono', 'nami',
               'hansen', 'oshibana', 'mochi', 'chara', 'bakuhatsu')
DECOR_NAMES = {
    'none': 'なし', 'wamon': '和文様', 'genko': '原稿', 'hoshizora': '星空', 'sakura': '桜',
    'kusaki': '草木', 'sumi': '墨と和紙', 'artdeco': '扇と帯', 'ikimono': 'いきもの',
    'nami': '波', 'chara': 'まじかる',
    'oshibana': 'しおり', 'hansen': '船',
    'mochi': 'おもち', 'bakuhatsu': '爆発',
}
# 絵の濃さ: 欄の地の色から文字の色へ寄せる割合
STRENGTH_ORDER = ('faint', 'normal', 'strong')
STRENGTH_NAMES = {'faint': '薄い', 'normal': '普通', 'strong': '濃い'}
# 既定の装飾と濃さ（うにさん 2026-10-15「デフォルトを、波、薄いにする」）。
# settings.DEFAULTS と、知らない値のときの戻り先
DEFAULT_DECOR = 'nami'
DEFAULT_STRENGTH = 'faint'
# うにさん 2026-10-15: 3つとも一段薄く（普通＝前の薄い・濃い＝前の普通）
PAPER_STRENGTH = {'faint': 0.06, 'normal': 0.09, 'strong': 0.14}
GUTTER_STRENGTH = {'faint': 0.12, 'normal': 0.18, 'strong': 0.26}


def paper_color(pane_bg, ink, strength):
    return mix(pane_bg, ink, PAPER_STRENGTH.get(strength, PAPER_STRENGTH['normal']))


def gutter_color(gutter_bg, number_fg, strength):
    return mix(gutter_bg, number_fg, GUTTER_STRENGTH.get(strength, GUTTER_STRENGTH['normal']))


def reserve_below(text, px):
    """欄の下に出す行（解析の進み具合など）のぶん px を、裏の絵に知らせる（消すときは 0）。
    app が行を出し入れする直前に呼ぶ。絵は動かない（Paper.BELOW_HOLD_MS）。"""
    try:
        px = max(0, int(px or 0))
    except Exception:
        px = 0
    text._correctnote_art_below = px
    paper = getattr(text, '_correctnote_paper', None)
    if paper is not None:
        try:
            paper.note_below()
        except Exception:
            pass


class _Bits:
    """1bit の絵（行ごとの bytes。下位ビットが左）。"""
    def __init__(self, w, h, data):
        raw = zlib.decompress(base64.b64decode(''.join(data)))
        self.w, self.h = w, h
        self.stride = (w + 7) // 8
        self.rows = [int.from_bytes(raw[y * self.stride:(y + 1) * self.stride], 'little')
                     for y in range(h)]

    def slice(self, r0, h, x0, width):
        """絵の r0 行目から h 行を、横 width の帯の x0 の位置に置いた xbm の中身。
        点が1つも無ければ None。"""
        nbytes = (width + 7) // 8
        mask = (1 << width) - 1
        out = []
        any_on = False
        for y in range(r0, r0 + h):
            if 0 <= y < self.h:
                v = self.rows[y]
                v = (v << x0 if x0 >= 0 else v >> -x0) & mask
                if v:
                    any_on = True
                out.append(v.to_bytes(nbytes, 'little'))
            else:
                out.append(bytes(nbytes))
        return b''.join(out) if any_on else None


_ART_CACHE = {}


def _art(kind, decor):
    key = (kind, decor)
    if key not in _ART_CACHE:
        import appearance_art as aa
        table = aa.ART if kind == 'art' else aa.GUTTER
        spec = table.get(decor)
        _ART_CACHE[key] = _Bits(*spec) if spec else None
    return _ART_CACHE[key]


class _SliceFiles:
    """xbm の切れ端を一時フォルダに書いて、その名前（'@パス'）を返す。同じものは使い回す。

    Tk の bgstipple はファイル名でしか受け取れない。Tk は使っている間は中身を覚えているので、
    **どこにも付いていない**切れ端だけ、溜まりすぎたら消してよい（prune）。"""
    LIMIT = 3000        # 1枚 10〜20KB（欄の幅1つ・行の高さ32まで 350 枚ほど）

    def __init__(self):
        self.dir = None
        self.paths = {}
        self.count = 0
        self.solid_name = None
        self.swept = False
        self.trash = []         # 消す切れ端のファイル（drain で少しずつ）

    def _ensure_dir(self):
        if self.dir is not None and not os.path.isdir(self.dir):
            self.dir = None         # 誰かに消された（一時フォルダの掃除など）
            self.paths.clear()
            self.solid_name = None
        if self.dir is None:
            if not self.swept:
                self.swept = True
                _sweep_old_dirs(tempfile.gettempdir())
            # 日本語や空白を含まない場所（Tk の読み込みのため）
            self.dir = tempfile.mkdtemp(prefix=DIR_PREFIX)
            atexit.register(shutil.rmtree, self.dir, True)

    def _write(self, width, height, data):
        self._ensure_dir()
        self.count += 1
        path = os.path.join(self.dir, f'p{self.count}.xbm')
        body = '0x' + data.hex(',').replace(',', ',0x') if data else ''
        with open(path, 'w', encoding='ascii', newline='\n') as f:
            f.write(f'#define p_width {width}\n#define p_height {height}\n')
            f.write('static char p_bits[] = {\n')
            f.write(body)
            f.write('\n};\n')
        return '@' + path.replace('\\', '/')

    def solid(self):
        """全部の点が立った 8x8（「模様なしで塗る」の代わり）。"""
        if self.solid_name is None:
            self.solid_name = self._write(8, 8, b'\xff' * 8)
        return self.solid_name

    def get(self, key, make, width, height):
        """key で覚える。make() は xbm の中身（bytes）か None（点が無い）を返す。"""
        if key in self.paths:
            return self.paths[key]
        data = make()
        name = None if data is None else self._write(width, height, data)
        self.paths[key] = name
        return name

    def trim(self):
        """溜まりすぎていたら、どこにも付いていない古いものから LIMIT の 8 割まで忘れる。
        描き終えた後に呼ぶ（描いている途中だと、その回に作った切れ端を消してしまう）。"""
        if len(self.paths) > self.LIMIT:
            self.prune(target=int(self.LIMIT * 0.8))
        self.drain()

    def drain(self, count=40):
        """忘れた切れ端のファイルを少しずつ消す（一度に消すと、ウイルス対策の検査などで止まる）。"""
        while self.trash and count > 0:
            count -= 1
            try:
                os.remove(self.trash.pop())
            except OSError:
                pass

    def drop(self, name):
        """Tk が読めなかった切れ端（ファイルが消された）を忘れる。次は書き直す。"""
        for key, value in list(self.paths.items()):
            if value == name:
                del self.paths[key]

    def prune(self, keep=(), target=0):
        """どこにも付いていない切れ端を、古いものから target 枚になるまで忘れる。
        ファイルは trash に入れて drain で消す。"""
        in_use = {self.solid_name}
        in_use.update(keep)
        for owner in list(_OWNERS):
            try:
                in_use.update(owner.names_in_use())
            except Exception:
                pass
        for key, name in list(self.paths.items()):
            if len(self.paths) <= target:
                break
            if name in in_use:
                continue
            del self.paths[key]
            if name:
                self.trash.append(name[1:])


def _sweep_old_dirs(base):
    """前に落ちたときに残った切れ端の一時フォルダを消す（DIR_SWEEP_AGE より古いものだけ）。
    動いている別の窓のものを消しても、その窓は読めなかった切れ端を書き直す。"""
    now = time.time()
    try:
        entries = list(os.scandir(base))
    except OSError:
        return
    for entry in entries:
        if not entry.name.startswith(DIR_PREFIX):
            continue
        try:
            if entry.is_dir(follow_symlinks=False) and \
                    now - entry.stat(follow_symlinks=False).st_mtime > DIR_SWEEP_AGE:
                shutil.rmtree(entry.path, True)
        except OSError:
            pass


_SLICES = _SliceFiles()
_OWNERS = weakref.WeakSet()

# 1回の呼び出しで、絵の高さに掛かる表示行を全部調べる（Python から1行ずつ聞くと遅い）。
# 返すのは {終わり方 {行の始まり 次の行の始まり y 高さ ...}}。終わり方は
# end（本文の最後まで見た）か more（絵より下にも行がある・画面の外に出た）。
# 行の終わりは、画面に出ている次の表示行の始まり（@0,y+高さ）から取る。
# `display lineend` は段落の頭から並べ直すので、長い段落の奥では1回が重い
# （3888字の段落で1回 0.5ms 前後、絵に掛かる15行で10ms ほど）。窓の下の縁に
# 掛かる行は、続きが画面の外なので段落の終わりまでとする（画面に出る前に描き直す）。
_TCL = r"""
proc ::cn_paper_lines {w ytop ybot wh} {
    set out {}
    set how more
    set idx [$w index "@0,$ytop"]
    while 1 {
        set info [$w dlineinfo $idx]
        if {$info eq ""} break
        lassign $info x y lw h b
        if {$y >= $ybot} break
        set next [expr {$y + $h}]
        set end ""
        if {$next >= $wh} {
            set end [$w index "$idx lineend +1c"]
        } else {
            set nidx [$w index "@0,$next"]
            set ninfo [$w dlineinfo $nidx]
            if {$ninfo ne ""} {
                set ny [lindex $ninfo 1]
                if {$ny == $next && [$w compare $nidx > $idx]} {
                    set end $nidx
                } elseif {$ny == $y} {
                    # 下に次の行が無い: 本文の最後の行か、窓の下の余白（pady）に掛かった
                    if {[lindex [$w dlineinfo "end -1c"] 1] eq $y} {
                        set end [$w index end]
                    } else {
                        set end [$w index "$idx lineend +1c"]
                    }
                }
            }
        }
        if {$end eq ""} {set end [$w index "$idx display lineend +1c"]}
        lappend out $idx $end $y $h
        if {[$w compare $end >= end]} {set how end; break}
        if {[$w compare $end <= $idx]} break
        set idx $end
    }
    return [list $how $out]
}
proc ::cn_paper_guard {w solid} {
    set seen 0
    set low 0
    foreach t [$w tag names] {
        if {[string match cn_paper_* $t]} {
            if {$seen} {set low 1}
            continue
        }
        if {[$w tag cget $t -background] ne ""} {
            set seen 1
            if {[$w tag cget $t -bgstipple] eq ""} {
                $w tag configure $t -bgstipple $solid
            }
        }
    }
    if {$low} {
        foreach t [$w tag names] {
            if {[string match cn_paper_* $t]} {$w tag lower $t}
        }
    }
}
proc ::cn_paper_unguard {w solid} {
    foreach t [$w tag names] {
        if {[$w tag cget $t -bgstipple] eq $solid} {
            $w tag configure $t -bgstipple {}
        }
    }
}
# 絵の Canvas の上のダブル・トリプルクリックを、Text が受けたのと同じに回す。
# 1回目の押下は event generate で Text へ渡すが、Tk の「続けて押した」の数え方は
# 窓が変わると切れるので、2回目からは Text の bindtags の bind を、Tk と同じ
# 選び方（ボタンの指定 → 回数 → 修飾キー）で探して %W などを埋めて呼ぶ。
proc ::cn_paper_click {w n b x y X Y s t} {
    set counts {}
    if {$n >= 3} {lappend counts Triple-}
    if {$n >= 2} {lappend counts Double-}
    lappend counts ""
    set pre ""
    if {$s & 4} {append pre Control-}
    if {$s & 1} {append pre Shift-}
    set mods [list ""]
    if {$pre ne ""} {set mods [list $pre ""]}
    set pats {}
    foreach detail [list "-$b" ""] {
        foreach c $counts {
            foreach m $mods {lappend pats "<${m}${c}ButtonPress${detail}>"}
        }
    }
    set map [list %% % %# 0 %b $b %f 0 %h ?? %k ?? %s $s %t $t %w ?? %x $x %y $y \
        %A ?? %E 1 %K ?? %N ?? %W $w %T 4 %X $X %Y $Y %D ?? %R ?? %S ?? %a ?? \
        %c ?? %d ?? %i ?? %m ?? %o ?? %p ?? %B ??]
    foreach tag [bindtags $w] {
        set script ""
        foreach p $pats {
            if {[catch {bind $tag $p} script]} {set script ""}
            if {$script ne ""} break
        }
        if {$script eq ""} continue
        set code [catch {uplevel #0 [string map $map $script]} msg]
        if {$code == 3} break
        if {$code == 1} {catch {bgerror $msg}}
        if {![winfo exists $w]} break
    }
}
"""


def _ensure_tcl(widget):
    # 窓（Tk）を作り直すと手続きも無くなるので、毎回その Tk に聞く
    if not widget.tk.call('info', 'procs', '::cn_paper_click'):
        widget.tk.eval(_TCL)


# ------------------------------------------------- 絵の Canvas の上のクリック
CLICK_TAG = 'CorrectNotePaperClick'
DOUBLE_CLICK_MS = 500


def _add_click_tag(widget):
    """Canvas の bindtags の頭に CLICK_TAG を足す（2回目からの押下を Text の bind へ）。"""
    tags = widget.bindtags()
    if CLICK_TAG not in tags:
        widget.bindtags((CLICK_TAG,) + tuple(tags))
    if not widget.tk.call('bind', CLICK_TAG, '<ButtonPress>'):
        widget.bind_class(CLICK_TAG, '<ButtonPress>', _on_click_press)


def _on_click_press(event):
    """続けて押した数を Text ごとに数える。1回目は次の bind（event generate で Text へ）。"""
    target = getattr(event.widget, 'master', None)
    if target is None:
        return None
    try:
        t = int(event.time)
        n = 1
        last = getattr(target, '_correctnote_clicks', None)
        if last is not None:
            pt, pnum, px, py, pn = last
            if (pnum == event.num and 0 <= (t - pt) & 0xffffffff <= DOUBLE_CLICK_MS
                    and abs(event.x_root - px) <= 8 and abs(event.y_root - py) <= 8):
                n = pn % 3 + 1
        target._correctnote_clicks = (t, event.num, event.x_root, event.y_root, n)
        if n < 2:
            return None
        _ensure_tcl(target)
        target.tk.call('::cn_paper_click', target._w, n, event.num,
                       event.x_root - target.winfo_rootx(), event.y_root - target.winfo_rooty(),
                       event.x_root, event.y_root, event.state, t)
    except Exception:
        return None
    return 'break'


class _Keeper:
    """切れ端を Tk に覚えさせておく（見えない Canvas に描いておく）。窓（Tk）ごとに1つで、
    両方の欄が共有する（同じ幅なら同じ切れ端を使う）。Tk はどこにも使われなくなった絵を
    忘れて、次はファイルから読み直す（Windows で1枚数 ms）。"""
    KEEP = 1200         # Windows では1枚が GDI の絵1つ（1プロセス 10000 まで）

    def __init__(self, widget):
        self.root = widget._root()
        self.items = OrderedDict()      # 切れ端の名前 -> Canvas の絵の番号
        self.cv = None
        _OWNERS.add(self)

    def _canvas(self):
        cv = self.cv
        if cv is None or not cv.winfo_exists():
            import tkinter as tk
            cv = self.cv = tk.Canvas(self.root, width=1, height=1)   # 置かない（見えない）
            self.items.clear()
        return cv

    def hold(self, name, recent=True):
        items = self.items
        if name in items:
            if recent:
                items.move_to_end(name)
            return
        try:
            cv = self._canvas()
            items[name] = cv.create_bitmap(0, 0, bitmap=name)
            if not recent:
                items.move_to_end(name, last=False)
        except Exception:
            return
        while len(items) > self.KEEP:
            _old, item = items.popitem(last=False)
            try:
                cv.delete(item)
            except Exception:
                pass

    def forget(self, name):
        item = self.items.pop(name, None)
        if item is not None and self.cv is not None:
            try:
                self.cv.delete(item)
            except Exception:
                pass

    def clear(self):
        if self.cv is not None:
            try:
                self.cv.delete('all')
            except Exception:
                pass
        self.items.clear()

    def names_in_use(self):
        return set(self.items)


def _keeper(widget):
    root = widget._root()
    keeper = getattr(root, '_correctnote_paper_keeper', None)
    if keeper is None:
        keeper = root._correctnote_paper_keeper = _Keeper(widget)
    return keeper


class Paper:
    """1つの Text の裏に絵を敷く（文字は絵の上）。Text 1つにつき1つ作る。

    作ると `text._correctnote_paper` に入り、スクロール・編集・タグの変更・大きさの変更を
    自分で拾って描き直す。装飾が「なし」の間は何もしない。"""

    SETTLE_MS = 150     # 幅を変えている間は待つ（変わるたびに切れ端が全部変わる）
    RETRY = 3           # 切れ端が読めなかったときに描き直す回数（続けて）
    # スクロールしている間は絵を外し、止まって SCROLL_REST_MS で戻す（軽い）。
    # 既定は外さない（うにさんの「右下アンカー」）。重さを比べるための切り替え。
    SCROLL_HIDE = False
    SCROLL_REST_MS = 150
    SLICE_H = 32              # 切れ端の高さの刻み（_tall）
    PREWARM_SLICE_S = 0.008   # 先に作る切れ端: 1回に使う時間
    PREWARM_GAP_MS = 15       # 先に作る切れ端: 回の間（その間に操作が回る）
    # 欄の下に出たり消えたりする行（解析の進み具合など）のぶんを、app が reserve_below で
    # 知らせる（Text の `_correctnote_art_below`、画素）。絵の右下は「欄の高さ＋その値」の所に
    # 合わせるので、行が出て欄が縮んでも絵は動かない（下の端が隠れるだけ。うにさん 2026-10-16）。
    # 行を出し入れしても、欄の大きさが変わるのは入れ子の枠を1段ずつ並べ直した後（アイドルの
    # 回が何回か後）。その間に描き直すと、欄の高さと値が食い違って絵が跳ねる。値が変わったら、
    # そのときの絵の位置（窓の中の高さ）を BELOW_HOLD_MS とその後アイドル BELOW_HOLD_IDLE 回の
    # 間は保つ。窓の大きさが変わったら（最大化など）すぐやめる。
    BELOW_HOLD_MS = 600
    BELOW_HOLD_IDLE = 8

    def __init__(self, text):
        self.t = text
        self.decor = None
        self.color = None
        self.bg = None
        self._slots = []         # [タグ名, 切れ端の名前, (始まり, 終わり)]
        self._job = None
        self._settle = None
        self._dirty = True
        self._last = None
        self._size = None
        self._size_at = 0.0
        self._origin_used = None   # 今のタグの切れ端を作ったときの絵の左上 (x, y)
        self._geom_used = None     # 同じく (x, y, 幅)。幅を変えている間はこれで付け直す
        self._view = None          # SCROLL_HIDE: 前に見た画面の位置
        self._rest_job = None      # SCROLL_HIDE: 絵を外している間の、戻す予約
        self._prewarm_key = None
        self._prewarm_todo = []
        self._prewarm_args = None
        self._prewarm_job = None
        self._prewarm_count = 0
        self._below = None
        self._below_key = None
        self._edges = {}           # 余白の帯の Canvas（right・bottom・left・top）
        self._edges_key = None
        self._covers = []          # [(Canvas の weakref, 置いた x, 置いた y)]
        self._below_seen = None    # 前に見た `_correctnote_art_below`
        self._anchor_used = None   # 前に絵の右下を合わせた高さ（欄の上から）
        self._anchor_place = None  # そのときの _place_in_window() と欄の大きさ
        self._anchor_hold = None   # (窓の上から絵の右下までの高さ, 窓の大きさ)。この間は保つ
        self._hold_job = None
        self._guarded = False
        self._retry = 0
        Paper._serial = getattr(Paper, '_serial', 0) + 1
        self._prefix = f'{PAPER_PREFIX}{Paper._serial}_'
        text._correctnote_paper = self
        _OWNERS.add(self)
        observers = getattr(text, '_correctnote_observers', None)
        if observers is not None:
            observers.setdefault('scrolled', []).append(self._on_scrolled)
            observers.setdefault('changed', []).append(self._on_changed)
            observers.setdefault('tagged', []).append(self._on_tagged)
        for seq in ('<Configure>', '<Map>', '<<WidgetViewSync>>'):
            text.bind(seq, self.queue, add=True)
        text.bind('<Destroy>', self._on_destroy, add=True)

    # ---------------------------------------------------------------- 外から
    def set(self, decor, color, bg):
        """decor=None/'none' で消す。color は点の色、bg は欄の地の色（Canvas 用）。"""
        decor = None if decor in (None, 'none') or _art('art', decor) is None else decor
        changed = decor != self.decor
        self.decor, self.color, self.bg = decor, color, bg
        raw = self._raw()
        if changed:
            self._drop_all()
            self._origin_used = self._geom_used = None
            if decor is None:
                self._anchor_used = self._anchor_place = self._anchor_hold = None
            self._prewarm_key = self._prewarm_args = None
            self._prewarm_todo = []
            self._prewarm_count = 0
            _keeper(self.t).clear()
            if decor is None and self._guarded:
                try:
                    _ensure_tcl(self.t)
                    self.t.tk.call('::cn_paper_unguard', raw, _SLICES.solid())
                except Exception:
                    pass
                self._guarded = False
        else:
            for tag, _name, _range in self._slots:
                try:
                    self.t.tk.call(raw, 'tag', 'configure', tag, '-background', color)
                except Exception:
                    pass
        for cv in [self._below] + list(self._edges.values()):
            if cv is not None:
                try:
                    cv.configure(bg=bg)
                    cv.itemconfigure('art', foreground=color)
                except Exception:
                    pass
        self._below_key = None if changed else self._below_key
        self._edges_key = None
        self._dirty = True
        self._last = None
        self._retry = 0
        self.redraw()
        self._refresh_covers()

    def queue(self, event=None):
        """描き直しを予約する（Tk が画面を描くより先に回る after(0)）。"""
        if self.decor is None or self._job is not None:
            return
        try:
            self._job = self.t.after(0, self._run)
        except Exception:
            self._job = None

    def flush(self):
        """予約した描き直しを今すぐ済ませる。app が update_idletasks で画面を先に描かせる
        所（行への移動・中央寄せ・左右の行合わせ）の直前に呼ぶ。描かせた後で after(0) が
        回ると、ずれた絵が一度だけ画面に出てしまうため。"""
        job, self._job = self._job, None
        if job is not None:
            try:
                self.t.after_cancel(job)
            except Exception:
                pass
        if self.decor is not None:
            try:
                self.redraw()
            except Exception:
                pass

    def cover(self, top, height, border):
        """中央寄せの余白の覆い（app の _mask_navigation_margins が欄の色の Frame の代わりに
        使う）。同じ絵を描いた Canvas を返す。app が (border, top) に place する。
        装飾が無い・まだ描いていないときは None。"""
        if self.decor is None or self._origin_used is None:
            return None
        import tkinter as tk
        try:
            cv = tk.Canvas(self.t, highlightthickness=0, bd=0, bg=self.bg or self.t.cget('bg'),
                           cursor='', takefocus=0)
        except Exception:
            return None
        cv._correctnote_paper_below = True      # typing_pointer: 欄の一部として扱う
        _add_click_tag(cv)
        self._covers.append((weakref.ref(cv), border, top))
        self._refresh_covers()
        return cv

    def names_in_use(self):
        names = {name for _tag, name, _range in self._slots if name}
        if self.decor is not None:
            full = _SLICES.paths.get(('full', self.decor))
            if full:
                names.add(full)
        return names

    def _hold(self, name):
        _keeper(self.t).hold(name)

    # ---------------------------------------------------------------- 知らせ
    def _on_scrolled(self):
        # その場で描き直す（after(0) より先に別の処理が画面を描かせることがあるため）
        try:
            if self.SCROLL_HIDE and self.decor is not None:
                mark = self._view_mark()
                moved = self._view is not None and mark != self._view
                self._view = mark
                if moved or self._rest_job is not None:
                    self._hide_for_scroll()
                    return
            self.flush()
        except Exception:
            pass

    def _view_mark(self):
        raw = self._raw()
        try:
            index = str(self.t.tk.call(raw, 'index', '@0,0'))
            info = self.t.tk.splitlist(self.t.tk.call(raw, 'dlineinfo', index))
            return index, (str(info[1]) if info else '')
        except Exception:
            return None

    def _hide_for_scroll(self):
        """SCROLL_HIDE: スクロールしている間は絵を外す（止まって SCROLL_REST_MS で戻す）。"""
        if self._rest_job is None:
            raw = self._raw()
            for slot in self._slots:
                if slot[2] is not None:
                    try:
                        self.t.tk.call(raw, 'tag', 'remove', slot[0], '1.0', 'end')
                    except Exception:
                        pass
                    slot[2] = None
            self._hide_below()
            self._hide_edges()
            self._last = None
        else:
            try:
                self.t.after_cancel(self._rest_job)
            except Exception:
                pass
        try:
            self._rest_job = self.t.after(self.SCROLL_REST_MS, self._end_rest)
        except Exception:
            self._rest_job = None

    def _end_rest(self):
        self._rest_job = None
        self._dirty = True
        self._view = self._view_mark()
        try:
            self.redraw()
        except Exception:
            pass

    def _on_changed(self, args=None):
        # 字を足すと、両隣のタグを引き継ぐ。行の境目に打った字には絵が付かず、
        # 改行すると上の行の切れ端が下にも付く。行の場所が同じでも付け直す。
        self._dirty = True
        try:
            self.queue()
        except Exception:
            pass

    def _on_tagged(self):
        try:
            self.queue()
        except Exception:
            pass

    def _on_destroy(self, event=None):
        if event is not None and event.widget is not self.t:
            return
        for job in (self._job, self._settle, self._rest_job, self._prewarm_job, self._hold_job):
            if job is not None:
                try:
                    self.t.after_cancel(job)
                except Exception:
                    pass
        self._job = self._settle = self._rest_job = self._prewarm_job = self._hold_job = None
        self.decor = None
        self._slots = []
        self._covers = []
        self._prewarm_todo = []

    def _run(self):
        self._job = None
        try:
            self.redraw()
        except Exception:
            pass

    def _run_settled(self):
        self._settle = None
        try:
            self.redraw()
        except Exception:
            pass

    # ---------------------------------------------------------------- 描画
    def _raw(self):
        """元の Tk の命令（app の包みを通さない）。包みは Text を作ったすぐ後に付く。"""
        raw = getattr(self, '_raw_name', None)
        if raw is not None:
            return raw
        t = self.t
        name = t._w + '_correctnote_work'
        try:
            if t.tk.call('info', 'commands', name):
                self._raw_name = name
                return name
        except Exception:
            pass
        return t._w

    def _border(self):
        try:
            return int(self.t.cget('borderwidth')) + int(self.t.cget('highlightthickness'))
        except Exception:
            return 0

    def _ring(self):
        """枠の線（highlightthickness）。絵はその内側まで。"""
        try:
            return int(self.t.cget('highlightthickness'))
        except Exception:
            return 0

    def _pads(self):
        try:
            return int(self.t.cget('padx')), int(self.t.cget('pady'))
        except Exception:
            return 0, 0

    def _origin(self, W, H, bits):
        """絵の左上。絵の右下の角を欄の枠の内側の角に合わせる（右と下は枠でちょうど切れる。
        うにさん 2026-10-15）。3つ目は枠の太さ（borderwidth＋highlightthickness）。
        H は欄の高さ（下に出ている行があれば、そのぶんを足した高さ。_anchor）。"""
        hl = self._ring()
        return W - hl - bits.w, H - hl - bits.h, self._border()

    def _below_value(self):
        try:
            return max(0, int(getattr(self.t, '_correctnote_art_below', 0) or 0))
        except Exception:
            return 0

    def _place_in_window(self):
        """(欄の上の端の、窓の中での高さ, 窓の大きさ)。分からなければ None。"""
        try:
            top = self.t.winfo_toplevel()
            return (self.t.winfo_rooty() - top.winfo_rooty(),
                    (top.winfo_width(), top.winfo_height()))
        except Exception:
            return None

    def note_below(self):
        """`_correctnote_art_below` が変わっていたら、今の絵の位置を保ち始める（BELOW_HOLD_MS）。
        reserve_below が値を入れた直後に呼ぶ。描き直しのときにも見る。"""
        below = self._below_value()
        if below == self._below_seen:
            return
        first = self._below_seen is None
        self._below_seen = below
        # 前に描いたときの絵の右下と窓の大きさ。その後で窓の大きさが変わっていたら（最大化と
        # 同時に行が出るなど）、_anchor がすぐやめる
        place = self._anchor_place
        if first or self._anchor_used is None or place is None:
            return
        hold = self._anchor_hold
        if hold is None or hold[1] != place[1]:
            self._anchor_hold = (place[0] + self._anchor_used, place[1])
        if self._hold_job is not None:
            try:
                self.t.after_cancel(self._hold_job)
            except Exception:
                pass
        try:
            self._hold_job = self.t.after(self.BELOW_HOLD_MS, self._run_hold, self.BELOW_HOLD_IDLE)
        except Exception:
            self._hold_job = None
            self._anchor_hold = None

    def _anchor(self, H):
        """絵の右下を合わせる高さ（欄の上から）。欄の高さ＋下に出ている行のぶん。
        行を出し入れした直後は、前の位置のまま（BELOW_HOLD_MS）。"""
        self.note_below()
        hold = self._anchor_hold
        if hold is not None:
            place = self._place_in_window()
            drawn = self._anchor_place
            if place is not None and (
                    place[1] == hold[1]
                    # 窓は変わったが、この欄はまだ前に描いたときのまま（並べ直しが届いていない）
                    or (drawn is not None and (place[0], self._size) == (drawn[0], drawn[2]))):
                return hold[0] - place[0]
            self._anchor_hold = None      # 窓も欄も大きさが変わった: 今の欄に合わせる
        return H + (self._below_seen or 0)

    def _run_hold(self, passes=0):
        """保つのをやめて描き直す。時間の後、アイドルを passes 回待つ（止まっていた後でも、
        入れ子の枠の並べ直しが欄まで届いてから）。"""
        self._hold_job = None
        if self._anchor_hold is None:
            return
        if passes > 0:
            try:
                self._hold_job = self.t.after_idle(self._run_hold, passes - 1)
                return
            except Exception:
                pass
        self._anchor_hold = None
        try:
            self.redraw()
        except Exception:
            pass

    def _edge_boxes(self, W, H):
        """Text の余白（padx・pady）と枠の内側の帯 (x0, y0, x1, y1)。行は余白に描かれないので、
        絵が掛かる所は Canvas で同じ絵を見せる（スクロールしても動かない）。"""
        hl, inset = self._ring(), self._border()
        padx, pady = self._pads()
        return (('right', (W - inset - padx, hl, W - hl, H - hl)),
                ('bottom', (hl, H - inset - pady, W - hl, H - hl)),
                ('left', (hl, hl, inset + padx, H - hl)),
                ('top', (hl, hl, W - hl, inset + pady)))

    def _slice(self, bits, ox, oy, W, top, h):
        r0 = top - oy
        if r0 + h <= 0 or r0 >= bits.h:
            return None
        hs = self._tall(h)
        key = ('a', self.decor, ox, W, r0, hs)
        return _SLICES.get(key, lambda: bits.slice(r0, hs, ox, W), W, hs)

    def _tall(self, h):
        """切れ端の高さ。行の高さを SLICE_H の倍へ切り上げる。Tk は行の上の端から模様を
        敷くので、行より高い切れ端の下の余りは使われないだけ。行の高さが違っても（折り返しの
        途中・段落の頭・絵文字の行・窓の下の縁で切れた行）同じ切れ端を使い回せる。"""
        return self.SLICE_H * -(-h // self.SLICE_H)

    def _full(self, bits):
        """絵を丸ごと1枚にした xbm（下の Canvas と中央寄せの覆いで使う）。"""
        return _SLICES.get(('full', self.decor), lambda: bits.slice(0, bits.h, 0, bits.w),
                           bits.w, bits.h)

    def _place_art(self, cv, name, x, y):
        items = cv.find_withtag('art')
        if items:
            cv.coords(items[0], x, y)
            if str(cv.itemcget(items[0], 'bitmap')) != name:
                cv.itemconfigure(items[0], bitmap=name)
            cv.itemconfigure(items[0], foreground=self.color)
        else:
            cv.create_bitmap(x, y, anchor='nw', bitmap=name, foreground=self.color, tags=('art',))

    def _lost(self, name):
        """Tk が切れ端を読めなかった（一時フォルダの掃除などでファイルが消えた）。
        忘れて、次の回に書き直す（続けて RETRY 回まで）。"""
        _SLICES.drop(name)
        _keeper(self.t).forget(name)
        self._last = None
        self._dirty = True
        if self._retry < self.RETRY:
            self._retry += 1
            self.queue()

    def _drop_all(self):
        raw = self._raw()
        for tag, _name, _range in self._slots:
            try:
                self.t.tk.call(raw, 'tag', 'delete', tag)
            except Exception:
                pass
        self._slots = []
        self._last = None
        self._hide_below()
        self._hide_edges()

    def _hide_below(self):
        if self._below is not None:
            try:
                self._below.place_forget()
            except Exception:
                pass
        self._below_key = None

    def redraw(self):
        t = self.t
        if self.decor is None:
            if self._slots or self._below_key or self._edges_key:
                self._drop_all()
            return
        bits = _art('art', self.decor)
        try:
            if bits is None or not t.winfo_ismapped():
                return
            W = t.winfo_width()
            H = t.winfo_height()
        except Exception:
            return
        if W < 20 or H < 20 or self._rest_job is not None:
            return
        # 幅を変えている間は、新しい切れ端を作らずに前の位置・前の幅の絵のまま付け直す
        # （スクロールしても絵は動かない）。止まって SETTLE_MS で新しい位置へ。
        # 高さだけの変化は待たない（切れ端は前と同じものが使える）。
        now = time.monotonic()
        if self._size != (W, H):
            if self._size is not None and self._size[0] != W:
                self._size_at = now
            self._size = (W, H)
        settling = (self._geom_used is not None
                    and now - self._size_at < self.SETTLE_MS / 1000.0)
        raw = self._raw()
        if settling:
            self._wait_settle()
            ox, oy, Wg = self._geom_used
            if W > Wg:
                # 広げている間に前の幅の切れ端を付けると、Tk は模様を横に繰り返すので
                # 絵がもう1つ出る。前の位置のまま、今の幅以上（256 刻み）の切れ端にする
                Wg = -(-W // 256) * 256
            bd = self._border()
        else:
            anchor = self._anchor(H)
            ox, oy, bd = self._origin(W, anchor, bits)
            Wg = W
        y_top, y_bot = max(0, oy), min(H - bd, oy + bits.h)
        try:
            _ensure_tcl(t)
            try:
                t.tk.call('::cn_paper_guard', raw, _SLICES.solid())
            except Exception:
                _SLICES.solid_name = None     # 消されていた: 書き直す
                t.tk.call('::cn_paper_guard', raw, _SLICES.solid())
            self._guarded = True
            # w は元の Tk の命令（窓の名前ではない）なので、窓の高さはこちらから渡す
            how, flat = t.tk.splitlist(t.tk.call('::cn_paper_lines', raw, y_top, y_bot, H - bd))
            flat = t.tk.splitlist(flat)
        except Exception:
            return
        lines = [(str(flat[i]), str(flat[i + 1]), int(flat[i + 2]), int(flat[i + 3]))
                 for i in range(0, len(flat) - 3, 4)]
        key = (self.decor, Wg, H, ox, oy, str(how), tuple(lines))
        if key == self._last and not self._dirty:
            return
        self._last = key
        if not self._apply_slots(raw, bits, ox, oy, Wg, lines):
            self._last = None
            return
        if not settling:
            self._geom_used = (ox, oy, W)
            self._anchor_used = anchor
            place = self._place_in_window()
            self._anchor_place = None if place is None else place + ((W, H),)
            if self._origin_used != (ox, oy):
                self._origin_used = (ox, oy)
                self._refresh_covers()
            self._prewarm(bits, ox, W, {h for _s, _e, _y, h in lines if h > 0})
        # 最後の行より下
        last_bottom = None
        if str(how) == 'end':
            last_bottom = (lines[-1][2] + lines[-1][3]) if lines else y_top
        self._draw_below(bits, ox, oy, W, H, bd, last_bottom, y_bot)
        self._draw_edges(bits, ox, oy, W, H)
        if self.SCROLL_HIDE:
            self._view = self._view_mark()
        _SLICES.trim()

    def _apply_slots(self, raw, bits, ox, oy, W, lines):
        """表示行ごとのタグに切れ端を付ける。続けられないときは False。"""
        t = self.t
        dirty, self._dirty = self._dirty, False
        failed = False
        wanted = []
        for start, end, y, h in lines:
            if h <= 0:
                continue
            name = self._slice(bits, ox, oy, W, y, h)
            if name:
                wanted.append((name, (start, end)))
        for i, (name, rng) in enumerate(wanted):
            if i >= len(self._slots):
                tag = f'{self._prefix}{i}'
                try:
                    t.tk.call(raw, 'tag', 'configure', tag, '-background', self.color)
                    t.tk.call(raw, 'tag', 'lower', tag)
                except Exception:
                    return False
                slot = [tag, None, None]
                self._slots.append(slot)
            else:
                slot = self._slots[i]
            try:
                if slot[1] != name:
                    self._hold(name)
                    try:
                        t.tk.call(raw, 'tag', 'configure', slot[0], '-bgstipple', name)
                    except Exception:
                        failed = True
                        self._lost(name)
                        continue
                    slot[1] = name
                if slot[2] != rng or dirty:
                    t.tk.call(raw, 'tag', 'remove', slot[0], '1.0', 'end')
                    t.tk.call(raw, 'tag', 'add', slot[0], rng[0], rng[1])
                    slot[2] = rng
            except Exception:
                slot[2] = None
        for slot in self._slots[len(wanted):]:
            if slot[2] is not None or dirty:
                try:
                    t.tk.call(raw, 'tag', 'remove', slot[0], '1.0', 'end')
                except Exception:
                    pass
                slot[2] = None
        if not failed:
            self._retry = 0
        return True

    def _prewarm(self, bits, ox, W, heights):
        """今の行の高さぶんの切れ端を、手が空いている間に少しずつ作って Tk に持たせる。
        スクロールで行が1画素ずつ動くと、行ごとの切れ端が全部新しくなる（作る・読むの分だけ
        最初の1歩が重い。PC で 1歩 125ms → 245ms）。"""
        tall = {self._tall(h) for h in heights if self._tall(h) <= 2 * self.SLICE_H}
        if not tall:
            return
        key = (self.decor, ox, W)
        done = self._prewarm_key[1] if self._prewarm_key and self._prewarm_key[0] == key else set()
        new = tall - done
        if not new:
            return
        self._prewarm_key = (key, done | new)
        todo = [(r0, hs) for hs in sorted(new, reverse=True) for r0 in range(bits.h - 1, -hs, -1)]
        if self._prewarm_args == key:
            self._prewarm_todo = todo + self._prewarm_todo
        else:
            self._prewarm_todo = todo
            self._prewarm_count = 0
        self._prewarm_args = key
        if self._prewarm_job is None:
            try:
                self._prewarm_job = self.t.after(self.PREWARM_GAP_MS * 4, self._prewarm_step)
            except Exception:
                self._prewarm_job = None

    def _prewarm_step(self):
        self._prewarm_job = None
        args = self._prewarm_args
        if not self._prewarm_todo or args is None or args[0] != self.decor or self.decor is None:
            self._prewarm_todo = []
            return
        decor, ox, W = args
        bits = _art('art', decor)
        keeper = _keeper(self.t)
        end = time.perf_counter() + self.PREWARM_SLICE_S
        try:
            while self._prewarm_todo and time.perf_counter() < end:
                r0, h = self._prewarm_todo.pop()
                key = ('a', decor, ox, W, r0, h)
                name = _SLICES.get(key, lambda: bits.slice(r0, h, ox, W), W, h)
                if name:
                    keeper.hold(name)
                    self._prewarm_count += 1
        except Exception:
            self._prewarm_todo = []
            return
        if self._prewarm_count >= keeper.KEEP // 2:
            self._prewarm_todo = []         # 両方の欄で持てる数まで（これ以上は入れ替わるだけ）
        _SLICES.trim()
        if self._prewarm_todo:
            try:
                self._prewarm_job = self.t.after(self.PREWARM_GAP_MS, self._prewarm_step)
            except Exception:
                self._prewarm_job = None

    def _wait_settle(self):
        if self._settle is not None:
            try:
                self.t.after_cancel(self._settle)
            except Exception:
                pass
        try:
            self._settle = self.t.after(self.SETTLE_MS, self._run_settled)
        except Exception:
            self._settle = None

    def _draw_below(self, bits, ox, oy, W, H, bd, last_bottom, y_bot):
        """最後の行より下に、絵を丸ごと描いた Canvas を置く（Canvas が欄の外を切る）。
        行が増えても減っても、置き場所と絵の位置を動かすだけ（切れ端を作らない）。"""
        top = None
        hl = self._ring()
        if last_bottom is not None:
            top = max(last_bottom, bd)
            if top >= y_bot or H - hl - top <= 0:
                top = None
        name = self._full(bits) if top is not None else None
        if name is None:
            if self._below_key is not None:
                self._hide_below()
            return
        key = (name, top, W, H, ox, oy, hl, self.color, self.bg)
        if key == self._below_key:
            return
        cv = self._ensure_below()
        try:
            self._place_art(cv, name, ox - hl, oy - top)
            cv.configure(bg=self.bg)
            cv.place(x=hl, y=top, width=max(1, W - 2 * hl), height=H - hl - top,
                     bordermode='outside')
            cv.tk.call('lower', cv._w)
            self._below_key = key
        except Exception:
            self._hide_below()
            self._lost(name)

    def _refresh_covers(self):
        """中央寄せの余白の覆いを、今の装飾・色・絵の位置に合わせる。"""
        live = []
        bits = _art('art', self.decor) if self.decor else None
        for ref, x, y in self._covers:
            cv = ref()
            try:
                if cv is None or not cv.winfo_exists():
                    continue
            except Exception:
                continue
            live.append((ref, x, y))
            try:
                cv.configure(bg=self.bg)
                if bits is None or self._origin_used is None:
                    cv.delete('art')
                    continue
                name = self._full(bits)
                if name:
                    self._place_art(cv, name, self._origin_used[0] - x, self._origin_used[1] - y)
            except Exception:
                pass
        self._covers = live

    def _ensure_below(self):
        if self._below is None:
            self._below = self._art_canvas()
        return self._below

    def _art_canvas(self):
        """欄の中に置く、絵を描く Canvas（最後の行より下・余白の帯）。押す・離す・動かす・
        ホイールは Text へ渡し、続けて押した数は CLICK_TAG が数える。"""
        import tkinter as tk
        t = self.t
        # cursor='' で、Text の今のカーソルの形（矢印・指・隠す）に従う
        cv = tk.Canvas(t, highlightthickness=0, bd=0, bg=self.bg or t.cget('bg'),
                       cursor='', takefocus=0)
        cv._correctnote_paper_below = True      # typing_pointer: 欄の一部として扱う
        _add_click_tag(cv)

        def forward(event, seq):
            options = dict(x=event.x_root - t.winfo_rootx(), y=event.y_root - t.winfo_rooty(),
                           rootx=event.x_root, rooty=event.y_root, state=event.state)
            # 押した時刻も渡す（無いと 0 になる）。app の右の二度押し（縮小）は時刻で見分ける
            # （emoji_color の札から渡すのと同じ）
            try:
                options['time'] = int(event.time)
            except Exception:
                pass
            if seq == '<MouseWheel>':
                options['delta'] = event.delta
            elif seq in ('<ButtonPress>', '<ButtonRelease>'):
                seq = '<%s-%s>' % (seq[1:-1], event.num)
                if seq == '<ButtonPress-1>':
                    try:
                        t.focus_set()
                    except Exception:
                        pass
            try:
                t.event_generate(seq, **options)
                if seq == '<Motion>' and event.state & 0x100:
                    self._auto_scan(options['x'], options['y'])
            except Exception:
                pass
            return 'break'

        for seq in ('<ButtonPress>', '<ButtonRelease>', '<Motion>', '<MouseWheel>'):
            cv.bind(seq, lambda e, s=seq: forward(e, s))
        return cv

    def _auto_scan(self, x, y):
        """押したまま動かしている（選択を広げている）。Canvas が押した所の窓になるので、
        Text には <B1-Leave> が来ない。欄の外へ出たら Text と同じ自動スクロールを始め、
        戻ったら止める（Tk の text.tcl の <B1-Leave>・<B1-Enter> と同じ）。"""
        t = self.t
        outside = x < 0 or y < 0 or x >= t.winfo_width() or y >= t.winfo_height()
        running = t.tk.eval('expr {[info exists ::tk::Priv(afterId)] && $::tk::Priv(afterId) ne ""}') == '1'
        if outside and not running:
            t.tk.call('set', '::tk::Priv(x)', x)
            t.tk.call('set', '::tk::Priv(y)', y)
            t.tk.call('::tk::TextAutoScan', t._w)
        elif not outside and running:
            t.tk.call('::tk::CancelRepeat')

    def _draw_edges(self, bits, ox, oy, W, H):
        """余白の帯に、行の裏と同じ位置の絵を見せる（絵が掛かる帯だけ）。"""
        name = self._full(bits)
        boxes = self._edge_boxes(W, H)
        key = (name, ox, oy, W, H, boxes, self.color, self.bg)
        if key == self._edges_key:
            return
        self._edges_key = key
        for side, (x0, y0, x1, y1) in boxes:
            show = (name is not None and x1 > x0 and y1 > y0 and ox < x1 and ox + bits.w > x0
                    and oy < y1 and oy + bits.h > y0)
            cv = self._edges.get(side)
            if not show:
                if cv is not None:
                    try:
                        cv.place_forget()
                    except Exception:
                        pass
                continue
            try:
                if cv is None or not cv.winfo_exists():
                    cv = self._edges[side] = self._art_canvas()
                self._place_art(cv, name, ox - x0, oy - y0)
                cv.configure(bg=self.bg)
                cv.place(x=x0, y=y0, width=x1 - x0, height=y1 - y0, bordermode='outside')
                cv.tk.call('lower', cv._w)
            except Exception:
                self._edges_key = None
                self._lost(name)
                return

    def _hide_edges(self):
        for cv in self._edges.values():
            try:
                cv.place_forget()
            except Exception:
                pass
        self._edges_key = None


class GutterBackdrop:
    """行番号の欄（Canvas）の裏の模様。LineNumberGutter.redraw が draw(canvas, 幅) を呼ぶ。

    模様は欄に対して動かない（行番号だけが上を流れる）。消さずに残しておき、
    装飾・色・幅・高さが変わったときだけ描き直す（Tk はファイルの絵を、どこにも
    使われなくなると忘れて、次はまた読み直すため）。"""
    TAG = 'cn_backdrop'

    def __init__(self):
        self.decor = None
        self.color = None
        self._key = None
        self._name = None
        _OWNERS.add(self)

    def set(self, decor, color):
        decor = None if decor in (None, 'none') else decor
        self.decor = decor if decor is None or _art('gutter', decor) is not None else None
        self.color = color

    def names_in_use(self):
        return {self._name} if self._name else set()

    def draw(self, canvas, width, _retry=True):
        tag = self.TAG
        if not self.decor or not self.color:
            if self._key is not None:
                canvas.delete(tag)
                self._key = None
                self._name = None
            return
        bits = _art('gutter', self.decor)
        if bits is None:
            return
        name = _SLICES.get(('g', self.decor), lambda: bits.slice(0, bits.h, 0, bits.w),
                           bits.w, bits.h)
        if not name:
            return
        height = max(int(canvas.winfo_height()), 1)
        key = (name, self.color, int(width), height)
        if key == self._key and canvas.find_withtag(tag):
            return
        canvas.delete(tag)
        try:
            y = 0
            while y < height:
                canvas.create_bitmap(width, y, anchor='ne', bitmap=name, foreground=self.color,
                                     state='disabled', tags=(tag,))
                y += bits.h
        except Exception:
            # ファイルが消されていた（一時フォルダの掃除など）: 書き直して1回だけやり直す
            canvas.delete(tag)
            _SLICES.drop(name)
            self._key = self._name = None
            if _retry:
                self.draw(canvas, width, _retry=False)
            return
        canvas.tag_lower(tag)
        self._key = key
        self._name = name
