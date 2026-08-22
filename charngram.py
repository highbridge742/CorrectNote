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
**日本語の「文字の並び」として無理がないか**（項目48-BM）。

うにさんの指定（項目48-AG）:「**メモちょが、というなににも
属さない文字列が修整対象だと分かります**」。

これまで、この判定に4つの道を試して全部だめだった（52〜62%＝
当てずっぽう。項目48-AG）。**語**を見る物差し（珍しさ・連接
コスト・馴染み）では原理的に届かない——おかしいのは**並び**で
あって語ではないため:

    ややて二死確保ぬ  →  やや/て/二/死/確保/ぬ   どの語も普通
    メモちょが        →  メモ/ちょ/が             どの語も辞書にある

**文字の並びで見ると届いた**（項目48-BL）:

    文字3連（このアプリの文書 8万字で学習）  **79.7%**
    語の並び（5万件のコーパス）               61.6%
    馴染みのずれ（UniDic）                    54.1%
    **単語リスト19万語**から作った文字3連     **50.0%**

**単語リストからでは駄目で、文章でないといけない。**
48-AG の「語ではなく並びを見る材料が要る」は正しかったが、
足りなかったのは語の並びではなく**文章そのもの**だった。

**メモから育てる**（うにさんの指定・2026-08-12・項目48-BN）。
同梱ぶん（アプリの文書8万字）だけだと、**うにさんが書くジャンル**
（雑談・ゲーム・実況）では**正しい断片の 9.5% を誤って止める**。
うにさんのメモから 1万字ぶん育てただけで **2.7% まで下がった**。
材料は「**直すところが無かった行**」＝アプリが見て何もおかしく
ないと判断した行だけ。誤字の見本が載っている行（矢印・引用符・
半角英数を含む行）も外す。**育つほど安全になる**向きなので、
敷居は動かさなくてよい。

**使い方は「止める」側だけ。**
点が高いことを「直してよい根拠」にはしない。**点が低いものを
出さない**（出口の検品）ためだけに使う。項目48-AR の教訓:
出口の検品は「**正しく書けている語をどれだけ落とさないか**」で
決まる。あそこは 23.3% を誤判定して却下になった。

敷居の決め方は `MIN_SCORE` の説明を参照。
"""

import hashlib
import json
import math
import os
import re
import sys

_TABLE = None
_CONTEXT = None
_MISSING = False

# 育てたぶんの置き場（実行時に作られる。同梱はしない）
STORE_NAME = 'charngram.json'
_STORE_PATH = None
_LEARNED = None          # {3連: 回数}
_SEEN = None             # 覚えた行の印（二度数えないため・学び20）
_DIRTY = False

# 覚える行の上限。**数えるものには必ず上限を付ける**
# （メモが何万行になっても、置き場が際限なく膨らまないように）。
MAX_SEEN = 200000

# 誤字の見本が載っている行は材料にしない（ngram_ja_build.py と同じ）
_NOT_PROSE = re.compile(r'[→⇒⇔←↔`「」『』"“”\'‘’|*#\[\]{}<>=+\\_~^$%&]'
                        r'|[0-9A-Za-z]')
_JP_RUN = re.compile(r'[ぁ-ヿ一-鿿ー々]+')

# 見たことのない文字の種類ぶんの重み（スムージングの分母）。
# 材料に出る文字は約2,000種。倍を見て 4000 にしてある。
_VOCAB = 4000
_FLOOR = 0.1

# **止める敷居**（項目48-BM）。
#
# 実測（正の材料＝正しい日本語から語の切れ目で取った断片、
# 負の材料＝アプリが作り出した文字列のうち本文に一度も出てこない
# もの。作り方は ngramcheck.py）:
#
#     正しい断片を捨てる割合   何にも属さない文字列を捕まえる割合
#              1%                        14%
#              2%                        14%
#              5%                        37%
#             10%                        45%
#             20%                        74%
#
# **1% の側（-8.3）を採った。** 取りこぼしは我慢できても、
# 正しく書いたものを壊すのは我慢できない、という軸のとおり。
#
# **`メモちょが`（-6.66）はこの敷居では止まらない。** 止めるには
# -6.4 あたりまで開ける必要があり、そこは**正しい断片を2割捨てる**
# ところ（`改行と行の削除` が -6.29、`正確な位置` が -6.28）。
# **いまの材料（8万字）では、そこまでは行けない。**
MIN_SCORE = -8.3


def _data_dir():
    """
    育てたぶんの置き場（`app.py` の `app_dir()` と同じ考え）。

    **exe のときは exe と同じフォルダ。** PyInstaller で固めると
    `__file__` は一時展開先（`sys._MEIPASS`）を指す。そこは
    **終了時に消える**ので、そこへ書いていたぶんは毎回失われ、
    読む側も毎回空から始まっていた。
    ——`familiarity.json` や `kanji_onkun.json` と違って、
    これは**同梱物ではなく育つデータ**なので、
    「読むだけ」の3つとは行き先が違う（項目48-DK の裏返し）。

    `.py` のまま動かしているときは、今までどおりソースと同じ
    フォルダを指す（**答えも置き場も変わらない**）。
    """
    if getattr(sys, 'frozen', False):
        return os.path.dirname(os.path.abspath(sys.executable)) or '.'
    return os.path.dirname(os.path.abspath(__file__)) or '.'


def _store_path():
    global _STORE_PATH
    if _STORE_PATH is None:
        _STORE_PATH = os.path.join(_data_dir(), STORE_NAME)
    return _STORE_PATH


def _read_learned():
    """育てたぶんを読む。壊れていても、無くても、黙って空で始める。"""
    global _LEARNED, _SEEN
    if _LEARNED is not None:
        return
    _LEARNED, _SEEN = {}, set()
    try:
        with open(_store_path(), encoding='utf-8') as f:
            data = json.load(f)
        _LEARNED = {k: int(v) for k, v in (data.get('trigrams') or {}).items()
                    if len(k) == 3}
        _SEEN = set(data.get('lines') or ())
    except Exception:
        _LEARNED, _SEEN = {}, set()


def _rebuild():
    """同梱ぶんと育てたぶんを重ねて、文脈の回数を作り直す。"""
    global _TABLE, _CONTEXT
    table = dict(_SEED or {})
    for g, c in (_LEARNED or {}).items():
        table[g] = table.get(g, 0) + c
    ctx = {}
    for g, c in table.items():
        k = g[:2]
        ctx[k] = ctx.get(k, 0) + c
    _TABLE, _CONTEXT = table, ctx


_SEED = None


def _load():
    global _SEED, _MISSING
    if _TABLE is not None or _MISSING:
        return _TABLE
    try:
        import ngram_ja
        _SEED = ngram_ja.TRIGRAMS
    except Exception:
        _MISSING = True
        return None
    _read_learned()
    # 2連（文脈）の回数は3連から足し上げられる。持たない。
    _rebuild()
    return _TABLE


def learn(line):
    """
    **直すところが無かった行**を、文字の並びの材料にする
    （項目48-BN・うにさんの「アプリの工夫にします」）。

    呼ぶ側は「アプリが何もおかしくないと判断した行」だけを渡すこと。
    ここでもう一度、**誤字の見本が載っている行**（矢印・引用符・
    半角英数を含む行）を外す。

    **同じ行は二度数えない**（学び20）。数え違いを防ぐ仕組みは
    呼ぶ側ではなく**数える側**に付ける。

    戻り値: 新しく数えたら True
    """
    global _DIRTY
    if not line or not line.strip():
        return False
    if _load() is None:
        return False
    if _NOT_PROSE.search(line):
        return False
    # **`hash()` を使わないこと。** Python の文字列の hash は
    # 実行のたびに値が変わる（PYTHONHASHSEED）。使うと
    # **起動のたびに同じ行を数え直す**（学び20 の型そのもの）。
    key = hashlib.blake2s(line.encode('utf-8'), digest_size=6).hexdigest()
    if key in _SEEN:
        return False
    runs = [m.group(0) for m in _JP_RUN.finditer(line)
            if len(m.group(0)) >= 2]
    if not runs:
        return False
    if len(_SEEN) >= MAX_SEEN:
        return False
    _SEEN.add(key)
    for r in runs:
        s = '^^' + r + '$'
        for i in range(len(s) - 2):
            g = s[i:i + 3]
            _LEARNED[g] = _LEARNED.get(g, 0) + 1
            _TABLE[g] = _TABLE.get(g, 0) + 1
            k = g[:2]
            _CONTEXT[k] = _CONTEXT.get(k, 0) + 1
    _DIRTY = True
    return True


def save():
    """育てたぶんを書き出す（変わっていなければ何もしない）。"""
    global _DIRTY
    if not _DIRTY or _LEARNED is None:
        return False
    try:
        with open(_store_path(), 'w', encoding='utf-8') as f:
            json.dump({'version': 1,
                       'trigrams': _LEARNED,
                       'lines': sorted(_SEEN)}, f, ensure_ascii=False)
        _DIRTY = False
        return True
    except Exception:
        return False


def stats():
    """診断用: (同梱ぶんの種類, 育てたぶんの種類, 覚えた行数)"""
    if _load() is None:
        return (0, 0, 0)
    return (len(_SEED or {}), len(_LEARNED or {}), len(_SEEN or ()))


def available():
    """表が読めているか（診断用）。"""
    return _load() is not None


def score(text):
    """
    1文字あたりの対数確率（0に近いほど日本語の並びらしい）。

    表が無ければ 0.0（＝止めない）。**知らないものを勝手に
    止めない**、が既定。
    """
    table = _load()
    if not table or not text:
        return 0.0
    s = '^^' + text + '$'
    total = 0.0
    n = 0
    for i in range(len(s) - 2):
        g = s[i:i + 3]
        total += math.log((table.get(g, 0) + _FLOOR)
                          / (_CONTEXT.get(g[:2], 0) + _FLOOR * _VOCAB))
        n += 1
    return total / max(1, n)


def looks_unnatural(text):
    """
    **日本語の文字の並びとして無理があるか**（止めるときだけ使う）。

    かな・漢字だけの並びに限る。英字・数字・記号が混じるものは
    材料に無いので判断しない（False＝止めない）。
    """
    if not text or len(text) < 2:
        return False
    for ch in text:
        if not ('ぁ' <= ch <= 'ヿ' or '一' <= ch <= '鿿'
                or ch == '々'):
            return False
    if not available():
        return False
    return score(text) < MIN_SCORE
