# CorrectNote — かな入力誤字補正メモ帳
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
