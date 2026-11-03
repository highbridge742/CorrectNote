# CorrectNote — 誤字補正メモ帳
# Copyright (C) 2026 Takahashi Yuu
# SPDX-License-Identifier: GPL-3.0-or-later
"""文の形として成り立たない並び（1打の打ち違いが別の字に変換されて残った所）に紫を付ける（手分け C・2026-11-01）。

特定の語は見ない。品詞と字の種類の並びだけで決める:
  - まし・でし（丁寧の連用）の後ろが た・て・ょう でない
  - を＋サ変名詞（漢字）の直後に する 以外の自立の動詞
  - 漢字の名詞（2字以上）＋1拍の漢字1字の名詞＋助詞／助詞＋1拍の漢字1字＋漢字の名詞（2字以上）
  - 動詞・形容詞・助動詞の後ろに1拍の漢字1字の名詞が付いて終わる（後ろが無いか助動詞）
  - 漢字1字の名詞が、助詞・記号・名詞・助動詞を挟まず用言どうしの間に挟まる
  - 片仮名1字だけが漢字・かなに挟まる／片仮名の短い語が漢字に挟まる・助詞の後ろで ン などから始まる
  - 文の途中のフィラー（あ・え など）・連用形の後ろの終助詞の直後に漢字・片仮名
  - 漢字・片仮名の接頭詞の後ろに かなで始まる用言
  - 文の途中の、句読点・括弧ではない記号（= など）
紫を付ける（直し先は決めない）。ただし、かな入力で 1拍の漢字1字が前後の語の読みの隣のキーを一緒に押した
1字の足しと見える所（語の前後・言い終わりの後ろの1字）は、その字を除いて直す（1字の足しの戻し）。前の段が直した所・紫の所・本人が「補正不要」にした所は見ない。
"""
import difflib
import re

_HIRA = re.compile(r'[ぁ-ゟ]')
_SAHEN_OK = {'する', 'できる', '出来る', 'なさる', 'いたす', '致す', 'される', 'させる', 'くださる',
             '始める', '終わる', '終える', '続ける', '出す', '直す'}
_SMALL = 'ゃゅょぁぃぅぇぉゎ'
# する の連用 し の直後に付く動詞（し直す・し始める など）
_AFTER_SHI = {'直す', '始める', '終わる', '終える', '続ける', '忘れる', '合う', '損ねる', '損なう', '過ぎる', '出す',
              '切る', '込む', '慣れる', '尽くす', '遂げる', '兼ねる', '返す', '得る', '残す', '漏らす', '逃す', '向ける'}
# 助詞の並びとして成り立たない組（が は・を は など。逆の は が／も を も）
_BAD_PAIRS = {('が', 'は'), ('が', 'も'), ('が', 'か'), ('を', 'は'), ('を', 'か'), ('を', 'が'), ('が', 'を'),
              ('は', 'が'), ('は', 'を'), ('も', 'が'), ('も', 'を'), ('は', 'も'), ('も', 'は')}
# ひらがなと日本語の字の間に挟まると打ち違いの記号（= @ # など。漢字＋漢字の間は 牛乳+パン のような書き方があるので見ない）
_STRAY_SYMBOL = re.compile(r'(?<=[\u3041-\u3093])[=＝@＠#＃$＄%％^＾&＆*＊+＋|｜~\\＼<>＜＞;；]+'
                           r'(?=[\u3041-\u30ff\u4e00-\u9fff々])')



def _mixed_katakana_word(line, a, b):
    """片仮名1字の後ろのかなを片仮名にすると辞書の片仮名の名詞1語になる所（スくりーん・シャつ）は、混ぜ書きの名詞
    （浮いた1字ではない・2026-11-03 tests_mixed_nominal_argument）。"""
    import os
    if os.environ.get('CN_BROKEN_MIXED_KATA') == '0':
        return False
    j = b
    while j < len(line) and ('ぁ' <= line[j] <= 'ゖ' or line[j] == 'ー'):
        j += 1
    if j == b:
        return False
    try:
        from morphology import tokenize
    except Exception:
        return False
    for k in range(j, b, -1):
        kata = line[a:b] + ''.join(chr(ord(c) + 0x60) if 'ぁ' <= c <= 'ゖ' else c for c in line[b:k])
        tt = list(tokenize(kata))
        if len(tt) == 1 and tt[0].pos == '名詞' and tt[0].has_reading:
            return k
    return False


def mixed_katakana_spans(line):
    """片仮名で始まり、後ろのかなを片仮名にすると辞書の片仮名の名詞1語になる所（スくりーん・スクりーン・シャつ） [(start, end)]。"""
    out = []
    i = 0
    while i < len(line):
        ch = line[i]
        if 'ァ' <= ch <= 'ヶ' and (i == 0 or not ('ァ' <= line[i - 1] <= 'ヶ' or line[i - 1] == 'ー')):
            j = i
            while j < len(line) and ('ァ' <= line[j] <= 'ヶ' or line[j] == 'ー'):
                j += 1
            if j < len(line) and 'ぁ' <= line[j] <= 'ゖ':
                k = j
                while k < len(line) and ('ぁ' <= line[k] <= 'ゖ' or 'ァ' <= line[k] <= 'ヶ' or line[k] == 'ー'):
                    k += 1
                try:
                    from morphology import tokenize
                    for e in range(k, j, -1):
                        kata = ''.join(chr(ord(c) + 0x60) if 'ぁ' <= c <= 'ゖ' else c for c in line[i:e])
                        tt = list(tokenize(kata))
                        if len(tt) == 1 and tt[0].pos == '名詞' and tt[0].has_reading:
                            out.append((i, e))
                            break
                except Exception:
                    pass
            i = max(j, i + 1)
            continue
        i += 1
    return out

def _kanji(s):
    return bool(s) and all('一' <= c <= '鿿' or c == '々' for c in s)


def _kata(s):
    return bool(s) and all('ァ' <= c <= 'ヺ' or c == 'ー' for c in s)


def _hira_head(s):
    return bool(s) and bool(_HIRA.match(s[0]))


def _mora(r):
    return len([c for c in (r or '') if c not in _SMALL])


def _one_kanji_noun(t):
    return (t.pos == '名詞' and len(t.surface) == 1 and _kanji(t.surface)
            and not (t.pos_sub or '').startswith(('接尾', '非自立', '数', '副詞可能')))


_EXTRA = ('語の後ろに1字が混じっています', '語の前に1字が混じっています', '言い終わりの後ろに1字が混じっています')


def _reading_of(t):
    return t.reading if getattr(t, 'has_reading', True) and t.reading else t.surface


def extra_chars(text, tokens=None):
    """1拍の漢字1字が、前後の語の読みのどちらかの隣のキーを一緒に押した1字の足し（かな入力）と見える所。
    [(字の始まり, 字の終わり)]。紫の決め手（_EXTRA）の付いた字だけ。"""
    if tokens is None:
        import morphology
        tokens = list(morphology.tokenize(text))
    import kana_layout
    out = []
    for a, b, why in spans(text, tokens):
        if why not in _EXTRA:
            continue
        for i, t in enumerate(tokens):
            if not (a <= t.start and t.end <= b and _one_kanji_noun(t) and _mora(t.reading) == 1):
                continue
            p = _reading_of(tokens[i - 1]) if i else ''
            q = _reading_of(tokens[i + 1]) if i + 1 < len(tokens) else ''
            try:
                if kana_layout.single_key_drop_adjacency(p + t.reading + q, p + q):
                    out.append((t.start, t.end))
            except Exception:
                pass
    return sorted(set(out))


def _clean_after_cut(text, d):
    """字を除いた行の、除いた所の前後に別の決め手が残らないこと（書きまし歯 → 書きまし のような半端は採らない）。"""
    ks, ke = d
    cut = text[:ks] + text[ke:]
    try:
        return not any(a <= ks <= b for a, b, _w in spans(cut))
    except Exception:
        return False


def spans(text, tokens=None):
    """(start, end, 理由) の並び。text の位置。"""
    if tokens is None:
        import morphology
        tokens = list(morphology.tokenize(text))
    out = []
    n = len(tokens)
    for i, t in enumerate(tokens):
        p = tokens[i - 1] if i else None
        q = tokens[i + 1] if i + 1 < n else None
        sub = t.pos_sub or ''
        if t.pos == '助動詞' and t.surface in ('まし', 'でし') and (q is None or q.surface[:1] not in 'たてょ'):
            out.append((t.start, q.end if q is not None and q.pos != '記号' else t.end, '丁寧の形の後ろが続きません'))
        if (t.pos == '名詞' and sub == 'サ変接続' and _kanji(t.surface) and p and p.surface == 'を'
                and q and q.pos == '動詞' and (q.pos_sub or '') == '自立' and q.base_form not in _SAHEN_OK):
            out.append((t.start, q.end, '名詞と動詞のつながりが変です'))
        if _one_kanji_noun(t) and _mora(t.reading) == 1:
            if (p and p.pos == '名詞' and _kanji(p.surface) and len(p.surface) >= 2
                    and not (p.pos_sub or '').startswith(('副詞可能', '数')) and q and q.pos == '助詞'):
                out.append((p.start, t.end, '語の後ろに1字が混じっています'))
            if (p and p.pos == '助詞' and q and q.pos == '名詞' and len(q.surface) >= 2 and _kanji(q.surface[:1])
                    and (_kanji(q.surface) or (q.pos_sub or '').startswith('副詞可能'))):
                out.append((t.start, q.end, '語の前に1字が混じっています'))
            if p and p.pos in ('助動詞', '動詞', '形容詞') and (q is None or q.pos == '助動詞' or q.pos == '記号'):
                out.append((t.start, t.end, '言い終わりの後ろに1字が混じっています'))
        if (_one_kanji_noun(t) and p and q and p.pos not in ('助詞', '記号', '連体詞', '接頭詞', '形容詞', '名詞')
                and q.pos not in ('助詞', '記号', '助動詞', '名詞')):
            out.append((t.start, t.end, '1字だけ浮いています'))
        if _kata(t.surface) and len(t.surface) <= 2:
            if p and q and _kanji(p.surface[-1:]) and _kanji(q.surface[:1]):
                out.append((t.start, t.end, '片仮名が混じっています'))
            elif (q and _kanji(q.surface[:1]) and not (q.pos_sub or '').startswith('接尾') and (not p or p.pos == '助詞')
                  and (len(t.surface) == 1 or t.surface[0] in 'ンーァィゥェォャュョッ')):
                out.append((t.start, q.end, '片仮名が混じっています'))
            elif p and _kanji(p.surface[-1:]) and q and q.pos != '助詞' and q.pos != '記号':
                out.append((t.start, t.end, '片仮名が混じっています'))
        if (len(t.surface) == 1 and _kata(t.surface) and t.surface not in 'ーヶヵ'
                and not (p and _kata(p.surface[-1:])) and not (q and _kata(q.surface[:1])) and (p or q)
                and not (p and p.pos == '記号' and (q is None or q.pos == '記号'))
                and not _mixed_katakana_word(text, t.start, t.end)):
            out.append((t.start, t.end, '片仮名1字が混じっています'))
        if (t.pos == '動詞' and t.surface == 'し' and t.base_form == 'する' and q and q.pos == '動詞'
                and (q.pos_sub or '') == '自立' and _kanji(q.surface[:1]) and q.base_form not in _AFTER_SHI):
            out.append((t.start, q.end, '動詞のつながりが変です'))
        if t.pos == '助詞' and q and q.pos == '助詞' and (t.surface, q.surface) in _BAD_PAIRS:
            out.append((t.start, q.end, '助詞の並びが変です'))
        if (t.pos == '形容詞' and t.surface.endswith('き') and q and q.pos == '動詞' and (q.pos_sub or '') == '自立'
                and q.base_form not in ('過ぎる', 'すぎる')):
            out.append((t.start, q.end, '形容詞と動詞のつながりが変です'))
        if t.pos == '助詞' and sub == '並立助詞' and t.surface == 'や' and q and q.pos == '動詞':
            out.append((t.start, q.end, '助詞と動詞のつながりが変です'))
        if (t.pos == '動詞' and sub == '接尾' and p and p.pos == '助詞' and i >= 2
                and (_kanji(tokens[i - 2].surface[-1:]) or _kata(tokens[i - 2].surface[-1:]))):
            out.append((t.start, t.end, '助詞の後ろに動詞の語尾が付いています'))
        if t.pos == '助動詞' and t.surface == 'う' and p and p.pos == '動詞' and (p.infl_form or '') == '連用形':
            out.append((p.start, t.end, '動詞の形が続きません'))
        if (t.pos == '名詞' and sub == '数' and _kanji(t.surface) and p and p.pos == '名詞' and _kanji(p.surface[-1:])
                and not (p.pos_sub or '').startswith('数') and q and q.pos == '動詞' and (q.pos_sub or '') == '自立'):
            out.append((t.start, t.end, '数の字が混じっています'))
        if (t.pos == '助詞' and sub == '終助詞' and t.surface in ('よ', 'な', 'わ', 'ね', 'ぞ') and p and p.pos == '助詞'
                and (p.pos_sub or '').startswith('格助詞') and (i >= 2 and any(_kanji(c) for c in tokens[i - 2].surface))
                and q and q.pos == '動詞' and _hira_head(q.surface) and q.end == len(text.rstrip('。．.！!？?\n'))):
            out.append((t.start, q.end, '文の途中に1字が混じっています'))
        # 行の頭の助詞は前の行から続く書き方があるので見ない。1字のフィラーの直後に漢字（句読点なし）だけ
        if ((i == 0 or (p and p.pos == '記号' and not p.surface.strip())) and q and _kanji(q.surface[:1])
                and t.pos == 'フィラー' and len(t.surface) == 1):
            out.append((t.start, q.end, '行の頭に1字が混じっています'))
        if (t.pos == '助詞' and sub == '接続助詞' and t.surface in ('て', 'で') and q and q.pos == '名詞' and _kata(q.surface)
                and (i + 2 >= n or tokens[i + 2].pos == '記号')):
            out.append((t.start, q.end, '言い終わりに片仮名が混じっています'))
        if (t.pos == '名詞' and _kanji(t.surface) and sub in ('サ変接続', '一般') and q and q.pos == '動詞'
                and q.base_form == 'なる' and _hira_head(q.surface)):
            out.append((t.start, q.end, '名詞と動詞のつながりが変です'))
        if t.pos == 'フィラー' and p and q and p.pos != '記号' and q.pos != '記号':
            out.append((t.start, q.end, '文の途中に1字が混じっています'))
        if (t.pos == '助詞' and sub == '終助詞' and p and q
                and ((p.pos in ('動詞', '形容詞') and '連用' in (p.infl_form or '')) or _kata(p.surface))
                and q.pos in ('動詞', '形容詞', '名詞', '接頭詞') and not _hira_head(q.surface)):
            out.append((t.start, q.end, '文の途中に1字が混じっています'))
        if (t.pos == '接頭詞' and not _hira_head(t.surface) and q and q.pos not in ('名詞', '接頭詞', '記号')
                and _hira_head(q.surface)):
            out.append((t.start, q.end, '前に付く字の後ろが続きません'))
    for k, ch in enumerate(text):
        # 付く先の かな の無い濁点・半濁点（行の頭・漢字や記号の後ろ）
        if ch in '゛゜ﾞﾟ' and not (k and text[k - 1] in '「『（(\'"“‘【［[') and (k == 0 or not ('\u3041' <= text[k - 1] <= '\u30fa' or '\uff66' <= text[k - 1] <= '\uff9d')):
            out.append((k, k + 1, '付く字の無い濁点が混じっています'))
    for mt in _STRAY_SYMBOL.finditer(text):
        out.append((mt.start(), mt.end(), '文の途中に記号が混じっています'))
    seen, uniq = set(), []
    for a, b, why in out:
        if (a, b) not in seen and a < b:
            seen.add((a, b))
            uniq.append((a, b, why))
    return uniq


def repair_line(line, result, decided=(), input_method='kana'):
    """紫を足す。かな入力で、1拍の漢字1字が隣のキーを一緒に押した1字の足しと見える所だけは、その字を除いて直す。
    ほかの所は直し先を決めない（odd_respell の戻しも当てない）。"""
    if not isinstance(result, dict):
        return result
    done = result.get('corrected') or line
    try:
        import morphology
        tokens = list(morphology.tokenize(done))
        found = spans(done, tokens)
        drops = extra_chars(done, tokens) if (found and input_method == 'kana') else []
    except Exception:
        return result
    if not found:
        return result
    marked = [tuple(x[:2]) for x in list(result.get('odd_spans') or ()) + list(result.get('unsure_spans') or ())]
    ops = difflib.SequenceMatcher(None, done, line, autojunk=False).get_opcodes()

    def to_org(s, e):
        for tag, i1, i2, j1, j2 in ops:
            if tag == 'equal' and i1 <= s and e <= i2:
                return (s - i1 + j1, e - i1 + j1)
        return None

    def to_org_wide(s, e):
        # 前の段が直した所に掛かるときは、掛かる元の行の範囲をまとめて返す（紫だけに使う）
        lo, hi = None, None
        for tag, i1, i2, j1, j2 in ops:
            if i1 < e and s < i2 or (i1 == i2 and s <= i1 <= e):
                a = j1 + max(0, s - i1) if tag == 'equal' else j1
                b = j1 + min(i2, e) - i1 if tag == 'equal' else j2
                lo = a if lo is None else min(lo, a)
                hi = b if hi is None else max(hi, b)
        return (lo, hi) if lo is not None and lo < hi else None

    def blocked(org):
        return any(x < org[1] and org[0] < y for x, y in list(decided or ()) + marked)

    add, cut = [], []
    for s, e, why in found:
        org = to_org(s, e)
        if org is None:
            # 前の段の直しで崩れた形になった所は、直しはそのまま・元の行の範囲に紫だけ
            wide = to_org_wide(s, e)
            if wide and not blocked(wide):
                add.append((wide[0], wide[1], why))
            continue
        if blocked(org):
            continue  # 紫の所・補正不要の所
        inner = [d for d in drops if s <= d[0] and d[1] <= e and _clean_after_cut(done, d)]
        if why in _EXTRA and inner:
            cut.extend(inner)
            continue
        add.append((org[0], org[1], why))
    cut = sorted(set(cut))
    # 除いた字に掛かる別の決め手の紫は付けない
    add = [x for x in add if not any(to_org(*d) and x[0] < to_org(*d)[1] and to_org(*d)[0] < x[1] for d in cut)]
    if not add and not cut:
        return result
    out = dict(result)
    if cut:
        new = done
        details = list(result.get('details') or ())
        for ks, ke in reversed(cut):
            details.append([done[max(0, ks - 2):min(len(done), ke + 2)],
                            done[max(0, ks - 2):ks] + done[ke:min(len(done), ke + 2)], '1字の足し'])
            new = new[:ks] + new[ke:]
        ops2 = [o for o in difflib.SequenceMatcher(None, line, new, autojunk=False).get_opcodes() if o[0] != 'equal']
        out.update({'original': line, 'corrected': new, 'changed': new != line, 'details': details,
                    'spans': [[o[3], o[4]] for o in ops2], 'original_spans': [[o[1], o[2]] for o in ops2]})
    if add:
        # 重なる紫は1つにまとめる（理由は先のもの）
        merged = []
        for a, b, why in sorted(add):
            if merged and a < merged[-1][1]:
                merged[-1] = (merged[-1][0], max(b, merged[-1][1]), merged[-1][2])
            else:
                merged.append((a, b, why))
        out['odd_spans'] = sorted(set(tuple(x[:2]) for x in (result.get('odd_spans') or ())) | {(a, b) for a, b, _ in merged})
        out['odd_reasons'] = list(result.get('odd_reasons') or ()) + merged
        out['face_doubt_spans'] = sorted(set(tuple(x[:2]) for x in (result.get('face_doubt_spans') or ()))
                                         | {(a, b) for a, b, _ in merged})
    return out
