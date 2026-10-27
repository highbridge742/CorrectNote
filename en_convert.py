# -*- coding: utf-8 -*-
"""文変換の英文（2026-10-26 うにさん 15:04Z・15:05Z）。

- english_reorderings: 英文 → 英文の倒置（句を文頭へ出す・句の順を入れ替える）
- japanese_order: 英文 → 日本語の文法で名詞は英語の並び
    "I read a book at the library." → library で book を読んだ

翻訳ではない（うにさん 10-26 01:14Z）。品詞は en_pos（本体の英語の品詞）で決め、
係り受けは語の並びから大まかに取る。述語は JMdict の逆引き（en_rev.json.gz）。
読めない文は None・空にして出さない。補正には使わない。
"""
import gzip
import itertools
import json
import os
import re
import sys
from functools import lru_cache

import en_pos

_LIMIT = 60


@lru_cache(maxsize=1)
def _data():
    base = getattr(sys, '_MEIPASS', None) or os.path.dirname(os.path.abspath(__file__))
    try:
        with gzip.open(os.path.join(base, 'en_rev.json.gz'), 'rt', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {'rev': {}, 'kind': {}, 'lemma': {}}


def is_english(text):
    letters = [c for c in text if c.isalpha()]
    return bool(letters) and sum(c.isascii() for c in letters) >= 0.8 * len(letters)


# ------------------------------------------------------------
# 句に分ける
# ------------------------------------------------------------

_BE = {'am', 'is', 'are', 'was', 'were', 'be', 'been', 'being', "'m", "'re", "'s"}
_AUX = _BE | {'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'can', 'could',
              'should', 'shall', 'may', 'might', 'must', "'ll", "'d", "'ve"}
_NEG = {'not', "n't", 'never'}
_PRON = {'i': '私', 'me': '私', 'you': 'あなた', 'he': '彼', 'him': '彼', 'she': '彼女',
         'her': '彼女', 'we': '私たち', 'us': '私たち', 'they': '彼ら', 'them': '彼ら',
         'it': 'それ', 'this': 'これ', 'that': 'それ', 'these': 'これら', 'those': 'それら'}
_POSS = {'my': '', 'our': '', 'your': 'あなたの', 'his': '彼の', 'her': '彼女の',
         'their': '彼らの', 'its': ''}
_ARTICLE = {'a', 'an', 'the', 'some', 'any'}
_PARTICLE = {'out', 'up', 'down', 'off', 'away', 'back', 'in', 'on', 'over'}
_TIME_ADV = {'yesterday', 'today', 'tomorrow', 'tonight', 'now', 'then', 'soon', 'later',
             'recently', 'ago'}


class Tok:
    def __init__(self, text, code, codes):
        self.text, self.code, self.codes = text, code, codes
        self.low = text.lower()

    def __repr__(self):
        return f'{self.text}/{self.code}'


def _toks(sentence):
    spans = [m.span() for m in re.finditer(r"[A-Za-z]+(?:'[A-Za-z]+)?|\d+(?:[.,]\d+)?", sentence)]
    out = []
    for (a, z), (codes, code, _) in zip(spans, en_pos.judge(sentence, spans)):
        w = sentence[a:z]
        low = w.lower()
        if low in _AUX or low.endswith("n't"):
            code = 'M'
        elif low in _PRON or low in _POSS:
            code = 'O' if low in _PRON else 'D'
        elif w[0].isdigit():
            code = 'U'
        elif not code:
            code = 'N'      # 名前・辞書に無い語は名詞として扱う
        out.append(Tok(w, code, codes or code))
    for a, b in zip(out, out[1:]):
        # her mother・this morning: 名詞の前は限定の語
        if a.low in ('her', 'this', 'that', 'these', 'those') and b.code in ('N', 'J') and 'V' not in b.code:
            a.code = 'D'
    # because of・in front of は1つの前置詞
    for i in range(len(out) - 1):
        if out[i].low in ('because', 'instead', 'out') and out[i + 1].low == 'of':
            out[i].code = 'P'
            out[i].text += ' of'
            out[i].low += ' of'
            del out[i + 1]
            break
    return out


def _np_end(toks, i):
    """i から始まる名詞句の終わり（含まない）。名詞句でなければ i。"""
    j = i
    if j < len(toks) and toks[j].code == 'O':
        return j + 1
    while j < len(toks) and (toks[j].code in ('D', 'U') or toks[j].low in _ARTICLE):
        j += 1
    while j < len(toks) and toks[j].code in ('J', 'R') and j + 1 < len(toks) and toks[j + 1].code in ('J', 'N', 'U'):
        j += 1
    k = j
    while k < len(toks) and toks[k].code in ('N', 'J', 'U') and not (toks[k].code == 'J' and k > j and toks[k - 1].code == 'N'):
        k += 1
    if k == j:
        return i if j == i else (j if toks[j - 1].code in ('D', 'U') and toks[j - 1].low not in _ARTICLE else i)
    # X and Y
    if k + 1 < len(toks) and toks[k].low == 'and':
        k2 = _np_end(toks, k + 1)
        if k2 > k + 1:
            return k2
    # X of Y
    if k + 1 < len(toks) and toks[k].low == 'of':
        k2 = _np_end(toks, k + 1)
        if k2 > k + 1:
            return k2
    return k


def parse(sentence):
    """英文 → {'subj': [Tok], 'verb': [Tok], 'parts': [(種類, [Tok])], 'pre': [...]}。読めなければ None。
    種類: obj（目的語）・comp（補語）・pp（前置詞句）・adv・prt（out などの小辞）・to（to＋動詞の句）"""
    toks = _toks(sentence)
    if not toks:
        return None
    i = 0
    pre = []
    # 文頭の前置詞句・副詞（At the library, ...）
    while i < len(toks) and toks[i].code in ('P', 'R') and toks[i].low not in ('to',):
        if toks[i].code == 'R':
            pre.append(('adv', toks[i:i + 1]))
            i += 1
            continue
        j = _np_end(toks, i + 1)
        if j == i + 1:
            return None
        pre.append(('pp', toks[i:j]))
        i = j
    s0 = i
    i = _np_end(toks, i)
    if i == s0:
        return None
    subj = toks[s0:i]
    # 主語の後ろの of 句・前置詞句は主語のうち（My friend from school ...）
    v0 = i
    while i < len(toks) and toks[i].code == 'R' and toks[i].low not in _NEG:
        pre.append(('adv', toks[i:i + 1]))
        i += 1
    v0 = i
    while i < len(toks) and (toks[i].code == 'M' or toks[i].low in _NEG):
        i += 1
    if i < len(toks) and toks[i].code == 'R' and i + 1 < len(toks) and 'V' in toks[i + 1].codes:
        pre.append(('adv', toks[i:i + 1]))
        toks = toks[:i] + toks[i + 1:]
    if i < len(toks) and ('V' in toks[i].codes and toks[i].code != 'P' or toks[i].code == 'V'):
        i += 1
    verb = toks[v0:i]
    if not verb:
        return None
    parts = []
    while i < len(toks):
        t = toks[i]
        if t.low == 'to' and i + 1 < len(toks) and 'V' in toks[i + 1].codes and toks[i + 1].code != 'N':
            j = i + 2
            while j < len(toks) and toks[j].code != 'P':
                j = _np_end(toks, j) if _np_end(toks, j) > j else j + 1
            parts.append(('to', toks[i:j]))
            i = j
        elif t.code == 'P' or t.low in ('to', 'than'):
            j = _np_end(toks, i + 1)
            if j == i + 1:
                if t.low in _PARTICLE and not parts:
                    parts.append(('prt', [t]))
                    i += 1
                    continue
                return None
            parts.append(('pp', toks[i:j]))
            i = j
        elif t.code == 'R' and i + 1 < len(toks) and toks[i + 1].code == 'J' and (i + 2 >= len(toks) or toks[i + 2].code != 'N'):
            parts.append(('comp', toks[i:i + 2]))     # very sweet
            i += 2
        elif t.code == 'R' or t.low in _TIME_ADV:
            j = i + 1
            # last week / this morning は名詞句（下で取る）
            parts.append(('adv', toks[i:j]))
            i = j
        elif t.code == 'J' and _np_end(toks, i) in (i, i + 1) and (i + 1 >= len(toks) or toks[i + 1].code != 'N'):
            parts.append(('comp', [t]))
            i += 1
        else:
            j = _np_end(toks, i)
            if j == i:
                return None
            np = toks[i:j]
            kind = 'adv' if _kind(np[-1]) == 't' and np[0].low in ('last', 'next', 'this', 'every') else (
                'comp' if any(v.low in _BE for v in verb) else 'obj')
            parts.append((kind, np))
            i = j
    return {'pre': pre, 'subj': subj, 'verb': verb, 'parts': parts}


# ------------------------------------------------------------
# 英文 → 英文の倒置
# ------------------------------------------------------------

def _words(ts):
    return ' '.join(t.text for t in ts)


def _keep_case(t):
    return t.text == 'I' or t.text.startswith('I\'') or (t.code == 'N' and not t.codes.strip('N') and t.text[:1].isupper()) \
        or (t.text[:1].isupper() and not en_pos.codes_for(t.text))


def _cap(s):
    return s[:1].upper() + s[1:]


def english_reorderings(sentence, limit=_LIMIT):
    """英文の倒置。主語＋述語（＋目的語・補語）の芯は保ち、前置詞句・副詞・時の句を
    文頭へ出したり順を入れ替えたりする。目的語を前に出す形（A book, I read.）も入れる。
    原文と同じものは出さない。並びは原文で先に来る句が頭のものから。"""
    p = parse(sentence)
    if p is None:
        return []
    end = sentence.rstrip()[-1:] if sentence.rstrip()[-1:] in '.!?' else '.'
    first = (p['pre'][0][1] if p['pre'] else p['subj'])[0]
    lowered = {id(first)}

    def text(ts, head=False):
        s = _words(ts)
        if not head and id(ts[0]) in lowered and not _keep_case(ts[0]):
            s = s[:1].lower() + s[1:]
        return s

    core = [p['subj'], p['verb']]
    ad = [x for _, x in p['pre']]
    tail_core = []
    for kind, x in p['parts']:
        if kind in ('obj', 'comp', 'prt', 'to') and not ad or kind in ('prt',):
            tail_core.append(x)
        elif kind in ('obj', 'comp', 'to'):
            tail_core.append(x)
        else:
            ad.append(x)
    obj = next((x for k, x in p['parts'] if k == 'obj'), None)
    original_order = [id(x[0]) for x in [x for _, x in p['pre']] + [p['subj']] + [x for _, x in p['parts']]]
    out = set()
    results = []

    def add(front, back, topic=None):
        heads = []
        pieces = []
        for x in front:
            pieces.append(text(x))
        mid = [text(p['subj']), text(p['verb'])] + [text(x) for x in tail_core if x is not topic] + [text(x) for x in back]
        s = ''
        if topic is not None:
            s = text(topic) + ', '
            heads.append(topic)
        if pieces:
            s += ', '.join(pieces) + ', '
            heads.extend(front)
        s += ' '.join(mid)
        heads.append(p['subj'])
        s = _cap(s) + end
        orig = _cap(_words([t for _, x in p['pre'] for t in x] and [t for _, x in p['pre'] for t in x]) or '')
        if s not in out:
            out.add(s)
            results.append((original_order.index(id(heads[0][0])) if id(heads[0][0]) in original_order else 99, s))

    n = len(ad)
    for k in range(n + 1):
        for front in itertools.combinations(range(n), k):
            rest = [j for j in range(n) if j not in front]
            for perm in itertools.permutations(rest):
                add([ad[j] for j in front], [ad[j] for j in perm])
                if len(results) > limit * 2:
                    break
    if obj is not None and not any(t.code == 'O' for t in obj):
        add([], ad, topic=obj)
    orig = re.sub(r'\s+', ' ', sentence.strip())
    got = [s for _, s in sorted(results, key=lambda r: r[0]) if s.rstrip('.!?').replace(',', '') != orig.rstrip('.!?').replace(',', '')]
    return got[:limit]


# ------------------------------------------------------------
# 英文 → 日本語の文法（名詞は英語）
# ------------------------------------------------------------

def _kind(t):
    d = _data()
    low = t.low
    if t.code == 'O' and low in _PRON and low not in ('it', 'this', 'that', 'these', 'those'):
        return 'p'
    if t.text[:1].isupper() and not en_pos.codes_for(t.text):
        return 'p'
    k = d['kind'].get(low) or (d['kind'].get(low[:-1]) if low.endswith('s') else None)
    if t.code == 'U' or low in _TIME_ADV:
        return 't'
    return k or ''


def _lemma(w):
    w = w.lower()
    d = _data()['lemma']
    if w in d:
        return d[w]
    for suf, rep in (('ies', 'y'), ('ied', 'y'), ('ing', ''), ('ing', 'e'), ('ed', ''), ('ed', 'e'), ('es', ''), ('s', '')):
        if w.endswith(suf):
            base = w[:-len(suf)] + rep
            if len(base) > 1 and _data()['rev'].get(base + '|v') or _data()['rev'].get(base + '|suru'):
                return base
            if suf in ('ing', 'ed') and len(base) > 2 and base[-1] == base[-2]:
                if _data()['rev'].get(base[:-1] + '|v'):
                    return base[:-1]
    return w


def _np_ja(ts):
    """名詞句 → 日本語の語順（英語の名詞はそのまま。冠詞は落とし所有は「の」）。"""
    if len(ts) == 1 and ts[0].low in _PRON and ts[0].code == 'O':
        return _PRON[ts[0].low]
    if any(t.low == 'and' for t in ts):
        k = next(i for i, t in enumerate(ts) if t.low == 'and')
        a, b = _np_ja(ts[:k]), _np_ja(ts[k + 1:])
        return a if b == '私' else (b if a == '私' else a + 'と' + b)
    if any(t.low == 'of' for t in ts):
        k = next(i for i, t in enumerate(ts) if t.low == 'of')
        return _np_ja(ts[k + 1:]) + 'の' + _np_ja(ts[:k])
    pre = ''
    words = []
    for t in ts:
        if t.low in _ARTICLE:
            continue
        if t.low in _POSS:
            pre += _POSS[t.low]
            continue
        if t.low.endswith("'s"):
            pre += t.text[:-2] + 'の'
            continue
        words.append(t.text)
    return pre + ' '.join(words)


# 逆引きの1番がずれる身近な語（JMdict の語義の順では古い語・硬い語が先に来る）
_COMMON = {'very|adv': 'とても', 'usually|adv': '普段', 'really|adv': '本当に', 'live|v': '住む',
           'open|v': '開ける', 'meet|v': '会う', 'play|v': 'する', 'cook|v': '作る',
           'lose|v': 'なくす', 'learn|v': '習う', 'study|v': '勉強する', 'travel|v': '旅行する',
           'give|v': 'あげる', 'arrive|v': '着く', 'talk|v': '話す', 'find|v': '見つける',
           'cold|adj': '寒い', 'clean|adj': '綺麗', 'good|adj': '良い', 'go out|v': '出掛ける'}
_CONJ = {'住む': 'godan', '開ける': 'ichidan', '会う': 'godan', 'する': 'suru', '作る': 'godan',
         'なくす': 'godan', '習う': 'godan', '勉強する': 'suru', '旅行する': 'suru', 'あげる': 'ichidan',
         '着く': 'godan', '話す': 'godan', '見つける': 'ichidan', '寒い': '', '綺麗': '', '良い': '',
         '出掛ける': 'ichidan', '遊ぶ': 'godan', '開く': 'godan', 'とても': '', '普段': '', '本当に': ''}


def _pick(english, kinds, transitive=None):
    from reverse_verb import Verb
    for k in kinds:
        w = _COMMON.get(f'{english}|{k}')
        if transitive == 0:
            w = {'する': '遊ぶ', '開ける': '開く'}.get(w, w)
        if w:
            v = Verb(w, _CONJ[w], {'綺麗': 'na', '寒い': 'adj', '良い': 'adj'}.get(w, 'suru' if w.endswith('する') else k))
            v.trans = 0 if w in ('会う', '着く') else -1
            return v
    rev = _data()['rev']
    cands = []
    for k in kinds:
        for word, trans, score, conj in rev.get(f'{english}|{k}', []):
            s = score
            if transitive == 0 and trans == 1:
                s += 40
            elif transitive == 1 and trans == 0:
                s += 10
            cands.append((s, word, conj, k, trans))
    if not cands:
        return None
    _, word, conj, k, trans = min(cands)
    v = Verb(word, conj, k)
    v.trans = trans
    return v


_EXIST = {'live', 'stay', 'be', 'remain', 'stand', 'sit', 'arrive', 'get'}
_LIKE = {'like': '好き', 'love': '大好き', 'hate': '嫌い', 'dislike': '嫌い'}
_ORDER = ('cause', 'subj', 'time', 'adv', 'with', 'loc', 'means', 'from', 'agent', 'benefit',
          'than', 'goal', 'path', 'obj', 'other')


def _particle(prep, np, verb_lemma, ctx):
    p = prep.lower()
    k = _kind(np[-1])
    if p in ('at', 'in', 'on', 'over', 'during'):
        if k == 't':
            return 'time', 'に'
        if verb_lemma in _EXIST:
            return 'goal', 'に'
        return 'loc', 'で'
    if p in ('to', 'into', 'toward', 'towards'):
        return 'goal', 'まで' if ctx.get('has_from') else 'に'
    if p == 'with':
        return ('with', 'と') if k == 'p' else ('means', 'で')
    if p == 'by':
        return ('agent', 'に') if ctx.get('passive') else ('means', 'で')
    if p == 'from':
        return 'from', 'から'
    if p in ('until', 'till'):
        return 'goal', 'まで'
    if p == 'for':
        return ('time', '間') if k == 't' else ('benefit', 'のために')
    if p == 'than':
        return 'than', 'より'
    if p == 'because of':
        return 'cause', 'で'
    if p == 'about':
        return 'obj', 'について'
    if p == 'through':
        return 'path', 'を通って'
    if p == 'after':
        return 'time', 'の後で'
    if p == 'before':
        return 'time', 'の前に'
    return 'other', 'に'


def japanese_order(sentence):
    """英文 → 日本語の文法で名詞は英語の並び。読めなければ None。"""
    p = parse(sentence)
    if p is None:
        return None
    verb = p['verb']
    lows = [t.low for t in verb]
    neg = any(w in _NEG or w.endswith("n't") for w in lows)
    main = verb[-1] if verb[-1].code != 'M' or verb[-1].low in _BE else None
    if main is not None and main.code == 'M' and main.low not in _BE:
        main = None
    past = any(w.split("n'")[0] in ('was', 'were', 'did', 'had', 'could', 'wasn', 'weren', 'didn', 'hadn', 'couldn') for w in lows) or (
        main is not None and len(verb) == 1 and (main.low.endswith('ed') or _data()['lemma'].get(main.low) and main.low not in _data()['lemma'].get(main.low, '')
                                               and not main.low.endswith('s')))
    be_aux = any(w in _BE for w in lows[:-1])
    prog = main is not None and main.low.endswith('ing') and be_aux
    passive = main is not None and be_aux and not prog and (main.low.endswith('ed') or main.low in _data()['lemma'])
    can = any(w.split("n'")[0] in ('can', 'could', 'ca', 'couldn') for w in lows)
    parts = list(p['parts'])
    has_obj = any(k == 'obj' for k, _ in parts)
    ctx = {'passive': passive, 'has_from': any(k == 'pp' and x[0].low == 'from' for k, x in parts)}
    lemma = _lemma(main.text) if main is not None else 'be'
    copula = main is None or main.low in _BE
    want = False
    if lemma == 'want' and parts and parts[0][0] == 'to':
        want = True
        to = parts.pop(0)[1]
        lemma = _lemma(to[1].text)
        rest = to[2:]
        if rest:
            j = _np_end(rest, 0)
            parts.insert(0, ('obj', rest[:j or len(rest)]))
        has_obj = any(k == 'obj' for k, _ in parts)
    args = [('subj', _np_ja(p['subj']) + '\0')]
    pred = None
    prt = ''
    for kind, x in p['pre'] + parts:
        if kind == 'pp':
            role, part = _particle(x[0].low, x[1:], lemma, ctx)
            if role == 'than' and x[-1].low in ('me', 'i'):
                args.append((role, '私より'))
                continue
            args.append((role, _np_ja(x[1:]) + part))
        elif kind == 'obj':
            args.append(('obj', _np_ja(x) + '\1'))
        elif kind == 'adv':
            w = ' '.join(t.low for t in x)
            v = _pick(w, ('adv',))
            role = 'time' if _kind(x[-1]) == 't' else 'adv'
            if v is not None:
                args.append((role, v.word))
            elif len(x) > 1 or x[0].low in _TIME_ADV:
                args.append((role, _np_ja(x)))
            else:
                return None
        elif kind == 'prt':
            prt = x[0].low
        elif kind == 'comp':
            if x[-1].code == 'J' and len(x) <= 2:
                adv = x[0] if len(x) == 2 else None
                if adv is not None:
                    v = _pick(adv.low, ('adv',))
                    args.append(('adv', v.word if v else adv.text))
                w = x[-1].low
                if w.endswith('er') and w not in _data()['rev'] and not _pick(w, ('adj', 'na')):
                    w = w[:-2] if not w[:-2].endswith(w[-3]) else w[:-3]
                    w = {'bigg': 'big', 'hott': 'hot'}.get(w, w)
                v = _pick(w, ('adj', 'na'))
                if v is None:
                    return None
                pred = ('adj', v)
            else:
                pred = ('cop', _np_ja(x))
        elif kind == 'to':
            return None
    if pred is None and lemma in _LIKE and has_obj:
        from reverse_verb import Verb
        args = [(r, s.replace('\1', 'が')) for r, s in args]
        pred = ('adj', Verb(_LIKE[lemma], '', 'na'))
    if pred is None:
        if copula:
            return None
        v = (_pick(f'{lemma} {prt}', ('v', 'suru'), 1 if has_obj else 0) if prt else None) or \
            _pick(lemma, ('v', 'suru'), 1 if has_obj else 0)
        if v is None:
            return None
        pred = ('v', v)
    pk, v = pred
    if pk == 'v' and v.word in ('住む',) and not past:
        prog = True     # 状態の動詞（lives in → 住んでいる）
    topic = pk in ('adj', 'cop') or (not past and not prog)
    out = []
    for r, s in args:
        if '\0' in s:
            head = s.replace('\0', '')
            if head == '私':
                continue        # 日本語では「私は」を言わないことが多い
            s = head + ('は' if topic or head in _PRON.values() else 'が')
        out.append((r, s.replace('\1', 'を')))
    out.sort(key=lambda a: _ORDER.index(a[0]) if a[0] in _ORDER else len(_ORDER))
    if pk == 'cop':
        tail = v + (('ではなかった' if past else 'ではない') if neg else ('だった' if past else 'だ'))
    else:
        tail = v.form(past=past, neg=neg, prog=prog, want=want, can=can, passive=passive)
        if pk == 'v' and getattr(v, 'trans', -1) == 0 and not can:
            out = [(r, a[:-1] + 'に') if r == 'obj' and a.endswith('を') else (r, a) for r, a in out]
    s = ''.join([a for _, a in out] + [tail])
    s = re.sub(r'(?<=[A-Za-z0-9.])(?=[^\x00-\x7f])|(?<=[^\x00-\x7f])(?=[A-Za-z0-9])', ' ', s)
    return re.sub(r' +', ' ', s).strip()
