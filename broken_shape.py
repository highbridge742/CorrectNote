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
# 動作の名詞の後ろに直に付く敬語の動詞（追加いただく・ご確認ください・お願い申し上げる）。2026-11-16 うに: 追加いただけ に紫。
# CN_BROKEN_SAHEN_HONOR=0 で前のまま
_SAHEN_HONOR = {'いただく', 'いただける', '頂く', '頂ける', '願う', '申し上げる', '差し上げる', '賜る'}
_SMALL = 'ゃゅょぁぃぅぇぉゎ'
# する の連用 し の直後に付く動詞（し直す・し始める など）
_AFTER_SHI = {'直す', '始める', '終わる', '終える', '続ける', '忘れる', '合う', '損ねる', '損なう', '過ぎる', '出す',
              '切る', '込む', '慣れる', '尽くす', '遂げる', '兼ねる', '返す', '得る', '残す', '漏らす', '逃す', '向ける'}
# 助詞の並びとして成り立たない組（が は・を は など。逆の は が／も を も）
_BAD_PAIRS = {('が', 'は'), ('が', 'も'), ('が', 'か'), ('を', 'は'), ('を', 'か'), ('を', 'が'), ('が', 'を'),
              ('は', 'が'), ('は', 'を'), ('も', 'が'), ('も', 'を'), ('は', 'も'), ('も', 'は')}
_INDEF = frozenset(('誰', 'だれ', '何', 'なに', 'どれ', 'どこ', 'いずれ', 'どちら', 'いつ'))
# ひらがなと日本語の字の間に挟まると打ち違いの記号（= @ # など。漢字＋漢字の間は 牛乳+パン のような書き方があるので見ない）
_STRAY_SYMBOL = re.compile(r'(?<=[\u3041-\u3093])[=＝@＠#＃$＄%％^＾&＆*＊+＋|｜~\\＼<>＜＞;；]+'
                           r'(?=[\u3041-\u30ff\u4e00-\u9fff々])')



def _symbol_splits_word(text, a, b):
    """記号を抜くと、両側の字が1つの語になる（かなの語の中に割り込んだ記号）か。両側がそれぞれ語として成り立つ形
    （泳ぐ＝運動・休みあり＝週末: 記号で語をつなぐメモの書き方）は紫にしない（2026-11-14 補正担当・全体評価の方針 v1 の2）。
    CN_STRAY_SYMBOL_SPLIT=0 で前のまま（いつも紫）"""
    import os
    if os.environ.get('CN_STRAY_SYMBOL_SPLIT') == '0':
        return True
    try:
        from morphology import tokenize
        # 記号のすぐ前が助詞・助動詞（家に＝透けて）なら、語をつなぐ書き方ではない（手のずれで記号が混じった跡）
        left = [t for t in tokenize(text[:a]) if t.end == a]
        if left and left[-1].pos in ('助詞', '助動詞'):
            return True
        joined = text[:a] + text[b:]
        for t in tokenize(joined):
            if t.start < a < t.end and t.pos not in ('記号',) and getattr(t, 'has_reading', True):
                return True
        return False
    except Exception:
        return True


def _suffix_kanji(face):
    """辞書がその漢字1字を名詞に付く語（接尾の一般・助数詞: 段・行・字・型）として持つか。"""
    try:
        from morphology import dictionary_inflections
        return any(r[0].startswith(('名詞,接尾,一般', '名詞,接尾,助数詞')) for r in dictionary_inflections(face) or ())
    except Exception:
        return False


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


def _whole_word(face):
    """名詞＋1字（補助｜輪）が、まとめて1語として表に在るか（seed_japanese.is_unit）。在れば浮いた1字ではない
    （2026-11-13 全体評価の作った正しい文: 補助輪 の 輪 を除いていた）。CN_BROKEN_WHOLE_WORD=0 で前のまま"""
    if __import__('os').environ.get('CN_BROKEN_WHOLE_WORD') == '0':
        return False
    try:
        import seed_japanese
        return seed_japanese.is_unit(face) is True
    except Exception:
        return False


_EXTRA = ('語の後ろに1字が混じっています', '語の前に1字が混じっています', '言い終わりの後ろに1字が混じっています')


def _reading_of(t):
    return t.reading if getattr(t, 'has_reading', True) and t.reading else t.surface


def _adnominal_word(surface):
    """辞書に連体詞の行がある語か（あの・その）。"""
    try:
        from morphology import dictionary_inflections
        return any(str(r[0]).startswith('連体詞') for r in dictionary_inflections(surface) or ())
    except Exception:
        return False


def _particle_word(surface):
    """辞書に副助詞の行がある語か（なんか）。"""
    try:
        from morphology import dictionary_inflections
        return any(str(r[0]).startswith('助詞,副助詞') for r in dictionary_inflections(surface) or ())
    except Exception:
        return False


def _prefix_row(surface, pos):
    """辞書に「接頭詞,<pos>接続」の行がある字か（超 の 形容詞接続）。"""
    try:
        from morphology import dictionary_inflections
        return any(str(r[0]).startswith('接頭詞,%s接続' % pos) for r in dictionary_inflections(surface) or ())
    except Exception:
        return False


def _long_noun_reading(surface):
    """漢字1字が、固有名詞・接尾でない名詞として2拍以上の読みを辞書に持つか（間＝あいだ）。"""
    if __import__('os').environ.get('CN_BROKEN_NO_HEAD') == '0':
        return False
    try:
        from morphology import dictionary_inflections
        rows = dictionary_inflections(surface) or ()
    except Exception:
        return False
    return any(str(r[0]).startswith(('名詞,一般', '名詞,副詞可能')) and len(r) > 3 and _mora(r[3]) >= 2 for r in rows)


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
            if i and tokens[i - 1].surface == 'の' and tokens[i - 1].pos == '助詞' and _long_noun_reading(t.surface):
                # の＋漢字1字の名詞（しばらくの｜間｜秘密に）は、解析が1拍に読んでも2拍以上の読み（あいだ）の名詞の頭で
                # ありうる（例文 Tatoeba の正しい文で 間 を抜いていた・2026-11-07）。CN_BROKEN_NO_HEAD=0 で前のまま
                continue
            nx = tokens[i + 1] if i + 1 < len(tokens) else None
            if (nx is not None and nx.start == t.end and nx.pos == '名詞'
                    and str(nx.pos_sub or '').startswith('副詞可能') and _kanji(nx.surface) and len(nx.surface) >= 2
                    and __import__('os').environ.get('CN_BROKEN_EXTRA_ADV_HEAD') != '0'):
                # 漢字1字の名詞＋副詞可能の名詞（市｜全体・県｜全域）は、範囲を言う名詞の前に置いた普通の名詞の形でありうる。
                # 打った漢字を除いて消さない（紫は残る・2026-11-20 例文 2000(e) 市全体→全体）。CN_BROKEN_EXTRA_ADV_HEAD=0 で前のまま
                continue
            if (nx is not None and nx.start == t.end and nx.pos == '名詞'
                    and str(nx.pos_sub or '').startswith('一般') and _kanji(nx.surface) and len(nx.surface) >= 2
                    and getattr(nx, 'has_reading', True)
                    and __import__('os').environ.get('CN_BROKEN_EXTRA_NOUN_HEAD') != '0'):
                # 漢字1字の名詞＋漢字の普通の名詞（市｜東部・客｜間 は別）も、前に置いた名詞の形でありうる。打った漢字を消さない
                # （紫は残る・2026-11-20 例文 2000(f) 市東部→東部）。CN_BROKEN_EXTRA_NOUN_HEAD=0 で前のまま
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
        if any(a <= ks <= b for a, b, _w in spans(cut)):
            return False
    except Exception:
        return False
    # 除いた所の手前が、言い切りの用言のすぐ後ろに形容詞が来る形（する｜よい｜です: 予定です を よい手です と打った）
    # のままなら、1字の足しではなく語の打ち違い。除いても文にならない（2026-11-06 かなの試験）。CN_BROKEN_CUT_VERB_ADJ=0
    import os
    if os.environ.get('CN_BROKEN_CUT_VERB_ADJ') != '0':
        try:
            import morphology
            toks = list(morphology.tokenize(cut))
            for x, y in zip(toks, toks[1:]):
                if x.end == y.start and y.start <= ks <= y.end and x.pos == '動詞' \
                        and (x.infl_form or '').startswith('基本形') and y.pos == '形容詞':
                    return False
        except Exception:
            pass
    return True


def _kata_word_known(k):
    try:
        import corrector
        return bool(corrector._katakana_known_or_compound(k))
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
        # でしょ・ましょ（未然の形）の後ろは う だけ。言い切りの でしょ（そうでしょ。でしょね）は見ない。後ろに語が続いて
        # う でないなら崩れた形（でしょいか: う を隣の い と打った跡）。2026-11-19 うに。CN_BROKEN_SHO_TAIL=0 で前のまま
        if (t.pos == '助動詞' and t.surface in ('でしょ', 'ましょ') and q is not None and q.pos != '記号'
                and q.surface[:1] not in 'うーぅっ〜～' and not (q.pos == '助詞' and q.surface in ('ね', 'よ', 'ねえ', 'な', 'よね'))
                and __import__('os').environ.get('CN_BROKEN_SHO_TAIL') != '0'):
            out.append((t.start, q.end, '丁寧の形の後ろが続きません'))
        if (t.pos == '名詞' and sub == 'サ変接続' and _kanji(t.surface) and p and p.surface == 'を'
                and q and q.pos == '動詞' and (q.pos_sub or '') == '自立' and q.base_form not in _SAHEN_OK
                and not (q.base_form in _SAHEN_HONOR and __import__('os').environ.get('CN_BROKEN_SAHEN_HONOR') != '0')):
            out.append((t.start, q.end, '名詞と動詞のつながりが変です'))
        if _one_kanji_noun(t) and _mora(t.reading) == 1:
            if (p and p.pos == '名詞' and _kanji(p.surface) and len(p.surface) >= 2
                    and not (p.pos_sub or '').startswith(('副詞可能', '数')) and q and q.pos == '助詞'
                    # 非自立:副詞可能（以上・以下｜間）も副詞可能の名詞（2026-11-20 補正担当、判断 POLICY.md A の 秒以上間。
                    # CN_BROKEN_ADV_NONINDEP=0 で前のまま）
                    and not ('副詞可能' in (p.pos_sub or '') and __import__('os').environ.get('CN_BROKEN_ADV_NONINDEP') != '0')
                    and not _whole_word(p.surface + t.surface)):
                out.append((p.start, t.end, '語の後ろに1字が混じっています'))
            if (p and p.pos == '助詞' and q and q.pos == '名詞' and len(q.surface) >= 2 and _kanji(q.surface[:1])
                    and (_kanji(q.surface) or (q.pos_sub or '').startswith('副詞可能'))
                    and not _whole_word(t.surface + q.surface)):
                out.append((t.start, q.end, '語の前に1字が混じっています'))
            if (p and p.pos in ('助動詞', '動詞', '形容詞') and (q is None or q.pos == '助動詞' or q.pos == '記号')
                    and not ((p.infl_form or '') in ('基本形', '体言接続', '連体形') and q is not None and q.pos == '助動詞'
                             and __import__('os').environ.get('CN_BROKEN_ATTR_NOUN') != '0')
                    # 言い切り・連体の形＋行末の1字の名詞（母が描いた画）は名詞を修飾する正しい形（2026-11-14 全体評価の方針 v2 の L）。
                    # 動詞・た の後ろで、名詞の一般の語だけ。CN_BROKEN_ATTR_END=0 で前のまま
                    and not ((p.infl_form or '') in ('基本形', '体言接続', '連体形') and p.pos in ('動詞', '助動詞')
                             and (p.pos == '動詞' or p.surface == 'た') and (t.pos_sub or '') == '一般'
                             and (q is None or q.surface in '。．.！？!?'
                                  # 読点の前も同じ（君が買った絵、見ていい？・2026-11-20 補正担当の例文の正しい文）。
                                  # CN_BROKEN_ATTR_END_COMMA=0 で前のまま
                                  or (q.surface in '、，,' and __import__('os').environ.get('CN_BROKEN_ATTR_END_COMMA') != '0'))
                             and __import__('os').environ.get('CN_BROKEN_ATTR_END') != '0')
                    and not ((p.infl_form or '') in ('基本形', '体言接続', '連体形') and q is not None
                             and (q.surface in '、，,'
                                  # 開き括弧の前も同じ（無視する間（0〜300ms）: 括弧は前の語の言い添え。2026-11-21 うに
                                  # 説明書の文の紫）。CN_BROKEN_ATTR_BRACKET=0 で前のまま
                                  or ((q.pos_sub or '') == '括弧開'
                                      and __import__('os').environ.get('CN_BROKEN_ATTR_BRACKET') != '0'))
                             and _long_noun_reading(t.surface)
                             and __import__('os').environ.get('CN_BROKEN_ATTR_COMMA') != '0')):
                # 連体の形＋読点の前の1字の名詞で、2拍以上の読みを持つ語（待っている間、）も名詞を修飾する正しい形（2026-11-07）
                # 言い切り・連体の形＋1字の名詞＋だ・です（いい子だから・赤い花だ）は名詞を修飾する正しい形（2026-11-07）
                out.append((t.start, t.end, '言い終わりの後ろに1字が混じっています'))
        if (_one_kanji_noun(t) and p and q and p.pos not in ('助詞', '記号', '連体詞', '接頭詞', '形容詞', '名詞')
                and q.pos not in ('助詞', '記号', '助動詞', '名詞')
                # 前の漢字1字（解析が動詞と見た 採）とつないだ2字が表の1語（採水）なら、解析の切り違いで浮いた1字ではない
                # （2026-11-15 補正担当・作った正しい文）。CN_BROKEN_LONE_JOIN=0 で前のまま
                and not (len(p.surface) == 1 and _kanji(p.surface) and _whole_word(p.surface + t.surface)
                         and __import__('os').environ.get('CN_BROKEN_LONE_JOIN') != '0')
                # 前の漢字1字と後ろの送り仮名（見｜做｜し）をつないだ形が表の1語（見做し）なら、解析が切り違えた動詞
                # （2026-11-22 補正担当、誤判定タブの正しい文）。CN_BROKEN_LONE_JOIN_OKURI=0 で前のまま
                and not (len(p.surface) == 1 and _kanji(p.surface) and p.end == t.start and q.start == t.end
                         and q.surface and all('ぁ' <= c <= 'ゖ' for c in q.surface)
                         and _whole_word(p.surface + t.surface + q.surface)
                         and __import__('os').environ.get('CN_BROKEN_LONE_JOIN_OKURI') != '0')
                # 連体の形の動詞・助動詞＋2拍以上の読みの1字の名詞＋副詞（している｜間｜少しも）は、名詞を修飾した句が
                # 副詞に続く正しい形（2026-11-20 正しい文の見直し）。CN_BROKEN_LONE_ATTR_ADV=0 で前のまま
                and not (p.pos in ('動詞', '助動詞') and (p.infl_form or '') in ('基本形', '体言接続', '連体形')
                         and q.pos == '副詞' and _long_noun_reading(t.surface)
                         and __import__('os').environ.get('CN_BROKEN_LONE_ATTR_ADV') != '0')
                # 漢字1字の代名詞（なんで｜俺｜こんな）は話し言葉で助詞を省いて置ける語で、浮いた1字ではない
                # （2026-11-20 補正担当の例文の正しい文）。CN_BROKEN_LONE_PRONOUN=0 で前のまま
                # 連体の形の動詞＋1字の名詞＋ない・ある（通す｜気｜ない・やる｜気｜ある）は が を省いた話し言葉の在る無し
                # （2026-11-20 補正担当の例文の正しい文）。CN_BROKEN_LONE_EXIST=0 で前のまま
                and not (p.pos == '動詞' and (p.infl_form or '') in ('基本形', '体言接続', '連体形')
                         and q.base_form in ('ない', 'ある') and q.pos in ('形容詞', '動詞')
                         and (t.pos_sub or '') == '一般'
                         and __import__('os').environ.get('CN_BROKEN_LONE_EXIST') != '0')
                # 後ろの語とつないで表の1語（先｜延ばし＝先延ばし）なら、解析の切り違いで浮いた1字ではない
                # （2026-11-20 補正担当の例文の正しい文）。CN_BROKEN_LONE_JOIN_NEXT=0 で前のまま
                and not (q.pos in ('動詞', '名詞') and _kanji(q.surface[:1]) and _whole_word(t.surface + q.surface)
                         and __import__('os').environ.get('CN_BROKEN_LONE_JOIN_NEXT') != '0')
                and not ((t.pos_sub or '').startswith('代名詞') and _mora(t.reading or '') >= 2
                         and __import__('os').environ.get('CN_BROKEN_LONE_PRONOUN') != '0')):
            out.append((t.start, t.end, '1字だけ浮いています'))
        # 片仮名1字が漢字の語にすぐ付いて複合語を作る所（オ段・ウ段・A案）は、メモの普通の書き方。打ち違いの跡と見ない
        # （2026-11-14 補正担当・全体評価の方針 v1 の3: 残すのは、ひらがなの並びに挟まる片仮名1字）。CN_KATA_ONE_COMPOUND=0 で前のまま
        # 形は「助詞＋片仮名1字＋漢字1字の語＋助詞か行末」だけ（音が｜オ｜段｜で）。片仮名1字が漢字の語の後ろ（準備ガ）・
        # 行の頭（リ勝）・2字以上の漢字の語の前（チ時間）は打ち違いの跡のことが多い（cases_full 692行で5行が紫を失った）
        _r = tokens[i + 2] if i + 2 < n else None
        _kata_compound = (len(t.surface) == 1 and _kata(t.surface) and __import__('os').environ.get('CN_KATA_ONE_COMPOUND') != '0'
                          and ((p is not None and p.pos in ('助詞', '記号'))
                               # 行の頭は、後ろが の・で・は・も・行末の時だけ（ア段の音・カ行は）。行の頭の 片仮名1字＋漢字1字＋を
                               # （リ勝を送る）は打ち違いの跡だった
                               or (p is None and (_r is None or _r.surface in ('の', 'で', 'は', 'も', '、', '。'))))
                          and q is not None and q.start == t.end and len(q.surface) == 1 and _kanji(q.surface)
                          and _suffix_kanji(q.surface)
                          and (_r is None or _r.pos in ('助詞', '記号')))
        # 接頭の漢字（全・新・各）のすぐ後ろの片仮名2字の名詞（全｜タブ）は、接頭＋外来語の普通の書き方
        # （2026-11-14 補正担当、未解決タブ40行目の型）。CN_KATA_AFTER_PREFIX=0 で前のまま
        _prefix_kata = (p is not None and p.pos == '接頭詞' and t.pos == '名詞' and len(t.surface) == 2
                        and getattr(t, 'has_reading', True) and __import__('os').environ.get('CN_KATA_AFTER_PREFIX') != '0')
        # 漢字の名詞に挟まれた身近な片仮名2字の名詞（隣接｜キー｜補正）は、外来語を挟んだ複合語の普通の書き方
        # （2026-11-14 未解決タブの正しい文）。CN_KATA_IN_COMPOUND=0 で前のまま
        _known_kata = (len(t.surface) == 2 and t.pos == '名詞' and getattr(t, 'has_reading', True)
                       and p is not None and q is not None and p.pos == '名詞' and q.pos == '名詞'
                       and (p.pos_sub or '').startswith('サ変')     # 隣接｜キー（する名詞＋外来語）。先輩｜イン は見ない
                       and _kanji(p.surface[-1:]) and _kanji(q.surface[:1]) and _kata_common(t.surface)
                       and __import__('os').environ.get('CN_KATA_IN_COMPOUND') != '0')
        # 表の身近な片仮名の名詞（ゼロ・メモ）が、名詞で言い切る形（効果｜ゼロ｜でした）か、表の漢字2字以上の名詞と
        # 名詞に挟まれた複合語（実機｜メモ｜全タブ）なら混じった片仮名と見ない（2026-11-20 補正担当、うに 誤判定タブの
        # 正しい文。判断 POLICY.md C1）。CN_KATA_KNOWN_NOUN=0 で前のまま
        if (not _known_kata and len(t.surface) == 2 and t.pos == '名詞' and getattr(t, 'has_reading', True)
                and __import__('os').environ.get('CN_KATA_KNOWN_NOUN') != '0' and _kata(t.surface)
                and _kata_common(t.surface) and _unit_word(t.surface)
                and (q is None or q.pos in ('助詞', '助動詞', '記号')
                     # (ii) は名詞だけを並べた見出し・メモの行のときだけ（先輩｜イン｜相談の… のような文の中は今のまま紫）
                     or (p is not None and q.pos == '名詞' and p.pos == '名詞' and len(p.surface) >= 2
                         and _kanji(p.surface) and _unit_word(p.surface)
                         and all(x.pos in ('名詞', '接頭詞', '記号') for x in tokens)))):
            _known_kata = True
        # 数の後ろの片仮名の助数詞（１万｜ドル）は数え方の語（2026-11-20 正しい文の見直し）。CN_KATA_COUNTER=0 で前のまま
        if (_kata(t.surface) and (t.pos_sub or '') == '接尾:助数詞' and p is not None
                and (p.pos_sub or '').startswith('数') and __import__('os').environ.get('CN_KATA_COUNTER') != '0'):
            _known_kata = True
        # 前か後ろの漢字の語とつないで表の1語（腹｜ペコ＝腹ペコ）なら、語の中の片仮名（2026-11-20 補正担当の例文の
        # 正しい文）。CN_KATA_WHOLE_WORD=0 で前のまま
        if (_kata(t.surface) and len(t.surface) <= 2 and __import__('os').environ.get('CN_KATA_WHOLE_WORD') != '0'
                and ((p is not None and p.end == t.start and _kanji(p.surface[-1:]) and _whole_word(p.surface + t.surface))
                     or (q is not None and q.start == t.end and _kanji(q.surface[:1]) and _whole_word(t.surface + q.surface)))):
            _known_kata = True
        if _kata(t.surface) and len(t.surface) <= 2 and not _kata_compound and not _prefix_kata and not _known_kata:
            if p and q and _kanji(p.surface[-1:]) and _kanji(q.surface[:1]):
                out.append((t.start, t.end, '片仮名が混じっています'))
            elif (q and _kanji(q.surface[:1]) and not (q.pos_sub or '').startswith('接尾') and (not p or p.pos == '助詞')
                  and (len(t.surface) == 1 or t.surface[0] in 'ンーァィゥェォャュョッ')):
                out.append((t.start, q.end, '片仮名が混じっています'))
            elif p and _kanji(p.surface[-1:]) and q and q.pos != '助詞' and q.pos != '記号':
                out.append((t.start, t.end, '片仮名が混じっています'))
        if (len(t.surface) == 1 and _kata(t.surface) and t.surface not in 'ーヶヵ' and not _kata_compound
                and not (p and _kata(p.surface[-1:])) and not (q and _kata(q.surface[:1])) and (p or q)
                and not (p and p.pos == '記号' and (q is None or q.pos == '記号'))
                and not _mixed_katakana_word(text, t.start, t.end)
                # 上で語の中の片仮名と分かった字（表の1語 皮フ）は1字でも混じりと見ない（2026-11-22 補正担当、
                # 誤判定タブの正しい文）。CN_KATA_ONE_KNOWN=0 で前のまま
                and not (_known_kata and __import__('os').environ.get('CN_KATA_ONE_KNOWN') != '0')):
            out.append((t.start, t.end, '片仮名1字が混じっています'))
        if (t.pos == '動詞' and t.surface == 'し' and t.base_form == 'する' and q and q.pos == '動詞'
                and (q.pos_sub or '') == '自立' and _kanji(q.surface[:1]) and q.base_form not in _AFTER_SHI
                # し の前が漢字2字以上のサ変の名詞（検討し組み込む・確認し報告する）は読点を省いた連用中止
                # （2026-11-20 補正担当、判断 POLICY.md C2）。CN_BROKEN_SHI_RENYO=0 で前のまま
                and not (p is not None and p.pos == '名詞' and (p.pos_sub or '').startswith('サ変')
                         and len(p.surface) >= 2 and _kanji(p.surface) and p.end == t.start
                         and __import__('os').environ.get('CN_BROKEN_SHI_RENYO') != '0')):
            out.append((t.start, q.end, '動詞のつながりが変です'))
        if (t.pos == '助詞' and q and q.pos == '助詞' and (t.surface, q.surface) in _BAD_PAIRS
                # 疑問の語＋も＋が・を（誰もが・何もかもが の 誰も）は「みな」の意味の正しい形（2026-11-20 補正担当・例文の
                # 正しい文）。CN_BROKEN_INDEF_MO=0 で前のまま
                and not (t.surface == 'も' and p is not None and p.end == t.start and p.pos == '名詞'
                         and (p.pos_sub or '').startswith('代名詞') and p.surface in _INDEF
                         and __import__('os').environ.get('CN_BROKEN_INDEF_MO') != '0')):
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
                and (i + 2 >= n or tokens[i + 2].pos == '記号')
                # 行末の片仮名が世の中の外来語（選択して｜コピー）なら、名詞で言い終える箇条書きの普通の書き方
                # （2026-11-16 うに）。CN_BROKEN_TE_KATA_END=0 で前のまま
                and not (len(q.surface) >= 2 and __import__('os').environ.get('CN_BROKEN_TE_KATA_END') != '0'
                         and _kata_word_known(q.surface))):
            out.append((t.start, q.end, '言い終わりに片仮名が混じっています'))
        if (t.pos == '名詞' and _kanji(t.surface) and sub in ('サ変接続', '一般') and q and q.pos == '動詞'
                and q.base_form == 'なる' and _hira_head(q.surface)):
            out.append((t.start, q.end, '名詞と動詞のつながりが変です'))
        if (t.pos == 'フィラー' and p and q and p.pos != '記号' and q.pos != '記号'
                # 連体詞でもある語（あの・その）が名詞の前に在るなら、名詞に掛かる連体詞（あの｜ペン）。
                # （2026-11-20 正しい文の見直し）。CN_BROKEN_FILLER_ADNOMINAL=0 で前のまま
                and not (q.pos == '名詞' and __import__('os').environ.get('CN_BROKEN_FILLER_ADNOMINAL') != '0'
                         and _adnominal_word(t.surface))
                # 副助詞でもある語（なんか）が助詞の後ろに在るなら、取り立ての副助詞（私に｜なんか｜目もくれない）。
                # （2026-11-20 正しい文の見直し）。CN_BROKEN_FILLER_PARTICLE=0 で前のまま
                and not (p.pos == '助詞' and __import__('os').environ.get('CN_BROKEN_FILLER_PARTICLE') != '0'
                         and _particle_word(t.surface))):
            out.append((t.start, q.end, '文の途中に1字が混じっています'))
        if (t.pos == '助詞' and sub == '終助詞' and p and q
                and ((p.pos in ('動詞', '形容詞') and '連用' in (p.infl_form or '')) or _kata(p.surface))
                and q.pos in ('動詞', '形容詞', '名詞', '接頭詞') and not _hira_head(q.surface)):
            out.append((t.start, q.end, '文の途中に1字が混じっています'))
        if (t.pos == '接頭詞' and not _hira_head(t.surface) and q and q.pos not in ('名詞', '接頭詞', '記号')
                and _hira_head(q.surface)
                # 辞書がその品詞に付く接頭詞の行を持つ字（超・真＋形容詞: 超かわいい）は語の作りどおり（2026-11-20 正しい文の
                # 見直し）。CN_BROKEN_PREFIX_ROW=0 で前のまま
                and not (__import__('os').environ.get('CN_BROKEN_PREFIX_ROW') != '0' and _prefix_row(t.surface, q.pos))):
            out.append((t.start, q.end, '前に付く字の後ろが続きません'))
    for k, ch in enumerate(text):
        # 付く先の かな の無い濁点・半濁点（行の頭・漢字や記号の後ろ）
        if ch in '゛゜ﾞﾟ' and not (k and text[k - 1] in '「『（(\'"“‘【［[') and (k == 0 or not ('\u3041' <= text[k - 1] <= '\u30fa' or '\uff66' <= text[k - 1] <= '\uff9d')):
            out.append((k, k + 1, '付く字の無い濁点が混じっています'))
    for mt in _STRAY_SYMBOL.finditer(text):
        if not _symbol_splits_word(text, mt.start(), mt.end()):
            continue
        # 同じ記号の並びが同じ行の前にも在り、間に字を挟むなら囲みの記号（**…**・~~…~~）。2026-11-20 補正担当、
        # 判断 POLICY.md C3。CN_STRAY_SYMBOL_PAIRED=0 で前のまま
        if __import__('os').environ.get('CN_STRAY_SYMBOL_PAIRED') != '0':
            k0 = text.rfind(mt.group(), 0, mt.start())
            if k0 >= 0 and k0 + len(mt.group()) < mt.start():
                continue
        out.append((mt.start(), mt.end(), '文の途中に記号が混じっています'))
    # 助詞・記号のすぐ後ろの漢字で始まる名詞が、助詞を挟まず自立の動詞に続き（課題に｜手取り｜掛かる）、名詞の読みの頭の
    # 1打（て）が前後のキーの隣で、それを抜けば説明の付く所は、隣のキーを一緒に押した1字の足しの見込み（正しい文765行で
    # 0件・2026-11-17 うにの未解決タブ）。CN_BROKEN_HEAD_DROP_VERB=0 で前のまま
    if __import__('os').environ.get('CN_BROKEN_HEAD_DROP_VERB') != '0':
        out += [x for x in _head_drop_spots(tokens) if not any(x[0] < y[1] and y[0] < x[1] for y in out)]
    seen, uniq = set(), []
    for a, b, why in out:
        if (a, b) not in seen and a < b:
            seen.add((a, b))
            uniq.append((a, b, why))
    return uniq


HEAD_DROP_COMMON = 400


def _head_drop_spots(tokens):
    try:
        import kana_layout
    except Exception:
        return []
    out = []
    for i in range(1, len(tokens) - 1):
        p, x, q = tokens[i - 1], tokens[i], tokens[i + 1]
        # 時の名詞（今日・明日: 副詞可能）は助詞を挟まず動詞に続くのがふつう（今日来ない・2026-11-20 補正担当・例文の
        # 正しい文）。CN_HEAD_DROP_TIME=0 で前のまま
        if ((x.pos_sub or '').startswith('副詞可能') and __import__('os').environ.get('CN_HEAD_DROP_TIME') != '0'):
            continue
        # とても身近な名詞（名前・写真: 順位 HEAD_DROP_COMMON 以下）は、を を省いて動詞に続く話し言葉（名前書いて）。
        # 頭の1打の足しとは見ない（2026-11-20 補正担当・例文の正しい文）。CN_HEAD_DROP_COMMON=0 で前のまま
        if __import__('os').environ.get('CN_HEAD_DROP_COMMON') != '0':
            try:
                import ime_reconvert as _R
                if _R._rank(x.surface) <= HEAD_DROP_COMMON:
                    continue
            except Exception:
                pass
        if not (p.pos in ('助詞', '記号') and x.pos == '名詞' and _kanji(x.surface[:1]) and x.end == q.start
                and q.pos == '動詞' and (q.pos_sub or '') == '自立'
                and (q.base_form or '') not in ('する', 'できる', '出来る', 'なる')):
            continue
        if ((x.pos_sub or '') == 'サ変接続' and __import__('os').environ.get('CN_HEAD_DROP_SAHEN_HONOR') != '0'
                and ((q.base_form or '') in (_SAHEN_OK | _SAHEN_HONOR)
                     or __import__('os').environ.get('CN_HEAD_DROP_SAHEN_ANY') != '0')):
            # 動作の名詞（入力・追加）の後ろに を を省いて動詞が続くのは、メモの書き方でふつう（【入力見ています】）。
            # 頭の1打が混じった形とは見ない（2026-11-17 補正担当、うに: 以前直った行に batch602 で紫）。
            # CN_HEAD_DROP_SAHEN_ANY=0 で敬語・する の仲間だけ
            # 動作の名詞に直に付く敬語・する の仲間（追加いただけ・ご確認ください）は、そのままで続く形（2026-11-17 補正担当、
            # うに 11-16 の 追加いただけ の紫が batch602 で戻った）。CN_HEAD_DROP_SAHEN_HONOR=0 で前のまま
            continue
        # 1字の漢字の名詞（鍵・窓）は、頭の1打を抜くと書かれた字が残らず、抜いた形の説明（手取り｜掛かる → 取り掛かる）
        # が付かない。を を省いて動詞に続く話し言葉（鍵しめた？）と見る（2026-11-20 補正担当・例文の正しい文）。
        # CN_HEAD_DROP_ONE_KANJI=0 で前のまま
        if len(x.surface) == 1 and __import__('os').environ.get('CN_HEAD_DROP_ONE_KANJI') != '0':
            continue
        r = _reading_of(x)
        if len(r) < 2 or not all('ぁ' <= c <= 'ゖ' for c in r):
            continue
        pr, qr = _reading_of(p)[-1:], _reading_of(q)[:1]
        try:
            if kana_layout.single_key_drop_adjacency(pr + r + qr, pr + r[1:] + qr):
                out.append((x.start, q.end, '語の前に1字が混じっています'))
        except Exception:
            continue
    return out


def _head_drop(done, tokens, s, e):
    """_head_drop_spots の所で、名詞の読みの頭の1打を抜いた読みの表記（同梱の読みの表・かなのまま）に替えた行のうち、
    元より READING_DROP_GAIN 以上軽く、二番より MARGIN 以上軽いものの (名詞の始め, 終わり, 表記)。無ければ None"""
    try:
        import morphology
        import last_keystroke as L
        import odd_respell as O
    except Exception:
        return None
    x = [t for t in tokens if t.start == s]
    if not x or x[0].pos != '名詞':
        return None
    x = x[0]
    r2 = _reading_of(x)[1:]
    base = morphology.path_cost(done)
    if base is None or not r2:
        return None
    ranked = []
    for f in dict.fromkeys([f for f, _c in L._seed_surfaces(r2)][:8] + [r2]):
        cost = morphology.path_cost(done[:x.start] + f + done[x.end:])
        if cost is not None:
            ranked.append((cost, f))
    ranked.sort()
    if not ranked or base - ranked[0][0] < READING_DROP_GAIN:
        return None
    if len(ranked) > 1 and ranked[1][0] - ranked[0][0] < O.MARGIN:
        return None
    return x.start, x.end, ranked[0][1]


READING_DROP_GAIN = 2000


def _reading_drop(done, tokens, s, e):
    """「語の後ろに1字が混じっています」の所（変化｜字）で、漢字1字を抜いても直らない時に、所の読み（へんかじ）から
    隣のキーを一緒に押した1打のかな（ん の隣の か）を抜いた読み（へんじ）の表記（返事）に替える形。1打で説明できる
    抜き方だけ（じ＝し＋゛ のような2打は抜かない: 2026-11-17 うに「し も ゛ も隣接キーではありません」）。
    行の費用が元より READING_DROP_GAIN 以上軽く、二番の形より MARGIN 以上軽いものが1つだけなら (表記)、ほかは None（紫のまま）。"""
    try:
        import kana_layout
        import morphology
        import last_keystroke as L
        import odd_respell as O
    except Exception:
        return None
    inside = [t for t in tokens if s <= t.start and t.end <= e]
    if not inside or inside[0].start != s or inside[-1].end != e:
        return None
    rd = ''.join(_reading_of(t) for t in inside)
    nxt = [t for t in tokens if t.start == e]
    q = _reading_of(nxt[0]) if nxt else ''
    if not rd or not all('ぁ' <= c <= 'ゖ' or c == 'ー' for c in rd + q):
        return None
    base = morphology.path_cost(done)
    if base is None:
        return None
    seen = {}
    for i in range(len(rd)):
        r2 = rd[:i] + rd[i + 1:]
        if len(r2) < 2 or r2 in seen:
            continue
        try:
            if not kana_layout.single_key_drop_adjacency(rd + q, r2 + q):
                continue
        except Exception:
            continue
        # 同じ読みの表記どうし（返事・返辞）は張り合わせない。読みごとに、いちばん使われる表記（ime_reconvert の順位）で
        # 抜き方どうしを比べる
        faces = [f for f, _c in list(L._seed_surfaces(r2))[:6] if any('一' <= ch <= '鿿' for ch in f)]
        if not faces:
            continue
        try:
            import ime_reconvert as R
            face = min(faces, key=R._rank)
        except Exception:
            face = faces[0]
        cost = morphology.path_cost(done[:s] + face + done[e:])
        if cost is not None:
            seen[r2] = (cost, face)
    ranked = sorted(seen.values())
    if not ranked:
        return None
    # 所の崩れは spans が見つけた決め手なので、1打で説明できる形だけを比べ、費用の下がりは READING_DROP_GAIN で足りる
    if base - ranked[0][0] < READING_DROP_GAIN:
        return None
    if len(ranked) > 1 and ranked[1][0] - ranked[0][0] < O.MARGIN:
        return None
    return ranked[0][1]


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
    # 言い終わりの片仮名（してねた → して｜ネタ）が、元の行のかなを片仮名にしただけで、元のかな（てねた）が用言の形として
    # 説明できるなら、紫にせずかなに戻す（入口の変換が かなの動詞 を片仮名の名詞にした）。CN_BROKEN_KATA_BACK=0
    import os
    if os.environ.get('CN_BROKEN_KATA_BACK') != '0':
        try:
            import pos_grammar
            for s0, e0, why in found:
                if why != '言い終わりに片仮名が混じっています' or e0 - s0 < 3:
                    continue
                k0 = s0 + 1
                kata = done[k0:e0]
                hira = ''.join(chr(ord(c) - 0x60) if 'ァ' <= c <= 'ヶ' else c for c in kata)
                if hira == kata or not all('ぁ' <= c <= 'ゖ' or c == 'ー' for c in hira):
                    continue
                hit = False
                for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, done, line, autojunk=False).get_opcodes():
                    if tag == 'replace' and i1 <= k0 and e0 <= i2 and line[j1:j2] == done[i1:k0] + hira + done[e0:i2]:
                        hit = True
                lb = s0
                while lb > 0 and 'ぁ' <= done[lb - 1] <= 'ゖ':
                    lb -= 1
                if not hit or not pos_grammar.explain_kana_run(done[lb:k0] + hira, after_kanji=lb > 0):
                    continue
                new = done[:k0] + hira + done[e0:]
                ops2 = [o for o in difflib.SequenceMatcher(None, line, new, autojunk=False).get_opcodes() if o[0] != 'equal']
                res2 = dict(result)
                res2.update({'corrected': new, 'changed': new != line,
                             'details': [d for d in (result.get('details') or ()) if not (len(d) > 1 and kata in str(d[1]))],
                             'spans': [[o[3], o[4]] for o in ops2], 'original_spans': [[o[1], o[2]] for o in ops2]})
                return repair_line(line, res2, decided, input_method)
        except Exception:
            pass
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

    add, cut, swap = [], [], []
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
        if why == _EXTRA[1] and input_method == 'kana' and os.environ.get('CN_BROKEN_HEAD_DROP_VERB') != '0':
            got = _head_drop(done, tokens, s, e)
            if got is not None:
                swap.append(got)
                continue
        if why == _EXTRA[0] and input_method == 'kana' and os.environ.get('CN_BROKEN_READING_DROP') != '0':
            got = _reading_drop(done, tokens, s, e)
            if got is not None:
                swap.append((s, e, got))
                continue
        add.append((org[0], org[1], why))
    cut = sorted(set(cut))
    # 除いた字に掛かる別の決め手の紫は付けない
    add = [x for x in add if not any(to_org(*d) and x[0] < to_org(*d)[1] and to_org(*d)[0] < x[1] for d in cut)]
    swap = [x for x in swap if not any(x[0] < d[1] and d[0] < x[1] for d in cut)]
    if not add and not cut and not swap:
        return result
    out = dict(result)
    if cut or swap:
        new = done
        details = list(result.get('details') or ())
        edits = [(ks, ke, '') for ks, ke in cut] + list(swap)
        for ks, ke, face in sorted(edits, reverse=True):
            details.append([done[ks:ke] if face else done[max(0, ks - 2):min(len(done), ke + 2)],
                            face if face else done[max(0, ks - 2):ks] + done[ke:min(len(done), ke + 2)], '1字の足し'])
            new = new[:ks] + face + new[ke:]
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


def _unit_word(face):
    try:
        import seed_japanese
        return seed_japanese.is_unit(face) is True
    except Exception:
        return False


def _kata_common(face):
    """片仮名の語が身近か（語の使われやすさの順位が 530 以下）。"""
    try:
        import ime_reconvert
        return ime_reconvert._rank(face) <= 530
    except Exception:
        return False
