# -*- coding: utf-8 -*-
"""くだけた形の形容詞（おもしれえ・すげえ・うめえ・ねえ）を元の形容詞（おもしろい・すごい・うまい・ない）に戻して読む
（うに 2026-11-09 09:53Z「おもしれえ、は、おもしろいの活用の一種と捉える必要があります」）。

くだけた形は 語幹の最後の あ・お・う 段の字＋い が、同じ行の え 段の字＋え（ー・ぇ も）になったもの
（しろい → しれえ・ごい → げえ・まい → めえ・ない → ねえ・たかい → たけえ）。字の数は同じなので、
元の形に置き換えた並びをそのまま格子や解析に渡せる（位置がずれない）。
戻した形が1つの形容詞（自立）として読めるときだけ。特定の語には合わせない。CN_COLLOQUIAL_ADJ=0 で使わない。
"""
import os

_ROWS = ['あいうえお', 'かきくけこ', 'がぎぐげご', 'さしすせそ', 'ざじずぜぞ', 'たちつてと', 'だぢづでど',
         'なにぬねの', 'はひふへほ', 'ばびぶべぼ', 'ぱぴぷぺぽ', 'まみむめも', 'らりるれろ', 'わ']
_BACK = {}
for r in _ROWS:
    if len(r) == 5:
        _BACK[r[3]] = (r[0], r[4], r[2])   # え段 → あ・お・う段
_LONG = ('え', 'ー', 'ぇ')
_A_ROW = frozenset(r[0] for r in _ROWS)


def on():
    return os.environ.get('CN_COLLOQUIAL_ADJ') != '0'


def _adj(word):
    try:
        from morphology import tokenize
        t = list(tokenize(word))
        return len(t) == 1 and t[0].pos == '形容詞' and (t[0].pos_sub or '').startswith('自立') and t[0].surface == word
    except Exception:
        return False


def spans(text):
    """[(開始, 終了, 元の形容詞の字)]。終了は x＋え の後ろ（伸ばしの続き ーー は含めない）。"""
    if not on():
        return []
    out = []
    i = 1
    while i < len(text) - 0:
        x = text[i] if i < len(text) else ''
        if x in _BACK and i + 1 < len(text) and text[i + 1] in _LONG:
            done = False
            for k in range(min(i, 5), -1, -1):
                st = text[i - k:i]
                if not all('ぁ' <= c <= 'ゖ' for c in st):
                    continue
                # 語幹の無い ねえ（＝ない）は、前が あ段（しらねえ）か は・が・も・く（ことがねえ・よくねえ）のときだけ。
                # いいねえ・そうだねえ の ねえ は終助詞
                if k == 0 and not (i > 0 and text[i - 1] != 'だ' and (text[i - 1] in _A_ROW or text[i - 1] in 'はがもく')):
                    continue
                for v in _BACK[x]:
                    w = st + v + 'い'
                    if _adj(w):
                        out.append((i - k, i + 2, w))
                        done = True
                        break
                if done:
                    break
            if done:
                i += 2
                continue
        i += 1
    return out


def normalize(text):
    """くだけた形を元の形容詞に置き換えた並び（字の数は同じ）と、その所の一覧。"""
    sp = spans(text)
    new = text
    for s, e, w in sp:
        new = new[:s] + w + new[e:]
    return new, sp


def tokenize_with(text, fn):
    """くだけた形を元の形容詞に戻して fn で解析し、語の表記だけ元の字に戻した語の並び（字の数が同じなので位置はそのまま）。
    品詞の表示や説明で おもしれえ を 重い の活用と出さないために使う（うに 2026-11-09 10:42Z）。"""
    new, sp = normalize(text)
    toks = list(fn(new))
    if not sp:
        return toks
    out = []
    for t in toks:
        try:
            from morphology import Token
            surf = text[t.start:t.end]
            out.append(Token(surf, t.pos, t.base_form, t.reading if surf == t.surface else surf,
                             t.start, t.end, t.has_reading, t.pos_sub, 'くだけた形' if surf != t.surface else t.infl_form))
        except Exception:
            out.append(t)
    return out
