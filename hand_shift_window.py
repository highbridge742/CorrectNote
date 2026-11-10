# -*- coding: utf-8 -*-
# CorrectNote — Copyright (C) 2026 Takahashi Yuu
# SPDX-License-Identifier: GPL-3.0-or-later
"""ホームポジションのずれによる続けての打ち違いを戻す候補（かな入力・2026-11-10・うにさんの指定）。

何を戻すか
----------
片手の置き場所が横に1キーずれると、その手で打ったキーが **同じ向きに続けて** 1つずつずれる。もう片方の手のキーは
ずれない。字の単位では2か所・3か所の別々の違いに見えるが、原因は1つ（手のずれ）。

    作った例: たてもの（た｜て｜も｜の）の左手が右へ1つ → ていもの（て｜い｜も｜の）

どうやって
----------
読みをキーの並びにして（濁音は 清音のキー＋゛のキー、小書きは Shift＋同じキー）、
「手（左・右）× 向き（右へ・左へ）× キーの続きの範囲」ごとに、その範囲の中でその手のキーに当たるものを全部、同じ向きに
1つ戻した読みを作る。2キー以上が戻るものだけ（1キーだけの戻しは前からの1キーの打ち違いの道がする）。
候補の数は 1つの読みで数十ほど。2か所を別々に探す探索（数千）より ずっと少ない。

この部品は候補の読みを作るだけ。語として成り立つか・行の費用が下がるか・直すか紫かは、候補を受け取る段
（keyslip_window: 窓・格子・GAIN・FIX_MARGIN）の決まりにそのまま従う。特定の語や文字列には合わせない。

決まり
------
- かな入力だけ（keyslip_window がかな入力の段）。配列は今選ばれている kana_layout.KANA_POSITIONS を読む。
- 既存のファイルは変えない。install() が keyslip_window._variants を外から包み、前からの候補に足すだけ。
  前からの候補と同じ読みは、前からの重みを残す。
- 抜きだけ試す所（drops_only・根拠の弱い ひらがなだけの並び）には足さない。

切り替え: CN_HAND_SHIFT_WINDOW=0 で前のまま。
"""
import os
from functools import lru_cache

WEIGHT = 1.5        # 手のずれ1つの重み（1キーの打ち違い 1.0 より重く、別々の2キー 2.0 より軽く）
MIN_KEYS = 2        # 戻すキーの数の下限（1キーだけは前からの道）
MAX_KEYS = 16       # 読みのキーの数の上限

_orig = {}
STATS = {'calls': 0, 'added': 0}


def _on():
    return os.environ.get('CN_HAND_SHIFT_WINDOW') != '0'


@lru_cache(maxsize=4)
def _tables(stamp):
    """(位置 → 素のキー, 位置 → Shift のキー, キー → (位置, Shift か))。stamp は配列が替わったら作り直すため。"""
    import kana_layout as KL
    shift = set(getattr(KL, '_SHIFT_KANA', ()) or ())
    plain_at, shift_at, where = {}, {}, {}
    for key, pos in KL.KANA_POSITIONS.items():
        pos = tuple(pos[:2])
        if key in shift:
            shift_at.setdefault(pos, key)
        else:
            plain_at.setdefault(pos, key)
        where[key] = (pos, key in shift)
    return plain_at, shift_at, where


def _stamp():
    import kana_layout as KL
    return (tuple(sorted((k, tuple(v[:2])) for k, v in KL.KANA_POSITIONS.items())),
            tuple(sorted(getattr(KL, '_SHIFT_KANA', ()) or ())))


def _left(pos):
    import kana_layout as KL
    edge = getattr(KL, '_SPLIT_LEFT_MAX_STAGGERED', None) or {0: 5, 1: 4, 2: 4, 3: 4}
    return pos[1] <= edge.get(pos[0], 4)


def _restore(key, direction, left, tables):
    """打たれた key が「left の手が direction へ1つずれて打った」ものなら、打ちたかったキー。そうでなければ None。"""
    plain_at, shift_at, where = tables
    hit = where.get(key)
    if hit is None:
        return None
    (row, col), shifted = hit
    want = (row, col - direction)
    if _left(want) != left:
        return None
    return (shift_at if shifted else plain_at).get(want)


def shifted_readings(reading):
    """手のずれを戻した読み {読み: 重み}。reading は ひらがな（と ゛゜）。"""
    import keyslip_window as KW
    if not reading or not all(KW._hira_char(c) or c in '゛゜' for c in reading):
        return {}
    groups = KW._groups(reading)
    flat = KW._flat(groups)
    if not MIN_KEYS <= len(flat) <= MAX_KEYS:
        return {}
    tables = _tables(_stamp())
    out = {}
    for left in (True, False):
        for direction in (1, -1):
            fixed = [_restore(k, direction, left, tables) for _gi, _ki, k in flat]
            spots = [n for n, c in enumerate(fixed) if c is not None]
            # 範囲は「戻るキー」から「戻るキー」まで。間のその手のキーは全部戻す（同じ向きに続けてずれる）
            for a in range(len(spots)):
                for b in range(a + MIN_KEYS - 1, len(spots)):
                    ng = [list(g) for g in groups]
                    for n in spots[a:b + 1]:
                        gi, ki, _k = flat[n]
                        ng[gi][ki] = fixed[n]
                    # ゛゜ のキーの所に字のキーが来る形は、前の字に付かないので そのまま並べる（_compose が決める）
                    restored = KW._compose([tuple(g) for g in ng])
                    # 前の字に付かずに残った ゛゜ は読みにならない
                    if restored and restored != reading and '゛' not in restored and '゜' not in restored:
                        out.setdefault(restored, WEIGHT)
    return out


def _variants(reading, drops_only=False, solo=frozenset(), long=False):
    out = _orig['_variants'](reading, drops_only, solo, long)
    if drops_only or not _on():
        return out
    STATS['calls'] += 1
    try:
        extra = shifted_readings(reading)
    except Exception:
        return out
    if extra:
        out = dict(out)
        for restored, weight in extra.items():
            if restored not in out:
                out[restored] = weight
                STATS['added'] += 1
    return out


def install():
    """包みを掛ける（もう掛かっていれば何もしない）。CN_HAND_SHIFT_WINDOW=0 なら掛けない。"""
    if _orig or not _on():
        return bool(_orig)
    import keyslip_window as KW
    _orig['_variants'] = KW._variants
    KW._variants = _variants
    return True


def uninstall():
    if not _orig:
        return
    import keyslip_window as KW
    KW._variants = _orig.pop('_variants')
