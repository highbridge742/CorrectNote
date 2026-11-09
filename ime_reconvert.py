# -*- coding: utf-8 -*-
"""IME で読みを変換し直して、選び違いと1打の打ち違いの漢字の語を疑う段（2026-10-30・うにさん「定番の誤字をカバー」）。

行の漢字やカタカナの語は、打った読みを IME が変換したもの。世の中でめったに使わない語（wordfreq の段で珍しい語）が
行に出ているとき、次の2つを PC の IME（読み取りだけの IFELanguage）で確かめる。
1. 選び違い: 行の読みをそのまま IME で変換し直すと、その語の所が身近な語になる。
2. 1打の打ち違い: その語の読みの1打を戻した読み（ローマ字・かな入力ごと）で行を変換し直すと、身近な語になる。
どちらも行の費用（morphology.path_cost）が下がるときだけ候補にする。
選び違いで、IME 自身の最初の変換と同じ・語の所だけが替わる・珍しさの差が大きい ときは直す。ほかは紫。
雲の読みの格子で組んだ並びは無意味な語の並びを好むので、変換は IME に任せる（格子は1打の候補を絞るのにだけ使う）。
特定の語や文字列には合わせない（局所的な補正はしない）。
2026-11-07: 読みは打った記録から、表記は辞書から（typed_reverse・dict_convert・下の節）。IME は記録の無い所の読みと、
辞書に無い語を足すときだけ。IME の無い環境（雲）でも同じ答えになる。CN_RECONVERT_TYPED=0・CN_RECONVERT_DICT=0 で前のまま。
"""
import difflib
import gzip
import json
import os
from functools import lru_cache

DOUBT = 560        # wordfreq の段（大きいほど珍しい）。これ以上の語を疑う
DOUBT_MARK = 600   # 選び違いを紫にするのは、これ以上珍しい語
DOUBT_KEY = 700    # 1打の打ち違いを試すのは、これ以上珍しい語（表に無い語は 800）
DOUBT_KEY_TRY = 650  # 1打の戻しを IME で試すのはこれ以上（密偵 663・2026-11-04）。選び違いを直す門は DOUBT_KEY のまま
COMMON = 470       # 替わった先の語はこれ以下（身近な語）
FIX_COMMON = 430   # 直すときの替わった先の語
JUMP = 100         # 元の語より、替わった先がこれだけ身近
FIX_JUMP = 200     # 直すときの差
MARK_GAIN = 1000   # 選び違い: 行の費用がこれだけ下がれば紫
SAME_BIG_GAIN = 4000  # 打った読みのままの表記で、門より身近な語でも見る行の費用の下がり（お客彷徨う → お客様用 は 5800）
SAME_BIG_FIX = 5000   # これ以上なら直す（足りなければ紫）
KEY_GAIN = 3000    # 1打の打ち違い: 行の費用がこれだけ下がれば紫（切り方の揺れで下がる分より大きく）
KEY_COMMON = 500   # 1打の戻しの先の語の身近さ（日程 478 が 470 で落ちていた・2026-11-04）
KEY_FIX_COMMON = 480  # 1打の戻しで直すときの先の語
KEY_MARK_GAIN = 2000  # 1打の戻しが1つだけで、窓の語がどれも身近な語になるときはこれで足りる（3語→1語の 補遺国書→報告書 は約2500・2026-11-04）
KEY_TOP = 8        # 1打の候補は、格子で身近な語に組める読みのうち費用の安い順にこれだけ IME に渡す
MAX_WORDS = 2      # 窓の IME の語の数


def _kanji(c):
    return '一' <= c <= '鿿'


def _katakana(c):
    return 'ァ' <= c <= 'ヶ' or c == 'ー'


def _strong(s):
    return any(_kanji(c) or _katakana(c) for c in s)


def _hira(s):
    return ''.join(chr(ord(c) - 0x60) if 'ァ' <= c <= 'ヶ' else c for c in s)


@lru_cache(maxsize=1)
def _freq():
    """語 → 使われやすさの順位（ja_wordfreq.json.gz）。子ごとに json を読むと約0.2秒・約16MB（雲）かかるので、
    詰めた形（compact_tables.CompactCosts、同じ鍵・同じ値の get）を控え（cn_ja_wordfreq.cache.pickle）から読む
    （2026-11-07・解析の子の起動とメモリ）。元のファイルの大きさ・更新時刻が同じ間だけ。CN_TABLE_PICKLE=0 で前の形。"""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ja_wordfreq.json.gz')
    if os.environ.get('CN_TABLE_PICKLE') != '0':
        try:
            import compact_tables
            stamp = ('ja_wordfreq', 1, compact_tables._file_stamp(path))
            got = compact_tables._pickled('cn_ja_wordfreq.cache.pickle', stamp, lambda: _freq_compact(path))
            if got is not None:
                return got
        except Exception:
            pass
    return _freq_read(path)


def _freq_read(path):
    try:
        with gzip.open(path, 'rt', encoding='utf-8') as f:
            return json.load(f)['words']
    except Exception:
        return {}


def _freq_compact(path):
    """詰めた形にできる表（鍵が NUL の無い str・値が int）なら CompactCosts、できなければ None（呼ぶ側は dict）。"""
    table = _freq_read(path)
    if not table or any(type(k) is not str or '\x00' in k for k in table) or any(type(v) is not int for v in table.values()):
        return None
    import compact_tables
    return compact_tables.CompactCosts.of(table)


def _rank(face):
    return _freq().get(face, 800)


def _token_rarity(t, tokens=None):
    """解析の1語の珍しさ。かなだけの語・機能語は 0。活用する語は基本形で、表に無い名詞は身近な2つの語の組なら組の珍しさ。
    tokens（行の解析の並び）を渡すと、動詞の連用形の直後の動詞（書き｜換わる・飛び｜跳ねる の後ろ）は複合動詞の後ろの語
    なので、複合動詞が表に在ればその珍しさ、無ければ前の動詞の珍しさで見る（2026-11-03 うに 未解決タブ: 複合動詞の
    後ろの語だけを珍しい語と見て、正しい行を別の語に直した）。"""
    if not _strong(t.surface) or t.pos in ('助詞', '助動詞', '記号'):
        return 0
    face = t.surface
    if t.pos in ('動詞', '形容詞'):
        face = getattr(t, 'base_form', '') or face
    r = _rank(face)
    if tokens and t.pos == '動詞' and r >= DOUBT and os.environ.get('CN_RECONVERT_COMPOUND') != '0':
        prev = [p for p in tokens if p.end == t.start and p.pos == '動詞' and _strong(p.surface)]
        if prev and getattr(prev[0], 'base_form', '') and prev[0].surface != prev[0].base_form:
            whole = prev[0].surface + face
            return min(r, _freq().get(whole, _rank(prev[0].base_form)))
    if t.pos == '動詞' and r >= DOUBT and os.environ.get('CN_RECONVERT_COMPOUND_ONE') != '0':
        # 1語に解析された複合動詞（見入る・書き込む）は、前の動詞の連用形と後ろの動詞のどちらも身近なら、その珍しさで見る
        r2 = _compound_verb_rarity(face)
        if r2 is not None:
            r = min(r, r2)
    if tokens and t.pos == '名詞' and len(face) == 1 and _kanji(face) and r < 800 \
            and os.environ.get('CN_RECONVERT_SINGLE_RUN') != '0' and _single_kanji_run(t, tokens):
        # 1字の漢字の名詞が続けて並ぶ所（集｜亜｜量・田｜桁）で、つないだ字の並びが語でないものは、IME が読みを
        # 1字ずつの漢字に当てた形（打ち違いの跡）。表に無い語と同じに見る（2026-11-04 うにの未解決タブ・作った例で確かめ）
        return 800
    if tokens and t.pos == '名詞' and len(face) == 1 and _kanji(face) and os.environ.get('CN_RECONVERT_SPLIT_PAIR') != '0':
        # 解析が1字ずつに切った2字の語（二｜言: 数＋助数詞と読んだ）は、つないだ語が表に在れば、その語の珍しさで見る
        # （2026-11-08 手分けA: 伝え二言で の 二言 642 が 二 323・言 483 に分かれて、疑う門を通らなかった）
        for u in tokens:
            if u.pos != '名詞' or len(u.surface) != 1 or not _kanji(u.surface):
                continue
            pair = u.surface + face if u.end == t.start else face + u.surface if u.start == t.end else None
            if pair and DOUBT <= _rank(pair) < 800:
                r = max(r, _rank(pair))
    if r >= 800 and t.pos == '名詞':
        # 接頭の1字＋表の語（再＋描画・未＋登録）は、後ろの語の珍しさで見る。CN_RECONVERT_SEED_WORD=0 で前のまま
        if (len(face) >= 3 and _kanji(face[0]) and _seed_word(face[1:]) and _prefix_kanji(face[0])):
            return min(r, max(_rank(face[1:]), DOUBT - 1))
        for k in range(1, len(face) - 1):
            a, b = face[:k], face[k:]
            if len(a) < 2 and not any('ぁ' <= c <= 'ゖ' for c in b):
                continue
            ra, rb = _rank(a), _rank(b)
            if ra <= 520 and rb <= 520:
                return max(ra, rb)
    return r


def _kana_scraps(text, other):
    """変換し直した行の替わった所に、かなだけの短い内容の語（差＋へ＋い＋ます の い）が残るか。1打の戻しを IME が
    語にし切れなかった形なので直さない（紫にとどめる・2026-11-04 Store の測り: 参加左飛ます→参加差へいます）。"""
    try:
        from morphology import tokenize
    except Exception:
        return True
    ops = [o for o in difflib.SequenceMatcher(None, text, other, autojunk=False).get_opcodes() if o[0] != 'equal']
    if not ops:
        return False
    j1, j2 = ops[0][3], ops[-1][4]
    for t in tokenize(other):
        if t.start < j2 and j1 < t.end and t.pos in ('名詞', '動詞', '形容詞') and _hira(t.surface) == t.surface \
                and all('ぁ' <= c <= 'ゖ' for c in t.surface) and len(t.surface) <= 2:
            if _verb_tail(other, j1, j2):
                continue
            return True
    return False


def _verb_tail(other, j1, j2):
    """other[j1:j2] が、すぐ前の漢字の活用する語に付く かなの助動詞・助詞・形式名詞（伝え｜たこと の た・こと）だけか。
    語の切れ端ではなく活用の尾と付属の語。CN_RECONVERT_KANA_TAIL=0 で前のまま（2026-11-08 手分けA）。"""
    if os.environ.get('CN_RECONVERT_KANA_TAIL') == '0' or j2 <= j1:
        return False
    try:
        from morphology import tokenize
        toks = list(tokenize(other))
    except Exception:
        return False
    prev = [t for t in toks if t.end == j1 and t.pos in ('動詞', '形容詞') and _kanji(t.surface[:1])]
    mid = [t for t in toks if t.start < j2 and j1 < t.end]
    if not prev or not mid or mid[0].start != j1 or mid[-1].end != j2:
        return False
    # 活用の尾は助動詞か形式名詞から始まる（出る｜た は無いが 伝え｜た）。助詞から始まる形（出る｜の｜つもり）は、
    # 1打の戻しが字の並びを入れ替えて足した助詞で、尾ではない（2026-11-08 補正担当の測り）
    if mid[0].pos == '助詞' and os.environ.get('CN_RECONVERT_TAIL_PARTICLE') != '1':
        return False
    return all(not _strong(t.surface) and (t.pos in ('助動詞', '助詞')
                                           or (t.pos == '名詞' and (t.pos_sub or '').startswith('非自立')))
               for t in mid)


def _key_fix_overreach(text, other):
    """1打の戻しの直しが、打ち違いの所の外まで書き換える形か。元の行のかなの並び（3字以上: おくしょ）を漢字にする・
    片仮名の語を持ち込む（女辞書→おんなじショー）・かなの内容の語を持ち込む形は、IME が戻した読みを別の区切りで
    変換し直したもので、直しとしては採らない（紫にとどめる・2026-11-04 Store の測り）。"""
    import re
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, text, other, autojunk=False).get_opcodes():
        if tag == 'equal':
            continue
        src, dst = text[i1:i2], other[j1:j2]
        if re.search('[ぁ-ゖ]{3,}', src) and any(_kanji(c) for c in dst):
            return True
        if any(_katakana(c) for c in dst) and not any(_katakana(c) for c in src):
            return True
        if re.search('[ぁ-ゖ]{3,}', dst) and not re.search('[ぁ-ゖ]{3,}', src) \
                and not _inflected_face(other, j1, j2) and not _verb_tail(other, j1, j2):
            return True
    return False


def _inflected_face(other, j1, j2):
    """other[j1:j2] が 漢字で始まる活用する語＋助動詞（出かけ｜た）だけか。かなは送り仮名と活用の尾で、IME が別の区切りで
    持ち込んだかなの内容の語ではない（2026-11-08 田桁→出かけた）。CN_RECONVERT_INFLECTED_FACE=0 で前のまま。"""
    if os.environ.get('CN_RECONVERT_INFLECTED_FACE') == '0' or not _kanji(other[j1:j1 + 1] or 'あ'):
        return False
    try:
        from morphology import tokenize
        toks = [t for t in tokenize(other) if t.start < j2 and j1 < t.end]
    except Exception:
        return False
    if not toks or toks[0].start != j1 or toks[-1].end != j2:
        return False
    return toks[0].pos in ('動詞', '形容詞') and all(t.pos == '助動詞' for t in toks[1:])


HOMO_MARGIN = 1500   # 1打を戻した読みの、身近な同じ読みの表記2つの点の差がこれ未満なら決めない


def _homophone_tie(text, other):
    """1打を戻した行 other の替わった所の語に、同じ読みの身近な別の表記が在り、行の費用＋身近さの点がほとんど同じ
    （涼しい｜風邪／風: かぜ）なら True。読みは戻せても表記を決める根拠が無いので紫にとどめる（2026-11-08 手分けA:
    巣瀬 → 風邪）。CN_RECONVERT_HOMO_TIE=0 で前のまま。"""
    if os.environ.get('CN_RECONVERT_HOMO_TIE') == '0' or not other or other == text:
        return False
    from morphology import tokenize, path_cost
    ops = [o for o in difflib.SequenceMatcher(None, text, other, autojunk=False).get_opcodes() if o[0] != 'equal']
    if not ops:
        return False
    j1, j2 = ops[0][3], ops[-1][4]
    for t in tokenize(other):
        if not (t.start < j2 and j1 < t.end) or t.pos != '名詞' or not _strong(t.surface) or not t.reading:
            continue
        rd = _hira(t.reading)
        mine = _rank(t.surface)
        if mine > COMMON:
            continue
        base = _score(other, path_cost, t.start, t.end)
        if base is None:
            continue
        for f in _dict_faces(rd, 8):
            if f == t.surface or _rank(f) > COMMON or not any(_kanji(c) for c in f):
                continue
            line = other[:t.start] + f + other[t.end:]
            sc = _score(line, path_cost, t.start, t.start + len(f))
            if sc is not None and abs(sc - base) < HOMO_MARGIN:
                return True
    return False


def _same_reading_rival(text, first, s, e):
    """IME が行の読みを丸ごと変換し直した第1候補（first）が、窓 [s, e) の語を同じ読みの別の表記に替えるか（思料 → 試料）。
    同じ読みの別の語が在る所は IME の選び違いかもしれず、1打違いの読みの語（市長）に決める決め手にならない。紫にとどめる
    （2026-11-06 変換ミスの担当: 行頭の 思料 → 市長）。切り替え CN_RECONVERT_SAME_RIVAL=0"""
    if os.environ.get('CN_RECONVERT_SAME_RIVAL') == '0' or not first or first == text:
        return False
    ch = _changed_span(text, first)
    return ch is not None and ch[0] < e and s < ch[1]


def _splits_neighbour(tokens, s, e, a, b):
    """1打の戻しで替わる所 [a, b) が、窓 [s, e) の外の語の途中までを書き換えるか（晴れ｜のち｜曇り の 曇り を戻すと
    IME が のち の ち を取って 地区漏れ と区切り直す）。窓の外の語を割る直しは区切り直しなので採らない（紫にとどめる・
    2026-11-06 変換ミスの試験）。切り替え CN_RECONVERT_NO_SPLIT=0"""
    if os.environ.get('CN_RECONVERT_NO_SPLIT') == '0':
        return False
    for t in tokens:
        if s <= t.start and t.end <= e:
            continue
        if a < t.end and t.start < b and not (a <= t.start and t.end <= b):
            return True
    return False


def _single_kanji_run(t, tokens):
    """t の隣（前か後ろ）に、続けて1字の漢字の名詞（固有名詞の国名は除く）があり、その2字をつないだ並びも語でないか。"""
    def single(u):
        sub = u.pos_sub or ''
        return (u.pos == '名詞' and len(u.surface) == 1 and _kanji(u.surface)
                and not sub.startswith('固有名詞:地域:国') and not sub.startswith('数') and not sub.startswith('接尾'))
    if not single(t):
        return False
    for u in tokens:
        if not single(u):
            continue
        if u.end == t.start:
            pair = u.surface + t.surface
        elif u.start == t.end:
            pair = t.surface + u.surface
        else:
            continue
        if _rank(pair) >= 800 and not _known_compound(pair) and not _seed_word(pair):
            return True
    return False


@lru_cache(maxsize=4096)
def _prefix_kanji(c):
    try:
        from morphology import dictionary_base_pos
        return any(p.startswith('接頭詞') for p in (dictionary_base_pos(c) or ()))
    except Exception:
        return False


def _seed_word(face):
    """語の表（seed_japanese・oddness の表）に在る語か。解析が1字ずつに切った 横｜幅・空｜行 を打ち違いの跡と
    見ないため（2026-11-07 うにの未解決タブ: 横幅→横場は・の空行→農業）。CN_RECONVERT_SEED_WORD=0 で前のまま。"""
    if os.environ.get('CN_RECONVERT_SEED_WORD') == '0':
        return False
    try:
        import oddness
        return face in (oddness._load() or ())
    except Exception:
        return False


def _known_compound(face):
    return face in _faces_index()


@lru_cache(maxsize=1)
def _faces_index():
    try:
        import reading_lattice
        reading_lattice.load()
        return frozenset(row[0] for rows in reading_lattice._table.values() for row in rows if row and row[0])
    except Exception:
        return frozenset()


@lru_cache(maxsize=4096)
def _compound_verb_rarity(face):
    try:
        from morphology import tokenize
    except Exception:
        return None
    best = None
    for k in range(1, len(face) - 1):
        head, tail = face[:k], face[k:]
        if not _strong(head) or not _strong(tail[:1]):
            continue
        tt = list(tokenize(tail))
        if len(tt) != 1 or tt[0].pos != '動詞' or tt[0].surface != tail:
            continue
        ht = list(tokenize(head + 'ます'))
        if not ht or ht[0].pos != '動詞' or ht[0].surface != head or not getattr(ht[0], 'base_form', ''):
            continue
        v = max(_rank(ht[0].base_form), _rank(getattr(tt[0], 'base_form', '') or tail))
        best = v if best is None else min(best, v)
    return best


def _span_rarity(text, a, b, tokens):
    return max([_token_rarity(t, tokens) for t in tokens if t.start < b and a < t.end] + [0])


@lru_cache(maxsize=4096)
def _lattice_cost(reading):
    """1打の候補の読みが、格子で身近な語だけに組めるときの費用（組めなければ None）。"""
    try:
        import reading_lattice
        res = reading_lattice.best(reading)
    except Exception:
        return None
    if not res.surface or any(w[2] == '未知' for w in res.words):
        return None
    if max([_rank(w[0]) for w in res.words if _strong(w[0])] + [0]) > KEY_COMMON:
        return None
    return res.cost


def _key_readings(reading, input_method):
    out = []
    try:
        if input_method == 'romaji':
            import romaji_repair
            import romaji_swap_repair
            for spelled in romaji_swap_repair._spellings(reading, limit=2):
                found = romaji_repair.one_key_readings(spelled)
                out.extend(row[0] for row in getattr(found, 'candidates', ()))
        else:
            from contextual_repair import key_repairs
            out.extend(getattr(r, 'reading', r) for r in key_repairs(reading))
            if os.environ.get('CN_RECONVERT_KANA_EXTRA') != '0' and len(reading) >= 4:
                # 巻き込みの余分な1打（しゅう＋あ＋りょう）: かな1字を抜いた読み（2026-11-04）
                out.extend(reading[:i] + reading[i + 1:] for i in range(len(reading))
                           if reading[i] not in 'ゃゅょぁぃぅぇぉっー')
    except Exception:
        return []
    ranked = []
    for v in dict.fromkeys(out):
        if not v or v == reading:
            continue
        c = _lattice_cost(v)
        if c is not None:
            ranked.append((c, v))
    return [v for c, v in sorted(ranked)[:KEY_TOP]]


def _typed_real_noun(text, s, e, reading, tokens):
    """窓の漢字の語が1つの名詞で、辞書にその表記の読みが在り、その読みを打ったとおり（自薦 を じせん）か。
    打ったとおりに実在の語が出ているので、それほど珍しくない語（DOUBT_KEY 未満）を1打の戻し（゛の付け替え: じせん →
    しぜん）で別の語に替える根拠にならない（2026-11-09 うに 誤判定: 正しい行の 自薦の → 自然の）。
    CN_RECONVERT_TYPED_REAL=0 で前のまま。"""
    if os.environ.get('CN_RECONVERT_TYPED_REAL') == '0':
        return False
    strong = [t for t in tokens if t.start < e and s < t.end and _strong(t.surface)]
    if len(strong) != 1 or strong[0].pos != '名詞' or (strong[0].pos_sub or '').startswith('固有名詞'):
        return False
    t = strong[0]
    if not (s <= t.start and t.end <= e) or not any(_kanji(c) for c in t.surface):
        return False
    try:
        from inflected_lexicon import dictionary_readings
        rds = dictionary_readings(t.surface)
    except Exception:
        return False
    return any(r and r in reading for r in rds)


def _eats_kana_head(text, s, e, other):
    """窓 text[s:e] の頭のかな（し｜知多 の し: 活用の尾・付属の字）が、変換し直した行で漢字に飲み込まれるか。
    巻き込みの戻しは字を1つ抜くだけなので、打ったかなはかなのまま残るはず（2026-11-08 補正担当の測り: 散歩し知多 →
    散歩下）。CN_RECONVERT_ROLLIN_KANA_HEAD=0 で前のまま。"""
    if os.environ.get('CN_RECONVERT_ROLLIN_KANA_HEAD') == '0':
        return False
    k = s
    while k < e and 'ぁ' <= text[k] <= 'ゖ':
        k += 1
    head = text[s:k]
    return bool(head) and other[s:k] != head


def _rollin_drop(reading, v):
    """v は reading から、隣の字（前か後ろ）と隣り合うキーの字を1つ抜いた形か（巻き込みの1打）。"""
    if len(v) != len(reading) - 1:
        return False
    try:
        import kana_layout
    except Exception:
        return False
    for i, c in enumerate(reading):
        if reading[:i] + reading[i + 1:] != v or c in 'ゃゅょぁぃぅぇぉっー':
            continue
        for j in (i - 1, i + 1):
            if 0 <= j < len(reading) and reading[j] != c:
                try:
                    if kana_layout.kana_key_distance(reading[j], c, intrusion=True) <= 1.05:
                        return True
                except Exception:
                    pass
    return False


def _new_rarity(t, tokens):
    """替わった先の語の珍しさ。活用する語は基本形の珍しさだが、活用した形そのもの（出かけ 474）が表でより身近なら
    そちら（基本形 出かける 505 は 出かけ｜た・出かけ｜ます に分かれて数えられる・2026-11-08 田桁）。
    CN_RECONVERT_INFLECTED_RANK=0 で前のまま。"""
    r = _token_rarity(t, tokens)
    if t.pos in ('動詞', '形容詞') and r > 0 and os.environ.get('CN_RECONVERT_INFLECTED_RANK') != '0' \
            and len(t.surface) >= 2 and _strong(t.surface):
        r = min(r, max(_rank(t.surface), 1))
    return r


def _unreadable_face(text, w, reading):
    """窓の語がどれも打った記録の語で、窓の表記が打った読みでは読めない（辞書の読みのどれとも合わない: 給田 を たべた）か。
    IME が打った読みを変換したものではない表記なので、同じ読みの変換し直しで品詞が替わってもよい（名詞→動詞:
    給田→食べた・2026-11-08 PC の未解決タブ）。CN_RECONVERT_UNREADABLE=0 で前のまま。"""
    if os.environ.get('CN_RECONVERT_UNREADABLE') == '0' or not w or any(x[5] != 'typed' for x in w):
        return False
    face = text[w[0][0]:w[-1][1]]
    if not all(_kanji(c) for c in face):
        return False
    try:
        from inflected_lexicon import dictionary_readings
        from morphology import tokenize
        known = {_hira(r) for r in dictionary_readings(face) or ()}
        known.add(''.join(_hira(t.reading or '') for t in tokenize(face)))
    except Exception:
        return False
    return reading not in known


def _held_particles(text, w, tokens):
    """窓の端の助詞のうち、窓の外の隣が身近な漢字・片仮名の語（料理｜を・会社｜に）のもの。そうした助詞は前後の語との
    つながりで決まっていて、打ち違いの跡ではない（する｜よ｜手合い の よ・江合｜が の が は守らない）。"""
    out = []
    head, tail = w[0], w[-1]
    if head[4] == '助詞':
        prev = [t for t in tokens if t.end == head[0]]
        if prev and _strong(prev[-1].surface) and 0 < _token_rarity(prev[-1], tokens) <= COMMON:
            out.append(head)
    if tail[4] == '助詞' and tail is not head:
        nxt = [t for t in tokens if t.start == tail[1]]
        if nxt and _strong(nxt[0].surface) and 0 < _token_rarity(nxt[0], tokens) <= COMMON:
            out.append(tail)
    return out


def _changes_edge_particle(text, w, other, tokens=()):
    """窓の端の助詞の字が、変換し直した行で別の字になるか（会社に治国 → 会社二石: に が 二 に）。CN_RECONVERT_KEEP_PARTICLE=0 で前のまま。"""
    if os.environ.get('CN_RECONVERT_KEEP_PARTICLE') == '0' or len(w) < 2 or not other:
        return False
    held = _held_particles(text, w, tokens)
    head, tail = w[0], w[-1]
    if head in held and other[head[0]:head[1]] != text[head[0]:head[1]]:
        return True
    if tail in held:
        n = len(text) - tail[0]
        if other[len(other) - n:len(other) - n + (tail[1] - tail[0])] != text[tail[0]:tail[1]]:
            return True
    return False


def _drops_edge_particle(w, phon, v, text='', tokens=()):
    """窓の端の助詞（を｜給田 の を）を、1打の戻しの読みが丸ごと落とすか。助詞は打ち違いの跡ではなく文の骨組みなので、
    抜いた読みは採らない（2026-11-08 PC: 外国の料理を給田。→ 外国の料理食べた。）。CN_RECONVERT_KEEP_PARTICLE=0 で前のまま。"""
    if os.environ.get('CN_RECONVERT_KEEP_PARTICLE') == '0' or len(w) < 2:
        return False
    held = _held_particles(text, w, tokens)
    head, tail = w[0], w[-1]
    if head in held:
        p = _hira(phon[head[2]:head[3]])
        if p and not v.startswith(p):
            return True
    if tail in held:
        p = _hira(phon[tail[2]:tail[3]])
        if p and not v.endswith(p):
            return True
    return False


def _judge(text, here, other, s, e, tokens, src_rare, path_cost, tokenize, common=COMMON):
    """変換し直した行が、窓の所だけ身近な語に替わり行の費用が下がるなら (下がった分, 替わった先の珍しさ, 変わった所)。"""
    if not other or other == text:
        return None
    ops = [o for o in difflib.SequenceMatcher(None, text, other, autojunk=False).get_opcodes() if o[0] != 'equal']
    if not ops or ops[0][1] < s - 1 or ops[-1][2] > e + 1:
        return None
    j1, j2 = ops[0][3], ops[-1][4]
    new = [t for t in tokenize(other) if t.start < j2 and j1 < t.end]
    if not new and j1 == j2 and os.environ.get('CN_RECONVERT_DROP_TOKEN') != '0':
        # 字を抜いただけの戻し（宇遊んで → 遊んで）は替わった所の幅が0。抜いた所から始まる語で見る（2026-11-08 手分けA）
        new = [t for t in tokenize(other) if t.start <= j1 < t.end]
    if any(not t.has_reading for t in new):
        return None
    # 変わった所の頭の格助詞（料理を｜給田 の を）を、述語に飲み込んで消す変換し直し（料理食べた）は採らない。
    # 助詞は打ったとおりのかな。CN_RECONVERT_KEEP_CASE=0 で前のまま
    if os.environ.get('CN_RECONVERT_KEEP_CASE') != '0':
        i1, i2 = ops[0][1], ops[-1][2]
        lost = [t for t in tokens if i1 <= t.start and t.end <= i2 and t.pos == '助詞'
                and t.surface in ('を', 'が', 'に', 'へ', 'と', 'で', 'は', 'も')]
        if lost and not any(t.pos == '助詞' and t.surface == lost[0].surface for t in new):
            return None
    # 替わった所の終わりが名詞で、すぐ後ろが用言に付く 接続助詞（て・で・んで）か た・だ の助動詞（嘘｜んで｜いる）なら、
    # 動詞の語幹を名詞に替えた形で文にならない。採らない（2026-11-08 手分けA: 宇遊んで → 嘘んで）。
    # CN_RECONVERT_NOUN_TE=0 で前のまま
    if os.environ.get('CN_RECONVERT_NOUN_TE') != '0' and new and new[-1].pos == '名詞':
        nxt = [t for t in tokenize(other) if t.start == new[-1].end]
        if nxt and ((nxt[0].pos == '助詞' and (nxt[0].pos_sub or '').startswith('接続助詞')
                     and nxt[0].surface in ('て', 'で', 'んで'))
                    or (nxt[0].pos == '助動詞' and nxt[0].surface in ('た', 'だ'))):
            return None
    rr = max([_new_rarity(t, new) for t in new] + [0])
    if rr == 0 and os.environ.get('CN_RECONVERT_KANA_TAIL') != '0':
        # 替わった所がかなの付属語・形式名詞だけ（伝え｜二言 → 伝え｜たこと）なら、すぐ前の語（活用する語）に付く形として
        # その語の珍しさで見る（2026-11-08 手分けA）。前が活用する語でなければ今まで通り採らない
        prev = [t for t in tokenize(other) if t.end == j1 and t.pos in ('動詞', '形容詞') and _strong(t.surface)]
        if prev and all(not _strong(t.surface) for t in new):
            rr = _new_rarity(prev[0], new)
    if not (0 < rr <= common and src_rare - rr >= JUMP):
        return None
    c = path_cost(other)
    if c is None:
        return None
    return here - c, rr, (ops[0][1], ops[-1][2])


_EXTRA_FUNC = ('助詞', '助動詞')


def _extra_key(text, phon, words, here, path_cost, tokenize):
    """ローマ字で1打多く打って（同じキーの2度押し・隣のキーの巻き込み）、かなの続き（ください・おります）が
    珍しい漢字の語に変換された形。IME の読みと前後のかなをローマ字に戻して1打を抜き、かなのまま行に戻すと
    その所が付属の語（非自立の動詞・助動詞・助詞）だけになり、行の費用が大きく下がるものを探す。
    [(開始, 終了, 置く行 or None)]。候補が1つなら置く行、2つ以上なら紫。"""
    try:
        import romaji_swap_repair
        from halfwidth import romaji_to_kana
    except Exception:
        return []
    out = []
    for s, e, rs, re_ in [w[:4] for w in words]:
        face = text[s:e]
        if not face or not all(_kanji(c) for c in face) or _rank(face) < DOUBT_KEY:
            continue
        a = s
        while a > 0 and s - a < 2 and 'ぁ' <= text[a - 1] <= 'ゖ':
            a -= 1
        b = e
        while b < len(text) and b - e < 2 and 'ぁ' <= text[b] <= 'ゖ':
            b += 1
        found = set()
        for x in range(a, s + 1):
            for y in range(e, b + 1):
                typed_kana = text[x:s] + _hira(phon[rs:re_]) + text[e:y]
                for typed in romaji_swap_repair._spellings(typed_kana, limit=2):
                    for i in range(1, len(typed)):
                        k = romaji_to_kana(typed[:i] + typed[i + 1:])[0]
                        if not k or not all('ぁ' <= c <= 'ゖ' for c in k):
                            continue
                        other = text[:x] + k + text[y:]
                        new = [t for t in tokenize(other) if t.start < x + len(k) and x < t.end]
                        if (not new or new[0].start != x or new[-1].end != x + len(k)
                                or any(not t.has_reading for t in new)
                                or not all(t.pos in _EXTRA_FUNC or (t.pos == '動詞' and t.pos_sub.startswith('非自立'))
                                           for t in new)
                                or not any(t.pos != '助詞' for t in new)):
                            continue
                        c = path_cost(other)
                        if c is not None and here - c >= KEY_GAIN:
                            found.add(other)
        if found:
            out.append((s, e, found.pop() if len(found) == 1 else None))
    return out


_SMALL = 'ゃゅょぁぃぅぇぉ'


def _morae(reading):
    """読み → [(子音, 母音, 長音か)]。拗音は前の字と組、長音（えい・おう・ー・同じ母音）は前の拍に付ける。"""
    try:
        import romaji_swap_repair
    except Exception:
        return None
    units = []
    for c in reading:
        if c in _SMALL and units:
            units[-1] += c
        else:
            units.append(c)
    out = []
    for u in units:
        sp = romaji_swap_repair._spellings(u, limit=1)
        if not sp:
            return None
        sp = sp[0]
        vow = sp[-1] if sp[-1] in 'aiueo' else ''
        if out and not vow and u in 'ー':
            out[-1] = (out[-1][0], out[-1][1], True)
            continue
        if (out and u in 'いう' and not out[-1][2]
                and (out[-1][1][-1:], u) in (('e', 'い'), ('o', 'う'), ('u', 'う'), ('i', 'い'), ('a', 'あ'))):
            out[-1] = (out[-1][0], out[-1][1], True)
            continue
        cons = sp[:1] if sp[:1] not in 'aiueo' else ''
        out.append((cons, sp[len(cons):], False))
    return out


def _vowel_slip(a, b):
    """拍の数と長音が同じで、1拍だけ子音が同じまま母音（拗音を含む）が違う（れい／りょう）。"""
    ma, mb = _morae(a), _morae(b)
    if not ma or not mb or len(ma) != len(mb) or len(ma) < 2:
        return False
    diff = [(x, y) for x, y in zip(ma, mb) if x != y]
    return (len(diff) == 1 and diff[0][0][0] == diff[0][1][0] and diff[0][0][0] != ''
            and diff[0][0][2] == diff[0][1][2])


_SURU_HEAD = ('し', 'する', 'すれ', 'させ', 'され', 'いたし', 'いたす', '致し', '致す')


def _vowel_slip_noun(text, phon, words):
    """めったに使わない漢字の語＋する（しました・いたします）で、その語の読みが、名詞＋する の組の表の語の読みと
    1拍の母音だけ違う（じゅれい／じゅりょう）。表の語が1つなら直す、2つ以上なら紫。"""
    try:
        import collocation_repair
        _t, by_pv, _np, _w = collocation_repair.table()
    except Exception:
        return []
    nouns = set(by_pv.get(('続', 'する'), ())) | set(by_pv.get(('続', 'いたす'), ()))
    out = []
    for i in range(len(words)):
        for k in (1, 2):
            w = words[i:i + k]
            if len(w) < k:
                break
            s, e, rs, re_ = w[0][0], w[-1][1], w[0][2], w[-1][3]
            # IME が送りがなまで1語にした形（受領し）: 読みの終わりと同じかなを外す
            while e > s and not _kanji(text[e - 1]) and re_ > rs and _hira(phon[re_ - 1]) == text[e - 1]:
                e, re_ = e - 1, re_ - 1
            face = text[s:e]
            if (not face or not all(_kanji(c) for c in face) or _rank(face) < DOUBT_KEY
                    or not text.startswith(_SURU_HEAD, e) or (s > 0 and _kanji(text[s - 1]))):
                continue
            if any(x[0] == s and x[1] == e for x in out):
                continue
            # 読みは IME の逆変換（受 を うけ と読むことがある）と、字ごとの読みの組（じゅ＋りょう）の両方で見る
            typed = {_hira(phon[rs:re_])}
            try:
                import kanji_guess
                typed.update(kanji_guess.reading_combos(face)[:12])
            except Exception:
                pass
            cands = sorted(c for c in nouns if c != face and any(
                r == (collocation_repair._word_reading(c) or '') or _vowel_slip(r, collocation_repair._word_reading(c) or '')
                for r in typed))
            if cands:
                out.append((s, e, text[:s] + cands[0] + text[e:] if len(cands) == 1 else None))
    return out


RESEG_TIE = 300     # 区切り直し: 2番目の並びとの費用の差がこれより小さければ紫
_HIRAGANA = ''.join(chr(x) for x in range(0x3041, 0x3097))
RESEG_SLACK = 1500  # 区切り直し: 左右とも身近でない語のときに許す費用の上がり


def _reseg_faces(reading, cut=0):
    """読みを格子で区切り直した表記の並び。境目（cut）より後ろのかなのままの語は、同じ読みの身近な漢字の名詞が
    在ればそちらだけにする（元はIMEが漢字にした所なので）。"""
    try:
        import reading_lattice
        reading_lattice.load()
        # 世の中で珍しい語は高くして、身近な語の並びを選ぶ（かいとうあん → 甲斐＋東庵 でなく 回答＋案）
        res = reading_lattice.best(reading, word_cost=lambda surf, key, cost:
                                   cost + (KEY_GAIN if _strong(surf) and _rank(surf) > COMMON else 0))
    except Exception:
        return []
    if not res.surface or any(w[2] == '未知' for w in res.words):
        return []
    outs = ['']
    at = 0
    for w in res.words:
        alts = [w[0]]
        start, at = at, at + len(w[1])
        if not _strong(w[0]) and (w[2] == '名詞' or start >= cut):
            # IME は名詞を漢字にするので、身近な漢字の名詞が在ればそちらだけ
            alts = sorted({surf for surf, _l, _r, _c, pos in reading_lattice._table.get(w[1], ())
                           if pos == '名詞' and _strong(surf) and _rank(surf) <= COMMON}) or alts
        outs = [o + a for o in outs for a in alts][:64]
    return outs


def _reseg_scored(text, phon, s0, e0, r0, s1, e1, r1, q1, tokens, here, path_cost, tokenize):
    """左の語 [s0, e0) と珍しい語 [s1, e1) の読みを区切り直した行と費用の並び。"""
    if _span_rarity(text, s1, e1, tokens) < DOUBT or _span_rarity(text, s0, e0, tokens) >= DOUBT:
        return []
    both_odd = _span_rarity(text, s0, e0, tokens) > COMMON
    cut = len(_hira(phon[r0:r1]))
    reading = _hira(phon[r0:q1])
    scored = []
    for face in _reseg_faces(reading, cut):
        # 左の語が身近な語なら、そのままの表記で残る並びだけ（お客｜さまよう → お客様用）。左の語も
        # 身近でなければ（怪盗｜あんです）左の語ごと区切り直してよい
        if not all(_kanji(ch) or _katakana(ch) or 'ぁ' <= ch <= 'ゖ' for ch in face):
            continue
        if face == text[s0:e1] or (not face.startswith(text[s0:e0]) and not both_odd):
            continue
        other = text[:s0] + face + text[e1:]
        new = [t for t in tokenize(other) if t.start < s0 + len(face) and s0 < t.end]
        if not new or any(not t.has_reading for t in new):
            continue
        if any(_strong(t.surface) and _token_rarity(t, new) > COMMON for t in new):
            continue
        # 同じ字の語が続く並び（様＋様）は変換の重なりで、区切り直しの答えにしない
        if any(a.surface.endswith(b.surface) and _strong(b.surface) for a, b in zip(new, new[1:])):
            continue
        # 元の境目（左の語の読みの終わり）をまたぐ語が在ること（区切りが替わった）
        pos, crosses = 0, False
        for t in new:
            r = len(_hira(t.reading))
            if pos < cut < pos + r:
                crosses = True
            pos += r
        if not crosses and not both_odd:
            continue
        # 左右とも身近でない語の区切り直しは、語の部分が漢字・カタカナだけのもの（後ろの です などは別）
        relaxed_ok = not any('ぁ' <= ch <= 'ゖ' for ch in face.rstrip(_HIRAGANA))
        c = path_cost(other)
        # 行の費用が大きく下がる。または、左右とも身近でない語（怪盗＋アンデス）が身近な語だけの並びになり、
        # 費用がほとんど上がらない（名詞2つの並びは安いので、下がり方では見えない）
        if c is not None and (here - c >= KEY_GAIN or (both_odd and relaxed_ok and c - here <= RESEG_SLACK)):
            scored.append((c, other))
    return sorted(scored)


def _resegment(text, phon, words, here, path_cost, tokenize):
    """IME が読みの区切りを違えた形（おきゃくさま｜よう を お客｜さまよう と区切った）。珍しい語とその左の語の読みを
    格子で区切り直し、二つの語の境目をまたぐ身近な語の並びになって行の費用が大きく下がるなら、いちばん安い並びに直す。
    2番目と費用が近ければ紫。"""
    out = []
    tokens = None
    for i in range(1, len(words)):
        (s0, e0, r0, _q0), (s1, e1, r1, q1) = words[i - 1][:4], words[i][:4]
        if e0 != s1 or not _strong(text[s0:e0]) or not _strong(text[s1:e1]):
            continue
        if tokens is None:
            tokens = list(tokenize(text))
        ends = [(e1, q1)]
        # IME が送りがなを別の語にした形（彷徨｜う）: 続くかなだけの短い語を含めた形を先に見る（含めないと 様＋夜 のような切れ端が残る）
        if (i + 1 < len(words) and words[i + 1][0] == e1 and words[i + 1][1] - words[i + 1][0] <= 2
                and all('ぁ' <= ch <= 'ゖ' for ch in text[words[i + 1][0]:words[i + 1][1]])):
            ends.insert(0, (words[i + 1][1], words[i + 1][3]))
        for e, q in ends:
            scored = _reseg_scored(text, phon, s0, e0, r0, s1, e, r1, q, tokens, here, path_cost, tokenize)
            if scored:
                sure = len(scored) == 1 or scored[1][0] - scored[0][0] >= RESEG_TIE
                out.append((s1, e, scored[0][1] if sure else None))
                break
    return out


def _noun_compound(tokens, s, e):
    """[s, e) とそれにつながる名詞の並び（2語以上の複合語）の語。複合語でなければ []（2026-11-05 うに）。"""
    inside = [t for t in tokens if t.start < e and s < t.end]
    if not inside or not all(t.pos == '名詞' for t in inside):
        return []
    run = list(inside)
    grew = True
    while grew:
        grew = False
        for t in tokens:
            if t.pos == '名詞' and t not in run and (t.end == run[0].start or t.start == run[-1].end):
                run.insert(0, t) if t.end == run[0].start else run.append(t)
                grew = True
    return run if len(run) >= 2 else []


def _unlisted_in_compound(compound):
    """複合語の中に辞書に無い漢字の語（専門の語の一部）が在るか。在れば1打の戻しは紫まで（別の複合語に替えない:
    2026-11-05 うに 未解決タブ）。切り替え CN_RECONVERT_UNLISTED=0。"""
    if not compound or os.environ.get('CN_RECONVERT_UNLISTED') == '0':
        return False
    try:
        from morphology import dictionary_inflections
    except Exception:
        return False
    return any(len(t.surface) >= 2 and all('一' <= c <= '鿿' for c in t.surface) and not dictionary_inflections(t.surface)
               for t in compound)


def _in_noun_run(tokens, s, e):
    """[s, e) の語が、隣の名詞とつながった複合語の一部か（同音｜異義｜語・誤判｜定・産地｜アソート）。複合語の部分は
    1語より珍しく出るので、珍しさ DOUBT_KEY_TRY〜DOUBT_KEY の間の語は、複合語の中なら1打の戻しを試さない
    （2026-11-05 うに「解決していたものがいくつか戻ってます」: 11-04 batch127 で門を 650 に下げてから、正しい複合語が
    別の語に替わっていた）。切り替え CN_RECONVERT_NOUN_RUN=0。"""
    if os.environ.get('CN_RECONVERT_NOUN_RUN') == '0':
        return False
    inside = [t for t in tokens if t.start < e and s < t.end]
    if not inside or not all(t.pos == '名詞' for t in inside):
        return False
    return any(t.pos in ('名詞', '接頭詞') and (t.end == s or t.start == e) for t in tokens)


# ------------------------------------------------------------
# 打った記録の読みと辞書の表記で変換し直す（2026-11-07・うに「打った記録があれば読みに戻す変換は必要ない」
# 「候補は辞書から」）。雲と PC で同じ答えになるように、IME は次の2つのときだけ使う。
#   1. 読み: 記録の無い所（貼り付け・前に書いた行）だけ IME の reverse_words（IME が無ければ辞書の読み）
#   2. 表記: 辞書（reading_lattice の表＝janome の全項目）の同じ読みの表記を窓に当て、行の費用＋身近さで1つ選ぶ。
#      辞書に候補が無い窓だけ、IME の変換で辞書に無い語が出るなら足す
# 特定の語には合わせない。切り替え CN_RECONVERT_TYPED=0 で読みを前のまま（IME の reverse_words）、
# CN_RECONVERT_DICT=0 で表記を前のまま（IME の convert）。
# ------------------------------------------------------------
from contextvars import ContextVar

# (元の行, 記録の並び analysis_work.Occurrence)。correction_entry の段の前に置く（analysis_work.current_input が
# 段の外で切れているため）。置かれていなければ analysis_work の今の入力を見る
TYPED = ContextVar('ime_reconvert_typed', default=None)

DICT_TOP = 12        # 1つの読みで比べる辞書の表記の数（janome の費用の安い順）
DICT_PART_TOP = 5    # 2語の窓で語ごとに比べる表記の数
DICT_RANK_W = 15     # 選ぶときの身近さの重み（行の費用＋重み×wordfreq の段）。電機(549)より電気(419)を選ぶ程度
DICT_KANA_RANK = 520  # 選ぶとき、かなのままの内容の語（名詞・動詞・形容詞）の身近さ（IME は読みをふつう漢字にする）
_DICT_POS = ('名詞', '動詞', '形容詞', '副詞', '連体詞', '接頭詞', '感動詞', '接続詞')


def _env_on(name):
    return os.environ.get(name) != '0'


def _active_record():
    got = TYPED.get()
    if got:
        return got
    try:
        from analysis_work import _INPUT
        return _INPUT.get()
    except Exception:
        return None


def _map_span(text, source, a, b):
    """text[a:b] を source の同じ字の所へ（変わっていない所だけ）。"""
    if text == source:
        return a, b
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, text, source, autojunk=False).get_opcodes():
        if tag == 'equal' and i1 <= a and b <= i2:
            return a - i1 + j1, b - i1 + j1
    return None


def _one_reading(got):
    got = [_hira(r) for r in got or () if r]
    if len(set(got)) != 1 or not all('ぁ' <= c <= 'ゖ' or c in 'ー゛゜' for c in got[0]):
        return None
    return got[0]


def _record_reading(text, a, b, active):
    """text[a:b] の打った読み（記録から1つに決まるときだけ・かなで）。この行の確定の記録（occurrence_readings）を先に、
    無ければ表記ごとに覚えた打った読み（kanji_guess.ime_readings_for）。"""
    got = None
    if active and active[1]:
        source, occs = active
        m = _map_span(text, source, a, b)
        if m is not None:
            try:
                from analysis_work import current_input, occurrence_readings
                with current_input(source, occs):
                    got = _one_reading(occurrence_readings(source, m[0], m[1]))
            except Exception:
                got = None
    if got is None:
        try:
            import kanji_guess
            got = _one_reading(kanji_guess.ime_readings_for(text[a:b]))
        except Exception:
            got = None
    return got


def typed_reverse(text, tokens=None, ime=None):
    """IME の reverse_words と同じ形 (読み, ((開始, 終了, 読みの開始, 読みの終了, 品詞, 出所), ...))。
    出所は 'typed'（打った記録）・'kana'（かなの所）・'ime'（記録の無い所を IME で）・'dict'（記録も IME も無い所を
    辞書の読みで）。記録の無い所を IME の語の端に揃えられなければ IME の reverse_words をそのまま返す（前と同じ）。"""
    from morphology import tokenize
    toks = [t for t in (tokens if tokens is not None else tokenize(text))]
    active = _active_record()
    units, i, at = [], 0, 0
    while i < len(toks):
        t = toks[i]
        if t.start > at:                        # 解析の語の間の字（空白など）
            units.append([at, t.start, _hira(text[at:t.start]), '記号', 'kana'])
        if not _strong(t.surface):
            units.append([t.start, t.end, _hira(t.surface), t.pos, 'kana'])
            at = t.end
            i += 1
            continue
        got = None
        for k in (1, 2, 3):                     # 記録が複合語ごと（会議｜室）なら語をつないで引く
            if i + k > len(toks):
                break
            r = _record_reading(text, t.start, toks[i + k - 1].end, active)
            if r:
                got = (k, r)
                break
        if got:
            k, r = got
            units.append([t.start, toks[i + k - 1].end, r, t.pos, 'typed'])
            at = toks[i + k - 1].end
            i += k
            continue
        prev = units[-1] if units else None
        if prev is not None and prev[4] == 'typed' and prev[1] == t.start:
            # 前の語と1つの記録（補遺｜国書: 辞書の読み ほい と打った読み ほうい が違い、後ろだけでは引けない）
            r = _record_reading(text, prev[0], t.end, active)
            if r:
                prev[1], prev[2] = t.end, r
                at = t.end
                i += 1
                continue
        if all(_katakana(c) for c in t.surface):
            units.append([t.start, t.end, _hira(t.surface), t.pos, 'kana'])
        else:
            units.append([t.start, t.end, None, t.pos, 'none'])
        at = t.end
        i += 1
    if at < len(text):
        units.append([at, len(text), _hira(text[at:]), '記号', 'kana'])
    if any(u[4] == 'none' for u in units):
        rw = None
        if ime is not None:
            try:
                rw = ime.reverse_words(text)
            except Exception:
                rw = None
        if rw:
            phon_i, words_i = rw
            for u in units:
                if u[4] != 'none':
                    continue
                inside = [w for w in words_i if u[0] <= w[0] and w[1] <= u[1]]
                if not inside or inside[0][0] != u[0] or inside[-1][1] != u[1]:
                    return rw                    # IME の語の端が解析の語の端と揃わない: 前と同じ
                u[2] = _hira(phon_i[inside[0][2]:inside[-1][3]])
                u[4] = 'ime'
        else:
            for u, t in ((u, next((t for t in toks if t.start == u[0]), None)) for u in units):
                if u[4] != 'none':
                    continue
                if t is None or not getattr(t, 'has_reading', True) or not t.reading:
                    return None
                u[2] = _hira(t.reading)
                u[4] = 'dict'
    phon, words, rs = '', [], 0
    for s, e, r, pos, src in units:
        words.append((s, e, rs, rs + len(r), pos, src))
        phon += r
        rs += len(r)
    return phon, tuple(words)


@lru_cache(maxsize=1)
def _dict_table():
    try:
        import reading_lattice
        reading_lattice.load()
        return reading_lattice._table or {}
    except Exception:
        return {}


@lru_cache(maxsize=8192)
def _dict_faces(reading, limit=DICT_TOP):
    """この読みの辞書の表記（漢字か片仮名を含むもの）を janome の費用の安い順に。"""
    best = {}
    verb_kana = os.environ.get('CN_RECONVERT_VERB_KANA') != '0'
    for surf, _l, _r, cost, pos in _dict_table().get(reading, ()):
        # 漢字だけの動詞の表記で読みが字数の2倍以上（来 を きた）は、活用の字（た）を表記に入れない辞書の形。
        # 行に置くと た が消える（入って汲田 → 入って来）ので採らない（2026-11-08 手分けA）。CN_RECONVERT_VERB_KANA=0
        if verb_kana and pos == '動詞' and all(_kanji(c) for c in surf) and len(reading) >= 2 * len(surf):
            continue
        if pos in _DICT_POS and _strong(surf) and (surf not in best or cost < best[surf]):
            best[surf] = cost
    return tuple(sorted(best, key=lambda f: (best[f], f))[:limit])


def _score(line, path_cost, s, e):
    c = path_cost(line)
    if c is None:
        return None
    from morphology import tokenize
    ranks = []
    for t in tokenize(line):
        if t.start < e and s < t.end:
            if t.pos in ('名詞', '動詞', '形容詞') and not _strong(t.surface):
                ranks.append(DICT_KANA_RANK)
            else:
                ranks.append(_token_rarity(t))
    return c + DICT_RANK_W * max(ranks + [0])


LATTICE_ALT = 6      # 格子の並びの語ごとに比べる同じ読みの表記の数（しょ の 書 は6番目）
LATTICE_MAX = 64     # 格子の並びから作る表記の組の上限（1語として在るものだけ比べる）


def _suffix_kana_words(res):
    """格子の並びで、漢字の名詞のすぐ後ろのかなの語が接尾の名詞（お客様｜よう）なら、その読みの 接尾・一般 の
    漢字の表記（用）。{語の番号: [表記]}。辞書の費用の順では上の方に来ない（よう の 用 は15番目）ので別に足す。
    CN_RECONVERT_SUFFIX_FACE=0 で前のまま（2026-11-08 手分けA）。"""
    out = {}
    W = res.words
    if not any(not _strong(w[0]) for w in W[1:]):
        return out
    try:
        from morphology import tokenize, dictionary_base_pos
    except Exception:
        return out
    toks = list(tokenize(res.surface))
    pos = 0
    for i, (surf, key, _p, _o) in enumerate(W):
        a, b = pos, pos + len(surf)
        pos = b
        if i == 0 or _strong(surf) or not _strong(W[i - 1][0]):
            continue
        t = [x for x in toks if x.start == a and x.end == b]
        if not t or t[0].pos != '名詞' or not (t[0].pos_sub or '').startswith('接尾:一般'):
            continue
        out[i] = [f for f in _dict_faces(key, 40) if len(f) == 1 and _kanji(f)
                  and '名詞,接尾,一般,*' in (dictionary_base_pos(f) or ())]
    return out


@lru_cache(maxsize=8192)
def _lattice_faces(reading):
    """読みの格子の一番安い切り方（ほうこく｜しょ）で、語ごとに同じ読みの辞書の表記を替えた並び（報告署・報告書…）。
    格子は語の切り方だけに使い、表記は行の費用で選ぶ（格子の表記だけだと珍しい字を選ぶ）。知らない字があれば無し。
    組んだ表記は、1語として在る（seed_japanese.is_unit）ものだけ（報告書は在る・報告署は無い）。表が無ければ絞らない。"""
    try:
        import reading_lattice
        res = reading_lattice.best(reading)
    except Exception:
        return ()
    if not res.surface or any(w[2] == '未知' for w in res.words) or len(res.words) < 2:
        return ()
    out = ['']
    sfx = _suffix_kana_words(res) if os.environ.get('CN_RECONVERT_SUFFIX_FACE') != '0' else {}
    for i, (surf, key, _pos, _ops) in enumerate(res.words):
        opts = list(dict.fromkeys([surf] + (list(_dict_faces(key, LATTICE_ALT)) if _strong(surf) else sfx.get(i, []))))
        out = [a + b for a in out for b in opts][:LATTICE_MAX]
    try:
        import seed_japanese
        unit = seed_japanese.is_unit
    except Exception:
        unit = lambda f: None
    if (os.environ.get('CN_RECONVERT_VERB_FACE') != '0' and len(res.words) == 2
            and res.words[0][2] in ('動詞', '形容詞') and not _strong(res.words[1][0])
            and (res.words[1][2] == '助動詞'
                 # 活用する語＋て・で（遊ん｜で）も同じ（2026-11-08 手分けA: 宇遊んで の う を抜いた あそんで）。
                 # CN_RECONVERT_VERB_TE=0 で前のまま
                 or (res.words[1][2] == '助詞' and res.words[1][0] in ('て', 'で')
                     and os.environ.get('CN_RECONVERT_VERB_TE') != '0'))):
        # 活用する語＋かなの助動詞（出かけ｜た）は、語の表（1語の表記の表）には活用した形で載らない。活用する語の所が
        # 辞書の語なら採る（2026-11-08 田桁: 打った読み でんけた の1打を戻した でかけた が 出かけた にならず、かなのままだった）
        return tuple(f for f in out if _strong(f))
    whole = tuple(f for f in out if _strong(f) and unit(f) is not False)
    if sfx and len(res.words) == 2 and 1 in sfx:
        # 名詞＋接尾の名詞（お客様＋用）は、組そのものは語の表に載らない。前の名詞が表の語なら採る
        head = list(dict.fromkeys([res.words[0][0]] + list(_dict_faces(res.words[0][1], LATTICE_ALT))))
        whole += tuple(h + x for h in head for x in sfx[1] if _strong(h) and unit(h) is not False and h + x not in whole)
    if whole or os.environ.get('CN_RECONVERT_PHRASE_FACE') == '0' or len(res.words) > 4:
        return whole
    W = res.words
    # 句は活用する語で始まり、すぐ後ろがかなの助動詞で、3語以上（2語は上の VERB_FACE の受け持ち）
    if len(W) < 3 or W[0][2] not in ('動詞', '形容詞') or W[1][2] != '助動詞' or _strong(W[1][0]):
        return whole
    # 活用する語＋かなの助動詞を含む句（伝え｜た｜こと）は、句ごとは語の表に載らない。語ごとに表の語（かなの語はそのまま）
    # なら採る（2026-11-08 手分けA: 打った読み つたえふたこと の巻き込みを戻した つたえたこと が表記にならなかった）
    pieces = [[]]
    for surf, key, _pos, _ops in W:
        opts = list(dict.fromkeys([surf] + (list(_dict_faces(key, LATTICE_ALT)) if _strong(surf) else [])))
        pieces = [a + [b] for a in pieces for b in opts][:LATTICE_MAX]
    return tuple(''.join(ps) for ps in pieces
                 if _strong(''.join(ps)) and all(not _strong(x) or unit(x) is True for x in ps))


def _pos_major(text, s, e, line=None):
    """[s, e) の漢字・片仮名を含む語の品詞の大分類の組（変｜雌雄 と 編集 はどちらも 名詞 だけ）。"""
    from morphology import tokenize
    return frozenset(t.pos for t in tokenize(line if line is not None else text)
                     if t.start < e and s < t.end and _strong(t.surface))


def _plausible_face(face, src):
    """辞書で当てた表記として採れるか: 元に無い片仮名を持ち込まない（肺→ハイ）、1字の漢字の語を2つ続けた並び
    （照所→手署）は1語として在る（seed_japanese.is_unit）ときだけ。"""
    if any(_katakana(c) for c in face) and not any(_katakana(c) for c in src):
        return False
    from morphology import tokenize
    toks = [t for t in tokenize(face)]
    if any(len(a.surface) == 1 and len(b.surface) == 1 and _kanji(a.surface) and _kanji(b.surface)
           for a, b in zip(toks, toks[1:])):
        try:
            import seed_japanese
            return seed_japanese.is_unit(face) is not False
        except Exception:
            return True
    return True


def dict_convert(text, s, e, reading, parts=None, path_cost=None, keep=True, scored=False, any_pos=False):
    """text[s:e] を読み reading の辞書の表記にした行のうち、行の費用＋身近さが一番よい行。
    keep=True（同じ読み）なら元の行とも比べ、元の行より良くなければ元の行。keep=False（1打を戻した読み）は
    元の行と比べず、かなのままの読みも候補に入れる（IME も読みをかなのまま返すことがある）。
    parts: 窓が2語のとき [(元の表記, 読み), ...]（語ごとの表記の組も比べる）。候補が無ければ元の行。
    keep=True では品詞の大分類の組が元と同じ表記だけ（家→言え のように名詞を動詞にしない）。
    scored=True なら (行, 点)（点は小さいほど良い・候補が無ければ None）。"""
    if path_cost is None:
        from morphology import path_cost
    cands = list(_dict_faces(reading))
    cands += list(_lattice_faces(reading))
    if not keep:
        cands.append(reading)
    if parts and len(parts) == 2:
        # 語ごとに: 元が漢字・片仮名の語は辞書の表記（元の表記も）、元がかなの語はかなのまま
        def opts(face, rd):
            if not _strong(face):
                return [face]
            return list(dict.fromkeys(list(_dict_faces(rd, DICT_PART_TOP)) + [face]))
        (f1, r1), (f2, r2) = parts
        cands += [a + b for a in opts(f1, r1) for b in opts(f2, r2)]
    best_line, best = text, (_score(text, path_cost, s, e) if keep else None)
    pos0 = _pos_major(text, s, e) if keep and not any_pos else None
    for face in dict.fromkeys(cands):
        if face == text[s:e] or not _plausible_face(face, text[s:e]):
            continue
        line = text[:s] + face + text[e:]
        if pos0 is not None and _pos_major(text, s, s + len(face), line) != pos0:
            continue
        sc = _score(line, path_cost, s, s + len(face))
        if sc is not None and (best is None or sc < best):
            best_line, best = line, sc
    return (best_line, best) if scored else best_line


def _not_in_dict(text, other):
    """IME の変換で替わった所の語が、どれも辞書に読みを持たないか（辞書に無い語を足すときだけ IME を使う）。"""
    try:
        from inflected_lexicon import dictionary_readings
        from morphology import tokenize
    except Exception:
        return False
    ch = _changed_span(text, other)
    if ch is None:
        return False
    ops = [o for o in difflib.SequenceMatcher(None, text, other, autojunk=False).get_opcodes() if o[0] != 'equal']
    j1, j2 = ops[0][3], ops[-1][4]
    new = [t for t in tokenize(other) if t.start < j2 and j1 < t.end and _strong(t.surface)]
    return bool(new) and all(not dictionary_readings(t.surface) for t in new)


def _changed_rarity(text, other):
    """other で替わった所の語の珍しさの最大（かなだけ・機能語は 0）。"""
    from morphology import tokenize
    ops = [o for o in difflib.SequenceMatcher(None, text, other, autojunk=False).get_opcodes() if o[0] != 'equal']
    if not ops:
        return 0
    j1, j2 = ops[0][3], ops[-1][4]
    toks = list(tokenize(other))
    return max([_token_rarity(t, toks) for t in toks if t.start < max(j2, j1 + 1) and j1 < t.end] + [0])


_DIGITS = frozenset('0123456789０１２３４５６７８９〇一二三四五六七八九十百千万億')


def _numeral_in_word(text, i):
    """text[i] の漢数字が、隣の漢字1字とつないで表の語（二言・一言）になるか。数ではなく語の字なので (1) の数字に数えない。
    CN_RECONVERT_NUMERAL_WORD=0 で前のまま（2026-11-08 手分けA）。"""
    if os.environ.get('CN_RECONVERT_NUMERAL_WORD') == '0' or not _kanji(text[i]):
        return False
    for a, b in ((i - 1, i + 1), (i, i + 2)):
        pair = text[max(0, a):b]
        if len(pair) == 2 and all(_kanji(c) for c in pair) and not all(c in _DIGITS for c in pair) and _rank(pair) < 800:
            return True
    return False


def _window_ok(text, w, tokens):
    """記録と辞書の道で見てよい窓か（補正担当 2026-11-07 Tatoeba 2,496行の崩れ）:
    (1) 窓か前後1字に数字（全角・漢数字も）があれば見ない（２人おり→当たり）
    (2) 片仮名だけの語・固有名詞（人名・地名）を含む窓は見ない（テムズ・健次）
    (3) 打った記録の無い語（辞書の読み 'dict'）を含む窓は見ない（貼り付け・前に書いた行は前と同じく何もしない）"""
    s, e = w[0][0], w[-1][1]
    if any(c in _DIGITS and not _numeral_in_word(text, i) for i, c in enumerate(text[max(0, s - 1):e + 1], max(0, s - 1))):
        return False
    if any(x[5] == 'dict' and _strong(text[x[0]:x[1]]) for x in w):
        return False
    # (2) は、窓の漢字・片仮名の語がどれも打った記録の読みで見えているときは外す（アメル・月余エビ: かなで打って IME が
    # 片仮名・人名にした所は、打った読みが在るので打ち違いとして見てよい）
    if all(x[5] == 'typed' for x in w if _strong(text[x[0]:x[1]])):
        return True
    for t in tokens:
        if t.start < e and s < t.end and _strong(t.surface):
            if all(_katakana(c) for c in t.surface) or (t.pos_sub or '').startswith('固有名詞'):
                return False
    return True


class _Converter:
    """propose の変換し直し。辞書のとき（既定）は窓の所だけ辞書の表記を当てる。IME のときは前と同じ（行の読みを丸ごと）。"""

    def __init__(self, text, phon, words, ime):
        self.text, self.phon, self.words, self.ime = text, phon, words, ime
        self.dict = _env_on('CN_RECONVERT_DICT') and bool(_dict_table())
        self._first = None
        self._memo = {}

    def _parts(self, w, reading=None):
        if len(w) != 2 or reading is not None:
            return None
        return [(self.text[x[0]:x[1]], _hira(self.phon[x[2]:x[3]])) for x in w]

    def _ime_line(self, reading_line):
        if self.ime is None:
            return ''
        try:
            return self.ime.convert(reading_line) or ''
        except Exception:
            return ''

    def first(self, w=None):
        """読みを替えずに変換し直した行。辞書なら窓 w の所だけ。"""
        if not self.dict:
            if self._first is None:
                self._first = self._ime_line(self.phon)
            return self._first
        if w is None:
            return self.text
        # 1字の漢字だけの窓（線・背）は、IME なら前後とつないで変換する所。窓だけの辞書の表記では選び違いと言えない
        if w[-1][1] - w[0][0] == 1:
            return self.text
        key = ('first', w[0][0], w[-1][1])
        if key not in self._memo:
            s, e = w[0][0], w[-1][1]
            reading = _hira(self.phon[w[0][2]:w[-1][3]])
            got = dict_convert(self.text, s, e, reading, self._parts(w), any_pos=_unreadable_face(self.text, w, reading))
            # 同じ読みの別の表記は、替わった所の語がどれも身近な語（COMMON 以下）のときだけ「IME の最初の変換」とみなす。
            # 打った記録のある行は IME がその表記を出した行なので、辞書の費用だけで選んだ珍しい表記（補遺国書→包囲酷暑）を
            # 対抗の候補にしない（_same_reading_rival が1打の戻しを止めてしまう）
            if got != self.text and _changed_rarity(self.text, got) > COMMON:
                got = self.text
            if got == self.text and self.ime is not None:
                other = self._ime_line(self.phon)
                if other and other != self.text and _not_in_dict(self.text, other):
                    got = other
            self._memo[key] = got
        return self._memo[key]

    def key(self, w, v):
        """窓 w の読みを v に替えて変換し直した行。"""
        rs, re_ = w[0][2], w[-1][3]
        if not self.dict:
            return self._ime_line(self.phon[:rs] + v + self.phon[re_:])
        s, e = w[0][0], w[-1][1]
        got = dict_convert(self.text, s, e, v, keep=False)
        if got == self.text and self.ime is not None:
            other = self._ime_line(self.phon[:rs] + v + self.phon[re_:])
            if other and other != self.text and _not_in_dict(self.text, other):
                got = other
        return got


_VERB_ONLY_AUX = ('う', 'よう', 'た', 'ます', 'ない', 'ぬ', 'れる', 'られる', 'せる', 'させる', 'たい')


def _broken_noun_aux(tokens, s, e):
    """[s, e) の解析に、名詞のすぐ後ろの、用言にしか付かない助動詞（彷徨｜う の う）が在るか。"""
    inside = [t for t in tokens if t.start < e and s < t.end]
    return any(a.pos == '名詞' and b.pos == '助動詞' and b.start == a.end and b.surface in _VERB_ONLY_AUX
               for a, b in zip(inside, inside[1:]))


def _join_broken_reading(text, tokens, rw):
    """辞書の読みの語（'dict'）が、名詞＋用言にしか付かない助動詞（彷徨｜う）と切れた所は、つないだ表記の同梱の表の読みが
    1つなら（彷徨う → さまよう）それを1語の読みにする（IME の無い道・IME が読みを返さない道で、IME の読みの代わり）。"""
    phon, words = rw
    if os.environ.get('CN_RECONVERT_JOIN_BROKEN') == '0':
        return phon, words
    try:
        import corrector
        lookup = corrector._table_readings_for_surface
    except Exception:
        return phon, words
    out, i, changed = [], 0, False
    while i < len(words):
        w = words[i]
        if i + 1 < len(words) and w[5] in ('dict', 'ime') and words[i + 1][1] > w[1] \
                and _broken_noun_aux(tokens, w[0], words[i + 1][1]):
            nx = words[i + 1]
            if w[5] == 'ime':
                # IME の読み（彷徨 を さまよ・う を う）はそのままつなぐ（PC の IME は 彷徨｜う と2語で返す: 2026-11-09 PC の診断）
                rds = [_hira(phon[w[2]:w[3]] + phon[nx[2]:nx[3]])]
            else:
                try:
                    rds = list(dict.fromkeys(_hira(r) for r in (lookup(text[w[0]:nx[1]]) or ())))
                except Exception:
                    rds = []
            if len(rds) == 1:
                out.append([w[0], nx[1], rds[0], '動詞', 'dict'])
                i += 2
                changed = True
                continue
        out.append([w[0], w[1], phon[w[2]:w[3]], w[4], w[5]])
        i += 1
    if not changed:
        return phon, words
    new_phon, new_words, at = '', [], 0
    for s, e, r, pos, src in out:
        new_words.append((s, e, at, at + len(r), pos, src))
        new_phon += r
        at += len(r)
    return new_phon, tuple(new_words)


def _same_big_untyped(text, tokens, rw, path_cost, tokenize):
    """打った記録の無い行の、読みを替えない辞書の表記の直し（SAME_BIG の決まりだけ）。窓は1〜2語、窓の漢字の語は
    辞書の読み（または IME の読み）。数字・片仮名・固有名詞の窓は見ない。IME の読み違い（浅煎り）の所も見ない。"""
    phon, words = _join_broken_reading(text, tokens, rw)
    here = path_cost(text)
    if here is None:
        return []
    conv = _Converter(text, phon, words, None)
    if not conv.dict:
        return []
    # 辞書の解析が名詞のすぐ後ろに用言にしか付かない助動詞を置いた所（彷徨｜う）は、辞書の読みの方が崩れている。
    # そこは IME の読みとの食い違いを読み違いとみなさない
    misread = [m for m in _misread_spans(text, phon, words, tokens) if not _broken_noun_aux(tokens, m[0], m[1])]
    out = []
    for i in range(len(words)):
        for k in range(1, MAX_WORDS + 1):
            w = words[i:i + k]
            if len(w) < k:
                break
            s, e = w[0][0], w[-1][1]
            if not _strong(text[s:e]) or any(a < e and s < b for a, b, _f in out):
                continue
            ww = [tuple(x[:5]) + ('typed' if x[5] in ('dict', 'ime') else x[5],) for x in w]
            if not _window_ok(text, ww, tokens):
                continue
            if any((t.pos_sub or '').startswith('固有名詞') or all(_katakana(c) for c in t.surface)
                   for t in tokens if t.start < e and s < t.end and _strong(t.surface)):
                continue
            src_rare = _span_rarity(text, s, e, tokens)
            if src_rare < DOUBT:
                continue
            first = conv.first(w)
            same = _judge(text, here, first, s, e, tokens, src_rare, path_cost, tokenize)
            if same is None:
                continue
            gain, rr, (a, b) = same
            if s <= a and b <= e and gain >= SAME_BIG_GAIN and rr <= COMMON and src_rare - rr >= JUMP:
                m = (s, e, first if gain >= SAME_BIG_FIX else None)
                if not _touches(m, misread, text):
                    out.append(m)
    return out


def _head_suffix_marks(text, tokens):
    """文節の頭（行頭・記号の後ろ）に接尾の語（的・性・化）が来る所は、語に付く語が付く先なしに出ていて、解析が
    読めない並び（IME の変換の崩れ: 的｜買い）。その接尾の語と、すぐ後ろに続く漢字を含む語までを紫にする
    （2026-11-09 手分けA）。CN_RECONVERT_HEAD_SUFFIX=0 で前のまま。"""
    if os.environ.get('CN_RECONVERT_HEAD_SUFFIX') == '0':
        return []
    out = []
    for i, t in enumerate(tokens):
        if not (t.pos == '名詞' and (t.pos_sub or '').startswith('接尾') and _strong(t.surface)):
            continue
        prev = tokens[i - 1] if i else None
        if prev is not None and not (prev.pos == '記号' and prev.end == t.start):
            continue
        e = t.end
        if i + 1 < len(tokens) and tokens[i + 1].start == e and _strong(tokens[i + 1].surface):
            e = tokens[i + 1].end
        out.append((t.start, e, None))
    return out


def propose(text, input_method='kana', ime=None):
    """[(開始, 終了, 置く行 or None)]。置く行があれば直す、None は紫。"""
    typed = _env_on('CN_RECONVERT_TYPED')
    if not _freq() or (ime is None and not typed) or not text or not _strong(text):
        return []
    from morphology import path_cost, tokenize
    tokens = list(tokenize(text))
    head = _head_suffix_marks(text, tokens)
    if head:
        return head
    if max([_token_rarity(t, tokens) for t in tokens] + [0]) < DOUBT:
        return []
    rw = typed_reverse(text, tokens, ime) if typed else ime.reverse_words(text)
    big = []
    if typed and rw and not any(w[5] == 'typed' for w in rw[1]):
        # 打った記録の無い行でも、読みを替えない辞書の表記で行の費用がとても大きく下がる所（語の切れ目から崩れた形:
        # お客｜彷徨｜う → お客様用）は、IME が在っても無くても同じに見る（PC の IME は自分の選んだ表記を第1候補に
        # 返すので IME の道では見つからない）。CN_RECONVERT_SAME_BIG_UNTYPED=0 で前のまま（2026-11-08 手分けA）
        if os.environ.get('CN_RECONVERT_SAME_BIG_UNTYPED') != '0' and os.environ.get('CN_RECONVERT_SAME_BIG') != '0':
            from morphology import path_cost as _pc, tokenize as _tk
            big = _same_big_untyped(text, tokens, rw, _pc, _tk)
        # (3) 打った記録が1語も無い行（貼り付け・前に書いた行）は前と同じ: IME が無ければ何もしない、在れば IME の道
        if ime is None:
            return big
        typed = False
        rw = ime.reverse_words(text)
    if not rw:
        return []
    phon, words = rw
    here = path_cost(text)
    if here is None:
        return []
    conv = _Converter(text, phon, words, ime)
    if not typed:
        conv.dict = False
    misread = _misread_spans(text, phon, words, tokens)
    if typed:
        # 打った記録・辞書の読みの語は IME の読み違いではない。IME で読んだ語に掛かる所だけ残す
        misread = [m for m in misread
                   if any(w[0] < m[1] and m[0] < w[1] and w[5] not in ('typed', 'kana', 'dict') for w in words)]
    first = None
    picked = _extra_key(text, phon, words, here, path_cost, tokenize) if input_method == 'romaji' else []
    picked += [m for m in _vowel_slip_noun(text, phon, words) if not any(a < m[1] and m[0] < b for a, b, _f in picked)]
    picked += [m for m in _resegment(text, phon, words, here, path_cost, tokenize) if not any(a < m[1] and m[0] < b for a, b, _f in picked)]
    if typed:
        # 記録と辞書の道では、ほかの探し（区切り直し・母音の打ち違い）にも同じ窓の決まり（数字・片仮名・固有名詞・記録の無い語）
        picked = [m for m in picked
                  if _window_ok(text, [x for x in words if x[0] < m[1] and m[0] < x[1]] or [(m[0], m[1], 0, 0, '', 'dict')], tokens)]
    for i in range(len(words)):
        for k in range(1, MAX_WORDS + 1):
            w = words[i:i + k]
            if len(w) < k:
                break
            s, e, rs, re_ = w[0][0], w[-1][1], w[0][2], w[-1][3]
            if not _strong(text[s:e]):
                continue
            if typed and not _window_ok(text, w, tokens):
                continue
            src_rare = _span_rarity(text, s, e, tokens)
            if src_rare < DOUBT or any(a < e and s < b for a, b, _f in picked):
                continue
            first = conv.first(w)
            found = None
            same = _judge(text, here, first, s, e, tokens, src_rare, path_cost, tokenize)
            if same is not None:
                gain, rr, (a, b) = same
                # 直すのは、表に無いほど珍しい語が IME 自身の変換で身近な語に替わるときだけ（迷うなら紫）
                if (s <= a and b <= e and src_rare >= DOUBT_KEY and src_rare - rr >= FIX_JUMP and rr <= FIX_COMMON
                        and gain >= MARK_GAIN):
                    found = (s, e, first)
                elif src_rare >= DOUBT_MARK and gain >= MARK_GAIN:
                    found = (s, e, None)
                elif (typed and os.environ.get('CN_RECONVERT_SAME_BIG') != '0' and s <= a and b <= e
                      and gain >= SAME_BIG_GAIN and rr <= COMMON and src_rare - rr >= JUMP
                      and all(x[5] == 'typed' for x in w if _strong(text[x[0]:x[1]]))):
                    # 打った読みのままの辞書の表記で、行の費用がとても大きく下がり（語の切れ目から崩れていた形: お客｜彷徨｜う）、
                    # 替わった先が身近な語なら、門（DOUBT_MARK）より少し身近な語でも IME の選び違いとして直す（2026-11-08 手分けA）。
                    # 下がりが SAME_BIG_FIX 以上なら直す、足りなければ紫。CN_RECONVERT_SAME_BIG=0 で前のまま
                    found = (s, e, first if gain >= SAME_BIG_FIX else None)
            compound = _noun_compound(tokens, s, e)
            # 名詞が2つ以上つながった複合語で、どの部分も1語としては珍しくない（同音｜異義｜語・誤判｜定）。複合語は
            # 部分より珍しく出るだけなので、1打の戻しを試さない（2026-11-05 うに「解決していたものが戻った」）
            plain_compound = bool(compound) and max(_token_rarity(t, tokens) for t in compound) < DOUBT_KEY \
                and os.environ.get('CN_RECONVERT_NOUN_RUN') != '0'
            # 巻き込み（隣のキーを一緒に押した1字が入った: つたえ＋ふ＋たこと）の戻しは、打った記録の在る窓なら
            # 珍しさの門を DOUBT に下げて試す（指の動きで説明が付く形なので。ほかの1打の戻しは今まで通り）。
            # CN_RECONVERT_ROLLIN_LOW=0 で前のまま（2026-11-08 手分けA 伝え二言で）
            rollin_low = (found is None and not plain_compound and DOUBT <= src_rare < DOUBT_KEY_TRY
                          and input_method == 'kana' and typed and os.environ.get('CN_RECONVERT_ROLLIN_LOW') != '0'
                          and all(x[5] == 'typed' for x in w if _strong(text[x[0]:x[1]]))
                          # 固有名詞（人名・地名: 知多）を含む窓は今まで通り 650 の門（珍しさは名前の珍しさで、打ち違いの跡ではない。
                          # 散歩し知多 → 散歩下・散歩し千 を止める: 2026-11-08 補正担当の測り）。CN_RECONVERT_ROLLIN_PROPER=1 で前のまま
                          and (os.environ.get('CN_RECONVERT_ROLLIN_PROPER') == '1'
                               or not any((t.pos_sub or '').startswith('固有名詞')
                                          for t in tokens if t.start < e and s < t.end)))
            if found is None and not plain_compound and (rollin_low or src_rare >= DOUBT_KEY_TRY) \
                    and (rollin_low or src_rare >= DOUBT_KEY or not _in_noun_run(tokens, s, e)) \
                    and not (src_rare < DOUBT_KEY and _typed_real_noun(text, s, e, _hira(phon[rs:re_]), tokens)):
                reading = _hira(phon[rs:re_])
                passed = []
                keys = _key_readings(reading, input_method)
                if rollin_low and src_rare < DOUBT_KEY_TRY:
                    keys = [v for v in keys if _rollin_drop(reading, v)]
                for v in keys:
                    if _drops_edge_particle(w, phon, v, text, tokens):
                        continue
                    other = conv.key(w, v)
                    if _changes_edge_particle(text, w, other, tokens):
                        continue
                    if rollin_low and src_rare < DOUBT_KEY_TRY and _eats_kana_head(text, s, e, other):
                        continue
                    got = _judge(text, here, other, s, e, tokens, src_rare, path_cost, tokenize, KEY_COMMON)
                    if got is not None and got[0] >= KEY_MARK_GAIN:
                        passed.append((got[0], got[1], got[2], other))
                # KEY_GAIN に届かない戻しは、身近な語だけになる1つのときだけ数える（ほかは切り方の揺れの分かもしれない）
                if passed and max(x[0] for x in passed) < KEY_GAIN and (
                        len(passed) > 1 or passed[0][1] > KEY_FIX_COMMON):
                    passed = []
                if passed:
                    found = (s, e, None)
                    # 決める: 1打の戻しで窓の語がどれも身近な語になり、ほかの戻しより行の費用がはっきり下がる1つ
                    # （迷うなら紫・2026-11-04 うに「ローマ字で思ったより直らない」）。切り替え CN_RECONVERT_KEY_FIX=0
                    if os.environ.get('CN_RECONVERT_KEY_FIX') != '0':
                        passed.sort(key=lambda x: -x[0])
                        g0, r0, (a0, b0), o0 = passed[0]
                        if (r0 <= KEY_FIX_COMMON and src_rare - r0 >= JUMP and s - 1 <= a0 and b0 <= e + 1
                                and not _unlisted_in_compound(compound)

                                and (len(passed) == 1 or g0 - passed[1][0] >= KEY_GAIN)
                                and not _kana_scraps(text, o0) and not _key_fix_overreach(text, o0)
                                and not _splits_neighbour(tokens, s, e, a0, b0)
                                and not _same_reading_rival(text, first, s, e)
                                and not _homophone_tie(text, o0)
                                # 辞書で変換し直したときは、漢字が1字だけの窓は直さず紫（IME なら前後の語とつないで
                                # 変換する所で、窓だけの辞書の表記は当てにならない: 罪李→妻李・点くの→地区の の型）
                                and not (conv.dict and sum(_kanji(c) for c in text[s:e]) <= 1)):
                            found = (s, e, o0)
            if found is not None:
                # 紫は窓の中の珍しい語だけに付ける（前後の助詞などは含めない）
                rare = [t for t in tokens if t.start < e and s < t.end and _token_rarity(t, tokens) >= DOUBT]
                if rare and found[2] is None:
                    found = (max(s, rare[0].start), min(e, rare[-1].end), None)
                # 紫だけの所が、身近な2字以上の語2つの複合語（箇条＋書き）なら、複合語が表に無いだけ。紫にしない
                # （2026-11-06 PC の正しい文 箇条書きで書く のかなの紫）。CN_RECONVERT_PLAIN_MARK=0 で前のまま
                if (found[2] is None and os.environ.get('CN_RECONVERT_PLAIN_MARK') != '0'
                        and all(_kanji(c) or 'ぁ' <= c <= 'ゖ' for c in text[found[0]:found[1]])
                        and _plain_two_part(text[found[0]:found[1]])):
                    continue
                picked.append(found)
    # IME が本文の語を辞書と違う読みで読んだ所（浅煎り を せんいり）は、その読みからの直しも紫も出さない（2026-10-31）
    # 置く行が印の外まで書き換えるとき（印は 煎り、置く行は 浅 も変える）は、書き換わる所全体で見る
    out = [m for m in picked if not _touches(m, misread, text)]
    if big:
        # 重なる所は、ほかの探しの直しを先に、紫だけならこちらの直しを先に
        ov = lambda m, ms: any(a < m[1] and m[0] < b for a, b, _f in ms)
        keep = [m for m in big if not ov(m, [x for x in out if x[2] is not None])
                and (m[2] is not None or not ov(m, out))]
        out = keep + [m for m in out if not (m[2] is None and ov(m, [x for x in keep if x[2] is not None]))]
    # 置く行が、元の行の身近な語の途中までを書き換える（晴れ｜のち｜曇り → 晴れの｜地区漏れ）なら、IME が区切りを
    # 替えただけの別の読みなので直さず紫にとどめる（どの段の候補でも同じ・2026-11-06 変換ミスの試験）
    if os.environ.get('CN_RECONVERT_NO_SPLIT') != '0':
        split = [m for m in out if m[2] is not None and _splits_common(text, m[2], tokens)]
        if split:
            # 行の読みを IME が丸ごと変換した第1候補が元の行と同じなら、元の行は IME どおりの正しい形なので紫も付けない
            def _same(m):
                if not conv.dict:
                    return conv.first() == text
                w = [x for x in words if x[0] < m[1] and m[0] < x[1]]
                return (conv.first(w) if w else text) == text
            out = [m for m in out if not (m in split and _same(m))]
            out = [(m[0], m[1], None) if m in split else m for m in out]
    return out


def _plain_two_part(face):
    """face が、どちらも2字以上で一般の文の表で DOUBT_KEY より前の語2つに分けられるか（箇条＋書き）。"""
    for k in range(2, len(face) - 1):
        h, t = face[:k], face[k:]
        if _strong(h) and _strong(t) and _rank(h) < DOUBT_KEY and _rank(t) < DOUBT_KEY:
            return True
    return False


def _splits_common(text, other, tokens):
    ch = _changed_span(text, other)
    if ch is None:
        return False
    a, b = ch
    touched = [t for t in tokens if a < t.end and t.start < b]
    for t in touched:
        if not (a <= t.start and t.end <= b) and _token_rarity(t, tokens) < DOUBT:
            return True
    if os.environ.get('CN_RECONVERT_PLAIN_WORDS') != '0':
        # 替わる所の端が、身近な語（一般の文の表で DOUBT より前・漢字かカタカナ2字以上）の途中で切れる（追記｜文 の 記文 を替える）
        for x in range(max(0, a - 3), a):
            for y in range(a + 1, min(len(text), a + 3) + 1):
                w = text[x:y]
                if len(w) >= 2 and _strong(w) and all(_kanji(c) or _katakana(c) for c in w) and _rank(w) < DOUBT:
                    return True
        for x in range(max(0, b - 3), b):
            for y in range(b + 1, min(len(text), b + 3) + 1):
                w = text[x:y]
                if len(w) >= 2 and _strong(w) and all(_kanji(c) or _katakana(c) for c in w) and _rank(w) < DOUBT:
                    return True
        # 替わる所が、どちらも2字以上の珍しくない語2つに分けられる複合語（箇条＋書き）: 表に無いだけの正しい複合語
        if _plain_two_part(text[a:b]):
            return True
        # 替わる所が、身近な語（DOUBT より前・2字以上）＋ 漢字の続く複合語（追記＋文）で、置く行にその語が残らない
        span = text[a:b]
        for k in range(2, len(span)):
            h = span[:k]
            if (all(_kanji(c) or _katakana(c) for c in span) and _rank(h) < DOUBT
                    and h not in other[a:a + (len(other) - len(text)) + (b - a)]):
                return True
    # 替わる所が身近な かなの語だけ（晴れ｜のち → 晴れ｜日）: 疑った珍しい語に触れず、身近な語を替えるだけの直し
    # （2026-11-06 ローマ字の 晴れのち曇り）。CN_RECONVERT_COMMON_ONLY=0 で前のまま
    if touched and os.environ.get('CN_RECONVERT_COMMON_ONLY') != '0' \
            and all(_token_rarity(t, tokens) < DOUBT and all('ぁ' <= c <= 'ゖ' for c in t.surface) for t in touched):
        return True
    return False


def _changed_span(text, line):
    """text と置く行 line の違う所 (s, e)（text の側の位置）。同じなら None。"""
    if line == text:
        return None
    a = 0
    while a < len(text) and a < len(line) and text[a] == line[a]:
        a += 1
    b = 0
    while b < len(text) - a and b < len(line) - a and text[-1 - b] == line[-1 - b]:
        b += 1
    return a, len(text) - b


def _touches(m, spans, text):
    s, e = m[0], m[1]
    if m[2] is not None:
        ch = _changed_span(text, m[2])
        if ch is not None:
            s, e = min(s, ch[0]), max(e, ch[1])
    return any(a < e and s < b for a, b in spans)


def _misread_spans(text, phon, words, tokens):
    """IME の逆変換の読みが、同じ所の辞書の読み（解析の語の読みをつないだもの）と食い違う IME の語の範囲 → [(s, e)]。
    辞書の語の切れ目が IME の語の端と揃い、どの語も読みを持つ所だけ比べる（揃わない所は比べない）。
    IME が辞書の1語を2つ以上に切ったとき（浅｜煎り）は、続く IME の語をつないで揃う所で比べる（2026-10-31）。"""
    out = []
    for i in range(len(words)):
        for k in range(1, MAX_WORDS + 1):
            w = words[i:i + k]
            if len(w) < k:
                break
            s, e, rs, re_ = w[0][0], w[-1][1], w[0][2], w[-1][3]
            inside = [t for t in tokens if t.start < e and s < t.end]
            if not inside or inside[0].start != s:
                break
            if inside[-1].end != e:
                continue                     # 辞書の語の途中で切れている: 次の IME の語までつなぐ
            if not _strong(text[s:e]):
                break
            if not all(getattr(t, 'has_reading', True) and t.reading for t in inside):
                break
            # 辞書の読みが確かな所だけ: 送りがなの在る語（浅煎り）か、辞書の1語の漢字の並び。漢字1字ずつに切れた並び
            # （打ち違いで出来た珍しい字の組）は字ごとの読みが当てにならないので比べない
            if not (any('ぁ' <= c <= 'ゖ' for c in text[s:e]) or len(inside) == 1):
                break
            mine = _hira(''.join(t.reading for t in inside))
            if mine != _hira(phon[rs:re_]):
                out.append((s, e))
            break
    return out


def repair_line(line, result, input_method='kana', decided=()):
    out = _repair_line_ime(line, result, input_method, decided)
    # 巻き込みの1打で崩れた名詞の句（でんなきだい→電気代）は別の段（rollin_word・2026-11-08）。かな入力だけ
    if input_method == 'kana' and os.environ.get('CN_ROLLIN_WORD') != '0':
        try:
            import rollin_word
            out = rollin_word.repair_line(line, out, decided)
        except Exception:
            pass
    # かなの切れ端を語に戻す段（食事｜けん の紫 → 食事券・たふせ → タブ: kana_piece_word・2026-11-08 手分けA）
    if os.environ.get('CN_KANA_PIECE_WORD') != '0':
        try:
            import kana_piece_word
            out = kana_piece_word.repair_line(line, out, input_method, decided)
        except Exception:
            pass
    # 名詞＋です を IME が片仮名の1語にした所（怪盗アンデス → 回答案です: kata_copula・2026-11-08 手分けA）
    if os.environ.get('CN_KATA_COPULA') != '0':
        try:
            import kata_copula
            out = kata_copula.repair_line(line, out, decided)
        except Exception:
            pass
    # 1打違いの読みを IME が漢字の名詞2つにした所（野外｜文章 → 長い文章: compound_key_alt・2026-11-09 手分けA）
    if os.environ.get('CN_COMPOUND_KEY_ALT') != '0':
        try:
            import compound_key_alt
            out = compound_key_alt.repair_line(line, out, decided)
        except Exception:
            pass
    # 名詞＋の＋形容詞 で文が終わる所を同じ読みの名詞の選び違いとして見る（私の｜重い → 思い: gen_adj_noun・2026-11-09 手分けA）
    if os.environ.get('CN_GEN_ADJ_NOUN') != '0':
        try:
            import gen_adj_noun
            out = gen_adj_noun.repair_line(line, out, decided)
        except Exception:
            pass
    # 片仮名の名詞＋化＋片仮名の名詞 は並べる か の選び違いかもしれないので紫（クリック化ドラッグ: kata_ka_parallel・2026-11-09 手分けA）
    if os.environ.get('CN_KATA_KA_PARALLEL') != '0':
        try:
            import kata_ka_parallel
            out = kata_ka_parallel.repair_line(line, out, decided)
        except Exception:
            pass
    # 副助詞＋の＋用言 の の を隣のキーの格助詞の打ち違いとして見る（などのした → などにした: no_particle_slip・2026-11-09 手分けA）
    if os.environ.get('CN_NO_PARTICLE_SLIP') != '0':
        try:
            import no_particle_slip
            out = no_particle_slip.repair_line(line, out, input_method, decided)
        except Exception:
            pass
    # 漢字の語の読みの最後の字と助詞が入れ替わり、片仮名の語の頭が欠けた所（右田｜で｜ブル… → 右｜で｜ダブル…:
    # kata_head_swap・2026-11-09 手分けA）
    if os.environ.get('CN_KATA_HEAD_SWAP') != '0':
        try:
            import kata_head_swap
            out = kata_head_swap.repair_line(line, out, decided)
        except Exception:
            pass
    return out


# IME の逆変換の読み（行ごと・最後の数行だけ）。後ろの段（odd_respell の紫の読み直し）が、打った記録の無い行で
# 解析の読み（二言 を に＋こと）の代わりに使う（2026-11-09 手分けA: 伝え二言で）。CN_IME_REVERSE_READING=0 で使わない
_IME_REVERSE = {}
_IME_REVERSE_MAX = 64


def _remember_ime_reverse(text, ime):
    if os.environ.get('CN_IME_REVERSE_READING') == '0' or not text:
        return
    try:
        rw = ime.reverse_words(text)
    except Exception:
        rw = None
    if not rw:
        return
    if len(_IME_REVERSE) >= _IME_REVERSE_MAX:
        _IME_REVERSE.clear()
    _IME_REVERSE[text] = rw


def ime_reverse_reading(text, a, b):
    """text[a:b] の IME の逆変換の読み（ひらがな）。IME の語の端が a・b に揃うときだけ。無ければ None。"""
    if os.environ.get('CN_IME_REVERSE_READING') == '0':
        return None
    rw = _IME_REVERSE.get(text)
    if not rw:
        return None
    phon, words = rw
    inside = [w for w in words if a <= w[0] and w[1] <= b]
    if not inside or inside[0][0] != a or inside[-1][1] != b:
        return None
    r = _hira(phon[inside[0][2]:inside[-1][3]])
    return r if r and all('ぁ' <= c <= 'ゖ' or c == 'ー' for c in r) else None


def _undo_broken_head_fix(line, result):
    """入口の直しが、行頭の接尾の語の崩れた所（的｜買い）を、解析の読み（てきかい）から別の語（行き交い）に直していて、
    その所の IME の逆変換の読み（まとがい）が解析の読みと違うなら、その直しは読み違いからの直し。戻して紫にする
    （後ろの紫の読み直しが IME の読みで見直す）。2026-11-09 手分けA（PC の 的買い → 行き交い → 戻して紫だけ）。
    CN_RECONVERT_UNDO_HEAD=0 で前のまま。"""
    if os.environ.get('CN_RECONVERT_UNDO_HEAD') == '0' or not isinstance(result, dict):
        return result
    done = result.get('corrected') or line
    if done == line:
        return result
    try:
        from morphology import tokenize
        toks = list(tokenize(line))
    except Exception:
        return result
    heads = []
    for s, e, _f in _head_suffix_marks(line, toks):
        ime_r = ime_reverse_reading(line, s, e)
        inside = [t for t in toks if s <= t.start and t.end <= e]
        if not ime_r or not inside or not all(t.has_reading and t.reading for t in inside):
            continue
        if _hira(''.join(t.reading for t in inside)) != ime_r:
            heads.append((s, e))
    if not heads:
        return result
    ops = difflib.SequenceMatcher(None, line, done, autojunk=False).get_opcodes()
    bad = [o for o in ops if o[0] != 'equal' and any(o[1] < e and s < max(o[2], o[1] + 1) for s, e in heads)]
    if not bad:
        return result
    parts = [line[i1:i2] if (tag == 'equal' or (tag, i1, i2, j1, j2) in bad) else done[j1:j2]
             for tag, i1, i2, j1, j2 in ops]
    new = ''.join(parts)
    out = dict(result)
    ops2 = [o for o in difflib.SequenceMatcher(None, line, new, autojunk=False).get_opcodes() if o[0] != 'equal']
    out.update({'corrected': new, 'changed': bool(ops2), 'spans': [[o[3], o[4]] for o in ops2],
                'original_spans': [[o[1], o[2]] for o in ops2],
                'details': [d for d in (result.get('details') or []) if len(d) > 1 and d[1] and d[1] in new]})
    odd = [tuple(x[:2]) for x in (result.get('odd_spans') or ()) if not any(x[0] < e and s < x[1] for s, e in heads)]
    out['odd_spans'] = sorted(set(odd) | set(heads))
    out['odd_reasons'] = [r for r in (result.get('odd_reasons') or ()) if not any(r[0] < e and s < r[1] for s, e in heads)] + [
        (s, e, f'「{line[s:e]}」は変換が崩れた所かもしれません（付く先の無い接尾の語）') for s, e in heads]
    return out


def _repair_line_ime(line, result, input_method='kana', decided=()):
    if not isinstance(result, dict):
        return result
    done = result.get('corrected') or line
    typed = _env_on('CN_RECONVERT_TYPED')
    try:
        try:
            from ime_language import JapaneseIME
            session = JapaneseIME()
        except Exception:
            session = None
        if session is None:
            marks = propose(done, input_method, None) if typed else []
        else:
            with session as ime:
                if ime.available:
                    _remember_ime_reverse(done, ime)
                    if line != done:
                        # 前の段が直す前の行の読みも（_fix_lone_kanji_join が直しを戻すか決めるときに使う）
                        _remember_ime_reverse(line, ime)
                if not ime.available and not typed:
                    return result
                if ime.available and line != done:
                    result = _undo_broken_head_fix(line, result)
                    done = result.get('corrected') or line
                marks = propose(done, input_method, ime if ime.available else None)
    except Exception:
        return result
    if not marks:
        return result
    changed = [(o[3], o[4]) for o in difflib.SequenceMatcher(None, line, done, autojunk=False).get_opcodes()
               if o[0] != 'equal']
    odd_now = [tuple(x[:2]) for x in list(result.get('odd_spans') or ()) + list(result.get('unsure_spans') or ())]
    new = done
    odd_add, details = [], []
    # 直しは行ごとの置き換えなので、最初の1つだけ（ほかは紫）
    fixed = None
    for s, e, other in marks:
        if any(x < e and s < y for x, y in changed):
            continue
        org = None
        for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, done, line, autojunk=False).get_opcodes():
            if tag == 'equal' and i1 <= s and e <= i2:
                org = (s - i1 + j1, e - i1 + j1)
        if org is None or any(x < org[1] and org[0] < y for x, y in list(decided or ())):
            continue
        if other and not fixed:
            ops = [o for o in difflib.SequenceMatcher(None, done, other, autojunk=False).get_opcodes() if o[0] != 'equal']
            new = done[:ops[0][1]] + other[ops[0][3]:ops[-1][4]] + done[ops[-1][2]:]
            details.append([done[ops[0][1]:ops[-1][2]], other[ops[0][3]:ops[-1][4]], 'IMEの選び違い'])
            fixed = org
        elif not any(x < org[1] and org[0] < y for x, y in odd_now):
            odd_add.append(org)
    if not odd_add and new == done:
        return result
    out = dict(result)
    if fixed:
        # 直した所に前の段が付けた紫は外す
        out['odd_spans'] = [x for x in (result.get('odd_spans') or ()) if not (x[0] < fixed[1] and fixed[0] < x[1])]
        out['odd_reasons'] = [r for r in (result.get('odd_reasons') or ())
                              if not (r[0] < fixed[1] and fixed[0] < r[1])]
        if result.get('unsure_spans'):
            out['unsure_spans'] = [x for x in result['unsure_spans'] if not (x[0] < fixed[1] and fixed[0] < x[1])]
    if odd_add:
        out['odd_spans'] = sorted(set(tuple(x[:2]) for x in (out.get('odd_spans') or ())) | set(odd_add))
        out['odd_reasons'] = list(out.get('odd_reasons') or ()) + [
            (a, b, f'「{line[a:b]}」はあまり使わない語です。同じ読みか1打違いの読みで変換し直すと、より自然な文になります')
            for a, b in odd_add]
    if new != done:
        ops = [o for o in difflib.SequenceMatcher(None, line, new, autojunk=False).get_opcodes() if o[0] != 'equal']
        out.update({'original': line, 'corrected': new, 'changed': True,
                    'details': list(result.get('details') or []) + details,
                    'spans': [[o[3], o[4]] for o in ops], 'original_spans': [[o[1], o[2]] for o in ops]})
    return out


# ------------------------------------------------------------
# 読み直した語の表記は IME に任せる（2026-11-04・うにの画面: 打ち違いを読み直した所が 下さい のように
# 元の IME の漢字の一部を残した表記になる）。読み直しは読みを替えるので、元の IME の変換は替えた読みには当たらない。
# 替えた読みを含む句を IME で変換し直し、読み直した語の所だけ IME の表記にする（句のほかの所は替えない）。
# IME の無い環境（雲）では何もしない。かなのまま打った所（元がかなだけ）は kana_keep.wago_kana_respell の受け持ち。
# ------------------------------------------------------------
_CLAUSE_STOP = frozenset('、。，．,.!?！？\t 　「」『』（）()【】・\n')


def _clause(text, a, b):
    s, e = a, b
    while s > 0 and text[s - 1] not in _CLAUSE_STOP:
        s -= 1
    while e < len(text) and text[e] not in _CLAUSE_STOP:
        e += 1
    return s, e


def ime_face(before, fixed, ime=None):
    """before: 読み直す前の行、fixed: 読み直した行。読み直した所の表記を IME の最初の変換にした行（替えなければ fixed）。"""
    import os
    if os.environ.get('CN_RESPELL_IME_FACE') == '0' or not fixed or fixed == before:
        return fixed
    if ime is None:
        try:
            from ime_language import JapaneseIME
            with JapaneseIME() as got:
                if not got.available:
                    return fixed
                return ime_face(before, fixed, got)
        except Exception:
            return fixed
    from morphology import tokenize
    ops = [o for o in difflib.SequenceMatcher(None, before, fixed, autojunk=False).get_opcodes() if o[0] != 'equal']
    if not ops:
        return fixed
    toks = list(tokenize(fixed))
    out = fixed
    # 後ろの所から（前の位置がずれない）
    for tag, i1, i2, j1, j2 in sorted(ops, key=lambda o: o[3], reverse=True):
        src = before[i1:i2]
        # 元が IME の変換（漢字・片仮名を含む）だった所だけ。読みを替えない直し（漢字の選び直し）は見ない
        if not any(_kanji(c) or _katakana(c) for c in src):
            continue
        cover = [t for t in toks if t.end > j1 and t.start < max(j2, j1 + 1)]
        if not cover:
            continue
        ws, we = min(t.start for t in cover), max(t.end for t in cover)
        cs, ce = _clause(out, ws, we)
        piece = out[cs:ce]
        try:
            rd = ime.phonetic(piece)
            conv = ime.convert(_hira(rd)) if rd else None
        except Exception:
            conv = None
        if not conv or conv == piece:
            continue
        # IME の読みが辞書の読みと食い違う句（節女辞書 を せつおんなじしょ と読む）は、IME の変換も当てにならない
        try:
            import kana_keep as _kk
            if _kk._reading(piece) != _hira(rd):
                continue
        except Exception:
            continue
        a, b = ws - cs, we - cs
        # 句のほかの所は替えない: 変わった所が読み直した語の範囲に収まるときだけ採る
        diff = [o for o in difflib.SequenceMatcher(None, piece, conv, autojunk=False).get_opcodes() if o[0] != 'equal']
        touch = [o for o in diff if o[1] < b and a < max(o[2], o[1] + 1)]
        inside = [o for o in touch if a <= o[1] and o[2] <= b]
        if not inside or len(inside) != len(touch):
            continue
        # 片仮名の語を新しく持ち込む・かなの切れ端を残す変換は採らない（節おんなじショー の型・2026-11-04 Store の測り）
        if any(any(_katakana(c) for c in conv[o[3]:o[4]]) and not any(_katakana(c) for c in piece[o[1]:o[2]])
               for o in inside) or _kana_scraps(piece, conv):
            continue
        new_piece = piece
        for o in sorted(inside, key=lambda o: o[1], reverse=True):
            new_piece = new_piece[:o[1]] + conv[o[3]:o[4]] + new_piece[o[2]:]
        # 替えた表記が同じ読みであること（IME の読みで確かめる）
        try:
            if _hira(ime.phonetic(new_piece) or '') != _hira(rd):
                continue
        except Exception:
            continue
        out = out[:cs] + new_piece + out[ce:]
        toks = list(tokenize(out))
    return out


# ------------------------------------------------------------
# 行の打鍵の読みを1打ずつ戻して IME で変換し直す（line_key_repair・2026-11-04）
# ローマ字入力で、どの段も判定を立てない行（紫も直しも無い・確定の字は語に読める）が多い（Store の測り: 1か所の
# 打ち違いのかなだけの行の約4割）。打った読み（確定の記録）を打鍵に戻し、1打の入れ替え・隣のキー・巻き込みで
# 戻した読みを格子で安い順に LINE_TOP だけ IME で変換し、行の費用（path_cost）がはっきり下がり、替わる所が狭く、
# 珍しい語が身近な語に替わる形を採る。PC の IME の測り（作った文の打鍵 179 行・正しい 58 行）で、正しい行は
# 1行も替えず、元の文に戻ったのは 25 行増えた。IME の無い環境・打鍵の記録の無い行では何もしない。
# ------------------------------------------------------------
LINE_TOP = 40
LINE_GAIN = 3000
LINE_SPAN = 6
LINE_OPS = 2
LINE_JUMP = 150
LINE_COMMON = 470
LINE_CHAR_COST = 1100   # 1字あたりの費用がこれ未満の行は見ない（測り: 正しい58行の約6割を外す。950 では正しい行の待ちが中央 0.5→3.1 秒・処理の負荷を重く見る）
_NUM = frozenset('一二三四五六七八九十')


def _line_change(real, conv):
    from morphology import tokenize
    ops = [o for o in difflib.SequenceMatcher(None, real, conv, autojunk=False).get_opcodes() if o[0] != 'equal']
    if not ops:
        return None
    i1, i2, j1, j2 = ops[0][1], ops[-1][2], ops[0][3], ops[-1][4]
    tr, tc = list(tokenize(real)), list(tokenize(conv))
    rr = max([_token_rarity(t, tr) for t in tr if t.start < max(i2, i1 + 1) and i1 < t.end] + [0])
    rc = max([_token_rarity(t, tc) for t in tc if t.start < max(j2, j1 + 1) and j1 < t.end] + [0])
    return ops, i2 - i1, rr, rc, tc


def _line_conv_ok(real, conv, ops, tc):
    import re
    if _kana_scraps(real, conv) or _key_fix_overreach(real, conv):
        return False
    small = '[ぁぃぅぇぉゃゅょゎ]'
    if len(re.findall(small, conv)) > len(re.findall(small, real)):
        return False
    if re.search('[一-鿿]っ', conv) and not re.search('[一-鿿]っ', real):
        return False
    toks = [t for t in tc if t.surface.strip()]
    if toks and toks[0].pos in ('助詞', '助動詞'):
        return False
    if any(not t.has_reading for t in toks):
        return False
    for o in ops:
        if any(c in _NUM for c in conv[o[3]:o[4]]) and not any(c in _NUM for c in real[o[1]:o[2]]):
            return False
    if os.environ.get('CN_LINE_KEY_NO_SYMBOL') != '0':
        # 打ち違いの1打の戻しで、元に無い記号・括弧（友達都映画 → 友達）と映画）を入れる形は採らない。かなの1打は
        # 記号にならない（2026-11-06 挙動関連担当のアプリの道の試し: 正しく打った行を崩した）。CN_LINE_KEY_NO_SYMBOL=0
        import unicodedata
        def _sym(t):
            # 括弧・記号（）「」＋＝ など）だけを見る。句読点・長音（。、！？ー）は打った行にもよく出る
            return {c for c in t if (unicodedata.category(c) in ('Ps', 'Pe', 'Pi', 'Pf') or unicodedata.category(c)[0] == 'S')
                    and c not in 'ー〜～'}
        for o in ops:
            if _sym(conv[o[3]:o[4]]) - _sym(real[o[1]:o[2]]):
                return False
    return True


def _line_key_candidates(reading):
    try:
        import romaji_repair
        import romaji_swap_repair
        import reading_lattice
    except Exception:
        return []
    seen = []
    for spelled in romaji_swap_repair._spellings(reading, limit=2):
        try:
            found = romaji_repair.one_key_readings(spelled)
        except Exception:
            continue
        for row in getattr(found, 'candidates', ()):
            if row[0] and row[0] != reading and row[0] not in seen:
                seen.append(row[0])
    ranked = []
    for v in seen:
        try:
            b = reading_lattice.best(v)
        except Exception:
            continue
        if b is not None and b.surface:
            ranked.append((b.cost, v))
    return [v for _c, v in sorted(ranked)[:LINE_TOP]]


def line_key_propose(line, reading, ime):
    """1打の戻しで直した行（無ければ None）。"""
    from morphology import path_cost
    here = path_cost(line)
    if here is None:
        return None
    got = []
    for v in _line_key_candidates(reading):
        try:
            conv = ime.convert(v)
        except Exception:
            conv = None
        if not conv or conv == line:
            continue
        pc = path_cost(conv)
        if pc is not None and here - pc >= LINE_GAIN:
            got.append((pc, conv))
    for pc, conv in sorted(got):
        ch = _line_change(line, conv)
        if ch is None:
            continue
        ops, span, rr, rc, tc = ch
        if span > LINE_SPAN or len(ops) > LINE_OPS or rr - rc < LINE_JUMP or rc > LINE_COMMON:
            continue
        if not _line_conv_ok(line, conv, ops, tc):
            continue
        return conv
    return None


def line_key_repair(line, result, input_method='kana', decided=(), check=None):
    if (os.environ.get('CN_LINE_KEY_REPAIR') == '0' or input_method != 'romaji' or not isinstance(result, dict)
            or (result.get('corrected') or line) != line or not _strong(line) or len(line) > 80):
        return result
    try:
        import kanji_guess
        reads = [r for r in kanji_guess.ime_readings_for(line) if r and all(_hira(c) == c for c in r)]
    except Exception:
        return result
    if not reads:
        return result
    # 1字あたりの行の費用が低い行（正しい行の多く）は IME を呼ばない（正しい行の待ちが 0.1→3.7 秒になった）
    try:
        from morphology import path_cost
        c = path_cost(line)
    except Exception:
        return result
    if c is None or c < LINE_CHAR_COST * len(line):
        return result
    try:
        from ime_language import JapaneseIME
        with JapaneseIME() as ime:
            if not ime.available:
                return result
            fixed = line_key_propose(line, _hira(reads[0]), ime)
    except Exception:
        return result
    if not fixed:
        return result
    # 直した行を補正し直して、紫が付く・まだ直しが入る行は採らない（紫だった行を 説明辞書・会議のシアン化 の
    # ような別の文にした: Store の測り batch131）。直した行が落ち着く形だけ採る
    if check is not None and os.environ.get('CN_LINE_KEY_CHECK') != '0':
        try:
            again = check(fixed)
        except Exception:
            return result
        if not isinstance(again, dict) or (again.get('corrected') or fixed) != fixed or again.get('odd_spans'):
            return result
    ops = [o for o in difflib.SequenceMatcher(None, line, fixed, autojunk=False).get_opcodes() if o[0] != 'equal']
    if not ops or any(x < max(o[2], o[1] + 1) and o[1] < y for o in ops for x, y in (decided or ())):
        return result
    near = [(o[1], max(o[2], o[1] + 1)) for o in ops]
    out = dict(result)
    out.update({'original': line, 'corrected': fixed, 'changed': True,
                'details': list(result.get('details') or []) + [[line[ops[0][1]:ops[-1][2]], fixed[ops[0][3]:ops[-1][4]], 'IMEの1打の戻し']],
                'spans': [[o[3], o[4]] for o in ops], 'original_spans': [[o[1], o[2]] for o in ops]})
    for key in ('odd_spans', 'unsure_spans'):
        if result.get(key):
            out[key] = [sp for sp in result[key] if not any(x < sp[1] and sp[0] < y for x, y in near)]
    if result.get('odd_reasons'):
        out['odd_reasons'] = [r for r in result['odd_reasons'] if not any(x < r[1] and r[0] < y for x, y in near)]
    return out
