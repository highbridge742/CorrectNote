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
CorrectNote - オフライン誤字補正つきメモ帳

かな入力（JIS配列）での隣接キー押し間違いを、
オンラインAIを使わずローカルの語彙学習だけで補正する。

左のメモに入力すると、右に補正後のテキストが行ごとに対応して表示される。

使い方:
    python app.py

必要なもの:
    Python 3.8 以降（tkinter は標準で同梱）
"""

import os
import sys
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from vocabulary import VocabularyStore, find_known_readings_flex
from decisions import DecisionStore
from last_choice import LastChoiceStore
from candidates import (build_candidates, build_range_candidates,
                        symbol_candidates, is_symbol_word, MENU_KINDS)
from units import build_line_units, unit_at, make_range_unit, build_suspect_units
from dict_index import DictIndex
from session import SessionStore, new_tab, tab_title, is_blank
import search as searchlib
from settings import (Settings, effective_hotkeys,
                      LAYOUT_LABELS, LAYOUT_SPLIT, LAYOUT_UNIFIED,
                      INPUT_METHOD_LABELS, INPUT_KANA, INPUT_ROMAJI)
from hotkeys import GlobalHotkeys, HOTKEY_LABELS
from ime_readings import IMEReadings, is_kana_reading as ime_readings_kana
# 候補一覧のいちばん下に出す説明（項目48-MD・2026-08-31）。
# **画面に出す言葉を作るだけ**——補正の答えには触らない。
import explain

#: 候補一覧のいちばん下に足す説明の見出し（項目48-MD）。
#: **決めているのはこの2行**——`_make_dropdown` が「ここから下は
#: 説明」を知るのにも使う（項目48-ML）ので、書き写さないこと。
ANALYSIS_HEAD_POS = '－ 品詞判定 －'
ANALYSIS_HEAD_WHY = '－ 補正根拠 －'

#: 候補一覧に一度に見せる行数（項目48-ML）。
#: `DROPDOWN_ROWS` はこれまでどおり 16。**説明（品詞判定・補正根拠）が
#: 付いているときは、その分だけ伸ばす**——説明は**いちばん下**に足すので、
#: 16 で切ると候補の多い語では画面の外へ出る。しかも上下キーは
#: 選べない行（見出し）を飛ばすので、**キーボードでは届かない**。
#: `DROPDOWN_ROWS_MAX` は伸ばしすぎの止め（画面からはみ出さないため）。
#: 実測（実機メモ400行・説明を出した状態）: **いちばん多い語で 21 項目**。
DROPDOWN_ROWS = 16
DROPDOWN_ROWS_MAX = 26
import corrector


class _FakeEvent:
    """
    座標だけを持つ、作り物のイベント。

    F2 から候補一覧を呼ぶときに使う。候補一覧の表示処理は
    右クリックのイベント（マウス座標を持つ）を前提に書かれて
    いるため、キー操作から呼ぶ場合も同じ形を渡してやると、
    表示処理をそのまま使い回せる。
    """
    __slots__ = ('x', 'y', 'x_root', 'y_root', 'widget')


# F2 の対象になれる「語」の文字（かな・カタカナ・漢字・英数字）。
# 句読点・記号だけの単位は対象にしない。
import re as _re
_f2_word_re = _re.compile(
    '[0-9A-Za-zぁ-んァ-ヶー\u4e00-\u9fff'
    '\uff10-\uff19\uff21-\uff3a\uff41-\uff5a]')


def is_touch_pointer():
    """
    いま処理中のマウスイベントがタッチ（指）由来か（Windowsのみ）。

    Windows はタッチをマウスイベントに変換して届けるが、
    GetMessageExtraInfo の上位バイトに印（0xFF515700）が残る。
    tkinter からはイベントの由来が分からないので、これで見分ける。
    """
    if sys.platform != 'win32':
        return False
    try:
        import ctypes
        info = ctypes.windll.user32.GetMessageExtraInfo()
        return (info & 0xFFFFFF00) == 0xFF515700
    except Exception:
        return False


def monitor_work_area(x, y):
    """
    座標 (x, y) を含むモニターの作業領域 (left, top, right, bottom)。

    マルチディスプレイでは tkinter の winfo_screenwidth が
    プライマリの幅しか返さないため、2枚目以降のモニターでは
    「画面の右端」を取り違える（簡易入力がモニターの境目に
    またがる・右へ広がらない、と実機で報告された・2026-08-09）。
    Windows の MonitorFromPoint / GetMonitorInfoW で、その点を
    含むモニターの作業領域（タスクバーを除く）を取る。
    取れない環境（Windows以外・失敗時）は None。
    """
    try:
        import ctypes
        from ctypes import wintypes
        u32 = ctypes.windll.user32
        u32.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
        u32.MonitorFromPoint.restype = ctypes.c_void_p
        pt = wintypes.POINT(int(x), int(y))
        hmon = u32.MonitorFromPoint(pt, 2)   # MONITOR_DEFAULTTONEAREST
        if not hmon:
            return None

        class _MONITORINFO(ctypes.Structure):
            _fields_ = [('cbSize', wintypes.DWORD),
                        ('rcMonitor', wintypes.RECT),
                        ('rcWork', wintypes.RECT),
                        ('dwFlags', wintypes.DWORD)]

        mi = _MONITORINFO()
        mi.cbSize = ctypes.sizeof(_MONITORINFO)
        if not u32.GetMonitorInfoW(ctypes.c_void_p(hmon),
                                   ctypes.byref(mi)):
            return None
        r = mi.rcWork
        return (r.left, r.top, r.right, r.bottom)
    except Exception:
        return None


def has_fullwidth(text):
    """
    全角文字（East Asian Width が F または W）を含むか。

    （）ボタンで全角・半角のどちらの括弧を使うかの判断に使う。
    ひらがな・カタカナ・漢字・全角記号は W/F、半角カナは H なので
    含まれない。
    """
    import unicodedata
    return any(unicodedata.east_asian_width(c) in ('F', 'W')
               for c in text)


def correct_line(line, store, context_vocab=None, decisions=None,
                 input_method='kana', context_vec=None, dict_index=None,
                 nearby_words=(), recent_words=()):
    """
    補正エンジンの入口。

    補正の判断は corrector.py に集約されている。
    （以前は補正経路が複数並列に存在し、片方に安全策を入れても
      別の経路が同じ誤りを通してしまう構造だったため、
      正しい日本語を壊す誤補正が頻発した。単一経路に作り直した。）

    decisions には、ユーザーが補正結果をクリックして示した
    「この補正は不要」という判断が入る。

    context_vec には、語の共起から作った軽量な文脈ベクトル
    （context_vec.ContextVectorStore）を渡せる。同じ読みに
    複数の有力な表記がある場合に、周辺の語と意味的に馴染む方を
    選ぶ追加の手がかりとして使う（無くても動く）。

    dict_index には janome 辞書の読み索引を渡せる。
    「素帰任」のような、語として成立しない漢字列を読みに戻して
    推測する際に、漢字1文字の読みを引くのに使う（無くても
    自前の単漢字読み表で動く）。
    """
    # トークナイザは毎回作り直さずに使い回す（行ごとに作ると遅い）
    fn = getattr(store, '_tokenize_fn', None)
    if fn is None:
        fn = corrector.make_tokenizer(store)
        store._tokenize_fn = fn
    tokenize_fn = fn
    return corrector.correct_line(
        line, store, tokenize_fn, find_known_readings_flex,
        context_vocab=context_vocab, decisions=decisions,
        input_method=input_method, context_vec=context_vec,
        dict_index=dict_index,
        nearby_words=nearby_words, recent_words=recent_words)
from seed_vocabulary import load_seed

# 画面に表示するアプリ名（タイトルバー・ダイアログのタイトル等）。
# 内部の設計上の呼び名（コード中のコメントやファイル名の
# 「CorrectNote」）とは別に、ユーザーに見せる名前だけをここで変える。
APP_TITLE = 'CorrectNote'

# 画面に出すバージョン（メニューの「このアプリについて」）。
# GitHub のタグと揃えること（タグは v を付けて v1.3.0）。
# 1.0.0（公開時）からの変更: タブのドラッグ並べ替え、説明書の同梱と
# 「このアプリについて」メニュー、重いタブの高速化、窓の移動を OS に
# 任せる、括弧と F2 と引用モードの手直し（項目48-m〜48-p）。
# 1.2.0 での変更: 同音異義語の文脈置換（方針2）、検証レポートの
# 指摘 2-C〜2-F / 3-A〜3-D、英単語の学習が使用回数を水増ししていた
# 不具合、解析の高速化と前回結果の控え（起動 12.2秒→1.8秒・
# タブ切り替え 6.5秒→0.7秒）、保存先が無いときの別名保存への誘導、
# 前回の表示位置からの再開（項目48-F〜48-N）。
# 1.2.1 での変更（**機能の追加は無い。直しが目的の版**）: テンキーの
# 小数点で文字が消える不具合（項目48-IN。1.2.0 の説明で「直した」と
# 書いたが、束縛の優先順位のせいで受け皿が一度も走っていなかった）、
# 初期語彙の同点が OS の時計の刻みで決まっていた不具合（項目48-IO）、
# 異様と見た範囲を紫で見せる・補正の直り具合（項目48-IP〜48-IX）。
#
# **バージョンを上げたら `analysis_cache.py` の ENGINE_STAMP も
# 見直すこと**（補正の中身が変わっているなら必ず上げる）。
# 1.3.0 での変更（**ここから機能の追加が入る**）: 紫の意味を
# 「判断に迷った箇所」から**「不自然な文字列」**へ入れ替え（既定オン・
# 補正が入った範囲には付けない）、**かな書きのアルファベット読みを
# 英字に直す**（`エフ2 → F2`）、スクロール後の反映（項目48-IZ〜）。
APP_VERSION = '1.7.0'

# 同梱する説明書のファイル名。exe の中に入れて持ち歩き、
# 初回起動時に exe と同じフォルダへ書き出す
# （zip での配布にはしない、といううにさんの指定・2026-08-10）。
# **説明書の版を上げたら、この名前も一緒に変えること。**
# 名前が変わったことを合図に、書き出し済みの印を無視して
# 新しい版を書き出す（_extract_manual）。
#: **説明書のファイル名には版を入れない**（項目48-OE・2026-09-02・
#: うにさんの指定「**更新のたびに説明書が増えるので、末尾の v6 を取り、
#: アプリのバージョンが更新されたことを検知したら説明書を更新する形に
#: 変更する**」）。
#:
#: v5・v6 のように名前へ版を入れていたのは、「書き出した印を名前で
#: 残す」造りだったから——名前が変わらないと手元の HTML が
#: 入れ替わらなかった。**印をアプリの版（`APP_VERSION`）で残せば、
#: 名前は固定でよい**。古い `CorrectNote_説明書v*.html` は、
#: 書き出すときにこちらで片付ける（増えていく元）。
MANUAL_FILENAME = 'CorrectNote_説明書.html'
#: 名前に版が入っていた頃の説明書（片付ける相手）
MANUAL_OLD_GLOB = 'CorrectNote_説明書v*.html'


def map_column(original, corrected, col):
    """
    行を書き換えたとき、カーソルの桁を新しい行の対応する場所へ移す。

    統合表示の自動反映は行をまるごと入れ替えるので、そのままだと
    カーソルが行頭へ飛ぶ。書き換えの前後で「同じところ」を指し
    続けるように、差分を見て桁を読み替える。

    考え方:
      - 変わっていない部分に居るなら、そのぶんだけずらす
      - 書き換えられた部分の中に居るなら、その**終わり**へ置く
        （打っている途中の語が直った場合、続きは語の後ろから
          書きたいはずなので）
      - 行末に居たなら、新しい行末へ

    純粋関数にしてあるので、画面なしで検証できる。
    """
    if col <= 0:
        return 0
    if col >= len(original):
        return len(corrected)
    import difflib
    sm = difflib.SequenceMatcher(None, original, corrected, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if not (i1 <= col < i2 or (tag == 'insert' and i1 == col)):
            continue
        if tag == 'equal':
            return j1 + (col - i1)
        return j2
    return min(col, len(corrected))


def resolve_pick_text(selected, unit_text):
    """
    「語を拾うモード」で実際に差し込む文字列を決める。

    ドラッグで範囲が選ばれていればそれを優先し、
    選ばれていなければクリックした語を使う。
    どちらも空なら差し込まない（モードだけ解除する）。
    """
    if selected and selected.strip():
        return selected
    if unit_text and unit_text.strip():
        return unit_text
    return ''


def header_should_show(first, threshold=0.0008):
    """
    見出し（メモ・補正結果の操作説明）を表示するかどうか。

    先頭付近（スクロール位置がほぼ0）のときだけ表示する。
    スペースを本文に譲るため、少しでも下へスクロールしたら隠す。

    first は文字列で渡されることがある（tkinter の
    yscrollcommand は Tcl 経由の値をそのまま渡すことがあり、
    常に float とは限らない）。ここでも念のため変換しておく。
    """
    try:
        first = float(first)
    except (TypeError, ValueError):
        return True    # 判断できない場合は、表示しておく側に倒す
    return first <= threshold


def next_bookmark(current_line, bookmarks, forward=True):
    """
    現在行から見て、次（または前）のブックマーク行を返す。

    見つからない場合は末尾から先頭へ（またはその逆へ）循環する。
    ブックマークが無ければ None。
    """
    bm = sorted(bookmarks)
    if not bm:
        return None
    if forward:
        for b in bm:
            if b > current_line:
                return b
        return bm[0]
    for b in reversed(bm):
        if b < current_line:
            return b
    return bm[-1]


def classify_drag(dx, dy, threshold=14, ratio=1.4):
    """
    ドラッグの動きから、スクロールと見なすかどうかを判定する。

    タッチパネルでの1本指操作は、Tk 上では通常のマウスドラッグと
    区別がつかない。そこで動きの向きで判断する:
    縦方向の移動が横方向より十分大きければスクロールとみなす
    （このアプリでの範囲選択・文字選択は基本的に1行の中で
      横方向に動かすものなので、縦方向優位の動きと自然に区別できる）。

    戻り値: 'scroll' / 'other' / None（判定するにはまだ動きが小さい）
    """
    if max(abs(dx), abs(dy)) < threshold:
        return None
    if abs(dy) >= abs(dx) * ratio:
        return 'scroll'
    return 'other'


def design33_classify(applied, spans, now):
    """
    設計33（1段目）——自動反映した行が手で書き換えられたとき、
    「補正された語を、意図して消したか」を**消え方の形だけ**で
    見分ける（`設計33_消した操作を拒否として学ぶ_20260824.md`・
    うにさんの指定 2026-08-24）。

    applied  自動反映した直後の行の姿（控えの 'applied'）
    spans    控えの 'spans'（(start, end, kind, 元の語) の並び）
    now      いまの行の姿

    戻り値: (元の語, 補正後の語, 仮か) の並び。

    拾う形は2つだけ。**曖昧なものを拾わないのがこの設計の芯**:

    甲  消えた範囲＝補正の範囲で、**後ろの文が残っている**。
        「後ろが残っているのに、その語だけ消す。これは意図的な変更」
        （うにさんの言葉）。→ 仮ではない
    乙  行の頭は残したまま、その語から後ろがまとめて消えた
        （BackSpace で消しながら戻った形）。行末の語を消した形も
        後ろが無く甲の見分けが立たないので、ここ。
        → 仮（カーソルがその行から離れるまで確定しない）

    それ以外（丙: 途中の打ち直し・範囲選択して上書き・別の編集）は
    何も返さない。**行がまるごと消えた形も返さない**——段落ごと
    消した（丙）と見分けが付かないため。

    F2 で選び直した記憶の反映（kind='chosen'）は対象にしない。
    あちらは choices 側の記憶で、消し方の意味付けが別の話になる。
    """
    out = []
    if now == applied or not now.strip():
        return out
    for start, end, kind, before in spans:
        if kind != 'fixed':
            continue
        corrected = applied[start:end]
        if not before or not corrected or before == corrected:
            continue
        tail = applied[end:]
        if now == applied[:start] + tail:
            # 消えた範囲＝補正の範囲。後ろが残っていれば甲、
            # 行末の語（後ろが空白だけ）なら乙の扱い（仮）
            out.append((before, corrected, not tail.strip()))
        elif len(now) <= start and applied.startswith(now):
            # 消しながら戻った（その語ごと後ろが消えている）
            out.append((before, corrected, True))
    return out


def remap_pending_lines(pending, head, tail, prev_len, new_len):
    """
    分割解析のやり残し行を、編集後の行番号に読み替える。

    全行解析は少しずつに分けて行う（ANALYZE_CHUNK）。その途中で
    ユーザーが文字を打つと解析はやり直しになるが、やり残した行は
    **内容が変わっていない** ため差分（head/tail）では拾われない。
    読み替えて持ち越さないと、仮置きのまま二度と解析されない行が
    残ってしまう。

    head: 先頭から変わっていない行数
    tail: 末尾から変わっていない行数
    prev_len / new_len: 編集前・編集後の行数

    変わった範囲（head 以上 prev_len-tail 未満）の行は、
    どのみち改めて解析されるので読み替えない。

    戻り値: 新しい行番号の一覧（昇順・重複なし）
    """
    shift = new_len - prev_len
    out = set()
    for i in pending:
        if i < head:
            j = i
        elif i >= prev_len - tail:
            j = i + shift
        else:
            continue
        if 0 <= j < new_len:
            out.add(j)
    return sorted(out)


# IME が確定した半角文字が、編集キー・移動キーとして届いてしまう問題。
#
# 実機のキー記録（keylog.py）で確定した事実:
#
#   KeyPress keysym=Delete keycode=46 char='.' state=8  → 1文字消えた
#
# 「る」のキーを打って F9/F8 で半角に確定すると、tkinter には
# **keysym が Delete、char が '.'** というキー押下として届く。
# Text ウィジェットは keysym を見て動くので、Tk 標準の
# 「Delete＝カーソル位置の1文字を消す」が実行され、
#   - 打った「.」は入らない（Delete の束縛が文字入力の束縛より優先される）
#   - カーソル位置の文字が消える（行末なら改行が消え、下の行が上に詰まる）
# という、報告どおりの壊れ方をする。
#
# 理由は keycode を見れば分かる。46 は Windows の VK_DELETE であると
# 同時に、文字「.」のASCII番号でもある。IME が確定した文字について、
# tkinter は仮想キーコードの欄に **文字の番号をそのまま入れて**しまい、
# それを仮想キーコードとして読み直すため、別のキーに化ける。
#
# 化けるのは 0x21〜0x2F（! " # $ % & ' ( ) * + , - . /）の記号。
# このうち Text が独自の動きを持つキー名に当たるものだけが実害を出す:
#
#   '!'(0x21) Prior   '"'(0x22) Next    '#'(0x23) End    '$'(0x24) Home
#   '%'(0x25) Left    '&'(0x26) Up      "'"(0x27) Right  '('(0x28) Down
#   '-'(0x2D) Insert  '.'(0x2E) Delete
#
# 「+ / * は化けない」という報告とも合う（Execute / Help / Print に
# 当たるが、Text はこれらに動きを割り当てていないため文字が入る）。
#
# **記号だけの話ではなかった**（2026-08-17・うにさん報告・項目48-EH）:
#
#     「ｐを半角変換して確定すると、引用モードが誤作動したり、
#       前後の文字列によっては検索が誤作動することがあります」
#
# 同じ理屈を英小文字まで伸ばすと、**そのまま当たる**。
# `p` の番号は 0x70 で、これは **VK_F1 と同じ番号**である:
#
#     p(0x70) F1   q(0x71) F2   r(0x72) F3   s(0x73) F4
#     t(0x74) F5   u(0x75) F6   v(0x76) F7   w(0x77) F8
#     x(0x78) F9   y(0x79) F10  z(0x7A) F11  {(0x7B) F12
#     `(0x60) KP_0  a〜i(0x61-0x69) KP_1〜KP_9
#     j(0x6A) KP_Multiply  k(0x6B) KP_Add   l(0x6C) KP_Separator
#     m(0x6D) KP_Subtract  n(0x6E) KP_Decimal  o(0x6F) KP_Divide
#
# このアプリは F1＝引用モード・F2＝候補一覧・F3＝次を検索を
# 割り当てている。だから
#
#     ｐ を半角に確定 → keysym=F1  → **引用モードが始まる**
#                                   （しかも `p` が入らない。
#                                     F1 の束縛が 'break' を返して
#                                     Tk の文字入力まで届かないため）
#     ｒ を半角に確定 → keysym=F3  → **前回の検索語で次を探す**
#                                   （見つかると**その範囲が選択され**、
#                                     次に打った字が選択を置き換える。
#                                     「前後の文字列によっては」は
#                                     これ。検索語が無ければ検索窓が開く）
#     ｑ を半角に確定 → keysym=F2  → **候補一覧が開く**
#
# a〜o は KP_* に化けるが、Text は KP_* に独自の動きを持たないので
# 文字がそのまま入る（実害なし）。**F1〜F12 だけが実害を出す。**
#
# 本物の Delete キー・F1 キー等は文字を伴わない（char が空、
# または制御文字）。文字を伴っているかどうかで確実に見分けられる。
# **本物のテンキーは文字を伴う**が、そのときに入れたい文字は
# char そのもの（KP_1 なら '1'）なので、文字として扱って正しい。
_IME_MISREAD_KEYSYMS = frozenset({
    'Delete', 'Insert', 'Prior', 'Next', 'Home', 'End',
    'Left', 'Right', 'Up', 'Down',
    # 実害は確認できていないが、同じ番号の並びにあるキー名も
    # 文字を伴って届いたなら文字として扱う（取りこぼさないため）。
    'Clear', 'Select', 'Print', 'Execute', 'Help',
    # 0x60〜0x7E（`〜~）。項目48-EH。
    'F1', 'F2', 'F3', 'F4', 'F5', 'F6', 'F7', 'F8',
    'F9', 'F10', 'F11', 'F12', 'F13', 'F14', 'F15',
    'KP_0', 'KP_1', 'KP_2', 'KP_3', 'KP_4',
    'KP_5', 'KP_6', 'KP_7', 'KP_8', 'KP_9',
    'KP_Multiply', 'KP_Add', 'KP_Separator', 'KP_Subtract',
    'KP_Decimal', 'KP_Divide',
})

# そのうち、**このアプリが機能を割り当てているキー**。
# ここに当たったときだけ「機能を実行するか、文字を入れるか」の
# 分かれ道になる（項目48-EH）。
_IME_MISREAD_FUNCTION_KEYS = frozenset({
    'F1', 'F2', 'F3', 'F4', 'F5', 'F6', 'F7', 'F8',
    'F9', 'F10', 'F11', 'F12',
})


def ime_confirmed_char(keysym, char):
    """
    このキー押下は、IME が確定した文字を編集キーと取り違えたものか。

    そうなら「本当に入力したい文字」を返す。違えば None
    （＝本物の編集キーなので、Tk の標準の動きに任せる）。

    keysym: tkinter が解釈したキー名
    char:   そのキー押下が伴っている文字
    """
    if not char or len(char) != 1:
        return None
    # 本物の Delete / BackSpace は制御文字（\x7f 等）を伴うことがある。
    # 印字できる文字だけを「入力したかった文字」とみなす。
    if not char.isprintable():
        return None
    # **日本語（非 ASCII）の字を伴う KeyPress は、キー名が何であれ IME の
    # 確定**（項目48-SZ'・2026-09-06）。Tk は確定した字を1字ずつ KeyPress に
    # 直すとき、**字のコードの下位バイトからキー名を作る**——
    # `映`（U+6620）は `space`、`さ`（U+3055）は `U`、`せ`（U+305B）は `Win_L`。
    # 本物のキーがこの字を伴うことは無い。うにさんの実機（`deletion_log.txt`）:
    # Shift を押したまま「反映されません」を確定 → `映` が `<Shift-space>`
    # （行の中身を選ぶ・48-OD）に化けて行を選び、次の `さ` が選択を置き換えた
    # ——「それまでの行の文字がすべて消える」。キー名が `??`（Tk が名前を
    # 付けられなかった字）は束縛に掛からないので、今までどおり Tk に任せる
    if ord(char) > 0x7F:
        return char if keysym and keysym != '??' else None
    if keysym not in _IME_MISREAD_KEYSYMS:
        return None
    return char


# --- 項目48-FY: テンキーの小数点で文字が消える ---
#
# うにさん報告（2026-08-19）:
#
#     「テンキーの小数点を打つと文字が消えます」
#
# 項目48-EH と**同じ番号の罠**だが、原因は逆向き。
#
#     VK_DELETE  = 0x2E = **46**   本物の Delete キー
#     VK_DECIMAL = 0x6E = **110**  テンキーの小数点（NumLock 入）
#
# 48-EH は「**文字を伴っていれば**文字として入れる」で塞いだ。
# 48-FY はこれに「テンキーの小数点は、日本語IMEが入っていると
# **文字を伴わずに**（`char` が空・番号 110 のまま）届くことがある」
# という**仮説**を足し、番号 110 で見分ける道を置いた。
#
# **実機で測ったら、その形は来なかった**（項目48-IN・2026-08-22・
# うにさんの PC に SendInput で本物の打鍵を送って記録した）:
#
#     IME ひらがな  keysym=Delete keycode=46  char='.'  ← 項目31 と同じ形
#     IME オフ      keysym=period keycode=110 char='.'  ← 初めから正常
#     本物の Delete keysym=Delete keycode=46  char=''   state に 0x40000
#
# 消えていた本当の理由は、`<Delete>` の個別束縛（項目48-ED）が
# `<KeyPress>` の受け皿を黙らせていたこと（`_ime_first` を参照）。
# 48-FY の確認は関数を直接呼んでいたので、束縛の道を通っていなかった。
#
# この関数は**保険として残す**（触っても何も壊さない）。
# NumLock を切っているときのテンキーの小数点は、Windows が
# **VK_DELETE(46) として送る**ので、そちらは今までどおり
# 「消す」が正しい（キーの意味そのものが Delete になる）。
#
# 文字を伴っていればその文字を入れる（IMEが確定した `n` は
# 番号が同じ 110 だが、`char` が `n` なので取り違えない）。
_VK_DECIMAL = 110
_KP_DECIMAL_KEYSYMS = frozenset({'KP_Decimal', 'KP_Separator'})


def numpad_decimal_char(event):
    """
    このキー押下は「テンキーの小数点」か。そうならその文字を返す。

    違えば None（＝本物の Delete などなので、標準の動きに任せる）。
    """
    if event is None:
        return None
    keysym = getattr(event, 'keysym', '') or ''
    char = getattr(event, 'char', '') or ''
    try:
        keycode = int(getattr(event, 'keycode', 0) or 0)
    except Exception:
        keycode = 0
    try:
        state = int(getattr(event, 'state', 0) or 0)
    except Exception:
        state = 0
    # Ctrl / Alt を伴うものは、押した人が編集キーとして使っている。
    # （0x08 は Windows の tkinter では NumLock なので**見ない**）
    if state & 0x04 or state & 0x20000:
        return None
    if keysym not in _KP_DECIMAL_KEYSYMS and keycode != _VK_DECIMAL:
        return None
    if len(char) == 1 and char.isprintable():
        return char
    return '.'


def ime_confirmed_char_event(event):
    """
    このイベントは「IME が確定した文字」か（項目48-EH）。

    `ime_confirmed_char` と同じ判定を、tkinter のイベントから直に行う。
    **F1〜F12 の束縛の入口で使う**もので、そうと分かったら
    機能（引用モード・候補一覧・検索）を実行してはいけない。

    修飾キーが押されているものは除く。本物の Ctrl+F3 などを
    文字と読み違えないため（IME の確定は修飾なしで届く）。
    """
    keysym = getattr(event, 'keysym', '') if event is not None else ''
    if not keysym:
        return None
    try:
        state = int(getattr(event, 'state', 0) or 0)
    except Exception:
        state = 0
    # 0x04 Control / 0x01 Shift / 0x20000 Alt（Windows の tkinter）。
    # Shift は IME の確定でも立つことがあるので見ない。
    if state & 0x04 or state & 0x20000:
        return None
    return ime_confirmed_char(keysym, getattr(event, 'char', '') or '')


def app_dir():
    """
    データファイル（語彙・判断・選び直し・辞書索引）を置く場所。

    PyInstaller で exe 化すると、__file__ は一時展開先
    （sys._MEIPASS）を指すようになる。そこは実行のたびに変わり、
    終了時に消えることもあるため、データを置いてはいけない。
    exe のときは exe と同じフォルダに置く（USBに入れて持ち運べる）。
    """
    if getattr(sys, 'frozen', False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def bundled_path(name):
    """
    exe に同梱したファイルの、読み出し元のパス。

    PyInstaller で固めると、同梱したデータは実行のたびに作られる
    一時フォルダ（sys._MEIPASS）に展開される。**そこは終了時に
    消えるので、ユーザーに渡すものは app_dir() へ写す**
    （データファイルと同じ考え方。app_dir の説明を参照）。

    .py のまま動かしているとき（開発中）は、ソースと同じフォルダに
    実物があるので、そちらを指す。見つからなければ None。
    """
    base = getattr(sys, '_MEIPASS', None)
    if base:
        p = os.path.join(base, name)
        if os.path.exists(p):
            return p
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), name)
    return p if os.path.exists(p) else None


# アプリのアイコン（項目48-JR・うにさんの指定「ノートまたは書く媒体に
# 対して補正されて入っていくイメージ」）。**同梱物なので `bundled_path`**
# （`app_dir()` ではない。exe では `_MEIPASS` に展開される）。
#
# **同じ絵を2つの形で持つ。** 役割が違うので名簿が2つあるのとは違う:
#     `.ico` … Windows の窓・タスクバー（`iconbitmap`）と **exe の絵**
#              （`correctnote.spec` / `kana_memo.spec` の `icon=`）
#     `.png` … `iconphoto` 用。**Tk は .ico を PhotoImage で読めない**ので、
#              Windows 以外や `iconbitmap` が使えない環境の逃げ道になる
# 作り直しは `tools_local/make_icon.py` **ただ1つ**（Pillow が要る。
# アプリ側は Pillow に依存しない）。
ICON_ICO = 'correctnote.ico'
ICON_PNG = 'correctnote.png'

VOCAB_FILE = os.path.join(app_dir(), 'vocabulary.json')
DECISIONS_FILE = os.path.join(app_dir(), 'decisions.json')
CHOICES_FILE = os.path.join(app_dir(), 'choices.json')
# **最後にどの変換をしたか**の1枠（項目48-QH・2026-09-05）。
# `choices.json`（回数・時刻・前後の本文つき）を畳んだ置き換え。
LAST_CHOICE_FILE = os.path.join(app_dir(), 'last_choice.json')
DICT_INDEX_FILE = os.path.join(app_dir(), 'dict_index.json')
# 語の共起から作る軽量な文脈ベクトル（同音異義語の文脈判定に使う）
CONTEXT_VEC_FILE = os.path.join(app_dir(), 'context_vec.json')
# 初回セットアップ（辞書の取り込み・索引の作成）が済んだ印
SETUP_FILE = os.path.join(app_dir(), 'setup.json')
# 編集中の内容の自動保存（保存せず閉じても続きから再開できる）
SESSION_FILE = os.path.join(app_dir(), 'session.json')
SETTINGS_FILE = os.path.join(app_dir(), 'settings.json')
# 前回の解析結果の控え（起動を速くするためだけのもの。
# 消しても動作は変わらない＝その回だけ解析し直すだけ）。
# **ユーザーのメモそのものを含むので .gitignore に入れてある。**
ANALYSIS_CACHE_FILE = os.path.join(app_dir(), 'analysis_cache.json')
# **IME が確定した「表記 → 打った読み」の対**（設計25(甲)）。
# **うにさんの打った文章の断片そのものなので .gitignore に入れてある**
# （session.json と同格）。**語彙とは別の置き場**（学び2:
# `奥悠久子帝 → おくゆくこてい` は誤変換そのもので、語彙に入れると
# 次からその誤変換を守ってしまう）。
IME_READINGS_FILE = os.path.join(app_dir(), 'ime_readings.json')
# 説明書の書き出し先（exe と同じフォルダ）
MANUAL_FILE = os.path.join(app_dir(), MANUAL_FILENAME)

# 配色
BG = '#f6f4ee'
PANEL = '#ffffff'
INK = '#1c2b2d'
RULE = '#d8d3c4'
ACCENT = '#2c5f6f'
MUTED = '#8a8577'
WARN = '#a8443a'

EDITOR_FONT = ('Yu Mincho', 11)
# **俯瞰**（右ダブルクリックを押し続けている間の字の大きさ）。
# うにさんの指定（2026-08-28）:「右クリックをダブルクリックして
# そのまま押し続けている間、**フォントサイズを一時的に5**にします。
# 全体が把握しやすくなり、そのままマウスを上下に動かすと
# スクロールします。クリックを離すと元に戻る」
OVERVIEW_FONT_SIZE = 5
# 俯瞰のあいだだけ、**行と行のあいだの余白を落とす**
# （うにさんの指定・2026-08-28 2度目:「右クリックダブルクリックは
# フォントサイズ5でよいですが、**行間をもっと詰めて広い範囲が
# 映るようにします**」）。
#
# Tk の Text の1行の高さは **字の高さ＋spacing1＋spacing3**
# （折り返した行の間は spacing2）。字だけ 11 → 5 にしても、この
# 余白は 2＋4＝6px のまま残るので、**小さくした字に対して余白の
# 割合が大きくなり、詰めたぶんが余白に食われる**。
# `pady`（欄の上下の余白・一度きり）も、字が小さいと 24px＝
# **2行以上**を食うので一緒に詰める。
# 元の値は**その場で読んで控える**（同じ数を2か所に書かない・48-GN）。
OVERVIEW_TIGHT = {'spacing1': 0, 'spacing2': 0, 'spacing3': 0, 'pady': 2}

# 俯瞰の間、**離したときに映る範囲**（いまの上端から、ふだんの字で
# 1画面ぶん）を四角で囲って示す（項目48-LH・2026-08-29 うにさんの指定
# 「右ダブルクリックの間、元に戻した時に移る範囲を四角で囲って示します」。
# 俯瞰から出るときは「見ていた行のまま」＝上端の行が置き直されるので、
# 移る範囲は 上端から普段の字での1画面ぶん）。
# 見た目は参考の画像が届いたら合わせ込む——枠の太さと地色はここ。
OVERVIEW_DEST_TAG = 'ov_dest'
OVERVIEW_DEST_BORDER = 1
LINE_NUM_BG = '#f0ede4'
LINE_NUM_FG = '#a39d8c'

# 補正結果欄（右ペイン）の配色。メモ欄と少し変えて区別する。
RESULT_BG = '#fbfaf7'
RESULT_GUTTER_BG = '#f2efe8'
# 補正の可能性がある箇所への薄い網掛け。
# **明るい配色のとき、白地との差が 1.07 しかなく「見えにくい」と
# 報告された**（うにさん・2026-08-18）。暗い配色側は同じ指摘を受けて
# 既に 1.48 まで上げてあるので、**明るい側もそこへ揃える**
# （#f8cdc1 = 白地と 1.45・補正欄と 1.39。文字（INK）との差は
#  10.1 あるので読みやすさは落ちない）。
SUSPECT_BG = '#f8cdc1'
# ドラッグ選択の背景色（メモ欄・補正結果欄でわずかに変えている）
EDITOR_SEL_BG = '#cfe0e6'
RESULT_SEL_BG = '#bcd7e0'
# オンマウスした語の背景色
HOVER_BG = '#e9eff1'
# 補正された語の文字色
FIXED_FG = '#c4564a'
# 検索で見つかった箇所の背景色
FOUND_BG = '#ffe9a8'
FOUND_CUR_BG = '#ffc95c'
# 「単語として成立していないが、何に直すべきか確信が持てない」箇所。
# 自動補正の網掛け（SUSPECT_BG）とは別の色にして、
# 「直した／直せる」と「壊れているが直し方が分からない」を区別する。
# 明るい配色側は白地との差が 1.20 しかなかった。SUSPECT_BG と
# 同じ考えで 1.48 へ（文字との差は 9.9 で十分）。
UNSURE_BG = '#e6cbf3'

# 簡易入力ウィンドウから本体のメモ欄へ**送った文字**に、一時的に
# 付ける色（うにさんの指定・2026-08-20・項目48-GN）。
#
# > 「簡易入力からアプリ本体に送った文字は、一時的に色を付ける。
# >   **2色を用意し、連続して簡易入力から送ったら交互に色を付ける**」
#
# 交互にするのは、続けて送ったときに**どこまでが今回ぶんか**が
# 分かるようにするため。既にある色（網掛け #f8cdc1・直し方が
# 分からない #e6cbf3・検索 #ffe9a8・F2 #ffd9a0・オンマウス
# #e9eff1）とぶつからない色相を選んである。
# **2色目は1色目から十分に離すこと**（うにさんの指定・2026-08-20）。
# 最初は `#bbdefb`（薄い青）にしていたが、薄い緑との隔たりが
# CIE Lab で 30.5 しかなく「近い」と言われた。**測って選び直した**:
#
#     ライト  緑 #c8e6c9 ←→ 青 #9cc2fe   隔たり 48.8（前は 30.5）
#             他の色との最小の隔たり 23.9（前は 10.9・選択色と）
#     ダーク  緑 #35513a ←→ 青 #004c88   隔たり 53.3（前は 27.9）
#             他の色との最小の隔たり 25.8（**前は 4.8**・選択色と
#             ほとんど同じ色だった）
#
# 色相は青（274度）を選んだ。桃色のほうが数の上ではもっと離れるが、
# **網掛け（補正候補あり・41度）と同じ family に見える**ので採らない。
# **色は意味を持っている。空いている色相から選ぶ。**
QUICK_SENT_BG_A = '#c8e6c9'      # 薄い緑
QUICK_SENT_BG_B = '#9cc2fe'      # 青（緑から十分に離した）

# 目に見えない空白（半角・全角・タブ）を見せる色（項目48-IF／
# 項目48-IG でやり直し・うにさんの指定・2026-08-21）。
#
# **無彩色にする。** ほかの色は全部「意味」を持っている
# （網掛け＝補正候補あり／紫＝迷い／緑と青＝簡易入力から送った）。
# 空白の印は**既定でずっと出しっぱなし**なので、色相を1つ使うと
# 意味のある色と競ってしまう。空いているのは**彩度**のほうで、
# そこを使う。
#
# **2色を交互に置く**（うにさんが簡易入力の色で指定された形と同じ）。
# 1色だと「3つ並んだ空白」が1本に見えて数えられない。
#
# **スペースは地色の箱ではなく「行の下端の線」にする**（項目48-IG）。
# うにさんの指定「**縦の長さを短くして、下詰めで縦2割ほどの高さ**に」。
# Tk で実際に描いて測った結果:
#     地色の箱は**必ず行の高さいっぱいに描かれる**。タグに小さい字を
#     指定すると `bbox` は縮むが、**塗られる高さは変わらない**
#     （画素を数えて確かめた）。縮むのは**幅**のほうで、それは
#     文字送りが変わるということ＝**本文がずれる**。使えない。
#     下線は**行の下端から1px の位置に太さ2px**で引かれる。
#     これが Tk で引ける**いちばん低い印**である。
#     `offset` で更に下げると**行の高さが伸びる**（測った）ので使わない。
# ——なので、スペースは**下端の線1本だけ**にする（項目48-IJ）。
#
# ここまでの経緯（うにさんの指定を、順に）:
#     48-IF  地色の箱      → 「目立つ。短く・下詰めに」
#     48-IG  下線1本       → 「`_` と見分けが付かない。高さを」
#     48-IH  下線＋打ち消し線 → 「全角が**伸ばし棒 `ー`** と紛れる」
#     48-II  薄い四角＋下線 → 「**地色は目立つので無しに**。
#                              下線を二重にできますか。
#                              **どちらにせよ下線の色を灰色に**」
#     48-IJ  **灰色の下線1本だけ**（地色なし）
#
# **二重下線は Tk に無い。** タグに指定できるのは
# `underline`（下線1本）と `overstrike`（打ち消し線1本）だけで、
# 「二重下線」も「線の太さ」も指定が無い（`probe_ws_double.py` で
# 全項目を並べて確認）。太さは**字の大きさから決まる**ので、
# 太くすると**文字送りが変わって本文がずれる**:
#     字 8→1px / 11→2px / 14→2px / 20→3px / 28→4px（幅 4/5/6/9/12px）
# 打ち消し線は**真ん中**にしか出ない。それが `ー` に見えた（48-IH）。
#
# **色は灰色**（うにさんの指定）。ここまでは背景に合わせた
# 暖色寄り・青寄りの灰にしていたが、無彩色そのものにする。
#
# **背景に近づけて、存在感を減らす**（項目48-IK・うにさんの指定
# 「線の存在感が強いです。**色を背景色に近くして、見えにくく存在感を
# 減らして**ください」）。5段階を描いて選んだ（`probe_ws_faint.py`）。
# 選んだのは**背景との明るさの差が 45 と 29**（前は 115 と 71）:
#
#     いま(前)  差 115 / 71   はっきり見える
#     A         差  75 / 50
#     B         差  59 / 39
#     **C**     差 **45 / 29**  **見えるが引っ込む** ← これ
#     D         差  33 / 20   ほとんど見えない
#
# 2色の差は、隣り合った空白を数えるための段差である。これ以上
# 縮めると数えられなくなる。回帰テストで差の幅を見張る。
WS_LINE_A = '#d2d2d2'    # 下端の線（濃）
WS_LINE_B = '#e2e2e2'    # 同（淡）。隣り合ったときの数え分け用
# タブだけは線にできない（**Tk はタブに下線も打ち消し線も引かない**。
# 描いて確かめた）。地色の帯しかないので、いちばん薄くする。
# 幅が広いので薄くても分かる。
WS_TAB_A = '#f3f0e8'
WS_TAB_B = '#ece8de'

# ライト／ダークの配色一式。ダークモードの切り替えは、
# これらの値を module レベルの定数に入れ替えることで行う
# （_apply_theme を参照）。新しく開くダイアログは、作る時点で
# その時の定数値を参照するので自動的に新しい配色になる。
# 既に開いている持続的な部品（メモ欄・補正欄・メニュー等）だけ、
# 切り替え時に明示的に配色をやり直す。
_PALETTE_KEYS = ['BG', 'PANEL', 'INK', 'RULE', 'ACCENT', 'MUTED',
                'LINE_NUM_BG', 'LINE_NUM_FG', 'RESULT_BG', 'RESULT_GUTTER_BG',
                'SUSPECT_BG', 'EDITOR_SEL_BG', 'RESULT_SEL_BG', 'HOVER_BG',
                'FOUND_BG', 'FOUND_CUR_BG', 'UNSURE_BG',
                'QUICK_SENT_BG_A', 'QUICK_SENT_BG_B',
                'WS_LINE_A', 'WS_LINE_B',
                'WS_TAB_A', 'WS_TAB_B']

LIGHT_PALETTE = {k: globals()[k] for k in _PALETTE_KEYS}

DARK_PALETTE = {
    'BG': '#1e2124', 'PANEL': '#25292d', 'INK': '#e6e4dd',
    'RULE': '#3a3f44', 'ACCENT': '#6bb0d1', 'MUTED': '#8b9198',
    'LINE_NUM_BG': '#202327', 'LINE_NUM_FG': '#666e75',
    'RESULT_BG': '#23272a', 'RESULT_GUTTER_BG': '#1c1f22',
    'FOUND_BG': '#5c4e22', 'FOUND_CUR_BG': '#7a6620',
    # 網掛け（補正候補あり）とオンマウスは、暗い背景の上では
    # 元の値（#332726 / #2c3437）だと背景とほとんど区別が付かず、
    # 「色が付いているのが見えない」と報告された。
    # 背景 PANEL(#25292d) との差を明確に取れる明るさまで上げる。
    'SUSPECT_BG': '#5c3b33', 'EDITOR_SEL_BG': '#3a5568',
    'RESULT_SEL_BG': '#3f5c70', 'HOVER_BG': '#3c464c',
    # 不自然な文字列の紫（項目48-IZ）。もとは「直し方が分からない
    # 箇所（unsure）」の色。名前は配色の名簿（`_PALETTE_KEYS`）と
    # 設定ファイルに残るので変えていない。
    # 暗い背景の上で、背景とも文字色とも十分に差が出る明るさにする
    # （'#4a3654' では文字と紛れて読めないと報告された）。
    'UNSURE_BG': '#6b4d7a',
    # 簡易入力から送った文字（2色を交互に）。暗い背景（#25292d）の
    # 上でそれと分かり、文字（#e6e4dd）は読めたまま。
    # **2色目は選択色（#3a5568）とほとんど同じ色だった**（隔たり 4.8）。
    # 緑からも近かったので、測って選び直した（上の注記を参照）。
    'QUICK_SENT_BG_A': '#35513a', 'QUICK_SENT_BG_B': '#004c88',
    # 目に見えない空白（項目48-IF／48-IG／48-II）。暗い背景（#25292d）
    # の上で「はっきり見えるが、読む邪魔にはならない」明るさ。
    # ライトと同じく**2色を交互に**置いて、数えられるようにする。
    # 線は 48-IH より**濃くした**（「まだ見えにくい」との報告）。
    # 空白の印の線（項目48-IK）。**背景 #25292d との明るさの差は
    # 37 と 20**。ライト（45/29）と同じくらいの薄さになる。
    'WS_LINE_A': '#4d4d4d', 'WS_LINE_B': '#3c3c3c',
    'WS_TAB_A': '#2b3036', 'WS_TAB_B': '#333a41',
}


def is_kana(ch):
    """ひらがな（濁点・小書き含む）かどうか"""
    return '\u3041' <= ch <= '\u3096'


class LineNumberGutter(tk.Canvas):
    """
    テキスト欄の左に表示する行番号。

    以前は別の Text 部品に番号だけを並べて、ペア先の折り返しに合わせて
    空行を挟むことで位置を合わせようとしていた。しかし折り返した行は
    「改行文字による別の段落」として空行を挿入していたため、
    段落ごとに掛かる余白（spacing1/spacing3）が本文側の1回ぶんに対して
    ガター側では折り返した行数ぶん重複してしまい、
    折り返しが起こるたびに数ピクセルずつずれ、それが積み重なっていた。

    この実装では、ペア先の実際の描画位置を dlineinfo() でそのまま読み、
    その座標にキャンバス上で数字を描く。ペア先の折り返し方法や
    余白設定がどうであっても、実際に描画された位置を直接使うので
    原理的にずれようがない。

    ついでに、行番号のクリック／ドラッグでの行選択と、
    ダブルクリックでのブックマーク表示もここで受け持つ
    （どちらも「行の位置を知っている」ことが前提の機能のため）。
    """

    def __init__(self, parent, target, bookmarks=None,
                on_toggle_bookmark=None, width=48,
                on_pick_lines=None, **kwargs):
        defaults = dict(bg=LINE_NUM_BG, highlightthickness=0)
        defaults.update(kwargs)
        super().__init__(parent, width=width, **defaults)
        self.target = target
        # ブックマークの行番号の集合。メモ欄と補正欄で同じ集合を
        # 共有させることで、片方に付けたら両方に表示される。
        self.bookmarks = bookmarks if bookmarks is not None else set()
        self.on_toggle_bookmark = on_toggle_bookmark
        # 引用モードのときに呼ぶ関数。行の範囲を渡すと、
        # その行のテキストを引用する（None なら通常の行選択）。
        # 「引用モードで行番号をクリック・ドラッグしたら、
        #   その範囲を引用してほしい」という実機からの要望。
        self.on_pick_lines = on_pick_lines

        self._drag_anchor = None   # ドラッグ選択の起点行
        self._autoscroll_id = None  # 端に達したときの自動スクロール
        self._drag_last_y = 0
        # 番号を描く字（俯瞰の間だけ小さくする・2026-08-28）。
        # **本文と同じ字**でないと行の高さが合わないので、
        # ここを持たずに EDITOR_FONT を直に使うと、俯瞰の間だけ
        # 番号が本文からはみ出す（学び22——片方に置くと迂回する）。
        self.font = EDITOR_FONT

        self.bind('<Configure>', lambda e: self.redraw())
        self.bind('<Button-1>', self._on_press)
        self.bind('<B1-Motion>', self._on_drag)
        self.bind('<ButtonRelease-1>', self._on_release)
        self.bind('<Double-Button-1>', self._on_double_click)
        # **Shift+行番号で2点間**（項目48-RC）。`<Button-1>` より
        # 細かい束縛なので Tk はこちらを先に選ぶ
        self.bind('<Shift-Button-1>', self._on_shift_press)
        # **ホイールの3つはクラスの外（App 側）から張られている**
        # ——「ガターの束縛はここに全部ある」ではない（学び22）

    # ------------------------------------------------------------
    # 描画
    # ------------------------------------------------------------
    def redraw(self):
        """ペア先の今の描画内容に合わせて、見えている行番号を引き直す。"""
        self.delete('all')
        target = self.target
        try:
            line_count = int(target.index('end-1c').split('.')[0])
        except Exception:
            return

        width = int(self['width'])
        # 48-VV: 画面外の全行へ dlineinfo を問い合わせない。
        try:
            top = int(target.index('@0,0').split('.')[0])
            bottom = int(target.index(f'@0,{max(1, target.winfo_height() - 1)}').split('.')[0])
        except Exception:
            return
        for line_idx in range(max(1, top), min(line_count, bottom) + 1):
            try:
                info = target.dlineinfo(f'{line_idx}.0')
            except Exception:
                info = None
            if info is None:
                continue   # 画面外（表示されていない行）は描かない
            _x, y, _w, h, _baseline = info

            self.create_text(width - 10, y + h / 2, anchor='e',
                             text=str(line_idx), fill=LINE_NUM_FG,
                             font=self.font, tags=('num',))

            if line_idx in self.bookmarks:
                self.create_oval(4, y + h / 2 - 4, 12, y + h / 2 + 4,
                                 fill='#3a72c4', outline='', tags=('mark',))

    def sync_yview(self, first, last):
        """互換のために残す（以前の Text ガターの API に合わせてある）。"""
        self.redraw()

    # ------------------------------------------------------------
    # クリック・ドラッグでの行選択、ダブルクリックでのブックマーク
    # ------------------------------------------------------------
    def _line_at_y(self, y):
        """キャンバス上の縦位置から、対応する論理行番号を求める。"""
        try:
            index = self.target.index(f'@0,{y}')
            return int(index.split('.')[0])
        except Exception:
            return None

    def _select_lines(self, a, b):
        """
        target 側で、行 a〜b（両端含む）をまるごと選択する。

        ★★ **錨（選択の起点）を、選んだ範囲の先頭の行頭に置く**
        （項目48-RC・2026-09-05・うにさんの指定「行番号クリックで
        選択した後、Shift+矢印での選択範囲が想定と違う。**行の先頭に
        始点（錨）があるように広げる**」）。

        もとは `sel` を張って `insert` を動かすだけで、**Tk の錨には
        触っていなかった**。Tk の錨は「最後に普通のクリックをした
        位置」に残るので、行番号で選んだあと Shift+矢印を押すと
        **まったく別の場所から**伸びていた。
        """
        target = self.target
        lo, hi = (a, b) if a <= b else (b, a)
        try:
            line_count = int(target.index('end-1c').split('.')[0])
        except Exception:
            return
        hi = min(hi, line_count)
        start = f'{lo}.0'
        end = f'{hi + 1}.0' if hi < line_count else f'{hi}.end'
        try:
            target.tag_remove('sel', '1.0', 'end')
            target.tag_add('sel', start, end)
            target.mark_set('insert', end)
            # **錨は選んだ範囲の先頭の行頭**（項目48-RC）。
            # `insert` は動かしている側の端（end）に置いてある
            # ので、Shift+矢印は「行頭 → いまの端」を伸び縮み
            # させる形になる。
            # 名前の決め方は `CorrectNoteApp._sel_anchor_mark` の
            # **1か所**に任せる（48-GN——ここには書かない）
            try:
                target.mark_set(CorrectNoteApp._sel_anchor_mark(target),
                                start)
            except Exception:
                pass
            # Shift+行番号クリックで2点間を選ぶための控え（48-RC）
            self._sel_anchor_line = lo
            # ドラッグで動かしている側の端（b）を見せる。
            # 以前は常に選択の先頭（start）を見せていたため、
            # 下向きのオートスクロールが1画面ぶん進むたびに
            # 先頭へ引き戻され、進まなくなっていた
            # （実機で「10行ぐらいで止まる」と報告・2026-08-09）。
            target.see(f'{max(1, min(b, line_count))}.0')
            # 焦点を移さないと、選択の背景色が出ない環境がある。
            # そのままコピー（Ctrl+C）もできるようにしておく。
            target.focus_set()
        except Exception:
            pass

    def _on_shift_press(self, event):
        """
        **Shift+行番号クリックで2点間を選ぶ**（項目48-RC・2026-09-05・
        うにさんの指定「行番号クリック後、Shift+別の行番号クリックで
        2点間を選択」）。

        錨がまだ無ければ、普通のクリックとして扱う（**錨を動かさない**
        のがこの操作の要点なので、`_select_lines` が置き直した
        `_sel_anchor_line` はそのまま使い回す）。
        """
        line = self._line_at_y(event.y)
        if line is None:
            return None
        anchor = getattr(self, '_sel_anchor_line', None)
        if not anchor:
            return self._on_press(event)
        self._drag_anchor = anchor
        self._select_lines(anchor, line)
        # `_select_lines` が錨を選択の先頭へ置き直すので、
        # 元の錨の行を戻しておく（2点間の起点は動かさない）
        self._sel_anchor_line = anchor
        return 'break'

    def _on_press(self, event):
        line = self._line_at_y(event.y)
        if line is None:
            return
        self._drag_anchor = line
        self._select_lines(line, line)

    def _on_drag(self, event):
        if self._drag_anchor is None:
            return
        # ドラッグしたまま欄の上端・下端に達したらスクロールする
        # （実機からの要望・2026-08-09）。押しっぱなしで止めていても
        # 進むように、after の繰り返しで続ける。
        self._drag_last_y = event.y
        if self._autoscroll_id is None:
            self._autoscroll()
        line = self._line_at_y(event.y)
        if line is None:
            return
        self._select_lines(self._drag_anchor, line)

    def _autoscroll(self):
        self._autoscroll_id = None
        if self._drag_anchor is None:
            return
        y = self._drag_last_y
        try:
            h = self.winfo_height()
        except Exception:
            return
        if y < 12:
            step = -1
        elif y > h - 12:
            step = 1
        else:
            return   # 端にいない。次の Motion でまた判断する
        try:
            self.target.yview_scroll(step, 'units')
        except Exception:
            return
        line = self._line_at_y(min(max(y, 1), max(1, h - 1)))
        if line is not None:
            self._select_lines(self._drag_anchor, line)
        self.redraw()
        self._autoscroll_id = self.after(60, self._autoscroll)

    def _on_release(self, event):
        """
        ボタンを離した。引用モード中なら、選んだ行の範囲を引用する。

        選択自体は _on_press / _on_drag で済んでいるので、
        ここでは「引用するかどうか」だけを判断する。
        """
        anchor = self._drag_anchor
        self._drag_anchor = None
        if self._autoscroll_id is not None:
            try:
                self.after_cancel(self._autoscroll_id)
            except Exception:
                pass
            self._autoscroll_id = None
        if anchor is None or self.on_pick_lines is None:
            return
        line = self._line_at_y(event.y)
        if line is None:
            line = anchor
        lo, hi = (anchor, line) if anchor <= line else (line, anchor)
        try:
            self.on_pick_lines(lo, hi)
        except Exception:
            pass

    def _on_double_click(self, event):
        line = self._line_at_y(event.y)
        if line is None:
            return
        if self.on_toggle_bookmark:
            self.on_toggle_bookmark(line)


# 最大化中の帯で「クリック」と「ドラッグ」を分ける幅（画素・項目48-EE）。
# 押したまま指がこれ以上動いたらドラッグとみなす。手ぶれで
# 最大化が外れない程度に広く、意図した移動は必ず拾える程度に狭く。
_WIN_DRAG_SLOP = 5


class CorrectNoteApp:
    def _apply_window_icon(self):
        """
        窓・タスクバーのアイコンを付ける（項目48-JR）。

        **2つとも呼ぶ**（片方だけだと、そちらを迂回して既定の羽根に
        戻る場所が残る・学び22）:

            `iconphoto` … PNG から。**どの環境でも効く**。`default=True`
                なので、あとから開くダイアログにも付く
            `iconbitmap(default=…)` … Windows だけ。`.ico` は小さい寸法を
                別に持っているので**タスクバーで潰れない**。`default=`
                なので新しい窓にも自動で付く（X11 では `.ico` を受け取れず
                例外になる——そこは PNG のほうが受け持つ）

        **PhotoImage は握っておくこと。** 参照を捨てると Python が
        回収して、アイコンが消える。

        絵が無くても起動を止めない（同梱漏れは `bundle_manifest` の
        報告と `ci_smoke_test` が知らせる）。
        """
        self._icon_image = None
        try:
            png = bundled_path(ICON_PNG)
            if png:
                self._icon_image = tk.PhotoImage(file=png)
                self.root.iconphoto(True, self._icon_image)
        except Exception:
            self._icon_image = None
        try:
            ico = bundled_path(ICON_ICO)
            if ico:
                self.root.iconbitmap(default=ico)
        except Exception:
            pass        # X11 は .ico を受け取れない。PNG のほうで足りる
        self._set_window_icons_win32()

    # 窓そのものが持つアイコン（Alt+Tab が見るのはこちら）。
    # `LoadImageW` で読んだ絵は**呼んだ側のもの**なので、
    # 掴んだまま持っておく（捨てると Windows が絵を失う）。
    _win_icon_big = None
    _win_icon_small = None

    def _set_window_icons_win32(self, widget=None):
        """
        **窓そのものにアイコンを結び付ける**（`WM_SETICON`・項目48-LY）。

        うにさんの報告（2026-08-30）:
        「**Alt+Tab でウインドウ選択時に、アプリアイコンが出てこない**」。

        調べたら、Tk の `iconphoto` も `iconbitmap(default=…)` も
        Windows では**クラスのアイコン**（`GCL_HICON`）しか置いて
        いなかった——窓に聞く `WM_GETICON` は BIG も SMALL も
        **0 のまま**（`tools_local/probe_icon.py` で実測）。
        タスクバーはクラスの絵で足りるので気づかないが、
        **Alt+Tab の切り替え画面は窓に聞く**ので、そこだけ絵が出ない。

        直し方は「クラスではなく**窓**に置く」——`.ico` から
        大小2つ読んで `WM_SETICON` を送る。**Tk の呼び出しは
        そのまま残す**（クラスの絵は、あとから開くダイアログや
        簡易入力の窓が受け取る側なので、どちらも要る・学び22）。

        `widget` を渡すとその窓に掛ける（既定は本体）。**簡易入力の
        窓にも掛ける**——クラスの絵を当てにしない（学び22。実測でも
        `GCL_HICON` は使えない値のことがあった）。

        絵が無くても、Windows でなくても、起動は止めない。
        """
        if sys.platform != 'win32':
            return False
        widget = widget if widget is not None else self.root
        ico = bundled_path(ICON_ICO)
        if not ico:
            return False
        try:
            import ctypes
            u32 = ctypes.windll.user32
            widget.update_idletasks()
            hwnd = u32.GetParent(widget.winfo_id())
            if not hwnd:
                return False
            IMAGE_ICON = 1
            LR_LOADFROMFILE = 0x0010
            WM_SETICON = 0x0080
            ICON_SMALL, ICON_BIG = 0, 1
            SM_CXICON, SM_CYICON = 11, 12
            SM_CXSMICON, SM_CYSMICON = 49, 50
            u32.LoadImageW.restype = ctypes.c_void_p
            u32.SendMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint,
                                         ctypes.c_void_p, ctypes.c_void_p]
            u32.SendMessageW.restype = ctypes.c_void_p

            def load(cx, cy):
                # 寸法を指定して読むと、`.ico` の中の**いちばん近い
                # 寸法**が選ばれる（256 を縮めた眠い絵にならない）
                return u32.LoadImageW(None, ico, IMAGE_ICON,
                                      u32.GetSystemMetrics(cx),
                                      u32.GetSystemMetrics(cy),
                                      LR_LOADFROMFILE)

            # 一度読んだ絵を使い回す（窓ごとに読み直さない）
            if not self._win_icon_big:
                CorrectNoteApp._win_icon_big = load(SM_CXICON, SM_CYICON)
            if not self._win_icon_small:
                CorrectNoteApp._win_icon_small = load(SM_CXSMICON,
                                                      SM_CYSMICON)
            big, small = self._win_icon_big, self._win_icon_small
            if not big and not small:
                return False
            for which, h in ((ICON_BIG, big), (ICON_SMALL, small)):
                if h:
                    u32.SendMessageW(ctypes.c_void_p(hwnd), WM_SETICON,
                                     ctypes.c_void_p(which),
                                     ctypes.c_void_p(h))
            return True
        except Exception:
            return False        # 絵が付かなくても起動は妨げない

    def __init__(self, root):
        import time
        _t_start = time.monotonic()
        self.root = root
        self.root.title(APP_TITLE)
        self._apply_window_icon()
        self.root.geometry('1280x720')
        self.root.minsize(900, 480)
        self.root.configure(bg=BG)

        self.store = VocabularyStore(VOCAB_FILE)
        # **回数と最終使用時刻を、ファイルから実際に消す**
        # （項目48-QG/48-QN・2026-09-05）。うにさんの指定
        # 「この回数を記録する仕組みを削除します」は、**これから
        # 書かない**だけでは足りない——既に書かれているものが
        # 消えなければ「人に見られたくないデータが保存されている」
        # ままになる。読み込みで潰した形を、その場で書き戻す。
        # **控えは残さない**（残すと依頼の目的に反する）。
        # **書けなくても起動は止めない**（読み取り専用の場所に置かれた・
        # 空きが無い等）。移行は次の起動でまたやり直せる——
        # `legacy_on_disk` は読み込むたびに立つ。
        try:
            if getattr(self.store, 'legacy_on_disk', False):
                self.store.save()
        except Exception:
            pass
        # **育ちのデータを消す**（項目48-QL/48-QN）。
        # うにさんの指定への回答3「推奨のとおり初期分だけ」——
        # 語の共起（`context_vec.json`）と字の並び（`charngram.json`）は
        # **本人の書いた行から育つ**ので、記録をやめるだけでは足りない。
        # 既に書かれているものを消して初めて「保存されていない」になる。
        # **控えは残さない**（残すと依頼の目的に反する）。
        # 同梱の初期分（`seed_context.ensure_seeded`）は今までどおり使う。
        for _grown in (CONTEXT_VEC_FILE, os.path.join(app_dir(),
                                                      'charngram.json')):
            try:
                if os.path.exists(_grown):
                    os.remove(_grown)
            except Exception:
                pass
        # 語彙が空だと補正が一切効かないため、初回起動時に常用語を投入する
        # **書けなくても起動は止めない**（すぐ上の移行と同じ形）。
        # `os.replace` は Windows では**書き込み先を誰かが掴んでいると
        # 落ちる**——USB や同期フォルダに置かれると起きうる。
        # 種はメモリには載っているので、この回も補正は効く。
        if load_seed(self.store):
            try:
                self.store.save()
            except Exception:
                pass
        _t_vocab = time.monotonic()

        # 補正結果をクリックして示された判断（誤補正の抑止）
        self.decisions = DecisionStore(DECISIONS_FILE)
        # **最後に選んだ表記の1枠**（項目48-QH）。前後の語も回数も
        # 時刻も持たない。旧 `choices.json` はここで畳んで消す。
        self.choices = LastChoiceStore(LAST_CHOICE_FILE)
        try:
            from last_choice import migrate_from_choices
            # **語彙を渡す**（項目48-QI）。渡さないと
            # `is_homophone_reading` が何も言えず、**読みの枠が
            # 1つも立たない**まま移行が終わる。索引（`dict_index`）は
            # この時点でまだ組まれていない（`ensure_built` は後）ので
            # 渡しても空を返す——**本人の語彙で判定する**。
            _n, _r = migrate_from_choices(CHOICES_FILE, LAST_CHOICE_FILE,
                                          store=self.store)
            if _n:
                self.choices.load()
        except Exception:
            pass
        # janome 辞書の読み索引（候補づくり用）。初回使用時に構築する
        self.dict_index = DictIndex(DICT_INDEX_FILE)
        # **同音異義語かの判定に使う材料を預ける**（項目48-QH）。
        # 預けないと、`record` を呼ぶ 8 か所すべてに引数が生える。
        self.choices.bind(self.store, self.dict_index)
        # **枠を差す口はここ1か所**（項目48-QH・`last_choice.set_active`）。
        # `vocabulary.lookup` の並びと、corrector の同音の道が、
        # どちらもこの1本を読む（学び22）。**測る道具は差さない**ので、
        # 初期状態の測定は枠の影響を受けない。
        try:
            import last_choice as _lc_mod
            _lc_mod.set_active(self.choices)
        except Exception:
            pass
        # 語の共起から作る軽量な文脈ベクトル。
        # 同じ読みに複数の有力な表記がある場合（過ぎ／好き 等）に、
        # 周辺の語と意味的に馴染む方を選ぶ追加の手がかりに使う。
        # 外部の学習済みモデルは使わず、このアプリが解析した
        # メモの内容だけから育てる（オフライン・辞書と統計だけ、
        # という設計方針を保つため）。
        # 起動を待たせないため、読み込みは裏のスレッドで行う
        # （_start_warmup）。それまでは None（無しでも補正は動く）。
        self.context_vec = None
        # 直前に確定した語（新しい順）。同音異義語をどちらにするかの
        # 手がかりとして、周囲の語と並べて使う。保存はしない
        # （書いている最中の流れを見るためのもので、開き直せば忘れる）。
        try:
            from context_vec import RecentWords
            self.recent_words = RecentWords()
        except Exception:
            self.recent_words = None
        _t_context_vec = time.monotonic()

        self._dropdown = None      # 開いている選び直しメニュー
        self._dropdown_text = ''   # 候補表示中に Ctrl+C でコピーする文字列
        self._drag = None          # 1本指ドラッグ（タッチパネルのスクロール用）
        # スクロールの掴みの間だけカーソルを隠す（項目48-JQ）。
        # (欄, 隠す前の形) を控えて、離したときに戻す。
        self._scroll_cursor = None
        self._line_h = None        # 行の高さ（ピクセル）。初回に測る
        self._overview = None      # 俯瞰（右ダブルクリック押しっぱなし）
        self._overview_pad = {}    # 俯瞰の前の行間（欄ごとに控える）
        self._font_swap = False    # 字を入れ替えている間（逆流の門）
        self._pick_mode = None      # 語を拾って差し込むモード。
                                    # None（オフ）/ 'f1' / 'equals'
        self._find_dialog = None   # 開いている検索／置換ダイアログ
        self._find_query = None    # 検索条件（ダイアログを閉じても覚えておく）
        # **検索した文字列の履歴**（項目48-SG・2026-09-06・うにさんの指定
        # 「前回の検索文字を記憶しておき、検索表示時に欄にセットする。
        # 下キーで検索した文字列の履歴を選べるようにする。どちらも
        # 保存はしないので、アプリを終了すると欄と履歴は消える」）。
        # **保存しない**——settings にも session にも書かない
        self._find_history = []    # 新しいものが先。同じ語は1つ
        self._find_last_text = ''  # 最後に検索した文字列
        self._find_hist_popup = None
        # 統合レイアウト・簡易入力ウィンドウで選び直した履歴。
        # 候補一覧に「元に戻す」を出すために使う。
        # ひとつ前だけでなく、それより前の選び直しにも戻れるよう
        # スタックとして持つ（実機からの要望）。
        # 古いものから順に捨てるため、上限を決めておく。
        self._editor_changes = []
        self._quick_changes = []
        self.line_units = []       # 各行のクリックできる語の単位
        self.line_texts = []       # 各行の表示テキスト（選び直し反映後）
        # F2 で候補を出している対象の語（括弧ボタンがこれを使う）。
        # {'widget':..., 'row':..., 'start':..., 'end':..., 'text':...}
        self._f2_focus_target = None

        self.current_file = None
        self.line_results = []
        self._prev_lines = []
        self._after_id = None
        self._gutter_after_id = None    # 行番号の引き直しの予約
        self._last_equals_pos = None    # 後追いで拾った「＝」の位置
        self._learn_after_id = None
        # 入力方式が変わったあとの解析し直しの予約（項目48-S）。
        # 変換中は走らせないので、予約したまま待つことがある。
        self._imethod_after_id = None
        self._ime_checked_at = 0.0
        # 前回の解析結果の控え（項目48-L）。起動時に一度だけ読む。
        self._analysis_cache = {}
        # 「古いかもしれない」印（項目48-LF）。学習で答えが変わり
        # うる控えの鍵を入れる。捨てずに印だけにする——理由は
        # `_invalidate_analysis_cache` の説明。
        self._analysis_stale = set()
        # その控えから復元した回だけ True。描画用の単位だけ組み立てる。
        self._analyze_units_only = False
        # タブを開いたときに戻したい表示位置（項目48-N）。
        self._pending_scroll = 0.0
        self._pending_scroll_top = None   # 行番号の控え（2026-08-16）
        # 統合表示の自動反映で書き換えた行の控え。
        # **行そのもの**（Tk のマーク）に結び付けて持つ。
        # 詳しくは _autofix_remember の説明を参照。
        self._autofix_records = []
        # 簡易入力の欄の控え。**名簿は面ごとに分ける**——
        # `editor_source_text` が `_autofix_live_records()` を引いて
        # 保存する原文を作るので、混ぜると簡易入力の原文が
        # ファイルへ焼き付く。対応づけは `_autofix_pane`。
        self._quick_autofix_records = []
        self._autofix_mark_seq = 0
        self._autofix_rounds = 0
        # 設計33（1段目）の仮の記録。自動反映した語が手で消されたとき、
        # ここに置き、**カーソルがその行から離れた時点で**初めて
        # decisions.reject() を呼ぶ（消しが続けば呼ばずに捨てる）。
        # DecisionStore には確定するまで入れない——「一度伝えた判断は
        # 二度と覆らない」という decisions.py の決まりを曲げないため。
        self._d33_pending = []
        self._d33_mark_seq = 0
        # いま編集中の行の、控えの写し（{'row','applied','spans'}）。
        # 控えは行が書き換わると解析が落とすので、消し終わるまで
        # 見張り側で姿を持っておく。カーソルがその行を離れたら捨てる。
        self._d33_shadow = None
        # このセッションで既に語彙学習の対象にした行（行の文字列そのもの）。
        # 編集のたびにメモ全文を学習し直すと、貼り付けた長文の中の語が
        # 編集のたびに count を稼いで「使用実績のある語」に化けてしまう
        # （count=1 の関門が数回の編集で突破される）。書かれた行は
        # 一度だけ学習し、以後は「新しく書かれた行」だけを学習する。
        # 復元・ファイルを開いた内容にも学習済みの種を蒔く
        # （開き直すだけで使用実績が増えるのは「使用」ではないため）。
        self._learned_lines = set()
        self._session_after_id = None   # 自動保存の予約
        self._dirty = False             # 保存済みの内容から変わっているか
        self._syncing = False   # スクロール同期の再帰を防ぐ
        # 全行解析を小分けにするための状態（_analyze 参照）
        self._analyze_job = None    # 次のひと区切りの予約
        self._analyze_todo = []     # まだ解析していない行番号（0始まり）
        self._analyze_pos = 0       # _analyze_todo のどこまで済んだか
        self._analyze_ctx = {}      # そのひと続きで使う文脈語彙
        self._analyze_text = ''     # 学習に渡す本文（解析し終えてから使う）
        self._analyze_band = None   # 直前に見た画面の範囲（項目48-BS）
        # 行ごとの内容語の控え（近傍の行を何度も分割し直さないため）
        self._line_words_cache = {}

        # 編集中の内容の控え（保存せず閉じても続きから再開できる）
        self.session = SessionStore(SESSION_FILE)

        # グローバルホットキー（アプリが非アクティブでも簡易入力を呼べる）
        self.settings = Settings(SETTINGS_FILE)

        # **IME が確定した「表記 → 打った読み」の対**（設計25）。
        #
        # うにさんの指定（2026-08-20）:
        #
        # > 「確定直前のひらがな情報を保持する実装を次に始めて
        # >   ください。**ひらがながあれば、読みが分かるので
        # >   自動補正します**」
        #
        # 覚えるのは `_ime_reading_tick`（Windows のみ）。
        # 使うのは `kanji_guess` の読みの組み立てで、**逆算より先に
        # 打った読みを試す**。**語彙・charngram・文脈ベクトルには
        # 一切流さない**（学び2）。
        #
        # **差すのはここ1か所。** 差さなければ今までどおり逆算だけで
        # 動く（ものさしはそちらで回る）。
        self.ime_readings = IMEReadings(IME_READINGS_FILE).load()
        self._ime_pairs_dirty = False    # 新しい対を覚えたか（下記）
        # 見張りの控え。**Windows 以外では使われない**が、
        # 「在るのに空」と「そもそも無い」を分けないで済むよう、
        # ここで作っておく（`_ime_reading_tick` が素直に書ける）。
        self._ime_comp = ''           # 直前の未確定文字列
        self._ime_comp_reading = ''   # 変換中に見えていた読み
        self._ime_first_kana = ''     # まだ全部かなだった間の最長
        self._ime_last_result = ''    # 直前に見た確定文字列
        self._ime_watch_id = None
        try:
            import kanji_guess
            kanji_guess.set_ime_readings_provider(
                self.ime_readings.readings_for)
        except Exception:
            pass

        # 語彙の控えからの復元（vocabulary_restore.json があれば一回だけ）。
        # 手入れの第1版（下記）が連用形（打ち・入れ・出し）まで
        # 実績を取り消してしまい、かな打ち（1-D の語の組）が直らなく
        # なった。取り消し前の控えへ正しい基準の手入れを掛け直した
        # ものをこのファイルで渡し、使用回数を「今と控えの大きい方」に
        # 合わせる。適用したらファイルを消すので、二度は行われない。
        self._apply_vocab_restore()

        # 語彙の一回きりの手入れ。過去の自動学習の count 水増しで
        # 「使用実績のある語」になってしまった活用の断片（分から・
        # 使え 等）の実績を取り消す（janome_import.
        # repair_conjugated_fragments 参照）。一度実施したら印を立て、
        # 以後は行わない（今後の本当の使用実績を消さないため）。
        # 印は v2: 第1版は連用形まで取り消す誤りがあったため、
        # 基準を直した版で改めて一度だけ実施する（上の復元のあとに
        # 走る並びなので、復元された実績が誤って消されることはない）。
        if not self.settings.get('vocab_repair_fragments_v2_done'):
            try:
                from janome_import import (repair_conjugated_fragments,
                                           HAS_JANOME)
                if HAS_JANOME:
                    if repair_conjugated_fragments(self.store):
                        self.store.save()
                    # janome が無い環境では印を立てない
                    # （立てると、次に janome が入っても手入れされない）
                    self.settings.set('vocab_repair_fragments_v2_done', True)
                    self.settings.save()
            except Exception:
                pass
        # その回の起動中だけ効く「一時解除」。
        # 設定ファイルには書かない（書くと次回も解除されたままになり、
        # 「一時的」でなくなるため）。アプリを開き直せば元に戻る。
        self._hotkey_suspended = set()
        # ホットキーのスレッドから主スレッドへ受け渡す箱。
        # スレッドから tkinter を触らないための入れ物
        # （_on_hotkey_triggered / _poll_hotkey_queue）。
        import queue as _queue
        self._hotkey_queue = _queue.Queue()
        self.hotkeys = GlobalHotkeys(on_triggered=self._on_hotkey_triggered)
        # 設定を先に入れてから起動する。
        # 起動してから設定すると、スレッドが「まだ全部オフ」の状態で
        # 最初の登録を済ませてしまう並びが起こりうる（実機で発生した）。
        # 先に入れておけば、スレッドは最初の同期で正しい状態を見る。
        self._apply_hotkey_state()
        self.hotkeys.start()

        self._build_ui()
        _t_build_ui = time.monotonic()
        self._update_status()

        # 前回のダークモード設定を反映する。
        # _build_ui はライトパレットの色でウィジェットを作るため、
        # 保存済みの設定がダークだった場合はここで塗り直す。
        #
        # タイトルバーの塗り替え（_apply_titlebar_theme）は、
        # ウィンドウが実際に画面へ出た後でないと正しいウィンドウ
        # ハンドルを取れないことがある。mainloop に入る前のこの時点
        # ではまだ実体化が済んでいない場合があるため、ウィジェットの
        # 色は即座に、タイトルバーだけ少し遅らせて行う。
        if self.settings.get('dark_mode'):
            self._apply_theme(True, titlebar_immediate=False)
            self.root.after(50, lambda: self._apply_titlebar_theme(True))
        # タイトルバーを隠す設定の反映（実体化後でないと効かない）
        self.root.after(150, self._apply_titlebar_visibility)
        # 窓のアイコン（Alt+Tab が見るほう・項目48-LY）も、実体化を
        # 待ってからもう一度掛ける。**同じ入口を呼ぶ**——__init__ の
        # 時点で付いていれば同じ絵をもう一度置くだけで、害は無い。
        self.root.after(200, self._set_window_icons_win32)

        # 前回のレイアウトを反映する。
        # _build_ui は左右分割の形で組み立てるので、統合が
        # 選ばれていた場合はここで補正欄を畳む。
        if self._layout_is_unified():
            self._apply_layout(reanalyze=False)
        self._update_layout_buttons()

        # 前回の続きを復元する。無ければ空の状態で始める。
        # tkinter のテキスト欄は「文字が存在しない位置」にカーソルを
        # 置けないため、どちらの場合も末尾に空行を足しておく
        # （起動直後から好きな行をクリックして書き始められるように）。
        self._restore_session()
        # ★★ **本文に残っていない打鍵の記録を、起動時にも落とす**
        # （項目48-QM・2026-09-05）。古いファイルに溜まった対は
        # ここで消える＝**移行を兼ねる**（`ime_readings.json` は
        # 削除ではなく掃除、というのがうにさんの指定）。
        #
        # **控えを読めた起動のときだけ**。読めなかった起動で掃除すると、
        # 空のタブ1枚を「本当に空だ」と読んで**全部消してしまう**。
        # 読めなかった回は掃除を見送るだけ——次に打てば保存の道で走る。
        if getattr(self, '_session_restored', False):
            try:
                self._prune_ime_readings()
                self.ime_readings.save()
            except Exception:
                pass
            try:
                self._sz_prune_log()      # 消えたときの記録も同じ（48-TM）
            except Exception:
                pass
        _t_restore = time.monotonic()

        # 閉じるときに、その時点の内容を必ず控える。
        # 保存していなくても次回に続きが出るようにするため。
        self.root.protocol('WM_DELETE_WINDOW', self._on_close)

        # **最小化から戻ったとき**も、最大化がタスクバーを覆って
        # いないか見る（項目48-MA。`_on_resize` でも拾えているが、
        # 「戻したら大きさが同じだった」道が残らないように口を2つ。
        # 収まっていればすぐ帰るので値段は付かない・学び22）。
        self.root.bind('<Map>', lambda e: self._clamp_zoom_to_workarea())

        self.editor.focus_set()
        # **変換の見張り**を始める（設計25(甲)・Windows のみ）。
        # ウィジェットが出来てからでないと `winfo_id()` が取れない。
        self._start_ime_reading_watch()
        # **ファイルのドロップを受ける**（項目48-TO）。同じ理由で
        # ここ——`winfo_id()` が取れてからでないと窓に手を掛けられない。
        self._setup_file_drop()
        _t_before_analyze = time.monotonic()
        # 最初の解析は起動処理の中では行わない。janome の辞書
        # 読み込みとメモ全文の形態素解析が重く、画面が出るまで
        # 待たされていた（実機で「起動時の動作が重い」と報告・
        # 2026-08-09）。裏のスレッドで下ごしらえし、済んでから
        # 解析を予約する（_start_warmup）。
        self._start_warmup()
        _t_analyze = time.monotonic()

        # 起動の各段階にかかった時間を、しばらくステータス欄に出す。
        # 「起動が長い」という報告の原因を切り分けるための一時的な
        # 診断表示。数値を見終えたら、この段落ごと取り除いてよい。
        try:
            timing = (
                f'起動: 語彙={_t_vocab - _t_start:.2f} '
                f'文脈={_t_context_vec - _t_vocab:.2f} '
                f'画面={_t_build_ui - _t_context_vec:.2f} '
                f'復元={_t_restore - _t_build_ui:.2f} '
                f'解析={_t_analyze - _t_before_analyze:.2f} '
                f'合計={_t_analyze - _t_start:.2f}s')
            print(timing)
            self.root.after(8000, lambda: self.status.config(text=timing))
        except Exception:
            pass

        # 初回起動時は、辞書の取り込みと索引の作成を自動で行う。
        # どちらも「やらないと候補が出ない」土台なので、
        # ユーザーがボタンの存在に気づく前に済ませてしまう。
        # 画面が出てから走らせたいので、少し待ってから呼ぶ。
        self.root.after(400, self._first_run_setup)
        # 説明書（HTML）を exe と同じフォルダへ書き出す。
        # 初回だけ・ファイルの写しだけなので軽いが、画面が出てから
        # 行う（起動を1ミリ秒でも待たせない）。
        self.root.after(600, self._extract_manual_on_start)
        # ホットキーの受け取りの見回りを始める（主スレッド）
        self.root.after(self.HOTKEY_POLL_MS, self._poll_hotkey_queue)
        self.root.after_idle(self._on_resize)

    # ------------------------------------------------------------
    # UI構築
    # ------------------------------------------------------------
    # ------------------------------------------------------------
    # 初回起動時の自動セットアップ
    # ------------------------------------------------------------
    def _first_run_setup(self):
        """
        初回起動時に、辞書の取り込みと索引の作成を自動で済ませる。

        どちらも済んでいないと候補がほとんど出ないため、
        ユーザーが自分でボタンを探して押す必要がない状態にする。
        一度終えたら印（setup.json）を残し、二度目以降は走らせない。

        途中で失敗しても起動は止めない。索引が無くても、
        覚えた語彙の範囲では候補が出るし、補正自体は動く。
        """
        if os.path.exists(SETUP_FILE):
            # 二度目以降。**アプリを更新して、辞書か索引の決まりが
            # 変わっていれば一度だけ尋ねる**（項目48-T・D-1）。
            # 起動の邪魔をしないよう、画面が落ち着いてから。
            try:
                self.root.after(2000, self._maybe_offer_data_update)
            except Exception:
                pass
            return
        try:
            from janome_import import HAS_JANOME
        except Exception:
            HAS_JANOME = False

        if not HAS_JANOME:
            # janome が無い環境では、やることが無いので印だけ残す
            self._mark_setup_done(dictionary=False, index=False)
            self.status.config(
                text='janome が見つからないため、簡易的な解析で動作します')
            return

        # 生成には数秒〜十数秒かかることがある。黙って固まっている
        # ように見えないよう、何をしているかのダイアログを出す
        # （うにさんの指定・2026-08-10）。終わったら自動で閉じる。
        dlg = self._show_busy_dialog(
            '辞書と索引を生成しています。\nしばらくお待ちください')
        try:
            ok_dict = self._auto_import_dictionary()
            ok_index = self._auto_build_index()
        finally:
            self._close_busy_dialog(dlg)
        self._mark_setup_done(dictionary=ok_dict, index=ok_index)

        self._update_status()
        if ok_dict or ok_index:
            self.status.config(
                text='初回の準備が終わりました。そのまま書き始められます。')

    # ------------------------------------------------------------
    # 説明書（HTML）の書き出しと表示
    # ------------------------------------------------------------
    # 説明書は exe の中に同梱し、初回起動時に exe と同じフォルダへ
    # 書き出す（うにさんの指定・2026-08-10。exe と html を zip に
    # まとめた配布にはしない。ダウンロードした exe 1つを置くだけで、
    # 説明書も一緒に手に入る形にする）。
    # メニューの「このアプリについて → 説明書をHTMLで展開」からは、
    # いつでも書き出し直して開ける。

    def _extract_manual(self, force=False):
        """
        同梱の説明書を app_dir()（exe と同じフォルダ）へ書き出す。

        force=False（初回起動時）は、まだ書き出していないときだけ
        行う。書き出した印は設定に **`APP_VERSION` で**残すので、
        **アプリの版が上がれば、次の起動で新しい説明書に
        入れ替わる**（項目48-OE）。ユーザーが自分で消したものを
        勝手に戻さないよう、印が残っていれば何もしない
        （メニューから force=True で明示的に書き出せる）。

        あわせて、**名前に版が入っていた頃の説明書**
        （`CorrectNote_説明書v5.html` など）を片付ける
        ——うにさんの「更新のたびに説明書が増える」への答え。

        戻り値: 書き出した（またはすでにある）説明書のパス。
            同梱もされておらず、フォルダにも無ければ None。
        """
        src = bundled_path(MANUAL_FILENAME)
        dst = MANUAL_FILE
        # 開発中（.py のまま実行）は、読み出し元と書き出し先が
        # 同じファイルになる。写す必要は無い。
        try:
            same = (src is not None
                    and os.path.abspath(src) == os.path.abspath(dst))
        except Exception:
            same = False
        if same:
            return dst
        if src is None:
            return dst if os.path.exists(dst) else None
        if not force:
            if self.settings.get('manual_extracted') == APP_VERSION:
                return dst if os.path.exists(dst) else None
        try:
            import shutil
            shutil.copyfile(src, dst)
        except Exception:
            return dst if os.path.exists(dst) else None
        # **名前に版が入っていた頃の説明書を片付ける**（項目48-OE）。
        # 消すのは**この造りが自分で書き出した形**だけ
        # （`CorrectNote_説明書v<数字>.html`）。
        try:
            import glob as _glob
            import re as _re
            for _old in _glob.glob(os.path.join(app_dir(),
                                                MANUAL_OLD_GLOB)):
                if _re.fullmatch(r'CorrectNote_説明書v\d+\.html',
                                 os.path.basename(_old)):
                    try:
                        os.remove(_old)
                    except Exception:
                        pass
        except Exception:
            pass
        try:
            self.settings.set('manual_extracted', APP_VERSION)
            self.settings.save()
        except Exception:
            pass    # 印が残せなくても動作には支障がない
        return dst

    def _extract_manual_on_start(self):
        """初回起動時の書き出し（起動を待たせないよう後回しで呼ぶ）。"""
        try:
            self._extract_manual(force=False)
        except Exception:
            pass

    def open_manual(self):
        """
        説明書を書き出して開く（メニューの「説明書をHTMLで展開」）。

        既にフォルダにあっても、同梱のものを書き出し直してから開く。
        「展開」と言われて押した以上、古いままのものが開くと
        分かりにくいため。
        """
        path = self._extract_manual(force=True)
        if not path or not os.path.exists(path):
            messagebox.showinfo(
                APP_TITLE,
                '説明書が見つかりませんでした。\n'
                f'{MANUAL_FILENAME} を {app_dir()} に置いてください。')
            return
        opened = False
        try:
            if sys.platform == 'win32':
                os.startfile(path)      # 既定のブラウザで開く
                opened = True
            else:
                import webbrowser
                opened = webbrowser.open(
                    'file://' + os.path.abspath(path))
        except Exception:
            opened = False
        if opened:
            self.status.config(
                text=f'説明書を書き出しました（{MANUAL_FILENAME}）')
        else:
            messagebox.showinfo(
                APP_TITLE,
                '説明書を書き出しました。\n'
                'ブラウザで開いてください:\n' + path)

    def ask_yes_no(self, message, yes='はい', no='いいえ',
                   default='no'):
        """
        「はい／いいえ」を尋ねる。**右上の × はキャンセル扱い**。

        tkinter の messagebox は、窓の × を押したときの扱いを
        こちらで決められない（環境によっては押せない・押すと
        「いいえ」になる）。うにさんの指定（2026-08-10）は
        「×を押したらキャンセル扱いとしてダイアログを閉じる」
        なので、自前の小さな窓にする。Esc も同じ扱い。

        default: 最初に選ばれているボタン（'no' か 'yes'）。
            **既定は 'no'（キャンセル）**。うにさんの指定
            （2026-08-10）: 「エンターを押したらキャンセル扱いと
            してダイアログを閉じる。キャンセルにデフォルト
            フォーカスしているような状態」。
            うっかり Enter を押しても、消える方へは倒れない。
            Enter は**選ばれているボタン**を押したのと同じ動き。

        あわせて、ダークモードの配色もそのまま乗る
        （messagebox は OS の描画なので色を合わせられない）。

        戻り値: 「はい」なら True。× ・Esc ・「いいえ」なら False。
        """
        result = {'v': False}
        try:
            dlg = tk.Toplevel(self.root)
        except Exception:
            return False
        dlg.title(APP_TITLE)
        dlg.transient(self.root)
        dlg.resizable(False, False)
        dlg.configure(bg=PANEL)

        def close(v=False):
            result['v'] = bool(v)
            try:
                dlg.grab_release()
            except Exception:
                pass
            try:
                dlg.destroy()
            except Exception:
                pass

        # × と Esc は「キャンセル」
        dlg.protocol('WM_DELETE_WINDOW', lambda: close(False))
        dlg.bind('<Escape>', lambda e: close(False))

        tk.Label(dlg, text=message, bg=PANEL, fg=INK,
                 font=('Yu Gothic UI', 10), justify='left',
                 padx=24, pady=18).pack(fill='both', expand=True)
        row = tk.Frame(dlg, bg=PANEL)
        row.pack(fill='x', padx=20, pady=(0, 16))
        _yes_default = (default == 'yes')
        btn_no = tk.Button(row, text=no, command=lambda: close(False),
                           bg=PANEL, fg=INK, relief='groove',
                           highlightthickness=(1 if not _yes_default else 0),
                           highlightbackground=ACCENT, highlightcolor=ACCENT,
                           font=('Yu Gothic UI', 9), width=10)
        btn_no.pack(side='right')
        btn_yes = tk.Button(row, text=yes, command=lambda: close(True),
                            bg=PANEL, fg=INK, relief='groove',
                            highlightthickness=(1 if _yes_default else 0),
                            highlightbackground=ACCENT, highlightcolor=ACCENT,
                            font=('Yu Gothic UI', 9), width=10)
        btn_yes.pack(side='right', padx=(0, 8))
        # Enter は「いま選ばれているボタン」を押したのと同じ
        dlg.bind('<Return>', lambda e: close(_yes_default))

        # 行数に応じて縦を伸ばす
        _lines = message.count('\n') + 1
        self._place_dialog(dlg, 460, 110 + 20 * _lines)
        try:
            (btn_yes if _yes_default else btn_no).focus_set()
            dlg.grab_set()
            self.root.wait_window(dlg)
        except Exception:
            pass
        return result['v']

    def _show_busy_dialog(self, message):
        """
        「処理中」を知らせる小さなダイアログを出す。

        ボタンは無く、閉じる操作もできない（処理が終われば
        _close_busy_dialog が自動で閉じる）。処理は主スレッドで
        走るため、出した直後に update() で一度描き切っておく。
        処理の途中の update_idletasks()（進み具合の表示）でも
        描画が保たれる。
        """
        try:
            dlg = tk.Toplevel(self.root)
            dlg.title(APP_TITLE)
            dlg.transient(self.root)
            dlg.resizable(False, False)
            dlg.protocol('WM_DELETE_WINDOW', lambda: None)
            dlg.configure(bg=PANEL)
            tk.Label(dlg, text=message, bg=PANEL, fg=INK,
                     font=('Yu Gothic UI', 10), padx=28, pady=20,
                     justify='left').pack(fill='both', expand=True)
            self._place_dialog(dlg, 380, 100)
            dlg.update()
            return dlg
        except Exception:
            return None

    def _close_busy_dialog(self, dlg):
        if dlg is None:
            return
        try:
            dlg.destroy()
        except Exception:
            pass

    def _auto_import_dictionary(self):
        """初回セットアップ: 辞書からよく使う語を取り込む。"""
        try:
            from janome_import import import_from_janome, DEFAULT_MAX_WORDS
        except Exception:
            return False

        # 既に十分な語彙があるなら取り込まない
        # （seed だけの状態かどうかで判断する）
        try:
            if len(self.store.to_list()) >= DEFAULT_MAX_WORDS:
                return False
        except Exception:
            pass

        self.status.config(text='初回の準備: 辞書を取り込んでいます…')
        self.root.update_idletasks()

        def progress(n):
            self.status.config(text=f'初回の準備: 語を集めています… {n} 語')
            self.root.update_idletasks()

        try:
            added = import_from_janome(self.store, progress=progress)
        except Exception:
            return False
        if added:
            try:
                self.store.save()
            except Exception:
                pass
        return bool(added)

    def _auto_build_index(self):
        """初回セットアップ: 候補づくり用の索引を作る。"""
        self.status.config(text='初回の準備: 辞書の索引を作っています…')
        self.root.update_idletasks()
        try:
            self.dict_index.ensure_built()
        except Exception:
            return False
        try:
            return self.dict_index.stats()['readings'] > 0
        except Exception:
            return False

    def _mark_setup_done(self, dictionary, index, declined=None):
        """
        初回セットアップが済んだ印を残す。

        **どの決まりで作ったか**も一緒に残す（項目48-T）。
        次の起動でここを見比べて、アプリを更新していれば
        「作り直しますか？」と尋ねる。

        declined: 「いいえ」と答えられた決まりの印。ここに入って
            いる間は、同じ版で二度は尋ねない。
        """
        import json
        import time
        data = {'done_at': time.time(),
                'dictionary': dictionary,
                'index': index}
        data.update(self._data_recipe_stamp())
        if declined:
            data['declined'] = declined
        try:
            with open(SETUP_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=1)
        except Exception:
            pass    # 印が残せなくても動作には支障がない（次回また試すだけ）

    # ------------------------------------------------------------
    # アプリを更新したあとの、辞書と索引の作り直し（項目48-T・D-1）
    # ------------------------------------------------------------

    def _data_recipe_stamp(self):
        """
        いまのアプリが「どの決まりで」辞書と索引を作るか。

        - `recipe`: 取り込みの決まりの版（janome_import）
        - `index_version`: 索引の形式の版（dict_index）

        **APP_VERSION は入れない。** 版を上げるたびに尋ねることに
        なるが、辞書と索引の中身が変わらない更新のほうが多い。
        中身が変わる変更をしたときだけ、上の2つを上げる。
        """
        stamp = {'recipe': 0, 'index_version': 0}
        try:
            from janome_import import IMPORT_RECIPE_VERSION
            stamp['recipe'] = IMPORT_RECIPE_VERSION
        except Exception:
            pass
        try:
            from dict_index import CACHE_VERSION
            stamp['index_version'] = CACHE_VERSION
        except Exception:
            pass
        return stamp

    def _read_setup_file(self):
        import json
        try:
            with open(SETUP_FILE, encoding='utf-8') as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _data_recipe_changed(self):
        """
        アプリを更新した結果、辞書か索引の決まりが変わったか。

        戻り値: (変わったか, いまの印)
        古い setup.json には印が入っていない。その場合は
        「0 だったもの」として扱うので、今の版が 1 以上なら
        一度だけ尋ねることになる（狙いどおり）。
        """
        now = self._data_recipe_stamp()
        saved = self._read_setup_file()
        if not saved:
            return False, now       # そもそも初回セットアップ前
        old = {'recipe': saved.get('recipe', 0),
               'index_version': saved.get('index_version', 0)}
        if old == now:
            return False, now
        if saved.get('declined') == now:
            return False, now       # この版は「いいえ」と答えられている
        return True, now

    def _maybe_offer_data_update(self):
        """
        アプリを更新したあと、辞書と索引の作り直しを一度だけ尋ねる。

        うにさんの指定（2026-08-11・D-1）:「ユーザがアップデート
        した際に辞書と索引が古いままになる問題があります。
        バージョンを差分で見て、更新を『はい/いいえ』で促しますが、
        **ユーザが手動で追加したものを消さない工夫**を検討して
        ください」。

        **消さない工夫の答え: 消さない。足すだけ。**
        語彙には「辞書から取り込んだ語」と「うにさんが打って
        覚えた語」「手で足した語」の区別が付いていない
        （どれも reading/surface/count/last_seen だけを持つ）。
        区別が付かない以上、**消してよいものを選べない**。
        だから作り直しは

          - 語彙: **足りないものを足すだけ**（`only_new=True`）。
            既にある語には触らない（使用回数も増やさない）。
          - 索引: **まるごと作り直す**。索引は janome の辞書から
            導かれるだけで、ユーザーのものは1つも入っていない。

        という形にする。この非対称が肝で、**ユーザーのものが
        混ざっている側は足すだけ／混ざっていない側は作り直す**。

        起動の邪魔をしないよう、落ち着いてから尋ねる。
        """
        try:
            changed, stamp = self._data_recipe_changed()
        except Exception:
            return
        if not changed:
            return
        try:
            from tkinter import messagebox
            answer = messagebox.askyesno(
                'CorrectNote',
                'アプリを更新しました。\n'
                '辞書と索引を新しい版で作り直しますか？\n\n'
                '・覚えた語や手で足した語は消えません（足すだけです）\n'
                '・数十秒かかることがあります\n'
                '・あとで「設定 → 辞書を取り込む」からもできます',
                parent=self.root)
        except Exception:
            return
        if not answer:
            # 同じ版では二度尋ねない。次にこちらが決まりを変えたら
            # また尋ねる（印が変わるため）。
            saved = self._read_setup_file()
            self._mark_setup_done(
                dictionary=saved.get('dictionary', False),
                index=saved.get('index', False),
                declined=stamp)
            return
        self._rebuild_dictionary_and_index()

    def _rebuild_dictionary_and_index(self):
        """
        辞書（語彙）を足し、索引を作り直す。

        **語彙は足すだけ・索引は作り直す**（理由は
        `_maybe_offer_data_update` の説明）。
        """
        dlg = self._show_busy_dialog(
            '辞書と索引を新しい版で作り直しています。\n'
            'しばらくお待ちください')
        added = 0
        ok_index = False
        try:
            try:
                from janome_import import (import_from_janome,
                                           DEFAULT_MAX_WORDS)

                def progress(n):
                    try:
                        self.status.config(text=f'辞書を見ています… {n} 語')
                        self.root.update_idletasks()
                    except Exception:
                        pass

                added = import_from_janome(self.store, progress=progress,
                                           only_new=True)
                if added:
                    self.store.save()
            except Exception:
                added = 0
            # 索引はまるごと作り直す。控えのファイルを消してから
            # 組み直さないと、古い控えをそのまま読んでしまう。
            #
            # **janome が無いなら消さない。** 消してから
            # `ensure_built` を呼ぶと、janome が無い環境では
            # 空の索引になって戻ってくる。いま持っている索引のほうが
            # まだましなので、そのまま置いておく。
            # （索引の中身は janome の辞書由来で、うにさんの
            #   ものは1つも入っていないが、**作り直せないなら
            #   壊すべきではない**。）
            try:
                from dict_index import HAS_JANOME as _HAS_JANOME
            except Exception:
                _HAS_JANOME = False
            if _HAS_JANOME:
                try:
                    import os as _os
                    self.dict_index._by_reading = None
                    self.dict_index._by_surface = None
                    path = getattr(self.dict_index, 'cache_path', None)
                    if path and _os.path.exists(path):
                        _os.remove(path)
                    self.dict_index.ensure_built()
                    ok_index = self.dict_index.stats()['readings'] > 0
                except Exception:
                    ok_index = False
            else:
                ok_index = bool(getattr(self.dict_index, 'ready', False))
        finally:
            self._close_busy_dialog(dlg)
        # 作り直したので、覚えている解析結果は全部捨てる。
        # **`keep_current=False`。** このあと全行を解析し直すため
        # （学び23。詳しくは `_invalidate_analysis_cache` の説明）。
        try:
            self._invalidate_analysis_cache(keep_current=False)
            self._prev_lines = []
            self._analyze_cause = '辞書と索引の作り直し'
            self._analyze()
        except Exception:
            pass
        saved = self._read_setup_file()
        self._mark_setup_done(
            dictionary=bool(added) or saved.get('dictionary', False),
            index=ok_index or saved.get('index', False))
        try:
            self.status.config(
                text=(f'辞書と索引を作り直しました（語を {added} 件追加）'
                      if added else '索引を作り直しました'))
        except Exception:
            pass
        self._update_status()

    # ------------------------------------------------------------
    # 自動保存と前回の続き
    # ------------------------------------------------------------
    # Windows 11 のメモ帳と同じ使い勝手を目指す。
    # 「保存」（ファイルへの書き出し）とは別に、書いた内容を
    # 裏で控えておき、保存せずに閉じても次回に続きが出るようにする。

    # 起動直後にクリックで書き始められるよう、末尾に足しておく空行の数
    TRAILING_BLANK_LINES = 24

    def _pad_blank_lines(self):
        """
        末尾に空行を足す。

        tkinter のテキスト欄は文字の無い位置にカーソルを置けないため、
        これが無いと下のほうをクリックしても書き始められない。
        """
        try:
            text = self.editor.get('1.0', 'end-1c')
            have = len(text) - len(text.rstrip('\n'))
            need = self.TRAILING_BLANK_LINES - have
            if need > 0:
                self.editor.insert('end', '\n' * need)
        except Exception:
            pass

    def _start_warmup(self):
        """
        重い準備（janome の辞書読み込み・文脈ベクトルの読み込み・
        メモ全文の内容語の下ごしらえ）を裏のスレッドで行い、
        終わってから最初の解析を予約する。

        tkinter への操作はスレッドから行えないので、スレッドは
        材料の準備だけを行い、画面への反映（解析の開始）は after の
        ポーリングで主スレッドが行う。準備が済む前にユーザーが
        打鍵した場合は、従来どおりその場で（同期で）準備される
        だけで、壊れはしない。
        """
        self._warmup = {'done': False, 'context_vec': None,
                        'ctx_cache': {}}
        try:
            warm_lines = self.editor.get('1.0', 'end-1c').split('\n')
        except Exception:
            warm_lines = []

        def _work(state=self._warmup, lines=warm_lines):
            fn = None
            try:
                fn = corrector.make_tokenizer(self.store)
                self.store._tokenize_fn = fn
            except Exception:
                pass
            # **辞書の読み索引もここで読み込む**（2026-08-16・実機）。
            # 普段の起動では誰も `ensure_built` を呼ばず、索引が
            # **空のまま全行の解析が走っていた**（控えの見分けに
            # dict_index=[0,0] が残っていた）。索引を門にしている
            # 補正（48-EG の「辞書に載っている語は触らない」など）が
            # 黙って守りを失い、`むすめ → むす？` と壊した。
            # キャッシュ（dict_index.json）を読むだけなら一瞬で、
            # 無ければ janome から作る（janome も無ければ空のまま。
            # その場合は corrector 側の門(0)が補正ごと止める）。
            try:
                self.dict_index.ensure_built()
            except Exception:
                pass
            # **「1語として在るか」の表もここで読む**（項目48-FC）。
            #
            # 100万語あって、読むのに **0.62秒** かかる（実測）。
            # 遅延読み込みのままにすると、**最初の解析の途中で
            # 0.6秒止まる**（門から呼ばれた瞬間に読まれるため）。
            # `familiarity` や `dict_index` と同じで、
            # **重い同梱物は裏で先に読む**のが筋。
            # 表が無ければ何も起きない（読み手が「意見なし」を返す）。
            try:
                import seed_japanese
                seed_japanese.available()
            except Exception:
                pass
            # **異様さの表もここで読む**（項目48-IR）。同梱の表から
            # 漢字の隣接ペアを作るのに **1.35秒**（実測）。最初の解析の
            # 途中で止まらないよう、裏で先に。読み終わるまで呼ばれたら
            # 「意見なし」（色が付かないだけ）。
            try:
                import oddness
                oddness.available()
            except Exception:
                pass
            try:
                from context_vec import ContextVectorStore
                cv = ContextVectorStore(CONTEXT_VEC_FILE)
                if cv.ensure_seeded():
                    cv.save()
                state['context_vec'] = cv
            except Exception:
                state['context_vec'] = None
            # ★★ **ここで語彙を書き換えない**（項目48-TT・2026-09-07。
            # 一度そうして、検品で止められた）。
            #
            # 英単語の覚え直しは「いったん全部消してから入れ直す」作りで、
            # `store` の辞書の**キーが消えて増える**。`VocabularyStore` は
            # **錠前を1本も持っていない**ので、主スレッドが同じ辞書を
            # 回している最中（`reading_trie`・`all_readings`・`to_list`…）に
            # ここで出し入れすると **RuntimeError で落ちる**。
            # 主スレッドの入口は10本以上あり、門を全部に掛けるのは
            # **同じ判定を道ごとに書く**ことになる（48-GN）。
            #
            # ★★ 速さのために正しさを賭けない。**覚え直しは主スレッド**
            # （`_poll_warmup`）のまま。控えが捨てられる無駄は、
            # そのあとの控え作りを**裏で回す入口**（`_warm_then_analyze`）に
            # 任せて避ける——主スレッドが払うのは覚え直しの分だけになる。
            # 復元したメモ全文の文脈語彙を先に作っておく
            # （最初の解析の同期部分を軽くする）
            try:
                if fn is not None:
                    from vocabulary import build_context_vocab_cached
                    build_context_vocab_cached(lines, self.store,
                                               state['ctx_cache'])
            except Exception:
                pass
            state['done'] = True

        import threading
        threading.Thread(target=_work, daemon=True).start()
        self._poll_warmup()

    def _merge_ctx_cache(self, got):
        """
        裏で作った文脈語彙の控えを、いまの控えへ入れる（項目48-TT''・2026-09-07）。

        ★★ **版の印（`_store_size`）ごと考える。**
        `build_context_vocab_cached` は「語の顔ぶれが変わったら控えを丸ごと
        捨てる」ので、控えには版の印が入っている。これを `setdefault` で
        混ぜると**古い印が残り**、せっかく裏で作った控えが**次の呼びで
        丸ごと捨てられる**（実機で 1.2秒の作り直しを主スレッドが払っていた）。

        印が違うなら**丸ごと置き換える**——古いほうはどのみち捨てられる
        中身なので、これが正しい。同じなら足すだけ。
        """
        got = got or {}
        cur = getattr(self, '_ctx_vocab_cache', None)
        if cur is None or cur.get('_store_size') != got.get('_store_size'):
            self._ctx_vocab_cache = got
            return
        for k, v in got.items():
            cur.setdefault(k, v)

    def _poll_warmup(self):
        state = getattr(self, '_warmup', None)
        if state is None:
            return
        if not state['done']:
            try:
                self.status.config(text='準備中…（読み書きはできます）')
            except Exception:
                pass
            self.root.after(50, self._poll_warmup)
            return
        self._warmup = None
        if state['context_vec'] is not None and self.context_vec is None:
            self.context_vec = state['context_vec']
        self._merge_ctx_cache(state['ctx_cache'])
        try:
            self.status.config(text='')
        except Exception:
            pass
        # 最初の解析の**前**に、メモにある英単語を覚えておく。
        # あとから覚えても、本文が変わっていない行は解析し直されない
        # ので、その回は直らないまま残る（実機で Planetarium が
        # 直らなかった原因のひとつ・2026-08-10）。
        self._learn_english_from_tabs()
        # 前回の解析結果の控えを読む（項目48-L）。**英単語の
        # 覚え直しより後**に読むこと: 覚え直しで語彙が変われば
        # vocabulary.json の見分けも変わり、控えは自動で捨てられる。
        self._load_analysis_cache()
        self._analyze_cause = '起動'
        # ★★ **`_analyze` を直に呼ばない**（項目48-TT・2026-09-07）。
        # すぐ上の覚え直しで**語の顔ぶれが変わる**（実機で143語・
        # `shape_revision` 1→287）ので、裏で作った文脈語彙の控えは
        # `build_context_vocab_cached` に**丸ごと捨てられる**。
        # ここで `_analyze` を呼ぶと、その作り直し（実機で1.07秒）を
        # **主スレッドで**払うことになる。
        # `_warm_then_analyze` に渡せば、作り直しは**裏のスレッド**へ行く
        # （控えが温かいまま＝捨てられなかった回は、その場で解析へ進む）。
        self._warm_then_analyze()

    def _apply_vocab_restore(self):
        """
        vocabulary_restore.json があれば、**立っている印だけ**を
        控えに合わせて、ファイルを消す。

        語彙の手入れ第1版（2026-08-09）が連用形の実績まで取り消して
        しまった分の復元用。控え側には正しい基準の手入れが済んで
        いるので、
        - 誤って取り消された語（打ち 等）は立った状態に戻り、
        - 正しく取り消された断片（分から 等）は控えでも立っていない
          ので戻らず、
        - 適用までの間に新しく覚えた分はそのまま。

        **回数は見ない**（項目48-QG）。控えが旧形式（count 付き）
        なら `count >= 2` を「立っていた」と読む——移行と同じ読み方。
        """
        restore_path = os.path.join(app_dir(), 'vocabulary_restore.json')
        if not os.path.exists(restore_path):
            return
        try:
            import json
            with open(restore_path, encoding='utf-8') as f:
                data = json.load(f)
            from vocabulary import _set_solid as _mark
            from vocabulary import entry_is_solid as _is_solid
            changed = 0
            for item in data if isinstance(data, list) else []:
                reading = item.get('reading')
                surface = item.get('surface')
                if not reading or not surface:
                    continue
                # `entry_is_solid` が旧形式（count 付き）の読み方も
                # 持っている——**同じ判定を2度書かない**（48-GN）。
                if not _is_solid(item):
                    continue
                for e in self.store.lookup(reading):
                    if e['surface'] == surface and not _is_solid(e):
                        _mark(e, True)
                        changed += 1
            if changed:
                self.store._invalidate_cache()
                self.store.save()
        except Exception:
            return
        try:
            os.remove(restore_path)
        except Exception:
            pass

    def _restore_session(self):
        """前回の続きを開く。無ければ空の状態で始める。

        控えは最初からタブの配列なので、複数タブもそのまま戻る。
        画面への反映は _load_active_tab に一本化した（タブ切り替えと
        同じ経路。2026-08-09 のタブ管理UIの導入にあわせて整理）。
        """
        restored = False
        try:
            restored = self.session.load()
        except Exception:
            restored = False
        if not restored or not self.session.tabs:
            # 起動して**新しく作る**1枚（項目48-RA）。控えが読めた回は
            # ここを通らない。**印を付けるかを決めているのは
            # `session.fresh_tab` の1か所**（48-GN——ここには書かない）
            self.session.reset_fresh()
        # **控えを本当に読めたか**（項目48-QM）。読めなかった起動で
        # 「本文は空だ」と読むと、打鍵の記録を全部消してしまう
        # ——`set_single('')` は**空のタブ1枚**を作るので、
        # 「読み込みに失敗した」と「本当に空だ」の区別が付かなくなる。
        self._session_restored = bool(restored and self.session.tabs)
        self._load_active_tab(initial=True)
        self._refresh_tab_bar()
        try:
            if self.session.has_content():
                if self._dirty:
                    self.status.config(text='前回の続きを開きました（未保存）')
                else:
                    self.status.config(text='前回の続きを開きました')
        except Exception:
            pass

    def editor_source_text(self):
        """
        メモ欄の**原文**（打った文字そのもの）を組み立てて返す。

        統合表示の自動反映は、あくまで**見せ方**の変換であって、
        文書そのものを書き換えたことにはしない
        （うにさんの指定・2026-08-10「分割モードのメモ欄に文字列が
        残り、補正欄が表示されているような仕組み」）。
        そのため、控え（session.json）とファイルへの保存には
        **原文のほうを書く**。

        こうしないと、閉じて開き直したときに書き換わったほうが
        本文として残り、原文が永久に失われる。色も付かなくなる
        （もう直すところが無いため。実機で報告・2026-08-10
        「起動時にも色が付かない。原文が書き換わっているように
        見えます」）。

        控えの無い行（自動反映で書き換えていない行）は、そのまま返す。

        **控えは「行の文字列」ではなく「その行そのもの」に結び付けて
        持つ**（`_autofix_remember`）。文字列を鍵にしていた頃は、
        補正の結果と同じ文字列を**自分で正しく打った行**まで
        逆引きの対象になり、打っていない誤字が保存されていた
        （2026-08-10 の検証で判明。「たんこ゛のつながり」を直した
        あとに「たんごのつながり」と自分で打つと、保存した中身が
        2行とも「たんこ゛のつながり」になる）。
        """
        try:
            text = self.editor.get('1.0', 'end-1c')
        except Exception:
            return ''
        lines = text.split('\n')
        for rec, row in self._autofix_live_records():
            if 1 <= row <= len(lines):
                lines[row - 1] = rec['original']
        return '\n'.join(lines)

    def _capture_session(self):
        """今の状態を控えの形にまとめる。"""
        # 起動時に足した末尾の空行は控えに残さない
        # （毎回積み重なって増えていくのを防ぐ）
        # 統合表示で自動反映した分は原文に戻して控える
        # （editor_source_text の説明を参照）。
        text = self.editor_source_text().rstrip('\n')
        try:
            cursor = self.editor.index('insert')
        except Exception:
            cursor = '1.0'
        try:
            scroll = self.editor.yview()[0]
        except Exception:
            scroll = 0.0
        # **いちばん上に見えている行番号も控える**（2026-08-16）。
        # scroll（割合）は折り返し・解析後の描き直しで意味がずれる
        # ので、タブへ戻ったときの復元はこちらを優先する。
        try:
            top = int(self.editor.index('@0,0').split('.')[0])
        except Exception:
            top = None
        cur = self.session.current()
        title = cur.get('title') if cur else None
        self.session.update_active(new_tab(
            text, self.current_file, saved=not self._dirty,
            cursor=cursor, scroll=scroll, title=title,
            bookmarks=self.bookmarks, top=top))

    def _schedule_session_save(self):
        """入力が落ち着いたら控えを書き出す。"""
        if self._session_after_id:
            self.root.after_cancel(self._session_after_id)
        self._session_after_id = self.root.after(1500, self._save_session)

    def _save_session(self):
        self._session_after_id = None
        try:
            self._capture_session()
            self.session.save()
        except Exception:
            pass    # 控えが取れなくても編集は続けられる
        # **IME の読みの対**も、控えと同じ間合いで書く（設計25(甲)）。
        # 変わっていなければ何もしない（`save` の中で見ている）。
        # 打つたびに書かないのは、1確定ごとにファイルを書き換えると
        # 手が止まるため。落ちても失うのは「その少しの間に打った
        # 読み」だけで、次に同じ表記を打てばまた覚える。
        #
        # ★★ **書く前に掃除する**（項目48-QM・2026-09-05）。
        # うにさんの指定「打った表記は、アプリに掛かれている文字と
        # 対にするので、**アプリの文字が消えれば打ったキー情報も
        # 消えます**」。＝ 蓄積する入力履歴ではなく、いま書かれている
        # 本文の付随情報。**どのタブの本文にも無い対は落としてから**
        # 書く。掃除で中身が減れば `stamp()` も変わるので、
        # 覚えている解析結果は自動で捨てられる（項目48-HA）。
        try:
            self._prune_ime_readings()
        except Exception:
            pass
        try:
            self._sz_prune_log()          # 消えたときの記録も同じ（48-TM）
        except Exception:
            pass
        try:
            self.ime_readings.save()
        except Exception:
            pass

    def _prune_ime_readings(self):
        """
        **本文に残っていない打鍵の記録を落とす**（項目48-QM）。

        判定は全タブの本文への部分一致（`ime_readings.keep_only_in`）。

        ★★ **本文が1枚も取れていないときは、渡さない**。
        `keep_only_in` は「紙が1枚も無い→何もしない／中身の無い紙が
        来た→全部落とす」で分けている（項目48-QM）。ところが
        `editor_source_text()` は**失敗しても `''` を返す**ので、
        素直に足すと**必ず「中身の無い紙が1枚」**になり、
        「取れなかった」が「本当に空だ」に化ける。
        控えの読み込みに失敗した起動で**打鍵の記録を全部消す**形。

        48-HA（打った読みの口）・48-LB（本人確定の記録）は、
        **本文に残っている語については今までどおり働く**。
        解析し直しに証拠が要るのはまさに「まだ書かれている行」なので、
        意味も合っている。
        """
        ir = getattr(self, 'ime_readings', None)
        if ir is None or not hasattr(ir, 'keep_only_in'):
            return
        texts = [tab.get('text', '') or ''
                 for tab in (self.session.tabs or [])]
        # いま編集中のタブは、まだ控えに書き戻されていないことがある。
        # **取れたときだけ足す**（`''` は「取れなかった」と区別が
        # 付かないので足さない。タブが在れば上の並びに入っている）
        try:
            _now = self.editor_source_text()
        except Exception:
            _now = ''
        if _now:
            texts.append(_now)
        if not texts:
            return          # 紙が1枚も無い＝読み込みの途中。何もしない
        ir.keep_only_in(texts)

    def _on_close(self):
        """
        閉じるとき。

        保存を促すダイアログは出さない。控えが必ず残り、
        次回に続きから再開できるため（メモ帳と同じ考え方）。
        """
        # 窓の差し替えを外す（項目48-TO の後片付け）。閉じる途中に
        # 落ちてきたメッセージで、手放したコールバックが呼ばれるのを防ぐ。
        try:
            self._teardown_file_drop()
        except Exception:
            pass
        if self._session_after_id:
            try:
                self.root.after_cancel(self._session_after_id)
            except Exception:
                pass
            self._session_after_id = None
        # 変換の見張りを止める（設計25(甲)）。止めずに destroy すると
        # 予約が生き残り、無くなったウィジェットを触りに行く。
        job = getattr(self, '_ime_watch_id', None)
        if job:
            try:
                self.root.after_cancel(job)
            except Exception:
                pass
            self._ime_watch_id = None
        # 設計33: 確定していない仮の記録を、閉じる前に確定する
        try:
            self._design33_flush()
        except Exception:
            pass
        self._save_session()     # ここで ime_readings も書かれる
        try:
            self.store.save()
        except Exception:
            pass
        # **語彙を保存したあとで**解析結果の控えを書く。
        # 見分けに vocabulary.json の更新時刻を使うので、順番が逆だと
        # 次回起動で必ず食い違って捨てられる。
        self._save_analysis_cache()
        try:
            self.hotkeys.stop()
        except Exception:
            pass
        self.root.destroy()

    def _save_analysis_cache(self):
        """
        解析済みのタブの結果を控えておく（項目48-L / 48-M）。

        次の起動でこれを読めれば、1000行のタブでも解析を丸ごと
        飛ばせる。**状況が少しでも違えば使われない**ので、
        書くほうは気楽でよい（詳しくは analysis_cache.py）。

        **開いていたタブだけでなく、この回に見たタブを全部書く。**
        最初は表に出ているタブ1つだけを書いていたが、それでは
        次の起動で別のタブへ移った瞬間にまるごと解析し直しになる
        （うにさんの報告・2026-08-11「タブ切り替えで5秒以上」）。
        """
        try:
            import analysis_cache
            recent = (self.recent_words.words()
                      if getattr(self, 'recent_words', None) is not None
                      else ())
            # **解析したときの入力方式**で見分けを作る（今の設定では
            # ない）。設定だけ変えて解析し直していない状態で保存する
            # と、次回「設定は合っているのに中身は古い」控えを読んで
            # しまう（Xvfb の probe で実際に踏んだ）。
            fp = analysis_cache.build_fingerprint(
                app_dir(), APP_VERSION,
                getattr(self, '_analyze_input_method', None), recent,
                store=self.store, context_vec=self.context_vec,
                dict_index=self.dict_index, decisions=self.decisions,
                choices=self.choices,
                ime_readings=getattr(self, 'ime_readings', None))
            # この回に解析したタブぶん（_remember_tab_results が
            # 溜めている）＋ いま表に出ているタブ。
            # **「古いかもしれない」印の付いたタブは書かない**
            # （項目48-LF）。画面の中では即表示を優先して使うが、
            # 次の起動の控えは今までどおり確かなものだけにする
            # （指紋は保存時の語彙で作るので、古い答えが新しい指紋で
            # 蘇ってしまう）。
            _stale = getattr(self, '_analysis_stale', ()) or ()
            tabs = {k: v for k, v in
                    (getattr(self, '_analysis_cache', {}) or {}).items()
                    if k not in _stale}
            # 鍵は `_analysis_key`（末尾の空行を落とす）。落とした
            # ぶんの結果も一緒に落とす——数が合わないと使われない。
            text = self._analysis_key('\n'.join(self._prev_lines or ()))
            if text and self._prev_lines and self.line_results \
                    and len(self.line_results) == len(self._prev_lines) \
                    and all(r is not None for r in self.line_results):
                tabs[text] = self.line_results[:len(text.split('\n'))]
            tabs = {k: v for k, v in tabs.items() if k and v}
            analysis_cache.save(ANALYSIS_CACHE_FILE, fp, tabs)
        except Exception:
            pass    # 控えが作れなくても、次回に解析し直すだけ

    # ------------------------------------------------------------
    # 検索と置換
    # ------------------------------------------------------------
    # Windows 11 のメモ帳の機能を目安にしている。
    # 一致の計算は search.py に置き、ここでは画面の操作だけを行う。

    def _editor_text(self):
        return self.editor.get('1.0', 'end-1c')

    def _place_dialog(self, dlg, w, h, y_ratio=1 / 3):
        """
        小さなダイアログを、本体ウィンドウを基準にした位置へ置く。

        位置を指定しないと OS・ウィンドウマネージャの既定配置に
        委ねられる。マルチディスプレイ環境では、それが本体と
        別のディスプレイになることがある（実機で報告された不具合）。
        本体ウィンドウの座標を基準にすれば、常に本体と同じ画面に出る。

        y_ratio: 縦位置。既定は本体の上から1/3の高さ
            （検索ダイアログのような横長・上寄りのものは呼び出し側で
            別の値を渡す）。
        """
        try:
            x = self.root.winfo_rootx() + max(
                0, (self.root.winfo_width() - w) // 2)
            y = self.root.winfo_rooty() + max(
                0, int((self.root.winfo_height() - h) * y_ratio))
            dlg.geometry(f'{w}x{h}+{x}+{y}')
        except Exception:
            dlg.geometry(f'{w}x{h}')

    def _offset_to_index(self, offset):
        """文字数での位置を、tkinter の「行.桁」に直す。"""
        return self.editor.index(f'1.0+{offset}c')

    def _index_to_offset(self, index):
        """tkinter の「行.桁」を、文字数での位置に直す。"""
        return len(self.editor.get('1.0', index))

    # メモ欄で文字が入力されてから、この秒数以内は Ctrl+F/Ctrl+H で
    # 検索ダイアログを開かない。IMEの変換確定操作がこれらのキーに
    # 割り当てられている場合の誤爆（合成中のフォーカス奪取）を防ぐ。
    _FIND_GUARD_SECONDS = 0.35

    def _open_find_dialog_guarded(self, replace=False):
        """
        IME確定直後の可能性がある場合は、ダイアログを開くのを
        一呼吸だけ遅らせて再確認する。

        メモ欄に焦点が無い場合（既に検索欄や他のウィジェットにいる場合）
        はIMEの合成と衝突しないので、遅延せずそのまま開く。
        """
        try:
            focused_editor = (self.root.focus_get() is self.editor)
        except Exception:
            focused_editor = False

        if not focused_editor:
            self.open_find_dialog(replace)
            return

        import time
        last = getattr(self, '_last_editor_change_at', 0.0)
        elapsed = time.monotonic() - last
        if elapsed >= self._FIND_GUARD_SECONDS:
            self.open_find_dialog(replace)
            return

        # 怪しいタイミング。IME確定の続きが割り込む余地を残すため、
        # 猶予ぶんだけ遅らせてから開く（フォーカスを奪う前に
        # IME側の確定処理が先に終わるようにする）。
        wait_ms = int((self._FIND_GUARD_SECONDS - elapsed) * 1000) + 50
        try:
            self.root.after(wait_ms, lambda: self.open_find_dialog(replace))
        except Exception:
            self.open_find_dialog(replace)

    def open_find_dialog(self, replace=False):
        """検索（と置換）のダイアログを開く。"""
        # 既に開いていれば、それを前に出す
        dlg = getattr(self, '_find_dialog', None)
        if dlg is not None:
            try:
                dlg.deiconify()
                dlg.lift()
                dlg.focus_force()
                if replace:
                    self._show_replace_row()
                return
            except Exception:
                self._find_dialog = None

        dlg = tk.Toplevel(self.root)
        dlg.title('置換' if replace else '検索')
        dlg.configure(bg=BG)
        dlg.transient(self.root)
        dlg.resizable(False, False)
        self._find_dialog = dlg

        # 選択中の文字列があれば、検索欄の初期値にする（メモ帳と同じ）。
        # **選択が無ければ、前回の検索語**（項目48-SG）
        initial = ''
        try:
            if self.editor.tag_ranges('sel'):
                initial = self.editor.get('sel.first', 'sel.last')
                if '\n' in initial:
                    initial = ''
        except Exception:
            initial = ''
        if not initial:
            initial = getattr(self, '_find_last_text', '') or ''

        self._find_query = tk.StringVar(value=initial)
        self._find_replacement = tk.StringVar()
        # **開いた直後（と、語を変えた直後）の検索は「新しい検索」**
        # （項目48-SG'・2026-09-06・うにさんの報告「タブ移動して検索
        # ウインドウを開いてエンターしただけだと、検索が見つからないと
        # 出る。メモ欄を一回クリックすると見つかる」）。タブを移ると
        # カーソルは控えた位置（たいてい末尾）に戻るので、「折り返して
        # 検索」が切れていると末尾から先に一致が無く「これ以上見つかり
        # ません」になっていた。新しい検索は、カーソルから先に無ければ
        # **先頭から**探す（「次を検索」の続きは今までどおり折り返しの設定）
        self._find_fresh = True
        self._find_query.trace_add(
            'write', lambda *_a: setattr(self, '_find_fresh', True))
        # 検索条件は前回の値を引き継ぐ。同じ検索の続きはもちろん、
        # アプリを開き直した後も同じ条件で検索したいという要望のため、
        # settings.json に保存する（正規表現は既定でオンにする）。
        self._find_match_case = tk.BooleanVar(
            value=self.settings.get('find_match_case'))
        self._find_whole_word = tk.BooleanVar(
            value=self.settings.get('find_whole_word'))
        self._find_regex = tk.BooleanVar(
            value=self.settings.get('find_regex'))
        self._find_wrap = tk.BooleanVar(
            value=self.settings.get('find_wrap'))
        for key, var in (('find_match_case', self._find_match_case),
                         ('find_whole_word', self._find_whole_word),
                         ('find_regex', self._find_regex),
                         ('find_wrap', self._find_wrap)):
            var.trace_add('write', lambda *_a, k=key, v=var:
                          self._save_find_option(k, v))

        body = tk.Frame(dlg, bg=BG)
        body.pack(fill='both', expand=True, padx=14, pady=12)

        tk.Label(body, text='検索する文字列', bg=BG, fg=INK,
                 font=('Yu Gothic UI', 9)).grid(row=0, column=0,
                                                sticky='w', pady=(0, 2))
        e_find = tk.Entry(body, textvariable=self._find_query, width=34,
                          font=('Yu Gothic UI', 10), relief='flat',
                          bg=PANEL, fg=INK, insertbackground=INK)
        e_find.grid(row=1, column=0, columnspan=3, sticky='we', ipady=4)

        # 置換欄は必要なときだけ見せる
        self._replace_label = tk.Label(body, text='置換後の文字列',
                                       bg=BG, fg=INK,
                                       font=('Yu Gothic UI', 9))
        self._replace_entry = tk.Entry(
            body, textvariable=self._find_replacement, width=34,
            font=('Yu Gothic UI', 10), relief='flat',
            bg=PANEL, fg=INK, insertbackground=INK)

        # **検索欄・置換欄にも、同じ受け皿を張る**（項目48-FY）。
        # IME が確定した半角記号（項目48-EH）と、テンキーの小数点は
        # メモ欄と同じように編集キーとして届く。ここだけ塞いで
        # いなかったので、検索語を打つときに文字が消えていた。
        # `tk.Entry` にも `insert('insert', ...)` があるので、
        # `_on_ime_ascii_key` はそのまま使える。
        for _e in (e_find, self._replace_entry):
            try:
                _e.bind('<KeyPress>', self._on_ime_ascii_key, add=True)
            except Exception:
                pass

        opts = tk.Frame(body, bg=BG)
        opts.grid(row=4, column=0, columnspan=3, sticky='w', pady=(10, 6))
        for text, var in [('大文字と小文字を区別する', self._find_match_case),
                          ('単語単位で探す', self._find_whole_word),
                          ('正規表現', self._find_regex),
                          ('折り返して検索', self._find_wrap)]:
            tk.Checkbutton(opts, text=text, variable=var, bg=BG, fg=INK,
                           font=('Yu Gothic UI', 9), selectcolor=PANEL,
                           activebackground=BG, activeforeground=INK,
                           anchor='w').pack(anchor='w')

        btns = tk.Frame(body, bg=BG)
        btns.grid(row=5, column=0, columnspan=3, sticky='we', pady=(6, 0))

        def mk(parent, label, cmd, primary=False):
            return tk.Button(
                parent, text=label, command=cmd,
                bg=(INK if primary else PANEL), fg=(BG if primary else INK),
                relief='flat', bd=(0 if primary else 1),
                font=('Yu Gothic UI', 9), padx=10, pady=4, cursor='hand2')

        mk(btns, '次を検索', lambda: self._do_find(False),
           primary=True).pack(side='left', padx=(0, 4))
        mk(btns, '前を検索', lambda: self._do_find(True)).pack(side='left',
                                                              padx=4)
        self._btn_replace = mk(btns, '置換', self._do_replace)
        self._btn_replace_all = mk(btns, 'すべて置換', self._do_replace_all)

        self._find_status = tk.Label(body, text='', bg=BG, fg=MUTED,
                                     font=('Yu Gothic UI', 9), anchor='w')
        self._find_status.grid(row=6, column=0, columnspan=3,
                               sticky='we', pady=(8, 0))

        body.columnconfigure(0, weight=1)

        # 検索欄で Enter を押したら次を検索（メモ帳と同じ）
        e_find.bind('<Return>', lambda e: self._do_find(False))
        e_find.bind('<Shift-Return>', lambda e: self._do_find(True))
        # **下キーで、検索した文字列の履歴を選ぶ**（項目48-SG）
        # `Down` は IME の取り違えの対象のキー名（項目48-IN）なので、
        # `_ime_first` で包む（確定した文字なら文字として入れる）
        e_find.bind('<Down>', self._ime_first(
            lambda e=None, w=e_find: self._show_find_history(w)))
        self._find_entry = e_find
        self._replace_entry.bind('<Return>', lambda e: self._do_replace())
        dlg.bind('<Escape>', lambda e: self._close_find_dialog())
        dlg.protocol('WM_DELETE_WINDOW', self._close_find_dialog)

        # 検索結果の目印
        self.editor.tag_configure('found', background=FOUND_BG)
        self.editor.tag_configure('found_current', background=FOUND_CUR_BG)

        if replace:
            self._show_replace_row()
        else:
            self._hide_replace_row()

        # 親ウィンドウの近くに出す（別ディスプレイに飛ばないように）
        dlg.update_idletasks()
        x = self.root.winfo_rootx() + 60
        y = self.root.winfo_rooty() + 80
        dlg.geometry(f'+{x}+{y}')
        e_find.focus_set()
        e_find.select_range(0, 'end')

    def _show_replace_row(self):
        self._replace_label.grid(row=2, column=0, sticky='w', pady=(8, 2))
        self._replace_entry.grid(row=3, column=0, columnspan=3,
                                 sticky='we', ipady=4)
        self._btn_replace.pack(side='left', padx=4)
        self._btn_replace_all.pack(side='left', padx=4)
        if self._find_dialog:
            self._find_dialog.title('置換')

    def _hide_replace_row(self):
        self._replace_label.grid_remove()
        self._replace_entry.grid_remove()
        self._btn_replace.pack_forget()
        self._btn_replace_all.pack_forget()

    def _remember_find_text(self, text):
        """
        検索した文字列を覚える（項目48-SG）。**このセッションの中だけ**
        ——保存しない。新しいものを先頭に、同じ語は1つ、20件まで。
        """
        if not text:
            return
        self._find_last_text = text
        hist = getattr(self, '_find_history', None)
        if hist is None:
            hist = self._find_history = []
        if text in hist:
            hist.remove(text)
        hist.insert(0, text)
        del hist[20:]

    def _show_find_history(self, entry):
        """
        **検索欄の下に、検索した文字列の履歴を出して選べるようにする**
        （項目48-SG・うにさんの指定「下キーで検索した文字列の履歴を
        選べるように」）。上下キーで動き、Enter か クリックで欄に入る。
        Esc・欄の外へ焦点が移る・ダイアログが閉じる、で消える。
        履歴が無ければ何も出ない。
        """
        hist = list(getattr(self, '_find_history', None) or [])
        if not hist:
            return 'break'
        self._close_find_history()
        try:
            pop = tk.Toplevel(entry)
            pop.overrideredirect(True)
            pop.configure(bg=PANEL)
            self._find_hist_popup = pop
            n = min(len(hist), 8)
            lb = tk.Listbox(pop, height=n,
                            width=max(34, max(len(h) for h in hist)),
                            font=('Yu Gothic UI', 10), relief='flat', bd=1,
                            bg=PANEL, fg=INK, selectbackground=INK,
                            selectforeground=BG, activestyle='none',
                            exportselection=False)
            for h in hist:
                lb.insert('end', h)
            lb.pack(fill='both', expand=True)
            lb.selection_set(0)
            lb.activate(0)

            def _pick(_e=None):
                try:
                    sel = lb.curselection()
                    if sel:
                        self._find_query.set(lb.get(sel[0]))
                except Exception:
                    pass
                # **焦点を先に検索欄へ返してから閉じる**（項目48-SL）。焦点を
                # 持つ小窓を destroy すると Tk は「焦点の在る窓が無い」になり、
                # そのあとの focus_set は OS の焦点を動かさない（写しで実測）
                try:
                    entry.focus_set()
                except Exception:
                    pass
                self._close_find_history()
                try:
                    entry.icursor('end')
                    entry.select_range(0, 'end')
                except Exception:
                    pass
                return 'break'

            def _cancel(_e=None):
                try:
                    entry.focus_set()       # 先に返す（項目48-SL・上と同じ）
                except Exception:
                    pass
                self._close_find_history()
                return 'break'

            self._find_hist_lb = lb
            self._find_hist_cancel = _cancel
            lb.bind('<Return>', _pick)
            lb.bind('<Double-Button-1>', _pick)
            lb.bind('<Escape>', _cancel)
            # `Up` は IME の取り違えの対象のキー名（項目48-IN）——
            # 受け皿（`_ime_fkey_insert`）を先に呼ぶ method に束縛する
            lb.bind('<Up>', self._on_find_history_up)
            lb.bind('<FocusOut>', lambda e: self._close_find_history())
            pop.update_idletasks()
            x = entry.winfo_rootx()
            y = entry.winfo_rooty() + entry.winfo_height()
            pop.geometry(f'+{x}+{y}')
            lb.focus_set()
        except Exception:
            self._close_find_history()
        return 'break'

    def _on_find_history_up(self, event=None):
        """履歴一覧のいちばん上で上キーなら、欄へ戻す（項目48-SG）。
        IME が確定した文字なら受け皿が先（項目48-IN）。"""
        got = self._ime_fkey_insert(event) if event is not None else None
        if got is not None:
            return got
        lb = getattr(self, '_find_hist_lb', None)
        cancel = getattr(self, '_find_hist_cancel', None)
        try:
            sel = lb.curselection() if lb is not None else ()
            if sel and sel[0] == 0 and cancel is not None:
                return cancel()
        except Exception:
            pass
        return None

    def _close_find_history(self):
        pop = getattr(self, '_find_hist_popup', None)
        self._find_hist_popup = None
        if pop is not None:
            try:
                pop.destroy()
            except Exception:
                pass

    def _find_follow_tab(self):
        """
        **検索ウインドウを開いたままタブを移っても、焦点は検索ウインドウに残す**
        （項目48-SL・2026-09-06・うにさんの報告「検索ウインドウを開いたまま
        タブ移動した場合、タブウインドウをフォーカスする〔＝本体に焦点が
        移ってしまう〕。札のクリック／Ctrl+Tab／Ctrl+PageDown どれでもなる。
        検索ウインドウが非アクティブ表示になっていて、入力欄がアクティブ」）。

        開いている検索ウインドウは「次のタブでも同じ語を探す」途中なので、
        タブを移ったあとも Enter で続けられなければならない。本体へ焦点を
        戻していたのは `_load_active_tab` の末尾の `editor.focus_set()`
        （タブを移る道は全部ここを通る——札のクリック・Ctrl+Tab・
        Ctrl+PageDown・閉じる・新規）。検索ウインドウが開いているときは
        メモ欄に置かず、検索欄へ返す。札のクリックでは OS が先に本体を
        活性にするので、`focus_force` で検索ウインドウを取り直す
        （アプリが焦点を持たないときは奪わない）。

        あわせて、移った先での次の検索は**新しい検索**（先頭から探す・
        項目48-SG'——タブを移るとカーソルは控えた位置〔たいてい末尾〕に
        戻るので、そのままでは「これ以上見つかりません」になる）にし、
        履歴の一覧が開いていれば閉じる。

        戻り値: 検索ウインドウが開いていて焦点をそちらに置いたら True
        （呼ぶ側はメモ欄へ焦点を置かない）。
        """
        dlg = getattr(self, '_find_dialog', None)
        if dlg is None:
            return False
        # 「アプリが焦点を持っているか」は**履歴の一覧を閉じる前**に見る。
        # 一覧（焦点を持つ小窓）を destroy すると Tk は「焦点の在る窓が
        # 無い」になり、そのあとの focus_set は OS の焦点を動かさない
        # （写しで実測・focus_displayof が None のまま）
        try:
            has_focus = self.root.focus_displayof() is not None
        except Exception:
            has_focus = False
        self._close_find_history()
        self._find_fresh = True
        entry = getattr(self, '_find_entry', None)
        if entry is None:
            return True
        try:
            if has_focus:
                entry.focus_force()     # 本体が活性でも小窓を閉じた後でも取り直す
            else:
                entry.focus_set()
        except Exception:
            pass
        return True

    def _close_find_dialog(self):
        self._clear_find_marks()
        self._close_find_history()
        dlg = getattr(self, '_find_dialog', None)
        if dlg is not None:
            try:
                dlg.destroy()
            except Exception:
                pass
        self._find_dialog = None

    def _save_find_option(self, key, var):
        """
        検索オプションのチェックボックスが変わるたびに保存する。

        次に同じ検索を続けるときはもちろん、アプリを開き直した
        あとも同じ条件で検索したいという要望のため（実機から報告）。
        """
        try:
            self.settings.set(key, bool(var.get()))
            self.settings.save()
        except Exception:
            pass

    def _clear_find_marks(self):
        try:
            self.editor.tag_remove('found', '1.0', 'end')
            self.editor.tag_remove('found_current', '1.0', 'end')
        except Exception:
            pass

    def _current_pattern(self):
        """
        画面の設定から検索の条件を作る。

        誤りがあればダイアログに理由を出して None を返す
        （正規表現の書き間違いはよくあるので、黙って何もしないと困る）。
        """
        try:
            _q = self._find_query.get()
            # **検索した文字列を覚える**（項目48-SG。次を検索・前を検索・
            # 置換・F3 の全部がここを通るので、決めているのはここ1か所）
            self._remember_find_text(_q)
            return searchlib.build_pattern(
                _q,
                regex=self._find_regex.get(),
                match_case=self._find_match_case.get(),
                whole_word=self._find_whole_word.get())
        except searchlib.SearchError as e:
            self._find_status.config(text=str(e).replace('\n', ' '),
                                     fg='#c4564a')
            return None

    def _highlight_all(self, pattern):
        """一致する箇所すべてに薄い目印を付ける。"""
        self._clear_find_marks()
        text = self._editor_text()
        spans = searchlib.find_all(text, pattern)
        for start, end in spans[:500]:      # 多すぎるときは打ち切る
            self.editor.tag_add('found', self._offset_to_index(start),
                                self._offset_to_index(end))
        return spans

    def _do_find(self, backwards=False):
        pattern = self._current_pattern()
        if pattern is None:
            return 'break'
        text = self._editor_text()
        spans = self._highlight_all(pattern)
        if not spans:
            self._find_status.config(text='見つかりませんでした', fg=MUTED)
            return 'break'

        # 探し始める位置は、いまの選択（または カーソル）から
        try:
            if self.editor.tag_ranges('sel'):
                start = (self._index_to_offset('sel.first') if backwards
                         else self._index_to_offset('sel.last'))
            else:
                start = self._index_to_offset('insert')
        except Exception:
            start = 0

        hit = searchlib.find_next(text, pattern, start,
                                  backwards=backwards,
                                  wrap=self._find_wrap.get())
        _from_top = False
        if hit is None and getattr(self, '_find_fresh', False):
            # **新しい検索は先頭（後ろ向きなら末尾）から**（項目48-SG'）
            hit = searchlib.find_next(
                text, pattern, (len(text) if backwards else 0),
                backwards=backwards, wrap=False)
            _from_top = hit is not None
        if hit is None:
            self._find_status.config(
                text='これ以上見つかりませんでした', fg=MUTED)
            return 'break'

        self._find_fresh = False
        self._select_span(hit)
        idx = spans.index(hit) + 1 if hit in spans else 0
        self._find_status.config(
            text=f'{idx} / {len(spans)} 件目'
                 + ('（先頭から探しました）' if _from_top and not backwards
                    else '（末尾から探しました）' if _from_top else ''),
            fg=MUTED)
        return 'break'

    def _select_span(self, span):
        """
        一致した範囲を選択して、見える位置まで送る。

        ここで焦点をメモ欄へ移すと、検索欄で Enter を押すたびに
        フォーカスがメモ欄へ移ってしまう。次に検索欄で Enter を
        押したとき、実際に文字が入るのはメモ欄側になり、
        選択中の一致がその文字（何も打っていなければ空文字＝削除）で
        上書きされてしまう（実機で報告された不具合）。
        検索を続けられるよう、焦点は呼び出し元（検索欄）に残す。
        """
        start, end = span
        i1, i2 = self._offset_to_index(start), self._offset_to_index(end)
        self.editor.tag_remove('sel', '1.0', 'end')
        self.editor.tag_add('sel', i1, i2)
        self.editor.tag_remove('found_current', '1.0', 'end')
        self.editor.tag_add('found_current', i1, i2)
        self.editor.mark_set('insert', i2)
        self.editor.see(i1)

    def _do_replace(self):
        """
        いま選択されている一致を置き換えて、次を探す。

        選択が一致していない場合は、まず次を検索するだけにする
        （メモ帳と同じ振る舞い。いきなり別の場所を書き換えない）。
        """
        pattern = self._current_pattern()
        if pattern is None:
            return 'break'
        text = self._editor_text()

        sel_span = None
        try:
            if self.editor.tag_ranges('sel'):
                s = self._index_to_offset('sel.first')
                e = self._index_to_offset('sel.last')
                m = pattern.match(text, s, e)
                if m is not None and m.end() == e:
                    sel_span = (s, e)
        except Exception:
            sel_span = None

        if sel_span is None:
            return self._do_find(False)

        try:
            new_text, after = searchlib.replace_one(
                text, pattern, sel_span, self._find_replacement.get(),
                regex=self._find_regex.get())
        except searchlib.SearchError as e:
            self._find_status.config(text=str(e).replace('\n', ' '),
                                     fg='#c4564a')
            return 'break'

        self._replace_editor_text(new_text, cursor_offset=after)
        self._find_status.config(text='1 件置換しました', fg=MUTED)
        self._do_find(False)
        return 'break'

    def _do_replace_all(self):
        pattern = self._current_pattern()
        if pattern is None:
            return 'break'
        text = self._editor_text()
        try:
            new_text, n = searchlib.replace_all(
                text, pattern, self._find_replacement.get(),
                regex=self._find_regex.get())
        except searchlib.SearchError as e:
            self._find_status.config(text=str(e).replace('\n', ' '),
                                     fg='#c4564a')
            return 'break'

        if n == 0:
            self._find_status.config(text='見つかりませんでした', fg=MUTED)
            return 'break'

        self._replace_editor_text(new_text)
        self._find_status.config(text=f'{n} 件置換しました', fg=MUTED)
        return 'break'

    def _replace_editor_text(self, new_text, cursor_offset=None):
        """
        本文を差し替える。

        置換は1回の操作としてまとめて取り消せるようにする
        （edit_separator で Undo の区切りを入れる）。
        """
        try:
            self.editor.edit_separator()
        except Exception:
            pass
        top = self.editor.yview()[0]
        # 本文をまるごと入れ替えるので、自動反映の控えは捨てる
        # （行との対応が付かなくなるため）。
        self._autofix_reset()
        self.editor.delete('1.0', 'end')
        self.editor.insert('1.0', new_text)
        # 入れ替えた本文は「打った文字」ではない（項目48-X）
        self._reset_typed_marks()
        self._pad_blank_lines()
        try:
            self.editor.edit_separator()
        except Exception:
            pass
        if cursor_offset is not None:
            try:
                self.editor.mark_set('insert',
                                     self._offset_to_index(cursor_offset))
            except Exception:
                pass
        self.editor.yview_moveto(top)
        self._mark_dirty()
        self._analyze()

    def _find_next_shortcut(self, backwards=False):
        """
        F3 で次を検索。

        ダイアログを開いていなくても、前回の検索語があれば
        それで探す（メモ帳と同じ）。無ければダイアログを開く。
        """
        if getattr(self, '_find_dialog', None) is None:
            if not getattr(self, '_find_query', None) \
                    or not self._find_query.get():
                self.open_find_dialog(False)
                return 'break'
            # ダイアログを閉じたあとでも、条件を覚えているので探せる
            pattern = self._current_pattern()
            if pattern is None:
                return 'break'
            text = self._editor_text()
            try:
                start = self._index_to_offset('insert')
            except Exception:
                start = 0
            hit = searchlib.find_next(text, pattern, start,
                                      backwards=backwards,
                                      wrap=self._find_wrap.get())
            if hit is None:
                self.status.config(text='見つかりませんでした')
            else:
                self._select_span(hit)
                # ダイアログは既に閉じているので、
                # ここでは焦点をメモ欄へ戻してよい
                # （検索欄でのEnter連打とは違い、奪う相手がいない）。
                try:
                    self.editor.focus_set()
                except Exception:
                    pass
            return 'break'
        return self._do_find(backwards)

    # ------------------------------------------------------------
    # ダークモード
    # ------------------------------------------------------------
    # 配色は module レベルの定数（BG, INK 等）で持っている。
    # 切り替え時にこれらの値を入れ替えると、以後 新しく開く
    # ダイアログ（語彙を追加・検索 等）はその時点の値を参照して
    # 作られるので、何もしなくても自動的に新しい配色になる。
    # 既に画面に出ている持続的な部品（メモ欄・補正欄・メニュー等）だけ、
    # ここで明示的に配色をやり直す。

    # ------------------------------------------------------------
    # グローバルホットキーの有効/無効
    # ------------------------------------------------------------
    # 有効かどうかは2つの条件の重ね合わせで決まる。
    #
    #   1. 設定（settings.json に残る。メニューのチェック）
    #   2. 一時解除（この起動の間だけ。簡易入力ウィンドウのボタン）
    #
    # 2 を設定ファイルに書かないのが要点。Ctrl+Insert は Windows の
    # 「コピー」と同じ組み合わせなので、他のアプリでコピーが効かなくて
    # 困った人がその場で切れる逃げ道が要る。ただしそれは
    # 「今この瞬間の困りごと」への対処であって、次回もオフにしたい
    # という意思表示とは限らない。アプリを開き直せば元に戻す。

    def _hotkey_active(self, name):
        """このホットキーを今 登録すべきか。"""
        return name in effective_hotkeys(self.settings,
                                         self._hotkey_suspended)

    def _apply_hotkey_state(self, name=None):
        """設定と一時解除の状態を、実際の登録に反映する。"""
        names = [name] if name else list(HOTKEY_LABELS)
        for n in names:
            try:
                self.hotkeys.set_enabled(n, self._hotkey_active(n))
            except Exception:
                pass

    def _on_toggle_hotkey(self, name, var):
        """表示メニューのチェックでホットキーのオン/オフを切り替える。"""
        enabled = var.get()
        self.settings.set(f'hotkey_{name}_enabled', enabled)
        self.settings.save()
        if enabled:
            # メニューから明示的に入れ直したなら、
            # 一時解除も一緒に取り消す（そうしないと
            # チェックを入れても効かない、という状態になる）
            self._hotkey_suspended.discard(name)
        self._apply_hotkey_state(name)

    # Ctrl+Insert / Ctrl+Shift+- として扱うキー名。
    # 名前は環境（Tk のビルド・キーボードの配列）で変わるので、
    # 並びの束縛（<Control-Insert> など）に頼らず、
    # 押されたキーの名前を自分で照らし合わせる。
    _HOTKEY_KEYSYMS = {
        'insert': ('Insert', 'KP_Insert', 'KP_0'),
        # JIS 配列では Shift+「-」は「=」なので equal も見る
        'minus': ('minus', 'underscore', 'equal', 'KP_Subtract'),
    }

    def _maybe_hotkey_notice_from_key(self, event=None):
        """
        すべての打鍵を見て、簡易入力のホットキーだったら受け皿へ回す。

        <Control-Insert> のような並びの束縛は、キー名が環境で違うと
        当たらないうえ、'all' タグは最後に評価されるので手前の束縛が
        'break' を返すと届かない。ここでは KeyPress そのものを受け、
        修飾キーの状態とキー名から自分で判断する（実機で
        「メッセージが出ない」と報告・2026-08-09）。
        """
        if event is None:
            return None
        state = getattr(event, 'state', 0)
        if not isinstance(state, int) or not (state & 0x0004):
            return None                      # Control が押されていない
        keysym = getattr(event, 'keysym', '') or ''
        for name, names in self._HOTKEY_KEYSYMS.items():
            if keysym in names:
                return self._on_quick_hotkey_fallback(name)
        return None

    def _on_quick_hotkey_fallback(self, name):
        """
        アプリの中で Ctrl+Insert / Ctrl+Shift+- が押されたときの受け皿。

        ホットキーは RegisterHotKey で OS に予約する方式で、
        登録できているあいだは打鍵が OS に横取りされ、
        アプリのキー束縛までは届かない。
        **ここへ来たということは、登録できていない**ということ。

        そこで理由を切り分けて伝える（うにさんの指定・2026-08-09）:
          - メニューでオフにしている → 説明欄に一時的に出すだけ
            （自分で切ったものなので、ダイアログで邪魔をしない）
          - オンのはずなのに登録が外れている → ダイアログで知らせる

        なお 'break' は返さない。Ctrl+Insert は Windows 標準の
        コピーでもあるので、オフにしているときは本来の働き
        （コピー）をそのまま通す。
        """
        # メモ欄への直接の束縛と bind_all の両方に届くので、
        # 1回の打鍵で二度呼ばれる。ダイアログが2枚出ないよう、
        # ごく短い間の重複は捨てる。
        import time as _time
        now = _time.monotonic()
        last = getattr(self, '_hotkey_notice_at', None)
        if last is not None and last[0] == name and now - last[1] < 0.5:
            return None
        self._hotkey_notice_at = (name, now)

        label = HOTKEY_LABELS.get(name, name)
        try:
            enabled = bool(self.settings.get(f'hotkey_{name}_enabled'))
        except Exception:
            enabled = True
        if not enabled:
            msg = (f'簡易入力のショートカットキー（{label}）は'
                   'メニューでオフになっています')
            self._flash_editor_header(msg)
            # 見出しは、スクロール位置によっては隠れていることがある。
            # 下の状態表示にも出して、必ずどこかで見えるようにする。
            try:
                self.status.config(text=msg)
            except Exception:
                pass
            return None

        # オンのはずなのに届いてしまった＝登録が外れている
        try:
            st = self.hotkeys.status()
            registered = name in (st.get('registered') or set())
        except Exception:
            registered = False
        if registered:
            # 登録できているのにここへ来ることは通常ない。
            # 念のため、本来の働き（簡易入力を開く）を行う。
            self._open_quick_capture(name)
            return 'break'
        messagebox.showwarning(
            APP_TITLE,
            f'ショートカットキー（{label}）の登録が外れています。\n'
            'アプリを起動しなおしてください。')
        return None

    def _flash_editor_header(self, message, seconds=6):
        """
        メモ欄の上の説明欄に、一時的なお知らせを出す。

        ダイアログを出すほどでもないが、状態を伝えたい場面で使う。
        一定時間で元の説明文に戻る。
        """
        label = getattr(self, 'editor_header', None)
        if label is None:
            return
        seq = getattr(self, '_header_flash_seq', 0) + 1
        self._header_flash_seq = seq
        self._header_flash = seq
        try:
            label.config(text=message, fg=ACCENT)
        except Exception:
            self._header_flash = None
            return

        def _restore():
            if getattr(self, '_header_flash', None) != seq:
                return
            self._header_flash = None
            try:
                label.config(
                    text=(self.UNIFIED_HEADER_TEXT
                          if self._layout_is_unified()
                          else self.EDITOR_HEADER_TEXT), fg=MUTED)
            except Exception:
                pass
            try:
                self._update_header_visibility(self.editor.yview()[0])
            except Exception:
                pass

        try:
            self.root.after(int(seconds * 1000), _restore)
        except Exception:
            pass

    def _on_toggle_quick_hint(self):
        """簡易入力ウィンドウの説明文を出すかどうかを切り替える。"""
        self.settings.set('show_quick_hint', self.quick_hint_var.get())
        self.settings.save()
        # 今まさに開いている窓にも即座に反映する
        self._refresh_quick_hint()

    def _suspend_hotkey(self, name):
        """
        このホットキーを、アプリを閉じるまでの間だけ解除する。

        設定は書き換えない。メニューのチェックだけ外して、
        今 効いていないことが見て分かるようにする
        （チェックを入れ直せば一時解除も解ける）。
        """
        self._hotkey_suspended.add(name)
        self._apply_hotkey_state(name)
        var = getattr(self, f'hotkey_{name}_var', None)
        if var is not None:
            try:
                # 変数を書き換えるだけでは command は呼ばれないので、
                # 設定ファイルには影響しない
                var.set(False)
            except Exception:
                pass
        label = HOTKEY_LABELS.get(name, name)
        self.status.config(
            text=f'{label} での呼び出しを解除しました'
                 f'（アプリを開き直すと元に戻ります）')
        self._refresh_quick_hint()

    def show_hotkey_status(self):
        """
        グローバルホットキーが実際に登録できているかを見せる。

        「押しても簡易入力が出ない」という報告のとき、原因が
          (a) 登録自体に失敗している（他のアプリが先に使っている等）
          (b) 登録はできているがキーが届いていない
        のどちらなのかを、この画面だけで切り分けられるようにする。
        """
        try:
            st = self.hotkeys.status()
        except Exception as e:
            messagebox.showerror('ホットキーの状態', f'取得に失敗しました:\n{e}')
            return

        lines = []
        lines.append(f'この環境で使えるか: '
                     f'{"はい" if st["supported"] else "いいえ"}')
        lines.append(f'待ち受けスレッド: '
                     f'{"動作中" if st["running"] else "停止"}')
        lines.append('')
        for name, label in HOTKEY_LABELS.items():
            on = st['enabled'].get(name)
            registered = name in st['registered']
            errs = st['errors'].get(name)
            if not on:
                state = '設定でオフ'
                if name in self._hotkey_suspended:
                    state = '一時解除中（アプリを開き直すと戻ります）'
            elif registered:
                state = 'OS に登録できています'
            elif errs is None:
                state = 'OS に登録できています'
            elif errs:
                state = '登録に失敗しました'
                if 1409 in errs:
                    state += '（他のアプリが既に同じキーを使っています）'
                else:
                    state += f'（Win32エラー {errs}）'
            else:
                # エラー番号が1つも無い＝登録処理そのものを通っていない。
                # 設定がスレッドに伝わっていないときにこうなる。
                state = ('まだ登録を試みていません'
                         '（設定がホットキー側に伝わっていません）')
            lines.append(f'{label}: {state}')

        lines.append('')
        lines.append('「登録できています」と出ているのに反応しない場合は、')
        lines.append('管理者権限で動いている別のアプリが前面にあると、')
        lines.append('そちらにキーが吸われることがあります。')
        lines.append('編集メニューの「簡易入力ウィンドウを開く」で、')
        lines.append('窓そのものが正しく開くかを確かめられます。')

        messagebox.showinfo('ホットキーの状態', '\n'.join(lines))

    def _on_hotkey_triggered(self, name):
        """
        グローバルホットキーが押された（**別スレッドから呼ばれる**）。

        ここで tkinter に触ってはいけない。**root.after も tkinter
        （Tcl）の呼び出しなので、別スレッドから呼ぶのは危ない**。
        以前はここで after を呼んでいたが、Tcl は呼ぶスレッドを
        選ぶ作りで、運が悪いと状態を壊す（2026-08-10 の
        Fatal Python error と同じ「スレッドから Python/Tcl を
        触る」型の問題。あちらは ctypes の GIL だったが、根は同じ）。

        代わりに、**受け取ったことだけを箱に入れて戻る**。
        箱の出し入れは queue が面倒を見てくれる（スレッド安全）。
        実際に窓を開くのは、主スレッドで回している見張り
        （_poll_hotkey_queue）。
        """
        try:
            self._hotkey_queue.put_nowait(name)
        except Exception:
            pass

    # ホットキーの受け取りを見に行く間隔（ミリ秒）。
    # 押してから窓が出るまでの待ちになるので、短めにする。
    HOTKEY_POLL_MS = 40

    def _poll_hotkey_queue(self):
        """
        ホットキーの箱を主スレッドから覗きに行く。

        入っていれば簡易入力ウィンドウを開く。空なら何もしない。
        """
        try:
            while True:
                name = self._hotkey_queue.get_nowait()
                try:
                    self._open_quick_capture(name)
                except Exception:
                    pass
        except Exception:
            pass    # 箱が空（queue.Empty）。次の見回りへ
        try:
            self.root.after(self.HOTKEY_POLL_MS, self._poll_hotkey_queue)
        except Exception:
            pass

    def _apply_border_color(self, hwnd=None):
        """
        ウィンドウの枠（Windows のアクセントカラーの線）の色を、
        テーマの背景色に固定する。

        既定では枠はアクティブ時にアクセント色・非アクティブ時に
        灰色で描かれるため、F2 の候補一覧の開閉（フォーカスの
        出入り）のたびに色が切り替わって点滅して見える
        （実機で報告・2026-08-09）。固定色にすれば点滅しない。
        """
        if sys.platform != 'win32':
            return
        try:
            import ctypes
            if hwnd is None:
                self.root.update_idletasks()
                hwnd = ctypes.windll.user32.GetParent(
                    self.root.winfo_id())
            dark = bool(self.settings.get('dark_mode'))
            rgb = 0x1e2124 if dark else 0xf6f4ee   # BG と同じ色
            colorref = (((rgb & 0xFF) << 16) | (rgb & 0xFF00)
                        | (rgb >> 16))
            v = ctypes.c_uint32(colorref)
            DWMWA_BORDER_COLOR = 34
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, DWMWA_BORDER_COLOR, ctypes.byref(v), 4)
        except Exception:
            pass

    def _minimize_window(self):
        try:
            self.root.state('iconic')
        except Exception:
            try:
                self.root.iconify()
            except Exception:
                pass

    def _toggle_maximized(self):
        try:
            if self.root.state() == 'zoomed':
                self.root.state('normal')
            else:
                self.root.state('zoomed')
                # タスクバーを隠さない（下の説明）。
                self._clamp_zoom_to_workarea()
        except Exception:
            pass

    def _clamp_zoom_to_workarea(self):
        """
        **最大化がタスクバーを隠さないようにする**（うにさんの報告・
        2026-08-27「最大化した時に、タスクバーを隠してしまっている。
        タスクバーがある場合は隠さない」）。

        タイトルバー（WS_CAPTION）を消した窓（`_apply_titlebar_
        visibility`）は、Windows が「枠なし全画面」と同じ扱いで
        **モニタ全体**に広げるため、最大化するとタスクバーまで
        覆っていた。枠のある窓なら OS が作業領域（タスクバーを
        除いた範囲）に収めてくれるので、何もしない。

        最大化した**あと**に、その窓が載っているモニタの作業領域
        （`rcWork`）へ収め直す。OS 側の「最大化中」の状態はそのまま
        なので、`state() == 'zoomed'` を見ている道
        （帯のクリック・ドラッグ・▢ の切り替え）は全部今までどおり。

        **何度呼んでもよい形にしてある**（項目48-MA）。もともとは
        「最大化していない → している」に変わった1回だけ掛けていたが、
        **最小化して戻すとその変わり目が来ない**——最小化の間は
        `<Configure>` が届かないので控えが `zoomed` のままになり、
        戻ったときに「変わっていない」と見えて掛からなかった。
        うにさんの報告（2026-08-30）:

        > 「ドラッグで上の端に付けて最大化した後、タスクバーの
        >   アプリをクリックして最小化して、**再度クリックすると
        >   最大化された際にタスクバーが隠れます**」

        変わり目を数える代わりに、**いまの外形が目当てと同じなら
        すぐ帰る**。掛ける口を増やしても値段が付かない
        （学び22——口が1つだけだと、そこを通らない道が必ず残る）。
        """
        if sys.platform != 'win32':
            return
        try:
            if self.root.state() != 'zoomed':
                return      # 最小化中は窓の外形が読めない（-32000）
        except Exception:
            return
        try:
            import ctypes
            from ctypes import wintypes
            u32 = ctypes.windll.user32
            self.root.update_idletasks()
            hwnd = (u32.GetParent(self.root.winfo_id())
                    or self.root.winfo_id())
            GWL_STYLE = -16
            WS_CAPTION = 0x00C00000
            if u32.GetWindowLongW(hwnd, GWL_STYLE) & WS_CAPTION:
                return      # 枠があるなら OS が作業領域に収める
            MONITOR_DEFAULTTONEAREST = 2
            mon = u32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)

            class _MONITORINFO(ctypes.Structure):
                _fields_ = [('cbSize', wintypes.DWORD),
                            ('rcMonitor', wintypes.RECT),
                            ('rcWork', wintypes.RECT),
                            ('dwFlags', wintypes.DWORD)]

            mi = _MONITORINFO()
            mi.cbSize = ctypes.sizeof(_MONITORINFO)
            if not u32.GetMonitorInfoW(mon, ctypes.byref(mi)):
                return
            work = mi.rcWork
            full = mi.rcMonitor
            if (work.left == full.left and work.top == full.top
                    and work.right == full.right
                    and work.bottom == full.bottom):
                return      # タスクバーが自動で隠れる設定。触らない
            # **見えないリサイズ枠のぶんだけ外へ広げる**（うにさんの
            # 報告・2026-08-27「タスクバーとの間にわずかな空間」
            # 「左右にも隙間」）。窓の外形を作業領域に合わせると、
            # 枠（WS_THICKFRAME。見えないが太さがある）のぶん中身が
            # 内側に寄る。いまの窓で枠の太さを実測し、**中身が作業領域に
            # ぴったり**になる位置へ置く。
            wr = wintypes.RECT()
            u32.GetWindowRect(hwnd, ctypes.byref(wr))
            cr = wintypes.RECT()
            u32.GetClientRect(hwnd, ctypes.byref(cr))
            pt = wintypes.POINT(0, 0)
            u32.ClientToScreen(hwnd, ctypes.byref(pt))
            ins_l = max(0, pt.x - wr.left)
            ins_t = max(0, pt.y - wr.top)
            ins_r = max(0, wr.right - (pt.x + cr.right))
            ins_b = max(0, wr.bottom - (pt.y + cr.bottom))
            x = work.left - ins_l
            y = work.top - ins_t
            cx = (work.right - work.left) + ins_l + ins_r
            cy = (work.bottom - work.top) + ins_t + ins_b
            if (wr.left, wr.top, wr.right - wr.left,
                    wr.bottom - wr.top) == (x, y, cx, cy):
                return      # もう収まっている（**何度呼んでも安い**）
            SWP_NOZORDER = 0x0004
            SWP_NOACTIVATE = 0x0010
            SWP_FRAMECHANGED = 0x0020
            u32.SetWindowPos(hwnd, 0, x, y, cx, cy,
                             SWP_NOZORDER | SWP_NOACTIVATE
                             | SWP_FRAMECHANGED)
        except Exception:
            pass

    def _start_window_drag(self, event=None):
        """
        メニューの帯の空き部分のドラッグで窓を動かす（隠しているとき）。

        Windows では OS の移動に任せる（_os_window_move）。
        Tk の geometry() で動かすと、位置の更新と中身の描き直しが
        別々に走るため、ドラッグ中に文字が震えて見える
        （実機で報告・2026-08-09）。OS に任せれば窓全体が
        1枚の絵として動くので震えない。

        以前この経路で**アプリごと落ちていた**のは、
        SendMessage（返ってこないモーダルな呼び出し）で頼んで
        いたため。ctypes が GIL を手放したまま移動ループへ入り、
        その中から Tk が Python を呼び戻して致命エラーになっていた。
        PostMessage に変えて解決した（詳しくは _os_window_move）。

        Windows 以外（開発環境の Linux 等）では従来どおり
        Tk の中だけで座標を動かす。
        """
        self._win_drag = None
        if not self.settings.get('hide_titlebar'):
            return
        if event is None:
            return
        # **クリックだけでは最大化を解除しない**（項目48-EE・
        # 2026-08-16）。うにさんの指定:
        #
        # > もしこの対応が難しければ、クリックだけでは最大化が
        # > 解除されないようにする。つまり、**ドラッグ操作した時だけ**
        # > 最大化を解除する。
        #
        # ここで解除していたので、帯の隙間を1回クリックしただけで
        # 最大化が外れていた。最大化中は**押した場所を控えるだけ**に
        # して、実際に指が動いてから（`_on_window_drag`）解除する。
        # 最大化していないときの動きは今までどおり。
        try:
            _zoomed = (self.root.state() == 'zoomed')
        except Exception:
            _zoomed = False
        if _zoomed:
            self._win_press = (event.x_root, event.y_root)
            return
        self._win_press = None
        # 最大化しているときは、まず最大化を解除してから動かす
        # （Windows のタイトルバーと同じ振る舞い。実機からの指摘・
        #  2026-08-10「最大化しているウインドウを、メニュー部分
        #  ドラッグで最大化解除できませんでした」）。
        if self._restore_before_drag(event):
            if self._os_window_move():
                return 'break'
        elif self._os_window_move():
            return 'break'
        try:
            self._win_drag = (event.x_root - self.root.winfo_x(),
                              event.y_root - self.root.winfo_y())
        except Exception:
            self._win_drag = None

    def _restore_before_drag(self, event):
        """
        最大化中にドラッグが始まったら、最大化を解除して
        **掴んだ場所がマウスの下に来るように**置き直す。

        Windows のタイトルバーを最大化状態でドラッグすると、
        窓が元の大きさに戻り、そのまま掴んだ位置を保ったまま
        付いてくる。同じ手触りにする。掴んだ位置は
        「窓の横幅に対する割合」で覚え、戻した後の横幅に
        当てはめ直す（左端で掴んだら左端のまま）。

        戻り値: 最大化を解除したら True。
        """
        try:
            if self.root.state() != 'zoomed':
                return False
        except Exception:
            return False
        try:
            win_x = self.root.winfo_x()
            win_w = max(1, self.root.winfo_width())
            ratio = min(1.0, max(0.0, (event.x_root - win_x) / win_w))
            self.root.state('normal')
            self.root.update_idletasks()
            new_w = max(1, self.root.winfo_width())
            new_h = max(1, self.root.winfo_height())
            x = int(event.x_root - ratio * new_w)
            y = int(event.y_root - max(0, event.y_root
                                       - self.root.winfo_y()))
            # 画面の外に飛ばさない
            try:
                area = monitor_work_area(event.x_root, event.y_root)
            except Exception:
                area = None
            if area:
                left, top, right, bottom = area
                x = min(max(x, left - new_w // 2), right - new_w // 2)
                y = min(max(y, top), bottom - 40)
            self.root.geometry(f'+{x}+{y}')
            self.root.update_idletasks()
        except Exception:
            return True     # 解除自体はできたかもしれないので True
        return True

    def _os_window_move(self):
        """
        OS のウィンドウ移動に任せて窓を動かす（Windows のみ）。

        **SendMessage で呼んではいけない**（2026-08-10・実機の
        Fatal Python error でようやく正体が分かった）。

            Fatal Python error: PyEval_RestoreThread: the function
            must be called with the GIL held, but the GIL is released

        理由:
        ctypes は、時間の掛かる呼び出しの間 **GIL を手放す**。
        SendMessage は移動が終わるまで返ってこない（モーダル）ので、
        その長い間ずっと GIL を手放したままになる。ところが移動
        ループの中では Windows がメッセージを配り続けるため、
        **Tk が Python のコールバック（after で予約した解析など）を
        呼び出してしまう**。GIL を手放し、スレッドの状態も外して
        あるところへ Python が再入する形になり、インタプリタが
        「これは続行できない」と判断して即座に落ちる。
        try/except では捕まえられない（例外ではなく致命エラー）。

        これは「解析が動いている間だけ危ない」のではなく、
        **after の予約が1つでもあれば起こりうる**。予約を止めて
        から入る・賑やかな間は入らない、という以前の対処では
        塞ぎきれなかったのはこのため。

        対処: **PostMessage で `WM_SYSCOMMAND` / `SC_MOVE` を
        投げる**。投げるだけなのですぐ戻り、GIL もスレッドの状態も
        正しいまま Tk へ帰れる。移動ループはそのあと **Tk 自身の
        メッセージ処理の中から**始まるので、コールバックが呼ばれても
        Python の状態は正常。窓は OS が動かすので、文字が震えることも
        ない（自前で geometry を動かすと震える）。

        戻り値: OS に任せられたら True。False なら呼び出し側が
        従来の Tk での移動にフォールバックする。
        """
        if sys.platform != 'win32':
            return False
        try:
            if self.root.state() == 'zoomed':
                return False   # 最大化中は動かさない
        except Exception:
            pass
        try:
            import ctypes
            u32 = ctypes.windll.user32
            hwnd = (u32.GetParent(self.root.winfo_id())
                    or self.root.winfo_id())
            if not hwnd:
                return False
            WM_SYSCOMMAND = 0x0112
            SC_MOVE = 0xF010
            HTCAPTION = 2
            # Tk が握っているマウスを放してからでないと、
            # OS 側の移動がマウスを追ってくれない。
            u32.ReleaseCapture()
            ok = u32.PostMessageW(hwnd, WM_SYSCOMMAND,
                                  SC_MOVE | HTCAPTION, 0)
            if ok:
                self._begin_native_window_drag()
            return bool(ok)
        except Exception:
            return False

    def _on_window_drag(self, event=None):
        """
        帯のドラッグで窓を動かす。

        マウスの動きは1秒に何十回も届く。届くたびに geometry() を
        呼ぶと、窓の位置だけが先に進み、中身の描き直しが追いつかない。
        すると前の位置の絵が残ったまま重なって、画面が壊れたように
        見える（実機で「グラフィックボードのエラーのような見た目」と
        報告・2026-08-09）。

        そこで、届いた座標は控えるだけにして、**実際に動かすのは
        手が空いたとき（after_idle）に1回だけ**にまとめる。
        移動中の描画はOS/Tkに任せ、強制再描画はボタンを放した後だけ行う。
        """
        # 最大化中に押したまま指が動いたら、ここで初めて解除する
        # （項目48-EE。押した瞬間には何もしていない）。
        press = getattr(self, '_win_press', None)
        if press is not None and event is not None:
            if (abs(event.x_root - press[0]) < _WIN_DRAG_SLOP
                    and abs(event.y_root - press[1]) < _WIN_DRAG_SLOP):
                return          # まだ「クリック」の範囲
            self._win_press = None
            if self._restore_before_drag(event):
                if self._os_window_move():
                    return 'break'
            elif self._os_window_move():
                return 'break'
            try:
                self._win_drag = (event.x_root - self.root.winfo_x(),
                                  event.y_root - self.root.winfo_y())
            except Exception:
                self._win_drag = None
            return

        wd = getattr(self, '_win_drag', None)
        if not wd or event is None:
            return
        self._win_drag_to = (event.x_root - wd[0], event.y_root - wd[1])
        if getattr(self, '_win_drag_pending', False):
            return
        self._win_drag_pending = True
        try:
            self.root.after_idle(self._apply_window_drag)
        except Exception:
            self._win_drag_pending = False

    def _apply_window_drag(self):
        self._win_drag_pending = False
        pos = getattr(self, '_win_drag_to', None)
        if pos is None or not getattr(self, '_win_drag', None):
            return
        try:
            if self.root.state() == 'zoomed':
                return   # 最大化中は動かさない
            # 48-VX: 位置更新のたびに全子ウインドウの再描画を強制しない。
            self.root.geometry(f'+{int(pos[0])}+{int(pos[1])}')
        except Exception:
            return

    def _redraw_window_now(self):
        """窓全体（子まで）を、いますぐ描き直させる。"""
        if sys.platform != 'win32':
            return
        try:
            import ctypes
            u32 = ctypes.windll.user32
            hwnd = u32.GetParent(self.root.winfo_id()) or self.root.winfo_id()
            RDW_INVALIDATE = 0x0001
            RDW_ALLCHILDREN = 0x0080
            RDW_UPDATENOW = 0x0100
            u32.RedrawWindow(hwnd, None, None,
                             RDW_INVALIDATE | RDW_ALLCHILDREN
                             | RDW_UPDATENOW)
        except Exception:
            pass

    def _end_window_drag(self, event=None):
        # 最後の座標がafter_idle待ちでも、ボタンを放した位置まで動かす。
        self._apply_window_drag()
        self._win_drag = None
        self._win_drag_to = None
        self._win_press = None
        self._note_view_change()
        # 動かし終わりに、もう一度きちんと描き直す
        try:
            self.root.update_idletasks()
        except Exception:
            pass
        self._redraw_window_now()

    def _apply_titlebar_visibility(self, hide=None):
        """
        OSのタイトルバー（WS_CAPTION）を隠す／戻す。

        最上部の水色の帯（Windows のアクセントカラーの枠）を
        「そもそも枠ごと消したい」といううにさんの指定（2026-08-09）。
        隠している間は、メニューの帯の右端に ─ ▢ ✕ を出し、
        帯の空き部分のドラッグで移動・ダブルクリックで最大化できる。
        """
        if hide is None:
            hide = bool(self.settings.get('hide_titlebar'))
        ctrl = getattr(self, '_win_controls', None)
        if ctrl is not None:
            try:
                if hide:
                    ctrl.pack(side='right')
                else:
                    ctrl.pack_forget()
            except Exception:
                pass
        if sys.platform != 'win32':
            return
        try:
            import ctypes
            self.root.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            u32 = ctypes.windll.user32
            GWL_STYLE = -16
            WS_CAPTION = 0x00C00000
            style = u32.GetWindowLongW(hwnd, GWL_STYLE)
            if hide:
                style &= ~WS_CAPTION
            else:
                style |= WS_CAPTION
            u32.SetWindowLongW(hwnd, GWL_STYLE, style)
            SWP_NOMOVE = 0x0002
            SWP_NOSIZE = 0x0001
            SWP_NOZORDER = 0x0004
            SWP_NOACTIVATE = 0x0010
            SWP_FRAMECHANGED = 0x0020
            u32.SetWindowPos(hwnd, 0, 0, 0, 0, 0,
                             SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER
                             | SWP_NOACTIVATE | SWP_FRAMECHANGED)
            # 枠の描き直しで色が既定に戻ることがあるので、
            # 固定色を掛け直す（ライトモードでもここで必ず通る）
            self._apply_border_color(hwnd)
        except Exception:
            pass

    def _on_toggle_hide_titlebar(self):
        v = bool(self.hide_titlebar_var.get())
        try:
            self.settings.set('hide_titlebar', v)
            self.settings.save()
        except Exception:
            pass
        self._apply_titlebar_visibility(v)

    def _apply_titlebar_theme(self, dark):
        """
        タイトルバー（最小化・最大化・閉じるボタンを含む、OSが描く枠）
        の色をダークモードに合わせる。

        tkinter 標準のウィジェットではこの部分は塗り替えられない
        （root.configure(bg=...) が効くのはクライアント領域だけ）。
        Windows 11 のメモ帳がタイトルバーまで黒くなるのに合わせたい
        という要望のため、Windows のテーマ属性 API を ctypes 経由で
        直接呼ぶ（hotkeys.py が RegisterHotKey を直接呼ぶのと同じ
        考え方）。Windows 以外では何もしない。
        """
        if sys.platform != 'win32':
            return
        try:
            import ctypes

            # ウィンドウがまだ画面に実体化（マップ）される前は、
            # winfo_id() から辿れる親子関係がまだ確定していないことが
            # あり、その状態で GetParent を呼ぶと違うウィンドウの
            # ハンドルを取ってしまう（起動直後にダークモードが
            # 反映されない・アプリ再起動で設定が戻って見える、
            # という不具合の原因になっていた）。
            # update_idletasks で実体化を確定させてから取得する。
            self.root.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())

            # DWMWA_USE_IMMERSIVE_DARK_MODE。
            # Windows 10 1809-19042 では 19、1903+ では 20。
            # 両方試して、どちらかが通ればよい。
            value = ctypes.c_int(1 if dark else 0)
            for attr in (20, 19):
                ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, attr, ctypes.byref(value), ctypes.sizeof(value))

            # ウィンドウの枠（アクセントカラーの線）の色を固定する
            # （_apply_border_color 参照。F2 の候補一覧の開閉で
            # アクティブ／非アクティブの色が切り替わって点滅して
            # 見えるため、どちらの状態でも同じ色にする）。
            self._apply_border_color(hwnd)

            # DWM属性を変えただけでは、OSがすぐには枠を再描画しない
            # ことがある（「表示メニューでオフ→オンにすると一部だけ
            # 黒くなる」という実機報告はこれが原因と見られる）。
            # 非クライアント領域の再計算を伴わない SetWindowPos で
            # 明示的に再描画を促す。SWP_FRAMECHANGED が肝で、
            # 位置・大きさそのものは変えない
            # （NOMOVE/NOSIZE/NOZORDER/NOACTIVATE を立てて無変更にする）。
            SWP_NOMOVE = 0x0002
            SWP_NOSIZE = 0x0001
            SWP_NOZORDER = 0x0004
            SWP_NOACTIVATE = 0x0010
            SWP_FRAMECHANGED = 0x0020
            ctypes.windll.user32.SetWindowPos(
                hwnd, 0, 0, 0, 0, 0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE
                | SWP_FRAMECHANGED)
        except Exception:
            pass    # 非対応の Windows バージョン等。失敗しても致命的ではない

    def _on_toggle_dark_mode(self):
        dark = self.dark_mode_var.get()
        self.settings.set('dark_mode', dark)
        self.settings.save()
        self._apply_theme(dark)

    def _apply_theme(self, dark, titlebar_immediate=True):
        if titlebar_immediate:
            self._apply_titlebar_theme(dark)

        pal = DARK_PALETTE if dark else LIGHT_PALETTE
        # **名簿（`_PALETTE_KEYS`）から回す**（項目48-IF・2026-08-21）。
        #
        # ここは以前、色の名前を左辺・右辺に**手で並べて**いた。
        # そこに列挙し忘れた色は、テーマを切り替えても**切り替え前の
        # 値のまま残る**——`UNSURE_BG` を足し忘れて、ダークモード
        # なのにライトのほぼ白い色で塗られ、白い文字が読めなくなる
        # 不具合を**実機で2度**起こしている。
        #
        # **3度目を踏んだ。** 空白の印の色（`WS_*`・6つ）を足したとき、
        # やはりここに足し忘れて、ダークモードでライトの色のまま
        # 出た（xvfb で撮って気付いた）。**同じ形の不具合が3度出たら、
        # 形のほうを直す。** 名簿は `_PALETTE_KEYS` ただ1つなので、
        # そこから回せば**足し忘れようがない**
        # （`bundle_manifest.py` を名簿1つにしたのと同じ考え・48-GS）。
        globals().update({k: pal[k] for k in _PALETTE_KEYS})

        # 既に画面にある部品は、いま設定されている色を古い配色の値と
        # 突き合わせて、対応する新しい値に置き換える。
        # こうしておけば、部品ごとに個別の書き換えコードを
        # 用意しなくても、色を持つ部品ならたいてい拾える。
        old_to_new = {}
        other = LIGHT_PALETTE if dark else DARK_PALETTE
        for key in _PALETTE_KEYS:
            old_to_new[other[key]] = pal[key]

        self._restyle_widget(self.root, old_to_new)
        try:
            self._menu_bar_frame.configure(bg=PANEL)
            for btn in getattr(self, '_menu_buttons', []):
                btn.configure(bg=PANEL, fg=INK,
                              activebackground=ACCENT,
                              activeforeground=PANEL)
        except Exception:
            pass
        for menu in getattr(self, '_menus', []):
            try:
                menu.configure(bg=PANEL, fg=INK,
                              activebackground=ACCENT,
                              activeforeground=PANEL,
                              # 押せない項目（バージョン表記・
                              # 「ホットキーは使えません」の案内）。
                              # 既定の灰色はダークモードの背景に
                              # 沈んで読めないので、こちらも指定する。
                              disabledforeground=MUTED)
            except Exception:
                pass
            # チェック項目の「オン」を示す色（selectcolor）は
            # configure() では拾えない。widget 自体の option ではなく
            # エントリごとの option のため、個別にやり直す必要がある。
            # ここを忘れると、チェックが入っているのに背景と
            # 同化して見えなくなる（ダークモードで報告された不具合）。
            try:
                last = menu.index('end')
            except Exception:
                last = None
            if last is not None:
                for i in range(last + 1):
                    try:
                        if menu.type(i) in ('checkbutton', 'radiobutton'):
                            menu.entryconfigure(i, selectcolor=ACCENT)
                    except Exception:
                        pass


        # タグの色は部品の option ではないので、個別に設定し直す
        self.editor.tag_configure('suspect', background=SUSPECT_BG)
        # **不自然な文字列**（項目48-IR で入れ、48-IZ で紫の意味を
        # これ一本にした）。
        # 色の定義そのものは常に置く（切り替えるのは**塗るかどうか**）。
        self.editor.tag_configure('odd', background=UNSURE_BG)
        self.editor.tag_configure('autofixed', foreground=FIXED_FG)
        self.editor.tag_configure('autochosen', foreground=ACCENT)
        self.editor.tag_configure('hover', background=HOVER_BG)
        self.editor.tag_configure('found', background=FOUND_BG)
        self.editor.tag_configure('found_current', background=FOUND_CUR_BG)
        # 簡易入力から送った文字の色（項目48-GN）。色が付いている
        # 最中にテーマを切り替えても、そのまま塗り直される。
        self.editor.tag_configure('quick_sent_a', background=QUICK_SENT_BG_A)
        self.editor.tag_configure('quick_sent_b', background=QUICK_SENT_BG_B)
        # 目に見えない空白の印（項目48-IF）。テーマを切り替えても
        # そのまま塗り直される。
        try:
            self._configure_whitespace_tags()
            self._configure_end_rule_tag()      # 終端の罫線（項目48-IM）
        except Exception:
            pass
        self.editor.config(selectbackground=EDITOR_SEL_BG,
                           selectforeground=INK)
        self.result_view.tag_configure('fixed', foreground=FIXED_FG)
        self.result_view.tag_configure('chosen', foreground=ACCENT)
        self.result_view.tag_configure('hover', background=HOVER_BG)
        # 簡易入力ウィンドウが開いていれば、そちらの色も塗り直す
        qt = getattr(self, '_quick_text', None)
        if qt is not None:
            try:
                qt.tag_configure('suspect', background=SUSPECT_BG)
                qt.tag_configure('hover', background=HOVER_BG)
                qt.tag_configure('sel', background=EDITOR_SEL_BG)
            except Exception:
                pass
        self.result_view.tag_configure('sel', background=RESULT_SEL_BG)
        self.editor.tag_raise('sel')
        self.result_view.tag_raise('sel')

        # ガター（行番号）は色定数を描画時に読むので、引き直せば反映される
        self.editor_gutter.configure(bg=LINE_NUM_BG)
        self.result_gutter.configure(bg=RESULT_GUTTER_BG)
        self.editor_gutter.redraw()
        self.result_gutter.redraw()

        # スクロールバーは ttk なので、bg/fg ではなく style で色を持つ
        try:
            style = ttk.Style()
            style.theme_use(style.theme_use())   # 現在のテーマのまま
            style.configure('Vertical.TScrollbar',
                            background=PANEL, troughcolor=BG,
                            bordercolor=RULE, arrowcolor=INK)
        except Exception:
            pass

        self._refresh_title()

    @staticmethod
    def _restyle_widget(widget, old_to_new):
        """
        widget とその子孫について、いま設定されている色が
        旧配色の値と一致するものを、対応する新しい値に差し替える。

        Frame/Label/Button/Text/Canvas など、色の option 名が
        部品ごとに違うので、よく使われる名前を一通り試す。
        """
        option_names = ('bg', 'fg', 'background', 'foreground',
                        'insertbackground', 'selectbackground',
                        'selectforeground', 'activebackground',
                        'activeforeground', 'highlightbackground',
                        'selectcolor')
        try:
            for opt in option_names:
                try:
                    cur = widget.cget(opt)
                except Exception:
                    continue
                new = old_to_new.get(cur)
                if new is not None:
                    try:
                        widget.configure(**{opt: new})
                    except Exception:
                        pass
        except Exception:
            pass

        try:
            children = widget.winfo_children()
        except Exception:
            children = []
        for child in children:
            CorrectNoteApp._restyle_widget(child, old_to_new)

    # ------------------------------------------------------------
    # 簡易入力ウィンドウ（グローバルホットキーで呼び出す）
    # ------------------------------------------------------------
    # メモ欄と補正結果欄を1つにまとめた、小さなフローティング入力。
    # 自動では直さず、疑わしい語に色を付けるだけ。
    # クリック／ドラッグで候補から選べるのは補正結果欄と同じ操作感。
    # 閉じると、入力した内容をクリップボードに入れつつ、
    # 呼び出された時点でメモ欄のカーソルがあった位置に差し込む。

    QUICK_MIN_LINES = 3
    QUICK_MAX_LINES = 15
    # 基本の横幅（文字数）。以前は42だったが、「基本の横幅を今の6割
    # 程度にしてほしい」という指定に合わせて縮めた（42 * 0.6 ≒ 25）。
    QUICK_MIN_WIDTH = 25
    # 右へ自動拡張できる上限（文字数）。この幅を画面上のピクセル数に
    # 換算した値が画面の右端に達したら、それ以上は広げず折り返す
    # （_quick_max_width_chars で画面幅から実際に計算する）。
    QUICK_MAX_WIDTH_FALLBACK = 120

    # 呼び出したホットキーごとの説明文。
    # 表示のオン/オフは「簡易入力の説明を表示」（既定オン）で切り替える。
    QUICK_HINTS = {
        'insert': ('Ctrl+Insert は Windows の「コピー」と同じ組み合わせです。\n'
                   '他のアプリでコピーが効かないときは、下のボタンで'
                   '呼び出しを解除できます。'),
        'minus': ('Ctrl+Shift+- での呼び出しが他の操作とぶつかるときは、\n'
                  '下のボタンで解除できます。'),
    }

    def _open_quick_capture(self, source=None):
        """
        簡易入力ウィンドウを開く。

        source: どのホットキーで呼ばれたか（'insert' / 'minus'）。
            メニュー等から呼ばれた場合は None。
            そのホットキーだけを一時解除するボタンを出すのに使う。
        """
        win = getattr(self, '_quick_win', None)
        if win is not None:
            try:
                # 別のホットキーで呼び直された場合に備えて、
                # 説明文と解除ボタンも今回の呼び出し元に合わせ直す
                self._quick_source = source or getattr(
                    self, '_quick_source', None)
                self._refresh_quick_hint()
                # 呼び直したときも、いま見ている場所（マウスの近く）へ
                # 出し直し、確実に打てる状態にする
                self._place_quick_window(win)
                self._focus_quick_window(win, self._quick_text)
                return
            except Exception:
                # 前の窓はもう触れない。**ドロップの差し替えを外して
                # から**手放す（項目48-TW。死んだ番号を控えに残さない）
                try:
                    self._detach_file_drop(
                        getattr(self, '_quick_drop_hwnds', ()))
                except Exception:
                    pass
                self._quick_drop_hwnds = ()
                self._quick_win = None
                # 欄ごと死んでいる＝マークも一緒に消えている。
                # 控えだけ残すと、次の窓の行番号に化ける。
                self._quick_autofix_records = []

        self._quick_source = source

        win = tk.Toplevel(self.root)
        win.title('簡易入力')
        win.configure(bg=PANEL)
        # この窓にもアプリの絵を付ける（項目48-LY。Tk のクラスの絵は
        # 当てにしない——学び22）
        self._set_window_icons_win32(win)
        try:
            win.attributes('-topmost', True)
        except Exception:
            pass
        # 最大化ボタンを消す。
        # この窓は入力量に応じて高さが伸びる小さな入力欄なので、
        # 画面いっぱいに広げる意味が無い（実機からの指定）。
        # 横幅の変更まで塞ぐと窮屈なので、縦だけ固定する。
        try:
            # 縦だけ固定にする（内容に合わせて高さが伸びる窓なので、
            # 縦のドラッグ変更には意味が無い）。
            #
            # かつて `-toolwindow` 属性で最大化ボタンを消していたが、
            # この属性は最小化ボタンも一緒に消してしまう。
            # 最小化のほうが使う場面が多いため、
            # 「最大化が残ってもいいので最小化を戻してほしい」という
            # 指定に従い、属性の指定はやめた。
            win.resizable(True, False)
        except Exception:
            pass

        # wrap='none' を基本にし、行が伸びたらウィンドウの横幅そのものを
        # 広げる（右端に届いても折り返さない・実機からの指定）。
        # 画面の右端まで達したときだけ 'char' に切り替えて折り返す
        # （_adjust_quick_size が幅と wrap モードの両方を管理する）。
        text = tk.Text(
            win, wrap='none', undo=True, bg=PANEL, fg=INK,
            insertbackground=INK, font=EDITOR_FONT, relief='flat',
            padx=10, pady=8, height=self.QUICK_MIN_LINES,
            width=self.QUICK_MIN_WIDTH,
        )
        text.pack(fill='both', expand=True)
        text.tag_configure('suspect', background=SUSPECT_BG)
        # 自動反映の色（項目48-LR。本体と同じ配色——補正は赤・
        # 選び直しは青緑）
        text.tag_configure('autofixed', foreground=FIXED_FG)
        text.tag_configure('autochosen', foreground=ACCENT)
        text.tag_configure('sel', background=EDITOR_SEL_BG)
        text.tag_raise('sel')

        # 説明文と「一時解除」ボタンの置き場所。
        # 中身は _refresh_quick_hint が作り直す（呼び出し元や
        # 設定が変わっても、この1箇所で組み立て直せるようにしておく）。
        hint = tk.Frame(win, bg=PANEL)
        hint.pack(fill='x', side='bottom')

        self._quick_win = win
        self._quick_text = text
        self._quick_hint_frame = hint
        self._quick_after_id = None
        # 見えない空白の印（項目48-IH・うにさんの指定
        # 「簡易入力にも実装してください。**オプションは共通です**」）。
        # 色も切り替えも本体と同じものを見る（`_whitespace_targets`）。
        self._configure_whitespace_tags()
        self._apply_tab_stops()      # タブの止まり（項目48-LG）
        self._schedule_whitespace_paint(delay=1)
        self._quick_units = []     # 行ごとの単位（build_suspect_units の結果）
        self._quick_results = []   # 行ごとの補正結果（項目48-MD の根拠）
        self._quick_autofix_records = []   # 自動反映の控え（_autofix_pane）
        self._quick_drag = None

        text.bind('<KeyRelease>', self._on_quick_change)
        # 本体のメモ欄と同じく、IME が確定した半角記号が Delete 等の
        # 編集キーとして届く問題に備える（ime_confirmed_char 参照）。
        text.bind('<KeyPress>', self._on_ime_ascii_key, add=True)
        # Shift+クリックの範囲選択の起点合わせ（本体のメモ欄と同じ。
        # 理由は _on_shift_click_anchor の説明を参照）。
        text.bind('<Shift-Button-1>', self._on_shift_click_anchor, add=True)
        # F1 で引用モード（本体の F1 と同じ。拾った語は簡易入力の
        # カーソル位置に入る。実機からの要望・2026-08-09）。
        # F1 は '<F1>' の個別束縛ではなく、_on_ime_ascii_key（全ての
        # KeyPress を受ける、動作実績のある経路）の中で受ける。
        # 個別束縛が実機で効かなかったため（2026-08-09）。
        # 本体のメモ欄と同じく、選択なしの Ctrl+C でも引用モードに
        # 入る（実機からの指定・2026-08-09。選択があるときは
        # 標準のコピーに任せる）。
        text.bind('<Control-c>', self._on_quick_ctrl_c)
        # Ctrl+Z: 自動反映した行は `_undo_autofix` を通す
        # （_on_quick_ctrl_z の説明を参照）。控えの無い行は
        # 素通しして Tk のふつうの取り消しに任せる。
        text.bind('<Control-z>', self._on_quick_ctrl_z)
        # 引用モード中は、簡易入力欄の中の語も拾える
        # （実機からの要望・2026-08-09）。押した時点ではなく
        # **離した時点**で拾う。押した時点で拾うと、範囲選択の
        # ドラッグが始められない（実機で「クリック時点で引用が
        # 終わる」と報告・2026-08-09）。通常時は何もしない。
        text.bind('<ButtonRelease-1>', self._on_quick_pick_click,
                  add=True)
        # F2: カーソル直前の語の候補。押すごとに左の語へ遡る
        # （本体と同じ操作・2026-08-09）。
        # **IME が確定した `q` は keysym が F2 に化ける**ので、
        # 欄への束縛用の入口を通す（項目48-EH）。
        text.bind('<F2>', self._on_quick_f2_widget)
        # 中身が変わったことを確実に捉える経路。
        # IMEの確定・貼り付け・差し込みは KeyRelease では
        # 取りこぼすことがあり、枠が伸びずに右へ見切れていた。
        text.bind('<<Modified>>', self._on_quick_modified)
        # 操作は本体のメモ欄と揃える（実機からの指定）:
        #   左クリック … カーソル移動・範囲選択（Text の既定のまま）
        #   右クリック … 候補一覧
        # 以前は左クリックで候補を出していたが、本体と操作が食い違って
        # 混乱するため、右クリックに統一した。
        text.bind('<Button-3>', self._on_quick_right_click)
        # 余白をクリックしたら F2 の色を消す（うにさんの報告・
        # 2026-08-11・C-5）。本体のメモ欄と同じ束縛
        # （`_clear_f2_on_click`）。簡易入力だけこれが無く、
        # 色が残りっぱなしになっていた。
        text.bind('<Button-1>', self._clear_f2_on_click, add=True)
        # 行末より右の余白を押したら、カーソルをその行の末尾に置く
        # （本体のメモ欄と同じ・項目48-GN）
        text.bind('<Button-1>', self._on_click_past_line_end, add=True)
        # オンマウスで背景色を変えて、選び直せる語だと分かるようにする
        text.bind('<Motion>', self._on_quick_motion)
        text.bind('<Leave>', self._on_quick_leave)
        text.tag_configure('hover', background=HOVER_BG)
        win.protocol('WM_DELETE_WINDOW', self._close_quick_capture)
        win.bind('<Escape>', lambda e: self._close_quick_capture())
        win.bind('<F1>', self._on_quick_f1)
        # テキスト欄に焦点があるときは、Text 側がキーを先に受け取り
        # Toplevel の束縛まで届かないことがある。欄にも直接束縛して、
        # どこに焦点があっても Esc で閉じられるようにする
        # （実機で「Escを押しても閉じない」と報告された）。
        # 閉じる処理は、書いた内容のコピーと本体への挿入も行うので、
        # 何か書いてある場合でもそのまま呼んでよい。
        text.bind('<Escape>', lambda e: (self._close_quick_capture(),
                                         'break')[1])

        self._refresh_quick_hint()

        # **専用の IME 文脈を持たせる**（項目48-LR・2026-08-30）。
        # 本体と文脈を1つ共有したままだと、本体の描き直しが caret
        # （＝未変換文字列の表示位置）を引き戻し、簡易入力で打って
        # いる未変換の文字が本体側（最大化ならモニターの左上あたり）
        # と**交互に点滅**する（うにさんの報告。probe_quick_ime3 で
        # 0.25〜0.3秒ごとの往復を実測）。
        # 結び付ける窓は**包み（wrapper・焦点が向かう窓）と Text の
        # 両方**——IME は焦点の窓の文脈を読み、Tk は Text の窓へ
        # 位置を書くため（片方だけだと素通り・学び22）。
        self._quick_himc = None
        self._quick_himc_hwnds = ()
        try:
            import ime_watch
            if ime_watch.HAS_SUPPORT:
                import ctypes as _ct
                win.update_idletasks()
                _wrap = _ct.windll.user32.GetParent(win.winfo_id())
                _hs = tuple(h for h in (_wrap, text.winfo_id()) if h)
                self._quick_himc = ime_watch.give_own_context(_hs)
                if self._quick_himc:
                    self._quick_himc_hwnds = _hs
                    # 未変換の字も、この専用の文脈に掛ける（項目48-LO）
                    self._set_ime_font(widget=text)
        except Exception:
            self._quick_himc = None

        # この窓へ落としたファイルも受ける（項目48-TW・学び22）。
        # 行き先は本体と同じ——**本体の新しいタブ**に出す。
        self._quick_drop_hwnds = self._attach_file_drop(win)

        self._place_quick_window(win)
        self._focus_quick_window(win, text)
        self.status.config(text='簡易入力ウィンドウを開きました')

    def _place_quick_window(self, win):
        """
        簡易入力ウィンドウを、マウスカーソルのすぐ近くに出す。

        この窓は他のアプリを使っている最中にホットキーで呼ぶものなので、
        本体ウィンドウの位置を基準にすると、いま作業している場所から
        遠い所に出てしまう（本体を別のディスプレイに置いている場合は
        特に顕著。実機で報告された）。
        いま見ている場所＝マウスカーソルの位置を基準にする。

        ただし画面の端で切れないよう、はみ出す場合は内側へ寄せる。
        大きさの判定には、カーソルのある画面ではなく仮想デスクトップ
        全体を使えないため、winfo_screen* を使う（複数ディスプレイでは
        近似になるが、カーソル基準なので大きく外れることはない）。
        """
        win.update_idletasks()
        try:
            px, py = win.winfo_pointerxy()
        except Exception:
            px = self.root.winfo_rootx() + 80
            py = self.root.winfo_rooty() + 80

        w = win.winfo_reqwidth()
        h = win.winfo_reqheight()
        # カーソルの少し右下に出す（カーソル自体が窓に隠れないように）
        x, y = px + 16, py + 16
        # マウスカーソルのあるモニターの作業領域に収める
        # （マルチディスプレイで境目にまたがって出ていた・2026-08-09）
        area = monitor_work_area(px, py)
        if area:
            a_l, a_t, a_r, a_b = area
            if x + w > a_r:
                x = max(a_l, a_r - w - 8)
            if y + h > a_b:
                y = max(a_t, a_b - h - 8)
            x = max(a_l, min(x, a_r - 40))
            y = max(a_t, min(y, a_b - 40))
        else:
            try:
                sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
                if x + w > sw:
                    x = max(0, px - w - 16)
                if y + h > sh:
                    y = max(0, py - h - 16)
            except Exception:
                pass
        try:
            win.geometry(f'+{int(x)}+{int(y)}')
        except Exception:
            pass

    def _focus_quick_window(self, win, text):
        """
        簡易入力ウィンドウを前に出し、すぐ打ち始められる状態にする。

        ホットキーで呼ぶとき、アプリ自体は非アクティブなことが多い。
        その場合 focus_set だけでは Windows がキーボード入力の相手を
        こちらに切り替えてくれず、窓は見えているのに打てない、という
        状態になる（実機で報告された）。
        窓そのものを前面へ出したうえで focus_force で奪い取る。

        deiconify → lift → focus_force の順で呼ぶ。最小化されている
        場合に lift だけでは前に出ないため。
        """
        try:
            win.deiconify()
        except Exception:
            pass
        try:
            win.lift()
        except Exception:
            pass
        try:
            # 一瞬だけ最前面を強制すると、他アプリからの切り替えでも
            # 確実に前に出る。-topmost は元から立てているが、
            # 立て直すことで Windows に「今アクティブにせよ」と伝わる。
            win.attributes('-topmost', True)
        except Exception:
            pass
        try:
            win.focus_force()
        except Exception:
            pass
        try:
            text.focus_set()
        except Exception:
            pass
        # 直後だと OS 側の切り替えが間に合わないことがあるので、
        # 一拍おいてもう一度だけ焦点を取りに行く。
        def _again():
            try:
                if self._quick_win is win:
                    win.focus_force()
                    text.focus_set()
            except Exception:
                pass
        try:
            self.root.after(60, _again)
        except Exception:
            pass

    def _refresh_quick_hint(self):
        """
        説明文と「一時解除」ボタンを組み立て直す。

        出すのは、実際にこの窓を呼び出したホットキーのぶんだけ。
        既に一時解除したホットキーには、もうボタンを出さない。
        「簡易入力の説明を表示」をオフにした場合は、
        説明文だけでなく一時解除ボタンごと出さない
        （ユーザー指定。「説明を消したのにボタンだけ残る」状態を避ける）。
        """
        frame = getattr(self, '_quick_hint_frame', None)
        if frame is None:
            return
        try:
            for child in frame.winfo_children():
                child.destroy()
        except Exception:
            return

        if not self.settings.get('show_quick_hint'):
            return

        name = getattr(self, '_quick_source', None)
        if not name or name not in HOTKEY_LABELS:
            return                      # メニューから開いた場合など
        if name in self._hotkey_suspended:
            return                      # もう解除済み
        if not self.hotkeys.supported:
            return                      # ホットキーが動かない環境

        tk.Label(frame, text=self.QUICK_HINTS.get(name, ''),
                 bg=PANEL, fg=MUTED, font=('Yu Gothic UI', 8),
                 justify='left', anchor='w', wraplength=380,
                 padx=10, pady=2).pack(fill='x')

        label = HOTKEY_LABELS[name]
        tk.Button(
            frame,
            text=f'{label} でこのウィンドウを呼び出すのを一時的に解除する',
            bg=PANEL, fg=ACCENT, font=('Yu Gothic UI', 8),
            relief='flat', bd=0, highlightthickness=0, cursor='hand2',
            command=lambda n=name: self._suspend_hotkey(n),
        ).pack(fill='x', padx=6, pady=(0, 6))

    def _close_quick_capture(self):
        """
        閉じる。内容をクリップボードへ入れ、同時に
        呼び出し時点でメモ欄のカーソルがあった位置へ差し込む。
        """
        win = getattr(self, '_quick_win', None)
        text_widget = getattr(self, '_quick_text', None)
        if win is None:
            return

        # 予約済みの解析を取り消す。残したままだと、次にこの窓を
        # 開いた直後に古い予約が発火し、書き始める前の空の内容で
        # 解析が走ってしまう。
        if getattr(self, '_quick_after_id', None):
            try:
                self.root.after_cancel(self._quick_after_id)
            except Exception:
                pass
        self._quick_after_id = None

        content = ''
        if text_widget is not None:
            try:
                content = text_widget.get('1.0', 'end-1c')
            except Exception:
                content = ''

        # 専用の IME 文脈を片付ける（項目48-LR。**destroy の前**——
        # あとだと hwnd が無効で外せない）
        try:
            import ime_watch
            if getattr(self, '_quick_himc', None):
                ime_watch.restore_default_context(
                    getattr(self, '_quick_himc_hwnds', ()),
                    self._quick_himc)
        except Exception:
            pass
        self._quick_himc = None
        self._quick_himc_hwnds = ()

        # ドロップの差し替えも**destroy の前**に外す（項目48-TW）。
        # あとだと hwnd が無効で、控えに死んだ番号が残る。
        try:
            self._detach_file_drop(getattr(self, '_quick_drop_hwnds', ()))
        except Exception:
            pass
        self._quick_drop_hwnds = ()

        # 自動反映の控えも**destroy の前**に片づける（同じ理由。
        # あとだと `mark_unset` が例外で、控えが残る）。
        if text_widget is not None:
            try:
                self._autofix_reset(w=text_widget)
            except Exception:
                pass
        else:
            self._quick_autofix_records = []

        try:
            win.destroy()
        except Exception:
            pass
        self._quick_win = None
        self._quick_text = None
        self._quick_hint_frame = None
        self._quick_source = None
        self._quick_units = []

        if not content.strip():
            self.status.config(text='簡易入力を閉じました（内容は空でした）')
            return

        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(content)
        except Exception:
            pass

        target = None
        try:
            target = self.editor.index('insert')
        except Exception:
            target = None
        target = target or 'end-1c'
        try:
            # 差し込む前に**位置を確定させておく**。`end-1c` のような
            # 相対的な指定のままだと、差し込んだ後に指す場所が変わる。
            start = self.editor.index(target)
            self.editor.insert(start, content)
            self.editor.mark_set('insert', f'{start}+{len(content)}c')
            self.editor.see('insert')
            self._mark_quick_sent(start, len(content))
        except Exception:
            pass
        self._on_change()
        self.status.config(text='簡易入力の内容をクリップボードとメモに追加しました')

    def _mark_quick_sent(self, start, length):
        """
        簡易入力から送った範囲に色を付ける（項目48-GN／48-GO）。

        うにさんの指定（2026-08-20）:
        「簡易入力からアプリ本体に送った文字は、一時的に色を付ける。
          **2色を用意し、連続して簡易入力から送ったら交互に色を付ける**」
        「色は秒数ではなく、**次にアプリ本体に直接文字を入力したとき**に
          戻す。……**それまでは2色を交互につけ続ける。連続して3回
          簡易入力した際に、1回目の色もついたままにする**」（48-GO）

        だから **送ったぶんは消さずに足していく**。同じ色が2か所
        以上にあってよい（3回送れば A・B・A の3か所が残る）。
        消えるのは `_clear_quick_sent`（＝本体で文字を打ったとき）
        の一度きりで、まとめて消えるので取り違えようがない。
        """
        if length <= 0:
            return
        try:
            flip = 1 - getattr(self, '_quick_sent_flip', 1)
            self._quick_sent_flip = flip
            tag = 'quick_sent_b' if flip else 'quick_sent_a'
            bg = QUICK_SENT_BG_B if flip else QUICK_SENT_BG_A
            self.editor.tag_configure(tag, background=bg)
            self.editor.tag_add(tag, start, f'{start}+{length}c')
            # 網掛け（補正の候補あり）より**下**に置く。送った文字の
            # 中に誤字があれば、そちらの色を隠さずに見せたい。
            try:
                self.editor.tag_lower(tag, 'suspect')
            except Exception:
                pass
            self.editor.tag_raise('sel')
        except Exception:
            pass

    def _clear_quick_sent(self):
        """簡易入力から送った文字の色を、まとめて消す。"""
        for t in ('quick_sent_a', 'quick_sent_b'):
            try:
                self.editor.tag_remove(t, '1.0', 'end')
            except Exception:
                pass
        # 次に送るときは、また1色目（緑）から始める。
        self._quick_sent_flip = 1

    def _on_editor_typed(self, event=None):
        """
        本体のメモ欄で**直接文字を打った**ら、簡易入力の色を戻す。

        うにさんの指定（2026-08-20・項目48-GO）:

        > 「色は秒数ではなく、**次にアプリ本体に直接文字を入力した
        >   とき**に色を戻す。**ペーストや引用で文字を追加しただけ
        >   では戻さない。キーボード入力があってそこで戻す**」

        だから見るのは「文字が増えたか」ではなく**打鍵そのもの**。
        貼り付け（右クリックのメニュー）や引用（F1）で文字が入っても、
        打鍵ではないのでここへは来ない。

        除くもの:
          - `Ctrl` を伴う打鍵（Ctrl+V の `v` はこれで外れる）
          - 文字を持たない鍵（矢印・F2・Shift+Insert・Esc など）
          - 制御文字（BackSpace・Delete・Tab）。**消すのは「入力」
            ではない**ので、消しただけでは色を戻さない。
          - 改行（Enter）は文字が入るので**戻す側**に入れてある。

        **`Alt` の印（Mod1・0x08）は見てはいけない。**
        Windows の Tk は **NumLock が入っていると 0x08 を立てる**
        （Mod1Mask を NumLock に割り当てている）。ここを Alt と
        思って弾いていたため、**NumLock を入れている機械では
        どの打鍵も素通り**していた——うにさんの実機で
        「本体に文字入力しても色が戻りません」（2026-08-20）。
        xvfb（X11）では NumLock が入っていないので通っていた。
        `Ctrl`（0x04）だけは両方の環境で同じ意味なので見てよい。
        Alt を伴う打鍵は、そもそも印字できる文字を持たない。

        **IME で確定した日本語もここへ来る。** Windows の Tk は
        確定した文字を1字ずつ `KeyPress` として渡す（`KeyRelease`
        のほうは来ないことがあり、`_on_quick_modified` はそのために
        `<<Modified>>` を併用している）。
        """
        self._sz_note_key(event)        # 消えたときの証拠（項目48-SZ）
        try:
            ch = event.char if event is not None else ''
        except Exception:
            ch = ''
        if not ch:
            return None
        try:
            state = int(getattr(event, 'state', 0) or 0)
        except Exception:
            state = 0
        if state & 0x0004:
            return None                 # Control
        code = ord(ch[0])
        if code == 127 or (code < 32 and ch[0] not in ('\r', '\n')):
            return None                 # BackSpace・Delete・Tab・Esc 等
        self._clear_quick_sent()
        return None

    def _on_quick_change(self, event=None):
        # 本体メモ欄の _maybe_start_pick_from_equals と同じ考え方で、
        # 簡易入力欄でも直前に確定した文字が「＝」なら引用モードに
        # 入る（実機からの要望。「簡易表示でも、＝で引用モードを
        # 実行する」）。差し込み先はこの簡易入力欄自身にする。
        self._maybe_start_quick_pick_from_equals()

        # 打鍵があったら、自動反映の暴走止めを数え直す（項目48-LR。
        # 本体の `_autofix_rounds` と同じ構え）
        self._quick_autofix_rounds = 0

        # 枠の大きさの調整は、補正の解析（重い・250ms待つ）とは
        # 切り離して即座に行う。待たせると、打っている最中に
        # 文字が右へ見切れたままになる。
        self._adjust_quick_size(self._quick_text)

        # 見えない空白の印（項目48-IH）。枠の調整と同じく、
        # 重い解析（250ms待つ）とは切り離して早めに塗る。
        self._schedule_whitespace_paint()

        if self._quick_after_id:
            self.root.after_cancel(self._quick_after_id)
        self._quick_after_id = self.root.after(250, self._analyze_quick)

    def _on_quick_modified(self, event=None):
        """
        簡易入力欄の中身が変わったときに必ず呼ばれる入口。

        <KeyRelease> だけでは取りこぼす変化があるため、
        tkinter の <<Modified>> を併用する:
          - IMEの未変換文字列を確定したとき
            （確定は1回のキー操作で複数文字が入るため、
              KeyRelease が期待どおり飛ばないことがある）
          - 貼り付け（Ctrl+V・右クリックメニュー）
          - 引用モードでの差し込み
        いずれも「枠が伸びずに文字が右へ見切れる」と
        実機で報告された経路（無変換からの確定・ペースト）。

        <<Modified>> は一度発生すると、フラグを戻すまで
        二度と飛ばない仕様なので、毎回明示的に戻す。
        """
        text_widget = getattr(self, '_quick_text', None)
        if text_widget is None:
            return
        try:
            text_widget.edit_modified(False)
        except Exception:
            pass
        self._adjust_quick_size(text_widget)
        # 見えない空白の印を塗り直す（項目48-IH）。ここは
        # IME の確定・貼り付け・引用の差し込みまで拾う入口なので、
        # **打鍵だけを見る `<KeyRelease>` より取りこぼしが少ない**。
        self._schedule_whitespace_paint()

    def _maybe_start_quick_pick_from_equals(self):
        """
        簡易入力欄で直前に確定した文字が「＝」なら、引用モードに入る。

        本体メモ欄向けの _maybe_start_pick_from_equals と同じ後追い
        方式（KeyRelease後、確定済みの文字だけを見る）。全角入力・
        ローマ字入力では働くが、かな入力設定では Shift+「-」が
        「ほ」として確定してしまうため検出できない
        （本体側と同じ制約。SPEC.md参照）。
        """
        text_widget = getattr(self, '_quick_text', None)
        if text_widget is None:
            return
        if getattr(self, '_pick_mode', None):
            return
        try:
            pos = text_widget.index('insert')
            prev = text_widget.get('insert-1c', 'insert')
        except Exception:
            return
        if prev not in ('＝', '='):
            self._quick_last_equals_pos = None
            return
        if getattr(self, '_quick_last_equals_pos', None) == pos:
            return
        self._quick_last_equals_pos = pos

        try:
            text_widget.mark_set(self._PICK_EQUALS_START, 'insert-1c')
            text_widget.mark_gravity(self._PICK_EQUALS_START, 'left')
            text_widget.mark_set(self._PICK_EQUALS_END, 'insert')
            text_widget.mark_gravity(self._PICK_EQUALS_END, 'right')
        except Exception:
            return
        self._start_pick_mode(via_equals=True, target='quick')

    def _analyze_quick(self):
        """
        入力を解析して、疑わしい語だけに色を付ける（自動では直さない）。

        行数に応じてウィンドウの高さも調整する。
        """
        self._quick_after_id = None
        text_widget = self._quick_text
        if text_widget is None:
            return

        fn = getattr(self.store, '_tokenize_fn', None)
        if fn is None:
            fn = corrector.make_tokenizer(self.store)
            self.store._tokenize_fn = fn

        content = text_widget.get('1.0', 'end-1c')
        lines = content.split('\n')

        text_widget.tag_remove('suspect', '1.0', 'end')
        self._quick_units = []
        # どの文字から作った単位なのかを控える。F2 が「古い単位で
        # 判断してしまう」のを防ぐのに使う（_on_quick_f2 参照）。
        self._quick_units_text = content

        _results = []
        for i, line in enumerate(lines):
            row = i + 1
            if not line:
                self._quick_units.append([])
                _results.append(None)
                continue
            # 本体のメモ欄と同じ材料を渡す（項目48-LR。渡して
            # いなかった頃は、世の中の読みの辞書が要る補正
            # （泳いた→泳いだ 等）が簡易入力でだけ効かなかった）
            # **台帳（decisions）も渡す**（学び22——門は全部の道に
            # 掛ける）。渡していなかったので、簡易入力では
            # 「この補正は不要」「今後直さない」が1つも効かず、
            # 元へ戻しても次の解析（250ms後）でまた直っていた。
            # メモ欄の `_analyze` は最初から渡している。
            result = corrector.correct_line(
                line, self.store, fn, find_known_readings_flex,
                decisions=self.decisions,
                input_method=self.settings.get('input_method'),
                context_vec=self.context_vec,
                dict_index=self.dict_index)
            _results.append(result)
            _text, units = build_suspect_units(result, fn, self.choices,
                                           self._known_kana_word)
            self._quick_units.append(units)
            for u in units:
                if u['kind'] in ('suspect', 'chosen_hint'):
                    text_widget.tag_add(
                        'suspect', f'{row}.{u["start"]}', f'{row}.{u["end"]}')

        # 候補一覧の「－ 補正根拠 －」が読む（項目48-MD）。
        # **簡易入力の行は本体と別**なので、あちらの控え
        # （`self.line_results`）を引くと別の行の理由が付く。
        # **自動反映で下から抜ける前に**置いておくこと。
        self._quick_results = _results

        # 補正を欄の中へ自動で反映（項目48-LR・表示メニューで切替）。
        # 書き換えたら、色付けと単位を新しい文字で作り直すため
        # もう一度だけ解析へ回る（直した文は変わらないので収まる。
        # 万一の行ったり来たりは AUTOFIX_MAX_ROUNDS で降りる）。
        try:
            if self._apply_quick_autofix(lines, _results):
                self.root.after(50, self._analyze_quick)
                return
        except Exception:
            pass

        # 自動反映した箇所の色は**控えから塗り直す**
        # （メモ欄の `_refresh_after_analysis` と同じ形）。
        self._repaint_autofix_tags(w=text_widget)

        self._adjust_quick_size(text_widget, lines)

    def _apply_quick_autofix(self, lines, results):
        """
        簡易入力の欄の中へ、補正の結果を自動で反映する（項目48-LR・
        うにさんの指定・2026-08-30「簡易入力で補正を自動で反映する」）。

        書き込む中身は、本体の統合表示の自動反映と同じ作り
        （`build_line_units`——自動補正に加えて **F2 の選び直しも
        効く**。「オプションは共通です」の精神）。守りも統合表示の
        `_apply_unified_autofix` から最小の形で持ってくる:
          - **IME が変換中なら見送る**（未確定の文字を壊さない）
          - **続けて書き換えるのは5回まで**（暴走止め。打鍵で数え直す）
          - **カーソルは書き換え後の同じところへ**（map_column）
        取り消しは、右クリック／F2 の一覧の「― 自動補正 ―」か
        Ctrl+Z（`_on_quick_ctrl_z`）。どちらも `_undo_autofix` を
        通る。そのために**打った文字を控える**——控えは
        `_autofix_pane` でメモ欄と共用（48-GN）。

        lines / results: `_analyze_quick` が数え終えた行と結果
        （同じ correct_line を二度呼ばないため）。

        戻り値: 1行でも書き換えたら True。
        """
        if not bool(self.settings.get('quick_autofix')):
            return False
        text_widget = getattr(self, '_quick_text', None)
        if text_widget is None:
            return False
        try:
            import ime_watch
            if ime_watch.composition_active(text_widget.winfo_id()):
                return False
        except Exception:
            pass
        if getattr(self, '_quick_autofix_rounds', 0) \
                >= self.AUTOFIX_MAX_ROUNDS:
            return False
        fn = getattr(self.store, '_tokenize_fn', None)
        if fn is None:
            return False
        try:
            cur_row, cur_col = (int(x) for x in
                                text_widget.index('insert').split('.'))
        except Exception:
            cur_row, cur_col = -1, 0
        # いま生きている控えを、行番号で引ける形にしておく
        # （メモ欄の `_apply_unified_autofix` と同じ）
        live = {r: rec for rec, r in
                self._autofix_live_records(w=text_widget)}
        applied = []
        for i, line in enumerate(lines):
            result = results[i] if i < len(results) else None
            if not line or result is None:
                continue
            try:
                new_text, units = build_line_units(
                    result, fn, self.choices, self._known_kana_word)
            except Exception:
                continue
            if not new_text or new_text == line:
                continue
            rec = live.get(i + 1)
            # 「元の入力に戻す」を使った行はそのままにする
            # （戻したいという意図を上書きしない。メモ欄の
            #  `_apply_unified_autofix` と同じ帯）。
            if rec is not None and rec['manual']:
                continue
            # 欄の中身が解析の時点から変わっていたら触らない
            # （250ms の間に打ち続けた行を壊さない）
            try:
                if text_widget.get(f'{i + 1}.0', f'{i + 1}.end') != line:
                    continue
            except Exception:
                continue
            applied.append((i + 1, line, new_text, units, rec))
        if not applied:
            self._quick_autofix_rounds = 0
            return False
        self._quick_autofix_rounds = getattr(
            self, '_quick_autofix_rounds', 0) + 1
        try:
            text_widget.edit_separator()
            for row, old, new_text, units, rec in applied:
                text_widget.delete(f'{row}.0', f'{row}.end')
                text_widget.insert(f'{row}.0', new_text)
                # **打った文字を控える**（メモ欄と同じ
                # `_autofix_remember`）。これが無いと、直した
                # あとで「元の入力に戻す」が出せない。
                if rec is None:
                    if len(getattr(self, '_quick_autofix_records', ())) \
                            < self.AUTOFIX_ORIGINALS_LIMIT:
                        self._autofix_remember(row, new_text, old,
                                               units, w=text_widget)
                else:
                    # ★ **`original` は作るときにしか書かない。**
                    # 簡易入力の解析は**画面に出ている補正後の
                    # 文字**を読み直すので（`_analyze_quick`）、
                    # 2周目に上書きすると原文が「1周目の出力」に
                    # 化け、「元の入力に戻す」が別の文字へ戻す。
                    # メモ欄が原文を書き直せるのは、あちらが
                    # `editor_source_text` で原文に戻してから
                    # 解析しているため。
                    rec['applied'] = new_text
                    rec['spans'] = self._autofix_spans_of(units)
            text_widget.edit_separator()
            # 色は**控えから塗り直す**（`_repaint_autofix_tags`）。
            # ここで直に tag_add していた頃は、簡易入力の
            # `autofixed`／`autochosen` が一度も tag_remove されず、
            # 手で消したあとも色が残っていた。
            self._repaint_autofix_tags(w=text_widget)
            for row, old, new_text, _u, _rec in applied:
                if row == cur_row:
                    text_widget.mark_set(
                        'insert',
                        f'{row}.{map_column(old, new_text, cur_col)}')
                    break
        except Exception:
            return False
        return True

    def _quick_font(self):
        """簡易入力欄のフォント（実測に使う）。"""
        try:
            import tkinter.font as tkfont
            return tkfont.Font(font=EDITOR_FONT)
        except Exception:
            return None

    def _adjust_quick_size(self, text_widget, lines=None):
        """
        入力内容に合わせて、簡易入力ウィンドウの横幅・縦幅・折り返しを
        調整する。

        横幅: 最も長い行の**実際の表示幅（ピクセル）**に合わせて広げる。
            以前は tkinter の Text(width=N) に「行の文字数」を
            そのまま渡していたが、この N は「フォントの `0` 1文字分の
            幅の N 倍」という意味であり、全角の日本語は約2倍の幅を
            占めるため、日本語の行では必要な幅の半分しか確保できず
            右へ見切れていた（実機で報告された症状）。
            文字数ではなくフォントで実測した幅を使えば、
            日本語・英数字・記号が混ざっていても正しく合う。
            文字を消す・改行して最長行が短くなれば幅も縮める。
            画面の右端に届いたら、それ以上は広げず折り返す
            （wrap を 'char' にする）。
        縦幅: 折り返しで増えた表示行数まで含めて数える。
            論理行数だけを見ていると、折り返し後に縦が足りず
            入力した文字が上に見切れる（実機で報告された）。
        """
        win = getattr(self, '_quick_win', None)
        if win is None or text_widget is None:
            return
        if lines is None:
            try:
                lines = text_widget.get('1.0', 'end-1c').split('\n')
            except Exception:
                return

        font = self._quick_font()
        if font is None:
            return

        try:
            # 1文字ぶんの幅の基準。Text(width=N) の N はこの幅の倍数。
            unit = max(1, font.measure('0'))
            # 最も長い行の実測幅（ピクセル）。文字数ではなく実測なので
            # 全角・半角が混ざっていても正しい。
            max_px = max((font.measure(ln) for ln in lines), default=0)
            # カーソルぶんの余白を1文字足しておく（末尾で打ち続けた
            # ときに、カーソルが枠にめり込まないように）。
            max_px += unit

            win.update_idletasks()
            left = win.winfo_x()
            if left <= 0:
                left = win.winfo_pointerx()
            top = win.winfo_y()
            # ウィンドウのあるモニターの右端を基準にする。
            # winfo_screenwidth はプライマリの幅しか返さないため、
            # 2枚目のモニターでは right_edge - left が負になり、
            # 最小幅で折り返し続けていた（実機で「右へ拡張されない」
            # と報告された・2026-08-09）。
            area = monitor_work_area(left + 10, top + 10)
            if area:
                right_edge = area[2]
            else:
                right_edge = win.winfo_screenwidth()
            margin = 40   # 画面端ぎりぎりまで詰めない余白
            # padx=10 が左右にあるぶんを差し引く
            avail_px = max(unit * self.QUICK_MIN_WIDTH,
                          right_edge - left - margin - 20)

            min_px = unit * self.QUICK_MIN_WIDTH
            if max_px > avail_px:
                # 画面の端に届く。それ以上は広げず、折り返しに切り替える。
                new_px = avail_px
                new_wrap = 'char'
            else:
                new_px = max(min_px, max_px)
                new_wrap = 'none'

            # ピクセル幅を Text の width（＝基準文字の個数）に換算する。
            # 切り上げないと、端数のぶんだけ最後の文字が欠ける。
            new_width = max(self.QUICK_MIN_WIDTH,
                           -(-int(new_px) // unit))

            size_changed = False
            if int(text_widget.cget('width')) != new_width:
                text_widget.configure(width=new_width)
                size_changed = True
            if text_widget.cget('wrap') != new_wrap:
                text_widget.configure(wrap=new_wrap)
                size_changed = True
        except Exception:
            size_changed = False

        # 縦幅は実際の表示行数（折り返しぶんも含む）を数えて決める。
        # 幅や wrap を変えた直後は再計算前のことがあるので、先に確定させる。
        #
        # **生の count を int() に掛けてはいけない**（2026-09-04・実機の
        # 「改行しても窓が縦に伸びないことがある」の原因）。この環境の
        # Python 3.9 では count は 1要素のタプル `(21,)` を返すので、
        # int() が毎回 TypeError になり、**折り返しを数える道は一度も
        # 動いていなかった**（下の except で論理行数に落ちるため、
        # 折り返しの無い行では症状が出ず、長い行が折り返された窓でだけ
        # 高さが足りなくなる）。型ゆれを受ける関数が同じクラスに既に
        # 在る（`_displaylines_between`・学び7）ので、そちらを通す
        # （学び22——片方だけに置くと、そちらを迂回する）。
        try:
            text_widget.update_idletasks()
        except Exception:
            pass
        n_display = self._displaylines_between(text_widget, '1.0', 'end')
        if n_display <= 0:
            n_display = len(lines)
        n_lines = max(self.QUICK_MIN_LINES,
                      min(n_display, self.QUICK_MAX_LINES))
        try:
            if int(text_widget.cget('height')) != n_lines:
                text_widget.configure(height=n_lines)
                size_changed = True
        except Exception:
            pass
        # 大きさが変わったら、外形の固定を解いて中身に合わせ直す。
        # 一度でも geometry で外形が決まると（位置指定・手動リサイズ）、
        # 中の Text の width/height を変えても窓は広がらない
        # （実機で「右や下へ自動拡張されない」と報告・2026-08-09）。
        if size_changed:
            try:
                _x, _y = win.winfo_x(), win.winfo_y()
                win.geometry('')
                win.update_idletasks()
                # 位置は保ったまま大きさだけ自動に戻す
                win.geometry(f'+{_x}+{_y}')
            except Exception:
                pass

    def _quick_unit_under_pointer(self, event):
        text_widget = self._quick_text
        if text_widget is None:
            return None
        try:
            index = text_widget.index(f'@{event.x},{event.y}')
            row_s, col_s = index.split('.')
            row, col = int(row_s), int(col_s)
        except Exception:
            return None
        i = row - 1
        if not (0 <= i < len(self._quick_units)):
            return None
        unit = unit_at(self._quick_units[i], col)
        if unit is None:
            return None
        return row, unit

    def _on_quick_motion(self, event):
        """簡易入力欄で、語にオンマウスの背景色を付ける。"""
        text_widget = getattr(self, '_quick_text', None)
        if text_widget is None:
            return
        try:
            text_widget.tag_remove('hover', '1.0', 'end')
        except Exception:
            return
        hit = self._quick_unit_under_pointer(event)
        if hit is None:
            return
        row, unit = hit
        if not unit.get('text', '').strip():
            return
        try:
            text_widget.tag_add('hover',
                                f'{row}.{unit["start"]}',
                                f'{row}.{unit["end"]}')
        except Exception:
            pass

    def _on_quick_leave(self, event=None):
        text_widget = getattr(self, '_quick_text', None)
        if text_widget is None:
            return
        try:
            text_widget.tag_remove('hover', '1.0', 'end')
        except Exception:
            pass

    def _on_quick_right_click(self, event):
        """
        簡易入力欄で候補一覧を出す（本体のメモ欄と同じ操作）。

        ドラッグで範囲を選んでいればその範囲、
        選んでいなければポインタの下の語で候補を作る。

        範囲で候補を出したあとは、必ず選択を消してから返す。
        残したままだと、次に余白をクリックしたときにも
        「まだ範囲が選ばれている」と見なされ、同じ候補が
        また出てしまう（実機で報告された）。
        """
        text_widget = getattr(self, '_quick_text', None)
        if text_widget is None:
            return 'break'
        self._close_dropdown()

        sel_ranges = ()
        try:
            sel_ranges = text_widget.tag_ranges('sel')
        except Exception:
            sel_ranges = ()

        if sel_ranges:
            try:
                first = str(sel_ranges[0]).split('.')
                last = str(sel_ranges[1]).split('.')
                row1, col1 = int(first[0]), int(first[1])
                row2, col2 = int(last[0]), int(last[1])
            except Exception:
                row1 = row2 = -1
                col1 = col2 = 0
            # 押した場所が選択範囲の中のときだけ、その範囲で候補を出す。
            # 範囲の外（余白など）を押したなら、選択を解除して
            # ふつうのクリックとして扱う。
            inside = False
            try:
                pos = text_widget.index(f'@{event.x},{event.y}')
                inside = (text_widget.compare(pos, '>=', 'sel.first')
                          and text_widget.compare(pos, '<=', 'sel.last'))
            except Exception:
                inside = False
            if inside and row1 == row2 and col2 > col1:
                i = row1 - 1
                if 0 <= i < len(self._quick_units):
                    line_text = text_widget.get(f'{row1}.0', f'{row1}.end')
                    unit = make_range_unit(line_text, self._quick_units[i],
                                           col1, col2)
                    if unit is not None:
                        self._open_quick_dropdown(event, row1, unit)
                        return 'break'
            try:
                text_widget.tag_remove('sel', '1.0', 'end')
            except Exception:
                pass

        hit = self._quick_unit_under_pointer(event)
        if hit is None:
            return 'break'
        row, unit = hit
        if not unit.get('text', '').strip():
            return 'break'
        self._open_quick_dropdown(event, row, unit)
        return 'break'

    def _unit_surroundings(self, unit, units=None):
        """
        候補の並び替えに使う「周辺の語」を、単位から取り出す。

        units（同じ行の全単位）が渡された場合は、対象の前後
        それぞれ2語ずつまで拾って、対象に近い順に並べる。
        渡されない場合は unit が持つ prev / next だけを使う。

        文脈スコアは「近い語ほど重い」重み付けをするので、
        並び順（対象に近い順）を保つことが大切。
        """
        near = []
        if units:
            idx = None
            for i, u in enumerate(units):
                if u is unit or (u.get('start') == unit.get('start')
                                and u.get('end') == unit.get('end')):
                    idx = i
                    break
            if idx is not None:
                # 直前・直後 → 2つ前・2つ後 の順に、近いものから並べる
                for step in (1, 2):
                    for j in (idx - step, idx + step):
                        if 0 <= j < len(units):
                            w = units[j].get('text') or ''
                            if len(w) >= 2 and w not in near:
                                near.append(w)
        if not near:
            for w in (unit.get('prev') or '', unit.get('next') or ''):
                if len(w) >= 2:
                    near.append(w)
        return near

    def _functional_kanji_cands(self, unit, near):
        """
        機能語の単位に出してよい候補（項目48-KC・2026-08-27）。

        助詞・活用語尾に補正候補は出さない（項目48-GL。`の` に9件
        並んだ）——が、**3字以上のかなの塊**は話が別。`わずかな`
        `なぜか` は解析が機能語側に倒すので、48-GL の門がそのまま
        当たって**候補が1つも出なかった**（うにさんの報告・2026-08-27
        「平仮名だからのようですね。この場合は漢字変換候補を並べて
        ください」）。そういう塊には**「漢字にする」候補だけ**出す
        （打ち間違いの推測は出さない——機能語の並びに typo の雑音を
        戻さないため）。

        3つのメニュー（メモ欄・補正欄・簡易入力）が同じ門を持つので、
        **決めているのはこの1か所**（学び22）。
        """
        text = unit.get('base') or unit.get('text') or ''
        if len(text) < 3 or not all('ぁ' <= ch <= 'ゖ' or ch == 'ー'
                                    for ch in text):
            return []
        try:
            cands = build_candidates(
                unit['base'], unit['reading'], self.store,
                find_known_readings_flex, dict_index=self.dict_index,
                context_vec=self.context_vec, surrounding_words=near,
                attested=getattr(self, '_attested_surfaces', None))
        except Exception:
            return []
        return [c for c in cands if c['kind'] == 'kanji']

    def _open_quick_dropdown(self, event, row, unit):
        """
        簡易入力ウィンドウ用の候補一覧。

        本体の _open_dropdown とほぼ同じだが、選んだ結果を
        「別ペインに表示し直す」のではなく、この場でテキストを
        直接書き換える点が異なる（この欄自体が入力欄のため）。
        """
        units_in_row = None
        try:
            units_in_row = self._quick_units[row - 1]
        except Exception:
            units_in_row = None
        near = self._unit_surroundings(unit, units_in_row)

        if unit.get('kind') == 'range' and unit.get('segments'):
            cands = build_range_candidates(
                unit['segments'], self.store, find_known_readings_flex,
                dict_index=self.dict_index,
                context_vec=self.context_vec, surrounding_words=near,
                attested=getattr(self, '_attested_surfaces', None))
        elif unit.get('functional'):
            # **助詞・活用語尾だけの単位に、補正候補は出さない**
            # （項目48-GL）。`の` を押すと
            # `ノア／のく／熨斗／乗せ／のち／乗っ／ノド／伸び／ノ`
            # と9件出ていた（うにさんの「候補も大げさ」）。
            # 記号の候補・元に戻す・引用は下でそのまま足される。
            # **3字以上のかなの塊には「漢字にする」候補だけ出す**
            # （項目48-KC。門は `_functional_kanji_cands` の1か所）。
            cands = self._functional_kanji_cands(unit, near)
        else:
            cands = build_candidates(
                unit['base'], unit['reading'],
                self.store, find_known_readings_flex,
                dict_index=self.dict_index,
                context_vec=self.context_vec,
                surrounding_words=near,
                attested=getattr(self, '_attested_surfaces', None))
        cands = symbol_candidates(unit['text']) + cands

        items = [(f'「{unit["text"]}」', None)]

        rec = self._find_change(self._quick_changes, row, unit)
        if rec is not None:
            before = rec['before']
            items.append((f'↺ 元に戻す（「{before}」）',
                          lambda u=unit, r=row, b=before, k=rec:
                              self._quick_undo_choice(r, u, b, k)))

        # 自動反映（項目48-LR）で書き換わった語なら、メモ欄と
        # **同じ並び**で元へ戻す道を出す（うにさんの報告・
        # 2026-09-07「簡易入力で自動補正された場合、それを
        # 取り消す手段がない」）。並びは `_autofix_menu_items`
        # の1か所（48-GN）。
        _auto = self.autofix_span_at(row, unit['start'], unit['end'],
                                     w=self._quick_text)
        items.extend(self._autofix_menu_items(row, _auto,
                                             w=self._quick_text))

        seen = set()
        # **`samekey` を並べる場所が無かった**（項目48-EF・2026-08-16）。
        #
        # `candidates.symbol_candidates` は `（ → ゆ` `！ → ぬ` を
        # ちゃんと作っていたのに、この並びに `samekey` が無いので
        # **1件も表示されず**、`len(items) <= 1` で候補一覧そのものが
        # 開かなかった。記号を F2 で選ぶと「候補は見つかりません
        # でした」になっていたのはこれ。
        #
        # `probe_c123` の C-4 は `symbol_candidates` を**直に呼んで**
        # 「（ の候補に ゆ」を確かめていたので、緑のまま素通りした
        # （作る側と並べる側の両方があっても、繋がっているとは
        #  限らない。第37回の学びと同じ形）。
        for kind, label in MENU_KINDS:
            rows = [c for c in cands
                   if c['kind'] == kind and c['surface'] != unit['text']
                   and c['surface'] not in seen]
            if not rows:
                continue
            items.append((f'― {label} ―', None))
            for c in rows:
                seen.add(c['surface'])
                items.append((f'  {c["surface"]}',
                              lambda u=unit, r=row, c=c:
                              self._quick_choose_word(r, u, c)))

        # **いちばん下に説明**（項目48-MD）。簡易入力の欄には
        # 打った文字がそのまま出ているので、行はこの欄から取る。
        _src, _why = None, None
        try:
            _src = self._quick_text.get(f'{row}.0', f'{row}.end')
        except Exception:
            _src = None
        try:
            _why = (self._quick_results[row - 1] or {}).get('odd_reasons')
        except Exception:
            _why = None
        items.extend(self._analysis_items(row, unit, src_line=_src,
                                          recorded=_why))

        if len(items) <= 1:
            self.status.config(
                text=f'「{unit["text"]}」の候補は見つかりませんでした')
            return

        try:
            bbox = self._quick_text.bbox(f'{row}.{unit["start"]}')
            if bbox:
                x = self._quick_text.winfo_rootx() + bbox[0]
                y = self._quick_text.winfo_rooty() + bbox[1] + bbox[3]
            else:
                raise ValueError
        except Exception:
            x, y = event.x_root, event.y_root + 12
        self._close_dropdown()
        self._make_dropdown(items, x, y, parent=self._quick_win,
                            topmost=True)

    def _quick_choose_word(self, row, unit, cand):
        """
        簡易入力欄で候補を選んだ。この場でテキストを直接書き換え、
        選んだ結果は本体と共有の choices に記憶する
        （前後の語とセットで学習する点は本体と同じ）。
        """
        text_widget = self._quick_text
        if text_widget is None:
            return
        start = f'{row}.{unit["start"]}'
        end = f'{row}.{unit["end"]}'
        try:
            text_widget.delete(start, end)
            text_widget.insert(start, cand['surface'])
        except Exception:
            return
        self._invalidate_units_cache()
        self.choices.record(unit['base'], cand['surface'],
                            self._choice_reading(unit, cand),
                            unit['prev'], unit['next'])
        self.choices.save()
        self._invalidate_analysis_cache()
        self._remember_recent(cand['surface'])
        self._push_change(self._quick_changes, {
            'row': row, 'start': unit['start'],
            'before': unit['text'], 'after': cand['surface'],
        })
        self._analyze_quick()

    def _quick_undo_choice(self, row, unit, before_text, record=None):
        """
        簡易入力欄で、選び直した内容を元に戻す。

        メモ欄側（_editor_undo_choice）と同じく、**選び直しの記憶も
        取り消す**。記憶が残っていると、本体の補正欄では選び直した
        表記のまま残る（2026-08-10）。
        """
        text_widget = self._quick_text
        if text_widget is None:
            return
        start = f'{row}.{unit["start"]}'
        end = f'{row}.{unit["end"]}'
        try:
            text_widget.delete(start, end)
            text_widget.insert(start, before_text)
        except Exception:
            return
        if record is not None and record in self._quick_changes:
            self._quick_changes.remove(record)
        self._forget_chain(before_text, unit)
        self._analyze_quick()

    # ------------------------------------------------------------
    # タブ管理（Windows 11 メモ帳の操作性を目安にする・2026-08-09）
    # ------------------------------------------------------------
    # 控えの形式は最初からタブの配列（session.py）なので、
    # ここでは「選択中のタブと画面を対応させる」ことだけを行う。
    # タブを切り替えると Undo の履歴はリセットされる（tkinter の
    # Text は履歴を1本しか持てないため）。

    TAB_TITLE_MAX = 14   # タブに出す名前の最大文字数

    def _build_tab_bar(self):
        self.tab_bar = tk.Frame(self.root, bg=BG)
        self.tab_bar.pack(fill='x', padx=16, pady=(10, 0))
        self._refresh_tab_bar()

    # ------------------------------------------------------------
    # **タブの右クリックメニュー**（項目48-TQ・2026-09-07・うにさんの
    # 指定「タブを右クリックしたらメニューを出し、『エクスプローラで
    # 選択』をクリックしたらフォルダを開いて該当のファイルが選択された
    # 状態にする」）。
    #
    # 色は `_apply_theme` が `self._menus` を回って流し込むので、
    # **ここでは色を決めない**（決めているのは最初の行・48-GN）。
    # そのために、作ったら `self._menus` に並べる。

    def _tab_path(self, index):
        """そのタブが指しているファイル。無ければ None。

        **今見ているタブは `self.current_file` が本物**——控え
        （`session.tabs`）へ書き戻すのは `_capture_session` のときなので、
        打っている最中は古いことがある。
        """
        tabs = self.session.tabs or []
        if not (0 <= index < len(tabs)):
            return None
        if index == self.session.active and self.current_file:
            return self.current_file
        return tabs[index].get('path')

    def _tab_menu_items(self, index):
        """タブの右クリックで出す項目（`_make_dropdown` の形）。

        **一覧の形はこのアプリで1つに決まっている**——見出しは
        呼び出しが `None`（選べない灰色）、項目は先頭に半角2つの字下げ
        （`_odd_menu_items` と同じ・48-GN で言うところの「決めているのは
        最初の行」）。
        """
        tabs = self.session.tabs or []
        head = (tab_title(tabs[index]) if 0 <= index < len(tabs) else 'タブ')
        path = self._tab_path(index)
        items = [('― %s ―' % head, None)]
        if path:
            items.append(('  エクスプローラで選択',
                          lambda p=path: self._reveal_in_explorer(p)))
        else:
            # **押せない項目も出す**——「まだ保存していないから使えない」
            # と分かるほうが、項目ごと消えるより親切（48-RG の精神）
            items.append(('  エクスプローラで選択（まだ保存していません）',
                          None))
        return items

    def _on_tab_right_press(self, event, index):
        """タブを右クリック。一覧を出す（項目48-TQ）。"""
        if not (0 <= index < len(self.session.tabs or [])):
            return None
        try:
            self._close_dropdown()
            self._make_dropdown(self._tab_menu_items(index),
                                event.x_root, event.y_root + 12)
        except Exception:
            return None
        return 'break'

    def _reveal_in_explorer(self, path):
        """そのファイルを、エクスプローラで選ばれた状態にする（項目48-TQ）。

        `explorer /select,"道"` は**引数を1つの文字列で渡す**
        （並びで渡すと、空白を含む道が丸ごと引用符で括られて
        エクスプローラが読み違える）。文字列でも Windows では
        シェルを通さないので、記号で悪さはできない。
        """
        if not path:
            return
        path = os.path.normpath(path)
        if not os.path.exists(path):
            messagebox.showinfo(
                APP_TITLE,
                'ファイルが見つかりませんでした:\n%s\n\n'
                '（移動または削除されたようです）' % path)
            return
        try:
            import subprocess
            subprocess.Popen('explorer /select,"%s"' % path)
        except Exception as e:
            messagebox.showerror(
                APP_TITLE, 'エクスプローラを開けませんでした:\n%s' % e)

    def _tab_label_text(self, tab, active):
        if active:
            title = (os.path.basename(self.current_file)
                     if self.current_file else '無題')
            saved = not self._dirty
        else:
            title = tab_title(tab)
            saved = bool(tab.get('saved', True))
        if len(title) > self.TAB_TITLE_MAX:
            title = title[:self.TAB_TITLE_MAX] + '…'
        return ('' if saved else '● ') + title

    def _refresh_tab_bar(self):
        """
        タブバーの表示を今の状態に合わせる。

        タブの数が変わらない限り、既存のウィジェットの文字と色だけを
        更新する。毎回作り直すと、タブ切り替えのたびに一瞬消えて
        から出る（動作の重いタブでは長く消える）ちらつきになる
        （実機で報告・2026-08-09）。
        """
        bar = getattr(self, 'tab_bar', None)
        if bar is None:
            return
        tabs = self.session.tabs or [new_tab()]
        active_i = max(0, min(self.session.active, len(tabs) - 1))
        cache = getattr(self, '_tab_widgets', None)
        if cache is not None and len(cache) == len(tabs):
            try:
                bar.configure(bg=BG)
                for i, tab in enumerate(tabs):
                    w = cache[i]
                    active = (i == active_i)
                    bg = PANEL if active else BG
                    fg = INK if active else MUTED
                    w['frame'].configure(bg=bg)
                    w['label'].configure(
                        text=self._tab_label_text(tab, active),
                        bg=bg, fg=fg)
                    w['close'].configure(bg=bg, fg=fg)
                self._tab_plus.configure(bg=BG, fg=MUTED)
                _wc = getattr(self, '_win_controls', None)
                if _wc is not None:
                    _wc.configure(bg=PANEL)
                    for _b in _wc.winfo_children():
                        _b.configure(bg=PANEL, fg=INK)
                return
            except Exception:
                pass    # 壊れていたら作り直しに落ちる
        self._rebuild_tab_bar(tabs, active_i)

    def _rebuild_tab_bar(self, tabs, active_i):
        """タブの数が変わったときだけ、ウィジェットを作り直す。"""
        bar = self.tab_bar
        try:
            bar.configure(bg=BG)
            for w in bar.winfo_children():
                w.destroy()
        except Exception:
            return
        self._tab_widgets = []
        for i, tab in enumerate(tabs):
            active = (i == active_i)
            bg = PANEL if active else BG
            fg = INK if active else MUTED
            f = tk.Frame(bar, bg=bg)
            f.pack(side='left', padx=(0, 3))
            lb = tk.Label(f, text=self._tab_label_text(tab, active),
                          bg=bg, fg=fg, font=('Yu Gothic UI', 9),
                          padx=10, pady=3, cursor='hand2')
            lb.pack(side='left')
            lb.bind('<Button-1>', lambda e, k=i: self._switch_tab(k))
            # 中クリックで閉じる（ブラウザ・メモ帳と同じ）
            lb.bind('<Button-2>', lambda e, k=i: self._close_tab(k))
            # ドラッグで順序を入れ替える（実機からの要望・2026-08-10）
            lb.bind('<Button-1>',
                    lambda e, k=i: self._on_tab_press(e, k), add=True)
            lb.bind('<B1-Motion>', self._on_tab_drag_motion)
            lb.bind('<ButtonRelease-1>', self._on_tab_drag_end)
            x = tk.Label(f, text='✕', bg=bg, fg=fg,
                         font=('Yu Gothic UI', 8), padx=6, pady=3,
                         cursor='hand2')
            x.pack(side='left')
            x.bind('<Button-1>', lambda e, k=i: self._close_tab(k))
            # **右クリックはメニュー**（項目48-TQ）。札のどこを押しても
            # 同じ——文字・✕・その周りの枠の3つに掛ける（学び22）
            for _w in (f, lb, x):
                _w.bind('<Button-3>',
                        lambda e, k=i: self._on_tab_right_press(e, k))
            self._tab_widgets.append({'frame': f, 'label': lb, 'close': x})
        plus = tk.Label(bar, text='＋', bg=BG, fg=MUTED,
                        font=('Yu Gothic UI', 11), padx=8, pady=1,
                        cursor='hand2')
        plus.pack(side='left')
        plus.bind('<Button-1>', lambda e: self.new_file())
        self._tab_plus = plus

    # ------------------------------------------------------------
    # タブのドラッグによる並べ替え（実機からの要望・2026-08-10）
    # ------------------------------------------------------------
    # タブのウィジェットは「席」であり、表示する中身（session.tabs）
    # だけを入れ替える方式（_refresh_tab_bar が文字と色を席に流し込む）。
    # ドラッグ中はウィジェットを動かさず、tabs の並びを入れ替えて
    # 席の表示を更新するだけなので、ちらつかない。

    # ドラッグとみなす横移動の下限（ピクセル）。クリック（タブ切替）
    # との区別に使う。
    TAB_DRAG_THRESHOLD = 12

    def _on_tab_press(self, event, index):
        """タブの上でボタンが押された。並べ替えの起点を控える。"""
        self._tab_drag = {'from': index, 'x': event.x_root,
                          'moved': False}

    def _on_tab_drag_motion(self, event):
        drag = getattr(self, '_tab_drag', None)
        if drag is None:
            return
        if not drag['moved']:
            if abs(event.x_root - drag['x']) < self.TAB_DRAG_THRESHOLD:
                return
            drag['moved'] = True
        sess = self.session
        cur = drag['from']
        if not (0 <= cur < len(sess.tabs)):
            return
        # ポインタの真下にある「席」を探す（席の中央を境に判定）
        target = None
        for j, w in enumerate(self._tab_widgets or []):
            try:
                left = w['frame'].winfo_rootx()
                width = w['frame'].winfo_width()
            except Exception:
                continue
            if left <= event.x_root < left + width:
                target = j
                break
        if target is None or target == cur:
            return
        tab = sess.tabs.pop(cur)
        sess.tabs.insert(target, tab)
        # 押した時点でそのタブが選択されている（クリックで切り替わる）
        # ため、選択中の位置も一緒に動かす
        sess.active = target
        drag['from'] = target
        self._refresh_tab_bar()

    def _on_tab_drag_end(self, event=None):
        drag = getattr(self, '_tab_drag', None)
        self._tab_drag = None
        if drag and drag.get('moved'):
            self._schedule_session_save()

    def _load_active_tab(self, initial=False):
        """
        選択中のタブの内容を画面へ出す。

        initial=True は起動時（復元直後）。最初の解析は
        _start_warmup が予約するので、ここでは行わない。
        """
        tab = self.session.current() or new_tab()
        # 48-VV: 古いタブの待機・下準備通知は本文を入れ替える前に無効化。
        self._swap_tab_units(tab.get('text', ''))
        self._note_view_change()
        self._tab_warm_gen = getattr(self, '_tab_warm_gen', 0) + 1
        job = getattr(self, '_tab_analysis_job', None)
        if job is not None:
            self.root.after_cancel(job)
            self._tab_analysis_job = None

        # 自動反映の控えは**このタブの本文に結び付いている**ので、
        # 本文を入れ替える前に捨てる。残したままだと、切り替えた先の
        # 行に前のタブの原文が効いてしまう（2026-08-10 の検証で判明）。
        self._autofix_reset()
        # ★★ **F2 で選んだ範囲も、このタブの本文に結び付いている**
        # （項目48-TP''・2026-09-07。v1.6.0 から在った）。
        # 下ろさないと、`_f2_focus_target` の {行, 桁, 桁} が**別のタブの
        # 座標として生き残り**、移った先で Delete を1回押しただけで
        # **その範囲がまとめて消える**（実測: 1字のはずが6字消えた）。
        # 本文を消した時点で色は消えるので、**画面には何の手がかりも無い**。
        self._clear_f2_target()
        self.editor.delete('1.0', 'end')
        self.editor.insert('1.0', tab.get('text', ''))
        # 読み込んだ本文は「打った文字」ではない（項目48-X）。
        # 印を消し、**影も合わせる**。影を合わせ忘れると、
        # 次の解析でタブまるごとが「打った文字」になる。
        self._reset_typed_marks()
        self._pad_blank_lines()

        # タブの中身は「既に書かれた行」なので学習済み扱い
        # （項目46の理屈と同じ）
        self._learned_lines.update(
            l for l in tab.get('text', '').split('\n') if l.strip())

        self.current_file = tab.get('path')
        self._dirty = not tab.get('saved', True)

        # ブックマーク（集合オブジェクトは差し替えない。
        # ガターが参照を持っているため）
        self.bookmarks.clear()
        self.bookmarks.update(tab.get('bookmarks', []))
        try:
            _n_lines = int(self.editor.index('end-1c').split('.')[0])
        except Exception:
            _n_lines = None
        if _n_lines:
            _bad = {b for b in self.bookmarks
                    if not (isinstance(b, int) and 1 <= b <= _n_lines)}
            self.bookmarks.difference_update(_bad)

        try:
            self.editor.mark_set('insert', tab.get('cursor', '1.0'))
            self.editor.see('insert')
        except Exception:
            pass
        try:
            _top0 = int(tab.get('top') or 0)
            if _top0 > 1:
                # 行番号の控えがあれば、最初からそちらで当てる
                # （2026-08-16。割合は折り返しで意味がずれる）
                self.editor.yview(f'{_top0}.0')
            else:
                self.editor.yview_moveto(
                    float(tab.get('scroll', 0.0) or 0.0))
        except Exception:
            pass
        # 48-VT: このタブに今当てた位置を、利用者の移動と区別する。
        # 前タブの値を残すと、after_idleで復元を打ち切ってしまう。
        try:
            self._pending_scroll_applied = self.editor.yview()[0]
        except Exception:
            self._pending_scroll_applied = None
        # **ここで一度動かすだけでは効かない。**
        # 本文を入れた直後の入力欄はまだ配置が済んでおらず、
        # `yview_moveto` が効かずに先頭のままになる（うにさんの
        # 報告・2026-08-11「起動時に、前回終了時の行数から再開して
        # いません」。Xvfb で再現: 控えは 0.516 なのに実際は 0.000）。
        # 配置が済んでから、そして最初の解析が終わってからも
        # もう一度当て直す。
        self._pending_scroll = float(tab.get('scroll', 0.0) or 0.0)
        # 行番号の控え（あれば割合より優先。2026-08-16）
        try:
            self._pending_scroll_top = int(tab.get('top') or 0) or None
        except Exception:
            self._pending_scroll_top = None
        if self._pending_scroll > 0 or self._pending_scroll_top:
            try:
                self.root.after_idle(self._restore_pending_scroll)
            except Exception:
                pass
        self.editor.edit_reset()
        self.editor.edit_modified(False)

        # 解析の下地をリセット（前のタブの結果を引きずらない）
        # 前のタブの分割解析が予約されたままだと、切り替えた直後に
        # そのひと区切りが動き、**前のタブの本文で学習まで走る**
        # （_analyze_text が前のタブのまま残るため）。必ず取り消す。
        self._cancel_analysis_job()
        if self._after_id:
            try:
                self.root.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None
        # 学習の予約も止める（検証レポート 3-C）。
        # 上の2つは取り消していたのに、**同じ学習の流れの最後の1本
        # だけ**が生き残っていた。打鍵から3秒以内にタブを移ると、
        # この予約が**前のタブの本文を握ったまま**発火し、
        # すぐ下で None に戻した _last_learned_text を旧タブの内容で
        # 上書きしてしまう。
        if self._learn_after_id:
            try:
                self.root.after_cancel(self._learn_after_id)
            except Exception:
                pass
            self._learn_after_id = None
        # 入力方式の切り替えに伴う解析し直しの予約も止める（項目48-S）。
        # タブを移った先では、どのみち全行を解析し直すため。
        # 残しておくと、開いたばかりのタブでもう一度全行の解析が
        # 走って二度手間になる。
        if getattr(self, '_imethod_after_id', None):
            try:
                self.root.after_cancel(self._imethod_after_id)
            except Exception:
                pass
            self._imethod_after_id = None
        # ★★ **途中だった解析は捨てずに預ける**（項目48-RY・2026-09-05・
        # うにさんの報告「**タブ移動時に分析をやり直している気が
        # します**」）。控え（`_analysis_cache`）に入るのは**最後の行まで
        # 済んだタブだけ**で、途中で移ると `line_results`・やり残しの行
        # （`_analyze_todo`）をここで全部捨てていた。戻ると `_analyze` は
        # 「前回の控えなし」で**全行やり直し**——見えていた分まで消えて
        # また塗り直す。預けるのは**本文を鍵にした途中の状態**（48-RE と
        # 同じ考え方）。裏にも同じ材料を渡す（裏が続きを進めれば、
        # 戻ったときは控えが当たる）
        try:
            _fg_text = getattr(self, '_analyze_text', '') or ''
            _fg_key = self._analysis_key(_fg_text)
            _fg_todo = list(getattr(self, '_analyze_todo', []) or [])
            _fg_pos = getattr(self, '_analyze_pos', 0) or 0
            _fg_res = list(getattr(self, 'line_results', []) or [])
            _fg_lines = list(getattr(self, '_prev_lines', []) or [])
            if (_fg_key and _fg_todo and _fg_pos < len(_fg_todo)
                    and _fg_res and len(_fg_res) == len(_fg_lines)
                    and not getattr(self, '_analyze_units_only', False)):
                _parked = getattr(self, '_fg_parked', None)
                if _parked is None:
                    _parked = self._fg_parked = {}
                _parked[_fg_key] = {'lines': _fg_lines, 'results': _fg_res,
                                    'todo': _fg_todo[_fg_pos:]}
                while len(_parked) > self.BG_PARKED_MAX:
                    _parked.pop(next(iter(_parked)))
                _bgp = getattr(self, '_bg_parked', None)
                if _bgp is None:
                    _bgp = self._bg_parked = {}
                if _fg_key not in _bgp:
                    _kl = _fg_key.split('\n')
                    _bgp[_fg_key] = {
                        'text': _fg_key, 'lines': _kl,
                        'results': [
                            (_fg_res[_i] if (_i < len(_fg_res)
                                             and _fg_res[_i]
                                             and not _fg_res[_i].get(
                                                 'pending'))
                             else None)
                            for _i in range(len(_kl))],
                        'pos': 0, 'ctx': None}
        except Exception:
            pass
        self.line_results = []
        self._prev_lines = []
        self._analyze_todo = []
        self._analyze_pos = 0
        self._analyze_text = ''
        self._last_learned_text = None

        self._refresh_title()
        # **タブを開いた時点で、空白の印を付ける**（項目48-IF）。
        # 解析の反映を待つと、その間だけ空白が見えなくなる。
        try:
            self._schedule_whitespace_paint(delay=1)
        except Exception:
            pass
        if not initial:
            # **検索ウインドウが開いているなら、焦点はそちらに残す**
            # （項目48-SL）。ここでメモ欄に置いていたのが、うにさんの
            # 報告「タブを移ると本体に焦点が移る」の出どころ
            if not self._find_follow_tab():
                self.editor.focus_set()
            self._tab_warming = True
            self._tab_analysis_job = self.root.after(150, self._resume_tab_analysis)

    def _swap_tab_units(self, text):
        # 48-VW: 描画の控えも本文単位で預ける。別タブの文脈と混ぜない。
        parked = getattr(self, '_tab_units_cache', None)
        if parked is None:
            parked = self._tab_units_cache = {}
        old = self._analysis_key(getattr(self, '_analyze_text', '') or '')
        if old:
            parked.pop(old, None)
            parked[old] = (getattr(self, '_units_cache', {}),
                           getattr(self, '_suspect_units_cache', {}))
        pair = parked.pop(self._analysis_key(text), ({}, {}))
        while len(parked) > 3:
            parked.pop(next(iter(parked)))
        self._units_cache, self._suspect_units_cache = pair

    def _units_are_pending(self):
        return (getattr(self, '_analyze_units_only', False)
                and getattr(self, '_analyze_pos', 0)
                < len(getattr(self, '_analyze_todo', ()) or ()))

    def _window_dragging(self):
        return bool(getattr(self, '_win_drag', None)
                    or getattr(self, '_native_window_drag', False))

    @staticmethod
    def _window_drag_button_down():
        if sys.platform != 'win32':
            return False
        try:
            import ctypes
            u32 = ctypes.windll.user32
            key = 0x02 if u32.GetSystemMetrics(23) else 0x01
            return bool(u32.GetAsyncKeyState(key) & 0x8000)
        except Exception:
            return False

    def _begin_native_window_drag(self):
        self._native_window_drag = True
        self._note_view_change()
        if getattr(self, '_window_drag_poll_job', None) is None:
            self._window_drag_poll_job = self.root.after(60, self._poll_window_drag)

    def _poll_window_drag(self):
        self._window_drag_poll_job = None
        if self._window_drag_button_down():
            self._window_drag_poll_job = self.root.after(60, self._poll_window_drag)
            return
        self._native_window_drag = False
        self._note_view_change()

    def _track_window_position(self, event):
        # OSのタイトルバーからの移動も拾う。本文や全行の情報は読まない。
        rect = (event.x, event.y, event.width, event.height)
        previous = getattr(self, '_last_window_rect', None)
        self._last_window_rect = rect
        if previous is not None and previous != rect:
            self._note_view_change()
            if self._window_drag_button_down():
                self._begin_native_window_drag()

    def _note_view_change(self):
        # タブ移動・サイズ変更は、解析よりウインドウの反映を優先する。
        self._view_change_until = time.monotonic() + 0.25
        self._note_interaction()

    def _view_changing(self):
        return (self._window_dragging()
                or time.monotonic() < getattr(self, '_view_change_until', 0.0))

    def _resume_tab_analysis(self):
        self._tab_analysis_job = None
        if self._view_changing():
            self._tab_analysis_job = self.root.after(100, self._resume_tab_analysis)
            return
        self._tab_warming = False
        # 控えの復元には文脈語彙の再解析は要らない。
        self._mark_typed_from_shadow()
        if getattr(self, '_warmup', None) is None:
            text = self.editor_source_text()
            if self._use_analysis_cache(text, text.split('\n')):
                return
        self._warm_then_analyze()

    def _warm_then_analyze(self):
        """
        タブを切り替えた直後の解析の入り口。

        解析の前に必要な「文脈語彙の下ごしらえ」（メモ全文の
        形態素解析）は、行数に比例して重い。タブ切り替えの直後に
        主スレッドでやると、1000行のタブでは切り替えのたびに
        1秒近く画面が固まっていた（実測・2026-08-10。行ごとの
        控え _ctx_vocab_cache は、他のタブを解析した時点で
        落とされているため、戻ってくるたびに掛かる）。

        起動時の _start_warmup と同じ考え方で、下ごしらえだけを
        裏のスレッドで行い、済んでから解析を予約する。控えが
        温かい（未処理の行が少ない）ときは、その場で解析へ進む。
        """
        try:
            lines = self.editor.get('1.0', 'end-1c').split('\n')
        except Exception:
            lines = []
        cache = getattr(self, '_ctx_vocab_cache', None)
        if cache is None:
            cache = self._ctx_vocab_cache = {}
        missing = {l for l in lines if l.strip() and l not in cache}
        # ★★ **控えは「行が入っているか」だけでは温かくない**
        # （項目48-TT''・2026-09-07）。`build_context_vocab_cached` は
        # **語の顔ぶれ（`shape_revision`）が変わったら控えを丸ごと捨てる**
        # ので、行が全部入っていても**次の呼びで作り直しになる**。
        # ここでそれを見ないと「温かい」と判断して主スレッドで解析へ進み、
        # 作り直し（実機で1.2秒）を画面側で払う——起動直後（英単語を
        # 覚え直した直後）がまさにその形だった。
        try:
            # ★ **控えの鍵と同じものを見る**（項目48-UR）。
            # `build_context_vocab_cached` は `shape_revision_ja`
            # （英単語の出し入れでは進まない）で控えを見分けるので、
            # ここが `shape_revision` のままだと**温かい控えを
            # 「冷たい」と見て**、裏のスレッドを無駄に回す。
            _shape = self.store.shape_revision_ja()
        except Exception:
            try:
                _shape = self.store.shape_revision()
            except Exception:
                _shape = None
        if _shape is not None and cache.get('_store_size') != _shape:
            missing = {l for l in lines if l.strip()}
        # どの経路を通っても、前の回の見張りは必ず無効にする。
        # 番号を増やさずに戻ると、古い見張りが生き残って、
        # 別のタブを見ているときに解析を蹴ってしまう。
        gen = self._tab_warm_gen = getattr(self, '_tab_warm_gen', 0) + 1
        self._tab_warming = False

        # 起動直後の下ごしらえ（_start_warmup）がまだ走っているなら、
        # ここでスレッドを増やさない。**下ごしらえは janome の辞書を
        # 読む**ので、2本同時に走らせるのは避けたい（錠前で守っては
        # あるが、待ち合わせが増えるだけで得が無い）。
        # 済んだところで _poll_warmup が解析を始めてくれる。
        if getattr(self, '_warmup', None) is not None:
            return
        if len(missing) <= 100:
            # きっかけの名前は**呼び手が決めていればそれを使う**
            # （`解析の記録.txt` に何で走ったかが残る・48-LO）
            self._analyze_cause = (getattr(self, '_analyze_cause', None)
                                   or 'タブの切り替え')
            self._analyze()
            return
        # 既に下ごしらえのスレッドが走っているなら、増やさずに待つ。
        # タブ移動を連打されると、そのたびにスレッドが増えて
        # 辞書の読み出しが重なる（クラッシュの温床・項目48-p）。
        if getattr(self, '_tab_warm_thread', None) is not None \
                and self._tab_warm_thread.is_alive():
            self._tab_warming = True
            self._tab_warm_wait(gen)
            return
        self._tab_warming = True
        state = {'done': False, 'ctx_cache': {}}

        def _work(state=state, lines=lines):
            try:
                fn = getattr(self.store, '_tokenize_fn', None)
                if fn is None:
                    fn = corrector.make_tokenizer(self.store)
                    self.store._tokenize_fn = fn
                from vocabulary import build_context_vocab_cached
                build_context_vocab_cached(lines, self.store,
                                           state['ctx_cache'])
            except Exception:
                pass
            state['done'] = True

        import threading
        th = threading.Thread(target=_work, daemon=True)
        self._tab_warm_thread = th
        th.start()

        def _poll():
            if getattr(self, '_tab_warm_gen', None) != gen:
                return
            if not state['done']:
                try:
                    self.status.config(text='準備中…（読み書きはできます）')
                except Exception:
                    pass
                self.root.after(50, _poll)
                return
            self._merge_ctx_cache(state['ctx_cache'])
            try:
                self.status.config(text='')
            except Exception:
                pass
            self._tab_warming = False
            self._analyze_cause = (getattr(self, '_analyze_cause', None)
                                   or 'タブの切り替え')
            self._analyze()

        _poll()

    def _tab_warm_wait(self, gen):
        """
        先に走っている下ごしらえのスレッドが終わるのを待ってから、
        いまのタブで下ごしらえをやり直す。

        タブ移動を連打されたときに、スレッドを増やさないための待ち。
        自分より新しい切り替えが起きていれば（番号が変わっていれば）
        黙って降りる。
        """
        if getattr(self, '_tab_warm_gen', None) != gen:
            return
        th = getattr(self, '_tab_warm_thread', None)
        if th is not None and th.is_alive():
            try:
                self.status.config(text='準備中…（読み書きはできます）')
            except Exception:
                pass
            self.root.after(50, lambda: self._tab_warm_wait(gen))
            return
        self._tab_warm_thread = None
        # 待っている間に別のタブへ移っていれば、上の番号の確認で
        # 降りている。ここへ来たのは「いまのタブのまま待ち終えた」
        # 場合なので、改めて下ごしらえからやり直す。
        self._tab_warming = False
        self._warm_then_analyze()

    def _switch_tab(self, index):
        sess = self.session
        if not (0 <= index < len(sess.tabs)):
            return
        cur = max(0, min(sess.active, len(sess.tabs) - 1))
        if index == cur:
            return
        self._capture_session()
        self._prev_active = cur         # 裏が先に進める的（項目48-RY）
        sess.active = index
        self._load_active_tab()
        self._schedule_session_save()

    def _close_tab(self, index=None):
        sess = self.session
        if index is None:
            index = sess.active
        if not (0 <= index < len(sess.tabs)):
            return
        # 今の画面の内容を控えに反映してから判断する
        self._capture_session()
        tab = sess.tabs[index]
        if not is_blank(tab) and not tab.get('saved', True):
            if not self.ask_yes_no(
                    f'「{tab_title(tab)}」には保存していない内容が'
                    f'あります。\nタブを閉じると失われます。\n\n'
                    f'閉じますか？',
                    yes='閉じる', no='キャンセル'):
                return
        need_reload = sess.remove_tab(index)
        if need_reload:
            self._load_active_tab()
        else:
            self._refresh_tab_bar()
        self._schedule_session_save()

    def _next_tab(self, step=1):
        sess = self.session
        if len(sess.tabs) < 2:
            return
        cur = max(0, min(sess.active, len(sess.tabs) - 1))
        self._switch_tab((cur + step) % len(sess.tabs))

    def _on_tab_page_key(self, event=None, step=1):
        """
        **Ctrl+PageDown / Ctrl+PageUp でタブを移る**（項目48-FV）。

        うにさんの指定（2026-08-19）:

            「Ctrl+PageUp, Down でタブ移動させる。
              Ctrl+Tab と Ctrl+PageDown が同じ挙動」

        Ctrl+PageDown＝次のタブ（Ctrl+Tab と同じ）、
        Ctrl+PageUp＝前のタブ（Ctrl+Shift+Tab と同じ）。

        **IME が確定した半角記号を取り違えないこと**（項目48-EH）。
        `!` は Prior、`"` は Next に化ける。`ime_confirmed_char_event`
        は Ctrl が押されているものを除くので、ここでは基本的に
        None が返る（＝本物のキー）。取りこぼしを作らないために
        同じ見分けを通してから動かす。
        """
        if ime_confirmed_char_event(event) is not None:
            return None      # 文字として入れる。'break' しない
        self._next_tab(step)
        return 'break'

    def _build_menubar(self):
        """
        メニューバー。

        普段使わない操作（辞書の取り込み・索引の作成・語彙の追加）は
        ここに収める。初回起動時に自動で実行されるうえ、
        以後は入力から自動で学習するため、通常は触る必要がない。

        Windows の tkinter では、標準の Menu をそのまま
        `root.config(menu=...)` で使うと、**メニューバー本体
        （ファイル/編集/表示/学習の帯そのもの）はOSがネイティブに
        描画するため、bg/fg を設定してもダークモードで白いまま
        残ってしまう**（サブメニュー＝開いたときのドロップダウンは
        きちんと塗り替わるが、帯だけは色を無視される）。
        帯まで塗り替えるため、`Frame` の上に `Menubutton` を並べた
        自作の帯にする。各 `Menubutton` が開くドロップダウン
        （m_file 等）は、これまでどおり `tk.Menu` のまま使い回せる。
        """
        bar = tk.Frame(self.root, bg=PANEL)
        bar.pack(fill='x')
        self._menu_bar_frame = bar

        # タイトルバーを隠す設定のときの窓の操作（右端: ─ ▢ ✕）と、
        # 帯の空き部分のドラッグでの移動・ダブルクリックでの最大化
        # （2026-08-09。「ウインドウ枠部分を消せませんか」への対応）。
        ctrl = tk.Frame(bar, bg=PANEL)
        self._win_controls = ctrl
        for _label, _cmd in (('✕', self._on_close),
                             ('▢', self._toggle_maximized),
                             ('─', self._minimize_window)):
            _b = tk.Label(ctrl, text=_label, bg=PANEL, fg=INK,
                          font=('Yu Gothic UI', 10), padx=12, pady=2,
                          cursor='hand2')
            # メニューと同じ理由で帯いっぱいに（項目48-EE）
            _b.pack(side='right', fill='y')
            _b.bind('<Button-1>', lambda e, c=_cmd: c())
        bar.bind('<ButtonPress-1>', self._start_window_drag)
        bar.bind('<B1-Motion>', self._on_window_drag)
        bar.bind('<ButtonRelease-1>', self._end_window_drag)
        bar.bind('<Double-Button-1>',
                 lambda e: self._toggle_maximized())

        # Menubutton を先に作り、そのドロップダウンは
        # **その Menubutton 自身を親として** 作る。
        # tkinter では menu= に渡すメニューが Menubutton の子で
        # ないと結び付かず、クリックしても何も開かない
        # （実機で「メニューをクリックしても反応しない」と
        #   報告された原因）。
        self._menu_buttons = []

        def _make_menubutton(label):
            btn = tk.Menubutton(
                bar, text=label, bg=PANEL, fg=INK,
                activebackground=ACCENT, activeforeground=PANEL,
                font=('Yu Gothic UI', 9), relief='flat', bd=0,
                padx=10, pady=4)
            # **帯の高さいっぱいに広げる**（項目48-EE・2026-08-16）。
            # うにさんの報告:
            #
            # > 最大化時、メニューの「ファイル」や「編集」ボタンの
            # > **上のほう**にオンマウスすると余白のクリックになる
            #
            # `fill='y'` が無いと、ボタンは帯の中で上下中央に置かれ、
            # **その上に帯（＝窓を動かす場所）の隙間が残る**。
            # 最大化して画面のいちばん上にあるときは、そこが
            # 狙いにくい1〜数ピクセルの帯になり、メニューを押した
            # つもりで窓のドラッグになっていた。
            btn.pack(side='left', fill='y')
            self._menu_buttons.append(btn)
            menu = tk.Menu(btn, tearoff=0)
            btn.configure(menu=menu)
            return btn, menu

        _btn_file, m_file = _make_menubutton('ファイル')
        m_file.add_command(label='新しいタブ', accelerator='Ctrl+N',
                           command=self.new_file)
        m_file.add_command(label='タブを閉じる', accelerator='Ctrl+W',
                           command=self._close_tab)
        m_file.add_command(label='開く…', accelerator='Ctrl+O',
                           command=self.open_file)
        m_file.add_command(label='保存', accelerator='Ctrl+S',
                           command=self.save_file)
        m_file.add_command(label='名前を付けて保存…',
                           command=self.save_file_as)
        m_file.add_separator()
        m_file.add_command(label='補正結果をコピー',
                           command=self.copy_corrected)

        _btn_m_edit, m_edit = _make_menubutton('編集')
        m_edit.add_command(label='検索…', accelerator='Ctrl+F',
                           command=lambda: self.open_find_dialog(False))
        m_edit.add_command(label='置換…', accelerator='Ctrl+H',
                           command=lambda: self.open_find_dialog(True))
        m_edit.add_command(label='次を検索', accelerator='F3',
                           command=self._find_next_shortcut)
        m_edit.add_separator()
        m_edit.add_command(label='語を拾って差し込む (F1)',
                           command=self.toggle_pick_mode)
        m_edit.add_separator()
        # ホットキーが効かない環境でも簡易入力を試せるようにする。
        # 「押しても出ない」ときに、窓自体の問題なのか
        # ホットキーの問題なのかを切り分けられる。
        m_edit.add_command(label='簡易入力ウィンドウを開く',
                           command=lambda: self._open_quick_capture(None))

        _btn_m_view, m_view = _make_menubutton('表示')
        # --- 画面レイアウト ---
        # 2つから1つを選ぶ形なので、チェックではなくラジオにする。
        self.layout_var = tk.StringVar(value=self.settings.get('layout'))
        for key in (LAYOUT_SPLIT, LAYOUT_UNIFIED):
            m_view.add_radiobutton(
                label=LAYOUT_LABELS[key],
                value=key,
                variable=self.layout_var,
                command=self._on_choose_layout,
                selectcolor=ACCENT)
        m_view.add_separator()
        # --- 入力方式 ---
        # 打ち間違いの検査方向がこれで変わる。かな打ちなら JIS かな
        # 配列の隣接キー、ローマ字打ちなら QWERTY の隣接キーで
        # 「元の打鍵」を推測する（実機からの要望）。
        self.input_method_var = tk.StringVar(
            value=self.settings.get('input_method'))
        for key in (INPUT_KANA, INPUT_ROMAJI):
            m_view.add_radiobutton(
                label=INPUT_METHOD_LABELS[key],
                value=key,
                variable=self.input_method_var,
                command=self._on_choose_input_method,
                selectcolor=ACCENT)
        # IME に「いまローマ字入力か、かな入力か」を直接尋ねて、
        # 上の選択を自動で切り替える（Windowsのみ。ime_watch.py）。
        # ペーストは判定できないため、手動の選択も残してある。
        self.input_method_auto_var = tk.BooleanVar(
            value=self.settings.get('input_method_auto'))
        m_view.add_checkbutton(
            label='入力方式をIMEから自動判定（Windows）',
            variable=self.input_method_auto_var,
            command=self._on_toggle_input_method_auto,
            selectcolor=ACCENT)
        m_view.add_separator()
        self.hide_titlebar_var = tk.BooleanVar(
            value=self.settings.get('hide_titlebar'))
        m_view.add_checkbutton(
            label='タイトルバー（OSの枠）を隠す',
            variable=self.hide_titlebar_var,
            command=self._on_toggle_hide_titlebar,
            selectcolor=ACCENT)
        m_view.add_separator()
        # 統合表示のとき、補正を本文へ自動で反映するか
        # （うにさんの指定・2026-08-10。既定オン）。
        self.unified_autofix_var = tk.BooleanVar(
            value=self.settings.get('unified_autofix'))
        m_view.add_checkbutton(
            label='ひとつにまとめた表示で、補正を自動で反映する',
            variable=self.unified_autofix_var,
            command=self._on_toggle_unified_autofix,
            selectcolor=ACCENT)
        # 簡易入力でも、補正を欄の中へ自動で反映するか
        # （うにさんの指定・2026-08-30・項目48-LR。
        # **既定はオン**——項目48-LX で上げた）。
        self.quick_autofix_var = tk.BooleanVar(
            value=self.settings.get('quick_autofix'))
        m_view.add_checkbutton(
            label='簡易入力で、補正を自動で反映する',
            variable=self.quick_autofix_var,
            command=self._on_toggle_quick_autofix,
            selectcolor=ACCENT)
        m_view.add_separator()
        # 不自然な文字列を紫で見せる（項目48-IZ・うにさんの指定・
        # 2026-08-23）。**ここは「判断に迷った箇所（unsure）」の
        # 切り替えが在った場所**。役に立たないという指摘のまま
        # 既定オフで置いてあったので取り払い、**同じ場所**に
        # 異様さの印（`oddness.py`）の切り替えを置いた。
        # **既定はオン。**
        self.show_odd_var = tk.BooleanVar(
            value=self.settings.get('show_odd'))
        m_view.add_checkbutton(
            label='不自然な文字列を紫で表示',
            variable=self.show_odd_var,
            command=self._on_toggle_show_odd,
            selectcolor=ACCENT)
        # 目に見えない空白（半角・全角・タブ）を見せる。
        # **既定はオン**（うにさんの指定・2026-08-21・項目48-IF）。
        self.show_whitespace_var = tk.BooleanVar(
            value=self.settings.get('show_whitespace'))
        m_view.add_checkbutton(
            label='見えない空白（半角・全角・タブ）を表示',
            variable=self.show_whitespace_var,
            command=self._on_toggle_show_whitespace,
            selectcolor=ACCENT)
        # **補正候補に品詞の判定を出す**（項目48-MD・うにさんの指定・
        # 2026-08-31。**既定オフ**）。オンのときは、候補が1つも
        # 無い語でも一覧を開く（「－ 品詞判定 －」だけが見える）。
        # **なかなか進まない開発を分析するため**の窓。
        self.show_pos_info_var = tk.BooleanVar(
            value=self.settings.get('show_pos_info'))
        m_view.add_checkbutton(
            label='補正候補に品詞の判定を表示する',
            variable=self.show_pos_info_var,
            command=self._on_toggle_show_pos_info,
            selectcolor=ACCENT)
        # **そのひとつ下**（うにさんの指定の並びのまま）。
        # 「－ 品詞判定 －」の下に「－ 補正根拠 －」を足す。
        self.show_reason_info_var = tk.BooleanVar(
            value=self.settings.get('show_reason_info'))
        m_view.add_checkbutton(
            label='補正候補に根拠を表示する',
            variable=self.show_reason_info_var,
            command=self._on_toggle_show_reason_info,
            selectcolor=ACCENT)
        m_view.add_separator()
        self.dark_mode_var = tk.BooleanVar(
            value=self.settings.get('dark_mode'))
        m_view.add_checkbutton(label='ダークモード',
                               variable=self.dark_mode_var,
                               command=self._on_toggle_dark_mode,
                               selectcolor=ACCENT)
        m_view.add_separator()
        self.hotkey_insert_var = tk.BooleanVar(
            value=self.settings.get('hotkey_insert_enabled'))
        self.hotkey_minus_var = tk.BooleanVar(
            value=self.settings.get('hotkey_minus_enabled'))
        m_view.add_checkbutton(
            label='簡易入力ウィンドウ（Ctrl+Insert）',
            variable=self.hotkey_insert_var,
            command=lambda: self._on_toggle_hotkey(
                'insert', self.hotkey_insert_var),
            selectcolor=ACCENT)
        m_view.add_checkbutton(
            label='簡易入力ウィンドウ（Ctrl+Shift+-）',
            variable=self.hotkey_minus_var,
            command=lambda: self._on_toggle_hotkey(
                'minus', self.hotkey_minus_var),
            selectcolor=ACCENT)
        # 簡易入力ウィンドウに出す説明文の表示。
        # ボタン（一時解除）はこれとは別に常に出す。
        self.quick_hint_var = tk.BooleanVar(
            value=self.settings.get('show_quick_hint'))
        m_view.add_checkbutton(
            label='簡易入力の説明を表示',
            variable=self.quick_hint_var,
            command=self._on_toggle_quick_hint,
            selectcolor=ACCENT)
        if not self.hotkeys.supported:
            m_view.add_command(
                label='（この環境ではグローバルホットキーは使えません）',
                state='disabled')
        else:
            m_view.add_command(label='ホットキーの状態を確認…',
                               command=self.show_hotkey_status)

        # --- このアプリについて（「表示」の次・うにさんの指定・
        #     2026-08-10）---
        # 説明書は exe に同梱してあり、ここからいつでも
        # exe と同じフォルダへ書き出して開ける。
        # その下にバージョンを出す（押せない項目として並べる）。
        _btn_m_about, m_about = _make_menubutton('このアプリについて')
        m_about.add_command(label='説明書をHTMLで展開',
                            command=self.open_manual)
        m_about.add_separator()
        m_about.add_command(label=f'バージョン {APP_VERSION}',
                            state='disabled')

        _btn_m_learn, m_learn = _make_menubutton('学習')
        m_learn.add_command(label='補正の判断…',
                            command=self.open_decisions_dialog)
        m_learn.add_separator()
        # 保守用。通常は初回に自動で済むので、階層を1つ下げておく。
        m_maint = tk.Menu(m_learn, tearoff=0)
        m_maint.add_command(label='語彙を追加…',
                            command=self.open_vocab_dialog)
        m_maint.add_command(label='文章から学習…',
                            command=self.learn_from_file_dialog)
        m_maint.add_separator()
        m_maint.add_command(label='辞書を取り込む…',
                            command=self.import_dictionary)
        m_maint.add_command(label='索引を作り直す…',
                            command=self.rebuild_dict_index)
        m_learn.add_cascade(label='辞書と語彙の管理', menu=m_maint)

        self._menus = [m_file, m_edit, m_view, m_about, m_learn, m_maint]

    def _build_ui(self):
        self._build_menubar()
        self._build_tab_bar()

        # --- 上段: ツールバーとブックマークの行を1つにまとめる ---
        # 大見出し「CorrectNote」のラベルは廃止した
        # （タイトルバーに既に出ているので、本文中の表示は不要という
        #   実機からの指定）。空いた分、ブックマークボタンをこの行に
        # 詰めて、開く/保存/コピー相当のボタンと高さを揃える。
        toolbar = tk.Frame(self.root, bg=BG)
        toolbar.pack(fill='x', padx=16, pady=(14, 6))

        # 左側: ブックマークの移動。
        # 「次のブックマーク」の右に、行番号ダブルクリックでも
        # 作れることの案内を添える（ボタンが無いと気付きにくいため）。
        self.bookmarks = set()
        tk.Button(toolbar, text='▲ 前のブックマーク',
                 command=lambda: self._goto_bookmark(forward=False),
                 bg=PANEL, fg=INK, relief='flat', bd=1,
                 font=('Yu Gothic UI', 9), padx=10, pady=4,
                 cursor='hand2').pack(side='left')
        tk.Button(toolbar, text='▼ 次のブックマーク',
                 command=lambda: self._goto_bookmark(forward=True),
                 bg=PANEL, fg=INK, relief='flat', bd=1,
                 font=('Yu Gothic UI', 9), padx=10, pady=4,
                 cursor='hand2').pack(side='left', padx=(6, 0))
        tk.Label(toolbar, text='※行番号ダブルクリックで作成',
                 bg=BG, fg=MUTED, font=('Yu Gothic UI', 8)
                 ).pack(side='left', padx=(8, 0))

        # 「語を拾う」ボタンは左側、行番号の案内のすぐ右に置く
        # （実機からの指定）。
        self.pick_mode_btn = tk.Button(
            toolbar, text='クリックして引用 (F1,=)',
            command=self.toggle_pick_mode,
            bg=PANEL, fg=INK, relief='flat', bd=1,
            font=('Yu Gothic UI', 9), padx=10, pady=4, cursor='hand2')
        self.pick_mode_btn.pack(side='left', padx=(10, 0))

        # 括弧で括るボタン。「クリックして引用」の右に並べる。
        # 選択範囲があればその頭と末尾を括弧で挟み、
        # 選択が無ければ現在のカーソル位置に括弧だけを差し込む。
        # （）は括弧群の左端。選択範囲に全角文字が1つでもあれば
        # 全角の（）、全角が無ければ半角の () で括る
        # （実機からの指定・2026-08-09）。
        tk.Button(
            toolbar, text='（）', command=self._wrap_with_parens,
            bg=PANEL, fg=INK, relief='flat', bd=1,
            font=('Yu Gothic UI', 9), padx=8, pady=4,
            cursor='hand2').pack(side='left', padx=(4, 0))
        for open_ch, close_ch in (('「', '」'), ('『', '』'),
                                  ('【', '】'), ('“', '”')):
            tk.Button(
                toolbar, text=open_ch + close_ch,
                command=lambda o=open_ch, c=close_ch:
                    self._wrap_with_brackets(o, c),
                bg=PANEL, fg=INK, relief='flat', bd=1,
                font=('Yu Gothic UI', 9), padx=8, pady=4,
                cursor='hand2').pack(side='left', padx=(4, 0))

        # 右側: 開く・保存・レイアウト切り替え。
        # 「コピー」ボタンは廃止した（選択してのCtrl+Cで足りるため、
        #   実機からの指定）。右端から詰める pack(side='right') の
        # 都合で、ボタンは「表示させたい並びと逆順」に追加する。
        for label, cmd in [
            ('保存', self.save_file),
            ('開く', self.open_file),
        ]:
            tk.Button(toolbar, text=label, command=cmd,
                      bg=PANEL, fg=INK, relief='flat', bd=1,
                      font=('Yu Gothic UI', 9), padx=12, pady=4,
                      cursor='hand2').pack(side='right', padx=3)
        # レイアウト切り替えの2ボタン（開くボタンの左）
        self.layout_split_btn = tk.Button(
            toolbar, text='左右に並べる', command=self._set_layout_split,
            bg=PANEL, fg=INK, relief='flat', bd=1,
            font=('Yu Gothic UI', 9), padx=10, pady=4, cursor='hand2')
        self.layout_unified_btn = tk.Button(
            toolbar, text='1つにまとめる', command=self._set_layout_unified,
            bg=PANEL, fg=INK, relief='flat', bd=1,
            font=('Yu Gothic UI', 9), padx=10, pady=4, cursor='hand2')
        self.layout_unified_btn.pack(side='right', padx=3)
        self.layout_split_btn.pack(side='right', padx=3)

        # 補正の判断は使用頻度が低いため、メニューだけに残す
        # （ボタンは書きながら頻繁に押すものに絞る）。

        # --- 本体: 左右2ペイン（幅を1:1に固定） ---
        body = tk.Frame(self.root, bg=BG)
        body.pack(fill='both', expand=True, padx=16, pady=(0, 8))
        self._body = body
        # grid で列の重みを揃え、左右がぴったり同じ幅になるようにする
        body.grid_columnconfigure(0, weight=1, uniform='pane')
        body.grid_columnconfigure(1, weight=1, uniform='pane')
        # 右端に、両ペインで共有する縦スクロールバーを1本だけ置く
        # （左右は常に同じ位置を映しているので、スクロールバーも1本でよい。
        #   Windows 11 のメモ帳と同じ、単一の縦スクロールバー）
        body.grid_columnconfigure(2, weight=0)
        body.grid_rowconfigure(0, weight=1)

        # 左: 入力。説明は見出しラベルに載せ、ラベル自体は
        # 先頭からスクロールして離れたら隠す（本文のためにスペースを空ける）。
        #
        # 分割モードでの入力欄の説明。以前は「分割モードの場合」の
        # 見出しを付けていたが、冗長なため外した（実機からの指定）。
        self.EDITOR_HEADER_TEXT = (
            '入力したテキストを表示し、補正候補に色を付けます。'
            '補正後も元のテキストが表示されます')
        # 統合モードでの入力欄の説明。Ctrl+Insert（簡易入力）の
        # 使い方も合わせて案内する。
        #
        # 1行に収めるため、文言はできるだけ短く保つ。長いと
        # 見出しラベルの幅で折り返り、2行になって左右の高さが
        # ずれる（実機で「欄の上の説明テキストが2行になっている」と
        # 報告された）。詳しい使い方は説明書（HTML）に譲り、
        # ここでは操作の要点だけを示す。
        self.UNIFIED_HEADER_TEXT = (
            '確定済みの単語を右クリック（またはF2）で再変換できます。'
            '範囲選択して再変換もできます。Ctrl+Insertで簡易入力が開き、'
            '入力後に閉じるとコピーされ、ペースト可能になります。また、'
            'アプリ内に挿入されます')
        left = tk.Frame(body, bg=BG)
        left.grid(row=0, column=0, sticky='nsew', padx=(0, 1))

        # 高さは通常1行分。語を拾うモードのときだけ、案内文が
        # 長くなるため _start_pick_mode 側で一時的に2行へ広げ、
        # 終了時に _end_pick_mode が1行へ戻す（左右の高さが
        # そこだけずれないよう、両方の見出しを同時に切り替える）。
        # wraplength=0（折り返さない）＋ height=1 で、常に1行に保つ。
        #
        # **width=1 も必ず指定する。** ラベルは既定で「中身の文字列が
        # 収まる幅」を要求する。文言を出し入れするたびにその要求幅が
        # 大きく変わり、grid の列幅（uniform='pane'）の再計算を通じて
        # 本文の折り返し幅まで揺すってしまう。折り返しが変われば
        # 表示行数が変わるので、**先頭が見えた瞬間に見出しが現れ、
        # その拍子に1行目が押し出される**（実機で「1行目を映すと
        # 即座に見えなくなる」と報告された症状）。
        # 幅の要求を1文字分に固定してしまえば、文言の長さは
        # レイアウトに一切影響しない（欄に収まらない分は右端で
        # 見切れるだけ。それは元々の指定どおり）。
        self.editor_header = tk.Label(
            left, text=self.EDITOR_HEADER_TEXT, bg=BG, fg=MUTED,
            font=('Yu Gothic UI', 9), anchor='w', wraplength=0,
            justify='left', height=1, width=1)
        self.editor_header.pack(fill='x', pady=(0, 2))

        left_wrap = tk.Frame(left, bg=RULE)
        left_wrap.pack(fill='both', expand=True)
        self._editor_wrap = left_wrap

        left_inner = tk.Frame(left_wrap, bg=PANEL)
        left_inner.pack(fill='both', expand=True, padx=1, pady=1)

        self.editor = tk.Text(
            left_inner, wrap='word', undo=True,
            bg=PANEL, fg=INK, insertbackground=INK,
            font=EDITOR_FONT, relief='flat',
            padx=14, pady=12, spacing1=2, spacing3=4,
            width=1,   # grid の重みで幅が決まるよう、最小値にしておく
        )
        self.editor_gutter = LineNumberGutter(
            left_inner, self.editor, bookmarks=self.bookmarks,
            on_toggle_bookmark=self._toggle_bookmark,
            on_pick_lines=lambda a, b: self._pick_lines(self.editor, a, b))
        self.editor_gutter.pack(side='left', fill='y')
        self.editor.pack(side='left', fill='both', expand=True)
        self.editor.tag_configure('suspect', background=SUSPECT_BG)
        # **不自然な文字列**（項目48-IR で入れ、48-IZ で紫の意味を
        # これ一本にした）。
        # 色の定義そのものは常に置く（切り替えるのは**塗るかどうか**）。
        self.editor.tag_configure('odd', background=UNSURE_BG)
        # 目に見えない空白の印（項目48-IF）
        self._configure_whitespace_tags()
        # 終端の罫線（項目48-IM）
        self._configure_end_rule_tag()
        # 統合レイアウトでオンマウスした語の背景色
        # （分割レイアウトのとき補正欄がやっていたことと同じ）
        self.editor.tag_configure('hover', background=HOVER_BG)
        # ドラッグ選択時に文字が読めるよう、選択色を明示する
        self.editor.config(selectbackground=EDITOR_SEL_BG, selectforeground=INK)

        # 右: 補正結果。分割モードのときの「補正欄の説明」もここに置く
        # （以前はメモ欄側の見出しに同居させていたが、実機の指定で
        #   補正欄自身の見出しに差し替えた）。
        self.RESULT_HEADER_TEXT = (
            'こちらは入力できません。単語をクリックすると変換を補正します')
        right = tk.Frame(body, bg=BG)
        right.grid(row=0, column=1, sticky='nsew', padx=(1, 0))
        self._result_pane = right

        # 幅を要求しない（width=1）のはメモ欄側の見出しと同じ理由。
        # 文言の長さでレイアウトが揺れないようにする。
        self.result_header = tk.Label(
            right, text=self.RESULT_HEADER_TEXT, bg=BG, fg=MUTED,
            font=('Yu Gothic UI', 9), anchor='w', wraplength=0,
            justify='left', height=1, width=1)
        self.result_header.pack(fill='x', pady=(0, 2))

        right_wrap = tk.Frame(right, bg=RULE)
        right_wrap.pack(fill='both', expand=True)
        self._result_wrap = right_wrap

        right_inner = tk.Frame(right_wrap, bg=RESULT_BG)
        right_inner.pack(fill='both', expand=True, padx=1, pady=1)

        self.result_view = tk.Text(
            right_inner, wrap='word',
            bg=RESULT_BG, fg=INK, relief='flat',
            font=EDITOR_FONT,
            padx=14, pady=12, spacing1=2, spacing3=4,
            state='disabled', cursor='arrow',
            width=1,
        )
        self._apply_tab_stops()      # タブの止まり（項目48-LG）
        self.result_gutter = LineNumberGutter(
            right_inner, self.result_view, bg=RESULT_GUTTER_BG,
            bookmarks=self.bookmarks, on_toggle_bookmark=self._toggle_bookmark,
            on_pick_lines=lambda a, b: self._pick_lines(
                self.result_view, a, b))
        self.result_gutter.pack(side='left', fill='y')
        self.result_view.pack(side='left', fill='both', expand=True)
        # 補正された箇所だけ薄い赤。それ以外は通常の黒文字のまま。
        self.result_view.tag_configure('fixed', foreground=FIXED_FG)
        # ユーザーが選び直した語
        self.result_view.tag_configure('chosen', foreground=ACCENT)
        # オンマウスした語は背景色を変えて、クリックできることを示す
        self.result_view.tag_configure('hover', background=HOVER_BG)
        # 補正の有無を問わず、どの語もクリックで選び直せる。
        # 区切りが実態と合わないとき（ひ/ら/が/なを 等）のために、
        # ドラッグで範囲を選んでから離すと、その範囲で候補を出す。
        self.result_view.bind('<Motion>', self._on_result_motion)
        self.result_view.bind('<Leave>', self._on_result_leave)
        self.result_view.bind('<ButtonPress-1>', self._on_result_press)
        self.result_view.bind('<B1-Motion>', self._on_result_drag_motion)
        self.result_view.bind('<ButtonRelease-1>', self._on_result_release)
        # 補正欄は編集不可（state=disabled）だが、
        # 選択してコピーはできるようにする。
        # disabled の Text は既定のコピー操作が効かないため自分で繋ぐ。
        self.result_view.bind('<Control-c>', self._copy_selection)
        self.result_view.bind('<Control-C>', self._copy_selection)
        self.result_view.bind('<Control-Insert>', self._copy_selection)
        self.result_view.bind('<Button-3>', self._on_result_press)
        # 俯瞰は**補正欄からも入れる**（学び22——片方だけに置くと、
        # そちらを迂回する。分割レイアウトでは補正欄を見ている
        # ことのほうが多い）
        self.result_view.bind(
            '<Double-Button-3>',
            lambda e: self._on_right_double(e, self.result_view))
        self.result_view.bind('<B3-Motion>', self._on_result_drag_motion)
        self.result_view.bind('<ButtonRelease-3>', self._on_result_release)
        self.result_view.tag_configure('sel', background=RESULT_SEL_BG)
        # 焦点を受け取れるようにする（disabled のままでは
        # キー操作が届かず Ctrl+C が効かない）
        self.result_view.config(takefocus=True)

        # ドラッグで選択した範囲が見えなくなる問題への対応:
        # 'fixed'/'chosen'/'hover' などの色付けタグを後から追加すると、
        # 標準の 'sel'（選択時の背景色）タグより上に重なってしまい、
        # 選択していても背景色が変わって見えなくなっていた。
        # 'sel' を最前面に上げて、常に選択の背景色が見えるようにする。
        self.editor.tag_raise('sel')
        self.result_view.tag_raise('sel')

        # --- 縦のスクロールバー（Windows 11 のメモ帳と同じく1本） ---
        self.v_scrollbar = ttk.Scrollbar(
            body, orient='vertical', command=self._on_scrollbar)
        self.v_scrollbar.grid(row=0, column=2, sticky='ns', padx=(4, 0))

        # --- 左右のスクロールを連動させる ---
        self.editor.config(yscrollcommand=self._on_editor_scroll)
        self.result_view.config(yscrollcommand=self._on_result_scroll)

        # --- イベント ---
        self.editor.bind('<KeyRelease>', self._on_change)
        self.editor.bind('<<Paste>>', self._on_change)
        # メモ欄に**直接文字を打ったら**、簡易入力から送った文字の色を
        # 戻す（項目48-GO）。貼り付け・引用はここへ来ない。
        #
        # **いちばん先に張ること。** 同じ欄の `<KeyPress>` の束縛は
        # 張った順に走り、途中の1つが `'break'` を返すと**そこで
        # 打ち切られる**（`_on_ime_ascii_key` は文字を入れたら
        # `'break'` を返す）。あとに張ると届かないことがある。
        #
        # `<KeyRelease>` にも張って二重にしておく。`'break'` は
        # その1つのイベントを止めるだけなので、押した側が打ち切られ
        # ても離した側で拾える。
        self.editor.bind('<KeyPress>', self._on_editor_typed, add=True)
        self.editor.bind('<KeyRelease>', self._on_editor_typed, add=True)
        # 未変換（変換中）の文字をメモ欄と同じ字で描かせる（項目48-LO）。
        # IME の文脈は焦点の移動で作り直されることがあるので、
        # 焦点が来るたびに掛け直す（1回の呼び出しは 0.1ms 程度）。
        self.editor.bind('<FocusIn>',
                         lambda e: self._set_ime_font(), add=True)
        try:
            self.root.after(600, self._set_ime_font)
        except Exception:
            pass
        # 左ボタンは範囲選択に専念させる。
        # 以前は左ドラッグの向きを見てスクロールか選択かを判断して
        # いたが、余白から始めた範囲選択がスクロールと判定されて
        # しまい、選択できなかった（実機で報告された）。
        # スクロールは右ドラッグに移す（下の <Button-3> 系を参照）。
        self.editor.bind('<ButtonRelease-1>', self._on_editor_release)
        # 統合レイアウトのとき、右クリックで候補を出す
        # （分割レイアウトのときは何もしない）
        # 右ボタン: 押したまま動かせばスクロール、動かさずに離せば
        # 候補一覧。タッチパネルの1本指スクロールも、この経路が
        # 右ボタン相当として届くため同じ扱いになる。
        self.editor.bind('<ButtonPress-3>', self._on_editor_right_press)
        # **右ダブルクリックを押し続けている間だけ俯瞰**（2026-08-28・
        # うにさんの指定）。Tk は同じ欄に `<Double-Button-3>` が
        # 張ってあれば2回目の押し下げをこちらへ渡す（`<Button-3>`
        # より細かい束縛が勝つ）。離しは `_drag_release` 1か所で拾う。
        self.editor.bind('<Double-Button-3>',
                         lambda e: self._on_right_double(e, self.editor))
        self.editor.bind('<B3-Motion>', self._on_editor_right_motion)
        self.editor.bind('<ButtonRelease-3>', self._on_editor_right_click)
        self.editor.bind('<Motion>', self._on_editor_motion)
        self.editor.bind('<Leave>', self._on_editor_leave)
        self.editor.bind('<Configure>', self._on_resize)
        self.result_view.bind('<Configure>', self._on_resize)
        # メモ欄で、何も選択していない状態の Ctrl+C は
        # 通常のコピーとしては何もすることが無い（選択が無いため）。
        # その場合は「引用モードを実行する」（実機からの指定）。
        # 選択がある場合は、この束縛が 'break' を返さずに素通しし、
        # tkinter 標準のコピー動作をそのまま行わせる。
        self.editor.bind('<Control-c>', self._on_editor_ctrl_c)
        self.editor.bind('<Control-C>', self._on_editor_ctrl_c)

        # **Ctrl+A は、上下の空行を除いて選ぶ**（項目48-FK・
        # うにさんの指定・2026-08-18「Ctrl+Aで全選択する際は、
        # 改行だけの上下の余白を除外する」）。
        # tkinter の既定は 1.0〜end で、書き出しや末尾に残った
        # 空行までコピーに付いてくる。
        self.editor.bind('<Control-a>', self._on_select_all)
        self.editor.bind('<Control-A>', self._on_select_all)
        self.editor.bind('<<SelectAll>>', self._on_select_all)

        # **Shift+スペースで行の中身を選ぶ／Ctrl+スペースで
        # ブックマークを付け外しする**（項目48-OD・2026-09-02・
        # うにさんの指定）。どちらも**空白は入れない**（'break'）。
        # 補正欄（`result_view`）でも同じに使える——行番号を
        # クリックして選ぶのと同じで、片方で押せばもう片方にも効く。
        # **`_ime_first` で包む**（項目48-SZ'）。`映`（U+6620）の確定は
        # キー名 `space` で届き、Shift を押したままなら `<Shift-space>` に
        # 掛かる（実機で「反映されません」の確定が行を消した）
        for _w in (self.editor, self.result_view):
            try:
                _w.bind('<Shift-space>',
                        self._ime_first(self._on_select_line_text))
                _w.bind('<Control-space>',
                        self._ime_first(self._on_toggle_bookmark_key))
            except Exception:
                pass

        for _w in (self.result_view,):
            try:
                _w.bind('<Control-a>', self._on_select_all)
                _w.bind('<Control-A>', self._on_select_all)
                _w.bind('<<SelectAll>>', self._on_select_all)
            except Exception:
                pass

        # **人が触っている印を拾う**（項目48-FL）。
        # 解析中のスクロール・ドラッグ・ウインドウ移動が重い、という
        # うにさんの指摘への対処。触っている間だけ解析の手を緩める。
        # `add='+'` なので、既にある束縛はそのまま動く。
        # **右ボタンも「触っている」**（項目48-SY・2026-09-06・うにさんの
        # 報告「右ダブルクリックの縮小モードでは、重いタブだと元に戻る
        # 範囲は表示されませんし、マウスドラッグしてもスクロール表示が
        # 反映されません」）。右ドラッグ＝スクロール・右ダブルクリック＝
        # 俯瞰なのに、右ボタンの動きはこの一覧に無く、解析の一区切り
        # （1行 100ms・20行）が主スレッドを取り続けて、枠の付け直し
        # （60ms ごとの予約）も描き直しも順番待ちになっていた
        for _ev in ('<MouseWheel>', '<Button-4>', '<Button-5>',
                    '<B1-Motion>', '<ButtonPress-1>', '<Key>',
                    '<ButtonPress-3>', '<B3-Motion>', '<Double-Button-3>',
                    '<ButtonRelease-3>',
                    '<Configure>'):
            try:
                self.root.bind_all(_ev, self._note_interaction, add='+')
            except Exception:
                pass

        # --- 語を拾って差し込むモード ---
        # 対象は常にメモ欄（result_view からは開始できない）。
        # bind_all だけでなく editor にも直接バインドしておく
        # （tk.Text がクラスバインドとして独自の処理を持つ場合の保険）。
        self.root.bind_all('<F1>', self._on_pick_key)
        # 欄そのものへの束縛は Tk の文字入力より先に走るので、
        # IME が確定した `p` を受け取る入口を分ける（項目48-EH）。
        self.editor.bind('<F1>', self._on_pick_key_widget)
        # **候補一覧が開いていなくても、F2 で選んだ範囲を操作できる**
        # （項目48-ED・2026-08-16）。
        #
        # C-1（文字を打つと範囲の後ろへ）・C-2（Delete で範囲を消す）・
        # C-3（Shift+左右で範囲を伸び縮み）は、**候補一覧の Listbox に
        # 束縛してあった**。語なら一覧が開いて焦点がそちらへ移るので
        # 効くが、**記号（）！？は候補が無くて一覧が開かない**ため、
        # 焦点がメモ欄に残って1つも効かなかった（Xvfb で実測。
        # 記号のときは打った文字が**元のカーソル位置**に入っていた）。
        #
        # 同じ処理をメモ欄にも束縛する。`_f2_focus_target` が
        # 立っていて、かつ候補一覧が開いていないときだけ働く。
        self.editor.bind('<KeyPress>', self._on_f2_range_keypress,
                         add=True)
        # **キー名を指定した束縛は、`<KeyPress>` の束縛を全部黙らせる**
        # （項目48-IN・2026-08-22）。Tk は同じ欄に `<KeyPress>` と
        # `<Delete>` の両方があると、keysym=Delete の打鍵では
        # **より具体的な `<Delete>` だけ**を呼ぶ。`<KeyPress>` に張った
        # `_on_ime_ascii_key`（IME が確定した `.` を文字として入れる・
        # 項目31/48-EH/48-FY）は**一度も呼ばれなくなっていた**。
        # テンキーの小数点は IME が入っていると `keysym=Delete
        # keycode=46 char='.'` で届く（実機で測った）ので、ここで
        # 横取りされて Tk 標準の「1文字消す」が走っていた。
        # 取り違えの対象になるキー名（`_IME_MISREAD_KEYSYMS`）への
        # 個別束縛は、**必ず `_ime_first` で包む**。F1/F2 は
        # `_on_pick_key_widget` 等が同じ門を中で持っている。
        self.editor.bind('<Delete>', self._ime_first(self._on_f2_range_delete),
                         add=True)
        self.editor.bind('<BackSpace>', self._on_f2_range_delete,
                         add=True)
        self.editor.bind('<Shift-Left>',
                         self._ime_first(
                             lambda e: self._on_f2_range_resize(-1)),
                         add=True)
        self.editor.bind('<Shift-Right>',
                         self._ime_first(
                             lambda e: self._on_f2_range_resize(1)),
                         add=True)
        # **候補一覧が開いていなくても、左右キーで範囲を渡り歩ける**
        # （うにさんの報告・2026-08-27「Shift左右で範囲を狭めてから
        # 左右キーで範囲を変えようとすると、F2モードが解除されることが
        # あります」）。狭めた範囲に候補が無いと一覧が閉じ、焦点が
        # メモ欄に戻る——そこで左右を押すと、今まではただのカーソル
        # 移動になって F2 の記憶が捨てられていた。範囲がある間は
        # 左右キー＝渡り歩き（一覧が開いているときの左右と同じ）。
        self.editor.bind('<Left>',
                         self._ime_first(
                             lambda e: self._on_f2_range_move(-1)),
                         add=True)
        self.editor.bind('<Right>',
                         self._ime_first(
                             lambda e: self._on_f2_range_move(1)),
                         add=True)

        # F2 で候補一覧（右クリックと同じ機能）。
        # マウスを使わずに選び直せるようにする。
        # 範囲を選んでいればその範囲、選んでいなければカーソル位置の語。
        self.root.bind_all('<F2>', self._on_f2_candidates)
        # 欄への束縛は IME が確定した `q` を受け取る入口を分ける
        # （項目48-EH）。
        self.editor.bind('<F2>', self._on_f2_candidates_widget)
        self.result_view.bind('<F2>', self._on_f2_candidates_widget)

        # 簡易入力のホットキーを、アプリ自身の中でも受ける。
        #
        # RegisterHotKey で登録できているあいだ、この打鍵は OS が
        # 横取りするのでここまで届かない。**届いたということは
        # 登録できていない**ということなので、その理由を伝える
        # （メニューでオフなのか、登録が外れているのか）。
        # 詳しくは _on_quick_hotkey_fallback を参照。
        #
        # **キー名（keysym）は環境によって存在しないものがある。**
        # 例えば 'KP_Insert' は Linux の Tk にはあるが Windows の Tk
        # には無く、そのまま bind すると TclError で**起動できなく
        # なる**（実機で発生・2026-08-09）。1つずつ try で包み、
        # 使えない名前は黙って飛ばす。
        for name, seqs in (
                ('insert', ('<Control-Insert>', '<Control-KP_Insert>')),
                ('minus', ('<Control-Shift-minus>',
                           '<Control-Shift-underscore>',
                           '<Control-underscore>'))):
            for seq in seqs:
                # bind_all（'all' タグ）は最後に評価されるため、
                # 途中の束縛が 'break' を返すと届かない。メモ欄には
                # 直接も束縛して、確実に受けられるようにする。
                for target in (self.root.bind_all, self.editor.bind):
                    try:
                        target(
                            seq,
                            lambda e, n=name:
                                self._on_quick_hotkey_fallback(n),
                            add=True)
                    except Exception:
                        pass
        # 並びの束縛が当たらない環境に備えて、打鍵そのものからも見る
        # （_maybe_hotkey_notice_from_key）。
        for target in (self.editor.bind, self.root.bind_all):
            try:
                target('<KeyPress>', self._maybe_hotkey_notice_from_key,
                       add=True)
            except Exception:
                pass

        # 「=」はメモ欄で打ったときだけモードに入る。
        # JIS配列では「=」は独立したキーではなく Shift+「-」で
        # 入力するが、そのぶん打鍵自体は素直に行われるので、
        # 対応する keysym は <Key-equal> のみで良い
        # （以前ここに <Key-plus> 等を予防的に追加していたが、
        #   Shift を伴う別の入力にまで反応してしまい、
        #   「に」と入力しただけでモードに入ったように見える
        #   不具合の原因になっていた。撤去する）。
        #
        # 「=」を押した瞬間にまず「=」の文字そのものを入力し、
        # そのあとでモードに入る（実機からの要望）。
        # Esc または続けて別のキーを押すとモードだけ中断し、
        # 打った「=」はそのまま残す。語を拾えた場合だけ、
        # その「=」を消して拾った文字に差し替える。
        self.editor.bind('<Key-equal>', self._on_equal_key)
        # 以前はここに <Shift-Key-minus> も束縛し、全角入力中に
        # Shift+「-」相当の打鍵が「=」として来ない場合の代替入口に
        # していた。しかしこの束縛は「Shift+半角ハイフンのキー」そのもの
        # を捉えるため、IME入力中に全角の「－」や「。」を打った際、
        # IMEを経由せず直接このハンドラへ飛び込んでしまうことがあり、
        # ハンドラが打とうとした文字を勝手に「＝」へ差し替えてしまう
        # （実機で「全角で-を打つと入力されない」「全角で.を打つと
        #   文字が消える」と報告された。IME合成中に tkinter 側から
        #   insert/delete を行うと、IMEの未確定文字列とバッファが
        #   食い違い、意図しない削除も起こり得る）。
        # 全角確定後の「＝」の検出は、キー押下を奪わない後追いの経路
        # （_on_change → _maybe_start_pick_from_equals。KeyRelease後に
        #   確定済みの文字だけを見る）に一本化し、この束縛は撤去する。
        # かな入力設定でこの経路が働かない場合は F1 で代替する
        # （SPEC.md参照）。
        # 引用モード中のキー監視。Esc での解除もここが受け持つ。
        # 個別に <Key-Escape> を束縛すると <KeyPress> との実行順序が
        # 保証されず、押しても解除されないことがあったため、
        # キー処理の入口を1箇所に集約している。
        # モードに出入りするたびに bind/unbind せず、起動時に一度だけ
        # 張っておく（理由は _on_pick_mode_keypress のdocstring参照）。
        self.editor.bind('<KeyPress>', self._on_pick_mode_keypress, add=True)
        self.result_view.bind('<KeyPress>', self._on_pick_mode_keypress,
                              add=True)
        # IME が確定した半角記号が Delete / 矢印キー等として届く問題への
        # 対処（詳しい理由は ime_confirmed_char の説明を参照）。
        # 文字を伴っているなら、Tk の標準の動き（削除・カーソル移動）を
        # 止めて、その文字を入力する。
        # ウィジェット側の束縛はクラス側の束縛より先に呼ばれるので、
        # ここで 'break' を返せば Tk の Delete の動きは起きない。
        self.editor.bind('<KeyPress>', self._on_ime_ascii_key, add=True)
        # 本文より下の余白を1本指（マウス）でドラッグしたら
        # スクロールする（タッチモニター向け・実機からの要望・
        # 2026-08-09）。本文の上は通常どおり選択ドラッグ。
        # クリックで場所を選び直したなら、括弧の外へ出す待ち構えは
        # やめる（_arm_bracket_exit 参照）。
        self.editor.bind(
            '<Button-1>',
            lambda e: setattr(self, '_bracket_exit', None), add=True)
        # F2 で語を選んでいる最中に本文をクリックして抜けたら、
        # 語の色付けもすぐに消す。候補一覧は焦点を失った時点で
        # keep_target=True で閉じる（括弧ボタンのため記憶を残す）
        # ので、そのままでは次の打鍵まで色が残っていた
        # （実機で報告・2026-08-10）。
        self.editor.bind('<Button-1>', self._clear_f2_on_click, add=True)
        self.result_view.bind('<Button-1>', self._clear_f2_on_click,
                              add=True)
        # 行末より右の余白を押したら、カーソルをその行の末尾に置く
        # （うにさんの報告・2026-08-20・項目48-GN）
        self.editor.bind('<Button-1>', self._on_click_past_line_end,
                         add=True)
        self.editor.bind('<Button-1>', self._on_editor_blank_press,
                         add=True)
        self.editor.bind('<B1-Motion>', self._on_editor_blank_drag,
                         add=True)
        self.editor.bind('<ButtonRelease-1>',
                         self._on_editor_blank_release, add=True)
        # Shift+クリックの範囲選択の起点合わせ。
        # Tk は Shift+クリックで「アンカー（起点マーク）からクリック
        # 位置まで」を選択するが、このマークは選択が消えても昔の
        # 位置に残り続ける。範囲選択を Enter で改行に置き換える等で
        # 選択が消えたあと Shift+クリックすると、今のカーソルではなく
        # 置き換え前の選択の起点（もっと上）から選択されてしまう
        # （実機で報告された症状）。クラス側の束縛より先に呼ばれる
        # ウィジェット側の束縛で、起点を今の状態に合わせ直す。
        self.editor.bind('<Shift-Button-1>', self._on_shift_click_anchor,
                         add=True)
        self.result_view.bind('<Shift-Button-1>', self._on_shift_click_anchor,
                              add=True)
        # 本体側で Esc を押したときの受け皿。
        # 引用モード中ならその解除が優先され（上の監視が 'break' する）、
        # モードでなければここに届く。簡易入力の窓が開いたままなら、
        # 本体に切り替えてから Esc を押しても閉じられるようにする
        # （実機で「入力欄でエスケープを押しても簡易入力が閉じない」と
        #   報告された）。
        self.root.bind_all('<Escape>', self._on_global_escape, add=True)

        # --- ファイル操作のキー割り当て（メモ帳と同じ組み合わせ） ---
        self.root.bind_all('<Control-n>', lambda e: (self.new_file(), 'break')[1])
        self.root.bind_all('<Control-o>', lambda e: (self.open_file(), 'break')[1])
        self.root.bind_all('<Control-s>', lambda e: (self.save_file(), 'break')[1])
        # タブ操作（Windows 11 メモ帳と同じ・2026-08-09）
        self.root.bind_all('<Control-t>', lambda e: (self.new_file(), 'break')[1])
        self.root.bind_all('<Control-w>', lambda e: (self._close_tab(), 'break')[1])
        self.root.bind_all('<Control-Tab>', lambda e: (self._next_tab(1), 'break')[1])
        self.root.bind_all('<Control-Shift-Tab>', lambda e: (self._next_tab(-1), 'break')[1])
        # **Ctrl+PageDown / Ctrl+PageUp でもタブを移る**（項目48-FV・
        # うにさんの指定・2026-08-19「Ctrl+Tab と Ctrl+PageDown が
        # 同じ挙動」）。ブラウザ・エディタで共通の組み合わせ。
        #
        # **IME が確定した半角記号と取り違えないこと**（項目48-EH）。
        # `!`(0x21) は Prior、`"`(0x22) は Next に化けるが、
        # `ime_confirmed_char_event` は Ctrl が押されているものを
        # 除くので、ここに来た時点で本物のキーだと分かる。
        # 念のため同じ見分けを通してから動かす。
        self.root.bind_all('<Control-Next>', self._on_tab_page_key)
        self.root.bind_all('<Control-Prior>',
                           lambda e: self._on_tab_page_key(e, step=-1))
        # Ctrl+Tab は Text のクラス側にフォーカス移動の束縛があり、
        # bind_all まで届かない（実機で「Ctrl+Tab だけ効かない」と
        # 報告された・2026-08-09）。ウィジェット側の束縛はクラス側より
        # 先に呼ばれるので、ここで受けて 'break' する。
        # **PageUp/PageDown も同じ**。Text は Prior/Next に
        # 「1画面スクロール」を持っているので、ウィジェット側で
        # 受けて止めないと、タブが移った先で画面も飛ぶ。
        for _w in (self.editor, self.result_view):
            _w.bind('<Control-Tab>',
                    lambda e: (self._next_tab(1), 'break')[1])
            _w.bind('<Control-Shift-Tab>',
                    lambda e: (self._next_tab(-1), 'break')[1])
            _w.bind('<Control-Next>', self._on_tab_page_key)
            _w.bind('<Control-Prior>',
                    lambda e: self._on_tab_page_key(e, step=-1))

        # --- 検索と置換 ---
        # 一部のIMEは、変換候補の確定操作に Ctrl+F 相当のキーを
        # 割り当てていることがある（Emacs風キーバインド等）。
        # メモ欄で日本語入力中にその確定操作をすると、tkinter には
        # 「Ctrl+f が押された」だけが届き、この束縛が検索ダイアログを
        # 開いてしまう。ダイアログを開く際に検索欄へフォーカスを
        # 移すため、メモ欄側のIME合成が中断されて確定前の文字が
        # 失われる（実機で「非確定を確定した際に検索ウインドウが
        # 出てくる。文字が一部欠ける」と報告された）。
        # IME合成中かどうかを tkinter から直接知る手段は無いため、
        # 「メモ欄で直前に文字が入力された直後かどうか」を目安にし、
        # ごく短い間はダイアログを開くのを見合わせる。
        self.root.bind_all(
            '<Control-f>',
            lambda e: (self._open_find_dialog_guarded(False), 'break')[1])
        self.root.bind_all(
            '<Control-h>',
            lambda e: (self._open_find_dialog_guarded(True), 'break')[1])
        # F3＝次を検索。**IME が確定した `r` は keysym が F3 に化ける**
        # ので、`_on_find_next_key` で見分ける（項目48-EH）。
        # 見分けないと、打った `r` で前回の検索語が探され、
        # 見つかった範囲が**選択されて**次の1字で消える。
        self.root.bind_all('<F3>', self._on_find_next_key)
        self.root.bind_all('<Shift-F3>',
                           lambda e: self._on_find_next_key(e,
                                                            backwards=True))

        # 行番号ガターは、自身の __init__ で <Button-1>/<B1-Motion> に
        # 行選択（クリック・ドラッグ）を実装済み。
        # 以前はここでスクロール判定も add=True で重ねていたが、
        # 両方が競合し、ドラッグすると行選択より先にスクロールが
        # 起きてしまっていた（実機で報告された）。
        # 行番号の役割は行選択に一本化し、スクロールは重ねない。
        # スクロールが必要な場合はホイール、またはメモ欄・補正欄側の
        # 右ドラッグを使う。

        # ホイールはどのペイン上でも、両方の本文＋両方のガターを一緒に動かす。
        # 以前は editor だけに割り当てていたため、行番号や補正結果の上で
        # ホイールを回すとその欄だけが動いていた。
        for w in (self.editor, self.editor_gutter,
                 self.result_view, self.result_gutter):
            w.bind('<MouseWheel>', self._on_wheel)
            # Linux ではホイールが Button-4/5 として届く（環境によっては
            # Windows でも同時に届くことがあるため、両対応にしておく）
            w.bind('<Button-4>', lambda e: self._on_wheel_units(-3))
            w.bind('<Button-5>', lambda e: self._on_wheel_units(3))

        # --- ステータスバー ---
        self.status = tk.Label(self.root, text='', bg=BG, fg=MUTED,
                               font=('Consolas', 9), anchor='w')
        self.status.pack(fill='x', padx=16, pady=(0, 10))

    # ------------------------------------------------------------
    # スクロール連動
    # ------------------------------------------------------------
    def _shift_bookmarks(self, head, old_tail_start, new_tail_start):
        """
        改行の挿入・行の削除で行数が変わったとき、ブックマークの
        行番号を追従させる。

        head: 先頭から何行が変わっていないか（0-indexedの行数）。
        old_tail_start: 変更前のテキストで、末尾一致部分が
            始まる行（0-indexed）。ここより前が「変わった範囲」。
        new_tail_start: 変更後のテキストで、同じ末尾一致部分が
            始まる行（0-indexed）。

        head行目まで（1-indexedで 1..head）はそのまま。
        変わった範囲（head+1 .. old_tail_start）に付いていた
        ブックマークは、その範囲がまるごと置き換わったとみなし、
        範囲の先頭（head+1行目。範囲が無ければ動かさない）に寄せる。
        末尾一致部分（old_tail_start+1 行目以降）のブックマークは、
        行数の増減ぶんだけそのまま平行移動する。
        """
        if not self.bookmarks:
            return
        delta = new_tail_start - old_tail_start
        if delta == 0 and head == old_tail_start:
            return   # 行数・変更範囲ともに無し

        new_bookmarks = set()
        changed = False
        for line in self.bookmarks:
            idx0 = line - 1   # 0-indexed に揃える
            if idx0 < head:
                new_bookmarks.add(line)
            elif idx0 < old_tail_start:
                # 変わった範囲の中。範囲の先頭行に寄せる
                # （範囲がまるごと別の内容に置き換わったとみなす）。
                # ただし新しいテキストがそこまで届いていない
                # （行が減って範囲自体が無くなった）場合は、
                # 直後の残っている行に寄せる。
                changed = True
                target0 = min(head, max(0, new_tail_start - 1))
                new_bookmarks.add(target0 + 1)
            else:
                # 末尾一致部分。行数の増減ぶんだけ平行移動する
                shifted = line + delta
                if shifted != line:
                    changed = True
                new_bookmarks.add(max(1, shifted))

        if new_bookmarks != self.bookmarks:
            self.bookmarks.clear()
            self.bookmarks.update(new_bookmarks)
            changed = True
        if changed:
            try:
                self.editor_gutter.redraw()
                self.result_gutter.redraw()
            except Exception:
                pass
            self._schedule_session_save()

    def _on_toggle_show_odd(self):
        """表示メニュー「不自然な文字列を紫で表示」の切り替え。"""
        try:
            self.settings.set('show_odd',
                              bool(self.show_odd_var.get()))
            self.settings.save()
        except Exception:
            pass
        self._refresh_after_analysis(learn=False)

    def _on_toggle_show_pos_info(self):
        """
        表示メニュー「補正候補に品詞の判定を表示する」の切り替え
        （項目48-MD・2026-08-31）。

        **解析はやり直さない。** これは候補一覧の中身だけを変える
        設定で、補正の答えには何の影響も無い。開いている一覧は
        閉じる（開いたままだと、切り替えの前の中身が残る）。
        """
        try:
            self.settings.set('show_pos_info',
                              bool(self.show_pos_info_var.get()))
            self.settings.save()
        except Exception:
            pass
        self._close_dropdown()
        self.status.config(
            text=('補正候補に品詞の判定を表示します'
                  if self.show_pos_info_var.get()
                  else '補正候補の品詞の判定を表示しません'))

    def _on_toggle_show_reason_info(self):
        """
        表示メニュー「補正候補に根拠を表示する」の切り替え
        （項目48-MD・2026-08-31）。

        **品詞の判定とは別々**（項目48-OC・2026-09-02・うにさんの
        指摘で直した）。もとは「根拠を上げたら品詞も一緒に上げる」
        にしていたが、そのあと**品詞だけ下げると根拠も消えて**いた
        ——押したメニューと違うものが効くのは分かりにくい。
        いまは**押したものだけ**が変わる。
        """
        on = bool(self.show_reason_info_var.get())
        try:
            self.settings.set('show_reason_info', on)
            self.settings.save()
        except Exception:
            pass
        self._close_dropdown()
        self.status.config(
            text=('補正候補に根拠を表示します' if on
                  else '補正候補の根拠を表示しません'))

    def _on_select_line_text(self, event=None):
        """
        **Shift+スペース——その行の中身を選ぶ**（項目48-OD・2026-09-02・
        うにさんの指定「Shift+スペースで、行内を選択できるようにします」）。

        **改行は含めない。** 行番号のクリックで選ぶ形（`_select_lines`）は
        次の行の頭までを選ぶので、コピーすると改行が付いてくる。
        こちらは**行の中身だけ**なので、そのまま貼り直せる。

        既にその行の中身をちょうど選んでいるなら、**前後の空白を
        除いた中身**へ狭める（2回押すと引き締まる）。
        """
        w = event.widget if event is not None else self.target
        try:
            row = int(w.index('insert').split('.')[0])
            head, tail = f'{row}.0', f'{row}.end'
            text = w.get(head, tail)
        except Exception:
            return 'break'
        if not text:
            self.status.config(text='この行は空です')
            return 'break'
        # いま選んでいる範囲
        try:
            cur = (w.index('sel.first'), w.index('sel.last'))
        except Exception:
            cur = None
        s_off = len(text) - len(text.lstrip(' 	　'))
        e_off = len(text.rstrip(' 	　'))
        tight = (f'{row}.{s_off}', f'{row}.{e_off}')
        if cur == (w.index(head), w.index(tail)) and e_off > s_off                 and (s_off, e_off) != (0, len(text)):
            a, b = tight
            msg = f'{row} 行目の中身（前後の空白を除く）を選びました'
        else:
            a, b = head, tail
            msg = f'{row} 行目を選びました（改行は含みません）'
        try:
            w.tag_remove('sel', '1.0', 'end')
            w.tag_add('sel', a, b)
            w.mark_set('insert', b)
            w.see(b)
        except Exception:
            return 'break'
        self.status.config(text=msg)
        return 'break'

    def _on_toggle_bookmark_key(self, event=None):
        """
        **Ctrl+スペース——選んでいる行のブックマークを付け外しする**
        （項目48-OD・2026-09-02・うにさんの指定）。

        選んでいる範囲が複数行にまたがるなら**まとめて**扱う——
        **全部に付いていれば全部外し、そうでなければ全部に付ける**
        （半端な状態から押したときに「揃う」ほうへ動かす）。
        選んでいなければ、カーソルの在る行だけ。
        """
        w = event.widget if event is not None else self.target
        try:
            a = int(w.index('sel.first').split('.')[0])
            b = int(w.index('sel.last').split('.')[0])
            # 選択の終わりが行頭ちょうどなら、その行は含めない
            if w.index('sel.last').split('.')[1] == '0' and b > a:
                b -= 1
        except Exception:
            try:
                a = b = int(w.index('insert').split('.')[0])
            except Exception:
                return 'break'
        rows = list(range(min(a, b), max(a, b) + 1))
        if not rows:
            return 'break'
        if all(r in self.bookmarks for r in rows):
            for r in rows:
                self.bookmarks.discard(r)
            msg = (f'{rows[0]} 行目のブックマークを外しました' if len(rows) == 1
                   else f'{len(rows)} 行のブックマークを外しました')
        else:
            for r in rows:
                self.bookmarks.add(r)
            msg = (f'{rows[0]} 行目にブックマークを付けました' if len(rows) == 1
                   else f'{len(rows)} 行にブックマークを付けました')
        try:
            self.editor_gutter.redraw()
            self.result_gutter.redraw()
        except Exception:
            pass
        self.status.config(text=msg)
        self._schedule_session_save()
        return 'break'

    def _toggle_bookmark(self, line):
        """
        行番号のダブルクリックで、その行のブックマークを付け外しする。

        メモ欄・補正欄の両方のガターが同じ集合（self.bookmarks）を
        参照しているので、片方で操作すればもう片方にも反映される。
        """
        if line in self.bookmarks:
            self.bookmarks.discard(line)
            msg = f'{line} 行目のブックマークを外しました'
        else:
            self.bookmarks.add(line)
            msg = f'{line} 行目にブックマークを付けました'
        self.editor_gutter.redraw()
        self.result_gutter.redraw()
        self.status.config(text=msg)
        self._schedule_session_save()

    def _goto_bookmark(self, forward=True):
        """上下ボタン（またはショートカット）でブックマーク間を移動する。"""
        try:
            current = int(self.editor.index('insert').split('.')[0])
        except Exception:
            current = 1
        target = next_bookmark(current, self.bookmarks, forward=forward)
        if target is None:
            self.status.config(text='ブックマークがありません')
            return
        self._goto_line(target)

    def _goto_line(self, line):
        """指定した行へカーソルを移し、両方のペインをその位置まで送る。"""
        idx = f'{line}.0'
        try:
            self.editor.mark_set('insert', idx)
            self.editor.tag_remove('sel', '1.0', 'end')
            self.editor.see(idx)
        except Exception:
            pass
        try:
            self.result_view.see(idx)
        except Exception:
            pass
        self.editor_gutter.redraw()
        self.result_gutter.redraw()
        self.editor.focus_set()

    def _sync_partner_to_line(self, src, dst):
        """
        src で見えている位置に、dst をぴったり合わせる。

        合わせるものは3段階ある。上から順に効かせる。

          1. 論理行     いちばん上に見えている行を揃える。
                        左右は補正で文字数が変わるぶん折り返しの数が
                        違うので、割合（yview_moveto）では別の行が
                        出てしまう。行で合わせるのが基本。
          2. 折り返し   長い行を途中まで送っている場合、その行の
                        「何本目の折り返し」まで送ったかを揃える。
                        これが無いと、折り返しのある行に差し掛かった
                        とたん補正欄が追従しなくなる（実機で報告）。
          3. 端数の画素 スクロールバーを掴んで動かすと、行の途中の
                        半端な位置で止まる。その端数まで合わせる。
                        （実機で「折り返しが無くても半行ずれる」）

        3 を以前は避けていた。左右が互いに追従し合っていた頃は、
        画素単位で詰めようとすると、その動きが相手の追従を呼んで
        少しずつずれていく振動になったため（SPEC.md「過去の失敗と
        学び」9）。いまは **dst から src を動かす経路を無くした**
        ので、いくら細かく合わせても跳ね返ってこない。振動の条件
        そのものが消えているため、画素まで詰めて構わない。
        """
        try:
            top_index = src.index('@0,0')
            top_line = int(top_index.split('.')[0])
        except Exception:
            return
        try:
            dst_last = int(dst.index('end-1c').split('.')[0])
        except Exception:
            dst_last = top_line
        # dst のほうが行数が少ない場合（解析が追いついておらず
        # 補正欄がまだ短いなど）は、最終行で止める。
        line = max(1, min(top_line, dst_last))

        # --- 1. その行の先頭を上端に置く ---
        try:
            dst.yview(f'{line}.0')
        except Exception:
            return

        # --- 2. 折り返しの何本目まで送っているかを揃える ---
        if line == top_line:
            skipped = self._displaylines_between(src, f'{line}.0', top_index)
            if skipped > 0:
                # dst 側でその行が持つ折り返しの数を超えて送ると、
                # 次の行まで行き過ぎてしまう。行の中に収める。
                avail = self._displaylines_between(dst, f'{line}.0',
                                                   f'{line}.end')
                try:
                    dst.yview_scroll(min(skipped, avail), 'units')
                except Exception:
                    pass

        # --- 3. 端数の画素を詰める ---
        self._align_scroll_pixels(src, dst)

    @staticmethod
    def _displaylines_between(widget, index1, index2):
        """
        2つの位置の間に折り返しが何本あるか（表示行の本数）。

        Tk の count -displaylines を使う。環境によって整数ではなく
        1要素のタプルで返ることがあるため、どちらでも受けられる
        ようにしておく（tkinter のコールバック引数と同じく、
        戻り値の型を決め打ちしない。SPEC.md「過去の失敗と学び」7）。
        """
        try:
            got = widget.count(index1, index2, 'displaylines')
        except Exception:
            return 0
        if isinstance(got, (tuple, list)):
            got = got[0] if got else 0
        try:
            return max(0, int(got or 0))
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _align_scroll_pixels(src, dst):
        """
        上端に見えている行の、画面上の縦位置を揃える。

        スクロールバーを掴んで動かすと行の途中で止まるため、
        行・折り返しを揃えただけでは半行ぶんずれたままになる。
        dlineinfo() が返す y は、行が上へはみ出しているぶんだけ
        負の値になるので、その差だけ dst を画素単位で送る。
        """
        try:
            src_info = src.dlineinfo(src.index('@0,0'))
            dst_info = dst.dlineinfo(dst.index('@0,0'))
        except Exception:
            return
        if not src_info or not dst_info:
            return          # まだ描画されていない。次の機会に合わせる
        delta = dst_info[1] - src_info[1]
        if delta:
            try:
                dst.yview_scroll(delta, 'pixels')
            except Exception:
                pass        # 画素指定に対応しない環境では行単位のまま

    def _on_editor_scroll(self, first, last):
        # 相手側を追従させている最中（_sync_partner_to_line が
        # result_view を動かしている間）は、その動きによって
        # このハンドラ自身が再度呼ばれる。以前はここでガター再描画や
        # ヘッダー表示の切り替えだけは毎回実行してしまっており、
        # それが積み重なって画面がちらつく・縦に揺れるように見える
        # 一因になっていた（実機で報告された）。同期中は早々に
        # 何もせず抜け、無駄な再描画を避ける。
        if self._syncing:
            return
        self.editor_gutter.sync_yview(first, last)
        self.v_scrollbar.set(first, last)
        self._update_header_visibility(first)
        # **画面が動いた。見えた範囲を先に解析する**（項目48-IF）。
        # 空白の印も見えている範囲にしか付いていないので、一緒に塗る。
        try:
            self._on_view_moved()
        except Exception:
            pass
        if self._layout_is_unified():
            # 補正欄は畳まれており、中身も解析のたびに作り直されない。
            # そこへ合わせに行くと、古い（多くは空の）内容の先頭行へ
            # 引きずられる。統合のときは同期そのものを行わない。
            return
        self._syncing = True
        try:
            self._sync_partner_to_line(self.editor, self.result_view)
            self.result_gutter.sync_yview(first, last)
        finally:
            self._syncing = False

    def _on_result_scroll(self, first, last):
        """
        補正欄が動いたときの通知。

        **ここからメモ欄を動かすことは一切しない。**
        補正欄は入力できない表示専用の欄で、動くのは
        「メモ欄に合わせて動かした」ときだけである。その動きを
        メモ欄へ跳ね返すと、左右が互いを押し合って
        「入力のたびに揺れる」「突然1行目に戻る」という症状になる。
        位置を決めるのは常にメモ欄の側（唯一の基準）。
        ここは自分の行番号ガターを引き直すだけにする。
        """
        # **同期中と、字を入れ替えている間は聞かない**
        # （`_on_editor_scroll` と対の門・学び22）。メモ欄が源なので、
        # こちらから戻して引きずってはいけない。片方にしか門が
        # 無かったせいで、字を入れ替えた直後の報せでメモ欄が1行目へ
        # 飛んでいた（2026-08-28・probe_overview で実測）。
        #
        # **字の入れ替えの報せは idle より後にも来る**ので、`_syncing`
        # だけでは足りない（`after_idle` で解いた直後に届いた）。
        # 補正欄はまだ短いことがあり（解析の途中・空）、その行へ
        # 引きずられると、この説明文が言うとおり「突然1行目に戻る」。
        if self._syncing or getattr(self, '_font_swap', False):
            return
        self.result_gutter.sync_yview(first, last)
        # 48-VT: 再描画の通知は利用者のスクロール操作ではない。
        # 遅れて届く通知から入力欄へ戻すと、別タブの位置や短い補正欄の
        # 先頭へ引き戻す。ホイール・右ドラッグは入力欄を直接動かしている。

    def _on_scrollbar(self, *args):
        """
        スクロールバーを動かしたとき。

        メモ欄を動かし、補正欄はその場で行ベースの同期で合わせる。
        yscrollcommand の発火だけに頼ると、環境によって追従が
        走らず「入力欄だけがスクロールする」状態になったため、
        ここから明示的に同期する。
        両方を同じ割合で動かす方式は、折り返し数の違いでずれる。
        """
        self.editor.yview(*args)
        self._sync_partner_to_line(self.editor, self.result_view)
        try:
            self.result_gutter.redraw()
        except Exception:
            pass

    def _update_header_visibility(self, first):
        """
        先頭が見えているときだけ、見出し（説明つき）を表示する。

        スペースを本文に使うため、見出しは常に出しておかず、
        先頭から下へスクロールしたら隠れる（メモ帳の見出しのように
        常駐はしない）。先頭に戻れば再び現れる。

        first は yscrollcommand から渡ってくる値で、Tcl 経由だと
        文字列（例: '0.0'）で届くことがある。header_should_show は
        数値としての比較（<=）を行うため、文字列のまま渡すと
        TypeError になる（実機で確認された。scrollbar.set() は
        Tcl へそのまま渡すので文字列でも動くが、こちらの比較には
        明示的な変換が要る）。
        """
        try:
            first = float(first)
        except (TypeError, ValueError):
            return
        show = header_should_show(first)
        pick_header = getattr(self, '_pick_header', None)
        try:
            is_unified = self._layout_is_unified()
        except Exception:
            is_unified = False
        editor_full_text = (getattr(self, 'UNIFIED_HEADER_TEXT', '')
                            if is_unified
                            else getattr(self, 'EDITOR_HEADER_TEXT', ''))
        pairs = [(getattr(self, 'editor_header', None), editor_full_text),
                (getattr(self, 'result_header', None),
                 getattr(self, 'RESULT_HEADER_TEXT', ''))]
        for label, full_text in pairs:
            if label is None:
                continue
            # 引用モード中の案内文（_start_pick_mode が出す hint）を
            # 上書きしない。ここで書き換えると、モード中にスクロール
            # しただけで案内文が本来のテキストに戻ってしまう。
            if label is pick_header:
                continue
            # 一時的なお知らせ（_flash_editor_header）も同じ理由で
            # 上書きしない。出した直後にスクロールしただけで
            # 消えてしまわないようにする。
            if (label is getattr(self, 'editor_header', None)
                    and getattr(self, '_header_flash', None)):
                continue
            # pack_forget() で見出しラベルそのものを取り除くと、
            # その高さぶんだけ下の Text ウィジェットの表示領域が
            # 広がったり縮んだりする。すると1行目が画面に入った
            # 瞬間にレイアウトが再計算され、直前まで見えていた
            # 1行目がラベルの出現によって隠れてしまう
            # （実機で「1行目を映すと即座に見えなくなる」
            #   「キー操作の後に勝手に動く」と報告された）。
            #
            # ラベル自体は height=1 で常に pack したままにしておき、
            # 表示のオン/オフは中身の文字列を出し入れするだけにする。
            # 高さは文字の有無にかかわらず一定なので、
            # Text ウィジェット側のレイアウトは変化しない。
            wanted = full_text if show else ''
            if label.cget('text') != wanted:
                label.config(text=wanted)

    def _on_wheel(self, event):
        # 両方のペインを同じだけ動かす
        delta = -1 * (event.delta // 120)
        self._on_wheel_units(delta)
        return 'break'

    def _on_wheel_units(self, delta):
        """
        ホイールぶんスクロールする。

        動かすのは **メモ欄だけ** で、補正欄は行を合わせる同期
        （_sync_partner_to_line）で追従させる。

        以前は両方を同じ量だけ yview_scroll していた。すると
          1. メモ欄が delta ぶん動く
          2. その通知で補正欄がメモ欄と同じ行に合わせられる
          3. そのうえで補正欄をさらに delta ぶん動かす
          4. 補正欄の通知が逆流し、メモ欄が補正欄の位置に合わされる
        という往復が起き、1回のホイールで2回ぶん進むうえ、
        補正欄の位置がずれているときはメモ欄がそこへ引きずられた
        （実機で「ホイールでスクロールしていると突然1行目に戻る」）。
        統合レイアウトでは補正欄は畳まれていて中身も古いままなので、
        そちらへ合わせに行くと必ず先頭へ飛ぶ。動かさない。
        """
        was_syncing = self._syncing
        self._syncing = True
        try:
            self.editor.yview_scroll(delta, 'units')
            if not self._layout_is_unified():
                self._sync_partner_to_line(self.editor, self.result_view)
        finally:
            self._syncing = was_syncing
        first, last = self.editor.yview()
        self.v_scrollbar.set(first, last)
        self._update_header_visibility(first)
        self.editor_gutter.sync_yview(first, last)
        self.result_gutter.sync_yview(*self.result_view.yview())
        return 'break'

    def _on_resize(self, event=None):
        if event is not None:
            sizes = getattr(self, '_pane_sizes', None)
            if sizes is None:
                sizes = self._pane_sizes = {}
            key = str(event.widget)
            size = (event.width, event.height)
            if sizes.get(key) == size:
                return  # 位置だけのConfigureでは折り返しも空白の印も変わらない。
            sizes[key] = size
        self._note_view_change()
        job = getattr(self, '_resize_paint_job', None)
        if job is not None:
            self.root.after_cancel(job)
        self._resize_paint_job = self.root.after(120, self._finish_resize)
        self._clamp_zoom_to_workarea()

    def _finish_resize(self):
        self._resize_paint_job = None
        if self._window_dragging():
            self._resize_paint_job = self.root.after(120, self._finish_resize)
            return
        self.editor_gutter.redraw()
        self.result_gutter.redraw()
        self._schedule_whitespace_paint()

    # ------------------------------------------------------------
    # 入力の監視と補正
    # ------------------------------------------------------------
    # ------------------------------------------------------------
    # 「いま打った範囲」の記録（項目48-X）
    # ------------------------------------------------------------
    # うにさんの指定（2026-08-11）:
    # 「補正された単語が全部の各所で書き換わることがだめなので、
    #   **入力した部分は変わってもよい。それ以外の部分で勝手に
    #   補正しない**」
    #
    # 自動反映（_apply_unified_autofix）は、これまで**タブの全行**を
    # 見ていた。1文字打つだけで、遠くの行が4行まとめて書き換わる
    # （977行のタブで実測。probe_writes.py）。うにさんから見れば
    # 「触っていない場所が勝手に変わる」ことになる。
    #
    # **打った文字そのものに印を付ける**。tkinter のタグは文字に
    # くっついて動くので、行が増減しても位置がずれない
    # （行番号で覚えると、上に行を足しただけでずれる）。
    #
    # 印が付くのは:
    #   - 打鍵で変わったところ（1打鍵ぶんずつ union されていく）
    #   - 自動反映が書き換えたところ（その先も直せるように）
    #   - F2・右クリックで選び直したところ
    # 印が付かないのは:
    #   - 読み込んだ本文（起動・タブ切り替え・ファイルを開く）
    #   - **貼り付け**（打った文字ではない。引用を勝手に直さない）
    TYPED_TAG = 'typed'

    # --- 「打った」印の付け方 ---------------------------------------
    #
    # **キーの届き方に頼らない。** 最初は「押した瞬間に控えて、
    # 離した瞬間に比べる」形にしたが、それは Windows の IME が
    # 確定した文字を KeyPress / KeyRelease のどの順で届けるかに
    # 依存する。こちらの環境（Linux・Xvfb）には IME が無いので
    # **確かめようがなく、噛み合わなければ「印が付かない＝一切
    # 直らない」**という、いちばん困る壊れ方をする。
    #
    # そこで**本文の影**（前に見たときの姿）を持ち、解析の直前に
    # 突き合わせる。差が出ていれば、それはうにさんが変えたところ。
    # **どんな届き方でも、変わっていれば必ず拾える。**
    #
    # アプリ自身が書き換えたところは、書き換えた側が影を合わせるか
    # 印を付け直すので、うにさんの入力と取り違えない。

    def _sync_typed_shadow(self):
        """本文の影を、いまの姿に合わせる（印は付けない）。"""
        try:
            self._typed_shadow = self.editor.get('1.0', 'end-1c').split('\n')
        except Exception:
            self._typed_shadow = []

    def _reset_typed_marks(self):
        """
        印を全部消して、影も合わせる。

        本文をまるごと入れ替えたとき（起動・タブ切り替え・
        ファイルを開く）に呼ぶ。**影を合わせ忘れると、次の解析で
        タブまるごとが「打った文字」になる**ので、必ず対で行う。
        """
        self._clear_typed_marks()
        self._sync_typed_shadow()

    def _mark_typed_from_shadow(self):
        """
        影と今を突き合わせて、変わったところに「打った」印を付ける。

        行の増減にも耐える:
          1. 頭と尻の**同じ行**を落として、変わった範囲の行を出す
          2. その範囲だけを改行込みで繋ぎ、**文字単位**で
             頭と尻の同じところを落とす
          3. 残った真ん中が、変わったところ

        Enter を打った場合は、真ん中がほぼ改行1文字になるので、
        余計な行に印が付かない。
        """
        old = getattr(self, '_typed_shadow', None)
        if old is None:
            self._sync_typed_shadow()
            return
        try:
            new = self.editor.get('1.0', 'end-1c').split('\n')
        except Exception:
            return
        if old == new:
            return
        # 1. 同じ行を頭と尻から落とす
        head = 0
        n = min(len(old), len(new))
        while head < n and old[head] == new[head]:
            head += 1
        tail = 0
        while (tail < n - head
               and old[len(old) - 1 - tail] == new[len(new) - 1 - tail]):
            tail += 1
        o_block = '\n'.join(old[head:len(old) - tail])
        n_block = '\n'.join(new[head:len(new) - tail])
        # 2. 文字単位で頭と尻の同じところを落とす
        span = self._changed_span(n_block, o_block)   # new 側の範囲が要る
        if span is None:
            self._typed_shadow = new
            return
        c_s, c_e = span
        # 3. 文字位置を (行, 桁) に直して印を付ける
        row = head + 1
        col = 0
        pos = 0
        for ch in n_block:
            if c_s <= pos < c_e:
                self._mark_typed(row, col, col + 1)
            if ch == '\n':
                row += 1
                col = 0
            else:
                col += 1
            pos += 1
        self._typed_shadow = new

    def _mark_typed(self, row, start, end):
        """その行の [start, end) に「打った」印を付ける。"""
        if end <= start:
            return
        try:
            self.editor.tag_add(self.TYPED_TAG,
                                f'{row}.{start}', f'{row}.{end}')
        except Exception:
            pass

    def _clear_typed_marks(self):
        """印を全部消す（本文を読み込み直したとき）。"""
        try:
            self.editor.tag_remove(self.TYPED_TAG, '1.0', 'end')
        except Exception:
            pass

    def _typed_span_covers(self, row, start, end):
        """
        その行の [start, end) が、**まるごと**「打った」印の中か。

        一部でもはみ出していれば False。**はみ出した部分は
        うにさんが打っていない文字**なので、書き換えてはいけない。
        """
        if end <= start:
            return True
        try:
            ranges = self.editor.tag_ranges(self.TYPED_TAG)
        except Exception:
            return False
        want = start
        for i in range(0, len(ranges), 2):
            try:
                a = str(ranges[i]).split('.')
                b = str(ranges[i + 1]).split('.')
            except Exception:
                continue
            if int(a[0]) != row or int(b[0]) != row:
                continue
            s, e = int(a[1]), int(b[1])
            if s <= want < e:
                want = e
                if want >= end:
                    return True
        return want >= end

    def _change_is_inside_typed(self, row, before, after):
        """
        `before` を `after` に書き換えると、**打っていない文字に
        手を入れることになるか**。入らないなら True。

        **足すだけの直しに注意**（実測で踏んだ穴）。
        `もじにゅりょく` → `もじにゅうりょく` のように文字を
        足すだけの直しは、消える文字が無いので「変わる範囲」が
        **幅ゼロ**になる。幅ゼロを「収まっている」と数えると、
        打っていない行にも文字を差し込めてしまう。
        差し込む場所の**隣**が打った文字であることを求める。
        """
        span = self._changed_span(before, after)
        if span is None:
            return True         # 変わらない
        s, e = span
        if e > s:
            return self._typed_span_covers(row, s, e)
        # 幅ゼロ（足すだけ）。差し込む場所の隣を見る。
        if not before:
            return False        # 空の行に勝手に足さない
        lo = max(0, s - 1)
        hi = min(len(before), s + 1)
        if hi <= lo:
            return False
        return self._typed_span_covers(row, lo, hi)

    def _typed_ranges_of_row(self, row):
        """その行に付いている「打った」印の一覧 [(start, end), ...]。"""
        out = []
        try:
            ranges = self.editor.tag_ranges(self.TYPED_TAG)
        except Exception:
            return out
        for i in range(0, len(ranges), 2):
            try:
                a = str(ranges[i]).split('.')
                b = str(ranges[i + 1]).split('.')
                if int(a[0]) == row == int(b[0]):
                    out.append((int(a[1]), int(b[1])))
            except Exception:
                continue
        return out

    def _restore_typed_ranges(self, row, ranges, old_text, new_text):
        """
        行を入れ替えたあとに「打った」印を付け直す。

        変わったのは1か所（`_changed_span`）で、そこは**もともと
        打った範囲の中**だったことが分かっている（そうでなければ
        書き換えていない）。だから:

          - 変わった場所より前の印  … そのまま
          - 変わった場所より後ろの印 … 長さの差だけずらす
          - 変わった場所そのもの     … 新しい長さで付け直す
        """
        span = self._changed_span(old_text, new_text)
        if span is None:
            for s, e in ranges:
                self._mark_typed(row, s, e)
            return
        s0, e0 = span
        delta = len(new_text) - len(old_text)
        e1 = e0 + delta
        for s, e in ranges:
            if e <= s0:
                self._mark_typed(row, s, e)
            elif s >= e0:
                self._mark_typed(row, s + delta, e + delta)
            else:
                self._mark_typed(row, min(s, s0), max(e + delta, e1))
        self._mark_typed(row, s0, e1)

    @staticmethod
    def _changed_span(before, after):
        """
        2つの文字列で、変わっているところ（before 側の範囲）。

        共通の頭と共通の尻を除いた真ん中。離れた場所が2つ変わって
        いれば、その**両方を含む1つの範囲**になる（広めに出る）。
        広めに出るぶんには安全側: 「打った範囲に収まっているか」の
        判定が厳しくなるだけで、打っていない文字を巻き込まない。

        戻り値: (start, end)。同じなら None。
        """
        if before == after:
            return None
        head = 0
        n = min(len(before), len(after))
        while head < n and before[head] == after[head]:
            head += 1
        tail = 0
        while (tail < n - head
               and before[len(before) - 1 - tail]
               == after[len(after) - 1 - tail]):
            tail += 1
        return head, len(before) - tail

    # ------------------------------------------------------------------
    # **消えたときの証拠を残す見張り**（項目48-SZ・2026-09-06）。
    # うにさんの報告「折り返し後に文字を確定すると、それまでの行の文字が
    # すべて消されることがあります」。IMM32 で確定を起こす再現
    # （`tools_local/probe_ime_wrap.py`: 折り返す行・境目・解析中・統合の
    # 自動反映・Home/F2 に化ける半角）では消えなかった。**起きたときの
    # 証拠が要る**——打鍵のたびに「いまの行」を控え、次の打鍵で行が
    # 6字以上縮んでいて、それが消すキー（BackSpace・Delete・Ctrl）では
    # ないとき、直前の打鍵12件・IME の状態・カーソル・折り返しの位置を
    # `deletion_log.txt`（app_dir・.gitignore 済み）に書く。
    # 本文そのものは1行（120字まで）だけ。動きは何も変えない。
    #
    # ★★ **この記録は、アプリに書かれている文字と命運を共にする**
    # （項目48-TM・2026-09-07・うにさんの指定）:
    #
    #     「打鍵と本文を時刻つきの件は、**本文にない履歴が問題**であって、
    #       **アプリ内に打った文字の情報が残ることは構いません**。
    #       **アプリ内の文字を消したら連動して履歴が消えれば**よいです」
    #
    # ＝ 問題なのは「書いたものと切り離されて溜まる履歴」であって、
    # **いま書かれている本文についての情報**なら残ってよい。
    # だから止めるのではなく、**本文から消えたら落とす**
    # （`_sz_prune_log`）。`ime_readings.keep_only_in`（項目48-QM・
    # 「アプリの文字が消えれば打ったキー情報も消えます」）と**同じ形**——
    # **同じ意味の仕組みを2つ作らない**ので、掃除の口も同じ場所に並べる。
    #
    # ★ 一度「既定で切」にしたが、それは行き過ぎだった（2026-09-07 に正された）。
    _SZ_SHRINK_MIN = 6
    _SZ_KEEP = 12

    def _sz_note_key(self, event):
        """メモ欄への KeyPress を12件だけ控える（項目48-SZ）。"""
        try:
            import time as _t
            buf = getattr(self, '_sz_keys', None)
            if buf is None:
                buf = self._sz_keys = []
            try:
                sel = bool(self.editor.tag_ranges('sel'))
            except Exception:
                sel = False
            buf.append((round(_t.monotonic(), 3),
                        getattr(event, 'keysym', ''),
                        getattr(event, 'keycode', 0),
                        repr(getattr(event, 'char', '')),
                        getattr(event, 'state', 0), sel))
            del buf[:-self._SZ_KEEP]
        except Exception:
            pass

    def _sz_snapshot(self):
        try:
            idx = str(self.editor.index('insert'))
            row = int(idx.split('.')[0])
            line = self.editor.get(f'{row}.0', f'{row}.end')
            nlines = int(str(self.editor.index('end-1c')).split('.')[0])
            return {'row': row, 'line': line, 'n': nlines, 'idx': idx}
        except Exception:
            return None

    def _sz_check_shrink(self, event):

        """KeyRelease のあと、控えと比べて行が縮んでいたら証拠を書く。"""
        prev = getattr(self, '_sz_shadow', None)
        now = self._sz_snapshot()
        self._sz_shadow = now
        if prev is None or now is None:
            return
        keysym = getattr(event, 'keysym', '') if event is not None else ''
        try:
            state = int(getattr(event, 'state', 0) or 0)
        except Exception:
            state = 0
        if keysym in ('BackSpace', 'Delete') or state & 0x0004:
            return                      # 消すキー・Ctrl（x・z）は見ない
        lost_line = (prev['row'] == now['row']
                     and len(now['line']) < len(prev['line']) - self._SZ_SHRINK_MIN)
        lost_lines = now['n'] < prev['n'] - 1
        if not (lost_line or lost_lines):
            return
        # 前後の行の共通の頭・尾を除いて、消えた部分だけ取り出す
        a, b = prev['line'], now['line']
        h = 0
        while h < min(len(a), len(b)) and a[h] == b[h]:
            h += 1
        t = 0
        while (t < min(len(a), len(b)) - h
               and a[len(a) - 1 - t] == b[len(b) - 1 - t]):
            t += 1
        gone = a[h:len(a) - t]
        info = []
        try:
            import ime_watch
            hw = self.editor.winfo_id()
            info.append('ime_active=%r' % ime_watch.composition_active(hw))
            got = ime_watch.read_composition(hw) or {}
            info.append('comp=%r result=%r' % (got.get('comp'), got.get('result')))
        except Exception:
            info.append('ime=?')
        try:
            info.append('display_linestart=%s' % self.editor.index(
                f"{now['idx']} display linestart"))
        except Exception:
            pass
        info.append('layout=%s autofix_rounds=%s overview=%s drag=%s f2=%s' % (
            self.settings.get('layout'),
            getattr(self, '_autofix_rounds', None),
            getattr(self, '_overview', None) is not None,
            (getattr(self, '_drag', None) or {}).get('mode'),
            getattr(self, '_f2_focus_target', None) is not None))
        self._sz_log(prev, now, gone, keysym, state, info)

    def _sz_log(self, prev, now, gone, keysym, state, info):
        try:
            import datetime as _dt
            import os as _os
            path = _os.path.join(app_dir(), 'deletion_log.txt')
            keys = getattr(self, '_sz_keys', []) or []
            with open(path, 'a', encoding='utf-8') as f:
                print('=== %s  行 %d  KeyRelease=%s state=%s' % (
                    _dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    now['row'], keysym, state), file=f)
                print('  前 (%d字): %r' % (len(prev['line']), prev['line'][:120]), file=f)
                print('  後 (%d字): %r' % (len(now['line']), now['line'][:120]), file=f)
                print('  消えた: %r' % gone[:120], file=f)
                print('  行数 %d → %d  カーソル %s → %s' % (
                    prev['n'], now['n'], prev['idx'], now['idx']), file=f)
                print('  ' + '  '.join(info), file=f)
                print('  直前の打鍵: ' + repr(keys), file=f)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # **本文に残っていない記録を落とす**（項目48-TM・2026-09-07）。
    # `ime_readings.keep_only_in`（48-QM）と同じ考え方。判定の的は
    # **記録に写した「前」の行**（消える前の、うにさんが打った文字）。
    # その行がどのタブの本文にも無ければ、その記録は
    # 「アプリから消えた文字についての履歴」なので落とす。

    @staticmethod
    def _sz_filter_log(blob, texts):
        """
        記録のかたまり（`deletion_log.txt` の中身）から、**本文に残って
        いるものだけ**を返す（純粋な文字列の処理。見張りが直に叩ける）。

        `texts`: いま開いている全タブの本文。**空の並びなら何もしない**
        （「本文が取れなかった」と「本文が空だ」を分ける・48-QM と同じ）。
        **中身の無い紙が渡されたら全部落とす**（本当に何も書かれていない）。

        記録は `=== ` で始まる行で区切られ、`  前 (N字): <repr>` を持つ。
        **的が読めない記録は落とす**——何が入っているか言えないものを
        残すほうが危ない。
        """
        import ast as _ast
        if not blob:
            return blob
        got = [t for t in (texts or ()) if isinstance(t, str)]
        if not got:
            return blob                   # 取れなかった＝触らない
        body = '\n'.join(got)
        recs, cur = [], []
        for line in blob.split('\n'):
            if line.startswith('=== ') and cur:
                recs.append(cur)
                cur = []
            cur.append(line)
        if cur:
            recs.append(cur)
        kept = []
        for rec in recs:
            if not any(x.strip() for x in rec):
                continue
            anchor = None
            for line in rec:
                st = line.strip()
                if st.startswith('前 ('):
                    _, _, r = st.partition('): ')
                    try:
                        anchor = _ast.literal_eval(r)
                    except Exception:
                        anchor = None
                    break
            if not isinstance(anchor, str) or not anchor.strip():
                continue                  # 的が読めない＝落とす
            if anchor in body:
                kept.append('\n'.join(rec))
        out = '\n'.join(kept)
        return (out.rstrip('\n') + '\n') if out.strip() else ''

    def _sz_prune_log(self):
        """
        `deletion_log.txt` を、いまの本文に残っている記録だけにする。
        **全部落ちたらファイルごと消す**（空の紙を置いておかない）。
        `_prune_ime_readings` と同じ場所から呼ぶ（起動時と保存時）。
        """
        import os as _os
        path = _os.path.join(app_dir(), 'deletion_log.txt')
        if not _os.path.exists(path):
            return
        texts = [tab.get('text', '') or ''
                 for tab in (self.session.tabs or [])]
        try:
            _now = self.editor_source_text()
        except Exception:
            _now = ''
        if _now:
            texts.append(_now)
        if not texts:
            return                        # 紙が1枚も無い＝読み込みの途中
        try:
            with open(path, encoding='utf-8') as f:
                blob = f.read()
        except Exception:
            return
        out = self._sz_filter_log(blob, texts)
        if out == blob:
            return
        try:
            if out.strip():
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(out)
            else:
                _os.remove(path)
        except Exception:
            pass

    def _on_change(self, event=None):
        # 検索ダイアログの誤爆防止（_open_find_dialog_guarded）用に、
        # メモ欄で何か入力があった時刻を控えておく。
        import time
        self._last_editor_change_at = time.monotonic()
        try:
            self._sz_check_shrink(event)    # 消えたときの証拠（項目48-SZ）
        except Exception:
            pass

        # 設計33（1段目）: 自動反映した語が手で消されていないか見張る。
        # 解析（300ms 後）より先——解析が控えを落とすと、消した直後の
        # 姿はもう突き合わせられない。
        try:
            self._design33_watch()
        except Exception:
            pass

        # 目に見えない空白の印を塗り直す（項目48-IF）。
        # 打鍵のたびに走るので、少し待ってからまとめて。
        try:
            self._schedule_whitespace_paint()
        except Exception:
            pass

        # 貼り付けは「打った文字」ではないので印を付けない
        # ＝勝手に直さない（引用をそのまま残せる）。
        # `<<Paste>>` は type='35'（VirtualEvent）。
        # **この束縛は貼り付けの前に走る**（Tk は widget → class の
        # 順に呼ぶ）ので、貼り終わってから影を合わせる。
        # 影を合わせておけば、次の解析で差が出ず、印も付かない。
        if str(getattr(event, 'type', '')) == '35':
            try:
                self.root.after_idle(self._sync_typed_shadow)
            except Exception:
                pass

        # 本文が変わったりカーソルが動いたら、F2 で選んでいた語の
        # 記憶は捨てる（括弧ボタンが古い場所を括らないように）。
        #
        # **ただし F2 そのものの離しキーでは捨てない**（項目48-ED・
        # 2026-08-16）。うにさんの報告:
        #
        # > （）！？のような記号に対して F2 で選択すると、
        # > **すぐに範囲選択が解除されてしまう**
        #
        # 語のときは候補一覧が開いて焦点がそちらへ移るので、
        # メモ欄の `<KeyRelease>` は飛んでこない。**記号は候補が
        # 無くて一覧が開かない**ので焦点がメモ欄に残り、F2 を離した
        # その瞬間に自分で消していた（Xvfb で押し下げと離しを
        # 分けて送って確認）。
        # **Shift+左右（C-3・範囲の伸び縮み）では捨てない**
        # （2026-08-16・実機）。うにさんの報告:
        #
        # > F2で範囲選択している際に、Shift+←を押すと、
        # > 選択が解除されることがあります
        #
        # 押し下げ側（<Shift-Left>）は 'break' で止まるが、
        # **離した側（KeyRelease）はここへ届く**。焦点がメモ欄に
        # 残っている範囲（記号など）では、伸び縮みした直後に
        # ここが自分で消していた。Shift 単体の離しも同じ。
        # **左右キーでは捨てない**（2026-08-27・2度目の報告で形を
        # 変えた）。F2 の範囲がある間、左右キーは**範囲の渡り歩き**
        # （`_on_f2_range_move`）・Shift+左右は伸び縮み（C-3）で、
        # どちらもカーソル移動ではない——だから離しで捨てる理由が
        # 無い。1度目の直し（伸び縮みの印を離しが使い切る形）は、
        # Shift → 左 の順で離す競合は塞いだが、**素の左右で渡り歩く**
        # 形にした今は、印では足りない。左右は無条件に残す。
        # 範囲を捨てるのは、文字を打った・クリックした・Esc のとき
        # （今までどおり）。
        _ks = getattr(event, 'keysym', '')
        if (getattr(self, '_f2_focus_target', None) is not None
                and _ks != 'F2'
                and _ks not in ('Shift_L', 'Shift_R', 'Left', 'Right')):
            self._clear_f2_target()

        # 括った直後に変換を確定した場合、カーソルを括弧の外へ出す
        if getattr(self, '_bracket_exit', None):
            self._maybe_exit_bracket()

        # IME に入力方式（かな/ローマ字）を尋ね、補正の検査方向を
        # 自動で合わせる（Windowsのみ・1秒に1回まで）
        self._auto_detect_input_method()

        # IME が確定した「＝」を後から拾う。
        #
        # 全角入力中は、キーが先に IME に渡るため
        # <Key-equal> も <Shift-Key-minus> も飛んでこない。
        # tkinter が見られるのは「確定した結果の文字」だけなので、
        # 打ち終わった直後に、カーソルの直前が「＝」なら
        # 語を拾うモードに入る、という後追いの判定を行う。
        #
        # なお、かな入力（かなキーで直接ひらがなを打つ設定）では
        # このキーは「ほ」の位置なので、Shift+- では「ほ」が出る。
        # その場合は「＝」が現れないため、ここも反応しない。
        self._maybe_start_pick_from_equals()

        # 打鍵があったら、自動反映の暴走止めを数え直す
        self._autofix_rounds = 0
        # 連続入力中に何度も走らせないよう、少し待ってから解析する
        if self._after_id:
            self.root.after_cancel(self._after_id)
        self._after_id = self.root.after(300, self._analyze_if_changed)
        # 行番号の引き直しも打鍵ごとには行わない。
        # dlineinfo() は「今どう描画されているか」を問い合わせる呼び出しで、
        # 画面に出ている行数ぶん繰り返すため、1打鍵ごとに走らせると
        # 入力の手応えが鈍る（実機で「若干のラグ」と報告された）。
        # 折り返しが変わったときに追従できれば十分なので、
        # 短い間隔でまとめて1回だけ引き直す。
        if getattr(self, '_gutter_after_id', None):
            self.root.after_cancel(self._gutter_after_id)
        self._gutter_after_id = self.root.after(60, self._redraw_gutter_now)
        # 保存済みの内容から変わった印を付け、控えの書き出しも予約する
        self._mark_dirty()

    def _maybe_start_pick_from_equals(self):
        """
        直前に確定した文字が「＝」なら、語を拾うモードに入る。

        ローマ字入力・全角英数入力では、IME が確定した後の文字を
        ここで拾える。

        **かな入力設定のときは、この経路では検出できない。**
        JIS配列のかな入力では Shift+「-」キーの物理位置に
        「ほ」が割り当てられており、IME はキーを「ほ」として
        確定してしまう。tkinter に届く文字は最初から「ほ」であって
        「＝」ではないため、ここで「＝」を待っていても発火しない。
        「ほ」を「＝」の打ち間違いとみなして自動的に置き換えることは
        しない。「ほ」を本当に打ちたい場合と区別する手段が無く、
        誤爆すると書いた文章を勝手に書き換えることになるため。
        この場合は F1 を使う（メモ欄限定・修飾なしの単独キーなので
        IME の変換候補と衝突しない）。
        """
        if getattr(self, '_pick_mode', None):
            return
        try:
            pos = self.editor.index('insert')
            prev = self.editor.get('insert-1c', 'insert')
        except Exception:
            return
        if prev not in ('＝', '='):
            self._last_equals_pos = None
            return
        # 同じ位置の「＝」で繰り返し発動させない
        if getattr(self, '_last_equals_pos', None) == pos:
            return
        self._last_equals_pos = pos

        # 既に打たれている「＝」の前後にマークを置いてからモードに入る。
        # キー押下から入る経路（_on_equal_key）と同じ状態を作る。
        try:
            self.editor.mark_set(self._PICK_EQUALS_START, 'insert-1c')
            self.editor.mark_gravity(self._PICK_EQUALS_START, 'left')
            self.editor.mark_set(self._PICK_EQUALS_END, 'insert')
            self.editor.mark_gravity(self._PICK_EQUALS_END, 'right')
        except Exception:
            return
        self._start_pick_mode(via_equals=True)

    def _redraw_gutter_now(self):
        self._gutter_after_id = None
        try:
            self.editor_gutter.redraw()
        except Exception:
            pass

    def _mark_dirty(self):
        """内容が変わったことを記録し、タイトルに印を出す。"""
        if not self._dirty:
            self._dirty = True
            self._refresh_title()
        self._schedule_session_save()

    def _refresh_title(self):
        """タイトル欄に、ファイル名と未保存の印を出す。"""
        name = (os.path.basename(self.current_file)
                if self.current_file else '無題')
        mark = '*' if self._dirty else ''
        try:
            self.root.title(f'{mark}{name} - {APP_TITLE}')
        except Exception:
            pass
        # タブの見出し（名前・未保存の●）も一緒に追従させる
        try:
            self._refresh_tab_bar()
        except Exception:
            pass

    # 1回のひと区切りで解析する行数。
    # 全行をまとめて解析すると、行数の多いメモでは十数秒のあいだ
    # 画面が固まる（実機で「解析=8.22s」と報告された）。
    # 少しずつに分けて、その合間に画面の描画・キー入力を通す。
    ANALYZE_CHUNK = 20
    # 1回のひと区切りで使ってよい時間（ミリ秒）。
    # これを超えたら行数が残っていても一旦画面へ制御を返す。
    # キー入力の体感を守るための値で、解析の総時間は変わらない。
    ANALYZE_BUDGET_MS = 60
    # これ以下の行数なら、分けずにその場で片付ける
    # （打鍵のたびの1行だけの解析まで遅らせると、かえって
    #   補正結果の出るのが遅く感じられるため）。
    ANALYZE_INLINE_LIMIT = 40

    def _blank_result(self, line):
        """
        まだ解析していない行の、仮置きの結果（補正なし）。

        pending の印を立てておく。描画側はこの印を見て、語の単位の
        組み立て（形態素解析を伴う）を省く。仮置きの行にはどうせ
        補正も選び直しも無いので、文字をそのまま出せば足りる。
        1000行のタブでは、この組み立てだけで切り替えが1秒近く
        固まっていた（実測・2026-08-10）。
        """
        return {'original': line, 'corrected': line, 'changed': False,
                'details': [], 'spans': [], 'original_spans': [],
                'unsure_spans': [], 'pending': True}

    def _cancel_analysis_job(self):
        # **裏のタブの歩みも止める**（項目48-FQ）。本文が変わったり
        # タブを移ったりしたら、裏で作りかけの結果は当てにならない。
        try:
            self._stop_background_tabs()
        except Exception:
            pass
        """途中まで進んでいた分割解析の予約を取り消す。"""
        if getattr(self, '_analyze_job', None):
            try:
                self.root.after_cancel(self._analyze_job)
            except Exception:
                pass
        self._analyze_job = None

    def _analyze_if_changed(self):
        """
        打鍵の後に予約された解析。本文が変わっていなければ何もしない。

        _on_change は矢印・PageDown・PageUp のような「本文を変えない
        キー」の KeyRelease でも呼ばれる。そのたびに _analyze を
        走らせると、文脈語彙の作り直し（メモ全文の走査）が
        スクロールのキーを押すだけで発生し、押してから画面が
        動くまでの間が長くなる（実機で報告・2026-08-08）。
        本文が前回の解析時と同じなら、やり残しの分割解析の続きだけを
        進めて戻る。
        """
        self._after_id = None
        # タブ切り替えの下ごしらえ（_warm_then_analyze）中は待つ。
        # ここで解析へ進むと、下ごしらえの済んでいない全行を
        # 主スレッドで形態素解析することになり、固まる。
        # 済み次第、向こうが _analyze を呼ぶ。
        if getattr(self, '_tab_warming', False):
            return
        # ★★ **起動の下ごしらえの最中も待つ**（項目48-TT'・2026-09-07）。
        # 理由は上と同じ（済み次第 `_poll_warmup` が呼ぶ）ことに加えて、
        # **48-TT で語彙の書き換え（英単語の覚え直し）が裏のスレッドへ
        # 移った**ため。ここで解析へ進むと、書き換えの最中に語彙を
        # 読むことになる（`store.to_list()` を回している最中に
        # `add`／`remove` が走ると落ちる）。
        if getattr(self, '_warmup', None) is not None:
            return
        # **新しい読みの対を覚えたら、覚えている解析結果を捨てる**
        # （設計25(乙)。対は補正の答えを変える）。
        # 確定のたびではなく**手が止まってから**まとめて捨てる。
        # 確定のたびに捨てると、裏で進めているタブの下ごしらえ
        # （項目48-FQ）を毎回止めてしまう。
        if getattr(self, '_ime_pairs_dirty', False):
            self._ime_pairs_dirty = False
            try:
                self._invalidate_analysis_cache()
            except Exception:
                pass
        try:
            text = self.editor_source_text()
        except Exception:
            return
        if text == getattr(self, '_analyze_text', None):
            if (self._analyze_pos < len(self._analyze_todo)
                    and self._analyze_job is None):
                self._schedule_analysis_chunk()
            return
        self._analyze()

    def _analyze(self):
        """
        本文を解析し直す。

        変わった行だけを解析するのは以前と同じだが、対象が多いとき
        （起動直後の全行など）は **少しずつに分けて** 解析する。
        まとめて回すと、その間ずっと画面が固まり、起動が終わらない
        ように見えるため（実機で「解析=8.22s」と報告された）。

        分けている間、まだ解析できていない行は「補正なし」の仮置きで
        表示する。解析が済むにつれて、色づけと補正欄が埋まっていく。
        """
        if self._view_changing():
            job = getattr(self, '_after_id', None)
            if job is not None:
                self.root.after_cancel(job)
            self._after_id = self.root.after(100, self._analyze)
            return
        self._after_id = None
        self._cancel_analysis_job()

        # **ここで「打った」印を付ける**（項目48-X）。
        # 影（前に見たときの姿）と突き合わせ、変わったところに
        # 印を付ける。自動反映はこの解析のあとに走るので、
        # 印はそれまでに揃っていればよい。
        # キーの届き方に頼らないので、IME がどう確定しても拾える。
        self._mark_typed_from_shadow()

        # **解析するのは原文**（打った文字そのもの）。
        # 自動反映が効いていると、画面には直したあとの文字が出ている。
        # そのまま解析すると「直した結果」をさらに直そうとして、
        # 直した文と元の文が行ったり来たりする（実機で「青文字が
        # 0.5秒おきに入れ替わり続ける」と報告・2026-08-10）。
        # 原文を入力にすれば、解析の入力は変わらないので落ち着く。
        text = self.editor_source_text()
        lines = text.split('\n')

        # 解析の記録（項目48-LO）: この解析が**なぜ・どの形で**走ったか
        # を輪の控えに取る。説明の付かない全行解析が起きた瞬間だけ
        # `解析の記録.txt` に書き出す（うにさんの報告・2026-08-30
        # 「解析が終わったあと、行の上のほうで編集をすると、全体の
        # 解析が走る」——写しではどの編集も差分1行で再現しないため、
        # 実機で起きたときに、どの枝が全行へ落としたかを読めるように）。
        _lo_cause = getattr(self, '_analyze_cause', None)
        self._analyze_cause = None
        _lo_had = bool(getattr(self, '_analyze_text', ''))

        # 前回の解析結果の控えが使えるなら、解析そのものを飛ばす
        # （項目48-L）。使えるのは**このタブをまだ一度も解析して
        # いないとき**（起動直後・タブを開いた直後）だけ。
        # 一度でも解析していれば差分処理のほうが速いし、
        # 控えより手元の結果のほうが新しい。
        #
        # **「まだ一度も解析していない」の見方は `_analyze_text` の
        # ほう**（項目48-CO）。`_prev_lines` が空かどうかで見ていた
        # 頃は、**判断が変わったので解析し直す**道（`_reanalyze_all`）
        # がここへ落ちてきた。あちらは `_prev_lines` を空にするが
        # `_analyze_text` は残すので、二つは同じ意味ではない。
        # 落ちてくると `_use_analysis_cache` が**さっきの答え**を
        # そのまま拾い、「もう直さない」と言われた直後に同じ補正を
        # 出し続けた（Xvfb の本物の画面で実測・2026-08-13）。
        #
        # 起動直後は `_analyze_text` が ''、タブを移ったときも
        # `''` に戻す（`_switch_tab` 参照）ので、48-L / 48-M が
        # 効かせたい場面はそのまま残る。
        if not getattr(self, '_prev_lines', None) \
                and not getattr(self, '_analyze_text', '') \
                and self._use_analysis_cache(text, lines):
            return
        # ★★ **預けてあった途中の状態から続ける**（項目48-RY）。控えが
        # 無くても、途中で移ったタブなら `_load_active_tab` が預けた
        # `line_results`・やり残しの行が在る。それを前回の結果として
        # 置き直せば、下の差分の道が**やり残しだけ**を解析する。
        # 裏（48-RE）が進めたぶんが在れば、そちらの結果を重ねる
        if not getattr(self, '_prev_lines', None) \
                and not getattr(self, '_analyze_text', ''):
            try:
                _key = self._analysis_key(text)
                _fgp = (getattr(self, '_fg_parked', None) or {}).pop(
                    _key, None)
            except Exception:
                _fgp = None
            if (_fgp and list(_fgp.get('lines') or []) == list(lines)
                    and len(_fgp.get('results') or []) == len(lines)):
                _res = list(_fgp['results'])
                try:
                    _bgp = (getattr(self, '_bg_parked', None) or {}).get(
                        _key)
                    for _i, _r in enumerate(
                            (_bgp or {}).get('results') or []):
                        if _r is not None and _i < len(_res):
                            _res[_i] = _r
                except Exception:
                    pass
                self._prev_lines = list(_fgp['lines'])
                self.line_results = _res
                self._analyze_todo = [
                    i for i in (_fgp.get('todo') or [])
                    if i < len(_res) and (_res[i] or {}).get('pending')]
                self._analyze_pos = 0
                try:
                    self._trace_analysis('預かりから続き', len(lines),
                                         len(self._analyze_todo),
                                         '途中で移ったタブ（項目48-RY）')
                except Exception:
                    pass

        # 前回の結果と比較し、変化した行だけ再処理する。
        # 行数が変わったとき（改行を打った・行を消した）も、
        # 変わっていない行は使い回す。前後の共通部分を突き合わせ、
        # 間の変わった部分だけを直す。
        prev = getattr(self, '_prev_lines', [])
        prev_results = getattr(self, 'line_results', [])
        # 前回の分割解析でやり残した行（旧い行番号のまま）。
        # 打鍵で解析が中断された場合、この行は内容が変わっていない
        # ため差分では拾えない。読み替えて持ち越さないと、
        # 仮置きのまま二度と解析されない行が残る。
        leftover = [i for i in self._analyze_todo[self._analyze_pos:]]

        # 全行から文脈語彙を構築（同じメモ内の正しく書けた語を優先補正に使う）
        # 行ごとの抽出結果は控えて使い回す（毎回メモ全文を形態素解析
        # すると、1打鍵ごとの反応が行数に比例して重くなる。実機で
        # 「入力から画面反映までが長い」と報告された・2026-08-08）。
        try:
            from vocabulary import build_context_vocab_cached
            if not hasattr(self, '_ctx_vocab_cache'):
                self._ctx_vocab_cache = {}
            # 候補づくり用に、**メモに実際に書かれている表記**も
            # 一緒に集める（項目48-P）。語彙にも辞書索引にも無い語
            # （平仮名・直り 等）を選び直しの候補に出すため。
            # 同じ字句解析の結果を使い回すので、余分な手間は無い。
            attested = {}
            context_vocab = build_context_vocab_cached(
                lines, self.store, self._ctx_vocab_cache,
                attested_out=attested)
            self._attested_surfaces = attested
        except Exception:
            context_vocab = {}

        if not prev or len(prev_results) != len(prev):
            # 前回の結果が行と対応していない（初回など）。全行やる。
            # ※prev が空の初回を差分側に落とすと、head=0・tail=0 の
            #   「全行が変わった」扱いになり、_shift_bookmarks が
            #   全ブックマークを全行数ぶん下へずらしてしまう
            #   （起動のたびに行番号が水増しされ、ブックマークが
            #   消えたように見えた実機の不具合の正体・2026-08-09）。
            results = [None] * len(lines)
            todo = list(range(len(lines)))
            _lo_shape = ('全行（前回の控えなし）' if not prev else
                         f'全行（結果{len(prev_results)}件と'
                         f'行{len(prev)}行の食い違い）')
        else:
            # 先頭から一致する行数
            head = 0
            while (head < len(lines) and head < len(prev)
                   and lines[head] == prev[head]):
                head += 1
            # 末尾から一致する行数（先頭で数えた分とは重ねない）
            tail = 0
            while (tail < len(lines) - head and tail < len(prev) - head
                   and lines[len(lines) - 1 - tail]
                   == prev[len(prev) - 1 - tail]):
                tail += 1
            results = (prev_results[:head]
                       + [None] * (len(lines) - tail - head)
                       + (prev_results[len(prev) - tail:] if tail else []))
            todo = list(range(head, len(lines) - tail))
            # 改行の挿入・行の削除で行数が変わった場合、ブックマークの
            # 行番号もそれに合わせてずらす（実機からの要望）。
            # head/tail は上で数えた「変わっていない行数」と同じ基準
            # なので、そのままブックマークのシフト計算に使い回せる。
            self._shift_bookmarks(head, len(prev) - tail, len(lines) - tail)
            # やり残しを新しい行番号に読み替えて足す
            todo.extend(remap_pending_lines(leftover, head, tail,
                                            len(prev), len(lines)))
            todo = sorted(set(todo))
            _lo_shape = (f'差分 前{head}行一致・後{tail}行一致・'
                         f'やり残し{len(leftover)}行')

        # 解析の記録を取り、説明の付かない全行解析なら書き出す
        # （項目48-LO。「説明が付く」＝きっかけの印がある・起動や
        # タブ切り替えの直後・本文が小さい・対象が本文の8割未満）。
        try:
            self._trace_analysis(_lo_cause or '打鍵の差分',
                                 len(lines), len(todo), _lo_shape)
            if (_lo_cause is None and _lo_had and len(lines) > 10
                    and len(todo) >= max(10, int(len(lines) * 0.8))):
                self._trace_analysis_dump('説明の付かない全行解析')
        except Exception:
            pass

        # まだ解析していない行は、仮置き（補正なし）で埋めておく。
        # None のまま描画側へ渡すと落ちるため、ここで必ず形を揃える。
        for i, r in enumerate(results):
            if r is None:
                results[i] = self._blank_result(lines[i])
        self.line_results = results
        self._prev_lines = lines[:]
        self._analyze_ctx = context_vocab
        self._analyze_text = text
        # 画面の範囲の控え（項目48-BS）。解析のたびに持ち直す。
        self._analyze_band = None
        todo, visible_n = self._visible_first(todo)
        self._analyze_todo = todo
        self._analyze_visible_n = visible_n
        self._analyze_shown_visible = False
        self._analyze_painted_pos = 0
        self._analyze_last_paint_ms = 0.0
        self._analyze_pos = 0
        # 控えから復元した回の印は、普通の解析に入ったら必ず下ろす
        # （下ろし忘れると、以後どの行も補正されなくなる）。
        self._analyze_units_only = False
        # **この結果を作ったときの入力方式**を控える。控えを保存する
        # ときは、今の設定ではなくこちらを書く。設定だけ変えて解析し
        # 直していない状態で保存すると、次回「設定は合っているのに
        # 中身は古い方式で作った結果」を読んでしまう。
        self._analyze_input_method = self.settings.get('input_method')
        # 行ごとの内容語の控えは、いまある行のぶんだけ残して使い回す
        # （以前は毎回空にしていたが、近傍の行は繰り返し参照される
        #   ため、打鍵のたびに全部分割し直すのは重い。消えた行の
        #   控えだけを落とす）。
        _cur = set(lines)
        self._line_words_cache = {
            k: v for k, v in getattr(self, '_line_words_cache', {}).items()
            if k in _cur}

        if len(todo) <= self.ANALYZE_INLINE_LIMIT:
            # 行数が少なくても、1行が重いことがある（英字混じりの
            # 技術メモ等）。時間で区切り、収まらなければ残りを
            # 分割解析に回す。行数だけで判断していた頃は、重い40行が
            # 同期で走って起動から数秒間キー入力が詰まっていた
            # （実機で「8秒ほど入力できない」と報告された）。
            self._analyze_slice(len(todo), budget_ms=self.ANALYZE_BUDGET_MS)
            if self._analyze_pos >= len(todo):
                self._finish_analysis()
                return
            self._refresh_after_analysis(learn=False)
            self._schedule_analysis_chunk()
            return

        # 対象が多い。まず仮置きのまま画面を出し、あとは少しずつ。
        self._refresh_after_analysis(learn=False)
        self._schedule_analysis_chunk()

    def _analyze_slice(self, count, budget_ms=None):
        """
        todo の続きから count 行ぶんだけ解析する。

        budget_ms を渡すと、行数に達していなくてもその時間を超えた
        ところで切り上げる（残りは次のひと区切りに持ち越される）。
        1行の重さは内容次第で数十倍変わるため、行数だけで区切ると
        重い行が続いたときに画面が固まる。
        """
        import time as _time
        deadline = (_time.monotonic() + budget_ms / 1000.0
                    if budget_ms else None)
        lines = self._prev_lines
        todo = self._analyze_todo
        end = min(self._analyze_pos + count, len(todo))
        recent = (self.recent_words.words()
                  if getattr(self, 'recent_words', None) is not None else [])
        for k in range(self._analyze_pos, end):
            if deadline is not None and _time.monotonic() > deadline \
                    and k > self._analyze_pos:
                # 時間切れ。ここまでを確定して残りは持ち越す
                # （最低1行は進める。進めないと永遠に終わらない）。
                self._analyze_pos = k
                return
            i = todo[k]
            if not (0 <= i < len(self.line_results) and i < len(lines)):
                continue
            if getattr(self, '_analyze_units_only', False):
                # 控えから結果を復元した回（項目48-L）。
                # 補正はやり直さず、描画用の単位だけ組み立てる。
                self._prebuild_units_for(i)
                continue
            try:
                self.line_results[i] = correct_line(
                    lines[i], self.store,
                    context_vocab=self._analyze_ctx,
                    decisions=self.decisions,
                    input_method=self.settings.get('input_method'),
                    context_vec=self.context_vec,
                    dict_index=self.dict_index,
                    nearby_words=self._nearby_words_for(i),
                    recent_words=recent)
                # 描画用の単位もこの場で組み立てて控える。
                # 解析後の描き直しで全行まとめて組み立てると、
                # 行数の多いタブでは終わり際に1秒近く固まるため。
                self._prebuild_units_for(i)
                # **直すところが無かった行を、文字の並びの材料に
                # する**（項目48-BN・うにさんの「アプリの工夫に
                # します」）。同梱の表はアプリの技術文書から作って
                # あるので、その人が書くジャンルでは**正しい断片の
                # 9.5% を誤って止める**。自分のメモから育てると
                # 2.7% まで下がる（実測）。
                # 材料にしてよいのは「アプリが見て何もおかしくない
                # と判断した行」だけ。二度数えない仕組みは
                # charngram 側が持っている（学び20）。
                if not self.line_results[i].get('changed'):
                    self._learn_charngram(lines[i])
            except Exception:
                # 1行の失敗で解析全体を止めない（仮置きのまま残す）。
                # ただし黙って握りつぶさない。過去に、引数の食い違いで
                # 全行がここに落ち続け「起動しても何も補正されない」
                # 状態になったのに、例外が一切表に出ず原因の特定が
                # 1往復遅れた（正体は correct_line ラッパーの
                # nearby_words / recent_words 引数の受け漏れ）。
                # 最初の1回だけ記録と表示を残し、同じ轍を踏まない。
                if not getattr(self, '_analyze_error_reported', False):
                    self._analyze_error_reported = True
                    import traceback
                    self._analyze_last_error = traceback.format_exc()
                    traceback.print_exc()
                    try:
                        self.status.config(
                            text='解析でエラーが起きています（コンソール参照）')
                    except Exception:
                        pass
        self._analyze_pos = end

    def _remember_recent(self, surface):
        """
        いま確定した語を「直前の変換履歴」に覚える。

        ユーザーが自分で選び直した語は、その人がいま何の話をして
        いるかを最もはっきり示す。次の行以降で同音異義語を選ぶ
        ときの手がかりにする（方針: 「文脈とは、直前の変換履歴
        だったり、周囲に存在する単語を頼りにします」）。

        ひとつ前だけでなく、いくつか（RecentWords.LIMIT 件）を
        保持する。1語だけでは、そのとき偶然選んだ語に引きずられる。
        """
        if getattr(self, 'recent_words', None) is None:
            return
        try:
            self.recent_words.add(surface)
        except Exception:
            pass

    def _words_of_line(self, index):
        """
        その行の内容語（文脈の材料）。行ごとに覚えておく。

        近傍の行は何度も参照されるため、そのつど形態素解析を
        やり直すと解析の手間が行数の何倍にもなる。行の文字列を
        鍵にして控えておき、同じ内容なら使い回す
        （控えは解析のたびに作り直すので、古い行が残り続けない）。
        """
        lines = self._prev_lines
        if not (0 <= index < len(lines)):
            return []
        line = lines[index]
        cached = self._line_words_cache.get(line)
        if cached is not None:
            return cached
        try:
            from context_vec import extract_content_words
            fn = getattr(self.store, '_tokenize_fn', None)
            if fn is None:
                fn = corrector.make_tokenizer(self.store)
                self.store._tokenize_fn = fn
            words = extract_content_words(fn, line)
        except Exception:
            words = []
        self._line_words_cache[line] = words
        return words

    def _nearby_words_for(self, index):
        """対象行の上下の行から集めた内容語（近い行の順）。"""
        try:
            from context_vec import build_nearby_words
            return build_nearby_words(len(self._prev_lines), index,
                                      self._words_of_line)
        except Exception:
            return []

    def _load_analysis_cache(self):
        """
        前回の解析結果の控えを読む（起動時に一度だけ・項目48-L）。

        状況（語彙・文脈・判断・設定・エンジンの版）が前回と少しでも
        違えば、analysis_cache 側が空を返す。読めたかどうかに
        関わらず、**読むのはこの1回だけ**。以後は手元の結果のほうが
        新しいので使わない。
        """
        self._analysis_cache = {}
        self._analysis_stale = set()
        try:
            import analysis_cache
            recent = (self.recent_words.words()
                      if getattr(self, 'recent_words', None) is not None
                      else ())
            fp = analysis_cache.build_fingerprint(
                app_dir(), APP_VERSION,
                self.settings.get('input_method'), recent,
                store=self.store, context_vec=self.context_vec,
                dict_index=self.dict_index, decisions=self.decisions,
                choices=self.choices,
                ime_readings=getattr(self, 'ime_readings', None))
            self._analysis_cache = analysis_cache.load(
                ANALYSIS_CACHE_FILE, fp)
        except Exception:
            self._analysis_cache = {}

    @staticmethod
    def _analysis_key(text):
        """
        解析結果の控えの鍵（**末尾の空行を落とした本文**）。

        **末尾の空行を数に入れてはいけない**（うにさんの報告・
        2026-08-25「解析が終わってからタブ移動して戻ってくると
        また解析している」の正体）。

        画面の本文には、下のほうをクリックできるように空行が
        `TRAILING_BLANK_LINES`（24行）足してある（`_pad_blank_lines`）。
        控えに残すときは `_capture_session` が `rstrip('\\n')` で
        落とすので、**同じタブでも「いま画面にある本文」と
        「タブに控えた本文」は末尾の空行の数が違う**。

        鍵を画面の本文そのままにしていたので:

          - 末尾のあたりに打つ（空行の数が 24 でなくなる）と、
            **戻ってきたときの鍵が変わって控えが外れる**——
            うにさんの見た「また解析している」
          - 裏で進めたタブ（項目48-FQ）は**タブに控えた本文**を鍵に
            入れていたので、**一度も使われていなかった**（学び22の型。
            同じ鍵を2か所で別々に作っていた）

        だから鍵づくりはここ1か所にまとめ、**どちらの形からでも
        同じ鍵**になるようにする。落とした空行ぶんの結果は、
        使うときに仮置き（空行なので補正も選び直しも無い）で足す。
        """
        return (text or '').rstrip('\n')

    def _trace_analysis(self, cause, lines_n, todo_n, shape):
        """
        解析1回ぶんの記録を輪の控えに足す（項目48-LO・最新40件）。

        画面には出さない。`_trace_analysis_dump` が書き出すときだけ
        人の目に触れる。1件は文字列1本（数十バイト）なので、
        打鍵のたびに取っても重さは無い。
        """
        import time as _t
        tr = getattr(self, '_analyze_trace', None)
        if tr is None:
            tr = self._analyze_trace = []
        tr.append(f'{_t.strftime("%H:%M:%S")}  きっかけ={cause}  '
                  f'本文{lines_n}行  対象{todo_n}行  {shape}')
        del tr[:-40]

    def _trace_analysis_dump(self, reason):
        """
        直近の解析の記録を `解析の記録.txt` へ書き出す（項目48-LO）。

        **説明の付かない全行解析**（きっかけの印が無いのに、本文の
        8割以上が対象になった）が起きた瞬間に呼ばれる。写しで再現
        できない実機だけの症状を、次にファイルで読むための仕掛け。
        書けなくても何も起きない（記録のために本体を止めない）。
        """
        try:
            path = os.path.join(app_dir(), '解析の記録.txt')
            old = ''
            try:
                if os.path.exists(path) \
                        and os.path.getsize(path) < 200_000:
                    with open(path, 'r', encoding='utf-8') as f:
                        old = f.read()
            except Exception:
                old = ''
            import time as _t
            head = (f'--- {_t.strftime("%Y-%m-%d %H:%M:%S")} '
                    f'{reason}（v{APP_VERSION}） ---\n')
            body = '\n'.join(getattr(self, '_analyze_trace', ())) + '\n'
            with open(path, 'w', encoding='utf-8') as f:
                f.write(old + head + body)
        except Exception:
            pass

    def _use_analysis_cache(self, text, lines):
        """
        控えにこのタブの結果があれば、それを使って解析を飛ばす。

        戻り値: 使えたら True（呼び出し側は解析をやめてよい）。
        """
        cache = getattr(self, '_analysis_cache', None)
        if not cache:
            return False
        key = self._analysis_key(text)
        if not key:
            return False
        core = cache.pop(key, None)         # 一度使ったら取り下げる
        try:
            self._analysis_stale.discard(key)
        except Exception:
            pass
        if not core or len(core) > len(lines):
            return False
        # 鍵に入っていない末尾は、**空行でなければ別の本文**
        if any(l != '' for l in lines[len(core):]):
            return False
        results = list(core)
        results += [self._blank_result(l) for l in lines[len(core):]]
        if len(results) != len(lines):
            return False
        self.line_results = results
        self._prev_lines = lines[:]
        # 文脈語彙は「これから解析する行」のための材料なので、
        # 解析を飛ばすときは作らなくてよい（1000行で 0.6 秒）。
        # 次に打鍵して差分解析が走るときに作られる。
        self._analyze_ctx = {}
        self._analyze_text = text
        self._analyze_pos = 0
        self._line_words_cache = {}
        # 描画用の単位だけは組み立てる必要がある（控えていない）。
        # 1000行で 0.5 秒ほど。まとめてやると固まるので、解析と同じ
        # 仕組みに乗せて少しずつ進める（`_analyze_units_only`）。
        #
        # ★★ **見えている行から先に組み、そこで一度塗る**
        # （項目48-QZ・2026-09-05）。うにさんの報告——
        # 「**タブ移動でも（補正の色が）一度消えて再度つく**」。
        #
        # `_load_active_tab` が本文を入れ直すと**タグが全部消える**
        # のに、控えから戻す道は `line_results` を入れるだけで
        # **一度も塗らずに**戻っていた。塗りの合図は
        # `_analyze_chunk` の中にしか無く、その合図が使う3つの値を
        # **ここで置き直していなかった**ので、**前のタブの値を
        # 持ち越して**いた:
        #
        #     `_analyze_shown_visible`  前のタブで True のまま
        #                               → 48-JA の塗りが skip される
        #     `_analyze_painted_pos`    前のタブの行数（例 1000）のまま
        #                               → `done > _p` が永久に偽
        #     `_analyze_visible_n`      前のタブの数のまま
        #                               → 「見えているぶんが揃った」が
        #                                 いつ立つか当てにならない
        #
        # その結果、色が戻るのは**全行の単位を組み終えた
        # `_finish_analysis` のあと**だった。3つを置き直し、
        # 並びを `_visible_first` にすれば、**最初の区切りで
        # 見えているぶんが塗られる**。
        #
        # **順番を変えても結果は変わらない**——ここでやるのは
        # 単位の組み立てだけで、行どうしに前後関係が無い
        # （`_visible_first` の説明と同じ理由）。
        _todo, _vis_n = self._visible_first(list(range(len(lines))))
        self._analyze_todo = _todo
        self._analyze_band = None
        self._analyze_visible_n = _vis_n
        self._analyze_shown_visible = False
        self._analyze_painted_pos = 0
        self._analyze_last_paint_ms = 0.0
        self._analyze_units_only = True
        # 控えは「今の入力方式」で照合が通ったから使えている。
        self._analyze_input_method = self.settings.get('input_method')
        self._schedule_analysis_chunk()
        try:
            self._trace_analysis('控えから復元', len(lines), len(lines),
                                 '単位の組み立てのみ（補正はやり直さない）')
        except Exception:
            pass
        return True

    # 画面に見えている行の上下に、これだけ余分に先回りする。
    # 少しスクロールしても待たされないための余白。
    VISIBLE_MARGIN = 20

    # ------------------------------------------------------------
    # 目に見えない空白を見せる（項目48-IF・うにさんの指定・2026-08-21）
    # ------------------------------------------------------------
    #
    #   「半角スペース、全角スペース、タブキーによるスペースのような
    #     **目に見えない空白を見えるオプション**を追加します。
    #     **デフォルトはオン**で、**連続して入力されていても
    #     いくつ入っているか分かる見た目**にします」
    #
    # **「いくつ入っているか分かる」がいちばん難しいところ**だった。
    # Tk の Text は**隣り合う同じタグを1つのまとまりとして描く**ので、
    # 1つのタグで塗ると「空白3つ」が1本の帯になって数えられない。
    # 実際に描いて3通りを比べた（`probes/probe_whitespace.py`）:
    #
    #     枠だけ（1タグ）          → 3つが1つの枠になる。**数えられない**
    #     濃淡だけ（交互・弱い差）  → 境目が見えない。**数えられない**
    #     **交互のタグ＋濃淡**      → **数えられる**
    #
    # だから**2つのタグを交互に**置く。うにさんが簡易入力の色で
    # 指定された「2色を用意して交互に付ける」と同じ形である。
    #
    # 色は**無彩色**にした。ほかの色は全部「意味」を持っていて
    # （網掛け＝補正候補あり／紫＝迷い／緑と青＝簡易入力から送った）、
    # 空白の印は**既定でずっと出しっぱなし**なので、色相を1つ使うと
    # 意味のある色と競ってしまう。
    #
    # 見分け方は**幅**にした:
    #     半角スペース  1文字ぶん（線 6px）
    #     全角スペース  2文字ぶん（線 19px。紛れ込むと困るが幅で分かる）
    #     タブ          次のタブ位置まで（いちばん広い）
    #
    # **項目48-IG でやり直した**（うにさんの指定）:
    #
    #   「**次の行に折り返した時、末尾のスペースが半角か全角か
    #     分からない**」
    #   「ところどころにあるスペースが**目立つ**。**縦の長さを
    #     短くして、下詰めで縦2割ほどの高さ**にしてください」
    #
    # 折り返しの境目に来た空白は、**地色だと右端まで引き伸ばされる**
    # （半角6px が27px・63px になるのを画素で数えた）。だから
    # 半角と全角が見分けられなくなっていた。
    # **下線は文字送りのぶんだけ引かれるので伸びない。**
    # 同じ直しで「短く・下詰め」も同時に満たせる。
    #
    # 地色の箱を低くする道は**無かった**（測った）:
    #     タグに小さい字を指定 → `bbox` は縮むが**塗りは行の高さのまま**。
    #                            縮むのは**幅**＝本文がずれる。使えない
    #     `offset` で下げる     → **行の高さが伸びる**。使えない
    #     下線                  → **行の下端から1px・太さ2px**。
    #                            Tk で引ける**いちばん低い印**
    #
    # **項目48-IH でさらに直した**（うにさんの報告）:
    #
    #   「**すこし高さがないと、`_` このアンダーバーと見分けが
    #     つきません**」
    #   「**簡易入力にも実装してください。オプションは共通です**」
    #
    # 下線1本はアンダーバーの字形と同じ位置・同じ太さなので、
    # **打ち消し線を足して2本にした**。高さが出て、`_` と見分けが付く。
    # 折り返しで伸びないのは下線と同じ（測った）。
    # 印を置く欄は `_whitespace_targets` にまとめ、**簡易入力欄**も
    # 同じ切り替え・同じ色で塗るようにした。
    WS_KINDS = {' ': 'ws_sp', '\u3000': 'ws_wide', '\t': 'ws_tab'}
    WS_TAGS = ('ws_sp_a', 'ws_sp_b', 'ws_wide_a', 'ws_wide_b',
               'ws_tab_a', 'ws_tab_b')
    # 折り返しの境目に来た空白の四角を消すタグ（項目48-II）
    WS_NOBOX = 'ws_nobox'
    # 塗り直しは**見えている範囲＋余白**だけ（項目48-IF）。
    # 1,900行を毎回なぞると打鍵のたびに引っかかる。
    # **見えている範囲＋この行数**だけ塗る。
    # 40 にしていたが、英文の多い文書では画面の帯に印が2,600個できて
    # 塗り直しに50msかかった（測った・項目48-II）。打鍵のたびに
    # 引っかかるので 20 に減らした（画面1つぶんの余白は残る）。
    WS_PAINT_MARGIN = 20
    WS_PAINT_DELAY_MS = 80

    # ------------------------------------------------------------
    # 終端の罫線（項目48-IM・うにさんの指定・2026-08-22）
    # ------------------------------------------------------------
    #
    #   「文末のひとつ下の行の空白行には、**下に罫線を横一列**入れて
    #     終端であることが分かるようにします」
    #
    # **空行には字が無い。** Tk の Text で引ける印を全部試した
    # （`probe_endrule.py`）:
    #
    #     改行に下線        → **何も描かれない**（タブと同じ）
    #     改行に打ち消し線  → **何も描かれない**
    #     改行に地色        → **横いっぱいに描かれる**（幅348px＝欄の幅）
    #                         ただし高さは行の高さ（24px）まるごと
    #
    # 地色しか無い。**そこで、その行の字を小さくする。**
    # 空行には送る字が無いので、字を小さくしても**本文はずれない**
    # （縮むのは、その空行の高さだけ）。実測:
    #
    #     字1 → 3px ／ 字2 → **4px** ／ 字3 → 5px ／ 字5 → 9px
    #     （どれも幅は欄いっぱい。本文の行は24pxのまま）
    #
    # **カーソルがその行に居る間は引かない。** 引くと行が4pxになり、
    # **カーソルまで4pxになって見えなくなる**（末尾で改行した直後が
    # ちょうどこの状態）。居なくなったら引く。
    END_RULE_TAG = 'end_rule'
    END_RULE_FONT_SIZE = 2      # 実測 4px の帯になる

    def _configure_end_rule_tag(self):
        """終端の罫線の色を置き直す。テーマ切替でも呼ぶ。"""
        for w in (getattr(self, 'editor', None),
                  getattr(self, 'result_view', None)):
            if w is None:
                continue
            try:
                w.tag_configure(self.END_RULE_TAG, background=RULE,
                                font=(EDITOR_FONT[0],
                                      self.END_RULE_FONT_SIZE))
                w.tag_lower(self.END_RULE_TAG)
            except Exception:
                pass

    def _paint_end_rule(self):
        """
        **文字の終わりのひとつ下の行を、横一列の罫線にする。**

        うにさんの指定（2026-08-22）:
            「終端の線とは、**最後の改行ではなく、最後の文字を基準**に
              します。**Ctrl+Aで選択される範囲の最後の行から、その
              ひとつ下の行の下側**に罫線を引きます」

        だから見るのは**いちばん下の行ではない**。`Ctrl+A`（項目48-FK）
        が選ぶ範囲の終わり——**中身のある最後の行**——を探して、
        その**ひとつ下の行**に引く。末尾に空行がいくつ続いていても、
        罫線は**文字のすぐ下**に来る。

        引かない場合:
            中身のある行が1つも無い（まっさらな文書）
            その下に行が無い（文書が改行で終わっていない）
            **カーソルがその行に居る**（引くと行が4pxになり、
            カーソルまで4pxになって見えなくなる）
        """
        for w in (getattr(self, 'editor', None),
                  getattr(self, 'result_view', None)):
            if w is None:
                continue
            try:
                w.tag_remove(self.END_RULE_TAG, '1.0', 'end')
                lines = w.get('1.0', 'end-1c').split('\n')
                last_text = 0
                for k in range(len(lines), 0, -1):
                    # `strip()` で見るのは `_on_select_all`（Ctrl+A）と
                    # 同じ数え方にするため。空白だけの行は「中身」に
                    #数えない。
                    if lines[k - 1].strip():
                        last_text = k
                        break
                if not last_text:
                    continue          # 中身のある行が無い
                target = last_text + 1
                if target > len(lines):
                    continue          # その下に行が無い
                if w is getattr(self, 'editor', None):
                    cur = int(str(w.index('insert')).split('.')[0])
                    if cur == target:
                        continue      # カーソルが居る間は引かない
                w.tag_add(self.END_RULE_TAG,
                          f'{target}.0', f'{target + 1}.0')
            except Exception:
                pass

    def _whitespace_targets(self):
        """
        空白の印を置く欄を**1箇所で決める**。

        メモ欄・補正欄に加えて、**簡易入力ウィンドウ**も対象にする
        （項目48-IH・うにさんの指定「簡易入力にも実装してください。
        **オプションは共通です**」）。切り替えも色も、同じ
        `show_whitespace` と同じ配色を見る。

        学び22「片方だけに置くと、そちらを迂回して素通りする」。
        名簿を1つにしておけば、欄が増えても足し忘れようがない。
        """
        return [w for w in (getattr(self, 'editor', None),
                            getattr(self, 'result_view', None),
                            getattr(self, '_quick_text', None))
                if w is not None]

    def _apply_tab_stops(self, font=None):
        """
        **タブ1つの見た目の幅を全角ぶん確保する**（項目48-LG・
        2026-08-29 うにさんの指定「タブキーを1回打つと、半角スペース
        ほどの間隔しか開かず、見えにくい。全角スペースぐらいの幅は
        確保する」）。

        Tk のタブは「次の止まり位置まで進む」ので、最小の幅そのものは
        指定できない。止まりを**全角2つぶんの等間隔**にすると、
        全角の字で書かれた行では位置が全角の倍数に揃うため、タブの
        進みは必ず全角1〜2つぶんになる。既定（半角8つごと）では、
        位置しだいで半角1つぶんしか進まなかった。
        （半角が混ざる行では最小の保証が無いのは Tk の仕組みの限界）

        欄の名簿は `_whitespace_targets`（学び22——欄が増えても
        足し忘れない）。字の大きさを変えたら呼び直す（俯瞰）。
        """
        try:
            import tkinter.font as tkfont
            f = tkfont.Font(font=font or EDITOR_FONT)
            # 目盛りは**全角4つ**（Tk の既定＝半角8つ≈全角4つと同じ
            # 列合わせ。全角2つにしたら「タブを4つ5つ重ねないと他の
            # 行と揃えられない」になった——うにさんの報告・2026-08-29）
            step = max(16, f.measure('　') * 4)
        except Exception:
            return
        # **止まりは並べて渡す**。1つだけ渡すと、Tk はその先へ
        # 外挿してくれない（probe_ui_48lf で実測——2つ目の全角の
        # あとのタブが 4px になった）。20個あれば、その先は最後の
        # 2つの間隔（=step）で外挿される。
        stops = tuple(step * i for i in range(1, 21))
        for w in self._whitespace_targets():
            try:
                w.configure(tabs=stops)
            except Exception:
                pass

    def _line_tab_stops(self, w, line):
        """
        **行の中身に合わせたタブの止まり**（項目48-LG・後半）。

        widget 全体の止まり（`_apply_tab_stops`）だけでは「全角ぶん
        確保」にならない——Yu Mincho は「あ」(13px) と全角スペース
        (15px) の幅が違い、字の並びが格子に揃わないので、タブの直前が
        止まりのすぐ手前に来ると 4px しか進まない（probe_ui_48lf で
        実測）。そこで**行ごとに字の幅を測り**、各タブが
        **全角1つぶん以上**進む位置に止まりを置く（止まり自体は
        全角の倍数に丸める——行どうしの列がゆるく揃う）。

        タグの tabs は**表示行の先頭を支配するタグ**から読まれるので、
        行全体にタグを掛ければ行ごとに変えられる（1文字だけのタグは
        効かない・実測）。折り返した行の2枚目以降は左端からの測りに
        ずれが出るが、これは今までも同じ（Tk の仕組みの限界）。
        """
        import tkinter.font as tkfont
        cache = getattr(self, '_tab_stop_cache', None)
        if cache is None:
            cache = self._tab_stop_cache = {}
        try:
            fkey = str(w.cget('font'))
        except Exception:
            fkey = ''
        key = (fkey, line)
        got = cache.get(key)
        if got is not None:
            return got
        try:
            f = tkfont.Font(font=w.cget('font'))
            zk = max(4, f.measure('　'))
            grid = zk * 4       # 目盛りは土台（_apply_tab_stops）と同じ
            stops = []
            pos = 0
            for seg in line.split('	')[:-1]:
                pos += f.measure(seg)
                # **全角1つぶん先の、次の「4全角の目盛り」**。
                # 目盛りを全行で共有するから列が揃う（全角刻みに
                # したら、揃えるのにタブを重ねる羽目になった・実測）
                stop = ((pos + zk) + grid - 1) // grid * grid
                stops.append(stop)
                pos = stop
            if stops:
                stops.append(stops[-1] + grid)      # 外挿の間隔も同じ
            got = tuple(stops)
        except Exception:
            got = ()
        if len(cache) > 4000:
            cache.clear()
        cache[key] = got
        return got

    @staticmethod
    def _tags_still_there(w, probes):
        """
        **「前と同じ」と言う前に、その印がまだ本当に付いているか**
        （項目48-MO・2026-08-31。うにさんの報告「右のタブスペースが
        短いままでした。解析は済んでいます。ただこのあと最小化や
        戻したり、何かしたら正しいタブスペース幅に直りました」）。

        48-MB で入れた「**前と同じなら指1本触れない**」（点滅止め）は、
        **印が残っていること**を前提にしていた。ところが**補正欄は
        解析のたびに中身を作り直す**（`delete('1.0','end')` →
        `insert`）ので、**そこで印が全部消える**。作り直した中身が
        前と同じ字なら、次の塗りは「前と同じ」と言って**何も敷かない**
        ——タブの止まりも空白の印も、補正欄にだけ付かないまま残る。

        窓を動かすと見える行の範囲（lo/hi）が変わって控えが外れるので、
        「最小化して戻したら直った」。**塗りの側は正しく、控えの側が
        嘘をついていた。**

        **誰が中身を作り直したかを追いかけない**（学び22——書き手を
        数え上げると、いつか1つ漏れる）。**印が在るかをその場で
        確かめる**ほうが、書き手が増えても壊れない。

        probes: [(タグの名前, 位置), ...]（1〜2個で足りる）
        """
        for tag, index in probes:
            try:
                if tag not in w.tag_names(index):
                    return False
            except Exception:
                return False
        return True

    def _paint_line_tab_stops(self, w, lo, hi):
        """
        見えている範囲の行に、行ごとのタブの止まりを敷く。

        **敷き直すのは、前と違うときだけ**（項目48-MB）。剥がして
        貼り直す間にタブの幅が素の目盛りへ戻るので、解析中のように
        何度も呼ばれると幅が伸び縮みして見えていた。
        """
        regs = getattr(self, '_ws_stop_tags', None)
        if regs is None:
            regs = self._ws_stop_tags = {}
        prevs = getattr(self, '_ws_stop_sig', None)
        if prevs is None:
            prevs = self._ws_stop_sig = {}
        reg = regs.setdefault(str(w), set())
        try:
            want = {}
            for li in range(lo, hi + 1):
                line = w.get(f'{li}.0', f'{li}.end')
                if '	' not in line:
                    continue
                stops = self._line_tab_stops(w, line)
                if not stops:
                    continue
                want[li] = ('ws_stops_' + '_'.join(map(str, stops)), stops)
            sig = (lo, hi, tuple(sorted(
                (li, v[0]) for li, v in want.items())))
            # **敷いてあることを確かめてから**「前と同じ」と言う
            # （項目48-MO）。補正欄は解析のたびに中身を作り直すので、
            # 控えだけを見ると「敷いてある」と嘘をつく。
            if prevs.get(str(w)) == sig and (
                    not want or self._tags_still_there(
                        w, [(v[0], f'{li}.0')
                            for li, v in list(want.items())[:1]])):
                return              # もう敷いてある。触らない
            prevs[str(w)] = sig
            if len(reg) > 500:      # 増えすぎたらタグごと捨てる
                for name in reg:
                    w.tag_delete(name)
                reg.clear()
            for name in reg:
                w.tag_remove(name, f'{lo}.0', f'{hi + 1}.0')
            for li, (name, stops) in want.items():
                if name not in reg:
                    w.tag_configure(name, tabs=stops)
                    reg.add(name)
                w.tag_add(name, f'{li}.0', f'{li}.end')
        except Exception:
            prevs.pop(str(w), None)

    def _configure_whitespace_tags(self):
        """空白の印の色を（作り直しでなく）置き直す。テーマ切替でも呼ぶ。"""
        for w in self._whitespace_targets():
            try:
                # **スペースは行の下端の線**（項目48-IG）。
                # 地色の箱は必ず行の高さいっぱいになる（測った）ので、
                # 「短く・下詰め」にするには線にするしかない。
                # 線には**もう一つ効き目がある**——折り返しの境目に
                # 来た空白は、**地色だと右端まで引き伸ばされて
                # 半角か全角か分からなくなる**（うにさんの指定）。
                # 線は**文字送りのぶんだけ**引かれるので伸びない
                # （半角6px・全角19px のまま。画素を数えて確かめた）。
                # **スペースは灰色の下線1本だけ**（項目48-IJ）。
                # 地色は「目立つ」とうにさんから報告があったので
                # 付けない。**二重下線は Tk に無い**（タグの指定を
                # 全部並べて確認・`probe_ws_double.py`）。
                #
                # `underlinefg` は新しめの Tk にしかない。無いときは
                # `foreground` で同じことになる（空白には字が無いので、
                # 線の色だけが変わる）。
                for _t, _c in (('ws_sp_a', WS_LINE_A),
                               ('ws_sp_b', WS_LINE_B),
                               ('ws_wide_a', WS_LINE_A),
                               ('ws_wide_b', WS_LINE_B)):
                    try:
                        w.tag_configure(_t, background='', borderwidth=0,
                                        relief='flat', overstrike=False,
                                        underline=True, underlinefg=_c)
                    except tk.TclError:
                        w.tag_configure(_t, background='', borderwidth=0,
                                        relief='flat', overstrike=False,
                                        underline=True, foreground=_c)
                # **タブだけは線にできない。** Tk はタブの位置に
                # 下線も打ち消し線も引かない（実際に描いて確かめた）。
                # 地色の帯だけで、いちばん薄くする。
                for _t, _bg in (('ws_tab_a', WS_TAB_A),
                                ('ws_tab_b', WS_TAB_B)):
                    w.tag_configure(_t, background=_bg, borderwidth=0,
                                    relief='flat', underline=False)
                # **折り返しの境目に来たタブは、帯を消す。**
                # Tk は表示行の最後の塊の地色を右端まで塗るので、
                # そのままだと帯が右端まで伸びる（項目48-IG で測った）。
                # 地色を持つのは**タブだけ**になったので、
                # ここもタブのためだけに残す。
                w.tag_configure(self.WS_NOBOX, background=w.cget('bg'))
                # **意味のある色より下に置く。** 網掛け（補正候補あり）や
                # 選択が空白に重なっても、そちらが見えるようにする。
                for t in self.WS_TAGS:
                    w.tag_lower(t)
                # 四角消しは、印より1つだけ上に置く（印の地色に勝ち、
                # 網掛け・選択には負ける）。
                w.tag_lower(self.WS_NOBOX)
                w.tag_raise(self.WS_NOBOX, self.WS_TAGS[0])
            except Exception:
                pass

    def _schedule_whitespace_paint(self, delay=None):
        """空白の塗り直しを予約する（打鍵・スクロールのたびに呼ばれる）。"""
        if delay is None:
            delay = self.WS_PAINT_DELAY_MS
        job = getattr(self, '_ws_paint_job', None)
        if job is not None:
            try:
                self.root.after_cancel(job)
            except Exception:
                pass
        try:
            self._ws_paint_job = self.root.after(delay,
                                                 self._paint_whitespace)
        except Exception:
            self._ws_paint_job = None

    def _paint_whitespace(self):
        """
        **見えている範囲の空白に印を付ける。**

        交互に2つのタグを使う。**まとまりの先頭で必ず a から始める**
        ので、「空白2つ」はいつも同じ見え方になる（a b）。
        まとまりが切れたら数え直す。
        """
        self._ws_paint_job = None
        if self._window_dragging():
            self._schedule_whitespace_paint(delay=120)
            return
        on = True
        try:
            on = bool(self.settings.get('show_whitespace'))
        except Exception:
            pass
        sigs = getattr(self, '_ws_paint_sig', None)
        if sigs is None:
            sigs = self._ws_paint_sig = {}
        for w in self._whitespace_targets():
            try:
                top = int(str(w.index('@0,0')).split('.')[0])
                height = max(1, w.winfo_height() - 1)
                bottom = int(str(w.index(f'@0,{height}')).split('.')[0])
                last = int(str(w.index('end-1c')).split('.')[0])
            except Exception:
                continue
            lo = max(1, top - self.WS_PAINT_MARGIN)
            hi = min(last, bottom + self.WS_PAINT_MARGIN)
            # 行ごとのタブの止まり（項目48-LG・**空白の印の
            # 切り替えとは無関係に敷く**——タブの幅は見た目の骨格）
            self._paint_line_tab_stops(w, lo, hi)
            # **タグ付けはまとめて1回で呼ぶ。** Tk の `tag add` は
            # 範囲をいくつでも並べられる。1文字ずつ呼ぶと、英文の
            # 多い文書（画面の帯に2,600個の印）で **48ms → 21ms** の
            # 差が出た（測った・項目48-II）。
            batch = {}
            for li in (range(lo, hi + 1) if on else ()):
                try:
                    line = w.get(f'{li}.0', f'{li}.end')
                except Exception:
                    break
                if not line:
                    continue
                cols = [(ci, self.WS_KINDS[ch]) for ci, ch in enumerate(line)
                        if ch in self.WS_KINDS]
                if not cols:
                    continue
                # 折り返しの境目を数えるのは**タブのある行だけ**でよい
                # （地色を持つのはタブだけになった・項目48-IJ）。
                # 英文の多い文書で 20ms 使っていた仕事が、ここで消える。
                edges = (self._wrap_edge_columns(w, li)
                         if '\t' in line else ())
                n = 0
                prev = -2
                for ci, kind in cols:
                    n = n + 1 if ci == prev + 1 else 1
                    prev = ci
                    tag = f'{kind}_{"ab"[(n - 1) % 2]}'
                    batch.setdefault(tag, []).extend(
                        (f'{li}.{ci}', f'{li}.{ci + 1}'))
                    if ci in edges and kind == 'ws_tab':
                        # 折り返しの境目に来たタブ。帯が右端まで
                        # 伸びるので消す（項目48-II／48-IJ）
                        batch.setdefault(self.WS_NOBOX, []).extend(
                            (f'{li}.{ci}', f'{li}.{ci + 1}'))
            # **前と同じなら、指1本触れない**（項目48-MB）。
            # 消してから組むと、組む途中の `display lineend`
            # （`_wrap_edge_columns`）が Tk に画面を作り直させるので、
            # **印が消えた姿がそのまま描かれる**。解析中はここが
            # 毎秒7回走るので、印が点滅して見えていた。
            # うにさんの報告（2026-08-30）:「解析中、タブキーの空白が
            # 伸びたり縮んだりしています」（画素で確かめた——
            # `tools_local/probe_ws_flicker.py`）。
            try:
                text = w.get(f'{lo}.0', f'{hi}.end')
            except Exception:
                text = None
            sig = (on, lo, hi, w.winfo_width(), str(w.cget('font')),
                   text, tuple(sorted((t, tuple(v))
                                      for t, v in batch.items())))
            # 同じ確かめを、空白の印にも（項目48-MO）。**同じ理由**で
            # 同じことが起きる——片方だけ直すと、そちらを迂回する。
            if sigs.get(str(w)) == sig and (
                    not batch or self._tags_still_there(
                        w, [(t, v[0]) for t, v in
                            list(batch.items())[:1]])):
                continue
            sigs[str(w)] = sig
            try:
                for t in self.WS_TAGS + (self.WS_NOBOX,):
                    w.tag_remove(t, '1.0', 'end')
            except Exception:
                sigs.pop(str(w), None)
                continue
            for tag, args in batch.items():
                try:
                    w.tag_add(tag, *args)
                except Exception:
                    pass
        # 終端の罫線も、同じ予約に相乗りさせる（項目48-IM）。
        # 予約を2つに増やすと、片方だけ呼び忘れる（学び22）。
        self._paint_end_rule()

    def _wrap_edge_columns(self, w, li):
        """
        **折り返しの境目に来る桁**を返す（項目48-II）。

        Tk は表示行のいちばん最後の塊の地色を、**行の右端まで塗る**。
        そこに空白があると、半角が全角より広く見えてしまう
        （画素で数えた: 半角 6px が 22〜63px になる・項目48-IG）。
        そこだけ四角を消したいので、桁を先に知る必要がある。

        **折り返していない行では `index` を1回呼ぶだけ**で終わる。
        論理行の終わりは伸びないので数えない（実測）。

        **同じ行・同じ幅・同じ字なら答えは変わらない**ので控えて
        使い回す（項目48-LI・2026-08-29。うにさんの報告「タブキーが
        あると動作が重いです。おそらく解析などのたびに、タブの
        色分け判定を繰り返している」——分割解析の一区切りごとに
        塗り直しが走り、タブのある行だけ、この折り返し数え
        （display の index を行ごとに最大64回）を毎回やり直していた）。
        """
        cache = getattr(self, '_wrap_edge_cache', None)
        if cache is None:
            cache = self._wrap_edge_cache = {}
        key = None
        try:
            key = (str(w), w.get(f'{li}.0', f'{li}.end'),
                   w.winfo_width(), str(w.cget('font')))
            got = cache.get(key)
            if got is not None:
                return got
        except Exception:
            key = None
        edges = set()
        try:
            logical = w.index(f'{li}.end')
            idx = f'{li}.0'
            for _ in range(64):
                e = str(w.index(f'{idx} display lineend'))
                if w.compare(e, '>=', logical):
                    break                      # 折り返していない／最後
                ln, col = e.split('.')
                if int(ln) != li:
                    break
                # **その桁の文字**が伸ばされる（画素で確かめた。
                # `display lineend` が 1.28 のとき、伸びるのは 28 桁目）
                edges.add(int(col))
                nxt = str(w.index(f'{e} +1c'))
                if w.compare(nxt, '<=', idx):
                    break
                idx = nxt
        except Exception:
            return edges        # しくじった答えは控えない
        if key is not None:
            if len(cache) > 2000:
                cache.clear()   # 増えすぎたら捨てるだけ（また貯まる）
            cache[key] = edges
        return edges

    def _on_toggle_show_whitespace(self):
        """表示メニュー「見えない空白を表示」の切り替え。"""
        try:
            self.settings.set('show_whitespace',
                              bool(self.show_whitespace_var.get()))
        except Exception:
            pass
        self._paint_whitespace()

    # ------------------------------------------------------------
    # 画面が動いたら、そこを先に解析する（項目48-IF・うにさんの指定）
    # ------------------------------------------------------------
    #
    #   「起動時に見えている範囲の解析結果がすぐでるのはよいが、
    #     **下にスクロールして見えた範囲は解析が終わらないと結果が
    #     出なくて待たされる**。スクロール後の見えた範囲を先に
    #     解析結果を反映させる」
    #
    # 並べ替えの仕組み（`_reprioritise_visible`・項目48-BS）は
    # 既にあった。**呼ばれる場所が悪かった**:
    #
    #   (1) `_analyze_chunk` の中からしか呼ばれない
    #   (2) その `_analyze_chunk` は、**触っている間はいちばん上で
    #       return する**ので、スクロール中は並べ替えに届かない
    #   (3) 見えているぶんを出し終わったあとの区切りは
    #       `ANALYZE_SLOW_GAP_MS`（300ms）空くので、**気付くのが遅い**
    #
    # だから**スクロールそのものから呼ぶ**。画面が動いた合図
    # （`yscrollcommand`）は毎回鳴っているので、そこから少し待って
    # （落ち着いてから）並べ替え、**予約し直して待ち時間を詰める**。
    WS_SCROLL_SETTLE_MS = 90

    def _on_view_moved(self):
        """画面が動いた。少し待ってから、見えている範囲を先に回す。"""
        job = getattr(self, '_view_moved_job', None)
        if job is not None:
            try:
                self.root.after_cancel(job)
            except Exception:
                pass
        try:
            self._view_moved_job = self.root.after(
                self.WS_SCROLL_SETTLE_MS, self._after_view_moved)
        except Exception:
            self._view_moved_job = None

    def _after_view_moved(self):
        self._view_moved_job = None
        if self._window_dragging():
            self._view_moved_job = self.root.after(100, self._after_view_moved)
            return
        # 空白の印は、見えている範囲にしか付いていない（項目48-IF）
        self._schedule_whitespace_paint(delay=1)
        todo = getattr(self, '_analyze_todo', None)
        if not todo:
            return
        pos = getattr(self, '_analyze_pos', 0)
        if pos >= len(todo):
            return          # 解析はもう終わっている（_finish_analysis が出した）
        # **もう分かっているぶんは、その場で出す**（項目48-JA）。
        # 飛んだ先の行が既に解析済みでも、**最後に塗ったのは
        # 最初の画面ぶんが揃ったとき**なので、画面には出ていない。
        # 1行も解析し直さずに出せるぶんが、待ち時間の頭にある。
        #
        # **並べ替えたかどうかに関わらず出す**（うにさんの報告・
        # 2026-08-25「解析中にスクロールすると、解析が終わるまで
        # 補正が反映されない。スクロールしてからタブ移動して戻って
        # くると、その範囲がすぐ補正反映される」）。
        #
        # 48-JA はこの塗りを**並べ替えの後ろ**に置いていたので、
        # `_reprioritise_visible` が False を返す道——
        #   (a) 飛んだ先が**もう全部解析済み**（`near` が空）
        #   (b) 次に解析する行が画面の中（もう見えているところを進めている）
        #   (c) 同じ範囲を二度走査しない（`band` が前回と同じ）
        #   (d) 残りがひと区切りぶんしかない
        # では**一度も塗られなかった**。(a) がうにさんの言う
        # 「タブを往復すると出る」場面そのもの——答えは既に手元に
        # あるのに、画面へ出す合図だけが無かった。
        # `_analyze_shown_visible` が立ったあとの区切りは塗らない
        # （項目48-FP）ので、ここで出さないと解析が終わるまで出ない。
        if pos > getattr(self, '_analyze_painted_pos', 0):
            self._analyze_painted_pos = pos
            self._analyze_last_paint_ms = time.monotonic() * 1000.0
            try:
                self._refresh_after_analysis(learn=False)
            except Exception:
                pass
        try:
            moved = self._reprioritise_visible()
        except Exception:
            moved = False
        if not moved:
            return
        # **待たせない。** 遅い区切り（300ms）で予約されていたら
        # 取り消して、すぐ次の区切りを回す。
        job = getattr(self, '_analyze_job', None)
        if job is not None:
            try:
                self.root.after_cancel(job)
            except Exception:
                pass
            self._analyze_job = None
        try:
            self._schedule_analysis_chunk()
        except Exception:
            pass

    def _visible_first(self, todo):
        """
        **画面に見えている行から先に解析する**（項目48-BP・
        うにさんの指摘「1000行あると待ち時間が長い」の続き）。

        977行のタブは、どう速くしても**全部で7秒**かかる
        （`correct_line` が1行 7ミリ秒。項目48-BO で測った）。
        だが**その人が見ているのは30行ほど**で、残りは
        スクロールするまで目に入らない。**見えている行を先に
        片付けて、そこで一度だけ描き直す**と、待ち時間は
        全部ぶんではなく見えているぶんで済む。

        **順番を変えても結果は変わらない。** 1行の補正が使う材料
        （文脈語彙・上下の行の語・直前に確定した語）は、どれも
        **解析の途中経過を見ていない**（`_prev_lines` と
        `recent_words` から作る）ので、どの順に解析しても同じ。

        戻り値: (並べ替えた todo, 先に片付ける件数)
        """
        try:
            n = len(todo)
        except Exception:
            return todo, 0
        # 少ないときは並べ替える意味がない（描き直しが1回増えるだけ）
        if n <= self.ANALYZE_CHUNK * 2:
            return todo, n
        band = self._visible_band()
        if band is None:
            return todo, n
        lo, hi = band
        near = [i for i in todo if lo <= i <= hi]
        if not near or len(near) == n:
            return todo, n
        far = [i for i in todo if not (lo <= i <= hi)]
        self._analyze_band = band
        # **描き直しの合図は「本当に映っている行」だけで出す**
        # （項目48-FH・うにさんの指摘「画面に映っている部分を
        #   優先的に解析して、その範囲が済んだらまず補正を反映」・
        #   2026-08-18）。
        #
        # `band` は上下に `VISIBLE_MARGIN`（20行）の余白を足した
        # 範囲。余白はスクロールに備えて**先に解析しておく**ための
        # ものなのに、**描き直しまでその余白ぶん待っていた**。
        # 画面に35行映っているなら、余白込みで75行——待ち時間が
        # **2倍以上**になっていた。
        #
        # 順番は今までどおり（映っている行 → 余白 → 残り）。
        # 変えたのは**いつ画面に出すか**だけ。
        screen = self._visible_band(margin=0)
        n_show = len(near)
        if screen is not None:
            slo, shi = screen
            on = [i for i in near if slo <= i <= shi]
            rest = [i for i in near if not (slo <= i <= shi)]
            if on:
                near = on + rest
                n_show = len(on)
        return near + far, n_show

    def _visible_band(self, margin=None):
        """
        いま画面に見えている行の範囲（0始まり）。

        margin: 上下に足す余白の行数。既定は `VISIBLE_MARGIN`。
            **0 を渡すと「本当に映っている行」だけ**になる
            （項目48-FH。描き直しの合図はこちらで出す）。

        戻り値: (上, 下) か、取れなければ None。
        """
        if margin is None:
            margin = self.VISIBLE_MARGIN
        try:
            top = int(str(self.editor.index('@0,0')).split('.')[0]) - 1
            height = max(1, self.editor.winfo_height() - 1)
            bottom = int(str(
                self.editor.index(f'@0,{height}')).split('.')[0]) - 1
        except Exception:
            return None
        # **これから当て直す位置**があるなら、そちらを見る
        # （項目48-FR・うにさんの指摘・2026-08-18）:
        #
        #   「1000行あって、タブが切り替えた際に500行目に居ると
        #     重いので、**見えている範囲の判定がずれている**気が
        #     します」
        #
        # そのとおりだった。タブを開いた直後の表示位置の当て直しは
        # `after_idle` に予約される（項目48-N。本文を入れた直後は
        # 配置が済んでおらず、その場では効かないため）。**解析は
        # それより先に走る**ので、`@0,0` はまだ**先頭**を指す。
        # つまり 500行目を見ているのに、**1行目から解析していた**。
        #
        # 当て直す先（`_pending_scroll_top`）はもう分かっているので、
        # **まだ先頭にいるなら、そちらを見えている範囲とみなす**。
        want_top = getattr(self, '_pending_scroll_top', None)
        if want_top and top <= 0:
            span = max(1, bottom - top)
            top = max(0, int(want_top) - 1)
            bottom = top + span
        return (top - margin, bottom + margin)

    def _reprioritise_visible(self):
        """
        **解析の途中でスクロールしたら、そこから先に片付け直す**
        （項目48-BS・48-BP に「まだやっていないこと」と書いた宿題）。

        48-BP は**解析を始めた時点**の画面だけを見ていた。
        977行のタブで下のほうへ飛ぶと、そこは後回しのままなので
        **十数秒待つ**ことになる——長いメモほど、飛んだ先を
        読みたいのに待たされる。

        ひと区切りごとに画面を見て、**まだ解析していない行が
        映っていたら、それを待ち行列の先頭へ移す**。
        映っている行が全部片付いていれば何もしない。

        **並べ替えるのは、まだ解析していないところだけ**
        （`_analyze_pos` より後ろ）。済んだところは触らない。
        順番を変えても補正結果が変わらないことは
        `_visible_first` と同じ理由（1行の補正は解析の途中経過を
        見ていない）で、`probes/probe_visible.py` と
        `probes/probe_order_learn.py` で突き合わせて確かめてある。

        戻り値: 並べ替えたら True
        """
        todo = getattr(self, '_analyze_todo', None)
        pos = getattr(self, '_analyze_pos', 0)
        if not todo or getattr(self, '_analyze_units_only', False):
            return False
        left = len(todo) - pos
        # 残りがひと区切りぶんしかないなら、並べ替えても意味が無い
        if left <= self.ANALYZE_CHUNK:
            return False
        # **次に解析する行が画面の中なら、もう見えているところを
        # 進めている**。毎回の走査を省くための、いちばん安い判定。
        band = self._visible_band()
        if band is None:
            return False
        lo, hi = band
        if lo <= todo[pos] <= hi:
            self._analyze_band = band
            return False
        # 画面は動いたが、映っている行はもう全部済んでいた——という
        # 状態は解析の後半ずっと続く。同じ範囲で二度走査しない。
        if band == getattr(self, '_analyze_band', None):
            return False
        self._analyze_band = band
        rest = todo[pos:]
        near = [i for i in rest if lo <= i <= hi]
        if not near:
            return False
        far = [i for i in rest if not (lo <= i <= hi)]
        # **描き直しの合図は「本当に映っている行」だけで出す**
        # （項目48-FH をこちらにも・項目48-IF・2026-08-21）。
        #
        # 48-FH は**起動時の並べ替え**（`_visible_first`）にだけ
        # 入れていた。**スクロール側には無かった**ので、飛んだ先で
        # 「見えている行が片付いた」と数えるときに、上下 20行ずつの
        # **余白 40行まで待っていた**。画面に23行映っているなら、
        # 余白込みで63行——**待ち時間が2.7倍**になっていた。
        # 学び22「片方だけに置くと、そちらを迂回して素通りする」。
        #
        # 順番は今までどおり（映っている行 → 余白 → 残り）。
        # 変えたのは**いつ画面に出すか**だけ。
        screen = self._visible_band(margin=0)
        n_show = len(near)
        if screen is not None:
            slo, shi = screen
            on = [i for i in near if slo <= i <= shi]
            rest = [i for i in near if not (slo <= i <= shi)]
            if on:
                near = on + rest
                n_show = len(on)
        self._analyze_todo = todo[:pos] + near + far
        # **飛んだ先が片付いた時点で、もう一度描き直す**。
        # 48-BP の「一度だけ」を、スクロールのたびに巻き直す形。
        self._analyze_visible_n = pos + n_show
        self._analyze_shown_visible = False
        # 飛んだ先はまだ1行も塗っていない（項目48-JA）。
        self._analyze_painted_pos = pos
        self._analyze_last_paint_ms = 0.0
        return True

    # **人が触っている間は、解析の手を緩める**（項目48-FL）。
    #
    # うにさんの指摘（2026-08-18）:
    #   「解析中の操作が重いです。スクロールや、ウインドウの
    #     ドラッグ移動など」
    #
    # ひと区切り 60ms 働いて **1ms しか譲っていなかった**ので、
    # 画面が使える時間は 1.6% しかなかった。触っている間だけ
    # **短く働いて長く譲る**。触っていなければ今までどおり急ぐ
    # （総時間を延ばさないため）。
    ANALYZE_BUSY_GAP_MS = 30         # 触っている間に譲る時間
    ANALYZE_BUSY_WINDOW_MS = 250     # 最後の操作から、この間は「触っている」
    # 譲り続ける上限。これを超えたら1行だけ進める
    # （30ms × 40 ＝ 約1.2秒。触り続けても止まりっぱなしにしない）
    ANALYZE_MAX_YIELD = 40
    # **見えていないぶんは、ゆっくり進める**（項目48-FP・
    # うにさんの指定・2026-08-18「見えてない範囲の解析はもっと
    # 遅く進めてもよいです」）。1行が約100ms かかるので、
    # 続けて回すと画面がずっと引っかかる。1行ごとに大きく譲る。
    # 1行が約100ms なので、150ms 空けても4割は主スレッドを使う。
    # うにさんの「もっと遅くてよい」に甘えて、**300ms**空ける
    # （＝主スレッドを使うのは2割強）。画面に見えている範囲へ
    # スクロールされたら `_reprioritise_visible` が
    # `_analyze_shown_visible` を戻すので、そこは**また速くなる**。
    ANALYZE_SLOW_GAP_MS = 300
    ANALYZE_SLOW_COUNT = 1
    # **見えている範囲は、揃うのを待たずに出す**
    # （項目48-JA・2026-08-23・うにさんの報告「解析中に
    # スクロールした後、見えている範囲の解析反映が遅い」）。
    #
    # 48-IF で「飛んだ先を先に解析する」までは作ったが、
    # **画面に出すのは見えている行が全部片付いてから**
    # だった（`_analyze_shown_visible` が一度きりの旗）。
    # 画面に23行映っていれば、1行 24ms でも **0.6秒**、
    # 重い行が混ざれば数秒、**その間ずっと1行も出ない**。
    #
    # 直りは1行ずつ独立している（順番を変えても答えが
    # 変わらないのは 48-BS で確かめてある）ので、
    # **途中まででも出してよい**。この間合いごとに
    # 塗り直す。全部片付いたときの一度きりの塗り直しは
    # そのまま残す（そこで「終わった」旗が立つ）。
    ANALYZE_PAINT_GAP_MS = 150
    # **他のタブを裏で進める**ときの間合い（項目48-FQ）。
    # いま見ているタブより、さらにゆっくり。
    ANALYZE_BG_GAP_MS = 700
    # **触っていない間は、裏をまとめて進める**（2026-08-27・うにさんの
    # 再報告「今はまだ、そのタブに切り替えないと解析が始まらない」）。
    # 1行 0.7秒＋触っている間は完全停止、では 1000行のタブに10分以上
    # かかり、**切り替えのほうが先に来る**＝裏の意味が無かった。
    # 最後の操作からこの時間が過ぎたら「離席・読んでいる」とみなし、
    # ひと区切りの持ち時間ぶんまとめて進める（触った瞬間に戻る）。
    ANALYZE_BG_IDLE_MS = 3000
    ANALYZE_BG_FAST_BUDGET_MS = 45
    ANALYZE_BG_FAST_GAP_MS = 120

    def _on_select_all(self, event=None):
        """
        **全選択（Ctrl+A）。上下の空行は選ばない**（項目48-FK）。

        うにさんの指定（2026-08-18）:
        「Ctrl+Aで全選択する際は、**改行だけの上下の余白を除外**する」

        tkinter の既定は `1.0` 〜 `end` なので、書き出しや末尾に
        残った空行までコピーに付いてくる。**中の空行は残す**
        （段落の切れ目なので、消すと文章の形が変わる）。
        落とすのは**先頭と末尾の、空白しかない行**だけ。
        """
        w = getattr(event, 'widget', None) or self.editor
        try:
            lines = w.get('1.0', 'end-1c').split('\n')
        except Exception:
            return None
        first, last = 0, len(lines) - 1
        while first <= last and not lines[first].strip():
            first += 1
        while last >= first and not lines[last].strip():
            last -= 1
        try:
            w.tag_remove('sel', '1.0', 'end')
            if first > last:
                # 中身が空白だけ。既定どおり全部選ぶ
                w.tag_add('sel', '1.0', 'end-1c')
            else:
                w.tag_add('sel', f'{first + 1}.0', f'{last + 1}.end')
                w.mark_set('insert', f'{last + 1}.end')
            w.focus_set()
        except Exception:
            return None
        return 'break'

    def _note_interaction(self, event=None):
        """スクロール・ドラッグ・キーなど、人が触った印を付ける。"""
        import time as _time
        self._last_interaction = _time.monotonic()
        if (event is not None and getattr(event, 'widget', None) is self.root
                and str(getattr(event, 'type', '')) == '22'):
            self._track_window_position(event)

    def _interacting(self):
        import time as _time
        # **俯瞰の間・右ドラッグの間は、動いていなくても「触っている」**
        # （項目48-SY）。ボタンを押したまま止めていると 250ms で解析が
        # 再開し、枠の付け直しと描き直しが止まって見えていた
        if self._view_changing():
            return True
        if getattr(self, '_overview', None) is not None:
            return True
        _d = getattr(self, '_drag', None)
        if _d and _d.get('mode') == 'scroll':
            return True
        t = getattr(self, '_last_interaction', None)
        if t is None:
            return False
        return (_time.monotonic() - t) * 1000.0 < self.ANALYZE_BUSY_WINDOW_MS

    def _schedule_analysis_chunk(self):
        if self._interacting():
            gap = self.ANALYZE_BUSY_GAP_MS
        elif getattr(self, '_analyze_shown_visible', False):
            # 見えているぶんはもう出した。ここから先は**ゆっくり**
            # （項目48-FP）。
            gap = self.ANALYZE_SLOW_GAP_MS
        else:
            gap = 1
        self._analyze_job = self.root.after(gap, self._analyze_chunk)

    def _analyze_chunk(self):
        self._analyze_job = None
        if self._view_changing():
            self._schedule_analysis_chunk()
            return
        # 控えから復元した回は、1行あたりの仕事が桁違いに軽い
        # （描画用の単位を組み立てるだけ・0.5ms 程度）。20行ずつだと
        # 予約の往復のほうが高くつくので、まとめて進める。
        # 時間の上限（budget_ms）は同じなので画面は固まらない。
        count = (self.ANALYZE_CHUNK * 10
                 if getattr(self, '_analyze_units_only', False)
                 else self.ANALYZE_CHUNK)
        # **触っている間は、まるごと手を止める**（項目48-FL・
        # 2026-08-18 に measure して作り直した）。
        #
        # 最初は「12ms 働いて 24ms 譲る」にしたが、**効かなかった**
        # （うにさんから「ほぼできません」）。理由は測って分かった:
        # **1行の補正が約100ms かかる**ので、いくら短い持ち時間を
        # 渡しても、`_analyze_slice` は必ず1行は進めてしまう。
        # 時間で区切る形は、**1行が持ち時間より重い**と意味が無い。
        #
        # だから、触っている間は**1行も進めない**。指を止めれば
        # すぐ（`ANALYZE_BUSY_WINDOW_MS` 後に）続きから再開する。
        # ただし**止まりっぱなしにはしない**: 譲り続けた回数が
        # `ANALYZE_MAX_YIELD` を超えたら、1行だけ進める
        # （`<Configure>` が鳴り続ける環境でも前へ進むため）。
        if (self._interacting()
                and not getattr(self, '_analyze_units_only', False)):
            self._analyze_yields = getattr(self, '_analyze_yields', 0) + 1
            # **ボタンを押したまま（俯瞰・右ドラッグ）の間は、1行も
            # 進めない**（項目48-SY）。「止まりっぱなしにしない」の
            # 1行は `<Configure>` が鳴り続ける環境のためのもので、
            # 人がボタンを押し続けている間は、その1行（約100ms）が
            # 枠の付け直しと描き直しを止めて見える
            _held = (getattr(self, '_overview', None) is not None
                     or ((getattr(self, '_drag', None) or {})
                         .get('mode') == 'scroll'))
            if self._analyze_yields <= self.ANALYZE_MAX_YIELD or _held:
                self._schedule_analysis_chunk()
                return
            self._analyze_yields = 0
            count = 1
        else:
            self._analyze_yields = 0
            if (getattr(self, '_analyze_shown_visible', False)
                    and not getattr(self, '_analyze_units_only', False)):
                # 見えていないぶん（項目48-FP）
                count = self.ANALYZE_SLOW_COUNT
        self._analyze_slice(count, budget_ms=self.ANALYZE_BUDGET_MS)
        done, total = self._analyze_pos, len(self._analyze_todo)
        # **見えている行が片付いたら、そこで一度だけ描き直す**
        # （項目48-BP）。残りは裏で進めるので、その人から見た
        # 待ち時間は「見えているぶん」で終わる。
        _vis_n = getattr(self, '_analyze_visible_n', 0)
        if (not getattr(self, '_analyze_shown_visible', False)
                and _vis_n > 0 and done < total):
            _all_shown = (done >= _vis_n)
            _now = time.monotonic() * 1000.0
            _since = _now - getattr(self, '_analyze_last_paint_ms', 0.0)
            _new_lines = done > getattr(self, '_analyze_painted_pos', 0)
            # 全部揃ったときは必ず出す。途中でも、新しく片付いた行が
            # あって間合いが空いていれば出す（項目48-JA）。
            if _all_shown or (_new_lines
                              and _since >= self.ANALYZE_PAINT_GAP_MS):
                if _all_shown:
                    self._analyze_shown_visible = True
                self._analyze_last_paint_ms = _now
                self._analyze_painted_pos = done
                try:
                    self._refresh_after_analysis(learn=False)
                except Exception:
                    pass
        elif done < total:
            # **旗が立ったあとも、いま片付いた行が画面の中なら出す**
            # （うにさんの報告・2026-08-27「解析中にスクロールすると、
            # 解析が終わるまで補正が反映されない」）。
            #
            # 48-JA の塗りは `_analyze_shown_visible` が立つと止まり、
            # スクロールで並べ替え（`_reprioritise_visible`）が起きれば
            # 旗が戻る——が、**次に解析する行がもう画面の中**のとき
            # （解析の先端のすぐ先を見ているとき）は並べ替え自体が
            # 起きず、旗が立ったまま解析だけが進んで**一度も塗られ
            # なかった**。タブを往復すると出るのは、控えからの
            # 全塗りが走るから。
            #
            # 出すのは「新しく片付いた行が、本当に映っている範囲に
            # 掛かっているとき」だけ（先端が画面の外なら今までどおり
            # 塗らない＝余計な描き直しは増やさない）。
            _now = time.monotonic() * 1000.0
            _since = _now - getattr(self, '_analyze_last_paint_ms', 0.0)
            _p = getattr(self, '_analyze_painted_pos', 0)
            if done > _p and _since >= self.ANALYZE_PAINT_GAP_MS:
                _band = self._visible_band(margin=0)
                if _band is not None and any(
                        _band[0] <= i <= _band[1]
                        for i in self._analyze_todo[_p:done]):
                    self._analyze_last_paint_ms = _now
                    self._analyze_painted_pos = done
                    try:
                        self._refresh_after_analysis(learn=False)
                    except Exception:
                        pass
        # **途中でスクロールしたら、飛んだ先を先に片付ける**
        # （項目48-BS）。描き直しの判定の**後ろ**に置く。前に置くと、
        # せっかく揃った最初の画面ぶんの描き直しが、スクロールの
        # たびに後ろへずれる。
        try:
            self._reprioritise_visible()
        except Exception:
            pass
        if done < total:
            try:
                self.status.config(text=f'解析中… {done}/{total} 行')
            except Exception:
                pass
            self._schedule_analysis_chunk()
            return
        try:
            self.status.config(text='')
        except Exception:
            pass
        self._finish_analysis()

    # 解析結果を覚えておくタブの数。実機のタブは6つほどなので、
    # 全部持っても軽い（1000行ぶんでも数百KB）。
    ANALYSIS_CACHE_TABS = 12

    def _restore_pending_scroll(self, final=False):
        """
        タブを開いたときの表示位置を当て直す（項目48-N）。

        **一度当てただけでは戻ってしまう。** 本文を入れた直後は
        入力欄の配置が済んでおらず、そのあとの描き直しと2つの欄の
        スクロール合わせで、先頭に引き戻される（Xvfb で確認:
        読み込み直後は 0.513 に当たっているのに、次の合間には
        0.000 に戻っている）。だから
        **配置が済んだとき**と**最初の解析が終わったとき**の
        2回当て、最後の1回で控えを下ろす。

        **利用者が自分で動かしていたら邪魔しない。** いまの位置が
        「先頭」でも「こちらが当てた位置」でもなければ、
        利用者が動かしたということなので、そこで打ち切る。

        両方の欄に当てる。片方だけだと、スクロールの連動で
        もう片方（先頭のまま）に引きずられて戻る。
        """
        want = getattr(self, '_pending_scroll', 0.0)
        want_top = getattr(self, '_pending_scroll_top', None)
        if not want and not want_top:
            return
        try:
            now = self.editor.yview()[0]
            mine = getattr(self, '_pending_scroll_applied', None)
            if now > 0.001 and (mine is None or abs(now - mine) > 0.005):
                self._pending_scroll = 0.0      # 利用者が動かした
                self._pending_scroll_top = None
                return
            for widget in (self.editor, getattr(self, 'result_view', None)):
                if widget is None:
                    continue
                try:
                    if want_top:
                        # **行番号で当てる**（2026-08-16）。割合は
                        # 折り返し・解析後の描き直しで意味がずれ、
                        # 「タブ移動して戻るとスクロール位置が変わる」
                        # の原因だった。行なら配置に依らない。
                        # （`yview(index)` は、その位置を窓のいちばん
                        #   上に置く Tk の古い呼び方。両欄は行数が
                        #   常に同じなので、同じ行番号でよい。）
                        widget.yview(f'{want_top}.0')
                    else:
                        widget.yview_moveto(want)
                except Exception:
                    pass
            self._pending_scroll_applied = self.editor.yview()[0]
            try:
                self.editor_gutter.redraw()
                self.result_gutter.sync_yview(*self.result_view.yview())
            except Exception:
                pass
        except Exception:
            self._pending_scroll = 0.0
            self._pending_scroll_top = None
            return
        if final:
            self._pending_scroll = 0.0
            self._pending_scroll_top = None

    def _learn_charngram(self, line):
        """
        ★★ **もう覚えない**（項目48-QL・2026-09-05）。

        うにさんの指定への Fable の推奨「初期分だけ（＝同梱の初期分
        だけ使い、育ちの保存をやめる）」に**うにさんが「推奨のとおり」
        と答えた**。字の並びの表は**本人の書いた行そのもの**から
        育つので、残すと「人に見られたくないデータが保存されている」
        ことになる。

        呼び出し口（`_analyze_slice`）はそのまま残してある——
        **道を消すのではなく、覚えるのをやめる**（学び22。道ごと
        消すと、あとで初期分を差し込みたくなったときに口が無い）。
        """
        return

    def _finish_analysis(self):
        """解析結果を画面に反映し、語彙の学習を予約する。"""
        # ★★ **字の並びの表は、もう書き出さない**（項目48-QL・
        # 2026-09-05。うにさんの指定「推奨のとおり初期分だけ」）。
        # 覚える側（`_learn_charngram`）も止めてあるので、
        # 書き出しても中身は変わらないが、**書かないことを
        # ここでもはっきりさせる**（学び22——片方だけ止めると、
        # もう片方が古い中身を書き戻す）。
        self._remember_tab_results()
        self._refresh_after_analysis(learn=True)
        # 解析が終わって描き直したあとにも当て直す。折り返しで
        # 行の高さが変わるので、解析前に当てた位置はずれている。
        self._restore_pending_scroll(final=True)
        # 控えから復元した回は `_analyze` が途中で戻るので、
        # 候補づくりの材料が集まっていない。落ち着いてから作る。
        if not getattr(self, '_attested_surfaces', None):
            try:
                self.root.after(1200, self._ensure_attested)
            except Exception:
                pass
        # **このタブが済んだら、他のタブを裏で進める**（項目48-FQ）
        try:
            self.root.after(1500, self._start_background_tabs)
        except Exception:
            pass

    # ------------------------------------------------------------
    # 他のタブを裏で進める（項目48-FQ）
    # ------------------------------------------------------------
    #
    # うにさんの指定（2026-08-18）:
    #   「ひとつのタブの解析が終わったら、**次のタブの解析も
    #     進めていってください**」
    #
    # 済ませた結果は `_analysis_cache`（本文を鍵にした控え・項目48-M）
    # へ入れる。次にそのタブを開いたときは**一瞬**で出る。
    #
    # **表に出ているタブの解析よりさらにゆっくり**進める。
    # 触っている間は1行も進めない（48-FO と同じ構え）。
    #
    # **学習はしない。** 語彙も文字の並びの表も触らない
    # （裏で学ぶと、いま見ている画面の答えが裏で変わってしまう）。

    def _start_background_tabs(self):
        """裏で進めるタブを選び、1行ずつの歩みを始める。"""
        if getattr(self, '_bg_job', None) is not None:
            return
        # **表のタブの解析が済むまでは始めない**。済めば
        # `_finish_analysis` がまた呼ぶ。学習が控えを捨てた直後の
        # 再開（`_invalidate_analysis_cache`）が、表の解析と
        # 取り合いにならないための門。
        try:
            _todo = getattr(self, '_analyze_todo', None)
            if _todo and getattr(self, '_analyze_pos', 0) < len(_todo):
                return
        except Exception:
            pass
        try:
            sess = self.session
            cur = max(0, min(sess.active, len(sess.tabs) - 1))
            todo = []
            # **いま見ているタブの次から**回る（2026-08-27）。番号順だと
            # 先頭の大きいタブに時間を吸われて、次に開きそうなタブが
            # いつまでも来ない。
            n = len(sess.tabs)
            order = [(cur + k) % n for k in range(1, n)] if n > 1 else []
            # **いま離れたタブを先に**（項目48-RY）。2枚を行き来している
            # ときは、戻る先はたいてい直前のタブ
            _pa = getattr(self, '_prev_active', None)
            if isinstance(_pa, int) and 0 <= _pa < n and _pa != cur \
                    and _pa in order:
                order.remove(_pa)
                order.insert(0, _pa)
            for i in order:
                tab = sess.tabs[i]
                # **鍵は `_analysis_key` で作る**（学び22。ここで
                # 別々に作っていたので、裏で進めた結果は一度も
                # 使われていなかった——`_analysis_key` の説明を読む）。
                text = self._analysis_key(tab.get('text') or '')
                if not text.strip():
                    continue
                if text in self._analysis_cache                         and text not in getattr(self,
                                                '_analysis_stale', ()):
                    continue        # 新しい控えがある＝作り直し不要
                todo.append(text)
        except Exception:
            return
        if not todo:
            return
        self._bg_texts = todo
        self._bg = None
        self._bg_job = self.root.after(self.ANALYZE_BG_GAP_MS,
                                       self._bg_step)

    def _bg_step(self):
        """
        裏のタブを進める。

        触っている間は1歩も進めない（48-FO と同じ構え）。触っていても
        いなくても、しばらく（`ANALYZE_BG_IDLE_MS`）操作が無ければ
        「離席・読んでいる」とみなし、ひと区切りの持ち時間
        （`ANALYZE_BG_FAST_BUDGET_MS`）ぶん**まとめて**進める
        （2026-08-27。1行 0.7秒では 1000行のタブに10分以上かかり、
        切り替えのほうが先に来る＝裏の意味が無かった）。
        操作が戻れば、次の区切りからまた1行ずつに落ちる。
        """
        self._bg_job = None
        if self._interacting():
            self._bg_job = self.root.after(self.ANALYZE_BG_GAP_MS,
                                           self._bg_step)
            return
        import time as _time
        t = getattr(self, '_last_interaction', None)
        idle_ms = 1e9 if t is None else (_time.monotonic() - t) * 1000.0
        fast = idle_ms >= self.ANALYZE_BG_IDLE_MS
        deadline = _time.monotonic() + self.ANALYZE_BG_FAST_BUDGET_MS / 1000.0
        while True:
            more = self._bg_step_once()
            if not more:
                return                  # 全部済んだ
            if not fast or _time.monotonic() >= deadline:
                break
        gap = (self.ANALYZE_BG_FAST_GAP_MS if fast
               else self.ANALYZE_BG_GAP_MS)
        self._bg_job = self.root.after(gap, self._bg_step)

    def _bg_step_once(self):
        """裏のタブを**一歩だけ**進める。続きがあるなら True。"""
        try:
            if self._bg is None:
                if not getattr(self, '_bg_texts', None):
                    return False
                text = self._bg_texts.pop(0)
                if text in self._analysis_cache                         and text not in getattr(self,
                                                '_analysis_stale', ()):
                    return bool(self._bg_texts)
                # **預かってあるなら、その続きから**（項目48-RE）
                _parked = getattr(self, '_bg_parked', None) or {}
                _st = _parked.pop(text, None)
                if _st is not None:
                    self._bg = _st
                    return True
                lines = text.split('\n')
                self._bg = {'text': text, 'lines': lines,
                            'results': [None] * len(lines), 'pos': 0,
                            'ctx': None}
                return True
            st = self._bg
            if st['ctx'] is None:
                # **文脈語彙は、行ごとの控えを使う**ので、
                # ここで作っても2度目からは安い（項目48-BV）。
                from vocabulary import build_context_vocab_cached
                if not hasattr(self, '_ctx_vocab_cache'):
                    self._ctx_vocab_cache = {}
                st['ctx'] = build_context_vocab_cached(
                    st['lines'], self.store, self._ctx_vocab_cache)
                return True
            i = st['pos']
            if i < len(st['lines']):
                # **表が済ませていた行は飛ばす**（項目48-RY。途中で移った
                # タブの預かりは、見えていた行から先に埋まっている）
                if st['results'][i] is None:
                    st['results'][i] = self._bg_correct(st, i)
                st['pos'] = i + 1
            if st['pos'] >= len(st['lines']):
                if all(r is not None for r in st['results']):
                    self._analysis_cache[st['text']] = st['results']
                    try:
                        self._analysis_stale.discard(st['text'])
                    except Exception:
                        pass
                    self._prune_analysis_cache(keep=st['text'])   # 48-SH
                    try:
                        (getattr(self, '_bg_parked', None)
                         or {}).pop(st['text'], None)
                    except Exception:
                        pass
                    while len(self._analysis_cache) > self.ANALYSIS_CACHE_TABS:
                        self._analysis_cache.pop(
                            next(iter(self._analysis_cache)))
                self._bg = None
        except Exception:
            self._bg = None
        return bool(getattr(self, '_bg', None) is not None
                    or getattr(self, '_bg_texts', None))

    def _bg_correct(self, st, i):
        """裏のタブの1行を補正する（学習はしない）。"""
        try:
            from context_vec import build_nearby_words, extract_content_words
            lines = st['lines']

            def _words(k, _l=lines):
                if not (0 <= k < len(_l)):
                    return []
                s = _l[k]
                cache = getattr(self, '_line_words_cache', None)
                if cache is None:
                    cache = self._line_words_cache = {}
                got = cache.get(s)
                if got is None:
                    fn = getattr(self.store, '_tokenize_fn', None)
                    if fn is None:
                        return []
                    got = extract_content_words(fn, s)
                    cache[s] = got
                return got
            nearby = build_nearby_words(len(lines), i, _words)
        except Exception:
            nearby = ()
        try:
            return correct_line(
                lines[i], self.store, context_vocab=st['ctx'],
                decisions=self.decisions,
                input_method=self.settings.get('input_method'),
                context_vec=self.context_vec, dict_index=self.dict_index,
                nearby_words=nearby, recent_words=())
        except Exception:
            return self._blank_result(lines[i])

    #: 途中まで進めた裏のタブを、いくつまで預かるか（項目48-RE）
    BG_PARKED_MAX = 6

    def _stop_background_tabs(self):
        """
        裏の歩みを止める（本文が変わった・タブを移った等）。

        ★★ **途中まで進めたぶんは捨てずに預ける**（項目48-RE・
        2026-09-05・うにさんの報告「タブ移動すると解析が始まる。
        **裏の先読みが動いていない**」）。

        一巡の仕組み（`(cur+k) % n`）は前から在って正しく回っている
        ——「先頭に戻る処理が無い」のほうは当たっていなかった。
        止まっていた本当の理由は、**`_analyze` が走るたびに
        `_cancel_analysis_job` → ここが呼ばれ、`self._bg = None` で
        その時点までに補正した行を丸ごと捨てていた**こと。
        控えに入るのは**最後の1行まで行ったときだけ**（`_bg_step_once`）
        なので、打っている間は**成果が永久に 0 行**だった。

        預けるのは**本文を鍵にした途中経過**なので、本文が変われば
        鍵が変わって自然に外れる（古いものを使ってしまう心配が無い）。
        語彙が変わったときは `_invalidate_analysis_cache` が一緒に
        捨てる（答えが変わるため）。
        """
        job = getattr(self, '_bg_job', None)
        if job is not None:
            try:
                self.root.after_cancel(job)
            except Exception:
                pass
        self._bg_job = None
        st = getattr(self, '_bg', None)
        if st and st.get('pos'):
            parked = getattr(self, '_bg_parked', None)
            if parked is None:
                parked = self._bg_parked = {}
            parked[st['text']] = st
            while len(parked) > self.BG_PARKED_MAX:
                parked.pop(next(iter(parked)))
        self._bg = None
        self._bg_texts = []

    def _remember_tab_results(self):
        """
        解析し終えた結果を、**本文を鍵にして**覚えておく（項目48-M）。

        うにさんの報告（2026-08-11）:「タブ切り替えで解析が走り、
        5秒以上待たされます」。48-L で控えを入れたが、
        **保存していたのが開いていたタブ1つぶんだけ**だったので、
        別のタブへ移ると結局まるごと解析し直していた。
        解析が終わるたびにここへ入れておけば、
        **一度見たタブに戻るのは一瞬**になる。

        本文そのものを鍵にするので、タブを並べ替えても、同じ内容の
        タブが2つあっても取り違えない。中身が1文字でも変われば別の
        鍵になるので、古い結果を新しい本文に当てることも無い。

        **鍵は `_analysis_key`（末尾の空行を落とした形）で作る。**
        理由はそちらの説明を読むこと。
        """
        try:
            text = self._analyze_text
            results = self.line_results
            if not text or not results:
                return
            if len(results) != len(text.split('\n')):
                return
            key = self._analysis_key(text)
            if not key:
                return              # 空のタブ。覚えるものが無い
            n = len(key.split('\n'))
            cache = self._analysis_cache
            cache[key] = results[:n]
            try:
                self._analysis_stale.discard(key)
            except Exception:
                pass
            # ★★ **同じタブの古い本文の控えを先に落とす**（項目48-SH・
            # 2026-09-06）——下の「古いものから落とす」より前に
            self._prune_analysis_cache(keep=key)
            while len(cache) > self.ANALYSIS_CACHE_TABS:
                cache.pop(next(iter(cache)))    # 古いものから落とす
        except Exception:
            pass

    def _prune_analysis_cache(self, keep=None):
        """
        **いま在るどのタブの本文にも当たらない控えを落とす**（項目48-SH・
        2026-09-06・うにさんの報告「全てのタブの分析が終わった後、
        テキスト編集してから、まったく変更していないタブに移動すると
        分析が始まる」）。

        控えは**本文を鍵**にしている（`_analysis_key`）。表のタブで
        1文字打つたびに解析が済んで `_remember_tab_results` が
        **新しい本文の鍵で1件足す**ので、打ち続けると**同じタブの古い
        本文の控えが何件も積もる**。上限（`ANALYSIS_CACHE_TABS`＝12）
        は「古いものから落とす」なので、積もったぶんだけ**別のタブの
        控えが押し出され**、そのタブへ移ると全行の解析になっていた
        （`tools_local/probe_edit_switch.py` で再現: 4タブ・上限4・
        表のタブを5回編集 → 触っていないタブで `correct_line` 36回）。

        落とすのは「いま在るタブのどの本文（`_analysis_key`）にも
        当たらない鍵」だけ。いま解析している本文（`keep`）は、
        `_capture_session` がまだタブに写していないことがあるので
        必ず残す。**答えは1つも変えない**（当たらない鍵は二度と
        引かれない控え）。
        """
        try:
            cache = getattr(self, '_analysis_cache', None)
            if not cache:
                return
            live = set()
            sess = self.session
            tabs = getattr(sess, 'tabs', None) or ()
            k0 = self._analysis_key(getattr(self, '_analyze_text', '') or '')
            try:
                _cur = max(0, min(sess.active, len(tabs) - 1))
            except Exception:
                _cur = -1
            for _i, tab in enumerate(tabs):
                # **いま見ているタブは、いま解析している本文のほう**——
                # タブに控えた本文（打つ前の形）は `_capture_session` まで
                # 古いままなので、そちらを生かすと**打つ前の控え**が残って
                # 1件ぶん押し出す（実測: 4タブ・上限4で触っていないタブが
                # 落ちた）
                if _i == _cur and k0:
                    continue
                k = self._analysis_key(tab.get('text') or '')
                if k:
                    live.add(k)
            if k0:
                live.add(k0)
            if keep:
                live.add(keep)
            dead = [k for k in cache if k not in live]
            for k in dead:
                cache.pop(k, None)
                try:
                    self._analysis_stale.discard(k)
                except Exception:
                    pass
        except Exception:
            pass

    def _invalidate_analysis_cache(self, keep_current=True):
        # 48-VW: 語彙や判断が変わったときは、別タブの描画の控えも無効。
        self._tab_units_cache = {}
        # 裏で作りかけのものも捨てる（項目48-FQ）
        try:
            self._stop_background_tabs()
        except Exception:
            pass
        # ★★ **預かりは、控えと同じ扱いにする**（項目48-RJ・
        # 2026-09-05・うにさんの報告「次のタブの先読みが動いて
        # いません」）。
        #
        # 48-RE で「止められても捨てない」形にしたのに、**学習が
        # 走るたびにここで捨てて**いた——`_learn_now` は打鍵の3秒後、
        # 裏がまとめて進み始めるのも3秒後（`ANALYZE_BG_IDLE_MS`）
        # なので、**速い歩みが始まる前に必ず捨てられて**いた。
        # ＝48-RE の預かりは最初の3秒しか生きていなかった。
        #
        # 48-LF の理屈——「学習1回で他のタブの答えが変わることは稀。
        # 『また解析』の待ちのほうが害」——は、**途中まで進めた
        # ぶんにもそのまま当てはまる**。控えを捨てずに
        # `_analysis_stale` の印だけ付けるのと同じで、
        # **預かりも残して、続きから進めて完成させる**
        # （完成しても stale の印は残るので、暇なときに作り直す）。
        #
        # `keep_current=False`（入力方式の切り替え）は**今までどおり
        # 全部捨てる**——あちらは答えの形そのものが変わる。
        try:
            if keep_current:
                # 途中まで進めたぶんは「古いかもしれない」印を付けて
                # 残す（切り替えは今までどおり stale でも即座に使う）
                _parked = getattr(self, '_bg_parked', None) or {}
                if _parked:
                    self._analysis_stale = (
                        getattr(self, '_analysis_stale', set())
                        | set(_parked))
            else:
                self._bg_parked = {}
        except Exception:
            pass
        # **捨てたら、裏の歩みを立て直す**（うにさんの報告・2026-08-27
        # 「今は、そのタブに切り替えないと解析が始まらない」）。
        # 裏の歩みを始めるのは `_finish_analysis` だけだったので、
        # 解析の 3秒後に走る学習（`_learn_now`）がここを通ると、
        # 1.5秒後に始まった裏の歩みが**殺されたきり再開しなかった**。
        # 控えが当てにならなくなったのなら、作り直しも要る——
        # 止めるだけで終わらせない。表の解析が走っている間は
        # `_start_background_tabs` の頭の門が見送る（終われば
        # `_finish_analysis` がまた呼ぶ）。
        try:
            self.root.after(1500, self._start_background_tabs)
        except Exception:
            pass
        """
        覚えている解析結果を捨てる。

        **補正の答えが変わりうることをしたら、必ずここを呼ぶ。**
        語彙を覚えた・選び直しを記録した／取り消した・
        「この補正は不要」を記録した、のいずれも該当する。
        呼び忘れると**古い答えを新しい語彙のもとで表示する**ことに
        なり、「正しく書いたものを壊さない」に反する。

        keep_current=True（既定）: **どのタブの控えも捨てない**。
            他のタブのぶんに「古いかもしれない」印（`_analysis_stale`）
            を付けるだけにする（項目48-LF・2026-08-29）。戻ったタブは
            控えで即表示し、作り直しは裏の温め（48-FQ）に任せる。
            以前はいま見ているタブ以外を捨てていたので、**別のタブで
            1文字打つ（＝学習が走る）だけで、戻るたびに丸ごと解析**
            になっていた（うにさんの報告）。

        keep_current=False: いま見ているタブのぶんも捨てる。
            **そのあと `_prev_lines` を空にして解析し直す**ときは
            必ずこちら。`_analyze` は `_prev_lines` が空だと
            `_use_analysis_cache` を見に行くので、残しておくと
            **古い答えをそのまま拾って解析を飛ばす**。
            入力方式の切り替え（項目48-S）がこの形。
        """
        try:
            if keep_current:
                # **他のタブの控えは捨てない。「古いかもしれない」印だけ
                # 付ける**（項目48-LF・2026-08-29。うにさんの報告
                # 「解析が終わってからタブ移動して、移動先タブで何か
                # 入力してから元のタブに戻ると、また解析が走ります」。
                # 学習のたびにここが他のタブの控えを捨てていたのが正体
                # ——1文字打つだけで学習が走るので、戻るたび丸ごと
                # 解析になっていた）。
                # 戻ったタブは控えで**すぐ表示**し、作り直しは裏の
                # 温め（項目48-FQ）が静かにやる。学習1回で他のタブの
                # 答えが変わることは稀で、変わる場合も次の打鍵の
                # 差分解析で追いつく——「また解析」の待ちのほうが害。
                keep = self._analysis_key(
                    getattr(self, '_analyze_text', None))
                stale = set(self._analysis_cache)
                stale.discard(keep)
                self._analysis_stale = (
                    getattr(self, '_analysis_stale', set()) | stale)
            else:
                self._analysis_cache = {}
                self._analysis_stale = set()
        except Exception:
            self._analysis_cache = {}
            self._analysis_stale = set()

    def _refresh_after_analysis(self, learn=True):
        """
        いまの line_results を画面へ反映する。

        分割解析の途中でも呼ばれる（まだ解析していない行は
        仮置きの「補正なし」として描かれる）。
        """
        try:
            saved_cursor = self.editor.index('insert')
            had_focus = (self.root.focus_get() is self.editor)
        except Exception:
            saved_cursor, had_focus = None, False

        self.editor.tag_remove('suspect', '1.0', 'end')
        self.editor.tag_remove('odd', '1.0', 'end')
        # タグの色は、毎回その時点のパレットで塗り直す。
        # テーマ切替や起動時の適用経路がどうであれ、解析が走った
        # 時点で必ず正しい配色になる（実機で「ダークモードなのに
        # 紫がライトの色のまま」になった保険）。
        self.editor.tag_configure('suspect', background=SUSPECT_BG)
        # **不自然な文字列**（項目48-IR で入れ、48-IZ で紫の意味を
        # これ一本にした）。
        # 色の定義そのものは常に置く（切り替えるのは**塗るかどうか**）。
        self.editor.tag_configure('odd', background=UNSURE_BG)
        # 統合表示で自動反映した箇所の色（分割表示の補正欄と同じ配色）
        self.editor.tag_configure('autofixed', foreground=FIXED_FG)
        self.editor.tag_configure('autochosen', foreground=ACCENT)

        # 自動反映が効いているときは、**直した行だけ**が原文と違う。
        # その行は原文の位置で計算した網掛けが合わないので付けない
        # （直した箇所は autofixed / autochosen の色で示す・項目48-A）。
        #
        # **直していない行には付ける**（項目48-Y・2026-08-11）。
        # 48-X で「打った範囲の外は書き換えない」ようにしたところ、
        # ここが `_autofix_on` だけで**まるごと飛ばして**いたため、
        # 打っていない行の誤字が**色も付かず直りもしない＝画面から
        # 消える**ことになっていた（実機のメモで、直せる4行・
        # 自信の無い20行が全部見えなくなっていた）。
        #
        # 見分け方は簡単で、**画面の文字が原文と同じなら直していない**。
        # そのときは原文の位置がそのまま使える。
        _autofix_on = self.unified_autofix_on()
        _show_odd = bool(self.settings.get('show_odd'))
        # 1行ずつ get すると 1000 行で 1000 回の往復になる。まとめて取る。
        _shown = []
        if _autofix_on:
            try:
                _shown = self.editor.get('1.0', 'end-1c').split('\n')
            except Exception:
                _shown = []
        for i, result in enumerate(self.line_results):
            row = i + 1
            line = result['original']
            if _autofix_on:
                # 画面の文字が原文と違う＝この行は直してある
                _intact = (i < len(_shown) and _shown[i] == line)
            else:
                _intact = True
            # **不自然な文字列**（項目48-IR で入れ、48-IZ で意味を
            # 一本にした）。直せなくても紫で見せる（「どこまで
            # 判定できているのか」を見るため）。**表示メニューの
            # 「不自然な文字列を紫で表示」で切り替える。既定オン。**
            #
            # **補正が入った範囲には付けない**（うにさんの指定・
            # 2026-08-23）。直った箇所はもう不自然ではないし、
            # 網掛け（suspect）と紫が重なると何が起きたのか
            # 分からなくなる。**行ごとではなく範囲どうしの重なり**で
            # 見る——同じ行の別の場所が不自然なままなら、そちらは
            # 紫のままでよい。
            #
            # `_intact` の判定は下の網掛けと同じ（ひとつにまとめた
            # 表示で置き換え済みなら、原文の位置はもう使えない）。
            _fixed = (result.get('original_spans') or []
                      if result.get('changed') else [])
            # **「もう直さない」と決められた紫は、ここで落とす**
            # （項目48-QY・2026-09-05）。門は
            # `corrector.visible_odd_spans` の**1本だけ**——
            # エンジンは素の紫を返す。**画面へ紫を塗る口はここ1か所**
            # なので、ここに掛ければ全部の道に届く（学び22）。
            # `_odd_span_at`・F2・実画面の見張りは**塗ったタグを読む**
            # ので自動で追従する。
            _raw = (result.get('odd_spans', ())
                    if (_show_odd and _intact) else ())
            for o_s, o_e in corrector.visible_odd_spans(
                    line, _raw, self.decisions):
                if any(o_s < f_e and f_s < o_e for f_s, f_e in _fixed):
                    continue
                self.editor.tag_add('odd', f'{row}.{o_s}', f'{row}.{o_e}')
            if not result['changed'] or not _intact:
                continue
            # 補正エンジンが返す original_spans は、元テキスト上での
            # 置換範囲そのもの。これがあるときは必ずこちらを使う。
            # 文字列検索で位置を探し直すと、同じ語が行内に複数あるとき
            # 手前の（補正していない）ほうに網掛けしてしまう。
            spans = result.get('original_spans') or []
            if len(spans) == len(result['details']):
                for start, end in spans:
                    self.editor.tag_add('suspect',
                                        f'{row}.{start}', f'{row}.{end}')
                continue
            # 濁点の分離を合成した行では、元テキスト上の位置に
            # 対応付けられないため original_spans が空になる。
            # その場合だけ、文字列の一致で位置を推定する。
            cursor = 0
            for typed_frag, _surface, _cat in result['details']:
                pos = line.find(typed_frag, cursor)
                if pos < 0:
                    continue
                self.editor.tag_add('suspect',
                                    f'{row}.{pos}',
                                    f'{row}.{pos + len(typed_frag)}')
                cursor = pos + len(typed_frag)

        if self._layout_is_unified():
            # 統合レイアウトでは補正欄が無い。メモ欄そのものが
            # 表示先なので、単位だけを組み立てておく
            # （網掛けは上のループで既に付けてある）。
            self._build_editor_units()
            # 設定がオンなら、補正を本文へ実際に反映する
            # （うにさんの指定・2026-08-10）。書き換えたら
            # 解析し直して、色付けと単位を新しい本文に合わせる。
            if self._apply_unified_autofix():
                # カーソルの置き直しは _apply_unified_autofix が
                # 済ませている（書き換えた行の中では、古い桁を
                # そのまま戻すと位置がずれるため）。ここは
                # 焦点だけを戻す。
                try:
                    if had_focus:
                        self.editor.focus_set()
                except Exception:
                    pass
                self.root.after_idle(self._analyze)
                return
            # 直すところが無い（もう反映済み）。色だけ塗り直す。
            self._repaint_autofix_tags()
        else:
            self._render_corrected()
        self._update_status()
        if learn:
            self._schedule_learning(self._analyze_text)
        self.editor_gutter.redraw()
        # **補正欄は作り直されるので、空白の印も付け直す**（項目48-IF）
        try:
            self._schedule_whitespace_paint(delay=1)
        except Exception:
            pass

        if saved_cursor is not None:
            try:
                self.editor.mark_set('insert', saved_cursor)
                if had_focus:
                    self.editor.focus_set()
            except Exception:
                pass

    def _schedule_learning(self, text):
        """
        入力が落ち着いたら、書かれた内容から語彙を覚える。

        正しく変換できている語（漢字・カタカナを含む語）を
        辞書に取り込むことで、次からその語の誤字を直せるようになる。
        """
        if self._learn_after_id:
            self.root.after_cancel(self._learn_after_id)
        self._learn_after_id = self.root.after(
            3000, lambda: self._learn_now(text))

    def _learn_now(self, text):
        self._learn_after_id = None
        if not text.strip():
            return
        # 英単語の学習は**いちばん先に**行う。
        # この下には「同じ内容は学習しない」「新しく書かれた行だけ」
        # といった早い戻りが並んでおり、そこを通ると英単語まで
        # 届かなかった（実機で Planetarium が直らなかった原因・
        # 2026-08-10）。英単語は**在るか無いか**だけを見て
        # 使用回数に頼らないので、同じ行を何度見ても害が無い。
        self._learn_english_now(text)
        # 同じ内容を何度も学習しないようにする。
        #
        # 以前は編集のたびにメモ全体を学習し直していたため、
        # 1文字直すだけで中の語の使用回数(count)が増えていき、
        # 「何度も打った語」と誤認されていた。
        # その結果、補正の判断基準（使用実績）が歪み、
        # 「貼り付け直後は誤補正されるが、少し編集すると直る」
        # という一貫性のない挙動になっていた。
        #
        # 全文一致の抑制（_last_learned_text）だけでは足りない。
        # 編集で本文が1文字でも変わると「別の内容」になり、残りの
        # 全行がまた学習されて count を稼いでいた（貼り付けた長文が
        # 数回の編集で「使用実績のある語」の集まりに化け、誤検知の
        # 温床になる）。学習の対象を「このセッションでまだ学習して
        # いない行」だけに絞ることで、行が何度画面に残っていても
        # 使用実績は書いたとき1回だけ数える。
        if text == getattr(self, '_last_learned_text', None):
            return
        self._last_learned_text = text
        lines = [l for l in text.split('\n') if l.strip()]
        new_lines = [l for l in lines if l not in self._learned_lines]
        if not new_lines:
            return
        self._learned_lines.update(new_lines)
        # ★★ **異様と判定した／直した範囲の語は覚えない**（項目48-RX・
        # 2026-09-05）。うにさんの育ちの語彙に `囚虜`（段3）が solid で
        # 入っていて、`しゅうりょじ → 囚虜時`・`囚虜時`（据え置き）を
        # 作っていた——**このメモの誤変換をそのまま学習した**もの
        # （初期状態なら両方 `終了時`）。学習は「新しく書かれた行」から
        # 語を採るが、その行の中で**エンジンが直した範囲**
        # （original_spans）と**紫の範囲**（odd_spans・unsure_spans）は
        # 「本人の語」ではなく打ち間違いなので、空白で潰してから学ぶ。
        # 材料は `line_results`（同じ本文の解析結果）——**新しい判定は
        # 作らない**。既に覚えたものは触らない（本人のデータ）
        try:
            _res_by_line = {}
            _al = (getattr(self, '_analyze_text', '') or '').split('\n')
            for _l, _r in zip(_al, getattr(self, 'line_results', []) or []):
                if _l.strip() and _r and not _r.get('pending'):
                    _res_by_line.setdefault(_l, _r)
            _masked = []
            for _l in new_lines:
                _r = _res_by_line.get(_l)
                if _r:
                    _sp = (list(_r.get('original_spans') or [])
                           + list(_r.get('odd_spans') or [])
                           + list(_r.get('unsure_spans') or []))
                    if _sp:
                        _ch = list(_l)
                        for _a, _b in _sp:
                            for _i in range(max(0, _a), min(len(_ch), _b)):
                                _ch[_i] = ' '
                        _l = ''.join(_ch)
                _masked.append(_l)
            new_text = '\n'.join(_masked)
        except Exception:
            new_text = '\n'.join(new_lines)
        try:
            from janome_import import learn_from_text, HAS_JANOME
            if not HAS_JANOME:
                return
            added = learn_from_text(self.store, new_text)
            if added:
                self.store.save()
                self._update_status()
                # 語彙が変わったので、覚えている他タブの解析結果は
                # もう当てにならない（項目48-M）。
                self._invalidate_analysis_cache()
        except Exception:
            pass
        # 文脈ベクトル（語の共起）の学習も、語彙学習と同じ
        # タイミング・同じ「入力が落ち着いたら」の抑制に便乗させる。
        # 判断経路を増やさないという方針から、これは独立した新しい
        # 判断は何も行わず、あくまで evaluate_candidate が使う
        # 材料を育てるだけの処理。学習対象も語彙と同じ
        # 「新しく書かれた行」だけ（同じ行を何度も観測すると
        # 共起の重みが編集回数で水増しされるため）。
        self._learn_context_vec_now(new_text)

    def _learn_english_now(self, text):
        """
        書かれた英単語を覚える（loanword.py）。

        **英単語の辞書は持っていない**ので、直す相手は
        「ユーザーが正しく書いた語」だけになる。外部の辞書や
        モデルを持ち込まないという方針のため、ここは避けられない。
        逆に言えば、一度でも正しく書いた語はそれ以降ずっと直せる。
        """
        try:
            from loanword import learn_english_words
        except Exception:
            return
        try:
            if learn_english_words(text, self.store):
                self.store.save()
                self._invalidate_analysis_cache()
        except Exception:
            pass

    def _learn_english_from_tabs(self, texts=None, save=True):
        """
        起動時に、すべてのタブの本文から英単語を覚え直す。

        `texts`: 本文の並び。**`None` なら控えから取り出す**（主スレッド用）。
                 裏のスレッドから呼ぶときは、**主スレッドで取り出したものを渡す**
                 （スレッドから `session` を触らないため・項目48-TT）。
        `save`:  覚えたら書き出すか。**裏のスレッドからは False**——
                 書き出しは主スレッドに任せる（打鍵の側の書き出しと重なり得る）。
        戻り値: 覚えた語の数。

        普段の学習は「新しく書かれた行」だけを対象にする
        （開き直すだけで使用実績が増えるのを防ぐため・項目46）。
        英単語は**在るか無いか**だけを見て回数には頼らないので、
        既に書いてあるものも一度まとめて拾ってよい。
        こうしないと、ずっと前から書いてある語が直せない。

        中身は loanword.relearn_english_from_texts に任せる。
        **多く書かれている形から先に覚える**ので、同じメモに
        誤字と正しい形が両方あっても、正しいほうが残る。
        """
        try:
            from loanword import relearn_english_from_texts as _relearn
        except Exception:
            return 0
        try:
            if texts is None:
                texts = [tab.get('text', '') or ''
                         for tab in (self.session.tabs or [])]
            got = _relearn(texts, self.store) or 0
        except Exception as e:
            # ★★ **黙って飛ばさない**（項目48-TV・2026-09-07）。
            # 覚え直しは「いったん全部消してから入れ直す」作りなので、
            # 途中で落ちると**英単語の記録が消えたまま**になる。
            # 黙って 0 を返すと、利用者は「英語が急に直らなくなった」
            # としか分からない。次の起動で作り直せることも添えて知らせる。
            try:
                self.status.config(
                    text='英単語の覚え直しに失敗しました（%s）。'
                         '次の起動でやり直します' % e)
            except Exception:
                pass
            return 0
        if got and save:
            try:
                self.store.save()
            except Exception:
                pass
        return got

    def _learn_context_vec_now(self, text):
        """
        ★★ **もう育てない**（項目48-QL・2026-09-05）。

        語の共起は**本人が何と何を並べて書いたか**そのもの。
        うにさんの指定への Fable の推奨「初期分だけ」に、うにさんが
        「推奨のとおり」と答えた。同梱の話題のまとまり
        （`seed_context.py` の `ensure_seeded`）は**今までどおり使う**
        ——使うのをやめるのではなく、**書き足すのをやめる**。

        育った共起はむしろ誤爆源だった実績もある
        （項目48-IQ・思い↔動作。うにさんのメモは誤変換の議論だらけ
        なので、誤変換の側の共起まで育っていた）。

        呼び出し口（`_learn_from_text`）はそのまま残してある——
        道を消すのではなく、覚えるのをやめる（学び22）。
        """
        return

    def _build_editor_units(self):
        """
        統合レイアウト用に、メモ欄の各行を「クリックできる単位」に組み立てる。

        分割レイアウトの _render_corrected と違い、テキストは
        **書き換えない**。ユーザーが打った文字はそのまま残し、
        疑わしい箇所に色を付けるだけにする（build_suspect_units）。
        自動で置き換えてしまうと、入力欄そのものが書き換わることになり、
        カーソル位置も打鍵の途中経過も壊れるため。

        簡易入力ウィンドウが既にこの方式で動いており、同じ考え方を
        本体に持ち込んだもの（SPEC「統合レイアウト」参照）。
        """
        fn = getattr(self.store, '_tokenize_fn', None)
        if fn is None:
            fn = corrector.make_tokenizer(self.store)
            self.store._tokenize_fn = fn

        self.line_units = []
        self.line_texts = []
        autofix = self.unified_autofix_on()
        cache = getattr(self, '_suspect_units_cache', None)
        if cache is None:
            cache = self._suspect_units_cache = {}
        # **行ごとに、画面に出ている文字がどちらなのかを見る**
        # （項目48-Z・2026-08-11）。
        #
        # ここは以前「自動反映が入なら**全行が直っている**」と
        # みなして、全部を補正後の文字の上で組み立てていた。
        # 48-X で打っていない行は直らなくなったので、
        # **画面には原文が出ているのに単位は補正後の位置**という
        # 食い違いが起きる。長さが変わればクリックも F2 も
        # 隣の語を掴む（検証レポート 1-C の正体）。
        #
        # 見分け方は色付け（48-Y）と同じ:
        # **画面の文字が原文と同じなら、その行は直していない**。
        shown = []
        if autofix:
            try:
                shown = self.editor.get('1.0', 'end-1c').split('\n')
            except Exception:
                shown = []
        fresh = {}
        for i, result in enumerate(self.line_results):
            # 仮置きの行は組み立てを省く（_render_corrected と同じ理屈）
            if result.get('pending'):
                self.line_units.append([])
                self.line_texts.append(result['original'])
                continue
            original = result['original']
            # この行の画面の文字が原文と違う＝直してある
            use_fixed = bool(autofix) and not (
                i < len(shown) and shown[i] == original)
            key = (original, result['corrected'], use_fixed)
            got = cache.get(key)
            if got is None and self._units_are_pending():
                self.line_units.append([])
                self.line_texts.append(shown[i] if i < len(shown) else original)
                continue
            if got is None:
                # 直してある行は、出ている文字（補正後）の上で
                # 組み立てる。直した箇所・選び直した箇所の印も
                # そのまま付く（項目48-A）。
                # 直していない行は、出ている文字（原文）の上で
                # 組み立てる。置き換えはせず色だけ付ける形。
                got = (build_line_units(result, fn, self.choices,
                                        self._known_kana_word)
                       if use_fixed else
                       build_suspect_units(result, fn, self.choices,
                                           self._known_kana_word))
            fresh[key] = got
            text, units = got
            self.line_units.append(units)
            self.line_texts.append(text)
        self._suspect_units_cache = fresh

    def unified_autofix_on(self):
        """統合表示で、補正を本文へ自動反映する設定になっているか。"""
        try:
            return (self._layout_is_unified()
                    and bool(self.settings.get('unified_autofix')))
        except Exception:
            return False

    # ------------------------------------------------------------------
    # 統合表示で自動反映した行の控え
    #
    # 控えが持つもの（1行につき1つ）:
    #   mark     … その行に打っておいた Tk のマークの名前
    #   applied  … 反映した結果（＝いま画面に出ているはずの文字）
    #   original … 打った文字そのもの（保存・解析へ渡すのはこちら）
    #   spans    … 色を塗る場所 (start, end, kind, before) の並び
    #   manual   … その行で「元の入力に戻す」を使ったか
    #
    # **Tk のマークは、行が増減しても文章と一緒に動く**。
    # 以前は「書き換え後の行の文字列」を鍵にした対応表で持っていたが、
    # 同じ文字列を自分で打った行まで巻き添えにしていた
    # （editor_source_text の説明を参照）。
    #
    # 控えを持つ「面」は2つ——**メモ欄（統合表示）と簡易入力の欄**。
    # 仕組みは同じものを共用し、面の違いは `_autofix_pane` の1か所
    # だけで吸収する（48-GN——同じ意味の仕組みを2つ作らない）。
    # ------------------------------------------------------------------

    def _autofix_pane(self, w=None):
        """
        自動反映の控えを持つ「面」を1か所で決める（48-GN）。

        戻り: (欄, 控えの属性名, 書き換えたあとの後始末)。
        w を渡さなければメモ欄（今までどおり）。

        **控えは「属性名」で返す**（名簿の実体ではない）。
        `_autofix_reset` は `setattr(self, 名, [])` で**属性ごと
        差し替える**ので、実体を配って回ると差し替えが伝わらない。
        """
        if w is None or w is getattr(self, 'editor', None):
            return (getattr(self, 'editor', None), '_autofix_records',
                    self._on_change)
        return w, '_quick_autofix_records', self._analyze_quick

    def _autofix_pane_of(self, rec):
        """控え自身が覚えている面（'pane' の無い古い形はメモ欄）。"""
        if rec.get('pane', 'editor') != 'quick':
            return self._autofix_pane(None)
        qt = getattr(self, '_quick_text', None)
        if qt is None:
            # 窓は閉じている。**欄は無いが名簿は簡易入力のもの**
            # （ここでメモ欄に落とすと、本体の控えを削りにいく）。
            return None, '_quick_autofix_records', self._analyze_quick
        return self._autofix_pane(qt)

    def _autofix_reset(self, w=None):
        """控えを全部捨てる（タブの切り替え・本文の差し替えのとき）。"""
        wid, key, _after = self._autofix_pane(w)
        # 設計33: 本文が入れ替わる前に、仮の記録を確定する
        # （行から離れたのと同じ扱い。呼び元はどこも入れ替えの前に
        #   ここを通るので、行の中身はまだ読める）。写しも捨てる。
        # **メモ欄のときだけ**——設計33 は `_on_change`（メモ欄の
        # 打鍵）から動く仕掛けで、簡易入力の欄に対応物が無い。
        # 簡易入力を閉じた拍子に、本体の仮記録を確定させない。
        if key == '_autofix_records':
            try:
                self._design33_flush()
            except Exception:
                pass
            self._d33_shadow = None
        for rec in getattr(self, key, ()):
            try:
                wid.mark_unset(rec['mark'])
            except Exception:
                pass
        setattr(self, key, [])

    def _autofix_row_of(self, rec):
        """控えの指す行番号。分からなくなっていれば None。"""
        wid = self._autofix_pane_of(rec)[0]
        try:
            return int(wid.index(rec['mark']).split('.')[0])
        except Exception:
            return None

    def _autofix_live_records(self, w=None):
        """
        いまも生きている控えを (控え, 行番号) で返す。

        生きている＝マークがまだあり、**その行の中身が反映した結果の
        ままである**こと。行を自分で書き換えたら、その控えは用済み
        なのでここで落とす（控えが際限なく溜まるのも防げる）。
        """
        wid, key, _after = self._autofix_pane(w)
        live = []
        seen_rows = {}
        for rec in list(getattr(self, key, ())):
            row = self._autofix_row_of(rec)
            if row is None:
                self._autofix_drop(rec)
                continue
            try:
                now = wid.get(f'{row}.0', f'{row}.end')
            except Exception:
                self._autofix_drop(rec)
                continue
            if now != rec['applied']:
                self._autofix_drop(rec)
                continue
            # 行が1つにくっついた等で重なったら、新しいほうを残す
            old = seen_rows.get(row)
            if old is not None:
                self._autofix_drop(old[0])
                live.remove(old)
            seen_rows[row] = (rec, row)
            live.append((rec, row))
        return live

    def _autofix_drop(self, rec):
        wid, key, _after = self._autofix_pane_of(rec)
        try:
            wid.mark_unset(rec['mark'])
        except Exception:
            pass
        try:
            getattr(self, key).remove(rec)
        except (ValueError, AttributeError):
            pass

    def _autofix_record_for_row(self, row, w=None):
        """その行の控え。無ければ None。"""
        for rec, r in self._autofix_live_records(w):
            if r == row:
                return rec
        return None

    # ------------------------------------------------------------
    # 設計33（1段目）——手で消した補正を「拒否」として学ぶ
    # ------------------------------------------------------------
    # うにさんの指定（2026-08-24）。補正欄・F2 を使わずに
    # **Delete で消してから打ち直す**直し方には記録が1つも残らず、
    # 「補正は繰り返され、先に進まない」（うにさんの言葉）。
    #
    # 仕組み（新しい束縛は1つも足していない。項目48-IN の轍——
    # 同じ欄の個別束縛が `<KeyPress>` を黙らせる——を踏まないため）:
    #   - `_on_change`（KeyRelease）から `_design33_watch` を呼び、
    #     自動反映の控え（'applied' と 'spans'）といまの本文を
    #     突き合わせる。消え方の見分けは純粋関数 `design33_classify`。
    #   - 拾えたら**仮の記録**として `_d33_pending` に置く。
    #   - **カーソルがその行から離れたとき**に確定
    #     （decisions.reject）。行に補正後の形が戻っていれば
    #     （Ctrl+Z・打ち直して結局その形にした）呼ばずに捨てる。
    #   - 控えの見分け（build_fingerprint）には decisions が
    #     もともと入っているので、確定時の
    #     `_invalidate_analysis_cache()` だけでよい（48-BN の型）。
    #
    # 2段目（同じ文で補正前の形が出たら protect に上げる）は
    # **まだ入れない**。protect は部分一致で広く効くので、
    # 1段目を実機で確かめてから（設計33 §5.5）。

    def _design33_enabled(self):
        """測るとき・補正の素の姿を見たいときに切れるようにしておく。"""
        return os.environ.get('CORRECTNOTE_DESIGN33', '1').lower() \
            not in ('0', 'off')

    def _design33_row_of(self, p):
        try:
            return int(self.editor.index(p['mark']).split('.')[0])
        except Exception:
            return None

    def _design33_drop(self, p):
        try:
            self.editor.mark_unset(p['mark'])
        except Exception:
            pass
        try:
            self._d33_pending.remove(p)
        except ValueError:
            pass

    def _design33_add(self, row, original, corrected, provisional):
        """仮の記録をひとつ置く。同じ組は増やさない。"""
        if self.decisions.is_rejected(original, corrected):
            return
        for p in self._d33_pending:
            if p['original'] == original and p['corrected'] == corrected:
                if not provisional:
                    # 甲の証拠（後ろを残して消した）が出たら、
                    # 仮の印だけ外す
                    p['provisional'] = False
                return
        self._d33_mark_seq += 1
        name = f'design33_{self._d33_mark_seq}'
        try:
            self.editor.mark_set(name, f'{row}.0')
            self.editor.mark_gravity(name, 'right')
        except Exception:
            return
        self._d33_pending.append({'mark': name, 'original': original,
                                  'corrected': corrected,
                                  'provisional': provisional})

    def _design33_watch(self):
        """
        打鍵のたび（KeyRelease）に呼ばれる、設計33（1段目）の見張り。

        **解析（300ms 後）より先に走る**ことが大事——解析は
        `_autofix_live_records` で書き換わった控えを落とすので、
        「消した直後の姿」はそこまでしか残っていない。
        """
        if not getattr(self, '_d33_pending', None) \
                and not getattr(self, '_autofix_records', None) \
                and getattr(self, '_d33_shadow', None) is None:
            return
        if not self._design33_enabled():
            return
        try:
            cur_row = int(self.editor.index('insert').split('.')[0])
        except Exception:
            cur_row = None
        # 1. カーソルが離れた行の仮の記録を確定する
        self._design33_flush(cur_row)
        if cur_row is None:
            self._d33_shadow = None
            return
        try:
            line_now = self.editor.get(f'{cur_row}.0', f'{cur_row}.end')
        except Exception:
            return
        # 2. いまの行の控えの**写し**を持つ。控えそのものは、行が
        #    書き換わると解析（`_autofix_live_records`）が落とす——
        #    3文字の語を1打ずつ消すなど、消し終わるまでに 300ms より
        #    かかると、控えが途中で消えて残りの消しが突き合わせられ
        #    なくなる。写しは**カーソルがこの行に居る間だけ**生かす
        #    （行番号がずれる編集は行を離れないとできないので、
        #      ずれたら中身が合わなくなり、何も拾わない側に倒れる）。
        shadow = getattr(self, '_d33_shadow', None)
        if shadow is not None and shadow.get('row') != cur_row:
            shadow = None
        for rec in list(self._autofix_records):
            if self._autofix_row_of(rec) == cur_row:
                shadow = {'row': cur_row, 'applied': rec['applied'],
                          'spans': rec['spans']}
                break
        self._d33_shadow = shadow
        # 3. 写しと本文を突き合わせる（控えを落とすのは今までどおり
        #    `_autofix_live_records` の受け持ち。ここでは読むだけ）
        if shadow is not None and line_now != shadow['applied']:
            for o, c, prov in design33_classify(
                    shadow['applied'], shadow['spans'], line_now):
                self._design33_add(cur_row, o, c, prov)
        # 4. 補正後の形が行に戻っていれば取り下げる
        #    （Ctrl+Z・打ち直して結局その形を残した）
        for p in list(self._d33_pending):
            if self._design33_row_of(p) == cur_row \
                    and p['corrected'] in line_now:
                self._design33_drop(p)

    def _design33_flush(self, cur_row=None):
        """
        カーソルが離れた行の仮の記録を確定する（decisions.reject）。

        cur_row=None は「全部確定」（閉じる・タブ切り替え・本文の
        差し替え。どれも「行から離れた」のと同じ扱い）。
        その行にまだ補正後の形が残っているなら、拒否ではないので
        記録せずに捨てる。
        """
        pend = getattr(self, '_d33_pending', None)
        if not pend:
            return
        done = []
        for p in list(pend):
            row = self._design33_row_of(p)
            if cur_row is not None and row is not None and row == cur_row:
                continue                    # まだその行に居る
            self._design33_drop(p)
            if row is not None:
                try:
                    line = self.editor.get(f'{row}.0', f'{row}.end')
                except Exception:
                    line = None
                if line is not None and p['corrected'] in line:
                    continue                # 結局その形を残した
            if self.decisions.reject(p['original'], p['corrected']):
                done.append(p)
        if not done:
            return
        try:
            self.decisions.save()
        except Exception:
            pass
        self._invalidate_analysis_cache()
        p = done[-1]
        extra = f'（ほか{len(done) - 1}件）' if len(done) > 1 else ''
        try:
            self.status.config(
                text=f'消した補正「{p["original"]}→{p["corrected"]}」は'
                     f'今後行いません{extra}'
                     '（学習 → 補正の判断… で戻せます）')
        except Exception:
            pass

    @staticmethod
    def _autofix_spans_of(units):
        return tuple(
            (u['start'], u['end'], u['kind'],
             (u['detail'][0] if u.get('detail') else u.get('base')) or '')
            for u in units
            if u.get('kind') in ('fixed', 'chosen'))

    def _autofix_remember(self, row, applied, original, units, w=None):
        """その行を「自動反映した行」として控える。"""
        wid, key, _after = self._autofix_pane(w)
        if wid is None:
            return None
        pane = 'editor' if key == '_autofix_records' else 'quick'
        self._autofix_mark_seq = getattr(self, '_autofix_mark_seq', 0) + 1
        # マークの名前は面ごとに分ける。**メモ欄の綴りは変えない**
        # （`probes/probe_design33.py` と `probe_decisions_gui.py` が
        #  この文字を直に触る）。連番は面をまたいで1本で足りる。
        name = (f'autofix_{self._autofix_mark_seq}' if pane == 'editor'
                else f'quick_autofix_{self._autofix_mark_seq}')
        try:
            wid.mark_set(name, f'{row}.0')
            # 右重力。行頭に何かを挿し込まれても、マークは
            # 続く文字のほうに付いていく（行頭で改行しても、
            # 下がった中身と一緒に動く）。
            wid.mark_gravity(name, 'right')
        except Exception:
            return None
        rec = {'mark': name, 'applied': applied, 'original': original,
               'spans': self._autofix_spans_of(units), 'manual': False,
               'pane': pane}
        recs = getattr(self, key, None)
        if recs is None:
            recs = []
            setattr(self, key, recs)
        recs.append(rec)
        return rec

    def _apply_unified_autofix(self):
        """
        統合表示のとき、補正の結果をメモ欄の本文へ実際に反映する
        （うにさんの指定・2026-08-10。既定でオン、表示メニューで切替）。

        統合表示には補正欄が無いので、これまでは疑わしい箇所に
        色を付けるだけだった。「直った文が見たい」という要望で、
        本文そのものを書き換える形を足す。

        **書き込む中身は、分割表示の補正欄に出しているものと同じ**
        （`build_line_units`）。自動補正だけでなく、**F2 で選び直した
        記憶（choices）も反映される**。うにさんの指定:
        「横須磨」を F2 で「横スマ」に変えたら、次に「横須磨」と
        書いたときも自動で直ってほしい（2026-08-10）。
        自動補正の無い行でも、選び直しの記憶があれば直る。

        **カーソルのある行も直す**（うにさんの指定・2026-08-10:
        「試しに一度そこも対象にしてください。もしかしたら
        気にしすぎで、便利になるだけかもしれません」）。
        当初はカーソル行を避けていた。書き途中の行を書き換えると
        カーソルの位置も打鍵の途中経過も壊れる、という懸念から
        （SPEC「統合レイアウト」の但し書き）。今回は避けるのを
        やめ、代わりに壊れないための手当てを2つ入れてある:
          - **IME が変換中のあいだは、この回をまるごと見送る。**
            未確定の文字を持っているときに本文を入れ替えると、
            変換の途中経過ごと壊れる。確定して落ち着けば、
            次の解析で直る。
          - **カーソルは書き換え後の「同じところ」へ置き直す**
            （`map_column`）。行をまるごと入れ替えるので、
            置き直さないと行頭へ飛ぶ。
        なお解析そのものが打鍵から 300ms 待つので、書き換えは
        「手が止まったとき」に起きる。
        使いにくければ表示メニューで自動反映ごと切れる。

        書き換えは**行ごと**に行う。行数が変わらないので、
        他の行の位置・ブックマーク・選択範囲がずれない。
        取り消し（Ctrl+Z）は1回の反映ごとに区切る。
        直した箇所には色を付ける（補正は赤、選び直しは青緑。
        分割表示の補正欄と同じ配色。実機で「補正の色が付いて
        いません」と指摘された・2026-08-10）。

        戻り値: 1行でも書き換えたら True。
        """
        if not self.unified_autofix_on():
            return False
        # **変換中は何もしない。** IME が未確定の文字を持っている
        # あいだに本文を入れ替えると、変換の途中経過ごと壊れる。
        # 行を選ぶ以前の問題なので、この回はまるごと見送る
        # （確定して落ち着けば、次の解析で直る）。
        try:
            import ime_watch
            if ime_watch.composition_active(self.editor.winfo_id()):
                return False
        except Exception:
            pass
        # 暴走止め。書き換え → 解析 → また書き換え、が続いたら降りる。
        # 直した文がさらに直る形（連鎖）は普通すぐ収まるが、
        # 記録の組み合わせ次第で行ったり来たりしうる。打鍵のたびに
        # 数え直すので、通常の使用では上限に触れない。
        if getattr(self, '_autofix_rounds', 0) >= self.AUTOFIX_MAX_ROUNDS:
            return False
        try:
            cursor_row = int(self.editor.index('insert').split('.')[0])
        except Exception:
            cursor_row = -1
        fn = getattr(self.store, '_tokenize_fn', None)
        if fn is None:
            try:
                fn = corrector.make_tokenizer(self.store)
                self.store._tokenize_fn = fn
            except Exception:
                return False

        try:
            cursor_col = int(self.editor.index('insert').split('.')[1])
        except Exception:
            cursor_col = 0

        # いま生きている控えを、行番号で引ける形にしておく
        live = {row: rec for rec, row in self._autofix_live_records()}
        n_records = len(live)
        applied = []
        for i, result in enumerate(self.line_results):
            row = i + 1
            if result.get('pending'):
                continue
            original = result.get('original') or ''
            if not original:
                continue
            try:
                text, units = build_line_units(result, fn, self.choices,
                                        self._known_kana_word)
            except Exception:
                continue
            try:
                now = self.editor.get(f'{row}.0', f'{row}.end')
            except Exception:
                continue
            rec = live.get(row)
            if not text or text == original:
                # もう直すところが無い（「この補正は不要」「今後直さない」
                # を選んだ等）。既に反映してある行なら**原文へ戻す**。
                # 控えが行に結び付いているので、こう書ける。
                if rec is not None and not rec['manual']:
                    applied.append((row, original, [], rec))
                continue
            if now == text:
                # もう反映してある。控えが無ければここで作る
                # （起動し直した直後などに、控えが空のまま
                #   画面だけ直っていることがある）
                if rec is None:
                    if n_records < self.AUTOFIX_ORIGINALS_LIMIT:
                        self._autofix_remember(row, text, original, units)
                        n_records += 1
                else:
                    rec['spans'] = self._autofix_spans_of(units)
                continue
            if rec is not None:
                # 反映済みの行で、結果のほうが変わった（選び直しを
                # 覚えた等）。追従して書き換える。
                # ただし「元の入力に戻す」を使った行はそのままにする
                # （戻したいという意図を上書きしない）。
                if not rec['manual']:
                    applied.append((row, text, units, rec))
                continue
            if now != original:
                continue          # 自分で書き換えた行には触らない
            # **打った範囲の外は書き換えない**（項目48-X）。
            # うにさんの指定:「入力した部分は変わってもよい。
            # それ以外の部分で勝手に補正しない」。
            # 直そうとしている範囲が、打った印にまるごと収まって
            # いなければ見送る（色は付くので F2 で直せる）。
            if not self._change_is_inside_typed(row, now, text):
                continue
            if n_records >= self.AUTOFIX_ORIGINALS_LIMIT:
                # 控えきれる数を超えた。**原文を控えられないなら
                # 直さない**（取りこぼしは我慢できても、打った文字を
                # 失うのは我慢できない）。
                continue
            n_records += 1
            applied.append((row, text, units, None))
        if not applied:
            # 直すところが無かった＝落ち着いた。数え直す。
            # （数えるのは「続けて書き換えた回数」だけ。何もしない
            #   回まで数えると、静かにしているうちに上限へ達して
            #   本当に直したいときに動かなくなる）
            self._autofix_rounds = 0
            return False
        self._autofix_rounds = getattr(self, '_autofix_rounds', 0) + 1
        try:
            self.editor.edit_separator()
            for row, text, units, rec in applied:
                # 原文を控えておく。分割表示へ戻したときや、
                # 自動反映を切ったときに書き戻すため
                # （うにさんの指定・2026-08-10「原文の情報を
                #  残してください」）。
                # 控えは**その行そのもの**に結び付ける
                # （_autofix_remember の説明を参照）。
                # 色を塗る場所も一緒に控える。塗り直しは
                # `_repaint_autofix_tags` の受け持ち（タブを移って
                # 戻ると、本文を入れ替えるのでタグが消える。
                # 実機で報告・2026-08-10）。元の語も控えるのは、
                # 自動反映した語を F2／右クリックしたときに
                # 「元の入力に戻す」「この補正は不要」を出すため
                # （項目48-z）。
                src_line = self.line_results[row - 1].get('original') or ''
                # 行をまるごと入れ替えるとタグが消えるので、
                # 「打った」印は控えて付け直す（項目48-X）。
                # 消したままだと、直したあとの行が「打っていない行」に
                # なってしまい、続きを打っても直らなくなる。
                _was = self._typed_ranges_of_row(row)
                _old = self.editor.get(f'{row}.0', f'{row}.end')
                self.editor.delete(f'{row}.0', f'{row}.end')
                self.editor.insert(f'{row}.0', text)
                self._restore_typed_ranges(row, _was, _old, text)
                if rec is not None:
                    if text == src_line:
                        self._autofix_drop(rec)     # 原文へ戻した
                    else:
                        rec['applied'] = text
                        rec['original'] = src_line
                        rec['spans'] = self._autofix_spans_of(units)
                elif src_line and src_line != text:
                    self._autofix_remember(row, text, src_line, units)
            self.editor.edit_separator()
            # カーソルのある行も書き換えたなら、カーソルを
            # 「書き換え後の同じところ」へ置き直す（map_column）。
            # 行をまるごと入れ替えているので、置き直さないと
            # 行頭へ飛ぶ。
            for row, text, _units, _rec in applied:
                if row != cursor_row:
                    continue
                src_line = self.line_results[row - 1].get('original') or ''
                self.editor.mark_set(
                    'insert', f'{row}.{map_column(src_line, text, cursor_col)}')
                self.editor.see('insert')
                break
        except Exception:
            return False
        # 書き換えた行に色を塗る（塗る場所は控えから引く）
        self._repaint_autofix_tags()
        # 書き換えた行は、もう直すところが無い状態になった。
        # 解析し直して色付けと単位を合わせる。
        self._mark_dirty()
        return True

    # 統合表示の自動反映を、続けて何回まで行うか（暴走止め）
    AUTOFIX_MAX_ROUNDS = 5
    # 控えておく原文の上限。**超えたら「直さない」ほうへ倒す**
    # （控えを捨てると、画面に出ている補正後の文字が原文に
    #  成り代わってしまう）。自分で書き換えた行の控えは
    # `_autofix_live_records` が随時落とすので、実際にはここまで
    # 溜まるのは「一度に4000行以上が自動で直った」ときだけ。
    AUTOFIX_ORIGINALS_LIMIT = 4000

    def _repaint_autofix_tags(self, w=None):
        """
        統合表示で自動反映した箇所の色を、いまの本文に塗り直す。

        色はタグで付けているが、**本文を入れ替えるとタグは消える**。
        タブを移って戻ると `_load_active_tab` が本文を入れ直すので、
        直った文はそのままなのに色だけ消えていた（実機で報告・
        2026-08-10。分割にして統合へ戻すと付き直したのは、
        そのとき原文へ戻して自動反映をやり直していたため）。

        そこで「どこを塗るか」も控えに入れておき、解析のたびに
        ここで塗り直す。控えは**その行そのもの**に結び付いている
        ので、行が動いても付いてくる。自分で書き換えた行の控えは
        `_autofix_live_records` が落とすので、色も付かない。
        """
        wid, _key, _after = self._autofix_pane(w)
        try:
            for tag in ('autofixed', 'autochosen'):
                wid.tag_remove(tag, '1.0', 'end')
        except Exception:
            return
        records = self._autofix_live_records(w)
        if not records:
            return
        try:
            wid.tag_configure('autofixed', foreground=FIXED_FG)
            wid.tag_configure('autochosen', foreground=ACCENT)
            for rec, row in records:
                for start, end, kind, _before in rec['spans']:
                    tag = 'autofixed' if kind == 'fixed' else 'autochosen'
                    wid.tag_add(tag, f'{row}.{start}',
                                f'{row}.{end}')
            wid.tag_raise('autofixed')
            wid.tag_raise('autochosen')
        except Exception:
            pass

    def autofix_span_at(self, row, start, end, w=None):
        """
        統合表示で自動反映した箇所のうち、この範囲と重なるものを返す。

        戻り値: (開始, 終了, 種類, 元の語) または None
        """
        rec = self._autofix_record_for_row(row, w)
        if rec is None:
            return None
        for span in rec['spans']:             # (start, end, kind, before)
            if not (end <= span[0] or start >= span[1]):
                return span
        return None

    def _undo_autofix(self, row, span, forget=True, w=None):
        """
        統合表示で自動反映した1か所を、元の入力に戻す。

        戻すだけでは次の解析でまた直ってしまうので、
        **同時に「この補正は不要」という判断を残す**
        （分割表示の補正欄で「元の入力に戻す」を選んだときと同じ）。

        forget=False にすると判断は残さない（呼び出し側が
        別の形で覚えさせる場合に使う）。
        """
        wid, _key, after = self._autofix_pane(w)
        if wid is None:
            return
        start, end, kind, before = span
        try:
            current = wid.get(f'{row}.{start}', f'{row}.{end}')
        except Exception:
            return
        if not before or before == current:
            return
        # 控えは書き換える前に掴んでおく（書き換えたあとでは
        # 「反映した結果のまま」に一致せず、落とされてしまう）。
        rec = self._autofix_record_for_row(row, w)
        try:
            wid.edit_separator()
            wid.delete(f'{row}.{start}', f'{row}.{end}')
            wid.insert(f'{row}.{start}', before)
            wid.edit_separator()
        except Exception:
            return
        # **原文（行まるごと）はそのまま残す。**
        # 戻したのは「見せ方」であって、打った文字が変わったわけでは
        # ないため。ここで控えを捨てていた頃は、同じ行に残っている
        # 他の自動補正の原文まで辿れなくなり、保存した中身に補正後の
        # 文字が焼き付いていた（2026-08-10 の検証で判明）。
        if rec is not None:
            shift = len(before) - len(current)
            rest = []
            for s, e, k, b in rec['spans']:
                if (s, e) == (start, end):
                    continue                  # 戻した箇所は色を落とす
                if s >= end:
                    s, e = s + shift, e + shift
                rest.append((s, e, k, b))
            rec['spans'] = tuple(rest)
            rec['manual'] = True
            try:
                rec['applied'] = wid.get(f'{row}.0', f'{row}.end')
            except Exception:
                self._autofix_drop(rec)
        if forget:
            if kind == 'chosen':
                # 選び直しの記憶が元。記憶ごと取り消す
                self._forget_chain(before, {'prev': '', 'next': '',
                                            'text': current})
            else:
                self.decisions.reject(before, current)
                self.decisions.save()
                self._invalidate_analysis_cache()
        self.status.config(text=f'「{current}」を「{before}」に戻しました')
        # 後始末は面ごと（メモ欄は `_on_change`・簡易入力は
        # `_analyze_quick`）。`_autofix_pane` が対応づけている。
        after()

    def restore_autofix_originals(self):
        """
        統合表示の自動反映で書き換えた行を、原文へ書き戻す。

        うにさんの指定（2026-08-10）:
        「統合モードの自動補正は、原文の情報を残してください。
        　分割モードのメモ欄に文字列が残り、補正欄が表示されて
        　いるような仕組みにします。」

        分割表示のメモ欄は**打った文字そのもの**を出す場所なので、
        統合表示で書き換えた結果をそのまま持ち込まない。
        分割へ戻した時点で原文に戻し、補正の結果は補正欄で見せる。

        控えは**その行そのもの**（Tk のマーク）に結び付けて持つので、
        行が増減しても正しい行へ戻せる。自分で書き換えた行の控えは
        既に落ちているため、戻し過ぎることもない。

        戻り値: 1行でも書き戻したら True。
        """
        changed = [(row, rec['original'])
                   for rec, row in self._autofix_live_records()
                   if rec['original'] != rec['applied']]
        if not changed:
            self._autofix_reset()
            return False
        try:
            self.editor.edit_separator()
            for row, src_line in sorted(changed):
                self.editor.delete(f'{row}.0', f'{row}.end')
                self.editor.insert(f'{row}.0', src_line)
            self.editor.edit_separator()
            for tag in ('autofixed', 'autochosen'):
                self.editor.tag_remove(tag, '1.0', 'end')
        except Exception:
            return False
        # 原文へ戻したので、控えは用済み。統合表示へ戻せば
        # 自動反映がやり直され、控えも作り直される。
        self._autofix_reset()
        self._mark_dirty()
        return True

    def _on_toggle_quick_autofix(self):
        """簡易入力の自動反映の切り替え（項目48-LR）。"""
        v = bool(self.quick_autofix_var.get())
        try:
            self.settings.set('quick_autofix', v)
            self.settings.save()
        except Exception:
            pass
        # 開いている簡易入力にはすぐ効かせる（入れた直後に、いま
        # 書いてある内容が直るところまで見せる）
        if v and getattr(self, '_quick_text', None) is not None:
            try:
                self._analyze_quick()
            except Exception:
                pass

    def _on_toggle_unified_autofix(self):
        v = bool(self.unified_autofix_var.get())
        try:
            self.settings.set('unified_autofix', v)
            self.settings.save()
        except Exception:
            pass
        if v:
            self._analyze()
        else:
            # 切ったなら、自動で直した分は原文へ戻す
            self.restore_autofix_originals()
            self._analyze()

    def _editor_line_units(self, row):
        """
        分割レイアウトで、**メモ欄（左）の1行**を語の単位に組み立てる。

        self.line_units は補正後のテキスト（右の欄）の上での位置を
        持っている。F2 の対象をメモ欄にするには、打った文字そのもの
        の上での位置が要るので、統合レイアウトと同じ
        build_suspect_units でその行だけ組み立て直す。

        row は 1 始まり。組み立てられなければ空リストを返す。
        """
        i = row - 1
        if not (0 <= i < len(self.line_results)):
            return []
        fn = getattr(self.store, '_tokenize_fn', None)
        if fn is None:
            fn = corrector.make_tokenizer(self.store)
            self.store._tokenize_fn = fn
        try:
            _text, units = build_suspect_units(
                self.line_results[i], fn, self.choices,
                self._known_kana_word)
        except Exception:
            return []
        return units

    def _span_pairs(self, row):
        """
        その行の「**元の範囲 ↔ 補正後の範囲**」の対応表（項目48-RF）。

        **決めているのはここ1本**（48-GN）。行き（`_to_corrected_span`）
        と帰り（`_to_original_span`）が別々の対応を持つと、
        **塗る場所と一覧の指す場所が食い違う**。

        戻り値: `[((元の始, 元の終), (後の始, 後の終)), ...]`（元の順）
        と、その行の結果。引けなければ `([], None)`。
        """
        i = row - 1
        if not (0 <= i < len(self.line_results)):
            return [], None
        res = self.line_results[i]
        pairs = []
        for o, c in zip(res.get('original_spans') or [],
                        res.get('spans') or []):
            try:
                pairs.append(((int(o[0]), int(o[1])),
                              (int(c[0]), int(c[1]))))
            except Exception:
                continue
        pairs.sort(key=lambda p: p[0][0])
        return pairs, res

    def _to_original_span(self, row, start, end):
        """
        **補正欄の範囲を、元のテキストの上での範囲に読み替える**
        （項目48-RF・`_to_corrected_span` の逆向き）。

        補正欄のクリックから**紫**（元のテキストの上に塗ってある）を
        引くために要る。対応表は `_span_pairs` の**1本**を使う。

        補正された語そのものを指していたら、その**元の範囲**を返す。
        見当がつかないときは None（**当てずっぽうで返さない**——
        間違った場所を「正しい」と登録するほど危ないことは無い）。
        """
        pairs, res = self._span_pairs(row)
        if res is None:
            return None
        delta = 0
        for (os_, oe), (cs, ce) in sorted(pairs, key=lambda q: q[1][0]):
            if end <= cs:
                break
            if start >= ce:
                delta = oe - ce
                continue
            return os_, oe          # 補正された箇所と重なっている
        limit = len(res.get('original', ''))
        s2, e2 = start + delta, end + delta
        if s2 < 0 or e2 > limit or s2 >= e2:
            return None
        return s2, e2

    def _to_corrected_span(self, row, start, end):
        """
        メモ欄（元のテキスト）の範囲を、補正欄の上での範囲に読み替える。

        補正で語の長さが変わると、同じ列番号でも指す場所がずれる。
        correct_line は補正した箇所を original_spans（元の位置）と
        spans（補正後の位置）の対で持っているので、これを使って
        前から順に差分をたどる。

        補正された語そのものを指していた場合は、対応する補正後の
        範囲をそのまま返す。見当がつかないときは None を返す。

        対応表は `_span_pairs` の**1本**（48-GN）。
        """
        pairs, res = self._span_pairs(row)
        if res is None:
            return None

        delta = 0
        for (os_, oe), (cs, ce) in pairs:
            if end <= os_:
                break
            if start >= oe:
                # この補正はまるごと手前にある。ずれだけ引き継ぐ。
                delta = ce - oe
                continue
            # 補正された箇所と重なっている。補正後の範囲を使う。
            return cs, ce
        limit = len(res.get('corrected', ''))
        s2, e2 = start + delta, end + delta
        if s2 < 0 or e2 > limit or s2 >= e2:
            return None
        return s2, e2

    def _mirror_f2_focus_to_result(self, row, unit, bg):
        """
        F2 の対象語に、補正欄（右）でも色を付ける。

        うにさんの指定（2026-08-09）: 分割レイアウトでは候補一覧は
        入力欄（左）に出し、補正欄は「どの語のことか」が分かるように
        **色だけ**付ける。
        """
        span = self._to_corrected_span(row, unit['start'], unit['end'])
        if span is None:
            return
        try:
            self.result_view.tag_configure('f2_focus', background=bg)
            self.result_view.tag_add(
                'f2_focus', f'{row}.{span[0]}', f'{row}.{span[1]}')
            self.result_view.tag_raise('f2_focus')
        except Exception:
            pass

    # ------------------------------------------------------------
    # 画面レイアウト（左右分割 / 統合）
    # ------------------------------------------------------------
    # 'split'   … メモ欄と補正欄を左右に並べる（従来どおり）
    # 'unified' … 補正欄を出さず、メモ欄そのものに疑わしい箇所の色を
    #             付けて、その場でクリックして選び直せるようにする
    #
    # 統合レイアウトでは、補正結果でテキストを**置き換えない**。
    # 入力欄そのものを書き換えることになり、打鍵の途中でカーソルが
    # 飛ぶためである。自動補正は行わず「疑わしい」と示すだけにして、
    # 直すかどうかはクリックで選ばせる。
    # （この方式は簡易入力ウィンドウで先に実装・検証してある）

    def _layout_is_unified(self):
        return self.settings.get('layout') == LAYOUT_UNIFIED

    def _on_choose_layout(self):
        """表示メニューでレイアウトを選んだ。"""
        self._choose_layout(self.layout_var.get())

    def _set_layout_split(self):
        """ツールバーの「左右に並べる」ボタン。"""
        self.layout_var.set(LAYOUT_SPLIT)
        self._choose_layout(LAYOUT_SPLIT)

    def _set_layout_unified(self):
        """ツールバーの「1つにまとめる」ボタン。"""
        self.layout_var.set(LAYOUT_UNIFIED)
        self._choose_layout(LAYOUT_UNIFIED)

    def _on_choose_input_method(self):
        """表示メニューで入力方式（かな/ローマ字）を選んだ。"""
        method = self.input_method_var.get()
        if method not in INPUT_METHOD_LABELS:
            return
        if method == self.settings.get('input_method'):
            return
        self.settings.set('input_method', method)
        self.settings.save()
        # 検査方向が変わるので、全行を解析し直す。
        # 行キャッシュ（_prev_lines）が残っていると「変わっていない
        # 行」として使い回されてしまうため、必ず捨てる。
        #
        # **`_reanalyze_all` を通す**（項目48-CO）。ここで手ずから
        # `_prev_lines = []` としていた頃は、**解析結果の控えを
        # 捨てていなかった**ので、`_use_analysis_cache` が
        # **前の入力方式で出した答え**を拾って解析ごと飛ばせた。
        # IME から自動判定するほうの道（`_auto_detect_input_method`）
        # には `keep_current=False` が入っていて、こちらだけ
        # 抜けていた——「手動選択時と同じ」と書いてあるのに違う、
        # という形の食い違い。
        self._reanalyze_all()

    def _on_toggle_input_method_auto(self):
        """入力方式の自動判定（IMEに尋ねる）のオン/オフ。"""
        self.settings.set('input_method_auto',
                          bool(self.input_method_auto_var.get()))
        self.settings.save()

    def _auto_detect_input_method(self):
        """
        IME に入力方式（かな/ローマ字）を尋ね、違っていれば
        メニューの選択と補正の検査方向を自動で切り替える。

        打鍵のたびに呼ばれるが、確認は1秒に1回まで
        （ctypes 呼び出し自体は軽いが、無駄に繰り返さない）。
        判定できない場合（Windows以外・IMEオフ・ペースト）は
        何もしない＝現在の設定のまま。

        **変換中は切り替えない**（うにさんの指定・2026-08-11・E-1）。

        うにさんの報告:「かな入力をローマ字入力に変更して、補正が
        ローマ字に切り替わるのは、**文字を確定した時**にする。
        今は無変換の時に処理が走って入力できなくなる」。

        以前はここで `self._analyze()` を**その場で**呼んでいた。
        入力方式が変わると全行を見直すことになるので、
        打鍵の処理の中で1000行ぶんの下ごしらえが走り、
        変換中の IME まで巻き込んで手が止まる。
        いまは2段構えにしてある:

          1. 変換中（未確定の文字がある）なら**何もしない**。
             設定も変えない。確定してから切り替わる。
          2. 切り替えたあとの解析し直しも、その場では走らせない。
             手が止まってから `_run_input_method_reanalyze` が行う。
        """
        if not self.settings.get('input_method_auto'):
            return
        try:
            import time
            import ime_watch
            if not ime_watch.HAS_SUPPORT:
                return
            now = time.monotonic()
            if now - getattr(self, '_ime_checked_at', 0.0) < 1.0:
                return
            self._ime_checked_at = now
            hwnd = self.editor.winfo_id()
            # 変換中なら、確定を待つ。次の打鍵ですぐ見直せるよう、
            # 1秒の間隔も解いておく。
            if ime_watch.composition_active(hwnd) is True:
                self._ime_checked_at = 0.0
                return
            detected = ime_watch.current_input_method(hwnd)
        except Exception:
            return
        if not detected or detected == self.settings.get('input_method'):
            return
        self.settings.set('input_method', detected)
        self.settings.save()
        try:
            self.input_method_var.set(detected)
        except Exception:
            pass
        try:
            self.status.config(
                text=f'入力方式を自動判定: {INPUT_METHOD_LABELS[detected]}')
        except Exception:
            pass
        # **覚えている解析結果を、いま見ているタブのぶんも含めて
        # 全部捨てる。** 入力方式は補正の答えを変える（隣接キーの
        # 見方が変わる）ので、語彙が変わったときと同じ扱いが要る。
        # **`keep_current=False` が肝。** このあと `_prev_lines` を
        # 空にして解析し直すため、残しておくと `_use_analysis_cache`
        # が**前の入力方式で出した答え**を拾って解析を飛ばす。
        self._invalidate_analysis_cache(keep_current=False)
        # 検査方向が変わったので解析し直す（手動選択時と同じ）。
        # **ただし、その場では走らせない。**
        self._schedule_input_method_reanalyze()

    def _schedule_input_method_reanalyze(self):
        """
        入力方式が変わったあとの「全行の解析し直し」を予約する。

        打っている最中に走らせると手が止まるので、**手が止まってから**
        にする。打鍵のたびに呼ばれても、予約は取り直して1本に保つ。
        """
        job = getattr(self, '_imethod_after_id', None)
        if job:
            try:
                self.root.after_cancel(job)
            except Exception:
                pass
        self._imethod_after_id = self.root.after(
            700, self._run_input_method_reanalyze)

    def _run_input_method_reanalyze(self):
        """
        入力方式が変わったあとの、全行の解析し直し（予約された本体）。

        まだ変換中なら、**もう一度待つ**。ここで走らせてしまうと
        「確定した時にする」といううにさんの指定に反する。

        `_prev_lines` を空にするのは**この時点**。先に空にすると、
        打鍵ごとの通常の解析（`_analyze_if_changed`）が
        全行の解析として走ってしまい、待たせた意味が無くなる。
        """
        self._imethod_after_id = None
        try:
            import ime_watch
            if ime_watch.HAS_SUPPORT and ime_watch.composition_active(
                    self.editor.winfo_id()) is True:
                self._schedule_input_method_reanalyze()
                return
        except Exception:
            pass
        self._prev_lines = []
        self._analyze_cause = '入力方式の切り替え'
        self._analyze()

    def _set_ime_font(self, widget=None):
        """
        **未変換（変換中）の文字を、メモ欄と同じ字で描かせる**
        （項目48-LO・うにさんの報告・2026-08-30「入力して未変換状態の
        文字が、一回り小さいサイズで表示されることがある」）。

        Tk は未変換文字列の位置しか IME に伝えないので、字は IME の
        既定のまま＝メモ欄と食い違うことがある（ime_watch.
        set_composition_font の説明を参照）。ここでメモ欄の**いまの字**
        （俯瞰中なら小さい字）をピクセルに直して IME へ渡す。

        widget: 掛ける先の欄。省略ならメモ欄。簡易入力は専用の
            IME 文脈を持つ（項目48-LR）ので、開くたびにその文脈へも
            掛け直す（呼び元 _open_quick_capture）。

        呼びどころ（学び22——片方だけに掛けると迂回される）:
          - メモ欄の <FocusIn>（IME の文脈は焦点・入力言語の
            切り替えで作り直されることがある）
          - 起動直後（最初の焦点が FocusIn を運ばない環境の保険）
          - 俯瞰の出入り（_overview_fonts。字の大きさが変わる）
          - 簡易入力を開いたとき（専用文脈・項目48-LR）
        """
        try:
            import ime_watch
            if not ime_watch.HAS_SUPPORT:
                return
            import tkinter.font as tkfont
            w = widget if widget is not None else self.editor
            f = tkfont.Font(font=w.cget('font'))
            family = str(f.cget('family'))
            size = int(f.cget('size'))
            # Tk の字の大きさは 正=ポイント・負=ピクセル
            if size > 0:
                px = int(round(self.root.winfo_fpixels(f'{size}p')))
            else:
                px = -size
            ime_watch.set_composition_font(w.winfo_id(), family, px)
        except Exception:
            pass

    # ------------------------------------------------------------
    # 変換の見張り —— 確定直前のひらがなを覚える（設計25(甲)）
    # ------------------------------------------------------------
    #
    # うにさんの指定（2026-08-20）:
    #
    # > 「確定直前のひらがな情報を保持する実装を次に始めてください。
    # >   **ひらがながあれば、読みが分かるので自動補正します**」
    #
    # **なぜ Tk の打鍵では駄目か**（項目48-GX・実機の記録）:
    #
    #     10.34s  [Tk の打鍵] '奥' '悠' '久' '子' '帝'  ←**先に文字が届く**
    #     10.36s  RESULTSTR / RESULTREADSTR            ←そのあとで読める
    #
    # **文字が届いた時点では読みがまだ読めていないことがある。**
    # 「文字が届いてから読みを取りに行く」形にすると取り逃す。
    # **変換中に読みを覚えておいて、確定したときに対にする。**
    #
    # 変換中の打鍵は IME が食べてしまい Tk には届かないので、
    # **打鍵を合図にできない**。時計で見張るしかない。
    # 暇なときは**長さを聞くだけ**（呼び出し1回）にして軽くする。

    # 変換していないとき（`composition_active` だけ・呼び出し1回）
    _IME_POLL_IDLE_MS = 150
    # 変換中（読みは変わり続けるので細かく見る。probe と同じ 30ms）
    _IME_POLL_ACTIVE_MS = 30

    def _start_ime_reading_watch(self):
        """
        変換の見張りを始める（**Windows のみ**）。

        Windows 以外・IMM32 が無い環境では**何もしない**。
        そのときは対が1つも溜まらず、補正は今までどおり逆算だけで
        動く（`kanji_guess` 側が素通りする）。
        """
        try:
            import ime_watch
            if not ime_watch.HAS_SUPPORT:
                return
        except Exception:
            return
        self._ime_reading_tick()

    def _ime_reading_tick(self):
        """
        変換の様子を1回見る。**次の予約を必ず入れる。**

        **確定の合図は `COMPSTR` が空になった瞬間**（項目48-GX）。
        `RESULTSTR` の出現を待つと、**Tk に文字が届くほうが先**
        なので取り逃す。

        読みは3通りのどれかで取れる（実機で3通りとも生きていた）:

            ① RESULTREADSTR   確定した読み。**表記と対で来る**
            ② COMPREADSTR     変換中の読み。**変換後も残る**
            ③ 変換前の COMPSTR 「まだ全部かなだった間のいちばん長い値」

        ①が空の IME（TSF ベース）もあるので、②③を控えに持つ。
        """
        delay = self._IME_POLL_IDLE_MS
        try:
            import ime_watch
            hwnd = self.editor.winfo_id()
            active = ime_watch.composition_active(hwnd)
            if active or self._ime_comp:
                # 変換中か、**いま確定した直後**。4つとも取る。
                got = ime_watch.read_composition(hwnd) or {}
                comp = got.get('comp') or ''
                reading = got.get('comp_reading') or ''
                result = got.get('result') or ''
                if comp:
                    delay = self._IME_POLL_ACTIVE_MS
                    self._ime_comp = comp
                    # **COMPSTR は変換すると漢字に変わる。** まだ全部
                    # かなだった間のいちばん長い値を控えておく（③）。
                    if ime_readings_kana(comp) \
                            and len(comp) >= len(self._ime_first_kana):
                        self._ime_first_kana = comp
                if reading:
                    self._ime_comp_reading = reading
                # **文節ごとに何度も確定する**ことがある（項目48-GX）。
                # `RESULTSTR`／`RESULTREADSTR` は確定のたびに対で来る
                # ので、変わったらその場で覚える。
                if result and result != self._ime_last_result:
                    self._ime_last_result = result
                    self._remember_ime_pair(
                        result, got.get('result_reading') or '')
                if not comp and self._ime_comp:
                    # **確定した。** `RESULTSTR` が取れていなければ、
                    # 直前の未確定文字列を表記として使う。
                    if not result:
                        self._remember_ime_pair(
                            self._ime_comp,
                            self._ime_comp_reading or self._ime_first_kana)
                    self._ime_comp = ''
                    self._ime_comp_reading = ''
                    self._ime_first_kana = ''
                    self._ime_last_result = ''
        except Exception:
            pass    # 見張りが落ちても、メモは打てる
        try:
            self._ime_watch_id = self.root.after(
                delay, self._ime_reading_tick)
        except Exception:
            self._ime_watch_id = None

    def _remember_ime_pair(self, surface, reading):
        """
        (表記 → 打った読み) を1つ覚える。

        読みは**半角カタカナで返る**ので、`ime_readings` 側で
        NFKC → ひらがなに直してから入る（**素通しすると静かに
        効かなくなる**・項目48-GX）。

        **中身が変わったときだけ**印を立てる。**覚えている解析結果は
        古い判断のまま**なので捨てる必要があるが、確定のたびに
        捨てると裏で進めているタブの下ごしらえを毎回止めてしまう。
        印だけ立てて、**手が止まってから**（`_analyze_if_changed`）
        まとめて捨てる。
        """
        if not surface:
            return
        try:
            if self.ime_readings.remember(surface, reading):
                self._ime_pairs_dirty = True
        except Exception:
            pass

    def _choose_layout(self, layout):
        if layout not in LAYOUT_LABELS:
            return
        if layout == self.settings.get('layout'):
            return
        self.settings.set('layout', layout)
        self.settings.save()
        self._apply_layout()
        self._update_layout_buttons()

    def _update_layout_buttons(self):
        """
        今選ばれているほうのボタンを、押せない状態にして目立たせる。

        「既に選んでいる方を押しても意味が無い」ことが見た目で
        分かるようにする。メニューのラジオボタンと状態は常に
        settings 経由で一致しているので、ここは表示だけの処理。
        """
        current = self.settings.get('layout')
        try:
            self.layout_split_btn.config(
                state=('disabled' if current == LAYOUT_SPLIT else 'normal'))
            self.layout_unified_btn.config(
                state=('disabled' if current == LAYOUT_UNIFIED
                       else 'normal'))
        except Exception:
            pass

    def _apply_layout(self, reanalyze=True):
        """
        今の設定に合わせて、補正欄の表示・非表示を切り替える。

        ウィジェットを作り直すのではなく、grid から外す／戻すだけに
        する。作り直すと、それまでのブックマークや選択状態、
        スクロールの連動設定まで組み直すことになり、
        切り替えのたびに壊れる箇所が増えるため。

        reanalyze: 切り替え後に解析し直すか。起動時は、このあと
            セッションを復元してから改めて解析するので False にする
            （空の状態で1回余計に走らせないため）。

        **分割表示へ戻すときは、統合表示で自動反映した分を原文へ
        書き戻す**（うにさんの指定・2026-08-10）。分割表示のメモ欄は
        「打った文字そのもの」を出す場所なので、書き換えた結果を
        持ち込まない。補正の結果は補正欄のほうで見える。
        """
        if not self._layout_is_unified():
            self.restore_autofix_originals()
        unified = self._layout_is_unified()
        try:
            if unified:
                # 補正欄を畳む。
                # このとき uniform グループも外すのが要点。
                # uniform='pane' が残っていると、列1を消して重みを0に
                # しても列0は「2つで分け合う幅」のまま扱われ、
                # 右半分が余白として残る（実機で報告された）。
                self._result_pane.grid_remove()
                self._body.grid_columnconfigure(1, weight=0, uniform='')
                self._body.grid_columnconfigure(0, weight=1, uniform='')
                self.editor_header.config(text=self.UNIFIED_HEADER_TEXT)
            else:
                self._result_pane.grid()
                self._body.grid_columnconfigure(0, weight=1, uniform='pane')
                self._body.grid_columnconfigure(1, weight=1, uniform='pane')
                self.editor_header.config(text=self.EDITOR_HEADER_TEXT)
        except Exception:
            pass
        # 網掛けと単位を組み立て直す（レイアウトで作り方が変わるため）
        if reanalyze:
            self._analyze()

    def _invalidate_units_cache(self):
        """補正欄の行組み立ての控えを捨てる（選び直しが変わったとき）。"""
        self._units_cache = {}
        self._suspect_units_cache = {}
        self._tab_units_cache = {}

    def _ensure_attested(self):
        """
        メモに書かれている表記の一覧を、無ければ作る（項目48-P）。

        普段は `_analyze` が文脈語彙と一緒に集めるので手間ゼロだが、
        **前回の解析結果の控えを使った回（項目48-L/48-M）は
        `_analyze` が途中で戻るので集まらない**。候補づくりに要る
        ので、起動が落ち着いたころに作っておく。
        行ごとの控え（`_ctx_vocab_cache`）が温まっていれば一瞬。
        """
        if getattr(self, '_attested_surfaces', None):
            return
        try:
            from vocabulary import build_context_vocab_cached
            if not hasattr(self, '_ctx_vocab_cache'):
                self._ctx_vocab_cache = {}
            attested = {}
            build_context_vocab_cached(
                (self._prev_lines or []), self.store,
                self._ctx_vocab_cache, attested_out=attested)
            self._attested_surfaces = attested
        except Exception:
            pass

    def _known_kana_word(self, kana):
        """
        このかなの並びを、**1つの語として扱ってよいか**（項目48-P）。

        よりどころは「本人が書いているか」。語彙にある読みか、
        メモのどこかにその読みで書かれた語があれば認める。
        根拠が無ければ認めない（`あいうえお` のような並びを
        勝手に1語にしない）。
        """
        if not kana or len(kana) < 2:
            return False
        try:
            if self.store.has_reading(kana):
                return True
            return kana in (getattr(self, '_attested_surfaces', None) or {})
        except Exception:
            return False

    def _prebuild_units_for(self, i):
        """
        解析が済んだ行の「描画用の単位」を、解析の合間に組み立てて
        控えておく（_analyze_slice から呼ばれる）。

        以前は解析後の描き直し（_render_corrected）が全行まとめて
        組み立てていたため、行数の多いタブでは解析が終わる瞬間に
        1秒近く固まった。ここで1行ずつ済ませておけば、描き直しは
        控えを読むだけで済む（実測: 1000行で 800ms → 20ms）。
        """
        try:
            res = self.line_results[i]
            if self._layout_is_unified():
                cache = getattr(self, '_suspect_units_cache', None)
                if cache is None:
                    cache = self._suspect_units_cache = {}
                build = build_suspect_units
                # 鍵の3つ目は「直してある行か」（項目48-Z）。
                # ここで温めておけるのは**直していない側**だけ
                # （直したかどうかは、画面に出てからでないと
                #   分からない）。48-X 以降は直さない行のほうが
                # 多いので、これで十分に効く。
                key = (res['original'], res['corrected'], False)
            else:
                cache = getattr(self, '_units_cache', None)
                if cache is None:
                    cache = self._units_cache = {}
                build = build_line_units
                key = (res['original'], res['corrected'])
            if key in cache:
                return
            fn = getattr(self.store, '_tokenize_fn', None)
            if fn is None:
                fn = corrector.make_tokenizer(self.store)
                self.store._tokenize_fn = fn
            # **`known_kana_word` を渡し忘れない**（項目48-P）。
            # 渡さないと、ここで温めた行だけ「ひらがな」が
            # 1文字ずつに割れる。温めが当たったときだけ症状が出る
            # ので、気付きにくい（学び22と同じ形）。
            cache[key] = build(res, fn, self.choices,
                               self._known_kana_word)
        except Exception:
            pass

    def _render_corrected(self):
        """
        補正後のテキストを、メモと同じ行構成で表示する。

        各行を「クリックできる語の単位」に組み立て（units.py）、
        ユーザーが過去に選び直した語（choices.py）を反映してから描く。
        自動補正の箇所は赤、選び直した語は青緑で示す。

        テキストの組み立てと位置の確定は units.py の1箇所で同時に行う。
        描画側で後から位置を調整すると、置換で長さが変わったときに
        表示が崩れるため（「過去の失敗と学び」4と同種の問題）。
        """
        fn = getattr(self.store, '_tokenize_fn', None)
        if fn is None:
            fn = corrector.make_tokenizer(self.store)
            self.store._tokenize_fn = fn

        # 補正欄を作り直すと表示は先頭に戻るが、位置合わせは
        # 組み立てのあとに **メモ欄の今の位置** から改めて行うので
        # （_sync_partner_to_line）、ここで控えておく必要は無い。
        # メモ欄は組み立ての影響を受けない（補正欄からメモ欄を
        # 動かす経路そのものが無い）ため、基準は常に生きている。
        was_syncing = self._syncing
        self._syncing = True        # 組み立て中の同期を止める
        # 補正欄の state を切り替える・中身を作り直す操作の間に、
        # 焦点がメモ欄から外れることがある（実機で「非確定の英単語を
        # 確定すると、フォーカスが別のところに移ることがある」と
        # 報告された。IME確定直後の _on_change → _analyze →
        # _render_corrected という流れの中で、まだメモ欄に焦点が
        # 戻っていない一瞬に result_view 側の state 変更が割り込むと
        # 起こりうる）。_analyze 側でも保存・復元しているが、
        # ここでも独立に保存し直し、この関数を単体で呼んでも
        # 焦点が動かないようにしておく。
        try:
            focus_before = self.root.focus_get()
        except Exception:
            focus_before = None
        try:
            self.result_view.config(state='normal')
            self.result_view.delete('1.0', 'end')
            self.line_units = []
            self.line_texts = []

            # 行の組み立て（build_line_units）は形態素解析を伴い、
            # 全行ぶん毎回やり直すと打鍵ごとの反応が重くなる（実機で
            # 報告・2026-08-08）。結果は（元の行, 補正後の行）を鍵に
            # 控えて、変わっていない行は組み立て直さない。選び直し
            # （choices）が変わったときは控えごと捨てる
            # （_invalidate_units_cache）。
            cache = getattr(self, '_units_cache', None)
            if cache is None:
                cache = self._units_cache = {}
            fresh = {}
            tag_ranges = {'fixed': [], 'chosen': []}
            for i, result in enumerate(self.line_results):
                row = i + 1
                # まだ解析していない仮置きの行は、組み立てを省いて
                # 文字をそのまま出す（_blank_result 参照）。単位は
                # 解析が済んだあとの描き直しで付く。
                if result.get('pending'):
                    text = result['original']
                    self.line_units.append([])
                    self.line_texts.append(text)
                    continue
                key = (result['original'], result['corrected'])
                got = cache.get(key)
                if got is None and self._units_are_pending():
                    self.line_units.append([])
                    self.line_texts.append(result['corrected'])
                    continue
                if got is None:
                    got = build_line_units(result, fn, self.choices,
                                        self._known_kana_word)
                fresh[key] = got
                text, units = got
                self.line_units.append(units)
                self.line_texts.append(text)

                for u in units:
                    if u['kind'] in tag_ranges:
                        tag_ranges[u['kind']].extend(
                            (f'{row}.{u["start"]}', f'{row}.{u["end"]}'))

            # 本文は1回で渡す。行ごとの挿入・タグ付けでTkを往復しない。
            self.result_view.insert('1.0', '\n'.join(self.line_texts))
            for tag, ranges in tag_ranges.items():
                for start in range(0, len(ranges), 2000):
                    self.result_view.tag_add(tag, *ranges[start:start + 2000])
            self._units_cache = fresh
            self.result_view.config(state='disabled')
            # 右ペインを、左ペインの見えている位置に合わせ直す。
            # 行だけでなく折り返し・端数の画素まで揃える
            # （_sync_partner_to_line が3段階で面倒を見る）。
            self._sync_partner_to_line(self.editor, self.result_view)
        finally:
            self._syncing = was_syncing
        # **メモ欄（左ペイン）には触れない。**
        # 以前はここで editor.yview_moveto(keep_top) を行い、組み立ての
        # 過程で動いてしまった左ペインを戻していた。しかし
        #   - 割合での指定は行の境界に丸め直されるため、押した覚えの
        #     ない微妙なずれ（「1秒後に揺れる」）を毎回生む
        #   - そもそも右ペインの通知から左ペインを動かす経路
        #     （_on_result_scroll → 追従）を無くしたので、
        #     組み立てで左ペインが動くこと自体が起きない
        # ため、触らないのが正しい。
        self.editor_gutter.sync_yview(*self.editor.yview())
        self.result_gutter.sync_yview(*self.result_view.yview())
        # ★★ **作り直しで消えた印を、返る前に敷き直す**（項目48-RD・
        # 2026-09-05・うにさんの報告「**解析時にタブ（幅）が縮んだり
        # 伸びたりする**。以前もあった」）。
        #
        # 補正欄は解析のたびに `delete('1.0','end')` で**全行**作り
        # 直される。行ごとのタブの止まりも空白の印も**タグ**なので、
        # そこで消える。敷き直しは `after(1)` でしか来ないので、
        # **その間に一度、素の（細い）目盛りの姿が画面へ出る**。
        # 解析が進むたびに繰り返されて「伸び縮み」になる。
        # 実測（`tools_local/probe_tab_flicker.py`）: 作り直し5回とも
        # **止まりも空白の印も無いまま返っていた**。
        #
        # **`_paint_whitespace` を呼ぶ**（`_paint_line_tab_stops` だけ
        # ではない）——同じ `delete` で**空白の印も一緒に消える**ので、
        # 片方だけ敷き直すと、そちらを迂回して残る
        # （48-MO の注記「同じ理由で同じことが起きる」・学び22）。
        # あちらは見えている帯だけを塗り、`_tags_still_there` で
        # 「もう在る」なら何もしない作りなので、**あとから来る
        # `after(1)` は空振りで済む**（二重には塗らない）。
        try:
            self._paint_whitespace()
        except Exception:
            pass
        # state の切り替えで焦点が動いてしまった場合は戻す。
        # メモ欄に焦点があった場合だけを対象にする
        # （元々どこにも焦点が無かった／別のダイアログにあった場合まで
        #  奪い返すと、そちらの操作を妨げてしまうため）。
        if focus_before is self.editor:
            try:
                if self.root.focus_get() is not self.editor:
                    self.editor.focus_set()
            except Exception:
                pass

    # ------------------------------------------------------------
    # 補正結果のクリックによる確定・除外
    # ------------------------------------------------------------
    # 補正エンジンは辞書と統計だけで判断するため、固有名詞・俗語・
    # 専門語を誤って補正することが構造的に避けられない。
    # 取りこぼしは我慢できても、正しく書いたものを毎回壊されるのは
    # 我慢できないので、ユーザーが「これは不要」と伝えられるようにする。
    # 伝えられた判断は decisions.py に残り、二度と同じ補正をしない。

    # ------------------------------------------------------------
    # 語の選び直し（クリックによる手動修正）
    # ------------------------------------------------------------
    # 自動補正は「明確に誤りだと言えるもの」しか直さない方針なので、
    # 同音異義語の誤変換など、判断のつかない誤りは必ず残る。
    # そこで補正欄のどの語でも（補正の有無を問わず）クリックして
    # IMEの変換候補のように選び直せるようにする。
    # 選び直しは前後の語とセットで記憶し（choices.py）、
    # 次から同じ文脈では選んだ表記が自動で表示される。
    # 再クリックすれば何度でも選び直せる。

    def _get_line_height(self):
        """
        1行の高さ（ピクセル）。ドラッグ量を行数に変換するのに使う。

        **実際に描かれている高さを読む**（2026-08-28）。前は
        `EDITOR_FONT`——つまり**ふだんの字**——の linespace を返して
        いたので、**俯瞰の間も 19px のまま**だった。俯瞰の1行は
        字5＋行間0で **9px ほど**なので、マウスを動かしても
        **半分しか送らない**（うにさんの「そのまま上下に動かすと
        スクロール」が鈍る）。しかも `spacing1`／`spacing3` は
        最初から数に入っていなかった。

        `dlineinfo` は**字も行間も込みの本当の高さ**を返すので、
        どちらを変えても正しく付いてくる。読めないとき（行が
        描かれていない・欄がまだ無い）だけ、字の高さ＋行間で見積もる。
        """
        if self._line_h is None:
            w = getattr(self, 'editor', None)
            got = None
            try:
                info = w.dlineinfo('@0,0')      # (x, y, 幅, **高さ**, 基線)
                if info and len(info) >= 4 and int(info[3]) > 0:
                    got = int(info[3])
            except Exception:
                got = None
            if got is None:
                try:
                    import tkinter.font as tkfont
                    fnt = w.cget('font') if w is not None else EDITOR_FONT
                    got = tkfont.Font(font=fnt).metrics('linespace')
                    for k in ('spacing1', 'spacing3'):
                        try:
                            got += int(w.cget(k))
                        except Exception:
                            pass
                except Exception:
                    got = 20
            # 俯瞰では 9px ほどになる。**下限を 10 にしない**
            # （前の下限は、ふだんの字しか見ていなかった名残）
            self._line_h = max(4, int(got))
        return self._line_h

    def _drag_press(self, event, widget, always_scroll):
        """
        1本指ドラッグの起点を記録する。

        always_scroll=True の欄（行番号ガター）は、他に操作が無いので
        動いた向きを問わずスクロールにする。
        always_scroll=False の欄（本文）は、動きの向き（縦優位か）で
        「スクロールしたいのか」「選択したいのか」を後から判断する。
        """
        # 前の掴みの後始末が残っていたら、ここで必ず戻す（保険）
        self._scroll_cursor_restore()
        try:
            press_root = (widget.winfo_pointerx(), widget.winfo_pointery())
        except Exception:
            press_root = None
        self._drag = {
            'widget': widget, 'mode': None,
            'start_x': event.x, 'start_y': event.y,
            'last_y': event.y, 'accum': 0.0,
            'always_scroll': always_scroll,
            'press_root': press_root, 'warped': False,
        }

    def _drag_motion(self, event, widget):
        """
        ドラッグ中の判定と、スクロールモードでの実際の移動。

        戻り値: スクロールとして処理したら 'break'。
                そうでなければ None（呼び出し側で通常の動作に委ねる）。
        """
        d = self._drag
        if d is None or d['widget'] is not widget:
            return None

        dx = event.x - d['start_x']
        dy = event.y - d['start_y']

        if d['mode'] is None:
            if d['always_scroll']:
                if max(abs(dx), abs(dy)) < 8:
                    return None
                d['mode'] = 'scroll'
            else:
                cls = classify_drag(dx, dy)
                if cls is None:
                    return None
                d['mode'] = cls
            if d['mode'] == 'scroll':
                # 判定が確定するまでの間に既定の選択が始まっていたら消す
                try:
                    widget.tag_remove('sel', '1.0', 'end')
                except Exception:
                    pass
                # **掴んでいる間はカーソルを隠す**（項目48-JQ・下の
                # `_edge_warp` の説明。隠れていれば戻すのが見えない）。
                self._scroll_cursor_hide(widget)

        if d['mode'] != 'scroll':
            return None

        # --- 戻しの握手（Tk の warp が**非同期**な環境の逃げ道だけ）---
        # Windows は SetCursorPos（同期）なので、`_edge_warp` は
        # `warp_to` を置かず、ここには来ない。非同期の環境では、
        # 戻り先 ±60px に報せが来るまで捨てて待ち、回数の門
        # （DRAG_WARP_SKIP_MAX）を超えたら「戻せない道具」と判定する。
        want = d.get('warp_to', None)
        if want is not None:
            if abs(event.y - want) <= self.DRAG_WARP_TOLERANCE:
                d.pop('warp_to', None)
                d['last_y'] = event.y
                return 'break'
            d['warp_skip'] = d.get('warp_skip', 0) + 1
            if d['warp_skip'] <= self.DRAG_WARP_SKIP_MAX:
                return 'break'
            d.pop('warp_to', None)
            d['no_warp'] = True
            self._scroll_cursor_restore()
            d['last_y'] = event.y
            return 'break'

        # 指の動きに応じて実際にスクロールする。
        # 指を下へ動かす（y が増える）と、下に隠れていた内容が
        # 見えるよう画面を上へ送る（＝スクロール量は逆符号）。
        #
        # **動かされた量は、報せの座標ではなく実カーソル位置で数える**
        # （項目48-KD・2026-08-27 3度目の報告「同じ方向にドラッグを
        # 続けると、そのうち止まってカーソルが表示される」）。
        # 2度目の直し（回数の門）は「戻り先 ±60px に報せが来る」ことを
        # 当てにしていたが、**速いドラッグでは戻した直後の報せがもう
        # ±60px の外**——実際の動きだけで門の8回を使い切り、
        # 「戻せない道具」に落ちていた。実位置なら、戻し（同期）の後は
        # 必ず「戻した先＋動いたぶん」を指すので、照合そのものが要らない。
        # 報せは「動いた合図」としてだけ使う（複数の報せが同じ実位置を
        # 読んでも、差の合計は変わらない）。
        try:
            py = widget.winfo_pointery() - widget.winfo_rooty()
        except Exception:
            py = event.y
        dy_step = py - d['last_y']
        d['accum'] += dy_step
        line_h = self._get_line_height()
        lines = int(d['accum'] / line_h)
        if lines != 0:
            d['accum'] -= lines * line_h
            # **俯瞰の間、下端に着いてからの掴みは「枠」を進める**
            # （項目48-LH'・2026-08-29 うにさんの報告「右ダブル
            # クリックの縮小だと、下のスクロールが途中から進まなく
            # なります」。Tk は最終行が画面の下端に達するとそれ以上
            # スクロールできない——俯瞰は一度に61行見えるので、
            # 上端は「最終行−61」で頭打ちになり、**文書の末尾側を
            # 戻り先にできなかった**。余ったぶんは戻り先の枠を
            # 画面の中で下へ滑らせ、離したらその枠の上端に置き直す）
            fwd = -lines
            if self._overview is not None:
                fwd = self._ov_absorb(fwd)
            if fwd:
                self._on_wheel_units(fwd)
        d['last_y'] = py
        self._edge_warp(d, widget, event)
        return 'break'

    # 戻した先から、この画素数より離れた報せは「まだ戻っていない」
    # とみなす（下の `_edge_warp` と `_drag_motion` の頭）。
    DRAG_WARP_TOLERANCE = 60
    # 戻しを頼んでから、戻り先に着かない報せをいくつまで捨てて待つか。
    # これを超えても戻らなければ「戻せない道具」と判定する。
    # 戻す前に並んでいた古い報せは高々数個（OS がマウスの動きを
    # 合流させる）なので、ふつうは1〜2個で戻りの報せに合流する。
    DRAG_WARP_SKIP_MAX = 8
    # 画面の上下端から、この画素数まで近づいたら戻す。
    # **端に着いてからでは遅い**——速く振ると、その1回の報せで端まで
    # 行き着いてしまい、はみ出したぶんの動きが切り捨てられる。
    # 隠している（`_scroll_cursor_hide`）ので、早めに戻しても見えない。
    DRAG_WARP_EDGE = 64

    def _warp_pointer(self, widget, x, y):
        """
        カーソルを欄の (x, y) へ、**その場で**動かす（項目48-JQ の続き・
        2026-08-27）。

        Tk の `event_generate('<Motion>', warp=True, …)` は、実際の
        移動を **idle まで遅らせる**（Tk の作り）。プローブは `update()`
        を挟むので idle が来て動くが、**実機のドラッグ中は報せが流れ
        続けて idle が来ない**——戻しが実行されないまま報せだけが届き、
        「戻せない道具」と誤判定 → 端で止まる／遅れて戻った瞬間に
        大ジャンプ、が再発した（うにさんの報告・2026-08-27 の2度目）。
        Windows では `SetCursorPos`（同期）で動かす。

        戻り値: 'sync'（もう動いている）／'async'（動くのは後）／
                False（頼めなかった）。
        """
        if sys.platform == 'win32':
            try:
                import ctypes
                if ctypes.windll.user32.SetCursorPos(
                        int(widget.winfo_rootx() + x),
                        int(widget.winfo_rooty() + y)):
                    return 'sync'
            except Exception:
                pass
        try:
            widget.event_generate('<Motion>', warp=True, x=x, y=y)
            return 'async'
        except Exception:
            return False

    def _edge_warp(self, d, widget, event):
        """
        **画面の端でスクロールを止めない**（うにさんの指定・2026-08-25。
        項目48-JO → **48-JQ で UE4 と同じ形にした**）。

            「カーソルが画面の上下端に到達しても、そこからマウスを
              上下に動かしたらスクロールする。**カーソルが端にあったら
              必ずスクロールするわけではない**」

            「UE4ブループリント画面のスクロールは、どこまでもスクロール
              できた。**スクロール中にカーソルを消していたかもしれない**し、
              **マウスの移動量を基準にしてスクロールしていた**のかも
              しれない」

        カーソルが画面の端に貼り付くと、そこから先はマウスを動かしても
        **OS がカーソルを画面内に留める**ので、`<B3-Motion>` が
        **一度も来ない**。`event.y` が変わらない＝動かされていないのと
        見分けが付かず、スクロールがそこで止まっていた。

        **うにさんの見立てのとおり**にした:

            掴んだ瞬間に**カーソルを隠す**（`_scroll_cursor_hide`）
            → 端に近づいたら**欄の中ほどへ戻す**（見えないので気づかない）
            → 進めるのは**戻した量ではなく、動かされた量**だけ
            → 離したら**掴み始めた場所へ戻して**、また見せる

        Tk からは「生の移動量」が取れないので、**隠して戻す**ことで
        同じものを作る（SDL の相対モードと同じ手口）。
        「端に居る間ずっと送る」形（自動スクロール）にはしない——
        うにさんの2文目がそれを断っている。**動かしたぶんだけ**進み、
        手を止めれば止まる。

        戻したことでスクロールしてしまわないよう、`warp_to` に戻し先を
        控え、次の報せは「位置合わせだけ」にする（呼び元の頭）。
        画面に直接触る操作のようにカーソルを動かせない道具では戻らない
        ので、そのときは以後この掴みでは戻さず、カーソルも見せ直す
        （`no_warp`）。
        """
        if d.get('no_warp'):
            return
        try:
            py = widget.winfo_pointery()
            screen_h = widget.winfo_screenheight()
            top = widget.winfo_rooty()
            h = widget.winfo_height()
        except Exception:
            return
        if h <= 0 or screen_h <= 0:
            return
        # 48-VP: screenheight は現在のモニターの下端とは限らない。
        # 負の座標・高さの違う副画面でも、実際の作業領域で戻す。
        try:
            area = monitor_work_area(widget.winfo_pointerx(), py)
        except Exception:
            area = None
        screen_top, screen_bottom = (area[1], area[3]) if area else (0, screen_h)
        edge = min(self.DRAG_WARP_EDGE,
                   max(1, (screen_bottom - screen_top) // 4))
        if not (py <= screen_top + edge or py >= screen_bottom - 1 - edge):
            return
        # 欄の「見えていて、端から離れた部分」の中央へ戻す。
        # 欄全体の中央を切り詰めるだけだと、画面端に戻る場合がある。
        lo = max(top + 1, screen_top + edge + 1)
        hi = min(top + h - 2, screen_bottom - edge - 2)
        if hi <= lo:
            return
        want = (lo + hi) // 2 - top
        try:
            _w = widget.winfo_width()
        except Exception:
            _w = 0
        _x = event.x
        if _w > 8:
            xlo, xhi = 4, _w - 5
            if area:
                try:
                    left = widget.winfo_rootx()
                    xlo = max(xlo, area[0] + 1 - left)
                    xhi = min(xhi, area[2] - 2 - left)
                except Exception:
                    pass
            if xhi < xlo:
                return
            _x = max(xlo, min(xhi, _x))
        # **その場で動かす**（`_warp_pointer`・Windows は SetCursorPos）。
        # Tk の warp は idle まで遅れるので、実機のドラッグ中は
        # 間に合わない（`_warp_pointer` の説明）。
        _got = self._warp_pointer(widget, _x, want)
        if not _got:
            d['no_warp'] = True
            self._scroll_cursor_restore()
            return
        if _got == 'sync':
            # もう動いている。基準（last_y）を**実測**で取り直すだけで
            # よく、握手（warp_to）は要らない（項目48-KD——握手は
            # 速いドラッグで「戻せない道具」に誤判定する）。
            try:
                d['last_y'] = widget.winfo_pointery() - widget.winfo_rooty()
            except Exception:
                d['last_y'] = want
        else:
            # 非同期の環境（Tk の warp）だけ、従来の握手で待つ
            d['warp_to'] = want
            d['warp_skip'] = 0
            d['last_y'] = want
        d['warped'] = True

    def _drag_release(self, event, widget):
        """
        ドラッグを終える。

        戻り値: このドラッグがスクロールだったなら True。
                （呼び出し側は、クリック相当の処理を続けて良いかの判断に使う）
        """
        d = self._drag
        was_scroll = bool(d and d['widget'] is widget and d['mode'] == 'scroll')
        # 先に掴みを下ろす。_show_cursor_when_settled の
        # 「新しい掴みが始まったか」の門が、いま終わろうとしている
        # 掴み自身に当たらないように。
        self._drag = None
        # **俯瞰から出るのはここ1か所**（2026-08-28・学び22）。
        # 離しの道は欄ごとに別々（`_on_editor_right_click`・
        # `_on_result_release`・ガター）なので、そこに書くと片方を
        # 迂回して**字が小さいまま戻らなくなる**。
        if getattr(self, '_overview', None) is not None:
            self._overview_exit()
        if was_scroll:
            # **掴み始めた場所へ戻してから見せる**（項目48-JQ）。
            # 隠している間に何度も戻しているので、そのままだと
            # カーソルが見当違いの場所に現れる。
            # 見せる側（_scroll_cursor_restore）は _restore_pointer が
            # **戻り先に着いてから**呼ぶ——戻しは非同期なので、先に
            # 見せると移動先で一瞬見えてから飛ぶ（うにさんの報告・
            # 2026-08-27）。
            self._restore_pointer(d)
        else:
            self._scroll_cursor_restore()
        return was_scroll

    def _scroll_panes(self):
        """
        スクロールの掴みでカーソルを隠す**全部の欄**（2026-08-28）。

        掴んだ欄1つだけに `cursor='none'` を置いていたのが
        **うにさんの報告②の正体**——「右ドラッグのスクロールで
        マウスを素早く動かすと、カーソルが表示に戻ることがあります」。
        速く振ると、戻し（`_edge_warp`）が間に合う前に**ポインタが
        隣の欄（行番号ガター・補正欄）や窓の外へ出る**。掴みは
        Tk が握っているので報せは来続けるが、**カーソルの形は
        その下に在る窓のもの**なので、隠していない欄に入った瞬間に
        見えてしまう。

        **学び22 そのもの**（片方だけに置くと、そちらを迂回して
        素通りする）。門・印・設定は全部の道に掛ける——ここでは
        「隠す」を全部の欄と窓そのものに掛ける。
        """
        got = []
        for name in ('editor', 'editor_gutter', 'result_view',
                     'result_gutter', 'root'):
            w = getattr(self, name, None)
            if w is not None:
                got.append(w)
        return got

    def _scroll_cursor_hide(self, widget):
        """
        スクロールの掴みの間だけカーソルを隠す（項目48-JQ）。

        **掴んだ欄だけでなく、隣の欄と窓そのものにも掛ける**
        （2026-08-28・うにさんの報告②。`_scroll_panes` の説明）。
        """
        if getattr(self, '_scroll_cursor', None) is not None:
            return
        saved = []
        for w in self._scroll_panes():
            try:
                saved.append((w, w.cget('cursor')))
                w.config(cursor='none')
            except Exception:
                continue    # 隠せない欄は飛ばす（見えたままでも動く）
        if not saved:
            return          # 隠せない環境なら、見えたままでも動く
        self._scroll_cursor = saved

    def _scroll_cursor_restore(self):
        """隠したカーソルを元の形に戻す（掴みを離した・戻せなかった）。"""
        got = getattr(self, '_scroll_cursor', None)
        self._scroll_cursor = None
        if not got:
            return
        for widget, old in got:
            try:
                widget.config(cursor=old)
            except Exception:
                pass

    def _restore_pointer(self, d):
        """
        掴み始めた場所へカーソルを戻してから、見せる（項目48-JQ）。

        戻し（`event_generate` の warp）は**非同期**なので、頼んだ
        直後に見せると、**移動先で一瞬見えてから元の位置へ飛ぶ**のが
        見えてしまう（うにさんの報告・2026-08-27）。戻り先に着いたのを
        確かめてから見せる。着かないまま時間が過ぎたら、そのまま
        見せる（見せないままにはしない）。
        """
        if d.get('no_warp') or not d.get('press_root'):
            self._scroll_cursor_restore()
            return
        widget = d.get('widget')
        if widget is None:
            self._scroll_cursor_restore()
            return
        try:
            x = d['press_root'][0] - widget.winfo_rootx()
            y = d['press_root'][1] - widget.winfo_rooty()
            ok = self._warp_pointer(widget, x, y)
        except Exception:
            ok = False
        if not ok:
            self._scroll_cursor_restore()
            return
        # Windows（SetCursorPos）ならもう着いている。Tk の warp の
        # 環境（idle 待ち）に備えて、着いたのを確かめてから見せる。
        self._show_cursor_when_settled(d['press_root'], tries=25)

    def _show_cursor_when_settled(self, target_root, tries):
        """戻り先にカーソルが着いてから見せる（`_restore_pointer`）。"""
        got = getattr(self, '_scroll_cursor', None)
        if got is None:
            return              # もう見せてある（または隠していない）
        nd = getattr(self, '_drag', None)
        if nd is not None and nd.get('mode') == 'scroll':
            return              # 新しい掴みが始まった。そちらに任せる
        try:
            px, py = self.root.winfo_pointerxy()
            near = (abs(px - target_root[0]) <= 3
                    and abs(py - target_root[1]) <= 3)
        except Exception:
            near = True
        if near or tries <= 0:
            self._scroll_cursor_restore()
            return
        try:
            self.root.after(
                10, lambda: self._show_cursor_when_settled(
                    target_root, tries - 1))
        except Exception:
            self._scroll_cursor_restore()

    # ------------------------------------------------------------
    # 俯瞰（右ダブルクリックを押し続けている間だけ字を小さくする）
    # ------------------------------------------------------------
    # うにさんの指定（2026-08-28）:
    #
    #   「右クリックをダブルクリックしてそのまま押し続けている間、
    #     **フォントサイズを一時的に5**にします。全体が把握しやすく
    #     なり、そのままマウスを上下に動かすとスクロールします。
    #     クリックを離すと元に戻る」
    #
    # 動きは**既にある右ドラッグのスクロールに乗せる**（`_drag_*`）。
    # 掴みの型を最初から `scroll` にしておくだけで、端の戻し
    # （`_edge_warp`）・カーソル隠し・離したときの戻しが全部そのまま
    # 効く。**新しいスクロールをもう1つ書かない**（48-GN「同じ判定を
    # もう一度書くと、いつか食い違う」）。
    #
    # 行の高さ（`_line_h`）は字の大きさで変わるので、**入るときと
    # 出るときに捨てる**。捨て忘れると、俯瞰の間は11ポイントの
    # 行の高さで数えることになり、指の動きに対してスクロールが
    # 5分の1しか進まない。

    # 字を入れ替えたあと、補正欄からの「動いた」の報せが尽きるまで
    # 逆流の門を閉じておく時間（`_on_result_scroll`）。
    FONT_SWAP_QUIET_MS = 120

    def _overview_fonts(self, size):
        """
        本文・補正欄・行番号の字を size ポイントにする（俯瞰）。
        size が None なら元の大きさへ戻す。

        **字を変えると Tk は表示を先頭へ戻す。** 見ていた行を控えて
        置き直さないと、俯瞰に入った瞬間に1行目へ飛び（見たかった
        場所が消える）、離したときにも1行目へ戻る（行き先を決める
        道具にならない）。probe_overview で実測して足した。
        """
        font = (EDITOR_FONT[0], size) if size else EDITOR_FONT
        try:
            top = int(self.editor.index('@0,0').split('.')[0])
        except Exception:
            top = None
        # 俯瞰から出るときの置き直し先の上書き（項目48-LH'）
        _want = getattr(self, '_ov_exit_top', None)
        self._ov_exit_top = None
        if _want is not None:
            top = _want
        # **同期を止めてから字を変える**（`_on_wheel_units` と同じ構え）。
        # 補正欄の字を変えると補正欄が「動いた」と報せ、
        # `_on_result_scroll` → `_sync_partner_to_line(補正欄, メモ欄)`
        # が走って、**メモ欄が補正欄の行（空なら1行目）へ引きずられる**。
        # probe_overview で実測——離した直後は正しく、10ms 後の報せで
        # 1行目へ飛んでいた。メモ欄が源（項目48-JA の決め）なので、
        # 逆流はここで止める。
        was_syncing = self._syncing
        self._syncing = True
        self._font_swap = True      # 補正欄からの逆流を止める（下の門）
        try:
            for name in ('editor', 'result_view'):
                w = getattr(self, name, None)
                if w is None:
                    continue
                try:
                    w.config(font=font)
                except Exception:
                    pass
                # **行間も一緒に詰める**（うにさんの指定・2026-08-28
                # 2度目。字だけ小さくしても余白は残る——下の説明）
                self._overview_tighten(w, name, tight=bool(size))
            # タブの止まりは字の幅で決めている。字と一緒に置き直す
            # （項目48-LG）
            self._apply_tab_stops(font)
            # 行の高さは字で変わる。**捨てて測り直させる**
            self._line_h = None
            # **見ていた行へ置き直す**（字を変えた副作用の打ち消し）。
            # 置き直す前に **Tk に組み直させる**——字を変えた直後の
            # `yview` は古い寸法の上で効き、あとから来る組み直しが
            # 表示を先頭へ戻してしまう（probe_overview で実測。
            # `update_idletasks` を挟むまで 7行目 → 1行目に戻っていた）。
            if top is not None:
                try:
                    self.editor.update_idletasks()
                    self.editor.yview(f'{top}.0')
                    if not self._layout_is_unified():
                        self._sync_partner_to_line(self.editor,
                                                   self.result_view)
                except Exception:
                    pass
        except Exception:
            self._syncing = was_syncing
            raise
        # **同期はまだ解かない。** 補正欄の組み直しの報せは
        # `update_idletasks` のあとにも1つ来る（probe_overview で実測
        # ——ここで解くと、その報せで 7行目 → 1行目に戻された）。
        # 落ち着いてから置き直して、そこで解く。
        try:
            self.root.after_idle(self._overview_settle, top, was_syncing)
        except Exception:
            self._overview_settle(top, was_syncing)
        # 行番号は**置き直したあと**に引く（先に引くと前の位置のまま）
        for name in ('editor_gutter', 'result_gutter'):
            g = getattr(self, name, None)
            if g is None:
                continue
            try:
                g.font = font
                g.redraw()
            except Exception:
                pass
        # 未変換の文字の字も、いまの字に合わせ直す（項目48-LO）
        self._set_ime_font()
        try:
            first, last = self.editor.yview()
            self.v_scrollbar.set(first, last)
            self._update_header_visibility(first)
        except Exception:
            pass

    def _overview_tighten(self, widget, name, tight):
        """
        俯瞰のあいだ、**行と行のあいだの余白を落とす**（2026-08-28・
        うにさんの指定2度目）。

        > 「右クリックダブルクリックはフォントサイズ5でよいですが、
        >   **行間をもっと詰めて広い範囲が映るようにします**」

        字だけ 11 → 5 にしても、`spacing1`＋`spacing3`（2＋4＝6px）と
        `pady`（12＋12＝24px）は**そのまま残る**ので、詰めたぶんが
        余白に食われていた。落とす値は `OVERVIEW_TIGHT`。

        **元の値はその場で読んで控える**（`_scroll_cursor_hide` と
        同じ構え。同じ数を2か所に書かない・48-GN）。控えは欄ごと
        （`self._overview_pad[name]`）で、戻すときに使い切る。
        """
        store = self._overview_pad
        if tight:
            if name in store:
                return              # 二重に控えない（元が消える）
            try:
                store[name] = {k: widget.cget(k) for k in OVERVIEW_TIGHT}
            except Exception:
                return              # 読めない欄は触らない
            try:
                widget.config(**OVERVIEW_TIGHT)
            except Exception:
                store.pop(name, None)
        else:
            old = store.pop(name, None)
            if not old:
                return
            try:
                widget.config(**old)
            except Exception:
                pass

    def _overview_settle(self, top, was_syncing):
        """
        字を入れ替えたあと、**組み直しが落ち着いてから**行を置き直し、
        同期を解く（`_overview_fonts` の続き・2026-08-28）。

        補正欄の字を変えると、補正欄は「動いた」と何度か報せる。
        その最後の1つが `update_idletasks` のあとに来て、
        `_on_result_scroll` → `_sync_partner_to_line(補正欄, メモ欄)` で
        **メモ欄を補正欄の行（中身が無ければ1行目）へ引きずって**
        いた。メモ欄が源（スクロールの決め）なので、ここまで
        `_syncing` を立てたままにして逆流を止める。
        """
        try:
            if top is not None:
                self.editor.yview(f'{top}.0')
                if not self._layout_is_unified():
                    self._sync_partner_to_line(self.editor, self.result_view)
        except Exception:
            pass
        self._syncing = was_syncing
        try:
            first, last = self.editor.yview()
            self.v_scrollbar.set(first, last)
            self._update_header_visibility(first)
            self.editor_gutter.sync_yview(first, last)
            self.result_gutter.sync_yview(*self.result_view.yview())
        except Exception:
            pass
        # 補正欄の組み直しの報せが尽きるまで、逆流の門は閉じたまま
        def _open():
            self._font_swap = False
        try:
            self.root.after(self.FONT_SWAP_QUIET_MS, _open)
        except Exception:
            self._font_swap = False

    def _overview_enter(self, event, widget):
        """俯瞰に入る（右ダブルクリックを押した瞬間）。"""
        if self._overview is not None:
            return
        self._overview = {'widget': widget}
        self._ov_aim_off = 0         # 下端で余った掴みのぶん（48-LH'）
        # **ふだんの字での実際の可視行数**を、字を替える前に数えて
        # 控える（項目48-LH。字の高さからの見積もりでは 23 と出るのに
        # 実際は 35 行見えていて、枠と出た後の画面がずれた・実測）
        try:
            _t = int(str(self.editor.index('@0,0')).split('.')[0])
            _h = max(1, self.editor.winfo_height() - 1)
            _b = int(str(self.editor.index(f'@0,{_h}')).split('.')[0])
            self._ov_dest_n = max(1, _b - _t + 1)
        except Exception:
            self._ov_dest_n = 23
        self._overview_fonts(OVERVIEW_FONT_SIZE)
        self._ov_dest_start()        # 移る範囲の枠（項目48-LH）
        # 掴みを**最初から scroll の型で**置く（判定の8画素を待たない）
        try:
            press_root = (widget.winfo_pointerx(), widget.winfo_pointery())
        except Exception:
            press_root = None
        self._drag = {
            'widget': widget, 'mode': 'scroll',
            'start_x': event.x, 'start_y': event.y,
            'last_y': event.y, 'accum': 0.0,
            'always_scroll': True,
            'press_root': press_root, 'warped': False,
        }
        self._scroll_cursor_hide(widget)
        return 'break'

    def _overview_exit(self):
        """
        俯瞰から出る（ボタンを離した）。字を戻す。

        **俯瞰で見ていた行のまま**戻る（`_overview_fonts` が置き直す）
        ——俯瞰は行き先を決める道具なので、戻ったら元の場所では
        意味が無い。
        """
        if self._overview is None:
            return
        self._overview = None
        # 下端で枠を滑らせていたなら、**枠の上端**へ置き直す（48-LH'）
        _off = max(0, getattr(self, '_ov_aim_off', 0))
        if _off:
            try:
                self._ov_exit_top = int(str(self.editor.index(
                    '@0,0')).split('.')[0]) + _off
            except Exception:
                self._ov_exit_top = None
        self._ov_aim_off = 0
        self._ov_dest_stop()         # 移る範囲の枠（項目48-LH）
        self._overview_fonts(None)
        # 折り返しの境目が変わるので、空白の印は塗り直す（項目48-II）
        self._schedule_whitespace_paint()

    def _ov_dest_start(self):
        """移る範囲の枠を出す（項目48-LH・俯瞰の間だけ）。"""
        w = getattr(self, 'editor', None)
        if w is None:
            return
        try:
            w.tag_configure(OVERVIEW_DEST_TAG, background=HOVER_BG,
                            borderwidth=OVERVIEW_DEST_BORDER,
                            relief='solid')
        except Exception:
            pass
        self._ov_dest_lines = None
        self._ov_dest_job = None
        self._ov_dest_tick()

    def _ov_dest_tick(self):
        """
        枠を今の上端に付け直す（60msごと・俯瞰の間だけ）。

        俯瞰から出るときは**上端の行が置き直される**ので、離した
        ときに映るのは「いまの上端から、ふだんの字で1画面ぶん」。
        スクロールに枠が付いてくるよう、短い間隔で見直す（タグの
        付け直しは範囲が変わったときだけ＝ふだんは何もしない）。
        """
        self._ov_dest_job = None
        if self._overview is None:
            return
        w = getattr(self, 'editor', None)
        try:
            top = int(str(w.index('@0,0')).split('.')[0])
            # ふだんの字での実際の可視行数（俯瞰に入る前に数えた）
            n = max(1, getattr(self, '_ov_dest_n', 23))
            # 下端で余った掴みのぶん、枠は画面の中を下へ（48-LH'）
            aim = top + max(0, getattr(self, '_ov_aim_off', 0))
            aim = min(aim, self._ov_aim_cap(n))
            rng = (aim, aim + n - 1)
            if rng != getattr(self, '_ov_dest_lines', None):
                self._ov_dest_lines = rng
                w.tag_remove(OVERVIEW_DEST_TAG, '1.0', 'end')
                w.tag_add(OVERVIEW_DEST_TAG,
                          f'{rng[0]}.0', f'{rng[1] + 1}.0')
        except Exception:
            pass
        try:
            self._ov_dest_job = self.root.after(60, self._ov_dest_tick)
        except Exception:
            self._ov_dest_job = None

    def _ov_aim_cap(self, n):
        """枠の上端が行ける最深の行（項目48-LH'）。"""
        try:
            text = self.editor.get('1.0', 'end-1c')
            total = text.count('\n') + 1
            content = total - (len(text)
                               - len(text.rstrip('\n')))
            return max(1, min(content, total - n + 1))
        except Exception:
            return 1

    def _ov_absorb(self, fwd):
        """
        俯瞰の掴みのうち、**スクロールできないぶんを枠へ回す**
        （項目48-LH'）。fwd は進めたい行数（正＝下へ）。
        枠へ回したぶんを引いた残りを返す。
        """
        off = max(0, getattr(self, '_ov_aim_off', 0))
        try:
            if fwd > 0:
                # 下端に着いているなら、これ以上は枠を進める
                at_bottom = self.editor.yview()[1] >= 0.9999
                if at_bottom:
                    top = int(str(self.editor.index(
                        '@0,0')).split('.')[0])
                    n = max(1, getattr(self, '_ov_dest_n', 23))
                    # 枠の上端の限界＝**本文の最終行**と「ふだんの字で
                    # 置ける最深の上端」の小さいほう。末尾の下駄
                    # （空行）へ枠だけ滑ると、離したとき届かない
                    aim_cap = self._ov_aim_cap(n)
                    max_off = max(0, aim_cap - top)
                    take = min(fwd, max_off - off)
                    if take > 0:
                        off += take
                        fwd -= take
                    elif off >= max_off:
                        fwd = 0     # 枠も末尾に届いた。それ以上は無い
            elif fwd < 0 and off > 0:
                # 戻すときは、まず枠を上へ戻してからスクロール
                take = min(-fwd, off)
                off -= take
                fwd += take
        except Exception:
            pass
        self._ov_aim_off = off
        return fwd

    def _ov_dest_stop(self):
        """移る範囲の枠を消す（俯瞰から出るとき）。"""
        job = getattr(self, '_ov_dest_job', None)
        if job is not None:
            try:
                self.root.after_cancel(job)
            except Exception:
                pass
        self._ov_dest_job = None
        self._ov_dest_lines = None
        w = getattr(self, 'editor', None)
        if w is not None:
            try:
                w.tag_remove(OVERVIEW_DEST_TAG, '1.0', 'end')
            except Exception:
                pass

    def _on_right_double(self, event, widget):
        """
        右クリックのダブルクリック（2回目の押し下げ）で俯瞰に入る。

        候補一覧は閉じてから入る——1回目の離しで開いていることが
        ある（統合レイアウトのメモ欄・補正欄）。
        """
        self._close_dropdown()
        return self._overview_enter(event, widget)

    def _on_editor_release(self, event):
        # カーソルが動いただけでも、終端の罫線は出し入れが要る
        # （項目48-IM。打鍵は `_on_change` が拾うが、クリックは
        # こちらでしか拾えない）。
        self._schedule_whitespace_paint()
        # **Tk の自動スクロールの繰り返しを必ず止める**（項目48-TA・2026-09-06・
        # うにさんの報告「両方同時にクリックして、1行目の上までドラッグすると、
        # そのあとホイールで下へスクロールできなくなる」）。左ドラッグが欄の
        # 上へ出ると Tk は `tk::TextAutoScan`（50ms ごとに上へ送る）を始め、
        # `<ButtonRelease-1>` のクラス束縛 `tk::CancelRepeat` で止める。右も
        # 押していると下で「掴みだった」として 'break' を返し、クラス束縛が
        # 走らず、繰り返しが止まらないまま——ホイールで下へ送っても 50ms 後に
        # 上へ戻されていた
        try:
            self.root.tk.call('tk::CancelRepeat')
        except Exception:
            pass
        was_scroll = self._drag_release(event, self.editor)
        if was_scroll:
            self.editor.focus_set()
            return 'break'

        # --- 語を拾うモード中は、メモ欄の語も拾える ---
        # 統合レイアウトには補正欄が無いので、メモ欄から拾えないと
        # この機能が一切使えない。分割レイアウトでも「メモ欄の語を
        # 別の場所へ持っていきたい」ことがあるため、両方で有効にする
        # （どちらも実機から報告された）。
        #
        # 差し込み先はモードに入った時点のマーク位置なので、
        # 拾う場所と差し込む場所が同じ欄でも問題なく動く。
        if getattr(self, '_pick_mode', None):
            selected = ''
            try:
                sel = self.editor.tag_ranges('sel')
                if sel:
                    selected = self.editor.get('sel.first', 'sel.last')
            except Exception:
                selected = ''
            unit_text = ''
            hit = self._editor_unit_under_pointer(event)
            if hit is not None:
                unit_text = hit[1]['text']
            picked = resolve_pick_text(selected, unit_text)
            if picked:
                try:
                    self.editor.tag_remove('sel', '1.0', 'end')
                except Exception:
                    pass
                self._pick_insert(picked)
                return 'break'

        self.editor.focus_set()

    # ------------------------------------------------------------
    # 語を拾って差し込むモード（F1 / =）
    # ------------------------------------------------------------
    # 補正結果の語を、書きかけの文のカーソル位置に取り込むための操作。
    # 対象は常に「メモ欄」（result_view からは開始できない）。
    #
    # F1 と「=」でモードへの入り方が違う:
    #   F1  … それ自体は文字を入力しないキーなので、押した位置を
    #         そのまま覚えてモードに入る。
    #   =   … 「=」はメモ欄で普通に打てる文字でもあるため、まず
    #         「=」をその場に入力してから、その文字の位置を覚えて
    #         モードに入る。Esc を押す、あるいはモード中に続けて
    #         別のキーを打つと、モードだけを中断し、
    #         打った「=」はそのまま残す（削除しない）。
    #         語を拾えたときだけ、その「=」を消して拾った文字に
    #         差し替える。
    #
    # 差し込み先の位置は、文字列インデックス（"3.5" 等）ではなく
    # tkinter のマーク（gravity 付き）で覚える。モード中にメモ欄の
    # 他の場所へ文字を足しても、マークは自分の指した文字に
    # ついていくため、位置がずれない。

    _PICK_MARK = 'pick_target'
    _PICK_EQUALS_START = 'pick_equals_start'
    _PICK_EQUALS_END = 'pick_equals_end'
    # 引用モードに入った時点で選択されていた範囲（引用後に消す）
    _PICK_SEL_START = 'pick_sel_start'
    _PICK_SEL_END = 'pick_sel_end'

    # --- IME が確定した半角文字を、機能キーと取り違えない（項目48-EH）---
    #
    # うにさん報告（2026-08-17）:
    #   「ｐを半角変換して確定すると、引用モードが誤作動したり、
    #     前後の文字列によっては検索が誤作動することがあります」
    #
    # `p` の番号 0x70 は VK_F1 と同じ。tkinter は IME が確定した
    # 文字の番号を仮想キーコードとして読み直すため、keysym が F1 に
    # 化ける（詳しくは `_IME_MISREAD_KEYSYMS` の説明）。
    #
    # 入れ方が2通りあるので、受け口も2つに分ける:
    #
    #   欄への束縛（editor.bind('<F1>')）… Tk の文字入力より**先**に
    #       走る。'break' を返すと文字が入らないので、**ここで
    #       文字を入れてから** 'break' する。
    #   bind_all … Text のクラス束縛が**先**に走って文字はもう
    #       入っている。重ねて入れると `pp` になるので入れない。

    def _ime_first(self, handler):
        """
        キー名を指定した束縛を、IME の取り違えの受け皿の**後ろ**に置く
        （項目48-IN）。

        Tk は同じ欄に `<KeyPress>` と `<Delete>` の両方が張ってあると、
        keysym=Delete の打鍵では**より具体的な `<Delete>` だけ**を呼ぶ
        （`<KeyPress>` の束縛は1つも走らない）。`<KeyPress>` に張った
        `_on_ime_ascii_key` はそこで素通りされる。

        だから、取り違えの対象になるキー名（`_IME_MISREAD_KEYSYMS`）へ
        個別に束縛するときは、この包みを通す。IME が確定した文字なら
        **`<KeyPress>` の束縛と同じ順**で文字として扱い（F2 の範囲が
        あれば C-1＝範囲の後ろへ、無ければ受け皿がカーソル位置へ）、
        文字でなければ（本物の Delete など）元の処理へ渡す。

        候補一覧（Listbox）への束縛にも同じ包みを使う。一覧には
        文字を書けないので、そちらは C-1（`_on_dropdown_keypress`）
        だけに回す。
        """
        def wrapped(event=None):
            if event is not None:
                widget = getattr(event, 'widget', None)
                if isinstance(widget, tk.Listbox):
                    chain = (self._on_dropdown_keypress,)
                else:
                    chain = (self._on_f2_range_keypress,
                             self._on_ime_ascii_key)
                for fn in chain:
                    got = fn(event)
                    if got is not None:
                        return got
            return handler(event)
        return wrapped

    def _ime_fkey_insert(self, event):
        """欄への束縛用。文字を入れて 'break'。文字でなければ None。"""
        ch = ime_confirmed_char_event(event)
        if ch is None:
            return None
        widget = getattr(event, 'widget', None) or self.editor
        try:
            if widget.tag_ranges('sel'):
                widget.delete('sel.first', 'sel.last')
        except Exception:
            pass
        try:
            widget.insert('insert', ch)
            widget.see('insert')
        except Exception:
            return None      # 書けない欄なら標準の動きに委ねる
        return 'break'

    def _ime_fkey_skip(self, event):
        """bind_all 用。文字なら 'break'（機能は実行しない）。"""
        return 'break' if ime_confirmed_char_event(event) is not None \
            else None

    def _on_pick_key_widget(self, event=None):
        """メモ欄そのものへの `<F1>` 束縛（項目48-EH の入口）。"""
        got = self._ime_fkey_insert(event)
        if got is not None:
            return got
        return self._on_pick_key(event)

    def _on_f2_candidates_widget(self, event=None):
        """メモ欄・補正欄への `<F2>` 束縛（項目48-EH の入口）。"""
        got = self._ime_fkey_insert(event)
        if got is not None:
            return got
        return self._on_f2_candidates(event)

    def _on_find_next_key(self, event=None, backwards=False):
        """`<F3>` / `<Shift-F3>`（bind_all）。項目48-EH の入口。"""
        if self._ime_fkey_skip(event) is not None:
            return 'break'
        return self._find_next_shortcut(backwards=backwards)

    def _on_pick_key(self, event=None):
        # **IME が確定した `p`**（keysym が F1 に化けたもの）なら、
        # 引用モードに入ってはいけない（項目48-EH）。bind_all から
        # 来た場合は文字が既に入っているので、ここでは何もしない。
        if self._ime_fkey_skip(event) is not None:
            return 'break'
        # bind_all はフォーカス位置を問わず発火するため、
        # ここで焦点がメモ欄かどうかを確認する。対象は常にメモ欄で、
        # 補正欄やダイアログにフォーカスがあるときは反応しない
        # （実機からの指定）。
        # ただし、モードを解除する操作（Esc等）とは違い、
        # 既にモード中なら焦点の位置に関わらず解除だけは許す
        # （そうしないと、モード中に補正欄をクリックしようとして
        #   フォーカスが移った状態で F1 を押しても解除できなくなる）。
        if not getattr(self, '_pick_mode', None):
            try:
                focused = self.root.focus_get()
            except Exception:
                focused = None
            # 簡易入力ウィンドウ側にフォーカスがあるなら、簡易入力の
            # F1 として扱う（欄・窓への直接の束縛が環境によって
            # 効かないことがあるため、こちらでも受ける・2026-08-09）。
            qwin = getattr(self, '_quick_win', None)
            if qwin is not None and focused is not None:
                try:
                    if focused.winfo_toplevel() is qwin:
                        return self._on_quick_f1(event)
                except Exception:
                    pass
            if focused is not self.editor:
                return None
        self.toggle_pick_mode()
        return 'break'

    def _wrap_with_brackets(self, open_ch, close_ch):
        """
        メモ欄の選択範囲を括弧で括る。選択が無ければ、
        カーソル位置に括弧だけを差し込む（カーソルは括弧の間に残す）。

        「」『』【】“” の4種を、常にメモ欄に対して行う
        （分割・統合どちらのレイアウトでも同じ操作）。

        F2 で語を選んでいる（候補一覧が開いていて、その語に色が
        付いている）ときは、選択範囲の代わりに **その語** を括る
        （うにさんの指定・2026-08-09）。
        """
        f2_range = self._f2_bracket_range()
        if f2_range is not None:
            start, end = f2_range
            try:
                self._close_dropdown()
                self._clear_f2_target()
                self._bracket_undo_separator()
                self.editor.insert(end, close_ch)
                self.editor.insert(start, open_ch)
                self.editor.edit_separator()
                self.editor.tag_remove('sel', '1.0', 'end')
                self.editor.mark_set(
                    'insert', f'{end}+{len(open_ch) + len(close_ch)}c')
                self._arm_bracket_exit(close_ch)
            except Exception:
                return
            self.editor.focus_set()
            self._on_change()
            return

        try:
            sel = self.editor.tag_ranges('sel')
        except Exception:
            sel = None

        if sel:
            start, end = str(sel[0]), str(sel[1])
            # 行をまるごと選択すると（行番号のクリック等）、範囲の
            # 末尾に改行まで入る。改行の後ろに閉じ括弧を入れると
            # **次の行の頭**に出てしまうので、末尾の改行は括りに
            # 含めない（実機で報告・2026-08-10）。
            try:
                while (self.editor.compare(end, '>', start)
                       and self.editor.get(f'{end}-1c', end) == '\n'):
                    end = self.editor.index(f'{end}-1c')
            except Exception:
                pass
            try:
                self._bracket_undo_separator()
                self.editor.insert(end, close_ch)
                self.editor.insert(start, open_ch)
                self.editor.edit_separator()
                # 括ったら、カーソルは閉じ括弧の右（括弧の外）へ移す。
                # そのまま続きを書き始められるようにする
                # （実機からの指定・2026-08-09。以前は括った範囲を
                # 選択し直していた）。
                new_end = f'{end}+{len(open_ch) + len(close_ch)}c'
                self.editor.tag_remove('sel', '1.0', 'end')
                self.editor.mark_set('insert', new_end)
                self._arm_bracket_exit(close_ch)
            except Exception:
                return
        else:
            try:
                pos = self.editor.index('insert')
                self._bracket_undo_separator()
                self.editor.insert(pos, open_ch + close_ch)
                self.editor.edit_separator()
                # カーソルは括弧の間（開き括弧の直後）に残し、
                # そのまま中身を打ち始められるようにする
                self.editor.mark_set('insert', f'{pos}+{len(open_ch)}c')
                # ただし、**IME が変換中**（未確定の文字がある）に
                # 押された場合は別。未確定の文字は Tk の選択（sel）に
                # ならないためこの経路へ来るが、続く確定で文字は
                # 括弧の中へ入り、カーソルも中に残ってしまう
                # （実機で「確定するとカーソルが括弧の中に居る」と
                # 報告・2026-08-10）。変換中だったときに限り、
                # 確定を後追いで捉えて外へ出す構えをする。
                # 変換中でなければ構えない（中に書き始めたいので）。
                try:
                    import ime_watch
                    if ime_watch.composition_active(
                            self.editor.winfo_id()):
                        self._arm_bracket_exit(close_ch)
                except Exception:
                    pass
            except Exception:
                return
        self.editor.focus_set()
        self._on_change()

    # 括った直後に「まだ確定していない変換」が確定されると、
    # 確定した文字が括弧の中に入り、カーソルも中に残る。
    # そのときだけカーソルを閉じ括弧の外へ出すための待ち時間（秒）。
    BRACKET_EXIT_SECONDS = 8

    def _bracket_undo_separator(self):
        """
        括弧を差し込む前に、取り消し（Ctrl+Z）の区切りを入れる。

        tkinter のテキスト欄は、続けて行った編集を**ひとまとまり**に
        して取り消す。区切りを入れないと、直前に打った文字と括弧が
        同じかたまりになり、**Ctrl+Z で打った文字まで消える**
        （実機で報告・2026-08-10「括弧だけ外してほしい」）。

        ここで区切っておけば、取り消しは「括弧を差し込んだ操作」
        だけを戻す＝括弧だけが外れる。差し込んだ**後**にも
        区切りを入れて、続けて打つ文字と混ざらないようにする。
        """
        try:
            self.editor.edit_separator()
        except Exception:
            pass

    def _arm_bracket_exit(self, close_ch):
        """
        括った直後の「確定でカーソルが中に残る」に備える。

        変換を確定する前の文字を括ると、その後の確定で IME が
        文字を括弧の中へ入れ直し、カーソルが閉じ括弧の手前に残る。
        うにさんの指定（2026-08-09）は「確定したら括弧の外（右）に
        出てほしい」。確定は打鍵として届かないことがあるので、
        **次に中身が変わったときに、カーソルが閉じ括弧の直前に
        あれば外へ出す**という後追いで実現する。

        範囲を選んで括ったとき（＝変換中の文字を括ったときを含む）
        だけ構える。何も選ばずに括ったときは、中に書き始めたいので
        構えない。
        """
        def _arm():
            import time as _time
            self._bracket_exit = (
                close_ch, _time.monotonic() + self.BRACKET_EXIT_SECONDS)

        # 括る処理の直後に走る _on_change に食べられないよう、
        # ひと呼吸おいてから構える。
        try:
            self.root.after_idle(_arm)
        except Exception:
            _arm()

    # 確定の文字が入り終わったとみなすまでの待ち（ミリ秒）。
    # IME の確定文字は1文字ずつ届くことがあり、最初の1文字が
    # 入った時点でカーソルを外へ出すと、残りの文字が括弧の外に
    # 入ってしまう（実機で「最初の一文字だけ括られる」と報告・
    # 2026-08-10）。変化が続く間は待ち、この時間だけ静かになって
    # からカーソルの位置を確かめる。
    BRACKET_EXIT_SETTLE_MS = 150

    def _maybe_exit_bracket(self):
        """
        括った直後の確定を後追いで捉える（_on_change から呼ばれる）。

        すぐには動かさず、変化が落ち着くのを待ってから
        _exit_bracket_now が実際にカーソルを外へ出す。
        変化が続いている間は、そのたびに待ち直す。
        """
        armed = getattr(self, '_bracket_exit', None)
        if not armed:
            return
        import time as _time
        close_ch, until = armed
        if _time.monotonic() > until:
            self._bracket_exit = None
            return
        if getattr(self, '_bracket_exit_job', None):
            try:
                self.root.after_cancel(self._bracket_exit_job)
            except Exception:
                pass
        self._bracket_exit_job = self.root.after(
            self.BRACKET_EXIT_SETTLE_MS, self._exit_bracket_now)

    def _exit_bracket_now(self):
        """カーソルが閉じ括弧の直前にあれば、その右へ移す。"""
        self._bracket_exit_job = None
        armed = getattr(self, '_bracket_exit', None)
        if not armed:
            return
        import time as _time
        close_ch, until = armed
        if _time.monotonic() > until:
            self._bracket_exit = None
            return
        try:
            if self.editor.get('insert', f'insert+{len(close_ch)}c') \
                    != close_ch:
                return    # まだ途中か別の場所。構えは残す（8秒で失効）
            self.editor.mark_set('insert', f'insert+{len(close_ch)}c')
            self.editor.see('insert')
        except Exception:
            return
        self._bracket_exit = None

    def _f2_bracket_range(self):
        """
        括弧ボタンが対象にすべき「F2 で選んでいる語」の範囲。

        候補一覧が開いていて、対象がメモ欄の語のときだけ
        (start, end) の位置文字列を返す。それ以外は None。
        """
        tgt = getattr(self, '_f2_focus_target', None)
        if tgt is None:
            return None
        if tgt.get('widget') is not getattr(self, 'editor', None):
            return None
        row = tgt['row']
        start = f'{row}.{tgt["start"]}'
        end = f'{row}.{tgt["end"]}'
        try:
            # 候補を出した後に本文が変わっている場合は当てにしない
            if self.editor.get(start, end) != tgt.get('text', ''):
                return None
        except Exception:
            return None
        return start, end

    def _wrap_with_parens(self):
        """
        （）ボタン。選択範囲に全角文字が1つでもあれば全角の（）、
        全角が無ければ半角の () で括る。選択が無ければ全角の（）を
        カーソル位置に差し込む（日本語のメモが基本のため）。

        F2 で語を選んでいるときは、その語の中身で判断する。
        """
        text = ''
        f2_range = self._f2_bracket_range()
        if f2_range is not None:
            try:
                text = self.editor.get(*f2_range)
            except Exception:
                text = ''
            if text and not has_fullwidth(text):
                self._wrap_with_brackets('(', ')')
            else:
                self._wrap_with_brackets('（', '）')
            return
        try:
            sel = self.editor.tag_ranges('sel')
            if sel:
                text = self.editor.get(str(sel[0]), str(sel[1]))
        except Exception:
            text = ''
        if text and not has_fullwidth(text):
            self._wrap_with_brackets('(', ')')
        else:
            self._wrap_with_brackets('（', '）')

    def toggle_pick_mode(self):
        """
        F1（またはメニュー）でモードを切り替える。

        既にモード中なら中断する。'equals' 経由で入っていた場合、
        F1 での中断も Esc と同じ「中断」の扱いなので、
        打ってある「=」は残す（消すのは語を拾えたときだけ）。
        """
        if getattr(self, '_pick_mode', None):
            self._end_pick_mode(keep_equals=True)
        else:
            self._start_pick_mode(via_equals=False)

    def _on_equal_key(self, event=None):
        """
        メモ欄で「=」が押された。

        既にモード中に「=」が押された場合は、モードを解除して
        通常どおり「=」を打たせる（記号として使いたい場合の逃げ道）。
        そうでなければ、まず「=」を文字として入力してからモードに入る。

        **押されたキーが本当に「=」かを必ず確かめる。**
        IMEの確定操作の最中は、tkinter に届くキーイベントが
        実際に入力される文字と食い違うことがある。この関数は
        `insert` で文字を書き足したうえで 'break' を返し、本来の
        キー入力を止めてしまうため、取り違えると
        「打ったはずの文字が入らない」「入れた文字が消える」
        という壊れ方をする（実機で半角の「.」が消えると
        報告された。全角で確定した場合や無変換では起きない、
        という条件もIME確定経路の取り違えと符合する）。
        event から文字を確かめられない場合は、何もせず素通しする。
        """
        ch = getattr(event, 'char', None) if event is not None else None
        if ch is not None and ch not in ('=', '＝'):
            # 「=」以外の文字が入ろうとしている。触らずに素通しする。
            return None

        if getattr(self, '_pick_mode', None):
            self._end_pick_mode(keep_equals=True)
            return None    # このキー入力は素通しにして「=」を打たせる

        # 打つ「=」の全角・半角は、直前の文字に合わせる。
        # 全角で書いている最中に半角の = が混ざると不自然なため。
        mark = '='
        try:
            prev = self.editor.get('insert-1c', 'insert')
            if prev and ord(prev) > 0x7f and not prev.isspace():
                mark = '＝'
        except Exception:
            pass
        try:
            self.editor.insert('insert', mark)
        except Exception:
            return 'break'
        # 打った「=」の前後にマークを置く。
        # gravity を 'left'/'right' にして、直後にモード中の他の
        # 編集があってもこの「=」自身の位置に食い込まれないようにする。
        try:
            self.editor.mark_set(self._PICK_EQUALS_START,
                                 f'insert-{len(mark)}c')
            self.editor.mark_gravity(self._PICK_EQUALS_START, 'left')
            self.editor.mark_set(self._PICK_EQUALS_END, 'insert')
            self.editor.mark_gravity(self._PICK_EQUALS_END, 'right')
        except Exception:
            pass
        self._start_pick_mode(via_equals=True)
        return 'break'

    def _start_pick_mode(self, via_equals, target='editor'):
        # 差し込み先は、モードに入った時点のカーソル位置を覚えておく。
        # 補正欄をクリックすると編集欄の焦点が外れるため、
        # クリック後に位置を取りに行っても手遅れになる。
        # マークにしておくことで、拾うまでの間に他の編集があっても
        # 位置がずれない。
        #
        # target: 差し込み先。'editor'（本体メモ欄・既定）または
        #   'quick'（簡易入力ウィンドウ）。マーク自体は差し込み先の
        #   ウィジェットに置く必要がある（ウィジェットをまたいで
        #   マークは共有できないため）。
        self._pick_target = target
        dest = self._quick_text if target == 'quick' else self.editor
        # 範囲を選んだままモードに入ったら、その範囲を控えておき、
        # 引用できたときに消す（＝拾った語で置き換わる。うにさんの
        # 指定・2026-08-10）。位置は文字列ではなくマークで覚える。
        # 拾うまでの間に他の編集があっても、マークなら位置がずれない。
        # 拾わずに抜けた場合は消さない（_pick_insert でだけ消す）。
        #
        # 「=」経由のときは対象にしない。「=」を打った時点で、
        # tkinter の標準動作が選択範囲を置き換えて消しているため
        # （残っていたとしても、差し込み先は「=」の位置であって
        # 選択範囲ではない）。
        self._pick_had_selection = False
        try:
            sel = None if via_equals else dest.tag_ranges('sel')
        except Exception:
            sel = None
        if sel:
            try:
                dest.mark_set(self._PICK_SEL_START, str(sel[0]))
                dest.mark_gravity(self._PICK_SEL_START, 'left')
                dest.mark_set(self._PICK_SEL_END, str(sel[1]))
                dest.mark_gravity(self._PICK_SEL_END, 'left')
                self._pick_had_selection = True
            except Exception:
                self._pick_had_selection = False
        try:
            # 選択があったときは、その **末尾** に差し込む。
            # 差し込んでから選択範囲を消すので、結果として
            # 選んでいた文字が拾った語に置き換わる。
            dest.mark_set(self._PICK_MARK,
                          self._PICK_SEL_END if self._pick_had_selection
                          else 'insert')
            dest.mark_gravity(self._PICK_MARK, 'left')
        except Exception:
            pass
        self._pick_mode = 'equals' if via_equals else 'f1'
        self._close_dropdown()
        # 拾える欄すべてでカーソルの形を変えて、モード中だと分かるようにする
        # （簡易入力欄も拾えるので含める・2026-08-09）
        for w in (self.result_view, self.editor,
                  getattr(self, '_quick_text', None)):
            # 形を変える道は1か所に通す（`_set_pane_cursor`・学び22）
            self._set_pane_cursor(w, 'plus')
        hint = ('語を拾う　'
               '【引用モード】アプリ内の入力済みの単語をクリックで'
               '引用します。範囲選択でも引用できます。'
               '続けてキーを打つと引用を中断します')
        if via_equals:
            hint += '（何も拾わずに書き続けると「=」が残ります）'
        # 統合レイアウトでは補正欄の見出しが見えないので、
        # メモ欄側の見出しに出す
        header = (self.editor_header if self._layout_is_unified()
                  else self.result_header)
        self._pick_header = header
        header.config(text=hint, fg=ACCENT)
        # 見出しは常に1行のまま（折り返さず、長ければ右で見切れる）。
        # 以前は拾うモード中だけ2行に広げていたが、
        # 「2行にせず右に見切れるように」という指定に合わせてやめた。
        self.status.config(text='語を拾うモードです')
        try:
            self.pick_mode_btn.config(relief='sunken', fg=ACCENT)
        except Exception:
            pass
        # 簡易入力の窓が開いているなら、窓のタイトルでも分かるようにする
        try:
            if getattr(self, '_quick_win', None) is not None:
                self._quick_win.title('簡易入力【引用モード】'
                                      '語をクリックで引用')
        except Exception:
            pass

        # 「=」経由のときは、メモ欄の次のキー入力を監視する。
        # モード中に別の文字を打ったら、それは「記号の=を打ちたかった
        # だけで、拾う気は無かった」ということなので、モードだけ
        # 中断して「=」は残す。
        #
        # 監視の bind/unbind は、モードに出入りするたびに繰り返すと
        # tkinter の unbind が確実に効かない場合があり
        # （funcid を渡していても、実装によっては該当シーケンスの
        #  ハンドラが残り続けることがある）、モードを抜けたはずなのに
        # また別のモードが始まる、という不具合になっていた
        # （実機で「Escで解除しても再度実行される」と報告された）。
        # 対策として、監視バインド自体は起動時に一度だけ張り、
        # 実際に動くかどうかは _pick_mode の値だけで判断する。

    def _pick_lines(self, widget, first_line, last_line):
        """
        引用モード中に行番号をクリック／ドラッグしたときの引用。

        選んだ行の範囲をまるごと引用する
        （実機からの要望）。モードでなければ何もしない
        （通常の行選択がそのまま残る）。
        """
        if not getattr(self, '_pick_mode', None):
            return
        try:
            text = widget.get(f'{first_line}.0', f'{last_line}.end')
        except Exception:
            return
        if not text.strip():
            return
        try:
            widget.tag_remove('sel', '1.0', 'end')
        except Exception:
            pass
        self._pick_insert(text)

    def _on_global_escape(self, event=None):
        """
        どこで Esc が押されても最後に受け取る受け皿。

        優先順位は次のとおり。上のものが処理したらそこで終わる。
          1. 引用モード中 … その解除（_on_pick_mode_keypress が処理）
          2. 候補一覧が開いている … それを閉じる
          3. 簡易入力の窓が開いている … それを閉じる

        3 が要点で、簡易入力を開いたまま本体をアクティブにした場合、
        簡易入力側の Esc 束縛には届かない。本体側で受けて閉じる。
        """
        if getattr(self, '_pick_mode', None):
            return None      # 引用モードの解除が先（そちらが処理する）
        if getattr(self, '_dropdown', None) is not None:
            self._close_dropdown()
            return 'break'
        if getattr(self, '_quick_win', None) is not None:
            self._close_quick_capture()
            return 'break'
        return None

    def _on_pick_mode_keypress(self, event):
        """
        メモ欄でのキー入力を監視し、「=」経由のモードを
        意図せず終わらせずに済ませる。

        このバインドはアプリ起動時に一度だけ張られ、以後ずっと
        メモ欄のあらゆるキー入力で呼ばれる。実際に何かするのは
        「=」経由でモード中のときだけ（_pick_mode == 'equals'）。
        毎回 bind/unbind を繰り返さないのは、tkinter の unbind が
        funcid を渡しても該当シーケンスの他のハンドラまで巻き添えに
        することがあり、意図せずモードが残ったり、逆に無関係な
        タイミングでモードが再現したりする不具合の元になっていた
        ため（実機で「Escで解除しても再度実行される」と報告された）。

        Esc は**どのモード（f1 / equals）でも**ここで解除する。
        以前は Esc を別に `<Key-Escape>` として束縛していたが、
        同じウィジェットの `<KeyPress>`（add=True）と実行順序が
        保証されず、押しても解除されないことがあった
        （実機で「引用モードでエスケープを押しても解除されない」と
          報告された）。キー処理の入口をこの1箇所に集約する。

        修飾キー単体（Shift/Ctrl/Alt等）は文字の入力ではないので無視。
        それ以外のキーが押されたら、'equals' モードのときだけ
        「拾う気が無くなった」とみなして中断し、
        既に打ってある「=」はそのまま残す。
        """
        if not self._pick_mode:
            return None
        keysym = getattr(event, 'keysym', '')

        if keysym == 'Escape':
            # どのモードでも、Esc は必ず解除。
            # 'break' を返して、Esc が他の処理へ流れないようにする。
            self._end_pick_mode(keep_equals=True)
            return 'break'
        if keysym in ('F1', 'F2', 'Shift_L', 'Shift_R',
                     'Control_L', 'Control_R', 'Alt_L', 'Alt_R',
                     'equal') \
                and ime_confirmed_char_event(event) is None:
            # **IME が確定した `p` `q`** は keysym が F1 / F2 に
            # 化けるので、それは「文字を打った」として扱う
            # （項目48-EH。引用モードを中断させる側が正しい）。
            # F1 はモードの開始・終了そのものの操作。
            # F2 は候補一覧を出す操作で、文字の入力ではない。
            # 修飾キー単体は文字の入力ではない。
            # equal（=）は _on_equal_key が専用に処理するので、
            # ここで重ねて中断させない。
            return None

        # ここから先は「文字が打たれた」場合。
        # 'equals' で入っていたときだけ、打った「=」を残して中断する。
        # 'f1' のときは文字を打っても中断しない
        # （F1で入った場合は「=」を打っていないので、
        #   途中で書き足しても引用の意思は残っているとみなす）。
        if self._pick_mode == 'equals':
            self._end_pick_mode(keep_equals=True)
        return None    # このキー入力自体は素通しする

    def _on_ime_ascii_key(self, event):
        """
        IME が確定した文字が編集キーとして届いた場合に、文字として入れる。

        「る」のキーを F9/F10（環境により F8）で半角に確定すると、
        tkinter には keysym=Delete・char='.' として届き、Tk 標準の
        Delete の動き（カーソル位置の1文字を削除）が実行される。
        打った文字は入らず、行末なら改行が消えて下の行が上に詰まる
        （実機で報告された症状。keylog.py の記録で確定した）。

        文字を伴っているかどうかで、本物の編集キーと見分けられる。
        本物の Delete / 矢印キーは印字できる文字を伴わないので、
        その場合は何もせず Tk の標準の動きに任せる。

        簡易入力ウィンドウの入力欄からも同じ束縛で呼ばれるため、
        書き込む先は event.widget から取る。
        """
        keysym = getattr(event, 'keysym', '')
        # 簡易入力欄での F1（引用モード）。'<F1>' の個別束縛が
        # 実機で効かなかったため、全ての KeyPress を受けるこの経路
        # （IME対処で動作実績がある）で受ける（2026-08-09）。
        # keycode 112 は VK_F1（keysym が環境で違う場合の保険）。
        #
        # **その keycode 112 こそが `p` の番号だった**（項目48-EH・
        # 2026-08-17）。ｐ を半角に確定すると、この保険が
        # そのまま引用モードを開いていた。文字を伴っていたら
        # 機能キーではないので、下の「文字として入れる」へ落とす。
        if (keysym == 'F1' or getattr(event, 'keycode', 0) == 112) \
                and ime_confirmed_char_event(event) is None:
            qt = getattr(self, '_quick_text', None)
            if qt is not None and getattr(event, 'widget', None) is qt:
                return self._on_quick_f1(event)
        ch = ime_confirmed_char(keysym, getattr(event, 'char', ''))
        if ch is None:
            # **テンキーの小数点**（項目48-FY）。文字を伴わずに
            # `keysym=Delete` で届くと、上の見分けを素通りして
            # Tk 標準の「1文字消す」が走ってしまう。
            # キーの番号（VK_DECIMAL=110）で見分ける。
            ch = numpad_decimal_char(event)
        if ch is None:
            return None
        widget = getattr(event, 'widget', None) or self.editor
        try:
            # 選択範囲があれば、通常の文字入力と同じく置き換える
            if widget.tag_ranges('sel'):
                widget.delete('sel.first', 'sel.last')
        except Exception:
            # `tk.Entry` には tag_ranges が無い（項目48-FY で
            # 検索欄・置換欄にも張ったので、そちらの形も見る）
            try:
                if widget.selection_present():
                    widget.delete('sel.first', 'sel.last')
            except Exception:
                pass
        try:
            widget.insert('insert', ch)
        except Exception:
            return None     # 書けなかったときは標準の動きに委ねる
        return 'break'

    def _on_quick_f1(self, event=None):
        """
        簡易入力ウィンドウで F1。引用モードに入る。

        本体の F1 と同じモードだが、拾った語の差し込み先は
        簡易入力のカーソル位置（target='quick'。「=」で入る経路と
        同じ仕組みを使う）。モード中にもう一度押せば中断する。
        """
        # IME が確定した `p`（keysym が F1 に化けたもの）は文字。
        # 窓への束縛から来た場合は、欄に文字を入れてやる（項目48-EH）。
        got = self._ime_fkey_insert(event) if event is not None else None
        if got is not None:
            return got
        if getattr(self, '_pick_mode', None):
            self._end_pick_mode(keep_equals=True)
        else:
            self._start_pick_mode(via_equals=False, target='quick')
        return 'break'

    def _on_quick_f2_widget(self, event=None):
        """簡易入力欄への `<F2>` 束縛（項目48-EH の入口）。"""
        got = self._ime_fkey_insert(event)
        if got is not None:
            return got
        return self._on_quick_f2(event)

    def _editor_line_height(self):
        h = getattr(self, '_editor_line_h', None)
        if h:
            return h
        try:
            import tkinter.font as tkfont
            f = tkfont.Font(font=self.editor.cget('font'))
            h = max(1, f.metrics('linespace'))
        except Exception:
            h = 20
        self._editor_line_h = h
        return h

    def _on_editor_blank_press(self, event):
        """
        本文より下の余白でボタンが押された。ここからのドラッグは
        範囲選択ではなくスクロールとして扱う（タッチ操作の
        「指で送る」に相当）。本文の上では何もしない。
        """
        self._blank_drag = None
        if getattr(self, '_pick_mode', None):
            return None
        # タッチ（指）なら、本文の上でも余白でもドラッグをスクロールに
        # する（うにさん指定・2026-08-09。タップだけなら通常どおり
        # カーソル移動になる）。マウスのときは、本文より下の余白から
        # 始めたドラッグだけをスクロールにする。
        # **マウスの左ドラッグは、どこから始めても選択に専念させる**
        # （項目48-IM・うにさんの報告「文末よりも下だと、左クリックの
        # ドラッグがスクロールになっていた」）。
        #
        # 束縛のところには既に「左ボタンは範囲選択に専念させる。
        # スクロールは右ドラッグに移す」と書いてあったのに、
        # **この道だけが左ドラッグを横取りしていた**——
        # 学び22「片方だけに置くと、そちらを迂回して素通りする」。
        #
        # 指（タッチ）は別。1本指でなぞってスクロールするのは
        # うにさんの指定（2026-08-09）なので、そのまま残す。
        if not is_touch_pointer():
            return None
        try:
            frac = self.editor.yview()[0]
        except Exception:
            return None
        self._blank_drag = {'y': event.y_root, 'frac': frac,
                            'moved': False}
        return None

    def _on_editor_blank_drag(self, event):
        bd = getattr(self, '_blank_drag', None)
        if not bd:
            return None
        dy = event.y_root - bd['y']
        if abs(dy) > 4:
            bd['moved'] = True
        if not bd['moved']:
            return None
        try:
            total = self.editor.count('1.0', 'end', 'displaylines')
            if isinstance(total, tuple):
                total = total[0]
            total = max(1, int(total or 1))
            frac = bd['frac'] - dy / float(total *
                                           self._editor_line_height())
            self.editor.yview_moveto(max(0.0, min(1.0, frac)))
        except Exception:
            return None
        return 'break'

    def _on_editor_blank_release(self, event):
        self._blank_drag = None
        return None

    def _on_quick_f2(self, event=None):
        """
        簡易入力欄で F2。カーソル位置（無ければ直前）の語の候補を
        出し、候補一覧が開いたまま押すたびに左の語へ遡る
        （本体の F2 と同じ操作・2026-08-09）。
        """
        tw = getattr(self, '_quick_text', None)
        if tw is None:
            return 'break'
        # **候補が無い語で止まっても遡りは続ける**（項目48-GM。
        # 本体の F2 と同じ話。上の `_on_f2_candidates` を見ること）。
        if (getattr(self, '_f2q_cycle', None)
                and getattr(self, '_dropdown_owner', None) == 'quick'
                and (self._dropdown is not None
                     or getattr(self, '_f2_focus_target', None) is not None)):
            return self._quick_f2_step_back()

        # 解析は打鍵の 250ms 後にまとめて走らせている。引用（F1）で
        # 差し込んだ直後など、**まだ解析が済んでいないうちに F2 を
        # 押すと、単位が古いまま**で、差し込んだ語が無いものとして
        # 扱われる（実機で「引用文がスルーされます」と報告・
        # 2026-08-09）。予約が残っていれば、ここで先に済ませる。
        # 予約の有無だけでなく、**いま欄にある文字と、単位を作った
        # ときの文字が違う**なら作り直す（差し込みの経路によっては
        # 予約自体が入らないため）。
        try:
            now_text = tw.get('1.0', 'end-1c')
        except Exception:
            now_text = None
        if (getattr(self, '_quick_after_id', None)
                or (now_text is not None
                    and now_text != getattr(self, '_quick_units_text',
                                            None))):
            if getattr(self, '_quick_after_id', None):
                try:
                    self.root.after_cancel(self._quick_after_id)
                except Exception:
                    pass
                self._quick_after_id = None
            try:
                self._analyze_quick()
            except Exception:
                pass
        try:
            pos = tw.index('insert')
            r, c = pos.split('.')
            row, col = int(r), int(c)
        except Exception:
            return 'break'
        i = row - 1
        units = (self._quick_units[i]
                 if 0 <= i < len(self._quick_units) else [])
        if not units:
            return 'break'
        unit = unit_at(units, col)
        if unit is None and col > 0:
            unit = unit_at(units, col - 1)
        idx = None
        if unit is not None:
            for k, u in enumerate(units):
                if u is unit:
                    idx = k
                    break
        if unit is None or (not _f2_word_re.search(unit.get('text', ''))
                            and not unit.get('detail')
                            and not is_symbol_word(unit.get('text', ''))):
            start_k = idx if idx is not None else len(units)
            unit = None
            for k in range(start_k - 1, -1, -1):
                if (_f2_word_re.search(units[k].get('text', ''))
                        or units[k].get('detail')):
                    unit = units[k]
                    idx = k
                    break
        if unit is None or idx is None:
            return 'break'
        self._f2q_cycle = {'row': row, 'idx': idx}
        self._show_quick_unit_candidates(row, unit)
        # **候補の出ない語（助詞など）では止まらない**（項目48-GN。
        # 本体の `_f2_show_or_skip` と同じ話）。
        if self._dropdown is None and unit.get('kind') != 'range':
            return self._quick_f2_move(-1)
        return 'break'

    def _quick_f2_step_back(self):
        """簡易入力の F2 連打。1つ左の語へ。"""
        return self._quick_f2_move(-1)

    def _quick_f2_move(self, delta):
        """
        簡易入力で、F2 の対象を前後に移す（本体の _f2_move と同じ）。

        delta = -1 で左（前）、+1 で右（次）。行の端まで来たら
        隣の行へ続けてたどる（空行は飛ばす）。

        **候補の出ない語では止まらない**（項目48-GN）。見つから
        なければ元の語へ戻す。本体の `_f2_move` と同じ考え方。
        """
        cyc = getattr(self, '_f2q_cycle', None)
        if not cyc:
            return 'break'
        home = (cyc['row'], cyc['idx'])
        ended = False
        for _ in range(self.F2_SKIP_MAX):
            nxt = self._quick_f2_next_stop(cyc['row'], cyc['idx'], delta)
            if nxt is None:
                ended = True
                break
            row, idx = nxt
            cyc['row'], cyc['idx'] = row, idx
            self._show_quick_unit_candidates(row, self._quick_units[row - 1][idx])
            if self._dropdown is not None:
                return 'break'

        cyc['row'], cyc['idx'] = home
        try:
            units = self._quick_units[home[0] - 1]
            if 0 <= home[1] < len(units):
                self._show_quick_unit_candidates(home[0], units[home[1]])
        except Exception:
            pass
        try:
            self.status.config(
                text=(('最後の語まで来ました' if delta > 0
                       else '最初の語まで遡りました') if ended
                      else '候補の出る語が見つかりませんでした'))
        except Exception:
            pass
        return 'break'

    def _quick_f2_next_stop(self, row, idx, delta):
        """簡易入力で、次に止まれる語の位置。端まで来たら None。"""
        total = len(self._quick_units)
        i = row - 1
        if not (0 <= i < total):
            return None
        units = self._quick_units[i]
        idx = idx + delta

        for _ in range(total + 1):
            while 0 <= idx < len(units) and not (
                    _f2_word_re.search(units[idx].get('text', ''))
                    or units[idx].get('detail')
                    or is_symbol_word(units[idx].get('text', ''))):
                idx += delta
            if 0 <= idx < len(units):
                return row, idx
            next_row = row + (1 if delta > 0 else -1)
            j = next_row - 1
            if not (0 <= j < total):
                return None
            row, units = next_row, self._quick_units[j]
            idx = 0 if delta > 0 else len(units) - 1
            if not units:
                idx = 0 if delta > 0 else -1
        return None

    def _show_quick_unit_candidates(self, row, unit):
        """簡易入力欄の対象の語に色を付けてから候補一覧を開く。"""
        tw = self._quick_text
        ev = _FakeEvent()
        ev.widget = tw
        ev.x = ev.y = 0
        try:
            box = tw.bbox(f'{row}.{unit["start"]}')
            if box:
                ev.x, ev.y = box[0], box[1] + box[3]
        except Exception:
            pass
        try:
            ev.x_root = tw.winfo_rootx() + ev.x
            ev.y_root = tw.winfo_rooty() + ev.y
        except Exception:
            ev.x_root = ev.y_root = 0
        self._close_dropdown()
        self._open_quick_dropdown(ev, row, unit)
        self._dropdown_owner = 'quick'
        try:
            bg = ('#7a5a2b' if self.settings.get('dark_mode')
                  else '#ffd9a0')
            tw.tag_configure('f2_focus', background=bg)
            tw.tag_add('f2_focus',
                       f'{row}.{unit["start"]}', f'{row}.{unit["end"]}')
            tw.tag_raise('f2_focus')
        except Exception:
            pass
        # **本体と同じ記憶を持たせる**（うにさんの指定・2026-08-11・C-5）。
        #
        # うにさんの報告:「簡易入力だと、F2で単語を選択した後、
        # 余白をクリックしても色が残ったままになる」。
        # 原因は、簡易入力だけ `_f2_focus_target` を置いていなかった
        # こと。色を消す `_clear_f2_on_click` は
        # 「記憶があるときだけ」働くので、記憶が無い簡易入力では
        # 何もせず、色だけが残っていた。
        #
        # ここで置いておくと、C-1〜C-3（文字入力・Delete・
        # Shift+左右）も簡易入力で同じように効く。
        # **同じ見た目のものは、同じ記憶で動かす。**
        self._f2_focus_target = {
            'widget': tw, 'row': row,
            'start': unit['start'], 'end': unit['end'],
            'text': unit.get('text', ''),
        }

    def _on_quick_ctrl_c(self, event=None):
        """
        簡易入力欄での Ctrl+C。本体のメモ欄（_on_editor_ctrl_c）と
        同じ考え方: 選択があれば標準のコピーに任せ、選択なしなら
        引用モードに入る（差し込み先は簡易入力）。
        """
        text_widget = getattr(self, '_quick_text', None)
        if text_widget is None:
            return None
        try:
            has_sel = bool(text_widget.tag_ranges('sel'))
        except Exception:
            has_sel = False
        if has_sel:
            return None    # 標準のコピー動作に任せる
        if getattr(self, '_pick_mode', None):
            return None
        self._start_pick_mode(via_equals=False, target='quick')
        return 'break'

    def _on_quick_ctrl_z(self, event=None):
        """
        簡易入力欄での Ctrl+Z。

        自動反映で書き換わった行なら、**Tk の取り消しではなく
        `_undo_autofix` を通す**。Tk の取り消しは「文字を戻す」
        だけなので、250ms 後の解析でまた同じ補正が走って
        戻ってしまう（打鍵のたびに `_quick_autofix_rounds` が
        0 に戻るので、暴走止めも噛まない）。`_undo_autofix` は
        戻すと同時に**台帳へ「この補正は不要」を書く**ので、
        次の解析でも直らない。

        控えの無い行では何もしない（Tk のふつうの取り消しへ
        素通し）。戻す場所は、カーソルのある所に重なる控え、
        無ければその行の**最後に直した所**。
        """
        qt = getattr(self, '_quick_text', None)
        if qt is None:
            return None
        try:
            row, col = (int(x) for x in qt.index('insert').split('.'))
        except Exception:
            return None
        rec = self._autofix_record_for_row(row, w=qt)
        if rec is None or not rec['spans']:
            return None
        span = self.autofix_span_at(row, col, col, w=qt)
        if span is None:
            span = rec['spans'][-1]
        if not span[3]:
            return None
        # **戻すものが無ければ素通し**（`_undo_autofix` は黙って帰るので、
        # ここで 'break' を返すと Ctrl+Z が効かない欄になってしまう）。
        try:
            if qt.get(f'{row}.{span[0]}', f'{row}.{span[1]}') == span[3]:
                return None
        except Exception:
            return None
        self._undo_autofix(row, span, w=qt)
        return 'break'

    def _on_quick_pick_click(self, event):
        """
        引用モード中に簡易入力欄をクリックした。欄内の語を拾って
        差し込む（差し込み先は _pick_target が指す欄のマーク位置。
        本体の語を拾うのと同じ仕組み）。モードでなければ何もしない。
        """
        if not getattr(self, '_pick_mode', None):
            return None
        text_widget = getattr(self, '_quick_text', None)
        if text_widget is None:
            return None
        selected = ''
        try:
            sel = text_widget.tag_ranges('sel')
            if sel:
                selected = text_widget.get('sel.first', 'sel.last')
        except Exception:
            selected = ''
        unit_text = ''
        try:
            hit = self._quick_unit_under_pointer(event)
            if hit is not None:
                unit_text = hit[1].get('text', '')
        except Exception:
            unit_text = ''
        if not unit_text.strip():
            unit_text = self._quick_word_at(event)
        picked = resolve_pick_text(selected, unit_text)
        if picked:
            try:
                text_widget.tag_remove('sel', '1.0', 'end')
            except Exception:
                pass
            self._pick_insert(picked)
            return 'break'
        return None

    def _quick_word_at(self, event):
        """
        簡易入力欄のクリック位置の語（文字種の切れ目で区切る簡易版）。

        解析（build_suspect_units・250ms待ち）がまだ済んでいない
        直後でも拾えるようにするための代替。
        """
        tw = getattr(self, '_quick_text', None)
        if tw is None:
            return ''
        try:
            index = tw.index(f'@{event.x},{event.y}')
            row_s, col_s = index.split('.')
            row, col = int(row_s), int(col_s)
            line = tw.get(f'{row}.0', f'{row}.end')
        except Exception:
            return ''
        if not line:
            return ''
        col = min(col, len(line) - 1)

        def _cls(c):
            if 'ぁ' <= c <= 'ん':
                return 'h'
            if 'ァ' <= c <= 'ヶ' or c == 'ー':
                return 'k'
            if '\u4e00' <= c <= '\u9fff':
                return 'j'
            if c.isalnum():
                return 'a'
            return ''

        c0 = _cls(line[col])
        if not c0:
            return ''
        s_i = col
        while s_i > 0 and _cls(line[s_i - 1]) == c0:
            s_i -= 1
        e_i = col + 1
        while e_i < len(line) and _cls(line[e_i]) == c0:
            e_i += 1
        return line[s_i:e_i]

    @staticmethod
    def _sel_anchor_mark(widget):
        """
        Tk が Shift+クリック（範囲選択の伸長）の起点に使うマークの名前。

        Tk 8.6 では `tk::anchor<ウィジェットのパス>` という名前の
        マークだが、公式の取得手続き（::tk::TextAnchor）がある版では
        そちらに答えさせる（将来名前が変わっても追従できる）。
        """
        try:
            name = widget.tk.call('::tk::TextAnchor', widget._w)
            if name:
                return str(name)
        except Exception:
            pass
        return 'tk::anchor' + str(widget)

    def _on_shift_click_anchor(self, event):
        """
        Shift+クリックの前に、範囲選択の起点マークを合わせ直す。

        Tk の起点マークは「最後に普通のクリックをした位置」に
        置かれたまま動かない。範囲選択を Enter などで置き換えて
        選択が消えると、マークだけが置き換え前の位置（テキストが
        縮んだぶん、ずっと上）に取り残される。その状態で
        Shift+クリックすると、今のカーソル位置ではなく取り残された
        起点から選択されてしまう（実機で報告された症状）。

        - 選択が無いとき: 起点を今のカーソル位置（insert）にする。
          「カーソルからクリック位置まで」という自然な選択になる。
        - 選択があり、**起点がもう選択の端に立っている**とき:
          そのまま使う（項目48-RC・下の ★★）。
        - 選択があり、起点がどこか別の場所に取り残されているとき:
          クリックした側と反対の端を起点にする。検索などが作った
          選択（Tk の起点マークを知らない）でも伸長が働く。

        ★★ **「どちらの端が固定端か」を決めるのは、ここ1本**
        （48-GN・2026-09-05）。行番号ガターの選択は
        `_select_lines` が**選んだ範囲の先頭**へ起点を置く
        （48-RC・うにさんの指定「行の先頭に始点があるように広げる」）。
        ここが無条件に「クリックの反対側」へ書き直すと、
        **同じ操作の続きで固定端が入れ替わる**——ガターで選んだ
        直後に本文を Shift+クリックすると、Shift+矢印は先頭から、
        Shift+クリックは反対端から伸びる、という食い違いになる。
        **生きている起点が選択の端に在るなら、それを正とする。**

        ウィジェット側の束縛はクラス側より先に呼ばれるので、
        ここで直したマークをクラス側の選択処理がそのまま使う。
        None を返して標準の動きに委ねる。
        """
        w = getattr(event, 'widget', None)
        if w is None:
            return None
        try:
            mark = self._sel_anchor_mark(w)
            rng = w.tag_ranges('sel')
            if rng:
                start, end = rng[0], rng[1]
                # **もう端に立っている起点は動かさない**（48-RC）
                alive = None
                try:
                    alive = w.index(mark)
                except Exception:
                    alive = None
                if alive is not None and (
                        w.compare(alive, '==', str(start))
                        or w.compare(alive, '==', str(end))):
                    return None
                click = w.index(f'@{event.x},{event.y}')
                anchor = end if w.compare(click, '<', str(start)) else start
                w.mark_set(mark, anchor)
            else:
                w.mark_set(mark, 'insert')
        except Exception:
            pass
        return None

    def _end_pick_mode(self, keep_equals=True):
        """
        モードを抜ける。

        keep_equals: 「=」経由で入っていた場合に、打った「=」を
            残すか消すか。拾えずに終える（Esc・他のキー・拾う先が
            無かった）場合は残す（True）。
            語を拾えた場合は、_pick_insert が既に「=」を消してから
            呼ぶため、ここでは常に True（＝もう何もしない）を渡す。
        """
        was_equals = (self._pick_mode == 'equals')
        self._pick_mode = None
        target = getattr(self, '_pick_target', 'editor')
        dest = (self._quick_text if target == 'quick'
               and getattr(self, '_quick_text', None) is not None
               else self.editor)

        # 「=」を残したままモードを抜ける場合、その「=」の位置を
        # 控えておく。
        #
        # 後追いで「＝」を拾う仕組み（_maybe_start_pick_from_equals）は
        # 「カーソルの直前が＝なら引用モードに入る」という判定なので、
        # Esc で抜けても＝が残っている限り、次の入力のたびに
        # 何度でもモードに入り直してしまう
        # （実機で「エスケープキーを押しても、再度引用モードに
        #   なります」と報告された）。
        # 抜けた時点の位置を控え、そこでは入り直さないようにする。
        if was_equals and keep_equals:
            try:
                pos = dest.index(self._PICK_EQUALS_END)
            except Exception:
                try:
                    pos = dest.index('insert')
                except Exception:
                    pos = None
            if pos is not None:
                if target == 'quick':
                    self._quick_last_equals_pos = pos
                else:
                    self._last_equals_pos = pos
        if was_equals and not keep_equals:
            try:
                dest.delete(self._PICK_EQUALS_START,
                           self._PICK_EQUALS_END)
            except Exception:
                pass
        for mark in (self._PICK_MARK, self._PICK_EQUALS_START,
                    self._PICK_EQUALS_END,
                    self._PICK_SEL_START, self._PICK_SEL_END):
            try:
                dest.mark_unset(mark)
            except Exception:
                pass
        self._pick_had_selection = False
        self._pick_target = 'editor'
        # **分割レイアウトで引用モード中だけ出していた印を消す**
        # （項目48-FW）。統合レイアウトでは次の Motion が塗り直すが、
        # 分割ではもう `_on_editor_motion` が働かないので、
        # モードを抜けた時点の色がそのまま残ってしまう。
        if not self._layout_is_unified():
            try:
                self.editor.tag_remove('hover', '1.0', 'end')
            except Exception:
                pass
        for w in (self.result_view, self.editor):
            # 形を変える道は1か所に通す（`_set_pane_cursor`・学び22）
            self._set_pane_cursor(
                w, 'arrow' if w is self.result_view else 'xterm')
        try:
            qtext = getattr(self, '_quick_text', None)
            if qtext is not None:
                self._set_pane_cursor(qtext, 'xterm')
            if getattr(self, '_quick_win', None) is not None:
                self._quick_win.title('簡易入力')
        except Exception:
            pass
        # モード中に書き換えた見出しを元に戻す。
        # レイアウトによって書き換えた先が違うので、両方戻す。
        try:
            self.result_header.config(text=self.RESULT_HEADER_TEXT, fg=MUTED)
        except Exception:
            pass
        try:
            self.editor_header.config(
                text=(self.UNIFIED_HEADER_TEXT if self._layout_is_unified()
                      else self.EDITOR_HEADER_TEXT), fg=MUTED)
        except Exception:
            pass
        self._pick_header = None
        # モード終了直後、今のスクロール位置に応じて見出しの
        # 表示・非表示を改めて評価する。上でモード中の案内文を
        # 本文に戻したが、そのときスクロール位置が先頭でなければ
        # 本来は隠れているべきなので、ここで揃え直す。
        try:
            self._update_header_visibility(self.editor.yview()[0])
        except Exception:
            pass
        try:
            self.pick_mode_btn.config(relief='flat', fg=INK)
        except Exception:
            pass
        # ステータス欄も、モード中の表示のまま残さない。
        # 見出しは戻しても状態欄が「語を拾うモードです」のままだと、
        # 実際の状態と表示が食い違って見える（実機で報告された）。
        try:
            if self.status.cget('text') == '語を拾うモードです':
                self.status.config(text='')
        except Exception:
            pass
        return 'break'

    def _pick_insert(self, text):
        """
        拾った語を差し込み、モードを終える。

        「=」経由のモードだった場合は、先に打ってあった「=」を
        消してから拾った文字を入れる（残したままだと「=文字」の
        ように並んでしまうため）。

        差し込み先は通常メモ欄（self.editor）だが、簡易入力ウィンドウ
        側から「＝」で入ったモード（_pick_target == 'quick'）のときは
        簡易入力欄に差し込む。差し込み先を切り替えても、拾う操作
        （メモ欄・補正欄のクリック／ドラッグ）自体は変わらない。
        """
        if not text:
            self._end_pick_mode(keep_equals=True)
            return
        was_equals = (self._pick_mode == 'equals')
        target_widget = self.editor
        if getattr(self, '_pick_target', None) == 'quick':
            qtext = getattr(self, '_quick_text', None)
            if qtext is not None:
                target_widget = qtext
        try:
            if was_equals:
                target_widget.delete(self._PICK_EQUALS_START,
                                     self._PICK_EQUALS_END)
                target = self._PICK_EQUALS_START
            else:
                target = self._PICK_MARK
            target_widget.insert(target, text)
            # 差し込んだ直後に続けて書けるよう、末尾へカーソルを移す
            new_pos = f'{target}+{len(text)}c'
            target_widget.mark_set('insert', new_pos)
            # 範囲を選んだままモードに入っていたなら、その範囲を消す。
            # 差し込みは範囲の末尾に行っているので、消した結果
            # 「選んでいた文字が拾った語に置き換わる」形になる
            # （うにさんの指定・2026-08-10）。
            # カーソル（insert）はマークなので、前を削っても
            # 差し込んだ語の末尾に付いてくる。
            if getattr(self, '_pick_had_selection', False):
                try:
                    target_widget.delete(self._PICK_SEL_START,
                                         self._PICK_SEL_END)
                except Exception:
                    pass
                try:
                    target_widget.tag_remove('sel', '1.0', 'end')
                except Exception:
                    pass
            target_widget.focus_set()
        except Exception:
            pass
        self._pick_had_selection = False
        # ここでは「=」は既に消してあるので、_end_pick_mode 側で
        # もう一度削除させない。was_equals のまま keep_equals=False を
        # 渡すと、いま挿入したばかりの文字列（マークがgravityで
        # その前後に移動している）まで巻き添えで消えてしまう。
        self._pick_mode = None
        self._end_pick_mode(keep_equals=True)
        self.status.config(text=f'「{text}」を差し込みました')
        self._on_change()

    def _set_pane_cursor(self, widget, shape):
        """
        欄のカーソルの形を変える**唯一の場所**（2026-08-28・
        うにさんの報告）。

        > 「右クリックドラッグスクロールは、**分割モードの入力欄なら
        >   問題ない**のですが、**補正欄で実行すると端でカーソルの
        >   表示が元に戻ります**。**補正欄はそもそもカーソルの形が
        >   違うので対応漏れかと**」

        **見立てのとおりだった。** 補正欄だけは語の上で形が変わる
        （`hand2`／`arrow`）ので、`<Motion>` と `<Leave>` という
        **カーソルを書き換える道を2本持っている**。メモ欄には
        その道が無いので、メモ欄では起きなかった。

        端まで行くと `_edge_warp` がカーソルを欄の中ほどへ戻す。
        その出入りで **`<Leave>` が飛び、`arrow` に戻していた**——
        `_scroll_cursor_hide` が隠したものを、**別の道が見せ直して
        いた**（**学び22**——片方だけに置くと、そちらを迂回する。
        報告②で「隠す」を全部の欄に掛けたが、**書き換える側**は
        塞いでいなかった）。

        **掴んでいる間は、どんな理由でも形を変えない。**
        形を変える道は全部ここを通す——いまは4本
        （`<Motion>`・`<Leave>`・語を拾うモードの入り口と出口）。
        **新しい道を作ったら、ここを通すこと**（隠す側は
        `_scroll_cursor_hide`／`_scroll_cursor_restore` が持ち場）。
        """
        if widget is None:
            return
        if getattr(self, '_scroll_cursor', None) is not None:
            return      # スクロールの掴み中は隠したまま
        try:
            widget.config(cursor=shape)
        except Exception:
            pass

    def _on_result_motion(self, event):
        hit = self._unit_under_pointer(event)
        self.result_view.tag_remove('hover', '1.0', 'end')
        if hit is None:
            self._set_pane_cursor(self.result_view, 'arrow')
            return
        row, unit = hit
        self._set_pane_cursor(self.result_view, 'hand2')
        self.result_view.tag_add('hover',
                                 f'{row}.{unit["start"]}',
                                 f'{row}.{unit["end"]}')

    def _on_result_leave(self, event=None):
        self.result_view.tag_remove('hover', '1.0', 'end')
        self._set_pane_cursor(self.result_view, 'arrow')

    def _unit_under_pointer(self, event):
        """マウス位置にある語の単位を返す。無ければ None。"""
        try:
            index = self.result_view.index(f'@{event.x},{event.y}')
            row_s, col_s = index.split('.')
            row, col = int(row_s), int(col_s)
        except Exception:
            return None
        i = row - 1
        if not (0 <= i < len(self.line_units)):
            return None
        unit = unit_at(self.line_units[i], col)
        if unit is None:
            return None
        # 記号・空白だけの単位は選び直しの対象にしない
        t = unit['text']
        has_word_char = any(
            ('\u3041' <= c <= '\u30f6') or ('\u4e00' <= c <= '\u9fff')
            or c.isalnum() for c in t)
        if not has_word_char:
            return None
        return row, unit

    def rebuild_dict_index(self):
        """
        辞書索引を作り直す。

        索引が空だと「同音異義語の候補が一切出ない」という
        分かりにくい症状になる（実機で「平仮名」「実装」が
        候補に出ない問題が報告された）。
        作り直しと状態の確認をここから行えるようにする。
        """
        from dict_index import DictIndex, HAS_JANOME
        if not HAS_JANOME:
            messagebox.showwarning(
                '索引を作り直す',
                'janome が見つからないため、辞書索引を作れません。\n'
                '同音異義語の候補は、覚えた語彙の範囲だけになります。')
            return

        # 古いキャッシュを消してから作り直す
        try:
            if os.path.exists(DICT_INDEX_FILE):
                os.remove(DICT_INDEX_FILE)
        except Exception:
            pass

        self.status.config(text='辞書索引を作成しています…（数秒かかります）')
        self.root.update_idletasks()
        self.dict_index = DictIndex(DICT_INDEX_FILE)
        try:
            self.dict_index.ensure_built()
        except Exception as e:
            messagebox.showerror('索引を作り直す',
                                 f'索引の作成に失敗しました:\n{e}')
            self._update_status()
            return

        st = self.dict_index.stats()
        if st['readings'] < 5000:
            messagebox.showwarning(
                '索引を作り直す',
                f'索引が十分に作れませんでした。\n\n'
                f'読み: {st["readings"]:,} 件 / 表記: {st["surfaces"]:,} 件\n\n'
                'diagnose_index.py を実行して、その出力を確認してください。')
        else:
            messagebox.showinfo(
                '索引を作り直す',
                f'辞書索引を作成しました。\n\n'
                f'読み: {st["readings"]:,} 件 / 表記: {st["surfaces"]:,} 件')
        self._update_status()

    def _copy_text(self, text):
        """指定した文字列をクリップボードへ入れる。"""
        if not text:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.status.config(text=f'「{text}」をコピーしました')

    def _copy_selection(self, event=None):
        """補正欄で選択した範囲をクリップボードへコピーする。"""
        # 補正欄には Ctrl+Insert の束縛が先にあり、ここで 'break' を
        # 返すため bind_all（簡易入力のホットキーの受け皿）まで
        # 届かない。補正欄に焦点があるときもお知らせが出るよう、
        # ここから直接呼ぶ（実機で「メッセージが出ない」と報告・
        # 2026-08-09）。
        if event is not None and getattr(
                event, 'keysym', '') in ('Insert', 'KP_Insert'):
            try:
                self._on_quick_hotkey_fallback('insert')
            except Exception:
                pass
        try:
            text = self.result_view.get('sel.first', 'sel.last')
        except Exception:
            text = ''
        if not text:
            return 'break'
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.status.config(text=f'{len(text)}文字コピーしました')
        return 'break'

    def _on_editor_ctrl_c(self, event=None):
        """
        メモ欄での Ctrl+C。

        選択範囲があれば、tkinter 標準のコピー動作に任せる
        （ここでは何もせず、イベントを素通しする）。

        何も選択していない状態での Ctrl+C は、コピーとしては
        することが無い。その場合は「引用モードを実行する」
        （実機からの指定）。アプリがアクティブで、メモ欄にカーソルが
        あるときだけ働けばよいので、フォーカスの確認はメモ欄自身への
        束縛だけで自然に満たされる（他の欄にいるときはこの束縛自体が
        呼ばれない）。

        既に引用モード中であれば、二重に開始させず何もしない
        （その場合の Ctrl+C は本当にコピーしたい操作である可能性が
        あるため、モードを乱さないほうが安全）。
        """
        try:
            has_sel = bool(self.editor.tag_ranges('sel'))
        except Exception:
            has_sel = False
        if has_sel:
            return None    # 標準のコピー動作に任せる

        if getattr(self, '_pick_mode', None):
            return None

        self.toggle_pick_mode()
        return 'break'

    def _on_editor_right_press(self, event):
        """
        右ボタンを押した。ここではまだ何もせず、
        動かされたらスクロール、動かさず離されたら候補一覧とする。
        """
        self._close_dropdown()
        self._drag_press(event, self.editor, True)
        # 押した場所を控える（項目48-TA。離しが「クリック」か「動かした」かを
        # `_drag` とは別に見分ける——左も押していると左の押し下げが `_drag` を
        # 上書きして、掴みだったことが消える）
        try:
            self._r3_press = (int(event.x_root), int(event.y_root))
        except Exception:
            self._r3_press = None
        return 'break'

    def _on_editor_right_motion(self, event):
        """右ドラッグでスクロールする（タッチの1本指スクロールも同じ）。"""
        self._drag_motion(event, self.editor)
        return 'break'

    def _on_f2_candidates(self, event=None):
        """
        F2 で候補一覧を出す（右クリックと同じ機能）。

        マウスを使わずに選び直せるようにする（実機からの要望）。
        範囲を選んでいればその範囲で、選んでいなければカーソル位置の
        語で候補を出す。

        右クリックはマウスの座標を持っているが、F2 には座標が無い。
        そこで対象の語の画面上の位置を調べ、そこに右クリックした
        のと同じ形の作り物のイベントを渡す。こうすると候補一覧の
        表示処理（_open_dropdown / _open_editor_dropdown）を
        そのまま使い回せる。
        """
        # **IME が確定した `q`**（keysym が F2 に化けたもの）なら、
        # 候補一覧を開いてはいけない（項目48-EH）。
        if self._ime_fkey_skip(event) is not None:
            return 'break'
        unified = self._layout_is_unified()

        # 簡易入力の候補一覧が開いているなら、その遡りを続ける
        # （candidate一覧にフォーカスがあると widget 束縛に届かず
        # こちらへ来るため・2026-08-09）。
        if (self._dropdown is not None
                and getattr(self, '_dropdown_owner', None) == 'quick'
                and getattr(self, '_f2q_cycle', None)):
            return self._quick_f2_step_back()
        # フォーカスが簡易入力側にあるなら、簡易入力の F2 として扱う
        qwin = getattr(self, '_quick_win', None)
        if qwin is not None:
            try:
                focused = self.root.focus_get()
                if (focused is not None
                        and focused.winfo_toplevel() is qwin):
                    return self._on_quick_f2(event)
            except Exception:
                pass
        # 候補一覧が開いたまま F2 を連打したら、1つ左（前）の語へ
        # 遡って候補を出し直す（実機からの要望・2026-08-09。
        # 「全角文字が」で が → 文字 → 全角 と遡る）。
        #
        # **候補が1つも無い語で止まっても、遡りは続ける**（項目48-GM）。
        # 候補一覧は `len(items) <= 1` のとき開かないので、そこに
        # 止まると `self._dropdown` が None になり、次の F2 が
        # 「はじめから」の道へ落ちて**選んでいた語が外れて**いた。
        #
        #     されることを目指す。 の末尾から F2 を3回
        #       1回目 目指す（候補あり）→ 2回目 を（候補なし）
        #       → 3回目 **選択が外れる**（うにさんの報告・2026-08-20）
        #
        # `を` に候補が出なくなったのは項目48-GL から。それまでは
        # `図／ヲ` が出ていたので、この穴が見えていなかった。
        # **色が付いたまま**（`_f2_focus_target` が残っている）なら、
        # 遡りの途中とみなして続ける。本文をクリックすれば
        # `_clear_f2_on_click` が印を消すので、古い状態は残らない。
        _cyc = getattr(self, '_f2_cycle', None)
        if _cyc and getattr(self, '_dropdown_owner', None) == 'main' and (
                self._dropdown is not None
                or getattr(self, '_f2_focus_target', None) is not None):
            return self._f2_step_back()

        # F2 の対象は、レイアウトによらず **メモ欄（左の入力欄）**。
        #
        # うにさんの指定（2026-08-09）: 分割レイアウトでも、色付けと
        # 候補一覧は打った本人の文字がある入力欄に対して行う。
        # 補正欄（右）には対応する語に色を付けるだけで、候補は出さない
        # （_mirror_f2_focus_to_result）。
        #
        # 以前は補正欄に対して候補一覧を開いていた。補正後の文字を
        # 選び直す形になり、入力欄で範囲を選んで F2 を押しても
        # 補正欄には選択もカーソルも無く反応しない、という問題も
        # 抱えていた。
        widget = self.editor

        try:
            sel = widget.tag_ranges('sel')
        except Exception:
            sel = None

        row = col1 = col2 = None
        if sel:
            try:
                first = str(sel[0]).split('.')
                last = str(sel[1]).split('.')
                r1, c1 = int(first[0]), int(first[1])
                r2, c2 = int(last[0]), int(last[1])
                if r1 == r2 and c2 > c1:
                    row, col1, col2 = r1, c1, c2
            except Exception:
                row = None

        if row is None:
            # 選択が無ければ、カーソルのある語を対象にする
            try:
                pos = widget.index('insert')
                r, c = pos.split('.')
                row, col1 = int(r), int(c)
            except Exception:
                return 'break'
            col2 = None

        target_widget = widget

        # 行頭（カーソルの左に文字が無い）なら、前の行の末尾の語へ。
        # F2 は「カーソルの直前の語」を対象にするものなので、
        # 行頭では前の行の最後の語を見に行くのが自然
        # （うにさんの指定・2026-08-09。以前は何も起きなかった）。
        #
        # **この判定は、今の行の単位を調べるより前に行う。** 末尾の
        # 空行（_pad_blank_lines）には単位が無いので、先に調べると
        # そこで打ち切られ、前の行まで辿り着けない（実機で
        # 「行頭で F2 をしても反応しません」と再報告・2026-08-09）。
        if col2 is None and col1 == 0:
            found = self._f2_last_word_before(row)
            if found is None:
                return 'break'
            row, line_units, idx0 = found
            unit = line_units[idx0]
            self._f2_cycle = {'row': row, 'idx': idx0,
                              'widget': target_widget, 'unified': unified,
                              'units': line_units}
            return self._f2_show_or_skip(row, unit, target_widget, unified,
                                         line_units)

        i = row - 1
        if unified:
            units_all = self.line_units
            if 0 <= i < len(units_all):
                line_units = units_all[i]
            else:
                return 'break'
        else:
            # 分割レイアウトでは line_units が補正後の位置を持つので、
            # メモ欄の文字の上での単位を組み立て直して使う。
            line_units = self._editor_line_units(row)
            if not line_units:
                # この行に語が無い（空行など）。前の行の末尾へ。
                found = self._f2_last_word_before(row)
                if found is None:
                    return 'break'
                row, line_units, idx0 = found
                self._f2_cycle = {'row': row, 'idx': idx0,
                                  'widget': target_widget,
                                  'unified': unified, 'units': line_units}
                return self._f2_show_or_skip(row, line_units[idx0],
                                             target_widget, unified,
                                             line_units)

        if col2 is not None:
            line_text = target_widget.get(f'{row}.0', f'{row}.end')
            unit = make_range_unit(line_text, line_units, col1, col2)
        else:
            unit = unit_at(line_units, col1)
            if unit is None and col1 > 0:
                # 語の右端にカーソルがある場合は、直前の語を対象にする
                unit = unit_at(line_units, col1 - 1)
            # カーソルの直前が「補正の提案を持つ記号」なら、そちらを
            # 優先する。文頭の「?」（・の誤入力）はこの形で、
            # カーソルはその右（次の語の頭）にあることが多い
            # （実機で「文頭の?を F2 で直したい」と要望・2026-08-10）。
            if col1 > 0:
                _prev_u = unit_at(line_units, col1 - 1)
                if (_prev_u is not None and _prev_u is not unit
                        and _prev_u.get('end') == col1
                        and (_prev_u.get('detail')
                             or is_symbol_word(_prev_u.get('text', '')))):
                    unit = _prev_u
            # カーソルの位置が句読点・記号（行末の 。 等）なら、
            # 左隣の語まで遡る。ここで句読点を対象にしてしまうと、
            # 候補が出ず、F2 連打の遡りも始まらなかった
            # （実機で「句点で終えると遡れません」と報告・2026-08-09）。
            # ただし補正の提案（detail）を持つ記号は対象にできる
            # （文頭の「?」→「・」等・2026-08-10）。
            if unit is not None and not unit.get('detail') \
                    and not is_symbol_word(unit.get('text', '')) \
                    and not _f2_word_re.search(
                    unit.get('text', '')):
                k0 = None
                for k, u in enumerate(line_units):
                    if u is unit:
                        k0 = k
                        break
                unit = None
                if k0 is not None:
                    for k in range(k0 - 1, -1, -1):
                        if (_f2_word_re.search(
                                line_units[k].get('text', ''))
                                or is_symbol_word(
                                    line_units[k].get('text', ''))):
                            unit = line_units[k]
                            break
        if unit is None or not unit.get('text', '').strip():
            return 'break'

        # 連打で遡るための現在地を控える（範囲選択で出した場合も、
        # そこから F2 連打で左の語へ移れる）。
        try:
            idx = next(k for k, u in enumerate(line_units) if u is unit)
        except StopIteration:
            # 範囲選択から作った一時的な単位。位置で対応する語を探す
            idx = None
            for k, u in enumerate(line_units):
                if u['start'] <= unit['start'] < u['end']:
                    idx = k
                    break
        self._f2_cycle = {'row': row, 'idx': idx,
                          'widget': target_widget, 'unified': unified,
                          'units': line_units}
        return self._f2_show_or_skip(row, unit, target_widget, unified,
                                     line_units)

    def _f2_units_for_row(self, row):
        """
        F2 が対象にする、その行の単位の並び。

        行が無ければ None（メモ欄の外に出た合図）、
        中身の無い行なら空リストを返す。

        **メモ欄の行数と line_results の数は一致しない。**
        メモ欄の末尾には、どの行にもカーソルを置けるように
        空行を足してある（_pad_blank_lines）。そこは解析結果を
        持たないが「行としては在る」ので、空リストを返して
        飛ばせるようにする。ここで None を返すと、末尾の空行に
        カーソルがあるとき F2 が前の行へ遡れない（実機で
        「行頭で F2 をしても反応しません」と報告・2026-08-09）。
        """
        i = row - 1
        if i < 0:
            return None
        try:
            last = int(self.editor.index('end-1c').split('.')[0])
        except Exception:
            last = len(self.line_results)
        if row > max(last, len(self.line_results)):
            return None
        if i >= len(self.line_results):
            return []
        if self._layout_is_unified():
            if 0 <= i < len(self.line_units):
                return self.line_units[i]
            return []
        return self._editor_line_units(row)

    def _f2_last_word_before(self, row):
        """
        row より前の行をさかのぼって、最後の語を探す。

        行頭で F2 を押したときに、前の行の末尾の語へ移るために使う
        （うにさんの指定・2026-08-09）。
        戻り値は (row, units, idx)。見つからなければ None。
        """
        r = row - 1
        while r >= 1:
            units = self._f2_units_for_row(r) or []
            for k in range(len(units) - 1, -1, -1):
                if (_f2_word_re.search(units[k].get('text', ''))
                        or units[k].get('detail')
                        or is_symbol_word(units[k].get('text', ''))):
                    return r, units, k
            r -= 1
        return None

    # F2 で「候補の出ない語」を飛ばすとき、いくつまで見るか
    # （項目48-GN）。助詞ばかりの行が続いても、ここで必ず止まる。
    #
    # **実機メモ40行で測った**（2026-08-20）:
    #   語として止まれる単位 683 / 候補一覧が開く 434（64%）
    #   開かない 249 のうち **246 は助詞・活用語尾**（残り3件は
    #   記号混じりの長い塊）。うにさんの「助詞は飛ばす」と、
    #   「候補の出る語だけ」は**ほぼ同じもの**を指していた。
    #   続けて飛ばす数は 1 が 167 回・2 が 32 回・3 が 6 回で、
    #   **いちばん長くて3**。40 は余裕を見た上限で、ふつうは届かない。
    F2_SKIP_MAX = 40

    def _f2_step_back(self):
        """F2 連打。1つ左の語へ遡って候補を出し直す。"""
        return self._f2_move(-1)

    def _f2_move(self, delta):
        """
        F2 で選んでいる語を、前後に move する。

        delta = -1 で左（前）の語、+1 で右（次）の語。
        行の端まで来たら、隣の行へ続けてたどる（うにさんの指定・
        2026-08-09。行頭で止まらず、前の行の末尾の語へ移る）。

        **候補の出ない語（助詞など）では止まらない**（項目48-GN。
        うにさんの指定・2026-08-20:「助詞は飛ばして候補の出る語だけを
        渡り歩くようにします」）。

        「候補が出るか」は**実際に開いてみて決める**。候補一覧を
        組み立てるところ（`_open_editor_dropdown`）は、記号の
        言い換え・元に戻す・自動補正の取り消しなども足したうえで
        `len(items) <= 1` なら開かない。**同じ判定をもう一度
        書くと、いつか食い違う**ので、開いたかどうかを見る
        （`self._dropdown is None` なら開かなかった）。

        最後まで候補の出る語が無ければ、**元いた語に戻す**。
        戻さないと、飛ばした先の「候補の出ない語」に色が残る。
        """
        cyc = getattr(self, '_f2_cycle', None)
        if not cyc or cyc.get('idx') is None:
            return 'break'
        # **Shift+左右で範囲を変えたあとの右キーは、その範囲の
        # 終わりの次の文字から次の範囲にする**（うにさんの指定・
        # 2026-08-27）。cyc['idx'] は元の単位を指したままなので、
        # そのまま進めると、調整した範囲と重なったり、間の文字を
        # 飛ばしたりする。
        if delta > 0:
            got = self._f2_resized_next()
            if got is not None:
                return got
        home = (cyc['row'], cyc['idx'], cyc.get('units'),
                cyc.get('widget'), cyc.get('unified'))
        ended = False
        for _ in range(self.F2_SKIP_MAX):
            nxt = self._f2_next_stop(cyc['row'], cyc['idx'],
                                     cyc.get('units'), delta)
            if nxt is None:
                ended = True
                break
            row, idx, units = nxt
            cyc['row'], cyc['idx'], cyc['units'] = row, idx, units
            self._show_unit_candidates(row, units[idx], cyc['widget'],
                                       cyc['unified'], units)
            if self._dropdown is not None:
                return 'break'

        # 候補の出る語が見つからなかった。元の語へ色を戻す。
        h_row, h_idx, h_units, h_widget, h_unified = home
        cyc['row'], cyc['idx'], cyc['units'] = h_row, h_idx, h_units
        try:
            if h_units and 0 <= h_idx < len(h_units):
                self._show_unit_candidates(h_row, h_units[h_idx],
                                           h_widget, h_unified, h_units)
        except Exception:
            pass
        try:
            self.status.config(
                text=(('最後の語まで来ました' if delta > 0
                       else '最初の語まで遡りました') if ended
                      else '候補の出る語が見つかりませんでした'))
        except Exception:
            pass
        return 'break'

    def _f2_resized_next(self):
        """
        Shift+左右（C-3）で調整した F2 の範囲から、**右どなり**の
        範囲を作る（うにさんの指定・2026-08-27「左右キーで範囲を
        変更したあとに右キーで次の範囲に移るときは、その前の範囲
        終わりの次の文字から範囲にする」）。

        範囲の終わり e が単位の**途中**なら「e からその単位の終わり
        まで」を範囲にして出す。単位の**切れ目**に揃っているなら、
        cyc['idx'] を e の直前の単位に合わせて、通常の渡り歩き
        （`_f2_next_stop`。助詞は飛ばす）へ合流させる。

        戻り値: 'break'（ここで出した）か None（通常の道へ）。
        調整していないとき（範囲が元の単位のまま）は必ず None。
        """
        cyc = getattr(self, '_f2_cycle', None)
        tgt = getattr(self, '_f2_focus_target', None)
        if not cyc or not tgt:
            return None
        units = cyc.get('units')
        idx = cyc.get('idx')
        if not units or idx is None or not (0 <= idx < len(units)):
            return None
        row = cyc.get('row')
        if tgt.get('row') != row or tgt.get('widget') is not cyc.get('widget'):
            return None
        u = units[idx]
        s, e = tgt.get('start'), tgt.get('end')
        if s is None or e is None:
            return None
        if s == u.get('start') and e == u.get('end'):
            return None             # 調整していない。通常の渡り歩きへ
        # e を含む（または e より後ろの）最初の単位
        k = None
        for j, u2 in enumerate(units):
            if u2.get('end', 0) > e:
                k = j
                break
        if k is None:
            # e が行の終わり。次の行へは通常の道で（行の最後から）
            cyc['idx'] = len(units) - 1
            return None
        if units[k].get('start', 0) >= e:
            # 切れ目に揃っている。次の単位から通常の渡り歩き
            cyc['idx'] = k - 1
            return None
        widget = cyc.get('widget')
        try:
            line_text = widget.get(f'{row}.0', f'{row}.end')
        except Exception:
            return None
        unit = make_range_unit(line_text, units, e, units[k]['end'])
        if unit is None:
            cyc['idx'] = k - 1
            return None
        cyc['idx'] = k
        self._show_unit_candidates(row, unit, widget,
                                   cyc.get('unified'), units)
        return 'break'

    def _f2_peek(self, delta):
        """
        左右キーで**次に選ばれる範囲**を先読みする（塗るだけ・動かさない。
        `_paint_f2_neighbors` が使う）。右は、調整済みの範囲があれば
        「終わりの次の文字」から（`_f2_resized_next` と同じ規則）。

        **候補の出ない語は飛ばして、その奥を返す**（うにさんの指定・
        2026-08-27 3度目「候補が出ないところはその奥の範囲に薄い色を」）。
        「候補が出るか」は、実際の一覧と同じ組み立て
        （`_editor_dropdown_items`）で数える——同じ判定を2度書かない。

        戻り値: (行, 始まり, 終わり) か None。
        """
        cyc = getattr(self, '_f2_cycle', None)
        tgt = getattr(self, '_f2_focus_target', None)
        if not cyc or cyc.get('idx') is None:
            return None
        row = cyc.get('row')
        units = cyc.get('units') or []
        idx = cyc.get('idx')
        if not (0 <= idx < len(units)):
            return None

        def _scan(r0, i0, u0):
            """止まれる語を、**一覧が開く語**まで delta の向きへ辿る。"""
            for _ in range(self.F2_SKIP_MAX):
                nxt = self._f2_next_stop(r0, i0, u0, delta)
                if nxt is None:
                    return None
                r0, i0, u0 = nxt
                unit = u0[i0]
                try:
                    opens = len(self._editor_dropdown_items(
                        r0, unit, u0)) > 1
                except Exception:
                    opens = True
                if opens:
                    return (r0, unit['start'], unit['end'])
            return None

        if delta > 0 and tgt and tgt.get('row') == row:
            u = units[idx]
            s, e = tgt.get('start'), tgt.get('end')
            if s is not None and e is not None \
                    and (s != u.get('start') or e != u.get('end')):
                k = None
                for j, u2 in enumerate(units):
                    if u2.get('end', 0) > e:
                        k = j
                        break
                if k is not None and units[k].get('start', 0) < e:
                    # 単位の途中——実際の右キーもこの範囲を必ず見せる
                    # （`_f2_resized_next` は候補が無くても出す）
                    return (row, e, units[k]['end'])
                start_i = (len(units) - 1) if k is None else (k - 1)
                return _scan(row, start_i, units)
        return _scan(row, idx, units)

    def _paint_f2_neighbors(self):
        """
        左右キーの**行き先**に薄い色を付ける（うにさんの指定・
        2026-08-27「今選択している範囲から左右キーを押すと次に選択される
        範囲に薄い色が付くようにしてください」）。左右の両隣に `f2_next`。

        行き先は `_f2_next_stop`（止まれる語）の先読み。候補が出ない語は
        実際の移動でさらに飛ばされることがあるが、そこまでは追わない
        （塗りは目安。動きは今までどおり `_f2_move` が決める）。
        """
        cyc = getattr(self, '_f2_cycle', None)
        widget = ((cyc or {}).get('widget')
                  or getattr(self, 'editor', None))
        if widget is None:
            return
        try:
            widget.tag_remove('f2_next', '1.0', 'end')
        except Exception:
            pass
        if not cyc or getattr(self, '_f2_focus_target', None) is None:
            return
        # **もっと薄く**（うにさんの指定・2026-08-31）。地色との明るさの
        # 差を**およそ半分**にした（ダーク 18.9 → 10.1／ライト 15.1 → 8.1）。
        # 選んでいる範囲（`f2_focus`・53.0／34.0）との差が開くので、
        # 「いまここ」と「次はここ」が取り違えにくくなる。
        bg = ('#393225' if self.settings.get('dark_mode') else '#fff6e8')
        try:
            widget.tag_configure('f2_next', background=bg)
            # 選択そのもの（f2_focus）が重なったら、濃いほうを見せる
            widget.tag_lower('f2_next', 'f2_focus')
        except Exception:
            pass
        for delta in (-1, 1):
            try:
                got = self._f2_peek(delta)
            except Exception:
                got = None
            if not got:
                continue
            r2, s2, e2 = got
            try:
                widget.tag_add('f2_next', f'{r2}.{s2}', f'{r2}.{e2}')
            except Exception:
                pass

    def _f2_next_stop(self, row, idx, units, delta):
        """
        いまの位置から delta の向きへ、**次に止まれる語**を探す。

        戻り値 (row, idx, units)。端まで来たら None。
        ここでは位置を進めるだけで、色付けも候補一覧も出さない
        （候補が出るかどうかは呼び手が見る・項目48-GN）。
        """
        if not units:
            units = self._f2_units_for_row(row) or []
        idx = idx + delta

        # 行をまたいで探す。行数ぶん見れば必ず端に着く。
        # 補正の提案（detail）を持つ記号（文頭の「?」等）は
        # 語と同じように止まれる（2026-08-10）。
        for _ in range(len(self.line_results) + 1):
            while 0 <= idx < len(units) and not (
                    _f2_word_re.search(units[idx].get('text', ''))
                    or units[idx].get('detail')
                    or is_symbol_word(units[idx].get('text', ''))):
                idx += delta
            if 0 <= idx < len(units):
                return row, idx, units
            next_row = row + (1 if delta > 0 else -1)
            next_units = self._f2_units_for_row(next_row)
            if next_units is None:
                return None
            row, units = next_row, next_units
            idx = 0 if delta > 0 else len(units) - 1
            if not units:
                # 空行は飛ばす（idx が範囲外のまま次の行へ進む）
                idx = 0 if delta > 0 else -1
        return None

    def _f2_show_or_skip(self, row, unit, widget, unified, units):
        """
        語に色を付けて候補一覧を出す。**出なければ左へ遡る**
        （項目48-GN）。`_f2_cycle` は呼ぶ前に置いておくこと。
        """
        self._show_unit_candidates(row, unit, widget, unified, units)
        # **範囲を選んで押した場合は飛ばさない。** うにさんが
        # 「ここを見たい」と指したものを、勝手に離れないこと。
        if self._dropdown is None and unit.get('kind') != 'range':
            return self._f2_move(-1)
        return 'break'

    def _on_click_past_line_end(self, event):
        """
        行末より右の余白をクリックしたときの受け皿（項目48-GN）。

        押した場所を控えて、Tk がカーソルを置き終えた**あと**で
        直しに行く。ウィジェットへの束縛は Tk の既定の動き
        （`tk::TextButton1`）より**先**に走るので、ここで直接
        `insert` を動かしても上書きされてしまう。
        """
        if getattr(self, '_pick_mode', None):
            return None                 # 引用モードは別の意味を持つ
        try:
            widget, x, y = event.widget, event.x, event.y
            widget.after_idle(
                lambda: self._fix_click_past_line_end(widget, x, y))
        except Exception:
            pass
        return None

    def _fix_click_past_line_end(self, widget, x, y):
        """
        行末より右の余白を押したら、カーソルを**その行の末尾**に置く。

        うにさんの報告（2026-08-20）:
        「文末の余白をクリックすると、**次の行の頭にカーソルが出る
          ことがあります**。文末にカーソルを置いてください」

        **測ったこと**: 改行文字の枠は、行末から欄の右端まで
        広がっている（「短い行。」で x=77..547・幅 470）。Tk の
        `tk::TextClosestGap` は「押した位置が文字の**真ん中より右**
        なら1つ進める」ので、改行の真ん中より右を押すと
        **改行をまたいで次の行の頭**へ行く。行が短いほど枠が広く、
        当たりやすい（「ことがあります」はこれ。長い行では起きない）。

        直すのは「押した場所の文字が**その行の末尾**で、かつ Tk が
        **次の行へ渡した**とき」だけ。

        **折り返しの途中は触らない。** 折り返し目の右余白を押すと
        次の**表示行**の頭に出るが、そこは文字の位置としては正しい
        （同じ論理行の同じ隙間）。引き戻すと最後の1文字の手前に
        なってしまうし、Tk には「前の表示行の末尾に描く」という
        置き方が無い。**直せないものは触らない。**
        """
        try:
            hit = widget.index(f'@{x},{y}')
            row = int(hit.split('.')[0])
            end = widget.index(f'{row}.end')
            if hit != end:
                return                  # 行末より手前を押している
            after = widget.index(f'{end} + 1 char')
            if after == end:
                return                  # 最後の行（進みようがない）
            if widget.index('insert') != after:
                # Tk は渡していない（正しい位置）。ドラッグで
                # 選択中に割り込んだ場合もここで抜ける。
                return
            if widget.tag_ranges('sel'):
                return                  # 範囲を選んでいる最中
            widget.mark_set('insert', end)
            # 起点（Shift+クリックやドラッグが使う印）も揃える。
            # ここを置き忘れると、次に Shift+クリックしたときだけ
            # 直す前の位置から選択されてしまう。
            widget.mark_set('tk::anchor1', end)
        except Exception:
            pass

    def _clear_f2_on_click(self, event=None):
        """
        本文（メモ欄・補正欄）のクリックで、F2 の語の記憶と色を捨てる。

        クリックは「その語から離れる」操作なので、色を残さない。
        括弧ボタンなど本文の外のクリックはここへ来ないため、
        「F2 で選んだ語を括る」流れは壊さない。
        """
        if getattr(self, '_f2_focus_target', None) is not None:
            self._clear_f2_target()

    def _clear_f2_target(self):
        """F2 で選んでいる語の記憶と色付けを捨てる。"""
        self._f2_focus_target = None
        for _w in (getattr(self, 'editor', None),
                   getattr(self, 'result_view', None),
                   getattr(self, '_quick_text', None)):
            if _w is None:
                continue
            try:
                _w.tag_remove('f2_focus', '1.0', 'end')
                _w.tag_remove('f2_next', '1.0', 'end')
            except Exception:
                pass

    def _on_dropdown_horizontal(self, delta):
        """
        候補一覧が開いているときの左右キー。対象の語を前後に移す。

        上下キーは候補の選択に使うので、語の移動は左右に割り当てる
        （うにさんの指定・2026-08-09）。
        """
        if self._dropdown is None:
            return None
        owner = getattr(self, '_dropdown_owner', None)
        if owner == 'main' and getattr(self, '_f2_cycle', None):
            return self._f2_move(delta)
        if owner == 'quick' and getattr(self, '_f2q_cycle', None):
            return self._quick_f2_move(delta)
        return None

    # ------------------------------------------------------------
    # F2 で語を選んでいる最中のキー操作
    # （うにさんの指定・2026-08-11・C-1／C-2／C-3）
    #
    #   ・文字を打つ      → 選んでいる範囲の**後ろ**に入れる
    #   ・Delete          → 選んでいる範囲を消す
    #   ・Shift + 左右    → 選んでいる範囲を伸び縮みさせる
    #                      （IME の変換範囲調整と同じ感覚）
    #
    # どれも「候補一覧に焦点がある」状態で押される。Listbox は
    # 文字を受け取れないので、そのままでは打った文字が消える。
    # ここで受けて、**本文の欄へ焦点を返してから**行う。
    #
    # Tk の決まりで、同じウィジェットの束縛は**いちばん細かい型が
    # 1つだけ**走る。`<Return>` や `<Up>` のような個別の束縛が
    # ある鍵はそちらへ行き、それ以外だけが `<KeyPress>` に来る。
    # だから下の `_on_dropdown_keypress` は「印字できる文字」だけを
    # 見ればよく、F2 のような鍵は None を返して素通しする
    # （素通ししないと F2 連打の遡りが効かなくなる）。
    # ------------------------------------------------------------

    def _f2_editable_target(self):
        """
        F2 で選んでいる語と、それが載っている**書き込める欄**。

        戻り値: (widget, row, start, end)。無い・書けないなら None。
        補正欄（result_view）は state='disabled' なので None になる。
        いまの作りでは F2 の対象は必ずメモ欄か簡易入力欄なので
        通らないはずだが、読み取り専用の欄を書き換えて例外で
        止まるより、静かに何もしないほうがよい。
        """
        tgt = getattr(self, '_f2_focus_target', None)
        if not tgt:
            return None
        widget = tgt.get('widget')
        if widget is None:
            return None
        try:
            if str(widget.cget('state')) != 'normal':
                return None
            row = int(tgt['row'])
            start = int(tgt['start'])
            end = int(tgt['end'])
        except Exception:
            return None
        if end <= start:
            return None
        return widget, row, start, end

    def _after_f2_edit(self, widget):
        """
        F2 の範囲を書き換えたあとの後始末。

        `insert` / `delete` を呼んだだけでは `<KeyRelease>` が
        飛ばないので、**打鍵と同じ道**（_on_change / 簡易入力の
        変更検知）を自分で呼ぶ。呼ばないと解析も控えの書き出しも
        走らず、直したはずの行が古いまま残る。
        """
        try:
            widget.see('insert')
        except Exception:
            pass
        if widget is getattr(self, '_quick_text', None):
            # 簡易入力欄は <<Modified>> で拾う作りで、
            # プログラムからの書き換えでも発火する。
            return
        try:
            self._on_change()
        except Exception:
            pass

    def _on_dropdown_keypress(self, event):
        """
        候補一覧に焦点がある状態で、文字が打たれたとき（C-1）。

        うにさんの指定:「F2で単語を選んでいるときに、文字を
        入力したら**選択されている範囲の後ろにカーソルを置いて**
        そこへ文字入力する」。**選んでいる語は消さない**。

        印字できない鍵（F2・Tab・修飾キー等）は None を返して
        そのまま流す。
        """
        ch = getattr(event, 'char', '') or ''
        if len(ch) != 1 or not ch.isprintable():
            return None
        got = self._f2_editable_target()
        if got is None:
            return None
        widget, row, _start, end = got
        self._close_dropdown()
        try:
            widget.focus_set()
            widget.tag_remove('sel', '1.0', 'end')
            widget.mark_set('insert', f'{row}.{end}')
            widget.insert(f'{row}.{end}', ch)
            if widget is self.editor:
                # 打った1文字なので印を付ける（項目48-X）
                self._mark_typed(row, end, end + len(ch))
        except Exception:
            return 'break'
        self._after_f2_edit(widget)
        return 'break'

    def _f2_range_active(self):
        """
        メモ欄の側で F2 の範囲を操作してよいか（項目48-ED）。

        候補一覧が開いているなら、そちらの束縛が受け持つので
        **こちらは何もしない**（二重に効かせない）。
        """
        if getattr(self, '_dropdown', None) is not None:
            return False
        return getattr(self, '_f2_focus_target', None) is not None

    def _on_f2_range_keypress(self, event):
        """候補一覧が開いていないときの C-1（文字は範囲の後ろへ）。"""
        if not self._f2_range_active():
            return None
        return self._on_dropdown_keypress(event)

    def _on_f2_range_delete(self, event=None):
        """候補一覧が開いていないときの C-2（Delete で範囲を消す）。"""
        if not self._f2_range_active():
            return None
        return self._on_dropdown_delete(event)

    def _on_f2_range_move(self, delta):
        """
        候補一覧が開いていないときの左右キー（2026-08-27）。

        F2 の範囲がある間は、左右キーは**範囲の渡り歩き**
        （一覧が開いているときの `_on_dropdown_horizontal` と同じ）。
        範囲が無ければ None を返して、ふつうのカーソル移動に任せる。
        """
        if not self._f2_range_active():
            return None
        if getattr(self, '_f2_cycle', None):
            return self._f2_move(delta)
        return None

    def _on_f2_range_resize(self, delta):
        """候補一覧が開いていないときの C-3（Shift+左右で伸び縮み）。

        一覧が無いので候補は出し直せない。**色の付いた範囲だけ**を
        伸び縮みさせる（記号を選んだあと、隣の1文字まで含めて
        消す・打ち替える、という使い方ができる）。
        """
        if not self._f2_range_active():
            return None
        got = self._f2_editable_target()
        if got is None:
            return None
        widget, row, start, end = got
        try:
            line_text = widget.get(f'{row}.0', f'{row}.end')
        except Exception:
            return 'break'
        new_start, new_end = start, end + delta
        # **1文字のときの Shift+← は、左どなりを範囲に含める**
        # （2026-08-16・うにさんの指定）。右端はこれ以上縮められない
        # ので、代わりに左へ広げる。続けて押せば、縮める→左へ広げる
        # を繰り返して範囲が1文字ずつ左へ歩く。
        if delta < 0 and end - start == 1:
            if start <= 0:
                return 'break'
            new_start, new_end = start - 1, end
        if new_start < 0 or new_end <= new_start \
                or new_end > len(line_text):
            return 'break'      # 1文字未満にも、行の外にも出さない
        tgt = self._f2_focus_target
        tgt['start'] = new_start
        tgt['end'] = new_end
        tgt['text'] = line_text[new_start:new_end]
        try:
            widget.tag_remove('f2_focus', '1.0', 'end')
            widget.tag_add('f2_focus',
                           f'{row}.{new_start}', f'{row}.{new_end}')
            widget.tag_raise('f2_focus')
        except Exception:
            pass
        # 行き先の薄い色も引き直す（右は調整の終わりの次から）
        try:
            self._paint_f2_neighbors()
        except Exception:
            pass
        return 'break'

    def _on_dropdown_delete(self, event=None):
        """
        候補一覧に焦点がある状態で Delete（C-2）。

        うにさんの指定:「F2で単語を選んでいるときに、デリートを
        押したら選択範囲が消えるようにする」。

        BackSpace も同じ扱いにしてある。色の付いた範囲は
        見た目が選択そのもので、ふつうの編集ではどちらのキーでも
        選択が消えるため。**戻したいときはこの関数の束縛から
        `<BackSpace>` を外すだけでよい。**
        """
        got = self._f2_editable_target()
        if got is None:
            return None
        widget, row, start, end = got
        self._close_dropdown()
        try:
            widget.focus_set()
            widget.tag_remove('sel', '1.0', 'end')
            widget.delete(f'{row}.{start}', f'{row}.{end}')
            widget.mark_set('insert', f'{row}.{start}')
        except Exception:
            return 'break'
        self._after_f2_edit(widget)
        return 'break'

    def _on_dropdown_resize(self, delta):
        """
        候補一覧に焦点がある状態で Shift+左右（C-3）。

        うにさんの指定:「IMEの変換範囲調整のように、F2の範囲を
        広げたり短くしたりする」。IME と同じく**左端は動かさず、
        右端だけ**を伸び縮みさせる（Shift+→ で1文字伸ばし、
        Shift+← で1文字縮める）。

        伸ばした範囲の候補は `make_range_unit` が作る。ドラッグで
        範囲を選んだときと同じ道なので、漢字・かな混じりでも
        読みを繋いで候補が出せる。
        """
        got = self._f2_editable_target()
        if got is None:
            return 'break'
        widget, row, start, end = got
        owner = getattr(self, '_dropdown_owner', None)
        try:
            line_text = widget.get(f'{row}.0', f'{row}.end')
        except Exception:
            return 'break'
        new_start, new_end = start, end + delta
        # **1文字のときの Shift+← は、左どなりを範囲に含める**
        # （2026-08-16・うにさんの指定）。メモ欄側の
        # `_on_f2_range_resize` と同じ動き。
        if delta < 0 and end - start == 1:
            if start <= 0:
                return 'break'
            new_start, new_end = start - 1, end
        if new_start < 0 or new_end <= new_start \
                or new_end > len(line_text):
            return 'break'      # 1文字未満にも、行の外にも出さない

        if owner == 'quick':
            units = self._quick_line_units(row)
            if units is None:
                return 'break'
            unit = make_range_unit(line_text, units, new_start, new_end)
            if unit is None:
                return 'break'
            # **Shift+左右で作り替えた範囲**という印（項目48-MD）。
            # 語の切れ目に揃っていないので、品詞は名乗らない。
            unit['resized'] = True
            self._show_quick_unit_candidates(row, unit)
            return 'break'

        cyc = getattr(self, '_f2_cycle', None)
        if not cyc:
            return 'break'
        units = cyc.get('units') or self._f2_units_for_row(row) or []
        unit = make_range_unit(line_text, units, new_start, new_end)
        if unit is None:
            return 'break'
        unit['resized'] = True        # 項目48-MD（上と同じ印）
        self._show_unit_candidates(row, unit, widget,
                                   cyc.get('unified'), units)
        return 'break'

    def _quick_line_units(self, row):
        """簡易入力欄の row 行目の単位（無ければ None）。"""
        units_all = getattr(self, '_quick_units', None)
        if not units_all:
            return None
        i = row - 1
        if 0 <= i < len(units_all):
            return units_all[i]
        return None

    def _show_unit_candidates(self, row, unit, target_widget, unified,
                              units=None):
        """対象の語に色を付けてから、候補一覧を開く。"""
        fake = self._fake_event_at(target_widget, row, unit)
        self._close_dropdown()
        # 対象がメモ欄なら、メモ欄に対する候補一覧を開く。
        # 分割レイアウトでも同じ（補正欄には候補を出さない）。
        if target_widget is self.editor:
            self._open_editor_dropdown(fake, row, unit, units)
        else:
            self._open_dropdown(fake, row, unit)
        self._dropdown_owner = 'main'
        # F2 から開いた印。F2 で確定したときは選択を残さない
        # （実機からの要望・2026-08-10）。右クリックから開いた
        # 場合は _open_editor_dropdown / _open_dropdown が False に
        # 戻すため、ここで上書きする順序が大事。
        self._dropdown_via_f2 = True
        # どの語の候補を出しているかが分かるように、対象の語に
        # 色を付ける（候補一覧が閉じるときに消す）。
        # _close_dropdown が消す側を受け持つため、開いた後に付ける。
        bg = ('#7a5a2b' if self.settings.get('dark_mode')
              else '#ffd9a0')
        try:
            target_widget.tag_configure('f2_focus', background=bg)
            target_widget.tag_add(
                'f2_focus',
                f'{row}.{unit["start"]}', f'{row}.{unit["end"]}')
            target_widget.tag_raise('f2_focus')
        except Exception:
            pass
        # 括弧ボタンが「いま候補を出している語」を括れるように控える
        # （うにさんの指定・2026-08-09）。
        self._f2_focus_target = {
            'widget': target_widget, 'row': row,
            'start': unit['start'], 'end': unit['end'],
            'text': unit.get('text', ''),
        }
        # 分割レイアウトでは、補正欄の対応する語にも色だけ付ける
        if not unified and target_widget is self.editor:
            self._mirror_f2_focus_to_result(row, unit, bg)
        # 左右キーの行き先に薄い色（2026-08-27・うにさんの指定）
        try:
            self._paint_f2_neighbors()
        except Exception:
            pass

    def _fake_event_at(self, widget, row, unit):
        """
        対象の語の画面上の位置に、右クリックしたのと同じ形の
        イベントを作る（F2 から候補一覧を呼ぶため）。
        """
        ev = _FakeEvent()
        ev.widget = widget
        ev.x = ev.y = 0
        try:
            box = widget.bbox(f'{row}.{unit["start"]}')
        except Exception:
            box = None
        if box:
            ev.x, ev.y = box[0], box[1] + box[3]
        try:
            ev.x_root = widget.winfo_rootx() + ev.x
            ev.y_root = widget.winfo_rooty() + ev.y
        except Exception:
            ev.x_root = ev.y_root = 0
        return ev

    def _on_editor_right_click(self, event):
        """
        メモ欄の語の候補を出す（**統合・分割の両方**・項目48-RB）。

        左クリックではなく右クリックに割り当てる。メモ欄は入力欄
        そのものなので、左クリックのカーソル移動・範囲選択を奪うと
        文章が書けなくなるため（簡易入力ウィンドウは書いた直後に
        選び直す小さな窓なので左クリックで良いが、本体のメモ欄は
        長い文章を書き続ける場所なので事情が違う）。

        ドラッグで範囲を選んでから右クリックした場合は、その範囲で
        候補を出す（区切りが実態と合わないときのため）。
        """
        # 押してから動かしていればスクロール操作だったので、
        # 候補一覧は出さない
        if self._drag_release(event, self.editor):
            return 'break'
        # **右を押してから 8px 以上動いていたら、離しは「クリック」ではない**
        # （項目48-TA・2026-09-06・うにさんの報告「両方同時にクリックして、
        # 1行目の上までドラッグすると、そのあとホイールで下へスクロール
        # できなくなる」）。左右を押したまま動かすと Tk は `<B1-Motion>` だけを
        # 渡し（同じ動きに `<B3-Motion>` は渡さない）、左の押し下げが `_drag`
        # を上書きするので、右の離しが「掴みだった」と分からず**候補一覧が
        # 開いて焦点を取り**、以後ホイールが一覧に行っていた（Windows の
        # ホイールは焦点の窓へ届く）。実測: `tools_local/probe_autoscan.py`
        _p = getattr(self, '_r3_press', None)
        self._r3_press = None
        if _p is not None:
            try:
                if (abs(int(event.x_root) - _p[0]) >= 8
                        or abs(int(event.y_root) - _p[1]) >= 8):
                    return 'break'
            except Exception:
                pass

        # ★★ **分割表示でも開く**（項目48-RB・2026-09-05・うにさんの
        # 指定「**入力欄の紫を右クリック**でも候補メニューを出す」）。
        # もとは `if not self._layout_is_unified(): return None` で
        # **入口ごと閉じて**いたので、紫の項目へ届く道が F2 しか
        # 無かった。本体は1本のまま——違うのは
        # `_units_for_row` の中だけ（48-GN）。
        # F2 は前から分割でもメモ欄を対象にしている（`_editor_line_units`）
        # ので、**新しい道を作るのではなく、そのマウス版を足す**。
        self._close_dropdown()

        # 選択範囲があり、かつ押した位置がその範囲の中のときだけ、
        # その範囲を単位に仕立てる。
        #
        # 位置を確認しないと、直前に候補を選んで「選択されたまま」
        # 残っている状態で別の語を右クリックしたとき、新しく押した
        # 場所ではなく古い選択（直前に選んだ語）に対して候補が
        # 出てしまう（実機で報告された）。
        try:
            sel = self.editor.tag_ranges('sel')
        except Exception:
            sel = None
        if sel:
            inside = False
            try:
                pos = self.editor.index(f'@{event.x},{event.y}')
                inside = (self.editor.compare(pos, '>=', 'sel.first')
                          and self.editor.compare(pos, '<=', 'sel.last'))
            except Exception:
                inside = False
            if not inside:
                try:
                    self.editor.tag_remove('sel', '1.0', 'end')
                except Exception:
                    pass
                sel = None
        if sel:
            try:
                first = str(sel[0]).split('.')
                last = str(sel[1]).split('.')
                row1, col1 = int(first[0]), int(first[1])
                row2, col2 = int(last[0]), int(last[1])
            except Exception:
                row1 = row2 = -1
                col1 = col2 = 0
            if row1 == row2 and col2 > col1:
                _units = self._units_for_row(row1)
                if _units:
                    line_text = self.editor.get(f'{row1}.0', f'{row1}.end')
                    unit = make_range_unit(line_text, _units,
                                           col1, col2)
                    if unit is not None:
                        self._open_editor_dropdown(event, row1, unit)
                        return 'break'

        hit = self._editor_unit_under_pointer(event)
        if hit is None:
            return 'break'
        row, unit = hit
        # **中身が空白だけなら出さない**——ただし
        # **紫が立っているなら出す**（項目48-RB）。ここで黙って
        # 帰ると、「この文字列は正しい」に届く道が塞がる
        # （学び22——片方だけに門を置くと、そちらを迂回する）
        if not unit.get('text', '').strip() \
                and self._odd_span_at(row, unit.get('start'),
                                      unit.get('end')) is None:
            return 'break'
        self._open_editor_dropdown(event, row, unit)
        return 'break'

    def _on_editor_motion(self, event):
        """
        統合レイアウトで、メモ欄の語にオンマウスの背景色を付ける。

        分割レイアウトのとき補正欄がやっていたことを、統合では
        メモ欄が引き受ける（実機からの要望）。
        これが無いと、どこがクリックできる単位なのか分からない。

        **引用モード（F1）中は、分割レイアウトでもメモ欄に出す**
        （項目48-FW・うにさんの指定・2026-08-19「F1引用モードは、
        分割モードでメモ欄に対しても、単語のオンマウスで
        背景色の範囲を表示する」）。

        引用モード中はメモ欄の語もクリックで拾える
        （`_on_editor_release` が両レイアウトで受けている）のに、
        **どこが1語なのかの印だけが統合レイアウトにしか無かった。**
        拾える場所が見えないまま当てずっぽうでクリックすることに
        なるので、印だけを引用モード中に限って揃える。
        **拾える範囲そのものは変えていない。**
        """
        if not (self._layout_is_unified()
                or getattr(self, '_pick_mode', None)):
            return
        try:
            self.editor.tag_remove('hover', '1.0', 'end')
        except Exception:
            return
        hit = self._editor_unit_under_pointer(event)
        if hit is None:
            return
        row, unit = hit
        try:
            self.editor.tag_add('hover',
                                f'{row}.{unit["start"]}',
                                f'{row}.{unit["end"]}')
        except Exception:
            pass

    def _on_editor_leave(self, event=None):
        try:
            self.editor.tag_remove('hover', '1.0', 'end')
        except Exception:
            pass

    def _units_for_row(self, row):
        """
        **メモ欄のその行の単位**（項目48-RB・2026-09-05）。

        統合と分割の**違いはここだけ**——統合は `self.line_units`
        （画面の文字＝原文）、分割は `_editor_line_units` が
        その行だけ組み直す（`line_units` は補正後の欄の位置を持って
        いるので、メモ欄の位置には使えない）。

        **右クリックの本体は1本のまま**にするための口（48-GN——
        統合と分割で同じ判定を2度書くと、いつか食い違う）。
        F2 は前から同じ分け方をしている（`_editor_line_units`）。
        """
        if self._layout_is_unified():
            i = row - 1
            if 0 <= i < len(self.line_units):
                return self.line_units[i]
            return []
        return self._editor_line_units(row)

    def _editor_unit_under_pointer(self, event):
        """
        メモ欄で、ポインタの下にある語の単位を返す。

        形態素解析の単位が取れない場合は、その場で作った暫定の単位を
        返す。半角の英数字・記号（md@k のような文字列）は解析の単位に
        ならないことがあり、そのままだと右クリックしても何も
        起きない（実機で報告された）。そういう箇所でも候補一覧を
        開けるよう、空白で区切った塊を単位として扱う。
        """
        try:
            index = self.editor.index(f'@{event.x},{event.y}')
            row_s, col_s = index.split('.')
            row, col = int(row_s), int(col_s)
        except Exception:
            return None
        # **単位の採りどころは1本**（項目48-RB）——統合／分割の違いは
        # `_units_for_row` の中だけ
        _units = self._units_for_row(row)
        if _units:
            unit = unit_at(_units, col)
            if unit is not None:
                return row, unit
        return self._fallback_unit(row, col)

    def _fallback_unit(self, row, col):
        """
        解析の単位が無い位置で、空白区切りの塊を単位に仕立てる。

        「拾う」「かなに開く」など、解析結果に依らない操作も
        あるので、単位が取れないことを理由に何も出さないのは避ける。
        """
        try:
            line_text = self.editor.get(f'{row}.0', f'{row}.end')
        except Exception:
            return None
        if not line_text or col >= len(line_text):
            return None
        if line_text[col].isspace():
            return None
        start = col
        while start > 0 and not line_text[start - 1].isspace():
            start -= 1
        end = col
        while end < len(line_text) and not line_text[end].isspace():
            end += 1
        frag = line_text[start:end]
        if not frag.strip():
            return None
        return row, {
            'start': start, 'end': end,
            'text': frag, 'base': frag,
            'reading': '', 'prev': '', 'next': '',
            'kind': 'plain', 'detail': None,
        }

    def _halfwidth_candidates(self, text):
        """
        半角のまま打ってしまった文字列を、かなに直した候補にする。

        `qyb@kzut@l` のような半角の塊は形態素解析の単位にならず、
        同音異義語も打ち間違いも探しようがないので、通常の候補づくり
        では何も出ない（実機で「反応しない」と報告された）。
        かな入力のまま半角で打った場合と、ローマ字で打った場合の
        両方を試し、読めるものだけを候補として並べる。

        halfwidth_to_kana / romaji_to_kana は
        **(変換後の文字列, 変換できた文字数, 対象だった文字数)** を返す。
        文字列だけが返ると思い込んで使うと、タプルがそのまま
        候補として並んでしまう（実機で「たんこ゛のつなか゛り 10 10」
        と表示された原因）。
        """
        out = []
        if not text or not text.strip():
            return out
        # 半角英数記号だけの塊にしか意味が無い処理なので、
        # 全角が混ざっていれば何もしない
        if any(ord(c) > 0x7f for c in text):
            return out

        try:
            from halfwidth import (halfwidth_to_kana, romaji_to_kana,
                                   kana_to_kanji_where_possible,
                                   makes_sense_as_japanese)
            from morphology import normalize_marks
        except Exception:
            return out

        seen = set()

        def push(kana, kind):
            if not kana or kana == text or kana in seen:
                return
            seen.add(kana)
            out.append({'surface': kana, 'reading': kana, 'kind': kind})

        for conv in (halfwidth_to_kana, romaji_to_kana):
            try:
                kana, converted, target = conv(text)
            except Exception:
                continue
            if not kana or not target:
                continue
            # ほとんど変換できていないものは、ただの記号列を
            # かな混じりにしただけなので候補にしない
            if converted / target < 0.7:
                continue
            # かな入力では濁点が独立したキーなので、変換結果は
            # 「たんこ゛」のように濁点が離れて出る。1文字に合成する。
            try:
                kana = normalize_marks(kana)
            except Exception:
                pass
            # 日本語として読めないものは出さない。
            # 半角の記号列はたいてい意味のあるかなにならないので、
            # ここで弾かないと無関係な候補で埋まる。
            #
            # ただし短い語（もじの 等）は、含まれる語が少なく
            # 判定が厳しく出るので、全部かなに変換できていれば通す。
            try:
                if len(kana) > 4 and converted == target:
                    pass          # 全部変換できた長い語はそのまま信用する
                elif not makes_sense_as_japanese(kana, self.store):
                    if converted != target:
                        continue
            except Exception:
                pass
            push(kana, 'kana')
            # かなにできたなら、そこから漢字に直せる部分も出す
            try:
                kanji = kana_to_kanji_where_possible(kana, self.store)
            except Exception:
                kanji = None
            if kanji and kanji != kana:
                push(kanji, 'homophone')
        return out

    # ------------------------------------------------------------
    # 候補一覧のいちばん下の説明（項目48-MD・うにさんの指定・2026-08-31）
    # ------------------------------------------------------------
    #
    #   「メニューに『補正候補に品詞の判定を表示する』を追加し、
    #     デフォルトオフ。オンにすると、候補欄の一番下に
    #     『－ 品詞判定 －』の項目が増え、選択範囲の単語が何の品詞に
    #     判定されたか（名詞や動詞など。活用変化しているものはその形で
    #     書く。イ形容詞やナ形容詞など）を書く。（…）
    #     メニューのさらにそのひとつ下に『補正候補に根拠を表示する』を
    #     追加し、デフォルトオフ。『－ 品詞判定 －』の下に
    #     『－ 補正根拠 －』を増やし、3行の内容を入れる」
    #
    #   「上2件は、**なかなか進まない開発を分析するために役立てる**」
    #
    # **候補一覧は3つある**（補正欄・メモ欄／統合・簡易入力）。
    # 同じ組み立てを3回書くと、いつか食い違う（48-GN の教え）ので、
    # ここ1か所で作って3か所から呼ぶ。**足すのはいちばん下**。

    def _analysis_tokenizer(self):
        """説明のための語の割り方（エンジンが見ているのと同じもの）。"""
        fn = getattr(self.store, '_tokenize_fn', None)
        if fn is None:
            try:
                fn = corrector.make_tokenizer(self.store)
                self.store._tokenize_fn = fn
            except Exception:
                return None
        return fn

    @staticmethod
    def _analysis_pair(unit):
        """
        その単位の「**打った文字 → 直した文字**」を取り出す。

        `detail` は3つの一覧のどれでも `(打った, 直した, 種別)` の
        並び（`corrector` が積む形）。補正欄では `unit['text']` が
        直したあと、メモ欄では打ったまま——**どちらでも detail の
        並びは同じ**なので、そこだけを見る。
        """
        d = unit.get('detail')
        if d and len(d) >= 2 and d[0] and d[1]:
            return d[0], d[1]
        base = unit.get('base') or ''
        text = unit.get('text') or ''
        if unit.get('kind') == 'chosen' and base and base != text:
            return base, text
        return text, ''

    def _neighbour_texts(self, row, unit, units_in_row=None):
        """
        その単位の**隣の単位の字**（項目48-RG）。戻り値: (前, 後ろ)。

        「判定できません」しか言えないときに、
        **「隣とひとつづきのかな連続だ」という事実**を添えるための材料。
        判定はしない——`explain._run_neighbour_note` が**1か所**で決める
        （48-GN）。

        単位の並びは呼び手が持っていれば使う（分割表示のメモ欄は
        `_editor_line_units` で組み直した別物なので、`line_units` を
        当てにできない）。無ければ行の単位から拾う。
        """
        units = units_in_row
        if units is None:
            try:
                units = self.line_units[row - 1]
            except Exception:
                return '', ''
        try:
            st, en = unit.get('start'), unit.get('end')
            if st is None or en is None:
                return '', ''
            prev_t = next_t = ''
            for u in units:
                if u.get('end') == st:
                    prev_t = u.get('text') or ''
                elif u.get('start') == en:
                    next_t = u.get('text') or ''
            return prev_t, next_t
        except Exception:
            return '', ''

    @staticmethod
    def _lead_candidate(cands):
        """
        一覧の**筆頭候補**（項目48-RH）。並び順は一覧と同じ
        （`MENU_KINDS`）——**打ち間違いを先に見る**。

        「その候補ならこう」と言うためのものなので、
        **打ち間違いの可能性**が在ればそれを採り、無ければ一覧の頭。
        """
        if not cands:
            return ''
        try:
            for c in cands:
                if c.get('kind') == 'typo' and c.get('surface'):
                    return c['surface']
            order = {k: i for i, (k, _l) in enumerate(MENU_KINDS)}
            best = min(cands,
                       key=lambda c: order.get(c.get('kind'), 99))
            return best.get('surface') or ''
        except Exception:
            return ''

    def _analysis_items(self, row, unit, src_line=None, pair=None,
                        recorded=None, units_in_row=None, cands=None):
        """
        候補一覧のいちばん下に足す説明の行（項目48-MD）。

        「補正候補に品詞の判定を表示する」がオフなら **[]**——
        既定はオフなので、**何も足さない＝今までと同じ画面**。

        row / src_line は「違和感の正体」を測り直すための行の文脈。
        src_line を渡さなければ、その行の解析結果から**打った側の
        行**（`original`）を引く（補正欄には直した文が出ているので、
        そのまま測ると打った文の異様さが見えない）。

        recorded: その行の `odd_reasons`（エンジンが控えた理由）。
            **簡易入力の欄は本体と行が別**なので、あちらは自分の
            控えを渡すこと（`self.line_results` を引くと別の行の
            理由が付く）。
        """
        # **2つの設定は別々**（項目48-OC・2026-09-02・うにさんの指摘
        # 「**メニューで品詞をオフ、根拠をオンにした場合、根拠が
        # 出ません**」）。もとは「品詞がオフなら何も出さない」で
        # 早く帰っていたので、**根拠だけを見たい人が何も見られなかった**。
        # 根拠は品詞の下に並べる形だが、**上が無ければ根拠から始めれば
        # よい**だけで、上に依存する理由は無い。
        try:
            _pos_on = bool(self.settings.get('show_pos_info'))
            _why_on = bool(self.settings.get('show_reason_info'))
        except Exception:
            return []
        if not (_pos_on or _why_on):
            return []

        items = []
        if _pos_on:
            items.append((ANALYSIS_HEAD_POS, None))
            # **Shift+左右で範囲を変えたときは「判定できません」**
            # （うにさんの指定）。切れ目に揃っていない範囲の品詞を
            # 名乗るのは、判定ではなく当てずっぽうになる。
            if unit.get('resized'):
                items.append(('  判定できません', None))
            else:
                fn = self._analysis_tokenizer()
                try:
                    # store＝カタカナ語のかな書きの言い切り／
                    # pos_hint＝1字の助詞を行の文脈の品詞で言う
                    # （どちらも項目48-PW・2026-09-04）
                    # **隣とひとつづきである事実**を添える材料
                    # （項目48-RG。品詞は言わない）
                    _pv, _nx = self._neighbour_texts(row, unit,
                                                     units_in_row)
                    lines = explain.pos_lines(
                        unit.get('text') or '', fn, store=self.store,
                        pos_hint=unit.get('pos') or '',
                        infl_hint=unit.get('infl') or '',
                        # 行の解析が手を加えずに1語と見たか（48-QC）
                        atomic_hint=bool(unit.get('atomic')),
                        known_hint=bool(unit.get('known')),
                        prev_text=_pv, next_text=_nx,
                        # **固有名詞を信用してよいか**を①と同じ材料で
                        # 見るために要る（項目48-RN）
                        dict_index=self.dict_index)
                except Exception:
                    lines = [explain.UNKNOWN_POS]
                for ln in lines:
                    items.append((f'  {ln}', None))
                # ★★ **判定できないなら、候補の側で言えることを言う**
                # （項目48-RH）。一覧に既に並んでいる筆頭候補を借りて
                # 1行だけ足す。**新しい判定は作らない**——janome に
                # 聞くだけ（48-GN）。候補が無ければ1行も増えない。
                if lines and all(explain.UNKNOWN_POS in x for x in lines):
                    _lead = self._lead_candidate(cands)
                    _cp = explain.candidate_pos_line(_lead, fn)
                    if _cp:
                        items.append((f'  候補「{_lead}」なら {_cp}',
                                      None))

        if not _why_on:
            return items

        typed, fixed = pair if pair is not None else self._analysis_pair(unit)
        # **補正根拠は、補正した単語にだけ**（うにさんの指定・2026-08-31）:
        # 「補正根拠の項目は、補正した単語にだけ表示して、そうでない
        #   ものは**項目ごと省きます**」。
        # 直していない語に「補正はしていない（印だけ）」と書いても、
        # 見出しの分だけ一覧が伸びるだけで何も分からない。
        # Shift+左右で作り替えた範囲も、そこに補正は無いので同じ。
        if unit.get('resized') or not fixed or fixed == typed:
            return items
        # **エンジンが控えた「なぜ異様と見たか」**（項目48-MD）。
        # 在るならそれを使う——判定を立てた当人の言葉なので、
        # 画面で測り直すと食い違う（48-GN）。
        if recorded is None and src_line is None:
            try:
                _res = self.line_results[row - 1] or {}
                recorded = _res.get('odd_reasons')
                src_line = _res.get('original')
            except Exception:
                pass
        items.append((ANALYSIS_HEAD_WHY, None))
        try:
            fn = self._analysis_tokenizer()
            rows = explain.reason_lines(
                typed, fixed, unit=unit, line=src_line or '',
                input_method=self.settings.get('input_method'),
                tokenize_fn=fn, store=self.store,
                dict_index=self.dict_index, choices=self.choices,
                recorded=recorded)
        except Exception:
            rows = [explain.NO_ODD_REASON, explain.NO_HAND_REASON]
        for ln in rows:
            items.append((f'  {ln}', None))
        return items

    def _odd_span_at(self, row, start, end):
        """
        **その位置に立っている紫の範囲**（項目48-QK・2026-09-05）。

        画面に実際に塗ってある `odd` タグを引く——`line_results` の
        `odd_spans` ではなく**塗った結果**を見るのは、統合表示で
        自動反映した行では原文の位置と画面の位置がずれるため
        （`_render_marks` は そのとき紫を塗らない）。**見えている
        紫だけを対象にする**、で1本にする（48-GN）。

        戻り値: (始まりの列, 終わりの列, その文字列) か None。
        **1字の範囲は返さない**——`decisions.protect` が
        「1文字の語を守ると、それを含む広い範囲まで巻き添えで
        補正できなくなる」として受け付けないので、出しても押せない。
        """
        if not row or start is None or end is None:
            return None
        try:
            idx = f'{row}.0'
            while True:
                rng = self.editor.tag_nextrange('odd', idx, f'{row}.end')
                if not rng:
                    return None
                a, b = str(rng[0]), str(rng[1])
                ca = int(a.split('.')[1])
                cb = int(b.split('.')[1])
                if ca < end and start < cb:
                    if cb - ca < 2:
                        return None
                    return (ca, cb, self.editor.get(a, b))
                idx = b
        except Exception:
            return None

    def _odd_menu_items(self, row, src_start, src_end):
        """
        **紫の印の項目**（項目48-RF・2026-09-05）。
        `src_start`/`src_end` は**元のテキスト（メモ欄）の上の列**。

        **紫の項目を組むのは、ここ1本**（48-GN）。メモ欄の一覧
        （`_editor_dropdown_items`）も、補正欄の一覧（`_open_dropdown`）も
        ここを呼ぶ——2か所に書き写すと、いつか文言と保存先が食い違う。

        紫の**出どころは editor に塗った `odd` タグの1本のまま**
        （`_odd_span_at`。補正欄には紫を塗らない）。補正欄から呼ぶときは
        呼び手が**列を元テキストへ写して**から渡す。

        当たらなければ空の一覧（＝一覧に何も足さない）。
        """
        _odd = self._odd_span_at(row, src_start, src_end)
        if not _odd:
            return []
        _odd_text = _odd[2]
        # **文言は「紫を付けない」だけ**（項目48-QU）。補正は
        # 止めない——止める台帳（`protect`）と分けたので、
        # 書いてあるとおりのことだけが起きる。
        return [
            ('― 紫の印 ―', None),
            ('  この文字列は正しい（今後、紫を付けない）',
             lambda w=_odd_text: self._leave_odd_alone(w)),
        ]

    def _autofix_menu_items(self, row, span, w=None):
        """
        自動反映した箇所に出す「― 自動補正 ―」の並び。

        **メモ欄と簡易入力で同じものを出す**（48-GN——欄ごとに
        並びを書き分けると、いつか食い違う）。欄の指定は `w`
        だけで、ラベルも順番も `_undo_autofix` の呼び方も共通。

        span: `autofix_span_at` の戻り (開始, 終了, 種類, 元の語)。
        None や元の語が空なら何も出さない。
        """
        if span is None or not span[3]:
            return []
        _before = span[3]
        items = [('― 自動補正 ―', None)]
        items.append((f'  ↺ 元の入力に戻す（{_before}）',
                      lambda r=row, s=span: self._undo_autofix(r, s, w=w)))
        if span[2] == 'fixed':
            items.append(
                (f'  この補正は不要（{_before} のまま）',
                 lambda r=row, s=span: self._undo_autofix(r, s, w=w)))
            items.append(
                (f'  「{_before}」は今後直さない',
                 lambda r=row, s=span, o=_before:
                 (self._undo_autofix(r, s, forget=False, w=w),
                  self._protect_word(o))))
        else:
            items.append(
                (f'  「{_before}」の選び直しを取り消す',
                 lambda r=row, s=span: self._undo_autofix(r, s, w=w)))
        return items

    def _editor_dropdown_items(self, row, unit, units_in_row=None):
        """
        メモ欄の候補一覧の**中身**を組み立てる（開かずに）。

        `_open_editor_dropdown`（実際に開く）と、行き先の先読み
        （`_f2_peek`・項目48-KD「候補が出ないところはその奥の範囲に
        薄い色を」）が**同じもの**を見る。「開くかどうか」の判定
        （`len(items) <= 1`）を2か所に書かないための切り出し
        （48-GN の教え「同じ判定をもう一度書くと、いつか食い違う」）。
        """
        if units_in_row is None:
            try:
                units_in_row = self.line_units[row - 1]
            except Exception:
                units_in_row = None
        near = self._unit_surroundings(unit, units_in_row)

        if unit.get('kind') == 'range' and unit.get('segments'):
            cands = build_range_candidates(
                unit['segments'], self.store, find_known_readings_flex,
                dict_index=self.dict_index,
                context_vec=self.context_vec, surrounding_words=near,
                attested=getattr(self, '_attested_surfaces', None))
        elif unit.get('functional'):
            # **助詞・活用語尾だけの単位に、補正候補は出さない**
            # （項目48-GL）。`の` を押すと
            # `ノア／のく／熨斗／乗せ／のち／乗っ／ノド／伸び／ノ`
            # と9件出ていた（うにさんの「候補も大げさ」）。
            # 記号の候補・元に戻す・引用は下でそのまま足される。
            # **3字以上のかなの塊には「漢字にする」候補だけ出す**
            # （項目48-KC。門は `_functional_kanji_cands` の1か所）。
            cands = self._functional_kanji_cands(unit, near)
        else:
            cands = build_candidates(
                unit['base'], unit['reading'],
                self.store, find_known_readings_flex,
                dict_index=self.dict_index,
                context_vec=self.context_vec,
                surrounding_words=near,
                attested=getattr(self, '_attested_surfaces', None))

        # ★★ **紫のかな連続の中の単位には、連続まるごとの候補を先に**
        # （項目48-SF・2026-09-06）。`たぶいごうして` の `たぶい` に
        # `舞台` を出しても `舞台ごうして` は成立しない——候補は
        # **残りと組めるもの**でなければならない。連続まるごとの候補
        # （`タブ移動して`）は、選ぶと連続まるごとが置き換わる（`span`）
        try:
            _run_c = self._odd_run_candidates(row, unit)
        except Exception:
            _run_c = []
        if _run_c:
            cands = _run_c + cands

        # この語が「疑わしい」と判定されていれば、補正エンジンが
        # 既に導き出している提案（detail）を候補の先頭に足す。
        #
        # 「?」のような記号は読みを持たず、build_candidates の探索
        # （読みを起点にした同音異義語・打ち間違い探索）では
        # 何も見つからない。しかし補正エンジン自身は「文頭の?は
        # ・の誤入力」という判断を既に original_spans/details として
        # 持っているので、それをそのまま使わないのはもったいない
        # （実機で「文頭の?を右クリックしても・の候補が出ない」と
        #   報告された）。
        detail = unit.get('detail')
        if detail:
            _typed, corrected_text, _cat = detail
            if corrected_text and corrected_text != unit['text']:
                cands = [{'surface': corrected_text, 'reading': None,
                         'kind': 'homophone'}] + cands

        # 半角のまま打った塊（qyb@kzut@l 等）は、上の探索では
        # 何も見つからない。かなに直した候補を先に足しておく。
        cands = self._halfwidth_candidates(unit['text']) + cands
        # 記号の言い換え（〜 → から）。記号は読みを持たないので、
        # 読みを起点にした探索には一切かからない（2026-08-10）。
        cands = symbol_candidates(unit['text']) + cands

        items = [(f'「{unit["text"]}」', None)]

        # この位置で過去に選び直していれば、「元に戻す」を先頭に出す。
        # unit は毎回テキストから作り直されるため、選び直した後は
        # 「置き換える前が何だったか」を unit 自身からは辿れない。
        # そのため _editor_changes に控えてある履歴を、新しいものから
        # 順にたどって、今回押した箇所と一致するものを探す。
        # ひとつ前だけでなく、それより前の選び直しにも戻れる。
        rec = self._find_change(self._editor_changes, row, unit)
        if rec is not None:
            before = rec['before']
            items.append((f'↺ 元に戻す（「{before}」）',
                          lambda u=unit, r=row, b=before, k=rec:
                              self._editor_undo_choice(r, u, b, k)))

        # この語に**選び直しの記録**があるなら、原文の側からも
        # 取り消せるようにする（うにさんの指定・2026-08-10:
        # 「分割モードのメモ欄からF2で元に戻す候補がありません」）。
        #
        # 分割表示のメモ欄には**打った文字（原文）**が出ている。
        # 統合表示で選び直した記録は、原文のほうを書き換えないので
        # （項目48-A）、メモ欄の語からは「直した痕跡」が見えない。
        # 記録を引き当てて、そこから取り消せるようにする。
        _base = unit.get('base') or unit.get('text') or ''
        try:
            _chosen = self.choices.lookup(_base, unit.get('prev', ''),
                                          unit.get('next', ''))
        except Exception:
            _chosen = None
        if _chosen and _chosen != _base:
            items.append(
                (f'↺ 「{_chosen}」への選び直しを取り消す',
                 lambda b=_base, u=unit: self._undo_recorded_choice(b, u)))

        # 統合表示で**自動反映した**語なら、そこから元へ戻す道と、
        # 「今後この補正はしない」を出す（うにさんの指定・
        # 2026-08-10）。本文はもう直った形になっているので、
        # 単位そのものからは「何から直したのか」が分からない。
        # 反映したときの控え（その行に結び付けてある）から引く。
        _auto = self.autofix_span_at(row, unit['start'], unit['end'])
        _now = ''
        if _auto is not None and _auto[3]:
            _now = self.editor.get(f'{row}.{_auto[0]}', f'{row}.{_auto[1]}')
        items.extend(self._autofix_menu_items(row, _auto))

        seen = set()
        # **`samekey` を並べる場所が無かった**（項目48-EF・2026-08-16）。
        #
        # `candidates.symbol_candidates` は `（ → ゆ` `！ → ぬ` を
        # ちゃんと作っていたのに、この並びに `samekey` が無いので
        # **1件も表示されず**、`len(items) <= 1` で候補一覧そのものが
        # 開かなかった。記号を F2 で選ぶと「候補は見つかりません
        # でした」になっていたのはこれ。
        #
        # `probe_c123` の C-4 は `symbol_candidates` を**直に呼んで**
        # 「（ の候補に ゆ」を確かめていたので、緑のまま素通りした
        # （作る側と並べる側の両方があっても、繋がっているとは
        #  限らない。第37回の学びと同じ形）。
        for kind, label in MENU_KINDS:
            rows = [c for c in cands
                   if c['kind'] == kind and c['surface'] != unit['text']
                   and c['surface'] not in seen]
            if not rows:
                continue
            items.append((f'― {label} ―', None))
            for c in rows:
                seen.add(c['surface'])
                items.append((f'  {c["surface"]}',
                              lambda u=unit, r=row, c=c:
                              self._editor_choose_word(r, u, c)))

        # ★★ **紫だけの範囲には「この文字列は正しい」を出す**
        # （項目48-QK・2026-09-05）。うにさんの指定:
        #
        #   「紫を選択して、**個別に紫と指摘することを不要とする学習**
        #     も必要です」
        #
        # 紫は「異様だと判定した」という印（CLAUDE.md ★★）なので、
        # 本人が「これでよい」と言ったならその判定を取り下げる。
        #
        # ★★ 保存先は **`decisions.leave_odd_alone`**（項目48-QU）。
        # 最初は `decisions.protect` に相乗りさせたが、**危ない**:
        # `blocks()` は**部分一致**で止めるので、ここに真っ当な
        # 2〜3字（紫の範囲は `oddness.odd_spans` の形態素の連なり＝
        # **2字がふつうに出る**）を入れると、**それを含む行の補正が
        # 全部止まる**。`protect` に食わせていたのは今まで
        # 「打ち間違いの塊」だけだったので網が危険側に効かなかった。
        # 台帳を分け、**紫を下げる口にだけ混ぜる**。
        # 48-KO の `left_alone_texts` → `_odd_spans_for_line` が
        # **紫を消す仕組みを既に持っている**ので、足りないのは入口だけ。
        # 補正が入った範囲には紫が付かない（`_render_marks` が重なりを
        # 落とす）ので、ここに来るのは**紫だけの範囲**になる。
        items.extend(self._odd_menu_items(row, unit.get('start'),
                                          unit.get('end')))

        # **いちばん下に説明**（項目48-MD）。既定オフなので、
        # 何も足さない＝今までと同じ一覧。
        # 統合表示で自動反映したあとは `detail` が付いていない
        # （本文がもう直った形）ので、控え（`_auto`）から
        # 「打った文字 → 直した文字」を渡す。
        _pair = None
        if _auto is not None and _auto[3]:
            _pair = (_auto[3], _now)
        items.extend(self._analysis_items(
            row, unit, pair=_pair, cands=cands,
            units_in_row=(units_in_row
                          if units_in_row is not None
                          else self._units_for_row(row))))
        return items

    def _open_editor_dropdown(self, event, row, unit, units_in_row=None):
        """
        メモ欄の語に対する候補一覧を出す。

        選んだ結果はメモ欄のテキストを直接書き換える
        （簡易入力ウィンドウと同じ考え方。補正欄が無いので、
        「別ペインに表示し直す」という選択肢が無い）。

        units_in_row: その行の単位の並び（前後の語を知るために使う）。
            分割レイアウトから F2 で呼ぶ場合、self.line_units は
            補正後の位置を持つ別物なので、呼び出し側が
            メモ欄の上で組み立てたものを渡す。
        """
        # 開き方の既定は「F2 以外」。F2 から開くときは、このあと
        # _show_unit_candidates が True に上書きする。
        self._dropdown_via_f2 = False
        items = self._editor_dropdown_items(row, unit, units_in_row)

        if len(items) <= 1:
            self.status.config(
                text=f'「{unit["text"]}」の候補は見つかりませんでした')
            return

        try:
            bbox = self.editor.bbox(f'{row}.{unit["start"]}')
            if bbox:
                x = self.editor.winfo_rootx() + bbox[0]
                y = self.editor.winfo_rooty() + bbox[1] + bbox[3]
            else:
                raise ValueError
        except Exception:
            x, y = event.x_root, event.y_root + 12
        self._make_dropdown(items, x, y)

    # 選び直しの履歴に残す件数の上限。
    # 何度も選び直したときに、古いものからどこまで戻れるかの範囲。
    MAX_CHANGE_HISTORY = 50

    @staticmethod
    def _push_change(stack, record):
        """選び直しの履歴に1件積む（古いものから捨てる）。"""
        stack.append(record)
        if len(stack) > CorrectNoteApp.MAX_CHANGE_HISTORY:
            del stack[0]

    @staticmethod
    def _find_change(stack, row, unit):
        """
        いま押している箇所に当てはまる、選び直しの履歴を探す。

        新しいものから順に見て、行・開始位置・現在の表記が
        すべて一致する最初の1件を返す。同じ箇所を何度も選び直して
        いれば、戻すたびに1つ前、さらに1つ前へと遡れる。
        """
        for rec in reversed(stack):
            if (rec['row'] == row and rec['start'] == unit['start']
                    and rec['after'] == unit['text']):
                return rec
        return None

    def _editor_undo_choice(self, row, unit, before_text, record=None):
        """
        選び直した内容を元に戻す（候補一覧の「元に戻す」）。

        unit は「今」の状態（選び直した後の表記）を指しているので、
        その範囲を before_text に置き換えるだけでよい。
        戻した履歴は取り除く。さらに前の選び直しが残っていれば、
        もう一度「元に戻す」でそこまで遡れる。

        **選び直しの記憶（choices）も取り消す。**
        メモ欄の文字を戻しただけでは、記憶が残っているので
        補正欄は選び直した表記のまま残る（実機で報告・2026-08-10:
        「メモ欄の元気を再度F2から元に戻した場合、補正欄だけが
        元に戻っていない状態になります」）。
        戻すと言われた以上は、次に同じ語を書いたときにも
        戻っていてほしいはずなので、記憶ごと取り消す。
        """
        start = f'{row}.{unit["start"]}'
        end = f'{row}.{unit["end"]}'
        try:
            self.editor.delete(start, end)
            self.editor.insert(start, before_text)
            self.editor.tag_remove('sel', '1.0', 'end')
            self.editor.tag_add('sel', start,
                                f'{row}.{unit["start"] + len(before_text)}')
        except Exception:
            return
        if record is not None and record in self._editor_changes:
            self._editor_changes.remove(record)
        self._forget_chain(before_text, unit)
        self.status.config(text=f'「{unit["text"]}」を元に戻しました')
        self._on_change()

    def _undo_recorded_choice(self, base, unit):
        """
        記録してある選び直しを取り消す（メモ欄の候補一覧から）。

        メモ欄には原文が出ているので、書き換えるものは無い。
        記録を消して解析し直せば、補正欄や統合表示の見せ方が
        元に戻る。
        """
        self._forget_choice(base, unit)
        self.status.config(text=f'「{base}」の選び直しを取り消しました')
        self._analyze()

    def _forget_chain(self, base, unit):
        """
        「元に戻す」で、その箇所に積み上がった選び直しの記録を捨てる。

        同じ箇所を渡り歩いて選び直すと、記録が鎖のように連なる
        （実機の例・2026-08-10）:

            決闘 → 決定 → 結成
            （記録: 決闘→結成 と **決定→結成**）

        元（決闘）へ戻したとき、**途中で経由した語の記録
        （決定→結成）も一緒に捨てる**。残しておくと、次に
        「決定」と書いたときに「結成」が出てきてしまう。
        戻すと言われた以上、その場の学習はまとめて無かったことに
        するのが素直。

        文脈（前後の語）の一致は見ない。渡り歩くと見ている場所に
        よって前後の語がずれ、消し損ねるため（項目48-D と同じ理由）。
        """
        cur = unit.get('text', '') if isinstance(unit, dict) else ''
        self._forget_choice(base, unit, force_all=True)
        if cur and cur != base:
            self._forget_choice(cur, unit, force_all=True)

    def _forget_choice(self, base, unit, force_all=False):
        """
        選び直しの記憶を取り消す（`_reset_choice` の中身と同じ判断）。

        base: 戻したい元の表記（記憶の「見出し」になっている語）

        まずはこの文脈（前後の語）に一致する記録だけを消す。
        使い分け（「明日の｜こうえん｜に行く→公園」と
        「大学で｜こうえん｜を→講演」）を教えてある場合に、
        片方を取り消しただけでもう片方まで失わないようにするため。
        ただし `choices.lookup` は文脈が一致しなくても、その語の
        選び直しが1通りしかなければ引き当てる（弱い一致）。
        消した後にもう一度引き当てを試し、まだ別の表記が返るなら、
        その語の記録をすべて消す。
        """
        if not base:
            return
        self._invalidate_units_cache()
        prev = unit.get('prev', '') if isinstance(unit, dict) else ''
        next_ = unit.get('next', '') if isinstance(unit, dict) else ''
        try:
            if force_all:
                self.choices.forget_all(base)
            else:
                self.choices.forget(base, prev, next_)
                still = self.choices.lookup(base, prev, next_)
                if still and still != base:
                    self.choices.forget_all(base)
            self.choices.save()
            self._invalidate_analysis_cache()
        except Exception:
            pass

    def _odd_run_candidates(self, row, unit):
        """
        **単位が紫のかな連続の中に居るなら、連続まるごとの候補**
        （項目48-SF）。無ければ []。候補は `span`（連続の範囲）と
        `base`（連続の文字列）を持つ——選ぶと連続まるごとが置き換わる
        （`_editor_choose_word` が見る）。
        """
        i = row - 1
        if not (0 <= i < len(self.line_results)):
            return []
        res = self.line_results[i] or {}
        text = res.get('original') or ''
        spans = (list(res.get('odd_spans') or [])
                 + list(res.get('unsure_spans') or []))
        u_s, u_e = int(unit.get('start', -1)), int(unit.get('end', -1))
        if u_s < 0 or u_e <= u_s:
            return []
        _hira = lambda ch: 'ぁ' <= ch <= 'ゖ' or ch == 'ー'
        for sa, sb in sorted(spans, key=lambda q: (q[1] - q[0]), reverse=True):
            try:
                sa, sb = int(sa), int(sb)
            except Exception:
                continue
            if not (sa <= u_s and u_e <= sb) or sb - sa < 4:
                continue
            run = text[sa:sb]
            if not run or not all(_hira(ch) for ch in run):
                continue
            fn = getattr(self.store, '_tokenize_fn', None)
            if fn is None:
                fn = corrector.make_tokenizer(self.store)
                self.store._tokenize_fn = fn
            got = corrector.lu_run_candidates(
                run, self.store, self.dict_index, fn,
                input_method=self.settings.get('input_method'))
            return [{'surface': sf, 'reading': None, 'kind': 'typo',
                     'span': (sa, sb), 'base': run} for sf in got]
        return []

    def _editor_choose_word(self, row, unit, cand):
        """
        統合レイアウトで候補を選んだ。メモ欄を直接書き換える。

        選んだ結果は分割レイアウトと同じ choices に記憶するので、
        レイアウトを切り替えても学習の内容は共通のまま。

        置き換えた内容は _editor_last_change に控えておく。
        再解析で unit は作り直されるため、元の表記は unit からは
        辿れなくなる。次に右クリックしたとき、直前の置き換えと
        同じ箇所であれば「元に戻す」を候補の先頭に出す
        （実機で「右クリックで変更した後、再度右クリックしても
          元に戻すが無い」と報告された）。
        """
        # **連続まるごとの候補**（項目48-SF）は、単位を連続の範囲に
        # 読み替えてから同じ道を通す
        if isinstance(cand, dict) and cand.get('span'):
            try:
                _sa, _sb = int(cand['span'][0]), int(cand['span'][1])
                _base = cand.get('base') or self.editor.get(
                    f'{row}.{_sa}', f'{row}.{_sb}')
                unit = dict(unit, start=_sa, end=_sb, text=_base,
                            base=_base, reading='')
            except Exception:
                pass
        start = f'{row}.{unit["start"]}'
        end = f'{row}.{unit["end"]}'
        if self.unified_autofix_on():
            # 自動反映が効いているときは、本文（原文）は書き換えない。
            # 選んだことを記録するだけにして、画面への反映は
            # 自動反映に任せる。こうしないと**原文のほうが
            # 書き換わって**しまい、分割表示に戻したときに
            # 「選び直した」印（青）も「元に戻す」も出せなくなる
            # （実機で報告・2026-08-10）。
            self._invalidate_units_cache()
            self.choices.record(unit['base'], cand['surface'],
                                self._choice_reading(unit, cand),
                                unit['prev'], unit['next'])
            self.choices.save()
            self._invalidate_analysis_cache()
            self._remember_recent(cand['surface'])
            self.status.config(
                text=f'「{unit["base"]}」→「{cand["surface"]}」に直しました')
            self._analyze()
            return
        new_end = f'{row}.{unit["start"] + len(cand["surface"])}'
        try:
            self.editor.delete(start, end)
            self.editor.insert(start, cand['surface'])
            # 自分で選び直した語は「打った文字」として扱う
            # （項目48-X）。この先も直せるようにしておく。
            self._mark_typed(row, unit['start'],
                             unit['start'] + len(cand['surface']))
            self.editor.tag_remove('sel', '1.0', 'end')
            if getattr(self, '_dropdown_via_f2', False):
                # F2（キーボード）で確定したときは選択を残さず、
                # カーソルだけを置き換えた語の末尾に置く。そのまま
                # 書き続けられるようにするため（うにさんの指定・
                # 2026-08-10。選択が残っていると、次に打った文字で
                # 置き換わってしまう）。
                self.editor.mark_set('insert', new_end)
            else:
                # 右クリックで選んだときは、置き換えた範囲を選択した
                # ままにする（そのままコピーしたい、という要望）。
                self.editor.tag_add('sel', start, new_end)
        except Exception:
            return
        self._invalidate_units_cache()
        # 同じ箇所を続けて選び直した場合は、前の記録を捨てて
        # 元の語からの記録に置き換える（項目48-C）
        _orig = self._supersede_prior_choice(row, unit, cand)
        self.choices.record(unit['base'], cand['surface'],
                            self._choice_reading(unit, cand),
                            unit['prev'], unit['next'])
        self.choices.save()
        self._invalidate_analysis_cache()
        self._remember_recent(cand['surface'])
        self._push_change(self._editor_changes, {
            'row': row, 'start': unit['start'],
            'before': _orig or unit['text'], 'after': cand['surface'],
        })
        self.status.config(
            text=f'「{unit["base"]}」→「{cand["surface"]}」に直しました')
        self._on_change()

    def _on_result_press(self, event):
        # ドロップダウンが開いていれば閉じる。
        # break せずに返して、Text 標準のドラッグ選択を活かす。
        self._close_dropdown()
        self._drag_press(event, self.result_view, False)
        # state='disabled' の Text はそのままではキーボード入力を
        # 受け取れず、Ctrl+C が効かない。クリック時に焦点を移して
        # コピーできるようにする。
        try:
            self.result_view.focus_set()
        except Exception:
            pass

    def _on_result_drag_motion(self, event):
        """
        補正結果欄でのドラッグ中の動き。

        縦方向優位の動きならタッチパネルでのスクロールとみなして
        画面を動かす。横方向優位の動き（語の範囲選択）は、
        ここでは何もせず Text 標準のドラッグ選択に任せる
        （それを _on_result_release が拾って候補を出す）。
        """
        return self._drag_motion(event, self.result_view)

    def _on_result_release(self, event):
        """
        ボタンを離したときに、クリックかドラッグ選択かを判断する。

        - 縦方向優位のドラッグだった場合はスクロールなので、
          候補は出さない（タッチパネルでのスクロール操作との衝突を防ぐ）。
        - ドラッグで範囲が選ばれていれば、その範囲で候補を出す。
          janome の区切りが実態と合わない（ひ/ら/が/なを 等）とき、
          ユーザーが自分で正しい範囲を指定できるようにするため。
        - 選択が無ければ、クリック位置の語で候補を出す。
        """
        if self._drag_release(event, self.result_view):
            self.result_view.tag_remove('sel', '1.0', 'end')
            return

        # --- 語を拾うモード中は、候補を出さずに差し込む ---
        # ドラッグで範囲を選んでいればその範囲、
        # 選んでいなければクリックした語を拾う。
        if getattr(self, '_pick_mode', False):
            selected = ''
            try:
                sel = self.result_view.tag_ranges('sel')
                if sel:
                    selected = self.result_view.get('sel.first', 'sel.last')
            except Exception:
                selected = ''
            hit = self._unit_under_pointer(event)
            unit_text = hit[1]['text'] if hit is not None else ''
            picked = resolve_pick_text(selected, unit_text)
            self.result_view.tag_remove('sel', '1.0', 'end')
            self._pick_insert(picked)
            return 'break'

        # --- ドラッグ選択があるか ---
        try:
            sel_ranges = self.result_view.tag_ranges('sel')
        except Exception:
            sel_ranges = ()
        if sel_ranges:
            try:
                first = str(sel_ranges[0]).split('.')
                last = str(sel_ranges[1]).split('.')
                row1, col1 = int(first[0]), int(first[1])
                row2, col2 = int(last[0]), int(last[1])
            except Exception:
                row1 = row2 = -1
                col1 = col2 = 0
            # 同じ行の中で、1文字以上が選ばれている場合だけ
            # 選び直しの候補を出す。
            # 選択自体は消さずに残す（Ctrl+C でコピーできるように）。
            if row1 == row2 and col2 > col1:
                i = row1 - 1
                if 0 <= i < len(self.line_units):
                    unit = make_range_unit(self.line_texts[i],
                                           self.line_units[i], col1, col2)
                    if unit is not None:
                        self._open_dropdown(event, row1, unit)
                        return 'break'
            # 行をまたぐ選択などは候補を出さないが、
            # 選択はそのまま残してコピーできるようにする
            return

        # --- 通常のクリック ---
        hit = self._unit_under_pointer(event)
        if hit is None:
            return
        row, unit = hit
        self._open_dropdown(event, row, unit)
        return 'break'

    def _open_dropdown(self, event, row, unit):
        """
        語の下に候補一覧を出す（IMEの変換候補・Excelのドロップダウン風）。

        候補の並び順は、
          1. 同音異義語（自動補正が最も苦手な領域なので最優先）
          2. 打ち間違い（隣接キー・脱字・押しすぎ・順序間違い）
          3. かな表記
        自動補正が入った語なら「補正は不要」等の判断もここから伝えられる。
        """
        # 開き方の既定は「F2 以外」（_open_editor_dropdown と同じ）
        self._dropdown_via_f2 = False
        # janome 辞書の読み索引。初回だけ構築に数秒かかる
        if not self.dict_index.ready:
            self.status.config(text='辞書の索引を作成しています…（初回のみ）')
            self.root.update_idletasks()
            self.dict_index.ensure_built()
            self._update_status()

        units_in_row = None
        try:
            units_in_row = self.line_units[row - 1]
        except Exception:
            units_in_row = None
        near = self._unit_surroundings(unit, units_in_row)

        if unit.get('kind') == 'range' and unit.get('segments'):
            # ドラッグ範囲: 漢字の別読み（時=とき/じ）も組み合わせて探す
            cands = build_range_candidates(
                unit['segments'], self.store, find_known_readings_flex,
                dict_index=self.dict_index,
                context_vec=self.context_vec, surrounding_words=near,
                attested=getattr(self, '_attested_surfaces', None))
        elif unit.get('functional'):
            # **助詞・活用語尾だけの単位に、補正候補は出さない**
            # （項目48-GL）。`の` を押すと
            # `ノア／のく／熨斗／乗せ／のち／乗っ／ノド／伸び／ノ`
            # と9件出ていた（うにさんの「候補も大げさ」）。
            # 記号の候補・元に戻す・引用は下でそのまま足される。
            # **3字以上のかなの塊には「漢字にする」候補だけ出す**
            # （項目48-KC。門は `_functional_kanji_cands` の1か所）。
            cands = self._functional_kanji_cands(unit, near)
        else:
            cands = build_candidates(
                unit['base'], unit['reading'],
                self.store, find_known_readings_flex,
                dict_index=self.dict_index,
                context_vec=self.context_vec,
                surrounding_words=near,
                attested=getattr(self, '_attested_surfaces', None))
        cands = symbol_candidates(unit['text']) + cands

        items = []   # (表示する文字列, 選んだときに実行する関数 or None)

        def head(label):
            items.append((label, None))

        head(f'「{unit["text"]}」')
        if unit['kind'] == 'chosen' and unit['base'] != unit['text']:
            items.append((f'  元に戻す（{unit["base"]}）',
                          lambda u=unit: self._reset_choice(u)))

        # 自動補正が掛かっている範囲なら、まず「元の入力に戻す」を出す。
        # 半角のメールアドレスがかなに変換された場合など、
        # 候補から選ぶのではなく元の文字列に戻したいことがあるため。
        if unit['detail'] is not None:
            original_text = unit['detail'][0]
            if original_text and original_text != unit['text']:
                items.append((f'  元の入力に戻す（{original_text}）',
                              lambda o=original_text, c=unit['text']:
                              self._reject_correction(o, c)))

        # **`samekey` を並べる場所が無かった**（項目48-EF・2026-08-16）。
        #
        # `candidates.symbol_candidates` は `（ → ゆ` `！ → ぬ` を
        # ちゃんと作っていたのに、この並びに `samekey` が無いので
        # **1件も表示されず**、`len(items) <= 1` で候補一覧そのものが
        # 開かなかった。記号を F2 で選ぶと「候補は見つかりません
        # でした」になっていたのはこれ。
        #
        # `probe_c123` の C-4 は `symbol_candidates` を**直に呼んで**
        # 「（ の候補に ゆ」を確かめていたので、緑のまま素通りした
        # （作る側と並べる側の両方があっても、繋がっているとは
        #  限らない。第37回の学びと同じ形）。
        for kind, label in MENU_KINDS:
            rows = [c for c in cands
                    if c['kind'] == kind and c['surface'] != unit['text']]
            if not rows:
                continue
            head(f'― {label} ―')
            for c in rows:
                items.append((f'  {c["surface"]}',
                              lambda u=unit, c=c, r=row:
                              self._choose_word(u, c, r)))

        if unit['detail'] is not None:
            original, corrected, _cat = unit['detail']
            head('― 自動補正 ―')
            items.append((f'  この補正は不要（{original} のまま）',
                          lambda o=original, c=corrected:
                          self._reject_correction(o, c)))
            items.append((f'  「{original}」は今後直さない',
                          lambda o=original: self._protect_word(o)))

        # **いちばん下に説明**（項目48-MD）。オンのときは
        # 候補が1つも無い語でも一覧を開く（下の門より前に足す）。
        # ★★ **補正欄からも紫を下ろせるようにする**（項目48-RF・
        # 2026-09-05・うにさんの報告「紫が付いた単語の**補正欄**を
        # クリックしても、紫としない選択肢が出ません」）。
        #
        # 紫は**元のテキストの上に塗ってある**（補正欄には塗らない）
        # ので、クリックした範囲を**元の列へ写して**から引く。
        # 写すのは `_to_original_span`＝`_span_pairs` の**同じ対応表**
        # （48-GN——塗りと一覧で別の対応を持つと食い違う）。
        #
        # **写した先の字が、押した字と一致しなければ出さない**
        # （安全側。当てずっぽうで「この文字列は正しい」を登録する
        # ほど危ないことは無い）。紫は**補正されなかった字**にしか
        # 立たないので、一致するのが正しい姿。
        try:
            _src = self._to_original_span(row, unit.get('start'),
                                          unit.get('end'))
            if _src is not None:
                _res = self.line_results[row - 1]
                _orig = (_res.get('original') or '')[_src[0]:_src[1]]
                if _orig == unit.get('text'):
                    items.extend(self._odd_menu_items(row, _src[0],
                                                      _src[1]))
        except Exception:
            pass
        items.extend(self._analysis_items(row, unit, cands=cands))

        if len(items) <= 1:
            self.status.config(
                text=f'「{unit["text"]}」の候補は見つかりませんでした')
            return

        # 語の直下に出す（取れなければクリック位置の下）
        try:
            bbox = self.result_view.bbox(f'{row}.{unit["start"]}')
            if bbox:
                x = self.result_view.winfo_rootx() + bbox[0]
                y = self.result_view.winfo_rooty() + bbox[1] + bbox[3]
            else:
                raise ValueError
        except Exception:
            x, y = event.x_root, event.y_root + 12
        # 候補が開いている間の Ctrl+C でコピーする対象
        self._dropdown_text = unit['text']
        self._make_dropdown(items, x, y)

    def _make_dropdown(self, items, x, y, parent=None, topmost=False):
        parent = parent or self.root
        dd = tk.Toplevel(parent)
        dd.wm_overrideredirect(True)
        dd.configure(bg=RULE)
        if topmost:
            # 簡易入力ウィンドウ自身が -topmost なので、
            # その子でなくても常に最前面にしないと裏に隠れてしまう
            # （実機で報告された不具合）。
            try:
                dd.attributes('-topmost', True)
            except Exception:
                pass

        # Listbox の width はおおむね半角1文字ぶんが単位なので、
        # 日本語（全角）は2として数えないと右端が見切れる。
        def _disp_width(s):
            w = 0
            for ch in s:
                # 全角の範囲（かな・漢字・全角記号）は2文字ぶん
                if ('\u3000' <= ch <= '\u30ff' or '\u4e00' <= ch <= '\u9fff'
                        or '\uff01' <= ch <= '\uff60'):
                    w += 2
                else:
                    w += 1
            return w

        # **横に広がりすぎないようにする**（項目48-MD）。
        # 説明（品詞判定・補正根拠）は長い行になることがあり、
        # そのまま幅にすると一覧が画面をはみ出す。上限を切っても
        # 中身は消えない（見切れるだけ・上下の選び方も変わらない）。
        width = max(20, min(80, max(_disp_width(t) for t, _ in items) + 3))
        # **いちばん下の説明は、必ず見えるところに置く**（項目48-ML・
        # 2026-08-31。うにさんの画面「品詞判定が出ないものがあります」）。
        # 説明は一覧の**いちばん下**に足すので、これまでの16行で切ると
        # 候補の多い語（`やん` は21項目）では**外に出て、しかも上下キーは
        # 見出しを飛ばすので届かない**。説明が在るぶんだけ伸ばす。
        rows = min(len(items), DROPDOWN_ROWS)
        for _i, (_t, _cb) in enumerate(items):
            if _t in (ANALYSIS_HEAD_POS, ANALYSIS_HEAD_WHY):
                # **説明の塊ぜんぶが見える高さにする**（項目48-QB・
                # 2026-09-04）。以前の「16 ＋ 説明の行数」は、説明の
                # 見出しが**16行目より下から始まる**（候補が16件を
                # 超える）語では足りない——実機の `たぶい` は候補18行
                # ＋品詞判定4行＝22項目に対して 16+4=20 行となり、
                # `い ＝ 名詞` と ※の注記の**2行が画面の外**に出ていた
                # （うにさんの画面・2026-09-04）。見出しがどこから
                # 始まっても下端（説明）まで入る高さ＝項目の総数
                # （上限は今までどおり ROWS_MAX）。品詞判定がオフで
                # 根拠だけオンのとき（項目48-OC）は見出しが
                # ANALYSIS_HEAD_WHY から始まるので、そちらも見る
                # （HEAD_POS だけ見ると根拠が切れたまま伸びない）。
                rows = min(len(items), DROPDOWN_ROWS_MAX)
                break
        lb = tk.Listbox(dd, bg=PANEL, fg=INK, relief='flat',
                        font=('Yu Gothic UI', 10), activestyle='none',
                        selectbackground=EDITOR_SEL_BG, selectforeground=INK,
                        width=width, height=rows,
                        exportselection=False)
        lb.pack(padx=1, pady=1)
        for label, cb in items:
            lb.insert('end', label)
            if cb is None:
                lb.itemconfigure('end', foreground=MUTED)

        def pick(_e=None):
            sel = lb.curselection()
            if not sel:
                return
            cb = items[sel[0]][1]
            if cb is None:
                return
            self._close_dropdown()
            cb()

        lb.bind('<ButtonRelease-1>', pick)
        lb.bind('<Return>', pick)
        lb.bind('<Double-Button-1>', pick)
        # 左右キーで、候補を出している語そのものを前後に移す
        # （うにさんの指定・2026-08-09）。
        #
        # **IME が確定した記号は、これらのキー名で届く**（項目48-EH・
        # 48-IN。`.`＝Delete・`%`＝Left・`'`＝Right・`&`＝Up・`(`＝Down・
        # `!`＝Prior・`"`＝Next）。個別の束縛は `<KeyPress>` より先に
        # 選ばれるので、そのままだと C-1（範囲の後ろへ入れる）へ
        # 届かない。`_ime_first` で包んで、文字なら C-1 に回す。
        lb.bind('<Left>',
                self._ime_first(lambda e: self._on_dropdown_horizontal(-1)))
        lb.bind('<Right>',
                self._ime_first(lambda e: self._on_dropdown_horizontal(1)))

        # Shift+左右で、選んでいる範囲そのものを伸び縮みさせる
        # （IME の変換範囲調整と同じ。うにさんの指定・2026-08-11・C-3）。
        # Tk は修飾つきのほうを細かい型とみなすので、上の <Left> /
        # <Right> とは競合しない。
        lb.bind('<Shift-Left>',
                self._ime_first(lambda e: self._on_dropdown_resize(-1)))
        lb.bind('<Shift-Right>',
                self._ime_first(lambda e: self._on_dropdown_resize(1)))

        # Delete で選んでいる範囲を消す（うにさんの指定・C-2）。
        lb.bind('<Delete>', self._ime_first(self._on_dropdown_delete))
        lb.bind('<BackSpace>', self._on_dropdown_delete)

        # 文字を打ったら、選んでいる範囲の後ろへ入れる
        # （うにさんの指定・C-1）。**いちばん最後に束縛する。**
        # 上の個別の束縛（Return / 矢印 / Delete 等）のほうが
        # 細かい型なので、そちらが優先される。ここへ来るのは
        # 個別の束縛が無い鍵だけで、印字できない鍵は None を
        # 返して素通しする（F2 連打の遡りを殺さないため）。
        lb.bind('<KeyPress>', self._on_dropdown_keypress)

        # 上下キーは、見出し（「－同音の語－」のような選べない項目・
        # cb が None のもの）を飛ばして移動する（実機からの指定・
        # 2026-08-09）。Listbox 標準の上下移動は見出しにも止まるので
        # 置き換える。
        def _move(step):
            n = lb.size()
            if not n:
                return 'break'
            sel = lb.curselection()
            i = sel[0] if sel else (-1 if step > 0 else n)
            j = i + step
            while 0 <= j < n and items[j][1] is None:
                j += step
            if not (0 <= j < n):
                return 'break'   # 端。それ以上は動かさない
            lb.selection_clear(0, 'end')
            lb.selection_set(j)
            lb.activate(j)
            lb.see(j)
            return 'break'

        lb.bind('<Up>', self._ime_first(lambda e: _move(-1)))
        lb.bind('<Down>', self._ime_first(lambda e: _move(1)))

        # PageUp / PageDown で、まとめて飛ばして選ぶ
        # （候補が多いときに上下キーだけでは遠い・うにさんの指定・
        #  2026-08-10）。飛ぶ幅は「一度に見えている行数」に合わせる。
        # 見出し（選べない行）は _move が飛ばしてくれるので、
        # ここは単純に幅ぶん動かすだけでよい。端に着いたら
        # そこで止まる（_move が端を守る）。
        def _page(direction):
            try:
                span = max(1, int(lb.cget('height')) - 1)
            except Exception:
                span = 5
            for _ in range(span):
                if _move(direction) is None:
                    break
            return 'break'

        lb.bind('<Prior>', self._ime_first(lambda e: _page(-1)))
        lb.bind('<Next>', self._ime_first(lambda e: _page(1)))
        dd.bind('<Escape>', lambda e: self._close_dropdown())
        # 焦点が外れたら閉じるが、F2 で選んでいる語の記憶は残す
        # （括弧ボタンを押した瞬間もここを通るため。_close_dropdown 参照）
        lb.bind('<FocusOut>',
                lambda e: self._close_dropdown(keep_target=True))
        # 候補が開いている間でも、ドラッグした範囲をコピーできるようにする。
        # 焦点は候補一覧に移っているので、ここにも割り当てておく。
        copy_target = self._dropdown_text

        def _copy_here(_e=None):
            self._copy_text(copy_target)
            return 'break'

        lb.bind('<Control-c>', _copy_here)
        lb.bind('<Control-C>', _copy_here)
        lb.bind('<Control-Insert>', _copy_here)

        # 置き場所は「基準ウィンドウの中」に収める。
        # 画面全体の大きさで判断すると、マルチディスプレイのときに
        # 隣のディスプレイへ出てしまう（実機で報告された）。
        # 簡易入力ウィンドウから開いた場合は、本体ではなく
        # 簡易入力ウィンドウ自身を基準にする
        # （本体の位置に合わせると、簡易入力ウィンドウの外に
        #   候補が出てしまうことがあるため）。
        dd.update_idletasks()
        w, h = dd.winfo_reqwidth(), dd.winfo_reqheight()
        win_x = parent.winfo_rootx()
        win_y = parent.winfo_rooty()
        win_w = parent.winfo_width()
        win_h = parent.winfo_height()
        if parent is getattr(self, '_quick_win', None):
            # 簡易入力は窓が小さく、窓の中に収めようとすると候補が
            # 文字の上に重なる（実機で「文字を隠す」と報告・
            # 2026-08-09）。候補は常に最前面なので、窓の外
            # （モニターの作業領域の中）へ出してよい。
            area = monitor_work_area(win_x + 10, win_y + 10)
            if area:
                a_l, a_t, a_r, a_b = area
            else:
                a_l, a_t = 0, 0
                a_r = parent.winfo_screenwidth()
                a_b = parent.winfo_screenheight()
            x = max(a_l, min(x, a_r - w))
            if y + h > a_b:
                # 下に入り切らなければ、対象の語の上側に出す
                above = y - h - 24
                y = above if above >= a_t else max(a_t, a_b - h)
        else:
            # 右端・下端がウィンドウからはみ出すなら内側へ寄せる
            x = max(win_x, min(x, win_x + win_w - w))
            if y + h > win_y + win_h:
                above = y - h - 24
                y = (above if above >= win_y
                     else max(win_y, win_y + win_h - h))
        dd.geometry(f'+{int(x)}+{int(y)}')
        try:
            lb.focus_set()
        except Exception:
            pass
        self._dropdown = dd

    def _close_dropdown(self, keep_target=False):
        """
        候補一覧を閉じる。

        keep_target=True のときは、F2 で選んでいる語の記憶
        （_f2_focus_target と色付け）を残す。**候補一覧は焦点を
        失うと閉じる**ので、括弧ボタンをクリックした瞬間にも
        閉じてしまう。そこで消してしまうと、括弧が「いま選んで
        いる語」ではなく別の場所に入る（実機で報告・2026-08-09）。
        記憶は、本文が変わるかカーソルを動かした時点で
        _clear_f2_target が捨てる。
        """
        self._dropdown_owner = None
        if not keep_target:
            self._clear_f2_target()
        dd = self._dropdown
        if dd is not None:
            try:
                dd.destroy()
            except Exception:
                pass
            self._dropdown = None

    def _choice_reading(self, unit, cand, base=None):
        """
        **選び直しを覚えるときの読み**（項目48-QH）。

        `last_choice` の**読みの枠**（同音異義語で最後に選んだ表記）は
        この読みを鍵にする。候補が読みを持たないことがある——F2 の
        一覧に足す `detail` の候補は `'reading': None` で作られる——
        ので、**そのときは語彙に聞く**。

        **決めているのはここ1か所**（48-GN）。`choices.record` を
        呼ぶ場所は5つあり、片方だけに落とすと**そこだけ読みの枠が
        更新されない**（学び22）。
        """
        rd = cand.get('reading') if isinstance(cand, dict) else None
        if rd:
            return rd
        for src in (base, (unit or {}).get('base'), (unit or {}).get('text')):
            if not src:
                continue
            try:
                got = self.store.reading_of(src)
            except Exception:
                got = None
            if got:
                return got
        return None

    def _supersede_prior_choice(self, row, unit, cand,
                                keep_history=False):
        """
        「直前に選び直した語を、さらに別の候補へ選び直した」場合に、
        **前の記録を捨てて、元の語からの記録に置き換える**。

        分割表示の流れで起きる（実機で報告・2026-08-10）:
          1. メモ欄で F2 →「原文」を「元気」に選び直す
             （記録: 原文→元気。メモ欄の文字も元気になる）
          2. 補正欄で、その「元気」をさらに別の語へ選び直す
             （記録: 元気→◯◯）
        このとき **1 の記録（原文→元気）が残ったまま**になる。
        次に「原文」と書くと、捨てたはずの「元気」が出てくる。

        そこで、この行の選び直しの履歴に「いま選び直そうとしている
        語へ変えた記録」があれば、それは今回の選択で上書きされたと
        みなし、
          - 前の記録（原文→元気）を捨て
          - 元の語からの記録（原文→◯◯）を新しく覚える
        ことで、辻褄を合わせる。

        keep_history: 履歴（`_editor_changes`）を残すか。
            **補正欄から選び直した場合は True**。メモ欄の文字は
            書き換わっていないので、「元に戻す（元の語）」の道を
            残しておく必要がある（実機で報告・2026-08-10
            「『結構』に戻す方法がなくなる」）。
            メモ欄から選び直した場合は、その場で新しい履歴を
            積み直すので False でよい。

        戻り値: 置き換えた元の語。無ければ None。
        """
        if row is None:
            return None
        base = unit.get('base') or unit.get('text') or ''
        prior = None
        for rec in reversed(self._editor_changes):
            if rec.get('row') == row and rec.get('after') == base:
                prior = rec
                break
        if prior is None:
            return None
        before = prior.get('before') or ''
        if not before or before == base:
            return None
        # **その語の記録は全部捨てる。** 文脈の一致を見て消す
        # やり方だと、選び直した場所と今いる場所で前後の語が
        # 違ったときに消し損ねる（統合→分割→補正欄と渡り歩くと
        # 実際にずれる）。ここは「この語をどれにするかを選び直した」
        # という場面なので、迷わず全部消してよい。
        try:
            self._invalidate_units_cache()
            self.choices.forget_all(before)
            self.choices.record(before, cand['surface'],
                                self._choice_reading(unit, cand, before),
                                unit.get('prev', ''), unit.get('next', ''))
            self.choices.save()
            self._invalidate_analysis_cache()
        except Exception:
            pass
        if not keep_history:
            try:
                self._editor_changes.remove(prior)
            except ValueError:
                pass
        return before

    def _choose_word(self, unit, cand, row=None):
        """
        語を選び直した。手動による学習として、前後の語とセットで覚える。

        同音異義語は前後の語でしか区別できないため、
        「どの並びの中でこの表記を選んだか」ごと記憶する。

        row: 選び直した語があった行（1始まり）。分かっている場合は、
            選び直し後の表記をその場で再選択する。ドラッグで範囲を
            選んで変換した直後、そのままコピー操作したいという
            要望に応えるため（実機で報告された不具合）。
        """
        self._invalidate_units_cache()
        # 直前にメモ欄で選び直した語をさらに選び直した場合は、
        # 前の記録を捨てて元の語からの記録に置き換える（項目48-C）。
        # **履歴は残す**。メモ欄の文字は書き換わっていないので、
        # そこから「元に戻す（元の語）」を出す道が要る（項目48-D）。
        self._supersede_prior_choice(row, unit, cand, keep_history=True)
        self.choices.record(unit['base'], cand['surface'],
                            self._choice_reading(unit, cand),
                            unit['prev'], unit['next'])
        self.choices.save()
        self._invalidate_analysis_cache()
        # **選び直しは「最後の選択」の枠に入れる**（項目48-QH・
        # 2026-09-05）。かつてここは `demote_homophones` で
        # 「選ばれなかった表記の実績を 0.2 倍」にしていたが、
        # それは回数があってこその仕組みで、回数は廃止した。
        # 枠は上書きなので、**最後に選んだものが必ず勝つ**
        # ——侵食も蓄積も要らない（うにさんの指定・2026-09-05
        # 「同音異義語の一覧表を作成し、最後にどの変換をしたか、
        #   それぞれ履歴1回分記録します」）。
        # **書き込みは上の `self.choices.record(...)` 1本**
        # （枠は `LastChoiceStore` そのもの。ここで二重に書かない）。
        self._remember_recent(cand['surface'])
        self._render_corrected()
        self._update_status()
        # F2（キーボード）で確定したときは選択を残さない
        # （うにさんの指定・2026-08-10）。右クリックのときだけ、
        # そのままコピーできるよう選択し直す。
        if row is not None and not getattr(self, '_dropdown_via_f2', False):
            self._reselect_after_choice(row, unit, cand)
        elif row is not None:
            try:
                self.result_view.tag_remove('sel', '1.0', 'end')
            except Exception:
                pass
        self.status.config(
            text=f'「{unit["base"]}」→「{cand["surface"]}」を'
                 '前後の語と合わせて覚えました')

    def _reselect_after_choice(self, row, unit, cand):
        """
        選び直した直後、置き換わった表記をもう一度選択状態にする。

        _render_corrected はテキスト全体を作り直すため、ドラッグで
        作っていた選択はその時点で失われる。選んだばかりの表記を
        そのままコピーしたい、という要望に応えるため、
        置き換え後のテキストの中から新しい表記を再度探して選択し直す。

        置き換え前の範囲の開始位置を基準に探すことで、同じ表記が
        行内に複数あっても、実際に選び直した箇所に一致させる。
        """
        try:
            text = self.line_texts[row - 1]
        except (IndexError, AttributeError):
            return
        target = cand['surface']
        # 選び直す前、unit があった開始位置に最も近い一致を選ぶ。
        # build_line_units は選び直しを反映した後のテキストを作るため、
        # 前後の文字数が変わっていても、開始位置はおおむね近いままのはず。
        best = None
        idx = text.find(target)
        while idx >= 0:
            if best is None or abs(idx - unit['start']) < abs(
                    best - unit['start']):
                best = idx
            idx = text.find(target, idx + 1)
        if best is None:
            return
        start, end = f'{row}.{best}', f'{row}.{best + len(target)}'
        try:
            self.result_view.tag_remove('sel', '1.0', 'end')
            self.result_view.tag_add('sel', start, end)
        except Exception:
            pass

    def _reset_choice(self, unit):
        """
        選び直しを取り消して、元の表記に戻す。

        まずはこの文脈（前後の語）に一致する記録だけを消す。
        使い分け（「明日の｜こうえん｜に行く→公園」と
        「大学で｜こうえん｜を→講演」）を教えてある場合に、
        片方を取り消しただけでもう片方まで失わないようにするため。

        ただし choices.lookup は文脈が一致しなくても、その語の
        選び直しが1通りしかなければ引き当てる（弱い一致）。
        そのため文脈一致の記録を消しただけでは、別の文脈で
        覚えた記録に引き当たって**元に戻らないことがある**
        （実機で「元に戻すが効かないことがある」と報告された）。
        消した後にもう一度引き当てを試し、まだ同じ表記が返るなら、
        その語の記録をすべて消す。
        """
        base = unit['base']
        self._forget_choice(base, unit)
        self._render_corrected()
        self.status.config(
            text=f'「{base}」の選び直しを取り消しました')

    def _confirm_correction(self, original, corrected, category):
        """
        「この補正で正しい」と言われた。補正後の語の使用実績を増やす。

        補正の根拠になった語をユーザーが認めたということなので、
        以後その語への補正がより確かなものになる。
        """
        reading = None
        if all(is_kana(c) for c in corrected):
            reading = corrected
        else:
            try:
                reading = self.store.reading_of(corrected)
            except Exception:
                reading = None
        if reading:
            self.store.add(reading, corrected, category or 'その他')
            self.store.save()
        # 反対の判断が残っていれば取り消す
        self.decisions.unreject(original, corrected)
        self._reanalyze_all()
        self.status.config(text=f'「{corrected}」を正しい語として覚えました')

    def _reject_correction(self, original, corrected):
        """「この補正は不要」と言われた。この置換だけをやめる。"""
        self.decisions.reject(original, corrected)
        self.decisions.save()
        # 控えを捨てるのは `_reanalyze_all` の仕事（項目48-CO）。
        # ここで既定の `_invalidate_analysis_cache()` を書いても、
        # **いま見ているタブのぶんが残る＝これから引かれる1件が残る**
        # ので、何もしていないのと同じだった。
        self._reanalyze_all()
        self.status.config(
            text=f'「{original}」を「{corrected}」に直すのをやめました')

    def _protect_word(self, word):
        """「この語は正しい」と言われた。今後いっさい触らない。"""
        if not self.decisions.protect(word):
            self.status.config(text=f'「{word}」は短すぎるため登録できません')
            return
        self._after_decision(f'「{word}」は今後補正しません')

    def _leave_odd_alone(self, word):
        """
        **紫の右クリックから「この文字列は正しい」**（項目48-QU）。

        `_protect_word` と**手順は同じ・台帳だけ違う**
        （`decisions.leave_odd_alone` は紫を下げるだけで、補正は
        止めない。理由はあちらの説明）。**同じ手順を書き写さない**
        ため、後片付けは1本にまとめてある（48-GN）。
        """
        if not self.decisions.leave_odd_alone(word):
            self.status.config(text=f'「{word}」は登録できません')
            return
        self._after_decision(f'「{word}」には今後、紫を付けません',
                             answer_changed=False)

    def _after_decision(self, message, answer_changed=True):
        """
        判断を1件書いたあとの後片付け（項目48-QY）。

        `answer_changed`:
            True  **補正の答えが変わる**（`protect`・`reject`）。
                  控えを捨てて全行を検査し直す（48-CO）
            False **印だけ変わる**（`leave_odd_alone`・48-QU）。
                  `blocks()` を通らないので答えは1バイトも変わらない。
                  **控えを捨てる理由が無い**——塗り直すだけ。

        ★★ ここを分けていなかったので、うにさんの画面で
        「**紫を1つ下げると、他の行の補正の色が一度消えて再度つく**」
        が起きていた（2026-09-05）。`_reanalyze_all` が全タブの控えを
        捨てて `_prev_lines` を空にするため、全行が `_blank_result`
        （色の無い仮置き）になった画面が一度出てから塗り直される。

        `_refresh_after_analysis(learn=False)` は頭で紫を全部消して
        同じ呼び出しの中で塗り直すので、**画面が更新されるのは1回**
        ＝ちらつかない。`line_results` は触らないので網掛け・補正色・
        単位はそのまま。**新しい道は1本も作らない**（この呼び方は
        表示メニューの紫の切り替えなどで既に使われている）。
        """
        self.decisions.save()
        if answer_changed:
            self._reanalyze_all()   # 控えを捨てるのはあちらの仕事（48-CO）
        else:
            self._refresh_after_analysis(learn=False)   # 印だけ塗り直す
        self.status.config(text=message)
        # 簡易入力の欄が開いていれば、そちらも解析し直す
        # （学び22——`_reanalyze_all` はメモ欄しか見ない）。
        # 台帳が変わったので、簡易入力の補正も変わりうる。
        if getattr(self, '_quick_text', None) is not None:
            try:
                self._analyze_quick()
            except Exception:
                pass

    def _reanalyze_all(self):
        """
        判断が変わったので、全行を検査し直す。

        **覚えている解析結果は、いま見ているタブのぶんも含めて捨てる**
        （項目48-CO・`keep_current=False`）。ここを既定の
        `keep_current=True` でやると、次の行で `_prev_lines` を空に
        した瞬間に `_analyze` が `_use_analysis_cache` を見に行き、
        **たったいま「もう直さない」と言われた答え**をそのまま拾って
        解析を飛ばす。

        呼ぶ側で `_invalidate_analysis_cache()` を書いても効かない。
        既定は「いま見ているタブのぶんは残す」なので、**残るのは
        まさにこれから引かれる1件**だからである（項目48-M の
        `_remember_tab_results` が解析のたびに入れ直しているので、
        取りこぼしなく必ず当たる）。

        実測（2026-08-13・Xvfb の本物の画面）:
            右クリック →「この補正は不要」→ 判断は decisions.json に
            入るのに、**補正欄は「単語」のまま**。次に1文字打つまで
            変わらない。「今後直さない」も同じ。
            統合表示だけ直っていたのは、本文が書き変わって
            `_on_change` の差分解析に乗るため（別の道）。

        **`_prev_lines` を空にして解析し直す道は、必ずここを通すこと。**
        手で `_prev_lines = []` と書くと、この落とし穴を毎回踏む。
        """
        self._invalidate_analysis_cache(keep_current=False)
        self._prev_lines = []
        self._analyze_cause = '判断が変わった（選び直し・もう直さない等）'
        self._analyze()

    def open_decisions_dialog(self):
        """
        覚えている判断の一覧。間違えて登録したものを取り消せる。

        判断は一度伝えたら二度と覆らない仕組みなので、
        取り消す手段が無いと、誤って登録したときに詰んでしまう。
        """
        dlg = tk.Toplevel(self.root)
        dlg.title('補正の判断')
        dlg.configure(bg=BG)
        dlg.transient(self.root)
        self._place_dialog(dlg, 460, 420)

        tk.Label(dlg, text='「補正しない」と判断した語',
                 bg=BG, fg=INK, font=('Yu Gothic UI', 10, 'bold'),
                 anchor='w').pack(fill='x', padx=16, pady=(16, 2))
        tk.Label(dlg, text='補正結果の色つき部分をクリックすると登録されます。'
                           '選んで「取り消す」で元に戻せます。',
                 bg=BG, fg=MUTED, font=('Yu Gothic UI', 8),
                 anchor='w', justify='left').pack(fill='x', padx=16, pady=(0, 8))

        list_wrap = tk.Frame(dlg, bg=RULE)
        list_wrap.pack(fill='both', expand=True, padx=16)
        listbox = tk.Listbox(list_wrap, bg=PANEL, fg=INK, relief='flat',
                             font=('Yu Gothic UI', 10),
                             selectbackground=EDITOR_SEL_BG,
                             selectforeground=INK, activestyle='none')
        listbox.pack(fill='both', expand=True, padx=1, pady=1)

        rows = []      # (種別, 引数...) を listbox の並びと対応させる

        def refresh():
            listbox.delete(0, 'end')
            rows.clear()
            for e in self.decisions.protected_list():
                rows.append(('protect', e['word'], None))
                listbox.insert('end', f'  [触らない]  {e["word"]}')
            # **紫を付けないだけ**の台帳（項目48-QU）。取り消し口は
            # `unprotect` が両方の台帳を見るので `protect` と同じだが、
            # **種別は分ける**（項目48-QY）——`blocks()` を通らない
            # ＝答えが変わらないので、取り消しも**塗り直すだけ**で済む。
            # 同じ `'protect'` にしていたので、**紫を1つ下ろすのを
            # 取り消しただけで全行解析**になっていた。
            for e in self.decisions.odd_only_list():
                rows.append(('odd_only', e['word'], None))
                listbox.insert('end', f'  [紫を付けない]  {e["word"]}')
            for e in self.decisions.rejected_list():
                rows.append(('reject', e['original'], e['corrected']))
                listbox.insert('end',
                               f'  [直さない]  {e["original"]} → {e["corrected"]}')
            # **最後にどの変換をしたか**の枠（項目48-QH）。
            # 読みの枠（同音異義語）と、語の枠（選び直し）を分けて出す。
            # 前後の語はもう持たないので、そこは書かない。
            for rec in self.choices.all_records():
                rows.append(('choice', rec, None))
                _tag = ('同音の読み' if rec.get('kind') == 'reading'
                        else '選び直し')
                listbox.insert(
                    'end',
                    f'  [{_tag}]  {rec["original"]} → {rec["chosen"]}')
            if not rows:
                listbox.insert('end', '  （まだ登録された判断はありません）')

        def remove_selected():
            sel = listbox.curselection()
            if not sel or not rows:
                return
            i = sel[0]
            if i >= len(rows):
                return
            kind, a, b = rows[i]
            # **答えが変わるか**（項目48-QY）。分岐の前に置く——
            # 分岐の中で束縛すると、種別が増えた日に落ちる
            heavy = True
            if kind == 'protect':
                self.decisions.unprotect(a)
                self.decisions.save()
                self._invalidate_analysis_cache()
            elif kind == 'odd_only':
                # **紫を下げるだけの台帳**（48-QU）を取り消す。
                # `unprotect` は**両方の台帳**を pop するので、
                # **その語が `protect` にも在るなら答えが変わる**
                # ——そのときだけ重い道へ落とす。
                heavy = self.decisions.is_protected(a)
                self.decisions.unprotect(a)
                self.decisions.save()
                if heavy:
                    self._invalidate_analysis_cache()
            elif kind == 'reject':
                self.decisions.unreject(a, b)
                self.decisions.save()
                self._invalidate_analysis_cache()
            else:
                self._invalidate_units_cache()
                self.choices.forget_record(a)
                self.choices.save()
                self._invalidate_analysis_cache()
            refresh()
            if heavy:
                self._reanalyze_all()
            else:
                self._refresh_after_analysis(learn=False)   # 印だけ

        refresh()

        btns = tk.Frame(dlg, bg=BG)
        btns.pack(fill='x', padx=16, pady=12)
        tk.Button(btns, text='取り消す', command=remove_selected,
                  bg=PANEL, fg=INK, relief='flat', bd=1,
                  font=('Yu Gothic UI', 9), padx=12, pady=4,
                  cursor='hand2').pack(side='left')
        tk.Button(btns, text='閉じる', command=dlg.destroy,
                  bg=INK, fg=BG, relief='flat', bd=0,
                  font=('Yu Gothic UI', 9), padx=16, pady=4,
                  cursor='hand2').pack(side='right')

    def _corrected_text(self):
        # 選び直しを反映した表示テキストがあればそれを使う
        if self.line_texts and len(self.line_texts) == len(self.line_results):
            return '\n'.join(self.line_texts)
        return '\n'.join(r['corrected'] for r in self.line_results)

    def _update_status(self):
        """
        語彙件数やjanomeの有無は、常時表示すると場所を取るため出さない。
        値だけは控えておき（将来メニュー等に出したくなった場合のため）、
        ステータス欄は他の操作の一時的な通知にだけ使う。
        """
        n = len(self.store.to_list())
        changed = sum(1 for r in self.line_results if r['changed'])
        from morphology import HAS_JANOME
        self._vocab_count = n
        self._engine_ok = HAS_JANOME
        self._changed_lines = changed

    # ------------------------------------------------------------
    # 語彙の追加
    # ------------------------------------------------------------
    def open_vocab_dialog(self):
        dlg = tk.Toplevel(self.root)
        dlg.title('語彙を追加')
        dlg.configure(bg=BG)
        dlg.transient(self.root)
        self._place_dialog(dlg, 340, 230)
        dlg.grab_set()

        reading_var = tk.StringVar()
        surface_var = tk.StringVar()
        category_var = tk.StringVar(value='IT・PC操作')

        tk.Label(dlg, text='この語を覚えさせます', bg=BG, fg=INK,
                 font=('Yu Gothic UI', 10, 'bold')).pack(anchor='w', padx=16, pady=(16, 10))

        for label, var, hint in [
            ('読み', reading_var, 'ひらがなで（例: もじにゅうりょく）'),
            ('表記', surface_var, '（例: 文字入力）'),
        ]:
            tk.Label(dlg, text=f'{label}  {hint}', bg=BG, fg=MUTED,
                     font=('Yu Gothic UI', 8)).pack(anchor='w', padx=16)
            tk.Entry(dlg, textvariable=var, bg=PANEL, fg=INK, relief='flat',
                     font=('Yu Gothic UI', 11),
                     highlightbackground=RULE, highlightthickness=1
                     ).pack(fill='x', padx=16, pady=(2, 8))

        tk.Label(dlg, text='分類', bg=BG, fg=MUTED,
                 font=('Yu Gothic UI', 8)).pack(anchor='w', padx=16)
        ttk.Combobox(dlg, textvariable=category_var, state='readonly',
                     font=('Yu Gothic UI', 9),
                     values=['IT・PC操作', '仕事・ビジネス', '日常会話',
                             '趣味・ゲーム', '健康・体調', '学業・勉強',
                             '料理・グルメ', 'その他']
                     ).pack(fill='x', padx=16, pady=(2, 12))

        def submit():
            reading = reading_var.get().strip()
            surface = surface_var.get().strip()
            if not reading or not surface:
                messagebox.showinfo(APP_TITLE, '読みと表記の両方を入力してください。', parent=dlg)
                return
            if not all(is_kana(c) for c in reading):
                messagebox.showinfo(APP_TITLE, '読みはひらがなで入力してください。', parent=dlg)
                return
            self.store.add(reading, surface, category_var.get())
            self.store.save()
            dlg.destroy()
            # **`_reanalyze_all` を通す**（項目48-CP）。
            # `self._analyze()` だけでは**何も起きない**。
            # あれは「前回と本文を比べて、変わった行だけ」をやり直す
            # 仕組みで、語を覚えても**本文は1文字も変わらない**ため、
            # 変わった行は0行になる。「覚えました」と出るのに
            # 画面は直らないままだった（Xvfb の本物の窓で実測・
            # 2026-08-13。本物の「覚える」ボタンを押して確かめた）。
            self._reanalyze_all()
            self.status.config(text=f'「{surface}」を覚えました')

        tk.Button(dlg, text='覚える', command=submit,
                  bg=INK, fg=BG, relief='flat', bd=0,
                  font=('Yu Gothic UI', 10), pady=6, cursor='hand2'
                  ).pack(fill='x', padx=16, pady=(0, 16))

    # 「語彙の整理」ダイアログは 2026-08-08 に廃止した（項目45）。
    # 語彙はアプリの頭脳にあたる部分で、予測変換の学習のような
    # 「気軽に消してよいもの」に見える一覧UIは危険が大きく、
    # 使用回数の表示も履歴をのぞかれるようで不愉快、という判断。
    # 誤学習への対処は、補正結果のクリック（この補正は不要）と
    # シード語彙・辞書完全一致ベースの安全機構に任せる。
    # VocabularyStore.remove 自体は残してある（診断・将来の
    # 自動整理で使う）。

    def learn_from_file_dialog(self):
        """
        テキストファイルを読み込んで、そこに含まれる語を一括で覚える。

        自分が普段書いている文章を読ませると、
        使う語彙に合わせた辞書ができあがる。
        """
        try:
            from janome_import import learn_from_file, HAS_JANOME
        except Exception:
            self._need_janome()
            return

        if not HAS_JANOME:
            self._need_janome()
            return

        paths = filedialog.askopenfilenames(
            title='語彙を学習するテキストファイルを選んでください',
            filetypes=[('テキストファイル', '*.txt'), ('すべて', '*.*')])
        if not paths:
            return

        before = len(self.store.to_list())
        self.status.config(text='学習中...')
        self.root.update_idletasks()

        for path in paths:
            learn_from_file(self.store, path)

        self.store.save()
        after = len(self.store.to_list())
        # 語彙が増えた＝答えが変わるので、**全行を解析し直す**
        # （項目48-CP。`self._analyze()` は本文の差分しか見ないので、
        # 本文が変わらないここでは何もしなかった）。
        self._reanalyze_all()
        self.status.config(
            text=f'{after - before} 語を新しく覚えました（合計 {after} 語）')

    def import_dictionary(self):
        """janome の内蔵辞書から、よく使う語を選んで取り込む。"""
        try:
            from janome_import import (import_from_janome, HAS_JANOME,
                                       DEFAULT_MAX_WORDS)
        except Exception:
            self._need_janome()
            return
        if not HAS_JANOME:
            self._need_janome()
            return

        current = len(self.store.to_list())
        msg = (f'janome の辞書から、よく使われる語を約 {DEFAULT_MAX_WORDS} 語'
               '取り込みます。\n')
        if current > DEFAULT_MAX_WORDS * 2:
            msg += (f'\n現在 {current} 語が登録されています。\n'
                    '語彙が多すぎると誤補正の原因になるため、\n'
                    '一度すべて消してから取り込み直します。\n')
        msg += '\n続けますか？'

        if not self.ask_yes_no(msg, yes='取り込む', no='キャンセル'):
            return

        # 語彙が多すぎる場合は作り直す
        if current > DEFAULT_MAX_WORDS * 2:
            from vocabulary import VocabularyStore
            from seed_vocabulary import load_seed
            self.store = VocabularyStore(VOCAB_FILE)
            self.store._by_reading.clear()
            self.store._invalidate_cache()
            load_seed(self.store)

        self.status.config(text='辞書を読み込んでいます...')
        self.root.update_idletasks()

        def progress(n):
            self.status.config(text=f'候補を集めています... {n} 語')
            self.root.update_idletasks()

        added = import_from_janome(self.store, progress=progress)

        if added == 0:
            self.status.config(text='内蔵辞書からは取り込めませんでした')
            messagebox.showinfo(
                APP_TITLE,
                '内蔵辞書から直接取り込むことができませんでした。\n\n'
                '「文章から学習」で、手持ちのテキストファイルから\n'
                '語彙を覚えさせる方法をお使いください。')
            return

        self.store.save()
        total = len(self.store.to_list())
        # 語彙が増えた＝補正の答えが変わるので、全行を解析し直す。
        # **控えも一緒に捨てる**ため `_reanalyze_all` を通す
        # （項目48-CO。手ずから `_prev_lines = []` としていた頃は、
        # 取り込む前の語彙で出した答えをそのまま拾えた）。
        self._reanalyze_all()
        self.status.config(text=f'{added} 語を取り込みました（合計 {total} 語）')

    def _need_janome(self):
        messagebox.showinfo(
            APP_TITLE,
            'この機能には janome が必要です。\n\n'
            'コマンドプロンプトで次を実行してください:\n'
            '    pip install janome')

    def new_file(self):
        """
        新しいタブを開く（Ctrl+N・タブバーの＋）。

        Windows 11 メモ帳と同じく、今の内容はタブとして残るので
        確認ダイアログは出さない。
        """
        self._capture_session()
        self.session.add_tab()
        self._load_active_tab()
        self._schedule_session_save()

    # ------------------------------------------------------------------
    # **ファイルを開く道は、ここ1本にまとめる**（項目48-TP・2026-09-07）。
    #
    # うにさんの指定「**同一のファイルを開いた場合は、タブを増やさず、
    # 重複するタブを表示する**」。判定を1か所に置かないと、
    # 「開く…」では効いて「ドロップ」では効かない、が起きる
    # （**学び22**——門は全部の道に掛ける）。メニューの「開く…」も
    # ドロップ（項目48-TO）も、どちらもこの `_open_paths` を通す。

    @staticmethod
    def _same_file(a, b):
        """2つの道が**同じファイルを指すか**。
        大文字小文字・相対/絶対・短い名前（8.3）・リンクの違いを均す。
        どちらかが空なら False（無題どうしを同じ扱いにしない）。"""
        if not a or not b:
            return False
        try:
            na = os.path.normcase(os.path.abspath(a))
            nb = os.path.normcase(os.path.abspath(b))
        except Exception:
            return a == b
        if na == nb:
            return True                   # ここで大半が決まる（安い）
        # ★ **`realpath` は最後の手段**（項目48-TP'''・2026-09-07）。
        # Windows の `realpath` は**実際にファイルを開いて**本当の道を
        # 聞くので、**切れたネットワークの道では返るまで固まる**
        # （その間、画面ごと止まる）。リンクや短い名前（8.3）で
        # 書き方が違うだけ、という見込みが立つとき——**名前の部分が
        # 同じとき**だけ聞きに行く。
        try:
            if os.path.basename(na) != os.path.basename(nb):
                return False
            return (os.path.normcase(os.path.realpath(a))
                    == os.path.normcase(os.path.realpath(b)))
        except Exception:
            return False

    def _find_tab_by_path(self, path):
        """そのファイルを開いているタブの位置。無ければ None。
        **`_capture_session` のあとで呼ぶこと**——いま編集中のタブの
        道は `self.current_file` に在り、控えへ書き戻して初めて
        `session.tabs` から見える。"""
        for i, tab in enumerate(self.session.tabs or []):
            if self._same_file(tab.get('path'), path):
                return i
        return None

    def _read_text_file(self, path):
        """読めたら (中身, None)、駄目なら (None, 断る理由)。

        文字コードは UTF-8 → CP932 の順（日本語環境で多い順）。
        **テキストでないファイルは開かない**——中身に NUL が混じって
        いれば画像や実行ファイルなので、本文に入れると解析まで
        壊れた文字列に走る。先頭の BOM は落とす（保存は BOM 無しで
        書くので、残すと**開いて保存しただけで1字増える**）。
        """
        if os.path.isdir(path):
            return None, 'フォルダは開けません'
        try:
            with open(path, 'rb') as f:
                raw = f.read()
        except Exception as e:
            return None, str(e)
        if b'\x00' in raw[:8192]:
            return None, 'テキストファイルではないようです'
        for enc in ('utf-8', 'cp932'):
            try:
                text = raw.decode(enc)
            except UnicodeDecodeError:
                continue
            # ★★ **行末を均す**（項目48-TO'・2026-09-07・検品で見つかった退行）。
            # v1.6.0 まではテキストモードで読んでいたので、CR+LF は
            # Python が LF に均していた。ここは**バイナリで読む**
            # （NUL を見て断り、utf-8 → cp932 と２度読むため）ので、
            # **均す人がいない**。
            #
            # 均さないと CR が本文に入り、`_write_to_file` がテキスト
            # モードで書く（LF → CR+LF）ので、**開いて保存し直す
            # だけで行末が CR+CR+LF に増える**（繰り返すたびに１つずつ）。
            # ★★ 打った文字は消えないが、**何もしていないのに利用者の
            # ファイルのバイトが書き換わる**——壊さない ＞ 直る に当たる。
            #
            # `splitlines()` で代用しないこと——垂直タブや改頁でも切るので、
            # テキストモード（CR+LF・CR・LF の３つだけ）より**広く切る**。
            _cr, _lf = chr(13), chr(10)
            text = text.replace(_cr + _lf, _lf).replace(_cr, _lf)
            return (text[1:] if text.startswith('\ufeff') else text), None
        return None, '文字コードが分かりませんでした'

    def _place_in_new_tab(self, path, content):
        """読み込んだ中身を新しいタブに置く（解析と控えの書き出しは呼び手）。

        今のタブが**空の無題**ならそれを使い回す（Windows 11 の
        メモ帳と同じ・2026-08-09）。
        """
        _cur = self.session.current()
        if _cur is not None and not (is_blank(_cur)
                                     and not _cur.get('path')):
            # ★★ **ファイルを開く道は `fresh_tab` を通さない**
            # （項目48-RA・2026-09-05）。うにさんの指定は
            # 「**新規タブ**ができた際、1行目を…」であって、
            # 「開いたファイルに印を付ける」ではない。
            # ここで印を付けると、直後の `self.bookmarks.clear()` と
            # **同じことを2か所で決める**形になり（48-GN）、
            # 空の無題タブを使い回した回には**前の文書の印が別の文書の
            # 行に残る**（★★ 壊さない ＞ 直る）。**素の `new_tab`**。
            self.session.add_tab(new_tab())
        self.bookmarks.clear()
        # ★★ **本文を入れ替える前に、前の文書に結び付いたものを全部下ろす**
        # （項目48-TP''・2026-09-07・検品で見つかった。**打ったものが消える**）。
        # `_load_active_tab`（タブを移る道）は前からここを通っていたのに、
        # **ファイルを開く道は通っていなかった**（学び22——片方だけに置くと、
        # そちらを迂回する）。
        #
        #   `_autofix_reset()`   自動反映の控えと、設計33の仮の記録を確定する。
        #                        残すと**別の文書の行**に対して
        #                        `decisions.reject` が記録される
        #                        （消した覚えのない補正が「今後行わない」になる）
        #   `_clear_f2_target()` F2 で選んだ範囲（行・桁）。残すと、開いた
        #                        ファイルで Delete を1回押しただけで
        #                        **前の文書の桁にあたる範囲がまとめて消える**
        #                        （実測: 1字のはずが6字消えた）
        self._autofix_reset()
        self._clear_f2_target()
        # ★ **前のタブへ当て直す予約を下ろす**（項目48-TP'・2026-09-07・
        # 検品で見つかった）。`_load_active_tab` は「移った先のタブの
        # 見えていた位置」を控えて `after_idle` で当て直す。ところが
        # `_open_paths` は**1つのイベントの中で最後まで走る**ので、
        # 「既に開いているファイル」と「新しいファイル」を一緒に落とすと、
        # 当て直しが回る前に本文が**別の文書**に入れ替わり、
        # **新しいタブが前のタブの行番号へ飛ぶ**（解析の始まる場所もずれる）。
        # 新しく読み込んだ本文には掛からないのが筋。
        self._pending_scroll = 0.0
        self._pending_scroll_top = None

        self.editor.delete('1.0', 'end')
        self.editor.insert('1.0', content)
        # 開いたファイルの中身は「打った文字」ではない（項目48-X）
        self._reset_typed_marks()
        self._pad_blank_lines()
        # ファイルの中身は「既に書かれた行」なので学習済み扱いにする
        # （開くだけで中の語の使用実績が増えるのを防ぐ。復元と同じ理屈）。
        self._learned_lines.update(
            l for l in content.split('\n') if l.strip())
        self.editor.mark_set('insert', '1.0')
        self.editor.edit_reset()
        self.current_file = path
        self._dirty = False
        self._refresh_title()

    def _open_paths(self, paths):
        """ファイルを開く（**開く道はここ1本**・項目48-TP）。

        `paths`: 開きたい道の並び（1つでもよい）。
        既に開いているファイルは**タブを増やさず、そのタブへ移る**。
        読めなかったものは最後にまとめて知らせる（1つずつ止めない）。
        """
        paths = [p for p in (paths or ()) if p]
        if not paths:
            return
        errors = []
        placed = 0
        moved = None
        already = []
        for path in paths:
            # 1件ごとに控える——前の1件で新しいタブを作っているので、
            # ここで書き戻さないと**その中身が次のタブに流れ込む**
            self._capture_session()
            i = self._find_tab_by_path(path)
            if i is not None:
                # ★★ **読み直さない。移るだけ。**（項目48-TP）
                # そのタブにまだ保存していない編集が在るかもしれない。
                # 「同じファイルを開いた」を理由に読み直すと、
                # **打ったものが黙って消える**（★★ 壊さない ＞ 直る）。
                # ディスク側が変わっていても同じ——本人が閉じて
                # 開き直すまでは、画面に在るものが本物。
                # **既に見ているタブだったときは、画面が1ドットも動かない**
                # （`_switch_tab` は同じ位置なら何もせず帰る）。
                # 落としたのに何も起きないように見えるので、**知らせる**
                # （このアプリの決まり——黙って飛ばさない）
                self._switch_tab(i)
                moved = i
                already.append(os.path.basename(path))
                continue
            content, why = self._read_text_file(path)
            if content is None:
                errors.append((path, why))
                continue
            self._place_in_new_tab(path, content)
            placed += 1
        if placed:
            # 解析は**最後の1回だけ**（見えているタブの分。ほかのタブは
            # 裏の道が進める）。控えもここで1回。
            #
            # ★★ **`_analyze` を直に呼ばない**（項目48-TS・2026-09-07）。
            # 解析の前には「メモ全文の文脈語彙を作る」下ごしらえが要り、
            # **行数に比例して重い**（5,000行で 7秒。測った）。主スレッドで
            # やると**その間ずっと画面が固まる**——うにさんの
            # 「動作がだいぶ重いです」（2026-09-06）と同じ形。
            # タブを移る道は**前から**裏のスレッドで下ごしらえしてから
            # 解析していた（`_warm_then_analyze`・2026-08-10）のに、
            # **ファイルを開く道だけ通っていなかった**（学び22）。
            # 同じ入口に通す。控えが温かければ、その場で解析へ進む。
            self._analyze_cause = 'ファイルを開く'
            self._warm_then_analyze()
            self._save_session()
        elif moved is not None:
            self._save_session()
        if already:
            try:
                self.status.config(
                    text=('「%s」は既に開いています' % already[0]
                          if len(already) == 1 else
                          '%d 件は既に開いています' % len(already)))
            except Exception:
                pass
        try:
            self.editor.focus_set()
        except Exception:
            pass
        if errors:
            body = '\n'.join('%s\n  %s' % (os.path.basename(p), why)
                              for p, why in errors[:8])
            if len(errors) > 8:
                body += '\n… ほか %d 件' % (len(errors) - 8)
            messagebox.showerror(APP_TITLE, '開けませんでした:\n\n' + body)

    # ------------------------------------------------------------------
    # **ファイルのドロップを受ける**（項目48-TO・2026-09-07・うにさんの
    # 指定「ファイルをアプリにドロップしたら、新規タブにテキスト情報を
    # 表示する」）。
    #
    # 素の tkinter はドロップを受けられない（`tkdnd` は同梱していないし、
    # **外部ライブラリは増やさない**）。Windows の仕組みで受ける:
    #
    #     DragAcceptFiles → WM_DROPFILES → DragQueryFileW → DragFinish
    #
    # `WM_DROPFILES` は窓の手続きに来るので、**窓を差し替える**必要がある。
    # 生の `SetWindowLongPtrW` ではなく **`SetWindowSubclass`**（comctl32）を
    # 使う——Microsoft の言う安全な差し替え方で、外し方（`RemoveWindowSubclass`）
    # も揃っている。**Tk の手続きは `DefSubclassProc` でそのまま呼ぶ**ので、
    # ドロップ以外は今までどおり。
    #
    # ★ ctypes の罠（実験で踏んだ）: `GlobalAlloc` のように**戻り値の型を
    #   決めないと 64bit のハンドルが切り詰められる**。ここで使う関数は
    #   引数と戻り値を全部書いておく。
    # ★ **コールバックの参照を保つ**（`self._drop_proc`）。手放すと
    #   次のメッセージで落ちる。
    # ★★ **手続きの中から Tk を触らない**（実際に落ちた・2026-09-07）。
    #   この手続きは **Tk がメッセージを配っている最中**に呼ばれるので、
    #   そこから `root.after` を呼ぶと **Tcl に入れ子で入る**ことになり、
    #
    #       Fatal Python error: PyEval_RestoreThread:
    #       the function must be called with the GIL held
    #
    #   でアプリごと落ちる（単独の実験では Tk を触らなかったので通っていた）。
    #   手続きがするのは**受け皿に積むことだけ**。取り出しは時計
    #   （`_drain_drop_queue`）が、ふつうのイベントとして行う。

    _WM_DROPFILES = 0x0233

    def _setup_file_drop(self):
        """窓へファイルを落とせるようにする（Windows のみ）。
        失敗しても**黙って諦める**——落とせないだけで、本体は動く。"""
        if os.name != 'nt':
            return
        if getattr(self, '_drop_proc', None) is not None:
            return          # 2度掛けない（時計も差し替えも取り残される）
        try:
            import ctypes
            import ctypes.wintypes as _wt
            u32 = ctypes.windll.user32
            shell32 = ctypes.windll.shell32
            comctl = ctypes.windll.comctl32
            _LRESULT = ctypes.c_ssize_t
            _UINT_PTR = ctypes.c_size_t
            _DWORD_PTR = ctypes.c_size_t
            SUBCLASSPROC = ctypes.WINFUNCTYPE(
                _LRESULT, _wt.HWND, ctypes.c_uint, ctypes.c_size_t,
                ctypes.c_ssize_t, _UINT_PTR, _DWORD_PTR)
            comctl.SetWindowSubclass.argtypes = [
                _wt.HWND, SUBCLASSPROC, _UINT_PTR, _DWORD_PTR]
            comctl.SetWindowSubclass.restype = _wt.BOOL
            comctl.RemoveWindowSubclass.argtypes = [
                _wt.HWND, SUBCLASSPROC, _UINT_PTR]
            comctl.RemoveWindowSubclass.restype = _wt.BOOL
            comctl.DefSubclassProc.argtypes = [
                _wt.HWND, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t]
            comctl.DefSubclassProc.restype = _LRESULT
            shell32.DragQueryFileW.argtypes = [
                ctypes.c_void_p, ctypes.c_uint, ctypes.c_wchar_p,
                ctypes.c_uint]
            shell32.DragQueryFileW.restype = ctypes.c_uint
            shell32.DragFinish.argtypes = [ctypes.c_void_p]
            shell32.DragAcceptFiles.argtypes = [_wt.HWND, _wt.BOOL]
            u32.GetParent.argtypes = [_wt.HWND]
            u32.GetParent.restype = _wt.HWND
            _MSG = self._WM_DROPFILES

            def _allow_from_lower(h):
                """**管理者として起動していると、ふつうの権限の
                エクスプローラからのメッセージが OS に捨てられる**
                （UIPI）。落としても何も起きないので、この3つだけ通す。
                古い Windows で関数が無ければ黙って諦める。"""
                try:
                    for m in (_MSG, 0x0049, 0x004A):   # DROPFILES/COPYGLOBALDATA/COPYDATA
                        u32.ChangeWindowMessageFilterEx(
                            _wt.HWND(h), ctypes.c_uint(m),
                            ctypes.c_uint(1), None)    # MSGFLT_ALLOW
                except Exception:
                    pass

            def _on_message(hwnd, msg, wparam, lparam, uid, ref):
                if msg != _MSG:
                    return comctl.DefSubclassProc(hwnd, msg, wparam, lparam)
                got = []
                try:
                    n = shell32.DragQueryFileW(wparam, 0xFFFFFFFF, None, 0)
                    for i in range(n):
                        # **必要な長さを先に聞く**（決め打ちの入れ物だと、
                        # 長い道が**黙って切れる**。Windows の道は
                        # `\\?\` 付きで 32,767 字まで在り得る）
                        need = shell32.DragQueryFileW(wparam, i, None, 0)
                        if not need:
                            continue
                        buf = ctypes.create_unicode_buffer(need + 1)
                        if shell32.DragQueryFileW(wparam, i, buf, need + 1):
                            got.append(buf.value)
                except Exception:
                    pass
                finally:
                    try:
                        shell32.DragFinish(wparam)
                    except Exception:
                        pass
                if got:
                    # **ここで Tk を触らない**（上の ★★）。積むだけ。
                    try:
                        self._drop_queue.append(got)
                    except Exception:
                        pass
                return 0

            self._drop_proc = SUBCLASSPROC(_on_message)
            self._drop_comctl = comctl
            self._drop_hwnds = []
            self._drop_queue = []

            def _attach(widget):
                """その窓に差し替えを掛ける。掛けた hwnd の並びを返す。

                **窓は2つある**（Tk の中身と、その外側の枠）。落とす先は
                どちらにもなり得るので両方に掛ける（学び22）。
                """
                out = []
                try:
                    widget.update_idletasks()
                    child = widget.winfo_id()
                    top = u32.GetParent(child) or child
                except Exception:
                    return out
                for h in ([child] if child == top else [child, top]):
                    if h in self._drop_hwnds:
                        continue        # 2度掛けない
                    if comctl.SetWindowSubclass(h, self._drop_proc, 1, 0):
                        shell32.DragAcceptFiles(h, True)
                        _allow_from_lower(h)
                        self._drop_hwnds.append(h)
                        out.append(h)
                return out

            def _detach(hwnds):
                """その窓の差し替えだけ外す（窓を閉じる**前**に呼ぶ）。"""
                for h in list(hwnds or ()):
                    try:
                        comctl.RemoveWindowSubclass(h, self._drop_proc, 1)
                    except Exception:
                        pass
                    if h in self._drop_hwnds:
                        self._drop_hwnds.remove(h)

            self._drop_attach = _attach
            self._drop_detach = _detach
            _attach(self.root)
            if self._drop_hwnds:
                self._drain_drop_queue()      # 時計を回し始める
        except Exception:
            # ★ **掛けた分を外してから諦める**（項目48-TO''）。
            # 途中で転ぶと、差し替えは入ったままコールバックだけ
            # 手放すことになり、**次のメッセージで落ちる**。
            try:
                self._teardown_file_drop()
            except Exception:
                pass
            self._drop_proc = None
            self._drop_hwnds = []
            self._drop_attach = None
            self._drop_detach = None

    # ------------------------------------------------------------------
    # ★★ **窓は本体だけではない**（項目48-TW・2026-09-07・学び22）。
    # 48-TO で掛けたのは本体の窓だけで、**簡易入力ウィンドウへ落としても
    # 何も起きなかった**——同じアプリなのに、窓によって受けたり受けなかったり
    # していた。門・印・設定は**全部の道に掛ける**。
    #
    # 落とした先がどちらでも、行き先は**同じ1本**（`_on_files_dropped` →
    # `_open_paths`）——本体の新しいタブに出す。窓ごとに違う振る舞いを
    # 書かない（48-GN）。

    def _attach_file_drop(self, widget):
        """本体以外の窓にもドロップを掛ける。掛けた hwnd の組を返す。

        仕掛けが無い（Windows でない・48-TO が転んだ）ときは空を返す。
        **閉じるときに `_detach_file_drop` へ渡すこと**——窓が消えたあとの
        hwnd を控えに残すと、Windows がその番号を**別の窓に使い回した**
        あとで外しに行くことになる。
        """
        fn = getattr(self, '_drop_attach', None)
        if fn is None:
            return ()
        try:
            return tuple(fn(widget))
        except Exception:
            return ()

    def _detach_file_drop(self, hwnds):
        """`_attach_file_drop` で掛けた分だけ外す（窓を閉じる**前**に）。"""
        fn = getattr(self, '_drop_detach', None)
        if fn is None or not hwnds:
            return
        try:
            fn(hwnds)
        except Exception:
            pass

    DROP_POLL_MS = 120

    def _drain_drop_queue(self):
        """受け皿に積まれたドロップを取り出して開く（項目48-TO）。

        **窓の手続きからは Tk を触れない**ので、取り出しはここ——
        ふつうの `after` の中＝Tk のイベントとして行う。
        """
        try:
            q = getattr(self, '_drop_queue', None)
            while q:
                self._on_files_dropped(q.pop(0))
        except Exception:
            pass
        try:
            self._drop_after_id = self.root.after(self.DROP_POLL_MS,
                                                  self._drain_drop_queue)
        except Exception:
            self._drop_after_id = None

    def _teardown_file_drop(self):
        """閉じるときに差し替えを外す（後片付け。失敗は無視）。"""
        _id = getattr(self, '_drop_after_id', None)
        if _id:
            try:
                self.root.after_cancel(_id)
            except Exception:
                pass
            self._drop_after_id = None
        proc = getattr(self, '_drop_proc', None)
        comctl = getattr(self, '_drop_comctl', None)
        if not proc or comctl is None:
            return
        for h in (getattr(self, '_drop_hwnds', None) or []):
            try:
                comctl.RemoveWindowSubclass(h, proc, 1)
            except Exception:
                pass
        self._drop_hwnds = []

    def _on_files_dropped(self, paths):
        """落とされたファイルを開く（**開く道は1本**なので `_open_paths`）。"""
        # 開いている一覧は先に閉じる（`_on_tab_right_press` と同じ作法）。
        # 焦点を奪うと `<FocusOut>` が `keep_target=True` で閉じてしまい、
        # **F2 の的が残る**（項目48-TP''）
        try:
            self._close_dropdown()
        except Exception:
            pass
        try:
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()
        except Exception:
            pass
        self._open_paths(list(paths))

    def open_file(self):
        path = filedialog.askopenfilename(
            filetypes=[('テキストファイル', '*.txt'), ('すべて', '*.*')])
        if not path:
            return
        self._open_paths([path])

    def _ask_save_path(self):
        return filedialog.asksaveasfilename(
            defaultextension='.txt',
            filetypes=[('テキストファイル', '*.txt'), ('すべて', '*.*')])

    def _write_to_file(self, path):
        """
        いまの本文を path に書く。書けたら True、駄目なら False
        （理由は `self._save_failed_error` に置く）。

        書き出すのは**原文**（打った文字そのもの）。統合表示で
        自動反映した分は戻して書く（分割表示で保存したときと同じ
        中身になる。補正後がほしいときは「補正結果をコピー」）。
        起動時に用意した末尾の空行は取り除く。
        """
        content = self.editor_source_text().rstrip('\n')
        # 48-VJ: 書き込みが全部成功するまで元ファイルを残す。
        # 同じフォルダで作れば、置き換えが別ドライブを跨がない。
        import tempfile
        import stat
        target = os.path.realpath(path)
        tmp = None
        fd = None
        try:
            mode = None
            if os.path.exists(target):
                mode = stat.S_IMODE(os.stat(target).st_mode)
                if not mode & stat.S_IWRITE:
                    raise PermissionError('読み取り専用のファイルには保存できません')
            fd, tmp = tempfile.mkstemp(prefix='.correctnote-', suffix='.tmp',
                                       dir=os.path.dirname(target))
            stream = os.fdopen(fd, 'w', encoding='utf-8')
            fd = None  # ここからはstreamが閉じる（fdopen失敗時だけ自分で閉じる）
            with stream as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
            if mode is not None:
                os.chmod(tmp, mode)
            os.replace(tmp, target)
            tmp = None
        except Exception as e:
            self._save_failed_error = e
            return False
        finally:
            if fd is not None:
                os.close(fd)
            if tmp is not None:
                try:
                    os.remove(tmp)
                except OSError:
                    pass
        self.current_file = path
        self._dirty = False
        self._refresh_title()
        self.status.config(text=f'保存しました: {os.path.basename(path)}')
        self._save_session()
        return True

    def save_file(self):
        """
        上書き保存。**保存先が無くなっていたら別名保存へ回す。**

        うにさんからの報告（2026-08-11）:「上書き保存に失敗する
        ダイアログが出ることがある。保存先のファイルがなくなって
        いるのでしょうか？ 保存先のファイルを誤って消していること
        はありませんか？」

        **このアプリがユーザーのファイルを消すことは無い。**
        `os.remove` を呼んでいるのは自分の控えだけ
        （vocabulary_restore.json / dict_index.json /
        analysis_cache.json）。ユーザーのファイルに触るのは
        `_write_to_file` の書き込み1か所しかない。

        実際の原因は、**控えに残っている保存先が、いまの PC には
        無い場所**だったこと。session.json のタブが前の PC の
        ユーザーフォルダを指したまま残っており、そのフォルダが
        いまの PC には無い。PC を移ったあと、前から開いていた
        タブをそのまま保存しようとすると必ずこうなる。

        エラーを出して終わりにせず、**別名保存の窓を出す**
        （うにさんの指定）。
        """
        path = self.current_file
        if not path:
            self.save_file_as()
            return

        # 書きにいく前に、保存先のフォルダがあるか見る。
        # 無ければ「消えた」ではなく「別名で保存してください」。
        folder = os.path.dirname(path) or '.'
        if not os.path.isdir(folder):
            self._offer_save_as(
                '保存先のフォルダが見つかりません。\n'
                '別名で保存してください。\n\n'
                f'元の保存先:\n{path}')
            return

        if not self._write_to_file(path):
            self._report_save_failure(path)

    def _report_save_failure(self, path):
        """書き込みに失敗した。場所の問題なら別名保存へ誘導する。"""
        err = getattr(self, '_save_failed_error', None)
        if isinstance(err, OSError):
            # 見つからない・権限が無い・他のアプリが掴んでいる等。
            # どれも「別名で保存する」が正しい逃げ道になる。
            self._offer_save_as(
                'このファイルには保存できませんでした。\n'
                '別名で保存してください。\n\n'
                f'保存先:\n{path}\n\n理由: {err}')
            return
        messagebox.showerror(APP_TITLE, f'保存できませんでした:\n{err}')

    def _offer_save_as(self, message):
        """事情を知らせてから、別名保存の窓を開く。"""
        try:
            messagebox.showinfo(APP_TITLE, message)
        except Exception:
            pass
        self.save_file_as()

    def save_file_as(self):
        """別名で保存。"""
        path = self._ask_save_path()
        if not path:
            return
        if not self._write_to_file(path):
            err = getattr(self, '_save_failed_error', None)
            messagebox.showerror(APP_TITLE, f'保存できませんでした:\n{err}')

    def copy_corrected(self):
        text = self._corrected_text().rstrip('\n')
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        # 統合表示でも、コピーされるのは補正後の内容
        # （自動反映を切っていても、補正の結果を組み立てて渡す）。
        # 以前は統合表示で自動置換をしていなかったため、
        # 「メモの内容をコピーしました」と表現を変えていたが、
        # 項目48-t以降はどちらの表示でも補正後が入る。
        self.status.config(text='補正結果をコピーしました')


# 二重起動を防ぐための印。プロセスが終わるまで持ち続ける必要が
# あるので、モジュールの変数として残す（関数内の変数にすると
# 回収された時点で印が消えてしまう）。
_single_instance_handle = None


def _activate_running_instance():
    """
    既に動いている CorrectNote の窓を前に出す。見つかれば True。

    窓の見分けは「タイトルが CorrectNote（または『… - CorrectNote』）」
    かつ「窓のクラス名が Tk のもの」の両方で行う。タイトルだけだと、
    たまたま同じ名前を含む他のアプリ（ブラウザで開いた
    リポジトリのページ等）を掴んでしまう。
    """
    if sys.platform != 'win32':
        return False
    try:
        import ctypes
        from ctypes import wintypes
        u32 = ctypes.windll.user32
        found = []

        def _match(hwnd):
            if not u32.IsWindowVisible(hwnd):
                return False
            cls = ctypes.create_unicode_buffer(64)
            u32.GetClassNameW(hwnd, cls, 64)
            if not cls.value.startswith('Tk'):
                return False
            n = u32.GetWindowTextLengthW(hwnd)
            if n <= 0:
                return False
            buf = ctypes.create_unicode_buffer(n + 1)
            u32.GetWindowTextW(hwnd, buf, n + 1)
            title = buf.value
            return (title == APP_TITLE
                    or title.endswith(' - ' + APP_TITLE))

        proc_type = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND,
                                       wintypes.LPARAM)

        def _cb(hwnd, _lparam):
            try:
                if _match(hwnd):
                    found.append(hwnd)
                    return False
            except Exception:
                pass
            return True

        u32.EnumWindows(proc_type(_cb), 0)
        if not found:
            return False
        hwnd = found[0]
        SW_RESTORE = 9
        if u32.IsIconic(hwnd):
            u32.ShowWindow(hwnd, SW_RESTORE)
        u32.SetForegroundWindow(hwnd)
        u32.BringWindowToTop(hwnd)
        return True
    except Exception:
        return False


def _claim_single_instance():
    """
    このフォルダの CorrectNote を1つだけにする。

    多重起動すると、同じフォルダの session.json / vocabulary.json を
    双方が書きにいって**保存の取り合い**になる。さらにホットキーは
    RegisterHotKey の仕様で OS が先に登録した1つにしか渡さないため、
    「簡易入力が、いま見ているほうとは別の窓に出る」という
    分かりにくい状態になる（実機で発生・2026-08-09）。

    起動してよければ True。既に動いていれば、そちらを前に出して
    False を返す（呼び出し側はそのまま終了する）。

    印はフォルダごとに分ける。USB などに別のフォルダで持ち出した
    ものは、データも別なので同時に動かしてよい。
    """
    global _single_instance_handle
    if sys.platform != 'win32':
        return True
    try:
        import ctypes
        import zlib
        k32 = ctypes.windll.kernel32
        tag = '%08x' % (zlib.crc32(
            os.path.abspath(app_dir()).lower().encode('utf-8'))
            & 0xffffffff)
        ERROR_ALREADY_EXISTS = 183
        handle = k32.CreateMutexW(None, False, f'Local\\CorrectNote-{tag}')
        if handle and k32.GetLastError() == ERROR_ALREADY_EXISTS:
            _activate_running_instance()
            return False
        _single_instance_handle = handle
        return True
    except Exception:
        # 判定できない環境では、起動を妨げない
        return True


def _set_app_user_model_id():
    """
    **タスクバーで python.exe とまとめられないようにする**（項目48-JR）。

    `.py` のまま起動すると、Windows は「python.exe のアプリ」として
    束ねるので、窓にアイコンを付けてもタスクバーは Python の絵になる。
    自分の名札を先に名乗ると、自分の絵で並ぶ。

    **窓を作る前に呼ぶこと**（あとからでは効かない）。
    exe（`frozen`）では要らない——exe 自身が名札になる。
    """
    if sys.platform != 'win32' or getattr(sys, 'frozen', False):
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            'CorrectNote.CorrectNote')
    except Exception:
        pass        # 名乗れなくても起動は妨げない


def main():
    if not _claim_single_instance():
        return
    _set_app_user_model_id()
    root = tk.Tk()
    CorrectNoteApp(root)
    root.mainloop()


if __name__ == '__main__':
    main()
