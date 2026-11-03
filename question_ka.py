# CorrectNote — 誤字補正メモ帳
# Copyright (C) 2026 Takahashi Yuu
# SPDX-License-Identifier: GPL-3.0-or-later
"""
疑問の語で始まる文の終わりの「か」が、IME で同じ読みの接尾の漢字（化・課・家 など）に変換された所を
助詞の か に戻す段（question_ka・2026-11-01）。

疑問の語（なに・だれ・どこ・どれ・どちら・どの・なぜ・いくつ・いくら など）が が・は・の・を で文の中に入り、
文の終わりが「名詞＋か と読む接尾の漢字」で、あいだに用言（動詞・形容詞・助動詞）が無い文は、疑問の か で
終わる文（どこが原因か）。接尾の漢字のままでは、疑問の語を受ける述語が無い。
また、疑問の語（なんで・なぜ・どこ・だれ・いつ・どう・何＋助数詞）を含む文が、か・の・？ の無い丁寧な言い切り
（ます・です）で終わるのは、疑問の文の形にも言い切りの形にもならない（動詞の読みの1字が抜けて、残りが なんで・どこ と
読めた形）。直し先は脱字の足し方で幾つも在り決まらないので紫（決めるか紫・うに 10-18）。
疑問の語の後ろに も・でも・か・ても が来る形（何でも・どこか・どう見ても）は疑問ではないので見ない。
特定の語や文字列には合わせない（品詞と読みだけで見る）。
"""
import difflib

_QUESTION_READINGS = ('なに', 'なん', 'だれ', 'どこ', 'どれ', 'どちら', 'どっち', 'どの', 'なぜ', 'いくつ',
                      'いくら', 'どんな', 'どなた')
_ENDS = '。．.！!？?'


def _is_end(t):
    """文の切れ目。句点・感嘆符・疑問符と、空白・タブ（1行に左右の欄や別の文がタブ・空白で並ぶ）。"""
    return t.pos == '記号' and (t.surface in _ENDS or (t.surface != '' and not t.surface.strip()))


def _sentences(toks):
    cur = []
    for t in toks:
        if _is_end(t):
            if cur:
                yield cur
            cur = []
        else:
            cur.append(t)
    if cur:
        yield cur


def propose(text):
    """[(start, end, 'か')] 接尾の漢字を か に戻す所。"""
    from morphology import tokenize
    out = []
    for sent in _sentences(list(tokenize(text))):
        while sent and sent[-1].pos == '記号':
            sent = sent[:-1]
        if len(sent) < 4:
            continue
        last = sent[-1]
        if not (last.pos == '名詞' and (last.pos_sub or '').startswith('接尾') and last.reading == 'か'
                and len(last.surface) == 1 and '一' <= last.surface <= '鿿'):
            continue
        if sent[-2].pos != '名詞':
            continue
        q = None
        for i, t in enumerate(sent[:-2]):
            if t.reading in _QUESTION_READINGS and t.pos in ('名詞', '副詞', '連体詞') \
                    and i + 1 < len(sent) and sent[i + 1].pos == '助詞' and sent[i + 1].surface in ('が', 'は', 'の', 'を'):
                q = i
                break
        if q is None:
            continue
        rest = sent[q + 2:-1]
        if any(t.pos in ('動詞', '形容詞', '助動詞') for t in rest):
            continue
        if any(t.surface == 'か' for t in rest):
            continue
        out.append((last.start, last.end, 'か'))
    return out


_POLITE_END = ('ます', 'です', 'ました', 'でした', 'ません')
_QUESTION_ADVERBS = ('なんで', 'なぜ', 'どう', 'どうして')


def _is_question_word(t):
    if t.pos == '副詞':
        return t.reading in _QUESTION_ADVERBS
    if t.pos == '名詞' and ((t.pos_sub or '').startswith('代名詞') or (t.pos_sub or '') == '数'):
        return t.reading in _QUESTION_READINGS or t.reading == 'いつ'
    return False


def unanswered_question_spans(text):
    """[(start, end)] 疑問の語から文の終わりまで（か・の・？ の無い丁寧な言い切りで終わる文）。"""
    from morphology import tokenize
    toks = list(tokenize(text))
    out = []
    start = 0
    for i, t in enumerate(toks + [None]):
        if t is not None and not _is_end(t):
            continue
        sent = toks[start:i]
        closer = t.surface if t is not None else ''
        start = i + 1
        if (closer and closer in '？?') or len(sent) < 2:
            continue
        tail = ''.join(x.surface for x in sent[-2:])
        if not any(tail.endswith(e) for e in _POLITE_END):
            continue
        if any(x.surface in ('か', 'の', 'かな', 'かしら', 'っけ') and x.pos == '助詞' for x in sent):
            continue
        for j, x in enumerate(sent):
            if not _is_question_word(x):
                continue
            k = j + 1
            if (x.pos_sub or '') == '数':
                if k < len(sent) and (sent[k].pos_sub or '').startswith('接尾'):
                    k += 1
                else:
                    continue
            rest = sent[k:]
            if rest and rest[0].pos == '助詞' and rest[0].surface in ('も', 'でも', 'か', 'やら', 'ぞ'):
                continue
            if any(r.surface in ('ても', 'でも') or (r.surface == 'も' and r.pos == '助詞') for r in rest):
                continue
            out.append((x.start, sent[-1].end))
            break
    return out


def repair_line(line, result, decided=()):
    if not isinstance(result, dict):
        return result
    done = result.get('corrected') or line
    try:
        marks = propose(done)
    except Exception:
        return result
    if not marks:
        return _question_marks(line, result, done, decided)
    changed = [(o[3], o[4]) for o in difflib.SequenceMatcher(None, line, done, autojunk=False).get_opcodes()
               if o[0] != 'equal']
    odd_now = [tuple(x[:2]) for x in list(result.get('odd_spans') or ()) + list(result.get('unsure_spans') or ())]
    new = done
    details = []
    for s, e, rep in sorted(marks, reverse=True):
        if any(x < e and s < y for x, y in changed + odd_now):
            continue
        org = None
        for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, done, line, autojunk=False).get_opcodes():
            if tag == 'equal' and i1 <= s and e <= i2:
                org = (s - i1 + j1, e - i1 + j1)
        if org is None or any(x < org[1] and org[0] < y for x, y in list(decided or ())):
            continue
        new = new[:s] + rep + new[e:]
        details.append([done[s:e], rep, '疑問の文の終わりの か'])
    if new == done:
        return result
    ops = [o for o in difflib.SequenceMatcher(None, line, new, autojunk=False).get_opcodes() if o[0] != 'equal']
    out = dict(result)
    out.update({'original': line, 'corrected': new, 'changed': True,
                'details': list(result.get('details') or []) + details,
                'spans': [[o[3], o[4]] for o in ops], 'original_spans': [[o[1], o[2]] for o in ops]})
    return out


def _question_marks(line, result, done, decided):
    """疑問の語で始まり か の無い丁寧な言い切りの文に紫（前の段が触っていない行・紫の無い所だけ）。"""
    if done != line:
        return result
    try:
        spans = unanswered_question_spans(done)
    except Exception:
        return result
    odd_now = [tuple(x[:2]) for x in list(result.get('odd_spans') or ()) + list(result.get('unsure_spans') or ())]
    add = [sp for sp in spans if not any(x < sp[1] and sp[0] < y for x, y in odd_now + list(decided or ()))]
    if not add:
        return result
    out = dict(result)
    out['odd_spans'] = sorted(set(tuple(x[:2]) for x in (result.get('odd_spans') or ())) | set(add))
    out['odd_reasons'] = list(result.get('odd_reasons') or ()) + [
        (a, b, '疑問の語があるのに、か の無い言い切りで終わっています') for a, b in add]
    return out
