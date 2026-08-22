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
IME の入力方式（かな入力／ローマ字入力）を Windows から取得する。

補正エンジンは「元の打鍵」を推測するとき、かな入力なら JIS かな配列、
ローマ字入力なら QWERTY の隣接キーを見る。この切り替えはメニューから
手動でもできるが、**IME 自身がどちらの方式かを知っている**ので、
Windows ではそれを直接尋ねる（実機からの要望:「ユーザがどちらの
入力で打ったか取得することはできますか？」）。

仕組み: IMM32 の ImmGetConversionStatus が返す変換モードには
IME_CMODE_ROMAN（0x0010）というビットがあり、
  立っている   → ローマ字入力
  立っていない → かな入力
を表す（MS-IME。Google日本語入力等も IMM32 互換層で同じ値を
返すことが多いが、**実機での確認が必須**）。

hotkeys.py・タイトルバーのダークモードと同じく、外部ライブラリを
使わず ctypes で直接呼ぶ。Windows 以外・IMEが閉じている・
取得に失敗した場合は None を返し、呼び出し側は何もしない
（手動設定のまま動く）。

限界:
  - **ペーストは判定できない**。貼り付けられた文字列は、どの
    入力方式で打たれたかという情報を持っていない。
  - IME がオフ（直接入力）の間も判定できない。ただしその間の
    打鍵は半角文字として入り、半角経路（halfwidth.py）が入力
    方式に関係なく拾うので、実害は無い。
"""

import sys

HAS_SUPPORT = sys.platform.startswith('win')

# IMM32 の変換モードビット（imm.h より）
IME_CMODE_ROMAN = 0x0010


def mode_from_conversion(conversion):
    """
    変換モードの値から入力方式を読み取る（純粋関数・テスト用）。

    戻り値: 'romaji' または 'kana'
    """
    return 'romaji' if (conversion & IME_CMODE_ROMAN) else 'kana'


def current_input_method(hwnd):
    """
    そのウィンドウに結び付いた IME の入力方式を返す。

    hwnd: 対象ウィンドウのハンドル（tkinter なら widget.winfo_id()）

    戻り値: 'kana' / 'romaji' / None（判定できない）
        None の場合は呼び出し側で何もしないこと。
        IME が閉じている間（英数直接入力）も None を返す。
        閉じている間の変換モードは前回の値が残っているだけで、
        「いま日本語をどう打っているか」を表さないため。
    """
    if not HAS_SUPPORT or not hwnd:
        return None
    try:
        import ctypes
        imm = ctypes.windll.imm32
        himc = imm.ImmGetContext(hwnd)
        if not himc:
            return None
        try:
            if not imm.ImmGetOpenStatus(himc):
                return None
            conv = ctypes.c_ulong(0)
            sent = ctypes.c_ulong(0)
            if not imm.ImmGetConversionStatus(himc, ctypes.byref(conv),
                                              ctypes.byref(sent)):
                return None
            return mode_from_conversion(conv.value)
        finally:
            imm.ImmReleaseContext(hwnd, himc)
    except Exception:
        return None


# 変換中の文字列を問い合わせるための IMM32 の指定値（imm.h より）
GCS_COMPREADSTR = 0x0001
GCS_COMPSTR = 0x0008
GCS_RESULTREADSTR = 0x0200
GCS_RESULTSTR = 0x0800

# read_composition が返す4つ（項目48-GX で実機から取れた）。
COMPOSITION_FIELDS = (
    ('comp', GCS_COMPSTR),                   # いま未確定の**文字列**
    ('comp_reading', GCS_COMPREADSTR),       # いま未確定の**読み**
    ('result', GCS_RESULTSTR),               # 確定した**文字列**
    ('result_reading', GCS_RESULTREADSTR),   # 確定した文字列の**読み**
)


def composition_active(hwnd):
    """
    そのウィンドウで IME がいま変換（未確定文字の入力）中かを返す。

    hwnd: 対象ウィジェットのハンドル（tkinter なら widget.winfo_id()）

    戻り値: True / False / None（判定できない）
        括弧ボタンが「変換を確定する前の文字の上から押されたか」を
        知るために使う（app.py の _wrap_with_brackets）。変換中に
        括弧を差し込むと、確定した文字は括弧の中へ入るがカーソルも
        中に残るため、確定を後追いで捉えて外へ出す構えをする。
        None のときは呼び出し側で何もしないこと。
    """
    if not HAS_SUPPORT or not hwnd:
        return None
    try:
        import ctypes
        imm = ctypes.windll.imm32
        himc = imm.ImmGetContext(hwnd)
        if not himc:
            return None
        try:
            # ImmGetCompositionStringW は、変換中の文字列の
            # バイト数を返す（バッファ無しで長さだけ聞ける）。
            # 0 より大きければ、いま未確定の文字がある。
            n = imm.ImmGetCompositionStringW(himc, GCS_COMPSTR, None, 0)
            return bool(n and n > 0)
        finally:
            imm.ImmReleaseContext(hwnd, himc)
    except Exception:
        return None


def read_composition(hwnd):
    """
    **変換中／確定した文字列と、その読みを取る**（設計25(甲)）。

    `composition_active` は同じ呼び出しを**長さだけ**で使っている。
    ここは**同じ呼び出しにバッファを渡すだけ**（項目48-GX）。

    hwnd: 対象ウィジェットのハンドル（tkinter なら widget.winfo_id()）

    戻り値: 次の鍵を持つ辞書。取れないものは空文字。
        取得そのものができない（Windows 以外・IME が無い）なら None。

            comp            いま未確定の文字列（**変換すると漢字に変わる**）
            comp_reading    いま未確定の読み（**変換後も残る**）
            result          確定した文字列
            result_reading  確定した文字列の読み（**表記と対で来る**）

    実機で確かめた値（2026-08-20）:

        RESULTSTR      = '奥悠久子帝'
        RESULTREADSTR  = 'ｵｸﾕｸｺﾃｲ'      ←**半角カタカナで返る**

    **読みは `ime_readings.reading_to_hiragana` に通してから使うこと。**
    半角のまま渡すと静かに何とも当たらなくなる。

    > **`ImmGetCompositionStringW` は NUL 終端を付けない。**
    > 返ってきた**バイト数で切って** utf-16-le で読むこと。
    > `create_unicode_buffer().value` で読むと**隣の値を巻き込む**。

    限界（項目48-GX）:
      - **貼り付け・引用には効かない**（未確定を通らない）
      - IME を切っている間も無い
      - **TSF ベースの新しい IME では空のことがある**
        → 空でも落ちない。ただ覚えないだけ。
    """
    if not HAS_SUPPORT or not hwnd:
        return None
    try:
        import ctypes
        imm = ctypes.windll.imm32
        himc = imm.ImmGetContext(hwnd)
        if not himc:
            return None
        out = {}
        try:
            for name, idx in COMPOSITION_FIELDS:
                out[name] = ''
                try:
                    n = imm.ImmGetCompositionStringW(himc, idx, None, 0)
                    if not n or n <= 0:
                        continue
                    raw = ctypes.create_string_buffer(n)
                    got = imm.ImmGetCompositionStringW(himc, idx, raw, n)
                    if got is None or got <= 0:
                        continue
                    out[name] = raw.raw[:got].decode('utf-16-le', 'ignore')
                except Exception:
                    pass    # 1つ取れなくても、ほかは取る
            return out
        finally:
            imm.ImmReleaseContext(hwnd, himc)
    except Exception:
        return None
