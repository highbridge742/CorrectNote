# -*- coding: utf-8 -*-
# CorrectNote — 誤字補正メモ帳
# SPDX-License-Identifier: GPL-3.0-or-later
"""紫の付かない誤りのうち、IME 自身が「辞書の語として読めなかった」所に紫を付ける（2026-11-13・全体評価スレッド）。

なぜ
----
打ち違いの読みを IME が変換すると、語として読めない所は 1字の漢字・人名・切れ端をつないだ形になる
（作った例: みつもり を つみもり と打つと「積み森」のような形）。1つ1つは在る字・在る語なので、こちらの
異様の判定には掛からず、紫も付かずに通る行が残る。
IME の解析（IFELanguage の読み取り。確定もキー入力もしない）は、語ごとに種類を返す。打ち違いの所は
「未知の切れ端」「単漢字」などの種類に落ちる。作った誤字449行と正しい文199行を PC の IME で
読ませた記録では、この種類の語は誤字の行の 114行に出て、正しい文には1行も出なかった（名詞の後ろに付く
1字と数字は除いた後）。紫も直しも付かずに通っていた行では 32行のうち7行に掛かる。

どうやって
----------
既存のファイルは変えない。install() が correction_entry.correct_line を外から包む。
1. 前からの補正の答えの文を IME の解析に通し、語の種類を見る。
2. 種類が下の「落ちた種類」の語のうち、名前や接尾の普通の使い方に当たらないものを拾う。
3. 拾った語が元の行の同じ字のまま1か所だけに在り、まだ紫が掛かっていなければ、そこに紫を足す。
   文は書き換えない（直すのは前からの段の仕事）。
IME が使えない所（雲・IME の無い PC）では何もしない。特定の語や文字列には合わせない。

切り替え: CN_IME_CLASS_MARK=0 で前のまま。
"""
import functools
import os
import unicodedata

# IME の語の種類（IFELanguage の品詞の番号）のうち、辞書の語として読めなかった時に落ちる先
UNKNOWN = frozenset((900, 905))          # 未知の切れ端
SINGLE = frozenset((800, 803))           # 単漢字・1字の接尾に落ちた字
NAME = frozenset((107, 108))             # 姓・名
# 215・219 は「する」「来る」そのものの種類だった（正しい文の文末の「する」に紫を付けていた・2026-11-14 に外した。
# 記録の正しい文199行には「して・した」しか無く、言い切りの「する」が1つも無かったので見落とした）
ODD_VERB = frozenset()
# 姓・名は拾わない: 会社名・屋号（姓＋名詞）のような正しい使い方と見分けられず、束の見逃しにも効かなかった
FALLEN = UNKNOWN | SINGLE | ODD_VERB
NOUNISH = frozenset((100, 101, 103, 105, 109, 117))   # 名詞の類（この後ろの1字は接尾の普通の使い方）
PARTICLE = 0                             # 助詞・助動詞・語尾
HONORIFICS = ('さん', '様', '君', '氏', 'ちゃん', 'くん', '先生', '課長', '部長', '係長', '社長', '殿')
REASON = 'IME が辞書の語として読めなかった所'
REASON_SHORT = '名詞に付く字なのに、打ったかなの読みが付く時の読みと違います。打ち違いかもしれません'

_orig = {}
_words_provider = [None]     # 試験・束の比べ用: 文 → IME の語の並び（PC で取った記録）
STATS = {'lines': 0, 'marked': 0}


def _on():
    return os.environ.get('CN_IME_CLASS_MARK') != '0'


def set_words_provider(fn):
    """fn(文) → ((表記の始め, 終わり, 読みの始め, 終わり, 種類, 旗), ...) か None。None で外す（本物の IME に聞く）。"""
    _words_provider[0] = fn


def _japanese(s):
    return any(('぀' <= c <= 'ヿ') or ('一' <= c <= '鿿') for c in s)


def _letters(s):
    """かな・漢字の字（記号の ・ ー ゛ ゜ 々 を除く）を1つでも含むか。行頭の箇条書きの「・」は U+30FB で片仮名の
    範囲に入るので、_japanese だけだと IME が落ちた種類で返した「・」に紫が付いた（2026-11-13 補正担当、PC の
    未解決タブの通しで 箇条書きの行頭に紫 が10行）。CN_IME_CLASS_LETTERS=0 で前のまま。"""
    if os.environ.get('CN_IME_CLASS_LETTERS') == '0':
        return _japanese(s)
    return any(('ぁ' <= c <= 'ゖ') or ('ァ' <= c <= 'ヺ') or ('一' <= c <= '鿿') for c in s)


def _number(s):
    return all(c.isdigit() or c in '〇一二三四五六七八九十百千万億' for c in s)


def _ime_words(text):
    fn = _words_provider[0]
    if fn is not None:
        return fn(text)
    from ime_language import JapaneseIME
    with JapaneseIME() as ime:
        if not ime.available:
            return None
        got = ime.reverse_words(text)
    if not got:
        return None
    words = got[1]
    # 雲の代わりの辞書（dict_ime）は種類を返さない（全部 0）。種類の無い答えは使わない
    if not any(w[4] for w in words):
        return None
    return words


def _small_only(s):
    """小さい字・伸ばす音だけの切れ端（話し言葉の「でぇ」「ー」）。IME は未知の切れ端で返すが、打ち違いの跡ではない。"""
    return all(c in 'ぁぃぅぇぉっゃゅょゎァィゥェォッャュョヮー〜～' for c in s)


def _kana_face(s):
    return all(('ぁ' <= c <= 'ゖ') or ('ァ' <= c <= 'ヺ') or c in 'ー゛゜' for c in s)


def _restart(text, a, face):
    """語に付いた記号・括弧のすぐ後ろのかなの並びの中の切れ端と、伸ばす音のすぐ後ろのひらがなの切れ端。
    記号や括弧の後ろのかなは読み・言い換えの書き添え（作った例: 寝る＝ねる・手間（てま））、伸ばす音の後ろは話し言葉
    （いってきまーす）で、IME はそこで読みを切って1〜2字の未知の切れ端を返すが、打ち違いの跡ではない
    （2026-11-14 作った正しい文624行で、この部品だけが付けた紫10行が全部この形）。CN_IME_CLASS_RESTART=0 で前のまま。"""
    if os.environ.get('CN_IME_CLASS_RESTART') == '0' or a <= 0 or not _kana_face(face):
        return False
    if text[a - 1] == 'ー':
        return all('ぁ' <= x <= 'ゖ' for x in face)
    k = a
    while k > 0 and _kana_face(text[k - 1]):
        k -= 1                      # かなの並びの始めまで戻る（書き添えの2つ目より後ろの切れ端も同じ扱い）
    if k < 2:
        return False
    cat = unicodedata.category(text[k - 1])
    if cat in ('Ps', 'Pi'):
        return '一' <= text[k - 2] <= '鿿'      # 漢字の語のすぐ後ろの括弧（読みがな）。助詞の後ろ・行頭のかぎ括弧の中は別
    return cat in ('Sm', 'So', 'Sk', 'Sc') and ('一' <= text[k - 2] <= '鿿' or _kana_face(text[k - 2]))


def _redup(text, a, b):
    """切れ端が、2字以上の同じ並びを2回くり返したかなの並び（ぴよぴよ・ぴよピヨ。ひらがなと片仮名は同じに見る）の中か。
    畳語の擬音・擬態語は IME の辞書に無く切れ端で返るが、打ち違いではそろって出ない（2026-11-17 うに 誤判定）。
    CN_IME_CLASS_REDUP=0 で前のまま"""
    if os.environ.get('CN_IME_CLASS_REDUP') == '0':
        return False
    h = ''.join(chr(ord(c) - 0x60) if 'ァ' <= c <= 'ヶ' else c for c in text)
    s, e = a, b
    while s > 0 and _kana_face(text[s - 1]):
        s -= 1
    while e < len(text) and _kana_face(text[e]):
        e += 1
    for x in range(s, e):
        for n in range(2, (e - x) // 2 + 1):
            if h[x:x + n] == h[x + n:x + 2 * n] and x <= a and b <= x + 2 * n:
                return True
    return False


def _listed(text, a, b):
    """中黒・読点・空白で両側を区切られた、かな1字の項目（作った例: あ・い・う・え・お）。
    並べた項目は文として続かないので、IME は1字ずつの未知の切れ端で返すが、打ち違いの跡ではない。
    片側だけが区切り（文の途中の ・）は別。CN_IME_CLASS_LISTED=0 で前のまま。"""
    if os.environ.get('CN_IME_CLASS_LISTED') == '0':
        return False
    marks = '・、，,／/'
    s, e = a, b
    while s > 0 and _kana_face(text[s - 1]):
        s -= 1
    while e < len(text) and _kana_face(text[e]):
        e += 1
    left = s == 0 or text[s - 1] in marks or text[s - 1].isspace()
    right = e == len(text) or text[e] in marks or text[e].isspace()
    inner = (s > 0 and text[s - 1] in marks) or (e < len(text) and text[e] in marks)
    # 項目がかな1字（拗音・濁点のキーを足して2字まで）の時だけ: 字そのものを並べた見出し。語の項目の打ち違いは拾う
    return left and right and inner and e - s <= 2


def _quoted_kana(text, a, b):
    """括弧にちょうど囲まれた、かな1〜2字（助詞や語尾を取り上げて書いた所。作った例: 助詞（「は」など）を足す）。
    語として使っているのでなく字そのものを指しているので、打ち違いの跡ではない。CN_IME_CLASS_QUOTED=0 で前のまま。"""
    if os.environ.get('CN_IME_CLASS_QUOTED') == '0':
        return False
    return (b - a <= 2 and a > 0 and b < len(text) and _kana_face(text[a:b])
            and unicodedata.category(text[a - 1]) in ('Ps', 'Pi') and unicodedata.category(text[b]) in ('Pe', 'Pf'))


def _bare_subject(text, a, b):
    """行の頭の漢字1字の名詞に、助詞を挟まずに動詞・形容詞が続く形（話し言葉の助詞抜き。作った例: 雨ふったら中止）。
    こちらの解析でも その1字が名詞・次が自立の動詞か形容詞 と読める時だけ。助詞・助動詞が続く形（打ち違いが多い）は別。
    CN_IME_CLASS_BARE=0 で前のまま。"""
    if os.environ.get('CN_IME_CLASS_BARE') == '0' or a != 0 or b - a != 1 or not ('一' <= text[0] <= '鿿'):
        return False
    try:
        from morphology import tokenize
        toks = list(tokenize(text))
    except Exception:
        return False
    if len(toks) < 2 or toks[0].start != 0 or toks[0].end != 1 or toks[0].pos != '名詞':
        return False
    sub = getattr(toks[1], 'pos_sub', '') or ''
    return toks[1].pos in ('動詞', '形容詞') and sub.startswith('自立')


def _kana_noun(text, a, b, nxt):
    """行の頭か句読点・空白のすぐ後ろの、ひらがな1字に格助詞・係助詞が続く形（かなのままの1字の和語。作った例: てをふる）。
    IME は1字の未知の切れ端で返すが、語の頭で助詞を従える1字は語として立っている。語の途中の1字（打ち違いの切れ端）は別。
    CN_IME_CLASS_KANA_NOUN=0 で前のまま。"""
    if os.environ.get('CN_IME_CLASS_KANA_NOUN') == '0' or b - a != 1 or not ('ぁ' <= text[a] <= 'ゖ'):
        return False
    if a > 0 and not (text[a - 1].isspace() or text[a - 1] in '、。，．,.「『（('):
        return False
    return (nxt is not None and nxt[0] == b and nxt[4] == PARTICLE and nxt[1] - nxt[0] == 1
            and text[b] in 'をがにではもへと')


def _attached_here(text, a, b):
    """こちらの解析で、1字の所が前の語にじかに付く語（名詞の後ろの 接尾・非自立の名詞: 焙煎｜度、動詞の後ろの助動詞:
    劣ら｜ね｜ども）と読め、どちらも辞書の読みが在るか。IME が語として切れなかった付く語で、打ち違いの跡ではない
    （2026-11-16 うに: 正しい文の 1字 に紫）。CN_IME_CLASS_ATTACHED=0 で前のまま。"""
    if os.environ.get('CN_IME_CLASS_ATTACHED') == '0' or b - a != 1:
        return False
    try:
        from morphology import tokenize
        toks = list(tokenize(text))
    except Exception:
        return False
    for k, t in enumerate(toks):
        # 1字が語の中に在る（劣ら｜ね｜ども の も）ときも、その語で見る
        if not (t.start <= a and b <= t.end) or k == 0 or not t.has_reading:
            continue
        p = toks[k - 1]
        if p.end != t.start or not p.has_reading:
            return False
        sub = t.pos_sub or ''
        if t.pos == '名詞' and sub.startswith(('接尾', '非自立')) and p.pos == '名詞':
            return True
        if t.pos == '助動詞' and p.pos in ('動詞', '助動詞'):
            return True
        if (t.pos == '名詞' and len(t.surface) == 1 and p.pos == '動詞' and (p.infl_form or '') in ('基本形', '連体形')
                and (k + 1 == len(toks) or toks[k + 1].pos in ('助詞', '助動詞', '記号'))
                and os.environ.get('CN_IME_CLASS_ATTR_VERB') != '0'):
            # 動詞の言い切りの形が1字の名詞を修飾する（呼ぶ側・使う方）。後ろが助詞・記号・行の終わりの時だけ
            # （2026-11-17 補正担当、うに: 以前紫の無かった 呼ぶ側）。CN_IME_CLASS_ATTR_VERB=0 で前のまま
            return True
        if t.pos == '助詞' and sub.startswith('接続助詞') and p.pos in ('動詞', '助動詞'):
            return True
        return False
    return False


def _own_word(text, a, b):
    """IME が読めなかった所が、こちらの解析ではちょうど1語の漢字2字以上の普通名詞（固有名詞でない）。こちらの辞書に
    在る語（各行）を IME が知らないだけなので、打ち違いの跡と見ない（2026-11-17 補正担当、うに: 以前紫の無かった
    各行の選択された部分）。CN_IME_CLASS_OWN_WORD=0 で前のまま"""
    if os.environ.get('CN_IME_CLASS_OWN_WORD') == '0' or b - a < 2:
        return False
    face = text[a:b]
    if not all('一' <= c <= '鿿' for c in face):
        return False
    try:
        from morphology import tokenize
        toks = [t for t in tokenize(text) if t.start < b and a < t.end]
    except Exception:
        return False
    return (len(toks) == 1 and toks[0].start == a and toks[0].end == b and toks[0].pos == '名詞'
            and (toks[0].pos_sub or '').startswith(('一般', 'サ変接続')) and toks[0].has_reading)


def _plain_here(text, a, b):
    """こちらの解析で、IME が読めなかった所がふつうの書き方と読める形（2026-11-20 補正担当、うに 誤判定タブの正しい文）。
    - 言い切りの動詞・助動詞のすぐ後ろで記号・行末の前の終助詞（来たぞ、）
    - 記号・名詞のすぐ後ろの副助詞（。など の）。語句を取り上げて書いた所
    - 行がそのかな1字だけ（何の打ち違いかを決める前後が無い）
    - 漢字1字の形容詞の語幹＋動詞の連用形（浅＋煎り）。名詞の複合語で、IME が読みを取り違えただけ
    CN_IME_CLASS_PLAIN=0 で前のまま"""
    if os.environ.get('CN_IME_CLASS_PLAIN') == '0':
        return False
    if text.strip() == text[a:b] and b - a == 1:
        return True
    try:
        from morphology import tokenize
        toks = list(tokenize(text))
    except Exception:
        return False
    hit = [k for k, t in enumerate(toks) if t.start < b and a < t.end]
    if len(hit) != 1 or toks[hit[0]].start != a or toks[hit[0]].end != b:
        return False
    k = hit[0]
    t = toks[k]
    p = toks[k - 1] if k > 0 else None
    q = toks[k + 1] if k + 1 < len(toks) else None
    sub = t.pos_sub or ''
    if t.pos == '助詞' and sub.startswith('終助詞') and p is not None and p.end == a and p.pos in ('動詞', '助動詞', '形容詞') \
            and (q is None or q.pos == '記号'):
        return True
    if t.pos == '助詞' and sub.startswith('副助詞') and p is not None and p.end == a and p.pos in ('記号', '名詞'):
        return True
    if (t.pos == '形容詞' and len(t.surface) == 1 and '一' <= t.surface <= '鿿' and q is not None and q.start == b
            and q.pos == '動詞' and (q.infl_form or '').startswith('連用') and t.has_reading and q.has_reading):
        return True
    return False


def _hira(s):
    return ''.join(chr(ord(c) - 0x60) if 'ァ' <= c <= 'ヶ' else c for c in s)


def _kanji1(c):
    return '一' <= c <= '鿿'


def _mazegaki(text, a, b):
    """切れ端のかなが漢字1字に隣り合い、その漢字の読み＋かな（かな＋読み）が辞書の身近な語の読みで、その語が同じ漢字で
    始まる（終わる）なら、漢字の一部をかなで書いた交ぜ書き（作った例: 破たん・補てん）で、打ち違いの跡ではない
    （2026-11-23 補正担当、うに 誤判定タブ: 交ぜ書きの語の かな の所が「IME が辞書の語として読めなかった所」の紫）。
    CN_IME_CLASS_MAZEGAKI=0 で前のまま"""
    if os.environ.get('CN_IME_CLASS_MAZEGAKI') == '0' or not (1 <= b - a <= 2):
        return False
    frag = text[a:b]
    if not all('ぁ' <= c <= 'ゖ' or 'ァ' <= c <= 'ヶ' for c in frag):
        return False
    try:
        import ime_reconvert as RC
        import kanji_onkun as KO
    except Exception:
        return False
    sides = []
    if a > 0 and _kanji1(text[a - 1]) and not (a > 1 and _kanji1(text[a - 2])):
        sides.append((text[a - 1], True))
    if b < len(text) and _kanji1(text[b]) and not (b + 1 < len(text) and _kanji1(text[b + 1])):
        sides.append((text[b], False))
    for kan, before in sides:
        try:
            rds = {_hira(r if isinstance(r, str) else r[0]) for r in KO.readings_of(kan) or ()}
        except Exception:
            continue
        for rd in rds:
            reading = rd + _hira(frag) if before else _hira(frag) + rd
            try:
                faces = RC._dict_faces(reading, 50) or ()
            except Exception:
                continue
            for f in faces:
                if not all(_kanji1(c) for c in f) or not (f.startswith(kan) if before else f.endswith(kan)):
                    continue
                if len(f) < 2 or RC._rank(f) > RC.DOUBT_MARK:
                    continue
                return True
    return False


def fallen_spans(text, words):
    """IME の語の並びから、辞書の語として読めなかった所（始め, 終わり）を拾う。"""
    out = []
    for k, w in enumerate(words):
        a, b, kind = w[0], w[1], w[4]
        if kind not in FALLEN or not (0 <= a < b <= len(text)):
            continue
        face = text[a:b]
        if not _letters(face) or _number(face) or _small_only(face):
            continue
        if _restart(text, a, face) or _listed(text, a, b) or _quoted_kana(text, a, b) or _redup(text, a, b):
            continue
        if (kind in SINGLE or os.environ.get('CN_IME_CLASS_BARE_ANY') != '0') and _bare_subject(text, a, b):
            continue
        if _kana_noun(text, a, b, words[k + 1] if k + 1 < len(words) else None):
            continue
        if _attached_here(text, a, b):
            continue
        if _own_word(text, a, b):
            continue
        if _plain_here(text, a, b):
            continue
        if _mazegaki(text, a, b):
            continue
        prev = words[k - 1] if k else None
        nxt = words[k + 1] if k + 1 < len(words) else None
        if kind in NAME:
            # 名前の普通の使い方: 敬称が続く・助詞が続く・文の終わり。名詞や別の落ちた語へ直に続く時だけ拾う
            if text[b:].startswith(HONORIFICS):
                continue
            if nxt is None or nxt[0] != b or nxt[4] == PARTICLE or nxt[4] in NAME:
                continue
        if kind in SINGLE and prev is not None and prev[1] == a and prev[4] in NOUNISH:
            continue        # 名詞の後ろに付く1字（加湿器 の 器 の類）
        out.append((a, b))
    out += [sp for sp in _short_suffix_spans(text, words) if not any(x < sp[1] and sp[0] < y for x, y in out)]
    out += [sp for sp in _single_pair_spans(text, words) if not any(x < sp[1] and sp[0] < y for x, y in out)]
    return out


def _single_pair_spans(text, words):
    """IME が漢字1字の名詞2つに分けて並べた所（助詞の後ろ・行頭から、助詞か行末の前まで）で、2字をつないだ形が
    辞書の普通の語（固有名詞でない）でない所（作った例: あめが を打ち違えて「手目が」）。正しい2字の語は IME が
    1語で読むか辞書に在る。PC の IME の記録で正しい文823行に当たり0、作った誤字の行2万5千のうち500行。
    2026-11-20 補正担当。CN_IME_CLASS_SINGLE_PAIR=0 で前のまま。"""
    if os.environ.get('CN_IME_CLASS_SINGLE_PAIR') == '0':
        return []
    out = []
    for k in range(1, len(words)):
        a, b = words[k - 1], words[k]
        if len(a) < 5 or len(b) < 5 or not (0 <= a[0] < a[1] <= len(text) and 0 <= b[0] < b[1] <= len(text)):
            continue
        if not (a[1] - a[0] == 1 and b[1] - b[0] == 1 and a[1] == b[0]):
            continue
        if not all('\u4e00' <= c <= '\u9fff' for c in text[a[0]:b[1]]) or a[4] not in NOUNISH or b[4] not in NOUNISH:
            continue
        nx = words[k + 1] if k + 1 < len(words) else None
        if nx is not None and not (nx[0] == b[1] and nx[4] == PARTICLE):
            continue
        # 後ろに助詞が無い（行末・記号の前の）2字は、見出しや用語を並べた形（作った例: 前置き・後置き の行）で、
        # 文の中で使った形ではない。打ち違いの跡と分ける手がかりが無いので紫にしない（2026-11-22 うに: 誤判定タブで
        # 3日前から付いた紫）。CN_IME_CLASS_SINGLE_PAIR_BARE=1 で前のまま
        if nx is None and os.environ.get('CN_IME_CLASS_SINGLE_PAIR_BARE') != '1':
            continue
        pv = words[k - 2] if k >= 2 else None
        if pv is not None and pv[1] == a[0] and pv[4] != PARTICLE:
            continue
        try:
            from morphology import dictionary_inflections
            rows = dictionary_inflections(text[a[0]:b[1]]) or ()
        except Exception:
            continue
        if any(not str(r[0]).startswith('名詞,固有名詞') for r in rows):
            continue
        out.append((a[0], b[1]))
    return out


def _short_suffix_spans(text, words):
    """名詞のすぐ後ろに IME が別の語として置いた漢字1字で、IME の読みが1字のかななのに、その字を名詞に付けた時の
    読み（辞書の接尾の読み）がどれも2字以上の所（作った例: 見出しめい と打つ所を みだしな と打つと「見出し名」の
    形になり、名 は な と読まれている）。接尾として付いたなら読みは めい のはずで、1字の読みは打ったかなが別の語の
    つもりだった跡。2026-11-20 補正担当。CN_IME_CLASS_SHORT_SUFFIX=0 で前のまま。"""
    if os.environ.get('CN_IME_CLASS_SHORT_SUFFIX') == '0':
        return []
    out = []
    for k in range(1, len(words)):
        w, prev = words[k], words[k - 1]
        a, b = w[0], w[1]
        if not (0 <= a < b <= len(text)) or b - a != 1 or len(w) < 5:
            continue
        ch = text[a]
        if not ('\u4e00' <= ch <= '\u9fff') or w[4] not in NOUNISH or w[3] - w[2] != 1:
            continue
        if prev[1] != a or prev[4] not in NOUNISH or prev[1] - prev[0] < 2:
            continue
        nxt = words[k + 1] if k + 1 < len(words) else None
        if nxt is not None and not (nxt[0] == b and nxt[4] == PARTICLE):
            continue
        try:
            from morphology import dictionary_inflections
            rows = dictionary_inflections(ch) or ()
        except Exception:
            continue
        suf = [r[3] for r in rows if str(r[0]).startswith('名詞,接尾') and len(r) > 3 and r[3] not in ('*', '')]
        if suf and all(len(x) >= 2 for x in suf):
            out.append((a, b))
    return out


def _mark(line, result):
    text = result.get('corrected')
    if not isinstance(text, str) or not text or not _japanese(text):
        return result
    if result.get('odd_spans') and os.environ.get('CN_IME_CLASS_ADD') != '1':
        # もう紫の在る行には足さない。狙いは紫が1つも無いまま通る行で、束の良5行もみな紫なしの行だった
        # （2026-11-13 夜、PC の未解決タブの通しで紫の在る行に1つ足して悪くなった1行）。CN_IME_CLASS_ADD=1 で前のまま
        return result
    words = _ime_words(text)
    if not words:
        return result
    spans = fallen_spans(text, words)
    if not spans:
        return result
    odd = [tuple(x[:2]) for x in result.get('odd_spans') or ()]
    mixed = []
    if os.environ.get('CN_IME_CLASS_MIXED_LOAN') != '0':
        # 片仮名とひらがなを混ぜて書いた外来語（スくりーん）は、補正がそのまま残す名詞。IME はその表記を語として
        # 読めず切れ端で返すが、打ち違いの跡ではない（2026-11-15 v1.19.0 の CI: tests_mixed_nominal_argument）。
        # CN_IME_CLASS_MIXED_LOAN=0 で前のまま
        try:
            import fixed_still_odd as _fso
            mixed = _fso.mixed_loan_spans(text)
        except Exception:
            mixed = []
    add = []
    for a, b in spans:
        if any(x < b and a < y for x, y in mixed):
            continue
        if text == line:
            s, e = a, b
        else:
            # 直しの入った行: 同じ字が元の行の1か所だけに在る時だけ、元の行の位置に付ける
            face = text[a:b]
            s = line.find(face)
            if s < 0 or line.find(face, s + 1) >= 0:
                continue
            e = s + len(face)
        if any(x[0] < e and x[1] > s for x in odd) or any(x[0] < e and x[1] > s for x in add):
            continue
        add.append((s, e))
    if not add:
        return result
    out = dict(result)
    out['odd_spans'] = sorted(list(result.get('odd_spans') or ()) + add, key=lambda x: tuple(x[:2]))
    # 理由は（始め, 終わり, 文）の並び
    short = set(_short_suffix_spans(text, words)) if text == line else set()
    out['odd_reasons'] = sorted(list(result.get('odd_reasons') or ()) + [
        (s, e, REASON_SHORT if (s, e) in short else REASON) for s, e in add],
                                key=lambda x: tuple(x[:2]))
    STATS['marked'] += len(add)
    return out


def correct_line(line, *args, **kwargs):
    result = _orig['correct_line'](line, *args, **kwargs)
    if not _on() or not isinstance(line, str) or not isinstance(result, dict):
        return result
    try:
        STATS['lines'] += 1
        return _mark(line, result)
    except Exception:
        return result


def install():
    import correction_entry as ce
    if 'correct_line' in _orig:
        return
    _orig['correct_line'] = ce.correct_line
    # 呼ぶ側（analysis_worker）は inspect.signature で引数を確かめる。包みが元の関数の引数の形を見せるようにする
    functools.update_wrapper(correct_line, ce.correct_line)
    ce.correct_line = correct_line


def uninstall():
    import correction_entry as ce
    fn = _orig.pop('correct_line', None)
    if fn is not None and ce.correct_line is correct_line:
        ce.correct_line = fn
    correct_line.__dict__.pop('__wrapped__', None)
