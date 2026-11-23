"""接辞の形（漢字・片仮名・数字の続きが、語の作り方どおりの複合語か）を見る。

keyslip_window（unsure の枝）と odd_reason_fill が、表に無い複合語であることだけを根拠にした紫を外すときに使う
（2026-11-20 補正担当・判断 POLICY.md の A2・B1・B2）。

続きの語がみな次のどれかで、漢字1字の語は多くて1つ・続きの端に在るなら「接辞の形」:
  (a) 2字以上の漢字の名詞で、表の1語（固有名詞でない）
  (b) 2字以上の身近な片仮名の名詞
  (c) 数・数字で始まる語と、そのすぐ後ろの助数詞
  (d) 漢字1字の名詞・接頭詞で身近なもの
1字の語が2つ以上並ぶ形は、IME が単漢字を並べた跡のことが多いので含めない。
"""
import os

KATA_RANK = 530      # 身近な片仮名の語（これ以下）
SINGLE_RANK = 530    # 身近な漢字1字の語（これ以下）


def _kanji(c):
    return '一' <= c <= '鿿' or c == '々'


def _strong(c):
    return _kanji(c) or 'ァ' <= c <= 'ヺ' or c == 'ー' or c.isdigit() or c in '.．'


def _kata(s):
    return bool(s) and all('ァ' <= c <= 'ヺ' or c == 'ー' for c in s)


def _rank(face):
    try:
        import ime_reconvert
        return ime_reconvert._rank(face)
    except Exception:
        return 10 ** 6


def _unit(face):
    try:
        import seed_japanese
        return seed_japanese.is_unit(face)
    except Exception:
        return None


def is_num(t):
    """数の語（名詞:数・数字で始まる語: 5つ・9本 は辞書に無くてよい）。B2"""
    if t is None:
        return False
    s = t.surface or ''
    return s[:1].isdigit() or (t.pos_sub or '').startswith('数') or (s != '' and all(c in '.．' for c in s))


def okuri_noun(t):
    """送り仮名の付く表の名詞（作り・組み）。漢字で始まり、かなで終わり、表の1語。keyslip の窓だけで使う（odd_reason_fill で使うと 州｜受け の紫を外した）"""
    s = t.surface or ''
    return (len(s) >= 2 and t.pos == '名詞' and _kanji(s[0]) and all(_kanji(c) or 'ぁ' <= c <= 'ゖ' for c in s)
            and 'ぁ' <= s[-1] <= 'ゖ' and getattr(t, 'has_reading', True) and _unit(s) is True)


def _cls(t, prev, okuri=False):
    s = t.surface or ''
    sub = t.pos_sub or ''
    if is_num(t):
        return 'num'
    if sub.startswith('接尾:助数詞') and prev == 'num':
        return 'num'
    if not getattr(t, 'has_reading', True) or sub.startswith('固有名詞'):
        return None
    if okuri and okuri_noun(t):
        return 'unit2'
    if _kata(s):
        return 'kata' if len(s) >= 2 and _unit(s) is True and _rank(s) <= KATA_RANK else None
    if all(_kanji(c) for c in s):
        if len(s) >= 2:
            return 'unit2' if (_unit(s) is True and t.pos == '名詞') else None
        return 'single' if t.pos in ('名詞', '接頭詞') and _rank(s) <= SINGLE_RANK else None
    return None


def run_bounds(tokens, a, b, okuri=False):
    """[a, b) に掛かる語から左右へ、漢字・片仮名・数字だけの語が隙間なく続く範囲（語の添字 i..j）。無ければ None"""
    idx = [i for i, t in enumerate(tokens) if t.start < b and a < t.end]
    if not idx:
        return None
    i, j = idx[0], idx[-1]

    def ok(t):
        return bool(t.surface) and (all(_strong(c) for c in t.surface) or is_num(t) or (okuri and okuri_noun(t)))
    if not all(ok(tokens[k]) for k in range(i, j + 1)):
        return None
    while i > 0 and ok(tokens[i - 1]) and tokens[i - 1].end == tokens[i].start:
        i -= 1
    while j + 1 < len(tokens) and ok(tokens[j + 1]) and tokens[j].end == tokens[j + 1].start:
        j += 1
    return i, j


def affix_run(tokens, a, b, okuri=False):
    """[a, b) を含む漢字・片仮名・数字の続きが「接辞の形」か"""
    if os.environ.get('CN_AFFIX_FORM') == '0':
        return False
    rb = run_bounds(tokens, a, b, okuri)
    if rb is None:
        return False
    i, j = rb
    # 1語だけ（先年・死霊）は複合語の作りの話ではない。珍しい1語の紫は今のまま（同音の選び違いを見分けられない）
    if i == j:
        return False
    cs = []
    prev = None
    for k in range(i, j + 1):
        c = _cls(tokens[k], prev, okuri)
        cs.append(c)
        prev = c
    if None in cs:
        return False
    core = [c for c in cs if c != 'num']
    if core.count('single') > 1:
        return False
    if 'single' in core and len(core) >= 2 and core[0] != 'single' and core[-1] != 'single':
        return False
    if core == ['single'] and 'num' not in cs:
        return False
    # 続きの前後が語の切れ目であること: 前は行の頭・助詞・記号・接頭詞、後ろは行の終わり・助詞・助動詞・記号・する
    # （捨て｜天登録 のように動詞の形のすぐ後ろから始まる続きは、かなの打ち違いが漢字に化けた跡のことが多い）
    if os.environ.get('CN_AFFIX_FORM_EDGE') != '0':
        pv = tokens[i - 1] if i > 0 else None
        nx = tokens[j + 1] if j + 1 < len(tokens) else None
        if pv is not None and pv.end == tokens[i].start and pv.pos not in ('助詞', '記号', '接頭詞'):
            return False
        if (nx is not None and nx.start == tokens[j].end and nx.pos not in ('助詞', '助動詞', '記号')
                and getattr(nx, 'base_form', '') != 'する'):
            return False
    return True
