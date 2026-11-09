# -*- coding: utf-8 -*-
"""語の組の回数（Tatoeba の日本語の例文から数えた表）で、同じ読みの名詞の選び違いを疑う段（2026-10-30）。

行の名詞ごとに、隣の語との組（名詞＋の＋名詞・形容詞/連体詞＋名詞・名詞＋助詞＋述語・名詞＋直後の述語）を表で引く。
元の名詞の組は例文に一度も無く、同じ読みの別の名詞の組が例文に何度も在り、その名詞のほうが例文でよく使われるとき、
選び違いとして紫にする（組の回数が十分多く、候補が1つなら直す）。表が無ければ何もしない。
例文は Tatoeba（https://tatoeba.org・CC BY 2.0 FR）。表には組と回数だけを入れ、例文そのものは入れない。
特定の語や文字列には合わせない。
"""
import difflib
import gzip
import json
import os
from functools import lru_cache

MIN_PAIR = 2     # 候補の組がこれだけ例文に在ること
FIX_PAIR = 5     # これ以上で候補が1つなら直す
RATIO = 3        # 候補の名詞が元の名詞よりこれだけ多く例文に出ること
WF_MARGIN = 150  # 一般の文（wordfreq の段・大きいほど稀）でも、元の名詞が候補よりこれだけ稀なこと
KEY_PAIR = 3     # 1打違いの読みの名詞は、その組がこれだけ例文に在ること
KEY_WF_MARGIN = 250  # 1打違いの読みの名詞は、元の名詞が一般の文でこれだけ稀なこと
LOOSE_PAIR = 10  # 元の名詞が例文に無く、候補の組がこれだけ在るとき（2026-11-05 かな入力の担当）
LOOSE_WF_MARGIN = 100
CUT_FIX = 100   # その名詞が1つだけで例文にこれだけ出るなら直す
CUT_NOUN = 20    # 述語の無い行（名詞＋助詞で終わる）で紫にするのは、1打違いの名詞が例文にこれだけ出るとき
_FORMAL = {'ん', 'の', 'よう', 'こと', 'もの', 'ところ', 'わけ', 'はず', 'ため', 'とき', 'そう'}


@lru_cache(maxsize=1)
def _table():
    try:
        with gzip.open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tatoeba_pairs.json.gz'),
                       'rt', encoding='utf-8') as f:
            d = json.load(f)
        return d['pairs'], d['nouns']
    except Exception:
        return None


@lru_cache(maxsize=1)
def _wordfreq():
    # ja_wordfreq.json.gz は ime_reconvert の読み込みを共有する（解析の子1つで1回だけ読む）。
    try:
        from ime_reconvert import _freq
        return _freq() or None
    except Exception:
        return None


def _rarer_in_general(noun, alt, margin=None):
    """元の名詞が一般の文でも候補よりはっきり稀か。例文（Tatoeba）は話し言葉の短い文が多く、技術の語（改行・
    位置）が少ないので、例文に組が無いことだけでは選び違いの証にならない（改行したい→開業・その位置へ→市 に
    替えていた。2026-10-30・補正担当）。表が無い・候補が表に無いときは今まで通り。"""
    wf = _wordfreq()
    if not wf or alt not in wf:
        return True
    if noun not in wf:
        return True
    return wf[noun] - wf[alt] >= (WF_MARGIN if margin is None else margin)


def _hira(s):
    return ''.join(chr(ord(c) - 0x60) if 'ァ' <= c <= 'ヶ' else c for c in s)


def _noun(t):
    return (t.pos == '名詞' and getattr(t, 'pos_sub', '') not in ('非自立', '代名詞', '数', '接尾', '固有名詞')
            and t.surface not in _FORMAL and t.has_reading)


def _base(t):
    return (getattr(t, 'base_form', '') or t.surface) if t.pos in ('動詞', '形容詞') else t.surface


def _contexts(toks, i):
    """i の名詞を X とした組の型 [(種類, 左, 右)]（X の所は None）。"""
    out = []
    if i >= 2 and toks[i - 1].surface == 'の' and _noun(toks[i - 2]):
        out.append(('の', toks[i - 2].surface, None))
    if i + 2 < len(toks) and toks[i + 1].surface == 'の' and _noun(toks[i + 2]):
        out.append(('の', None, toks[i + 2].surface))
    if i >= 1 and toks[i - 1].pos in ('形容詞', '連体詞'):
        out.append(('連体', _base(toks[i - 1]), None))
    if i + 2 < len(toks) and toks[i + 1].pos == '助詞' and toks[i + 2].pos in ('動詞', '形容詞'):
        out.append((toks[i + 1].surface, None, _base(toks[i + 2])))
    if i + 1 < len(toks) and toks[i + 1].pos == '動詞' and _base(toks[i + 1]) not in ('ある', 'いる', 'なる'):
        out.append(('続', None, _base(toks[i + 1])))
    return out


def _cut_object(toks, i):
    """i の名詞のすぐ後ろが格助詞（を・に・が・で・へ・と）1つで、その後ろが行の終わりか句読点か。"""
    if i + 1 >= len(toks):
        return False
    p = toks[i + 1]
    if p.pos != '助詞' or p.surface not in ('を', 'に', 'が', 'で', 'へ', 'と') or p.start != toks[i].end:
        return False
    return i + 2 >= len(toks) or toks[i + 2].pos == '記号'


def _count(pairs, kind, left, right, x):
    return pairs.get('\t'.join((kind, x if left is None else left, x if right is None else right)), 0)


def _is_kanji(c):
    return '一' <= c <= '鿿' or c == '々'


def _kanji_word(s):
    """漢字で始まり漢字を含む語（漢字だけ・送り仮名付き: 飢え・行き・止まる）。"""
    return bool(s) and _is_kanji(s[0])


def _variant(a, b):
    """書き方の違い（子ども/子供・止る/止まる・珈琲/コーヒー）か。漢字の組の片方がもう片方に含まれるとき。
    違う漢字を含む同じ読みの語（有人/友人・講演/公園）は選び違いの候補に残す（2026-11-05 ローマ字担当）。"""
    ka, kb = {c for c in a if _is_kanji(c)}, {c for c in b if _is_kanji(c)}
    return not ka or not kb or ka <= kb or kb <= ka


def _alternatives(noun, reading):
    import reading_lattice
    reading_lattice.load()
    # 書き方の違い（子ども/子供・珈琲/コーヒー）は選び違いではないので外す。かなだけの表記も外す
    return {s for s, _l, _r, _c, pos in reading_lattice._table.get(reading, ())
            if pos == '名詞' and s != noun and _kanji_word(s) and not _variant(s, noun)}


_PRED_POS = ('動詞', '形容詞')
PRED_PAIR = 3    # 述語の選び違い: 候補の述語の組（名詞＋助詞＋述語）がこれだけ例文に在ること
PRED_FIX = 5     # これ以上で候補が1つなら直す


@lru_cache(maxsize=1)
def _pred_readings():
    """述語の原形 → 読み（reading_lattice の表から）。"""
    import reading_lattice
    reading_lattice.load()
    out = {}
    for r, ents in reading_lattice._table.items():
        for s, _l, _r, _c, pos in ents:
            if pos in _PRED_POS and _kanji_word(s):
                out.setdefault(s, set()).add(r)
    return out


def _split_okuri(s):
    k = max(i for i, c in enumerate(s) if _is_kanji(c)) + 1
    return s[:k], s[k:]


def _pred_alternatives(base, pos):
    """同じ読み・同じ送り仮名で漢字の違う述語（履く/吐く・止まる/泊まる・降る/振る）。"""
    import reading_lattice
    head, tail = _split_okuri(base)
    out = set()
    for r in _pred_readings().get(base, ()):
        for s, _l, _r, _c, p in reading_lattice._table.get(r, ()):
            if p == pos and s != base and _kanji_word(s) and not _variant(s, base) and _split_okuri(s)[1] == tail:
                out.add(s)
    return out


def _pred_marks(toks, pairs):
    """名詞＋助詞＋述語の組が例文に一度も無く、同じ読みの別の漢字の述語の組なら例文に在る所（2026-11-05 ローマ字担当）。
    靴を吐いて→履いて・電車が泊まって→止まって・雪が振る→降る。直すのは候補が1つで組が PRED_FIX 回以上のとき、ほかは紫。"""
    marks = []
    for j in range(2, len(toks)):
        t, p, n = toks[j], toks[j - 1], toks[j - 2]
        if t.pos not in _PRED_POS or getattr(t, 'pos_sub', '') not in ('自立', '') or not _kanji_word(t.surface):
            continue
        if p.pos != '助詞' or not _noun(n) or p.start != n.end or t.start != p.end:
            continue
        # 述語のすぐ後ろに名詞（接尾の 地 など）が続く所（本を変え｜地｜に）は、述語の形が崩れた所（返しに の打ち違い）。
        # 述語の選び違いではないので触らない（買え地 にしていた・2026-11-06 ローマ字の試験）。CN_PAIR_PRED_NOUN_AFTER=0
        # （言い切りの形＋名詞 は 雪が降る｜日 のように普通なので、言い切りでない形のときだけ）
        if j + 1 < len(toks) and toks[j + 1].start == t.end and toks[j + 1].pos == '名詞' \
                and not (getattr(t, 'infl_form', '') or '').startswith('基本形') \
                and os.environ.get('CN_PAIR_PRED_NOUN_AFTER') != '0':
            continue
        base = _base(t)
        if not _kanji_word(base) or _count(pairs, p.surface, n.surface, None, base):
            continue
        head = _split_okuri(base)[0]
        if not t.surface.startswith(head):
            continue
        best = []
        for alt in _pred_alternatives(base, t.pos):
            c = _count(pairs, p.surface, n.surface, None, alt)
            if c >= PRED_PAIR:
                best.append((c, _split_okuri(alt)[0] + t.surface[len(head):]))
        if not best:
            continue
        best.sort(reverse=True)
        marks.append((t.start, t.end, best[0][1] if len(best) == 1 and best[0][0] >= PRED_FIX else None))
    return marks


def _key_alternatives(noun, reading):
    """読みを1打だけ戻す（隣のキー・巻き込みの抜き・抜け・二度押し・入れ替わり: かな入力の打鍵）と読める名詞。
    同じ読みの選び違いより根拠が弱いので、propose で例文の組と一般の文の珍しさをより強く求める（2026-11-01）。"""
    import reading_lattice
    from contextual_repair import key_repairs
    reading_lattice.load()
    out = set()
    for r in key_repairs(reading):
        r = getattr(r, 'reading', r)
        if r == reading:
            continue
        for s, _l, _r, _c, pos in reading_lattice._table.get(r, ()):
            if pos == '名詞' and s != noun and all('一' <= c <= '鿿' for c in s) and len(s) >= 2:
                out.add(s)
    return out


SURU_ONLY_RARE = 700   # 組が 名詞＋する だけの所で見るのは、元の名詞が一般の文でこれ以上稀なとき（表に無い語は 800）


def _rare_general(face):
    try:
        import ime_reconvert
        return ime_reconvert._rank(face) >= SURU_ONLY_RARE
    except Exception:
        return False


def propose(text, input_method='kana'):
    tab = _table()
    if not tab:
        return []
    pairs, nouns = tab
    from morphology import tokenize
    toks = list(tokenize(text))
    marks = []
    for i, t in enumerate(toks):
        if not _noun(t) or len(t.surface) < 2 or not _kanji_word(t.surface):
            continue
        ctx = _contexts(toks, i)
        cut = input_method == 'kana' and _cut_object(toks, i)
        if (not ctx and not cut) or any(_count(pairs, k, l, r, t.surface) for k, l, r in ctx):
            continue
        # 組が「名詞＋する」だけの所（追究して）: する はどのサ変の名詞にも付くので、組の回数は名詞の使われやすさを
        # 数えるだけで、同じ読みの名詞の選び分けの証にならない。元の名詞が一般の文で稀（SURU_ONLY_RARE 以上・皆済 治国）なら
        # ほかの組と同じに見る（2026-11-06 紫だけにすると 皆済→開催 などが直らなくなった）。そうでなければ何もしない（2026-11-06 変換ミスの担当: 正しい文 原因を追究して を 追求 に崩した）。CN_PAIR_SURU_ONLY=0
        suru_only = (ctx and not cut and all(k == '続' and r == 'する' for k, l, r in ctx)
                     and os.environ.get('CN_PAIR_SURU_ONLY') != '0')
        if suru_only and not _rare_general(t.surface):
            continue
        here = nouns.get(t.surface, 0)
        best = []
        same = _alternatives(t.surface, _hira(t.reading))
        for alt in (same if ctx else ()):
            c = max(_count(pairs, k, l, r, alt) for k, l, r in ctx)
            # 元の名詞が例文に一度も出ず、候補の組が例文によく在るなら、一般の文の珍しさの差は緩める（来襲の月曜日・紫まで）
            loose = here == 0 and c >= LOOSE_PAIR
            if c >= MIN_PAIR and nouns.get(alt, 0) >= RATIO * max(here, 1) and \
                    _rarer_in_general(t.surface, alt, LOOSE_WF_MARGIN if loose else None):
                best.append((c, alt))
        # 1打違いの読みの名詞（かな入力・母音の段が1つ違う読み）: 元の名詞は例文に一度も出ず、一般の文でもはっきり稀なときだけ
        # 組が「名詞＋する」だけなら、1打違いの読みの名詞（改作 → 解散）は する の付きやすさを数えるだけで選び分けの証に
        # ならない（同じ読みの選び違いより根拠が弱い）。1打違いは見ない（2026-11-09 正しい文 小説を改作した を崩した）。
        # CN_PAIR_KEY_SURU=0 で前のまま
        key_ok = not (suru_only and os.environ.get('CN_PAIR_KEY_SURU') != '0')
        if not best and ctx and input_method == 'kana' and here == 0 and key_ok:
            for alt in _key_alternatives(t.surface, _hira(t.reading)) - same:
                c = max(_count(pairs, k, l, r, alt) for k, l, r in ctx)
                if c >= KEY_PAIR and _rarer_in_general(t.surface, alt, KEY_WF_MARGIN):
                    best.append((c, alt))
        # 行が名詞＋助詞で終わり（述語がまだ無い・〜で単軌を）、組で確かめられない所: 元の名詞が例文に
        # 一度も出ず、一般の文でもはっきり稀で、1打違いの読みの名詞が例文によく出るなら紫（直し先は決めない・2026-11-01 B）
        if not best and cut and here == 0:
            alts = [a for a in _key_alternatives(t.surface, _hira(t.reading))
                    if nouns.get(a, 0) >= CUT_NOUN and _rarer_in_general(t.surface, a, KEY_WF_MARGIN)]
            if alts:
                # 1打違いの名詞が1つだけで、例文に CUT_FIX 回以上出るなら、それに決める（決められなければ紫・2026-11-01 B）
                fix = alts[0] if len(alts) == 1 and nouns.get(alts[0], 0) >= CUT_FIX else None
                marks.append((t.start, t.end, fix))
            continue
        if not best:
            continue
        best.sort(reverse=True)
        if len(best) == 1 and best[0][0] >= FIX_PAIR:
            marks.append((t.start, t.end, best[0][1]))
        else:
            marks.append((t.start, t.end, None))
    try:
        done = {(a, b) for a, b, _r in marks}
        if __import__('os').environ.get('CN_PAIR_PRED') != '0':   # 述語の選び違い（2026-11-05 ローマ字担当）。0 で前のまま
            marks += [m for m in _pred_marks(toks, pairs) if (m[0], m[1]) not in done]
    except Exception:
        pass
    return marks


def repair_line(line, result, decided=(), input_method='kana'):
    if not isinstance(result, dict):
        return result
    done = result.get('corrected') or line
    try:
        marks = propose(done, input_method)
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
            new = new[:s] + rep + new[e:]
            details.append([done[s:e], rep, '語の組'])
        elif not any(x < org[1] and org[0] < y for x, y in odd_now):
            odd_add.append(org)
    if not odd_add and new == done:
        return result
    out = dict(result)
    if odd_add:
        out['odd_spans'] = sorted(set(odd_now) | set(odd_add))
        out['odd_reasons'] = list(result.get('odd_reasons') or ()) + [
            (a, b, f'「{line[a:b]}」は前後の語との組がほとんど使われません。同じ読みの別の語か、1打違いの別の語かもしれません')
            for a, b in odd_add]
    if new != done:
        ops = [o for o in difflib.SequenceMatcher(None, line, new, autojunk=False).get_opcodes() if o[0] != 'equal']
        out.update({'original': line, 'corrected': new, 'changed': True,
                    'details': list(result.get('details') or []) + details,
                    'spans': [[o[3], o[4]] for o in ops], 'original_spans': [[o[1], o[2]] for o in ops]})
    return out
