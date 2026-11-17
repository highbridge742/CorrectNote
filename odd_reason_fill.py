"""理由の文の無い紫を見直し、残す紫には理由の文を付ける（2026-11-14 補正担当・全体評価の方針 v2 の K・M）。

なぜ
----
紫の中に、理由の文の無いもの（辞書の段の中で付いた紫）が在る。理由の無い紫は、うにが画面で見て何が変なのか分からない。
また、メモの普通の書き方に付いた紫も在る（作った例: 煮込みする・開け閉めする・謙譲語・りんご・みかん・バナナ）。

どうやって
----------
既存のファイルは変えない。install() が correction_entry.correct_line を外から包む（答えが出た後に見る）。
理由の無い紫ごとに、元の行を解析して:
1. K: 紫が「名詞か動詞の連用形＋する」だけで、その名詞・動詞が辞書の1語なら外す（メモで動詞を名詞＋する で書く形）。
2. M: 紫が「・」で並べた語の1つの中に在り、その語が辞書の1語の名詞なら外す。
   常用外の字だけが理由の紫（kanji_doubt）も、並べた語の中で辞書の1語なら外す（常用外の字だけを理由にしない）。
3. 紫がちょうど辞書の1語の漢字2字以上の名詞で、すぐ後ろに接尾の語が付く（謙譲｜語・開口｜部）なら外す。
4. 残った理由の無い紫には、一般の理由の文を付ける。
書き換え（corrected）は変えない。特定の語や文字列には合わせない。

5. G: 直し先を決められず元の語に残した紫（文の形が続かない・隣のキー）で、紫の所の語がどれも
   辞書の語、隣に打ち違いの跡が無く、行の並びが切れていないなら外す（CN_ODD_REASON_UNDECIDED=0 で前のまま）。

7. R: お・ご＋連用形＋ください、拝＋漢字1字の漢語（CN_ODD_REASON_KEIGO=0）。S: 英大文字・数字・ハイフンの型番（CN_ODD_REASON_CODE=0）。
   T: 地名＋県・市・区・町・村（CN_ODD_REASON_PLACE=0）。どれも紫を付けない。
6. P: 行が名詞・接頭・数・記号だけ（見出し・ラベル）で、どの語も辞書の語なら紫を付けない（CN_ODD_REASON_LABEL=0）。

切り替え: CN_ODD_REASON_FILL=0 で前のまま（4 だけ止めるのは CN_ODD_REASON_TEXT=0）。
"""
import functools
import os

_orig = {}

GENERIC = '前後の語とのつながりが辞書で確かめられません'
_JOYO_OUT = '常用漢字の外の字'

# 直し先を決められなかった・採らなかった時に元の語へ残す紫の理由（全体評価の方針 v2 の F・G）
# F（1語・短い行のあまり使わない語）は名詞だけの行の P で見る。助詞の在る行の同音の選び違い（会議の死霊）は紫のまま
_UNDECIDED = ('直すと文の形が続かないので、直し先を決められない',
              'かな入力で隣のキーを打ったか')


# 弱い理由（打ち違いの見立てを言わない理由: 珍しい・組が少ない・品詞が分からない・決められなかった・片仮名の交じり・
# 常用外）。これだけの紫を P・G・R・S・T・M などの形で外してよい。何が何の打ち違いか・並べる記号か・隣のキー・抜け・
# 入れ替え などの見立てを言う理由が1つでも掛かる紫は、どの形でも残す（2026-11-14 全体評価）。一覧に無い理由は具体と見る
_WEAK_REASON = ('あまり使わない語です', GENERIC, '品詞として識別できない', '異様だと見たが、直し先を決められなかった',
                '直すと文の形が続かないので、直し先を決められない', 'は続けて置けない', '片仮名が混じっています',
                _JOYO_OUT, '組が例文に無いので決められない')


# 語の珍しさ・組ではなく、字の並びの形そのものを見た理由（前後の文が無くても打ち消されない）
_SHAPE_REASON = ('並べる「か」かもしれません', '「゛」「゜」の付く字がありません')


def _all_weak(texts):
    return all(any(k in t for k in _WEAK_REASON) for t in texts)


def _undecided(texts):
    return bool(texts) and all(any(k in t for k in _UNDECIDED) for t in texts)


_CODE = __import__('re').compile(r'[A-ZＡ-Ｚ0-9０-９][A-ZＡ-Ｚ0-9０-９\-－‐]*[A-ZＡ-Ｚ0-9０-９]')


def code_runs(line):
    """英大文字・数字・ハイフンだけで出来た並び（型番・略号: UD-27K）で、英字と数字の両方を含む所 [(始め, 終わり)]"""
    out = []
    for m in _CODE.finditer(line):
        t = m.group()
        if any(c.isdigit() for c in t) and any(c.isalpha() for c in t):
            a, b = m.start(), m.end()
            # 前後が英小文字につながる（英文の語の一部）なら見ない
            if (a > 0 and line[a - 1].isascii() and line[a - 1].isalpha()) or (b < len(line) and line[b].isascii() and line[b].isalpha()):
                continue
            out.append((a, b))
    return out


def _keigo_form(toks, a, b):
    """R: お・ご＋動詞の連用形＋ください（お申しつけください）と、拝＋漢字1字の漢語（拝受・拝読）は敬語の定型"""
    inside = [t for t in toks if t.end > a and t.start < b]
    if not inside:
        return False
    for n, t in enumerate(toks):
        if (t.pos == '接頭詞' and t.surface in ('お', 'ご', '御') and n + 2 < len(toks)
                and toks[n + 1].pos == '動詞' and (toks[n + 1].infl_form or '').startswith('連用')
                and toks[n + 2].surface.startswith('くださ') and _dict_entries(toks[n + 1].surface)):
            if t.start <= a and b <= toks[n + 2].end:
                return True
    first = inside[0]
    if (first.pos == '名詞' and len(first.surface) == 2 and first.surface[0] == '拝' and _kanji(first.surface)
            and _dict_noun(first.surface)):
        rest = inside[1:]
        return all(x.pos in ('動詞', '助動詞') and (x.base_form == 'する' or x.pos == '助動詞') for x in rest)
    return False


def _place_name(toks, a, b):
    """T: 地名＋県・市・区・町・村 の並びだけ（福岡県福岡市）"""
    inside = [t for t in toks if t.end > a and t.start < b]
    if not inside:
        return False
    run = [t for t in toks if str(t.pos_sub or '').startswith(('固有名詞:地域', '接尾:地域'))]
    if not all(t in run for t in inside):
        return False
    # 県・市 などは、すぐ前が地名の時だけ地名の続き（行の頭や括弧の後ろの 区 は切れ端）
    for t in inside:
        if str(t.pos_sub or '').startswith('接尾:地域'):
            n = toks.index(t)
            if n == 0 or not str(toks[n - 1].pos_sub or '').startswith('固有名詞:地域') or toks[n - 1].end != t.start:
                return False
    if not str(inside[0].pos_sub or '').startswith('固有名詞:地域'):
        return False
    return any(str(t.pos_sub or '').startswith('接尾:地域') and t.surface in ('都', '道', '府', '県', '市', '区', '町', '村', '郡')
               for t in run if t.start >= a - 4 and t.end <= b + 2)


def _label_cell(line, a, b):
    """タブ区切りの行で、a:b が1つの欄の中に収まり、その欄が見出し・ラベルの書き方（_label_line）か。"""
    if os.environ.get('CN_ODD_REASON_LABEL_CELL') == '0' or '\t' not in line:
        return False
    s0 = line.rfind('\t', 0, a) + 1
    e0 = line.find('\t', b)
    e0 = len(line) if e0 < 0 else e0
    if '\t' in line[a:b]:
        return False
    cell = line[s0:e0]
    if not cell.strip():
        return False
    try:
        from morphology import tokenize
        return _label_line(list(tokenize(cell)))
    except Exception:
        return False


def _label_line(toks):
    """行が名詞・接頭・数・記号だけで出来ていて（見出し・ラベルの書き方）、どの語も辞書の語として読めるか
    （全体評価の方針 v2 の P）。1字の切れ端は名詞か接尾として立つ時だけ"""
    words = [t for t in toks if t.pos != '記号']
    if not words or not all(t.pos in ('名詞', '接頭詞') for t in words):
        return False
    for t in words:
        sub = str(t.pos_sub or '')
        if not getattr(t, 'has_reading', True):
            return False
        if sub.startswith('数'):
            continue
        if any(c.isascii() and c.isalpha() or 'ａ' <= c <= 'ｚ' or 'Ａ' <= c <= 'Ｚ' for c in t.surface):
            return False
        if t.pos == '接頭詞' or sub.startswith('接尾'):
            continue
        if not _dict_entries(t.surface):
            return False
    return True


def _plain_dict_span(line, toks, a, b):
    """紫の所の語がどれも辞書の語で、隣も打ち違いの跡でなく、行の並びが切れていないか（dict_word_keep と同じ見方）"""
    try:
        import dict_word_keep as K
    except Exception:
        return False
    hit = [t for t in toks if t.start < b and a < t.end]
    if not hit or not all(K._dict_word(t) for t in hit):
        return False
    if not any(t.pos in ('名詞', '動詞', '形容詞', '副詞', '形容動詞') for t in hit):
        return False
    n0, n1 = toks.index(hit[0]), toks.index(hit[-1])
    side = toks[max(0, n0 - 1):n0] + toks[n1 + 1:n1 + 2]
    if any(K._latin(t.surface) or t.pos in ('感動詞', 'フィラー', 'その他') or not getattr(t, 'has_reading', True)
           for t in side):
        return False
    if K._verb_run(toks[max(0, n0 - 1):n1 + 2]):
        return False
    return not K._breaks(line, hit[0].start, hit[-1].end)


def _on():
    return os.environ.get('CN_ODD_REASON_FILL') != '0'


def _kanji(s):
    return bool(s) and all('一' <= c <= '鿿' or c in '々' for c in s)


def _dict_entries(surface):
    try:
        from morphology import dictionary_inflections
        return [r for r in dictionary_inflections(surface) or () if r[2] == surface or r[1] != '*']
    except Exception:
        return []


def _dict_noun(surface):
    return any(r[0].startswith('名詞,') and not r[0].startswith(('名詞,固有名詞', '名詞,接尾', '名詞,非自立', '名詞,数'))
               and r[2] == surface for r in _dict_entries(surface))


def _dict_stem(t):
    """する の前に立つ語: 辞書の1語の名詞か、辞書に在る動詞の連用形"""
    if t.pos == '名詞':
        return _dict_noun(t.surface)
    if t.pos == '動詞' and (t.infl_form or '').startswith('連用'):
        return any(r[0].startswith('動詞,') and (r[1] or '').startswith('連用') for r in _dict_entries(t.surface))
    return False


def _suru_form(line, toks, a, b):
    inside = [t for t in toks if t.end > a and t.start < b]
    if len(inside) < 2 or inside[0].start != a or inside[-1].end != b:
        return False
    last = inside[-1]
    if last.pos != '動詞' or last.base_form != 'する':
        return False
    return all(_dict_stem(t) for t in inside[:-1])


_SEP = '・･'
_EDGE = ' 　、。，．,.！？!?（）()「」『』'


def _list_item(line, a, b):
    """紫の所を含む「・」で並べた語（前か後ろが ・）。無ければ None"""
    s = a
    while s > 0 and line[s - 1] not in _SEP and line[s - 1] not in _EDGE:
        s -= 1
    e = b
    while e < len(line) and line[e] not in _SEP and line[e] not in _EDGE:
        e += 1
    if not ((s > 0 and line[s - 1] in _SEP) or (e < len(line) and line[e] in _SEP)):
        return None
    if any(c in _SEP or c in _EDGE for c in line[a:b]):
        return None
    return line[s:e]


def _suffixed_noun(toks, a, b):
    inside = [t for t in toks if t.end > a and t.start < b]
    if len(inside) != 1 or inside[0].start != a or inside[0].end != b:
        return False
    t = inside[0]
    if t.pos != '名詞' or len(t.surface) < 2 or not _kanji(t.surface) or not _dict_noun(t.surface):
        return False
    nxt = next((x for x in toks if x.start == b), None)
    if nxt is None or nxt.pos != '名詞' or not str(nxt.pos_sub or '').startswith('接尾'):
        return False
    # 接尾の語の後ろで語が終わる（助詞・記号・助動詞か行末）時だけ。後ろに名詞が続く（流布｜委｜書類）のは崩れた並び
    after = next((x for x in toks if x.start == nxt.end), None)
    return after is None or after.pos in ('助詞', '記号', '助動詞')


def _parallel_pair(toks, a, b):
    hit = [k for k, t in enumerate(toks) if t.start == a and t.end == b]
    if not hit:
        return False
    k = hit[0]
    t = toks[k]
    if t.pos != '名詞' or len(t.surface) != 2 or not _kanji(t.surface) or not _dict_noun(t.surface):
        return False
    for j in (k - 1, k + 1):
        if 0 <= j < len(toks):
            u = toks[j]
            if (u.pos == '名詞' and len(u.surface) == 2 and _kanji(u.surface) and u.surface != t.surface
                    and u.surface[0] == t.surface[0] and _dict_noun(u.surface)
                    and (u.end == t.start or t.end == u.start)):
                return True
    return False


def _joined_word(toks, a, b):
    """[a, b) がちょうど漢字を含む2つの名詞で、読みをつないだものが同梱の表の語の読みか。"""
    inside = [t for t in toks if a <= t.start and t.end <= b]
    if len(inside) != 2 or inside[0].start != a or inside[1].end != b or inside[0].end != inside[1].start:
        return False
    if any(t.pos != '名詞' or not t.reading for t in inside):
        return False
    if not any('一' <= c <= '鿿' for t in inside for c in t.surface):
        return False
    rd = ''.join(t.reading for t in inside)
    rd = ''.join(chr(ord(c) - 0x60) if 'ァ' <= c <= 'ヶ' else c for c in rd)
    try:
        import corrector
        corrector._table_readings_for_surface('仮名')
        spells = [w for _c, w in (corrector._TABLE_SURFACES or {}).get(rd) or ()]
    except Exception:
        return False
    # 表の表記が、片方の語はそのまま・もう片方はかなで書いた形（カギ＋括弧）のときだけ。両方とも別の漢字（期間車 ←
    # 機関車）は変換の選び違いなので紫のまま
    x, y = inside
    kana = lambda w: w and all('ぁ' <= c <= 'ゖ' or 'ァ' <= c <= 'ヶ' or c == 'ー' for c in w)
    for w in spells:
        if w.endswith(y.surface) and kana(w[:len(w) - len(y.surface)]):
            return True
        if w.startswith(x.surface) and kana(w[len(x.surface):]):
            return True
    return False


def fill(line, result):
    if not _on() or not isinstance(line, str) or not isinstance(result, dict):
        return result
    odd = [x for x in result.get('odd_spans') or () if len(x) >= 2 and isinstance(x[0], int)]
    if not odd:
        return result
    reasons = [x for x in result.get('odd_reasons') or () if len(x) >= 2 and isinstance(x[0], int)]
    why = {}
    for x in reasons:
        if len(x) >= 3 and isinstance(x[2], str) and x[2]:
            why.setdefault(tuple(x[:2]), []).append(x[2])
    done = result.get('corrected') or line
    try:
        from morphology import tokenize
        toks = list(tokenize(line))
    except Exception:
        return result
    drop, add, narrowed = set(), [], []
    label_line = done == line and _label_line(toks)
    for x in odd:
        a, b = x[0], x[1]
        key = (a, b)
        texts = why.get(key, [])
        # 重なる紫の理由も見る（同じ所に具体の見立てが在れば外さない）
        over = [t for (s0, e0), ts in why.items() if s0 < b and a < e0 for t in ts]
        # AD（前）: 隣のキーの見立ての紫も、名詞＋動詞の連用形の語（右詰め）にちょうど掛かるなら外す（下の AD と同じ）
        if (over and all(t.endswith(KEYSLIP_TAIL) or t == GENERIC or 'は続けて置けない' in t for t in over)
                and done == line and _noun_renyo(toks, a, b)):
            drop.add(key)
            continue
        if os.environ.get('CN_ODD_REASON_WEAK_ONLY') != '0' and not _all_weak(over):
            # 外さない紫でも、理由の文が無ければ一般の理由を付ける（重なる紫の理由はその紫のもの）
            if not texts:
                add.append(key)
            continue
        # 書き換えた所に掛かる紫は、元の行の形では見ない
        if done != line and line[a:b] != done[a:b]:
            if not texts:
                add.append(key)
            continue
        # H: 書き換えの無い行で、どの段も理由を付けていない紫（入口の本体の判定だけ）が、語2つ以上にわたって行の中身の
        # 全部に掛かるなら、裏付けの無い紫で行全体を疑うのは根拠が足りない（長さだけの決まりではなく、理由の無さと組にした扱い。
        # 弱い理由の紫まで外すと作った誤字692行のうち9行が紫を失ったので、理由の無い紫・行全体に限る。2026-11-15 全体評価の方針 1）。CN_ODD_REASON_WIDE_WEAK=0 で前のまま
        if (done == line and not over and os.environ.get('CN_ODD_REASON_WIDE_WEAK') != '0'
                and _wide_weak(line, toks, a, b)):
            drop.add(key)
            narrowed += _wide_slips(toks, a, b)
            continue
        reasonless = not texts
        joyo_only = bool(texts) and all(_JOYO_OUT in t for t in texts) and _all_weak(over)
        if reasonless and os.environ.get('CN_ODD_REASON_SURU') != '0' and _suru_form(line, toks, a, b):
            drop.add(key)
            continue
        if (reasonless or joyo_only) and os.environ.get('CN_ODD_REASON_LIST') != '0':
            item = _list_item(line, a, b)
            if item and _dict_noun(item):
                drop.add(key)
                continue
        # P: 名詞と接尾だけの見出し・ラベルの行で、どの語も辞書の語なら、組の少なさ・珍しさ・片仮名の交じりを紫の理由にしない
        # CN_ODD_REASON_LABEL=0 で前のまま
        # 紫が記号に掛かる所（片仮名の語のあいだの＊）は語の組の話ではないので見ない
        # タブで区切った表の行では、紫の掛かる1つの欄をそれだけで見る（副詞<TAB>主に連用修飾語になる の 副詞 は、
        # 1語だけの行と同じく見出しの語。2026-11-15 うに「49行目が問題ないのに、50や51に紫がつく」）。CN_ODD_REASON_LABEL_CELL=0 で前のまま
        if (os.environ.get('CN_ODD_REASON_LABEL') != '0' and (label_line or (done == line and _label_cell(line, a, b)))
                and not any(t.pos == '記号' for t in toks if t.start < b and a < t.end)):
            drop.add(key)
            continue
        # R・S・T: 敬語の定型・型番・地名の並び。CN_ODD_REASON_KEIGO / _CODE / _PLACE =0 で前のまま
        if os.environ.get('CN_ODD_REASON_KEIGO') != '0' and _keigo_form(toks, a, b):
            drop.add(key)
            continue
        if os.environ.get('CN_ODD_REASON_CODE') != '0' and any(s0 <= a and b <= e0 for s0, e0 in code_runs(line)):
            drop.add(key)
            continue
        if os.environ.get('CN_ODD_REASON_PLACE') != '0' and _place_name(toks, a, b):
            drop.add(key)
            continue
        # F・G: 直し先を決められず元の語に残した紫で、元の語が辞書の語のまま行が続くなら紫にしない。CN_ODD_REASON_UNDECIDED=0 で前のまま
        if (not reasonless and os.environ.get('CN_ODD_REASON_UNDECIDED') != '0' and _undecided(texts)
                and _plain_dict_span(line, toks, a, b)):
            drop.add(key)
            continue
        # V: 頭の字が同じ漢字2字の名詞が2つ並ぶ並列の複合（産前｜産後・入学前｜入学後 の型）で、紫がその片方に
        # ちょうど掛かり、どちらも辞書の語なら、珍しさ・組の少なさを紫の理由にしない（2026-11-14 補正担当、
        # 未解決タブ34行目の型）。CN_ODD_REASON_PARALLEL=0 で前のまま
        if (not reasonless and os.environ.get('CN_ODD_REASON_PARALLEL') != '0' and _parallel_pair(toks, a, b)):
            drop.add(key)
            continue
        # W: 理由が無いか「辞書で確かめられません」だけの紫が、かなの表記のまま辞書に載る語（いっぽう・ところ）とその後ろの
        # 助詞だけに掛かるなら、かなで書いた正しい語（2026-11-14 未解決タブの正しい文）。CN_ODD_REASON_KANA_ENTRY=0 で前のまま
        if ((reasonless or all(GENERIC in t for t in texts)) and os.environ.get('CN_ODD_REASON_KANA_ENTRY') != '0'
                and _kana_entry_span(toks, a, b)):
            drop.add(key)
            continue
        # X: 「A」と「B」は続けて置けない の紫が、言い切りの動詞 A と、解析が動詞の連用形と見た B（名詞としても同じ表記で
        # 辞書に載る: 決まり・集まり）の2語だけに掛かり、B の後ろが行の終わりか助詞・記号なら、動詞が名詞を修飾する形
        # （後で守る決まり）。解析の品詞の取り違いなので紫にしない（2026-11-14 作った正しい文）。CN_ODD_REASON_VERB_NOUN=0 で前のまま
        if (texts and all('は続けて置けない' in t for t in texts) and os.environ.get('CN_ODD_REASON_VERB_NOUN') != '0'
                and _verb_then_noun(toks, a, b)):
            drop.add(key)
            continue
        # Y: 「感動詞」と「って」は続けて置けない の紫が、感動詞＋って（ば）だけに掛かる所は、呼び掛けを繰り返す話し言葉
        # （作った正しい文: ねえってばー）。CN_ODD_REASON_INTERJ_TTE=0 で前のまま
        if (texts and all('は続けて置けない' in t for t in texts) and os.environ.get('CN_ODD_REASON_INTERJ_TTE') != '0'
                and _interj_tte(toks, a, b)):
            drop.add(key)
            continue
        # Z: 「A」と「B」は続けて置けない の紫が、格の助詞のすぐ後ろで、解析がかなの和語の動詞（よける）を 助詞＋動詞の切れ端
        # （よ｜ける）に切った所に掛かるなら、切れ端をつないだ読みが辞書の動詞（除ける・避ける）。解析の切り違いなので紫にしない
        # （2026-11-14 作った正しい文）。CN_ODD_REASON_KANA_VERB=0 で前のまま
        if (texts and all('は続けて置けない' in t for t in texts) and os.environ.get('CN_ODD_REASON_KANA_VERB') != '0'
                and _split_kana_verb(toks, a, b)):
            drop.add(key)
            continue
        # AD: 隣のキー・つながり・続けて置けない の紫が、身近な名詞＋動詞の連用形の語（右詰め）にちょうど掛かるなら、
        # 名詞＋連用形の複合語（2026-11-16 うに 未解決タブの正しい文）。CN_ODD_REASON_NOUN_RENYO=0 で前のまま
        if (texts and all(t.endswith(KEYSLIP_TAIL) or t == GENERIC or 'は続けて置けない' in t for t in texts)
                and done == line and _noun_renyo(toks, a, b)):
            drop.add(key)
            continue
        # AE: 理由が無いか「辞書で確かめられません」だけの紫が、漢字2字のサ変の名詞（動作を言う語: 打鍵・反証）1つに
        # ちょうど掛かり、表に在る語（ime_reconvert の順位 800 未満）で、隣に打ち違いの跡が無いなら、あまり使わないだけの
        # 正しい語（2026-11-16 うに 未解決タブの正しい文）。既定オン（batch597、CN_ODD_REASON_SAHEN_WORD=0 で前のまま）。前は既定オフだった: 692行で
        # IME の選び違いの珍しいサ変の語（下達・流布）の紫が2行消えた。順位では打鍵・反証と分けられない
        if ((reasonless or all(t == GENERIC for t in texts)) and done == line
                and os.environ.get('CN_ODD_REASON_SAHEN_WORD') != '0' and _sahen_word(toks, a, b)
                # 行にほかの紫が在れば、隣に打ち違いの跡が在る見込み（2026-11-17 batch599: 短い束の 名詞＋は＋名詞 の打ち違い）
                and not any(tuple(y[:2]) != key for y in odd)
                and _plain_dict_span(line, toks, a, b)):
            drop.add(key)
            continue
        # AC: 「A」と「B」は続けて置けない の紫が、漢字だけの辞書の名詞2つにちょうど掛かるなら、名詞をつないだ複合語
        # （2026-11-16 うに 未解決タブの正しい文）。CN_ODD_REASON_NOUN_PAIR=0 で前のまま
        if (texts and all('は続けて置けない' in t for t in texts) and done == line and _noun_pair(toks, a, b)):
            drop.add(key)
            continue
        # AA: 「A」と「B」は続けて置けない の紫が、名詞＋動詞の連用形の漢字で出来た語（様子見）＋する だけに掛かるなら、
        # その名詞はする を付けて使う（2026-11-16 うに: かなで打った正しい文の紫）。CN_ODD_REASON_VERB_TAIL_SURU=0 で前のまま
        if (texts and all('は続けて置けない' in t for t in texts) and done == line and _verb_tail_suru(toks, a, b)):
            drop.add(key)
            continue
        # AF: 「AとBは続けて置けない」だけの紫が、2つの名詞をつないだ読みが同梱の表の1語の読み（表記違い: 鍵括弧 →
        # かぎかっこ＝カギ括弧・鉤括弧）になる所なら外す（2026-11-17 補正担当、うに: 以前紫の無かった 鍵括弧で閉じる）。
        # CN_ODD_REASON_JOINED_WORD=0 で前のまま
        if (texts and all('は続けて置けない' in t for t in texts) and done == line
                and os.environ.get('CN_ODD_REASON_JOINED_WORD') != '0' and _joined_word(toks, a, b)):
            drop.add(key)
            continue
        # AB: 理由が無いか「辞書で確かめられません」だけの紫が、動作の名詞＋状態の語の複合語（判定不能）の後ろの語なら紫にしない
        # （2026-11-16 うに: かなで打った正しい文の紫）。CN_ODD_REASON_ACTION_STATUS=0 で前のまま
        if ((reasonless or all(t == GENERIC for t in texts)) and done == line and _action_status(toks, a, b)):
            drop.add(key)
            continue
        if reasonless and os.environ.get('CN_ODD_REASON_SUFFIXED') != '0' and _suffixed_noun(toks, a, b):
            drop.add(key)
            continue
        if reasonless:
            add.append(key)
    if not drop and (not add or os.environ.get('CN_ODD_REASON_TEXT') == '0'):
        return result
    out = dict(result)
    if drop:
        def keep(x):
            return not (len(x) >= 2 and isinstance(x[0], int) and tuple(x[:2]) in drop)
        for k in ('odd_spans', 'unsure_spans'):
            if k in result:
                out[k] = [x for x in result.get(k) or () if keep(x)]
        out['odd_reasons'] = [x for x in reasons if keep(x)]
    if add and os.environ.get('CN_ODD_REASON_TEXT') != '0':
        out['odd_reasons'] = list(out.get('odd_reasons') if 'odd_reasons' in out else reasons) + [
            (a, b, GENERIC) for a, b in add if (a, b) not in drop]
    have = [tuple(x[:2]) for x in out.get('odd_spans') or ()]
    narrowed = [(s0, e0, w) for s0, e0, w in narrowed if not any(x < e0 and s0 < y for x, y in have)]
    if narrowed:
        out['odd_spans'] = sorted(set(have) | {(s0, e0) for s0, e0, _ in narrowed})
        out['odd_reasons'] = list(out.get('odd_reasons') if 'odd_reasons' in out else reasons) + list(narrowed)
    return out


LONE_MARK = '「゛」「゜」の付く字がありません'
KATA_ONE = '片仮名1字が混じっています'


def _wide_slips(toks, a, b):
    """H で行全体の理由の無い紫を外す時、その中の打ち違いの跡がはっきりした語だけは紫に残す: 濁点・半濁点だけの語（゛゜）と、
    解析が読みを付けられない1字（ギ）。どちらも正しい文には立たない（2026-11-17 補正担当: PC では行全体の紫しか無い行で、
    紫が全部外れていた）。珍しい語・かなの1字は見ない（正しい文の紫を戻さない）。CN_ODD_REASON_WIDE_SLIP=0 で前のまま"""
    if os.environ.get('CN_ODD_REASON_WIDE_SLIP') == '0':
        return []
    out = []
    for t in toks:
        if not (a <= t.start and t.end <= b):
            continue
        s = t.surface or ''
        if _lone_mark(t):
            out.append((t.start, t.end, LONE_MARK))
        elif (len(s) == 1 and not getattr(t, 'has_reading', True) and t.pos != '記号'
              and not (s.isascii() or 'ａ' <= s.lower() <= 'ｚ')):
            out.append((t.start, t.end, KATA_ONE if 'ァ' <= s <= 'ヺ' else GENERIC))
    return out


IME_FIELD = 'IME候補に原文があり、復元した読みの接続が異様です'


def _rare_token(t, toks):
    if os.environ.get('CN_ODD_REASON_IME_FIELD_RARE') == '0':
        return False
    try:
        import ime_reconvert as R
        if R._token_rarity(t, toks) < R.DOUBT_MARK:
            return False
        return not _familiar_parts(t.surface, R) and not _name_of_common_chars(t, R)
    except Exception:
        return False


def _name_of_common_chars(t, R):
    """解析が固有名詞（姓など）と読んだ漢字だけの語で、1字ずつがどれも身近な語（上・中）なら、字を並べた書き方
    （上中下）を名前と取り違えただけとみて、珍しい語と数えない（2026-11-17 うに 誤判定: 上中下 に紫）。
    CN_ODD_REASON_IME_FIELD_NAME_CHARS=0 で前のまま"""
    if os.environ.get('CN_ODD_REASON_IME_FIELD_NAME_CHARS') == '0':
        return False
    face = t.surface or ''
    if not str(t.pos_sub or '').startswith('固有名詞') or len(face) < 2 or not _han(face):
        return False
    try:
        import odd_respell as O
        return all(R._rank(c) <= O.COMMON_NEW for c in face)
    except Exception:
        return False


def _familiar_parts(face, R):
    """漢字だけの珍しい語が、解析で身近な部品（接頭＋名詞・名詞＋接尾の形）に分かれるか。部品の一番珍しいものの値で
    読み、どれも身近（odd_respell.COMMON_NEW 以内）なら珍しい語と数えない（2026-11-15 全体評価の方針、未解決タブ
    42・49行目）。語の一覧は作らない。CN_ODD_REASON_IME_FIELD_PARTS=0 で前のまま"""
    if os.environ.get('CN_ODD_REASON_IME_FIELD_PARTS') == '0' or not _han(face) or len(face) < 2:
        return False
    try:
        from morphology import tokenize
        import odd_respell as O
    except Exception:
        return False
    parts = [p for p in tokenize(face)]
    if len(parts) < 2 or ''.join(p.surface for p in parts) != face:
        return False
    return all(_han(p.surface) and R._rank(p.surface) <= O.COMMON_NEW for p in parts)


def _inflected_one(t):
    """1字のかなが、活用する語の活用した形（する の し）か。浮いたかなではない。CN_ODD_REASON_IME_FIELD_INFLECT=0 で前のまま"""
    if os.environ.get('CN_ODD_REASON_IME_FIELD_INFLECT') == '0':
        return False
    base = getattr(t, 'base_form', '') or ''
    return t.pos in ('動詞', '形容詞') and len(base) >= 2 and base != t.surface


def _kata(s):
    return bool(s) and all('ァ' <= c <= 'ヶ' or c == 'ー' for c in s)


def _han(s):
    return bool(s) and all('一' <= c <= '鿿' or c == '々' for c in s)


def _glued_kata(toks):
    """漢字の名詞に前後を挟まれた片仮名の名詞（赤トン下）の位置。名詞が助詞を挟まず続き、つないだ形が辞書に無い時だけ
    （ローマ字・かなの打ち違いが漢字変換の間に片仮名の切れ端として残った形）。CN_ODD_REASON_IME_FIELD_GLUED=0 で見ない"""
    if os.environ.get('CN_ODD_REASON_IME_FIELD_GLUED') == '0':
        return []
    out = []
    for i in range(1, len(toks) - 1):
        p, t, q = toks[i - 1], toks[i], toks[i + 1]
        if not all(x.pos == '名詞' for x in (p, t, q)) or p.end != t.start or t.end != q.start:
            continue
        if not (_kata(t.surface) and _han(p.surface) and _han(q.surface)):
            continue
        try:
            if _dict_entries(p.surface + t.surface + q.surface) or _dict_entries(p.surface + t.surface):
                continue
        except Exception:
            continue
        out.append((p.start, q.end))
    return out


def _lone_mark(t):
    """濁点・半濁点だけの語（゛・゜）。文の中に濁点だけが立つのは、かな入力で ゛ の1打が前の字に付かなかった跡なので、
    IME の欄の紫を狭めても残す（2026-11-17 補正担当・未解決タブ、PC では行の紫が全部外れていた）。
    CN_ODD_REASON_IME_FIELD_MARK=0 で前のまま"""
    if os.environ.get('CN_ODD_REASON_IME_FIELD_MARK') == '0':
        return False
    s = t.surface or ''
    return bool(s) and all(c in '゛゜\u3099\u309aﾞﾟ' for c in s)


def _nominalizer(t):
    """名詞の非自立の1字（出てくる｜の｜は の の）は、前の句を名詞にする語で、崩れた切れ端ではない
    （2026-11-17 うに 誤判定）。CN_ODD_REASON_IME_FIELD_NO=0 で前のまま"""
    return (os.environ.get('CN_ODD_REASON_IME_FIELD_NO') != '0' and t.pos == '名詞'
            and str(t.pos_sub or '').startswith('非自立'))


def narrow_ime_field(line, result):
    """I: 「IME候補に原文があり、復元した読みの接続が異様です」だけの紫が、書き換えの無い行の中身全部に掛かる時は、
    行の中の疑わしい語（解析が読みを付けられない語・助詞でも助動詞でもない1字のかな）だけに狭める。無ければ外す。
    この理由は「今の形が IME の候補に在る」（今の形を支える）と「読みを戻すと接続が異様」（疑う）が同居していて、
    行全体を1つの紫にする根拠としては足りない（2026-11-15 全体評価の方針、未解決タブ41・42行目）。CN_ODD_REASON_IME_FIELD=0 で前のまま"""
    if os.environ.get('CN_ODD_REASON_IME_FIELD') == '0' or not isinstance(result, dict):
        return result
    if (result.get('corrected') or line) != line or not result.get('odd_spans'):
        return result
    reasons = [r for r in result.get('odd_reasons') or () if len(r) >= 3]
    from morphology import tokenize
    toks = list(tokenize(line))
    change = {}
    kept = {}
    for x in result['odd_spans']:
        a, b = x[0], x[1]
        texts = [r[2] for r in reasons if r[0] < b and a < r[1]]
        inner = []
        if (texts and not all(t == IME_FIELD for t in texts) and os.environ.get('CN_ODD_REASON_IME_FIELD_MIXED') != '0'
                and any(r[2] == IME_FIELD and (r[0], r[1]) == (a, b) for r in reasons)):
            # 行ぜんたいの IME の欄の紫の中に、ほかの理由の小さな紫も在る（長い行で起きやすい）。ほかの理由はその所だけに
            # 残し、IME の欄の紫は同じように狭める（2026-11-16 うに: 句点のない長い文の全体に紫）。
            # CN_ODD_REASON_IME_FIELD_MIXED=0 で前のまま（ほかの理由が在れば狭めない）
            inner = [r for r in reasons if r[2] != IME_FIELD and a <= r[0] and r[1] <= b and (r[0], r[1]) != (a, b)]
            if len(inner) != len([r for r in reasons if r[2] != IME_FIELD and r[0] < b and a < r[1]]):
                continue
        elif not texts or not all(t == IME_FIELD for t in texts):
            continue
        part_only = False
        if not _wide_weak(line, toks, a, b):
            # 行の一部だけの IME の欄の紫も、中に疑わしい語が1つも無ければ外す（疑わしい語が在れば今のまま）
            # （2026-11-17 うに 誤判定: 上中下 に紫）。CN_ODD_REASON_IME_FIELD_PART=0 で前のまま
            if inner or os.environ.get('CN_ODD_REASON_IME_FIELD_PART') == '0':
                continue
            part_only = True
        bad = [t for t in toks if a <= t.start and t.end <= b and (_lone_mark(t) or t.pos != '記号' and (
            (not getattr(t, 'has_reading', True) and not any(c.isascii() or 'ａ' <= c.lower() <= 'ｚ' for c in t.surface))
            or (len(t.surface) == 1 and 'ぁ' <= t.surface <= 'ゖ' and t.pos not in ('助詞', '助動詞')
                and not _inflected_one(t) and not _nominalizer(t))
            # 珍しい語（風位）も疑わしい語（ime_reconvert の紫の門 DOUBT_MARK 以上。2026-11-15 PC の release_check:
            # 添付の風位目 の紫を外して誤字の印を失った）
            or _rare_token(t, toks)))]
        got = [(t.start, t.end) for t in bad]
        if part_only and (got or any(g0 < b and a < g1 for g0, g1 in _glued_kata(toks))):
            continue
        # 片仮名の切れ端を挟んだ名詞の並び（赤トン下）は1つの紫にまとめる（2026-11-15 雲の束 two_same_word-17 で全部の紫を外した）
        for g0, g1 in _glued_kata(toks):
            if a <= g0 and g1 <= b:
                got = [x for x in got if not (g0 <= x[0] and x[1] <= g1)] + [(g0, g1)]
        for r in inner:
            if not any(x[0] <= r[0] and r[1] <= x[1] for x in got):
                got.append((r[0], r[1]))
        if inner:
            kept[(a, b)] = inner
            merged = []
            for x in sorted(set(got)):
                if merged and x[0] < merged[-1][1]:        # 重なる紫は1つにまとめる（理由はそれぞれの所のまま）
                    merged[-1] = (merged[-1][0], max(merged[-1][1], x[1]))
                else:
                    merged.append(tuple(x))
            got = merged
        change[(a, b)] = sorted(set(got))
    if not change:
        return result
    out = dict(result)
    spans, rs = [], []
    for x in result['odd_spans']:
        k = (x[0], x[1])
        if k in change:
            spans += [tuple(v) for v in change[k]]
        else:
            spans.append(x)
    for r in result.get('odd_reasons') or ():
        k = (r[0], r[1]) if len(r) >= 2 else None
        if k in change:
            inside = [(x[0], x[1]) for x in kept.get(k, ())]
            rs += [(s0, e0, IME_FIELD) for s0, e0 in change[k]
                   if not any(s0 <= i0 and i1 <= e0 for i0, i1 in inside)]
        elif any(r in kept.get(kk, ()) for kk in change):
            rs.append(r)
        elif not any(r[0] < kb and ka < r[1] for ka, kb in change):
            rs.append(r)
    out['odd_spans'] = spans
    out['odd_reasons'] = rs
    return out


FILLER_ONE = '文の途中に1字が混じっています'


def drop_filler_in_word(line, result):
    """J: 「文の途中に1字が混じっています」だけの紫で、解析がかなの1字をフィラー・感動詞に読んだ所（まど の ま・
    つくえ の え）が、かなの並びを読みの格子で切ると2字以上の語の中に入るなら、解析の切り違い。紫にしない
    （2026-11-15 全体評価、かなで打った正しい文の紫）。書き換えの無い行だけ。CN_ODD_REASON_FILLER_WORD=0 で前のまま"""
    if os.environ.get('CN_ODD_REASON_FILLER_WORD') == '0' or not isinstance(result, dict):
        return result
    if (result.get('corrected') or line) != line or not result.get('odd_spans'):
        return result
    import re
    from morphology import tokenize
    try:
        import reading_lattice as L
    except Exception:
        return result
    reasons = [r for r in result.get('odd_reasons') or () if len(r) >= 3]
    toks = list(tokenize(line))
    drop = set()
    for x in result['odd_spans']:
        a, b = x[0], x[1]
        texts = [r[2] for r in reasons if r[0] < b and a < r[1]]
        if not texts or not all(t == FILLER_ONE for t in texts):
            continue
        ones = [t for t in toks if a <= t.start < b and len(t.surface) == 1 and t.pos in ('フィラー', '感動詞')]
        if not ones:
            continue
        ok = True
        for t in ones:
            m = next((m for m in re.finditer('[ぁ-ゖー]+', line) if m.start() <= t.start < m.end()), None)
            if m is None:
                ok = False
                break
            at, inside = m.start(), False
            for w in L.best(m.group()).words:
                n = len(w[1])
                if at <= t.start < at + n and n >= 2 and not w[2].startswith(('未知', '助詞', '助動詞', '感動', 'フィラ')):
                    inside = True
                at += n
            if not inside:
                ok = False
                break
        if ok:
            drop.add((a, b))
    if not drop:
        return result
    out = dict(result)
    out['odd_spans'] = [x for x in result['odd_spans'] if (x[0], x[1]) not in drop]
    out['odd_reasons'] = [r for r in result.get('odd_reasons') or () if not (len(r) >= 2 and (r[0], r[1]) in drop)]
    if 'unsure_spans' in result:
        out['unsure_spans'] = [x for x in result.get('unsure_spans') or () if (x[0], x[1]) not in drop]
    return out


_LINE_EDGE = ' \t\u3000、。，．,.！？!?'


def _compound_line(line):
    """行が、身近な語だけをつないだ名詞の複合語1つだけで出来ているか（前後に何も無い行）。漢字・片仮名だけの行で、
    解析の語がどれも名詞で、どれも身近な語（ime_reconvert の表で odd_respell.COMMON_NEW 以内）。1字の漢字も
    それ自体が身近な語なら部品として認める。返すのは語の所 (a, b)、当たらなければ None。"""
    a, b = 0, len(line)
    while a < b and line[a] in _LINE_EDGE:
        a += 1
    while b > a and line[b - 1] in _LINE_EDGE:
        b -= 1
    body = line[a:b]
    if len(body) < 2 or not all(_han(c) or _kata(c) or c == 'ー' for c in body):
        return None
    try:
        from morphology import tokenize
        import ime_reconvert as R
        import odd_respell as O
    except Exception:
        return None
    toks = [t for t in tokenize(body)]
    if not toks or ''.join(t.surface for t in toks) != body:
        return None
    for t in toks:
        if t.pos != '名詞' or R._rank(t.surface) > O.COMMON_NEW:
            return None
    return a, b


def drop_compound_line(line, result):
    """前後に何も無い行が、身近な語をつないだ名詞の複合語1つだけなら、その語への紫を外す（2026-11-15 全体評価の
    方針: 前後の無い行では語を疑う根拠が語そのものにしか無く、部品がどれも身近な語なら根拠は弱い）。部品に
    珍しい語が在る行・かなの交じる行は今のまま。直しの入った行は見ない。CN_ODD_REASON_COMPOUND_LINE=0 で前のまま。"""
    if os.environ.get('CN_ODD_REASON_COMPOUND_LINE') == '0' or not isinstance(result, dict):
        return result
    if (result.get('corrected') or line) != line or not result.get('odd_spans'):
        return result
    where = _compound_line(line)
    if where is None:
        return result
    a, b = where
    drop = {tuple(x[:2]) for x in result.get('odd_spans') or () if a <= x[0] and x[1] <= b}
    if os.environ.get('CN_ODD_REASON_COMPOUND_STRONG') != '0':
        # 珍しさ・組の少なさではない、字の並びの形そのものの見立ての紫（片仮名の語のあいだの 化 は並べる か）は残す。
        # 行は文の途中で切れることがあり（うに 2026-11-17）、前後が無いことは形の見立てを打ち消さない。
        # CN_ODD_REASON_COMPOUND_STRONG=0 で前のまま
        why = {}
        for r in result.get('odd_reasons') or ():
            if len(r) >= 3 and isinstance(r[2], str):
                why.setdefault(tuple(r[:2]), []).append(r[2])
        drop = {k for k in drop if not any(any(m in t for m in _SHAPE_REASON) for t in why.get(k, ()))}
    if not drop:
        return result
    out = dict(result)
    out['odd_spans'] = [x for x in result.get('odd_spans') or () if tuple(x[:2]) not in drop]
    if 'odd_reasons' in result:
        out['odd_reasons'] = [x for x in result.get('odd_reasons') or () if tuple(x[:2]) not in drop]
    if 'unsure_spans' in result:
        out['unsure_spans'] = [x for x in result.get('unsure_spans') or () if tuple(x[:2]) not in drop]
    return out


def correct_line(line, *args, **kwargs):
    result = _orig['correct_line'](line, *args, **kwargs)
    try:
        result = fill(line, result)
    except Exception:
        return result
    try:
        result = narrow_ime_field(line, result)
    except Exception:
        return result
    try:
        result = drop_filler_in_word(line, result)
    except Exception:
        return result
    try:
        return drop_compound_line(line, result)
    except Exception:
        return result


def install():
    import correction_entry as ce
    if 'correct_line' in _orig:
        return
    _orig['correct_line'] = ce.correct_line
    functools.update_wrapper(correct_line, ce.correct_line)
    ce.correct_line = correct_line


def uninstall():
    import correction_entry as ce
    fn = _orig.pop('correct_line', None)
    if fn is not None and ce.correct_line is correct_line:
        ce.correct_line = fn
    correct_line.__dict__.pop('__wrapped__', None)


def _interj_tte(toks, a, b):
    inside = [t for t in toks if t.start < b and a < t.end and t.surface not in ('ー', '〜', '～')]
    if len(inside) < 2 or inside[0].pos != '感動詞' or inside[0].start != a:
        return False
    if inside[1].surface != 'って' or inside[1].start != inside[0].end:
        return False
    return all(t.surface == 'ば' and t.pos == '助詞' for t in inside[2:])


def _verb_then_noun(toks, a, b):
    inside = [t for t in toks if t.start < b and a < t.end]
    if len(inside) != 2:
        return False
    v, n = inside
    if not (v.start == a and n.end == b and v.end == n.start):
        return False
    if v.pos != '動詞' or not str(getattr(v, 'infl_form', '') or '').startswith('基本形'):
        return False
    if n.pos != '動詞' or not str(getattr(n, 'infl_form', '') or '').startswith('連用') or not any(_kanji(c) for c in n.surface):
        return False
    after = [t for t in toks if t.start >= n.end]
    if after and after[0].pos not in ('助詞', '記号', '助動詞'):
        return False
    try:
        import reading_lattice as lat
        lat.load()
        rd = ''.join(chr(ord(c) - 0x60) if 'ァ' <= c <= 'ヶ' else c for c in (n.reading or ''))
        return any(f == n.surface and p == '名詞' for f, _l, _r, _c, p in lat._table.get(rd, ()))
    except Exception:
        return False


def _kana_entry_span(toks, a, b):
    """紫の所の語が、ひらがなの表記のまま辞書に載る3字以上の語1つと、その後ろの助詞だけか（記号・゛ を含む所は見ない）。"""
    inside = [t for t in toks if t.start < b and a < t.end]
    words = [t for t in inside if t.pos != '助詞']
    if len(words) != 1:
        return False
    w = words[0]
    if w.pos not in ('名詞', '接続詞', '副詞'):
        return False                     # 活用する語（はれる）は打ち違いとも読めるので見ない
    if len(w.surface) < 3 or not all('ぁ' <= c <= 'ゖ' or c == 'ー' for c in w.surface):
        return False
    if inside and inside[0] is not w:
        return False
    try:
        import reading_lattice as lat
        lat.load()
        return any(f == w.surface and p == w.pos for f, _l, _r, _c, p in lat._table.get(w.surface, ()))
    except Exception:
        return False


_CASE = ('を', 'に', 'が', 'で', 'と', 'へ', 'も')


def _all_kana(s):
    return bool(s) and all('ぁ' <= c <= 'ゖ' for c in s)


def _noun_pair(toks, a, b):
    """紫がちょうど、漢字だけの辞書の名詞2つ（行間｜幅・入力｜欄）に掛かるか。どちらも ime_reconvert の表に在る語
    （順位が PAIR_RANK 以内）なら、名詞をつないだ複合語。CN_ODD_REASON_NOUN_PAIR=0 で見ない"""
    # 既定はオフ（CN_ODD_REASON_NOUN_PAIR=1 で入る）: 検査スレッドの short2 で、打ち違いの4行（名詞2つに割れた誤変換）の
    # 紫が消えた。順位・品詞では 行間｜幅 と 電子｜腹 を分けられない（2026-11-16）
    if os.environ.get('CN_ODD_REASON_NOUN_PAIR') != '1':
        return False
    inside = [t for t in toks if t.end > a and t.start < b]
    if len(inside) != 2 or inside[0].start != a or inside[1].end != b or inside[0].end != inside[1].start:
        return False
    try:
        import ime_reconvert as R
    except Exception:
        return False
    for t in inside:
        if t.pos != '名詞' or not _kanji(t.surface) or not _dict_noun(t.surface) or R._rank(t.surface) > PAIR_RANK:
            return False
    return True


PAIR_RANK = 650


KEYSLIP_TAIL = 'は、かな入力で隣のキーを打ったか、一緒に押したかもしれません'


def _noun_renyo(toks, a, b):
    """紫がちょうど、身近な漢字の名詞＋動詞の連用形の語（右｜詰め・左｜寄せ・手｜書き）に掛かるか。名詞を前に置いて
    動詞の連用形を名詞にした複合語。CN_ODD_REASON_NOUN_RENYO=0 で見ない"""
    if os.environ.get('CN_ODD_REASON_NOUN_RENYO') == '0':
        return False
    inside = [t for t in toks if t.end > a and t.start < b]
    if len(inside) != 2 or inside[0].start != a or inside[1].end != b or inside[0].end != inside[1].start:
        return False
    x, y = inside
    try:
        import ime_reconvert as R
        import odd_respell as O
        from morphology import dictionary_inflections
    except Exception:
        return False
    if x.pos != '名詞' or not _kanji(x.surface) or not _dict_noun(x.surface) or R._rank(x.surface) > O.COMMON_NEW:
        return False
    if not ('一' <= y.surface[0] <= '鿿') or _kanji(y.surface) or not all('ぁ' <= c <= 'ん' for c in y.surface[1:]):
        return False
    rows = [r for r in dictionary_inflections(y.surface) or () if r[0].startswith('動詞,自立')
            and (r[1] or '').startswith('連用形') and r[2] != y.surface]
    return any(R._rank(r[2]) <= O.COMMON_NEW + 100 for r in rows)


def _sahen_word(toks, a, b):
    hit = [t for t in toks if t.start == a and t.end == b]
    if not hit:
        return False
    t = hit[0]
    if t.pos != '名詞' or len(t.surface) != 2 or not _kanji(t.surface):
        return False
    try:
        import ime_reconvert as R
    except Exception:
        return False
    if R._rank(t.surface) >= 800:
        return False
    # 後ろが続く形（助詞・助動詞・記号・行末・する の正しい形）でなければ、隣が打ち違いの跡（流布｜委・下達｜せ｜れ）。
    # 既定オフの理由だった IME の選び違いの紫の消えを、ここで止める（2026-11-16 batch597）
    if not _sahen_tail_ok(toks, t):
        return False
    # 行のほかの内容の語に珍しい語（ime_reconvert の DOUBT 以上）が在れば、打ち違いが行に広がっている見込み
    # （2026-11-17 batch601: 短い束の 名詞＋は＋珍しい名詞 の打ち違いで、紫が1つだけでも外していた）
    if any(u is not t and u.pos in ('名詞', '動詞', '形容詞') and R._strong(u.surface) and R._token_rarity(u, toks) >= R.DOUBT
           for u in toks):
        return False
    return any(r[0].startswith('名詞,サ変接続') and r[2] == t.surface for r in _dict_entries(t.surface))


def _sahen_tail_ok(toks, t):
    nxt = [x for x in toks if x.start == t.end]
    if not nxt:
        return True
    q = nxt[0]
    if q.pos in ('助詞', '助動詞', '記号'):
        return True
    if q.pos == '動詞' and getattr(q, 'base_form', '') == 'する' and q.surface in ('し', 'する', 'すれ', 'さ', 'しろ'):
        return True
    return False


def _verb_tail_noun(surface):
    """名詞が、身近な名詞＋動詞の連用形の漢字1字で出来た語（様子見・下見・味見の型）か。辞書の1語の名詞で、
    最後の漢字が辞書の動詞の連用形、前の部分も辞書の1語の名詞。"""
    if len(surface) < 2 or not _kanji(surface) or not _dict_noun(surface) or not _dict_noun(surface[:-1]):
        return False
    try:
        from morphology import dictionary_inflections
        rows = dictionary_inflections(surface[-1]) or ()
    except Exception:
        return False
    return any(r[0].startswith('動詞,') and (r[1] or '').startswith('連用') and r[2] != surface[-1]
               and r[2].startswith(surface[-1]) for r in rows)


def _verb_tail_suru(toks, a, b):
    """紫がちょうど 名詞（_verb_tail_noun）＋する の活用 に掛かるか。CN_ODD_REASON_VERB_TAIL_SURU=0 で見ない"""
    if os.environ.get('CN_ODD_REASON_VERB_TAIL_SURU') == '0':
        return False
    inside = [t for t in toks if t.end > a and t.start < b]
    if len(inside) != 2 or inside[0].start != a or inside[-1].end != b:
        return False
    n, v = inside
    return n.pos == '名詞' and v.pos == '動詞' and v.base_form == 'する' and _verb_tail_noun(n.surface)


def _action_status(toks, a, b):
    """理由が「辞書で確かめられません」だけの紫が、漢字2字以上の身近な語1つにちょうど掛かり、すぐ前が身近なサ変の名詞
    （判定・変更・確認）で、紫の語が状態を言う語（形容動詞の語幹・サ変の名詞・接尾: 不能・可能・完了・中止・不可）なら、
    動作＋状態の複合語（判定不能・変更可能）。CN_ODD_REASON_ACTION_STATUS=0 で見ない"""
    if os.environ.get('CN_ODD_REASON_ACTION_STATUS') == '0':
        return False
    try:
        import ime_reconvert as R
        import odd_respell as O
    except Exception:
        return False
    for i, t in enumerate(toks):
        if t.start == a and t.end == b:
            break
    else:
        return False
    if i == 0:
        return False
    y = toks[i - 1]
    if y.end != a or y.pos != '名詞' or t.pos != '名詞':
        return False
    if not (len(y.surface) >= 2 and _kanji(y.surface) and len(t.surface) >= 2 and _kanji(t.surface)):
        return False
    if R._rank(y.surface) > O.COMMON_NEW or R._rank(t.surface) > O.COMMON_NEW:
        return False
    ye = [r[0] for r in _dict_entries(y.surface) if r[2] == y.surface]
    te = [r[0] for r in _dict_entries(t.surface) if r[2] == t.surface]
    return (any(e.startswith('名詞,サ変接続') for e in ye)
            and any(e.startswith(('名詞,形容動詞語幹', '名詞,サ変接続', '名詞,接尾')) for e in te))


def _split_kana_verb(toks, a, b):
    """a:b が [格の助詞] 助詞のかな… で終わり、b から始まる動詞のかなの切れ端とつないだ形の基本形が辞書の動詞の読みか。"""
    toks = list(toks)
    inside = [i for i, t in enumerate(toks) if t.start < b and a < t.end]
    if not inside or toks[inside[0]].start != a or toks[inside[-1]].end != b:
        return False
    nxt = inside[-1] + 1
    if nxt >= len(toks):
        return False
    v = toks[nxt]
    if v.pos != '動詞' or v.start != b or not _all_kana(v.surface) or not _all_kana(v.base_form or ''):
        return False
    k = 0
    if toks[inside[0]].surface in _CASE and toks[inside[0]].pos == '助詞' and len(inside) > 1:
        k = 1
    piece = [toks[i] for i in inside[k:]]
    if not piece or not all(t.pos == '助詞' and _all_kana(t.surface) for t in piece):
        return False
    if any(t.end != u.start for t, u in zip(piece, piece[1:] + [v])):
        return False
    head = ''.join(t.surface for t in piece)
    base = head + v.base_form
    try:
        import wago_verb as W
        return bool(W._verb_faces(base))
    except Exception:
        return False


def _mark_char(c):
    """矢印・箇条書きの印などの記号（→ ・ ※ ★）は行の中身の字に数えない（2026-11-17 うに: ほしふる は紫なし、
    - ほしふる → だけ紫）。かな・漢字・英数字は数える。CN_ODD_REASON_BODY_SYMBOLS=0 で前のまま"""
    if os.environ.get('CN_ODD_REASON_BODY_SYMBOLS') == '0':
        return False
    import unicodedata
    return unicodedata.category(c)[0] in 'SP' and c not in 'ー々〆'


def _wide_weak(line, toks, a, b):
    """a:b が語2つ以上に掛かり、行の空白・記号を除いた字の全部を含むか。"""
    body = [i for i, c in enumerate(line) if not c.isspace() and c not in '・、。，．,.「」『』（）()[]【】〔〕!?！？…-－ー/／'
            and not _mark_char(c)]
    if not body:
        return False
    inside = [i for i in body if a <= i < b]
    words = [t for t in toks if t.start < b and a < t.end and t.pos not in ('記号',)]
    if len(words) >= 2 and len(inside) != len(body) and os.environ.get('CN_ODD_REASON_IME_FIELD_CLAUSE') != '0':
        # 読点・句点で区切った1つの節の中身全部（…が、｜メモ帳画面が出てくるのは、）も、行の中身全部と同じに見る
        # （2026-11-17 うに 誤判定: 前に節の在る行で、後ろの節の全体に紫）。CN_ODD_REASON_IME_FIELD_CLAUSE=0 で前のまま
        cut = set('、。，．,.!?！？')
        lo, hi = a, b
        while lo > 0 and line[lo - 1] not in cut:
            lo -= 1
        while hi < len(line) and line[hi] not in cut:
            hi += 1
        part = [i for i in body if lo <= i < hi]
        return bool(part) and all(a <= i < b for i in part)
    return len(words) >= 2 and len(inside) == len(body)
