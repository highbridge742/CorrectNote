# -*- coding: utf-8 -*-
"""かな入力の1キーの打ち違いで崩れた語の並びを、打鍵の単位で戻す段（keyslip_window・2026-11-08 手分けB）。

かな入力では、濁音は 清音のキー＋゛のキー、小書きは Shift＋同じキー で打つ。1キーの打ち違い（隣のキー）や
巻き込み（隣のキーも一緒に押した1打）は、字の単位ではなく **キーの単位** で起きる:

- へんじ（へ｜ん｜し｜゛）の し を隣の と と打つ → へんど（変度）。字で見ると じ→ど の2つの違いに見える。
- これから の か を打つとき隣の に も押す → これかにら（これカニら）。
- がいとうの の う の隣の あ も押す → がいとうあの。

IME はその読みを変換できず、1字の漢字の語を並べた珍しい語（変｜度・下｜場合）や、かなの切れ端（が｜いとう｜あの）、
語にならない並び（これ｜カニ｜ら）にする。

崩れの疑える所（窓）:
1. 名詞の並び（名詞・接頭詞）が1語として表に無く（seed_japanese.is_unit が False）、珍しい（wordfreq の段 RARE 以上）。
3. ひらがなの並び（4字以上）が1字の内容の語の切れ端（い・れ）を含むとき。
窓の前後の助詞1つまでを窓に入れた形も試す（の｜下場合 → に｜した場合）。

窓の読み（打った記録が在ればそれ、無ければ辞書の読み）をキーの並びにして、1キーの置き換え（隣のキー・同じ指の
上下、kana_layout.kana_key_distance）か、隣のキーと一緒に押した余分な1打の抜き（intrusion_key_distance）を1つ、
それに加えて Shift だけの違い（や／ゃ）を1つまで戻す。戻した読みを格子（reading_lattice）で語に組み、どの内容の語も
身近（COMMON 以下）で、行の費用（path_cost）がはっきり下がる（GAIN 以上）ものを候補にする。
候補は 行の費用＋身近さ＋戻した打鍵の数 で比べ、2番目との差が FIX_MARGIN 以上なら直し、足りなければ紫。
特定の語や文字列には合わせない。

切り替え: CN_KEYSLIP_WINDOW=0 で何もしない（前のまま）。かな入力だけ（ローマ字入力は別の段）。
"""
import difflib
import os
from functools import lru_cache

RARE = 560          # 名詞の並びがこれ以上珍しい（表に無い並びは 800）とき疑う
COMMON = 530        # 戻した先の内容の語の身近さ（これ以下）
GAIN = 3000         # 行の費用がこれだけ下がれば候補（切り方の揺れより大きく）
FIX_MARGIN = 800    # 2番目の候補（別の表記）との差がこれ以上なら直す
RANK_W = 15         # 比べるときの身近さの重み（行の費用＋重み×段の和）
EDIT_W = 1500       # 戻した打鍵1つあたりの重み（Shift だけの違いは半分）
SUB_NEAR = 1.05     # 置き換え: 隣のキー・同じ指の上下（kana_key_distance）
DROP_NEAR = 1.0     # 抜き: 前後どちらかのキーの隣（intrusion_key_distance）
SHIFT_D = 0.3       # 同じキーの Shift の違い（kana_key_distance が 0.3 を返す）
TOP = 10            # 格子で組めた読みのうち、費用の安い順に表記を比べる数
MAX_WINDOW = 12     # 窓の読みの字数の上限
MAX_WEAK = 24       # かなだけの並び（抜きだけ試す）の字数の上限
MIN_READ = 3        # 窓の読みの字数の下限
MAX_READINGS = 8    # 窓の読みの組の上限

DEBUG = None
_PARTICLE = ('助詞',)
_CONTENT = ('名詞', '動詞', '形容詞', '副詞', '連体詞', '形容動詞')


def _on():
    return os.environ.get('CN_KEYSLIP_WINDOW') != '0'


def _kanji(c):
    return '一' <= c <= '鿿' or c == '々'


def _kata(c):
    return 'ァ' <= c <= 'ヶ'


def _hira_char(c):
    return 'ぁ' <= c <= 'ゖ' or c == 'ー'


def _hira(s):
    return ''.join(chr(ord(c) - 0x60) if 'ァ' <= c <= 'ヶ' else c for c in s)


def _is_hira(s):
    return bool(s) and all(_hira_char(c) for c in s)


def _strong(s):
    return any(_kanji(c) or _kata(c) for c in s)


def _rank(face):
    try:
        import ime_reconvert
        return ime_reconvert._rank(face)
    except Exception:
        return 800


@lru_cache(maxsize=4096)
def _unit(face):
    try:
        import seed_japanese
        return seed_japanese.is_unit(face)
    except Exception:
        return None


# ---- キーの並び ----

@lru_cache(maxsize=1)
def _compose_table():
    import kana_layout as KL
    out = {}
    for voiced in KL.DAKUTEN_BASE:
        ks = KL.keystrokes(voiced)
        if len(ks) == 2:
            out[ks] = voiced
    return out


def _compose_marks(reading):
    """打った記録の読みで、字の後ろに離れて残った ゛゜ を前の字に付ける（へんと゛ → へんど）。付かない字の後ろはそのまま。"""
    if '゛' not in reading and '゜' not in reading:
        return reading
    table = _compose_table()
    out = []
    for c in reading:
        if c in '゛゜' and out and (out[-1], c) in table:
            out[-1] = table[(out[-1], c)]
        else:
            out.append(c)
    return ''.join(out)


def _groups(reading):
    """読み → 字ごとのキーの並び [(キー, ...), ...]。"""
    import kana_layout as KL
    return [tuple(KL.keystrokes(c)) for c in reading]


def _compose(groups):
    table = _compose_table()
    out = []
    for g in groups:
        if not g:
            continue
        if (len(g) == 1 and g[0] in '゛゜' and out and (out[-1], g[0]) in table
                and os.environ.get('CN_KEYSLIP_MARK_KEY') != '0'):
            # 字のキーの代わりに ゛゜ のキーを打った形に戻すと、前の字に付く（はしせめる の せ → ゛ で はじめる・
            # 2026-11-08 補正担当）。CN_KEYSLIP_MARK_KEY=0 で前のまま
            out[-1] = table[(out[-1], g[0])]
        elif len(g) == 1:
            out.append(g[0])
        else:
            out.append(table.get(tuple(g)) or ''.join(g))
    return ''.join(out)


@lru_cache(maxsize=1)
def _alphabet():
    import kana_layout as KL
    return tuple(c for c in KL.KANA_POSITIONS if _hira_char(c) or c in '゛゜')


@lru_cache(maxsize=512)
def _subs(key):
    """key の代わりに打たれうるキー [(キー, 重み)]（隣のキー 1・同じキーの Shift 0.5）。"""
    import kana_layout as KL
    out = []
    for c in _alphabet():
        if c == key:
            continue
        try:
            d = KL.kana_key_distance(key, c)
        except Exception:
            continue
        if d <= SHIFT_D + 1e-9:
            out.append((c, 0.5))
        elif d <= SUB_NEAR + 1e-9:
            out.append((c, 1.0))
    return tuple(out)


def _near_drop(key, other):
    import kana_layout as KL
    if key == other:
        return False                 # 同じ字の2度押しは別の型（まとめない）
    try:
        return KL.intrusion_key_distance(key, other) <= DROP_NEAR + 1e-9
    except Exception:
        return False


def _flat(groups):
    return [(gi, ki, k) for gi, g in enumerate(groups) for ki, k in enumerate(g)]


def _edits1(groups, solo=frozenset()):
    """1キーの戻し [(新しい groups, 重み)]。solo: 1字だけの語の字（その字を抜くと語が丸ごと消えるので抜かない）。"""
    out = []
    flat = _flat(groups)
    for n, (gi, ki, k) in enumerate(flat):
        # 置き換え
        for c, w in _subs(k):
            g = list(groups[gi])
            g[ki] = c
            if ki > 0 and len(g) == 2 and c not in '゛゜':
                continue                 # 濁点のキーの所に字のキー（後ろの別の字）は置き換えでは作らない
            ng = list(groups)
            ng[gi] = tuple(g)
            out.append((ng, w))
        # 抜き（隣のキーの巻き込み）。読みの頭のキーは抜かない
        if n == 0:
            continue
        nb = [flat[m][2] for m in (n - 1, n + 1) if 0 <= m < len(flat)]
        if any(_near_drop(k, o) for o in nb) and not (gi in solo and len(groups[gi]) == 1):
            g = list(groups[gi])
            del g[ki]
            if g and g[0] in '゛゜' and len(g) == 1 and ki == 0:
                continue
            ng = list(groups)
            ng[gi] = tuple(g)
            out.append((ng, 1.0))
    return out


def _variants(reading, drops_only=False, solo=frozenset(), long=False):
    """1キー（＋Shift だけの違い1つ）を戻した読み {読み: 重み}。"""
    if not reading or len(reading) > (MAX_WEAK if (drops_only or long) else MAX_WINDOW) or not all(_hira_char(c) or c in '゛゜' for c in reading):
        return {}
    base = _groups(reading)
    out = {}
    nkeys = sum(len(g) for g in base)
    for g1, w1 in _edits1(base, solo):
        if drops_only:
            # 根拠の弱い所（ひらがなだけの行）は、巻き込みの1打の抜きだけ
            if sum(len(g) for g in g1) < nkeys and sum(g.count('゛') + g.count('゜') for g in g1) == sum(
                    g.count('゛') + g.count('゜') for g in base):
                r1 = _compose(g1)
                if r1 and r1 != reading:
                    out[r1] = min(out.get(r1, 9), w1)
            continue
        r1 = _compose(g1)
        if r1 and r1 != reading:
            out[r1] = min(out.get(r1, 9), w1)
        if w1 >= 1.0:
            # 2つ目は Shift だけの違い（ちやくしゃ → ちゃくしゅ: や の Shift 忘れ＋ゃ と ゅ の隣）
            for g2, w2 in _edits1(g1):
                if w2 < 1.0:
                    r2 = _compose(g2)
                    if r2 and r2 != reading:
                        out[r2] = min(out.get(r2, 9), w1 + w2)
        else:
            for g2, w2 in _edits1(g1, solo):
                if w2 >= 1.0:
                    r2 = _compose(g2)
                    if r2 and r2 != reading:
                        out[r2] = min(out.get(r2, 9), w1 + w2)
    out.pop(reading, None)
    return out


# ---- 窓 ----

def _token_readings(text, tokens, i, j):
    """tokens[i:j] の読みの候補 [(読み, 1字だけの語の字の位置)]（打った記録が在ればそれだけ）。"""
    s, e = tokens[i].start, tokens[j - 1].end
    surf = text[s:e]
    if _is_hira(surf) or all(_hira_char(c) or c in '゛゜' for c in surf):
        return [(surf, frozenset(t.start - s for t in tokens[i:j] if len(t.surface) == 1))]
    out = [('', frozenset())]
    # 数の字の音・訓をみな見るのは、数でない語がどれも漢字の語（貸す｜九｜人）のときだけ（ミウ｜一 の片仮名の切れ端は別の崩れ方）
    num = (any(t.surface in NUM_CHARS for t in tokens[i:j])
           and all(t.surface in NUM_CHARS or (t.pos == '名詞' and (t.pos_sub or '').startswith('接尾'))
                   or any(_kanji(c) and c not in NUM_CHARS for c in t.surface) for t in tokens[i:j]))
    k = i
    while k < j:
        # 打った記録の在る一番長い並び（変｜度 → へんど）を先に
        got = None
        inner = frozenset()
        for m in range(j, k + 1, -1):
            rec = _record(text, tokens[k].start, tokens[m - 1].end)
            if rec:
                got, k2 = [rec], m
                inner = _solo_in_record(text, tokens[k:m], _compose_marks(rec))
                break
        if got is None:
            got, k2 = _one_token_readings(text, tokens[k], num), k + 1
        if not got:
            return []
        got = [_compose_marks(b) for b in got]
        out = [(a + b, sa | ({len(a)} if len(b) == 1 else frozenset()) | {len(a) + x for x in inner})
               for a, sa in out for b in got][:MAX_READINGS]
        k = k2
    return out


def _solo_in_record(text, toks, rec):
    """打った記録が語の並びをまたぐとき（朝氏 → あさし）、記録が各語の読みをつないだ形なら、読みが1字の語（氏＝し・
    背＝せ）の位置。その字を抜くと語が丸ごと消える（IME がその字を1語にした）ので、巻き込みの抜きとはみない
    （2026-11-08 補正担当の束: 朝氏はやめに → 朝はやめに・的背を → 的を）。
    ただし巻き込んだかなを IME が1字の漢字にする形（駅派・台風柄・契約身）のほうが多く、それを直せなくなったので
    既定では使わない（CN_KEYSLIP_SOLO_REC=1 で使う）。"""
    if os.environ.get('CN_KEYSLIP_SOLO_REC') != '1' or len(toks) < 2:
        return frozenset()
    pos, out = 0, set()
    for t in toks:
        rs = [_compose_marks(r) for r in _one_token_readings_dict(t)]
        r = next((r for r in rs if rec.startswith(r, pos)), None)
        if r is None:
            return frozenset()
        if len(r) == 1:
            out.add(pos)
        pos += len(r)
    return frozenset(out) if pos == len(rec) else frozenset()


def _one_token_readings_dict(t):
    surf = t.surface
    if all(_hira_char(c) or c in '゛゜' for c in surf):
        return [surf]
    if all(_kata(c) or c == 'ー' for c in surf):
        return [_hira(surf)]
    out = []
    base = _hira(t.reading or '')
    if _is_hira(base):
        out.append(base)
    try:
        from inflected_lexicon import dictionary_readings
        out.extend(_hira(r) for r in dictionary_readings(surf) or ())
    except Exception:
        pass
    return list(dict.fromkeys(r for r in out if _is_hira(r)))


def _record(text, s, e):
    try:
        import ime_reconvert
        return ime_reconvert._record_reading(text, s, e, ime_reconvert._active_record())
    except Exception:
        return None


def _one_token_readings(text, t, num=False):
    surf = t.surface
    if all(_hira_char(c) or c in '゛゜' for c in surf):
        return [surf]
    if all(_kata(c) or c == 'ー' for c in surf):
        return [_hira(surf)]
    rec = _record(text, t.start, t.end)
    if rec:
        return [rec]
    out = []
    base = _hira(t.reading or '')
    if _is_hira(base):
        out.append(base)
    try:
        from inflected_lexicon import dictionary_readings
        out.extend(_hira(r) for r in dictionary_readings(surf) or ())
    except Exception:
        pass
    if num and len(surf) == 1 and surf in NUM_CHARS and os.environ.get('CN_KEYSLIP_NUM_READ') != '0':
        # 数の漢字1字は読みが幾つも在り（九＝きゅう・く、四＝し・よん）、IME はどの読みからも出す。
        # 打った記録が無いときは音・訓の読みもみな見る（2026-11-08 手分けB v11）。CN_KEYSLIP_NUM_READ=0 で前のまま
        try:
            import kanji_onkun
            out.extend(_hira(r) for r in kanji_onkun.readings_of(surf) or ())
        except Exception:
            pass
        return list(dict.fromkeys(r for r in out if _is_hira(r)))[:6]
    return list(dict.fromkeys(r for r in out if _is_hira(r)))[:4]


def _is_nounish(t):
    """名詞の並びに入れる語: 漢字・片仮名の名詞と接頭詞（代名詞 何・私 は別の語として切る）。"""
    return (t.pos in ('名詞', '接頭詞') and _strong(t.surface)
            and not (t.pos_sub or '').startswith('代名詞') and not _question_number(t))


def _question_number(t):
    """解析が 数 とした語のうち、数の字でない語（何・幾: 問う語）。代名詞の 何 と同じく別の語として切る（お土産｜何 を
    1つの並びとみて 土産なら にしていた・2026-11-08 補正担当の正しい文の試し）。CN_KEYSLIP_QUESTION_NUM=0 で前のまま。"""
    if os.environ.get('CN_KEYSLIP_QUESTION_NUM') == '0' or t.pos != '名詞' or not (t.pos_sub or '').startswith('数'):
        return False
    return not any(c.isdigit() or c in '〇一二三四五六七八九十百千万億兆零壱弐参拾' for c in t.surface)


def _one_kanji(t):
    return len(t.surface) == 1 and _kanji(t.surface)


def _fragment(t, tokens=()):
    """ひらがな1字の名詞（が｜いとう｜あの｜はん｜**い**・これ｜カニ｜**ら**）。形式名詞（着く｜の）と、
    ー に接する字（め｜ー｜るみ: ひらがなで書いた外来語）は切れ端とみない。"""
    if not (len(t.surface) == 1 and _is_hira(t.surface) and t.surface != 'ー' and t.pos == '名詞'):
        return False
    if (t.pos_sub or '').startswith('非自立'):
        return False
    for u in tokens:
        if (u.end == t.start or u.start == t.end) and 'ー' in u.surface:
            return False
    return True


def _kanji_inflected(t):
    """漢字で書いた活用する語（硬い・取り掛か）。この段は名詞の並びとかなの切れ端を見るので、窓に入れない。"""
    return t.pos in ('動詞', '形容詞') and any(_kanji(c) for c in t.surface)


def _lone_kanji(t, tokens, k):
    """名詞の並びの中の1字の漢字の語で、前後の漢字の語と1語にならないもの（何｜時 は 何時 という語）。"""
    if not _one_kanji(t):
        return False
    if k > 0 and _strong(tokens[k - 1].surface) and _unit(tokens[k - 1].surface + t.surface) is True:
        return False
    if k + 1 < len(tokens) and _strong(tokens[k + 1].surface) and _unit(t.surface + tokens[k + 1].surface) is True:
        return False
    return True


_PASSIVE_CAUSE = ('れる', 'られる', 'せる', 'させる')


@lru_cache(maxsize=2048)
def _common_verb(base):
    """ひらがなの動詞の基本形が、漢字で書くと身近な動詞か（わすれる→忘れる・ひく→引く）。のす（伸す）は身近でない。"""
    if not base or base == 'する':
        return True
    try:
        import ime_reconvert
        faces = ime_reconvert._dict_faces(base, 8)
    except Exception:
        return True
    ranks = [_rank(f) for f in faces if any(_kanji(c) for c in f)]
    return bool(ranks) and min(ranks) <= COMMON


def _grammar_breaks(tokens):
    """前の語と活用の決まりで続かない語の添字。
    受け身・使役の れる・られる・せる・させる（動詞・接尾）は、動詞の未然形の後だけ（こみ｜れ は続かない）。
    （し｜た｜ば は ばあい を ば｜あい と切った跡で、正しいかなの行にも出るので見ない）"""
    out = []
    for k in range(1, len(tokens)):
        t, p = tokens[k], tokens[k - 1]
        if t.pos == '動詞' and (t.pos_sub or '') == '接尾' and t.base_form in _PASSIVE_CAUSE:
            if p.pos == '動詞' and p.infl_form and not p.infl_form.startswith('未然'):
                out.append(k)
    return out


def _stacked_no(tokens):
    """名詞に付く の（連体化）が、行の頭か が・を・に のすぐ後ろに在る所の添字（荷物が｜の｜日｜って）。"""
    out = []
    for k, t in enumerate(tokens):
        if t.surface != 'の' or (t.pos_sub or '') != '連体化':
            continue
        p = tokens[k - 1] if k else None
        if p is None or p.pos == '記号' or (p.pos == '助詞' and p.surface in ('が', 'を', 'に') and p.end == t.start):
            out.append(k)
    return out


def _degree_head(text, tokens, i, j):
    """名詞の並び tokens[i:j] が「程度の語＋名詞」で、後ろが 助詞＋述語 と読める所か（大変｜頭 を 悩ませた）。
    程度の語（形容動詞の語幹・副詞）を名詞の前に置くのはふつうの書き方なので、1キー違いと見ない。
    CN_KEYSLIP_DEGREE_HEAD=0 で前のまま（2026-11-09 手分けB）。"""
    if os.environ.get('CN_KEYSLIP_DEGREE_HEAD') == '0' or j - i < 2:
        return False
    try:
        import degree_adverb
        words = degree_adverb.degree_words()
    except Exception:
        return False
    h = tokens[i]
    if h.surface not in words or not (h.pos == '副詞' or (h.pos == '名詞' and (h.pos_sub or '').startswith(('形容動詞語幹', '副詞可能')))):
        return False
    rest = text[tokens[i + 1].start:tokens[j - 1].end]
    if not (_unit(rest) is True or _rank(rest) <= COMMON):
        return False                 # 後ろが身近な語（頭・時間）でなければ守らない
    if j >= len(tokens) or tokens[j].pos != '助詞':
        return False
    return any(t.pos in ('動詞', '形容詞') or (t.pos_sub or '').startswith('形容動詞語幹') for t in tokens[j + 1:])


def _cores(text, tokens, odd=()):
    """疑う語の並び [(i, j, 弱い)]（tokens の添字）。弱い: ひらがなだけの行の切れ端だけが根拠（抜きだけ試す）。"""
    n = len(tokens)
    cores = set()
    weak = set()
    marks_only = set()
    chain = set()
    # 1. 漢字・片仮名の名詞の並び（2語以上）で、1字の漢字の語を含み、1語として表に無く珍しいもの
    #    （変｜度・下｜場合・血｜役者・変化｜字）。お昼｜何・今日｜返し のような語の並びは疑わない
    i = 0
    while i < n:
        if not _is_nounish(tokens[i]):
            i += 1
            continue
        j = i
        while j < n and _is_nounish(tokens[j]):
            j += 1
        run = tokens[i:j]
        face = text[run[0].start:run[-1].end]
        if (len(run) >= 2 and any(_lone_kanji(tokens[k], tokens, k) for k in range(i, j))
                and _unit(face) is not True and _rank(face) >= RARE and not _degree_head(text, tokens, i, j)):
            cores.add((i, j))
        i = j
    # 3. 助詞・記号で切らない語の並びで、ひらがな1字の名詞の切れ端を含むもの（いとう｜あの｜はん｜い・これ｜カニ｜ら）。
    #    ひらがなだけの行（助詞も含めて1つの並び）では、並び全体を見る
    if all(_is_hira(t.surface) or t.pos == '記号' for t in tokens):
        i = 0
        while i < n:
            if tokens[i].pos == '記号':
                i += 1
                continue
            j = i
            while j < n and tokens[j].pos != '記号':
                j += 1
            if any(_fragment(t, tokens) for t in tokens[i:j]) and tokens[j - 1].end - tokens[i].start >= 4:
                weak.add((i, j))     # かなの並びまるごと（語の切れ目は当てにならないので途中で切らない）
            i = j
    else:
        i = 0
        while i < n:
            if tokens[i].pos in ('助詞', '記号', '助動詞') or _kanji_inflected(tokens[i]):
                i += 1
                continue
            j = i
            while j < n and tokens[j].pos not in ('助詞', '記号', '助動詞') and not _kanji_inflected(tokens[j]):
                j += 1
            run = tokens[i:j]
            if (len(run) >= 2 and any(_fragment(t, tokens) for t in run)
                    and _unit(text[run[0].start:run[-1].end]) is not True):
                # 漢字・片仮名の語を含む並び（これ｜カニ｜ら）は強い根拠、ひらがなだけの並びは弱い根拠
                (cores if any(_strong(t.surface) for t in run) else weak).add((i, j))
            i = j
    # 6. ひらがなの動詞の連用形に、ひらがなの自立の動詞が続く所（つくり｜のす: ま の所で隣の の）。1語の複合動詞
    #    （つくり｜なおす）でも出るので、打ったままの読みが語に組めて、下がる戻し方が1つだけのときに限る（chain）
    for k in range(1, n):
        p, t = tokens[k - 1], tokens[k]
        if (p.pos == '動詞' and _is_hira(p.surface) and len(p.surface) >= 2 and (p.infl_form or '').startswith('連用')
                and t.pos == '動詞' and (t.pos_sub or '') == '自立' and _is_hira(t.surface)
                and not _common_verb(t.base_form)):
            j = k + 1
            while j < n and tokens[j].pos == '助動詞' and _is_hira(tokens[j].surface):
                j += 1
            chain.add((k - 1, j))
    # 5. 活用の決まりで続かない所（こみ｜れ: 受け身の れる は未然形の後）。
    #    その前後の助詞・記号までの語の並び
    for k in _grammar_breaks(tokens):
        i = k
        while i > 0 and tokens[i - 1].pos not in ('助詞', '記号') and k - i < 3:
            i -= 1
        j = k + 1
        while j < n and tokens[j].pos not in ('助詞', '記号') and j - k < 3:
            j += 1
        cores.add((i, j))
    # 10. 名詞に付く の（連体化）が、行の頭か が・を・に の後ろに在る（荷物が｜の｜日｜って: の の後ろの1キーの打ち違いで
    #     語が崩れた跡）。の から後ろの語の並び（記号まで・4語まで）を窓にする。から の・での・への は正しいので見ない。
    #     CN_KEYSLIP_STACKED_NO=0 で見ない（2026-11-09 手分けB）
    if os.environ.get('CN_KEYSLIP_STACKED_NO') != '0':
        for k in _stacked_no(tokens):
            p = tokens[k - 1] if k else None
            j = k + 1
            while j < n and tokens[j].pos != '記号' and j - k < 5:
                j += 1
            if j > k + 1 and any(_strong(x.surface) for x in tokens[k + 1:j]):
                # 前の助詞も窓に入れる（足された の を抜く戻し: 内容に｜の｜ついて → について）。かなだけの行は見ない
                cores.add((k - 1 if p is not None and p.pos == '助詞' else k, j))
    # 4. 字に付かずに残った ゛゜（して゛んじ: へ の所で隣の ゛ のキー）。後ろのひらがな2語まで
    for k, t in enumerate(tokens):
        if t.surface in ('゛', '゜'):
            j = k + 1
            while j < n and j < k + 3 and _is_hira(tokens[j].surface):
                j += 1
            if j > k + 1:
                marks_only.add((k, j))
    # 7. かなとして成り立たない並び（と｜ゅ: 小さい ゃゅょ は い段の字の後ろだけ）。巻き込み・打ち違いの確かな跡なので、
    #    その前後のひらがなの並びを窓にし、戻しはその字の所だけ（しとゅうがく → しゅうがく）
    bad = _bad_kana_cores(text, tokens) if os.environ.get('CN_KEYSLIP_BAD_KANA') != '0' else []
    # 9. 文の終わりの 終助詞 の後ろにさらに助詞（できるよね｜も: ね の隣の も の巻き込み）。終助詞の並びと後ろの助詞を窓にし、
    #    戻しはその助詞と直前の字の所だけ。CN_KEYSLIP_TAIL_PARTICLE=0 で見ない
    if os.environ.get('CN_KEYSLIP_TAIL_PARTICLE') != '0':
        for k in range(1, n):
            t, p = tokens[k], tokens[k - 1]
            if (t.pos == '助詞' and '終助詞' not in (t.pos_sub or '') and (p.pos_sub or '') == '終助詞'
                    and p.surface != 'か' and p.end == t.start
                    and (k + 1 == n or tokens[k + 1].pos == '記号')):
                i = k - 1
                while i > 0 and (tokens[i - 1].pos_sub or '') == '終助詞' and tokens[i - 1].end == tokens[i].start:
                    i -= 1
                bad.append((i, k + 1, (t.start, 'tail')))
    # 8. 前の段が紫にした所が、漢字の行の中のひらがなの並び（かいす｜せき）の中なら、その並び（助詞まで）を弱い根拠として
    #    巻き込みの1打の抜きだけ試す（かいすせき → かいせき）。CN_KEYSLIP_ODD_HIRA=0 で見ない
    odd_hira = set()
    # かなだけの行でも、前の段が紫にした所なら見る（かいす｜せき が おわった）。CN_KEYSLIP_ODD_HIRA_KANA=0 で前のまま
    kana_only = all(_is_hira(t.surface) or t.pos == '記号' for t in tokens)
    if os.environ.get('CN_KEYSLIP_ODD_HIRA') != '0' and (not kana_only or os.environ.get('CN_KEYSLIP_ODD_HIRA_KANA') != '0'):
        for x, y, *_ in odd or ():
            ks = [k for k, t in enumerate(tokens) if t.start < y and x < t.end]
            if not ks or any(_strong(tokens[k].surface) or tokens[k].pos in ('助詞', '記号') for k in ks):
                continue
            i, j = ks[0], ks[-1] + 1
            while i > 0 and _is_hira(tokens[i - 1].surface) and (
                    tokens[i - 1].pos not in ('助詞', '記号') or _split_particle(tokens, i - 1)):
                i -= 1
            while j < n and _is_hira(tokens[j].surface) and tokens[j].pos not in ('助詞', '記号'):
                j += 1
            if tokens[j - 1].end - tokens[i].start >= 4 and (i, j) not in cores:
                odd_hira.add((i, j))
    return sorted([(i, j, ('bad',) + (p if isinstance(p, tuple) else (p,))) for i, j, p in bad if (i, j) not in cores]
                  + [(i, j, ('oddhira',)) for i, j in odd_hira - cores - weak]
                  + [(i, j, False) for i, j in cores] + [(i, j, True) for i, j in weak - cores]
                  + [(i, j, 'mark') for i, j in marks_only - cores - weak]
                  + [(i, j, 'chain') for i, j in chain - cores - weak - marks_only])


def _split_particle(tokens, k):
    """tokens[k] が、1字ずつに切れたひらがなの並び（せ｜つ｜さ｜めい）の中に置かれた1字の助詞なら True。
    前の語も1字のひらがなで助詞でなく、すき間なく続くとき（語の切れ端の中の助詞は、崩れた語の一部とみる）。
    CN_KEYSLIP_SPLIT_PARTICLE=0 で見ない。"""
    if os.environ.get('CN_KEYSLIP_SPLIT_PARTICLE') == '0' or k < 1:
        return False
    t, p = tokens[k], tokens[k - 1]
    return (t.pos == '助詞' and len(t.surface) == 1 and _is_hira(p.surface) and len(p.surface) == 1
            and p.pos not in ('助詞', '記号') and p.end == t.start
            and k + 1 < len(tokens) and tokens[k + 1].start == t.end)


def _is_bad(kind):
    return isinstance(kind, tuple) and kind[0] == 'bad'


_I_ROW = set('きしちにひみりぎじぢびぴ')


def _bad_kana_cores(text, tokens):
    """[(i, j, 小さい字の位置)]。小さい ゃゅょ が い段でない字（と・ゅ の重なり）の後ろにある所の、ひらがなの並び。"""
    out = []
    n = len(tokens)
    for p, c in enumerate(text):
        if c not in 'ゃゅょ' or p == 0 or text[p - 1] in _I_ROW or not _hira_char(text[p - 1]):
            continue
        k = next((m for m, t in enumerate(tokens) if t.start <= p < t.end), None)
        if k is None:
            continue
        i = k
        while i > 0 and not _strong(tokens[i - 1].surface) and tokens[i - 1].pos != '記号' \
                and tokens[i].start == tokens[i - 1].end:
            i -= 1
        j = k + 1
        while j < n and not _strong(tokens[j].surface) and tokens[j].pos != '記号' and tokens[j].start == tokens[j - 1].end:
            j += 1
        if tokens[j - 1].end - tokens[i].start <= MAX_WEAK:
            out.append((i, j, p))
    return out


def _touches(r, v, a, b):
    """r → v の違いが、r の [a, b] の字にかかるか（前後から同じ字を除いた残りの所）。"""
    x = 0
    while x < min(len(r), len(v)) and r[x] == v[x]:
        x += 1
    y = 0
    while y < min(len(r), len(v)) - x and r[len(r) - 1 - y] == v[len(v) - 1 - y]:
        y += 1
    lo, hi = x, len(r) - 1 - y
    if hi < lo:
        lo = hi = x
    return lo <= b and a <= hi


def _windows(tokens, cores):
    out = []
    n = len(tokens)
    for i, j, weak in cores:
        for di in (0, 1):
            for dj in (0, 1):
                a, b = i - di, j + dj
                if a < 0 or b > n:
                    continue
                if di and tokens[a].pos not in _PARTICLE:
                    continue
                if dj and tokens[b - 1].pos not in _PARTICLE:
                    continue
                out.append((a, b, di, dj, weak, (i, j)))
    return list(dict.fromkeys(out))


# ---- 表記 ----

def _faces_of(reading, kana_ok):
    """読みを語に組んだ表記 [(表記, 内容の語の段の和)]。組めない・身近でない語を含むなら []。"""
    try:
        import reading_lattice
        res = reading_lattice.best(reading)
    except Exception:
        return []
    if not res.surface or any(w[2] == '未知' for w in res.words):
        return []
    opts = [('', 0)]
    try:
        import ime_reconvert
        dict_faces = ime_reconvert._dict_faces
    except Exception:
        dict_faces = lambda r, n=6: ()
    for surf, key, pos, _ops in res.words:
        alts = [surf]
        if _strong(surf):
            alts += [f for f in dict_faces(key, 6) if _strong(f) and not any(_kata(c) for c in f)]
        alts = [f for f in dict.fromkeys(alts) if all(_kanji(c) or _kata(c) or _hira_char(c) for c in f)]
        ranks = {f: (_rank(f) if _strong(f) else 0) for f in alts}
        alts = [f for f in alts if ranks[f] <= COMMON]
        if not alts:
            return []
        opts = [(a + f, r + ranks[f]) for a, r in opts for f in alts][:48]
    first, last = res.words[0][2], res.words[-1][2]
    return [(f, r, first, last) for f, r in opts]


def _odd_tokens(face):
    """組んだ表記の中に崩れが残るか: 1字の漢字の語が並ぶ（変｜度）、名詞の並びが1語として表に無い（変化｜時）。"""
    from morphology import tokenize
    toks = list(tokenize(face))
    singles = [t for t in toks if len(t.surface) == 1 and _kanji(t.surface) and t.pos == '名詞']
    if len(singles) >= 2:
        return True
    i, n = 0, len(toks)
    while i < n:
        if not (toks[i].pos in ('名詞', '接頭詞') and _strong(toks[i].surface)):
            i += 1
            continue
        j = i
        while j < n and toks[j].pos in ('名詞', '接頭詞') and _strong(toks[j].surface):
            j += 1
        if j - i >= 2 and _unit(''.join(t.surface for t in toks[i:j])) is False:
            return True
        i = j
    if os.environ.get('CN_KEYSLIP_GLUE') != '0':
        # 品詞の違う漢字の語がかなを挟まずに並ぶ所（如何｜軸: 副詞＋名詞）も、表に無ければ崩れ
        i = 0
        while i < n:
            j = i
            while j < n and _strong(toks[j].surface) and toks[j].pos in _CONTENT + ('接頭詞',) \
                    and (j == i or toks[j].start == toks[j - 1].end):
                j += 1
            if j - i >= 2 and any(t.pos not in ('名詞', '接頭詞') for t in toks[i:j]) \
                    and _unit(''.join(t.surface for t in toks[i:j])) is False:
                return True
            i = max(j, i + 1)
    return False


def _clean(line, s, e, src, src_tokens=(), any_infl=False):
    """置いた所が語としてきれいか: ひらがな1字の名詞の切れ端が無い、元の漢字の所の内容の語をひらがなにしない
    （掃除尾→そうじゃ・夕方→夕ほか にしない。これカニら→これから は元が漢字でないのでよい）、
    元に無い片仮名を持ち込まない（具室→グロ）。"""
    from morphology import tokenize
    face = line[s:e]
    if any(_kata(c) for c in face) and not any(_kata(c) for c in src):
        return False
    from_kanji = [False] * len(face)
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, src, face, autojunk=False).get_opcodes():
        if tag != 'equal' and any(_kanji(c) for c in src[i1:i2]):
            # 置き換えた所の頭から、元のかなの字の数だけは かなから出た字とみる（の下→にした: に は の から）
            if os.environ.get('CN_KEYSLIP_KANA_POS') != '0':
                # 字の位置で見る: 元の字がかなの所から出た字だけ、かなから出たとみる（の下→にした の に は の から。
                # 掛け校→が無効 の が は 掛 から出たので、漢字の所から助詞を作ったことになる）
                for j in range(j1, j2):
                    i = i1 + (j - j1)
                    if not (i < i2 and _hira_char(src[i])):
                        from_kanji[j] = True
                continue
            h = sum(1 for c in src[i1:i2] if _hira_char(c))
            for j in range(j1 + h, j2):
                from_kanji[j] = True
    # 元の窓に活用する語（する は除く）が無ければ、直した所にも持ち込まない（弟血→落とす土地・昼日班→着る批判）
    # かなとして成り立たない並び（しとゅうがく）は語の切り方が当てにならないので、元の活用する語の有無は見ない
    src_infl = any_infl or any(t.pos in ('動詞', '形容詞') and t.base_form != 'する' for t in src_tokens)
    toks = list(tokenize(line))
    for k, t in enumerate(toks):
        if t.end <= s or t.start >= e:
            continue
        if (os.environ.get('CN_KEYSLIP_SURU_NOUN') != '0' and t.base_form == 'する' and _is_hira(t.surface)
                and (t.infl_form or '').startswith('連用') and k + 1 < len(toks) and toks[k + 1].pos == '名詞'
                and toks[k + 1].start == t.end):
            return False                 # する の連用形のすぐ後ろに名詞（を以下族 → をし家族）は文の形にならない
        if not src_infl and (t.pos in ('動詞', '形容詞', '連体詞') and t.base_form != 'する'):
            return False
        if _fragment(t):
            return False
        if 'ー' != t.surface and len(t.surface) == 1 and _is_hira(t.surface) and t.pos in ('感動詞', 'フィラー', '連体詞', '接頭詞'):
            return False                 # あ｜家族 のような1字の切れ端
        if '固有名詞' in (t.pos_sub or '') and t.surface not in src:
            return False                 # 元に無い地名・人名（柄川→香川）は持ち込まない
        if (os.environ.get('CN_KEYSLIP_PLACED_RANK') != '0' and t.pos == '名詞' and _strong(t.surface)
                and t.surface not in src and t.start >= s and t.end <= e
                and _rank(t.surface) > COMMON and _unit(t.surface) is not True):
            return False                 # 置いた行で1語に読まれた所が身近でない（安｜さ → 安さ）
        if (t.start >= s and t.end <= e and len(t.surface) == 1 and _kanji(t.surface) and t.pos == '名詞'
                and t.surface not in src and _lone_new_kanji_bad(t)):
            return False                 # 元に無い1字の漢字の語（余屋を → 四を・掛け校 → が工）は作らない
        if t.start >= s and t.end <= e and _pair_misfit(toks, k):
            return False                 # 置いた名詞と後ろの述語の組が例文に無い（的を開ける）
        # 元の漢字の所から出たひらがなの語は、する と た だけ（下場合→にした場合）。内容の語・助詞にはしない
        # （掃除尾→そうじゃ・朝母→調子は・枷返信→から変身）
        if (_is_hira(t.surface) and t.base_form not in ('する', 'た', 'だ')
                and any(from_kanji[j - s] for j in range(max(t.start, s), min(t.end, e)))):
            return False
    return True


PAIR_EXPECT = 0.5   # 置いた名詞の回数と (格助詞, 述語) の組の回数から見込む組の回数がこれ以上なのに、
                    # 例文（Tatoeba）に1度も無ければ組まない（的を開ける 0.98・掃除を終える 0.06 は見ない）


LONE_NOUN = 30      # 置いた1字の漢字の名詞が、例文（Tatoeba）に1語としてこれだけ出ること（窓 574・工 7）


def _lone_new_kanji_bad(t):
    """置いた1字の漢字の語が、数（四）か、例文で1語として使われない字（工）か。CN_KEYSLIP_LONE_NEW=0 で見ない。"""
    if os.environ.get('CN_KEYSLIP_LONE_NEW') == '0':
        return False
    if (t.pos_sub or '').startswith('数'):
        return True
    try:
        import pair_choice
        tab = pair_choice._table()
    except Exception:
        return False
    if not tab:
        return False
    return (tab[1].get(t.surface) or 0) < LONE_NOUN


def _pair_misfit(toks, k):
    """toks[k] の名詞＋格助詞＋述語 の組が、どちらもよく出るのに例文に1度も無いか。表が無ければ False。
    CN_KEYSLIP_PAIR=0 で見ない。"""
    if os.environ.get('CN_KEYSLIP_PAIR') == '0' or toks[k].pos != '名詞' or k + 2 >= len(toks):
        return False
    p, v = toks[k + 1], toks[k + 2]
    if p.surface not in ('を', 'が', 'に') or v.pos != '動詞' or (v.pos_sub or '') != '自立':
        return False
    try:
        import pair_choice
        tab = pair_choice._table()
    except Exception:
        return False
    if not tab:
        return False
    pairs, nouns = tab
    w = toks[k].surface
    if not nouns.get(w):
        return False
    base = v.base_form or v.surface
    if pairs.get('\t'.join((p.surface, w, base)), 0):
        return False
    return nouns[w] * _pred_total(p.surface, base) / _noun_sum() >= PAIR_EXPECT


@lru_cache(maxsize=1)
def _noun_sum():
    import pair_choice
    return max(1, sum(pair_choice._table()[1].values()))


@lru_cache(maxsize=2048)
def _pred_total(p, base):
    try:
        import pair_choice
        pairs, _n = pair_choice._table()
    except Exception:
        return 0
    idx = _pred_index()
    return idx.get((p, base), 0)


@lru_cache(maxsize=1)
def _pred_index():
    import pair_choice
    pairs, _n = pair_choice._table()
    out = {}
    for key, c in pairs.items():
        kind, _l, r = key.split('\t')
        if kind in ('を', 'が', 'に'):
            out[(kind, r)] = out.get((kind, r), 0) + c
    return out


def _reads_as(line, s, e, reading):
    """置いた行で、[s, e) が戻した読みのとおりに読まれるか（経 を へ と読ませる・下 を しも と読ませる並びを採らない）。"""
    from morphology import tokenize
    got = []
    for t in tokenize(line):
        if t.end <= s or t.start >= e:
            continue
        if t.start < s or t.end > e:
            return True               # 窓の端をまたぐ語は比べない
        r = t.surface if _is_hira(t.surface) else _hira(t.reading or '')
        got.append(r)
    return ''.join(got) == reading


RARE_WORD = 600     # 紫の付いた2字の漢語でこれ以上珍しいもの
RARE_JUMP = 150     # 戻した先がこれだけ身近
RARE_SLACK = 500    # 行の費用がこれ以上は上がらない


import contextvars as _cv
# この行のファイルタブの文脈語彙（vocabulary.build_context_vocab の {読み: (表記, 分類)}・analysis_context.Reads）。
# correction_entry が段を回す間だけ入れる。無ければ None（前のまま）
DOC_CONTEXT = _cv.ContextVar('keyslip_doc_context', default=None)


def _in_doc(face, reading):
    ctx = DOC_CONTEXT.get()
    if not ctx:
        return False
    try:
        got = ctx[reading]
    except Exception:
        return False
    surf = got[0] if isinstance(got, (tuple, list)) and got else got
    return surf == face


def _rare_word_fixes(text, tokens, odd, here):
    """前の段が紫にした、珍しい2字の漢語1語（連接）で、1キーの戻しの身近な名詞のうち同じファイルタブに書かれている語が
    ちょうど1つ（隣接）なら直す。
    語の表に在る語なので行の費用はほぼ変わらない。戻し先が2つ以上なら紫のまま（決めない）。"""
    from morphology import tokenize, path_cost
    out = []
    try:
        import ime_reconvert
        dict_faces = ime_reconvert._dict_faces
    except Exception:
        return out
    for sp in odd or ():
        a, b = sp[0], sp[1]
        inside = [t for t in tokens if t.start < b and a < t.end]
        if len(inside) != 1:
            continue
        t = inside[0]
        surf = t.surface
        if (len(surf) != 2 or not all(_kanji(c) for c in surf) or t.pos != '名詞'
                or t.start < a - 1 or t.end > b + 1):
            continue
        if (t.start > 0 and _kanji(text[t.start - 1])) or (t.end < len(text) and _kanji(text[t.end])):
            continue                     # 長い漢字の並びの一部（追記｜文）は1語として見ない
        rk = _rank(surf)
        if rk < RARE_WORD:
            continue
        faces = {}
        homophone = False
        for r in _one_token_readings(text, t):
            r = _compose_marks(r)
            if len(r) < MIN_READ:
                continue
            if any(f != surf and _rank(f) <= COMMON for f in dict_faces(r, 8)):
                homophone = True         # 同じ読みに身近な語が在る（捨身／写真）のは変換の選び違いの型で、別の段の持ち
                break
            for v in _variants(r):
                for f in dict_faces(v, 8):
                    if (2 <= len(f) <= 3 and all(_kanji(c) for c in f) and f != surf
                            and _rank(f) <= min(COMMON, rk - RARE_JUMP)):
                        faces.setdefault(f, v)
        # 戻し先は、同じファイルタブのほかの所に正しく書かれている語だけ（連接→隣接・面接・建設 のうち書かれている 隣接）。
        # 書かれていなければ紫のまま（語の表に在る語どうしなので、行だけでは決める根拠が無い: 貴社→機種 など）
        if homophone:
            continue
        faces = {f: v for f, v in faces.items() if _in_doc(f, v)}
        if len(faces) != 1:
            continue
        face = next(iter(faces))
        line = text[:t.start] + face + text[t.end:]
        c = path_cost(line)
        if c is None or c > here + RARE_SLACK:
            continue
        if not any(x.surface == face for x in tokenize(line)):
            continue                     # 置いた行で1語として読まれない
        out.append((t.start, t.end, face, surf))
    return out


COMMON_WORD = 450   # 窓の中のこの身近さ以下の2字以上の漢字の語（検索・対象）は、その読みの中を打ち違いとみない


def _breaks_common_word(r, v, toks, face):
    """戻した打鍵が、窓の中の身近な2字以上の漢字の語（IME がその読みで返す語: 検索）の読みの中に在り、その語が直した
    表記に残らないなら採らない（検索欄 → 県三輪）。打ち違いはふつう身近でない字の所に在る（2026-11-08 未解決タブの
    誤判定）。切り替え CN_KEYSLIP_KEEP_COMMON=0。"""
    if os.environ.get('CN_KEYSLIP_KEEP_COMMON') == '0':
        return False
    rds = [_hira(t.reading or '') for t in toks]
    if not all(rds):
        return False
    if ''.join(rds) != r:
        # 窓の読みが別の読み（変 を かわ）で組まれていても、前から読みの合う語の所は分かる（部屋 + 変 を
        # へやかわ と読んで 変化輪: 2026-11-08 正しい文 この部屋変だ → 変化を）。前の字を別の読みにした窓（背 を せい）は
        # 前のまま見ない（背確認 の紫を残す）
        if os.environ.get('CN_KEYSLIP_KEEP_COMMON_ALIGN') == '0':
            return False
        ends = [None] * len(toks)
        pos = 0
        for k, rd in enumerate(rds):
            if r.startswith(rd, pos):
                ends[k] = (pos, pos + len(rd))
                pos += len(rd)
            else:
                break
        rds = [rd if ends[k] else None for k, rd in enumerate(rds)]
    else:
        ends, pos = [], 0
        for rd in rds:
            ends.append((pos, pos + len(rd)))
            pos += len(rd)
    i = 0
    while i < min(len(r), len(v)) and r[i] == v[i]:
        i += 1
    j = 0
    while j < min(len(r), len(v)) - i and r[len(r) - 1 - j] == v[len(v) - 1 - j]:
        j += 1
    lo, hi = i, len(r) - j          # 元の読みで替わった所 [lo, hi)
    for t, rd, ab in zip(toks, rds, ends):
        if not rd or not ab:
            continue
        a, b = ab
        if (len(t.surface) >= 2 and all(_kanji(c) for c in t.surface) and _rank(t.surface) <= COMMON_WORD
                and t.surface not in face and (a < max(hi, lo + 1) and lo < b)):
            return True
    return False


def _suffix_after_common(tokens, a, b):
    """窓の1字の漢字の語がどれも、英字・数のすぐ後ろに付いて、その読みで IME が上の方に返す字
    （A｜列）なら、直し先が決まらないときの紫は付けない（語に付く造語の要素で、打ち違いの印が弱い）。
    CN_KEYSLIP_SUFFIX_PURPLE=0 で前のまま。"""
    if os.environ.get('CN_KEYSLIP_SUFFIX_PURPLE') == '0':
        return False
    try:
        import ime_order
    except Exception:
        return False
    lone = [k for k in range(a, b) if len(tokens[k].surface) == 1 and _kanji(tokens[k].surface)]
    if not lone:
        return False
    for k in lone:
        if k == 0:
            return False
        p, t = tokens[k - 1], tokens[k]
        ps = p.surface or ''
        if p.end != t.start:
            return False
        rd = _hira(t.reading or '')
        # 前が数・英字、または身近な2字以上の漢語の名詞に音読みの1字が付いた形（検索｜欄・対象｜例: 漢語の複合語の
        # ふつうの作り方）。訓読みの1字（資料｜巣・野菜｜月）は打ち違いの紫を残す
        try:
            import kanji_onkun
            on = kanji_onkun.kind_of(t.surface, rd) == 'on'
        except Exception:
            on = False
        kango_head = (len(ps) >= 2 and all(_kanji(c) for c in ps) and _rank(ps) <= COMMON_WORD and p.pos == '名詞'
                      and not (p.pos_sub or '').startswith(('非自立', '副詞可能', '代名詞', '固有名詞')) and on)
        head = ((p.pos_sub or '').startswith('数')
                or bool(ps and all(c.isascii() and c.isalnum() for c in ps)) or kango_head)
        if not head or not ime_order.ime_plausible(t.surface, rd):
            return False
    return True


def _suffix_swap(r, v, toks, src, face):
    """身近な語のすぐ後ろの1字の漢字だけを、同じ長さの読みの1打違いで別の1字に替える形（対象｜例 → 対象｜性）で、
    元の字も替えた字もその読みで IME が上の方に返す字なら、どちらも書いたとおりの語として読めるので採らない
    （2026-11-08 未解決タブの誤判定）。CN_KEYSLIP_SUFFIX_SWAP=0 で前のまま。"""
    if os.environ.get('CN_KEYSLIP_SUFFIX_SWAP') == '0' or len(src) != len(face) or len(r) != len(v):
        return False
    diff = [i for i in range(len(src)) if src[i] != face[i]]
    if len(diff) != 1 or not _kanji(src[diff[0]]) or not _kanji(face[diff[0]]):
        return False
    pos = 0
    for k, t in enumerate(toks):
        a, b = pos, pos + len(t.surface)
        pos = b
        if a == diff[0] and b == a + 1:
            if k == 0:
                return False
            p = toks[k - 1]
            if not (len(p.surface) >= 2 and all(_kanji(c) for c in p.surface) and _rank(p.surface) <= COMMON_WORD):
                return False
            rd_old = _hira(t.reading or '')
            rdp = sum(len(_hira(x.reading or '')) for x in toks[:k])
            rd_new = v[rdp:rdp + len(rd_old)]
            try:
                import ime_order
                return ime_order.ime_plausible(src[a], rd_old) and ime_order.ime_plausible(face[a], rd_new)
            except Exception:
                return False
    return False


def _stem_sa(toks):
    """窓が 形容動詞の語幹＋さ（異様｜さ・静か｜さ）を含むなら、語幹から名詞を作るふつうの形で打ち違いの印にならない。
    直さない（異様さ → 少佐・2026-11-08 未解決タブの誤判定）。CN_KEYSLIP_STEM_SA=0 で前のまま。"""
    if os.environ.get('CN_KEYSLIP_STEM_SA') == '0':
        return False
    for p, t in zip(toks, toks[1:]):
        if ((p.pos_sub or '').startswith('形容動詞語幹') and t.surface == 'さ' and (t.pos_sub or '').startswith('接尾')
                and p.end == t.start and getattr(p, 'has_reading', True) and len(p.surface) >= 2):
            return True
    return False


def _bad_placed(text, s, src, face, tokens, a):
    """直した表記が文の形にならない: 数のすぐ後ろの数え方の字（3｜字以上）を数え方でない語に替える（3事情）、
    元に無い片仮名の語が身近でも辞書の語でもない（アプリ名 → アプリン）。CN_KEYSLIP_BAD_PLACED=0。"""
    if os.environ.get('CN_KEYSLIP_BAD_PLACED') == '0':
        return False
    if a > 0 and (tokens[a - 1].pos_sub or '').startswith('数') and tokens[a - 1].end == s:
        if (tokens[a].pos_sub or '').startswith('接尾') and face[:1] != src[:1]:
            return True
    m = 0
    while m < min(len(src), len(face)) and src[m] == face[m]:
        m += 1
    k = m
    while k > 0 and _kata(face[k - 1]):
        k -= 1
    q = m
    while q < len(face) and _kata(face[q]):
        q += 1
    word = face[k:q]
    if word and any(_kata(c) for c in word) and word not in src:
        if _unit(word) is not True and _rank(word) > COMMON:
            return True
    return False


def propose(text, odd=()):
    """[(開始, 終了, 置く表記 or None, 理由)]。置く表記が None なら紫。"""
    if not _on() or not text or len(text) > 200:
        return []
    from morphology import tokenize, path_cost
    tokens = list(tokenize(text))
    if not tokens:
        return []
    here = path_cost(text)
    if here is None:
        return []
    found = []
    swapped = set()
    doubtful = set()
    rare = _rare_word_fixes(text, tokens, odd, here) if os.environ.get('CN_KEYSLIP_RARE_WORD') != '0' else []
    two = _two_slip_verb(text, tokens, here) if os.environ.get('CN_KEYSLIP_TWO_SLIP') != '0' else []
    for a, b, di, dj, weak, core in _windows(tokens, _cores(text, tokens, odd)):
        odd_weak = isinstance(weak, tuple) and weak[0] == 'oddhira'
        if odd_weak:
            weak = True                  # 抜きだけ・下がる戻し方が1つだけ（打ったままが組めなくても行の費用と比べる）
        s, e = tokens[a].start, tokens[b - 1].end
        src = text[s:e]
        if src[0] in 'ーぁぃぅぇぉっゃゅょゎ':
            continue                     # 語の途中から始まる窓（りにゅ｜ーある）は見ない
        if any(_kata(t.surface[0]) and (len(t.surface) < 2 or _rank(t.surface) > COMMON) for t in tokens[a:b]):
            continue                     # 片仮名の切れ端（ラ人・コ円・トシイ）は IME の崩れ方が別（これ｜カニ｜ら の カニ はよい）
        if any(_kanji_inflected(t) for t in tokens[a:b]):
            continue                     # 漢字の活用する語（取り掛か｜する）は別の段（送り仮名・活用の直し）
        kana_src = not any(_kanji(c) for c in src)
        cands = {}
        gained = set()
        rejected = False
        rej = []
        base = here
        based = False
        readings = _token_readings(text, tokens, a, b)
        # 打ったままの読みを組み直しただけの表記（変換の選び直し・かなの行の変換）は、この段の直しではない。
        # その一番よい費用より GAIN 以上下がるものだけを1打の戻しとみる
        for r, _solo in ([] if _is_bad(weak) else readings):
            # かなとして成り立たない所（と｜ゅ・よね｜も）は、元の行そのものが崩れなので行の費用と比べる
            for face, _rk, _f, _l in _faces_of(r, kana_src):
                if _odd_tokens(face):
                    continue
                c0 = path_cost(text[:s] + face + text[e:])
                if c0 is not None:
                    base = min(base, c0)
                    based = True
        if weak == 'chain' and not based and os.environ.get('CN_KEYSLIP_CHAIN_RAW') != '0':
            # 動詞の連用形＋動詞 の所で、打ったままの読みが語に組めない（いれ｜のまし｜た）のは、それ自体が崩れの根拠。
            # 行の費用と比べ、下がる戻し方が1つだけのときに限る（下の gained の決まり）
            pass
        elif (weak is True or weak == 'chain') and not based and not odd_weak:
            # かなだけの並びで、打ったままの読みが語に組めないときは、抜いた形と比べる相手が無い（比べられない）
            continue
        # 重なった の（_stacked_no）は1字の語でも抜いてよい（足された1打: 内容に｜の｜ついて → について）
        # （の より前の窓の字はかなの助詞なので、読みの中の位置は字の位置と同じ）
        free = ({tokens[k].start - s for k in _stacked_no(tokens)
                 if a < k < b and all(_is_hira(x.surface) for x in tokens[a:k])}
                if os.environ.get('CN_KEYSLIP_STACKED_NO') != '0' else set())
        if odd_weak:
            # 1字ずつに切れた並びの中の1字の助詞（せ｜つ｜さ｜めい の さ）は、崩れた語の中の足された1打として抜いてよい
            free = set(free) | {tokens[k].start - s for k in range(a, b) if _split_particle(tokens, k)}
        for r, solo in readings:
            if free:
                solo = frozenset(solo) - free
            if len(r) < MIN_READ:
                continue                 # 短い読み（ら・へ）は1打で何にでもなる
            # かなとして成り立たない並び（し｜と｜ゅうがく）の語の切れ目は当てにならないので、1字の語の字も抜いてよい
            vs = _variants(r, drops_only=weak is True, solo=frozenset() if _is_bad(weak) else solo,
                           long=_is_bad(weak))
            ranked = []
            try:
                import reading_lattice
                for v, w in vs.items():
                    res = reading_lattice.best(v)
                    if res.surface and not any(x[2] == '未知' for x in res.words):
                        ranked.append((res.cost + EDIT_W * w, v, w))
            except Exception:
                continue
            if isinstance(weak, tuple) and weak[0] == 'bad':
                q = weak[1] - s
                ranked = [x for x in ranked if _touches(r, x[1], q - 1, q)]
            if weak == 'chain':
                # 動詞の連用形＋動詞 の所は、後ろの動詞の中の打ち違いだけ（つくり｜のす → つくり｜ます）。前の動詞まで
                # 替える形（はき｜どうじ → 弾き同時）は、ひらがなの切り方の揺れ
                keep = tokens[core[0]].end - s
                tail = e - tokens[core[0] + 1].end
                ranked = [x for x in ranked if x[1][:keep] == r[:keep]
                          and (tail <= 0 or x[1][len(x[1]) - tail:] == r[len(r) - tail:])]
            for _c, v, w in sorted(ranked)[:TOP]:
                faces = _faces_of(v, kana_src)
                if _is_bad(weak) and len(weak) > 2 and _is_hira(src):
                    # かなの所はかなのまま戻した形も比べる（できるよねも → できるよね。よね → 米 にしない）
                    faces = faces + [(v, 0, '助詞', '助詞')]
                for face, rk, first, last in faces:
                    if face == src or not face:
                        continue
                    # 窓に入れた前後の助詞は、助詞のまま（の→に はよい・て→手 は別の語）
                    if (di and first != '助詞') or (dj and last != '助詞'):
                        continue
                    # 直前の助詞と同じ字を窓の頭に作る戻し（内容に｜の → に｜に）は、助詞が2つ重なるだけ。
                    # 窓に前の助詞を入れて足された1字を抜く方（にの → に）を見る。CN_KEYSLIP_NO_DOUBLE=0 で前のまま
                    if (a > 0 and tokens[a - 1].pos == '助詞' and tokens[a - 1].end == s and face[0] != src[0]
                            and face[0] == text[s - 1] and os.environ.get('CN_KEYSLIP_NO_DOUBLE') != '0'):
                        continue
                    line = text[:s] + face + text[e:]
                    if (_breaks_common_word(r, v, tokens[a:b], face) or _bad_placed(text, s, src, face, tokens, a)
                            or _suffix_swap(r, v, tokens[a:b], src, face) or _stem_sa(tokens[a:b])):
                        continue
                    c = path_cost(line)
                    if c is None or base - c < GAIN:
                        continue
                    if _odd_tokens(face) or not _reads_as(line, s, s + len(face), v) or not _clean(line, s, s + len(face), src, tokens[a:b], any_infl=_is_bad(weak)):
                        rejected = True
                        rej.append((c + RANK_W * rk + EDIT_W * w, c, face))
                        continue
                    if odd_weak and not _one_word(line, s, s + len(face)):
                        continue         # 紫の所のひらがなの並びは、1語の中の巻き込み（かいすせき → 解析）だけ
                    if weak == 'chain' and not based and not _first_verb_kept(line, s, tokens[core[0]]):
                        continue         # 前の動詞（いれ）は動詞のまま（はき｜どうじ → 破棄どうぞ にしない）
                    sc = c + RANK_W * rk + EDIT_W * w
                    if face not in cands or sc < cands[face][0]:
                        cands[face] = (sc, c)
                    gained.add(v)
        if not cands:
            if isinstance(weak, tuple) and weak[0] == 'bad' and di + dj == 0 and odd_purple():
                # かなとして成り立たない所は、戻し先が決まらなくても紫（その字の前後だけ）
                q = weak[1]
                found.append((max(s, q - 1), q + 1, [], here, core, 0, 'unsure'))
                continue
            if (rejected and not weak and di + dj == 0 and odd_purple() and _plain_lone(tokens[a:b])
                    and not _suffix_after_common(tokens, a, b)):
                # 1キーの戻しで行がはっきり良くなるのに、どの戻し先も語としてきれいでない（如何｜軸・安｜さ）。
                # 直し先は決めきれないが打ち違いの見込みは高いので、紫だけ付ける
                found.append((s, e, [], here, core, 0, 'unsure'))
            continue
        if DEBUG is not None:
            DEBUG.append(('gained', src, sorted(gained), sorted(cands.items(), key=lambda x: x[1][0])[:3]))
        raw_chain = weak == 'chain' and not based
        if raw_chain and len(gained) > 1:
            # 打ったままが組めない並びでは、ほかの戻し方も行の費用を下げる。一番よい候補が2番目より GAIN 以上
            # よいときだけ（いれのました → 入れました 13118・入れのした 22454）
            rk2 = sorted(v[0] for v in cands.values())
            if len(rk2) > 1 and rk2[1] - rk2[0] < GAIN:
                continue
        elif (weak is True or weak == 'chain') and len(gained) > 1:
            # かなだけの並びで、抜いて下がる所が2つ以上あるのは、短くなって下がっただけ（正しいかなの行でも起きる）
            continue
        ranked = sorted(cands.items(), key=lambda x: x[1][0])
        if DEBUG is not None:
            DEBUG.append((src, here, base, ranked[:3], sorted(rej)[:4]))
        if (_in_odd(odd, s, e) and cands
                and any(sc <= min(v[0] for v in cands.values()) and _kanji_core(f, src) for sc, _c, f in rej)):
            # 前の段が紫にした所では、後ろの段（odd_respell の紫の所の打ち違い）が打った記録と前後の語で読み直す。
            # 1キーの戻しのほかに、行がもっと良くなるのに語の確かめで落ちた漢字の戻し方（さかじ → さんじ: 三時）が在るときは、
            # ここで決めると後ろの段の答え（差化時→三時）を上書きするので紫のまま（2026-11-08 補正担当の束）
            doubtful.add((s, e))
        if not weak and _swap_rival(text, s, e, readings, base, kana_src, src, tokens[a:b], ranked[0][0], ranked[0][1][1]):
            swapped.add((s, e))
        found.append((s, e, ranked, here, core, di + dj, weak))
    if not found:
        return _with_two(text, sorted(rare), two)
    # 前後の助詞を入れた窓は、入れない窓で候補が無いときだけ（に｜友達都映画 → の｜友達と映画 にしない）
    plain = {f[4] for f in found if f[5] == 0 and f[2]}
    found = [f for f in found if f[5] == 0 or f[4] not in plain]
    # 重なる窓は一番よいもの（費用の下がり＋差）を残す
    best = []
    for s, e, ranked, here, _core, _ext, _kind in sorted(found, key=lambda f: f[2][0][1][0] if f[2] else 1e18):
        if any(x < e and s < y for x, y, *_ in best):
            continue
        if not ranked:
            best.append((s, e, None, text[s:e]))
            continue
        face = ranked[0][0]
        rivals = [f for f, v in ranked[1:] if f != face]
        sure = ((not rivals or cands_gap(ranked) >= FIX_MARGIN) and _core_kind(found, s, e) != 'mark'
                and (s, e) not in swapped and not any(x < e and s < y for x, y in doubtful)
                and not (rivals and _in_odd(odd, s, e) and cands_gap(ranked) < ODD_MARGIN))
        best.append((s, e, face if sure else None, text[s:e]))
    best += [m for m in rare if not any(x < m[1] and m[0] < y for x, y, *_ in best)]
    return _with_two(text, sorted(best), two)


def _with_two(text, marks, two):
    """2打の戻しの動詞（_two_slip_verb）を足す。重なる1打の窓より行の費用が低い（または重なる窓が紫だけ）なら、そちらに替える。"""
    if not two:
        return marks
    from morphology import path_cost
    out = list(marks)
    for m in two:
        over = [x for x in out if x[0] < m[1] and m[0] < x[1]]
        if over and m[2] is None:
            continue
        if over and m[2] is not None:
            cm = path_cost(text[:m[0]] + m[2] + text[m[1]:])
            if cm is None or any(x[2] is not None and (path_cost(text[:x[0]] + x[2] + text[x[1]:]) or 0) <= cm
                                 for x in over):
                continue
        out = [x for x in out if x not in over] + [m]
    return sorted(out)


def _swap_rival(text, s, e, readings, base, kana_src, src, src_tokens, best, best_cost):
    """窓の読みの隣り合う2字を入れ替えた読み（かさな → さかな・ちょういせ → ちょうせい）でも、行がはっきり良くなる
    きれいな語に組めるか。組めるなら打鍵の順番違いとも読めて、1キーの戻しと決めきれないので紫だけにする
    （2026-11-08 補正担当の束: 傘名 → 加算・長伊勢 → 注意せ）。CN_KEYSLIP_SWAP_RIVAL=0 で見ない。"""
    if os.environ.get('CN_KEYSLIP_SWAP_RIVAL') == '0':
        return False
    from morphology import path_cost
    try:
        import reading_lattice
    except Exception:
        return False
    for r, _solo in readings:
        if len(r) < MIN_READ:
            continue
        for k in range(len(r) - 1):
            if r[k] == r[k + 1] or not (_hira_char(r[k]) and _hira_char(r[k + 1])):
                continue
            v = r[:k] + r[k + 1] + r[k] + r[k + 2:]
            if v[0] in 'ぁぃぅぇぉっゃゅょゎー' or not all(_hira_char(c) for c in v):
                continue
            res = reading_lattice.best(v)
            if not res.surface or any(x[2] == '未知' for x in res.words):
                continue
            for face, _rk, _f, _l in _faces_of(v, kana_src)[:6]:
                if not face or face == src or face == best:
                    continue
                line = text[:s] + face + text[e:]
                c = path_cost(line)
                if c is None or base - c < GAIN or c > best_cost + FIX_MARGIN:
                    continue             # 入れ替えの読みが1キーの戻しと張り合うほど良いときだけ
                if _odd_tokens(face) or not _clean(line, s, s + len(face), src, src_tokens):
                    continue
                if DEBUG is not None:
                    DEBUG.append(('swap', src, face, c, best, best_cost))
                return True
    return False


def _kanji_core(face, src):
    """元の窓と同じ後ろのかな（から・を）を除くと漢字だけの表記か（三時から → 三時。好きは は違う）。"""
    k = 0
    while k < min(len(face), len(src)) and face[-1 - k] == src[-1 - k] and not _kanji(face[-1 - k]):
        k += 1
    core = face[:len(face) - k]
    return bool(core) and all(_kanji(ch) for ch in core)


ODD_MARGIN = 1200   # 前の段が紫にした所で直すときの、2番目の候補との差


def _in_odd(odd, s, e):
    """前の段が紫にした所か。そこでは2番目の候補との差を ODD_MARGIN まで求める（本化 → 変化／本 の差 1003 は決めない・
    変度 → 返事／本土 の差 1415 は決める）。CN_KEYSLIP_ODD_STRICT=0 で前のまま。"""
    return os.environ.get('CN_KEYSLIP_ODD_STRICT') != '0' and any(x < e and s < y for x, y, *_ in odd or ())


def _one_word(line, s, e):
    """[s, e) の内容の語が1つだけか（後ろの助詞・助動詞は数えない）。"""
    from morphology import tokenize
    toks = [t for t in tokenize(line) if s <= t.start and t.end <= e]
    return sum(1 for t in toks if t.pos not in ('助詞', '助動詞', '記号')) == 1


def _first_verb_kept(line, s, verb):
    """置いた行で、窓の頭の語が元の動詞と同じ動詞（いれ → 入れ: 基本形の読みが同じ）のまま読まれるか。"""
    from morphology import tokenize
    for t in tokenize(line):
        if t.start == s:
            return t.pos == '動詞' and _hira(t.reading or '') == _hira(verb.reading or verb.surface)
        if t.start > s:
            break
    return False


def _plain_lone(run):
    """紫だけ付ける並びは、1字の漢字の語が普通の名詞（以下｜族 の 族）のときだけ。接尾（作成｜中）・数は付かない。
    続けた形が辞書に在る・身近な並び（誤判定）と、1字の語が隣の語の端の字と身近な語になる並び（誤判｜定 の 判定）は、
    語の切り違いとみて付けない（2026-11-08 補正担当: 見出しの 誤判定 に紫。CN_KEYSLIP_UNSURE_RESPLIT=0 で前のまま）"""
    lone = [k for k, t in enumerate(run) if len(t.surface) == 1 and _kanji(t.surface) and t.pos == '名詞'
            and (t.pos_sub or '').startswith('一般')]
    if not lone:
        return False
    if os.environ.get('CN_KEYSLIP_UNSURE_RESPLIT') == '0':
        return True
    whole = ''.join(t.surface for t in run)
    if _rank(whole) <= COMMON or _unit(whole) is True or _in_dict(whole, run):
        return False
    for k in lone:
        c = run[k].surface
        for pair in ((run[k - 1].surface[-1] + c) if k > 0 else '', (c + run[k + 1].surface[0]) if k + 1 < len(run) else ''):
            if len(pair) == 2 and all(_kanji(x) for x in pair) and _rank(pair) <= COMMON:
                return False
    return True


def _in_dict(face, run):
    """続けた形が辞書の語か（読みをつないで引く）。"""
    try:
        import ime_reconvert
        reading = ''.join(_hira(t.reading or '') for t in run)
        return bool(reading) and face in ime_reconvert._dict_faces(reading, 8)
    except Exception:
        return False


def odd_purple():
    return os.environ.get('CN_KEYSLIP_UNSURE_PURPLE') != '0'


def _core_kind(found, s, e):
    for f in found:
        if f[0] == s and f[1] == e:
            return f[6]
    return None


def cands_gap(ranked):
    return ranked[1][1][0] - ranked[0][1][0] if len(ranked) > 1 else 1e9


def repair_line(line, result, decided=(), input_method='kana'):
    """correction_entry の結果 result に、この段の直し・紫を足す（かな入力だけ）。"""
    if not _on() or input_method != 'kana' or not isinstance(result, dict):
        return result
    out = result
    for _round in range(2):          # 1行に崩れが2つ（こみれから…血役者）でも、直した行でもう1度だけ
        done = out.get('corrected') or line
        try:
            marks = propose(done, _odd_in(out, line, done))
        except Exception:
            return out
        marks = [m for m in marks if not any(x < m[1] and m[0] < y for x, y in _decided(decided))]
        if not marks:
            break
        nxt = _apply(line, out, done, marks)
        if nxt is out:
            break
        out = nxt
        if not any(m[2] for m in marks):
            break
    return out


def _decided(decided):
    return [tuple(x[:2]) for x in (decided or ())]


def _line_coords():
    """紫（odd_spans・odd_reasons・unsure_spans）を元の行の位置で扱うか（アプリは元の行に塗る・入口と多くの段がこの位置で書く）。
    2026-11-09 手分けA: 直した行の位置で足していたため、前に字数の変わる直しがある行で紫が1字ずれていた。
    CN_ODD_LINE_COORDS=0 で前のまま（直した行の位置）。"""
    return os.environ.get('CN_ODD_LINE_COORDS') != '0'


def _map_span(a, b, s, e):
    """文字列 a の範囲 (s, e) を、文字列 b の位置へ写す（同じ所はそのまま、変わった所は変わった範囲全体へ広げる）。"""
    if a == b:
        return s, e
    ops = difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes()

    def at(p, end):
        for tag, i1, i2, j1, j2 in ops:
            inside = (i1 < p <= i2) if end else (i1 <= p < i2)
            if inside:
                if tag == 'equal':
                    return j1 + (p - i1)
                return j2 if end else j1
            if i1 == i2 and p == i1:          # 挿し入れだけの所
                return j2 if end else j1
        return len(b) if end or p >= len(a) else 0
    s2, e2 = at(s, False), at(e, True)
    if e2 <= s2:
        e2 = min(s2 + 1, len(b))
        if e2 <= s2:
            s2 = max(0, e2 - 1)
    return s2, e2


def _odd_in(result, line, done):
    spans = [tuple(x[:2]) for x in (result.get('odd_spans') or ())]
    if done is None:
        return []
    if _line_coords() and done != line:
        return [_map_span(line, done, x[0], x[1]) for x in spans]
    return spans


def _apply(line, result, done, marks):
    out = dict(result)
    new = done
    details, odd_add, fixed = [], [], []
    for m in sorted(marks, key=lambda m: -m[0]):
        s, e, face, src = m[:4]
        if face:
            new = new[:s] + face + new[e:]
            details.append([src, face, m[4] if len(m) > 4 else 'かな入力の1キーの打ち違い'])
            fixed.append((s, e, len(face) - (e - s)))
        else:
            if any(x <= s and e <= y for x, y in _odd_in(out, line, done)):
                continue
            odd_add.append((s, e))
    if new == done and not odd_add:
        return result

    if _line_coords():
        # 紫は元の行の位置のまま。直した所（done の位置）を元の行へ写し、そこに掛かる紫だけ外す。足す紫も元の行へ写す
        base = out.get('corrected') or line
        fixed_org = [_map_span(base, line, fs, fe) for fs, fe, _d in fixed]

        def keep_org(x):
            return not any(x[0] < fe and fs < x[1] for fs, fe in fixed_org)
        for key in ('odd_spans', 'unsure_spans'):
            if out.get(key):
                out[key] = [tuple(x) for x in out[key] if keep_org(x)]
        if out.get('odd_reasons'):
            out['odd_reasons'] = [tuple(r) for r in out['odd_reasons'] if keep_org(r)]
        if odd_add:
            add = [(_map_span(base, line, a, b), done[a:b]) for a, b in odd_add]
            out['odd_spans'] = sorted(set(tuple(x[:2]) for x in (out.get('odd_spans') or ())) | set(x for x, _t in add))
            out['odd_reasons'] = list(out.get('odd_reasons') or ()) + [
                (a, b, f'「{t}」は、かな入力で隣のキーを打ったか、一緒に押したかもしれません') for (a, b), t in add]
        if new != done:
            ops = [o for o in difflib.SequenceMatcher(None, line, new, autojunk=False).get_opcodes() if o[0] != 'equal']
            out.update({'original': line, 'corrected': new, 'changed': True,
                        'details': list(result.get('details') or []) + details,
                        'spans': [[o[3], o[4]] for o in ops], 'original_spans': [[o[1], o[2]] for o in ops]})
        return out

    def shift(p):
        return p + sum(d for fs, fe, d in fixed if p >= fe)

    def keep(x):
        return not any(x[0] < fe and fs < x[1] for fs, fe, _d in fixed)
    for key in ('odd_spans', 'unsure_spans'):
        if out.get(key):
            out[key] = [(shift(x[0]), shift(x[1])) + tuple(x[2:]) for x in out[key] if keep(x)]
    if out.get('odd_reasons'):
        out['odd_reasons'] = [(shift(r[0]), shift(r[1])) + tuple(r[2:]) for r in out['odd_reasons'] if keep(r)]
    if odd_add:
        add = [(shift(a), shift(b)) for a, b in odd_add]
        out['odd_spans'] = sorted(set(tuple(x[:2]) for x in (out.get('odd_spans') or ())) | set(add))
        out['odd_reasons'] = list(out.get('odd_reasons') or ()) + [
            (a, b, f'「{new[a:b]}」は、かな入力で隣のキーを打ったか、一緒に押したかもしれません') for a, b in add]
    if new != done:
        ops = [o for o in difflib.SequenceMatcher(None, line, new, autojunk=False).get_opcodes() if o[0] != 'equal']
        out.update({'original': line, 'corrected': new, 'changed': True,
                    'details': list(result.get('details') or []) + details,
                    'spans': [[o[3], o[4]] for o in ops], 'original_spans': [[o[1], o[2]] for o in ops]})
    return out


NUM_CHARS = frozenset('〇一二三四五六七八九十百千万億')


def numeral_slip(line, i1, i2, new):
    """line[i1:i2] の漢数字が、かな入力の打ち違いで IME が数に変えた字か（貸す九人: 打った かすくにん の す の巻き込み）。
    次のとき True（correction_entry._keep_numerals が数を守らなくてよい）:
    - 元の所に漢数字と、数でない語（貸す）が助詞を挟まずに並んでいる（数だけの並び 三人 は守る）
    - 直した所 new が数を含まない身近な1語（確認）で、その読みが打った記録の読みの1キーの戻し
    CN_NUMERAL_SLIP=0 で常に False。"""
    if os.environ.get('CN_NUMERAL_SLIP') == '0' or not new or any(c in NUM_CHARS for c in new):
        return False
    src = line[i1:i2]
    if not any(c in NUM_CHARS for c in src):
        return False
    try:
        from morphology import tokenize
        toks = [t for t in tokenize(line) if t.start < i2 and i1 < t.end]
        nt = [t for t in tokenize(line[:i1] + new + line[i2:]) if i1 <= t.start and t.end <= i1 + len(new)]
    except Exception:
        return False
    if not toks or any(t.pos in ('助詞', '記号') for t in toks):
        return False
    others = [t for t in toks if not (t.pos == '名詞' and (t.pos_sub or '').startswith(('数', '接尾')))]
    if not others:
        return False                 # 数と助数詞だけ（三人）は守る
    if not all(any(_kanji(c) and c not in NUM_CHARS for c in t.surface) for t in others):
        return False                 # 数でない語は漢字の語（貸す）だけ。片仮名の切れ端（ミウ｜一）は IME の崩れ方が別
    content = [t for t in nt if t.pos not in ('助詞', '助動詞', '記号')]
    if len(content) != 1 or not _strong(content[0].surface) or _rank(content[0].surface) > COMMON:
        return False
    want = _hira(content[0].reading or '')
    head = line[toks[0].start:i1]
    tail = line[i2:toks[-1].end]
    if head or tail:
        return False                 # 窓の端が語の途中なら見ない
    rec = _record(line, toks[0].start, toks[-1].end)
    if rec:
        recs = [_compose_marks(rec)]
    elif os.environ.get('CN_KEYSLIP_NUM_READ') != '0':
        # 打った記録が無い行（PC の diag・貼り付けた行）は、辞書の読み（数の字は音・訓のどれも）で見る（v11）
        try:
            from morphology import tokenize as _tk
            all_t = _tk(line)
        except Exception:
            return False
        a = next((k for k, t in enumerate(all_t) if t.start == toks[0].start), None)
        b = next((k + 1 for k, t in enumerate(all_t) if t.end == toks[-1].end), None)
        if a is None or b is None:
            return False
        recs = [r for r, _solo in _token_readings(line, all_t, a, b) if r]
    else:
        return False
    return any(want in _variants(r) for r in recs)


# ---- 2か所の打ち違いの動詞（2026-11-09 手分けB） ----
TWO_SLIP_GAIN = 4500   # 行の費用がこれだけ下がるときだけ（2打の戻しなので1打の GAIN の1.5倍）
TWO_SLIP_NOUNS = 2     # 動詞の前の名詞の並びの語数の上限


def _voiced(groups):
    """groups の各字に ゛ を足した形（清音の字だけ）[(添字, 新しい groups)]。"""
    out = []
    for gi, g in enumerate(groups):
        if len(g) != 1:
            continue
        ng = list(groups)
        ng[gi] = (g[0], '゛')
        c = _compose([ng[gi]])
        if c and '゛' not in c:
            out.append((gi, ng))
    return out


def _two_slip_variants(reading):
    """隣のキーの巻き込み1打を抜き、そのすぐ前後の字の ゛ の抜け1打を足した読み（はひしめる → はじめる:
    は の隣の ひ の巻き込み＋し の ゛ の抜け）。2打の戻しはこの組だけ（ほかの2打は数が多く当てにならない）。"""
    if not reading or len(reading) > MAX_WINDOW or not all(_hira_char(c) for c in reading):
        return set()
    base = _groups(reading)
    flat = _flat(base)
    out = set()
    for n, (gi, ki, k) in enumerate(flat):
        if n == 0 or len(base[gi]) != 1:
            continue
        nb = [flat[m][2] for m in (n - 1, n + 1) if 0 <= m < len(flat)]
        if not any(_near_drop(k, o) for o in nb):
            continue
        g1 = list(base[:gi]) + list(base[gi + 1:])
        for vi, g2 in _voiced(g1):
            if abs(vi - gi) > 1 and abs(vi - (gi - 1)) > 1:
                continue                 # ゛ の抜けは抜いた字のすぐ前後だけ
            r2 = _compose(g2)
            if r2 and r2 != reading:
                out.add(r2)
    return out


def _two_slip_verb(text, tokens, here):
    """漢字の名詞の並び（1〜2語）に助詞を挟まず漢字の動詞が続く所（歯｜日｜占める・破棄｜締める）で、
    並びまるごとの読みの2打の戻し（_two_slip_variants）が身近な動詞1語になり、行がはっきり良くなるなら直す。
    戻し先が2つ以上なら紫。CN_KEYSLIP_TWO_SLIP=0 で見ない。[(開始, 終了, 置く表記 or None, 元の表記)]"""
    from morphology import tokenize, path_cost
    out = []
    try:
        import reading_lattice
    except Exception:
        return out
    n = len(tokens)
    for k in range(1, n):
        v = tokens[k]
        if v.pos != '動詞' or (v.pos_sub or '') != '自立' or not any(_kanji(c) for c in v.surface):
            continue
        i = k
        while (i > 0 and k - i < TWO_SLIP_NOUNS and tokens[i - 1].pos == '名詞' and tokens[i - 1].end == tokens[i].start
               and all(_kanji(c) for c in tokens[i - 1].surface)):
            i -= 1
        if i == k:
            continue
        j = k + 1
        while j < n and tokens[j].pos == '助動詞' and _is_hira(tokens[j].surface):
            j += 1
        s, e = tokens[i].start, tokens[j - 1].end
        tail = text[v.end:e]
        vr = _hira(v.reading or '')
        if not _is_hira(vr):
            continue
        cands = {}
        for r, _solo in _token_readings(text, tokens, i, k):
            whole = r + vr + tail
            for w in _two_slip_variants(whole):
                if not w.endswith(tail):
                    continue
                res = reading_lattice.best(w)
                face = res.surface
                if not face or face == text[s:e]:
                    continue
                line = text[:s] + face + text[e:]
                wt = [t for t in tokenize(line) if s <= t.start and t.end <= s + len(face)]
                content = [t for t in wt if t.pos not in ('助動詞',)]
                if len(content) != 1 or content[0].pos != '動詞' or content[0].start != s:
                    continue
                if not _strong(content[0].surface) or _rank(content[0].base_form or content[0].surface) > COMMON:
                    continue
                c = path_cost(line)
                if c is None or here - c < TWO_SLIP_GAIN:
                    continue
                sc = c + RANK_W * _rank(content[0].base_form or content[0].surface)
                if face not in cands or sc < cands[face]:
                    cands[face] = sc
        if not cands:
            continue
        ranked = sorted(cands.items(), key=lambda x: x[1])
        sure = len(ranked) == 1 or ranked[1][1] - ranked[0][1] >= FIX_MARGIN
        if DEBUG is not None:
            DEBUG.append(('two_slip', text[s:e], ranked[:3]))
        out.append((s, e, ranked[0][0] if sure else None, text[s:e]))
    return out


# ---- ひらがなの長音 ー を含む外来語（2026-11-09 手分けB） ----
LOAN_LEFT = 6      # ー の前に見る字数の上限
LOAN_RIGHT = 4     # ー の後ろに見る字数の上限
LOAN_MIN = 3       # 外来語の読みの字数の下限（ー を含めて）
LOAN_PARTICLE_HEAD = 'をがにでとはのもへやかよね'   # 外来語のすぐ後ろに来る助詞の頭の字


def _loan_face(reading):
    """読みが「片仮名でしか書かない語」の表（loanword の種）に在り、身近な語なら、その片仮名の表記。"""
    try:
        import loanword
        face = loanword._katakana_seed_kana_only().get(reading)
        if not face or not loanword._seed_kana_allowed(reading, face):
            return None
    except Exception:
        return None
    if _rank(face) > COMMON:
        return None
    return face


def _kata_word(reading):
    """読みが格子で片仮名の1語になるか（せーる → セール）。"""
    try:
        import reading_lattice
        res = reading_lattice.best(reading)
    except Exception:
        return False
    return bool(res.surface) and len(res.words) == 1 and all('ァ' <= c <= 'ヶ' or c == 'ー' for c in res.surface)


def _loan_broken(toks, i, j):
    """text[i:j] の所の解析が崩れているか: 語が所の端をまたぐ（がくし｜ゅうめにゅ｜ー）か、所の中の語が小さいかな・ー で
    始まる（め｜に｜ょ｜ー）。きれいに語に切れている所（けーき）は崩れていない。"""
    for t in toks:
        if t.start < j and i < t.end:
            if t.start < i or t.end > j or t.surface[:1] in 'ゃゅょぁぃぅぇぉっゎー':
                return True
    return False


def _loan_prefix_noun(prefix):
    """外来語の前のかなが名詞で終わるか（がくしゅう｜めにゅー: 学習＋メニュー の複合語）。"""
    try:
        import reading_lattice
        res = reading_lattice.best(prefix)
    except Exception:
        return False
    # 漢字の名詞だけ（あっぷ｜でーと・ぽいんと｜かーど の前は片仮名の語で、外来語の途中）
    return bool(res.words) and res.words[-1][2] == '名詞' and any(_kanji(c) for c in res.words[-1][0])


def _loan_prefix_ok(prefix):
    """外来語の前に残るかなが、語で終わるか（がくしゅう → 学習・これは → これ｜は）。1字の名詞（ご → 碁）は語と見ない。"""
    try:
        import reading_lattice
        res = reading_lattice.best(prefix)
    except Exception:
        return False
    if not res.surface or not res.words or any(w[2] == '未知' for w in res.words):
        return False
    last = res.words[-1]
    return (last[2] in ('助詞', '助動詞', '動詞', '形容詞')
            or (last[2] == '名詞' and len(last[0]) >= 2 and _rank(last[0]) <= COMMON))


def _loan_suffix_ok(rest):
    """外来語の後ろに続くかなが、助詞・助動詞で始まるか（めにゅー｜を）。語で始まる（ぼーる｜ぺん）なら外来語の途中。"""
    if not rest or rest[0] in LOAN_PARTICLE_HEAD:
        return True
    try:
        import reading_lattice
        res = reading_lattice.best(rest)
    except Exception:
        return False
    if not res.surface or not res.words:
        return False
    return res.words[0][2] in ('助詞', '助動詞')


def _long_loan(text, here, input_method='kana', orig=None):
    """ひらがなの並びの中の 長音 ー（日本語のひらがなの語にはほとんど出ない）を外来語の根拠にし、ー を含む読みが
    片仮名でしか書かない身近な語（めにゅー → メニュー）か、その1キーの戻し（めにょー: ゅ の隣の ょ）なら片仮名に直す。
    行の費用が GAIN 以上下がるものだけ。戻し先が並ぶ（FIX_MARGIN 未満）なら紫。CN_KEYSLIP_LONG_LOAN=0 で見ない。
    loanword.katakana_for_hiragana は5字以上だけを見るので、ー の在る4字以下の語（めにゅー）はここで見る。
    [(開始, 終了, 置く表記 or None, 元の表記)]"""
    from morphology import path_cost, tokenize
    out = []
    n = len(text)
    hira = lambda c: 'ぁ' <= c <= 'ゖ'
    toks = list(tokenize(text))
    # かなだけの行かは、打った元の行で見る（前の段が一部を漢字にした行でも、元がかなだけなら同じ扱い）
    kana_line = all(hira(c) or c == 'ー' or not (c.isalnum()) for c in (orig if orig is not None else text))
    for p, ch in enumerate(text):
        if ch != 'ー' or p == 0 or not hira(text[p - 1]):
            continue
        rs = p
        while rs > 0 and (hira(text[rs - 1]) or text[rs - 1] == 'ー') and p - rs < LOAN_LEFT:
            rs -= 1
        re_ = p + 1
        while re_ < n and (hira(text[re_]) or text[re_] == 'ー') and re_ - p <= LOAN_RIGHT:
            re_ += 1
        full = rs
        while full > 0 and hira(text[full - 1]):
            full -= 1
        cands = {}
        exact_at = []
        for i in range(rs, p):
            if i > full and not _loan_prefix_ok(text[full:i]):
                continue                 # 外来語の前のかなが語で終わらない（ご｜めーん → ごローン にしない）
            for j in range(p + 1, re_ + 1):
                r = text[i:j]
                if len(r) < LOAN_MIN:
                    continue
                kana_line_only = kana_line and not (i > full and _loan_prefix_noun(text[full:i]))
                if not _loan_broken(toks, i, j):
                    continue             # 解析が語に切れている所（けーき｜を）は今までどおり（かなのままでよい行を崩さない）
                end = j
                while end < n and hira(text[end]):
                    end += 1
                if not _loan_suffix_ok(text[j:end]):
                    continue             # 外来語の途中で切った所（ぼーる｜ぺん → ボールぺん にしない）
                # かなだけの行では、書いたままの外来語は かなのまま（ほかの段もかなの行を崩さない）。名詞に続けて書いた
                # 外来語（がくしゅう｜めにゅー）と、打ち違いの戻しだけ見る
                tries = [] if kana_line_only else [(r, 0.0)]
                if _loan_face(r) or _kata_word(r):
                    exact_at.append((i, j))  # 書いたままで外来語の読み（行が良くならなくても、打ち違いとは見ない）
                if input_method == 'kana':
                    tries += [(v, w) for v, w in _variants(r).items() if 'ー' in v]
                for v, w in tries:
                    face = _loan_face(v)
                    if not face:
                        continue
                    line = text[:i] + face + text[j:]
                    c = path_cost(line)
                    if c is None or here - c < GAIN:
                        continue
                    sc = c + RANK_W * _rank(face) + EDIT_W * w
                    key = (i, j, face)
                    if key not in cands or sc < cands[key][0]:
                        cands[key] = (sc, w)
        if not cands:
            continue
        cands = {k: v for k, v in cands.items()
                 if v[1] == 0 or not any(x < k[1] and k[0] < y for x, y in exact_at)}
        if not cands:
            continue
        if any(w == 0 for _sc, w in cands.values()):
            # 書いたままの読みで外来語になる所が在れば、打ち違いの戻し（せーる → レール）は見ない
            cands = {k: v for k, v in cands.items() if v[1] == 0}
        ranked = sorted(cands.items(), key=lambda x: x[1][0])
        (i, j, face), (best, bw) = ranked[0]
        rivals = [x for x in ranked[1:] if x[0][2].rstrip('ー') != face.rstrip('ー')]
        sure = not rivals or rivals[0][1][0] - best >= FIX_MARGIN
        if not sure and not bw:
            continue                     # 書いたままの外来語で表記が並ぶだけなら紫にしない
        if DEBUG is not None:
            DEBUG.append(('long_loan', text[i:j], ranked[:3]))
        if any(x[0] < j and i < x[1] for x in out):
            continue
        out.append((i, j, face if sure else None, text[i:j],
                    'ひらがなで書いた外来語' if not bw else 'かな入力の1キーの打ち違い（外来語）'))
    return out


def long_loan_line(line, result, decided=(), input_method='kana'):
    """correction_entry から、格子で漢字を置く段（kana_lattice_place）の前に呼ぶ。ひらがなの ー を含む外来語を片仮名にし
    （打ち違いの戻しはかな入力だけ）、前のかな（がくしゅう）は後ろの段がふつうに漢字にできるようにする。"""
    if not _on() or os.environ.get('CN_KEYSLIP_LONG_LOAN') == '0' or not isinstance(result, dict) or 'ー' not in line:
        return result
    done = result.get('corrected') or line
    try:
        from morphology import path_cost
        here = path_cost(done)
        if here is None:
            return result
        marks = _long_loan(done, here, input_method, orig=line)
    except Exception:
        return result
    marks = [m for m in marks if not any(x < m[1] and m[0] < y for x, y in _decided(decided))]
    if not marks:
        return result
    return _apply(line, result, done, marks)
