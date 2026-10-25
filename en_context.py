"""English words that are real words but wrong where they stand (2026-10-23).

A slip that lands on another real word (`come form the station`,
`better then before`, `I'll see you next weak`) passes every word list.
The words around it show it: for each word, the words one slip away
(`en_typo.one_slip`) and the common words that sound the same are
weighed by how often each stands between the same two neighbours, and
the word is changed only when another one fits far better on both sides.

The counts are in en_context.json.gz (made by
tools_local/en_context/build_en_context.py; the licences are inside the
table). Nothing here names a word: every pair is judged the same way.
"""
import array
import gzip
import json
import math
import os
import sys

import en_typo

_TABLE = None


def _path():
    base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, 'en_context.json.gz')


def _load():
    global _TABLE
    if _TABLE is None:
        try:
            with gzip.open(_path(), 'rt', encoding='utf-8') as f:
                raw = json.load(f)
            sounds = {}
            for group in raw.get('homophones', ()):
                for w in group:
                    sounds[w] = tuple(x for x in group if x != w)
            pairs = raw['pairs']
            starts = array.array('I', [0])
            at = pairs.find('\n')
            while at >= 0:
                starts.append(at + 1)
                at = pairs.find('\n', at + 1)
            _TABLE = (raw['scale'], raw['unigram'], (pairs, starts), sounds)
        except Exception:
            _TABLE = False
    return _TABLE


def available():
    return bool(_load())


# A pair the table lacks was seen fewer times than the rarest pair kept
# (about 6.4 million, ln = 15.67). Two words that happen to stand together
# no more often than chance (rare words) are guessed from their own counts,
# never above that floor.
_FLOOR = 15.67 - math.log(2)
# ln of the pair counts runs about ln(40) above the single-word counts.
_PAIR_SCALE = math.log(40)
_TOTAL = 27.02            # ln of all the single-word counts
_RARE = 9.0               # ln count of a word the table lacks

# The other word must fit this much better (ln odds) to replace a word one
# slip away, and to replace a word that sounds the same. Made-up sentences:
# of 914 slips onto real words, 521 fixed and 12 changed to a third word;
# of 431 correct lines and 539 lines of names, codes and casual English,
# none changed.
_SLIP_MARGIN = 5.0
_SOUND_MARGIN = 4.0
# Seen beside one word only (the start or end of a sentence): `He past
# the exam` is not `The past the exam`.
_ONE_SIDE = 2.0
# Seen before nothing (the end of a sentence): the table does not know
# which words end sentences.
_AT_END = 4.0
# Words that need another word after them (articles, subject pronouns,
# possessives, conjunctions, prepositions that take an object).
_NEVER_LAST = frozenset('''
a an the i he she we they my your his her its our their and or but nor if
because although though while whether than of to from with at by for into
onto upon about as so
'''.split())
# Every word weighed here is a common one: the typed word and its
# replacement (Zipf x 10).
_MIN_ZIPF = 30


def _uni(w):
    t = _load()
    v = t[1].get(w)
    return v / t[0] if v is not None else _RARE


def _count(a, b):
    """The stored count of `a b`, or None."""
    pairs, starts = _load()[2]
    key = a + ' ' + b + '\t'
    lo, hi = 0, len(starts)
    while lo < hi:
        mid = (lo + hi) // 2
        s = starts[mid]
        if pairs[s:s + len(key)] < key:
            lo = mid + 1
        else:
            hi = mid
    if lo < len(starts):
        s = starts[lo]
        if pairs.startswith(key, s):
            e = pairs.find('\n', s)
            return int(pairs[s + len(key):e if e >= 0 else len(pairs)])
    return None


def _expected(a, b):
    """ln of how often a b would stand together by chance."""
    return _PAIR_SCALE + _uni(a) + _uni(b) - _TOTAL


def _pair(a, b):
    t = _load()
    v = _count(a, b)
    if v is not None:
        return v / t[0]
    return min(_FLOOR, _expected(a, b))


def _known(a, b):
    return _count(a, b) is not None


def _fit(left, w, right):
    s = 0.0
    if left is not None:
        s += _pair(left, w)
    if right is not None:
        s += _pair(w, right)
    if left is not None and right is not None:
        s -= _uni(w)
    return s


def _variant(a, b):
    """British and American spellings of one word (color/colour,
    center/centre, realize/realise, traveled/travelled)."""
    if len(a) > len(b):
        a, b = b, a
    for x, y in (('or', 'our'), ('er', 're'), ('ize', 'ise'), ('yze', 'yse'),
                 ('l', 'll'), ('og', 'ogue'), ('ense', 'ence')):
        for i in range(len(a)):
            if a[i:i + len(x)] == x and a[:i] + y + a[i + len(x):] == b:
                return True
            if a[i:i + len(y)] == y and a[:i] + x + a[i + len(y):] == b:
                return True
    return False


# A word that is also a pronoun's contraction with its apostrophe left out
# (ill / I'll, were / we're, well / we'll, shed / she'd) may begin a clause
# as that contraction; at the start of a sentence it is not judged here.
_CONTRACTED = frozenset(
    p + t for p in ('i', 'you', 'he', 'she', 'it', 'we', 'they', 'that',
                    'there', 'who', 'what')
    for t in ('ll', 're', 'd', 's', 've', 'm'))


def best(left, key, right):
    """The word that fits between left and right far better than key, or
    None. left / right: the lowercase neighbour, or None."""
    if not available() or (left is None and right is None):
        return None
    if en_typo.zipf(key) < _MIN_ZIPF or en_typo.leave(key):
        return None
    if left is None and key in _CONTRACTED:
        return None
    sounds = _load()[3]
    kinds = dict.fromkeys(en_typo.one_slip(key), _SLIP_MARGIN)
    for w in sounds.get(key, ()):
        kinds.setdefault(w, _SOUND_MARGIN)
    base = _fit(left, key, right)
    found = None
    for w, margin in kinds.items():
        if en_typo.zipf(w) < _MIN_ZIPF or _variant(key, w):
            continue
        # it must be seen beside each neighbour, not only guessed
        if left is not None and not _known(left, w):
            continue
        if right is not None and not _known(w, right):
            continue
        if right is None:
            # the end of a sentence: nothing is known of what may end one,
            # so a word that never ends a sentence is not put there
            # (`Hasan said hi.` is not `said he.`)
            if w in _NEVER_LAST:
                continue
            margin += _AT_END
        elif left is None:
            margin += _ONE_SIDE
        gain = _fit(left, w, right) - base - margin
        if gain > 0 and (found is None or gain > found[0]):
            found = (gain, w)
    return found[1] if found else None


# A word no list knows (lare: late, large, lane...) whose one-slip words are
# weighed by the words around it; the best must beat the next by this much.
_UNKNOWN_MARGIN = 3.0


def best_unknown(left, key, right):
    """The common word an unknown spelling was meant to be, chosen by the
    words around it, or None."""
    if not available() or (left is None and right is None):
        return None
    if en_typo.zipf(key) or en_typo.seen(key) or en_typo.written(key) or en_typo.leave(key):
        return None
    if not en_typo._doubled_key_allowed() and any(
            key[:i] + key[i + 1:] in en_typo.frequencies()
            for i in range(1, len(key)) if key[i] == key[i - 1]):
        # a doubled key with 重複補正 off: not fixed, and no other word
        # stands in for it (ommit is not commit), as in en_typo
        return None
    cands = en_typo.one_slip(key)
    scored = []
    for w in cands:
        if en_typo.zipf(w) < _MIN_ZIPF:
            continue
        if left is not None and not _known(left, w):
            continue
        if right is not None and not _known(w, right):
            continue
        if right is None and w in _NEVER_LAST:
            continue
        scored.append((_fit(left, w, right), w))
    if not scored:
        return None
    scored.sort(reverse=True)
    margin = _UNKNOWN_MARGIN + (_AT_END if right is None else _ONE_SIDE if left is None else 0)
    if len(scored) > 1 and scored[1][0] > scored[0][0] - margin:
        return None
    return scored[0][1]


def unknown_fix(line, s, e, word, typo):
    """For an unknown word at line[s:e]: the word the neighbours choose,
    '' when they reject `typo` (en_typo's choice by frequency alone), or
    None when they have nothing to say."""
    if not available() or not word.isalpha() or not word[1:].islower():
        return None
    words = en_typo._words(line)
    n = next((i for i, w in enumerate(words) if w[0] == s and w[1] == e), None)
    if n is None:
        return None
    left = _neighbour(line, words, n, -1, s, e)
    right = _neighbour(line, words, n, 1, s, e)
    if left is None and right is None:
        return None
    key = word.lower()
    if word[:1].isupper() and not en_typo._sentence_start(line, s):
        return None                      # a name
    chosen = best_unknown(left, key, right)
    if chosen:
        return en_typo.recase(word, chosen)
    if typo and left is not None and right is not None:
        t = typo.lower()
        if (not _known(left, t) and not _known(t, right)
                and max(_expected(left, t), _expected(t, right)) > _FLOOR):
            # common enough that either pair would have been seen if it
            # were said: `Sounds god to me` fits neither side
            return ''
    return None


def _neighbour(line, words, n, step, s, e):
    """The lowercase word beside words[n] (step -1 / +1) when only spaces
    join them and it is an ordinary word (no capital inside a sentence,
    no apostrophe or symbol stuck to it)."""
    m = n + step
    if not 0 <= m < len(words):
        return None
    a, b, word = words[m]
    if not (en_typo._joined_by_space(line, b, s) if step < 0
            else en_typo._joined_by_space(line, e, a)):
        return None
    if en_typo._glued(line, a, b):
        return None
    if word[:1].isupper() and word != 'I' and not (
            step < 0 and en_typo._sentence_start(line, a)):
        return None
    if not en_typo.zipf(word.lower()) and not en_typo.seen(word.lower()):
        return None                      # a slip itself tells nothing
    return word.lower()


def fixes(line, store=None, taken=()):
    """[(start, end, fixed)] for real words the words around them show to
    be wrong. taken: spans already fixed."""
    if not line or not en_typo.available() or not available():
        return []
    try:
        import en_space
    except Exception:
        return []
    words = en_typo._words(line)
    out = []
    for n, (s, e, word) in enumerate(words):
        if len(word) < 2 or any(not (e <= a or s >= b) for a, b in taken):
            continue
        if not word.islower() and not (
                word[1:].islower() and en_typo._sentence_start(line, s)):
            continue                     # a name, an acronym, `I`, camelCase
        if en_typo._glued(line, s, e) or en_typo._quoted(line, s, e):
            continue
        key = word.lower()
        left = _neighbour(line, words, n, -1, s, e)
        right = _neighbour(line, words, n, 1, s, e)
        w = best(left, key, right) or best_unknown(left, key, right)
        if not w:
            continue
        if not en_space._english_context(line, s, e, key, store):
            continue
        out.append((s, e, en_typo.recase(word, w)))
    return out
