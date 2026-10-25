# CorrectNote — Copyright (C) 2026 Takahashi Yuu; GPL-3.0-or-later.
# -*- coding: utf-8 -*-
"""English typos that length alone could not settle (2026-10-16).

うにさん chose (2026-10-16) to strengthen the English correction before an
English menu is offered. The six-letter path (`loanword.fix_english_word`)
left two holes:

  - words of five letters or fewer were never fixed (wnat, tge, abot), and
  - with no idea how common a word is, it could not choose between two
    spellings one slip away, and sometimes took the rare one
    (shouls -> shoals while should is far more common).

How common a word is decides here. The numbers are in en_freq.json.gz (built
by tools_local/en_freq/build_en_freq.py from wordfreq; the CC BY-SA 4.0
licence and credits are inside the file under "license"). A value is the Zipf
frequency times ten: 60 is about once in a thousand words, 30 once in a
million.

A word is fixed only when
  - the app does not know the spelling (`en_space._known`: SCOWL, the
    part-of-speech dictionary, names, words the writer has used twice) and
    it is not written often either (the "seen" list: lol, tbh, xbox),
  - it stands in English (`en_space._english_context`; romaji and code are
    left alone), and is not a programming word (`_LEAVE`) or a capitalised
    word inside a sentence (a name),
  - one slip explains it: two letters swapped, a neighbouring key, a vowel
    for a vowel, a letter left out, or an extra key next to its neighbour
    (a doubled key only when 重複補正 is on), and
  - the most common word it can come from is common enough for its length
    and far more common than the next one (`_MIN_ZIPF`, `_MARGIN`) and than
    the typed spelling itself (`_WRITTEN_MARGIN`: blase stays blase).
A capitalised word keeps its first letter (`Teh -> The`, never `Iam -> am`).

Every example here and in tests_en_typo_20261016.py is made up.
"""
import gzip
import json
import os
import sys

FREQUENCIES = 'en_freq.json.gz'

_FREQ = None
_SEEN = frozenset()
_OTHER = {}


def _path():
    base = getattr(sys, '_MEIPASS', None) or os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, FREQUENCIES)


def frequencies():
    """{lowercase word: Zipf x 10}, loaded once (empty if the file is missing)."""
    global _FREQ, _SEEN, _OTHER
    if _FREQ is None:
        try:
            with open(_path(), 'rb') as handle:
                data = json.loads(gzip.decompress(handle.read()).decode('utf-8'))
            _FREQ = data['words']
            _SEEN = frozenset(data.get('seen', ()))
            _OTHER = data.get('other', {})
        except Exception:
            _FREQ = {}
    return _FREQ


def seen(key):
    """A spelling written often that the word lists lack (lol, tbh, xbox)."""
    frequencies()
    return key in _SEEN


def written(key):
    """How often a spelling the word lists lack is written (Zipf x 10,
    0 below 20): blase 22, teh 30."""
    frequencies()
    return _OTHER.get(key, 0)


def available():
    return bool(frequencies())


def zipf(word):
    return frequencies().get((word or '').lower(), 0)


# ---- one slip ----------------------------------------------------------

_LETTERS = 'abcdefghijklmnopqrstuvwxyz'
_VOWELS = frozenset('aeiou')

import keyboard_layout as _KEYBOARD
_NEAR = frozenset()
_INTRUDE = frozenset()


def _rebuild_keyboard():
    # A wrong key is the key beside it on the same row; a key pressed
    # along with the right one may be any of the eight around it, as in
    # Japanese (2026-10-23, うにさん「隣接キーの対象キーは、日本語と同じです」).
    global _NEAR, _INTRUDE
    _NEAR = _KEYBOARD.letter_near_pairs()
    _INTRUDE = _KEYBOARD.letter_intrusion_pairs()


_KEYBOARD.on_change(_rebuild_keyboard)


def _near(a, b):
    return (a, b) in _NEAR


def _doubled_key_allowed():
    try:
        from vocabulary import dup_repair_enabled
        return bool(dup_repair_enabled())
    except Exception:
        return False


def one_slip(key, keep_head=False):
    """{word: slip} for every spelling one slip away from key (lowercase).

    The words are not checked against anything here. keep_head keeps the
    first letter where it is (a capitalised word).
    """
    out = {}
    n = len(key)
    first = 1 if keep_head else 0
    for i in range(first, n - 1):
        if key[i] != key[i + 1]:
            out.setdefault(key[:i] + key[i + 1] + key[i] + key[i + 2:], 'swap')
    for i in range(first, n):
        ch = key[i]
        for alt in _LETTERS:
            if alt != ch and (_near(ch, alt) or (ch in _VOWELS and alt in _VOWELS)):
                out.setdefault(key[:i] + alt + key[i + 1:], 'key')
    for i in range(first, n + 1):
        for alt in _LETTERS:
            out.setdefault(key[:i] + alt + key[i:], 'missing')
    doubled = _doubled_key_allowed()
    for i in range(first, n):
        ch = key[i]
        sides = [key[k] for k in (i - 1, i + 1) if 0 <= k < n]
        if any((ch, c) in _INTRUDE for c in sides) or (doubled and ch in sides):
            out.setdefault(key[:i] + key[i + 1:], 'extra')
    out.pop(key, None)
    return out


# The most common candidate must be at least this common (Zipf x 10) for a
# typed word of this length, and at least _MARGIN above the next candidate.
_MIN_ZIPF = {2: 55, 3: 45, 4: 40, 5: 35}
_MIN_ZIPF_LONG = 30
_MARGIN = 10
# An extra key is the weakest explanation when it lands on a very common
# word: thre is the (extra r) but also there or three (a letter left out),
# tpo is to but also top. A word reached by an extra key must clear the other
# explanations by this much (made-up typos of made-up sentences: of 1,402,
# 27 fewer fixes and 8 fewer wrong ones).
_EXTRA_MARGIN = 15
# A spelling written nearly as often as the word it would become was meant
# (blase, not blade; chillin, not chilling). Typos are far rarer than their
# word: teh 30 / the 77, recieve 28 / receive 49, occured 28 / occurred 46.
_WRITTEN_MARGIN = 15
_ARTICLES = frozenset(('a', 'an', 'the'))


def ranked(key, keep_head=False):
    """[(Zipf x 10, word, slip), ...] of the common words one slip away,
    most common first."""
    freq = frequencies()
    found = [(freq[w], w, k) for w, k in one_slip(key, keep_head).items() if w in freq]
    found.sort(key=lambda t: (-t[0], t[1]))
    return found


def best_word(key, keep_head=False, followed=True):
    """The one common word key is a slip of, or None when two are close.

    followed: another word comes after it. An article needs one, so
    `at thre.` is not `at the.`.
    """
    if not _doubled_key_allowed() and any(
            key[:i] + key[i + 1:] in frequencies()
            for i in range(1, len(key)) if key[i] == key[i - 1]):
        # A doubled key that leaves a word is the slip (ommit is omit).
        # With 重複補正 off it is not fixed, and no other word stands in
        # for it (ommit -> commit), as in the six-letter path (48-VL).
        return None
    found = ranked(key, keep_head)
    if not followed:
        found = [t for t in found if t[1] not in _ARTICLES]
    if not found:
        return None
    top, word, slip = found[0]
    if top < _MIN_ZIPF.get(len(key), _MIN_ZIPF_LONG):
        return None
    if written(key) > top - _WRITTEN_MARGIN:
        return None
    if len(found) > 1 and found[1][0] > top - _MARGIN:
        return None
    if slip == 'extra' and any((k != 'extra' or len(key) == 3)
                               and z >= top - _EXTRA_MARGIN
                               for z, _w, k in found[1:]):
        # (two letters each left by one extra key, ius: is or us)
        return None
    return word


# Programming words the word lists lack, one slip away from a common word
# (bool -> book, sys -> says, struct -> strict, util -> until), and a
# loanword written without its accent (blase). Left as written wherever they
# stand, in this path and the six-letter one.
_LEAVE = frozenset('''
blase
asdict bool bools callee callees caron charref closefd cmp cmps compat ctor
ctors decl decls dest dests dtor fns gid gids gio iff iid memoize memoized
memoizes memoizing nagle parens passwd popen recurse recursed recurses
recursing repl restype rfile rng rvalue lvalue seeked sprintf strs struct
structs sys tix tty ttys uat undecoded util utils wfile
'''.split())


def leave(key):
    """A programming word to leave as written (`_LEAVE`)."""
    return (key or '').lower() in _LEAVE


_PROPER = None


def _proper_names():
    """Words written with a capital (Monday, English), lowercase."""
    global _PROPER
    if _PROPER is None:
        try:
            import seed_english_names
            _PROPER = frozenset(seed_english_names.PROPER_NAMES)
        except Exception:
            _PROPER = frozenset()
    return _PROPER


def recase(word, fixed):
    """fixed (lowercase) in the case the writer used for word."""
    if word.isupper() and len(word) > 1:
        return fixed.upper()
    if word[:1].isupper():
        return fixed[:1].upper() + fixed[1:]
    return fixed


def rival_outweighs(key, target, learned=False):
    """A slip of key toward a far more common word than target (the
    six-letter path's choice). learned: target is the writer's own word."""
    if not available():
        return False
    own = zipf(target)
    floor = max(own, 25) if learned or not own else own
    return any(z >= floor + _MARGIN for z, w, _k in ranked(key) if w != target)


def fix_word(word, store=None, followed=True, at_start=None):
    """The fixed spelling of one unknown English word, or None (en_space
    has checked the context and that the spelling is unknown). followed:
    another word comes after it in the sentence. at_start: a capitalised
    word begins its sentence (False: it stands inside one)."""
    if not available() or not word.isalpha():
        return None
    key = word.lower()
    if len(key) < 3 or seen(key) or key in _LEAVE:
        return None
    if word.isupper() or any(c.isupper() for c in word[1:]):
        return None
    head = word[:1].isupper()
    fixed = best_word(key, keep_head=head, followed=followed)
    if not fixed:
        return None
    if head and at_start is False and fixed not in _proper_names():
        # A capital inside a sentence is a name (Marlet, Kitchem), not
        # a slip of a common word; only a name's own slip is fixed there
        # (Mondya -> Monday).
        return None
    if store is not None and len(key) >= 6:
        # The writer's own words (six letters and up are remembered) that
        # are one slip away compete too: two near spellings, no fix.
        try:
            import loanword
            learned = loanword._english_vocabulary(store)
        except Exception:
            learned = {}
        if any(w in learned and w != fixed for w in one_slip(key, head)):
            return None
    return recase(word, fixed)


# ---- whole words in a sentence ------------------------------------------
#
# These fix a word the app knows, so the words around it must say which one
# was meant. Each rule is narrow on purpose: it fires only where the written
# word cannot stand (`dont`, `i think`, `come form`, `more then`).

import re as _re

_TOKEN = _re.compile(r'[A-Za-z]+')

# A dropped apostrophe. None of these is a word (`cant` `wont` `its` `lets`
# `were` `well` `ill` are, and have their own rules or none).
_APOSTROPHE = {
    'dont': "don't", 'doesnt': "doesn't", 'didnt': "didn't", 'isnt': "isn't",
    'wasnt': "wasn't", 'werent': "weren't", 'arent': "aren't",
    'havent': "haven't", 'hasnt': "hasn't", 'hadnt': "hadn't",
    'wouldnt': "wouldn't", 'couldnt': "couldn't", 'shouldnt': "shouldn't",
    'mustnt': "mustn't", 'neednt': "needn't",
    'im': "I'm", 'ive': "I've", 'youre': "you're", 'youve': "you've",
    'youll': "you'll", 'theyre': "they're", 'theyve': "they've",
    'theyll': "they'll", 'weve': "we've", 'itll': "it'll",
    'thats': "that's", 'whats': "what's", 'theres': "there's",
    'heres': "here's", 'wheres': "where's", 'whos': "who's", 'hows': "how's",
    'shes': "she's", 'hes': "he's",
    'wouldve': "would've", 'couldve': "could've", 'shouldve': "should've",
    'oclock': "o'clock",
}
# Words after which a clause (and so `I'm`) can begin.
_CLAUSE_BEFORE = frozenset((
    'and', 'but', 'so', 'because', 'cause', 'cuz', 'when', 'if', 'that',
    'think', 'guess', 'hope', 'know', 'sure', 'now', 'then', 'like', 'said',
    'since', 'while', 'until', 'unless', 'or', 'maybe', 'well', 'oh', 'yes',
    'yeah', 'no', 'ok', 'okay', 'sorry', 'thanks', 'lol', 'haha'))
_SUBJECTS = frozenset(('i', 'you', 'we', 'they', 'he', 'she', 'it', 'that',
                       'this', 'there', 'who', 'people', 'someone', 'everyone'))
# `cant` (insincere talk) and `wont` (habit) are words, but after a subject
# only the negative fits (`I cant` `it wont`).
_AFTER_SUBJECT = {'cant': "can't", 'wont': "won't"}
# `its` is a word; `its a` `its not` `its been` are not its possessive use.
_ITS_NEXT = frozenset((
    'a', 'an', 'not', 'been', 'going', 'gonna', 'getting', 'so', 'too',
    'really', 'just', 'always', 'never', 'still', 'already', 'almost', 'like',
    'about', 'raining', 'snowing', 'probably', 'definitely', 'actually'))
# ...and before these only when the sentence ends or goes on with to/that.
_ITS_STATE = frozenset((
    'ok', 'okay', 'fine', 'true', 'hard', 'easy', 'nice', 'great', 'good',
    'bad', 'cold', 'hot', 'late', 'early', 'important', 'possible',
    'impossible', 'fun', 'cool', 'weird', 'funny', 'sad', 'amazing', 'done',
    'over', 'time', 'here', 'there', 'free', 'safe', 'normal', 'strange',
    'better', 'worse', 'enough', 'necessary', 'useful', 'easier', 'harder'))
_STATE_TAIL = frozenset(('to', 'that', 'for', 'when', 'if', 'because'))
# ...and never after these (`a song of its time`).
_ITS_OWNER = frozenset(('of', 'in', 'on', 'at', 'for', 'with', 'by', 'from',
                        'to', 'into', 'about', 'before', 'after', 'under',
                        'over', 'and', 'or'))
# `lets` is a word (she lets me); at the start of a sentence before a verb it
# is the suggestion.
_LETS_NEXT = frozenset((
    'go', 'get', 'see', 'do', 'make', 'try', 'start', 'eat', 'meet', 'talk',
    'have', 'take', 'play', 'keep', 'wait', 'call', 'check', 'find', 'look',
    'not', 'just', 'all', 'hope', 'be', 'move', 'begin', 'finish', 'think',
    'ask', 'discuss', 'review', 'grab', 'focus', 'leave', 'stop', 'say'))
# `your` before these is `you're`.
_YOUR_NEXT = frozenset(('a', 'an', 'the', 'not', 'so', 'too', 'gonna'))
_YOUR_END = frozenset(('welcome', 'right', 'wrong', 'sure', 'kidding'))

# Two real words one slip apart, settled by the word next to them.
# from: `come form` `away form` `form now on` `work form home`.
_FROM_BEFORE = frozenset((
    'come', 'comes', 'came', 'coming', 'away', 'far', 'apart', 'different',
    'differs', 'differ', 'aside', 'returned', 'return', 'returning', 'back',
    'arrived', 'arrive', 'arriving', 'heard', 'hear', 'received', 'receive',
    'borrowed', 'borrow', 'moved', 'graduated', 'retired', 'escaped',
    'recovered', 'recover', 'suffer', 'suffers', 'suffered', 'suffering',
    'protect', 'protects', 'protected', 'prevent', 'prevents', 'prevented',
    'learned', 'learnt', 'downloaded', 'download', 'copied', 'removed',
    'remove', 'deleted', 'delete', 'translated', 'imported', 'derived',
    'originally', 'straight', 'directly', 'quit', 'resigned', 'free',
    'separate', 'separated', 'distinct', 'independent', 'absent', 'safe',
    'emails', 'message', 'letter', 'call', 'gift', 'news', 'friends',
    'people', 'someone', 'anyone', 'everyone', 'hello', 'greetings',
    'regards'))
# (only words a verb `form` does not take: clouds form everywhere)
_FROM_AFTER = frozenset(('now', 'home', 'scratch', 'abroad', 'afar'))
_DETERMINERS = frozenset(('a', 'an', 'the', 'this', 'that', 'these', 'those',
                          'my', 'your', 'his', 'her', 'our', 'their', 'its',
                          'each', 'every', 'any', 'some', 'no', 'one', 'which',
                          'what', 'whose', 'another', 'same', 'new', 'online',
                          'paper', 'order', 'application', 'entry', 'contact',
                          'registration', 'consent', 'feedback', 'tax', 'web',
                          'request', 'sign', 'signup', 'login', 'search'))
# than: `more then` `better then I thought`.
_COMPARATIVES = frozenset((
    'more', 'less', 'rather', 'better', 'worse', 'fewer', 'greater', 'larger',
    'smaller', 'bigger', 'higher', 'lower', 'older', 'younger', 'faster',
    'slower', 'longer', 'shorter', 'easier', 'harder', 'cheaper', 'stronger',
    'weaker', 'warmer', 'colder', 'hotter', 'cooler', 'richer', 'poorer',
    'smarter', 'safer', 'nicer', 'quicker', 'louder', 'quieter', 'heavier',
    'lighter', 'busier', 'happier', 'simpler', 'cleaner', 'wider', 'deeper',
    'taller', 'other'))
# then: `and than` `since than` `back than`.
_THEN_BEFORE = frozenset(('and', 'since', 'until', 'till', 'by', 'back',
                          'just', 'but'))
# with: `wit me` (wit is a word: a quick wit).
_WITH_NEXT = frozenset(('me', 'you', 'him', 'her', 'us', 'them', 'my', 'your',
                        'his', 'our', 'their', 'the', 'a', 'an', 'it', 'this',
                        'that', 'some', 'friends', 'family'))
# think: `I thing so`.
_THINK_NEXT = frozenset(('so', 'that', 'about', 'it', 'i', 'you', 'we', 'they',
                         'he', 'she', 'this', 'of', 'the', 'maybe', 'not'))
# whether: `wether or not` (a wether is a sheep).
_WHETHER_NEXT = frozenset(('or', 'it', 'i', 'you', 'we', 'they', 'he', 'she',
                           'the', 'to', 'this', 'that', 'there'))
# where: `were are you` (were cannot ask a question before these).
_WHERE_NEXT = frozenset(('are', 'is', 'do', 'does', 'did', 'can', 'should',
                         'would', 'could', 'will', 'was'))
# off: `turned of the light`.
# (not turn, switch: the turn of the year, the switch of the lamp)
_OFF_BEFORE = frozenset(('turned', 'switched', 'logged', 'kicked'))
_OFF_NEXT = frozenset(('the', 'my', 'your', 'his', 'her', 'our', 'their', 'it',
                       'them', 'this', 'that', 'all'))
# for: `fro you` (only `to and fro` is a word).
# I: `i` before these (en_space._AFTER_I without and, or, too, now, once,
# first, only, even: `i and j`, `i only if`).
try:
    from en_space import _AFTER_I as _I_AFTER
except Exception:
    _I_AFTER = frozenset(('am', 'was', 'have', 'had', 'will', 'would', 'can',
                          'think', 'want', 'know'))
_I_NEXT = _I_AFTER - frozenset(('and', 'or', 'too', 'now', 'once', 'first',
                                'only', 'even'))


def _i_pair(line, nxt):
    """The word after a small i is a verb or an adverb first of all (en_pos:
    `i advise` `i accidentally`), or a contraction (`i don't`). A noun or
    `is` after it (`i is the index`) keeps the letter i."""
    if nxt is None:
        return False
    if _re.match(r"['’](t|ve|ll|d|re)\b", line[nxt[1]:]):
        return True
    try:
        import en_pos
        codes = en_pos.codes_for(nxt[2])
    except Exception:
        return False
    return bool(codes) and codes[0] in 'VR'


def _words(line):
    """[(start, end, word)] of the ASCII words, with what joins them."""
    return [(m.start(), m.end(), m.group(0)) for m in _TOKEN.finditer(line)]


def _joined_by_space(line, a, b):
    """Only spaces (at least one) between positions a and b."""
    gap = line[a:b]
    return bool(gap) and gap.strip(' ') == ''


def _glued(line, s, e):
    """Letters stuck to a digit or a symbol (file.txt, v2, don't, e-mail)."""
    if s > 0 and (line[s - 1].isdigit() or line[s - 1] in "._-@/:\\#&+=%$~*'’"):
        return True
    if e < len(line) and (line[e].isdigit() or line[e] in "_-@/:\\#&+=%$~*'’"):
        return True
    if e < len(line) and line[e] == '.' and not _sentence_end(line, e):
        return True
    return False


_QUOTES = {'"': '"', "'": "'", '“': '”', '‘': '’', '「': '」', '『': '』'}


def _quoted(line, s, e):
    """The word alone inside quotes ("dont"): written as a mention."""
    return (s > 0 and e < len(line) and line[s - 1] in _QUOTES
            and line[e] == _QUOTES[line[s - 1]])


def _sentence_end(line, e):
    try:
        import loanword
        return loanword._sentence_period(line, e)
    except Exception:
        return False


def _recase_phrase(word, fixed):
    """`Dont -> Don't`, `DONT -> DON'T`; `im -> I'm` keeps its I."""
    if word.isupper() and len(word) > 1:
        return fixed.upper()
    if word[:1].isupper():
        return fixed[:1].upper() + fixed[1:]
    return fixed


def _sentence_start(line, s):
    """s begins the line or follows a sentence end (. ! ?) and spaces."""
    i = s
    while i > 0 and line[i - 1] in ' \t"\'(“‘':
        i -= 1
    return i == 0 or line[i - 1] in '.!?\n'


# A period after these is an abbreviation, not the end of a sentence.
_ABBREVIATIONS = frozenset('''
etc vs eg ie approx acc incl esp dept est fig figs no nos vol vols ch sec secs
min mins max cf al mr mrs ms dr st jr sr inc ltd co corp ft lb lbs oz pp
jan feb mar apr jun jul aug sep sept oct nov dec mon tue wed thu fri sat sun
'''.split())
# Words that begin a sentence in everyday writing. Others may be a name
# written small on purpose (`name is the file name`, `git is installed`).
_STARTERS = frozenset('''
we you he she they it there this that these those the my our your his her
their what when where why how who which but so and also then now well
however maybe perhaps please thanks thank sorry yes no yeah ok okay oh hi
hello hey let lets anyway still yet after before today tomorrow yesterday
tonight next last hope see if because since although though once sometimes
usually actually honestly unfortunately luckily finally first
'''.split())


def _sentence_after(line, s):
    """s follows `. ` `! ` `? ` that end a sentence inside the line."""
    i = s
    while i > 0 and line[i - 1] == ' ':
        i -= 1
    if i == s or i == 0 or line[i - 1] not in '.!?':
        return False
    if line[i - 1] != '.':
        return True
    if i >= 2 and line[i - 2] in '.!?':
        return False                     # an ellipsis goes on (`well... ok`)
    m = _re.search(r'([A-Za-z0-9]+)\.$', line[:i])
    if not m or not m.group(1).isalpha() or len(m.group(1)) < 2:
        return False                     # `1.` `J.` `3.5`
    if m.start() > 0 and line[m.start() - 1] == '.':
        return False                     # `e.g.` `a.m.`
    return m.group(1).lower() not in _ABBREVIATIONS


def _starts_capitalised(line, s):
    """Every sentence before s in its ASCII run begins with a capital, and
    there is one: the writer capitalises sentences."""
    a = s
    while a > 0 and line[a - 1].isascii() and line[a - 1] != '\n':
        a -= 1
    first = _TOKEN.search(line, a, s)
    if not first or not (line[a:first.start()].strip(' "\'(') == ''
                         or _sentence_start(line, first.start())):
        return False
    starts = [first] + [m for m in _TOKEN.finditer(line, first.end(), s)
                        if _sentence_after(line, m.start())]
    return all(m.group(0)[:1].isupper() for m in starts)


def line_fixes(line, store=None, taken=()):
    """[(start, end, fixed)] for whole words the sentence shows to be wrong.

    taken: spans already fixed by en_space or the six-letter path.
    """
    if not line or not available():
        return []
    try:
        import en_space
    except Exception:
        return []
    words = _words(line)
    out = []

    def free(s, e):
        return all(e <= a or s >= b for a, b in list(taken) + [(x, y) for x, y, _ in out])

    for n, (s, e, word) in enumerate(words):
        key = word.lower()
        prev = words[n - 1] if n and _joined_by_space(line, words[n - 1][1], s) else None
        nxt = words[n + 1] if n + 1 < len(words) and _joined_by_space(line, e, words[n + 1][0]) else None
        pkey = prev[2].lower() if prev else None
        nkey = nxt[2].lower() if nxt else None
        ends = not _re.match(r'\s*[A-Za-z]', line[e:])
        fixed = None
        if key == 'i' and word == 'i':
            # `i think` `and i went` `i'm`: a lone small i in English
            after = line[e:e + 1]
            if after == "'" or after == '’':
                if _re.match(r"['’](m|ve|ll|d)\b", line[e:]):
                    fixed = 'I'
            elif (s == 0 or line[s - 1] == ' ') and after == ' ' and (
                    nkey in _I_NEXT or nkey in _APOSTROPHE
                    or nkey in _AFTER_SUBJECT or _i_pair(line, nxt)) and not (
                    pkey in ('let', 'integer', 'index', 'variable', 'letter')):
                # only before a word a person says after I (`i think`
                # `i went`); `i` is also a name in a formula (`i such that`
                # `for i in`)
                fixed = 'I'
        elif _glued(line, s, e) or _quoted(line, s, e):
            continue
        elif key == 'im':
            # `im` is also `in` one key off (`born im a small town`); I'm
            # starts a clause
            if not word.isupper() and nxt is not None and (
                    _sentence_start(line, s) or pkey in _CLAUSE_BEFORE):
                fixed = "I'm"
        elif key in _APOSTROPHE and not (word.isupper() and len(word) <= 2):
            fixed = _recase_phrase(word, _APOSTROPHE[key])
        elif key in _AFTER_SUBJECT and pkey in _SUBJECTS:
            fixed = _recase_phrase(word, _AFTER_SUBJECT[key])
        elif key == 'its' and (nkey in _ITS_NEXT
                               or (nkey in _ITS_STATE and pkey not in _ITS_OWNER and (
                                   n + 2 >= len(words) or not _joined_by_space(line, nxt[1], words[n + 2][0])
                                   or words[n + 2][2].lower() in _STATE_TAIL))):
            fixed = _recase_phrase(word, "it's")
        elif key == 'lets' and nkey in _LETS_NEXT and _sentence_start(line, s):
            fixed = _recase_phrase(word, "let's")
        elif key == 'your' and (nkey in _YOUR_NEXT or (
                nkey in _YOUR_END
                and (pkey is None or pkey in _CLAUSE_BEFORE) and (
                n + 2 >= len(words) or not _joined_by_space(line, nxt[1], words[n + 2][0])))):
            # (`you outstayed your welcome` keeps its your)
            fixed = _recase_phrase(word, "you're")
        elif key == 'form' and word.islower() and pkey not in _DETERMINERS and (
                pkey in _FROM_BEFORE or nkey in _FROM_AFTER):
            fixed = 'from'
        elif key == 'then' and pkey in _COMPARATIVES and nxt is not None:
            fixed = _recase_phrase(word, 'than')
        elif key == 'than' and pkey in _THEN_BEFORE:
            fixed = _recase_phrase(word, 'then')
        elif key == 'wit' and nkey in _WITH_NEXT and pkey not in _DETERMINERS:
            fixed = _recase_phrase(word, 'with')
        elif key == 'thing' and pkey in ('i', 'you', 'we', 'they') and nkey in _THINK_NEXT:
            fixed = _recase_phrase(word, 'think')
        elif key == 'wether' and nkey in _WHETHER_NEXT:
            fixed = _recase_phrase(word, 'whether')
        elif key == 'were' and nkey in _WHERE_NEXT and _sentence_start(line, s):
            fixed = _recase_phrase(word, 'where')
        elif key == 'of' and pkey in _OFF_BEFORE and nkey in _OFF_NEXT:
            fixed = _recase_phrase(word, 'off')
        elif key == 'fro' and not (pkey == 'and' and n >= 2 and words[n - 2][2].lower() == 'to'):
            fixed = _recase_phrase(word, 'for')
        elif (word.islower() and key in _STARTERS
              and _sentence_after(line, s) and _starts_capitalised(line, s)):
            # `It rained. we stayed in.`: a sentence after a capitalised
            # one begins with a capital too
            fixed = word[:1].upper() + word[1:]
        if (fixed and word.islower() and fixed[:1].islower()
                and (key in _STARTERS or key in _APOSTROPHE or key in ('its', 'lets'))
                and _sentence_after(line, s) and _starts_capitalised(line, s)):
            # `Thanks! your welcome.` -> `Thanks! You're welcome.`
            fixed = fixed[:1].upper() + fixed[1:]
        if not fixed or fixed == word or not free(s, e):
            continue
        if not en_space._english_context(line, s, e, key, store):
            continue
        out.append((s, e, fixed))
    # Real words wrong where they stand, judged by the words around them
    # (2026-10-23, en_context).
    try:
        import en_context
        out.extend(en_context.fixes(line, store, list(taken) + [(x, y) for x, y, _f in out]))
    except Exception:
        pass
    return out
