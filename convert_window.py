"""
変換ウィンドウ（2026-10-26・うにさんの指定）。

ボタンメニューの「文変換」（狭いと「文」・再変換の次。2026-10-26 うにさん）を押すと別ウィンドウが開く。

    友達と映画館で映画を見た。          ← 1行目: 本体で選んでいる範囲（選び直すとすぐ変わる）
                                         ← 0.5行分の間
    映画を見た。友達と映画館で。         ← 文節の並べ替えと倒置（述語の後ろへ回す）
    映画を友達と映画館で見た。
    …
    (I) saw 映画 at 映画館 with 友達.    ← 最後に英語の文法・名詞は日本語

2行目から下は単語帳と同じく、クリックで入力中の窓に入る（クリップボードにも入る。
単語帳の「クリップボードに入れる」の設定に従う）。窓の横幅はいちばん長い行に合わせる。
同じ文は覚えておき（最近の 256 文）、選び直したときにすぐ出す。
補正には使っていない（補正の結果は変わらない）。
"""

import os
import re
import time
import tkinter as tk
import tkinter.font as tkfont
from collections import OrderedDict

_SENT_END = '。．！？!?'
_COMMA = '、，,'
_MARK = re.compile(r'^[\s\u3000]*(?:[・･●○■□◆◇▪•‐\-–—*＊※]|[0-9０-９]+[.)．）]|[（(][0-9０-９]+[）)]|[①-⑳])[\s\u3000]*')
_OPEN = '（(「『【［[〈《'
_LIMIT = 60          # 1文から出す並びの数の上限（文節が多いとき）
_CACHE_SIZE = 256


def _t(ja, en):
    """画面の言語が英語なら en（Language メニュー・ui_lang）。訳し直されないよう raw にする。"""
    try:
        import ui_lang
        if not ui_lang.is_japanese():
            return ui_lang.raw(en)
        return ui_lang.raw(ja)
    except Exception:
        return ja


# ------------------------------------------------------------
# 文と文節に分ける
# ------------------------------------------------------------

def sentences(text):
    """選んだ範囲 → 文の並び（文末の記号は付けたまま）。空の行は捨てる。"""
    out = []
    # タブで区切った所（表の升）は別々の文（うにさん 14:57Z）
    for line in re.split(r'[\r\n\t]+', text):
        # 英文は . ! ? と空白で切る（うにさん 15:04Z・15:05Z 英文も変換する）
        ends = _SENT_END + ('.' if _is_english(line) else '')
        for m in re.finditer(rf'[^{ends}]+[{ends}]*', line):
            s = m.group(0).strip()
            if s.strip(_SENT_END + ' 　'):
                out.append(s)
    return out


def _is_english(text):
    try:
        from en_convert import is_english
        return is_english(text)
    except Exception:
        return False


def _tokens(text):
    from context_skeleton import _tokenizer
    return list(_tokenizer().tokenize(text))


def phrases(sentence):
    """文 → (述語より前の文節の並び, 述語, 文末の記号)。

    文節の切れ目:
    - 格助詞・係助詞・副助詞の後ろ（「の」と並立の「と・や」は名詞をつなぐので切らない）
    - 副詞の後ろ、読点の後ろ
    - 「毎朝」「昨日」のような副詞のはたらきをする名詞の後ろ（続きが助詞・数・辞書の1語でないとき）
    残りの最後の塊が述語。
    """
    from context_skeleton import is_noun_word
    body = sentence.rstrip(_SENT_END + _COMMA)
    end = sentence[len(body):]
    toks = _tokens(body)
    out, cur = [], ''
    for i, t in enumerate(toks):
        major, sub = (t.part_of_speech.split(',') + ['*'])[:2]
        nxt = toks[i + 1] if i + 1 < len(toks) else None
        nmajor, nsub = ((nxt.part_of_speech.split(',') + ['*'])[:2] if nxt else ('', ''))
        if major == '記号' and t.surface in _COMMA:
            # 読点は前の文節に付けたまま（並べ替えても文の区切りが残る）
            if cur:
                out.append(cur + '、')
            elif out and not out[-1].endswith('、'):
                out[-1] += '、'
            cur = ''
            continue
        cur += t.surface
        if nxt is None:
            break
        if nmajor == '助詞' or nmajor == '助動詞':
            continue
        close = False
        if major == '助詞' and sub in ('格助詞', '係助詞', '副助詞', '副助詞／並立助詞／終助詞'):
            close = t.surface != 'の'
        elif major == '助詞' and sub == '並立助詞':
            # 「猫と犬が」は1つ、「友達と映画館で」は2つ（続く名詞の助詞が が・を・は・も・の なら並び）
            close = _after_nouns(toks, i + 1) not in ('が', 'を', 'は', 'も', 'の', 'や', 'と')
        elif major == '副詞':
            close = True
        elif major == '形容詞' and nmajor == '動詞' and nsub == '自立':
            close = True    # 「早く寝た」の「早く」
        elif major == '名詞' and sub == '副詞可能':
            close = (nmajor != '名詞' or nsub != '数') and not is_noun_word(t.surface + nxt.surface)
        elif major == '助詞' and sub == '接続助詞' and nmajor not in ('動詞', '形容詞'):
            close = True
        if close:
            out.append(cur)
            cur = ''
    if not cur and out:
        cur = out.pop()
    # 「中止になった」「静かにする」の「〜に」は述語と1つ
    if out and out[-1].endswith('に') and _base_of(cur) in ('なる', 'する'):
        cur = out.pop() + cur
    return out, cur, end


def _after_nouns(toks, j):
    """toks[j] から名詞（接頭・接尾を含む）が続いた後の最初の助詞。"""
    while j < len(toks) and toks[j].part_of_speech.split(',')[0] in ('名詞', '接頭詞'):
        j += 1
    if j < len(toks) and toks[j].part_of_speech.split(',')[0] == '助詞':
        return toks[j].surface
    return ''


def _base_of(pred):
    toks = _tokens(pred)
    for t in toks:
        if t.part_of_speech.split(',')[0] == '動詞':
            return t.base_form
    return ''


def _perms_within(n, budget):
    """入れ替えの数（転倒数）が budget 以下の並べ替えを、辞書順に (並び, 転倒数) で出す。
    全部（n!）は作らない。"""
    out = []

    def walk(prefix, rest, inv):
        if not rest:
            out.append((tuple(prefix), inv))
            return
        for pos, x in enumerate(rest):
            # x を先に置くと、rest の中で x より前（小さい）にあるものの数だけ転倒が増える
            if inv + pos > budget:
                break
            walk(prefix + [x], rest[:pos] + rest[pos + 1:], inv + pos)

    walk([], list(range(n)), 0)
    return out


def reorderings(sentence, limit=_LIMIT):
    """文節の並べ替えと倒置。

    述語より前の文節を並べ替え、そのうち後ろの何個かを述語の後ろへ回す（倒置）:
        友達と映画館で映画を見た。
        → 映画を見た。友達と映画館で。 / 映画を友達と映画館で見た。 / 見た。友達と映画館で映画を。 …
    元の文と同じものは出さない。多すぎるときは元の語順から遠くないもの（入れ替えの数＋
    述語の後ろへ回した数が小さいもの）を limit 個まで残す。遠さを1ずつ広げながら作り、
    limit 個に届いたら止めるので、文節が多くても全部の並べ替え（n!×(n+1)）は作らない。
    並びは、頭に来る文節が原文で前にあるものから（述語が頭のものは最後）。
    """
    # 行頭の「・」「1.」「（1）」「①」のような印は頭に置いたまま（うにさん 15:01Z）
    mark = _MARK.match(sentence)
    if mark and mark.end() < len(sentence):
        return [mark.group(0) + x for x in reorderings(sentence[mark.end():], limit)]
    args, pred, end = phrases(sentence)
    if not args or not pred:
        return []
    # 文の途中（「そこからすぐ上は」のように述語で終わらない、または読点で終わる）なら、
    # 倒置の区切りも末尾も読点（うにさん 14:50Z「そこから上はの次は読点が相応しい。末尾は読点になる」）
    if any(x.lstrip() and x.lstrip()[0] in _OPEN for x in args + [pred]):
        # 「くぅーん（犬の鳴き声）」のような括弧の注は区切らずにつなぐ（うにさん 14:53Z「中間に句点が要らない」）
        sep = ''
    elif (end and end[0] in _COMMA) or (not end and not _ends_like_sentence(pred)):
        sep, end = '、', '、'
        if not original_end_comma(sentence) and _ends_with_noun(pred):
            end = '。'      # 名詞で終わる句（体言止め）は末尾が句点（うにさん 15:59Z「文末は句点でよい」）
    else:
        sep, end = '。', (end or '。')
    n = len(args)
    original = sentence.rstrip(_SENT_END + _COMMA) + end
    max_dist = n * (n - 1) // 2 + n

    def text(perm, k):
        before = [args[i] for i in perm[:k]]
        after = [args[i] for i in perm[k:]]
        # 原文で読点の付いた文節（「ほら、」）は、文末に来るとき以外は読点を残す（うにさん 14:54Z）
        s = ''.join(before) + pred
        if after:
            s += sep + ''.join(after).rstrip('、')
        return s + end

    # 助詞で終わる並び（映画を見た。友達と映画館で。）は出さない。全部そうなるときだけ1つ出す
    # （うにさん 16:12Z「助詞で終わる日本語を除外する。ただし候補が1つもなくなる時は、1つだけ」）
    tail_particle = [_ends_with_particle(a) for a in args] + [_ends_with_particle(pred)]
    spare = None
    budget = 0
    while True:
        found = {}
        for perm, inv in _perms_within(n, budget):
            for k in range(n, max(-1, n - (budget - inv) - 1), -1):   # 述語の前に残す数
                s = text(perm, k)
                head = perm[0] if k else n     # 頭に来る文節の原文での順番（述語が頭なら最後）
                key = (inv + (n - k), head, perm, -k)
                if tail_particle[perm[-1] if k < n else n]:
                    if s not in (original, sentence) and (spare is None or key < spare[1]):
                        spare = (s, key)
                    continue
                if s not in found or key < found[s]:
                    found[s] = key
        for s in (original, sentence):
            found.pop(s, None)
        if len(found) >= limit or budget >= max_dist:
            break
        budget += 1
    if not found and spare is not None:
        found = {spare[0]: spare[1]}
    chosen = sorted(found.items(), key=lambda x: x[1])[:limit]
    # 原文の最初の文節が頭に来るものから並べる（うにさん 05:04Z「友達が頭にくるものを上から、その次は映画館」）
    chosen.sort(key=lambda x: x[1][1:])
    return [s for s, _ in chosen]


def _ends_like_sentence(pred):
    """述語の塊が動詞・形容詞・助動詞で終わるか（終助詞は飛ばす）。"""
    for t in reversed(_tokens(pred)):
        major, sub = (t.part_of_speech.split(',') + ['*'])[:2]
        if major == '記号' or (major == '助詞' and sub == '終助詞'):
            continue
        return major in ('動詞', '形容詞', '助動詞')
    return False


def original_end_comma(sentence):
    return sentence.rstrip()[-1:] in _COMMA


_SYN_PER_WORD = 8      # 1語から出す類語の数（最初の意味から）
_SYN_LIMIT = 24        # 類語の行の上限


def synonym_lines(sentence, per_word=_SYN_PER_WORD, limit=_SYN_LIMIT):
    """原文の語を類語に置き換えた行（うにさん 16:12Z「類語がある単語は、原文を類語に置き換えた
    パターンも書く」）。類語は本体の候補欄と同じ synonyms.py（分類語彙表）。
    類語のある語は全部同時に置き換える（うにさん 17:08Z「ひとつずつ並べずに、候補があるものを同時に
    組み合わせる」）。各語の1番目の類語どうしの組から、類語の順番の和が小さい組の順に limit 行まで。"""
    try:
        import synonyms
        toks = _tokens(sentence)
    except Exception:
        return []
    pos = 0
    spans = []
    for t in toks:
        start = sentence.find(t.surface, pos)
        if start < 0:
            continue
        pos = start + len(t.surface)
        spans.append((t, start, pos))
    slots = []      # (始め, 終わり, [類語…])
    i = 0
    while i < len(spans):
        t, a, z = spans[i]
        major = t.part_of_speech.split(',')[0]
        j = i + 1
        if major in ('動詞', '形容詞'):
            # 活用の尾（た・ない など）まで1語として引く（大きかった → でかかった）
            while j < len(spans) and spans[j][0].part_of_speech.split(',')[0] == '助動詞' and spans[j][1] == spans[j - 1][2]:
                j += 1
        if major in ('名詞', '動詞', '形容詞', '副詞', '連体詞'):
            z = spans[j - 1][2]
            try:
                senses = synonyms.synonyms(sentence[a:z])
            except Exception:
                senses = []
            cands = [c for c in (senses[0] if senses else [])[:per_word] if c != sentence[a:z]]
            if cands:
                slots.append((a, z, cands))
        i = j
    if not slots:
        return []
    # 各語の候補は繰り返さない（うにさん 10-27 01:18Z）: k 行目は各語の k 番目の類語。
    # 候補が尽きた語は原文のまま書き、原文と同じ所は灰色（_Row.gray）。
    # 助詞は直前の語が灰色のときだけ灰色（うにさん 10-27 01:50Z）。類語の1行目は灰色にしない。
    def between(text, start, prev_gray, gray):
        pos = 0
        for t in (_tokens(text) if text else ()):
            i = text.find(t.surface, pos)
            if i < 0:
                continue
            pos = i + len(t.surface)
            g = prev_gray if t.part_of_speech.split(',')[0] == '助詞' else True
            if g:
                gray.append((start + i, start + pos))
            prev_gray = g
        return prev_gray

    out = []
    for k in range(max(len(c) for _, _, c in slots)):
        line, last, gray, prev = '', 0, [], True
        for a, z, cands in slots:
            prev = between(sentence[last:a], len(line), prev, gray)
            line += sentence[last:a]
            if k < len(cands):
                line += cands[k]
                prev = False
            else:
                gray.append((len(line), len(line) + z - a))
                line += sentence[a:z]
                prev = True
            last = z
        between(sentence[last:], len(line), prev, gray)
        line += sentence[last:]
        if not out:
            gray = []
        if line != sentence and line not in out:
            out.append(_Row(line, [(a, z) for a, z in gray if z > a]))
            if len(out) >= limit:
                break
    return out


class _Row(str):
    """行の文字列＋灰色にする範囲 [(始め, 終わり)…]。"""

    def __new__(cls, text, gray=()):
        self = str.__new__(cls, text)
        self.gray = list(gray)
        return self


def _smallest_combos(sizes, count):
    """各語の類語の番号の組を、(番号の和, 組) の小さい順に count 個まで出す。

    sorted(itertools.product(...)) と同じ順だが、全部の組（語ごとの数の掛け算）は作らない。
    類語の多い語が並ぶ長い文で、組が数千万になって窓が固まるのを防ぐ（2026-10-26 PC の確かめ:
    「大きい箱」×9 で 9.5 秒、1つ増えるごとに約6倍）。"""
    import heapq
    start = tuple(0 for _ in sizes)
    heap, seen, out = [(0, start)], {start}, []
    while heap and len(out) < count:
        total, combo = heapq.heappop(heap)
        out.append(combo)
        for i, size in enumerate(sizes):
            if combo[i] + 1 < size:
                nxt = combo[:i] + (combo[i] + 1,) + combo[i + 1:]
                if nxt not in seen:
                    seen.add(nxt)
                    heapq.heappush(heap, (total + 1, nxt))
    return out


def _ends_with_particle(phrase):
    """文節が助詞で終わるか（読点・記号は飛ばす）。"""
    for t in reversed(_tokens(phrase)):
        major = t.part_of_speech.split(',')[0]
        if major == '記号':
            continue
        return major == '助詞'
    return False


def _ends_with_noun(pred):
    for t in reversed(_tokens(pred)):
        major = t.part_of_speech.split(',')[0]
        if major == '記号':
            continue
        return major == '名詞'
    return False


def english_order(sentence):
    """英語の文法・名詞は日本語（読めなければ None）。省いた主語の (I) は付けない
    （うにさん 14:52Z「英文の候補に頭に(I)と付くが、付けない」）。"""
    try:
        from context_skeleton import skeleton
        got = skeleton(_MARK.sub('', sentence, count=1).rstrip(_SENT_END + _COMMA))
    except Exception:
        return None
    if not got or '[' in got:
        return None     # 述語が読めなかった（[くい] のような行は出さない）
    if got.startswith('(I) '):
        got = got[4:]
        got = got[:1].upper() + got[1:]
    return got


_cache = OrderedDict()


def sections_for(sentence):
    """1文 → (倒置の行, 類語の行, 英語の並びの行)。最近の文は覚えておく。"""
    got = _cache.get(sentence)
    if got is not None:
        _cache.move_to_end(sentence)
        return got
    syn = []
    if _is_english(sentence):
        # 英文 → 英文の倒置、最後に日本語の文法・名詞は英語の並び
        try:
            from en_convert import english_reorderings, japanese_order
            body = _MARK.match(sentence)
            mark = body.group(0) if body else ''
            lines = [mark + x for x in english_reorderings(sentence[len(mark):])]
            eng = japanese_order(sentence[len(mark):])
        except Exception:
            lines, eng = [], None
    else:
        lines = reorderings(sentence)
        syn = [x for x in synonym_lines(sentence) if x not in lines]
        eng = english_order(sentence)
    got = (tuple(lines), tuple(syn), (eng,) if eng else ())
    _cache[sentence] = got
    while len(_cache) > _CACHE_SIZE:
        _cache.popitem(last=False)
    return got


def lines_for(sentence):
    """1文 → 窓に出す行（倒置、類語、最後に英語の並び）。"""
    return tuple(x for part in sections_for(sentence) for x in part)


_LONG = 30      # これ以上長い選択は最初の文末までだけ（うにさん 10-27 02:14Z）


def first_line(selection):
    for x in selection.splitlines():
        if x.strip():
            break
    else:
        return ''
    # 長い選択は最初の文末（。！？ など）で区切り、後ろは出さない（下に並べ直さない）
    if len(x.strip()) >= _LONG:
        m = re.search(rf'[{_SENT_END}]+', x)
        if m and x[m.end():].strip():
            x = x[:m.end()]
    return x


def build_sections(selection):
    """選んだ範囲 → (1行目, [倒置の行], [類語の行], [英語の並びの行])。"""
    # 複数行を選んだときは一番上の行だけ（うにさん 10-27 01:18Z）
    selection = first_line(selection)
    head = selection.strip().replace('\t', '\u3000\u3000')
    parts = ([], [], [])
    seen = set()
    for s in sentences(selection)[:1]:      # 区切った後ろを下に並べ直さない（10-27 02:14Z）
        for out, got in zip(parts, sections_for(s)):
            for line in got:
                if line not in seen:
                    seen.add(line)
                    out.append(line)
    return (head,) + parts


def build_lines(selection):
    """選んだ範囲 → (1行目, 2行目から下の行)。"""
    head, *parts = build_sections(selection)
    return head, [x for part in parts for x in part]


# ------------------------------------------------------------
# ウィンドウ
# ------------------------------------------------------------

def _pos_styles(app):
    """本体の欄の品詞のタグ（pos_font_N の大きさ・pos_color_N の色）→ {品詞: {font, foreground}}。"""
    editor = getattr(app, 'editor', None) if app is not None else None
    if editor is None:
        return {}
    try:
        from pos_font import POS_FONT_TAGS, POS_COLOR_TAGS
    except ImportError:
        return {}
    out = {}
    for tags, opt in ((POS_FONT_TAGS, 'font'), (POS_COLOR_TAGS, 'foreground')):
        for major, tag in tags.items():
            try:
                value = editor.tag_cget(tag, opt)
            except tk.TclError:
                continue
            if value:
                out.setdefault(major, {})[opt] = value
    return out


_POS_RUNS = OrderedDict()   # 行の文字列 → pos_runs の答え（窓を開いている間・閉じたら捨てる）
_POS_RUNS_LIMIT = 400


def pos_runs(text):
    """文 → 本体と同じ (品詞, 始め, 終わり) の並び（pos_font.spans）。行の文字列で控える
    （同じ行は窓を開き直しても形態素解析し直さない。2026-10-27）。"""
    got = _POS_RUNS.get(text)
    if got is not None:
        _POS_RUNS.move_to_end(text)
        return got
    got = _pos_runs(text)
    _POS_RUNS[text] = got
    while len(_POS_RUNS) > _POS_RUNS_LIMIT:
        _POS_RUNS.popitem(last=False)
    return got


def _pos_runs(text):
    try:
        from pos_font import spans
    except ImportError:
        return ()
    tokens = []
    pos = 0
    try:
        toks = _tokens(text)
    except Exception:
        return ()
    for t in toks:
        start = text.find(t.surface, pos)
        if start < 0:
            continue
        end = start + len(t.surface)
        label = ':'.join(x for x in t.part_of_speech.split(',') if x != '*')
        tokens.append((t.surface, label, '', start, end))
        pos = end
    try:
        return spans(text, tokens)
    except Exception:
        return ()


_GRAY = '#808080'
_GRAY_FG = 0.3      # 灰色＝文字色を背景色へ寄せる割合の残り（小さいほど見えにくい。うにさん 10-27 01:18Z）


def _faint(owner):
    try:
        r = owner.rows
        f = [v // 257 for v in r.winfo_rgb(owner.fg)]
        b = [v // 257 for v in r.winfo_rgb(owner.bg)]
        return '#%02x%02x%02x' % tuple(round(b[i] + (f[i] - b[i]) * _GRAY_FG) for i in range(3))
    except Exception:
        return _GRAY


def _common_prefix(a, b):
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return n


def _work_area(win):
    """窓が載っている画面の作業域 (left, top, right, bottom)（Windows の MonitorFromWindow・rcWork）。
    Windows 以外・取れないときは None。"""
    if os.name != 'nt':
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class _MonitorInfo(ctypes.Structure):
            _fields_ = [('cbSize', wintypes.DWORD), ('rcMonitor', wintypes.RECT),
                        ('rcWork', wintypes.RECT), ('dwFlags', wintypes.DWORD)]
        u32 = ctypes.windll.user32
        ancestor = ctypes.WINFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint)(('GetAncestor', u32))
        from_window = ctypes.WINFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint)(('MonitorFromWindow', u32))
        info = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p)(('GetMonitorInfoW', u32))
        hwnd = ancestor(int(win.winfo_id()), 2) or int(win.winfo_id())      # GA_ROOT
        monitor = from_window(hwnd, 2)                                     # MONITOR_DEFAULTTONEAREST
        if not monitor:
            return None
        mi = _MonitorInfo()
        mi.cbSize = ctypes.sizeof(_MonitorInfo)
        if not info(monitor, ctypes.byref(mi)):
            return None
        r = mi.rcWork
        return r.left, r.top, r.right, r.bottom
    except Exception:
        return None


class _Line:
    """1行。Text で品詞の大きさと色を付ける。command があればクリックで入れる。"""

    def __init__(self, owner, text, command, styles, pad_x, gray_upto=0, gray=()):
        self.text = text
        self.command = command
        bg, fg = owner.bg, owner.fg
        self.frame = tk.Frame(owner.rows, bg=bg)
        self.frame.pack(fill='x')
        w = self.widget = tk.Text(self.frame, bg=bg, fg=fg, font=owner.font, bd=0,
                                  highlightthickness=0, wrap='none', height=1, padx=pad_x, pady=1,
                                  cursor='hand2' if command else 'arrow', insertwidth=0,
                                  selectbackground=bg, inactiveselectbackground=bg,
                                  exportselection=False, takefocus=0)
        w.pack(fill='both', expand=True)
        for major, opts in styles.items():
            w.tag_configure('pos_' + str(abs(hash(major))), **opts)
        w.insert('1.0', text)
        if styles:
            for major, a, z in pos_runs(text):
                if major in styles:
                    w.tag_add('pos_' + str(abs(hash(major))), f'1.0+{a}c', f'1.0+{z}c')
        gray = list(gray) + ([(0, gray_upto)] if gray_upto else [])
        if gray:
            w.tag_configure('same_as_above', foreground=_faint(owner))
            for a, z in gray:
                w.tag_add('same_as_above', f'1.0+{a}c', f'1.0+{z}c')
            w.tag_raise('same_as_above')
        w.configure(state='disabled')
        w.bind('<MouseWheel>', owner._wheel)
        if command:
            hover_bg, hover_fg = owner.accent, bg
            w.bind('<Enter>', lambda e: w.configure(bg=hover_bg))
            w.bind('<Leave>', lambda e: w.configure(bg=bg))
            w.bind('<ButtonRelease-1>', lambda e: self.invoke())
        w.bind('<Button-1>', lambda e: 'break')
        w.bind('<B1-Motion>', lambda e: 'break')

    def fix_height(self):
        """大きい品詞の字でも切れない高さ。全部の行を作った後に1回だけ update_idletasks してから
        呼ぶ（行ごとに呼ぶと 66行で 0.75 秒かかっていた・2026-10-27 うにさん「動作が重い」）。"""
        w = self.widget
        try:
            h = int(w.count('1.0', 'end', 'ypixels')[0])
        except (tk.TclError, TypeError, IndexError):
            h = 0
        if h:
            self.frame.configure(height=h + 2)
            self.frame.pack_propagate(False)

    def pixel_width(self):
        try:
            return int(self.widget.count('1.0', '1.end', 'xpixels')[0])
        except (tk.TclError, TypeError, IndexError):
            return tkfont.Font(font=self.widget.cget('font')).measure(self.text)

    def cget(self, option):
        return self.text if option == 'text' else self.widget.cget(option)

    def invoke(self):
        if self.command:
            self.command(self.text)

class ConvertWindow:
    """1つだけ開く窓。本体の選択を見て中身を差し替える。"""

    def __init__(self, root, app=None):
        self.root, self.app = root, app
        self.window = None
        self.target = None          # 最後に選んでいた窓（クリックした文を入れる先）
        self.selection = None
        self._job = None
        self._watched = []

    # --- 本体の選択を見る ---
    def watch(self, widgets):
        for w in widgets:
            if w is None or w in self._watched:
                continue
            self._watched.append(w)
            w.bind('<<Selection>>', lambda e, w=w: self._selection_changed(w), add='+')

    def _selection_changed(self, widget):
        if self.window is None:
            return
        if self._job is not None:
            self.root.after_cancel(self._job)
        self._job = self.root.after(80, lambda: self._refresh_from(widget))

    def _refresh_from(self, widget):
        self._job = None
        try:
            text = widget.get('sel.first', 'sel.last')
        except tk.TclError:
            return          # 選択が外れたときは前の中身のまま
        if text.strip() and text != self.selection:
            self.target = widget
            self.show(text)

    # --- 窓 ---
    def open(self, selection, target=None, font=None, colors=None):
        self.target = target or self.target
        try:
            alive = self.window is not None and bool(self.window.winfo_exists())
        except tk.TclError:
            alive = False
        if not alive:
            self._build(font, colors or {})
        self.show(selection)
        self.window.deiconify()
        self.window.lift()
        # Windows が窓を最終の位置に置くのは出した後（本体の窓の画面へ移すことがある）。出してから
        # REFIT_S のあいだ、窓の位置・大きさが変わるたびに作業域へ収め直す（<Configure>）。
        # その後は見ない（人が窓を動かしているのと取り合わない）
        self._refit_until = time.monotonic() + self.REFIT_S
        self._refit_on_screen()
        if self._native is not None:
            # Tk の deiconify は窓を前に出して焦点も取るので、打っていた欄へ返す（単語帳の
            # _give_back_after_open と同じ・本文の焦点が残る）
            self.root.after_idle(self._give_focus_back)
        return self.window

    REFIT_S = 1.0

    def _on_window_configure(self, event):
        if event.widget is not self.window or time.monotonic() > getattr(self, '_refit_until', 0):
            return
        if getattr(self, '_refit_job', None) is None:
            self._refit_job = self.root.after_idle(self._run_refit)

    def _run_refit(self):
        self._refit_job = None
        self._refit_on_screen()

    def _refit_on_screen(self):
        """出した後の位置で、窓が載っている画面の作業域に収め直す（2026-10-27）。

        初めて出すときの _fit は窓を出す前（withdraw の間）に回るので、窓の位置がまだ決まっていない。
        Windows が置いた位置で下端が作業域の下 −60 を越えた（上端が作業域より上に出た）ときだけ測り直す。"""
        fit = getattr(self, '_last_fit', None)
        win = self.window
        if fit is None or win is None:
            return
        try:
            win.update_idletasks()
            area = _work_area(win)
            if area is None:
                return
            top = win.winfo_rooty()
            if top + win.winfo_height() > area[3] - 60 or top < area[1]:
                self._fit(*fit, reset_view=False)   # 収め直すだけ（読んでいた位置はそのまま）
        except tk.TclError:
            pass

    def _give_focus_back(self):
        target = self.target
        try:
            if target is not None and target.winfo_exists():
                target.focus_force()
        except tk.TclError:
            pass

    def _build(self, font, colors):
        self.font = font or tkfont.nametofont('TkDefaultFont')
        self.bg = colors.get('bg') or '#ffffff'
        self.fg = colors.get('fg') or '#000000'
        self.accent = colors.get('select') or '#2c5f6f'
        win = self.window = tk.Toplevel(self.root, bg=self.bg)
        win.withdraw()
        win.title(_t('文変換', 'Sentence convert'))
        win.bind('<Escape>', lambda e: self.close())
        win.bind('<Configure>', self._on_window_configure, add=True)
        win.protocol('WM_DELETE_WINDOW', self.close)
        # 単語帳と同じフロートの窓（うにさん 14:50Z）: いつも手前・押しても前に出ない（本文の
        # 焦点も変換中の文字もそのまま。14:52Z「クリックしてもペーストできなかった。フォーカスが
        # 文変換のほうだからでは」）
        win.attributes('-topmost', True)
        win.update_idletasks()
        self._native = None
        if os.name == 'nt':
            try:
                from word_book import _WordBookNative
                self._native = _WordBookNative(win, None)
                self._native.make_noactivate()
            except Exception:
                self._native = None
        # 上のドラッグする所（単語帳と同じ）
        rgb = [win.winfo_rgb(c) for c in (self.bg, self.fg)]
        header_bg = '#' + ''.join('%02x' % round((b * .92 + f * .08) / 257) for b, f in zip(*rgb))
        self.header = tk.Frame(win, bg=header_bg, cursor='fleur', height=12)
        self.header.pack(side='top', fill='x')
        self.header.bind('<ButtonPress-1>', self._start_drag)
        self.header.bind('<B1-Motion>', self._drag)
        self.header.bind('<ButtonRelease-1>', self._end_drag)
        self._drag_anchor = None
        self.canvas = tk.Canvas(win, bg=self.bg, highlightthickness=0, bd=0)
        self.scroll = tk.Scrollbar(win, command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scroll.set)
        self.canvas.pack(side='left', fill='both', expand=True)
        self.rows = tk.Frame(self.canvas, bg=self.bg)
        self._rows_item = self.canvas.create_window(0, 0, window=self.rows, anchor='nw')
        self.canvas.bind('<MouseWheel>', self._wheel)

    def _start_drag(self, event):
        self._drag_anchor = None
        if self._native is None or not self._native.start_move():
            self._drag_anchor = (event.x_root, event.y_root,
                                 self.window.winfo_x(), self.window.winfo_y())
        return 'break'

    def _drag(self, event):
        if self.window is not None and self._drag_anchor is not None:
            px, py, x, y = self._drag_anchor
            self.window.geometry('+%d+%d' % (x + event.x_root - px, y + event.y_root - py))
        return 'break'

    def _end_drag(self, event=None):
        self._drag_anchor = None
        return 'break'

    def close(self):
        _POS_RUNS.clear()
        native = getattr(self, '_native', None)
        if native is not None:
            try:
                native.detach()
            except Exception:
                pass
            self._native = None
        if self.window is not None:
            try:
                self.window.destroy()
            except tk.TclError:
                pass
        self.window = None
        self.selection = None

    def _wheel(self, event):
        self.canvas.yview_scroll(-1 if event.delta > 0 else 1, 'units')

    def show(self, selection):
        if self.window is None:
            return
        self.selection = selection
        head, reorder, syn, eng = build_sections(selection)
        if not head:
            head = _t('本体で文を選ぶと、ここに並びが出ます。', 'Select sentences in the editor to see them here.')
        for child in self.rows.winfo_children():
            child.destroy()
        f = tkfont.Font(root=self.window, font=self.font)
        line_h = f.metrics('linespace')
        pad_x = 8
        # 品詞ごとの大きさ・色は本体の欄と同じ（うにさん 16:06Z「文変換ウインドウ内の文字も、
        # 品詞ごとのフォントサイズとカラーを適用する」）
        styles = _pos_styles(self.app)
        first = _Line(self, head, None, styles, pad_x)
        self.buttons = []
        above = head
        for part in (reorder, syn, eng):
            if not part:
                continue
            # 1行目と2行目の間、倒置・類語・英語の境目は 0.5 行分あける（うにさん 04:46Z・17:08Z）
            tk.Frame(self.rows, bg=self.bg, height=max(1, line_h // 2)).pack(fill='x')
            for line in part:
                # 倒置の行は1行上と同じ所までを灰色に（大きさは品詞のまま。うにさん 17:08Z）
                same = _common_prefix(above, line) if part is reorder else 0
                self.buttons.append(_Line(self, line, self.paste, styles, pad_x, gray_upto=same,
                                          gray=getattr(line, 'gray', ())))
                above = line
        self.first = first
        self._last_fit = ([first] + self.buttons, pad_x)
        self.window.update_idletasks()
        for line in [first] + self.buttons:
            line.fix_height()
        self._fit([first] + self.buttons, pad_x)

    def _fit(self, lines, pad_x, reset_view=True):
        """横幅はいちばん長い行に合わせる。高さは画面に収まるまで、越えたらスクロール。"""
        win = self.window
        win.update_idletasks()
        width = max(line.pixel_width() for line in lines) + pad_x * 2 + 8
        rows_h = self.rows.winfo_reqheight()
        height = rows_h + self.header.winfo_reqheight()
        # 画面の下を越えない（うにさん 10-27 02:14Z）。窓の上端から画面の下端（タスクバー分あけて）まで。
        # それでも狭いときは窓を上へずらす。画面は**窓が載っている画面の作業域**（タスクバーを除く）
        # ——winfo_screenheight は主の画面の高さしか返さず、高さの違う別の画面では下を越えていた
        # （2026-10-27・3画面の PC で 4px）。取れないときは今までどおり主の画面。
        area = _work_area(win)
        area_top, area_bottom = (area[1], area[3]) if area else (0, win.winfo_screenheight())
        bottom = area_bottom - 60
        viewable = win.winfo_viewable()
        top = win.winfo_rooty() if viewable else win.winfo_y()
        # geometry の +x+y は枠（タイトルバー込み）の位置、rooty は中身の上端。その差だけずらして置く
        off = max(0, win.winfo_rooty() - win.winfo_y()) if viewable else 0
        if top - off < area_top:
            top = area_top + off
            win.geometry('+%d+%d' % (win.winfo_x(), top - off))
        maximum = max(120, bottom - top)
        full = area_bottom - area_top - off - 160
        if min(height, full) > maximum:
            maximum = max(120, full)
            top = max(area_top + off, bottom - maximum)
            win.geometry('+%d+%d' % (win.winfo_x(), top - off))
            maximum = max(120, min(maximum, bottom - top))
        if height > maximum:
            self.scroll.pack(side='right', fill='y')
            width += self.scroll.winfo_reqwidth()
        else:
            self.scroll.pack_forget()
        width = min(width, win.winfo_screenwidth() - 40)
        self.canvas.itemconfigure(self._rows_item, width=width)
        win.geometry('%dx%d' % (width, min(height, maximum)))
        self.canvas.configure(scrollregion=(0, 0, width, rows_h))
        if reset_view:
            self.canvas.yview_moveto(0)
        # 行の間のすき間の上でもホイールが効くように
        stack = [self.rows]
        while stack:
            w = stack.pop()
            w.bind('<MouseWheel>', self._wheel)
            stack.extend(w.winfo_children())

    # --- クリックで入れる（単語帳と同じ） ---
    def _outside_front(self):
        """前にある窓が他のアプリ（このアプリの窓でも文変換の窓でもない）ならその hwnd。"""
        native = self._native
        if native is None or os.environ.get('CORRECTNOTE_NO_EXTERNAL_PASTE') == '1':
            return None
        # 試験・確かめで外へ本物の Ctrl+V を送らない門（16:05Z、うにさんの窓へ送ってしまった）:
        # 本物の app（settings を持つ）で、窓が見えていて、マウスがこの窓の上にある（人が押した）とき、
        # しかも前の窓がフックで覚えた「直前に使っていた窓」と同じときだけ外へ貼る。
        try:
            win = self.window
            if getattr(self.app, 'settings', None) is None or win is None or not win.winfo_viewable():
                return None
            x, y = win.winfo_pointerxy()
            over = win.winfo_containing(x, y)
            if over is None or over.winfo_toplevel() is not win:
                return None
        except (tk.TclError, KeyError):
            return None
        try:
            from ctypes import wintypes as W
            front = native.user.GetForegroundWindow()
            if not front or front == native.hwnd:
                return None
            pid = W.DWORD()
            native.user.GetWindowThreadProcessId(front, native.c.byref(pid))
            if pid.value == os.getpid():
                return None
            previous = native.previous
            return front if previous and previous[0] == front else None
        except Exception:
            return None

    def _paste_outside(self, text, to_clip, tries=6):
        hwnd = self._outside_front()
        if hwnd is None:
            return False
        lent = None
        if not to_clip:
            # 他のアプリへは Ctrl+V でしか入らない: その間だけクリップボードを借りて戻す
            import clipboard_keep
            lent = clipboard_keep.lend(text)
            if lent is None:
                return True
        done = self._native.paste(hwnd)
        if lent is not None:
            if done:
                import clipboard_keep
                self.root.after(clipboard_keep.RESTORE_DELAY_MS, lent.restore)
            else:
                lent.restore()
        if done is None and tries > 0:
            # 前の窓がまだ有効になりきっていない（単語帳と同じく少し待ってもう一度）
            self.root.after(60, lambda: self._paste_outside(text, to_clip, tries - 1))
            return True
        if done:
            try:
                self.app.status.config(text=_t('文変換の文を入れました', 'Inserted the converted sentence'))
            except AttributeError:
                pass
        return True

    def paste(self, text):
        app = self.app
        to_clip = True
        try:
            to_clip = bool(app.settings.get('word_book_clipboard'))
        except AttributeError:
            pass
        if to_clip:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
        # 前にあるのが他のアプリなら、単語帳と同じく Ctrl+V でそのアプリの入力欄へ入れる
        # （うにさん 16:03Z「アプリ外の入力フォームにもペーストできるようにします。単語帳と同じ」）。
        # この窓は焦点を取らない（noactivate）ので、クリックしても前のアプリが前のまま。
        if self._paste_outside(text, to_clip):
            return
        # 入れる先は本文か簡易入力。補正結果の欄は読むだけ（state disabled）で入らないので、
        # そこで選んでいたときは本文のカーソルへ入れる（うにさん 16:01Z「入れましたと出るが何も出てない」）
        target = self.target
        editable = [w for w in (getattr(app, 'editor', None), getattr(app, '_quick_text', None)) if w is not None]
        if target not in editable:
            target = getattr(app, 'editor', None)
        if target is None:
            return
        done = False
        try:
            insert = getattr(app, '_insert_word_book_text', None)
            if insert is not None:
                done = insert(text, target) is not False
            else:
                target.insert('insert', text)
                done = True
            if self._native is None:
                target.focus_set()
        except tk.TclError:
            pass
        if not done:
            return
        try:
            app.status.config(text=_t('文変換の文を入れました', 'Inserted the converted sentence'))
        except AttributeError:
            pass


_instance = None


def _panes(app):
    return (app.editor, getattr(app, 'result_view', None), getattr(app, '_quick_text', None))


def open_from_app(app):
    """ボタン「文変換」から呼ぶ。入力中の窓（本文・補正結果・簡易入力）で選んだ範囲、
    選んでいなければカーソルの行で開き、以後その窓たちの選択を見て1行目と並びを差し替える。"""
    global _instance
    try:
        focused = app.root.focus_get()
    except Exception:
        focused = None
    panes = _panes(app)
    widget = focused if focused is not None and focused in panes else app.editor
    try:
        selection = widget.get('sel.first', 'sel.last')
    except tk.TclError:
        selection = widget.get('insert linestart', 'insert lineend')
    colors = {}
    for key, opt in (('bg', 'background'), ('fg', 'foreground'), ('select', 'selectbackground')):
        try:
            colors[key] = widget.cget(opt)
        except tk.TclError:
            pass
    try:
        font = widget.cget('font')
    except tk.TclError:
        font = None
    # 出ているときにもう一度押したら閉じる（うにさん 10-27 01:18Z）
    if _instance is not None and _instance.root is app.root and _instance.window is not None:
        try:
            shown = bool(_instance.window.winfo_exists()) and _instance.window.winfo_viewable()
        except tk.TclError:
            shown = False
        if shown:
            _instance.close()
            return None
    if _instance is None or _instance.root is not app.root:
        _instance = ConvertWindow(app.root, app)
    _instance.watch(panes)
    return _instance.open(selection, target=widget, font=font, colors=colors)
