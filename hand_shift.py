# CorrectNote — 誤字補正メモ帳
# SPDX-License-Identifier: GPL-3.0-or-later
"""
手の位置のずれ（ホームポジションが1列ずれ、同じ手で続けて打つ2〜4打がみな同じ向きの隣のキーになった形）を戻す
読みの候補（2026-11-06・隣キーの巻き込みのサンプル文の試験）。

1打の戻し（key_repairs）は1か所しか戻さないので、2打以上が揃ってずれた行（おせわ → おらよ・かいぎ → かてすう）は
紫のまま直らないか、1打だけ戻した途中までの直しになる。ここでは打った読みを打鍵に開き、同じ手の続く2〜4打を
まとめて同じ段の左か右へ1列戻した読みを作る。決め方（漢字を置く→補正し直し→二番と離れていれば採る）は
呼ぶ側（odd_respell）のまま。特定の語や文字列には合わせない。
"""
MIN_RUN = 2
MAX_RUN = 4

_SMALL = {'ぁ': 'あ', 'ぃ': 'い', 'ぅ': 'う', 'ぇ': 'え', 'ぉ': 'お', 'ゃ': 'や', 'ゅ': 'ゆ', 'ょ': 'よ', 'っ': 'つ'}
_SMALL_OF = {v: k for k, v in _SMALL.items()}


def _kana_table():
    import kana_layout as kl
    at = {}
    for ch, p in kl.KANA_POSITIONS.items():
        if ch in _SMALL or ch == 'を':
            continue
        at.setdefault(p, ch)
    return at, {ch: p for p, ch in at.items()}


def _left_hand(p, row0_max=5, other_max=4):
    return p[1] <= (row0_max if p[0] == 0 else other_max)


def _compose(keys):
    import keystroke_doubt
    return keystroke_doubt._compose_kana(keys)


def kana_repairs(rd, limit=200):
    """かな入力の打った読み → 同じ手の続く2〜4打を同じ向きに1列戻した読み（ひらがなの読みだけ）。"""
    import odd_respell
    at, pos = _kana_table()
    keys = []
    for ch in odd_respell._keys(rd):
        keys.append((ch in _SMALL, _SMALL.get(ch, ch)))
    out, seen = [], {rd}
    for i in range(len(keys)):
        for L in range(MIN_RUN, MAX_RUN + 1):
            run = keys[i:i + L]
            if len(run) < L or any(k not in pos for _s, k in run):
                continue
            hands = {_left_hand(pos[k]) for _s, k in run}
            if len(hands) != 1:
                continue
            for d in (-1, 1):
                new = []
                for small, k in run:
                    r, c = pos[k]
                    n = at.get((r, c + d))
                    if n is None or _left_hand((r, c + d)) != _left_hand(pos[k]):
                        break
                    new.append(_SMALL_OF.get(n, n) if small and n in _SMALL_OF else n)
                else:
                    ks = [_SMALL_OF.get(k, k) if s else k for s, k in keys[:i]] + new + \
                         [_SMALL_OF.get(k, k) if s else k for s, k in keys[i + L:]]
                    t = _compose(ks)
                    if t not in seen and odd_respell._is_hira(t):
                        seen.add(t)
                        out.append(t)
                        if len(out) >= limit:
                            return out
    return out


def romaji_shifts(sp):
    """ローマ字の綴り → 同じ手の続く2〜4打を同じ段の左か右へ1列戻した綴り。"""
    import keyboard_layout as KB
    pos = KB.letter_positions()
    at = {p: k for k, p in pos.items()}
    out = []
    for i in range(len(sp)):
        for L in range(MIN_RUN, MAX_RUN + 1):
            run = sp[i:i + L]
            if len(run) < L or any(k not in pos for k in run):
                continue
            if len({pos[k][1] <= 4 for k in run}) != 1:
                continue
            for d in (-1, 1):
                new = ''
                for k in run:
                    r, c = pos[k]
                    n = at.get((r, c + d))
                    if n is None or (c + d <= 4) != (c <= 4):
                        break
                    new += n
                else:
                    t = sp[:i] + new + sp[i + L:]
                    if t not in out:
                        out.append(t)
    return out


def kana_explains(before, after):
    """かなの読み before → after の打鍵の違いが、手の位置のずれ1つ（続く2〜4打が揃って同じ段の同じ向きに1列）で
    説明できるか。読み直しの遠さの守り（correction_entry._far_kana_respell の3打以上は採らない）から外すのに使う。"""
    import odd_respell
    _at, pos = _kana_table()
    kb, ka = list(odd_respell._keys(before)), list(odd_respell._keys(after))
    if len(kb) != len(ka):
        return False
    diff = [i for i, (x, y) in enumerate(zip(kb, ka)) if x != y]
    if not (MIN_RUN <= len(diff) <= MAX_RUN) or diff[-1] - diff[0] + 1 != len(diff):
        return False
    steps = set()
    for i in diff:
        x, y = _SMALL.get(kb[i], kb[i]), _SMALL.get(ka[i], ka[i])
        if x not in pos or y not in pos:
            return False
        (r1, c1), (r2, c2) = pos[x], pos[y]
        if r1 != r2 or abs(c1 - c2) != 1 or _left_hand(pos[x]) != _left_hand(pos[y]):
            return False
        steps.add((c2 - c1, _left_hand(pos[x])))
    return len(steps) == 1
