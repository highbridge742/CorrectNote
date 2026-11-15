"""書き換えは採るが、書き換えた後の並びに崩れが残る所には紫（不確か）を足す（2026-11-14 補正担当・全体評価の方針:
「決められない時は紫」）。

なぜ
----
短いかなの語の2打の打ち違いを、紫なしで別の語に書き換えていた（作った例: でるをがなった → モデルをがなった・
わだんをあがる → 輪高を上がる・ぺらをかして → べらを貸して）。書き換えた形がまだ崩れているなら、確かな直しではない。

どうやって
----------
既存のファイルは変えない。install() が correction_entry.correct_line を外から包む（一番外側、答えが出た後に見る）。
書き換えた所ごとに、直した後の行で次のどれかが在れば、書き換えはそのままに、元の行のその所へ紫と理由を足す:
1. 元の行で「X と Y は続けて置けない」と見た助詞の並びが、直した後の行にも同じ字のまま残っている（書き換えはその並びを
   説明していない）。
2. 書き換えた所に掛かる、名詞の漢字1字の後ろに名詞の接尾か漢字1字の名詞がすぐ続き、2字をつないだ語が辞書に無い
   （漢字1字の切れ端が残った: 輪＋高）。
3. 書き換えた所に掛かる 名詞＋を／に＋動詞 の組が、例文の組にも語の組の表にも無い（correction_entry._frame_at が
   False）。
特定の語や文字列には合わせない。

切り替え: CN_REWRITE_DOUBT=0 で前のまま。1・2 は CN_REWRITE_DOUBT_CLASH・_PIECE=0 で止める。3 は既定で止めてあり CN_REWRITE_DOUBT_FRAME=1 で見る。
かなを同じ読みの漢字に置いただけの所は見ない（2026-11-14 PC の正しい文 きれい→綺麗 に紫が付いた。CN_REWRITE_DOUBT_SAME_READING=0 で見る）。
3 の名詞は普通の名詞だけ（形容動詞語幹・副詞可能・数・代名詞・非自立・固有名詞・接尾は見ない）。
"""
import difflib
import functools
import os
import re

_orig = {}
REASON = '直した形にまだ崩れが残るので、直しは確かではありません'
_CLASH = re.compile(r'「(.)」と「(.)」は続けて置けない')


def _on(name=''):
    return os.environ.get('CN_REWRITE_DOUBT' + name) != '0'


def _kanji(c):
    return '一' <= c <= '鿿' or c == '々'


def _is_word(s):
    try:
        from morphology import dictionary_inflections
        return any(r[2] == s for r in dictionary_inflections(s) or ())
    except Exception:
        return True


def _orig_pos(ops, j):
    """直した後の行の位置 j を元の行の位置へ"""
    for tag, i1, i2, j1, j2 in ops:
        if j1 <= j < j2 or (j == j2 and tag == 'equal'):
            return i1 + (j - j1 if tag == 'equal' else 0) if tag == 'equal' else i1
    return ops[-1][2] if ops else j


# 組の表で見ない名詞: 形容動詞語幹（綺麗に洗う）・副詞可能・数・代名詞・非自立・固有名詞は、を／に＋動詞の組の表が薄い
_NOT_FRAME_NOUN = ('形容動詞語幹', '副詞可能', '数', '代名詞', '非自立', '固有名詞', '接尾')


def _kata2hira(s):
    return ''.join(chr(ord(c) - 0x60) if 'ァ' <= c <= 'ヶ' else c for c in s)


def _same_reading(src, dst):
    """元がかなだけで、直した所の読みが同じ（同じ読みの漢字に置いただけ）か"""
    k = _kata2hira(src)
    if not k or not all('ぁ' <= c <= 'ゖ' or c == 'ー' for c in k):
        return False
    try:
        from morphology import tokenize
        return _kata2hira(''.join(t.reading or t.surface for t in tokenize(dst))) == k
    except Exception:
        return False


def doubts(line, before, result):
    """[(元の行の始め, 終わり)]。before は包む前の答え（元の行の紫と理由を持つ）"""
    text = result.get('corrected')
    if not isinstance(text, str) or text == line:
        return []
    ops = difflib.SequenceMatcher(None, line, text, autojunk=False).get_opcodes()
    changed = [o for o in ops if o[0] != 'equal']
    if not changed:
        return []
    try:
        from morphology import tokenize
        toks = list(tokenize(text))
    except Exception:
        return []
    out = []
    # 1. 元の行の助詞の並びが残る
    if _on('_CLASH'):
        reasons = list((before or {}).get('odd_reasons') or ()) + list(result.get('odd_reasons') or ())
        for r in reasons:
            if not (isinstance(r, (list, tuple)) and len(r) >= 3 and isinstance(r[2], str)):
                continue
            m = _CLASH.search(r[2])
            if not m:
                continue
            pair = m.group(1) + m.group(2)
            a, b = r[0], r[1]
            p = line.find(pair, max(0, a - 1), b + 1)
            if p < 0:
                continue
            # その2字が直した後の行にも、書き換えに挟まれずに残る
            kept = any(tag == 'equal' and i1 <= p and p + 2 <= i2 for tag, i1, i2, j1, j2 in ops)
            near = any(o[1] <= p + 2 + 2 and p - 2 <= o[2] for o in changed)
            if kept and near:
                out.append((p, p + 2))
    for tag, i1, i2, j1, j2 in changed:
        if _on('_SAME_READING') and _same_reading(line[i1:i2], text[j1:j2]):
            continue        # かなを同じ読みの漢字に置いただけ（きれい→綺麗）は直しではないので見ない
        hit = [k for k, t in enumerate(toks) if t.start < max(j2, j1 + 1) and j1 - 1 < t.end]
        if not hit:
            continue
        lo, hi = max(0, hit[0] - 1), min(len(toks) - 1, hit[-1] + 1)
        bad = False
        # 2. 漢字1字の切れ端
        if _on('_PIECE'):
            for k in range(lo, hi):
                t, n = toks[k], toks[k + 1]
                if (t.pos == '名詞' and len(t.surface) == 1 and _kanji(t.surface) and n.start == t.end
                        and len(n.surface) == 1 and _kanji(n.surface)
                        and (n.pos == '名詞' and (n.pos_sub or '').startswith(('接尾', '一般')))
                        and (j1 - 1 < n.end and t.start < max(j2, j1 + 1) + 1)
                        and not _is_word(t.surface + n.surface)):
                    bad = True
        # 3. 例文に無い 名詞＋を／に＋動詞
        # 3 は既定で止める（例文に無い組は弱い根拠。PC の正しい文の紫が増えた 2026-11-14）。CN_REWRITE_DOUBT_FRAME=1 で見る
        if not bad and os.environ.get('CN_REWRITE_DOUBT_FRAME') == '1':
            try:
                import correction_entry as ce
                for k in range(max(0, lo - 1), hi + 1):
                    t = toks[k]
                    if (t.pos == '名詞' and not (t.pos_sub or '').startswith(_NOT_FRAME_NOUN) and k + 2 < len(toks) and toks[k + 1].surface in ('を', 'に')
                            and toks[k + 2].pos == '動詞'
                            and (t.start < max(j2, j1 + 1) and j1 < t.end
                                 or toks[k + 2].start < max(j2, j1 + 1) and j1 < toks[k + 2].end)
                            and ce._frame_at(text, t.start) is False):
                        bad = True
                        break
            except Exception:
                pass
        if bad:
            a = _orig_pos(ops, toks[hit[0]].start)
            b = max(i2, a + 1)
            out.append((min(a, i1), min(max(b, i1 + 1), len(line))))
    return sorted(set(out))


def mark(line, before, result):
    if not _on() or not isinstance(line, str) or not isinstance(result, dict):
        return result
    spans = doubts(line, before, result)
    have = [tuple(x[:2]) for x in result.get('odd_spans') or ()]
    spans = [sp for sp in spans if not any(x < sp[1] and sp[0] < y for x, y in have)]
    if not spans:
        return result
    out = dict(result)
    out['odd_spans'] = sorted(set(have) | set(spans))
    out['odd_reasons'] = list(result.get('odd_reasons') or ()) + [(a, b, REASON) for a, b in spans]
    return out


def correct_line(line, *args, **kwargs):
    result = _orig['correct_line'](line, *args, **kwargs)
    try:
        return mark(line, None, result)
    except Exception:
        return result


def install():
    import correction_entry as ce
    if 'correct_line' in _orig:
        return
    _orig['correct_line'] = ce.correct_line
    functools.update_wrapper(correct_line, ce.correct_line)
    ce.correct_line = correct_line


def uninstall():
    import correction_entry as ce
    fn = _orig.pop('correct_line', None)
    if fn is not None and ce.correct_line is correct_line:
        ce.correct_line = fn
    correct_line.__dict__.pop('__wrapped__', None)
