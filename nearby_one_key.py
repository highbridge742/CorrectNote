# -*- coding: utf-8 -*-
"""上下の行に書かれた語と、読みが隣のキーの1打だけ違う漢字の語を疑う段（2026-10-30・補正担当）。

かな入力で読みを1打だけ隣のキーに打ち違えると、IME はその読みを別の実在の語に変換する（ほんじ→本字）。
語としては正しいので印が立たないが、同じメモの上下の行（nearby_words）に、読みがそのキーだけ違う語が
書かれていれば、書くつもりだったのはその語と見る（同じメモの表記に合わせる、の1打違いへの広げ）。
- 候補が1つで、行の並びの費用が下がるなら置く。下がらなければ紫だけ。
- 候補が2つ以上なら紫だけ。
- 元の語が上下の行にも書かれていれば触らない（その語を使う文脈）。
- 元の語が上下の行の語より一般の文章で RARITY_GAP 以上珍しいときだけ見る。よく使う語どうし（申請と人生）は
  どちらも正しく書いた語でありうるので、近くの行に在るだけでは替えず紫も付けない（2026-10-31: 正しい動詞の語を
  2行上の語に替えた）。
特定の語や文字列には合わせない。
"""
import difflib

MAX_KEY = 1.05     # 隣のキー（同じ段の左右・同じ指の上下: kana_layout の VERTICAL_DISTANCE まで）
RARITY_GAP = 150   # ime_reconvert._rank（一般の文章の使われやすさの順位・大きいほど珍しい）の差


def _rank(word):
    try:
        import ime_reconvert
        return ime_reconvert._rank(word)
    except Exception:
        return None


def _hira(s):
    return ''.join(chr(ord(c) - 0x60) if 'ァ' <= c <= 'ヶ' else c for c in s)


def _kanji(ch):
    return '一' <= ch <= '鿿' or ch in '々〆'


def _reading(word, tokenize):
    toks = list(tokenize(word))
    if not toks or ''.join(t.surface for t in toks) != word:
        return ''
    out = []
    for t in toks:
        r = _hira(t.reading or '') if getattr(t, 'has_reading', True) else ''
        if not r or not all('ぁ' <= c <= 'ゖ' or c == 'ー' for c in r):
            return ''
        out.append(r)
    return ''.join(out)


def _one_key(a, b):
    import kana_layout as kl
    if len(a) != len(b) or a == b:
        return False
    diff = [(x, y) for x, y in zip(a, b) if x != y]
    return len(diff) == 1 and kl.kana_key_distance(*diff[0]) <= MAX_KEY


def propose(text, nearby_words):
    """text の中の (始まり, 終わり, 置く語 or None) の一覧。None は紫だけ。"""
    import morphology
    near = [w for w in dict.fromkeys(nearby_words or ()) if len(w) >= 2 and all(_kanji(c) for c in w)]
    if not near:
        return []
    near_set = set(nearby_words or ())
    near_r = [(w, _reading(w, morphology.tokenize)) for w in near]
    near_r = [(w, r) for w, r in near_r if r]
    if not near_r:
        return []
    toks = list(morphology.tokenize(text))
    out = []
    i = 0
    while i < len(toks):
        # 漢字だけの名詞の連なり（本＋字）を1語として見る
        j = i
        while j < len(toks) and toks[j].pos == '名詞' and toks[j].surface and all(_kanji(c) for c in toks[j].surface):
            j += 1
        if j == i:
            i += 1
            continue
        s, e = toks[i].start, toks[j - 1].end
        word = text[s:e]
        i = j
        if len(word) < 2 or word in near_set:
            continue
        r = _reading(word, morphology.tokenize)
        if not r:
            continue
        cands = sorted({w for w, rw in near_r if w != word and _one_key(r, rw)})
        rw0 = _rank(word)
        if rw0 is None:
            continue
        cands = [w for w in cands if (_rank(w) or rw0) + RARITY_GAP <= rw0]
        if not cands:
            continue
        out.append((s, e, cands[0] if len(cands) == 1 else None))
    return out


def _line_runs(text):
    """text の中の漢字だけの名詞の連なり (始まり, 終わり, 語)。"""
    import morphology
    toks = list(morphology.tokenize(text))
    out = []
    i = 0
    while i < len(toks):
        j = i
        while j < len(toks) and toks[j].pos == '名詞' and toks[j].surface and all(_kanji(c) for c in toks[j].surface):
            j += 1
        if j == i:
            i += 1
            continue
        s, e = toks[i].start, toks[j - 1].end
        out.append((s, e, text[s:e]))
        i = j
    return out


def _record_dependency(text):
    """この段の答えが上下の行の語のどこに依るかを used_keys に記録する（2026-11-06・挙動関連担当の案）。
    依るのは、行の漢字の語が上下の行に在るか（nearby_probes）と、行の漢字の語の読み（nearby_one_key: 上下の行に
    この読みと隣のキーの1打だけ違う読みの漢字の語が増えるか減るかした時だけ答えが変わりうる）。"""
    try:
        import used_keys as U
        rec = U._ACTIVE.get()
        if rec is None or U._IN_QUERY.get():
            return
        import morphology
        for s, e, word in _line_runs(text):
            if len(word) < 2:
                continue
            rec.nearby_probes.add(word)
            r = _reading(word, morphology.tokenize)
            if r and _rank(word) is not None:
                rec.nearby_one_key.add(r)
    except Exception:
        try:
            rec.nearby = True
        except Exception:
            pass


def change_matters(readings, old_words, new_words):
    """上下の行の語が old から new に変わった時、読み readings（_record_dependency の記録）の行のこの段の答えが
    変わりうるか。増えた・減った漢字の語の読みが、どれかの読みと隣のキーの1打だけ違えば True。"""
    import morphology
    if not readings:
        return False
    a = {w for w in old_words or () if len(w) >= 2 and all(_kanji(c) for c in w)}
    b = {w for w in new_words or () if len(w) >= 2 and all(_kanji(c) for c in w)}
    for w in a ^ b:
        rw = _reading(w, morphology.tokenize)
        if rw and any(_one_key(r, rw) for r in readings):
            return True
    return False


def repair_line(line, result, nearby_words, input_method='kana', decided=()):
    if not isinstance(result, dict) or input_method != 'kana':
        return result
    done = result.get('corrected') or line
    try:
        import os
        import used_keys as U
        if os.environ.get('CN_NEARBY_MARK') != '0' and isinstance(nearby_words, U.NearbyWords):
            _record_dependency(done)
            nearby_words = U.raw_tuple(nearby_words)
    except Exception:
        pass
    if not nearby_words:
        return result
    try:
        import morphology
        marks = propose(done, nearby_words)
    except Exception:
        return result
    if not marks:
        return result
    changed = [(o[3], o[4]) for o in difflib.SequenceMatcher(None, line, done, autojunk=False).get_opcodes()
               if o[0] != 'equal']
    odd_now = [tuple(x[:2]) for x in list(result.get('odd_spans') or ()) + list(result.get('unsure_spans') or ())]
    new = done
    odd_add, details = [], []
    for s, e, rep in sorted(marks, reverse=True):
        if any(x < e and s < y for x, y in changed):
            continue
        org = None
        for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, done, line, autojunk=False).get_opcodes():
            if tag == 'equal' and i1 <= s and e <= i2:
                org = (s - i1 + j1, e - i1 + j1)
        if org is None or any(x < org[1] and org[0] < y for x, y in list(decided or ())):
            continue
        if rep:
            trial = new[:s] + rep + new[e:]
            c0, c1 = morphology.path_cost(new), morphology.path_cost(trial)
            if c0 is not None and c1 is not None and c1 < c0:
                new = trial
                details.append([done[s:e], rep, '近くの語'])
                continue
        if not any(x < org[1] and org[0] < y for x, y in odd_now):
            odd_add.append(org)
    if not odd_add and new == done:
        return result
    out = dict(result)
    if odd_add:
        out['odd_spans'] = sorted(set(odd_now) | set(odd_add))
        out['odd_reasons'] = list(result.get('odd_reasons') or ()) + [
            (a, b, f'「{line[a:b]}」は上下の行の語と読みが1打だけ違います。打ち違いかもしれません')
            for a, b in odd_add]
    if new != done:
        ops = [o for o in difflib.SequenceMatcher(None, line, new, autojunk=False).get_opcodes() if o[0] != 'equal']
        out.update({'original': line, 'corrected': new, 'changed': True,
                    'details': list(result.get('details') or []) + details,
                    'spans': [[o[3], o[4]] for o in ops], 'original_spans': [[o[1], o[2]] for o in ops]})
    return out
