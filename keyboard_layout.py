# -*- coding: utf-8 -*-
# CorrectNote — 誤字補正メモ帳
# Copyright (C) 2026 Takahashi Yuu
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""
**キーボードの配列と形**（項目48-KB・2026-10-14）。

うにさんの指定（2026-10-14）:

> 「オプションにキーボード配列を追加して、QWERTY以外や、他に配列が
>   変わるもの、左右で分割されたキーボードなどの選択を用意してください。
>   これは隣接キーに影響します。」

隣接キーの表は、今まで `corrector`（QWERTY 4段・記号つき）・
`loanword`（英字3段）・`en_space`（英字3段）がそれぞれ QWERTY を
書き下していた。配列を選べるようにするには**表を1か所で持つ**
必要があるので（48-GN「同じ表を2つ作らない」）、ここに集めた。
**既定（QWERTY・JIS・標準の形）では3つの表の中身は1組も変わらない**
（tests_keyboard_layout_20261014 で、昔の書き下しと突き合わせている）。

3つの軸で選ぶ:

  配列（layout）  どのキーにどの字が刻まれているか。**ローマ字入力と
                  英字の隣接**に効く。かな入力の字の位置（かな配列）は
                  別の軸——かな入力の人は、刻印の英字が Dvorak でも
                  かなは JIS（または選んだかな配列）の位置で打つ。

                    qwerty_jis   今までどおり（既定）
                    qwerty_us    記号の位置が違う（英字は同じ）
                    dvorak / colemak / colemak_dh / workman
                    eucalyn      日本で作られた配列（JIS の記号つき）
                    azerty / qwertz
                    custom       自分で書く（下の「段の書き方」）

  形（shape）     キーの並び方。**かな入力・ローマ字入力の両方**に効く。

                    standard     段が少しずつ右へずれている（ふつうの
                                 キーボード・既定）
                    split        左右に分かれている（段ずれあり。
                                 Mistel Barocco・Kinesis Freestyle など）
                    ortho        格子（縦横まっすぐ。Planck など）
                    split_ortho  左右に分かれた格子（ErgoDox・Corne・
                                 Keyball など。列ごとの縦ずれは、隣が
                                 どれかには関係ない）

  かな配列（kana） かな入力でどのキーにどのかなが刻まれているか
                  （**かな入力の隣接**に効く。2026-10-14 にうにさんが
                  カードで「用意する」）。表と物差しは kana_layout が持ち、
                  ここからは `set_kana_layout` で合わせるだけ。

                    jis          JIS かな（既定・今までどおり）
                    nicola       親指シフト（NICOLA）。濁音・半濁音は
                                 親指との同時打鍵＝1打。面は 単独・左親指・
                                 右親指の3つ
                    shin_jis     新JIS（JIS X 6004）。Shift の2面、
                                 ゛ は中段、゜ は Shift＋W

分割の境は t|y・g|h・b|n。数字の段は、段ずれのある分割では 6|7
（6 は左の手の側に付く製品が多い）、格子の分割では 5|6（左右 6 列ずつ）。
**別の手の側のキーは隣としない**（置き換えも巻き込みも）。
格子では、段のずれ（`kana_layout.ROW_OFFSET`）を 0 にし、上下の隣は
**同じ列だけ**（斜めは隣ではない）。この物差しは `kana_layout` が持ち、
ここからは `set_shape` で合わせるだけ。

**段の書き方**は Hunspell の `KEY` と同じ:

    qwertyuiop|asdfghjkl|zxcvbnm

段を `|`（か改行）で区切る。空白は読み飛ばす。3段なら数字の段は
JIS のものを頭に足す。4段ならそのまま（0段目が数字の段）。
英字が 20 字に届かないものは配列として受けない（既定に戻る）。

使い方:

    import keyboard_layout
    # 設定: keyboard_layout / keyboard_shape / keyboard_custom_rows / kana_layout
    keyboard_layout.apply('dvorak', 'split')   # 変わらなければ何もしない
    keyboard_layout.on_change(callback)        # 表を持つ側が登録。
                                               # 登録したときに1回呼ばれる

設定から:  `apply_spec(spec(settings))`。解析の子（別プロセス）には
           task['keyboard'] に `spec(settings)` を載せて渡し、子は
           `correct_line` の前に `apply_spec` を呼ぶ（変わらなければ無料）。
控えの指紋: `spec_text(spec)`（analysis_cache.build_fingerprint）。
測るとき:  環境変数 `CN_KEYBOARD=dvorak` `CN_KEYBOARD_SHAPE=split`
           `CN_KEYBOARD_ROWS='...|...|...'`（読み込み時に当てる）。

ここで変わるのは**隣接の表だけ**。半角の記号の Shift の取り違え
（`halfwidth`）は JIS のまま——配列ごとの記号の段はまだ持たない。
"""
import os

import kana_layout

DEFAULT_LAYOUT = 'qwerty_jis'
DEFAULT_SHAPE = 'standard'
CUSTOM = 'custom'

# 段は 0=数字段・1=上段・2=中段・3=下段。列は左端が 0。
# 記号も置くのは、`ー` が `-`（数字段）で、Dvorak の `'` `,` `.` が
# 字の手前に挟まるため（列の数を正しく数える）。
# qwerty_jis は corrector が持っていた表そのまま（2026-10-14 まで）。
LAYOUT_ROWS = {
    'qwerty_jis': ('1234567890-^¥', 'qwertyuiop@[', 'asdfghjkl;:]',
                   'zxcvbnm,./\\'),
    'qwerty_us': ('1234567890-=', 'qwertyuiop[]\\', "asdfghjkl;'",
                  'zxcvbnm,./'),
    'dvorak': ('1234567890[]', "',.pyfgcrl/=\\", 'aoeuidhtns-',
               ';qjkxbmwvz'),
    'colemak': ('1234567890-=', 'qwfpgjluy;[]\\', "arstdhneio'",
                'zxcvbkm,./'),
    # Colemak-DH の標準形（z が左端。ANSI 向けの変種は z を v の右に置く）
    # Colemak-DH は段ずれの標準形（ANSI: X C D V Z が Z X C V B の位置）。格子形の
    # 並び z x c d v は、標準形では v|k が隣になってしまう（表示スレッドの査読・2026-10-14）
    'colemak_dh': ('1234567890-=', 'qwfpbjluy;[]\\', "arstgmneio'",
                   'xcdvzkh,./'),
    'workman': ('1234567890-=', 'qdrwbjfup;[]\\', "ashtgyneoi'",
                'zxmcvkl,./'),
    'eucalyn': ('1234567890-^¥', 'qw,.;mrdyp@[', 'aoeiugtksn:]',
                'zxcvfbhjl/\\'),
    'azerty': ('&é"\'(-è_çà)=', 'azertyuiop^$', 'qsdfghjklmù*',
               'wxcvbn,;:!'),
    'qwertz': ('1234567890ß´', 'qwertzuiopü+', 'asdfghjklöä#',
               'yxcvbnm,.-'),
}
LAYOUTS = tuple(LAYOUT_ROWS) + (CUSTOM,)
SHAPES = kana_layout.SHAPES
# かな配列（項目48-KB・かな配列・2026-10-14。うにさんがカードで「用意する」）。
# 表と意味は kana_layout（KANA_LAYOUTS・set_kana_layout）。既定 jis。
KANA_LAYOUTS = kana_layout.KANA_LAYOUTS
DEFAULT_KANA = kana_layout.DEFAULT_KANA_LAYOUT

# いまの状態。表は `_build` が作り、`apply` が差し替える。
_rows = LAYOUT_ROWS[DEFAULT_LAYOUT]
_layout = DEFAULT_LAYOUT
_shape = DEFAULT_SHAPE
_custom = ''
_kana = DEFAULT_KANA
_pos = {}
_near = frozenset()
_intrusion = frozenset()
_letter_pos = {}
_letter_near = frozenset()
_letter_intrusion = frozenset()
_listeners = []


def parse_rows(text):
    """`qwertyuiop|asdfghjkl|zxcvbnm` の形を段の並びにする。だめなら None。

    同じ字が2度出たら最初の位置を採る（Hunspell の KEY は同じ字を
    何度も書いて隣を増やせるが、ここでは位置を1つに決める）。
    """
    if not isinstance(text, str):
        return None
    rows = [''.join(r.split()).lower()
            for r in text.replace('\n', '|').split('|')]
    rows = [r for r in rows if r]
    if len(rows) == 3:
        # 手書きの段に使われた字は数字段から外す。**外した位置は穴にする**
        # （詰めると ^ や ¥ が左へ寄って、0↔^ が隣になる。空白は _build が飛ばす）
        used = set(''.join(rows))
        number_row = ''.join(ch if ch not in used else ' '
                             for ch in LAYOUT_ROWS[DEFAULT_LAYOUT][0])
        rows = [number_row] + rows
    if len(rows) != 4:
        return None
    letters = {ch for r in rows for ch in r if 'a' <= ch <= 'z'}
    if len(letters) < 20:
        return None
    return tuple(rows)


def _letter_intrude(pa, pb):
    """英字3段の巻き込み（loanword が持っていた形）: 縦横斜めの8方向。

    格子では斜めは隣ではない。分割では別の手の側は隣ではない。
    """
    if pa == pb or not kana_layout.same_half(pa, pb):
        return False
    dr, dc = abs(pa[0] - pb[0]), abs(pa[1] - pb[1])
    if dr == 0:
        return dc == 1
    if dr != 1:
        return False
    return dc == 0 or (dc == 1 and not kana_layout.is_ortho())


def _build():
    global _pos, _near, _intrusion, _letter_pos, _letter_near, _letter_intrusion
    pos = {}
    for r, row in enumerate(_rows):
        for c, ch in enumerate(row):
            if ch == ' ':           # 穴（キーが無い・使われた字を外した所）
                continue
            pos.setdefault(ch, (r, c))
    adjacent = kana_layout.physical_keys_adjacent
    intrude = kana_layout.physical_intrusion_keys_adjacent
    _pos = pos
    _near = frozenset((a, b) for a, pa in pos.items()
                      for b, pb in pos.items() if adjacent(pa, pb))
    _intrusion = frozenset((a, b) for a, pa in pos.items()
                           for b, pb in pos.items() if intrude(pa, pb))
    letters = {ch: p for ch, p in pos.items() if 'a' <= ch <= 'z'}
    _letter_pos = letters
    _letter_near = frozenset((a, b) for a, pa in letters.items()
                             for b, pb in letters.items() if adjacent(pa, pb))
    _letter_intrusion = frozenset((a, b) for a, pa in letters.items()
                                  for b, pb in letters.items()
                                  if _letter_intrude(pa, pb))


def apply(layout=None, shape=None, custom_rows=None, kana=None):
    """配列・形・かな配列を当てる。表が変わったら真。変わらなければ何もしない。

    知らない名前・読めない段は既定（QWERTY JIS・標準・JIS かな）に落とす——
    設定ファイルが壊れていても補正は止めない（settings の考えと同じ）。
    """
    global _rows, _layout, _shape, _custom, _kana
    layout = layout if layout in LAYOUTS else DEFAULT_LAYOUT
    shape = shape if shape in SHAPES else DEFAULT_SHAPE
    kana = kana if kana in KANA_LAYOUTS else DEFAULT_KANA
    custom = custom_rows if isinstance(custom_rows, str) else ''
    if layout == CUSTOM:
        rows = parse_rows(custom)
        if rows is None:
            layout, rows, custom = DEFAULT_LAYOUT, LAYOUT_ROWS[DEFAULT_LAYOUT], ''
    else:
        rows, custom = LAYOUT_ROWS[layout], ''
    shape_changed = kana_layout.set_shape(shape)
    kana_changed = kana_layout.set_kana_layout(kana)
    changed = shape_changed or kana_changed or rows != _rows or not _pos
    _rows, _layout, _shape, _custom, _kana = rows, layout, shape, custom, kana
    if not changed:
        return False
    _build()
    # ローマ字の隣の組（`_romaji_pairs`）・近い字（`nearby_candidates`）は
    # 配列にも依るので、形が同じでも捨てる
    kana_layout.clear_caches()
    for callback in list(_listeners):
        callback()
    return True


def on_change(callback):
    """表を持つ側（corrector・loanword・en_space）が登録する。すぐ1回呼ぶ。"""
    if callback not in _listeners:
        _listeners.append(callback)
    callback()


def current():
    """(配列, 形, 自分で書いた段, かな配列) のいま。"""
    return (_layout, _shape, _custom, _kana)


def rows():
    return _rows


def positions():
    """字 → (段, 列)。数字・記号も入る（corrector の `_QWERTY_POS` の形）。"""
    return _pos


def near_pairs():
    """同じ段の左右の隣（置き換え）。corrector の `_QWERTY_NEAR`。"""
    return _near


def intrusion_pairs():
    """巻き込みの隣（JIS の方向の決まり）。corrector の `_QWERTY_INTRUSION_NEAR`。"""
    return _intrusion


def letter_positions():
    """a〜z だけの位置（loanword・en_space の `_QWERTY_POS` の字と順。値は4段の (段, 列)
    なので q は (1, 0)——昔の3段の書き下し (0, 0) とは違う。使う側は字しか見ない）。"""
    return _letter_pos


def letter_near_pairs():
    return _letter_near


def letter_intrusion_pairs():
    return _letter_intrusion


# --- 設定との橋 ---

def spec(settings):
    """設定から (配列, 形, 自分で書いた段, かな配列)。設定が無い・壊れていれば既定。
    かな配列は 'input_method' が 'kana' のときだけ（ローマ字入力では JIS）。

    `settings` は `Settings` でも素の dict でもよい（試験は dict を使う）。
    """
    get = getattr(settings, 'get', None)
    if get is None:
        return (DEFAULT_LAYOUT, DEFAULT_SHAPE, '', DEFAULT_KANA)
    layout = get('keyboard_layout')
    shape = get('keyboard_shape')
    custom = get('keyboard_custom_rows')
    kana = get('kana_layout')
    layout = layout if layout in LAYOUTS else DEFAULT_LAYOUT
    shape = shape if shape in SHAPES else DEFAULT_SHAPE
    kana = kana if kana in KANA_LAYOUTS else DEFAULT_KANA
    # かな配列はかな入力のときだけ効く。ローマ字入力では打つキーは英字なので
    # かなの表は JIS のまま（小書き・「を」の Shift の直しは JIS の同じキーの
    # 相方で見る、2026-10-14 までと同じ）。'input_method' を持たない素の dict
    # は門を通す（試験・測るとき）。表示スレッドの確認 2026-10-15 で、ローマ字
    # のまま親指シフトを選ぶと「寒ぃ日だ→寒い日だ」が消えた件。
    if get('input_method') not in (None, 'kana'):
        kana = DEFAULT_KANA
    custom = custom if (layout == CUSTOM and isinstance(custom, str)) else ''
    return (layout, shape, custom, kana)


def _parts(spec_):
    """組を4つに揃える（3つの古い組・JSON の list も読める。組でない値は既定）。"""
    if not spec_:
        return (DEFAULT_LAYOUT, DEFAULT_SHAPE, '', DEFAULT_KANA)
    try:
        items = tuple(spec_)
    except TypeError:
        return (DEFAULT_LAYOUT, DEFAULT_SHAPE, '', DEFAULT_KANA)
    layout, shape, custom, kana = (items + (None, None, None, None))[:4]
    return (layout, shape, custom, kana)


def apply_spec(spec_):
    """`spec` の組を当てる（task['keyboard']）。無ければ既定を当てる。"""
    if not spec_:
        return apply()
    layout, shape, custom, kana = _parts(spec_)
    return apply(layout, shape, custom, kana)


def spec_text(spec_):
    """控えの指紋に入れる1行（JSON を往復しても同じ値のまま）。"""
    layout, shape, custom, kana = _parts(spec_)
    layout = layout if layout in LAYOUTS else DEFAULT_LAYOUT
    shape = shape if shape in SHAPES else DEFAULT_SHAPE
    kana = kana if kana in KANA_LAYOUTS else DEFAULT_KANA
    text = f'{layout}/{shape}/{kana}'
    return text + (f'/{custom}' if layout == CUSTOM and custom else '')


def describe(spec_=None):
    """画面・trace 向けの短い名前（`Dvorak・左右分割・親指シフト` のように）。"""
    layout, shape, custom, kana = _parts(spec_ or current())
    names = {'qwerty_jis': 'QWERTY(JIS)', 'qwerty_us': 'QWERTY(US)',
             'dvorak': 'Dvorak', 'colemak': 'Colemak',
             'colemak_dh': 'Colemak-DH', 'workman': 'Workman',
             'eucalyn': 'Eucalyn', 'azerty': 'AZERTY', 'qwertz': 'QWERTZ',
             CUSTOM: '手書き'}
    shapes = {'standard': '標準', 'split': '左右分割', 'ortho': '格子',
              'split_ortho': '左右分割・格子'}
    kanas = {'jis': '', 'nicola': '親指シフト', 'shin_jis': '新JIS'}
    text = f"{names.get(layout, layout)}・{shapes.get(shape, shape)}"
    kana_name = kanas.get(kana, kana)
    return text + (f'・{kana_name}' if kana_name else '')


def _apply_env():
    """測るときの切り替え口。CN_KEYBOARD / CN_KEYBOARD_SHAPE / CN_KEYBOARD_ROWS / CN_KANA_LAYOUT。"""
    layout = os.environ.get('CN_KEYBOARD') or None
    shape = os.environ.get('CN_KEYBOARD_SHAPE') or None
    rows_ = os.environ.get('CN_KEYBOARD_ROWS') or None
    kana = os.environ.get('CN_KANA_LAYOUT') or None
    if rows_ and not layout:
        layout = CUSTOM
    apply(layout, shape, rows_, kana)


_apply_env()
