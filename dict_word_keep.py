"""辞書の語のまま読める行の語を、使われやすさの差や例文の組の少なさだけで別の語に置き換えない（2026-11-14 補正担当・
全体評価の方針 v2 の N）。

なぜ
----
正しい行の正しい語が、「あまり使わない語」の紫や組の少なさを入口に、1打違い・同音のより使われる語へ置き換わっていた
（作った例: 読書に充てている → 当てている・広報担当 → 高等担当）。元の語は辞書の語で、行はそのまま読める。
使われやすさの差と、組が例文に無いことは、打ち違いの跡ではない。

どうやって
----------
既存のファイルは変えない。install() が correction_entry.correct_line を外から包む（答えが出た後に見る）。
答えの直しのうち、根拠が使われやすさ・組の段（紫の所の打ち違い・意味の分類・IMEの選び違い）だけのものについて:
1. 元の行の、書き換えた所に掛かる語がどれも辞書の語（読みのある語で、漢字1字の名詞の切れ端でない）で、
2. 元の行の並びが文法で切れていない（broken_shape・pos_seq_odd がその所の近くに何も出さない）なら、
その書き換えを採らず元の字に戻し、そこに掛かる紫も外す（決められないので紫も付けない）。
ほかの段の直し（打ち違いの跡のある所）はそのまま。特定の語や文字列には合わせない。

切り替え: CN_DICT_WORD_KEEP=0 で前のまま。
"""
import difflib
import functools
import os

_orig = {}

WEAK = ('紫の所の打ち違い', '意味の分類', 'IMEの選び違い', '語の組')


# 広げる試し（2026-11-14 全体評価の頼み）: かな入力・脱字 の直しにも同じ考えを当てる。既定は当てない
WIDE = ('かな入力', '脱字')


def _weak():
    return WEAK + WIDE if os.environ.get('CN_DICT_WORD_KEEP_WIDE') == '1' else WEAK


def _on():
    return os.environ.get('CN_DICT_WORD_KEEP') != '0'


def _kanji(s):
    return bool(s) and all('一' <= c <= '鿿' or c == '々' for c in s)


def _latin(s):
    return any(c.isascii() and c.isalpha() or 'ａ' <= c <= 'ｚ' or 'Ａ' <= c <= 'Ｚ' for c in s)


def _dict_word(t):
    if not getattr(t, 'has_reading', True) or _latin(t.surface):
        return False
    if t.pos in ('助詞', '助動詞'):
        return True
    # 記号・感動詞（ああ・わあ: 文の中の感動詞は打ち違いの跡のことが多い）・人名や地名（辞書の語でも行の中で浮く）は見ない
    if t.pos in ('記号', '感動詞', 'フィラー', 'その他') or str(t.pos_sub or '').startswith('固有名詞'):
        return False
    if t.pos == '名詞' and len(t.surface) == 1 and _kanji(t.surface):
        return False
    try:
        from morphology import dictionary_inflections
        return bool(dictionary_inflections(t.surface))
    except Exception:
        return False


def _verb_run(seq):
    """言い切りの動詞のすぐ後ろに自立の動詞（向く｜なっ）: 文法で切れた並び"""
    for x, y in zip(seq, seq[1:]):
        if (x.pos == '動詞' and (x.infl_form or '') == '基本形' and y.pos == '動詞'
                and str(y.pos_sub or '') == '自立' and x.end == y.start):
            return True
    return False


def _breaks(line, a, b):
    """元の行の a..b の近く（前後1字）に、文法の切れ目の印（崩れた形・品詞の並びの変な所）が在るか"""
    found = []
    try:
        import broken_shape
        found += [x[:2] for x in broken_shape.spans(line) or ()]
    except Exception:
        pass
    try:
        import pos_seq_odd
        found += [x[:2] for x in pos_seq_odd.spots(line) or ()]
    except Exception:
        pass
    if os.environ.get('CN_DICT_WORD_KEEP_ADNOMINAL') != '0':
        found += _adnominal_particle(line)
    return any(s < b + 1 and a - 1 < e for s, e in found)


def _adnominal_particle(line):
    """名詞に掛かる形（ような の な・大きな）のすぐ後ろに、名詞でなく助詞（も・は・が）が来る所。名詞に掛かる形は後ろに
    名詞が要るので、文法の切れ目（2026-11-16 うに: ようなも という不自然な形）。の・ので・のに・ん の前は見ない"""
    try:
        from morphology import tokenize
        toks = list(tokenize(line))
    except Exception:
        return []
    out = []
    for p, n in zip(toks, toks[1:]):
        if p.end != n.start or n.pos != '助詞' or n.surface[:1] in 'のん':
            continue
        if (p.pos == '助動詞' and p.base_form == 'だ' and (p.infl_form or '').startswith('体言接続')) or p.pos == '連体詞':
            out.append((p.start, n.end))
    return out


def _code_any(line):
    try:
        import odd_reason_fill as F
        return bool(F.code_runs(line))
    except Exception:
        return False


def _in_code(line, i1, i2):
    try:
        import odd_reason_fill as F
        return any(a <= i1 and max(i2, i1 + 1) <= b for a, b in F.code_runs(line))
    except Exception:
        return False


def _covers(line, src, i1, i2):
    p = line.find(src)
    while p >= 0:
        if p <= i1 and max(i2, i1 + 1) <= p + len(src):
            return True
        p = line.find(src, p + 1)
    return False


def _kana_piece_end(line, t):
    """1字のかなの自立語が行末か記号の手前に在る（へんじ｜ほ の ほ）。かなの並びの終わりが1字に切れた形
    （2026-11-16: 行末の切れ端を見ず、打ち違いの直しを辞書の語の並びとして戻していた）。CN_DICT_WORD_KEEP_KANA_END=0 で前のまま"""
    if os.environ.get('CN_DICT_WORD_KEEP_KANA_END') == '0':
        return False
    return t.end == len(line) or line[t.end] in '。、．，！？!?」』）) 　'


def _request_frame(text, j2):
    """語の組の直しの直後が頼みの形（〜お願いします・〜願います）か。頼みの前の名詞は頼む事柄（返信・確認）で、語の組の段は
    この形を表の語の1つに決めてから直す（変死→返信: うに 2026-11-02「変死は返信を優先したい」）。使われやすさの差だけの
    直しではないので戻さない（2026-11-17 うに: 最近壊れた）。CN_DICT_WORD_KEEP_REQUEST=0 で前のまま"""
    if os.environ.get('CN_DICT_WORD_KEEP_REQUEST') == '0' or not isinstance(text, str):
        return False
    rest = text[j2:].lstrip('をの')
    return rest.startswith(('お願い', '願い', '願う', '願え', 'ねがい'))


def _set_phrase_frame(text, j1, j2):
    """語の組の直しが、節の頭の名詞1語で、すぐ後ろが いたす・です の決まった言い方（承知いたしました・幸いです）か。
    語の組の段の「続」の組（名詞の直後の いたす・です）で決めた直しで、使われやすさの差だけの直しとは違う
    （2026-11-17 うに: ローマ字入力で以前は直っていた行がそのままになっていた）。CN_DICT_WORD_KEEP_SET_PHRASE=0 で前のまま"""
    if os.environ.get('CN_DICT_WORD_KEEP_SET_PHRASE') == '0' or not isinstance(text, str):
        return False
    head = text[:j1].rstrip()
    if head and head[-1] not in '。、，．,.!?！？「『（(・ 　→-':
        return False
    return text[j2:].startswith(('いたし', 'いたす', '致し', '致す', 'です', 'でし', 'でござ'))


def _same_reading(src, dst):
    """語の組の直しで、元の語と直し先が同じ読みの漢字の語（IME の表記の選び違い: しりょう の 飼料／資料）か。
    （リスとヒョウ／リスト表 のように元が片仮名・かな交じりでも、直し先に漢字があり読みが同じなら同じ）。
    語の組の段は、同じ読みの直しを、直し先が表の組の語で元の語が表の組に出ないときだけ確かとする。読みは正しく
    打てていて、表記の選びだけが組に合わない形なので、使われやすさの差だけの直しとは違う（2026-11-17 うに: 以前は
    直っていた 同じ読みの選び違いの行が、この戻しでそのままになっていた）。CN_DICT_WORD_KEEP_SAME_READING=0 で前のまま"""
    if os.environ.get('CN_DICT_WORD_KEEP_SAME_READING') == '0':
        return False
    if not (isinstance(src, str) and isinstance(dst, str) and src and dst) or src == dst or _latin(src + dst):
        return False
    if not any('一' <= c <= '鿿' for c in dst):
        return False
    try:
        import collocation_repair as C
        a, b = C._word_reading(src), C._word_reading(dst)
    except Exception:
        return False
    return bool(a) and a == b


def _rare_to_common(line, text, hit, j1, j2):
    try:
        import ime_reconvert as R
        from morphology import tokenize
    except Exception:
        return False
    src = max([R._token_rarity(t) for t in hit] + [0])
    if src < R.DOUBT_KEY:
        return False
    new = [t for t in tokenize(text) if t.start < max(j2, j1 + 1) and j1 < t.end and R._strong(t.surface)]
    return bool(new) and max(R._token_rarity(t) for t in new) <= R.KEY_FIX_COMMON


def keep(line, result, input_method='kana'):
    if not _on() or not isinstance(line, str) or not isinstance(result, dict):
        return result
    text = result.get('corrected')
    details = [d for d in result.get('details') or () if isinstance(d, (list, tuple)) and len(d) >= 3]
    if not isinstance(text, str) or text == line or not details:
        return result
    weak_src = {d[0] for d in details if d[2] in _weak() and isinstance(d[0], str) and d[0]}
    if not weak_src and not (os.environ.get('CN_DICT_WORD_KEEP_CODE') != '0' and any(c.isdigit() for c in line)
                             and _code_any(line)):
        return result
    try:
        from morphology import tokenize
        toks = list(tokenize(line))
    except Exception:
        return result
    ops = difflib.SequenceMatcher(None, line, text, autojunk=False).get_opcodes()
    undo = []
    for tag, i1, i2, j1, j2 in ops:
        if tag == 'equal':
            continue
        # S: 型番・略号（英大文字・数字・ハイフンだけの並び: UD-27K）の中の書き換えは、どの段でも採らない。CN_DICT_WORD_KEEP_CODE=0
        if os.environ.get('CN_DICT_WORD_KEEP_CODE') != '0' and _in_code(line, i1, i2):
            undo.append((i1, i2, j1, j2, i1, max(i2, i1 + 1)))
            continue
        # この書き換えが弱い根拠の直しの所か（直しの元の字が、書き換えた所を含む）
        mine = [d for d in details if d[2] in _weak() and isinstance(d[0], str) and d[0] and _covers(line, d[0], i1, i2)]
        if not mine:
            continue
        if all(d[2] == '語の組' for d in mine) and all(_same_reading(d[0], d[1]) for d in mine):
            continue
        if all(d[2] == '語の組' for d in mine) and (_request_frame(text, j2) or _set_phrase_frame(text, j1, j2)):
            continue
        # ローマ字入力の語の組の直しは、語の組の段がローマ字の1打の戻しで確かめた形（mittei → nittei）。ローマ字は1字の隣の
        # キーが少なく、1打で別の語になる組は打ち違いの跡（かなの配列のように何にでもなるのとは違う）。戻さない
        # （2026-11-17 うに: ローマ字入力で以前は直っていた 会議の密偵 などがそのままに）。CN_DICT_WORD_KEEP_ROMAJI=0 で前のまま
        if (input_method == 'romaji' and all(d[2] == '語の組' for d in mine)
                and os.environ.get('CN_DICT_WORD_KEEP_ROMAJI') != '0'):
            continue
        others = [d for d in details if d[2] not in _weak() and d[0] and d[0] in line[max(0, i1 - 2):i2 + 2]]
        if others:
            continue
        hit = [t for t in toks if t.start < max(i2, i1 + 1) and i1 < t.end]
        if not hit or not all(_dict_word(t) for t in hit):
            continue
        # 前後の1語も、英字・感動詞・記号でない（打ち違いの跡が隣に在る行は見ない）
        n0, n1 = toks.index(hit[0]), toks.index(hit[-1])
        side = toks[max(0, n0 - 1):n0] + toks[n1 + 1:n1 + 2]
        if any(_latin(t.surface) or t.pos in ('感動詞', 'フィラー', 'その他') or not getattr(t, 'has_reading', True)
               for t in side):
            continue
        if _verb_run(toks[max(0, n0 - 1):n1 + 2]):
            continue
        # かなの並びが1字の自立語（く｜たせ｜さい の く）に切れている所は、辞書の語の並びではなく切り方が崩れた印
        # （2026-11-15 v1.19.0 の CI: くたせさい→ください の戻しを、たせ が辞書の語だとして元に戻していた）。
        # CN_DICT_WORD_KEEP_KANA_PIECE=0 で前のまま
        if os.environ.get('CN_DICT_WORD_KEEP_KANA_PIECE') != '0' and any(
                len(t.surface) == 1 and 'ぁ' <= t.surface <= 'ゖ' and t.surface not in 'ぁぃぅぇぉっゃゅょゎゕゖ'
                and t.pos in ('動詞', '名詞', '形容詞', '副詞')
                and 0 < t.start and 'ぁ' <= line[t.start - 1] <= 'ゖ'
                and (t.end < len(line) and 'ぁ' <= line[t.end] <= 'ゖ' or _kana_piece_end(line, t))
                for t in toks[max(0, n0 - 1):n1 + 2]):
            continue
        # 元の語が表でとても珍しい語（ime_reconvert の DOUBT_KEY 以上: 本字）で、書き換えた先の語がどれも身近な語なら、
        # 使われやすさの差だけの直しではない（珍しい語そのものが打ち違いの跡）。戻さない（2026-11-16 うに: 以前は直っていた
        # 行が、この戻しで紫も無くなっていた）。CN_DICT_WORD_KEEP_RARE_SRC=0 で前のまま
        if os.environ.get('CN_DICT_WORD_KEEP_RARE_SRC') != '0' and _rare_to_common(line, text, hit, j1, j2):
            continue
        # 文の途中の終助詞（すずし｜いす｜ぜ｜が の ぜ）は、かなの並びの切り方が崩れた印。辞書の語の並びとは見ない
        # （2026-11-14 補正担当: かなのまま打った誤字の束で、すぜ→かぜ・はすん→はん の直しを戻していた）。
        # CN_DICT_WORD_KEEP_MID_FINAL=0 で前のまま
        if os.environ.get('CN_DICT_WORD_KEEP_MID_FINAL') != '0' and any(
                t.pos == '助詞' and str(t.pos_sub or '').startswith('終助詞') and k + 1 < len(toks)
                and toks[k + 1].pos != '記号'
                for k, t in enumerate(toks[max(0, n0 - 1):n1 + 2], max(0, n0 - 1))):
            continue
        a, b = hit[0].start, hit[-1].end
        if _breaks(line, a, b):
            continue
        undo.append((i1, i2, j1, j2, a, b))
    if not undo:
        return result
    parts = []
    for tag, i1, i2, j1, j2 in ops:
        if tag != 'equal' and any(u[0] == i1 and u[1] == i2 and u[2] == j1 for u in undo):
            parts.append(line[i1:i2])
        else:
            parts.append(text[j1:j2] if tag != 'equal' else line[i1:i2])
    new = ''.join(parts)
    out = dict(result)
    ops2 = [o for o in difflib.SequenceMatcher(None, line, new, autojunk=False).get_opcodes() if o[0] != 'equal']
    out.update({'corrected': new, 'changed': bool(ops2), 'spans': [[o[3], o[4]] for o in ops2],
                'original_spans': [[o[1], o[2]] for o in ops2],
                'details': [d for d in result.get('details') or ()
                            if not (isinstance(d, (list, tuple)) and len(d) >= 3 and d[2] in _weak()
                                    and isinstance(d[1], str) and d[1] and d[1] not in new)]})
    near = [(u[4], u[5]) for u in undo]

    def far(x):
        return not (len(x) >= 2 and isinstance(x[0], int) and any(x[0] < e and s < x[1] for s, e in near))
    for key in ('odd_spans', 'unsure_spans', 'odd_reasons'):
        if key in result:
            out[key] = [x for x in result.get(key) or () if far(x)]
    return out


def correct_line(line, *args, **kwargs):
    result = _orig['correct_line'](line, *args, **kwargs)
    try:
        im = kwargs.get('input_method', args[3] if len(args) > 3 else 'kana')
        return keep(line, result, input_method=im)
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
