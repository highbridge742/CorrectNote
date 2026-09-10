# -*- coding: utf-8 -*-
"""読みが壊れていても辞書で裏付けられる区切りを返す。本文は補正しない。"""
def known_reading_prefix(text,dict_index,allow_short=False):
    if not text or not all('ぁ'<=c<='ゖ' or c=='ー' for c in text):
        return None
    from morphology import dictionary_base_pos
    # 完成した読みを細切れにしない。未知の残りを最低2字確保する。
    if dict_index.is_world_reading(text):
        return None
    for cut in range(len(text)-2,2,-1):
        if text[cut] in 'ぁぃぅぇぉゃゅょっー':
            continue
        head=text[:cut]
        surfaces=dict_index.surfaces_for_reading(head,limit=16,band=True)
        evidence=[]
        for surface in surfaces:
            positions=dictionary_base_pos(surface)
            if not positions:
                continue
            # 固有名詞・機能語・未知語を境界の確定根拠にしない。
            nouns=[p for p in positions if p.startswith('名詞,') and '固有名詞' not in p
                   and '接尾' not in p and '非自立' not in p]
            if nouns and len(nouns)==len(positions):
                evidence.append(surface)
        if evidence:
            return (head,text[cut:],'名詞',tuple(dict.fromkeys(evidence)))
    if allow_short and len(text)>=6 and text[2] not in 'ぁぃぅぇぉゃゅょっー':
        head=text[:2]
        positions=dictionary_base_pos(head) or ()
        if any(p.startswith('名詞,一般,') or p.startswith('名詞,サ変接続,') for p in positions):
            return (head,text[2:],'名詞',(head,))
    return None


def odd_partial_loanwords(line,dict_index,store,tokenize_fn):
    """既知名詞＋未知の長音終わりの読みを、既存の接続判定で検証。"""
    if dict_index is None or store is None or tokenize_fn is None:
        return []
    import re
    import corrector as C
    import loanword as L
    import oddness as O
    out=[]
    for match in re.finditer(r'[ぁ-ゖー]+',line):
        run=match.group()
        end=match.end()
        if not run.endswith('ー') and 'ー' in run:
            import pos_grammar as PG
            cut=run.rfind('ー')+1
            suffix=run[cut:]
            if PG.explain_kana_run(suffix,no_words=True):
                run=run[:cut];end=match.start()+cut
        if (match.start()>0 and end<len(line) and
                line[match.start()-1] in C._QUOTE_OPEN and line[end] in C._QUOTE_CLOSE):
            continue
        if not (7<=len(run)<=24 and run.endswith('ー')):
            continue
        if C._chunk_is_intact(run,tokenize_fn):
            continue
        evidence=known_reading_prefix(run,dict_index)
        if not evidence:
            continue
        head,tail,major,surfaces=evidence
        # 普通の伸ばし声を外来語と決めつけない。今回は2拍以上の
        # 小書き仮名＋長音を持つ未知語の接続だけを検証する。
        if len(tail)<4 or tail[-2] not in 'ゃゅょ':
            continue
        if L.katakana_for_hiragana(tail,store,min_length=3):
            continue
        # 既知の前半は読みを変更せず、候補探索前に接続を検査する。
        projected=surfaces[0]+L.hiragana_to_katakana(tail)
        if not O.is_odd_run(projected,tokenize_fn,store=store,dict_index=dict_index):
            continue
        out.append((match.start(),end,head,tail,surfaces[0]))
    return out


from functools import lru_cache


def _continuative_head(token):
    return (token.has_reading and token.pos == '動詞' and token.pos_sub == '自立'
            and token.infl_form == '連用形' and 2 <= len(token.surface) <= 8
            and token.reading == token.surface)


@lru_cache(maxsize=2048)
def continuative_reading_prefix(text):
    """辞書が原文のまま読める連用形。後半の修正候補から前半を逆算しない。"""
    if not text or not all('ぁ' <= c <= 'ゖ' for c in text):
        return None
    from morphology import _tokenize_janome
    raw = _tokenize_janome(text)
    if not raw or raw[0].start != 0 or not _continuative_head(raw[0]):
        return None
    size = len(raw[0].surface)
    # 連用形の名詞用法＋の＋既知名詞は、解析が「のく」等へ
    # 結合していても複合語の誤打としない。原文の読みだけで検証。
    tail = text[size:]
    if tail.startswith('の') and len(tail) > 1:
        from corrector import table_surfaces_for_reading
        from morphology import dictionary_base_pos
        if any(any(p.startswith('名詞,') for p in (dictionary_base_pos(face) or ()))
               for face in table_surfaces_for_reading(tail[1:], limit=6)):
            return None
    # 助詞で接続して読める後半を、複合語の誤打へ組み替えない。
    # に＋ゅ…のような未知境界は、この条件には当たらない。
    if (len(raw) > 1 and raw[1].pos in ('助詞', '助動詞')
            and all(t.has_reading for t in raw[1:])):
        return None
    if len(text) - size < 4 or text[size] in 'ぁぃぅぇぉゃゅょっー':
        return None
    return text[:size]


@lru_cache(maxsize=2048)
def short_nominal_reading(text):
    """普通名詞／連用形に続く名詞の読み。未知の拗音境界を戻すだけ。"""
    if not (6 <= len(text) <= 20 and all('ぁ' <= c <= 'ゖ' or c == 'ー' for c in text)):
        return None
    from morphology import dictionary_base_pos, _tokenize_janome
    from corrector import table_surfaces_for_reading
    from pos_grammar import explain_kana_run
    # 前半は同音語ではなく原文の表記自体が名詞であることを確かめる。
    head = text[:2]
    # 読めている語を別の名詞2語へ組み替えない。未知語の先頭が
    # 拗音の途中で切れているときだけ、辞書の読みへ境界を戻す。
    raw = _tokenize_janome(text)
    if (not raw or not raw[0].has_reading
            or not any(not t.has_reading and t.surface[:1] in ('ゃ','ゅ','ょ')
                       for t in raw)):
        return None
    # 48-XN: 辞書が認める自立動詞の連用形も名詞を修飾できる。
    # 連体形・未然形や、語尾だけから推測した活用形には広げない。
    verbal = _continuative_head(raw[0])
    if verbal:
        head = raw[0].surface
    elif raw[0].surface != head or raw[0].pos != '名詞':
        return None
    def noun(surface):
        return any(p.startswith('名詞,一般,') or p.startswith('名詞,サ変接続,')
                   for p in (dictionary_base_pos(surface) or ()))
    size = len(head)
    if len(text) - size < 4 or (not verbal and not noun(head)) or text[size] in 'ぁぃぅぇぉゃゅょっー':
        return None
    for end in range(len(text), size + 3, -1):
        tail, suffix = text[size:end], text[end:]
        if suffix and not explain_kana_run(suffix, no_words=True, initial_state='Bw'):
            continue
        if suffix and suffix[0] in 'ぁぃぅぇぉゃゅょっー':
            continue
        for face in table_surfaces_for_reading(tail, limit=6):
            if noun(face):
                return (head, tail, suffix, face)
    return None
