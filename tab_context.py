# -*- coding: utf-8 -*-
"""ファイルタブ全体に関わる手がかり（行の補正はタブの他の行を見られないので、ここで渡す・2026-10-26）。

うに 2026-10-26 00:00Z「半角のまま打った文を全角に補正するのは、ファイルタブ内に、平仮名か片仮名が1文字以上ある
場合にする。完全英語環境での誤検知を防ぐため。絵文字が2バイト以上かもしれないので、バイトでは判断しない。」

tab_has_kana(text) は字で見る（バイトは見ない）。correction_entry.correct_line(tab_has_kana=…) が補正の間だけ
値を置き、corrector の半角のまま打った部分の補正（find_halfwidth_runs の段）は False のときだけ掛けない。
None（渡されていない: 試験・1行だけの道具）は今まで通り掛ける。
"""
from contextvars import ContextVar
from contextlib import contextmanager

_TAB_HAS_KANA = ContextVar('correctnote_tab_has_kana', default=None)


def tab_has_kana(text):
    """タブの文字列に平仮名か片仮名（半角の片仮名も）が1字以上あるか。字で数える・バイトでは見ない。"""
    if not text:
        return False
    return any('ぁ' <= c <= 'ゖ' or 'ァ' <= c <= 'ヺ' or c == 'ー'
               or 'ｦ' <= c <= 'ﾟ' for c in text)


@contextmanager
def tab_kana(flag):
    """補正の間、タブにかなが在るか（True／False／None=不明）を置く。"""
    token = _TAB_HAS_KANA.set(None if flag is None else bool(flag))
    try:
        yield
    finally:
        _TAB_HAS_KANA.reset(token)


def halfwidth_correction_allowed():
    """半角のまま打った部分の補正を掛けてよいか。タブにかなが無い（False）ときだけ掛けない。"""
    return _TAB_HAS_KANA.get() is not False
