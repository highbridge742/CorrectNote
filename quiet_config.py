# CorrectNote — 誤字補正メモ帳
# Copyright (C) 2026 Takahashi Yuu
# SPDX-License-Identifier: GPL-3.0-or-later
"""見た目が同じならウィジェットの設定を出さない（2026-11-05）。

打鍵1回ごとに、同じ値のボタンの設定が8回、同じ色のタグの設定が4回出ていた。Tk は値が同じでも描き直しを
予約する（タグは掛かっている範囲ぜんぶ）。今の値は控えず、毎回ウィジェットに尋ねる（配色の切り替えなど、
ほかの道で変わっていても見落とさない）。"""


def configure(widget, **options):
    """widget.configure(**options) を、値が変わる時だけ。"""
    try:
        if all(str(widget.cget(name)) == str(value) for name, value in options.items()):
            return False
    except Exception:
        pass
    widget.configure(**options)
    return True


def tag_configure(widget, tag, **options):
    """widget.tag_configure(tag, **options) を、値が変わる時だけ。"""
    try:
        if all(str(widget.tag_cget(tag, name)) == str(value) for name, value in options.items()):
            return False
    except Exception:
        pass
    widget.tag_configure(tag, **options)
    return True
