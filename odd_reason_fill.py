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
    if os.environ.get('CN_ODD_REASON_DECIMAL') != '0':
        # 数字に挟まれた小数点（4.5 の .）は数の一部。解析が名詞と読んでも語として見ない（2026-11-22 補正担当、
        # うに 誤判定タブの正しい文 星n中x.y）。CN_ODD_REASON_DECIMAL=0 で前のまま
        words = [t for k, t in enumerate(toks) if t.pos != '記号' and not (
            t.surface in ('.', '．') and 0 < k < len(toks) - 1 and toks[k - 1].end == t.start
            and toks[k + 1].start == t.end and toks[k - 1].surface[-1:].isdigit() and toks[k + 1].surface[:1].isdigit())]
    if not words or not all(t.pos in ('名詞', '接頭詞') for t in words):
        return False
    for t in words:
        sub = str(t.pos_sub or '')
        # 数字だけの数（4.5 の 4・5）は読みの表が無くても数（CN_ODD_REASON_DECIMAL=0 で前のまま）
        if (sub.startswith('数') and t.surface.isdigit()
                and os.environ.get('CN_ODD_REASON_DECIMAL') != '0'):
            continue
        if not getattr(t, 'has_reading', True):
            return False
        if sub.startswith('数'):
            continue
        # 数字で始まる語（5つ・9本）は辞書に無くても数（B2。CN_ODD_REASON_NUM_START=0 で前のまま）
        if t.surface[:1].isdigit() and os.environ.get('CN_ODD_REASON_NUM_START') != '0':
            continue
        if any(c.isascii() and c.isalpha() or 'ａ' <= c <= 'ｚ' or 'Ａ' <= c <= 'Ｚ' for c in t.surface):
            return False
        if t.pos == '接頭詞' or sub.startswith('接尾'):
            continue
        if not _dict_entries(t.surface):
            return False
    return True


_KANJI_NUM = set('一二三四五六七八九十百千')


def _noun_count(toks, a, b):
    """[a, b) がちょうど 辞書の名詞1つ＋数の語（五つ・三本・5つ: 漢数字か数字で始まる、辞書の語か数）か。
    物と数を並べた数え方（星五つ・林檎二つ）。前後は行の端・助詞・記号・空白"""
    hit = [t for t in toks if t.start < b and a < t.end]
    if len(hit) != 2 or hit[0].start != a or hit[1].end != b or hit[0].end != hit[1].start:
        return False
    x, y = hit
    if x.pos != '名詞' or str(x.pos_sub or '').startswith(('固有名詞', '数', '接尾', '非自立')):
        return False
    if not getattr(x, 'has_reading', True) or not _dict_entries(x.surface):
        return False
    if not (y.surface[:1] in _KANJI_NUM or y.surface[:1].isdigit()) or y.pos != '名詞':
        return False
    if not (str(y.pos_sub or '').startswith('数') or _dict_entries(y.surface)):
        return False
    n = toks.index(x)
    for z in toks[max(0, n - 1):n] + toks[n + 2:n + 3]:
        if z.pos not in ('助詞', '記号') and z.surface.strip():
            return False
    return True


def _unit_suffix(toks, a, b):
    """[a, b) の語がどれも接尾の漢字（科｜医）で、前の語とつないだ頭の所が表の1語（片仮名を交ぜた書き方の語＋科 の型）になり、
    その後ろが接尾の漢字だけなら、1語＋接尾の複合語。前後は行の端・助詞・助動詞・記号"""
    hit = [t for t in toks if t.start < b and a < t.end]
    if not hit or not all(str(t.pos_sub or '').startswith('接尾') and t.surface and all(
            '一' <= c <= '鿿' for c in t.surface) for t in hit):
        return False
    n0, n1 = toks.index(hit[0]), toks.index(hit[-1])
    nx = toks[n1 + 1] if n1 + 1 < len(toks) else None
    if nx is not None and nx.start == hit[-1].end and nx.pos not in ('助詞', '助動詞', '記号'):
        return False
    try:
        import seed_japanese
    except Exception:
        return False
    for i in range(n0 - 1, max(-1, n0 - 4), -1):
        if any(toks[k].end != toks[k + 1].start for k in range(i, n0)):
            break
        if toks[i].pos not in ('名詞', '接頭詞'):
            break
        pv = toks[i - 1] if i > 0 else None
        if pv is not None and pv.end == toks[i].start and pv.pos not in ('助詞', '記号'):
            continue
        face = ''.join(t.surface for t in toks[i:n0 + 1])
        if seed_japanese.is_unit(face) is True:
            return True
    return False


_QUOTE_VERBS = ('なる', 'いう', '言う', '思う', '考える', '書く', '聞く', '答える')


def _wa_quote(toks, a, b):
    """[a, b) がちょうど 係助詞の は＋引用の と で、と のすぐ後ろが言う・思う・なる の動詞か（言いかけの文を引いた形:
    これはと思った）"""
    hit = [t for t in toks if t.start < b and a < t.end]
    if len(hit) != 2 or hit[0].start != a or hit[1].end != b:
        return False
    x, y = hit
    if not (x.surface == 'は' and str(x.pos_sub or '').startswith('係助詞') and y.surface == 'と'
            and str(y.pos_sub or '').endswith('引用') and x.end == y.start):
        return False
    k = toks.index(y)
    nx = toks[k + 1] if k + 1 < len(toks) else None
    return (nx is not None and nx.start == y.end and nx.pos == '動詞'
            and (getattr(nx, 'base_form', '') or '') in _QUOTE_VERBS)


_LONE_PARTICLES = set('はがをにとでのもへや')


def _kana_list_run(line, toks, a, b):
    """紫の所に、解析が読めなかったひらがなの語（すす｜ぎとつけおきは）が在り、その語が「ひらがなのまま通す語の一覧」の
    3字以上の語を含み、その語を含むひらがなの並び全体が、一覧の語・表の語・辞書の語（2字以上）・助詞1字に切り分けられるか"""
    try:
        import kana_keep_list
        ws = [w for w in kana_keep_list.words() if len(w) >= 3]
        import seed_japanese
        from morphology import dictionary_inflections
    except Exception:
        return False
    bad = [t for t in toks if t.start < b and a < t.end and not getattr(t, 'has_reading', True)
           and t.surface and all(_hira_c(c) for c in t.surface)]
    for t in bad:
        hit = [w for w in ws if w in t.surface]
        if not hit:
            continue
        s0, e0 = t.start, t.end
        while s0 > 0 and _hira_c(line[s0 - 1]):
            s0 -= 1
        while e0 < len(line) and _hira_c(line[e0]):
            e0 += 1
        run = line[s0:e0]
        if not any(w in run for w in hit):
            continue
        wset = set(ws)

        def word(x):
            if len(x) == 1:
                return x in _LONE_PARTICLES
            return x in wset or seed_japanese.is_unit(x) is True or bool(dictionary_inflections(x))
        ok = [True] + [False] * len(run)
        for j in range(1, len(run) + 1):
            for i in range(max(0, j - 8), j):
                if ok[i] and word(run[i:j]):
                    ok[j] = True
                    break
        if ok[-1]:
            return True
    return False


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


def _affix_compound(toks, a, b):
    """[a, b) を含む漢字・片仮名・数字の続きが接辞の形（affix_form）で、すぐ後ろが崩れた形でないか（B1）"""
    try:
        import affix_form
    except Exception:
        return False
    if not affix_form.affix_run(toks, a, b):
        return False
    i, j = affix_form.run_bounds(toks, a, b)
    nx = toks[j + 1] if j + 1 < len(toks) else None
    if nx is not None and nx.start == toks[j].end:
        s = nx.surface or ''
        nn = toks[j + 2] if j + 2 < len(toks) else None
        # する の活用として立たない形（喜怒すれ・下達せれ の型。すれば は立つ）
        if s in ('すれ', 'せれ') and not (nn is not None and nn.surface == 'ば'):
            return False
        # かな1字の自立語（解析が切れ端を語と見た所）
        if (len(s) == 1 and 'ぁ' <= s <= 'ゖ' and nx.pos in ('名詞', '動詞', '形容詞', '副詞', '感動詞', '連体詞')):
            return False
    return True


_E_TO_A = dict(zip('えけげせぜてでねへべぺめれ', 'あかがさざただなはばぱまら'))
_E_TO_O = dict(zip('えけげせぜてでねへべぺめれ', 'おこごそぞとどのほぼぽもろ'))


def _hira_c(c):
    return '\u3041' <= c <= '\u3096' or c == 'ー'


_VOWEL_ROWS = ('あかさたなはまやらわがざだばぱぁゃゎ', 'いきしちにひみりぎじぢびぴぃ', 'うくすつぬふむゆるぐずづぶぷぅゅ',
               'えけせてねへめれげぜでべぺぇ', 'おこそとのほもよろをごぞどぼぽぉょ')


def _unstretch(line):
    """ひらがなの後ろの伸ばす音（ー・〜・～）を、その字の母音のかな（お段は う: しよー → しよう）に置き換えた行。字数は同じ。
    伸ばす音が無ければ None"""
    out, hit = list(line), False
    for k in range(1, len(line)):
        if line[k] in 'ー〜～' and _hira_c(line[k - 1]):
            for v, row in zip('あいうえう', _VOWEL_ROWS):
                if line[k - 1] in row:
                    out[k] = v
                    hit = True
                    break
    return ''.join(out) if hit else None


def _stretch_pair(line, a, b, texts):
    """「A」と「B」は続けて置けない だけの紫で、行の伸ばす音を母音のかなに戻して解析し直すと、紫の所に A｜B の並びが
    もう無いなら、話し言葉の伸ばす音で解析が切り違えた所（作った正しい文: 班分けしよー）"""
    import re
    norm = _unstretch(line)
    if norm is None or not texts:
        return False
    pairs = []
    for t in texts:
        m = re.search('「([^」]+)」と「([^」]+)」は続けて置けない', t)
        if not m:
            return False
        pairs.append(m.groups())
    try:
        from morphology import tokenize
        nt = list(tokenize(norm))
    except Exception:
        return False
    # 伸ばす音が紫のすぐ近く（後ろ3字まで）に在ること
    if not any(norm[k] != line[k] for k in range(a, min(len(line), b + 3))):
        return False
    for x, y in zip(nt, nt[1:]):
        if x.start < b and a < y.end and (x.surface, y.surface) in pairs:
            return False
    hit = [t for t in nt if t.start < b and a < t.end]
    return bool(hit) and all(getattr(t, 'has_reading', True) for t in hit)


def _spoken_kana_words(line):
    """[(始め, 終わり)]: かなの語の作り方として紫の理由にならない所（2026-11-20 補正担当、うに 誤判定タブの正しい文。
    判断 POLICY.md F2・F3）。
    F2 CN_KANA_REDUP: 2字以上の同じかなの並びを繰り返した語（わうわう・もふもふ）。同じ打ち違いを2度続ける見込みは低い。
    F3 CN_SPOKEN_EE_ADJ: え段のかな＋ぇ・え・ー で終わる語を、あい・おい で終わる形に戻すと形容詞1語になるもの
    （おもしれぇ → おもしろい・すげぇ → すごい）。話し言葉の音の変化"""
    out = []
    runs = []
    k = 0
    while k < len(line):
        if _hira_c(line[k]):
            j = k
            while j < len(line) and _hira_c(line[j]):
                j += 1
            runs.append((k, j))
            k = j
        else:
            k += 1
    redup = os.environ.get('CN_KANA_REDUP') != '0'
    ee = os.environ.get('CN_SPOKEN_EE_ADJ') != '0'
    for s0, e0 in runs:
        w = line[s0:e0]
        if redup:
            # 並びの頭からの繰り返し（もふもふ｜だ）。後ろに残る所は助詞・助動詞だけ
            done_r = False
            for L in range(len(w), 3, -1):
                v = w[:L]
                for n in range(2, L // 2 + 1):
                    if L % n == 0 and v[:n] * (L // n) == v and len(set(v[:n])) > 1:
                        if L < len(w):
                            try:
                                from morphology import tokenize
                                rest = list(tokenize(w[L:]))
                            except Exception:
                                rest = None
                            if not rest or not all(t.pos in ('助詞', '助動詞') for t in rest):
                                continue
                        out.append((s0, s0 + L))
                        done_r = True
                        break
                if done_r:
                    break
        if ee:
            q = len(w)
            while q > 0 and w[q - 1] in 'ぇえー':
                q -= 1
            if 0 < q < len(w) and w[q - 1] in _E_TO_A:
                try:
                    from morphology import tokenize
                except Exception:
                    continue
                for st in range(0, q):
                    hit = False
                    for tab in (_E_TO_O, _E_TO_A):
                        cand = w[st:q - 1] + tab[w[q - 1]] + 'い'
                        tk = list(tokenize(cand))
                        if len(tk) == 1 and tk[0].pos == '形容詞' and tk[0].surface == cand:
                            out.append((s0 + st, e0))
                            hit = True
                            break
                    if hit:
                        break
    return out


def _rengo_case(toks, a, b):
    hit = [k for k, t in enumerate(toks) if t.start < b and a < t.end]
    if len(hit) != 2 or hit[1] != hit[0] + 1:
        return False
    t, q = toks[hit[0]], toks[hit[1]]
    return ((t.pos_sub or '').endswith('連語') and t.pos == '助詞' and q.pos == '助詞'
            and q.surface in ('は', 'も', 'を', 'が', 'の') and q.start == t.end)


def _reading_beside(line, toks, a, b):
    hit = [t for t in toks if t.start < b and a < t.end]
    if not hit or hit[0].start < a or hit[-1].end > b or not any(_kanji(t.surface) for t in hit):
        return False
    if any(not getattr(t, 'has_reading', True) for t in hit):
        return False
    rd = ''.join(t.reading or '' for t in hit)
    rd = ''.join(chr(ord(c) - 0x60) if 'ァ' <= c <= 'ヶ' else c for c in rd)
    if len(rd) < 2 or not all('ぁ' <= c <= 'ゖ' or c == 'ー' for c in rd):
        return False
    k = line.find(rd)
    while k >= 0:
        l0 = line[k - 1] if k > 0 else ''
        r0 = line[k + len(rd)] if k + len(rd) < len(line) else ''
        sep = lambda c: c == '' or not (c.isalnum() or '\u3041' <= c <= '\u30ff' or '\u4e00' <= c <= '\u9fff')
        if (k + len(rd) <= a or b <= k) and sep(l0) and sep(r0):
            return True
        k = line.find(rd, k + 1)
    return False


def _kana_reading_of_beside(line, toks, a, b):
    """紫の [a, b) が記号・空白で区切られたひらがなだけの並びで、同じ行に記号・空白で区切られて在る漢字の語
    （漢字を含む字句の続き）の読みとちょうど同じか（よるかつ — 夜活: 読みを書き添えた かな の側）。"""
    run = line[a:b]
    if len(run) < 2 or not all('ぁ' <= c <= 'ゖ' or c == 'ー' for c in run):
        return False
    sep = lambda c: c in ('', '・') or not (c.isalnum() or '\u3041' <= c <= '\u30ff' or '\u4e00' <= c <= '\u9fff')
    if not (sep(line[a - 1] if a > 0 else '') and sep(line[b] if b < len(line) else '')):
        return False
    i = 0
    while i < len(toks):
        if not _kanji(toks[i].surface) or toks[i].start < b and a < toks[i].end:
            i += 1
            continue
        j = i
        while j + 1 < len(toks) and toks[j + 1].start == toks[j].end and _kanji(toks[j + 1].surface):
            j += 1
        grp = toks[i:j + 1]
        s0, e0 = grp[0].start, grp[-1].end
        if (sep(line[s0 - 1] if s0 > 0 else '') and sep(line[e0] if e0 < len(line) else '')
                and all(getattr(t, 'has_reading', True) and t.reading for t in grp)):
            rd = ''.join(chr(ord(c) - 0x60) if 'ァ' <= c <= 'ヶ' else c for c in ''.join(t.reading for t in grp))
            if rd == run:
                return True
        i = j + 1
    return False


def _letter_counter(line, toks, a, b):
    """紫の [a, b) の中に、前後に英数字の無い英字1字が在り、そのすぐ後ろが数の接尾（番目・回・個・n文字目 の 目）の
    並びか: 数を表す文字（n番目・x回目・n文字目）で、打ち残しの英字ではない。"""
    for i, t in enumerate(toks):
        c = t.surface
        if not (t.start < b and a < t.end and len(c) == 1 and (c.isascii() and c.isalpha() or 'ａ' <= c <= 'ｚ' or 'Ａ' <= c <= 'Ｚ')):
            continue
        l0 = line[t.start - 1] if t.start > 0 else ''
        if l0 and (l0.isascii() and l0.isalnum() or 'ａ' <= l0 <= 'ｚ' or 'Ａ' <= l0 <= 'Ｚ' or '０' <= l0 <= '９'):
            continue
        nxt = toks[i + 1:i + 3]
        if not nxt or nxt[0].start != t.end:
            continue
        if str(nxt[0].pos_sub or '').startswith('接尾:助数詞') or nxt[0].surface == '目':
            return True
        if (len(nxt) == 2 and nxt[0].pos == '名詞' and nxt[1].start == nxt[0].end
                and str(nxt[1].pos_sub or '').startswith('接尾') and nxt[1].surface == '目'):
            return True
    return False


GENERIC_LINK = '前後の語とのつながりが辞書で確かめられません'
COMMON_NOUN_RANK = 720
COMMON_NOUN_MARGIN = 50   # 同音同種の表記がこれだけ以上身近な時だけ、打ち違いかもしれないと見る（死霊 595・資料 433）   # odd_respell.TYPED_WORDS_RANK と同じ: これより身近な表記なら、確かに選んで確定した語


def _common_noun_slot(line, toks, a, b):
    """紫の [a, b) がちょうど1つの漢字だけの名詞（固有名詞・接尾でない、辞書に読みの在る、身近な表記）で、
    すぐ後ろが名詞の後ろに来る助詞（の・が・は・を・に・も・で・と・へ・から・まで）か。"""
    hit = [t for t in toks if t.start < b and a < t.end]
    if len(hit) != 1 or hit[0].start != a or hit[0].end != b:
        return False
    t = hit[0]
    sub = str(t.pos_sub or '')
    if (t.pos != '名詞' or len(t.surface) < 2 or not all('一' <= c <= '鿿' for c in t.surface)
            or sub.startswith(('固有名詞', '接尾', '数')) or not getattr(t, 'has_reading', True)):
        return False
    nxt = [u for u in toks if u.start == b]
    if not nxt:
        return False
    u = nxt[0]
    slot = (u.pos == '助詞' and u.surface in ('の', 'が', 'は', 'を', 'に', 'も', 'で', 'と', 'へ', 'から', 'まで'))
    if not slot and os.environ.get('CN_ODD_REASON_COMMON_NOUN_WIDE') != '0':
        # 名詞・形容動詞の語幹の後ろの だ・な・です（律儀な・高慢だった）と、サ変の名詞の後ろの する（洋行して）も
        # 名詞の置き場所（2026-11-20 例文の正しい文の紫）。CN_ODD_REASON_COMMON_NOUN_WIDE=0 で前のまま
        slot = ((u.pos == '助動詞' and u.surface in ('だ', 'な', 'です', 'でし', 'だっ', 'でしょ', 'だろ'))
                or (u.pos == '動詞' and getattr(u, 'base_form', '') == 'する' and sub.startswith('サ変')))
    if not slot:
        return False
    try:
        import ime_reconvert
        from morphology import tokenize
        mine = ime_reconvert._rank(t.surface)
        if mine > COMMON_NOUN_RANK:
            return False
        # 同じ読みで同じ種類の名詞のもっと身近な表記が在るなら、打ち違い・変換違いかもしれない（死霊 → 資料）。
        # 種類の違う同音（先年 と 専念: 時の名詞とサ変の名詞）は比べない
        rd = ''.join(chr(ord(c) - 0x60) if 'ァ' <= c <= 'ヶ' else c for c in (t.reading or ''))
        for f in ime_reconvert._dict_faces(rd, 12) if rd else ():
            if f == t.surface or ime_reconvert._rank(f) >= mine - COMMON_NOUN_MARGIN:
                continue
            ft = list(tokenize(f))
            if len(ft) == 1 and ft[0].pos == '名詞' and str(ft[0].pos_sub or '') == sub:
                return False
        return True
    except Exception:
        return False


def _attr_verb_kata(toks, a, b):
    """紫の [a, b) が 形容動詞の語幹＋な＋動詞の連用形（幸運な死に）で終わり、すぐ後ろが 方（死に方: 動詞の連用形＋方 は
    名詞）か。な は名詞の前に置く形で、連用形＋方 はその名詞なので、正しい並び。"""
    inside = [t for t in toks if a <= t.start and t.end <= b]
    if len(inside) < 3 or inside[0].start != a or inside[-1].end != b:
        return False
    x, na, v = inside[-3], inside[-2], inside[-1]
    nxt = [u for u in toks if u.start == b]
    return (bool(nxt) and nxt[0].surface == '方' and str(nxt[0].pos_sub or '').startswith('接尾')
            and v.pos == '動詞' and v.infl_form == '連用形' and str(v.pos_sub or '').startswith('自立')
            and na.surface == 'な' and na.pos == '助動詞'
            and str(x.pos_sub or '').startswith('形容動詞語幹')
            and x.end == na.start and na.end == v.start)


def _ime_one_noun(line, toks, a, b):
    hit = [t for t in toks if t.start < b and a < t.end]
    if (len(hit) != 2 or hit[0].start != a or hit[1].end != b or hit[0].end != hit[1].start
            or not all(len(t.surface) == 1 and _kanji(t.surface) and t.pos == '名詞' for t in hit)):
        return False
    try:
        import ime_class_mark
        words = ime_class_mark._ime_words(line)
    except Exception:
        return False
    if not words:
        return False
    return any(w[0] == a and w[1] == b and w[4] in ime_class_mark.NOUNISH for w in words)


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
    stems = inside[:-1]
    # 漢字1字の名詞が2つ以上に切れた並び（資料｜乳｜力｜し）は、1字ずつは辞書の語でも、つないだ形が辞書に無ければ IME が
    # 崩れた読みを字ごとに当てた跡（2026-11-20 簡易入力の試験 資料乳力します の紫が外れていた）。CN_ODD_REASON_SURU_PIECES=0 で前のまま
    if (os.environ.get('CN_ODD_REASON_SURU_PIECES') != '0' and len(stems) >= 2
            and sum(1 for t in stems if t.pos == '名詞' and len(t.surface) == 1 and _kanji_c(t.surface)) >= 2
            and not _dict_noun(''.join(t.surface for t in stems))):
        return False
    return all(_dict_stem(t) for t in stems)


def _kanji_c(c):
    return '一' <= c <= '鿿' or c == '々'


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
    # K（前）: 連語の格助詞＋を の「続けて置けない」の理由は、重なる紫の理由に数えない
    if os.environ.get('CN_ODD_REASON_RENGO_CASE') != '0' and (result.get('corrected') or line) == line:
        try:
            from morphology import tokenize as _tk
            _tks = list(_tk(line))
            _gone = {tuple(x[:2]) for x in reasons if len(x) >= 3 and isinstance(x[2], str) and 'は続けて置けない' in x[2]
                     and _rengo_case(_tks, x[0], x[1])}
            reasons = [x for x in reasons if tuple(x[:2]) not in _gone]
        except Exception:
            _gone = set()
    else:
        _gone = set()
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
    spoken = _spoken_kana_words(line) if done == line else []
    for x in odd:
        a, b = x[0], x[1]
        key = (a, b)
        # K: 連語の格助詞（について・に関して・として）のすぐ後ろの は・も・を・が・の に掛かる「続けて置けない」だけの紫は、
        # 〜について を名詞のように扱う普通の書き方（2026-11-20 補正担当、判断 POLICY.md K）。CN_ODD_REASON_RENGO_CASE=0 で前のまま
        _tx = why.get(key, [])
        if (done == line and _tx and all('は続けて置けない' in t for t in _tx)
                and os.environ.get('CN_ODD_REASON_RENGO_CASE') != '0' and _rengo_case(toks, a, b)):
            drop.add(key)
            continue
        # B5: 紫の漢字の語の読みと同じかなの並びが、同じ行に記号・空白で区切られて在るなら、書き手が読みを書き添えた語
        # （よるかつ—夜活）。理由が無いか弱い理由だけの時（2026-11-20 補正担当、判断 POLICY.md B5）。CN_READING_BESIDE=0 で前のまま
        if (done == line and os.environ.get('CN_READING_BESIDE') != '0' and _all_weak(_tx)
                and _reading_beside(line, toks, a, b)):
            drop.add(key)
            continue
        # 数を表す英字1字＋数の接尾（そのn文字目・x回目・n番目）に掛かる弱い理由だけの紫は外す（2026-11-20 うにの
        # 誤判定タブ）。CN_ODD_REASON_LETTER_COUNTER=0 で前のまま
        if (done == line and os.environ.get('CN_ODD_REASON_LETTER_COUNTER') != '0' and _all_weak(_tx)
                and _letter_counter(line, toks, a, b)):
            drop.add(key)
            continue
        # 身近な漢字の名詞1語（先年・罫線）がそのまま名詞の置き場所（の・が・を…の前）に在り、理由が「つながりが辞書で
        # 確かめられない」だけの紫は外す。辞書の語を珍しさだけで紫にしない（うに: 日常語を珍しい語扱いしない・
        # 2026-11-20 誤判定タブ）。CN_ODD_REASON_COMMON_NOUN=0 で前のまま
        if (done == line and os.environ.get('CN_ODD_REASON_COMMON_NOUN') != '0'
                and all(t == GENERIC_LINK for t in _tx) and _common_noun_slot(line, toks, a, b)):
            drop.add(key)
            continue
        # 形容動詞の語幹＋な＋動詞の連用形＋方（幸運な死に方・楽な死に方）の「つながりが辞書で確かめられない」だけの紫は外す。
        # 連用形＋方 は名詞（2026-11-20 補正担当の例文の正しい文）。CN_ODD_REASON_ATTR_VERB_KATA=0 で前のまま
        if (done == line and os.environ.get('CN_ODD_REASON_ATTR_VERB_KATA') != '0'
                and all(t == GENERIC_LINK for t in _tx) and _attr_verb_kata(toks, a, b)):
            drop.add(key)
            continue
        # B5 の かな の側: 紫の かな の並びが、同じ行に区切って書いた漢字の語の読みそのもの（よるかつ — 夜活）。
        # 書き手が読みを書き添えた所で、打ち違いではない（2026-11-20 うにの誤判定タブ）。CN_READING_BESIDE_KANA=0 で前のまま
        if (done == line and os.environ.get('CN_READING_BESIDE_KANA') != '0'
                and _kana_reading_of_beside(line, toks, a, b)):
            drop.add(key)
            continue
        if key in _gone:
            drop.add(key)
            continue
        # A3: 漢字1字＋1字の名詞の並び（残｜件）に掛かる弱い理由だけの紫は、PC の IME がその2字をちょうど1つの名詞として
        # 読むなら、IME の辞書に在る語（2026-11-20 補正担当、判断 POLICY.md A3）。IME が2字に割る並び（隣｜欄）は今のまま。
        # IME の無い所では何もしない。CN_ODD_REASON_IME_NOUN_PAIR=0 で前のまま
        if (done == line and os.environ.get('CN_ODD_REASON_IME_NOUN_PAIR') != '0' and _all_weak(_tx) and _tx
                and _ime_one_noun(line, toks, a, b)):
            drop.add(key)
            continue
        # F2・F3: 繰り返しのかなの語（わうわう・もふもふ）と、話し言葉の音の変化（おもしれぇ・すげぇ）の中の紫は外す
        if any(s0 <= a and b <= e0 for s0, e0 in spoken):
            drop.add(key)
            continue
        # F4: 伸ばす音（しよー）で解析が切り違えた「続けて置けない」の紫（2026-11-22 補正担当、うに 誤判定タブの正しい文）。
        # CN_ODD_REASON_STRETCH_PAIR=0 で前のまま
        if (done == line and _tx and all('は続けて置けない' in t for t in _tx)
                and os.environ.get('CN_ODD_REASON_STRETCH_PAIR') != '0' and _stretch_pair(line, a, b, _tx)):
            drop.add(key)
            continue
        texts = why.get(key, [])
        # 重なる紫の理由も見る（同じ所に具体の見立てが在れば外さない）
        over = [t for (s0, e0), ts in why.items() if s0 < b and a < e0 for t in ts]
        # AD（前）: 隣のキーの見立ての紫も、名詞＋動詞の連用形の語（右詰め）にちょうど掛かるなら外す（下の AD と同じ）
        if (over and all(t.endswith(KEYSLIP_TAIL) or t == GENERIC or 'は続けて置けない' in t for t in over)
                and done == line and _noun_renyo(toks, a, b)):
            drop.add(key)
            continue
        if os.environ.get('CN_ODD_REASON_WEAK_ONLY') != '0' and not _all_weak(over):
            # 外さない紫でも、理由の文が無ければ一般の理由を付ける（重なる紫の理由はその紫のもの）。
            # 重なる理由が IME の欄だけなら付けない（後の narrow_ime_field がその欄として狭める。2026-11-20 補正担当、
            # CN_ODD_REASON_IME_ONLY_NO_GENERIC=0 で前のまま）
            if not texts and not (over and all(t == IME_FIELD for t in over)
                                  and os.environ.get('CN_ODD_REASON_IME_ONLY_NO_GENERIC') != '0'):
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
        # B1: 書き換えの無い行で、理由が無いか弱い理由（辞書で確かめられない・続けて置けない・異様だと見たが）だけの紫が、
        # 語の作り方どおりの複合語（打鍵ミス・1打鍵・先年・可変状態・行間幅・星5つ。漢字1字の語は端に1つまで）の中なら、
        # 表に無い・珍しいことだけが根拠なので紫にしない。続きのすぐ後ろが崩れた形（すれ・せれ・かな1字の自立語）なら残す
        # （2026-11-20 補正担当、うに 誤判定タブの正しい文。判断 POLICY.md B1・B2）。CN_ODD_REASON_AFFIX_COMPOUND=0 で前のまま
        if (done == line and os.environ.get('CN_ODD_REASON_AFFIX_COMPOUND') != '0'
                and all(t == GENERIC or 'は続けて置けない' in t or '異様だと見たが' in t for t in over)
                and _affix_compound(toks, a, b)):
            drop.add(key)
            continue
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
        # AG: 弱い理由だけの紫が、ちょうど 辞書の名詞＋数の語（星五つ）に掛かるなら、物と数を並べた数え方
        # （2026-11-22 補正担当、うに 誤判定タブの正しい文）。CN_ODD_REASON_NOUN_COUNT=0 で前のまま
        if (texts and _all_weak(texts) and done == line and len(odd) == 1
                and os.environ.get('CN_ODD_REASON_NOUN_COUNT') != '0' and _noun_count(toks, a, b)):
            drop.add(key)
            continue
        # AH: 弱い理由だけの紫が、表の1語（片仮名を交ぜた書き方を含む）に続く接尾の漢字だけに掛かるなら、1語＋接尾の
        # 複合語（2026-11-22 補正担当、うに 誤判定タブの正しい文）。CN_ODD_REASON_UNIT_SUFFIX=0 で前のまま
        if (texts and _all_weak(texts) and done == line
                and os.environ.get('CN_ODD_REASON_UNIT_SUFFIX') != '0' and _unit_suffix(toks, a, b)):
            drop.add(key)
            continue
        # AI: 理由が無いか「つながりが辞書で確かめられません」だけの紫が、は＋引用の と（＋言う・思う・なる）だけに掛かるなら、言いかけの
        # 文を引いた形（2026-11-22 補正担当、うに 誤判定タブの正しい文）。CN_ODD_REASON_WA_QUOTE=0 で前のまま
        if ((reasonless or all(t == GENERIC for t in texts)) and done == line
                and os.environ.get('CN_ODD_REASON_WA_QUOTE') != '0' and _wa_quote(toks, a, b)):
            drop.add(key)
            continue
        # AJ: 弱い理由だけの紫が、一覧の語（つけおき）を含むのに解析が読めなかったひらがなの語に掛かり、その並びが語に
        # 切り分けられるなら、日常語を解析が知らないだけ（2026-11-23 補正担当、うに 誤判定タブの正しい文・
        # 日常語を珍しい語として扱わない）。CN_ODD_REASON_KANA_LIST_RUN=0 で前のまま
        if ((reasonless or _all_weak(texts)) and done == line
                and os.environ.get('CN_ODD_REASON_KANA_LIST_RUN') != '0' and _kana_list_run(line, toks, a, b)):
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
        # 表の片仮名の語（3字以上）＋漢字1字の接尾（テロップ｜風）は外来語の複合語の書き方
        if _known_loan(t.surface) and len(q.surface) == 1 and str(q.pos_sub or '').startswith('接尾'):
            continue
        try:
            if _dict_entries(p.surface + t.surface + q.surface) or _dict_entries(p.surface + t.surface):
                continue
        except Exception:
            continue
        out.append((p.start, q.end))
    return out


def _known_loan(face):
    """表に在る片仮名の語（3字以上: オンマウス・スクロールバー）。解析が読みを付けられないだけで、疑わしい語ではない
    （2026-11-20 補正担当、うに 誤判定タブの正しい文）。CN_ODD_REASON_IME_FIELD_LOAN=0 で前のまま"""
    if os.environ.get('CN_ODD_REASON_IME_FIELD_LOAN') == '0' or len(face) < 3 or not _kata(face):
        return False
    try:
        import corrector
        import seed_japanese
        kk = corrector._katakana_known_or_compound
        if kk(face):
            return True
        # 身近な片仮名の語2つをつないだ形（オン＋マウス・スクロール＋バー）。表の1語というだけ（シュア・チェン）では見ない
        import ime_reconvert

        def part(x):
            return kk(x) or (seed_japanese.is_unit(x) is True and ime_reconvert._rank(x) <= 530)
        return seed_japanese.is_unit(face) is True and any(
            part(face[:k]) and part(face[k:]) for k in range(2, len(face) - 1))
    except Exception:
        return False


def _listed_in_compound(t, toks):
    """珍しいが表に在る語（行間 618。表に無い 800 の 風位 は別）が、接辞の形の複合語（行間｜幅）の中に在る。
    IME の欄の紫を狭める時に疑わしい語に数えない（2026-11-20 補正担当、PC の 行間幅）。CN_ODD_REASON_IME_FIELD_COMPOUND=0 で前のまま"""
    if os.environ.get('CN_ODD_REASON_IME_FIELD_COMPOUND') == '0':
        return False
    try:
        import ime_reconvert as R
        if R._token_rarity(t, toks) >= 800:
            return False
    except Exception:
        return False
    return _affix_compound(toks, t.start, t.end)


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
    """下の _narrow_ime_field_core の前に、連語の格助詞＋を の「続けて置けない」の理由（K）を外す。その理由が
    IME の欄の紫の中の小さな紫として残ると、欄が狭まっても紫が広く残る（PC: 育ちについてを… の行の後ろ全部）。
    CN_ODD_REASON_RENGO_CASE=0 で前のまま"""
    if (os.environ.get('CN_ODD_REASON_RENGO_CASE') != '0' and isinstance(result, dict)
            and (result.get('corrected') or line) == line and result.get('odd_reasons')):
        try:
            from morphology import tokenize
            toks = list(tokenize(line))
            gone = {(r[0], r[1]) for r in result.get('odd_reasons') or ()
                    if len(r) >= 3 and isinstance(r[2], str) and 'は続けて置けない' in r[2] and _rengo_case(toks, r[0], r[1])}
            # B1 も同じ: IME の欄の紫の中の、接辞の形の複合語に掛かる弱い理由（行間｜幅）は小さな紫として残さない
            # （2026-11-20 PC: 雲では外れた 行間幅 が、IME の欄の紫に包まれて fill で外れず残った）
            if os.environ.get('CN_ODD_REASON_AFFIX_COMPOUND') != '0':
                gone |= {(r[0], r[1]) for r in result.get('odd_reasons') or ()
                         if len(r) >= 3 and isinstance(r[2], str)
                         and (r[2] == GENERIC or 'は続けて置けない' in r[2] or '異様だと見たが' in r[2])
                         and not any(len(y) >= 3 and (y[0], y[1]) == (r[0], r[1]) and y[2] != r[2]
                                     and not (y[2] == GENERIC or 'は続けて置けない' in y[2] or '異様だと見たが' in y[2])
                                     for y in result.get('odd_reasons') or ())
                         and _affix_compound(toks, r[0], r[1])}
        except Exception:
            gone = set()
        if gone:
            result = dict(result)
            result['odd_reasons'] = [r for r in result['odd_reasons'] if not (len(r) >= 2 and (r[0], r[1]) in gone)]
            result['odd_spans'] = [x for x in result.get('odd_spans') or () if (x[0], x[1]) not in gone]
    return _narrow_ime_field_core(line, result)


def _narrow_ime_field_core(line, result):
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
            (not getattr(t, 'has_reading', True) and not any(c.isascii() or 'ａ' <= c.lower() <= 'ｚ' for c in t.surface)
             and not _known_loan(t.surface))
            or (len(t.surface) == 1 and 'ぁ' <= t.surface <= 'ゖ' and t.pos not in ('助詞', '助動詞')
                and not _inflected_one(t) and not _nominalizer(t))
            # 珍しい語（風位）も疑わしい語（ime_reconvert の紫の門 DOUBT_MARK 以上。2026-11-15 PC の release_check:
            # 添付の風位目 の紫を外して誤字の印を失った）
            or (_rare_token(t, toks) and not _known_loan(t.surface) and not _listed_in_compound(t, toks))))]
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
