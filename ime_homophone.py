# -*- coding: utf-8 -*-
"""Read-only homophone evidence for a repaired IME first conversion.

The first conversion explains a possible typo.  A TSF search result may
offer a different spelling for its predicate; neither list is a verdict.
Only unchanged source arguments with positive semantic evidence can open
that alternative, and the caller still runs the common final validator.

2026-11-07（うに「候補は IME でなく辞書から」）: 述語の読みは辞書の読み（打った読みの後ろと合うもの）で、
同じ読みの述語の表記は辞書の活用形の索引（dict_index.inflected_surfaces_for_reading、無ければ読みの格子の表の
動詞）から出す。IME は、辞書で読みが合わないときの逆変換と、辞書に無い語を候補一覧から足すときだけ使う。
IME の無い環境（雲）でも同じ候補になる。CN_HOMOPHONE_DICT=0 で前のまま（IME の逆変換と候補一覧）。
"""
import os


def _hira(s):
    return ''.join(chr(ord(c) - 0x60) if 'ァ' <= c <= 'ヶ' else c for c in s)


def _token_reading(t):
    if getattr(t, 'has_reading', True) and t.reading:
        return _hira(t.reading)
    if all('ぁ' <= c <= 'ゖ' or c == 'ー' for c in t.surface):
        return t.surface
    return None


def _dict_suffix_reading(first, reading, verb, tokens):
    """first の動詞から後ろの辞書の読み（打った読み reading の後ろと合うものだけ）。動詞の読みが辞書に何通りか
    あれば（行っ いっ/おこなっ）合うものを選ぶ。(後ろ全体の読み, 動詞の読み) か None。"""
    rest = [t for t in tokens if t.start >= verb.end]
    rest_reading = ''
    for t in rest:
        r = _token_reading(t)
        if r is None:
            return None
        rest_reading += r
    options = []
    r0 = _token_reading(verb)
    if r0:
        options.append(r0)
    try:
        from inflected_lexicon import dictionary_readings
        options += [_hira(r) for r in dictionary_readings(verb.surface)]
    except Exception:
        pass
    for rv in dict.fromkeys(options):
        whole = rv + rest_reading
        if whole and len(whole) < len(reading) + 1 and reading.endswith(whole):
            return whole, rv
    return None


def _inflected_faces(verb_reading, dict_index=None):
    """読み verb_reading の動詞の活用形の表記（辞書の活用形の索引、無ければ読みの格子の表の動詞）。"""
    if dict_index is not None:
        try:
            got = tuple(dict_index.inflected_surfaces_for_reading(verb_reading))
            if got:
                return got
        except Exception:
            pass
    try:
        import reading_lattice
        reading_lattice.load()
        rows = reading_lattice._table.get(verb_reading, ())
    except Exception:
        return ()
    best = {}
    for surf, _l, _r, cost, pos in rows:
        if pos == '動詞' and (surf not in best or cost < best[surf]):
            best[surf] = cost
    return tuple(sorted(best, key=lambda f: (best[f], f)))


def _in_dictionary(face):
    try:
        from inflected_lexicon import dictionary_readings
        return bool(dictionary_readings(face))
    except Exception:
        return True


def _suffix_reading_ok(suffix, suffix_reading, verb_reading=None):
    """表記 suffix の辞書の読みが suffix_reading になるか（IME の phonetic の代わり）。"""
    from morphology import tokenize as native_tokenize
    toks = list(native_tokenize(suffix))
    if not toks:
        return False
    head = toks[0]
    tail = ''
    for t in toks[1:]:
        r = _token_reading(t)
        if r is None:
            return False
        tail += r
    heads = [r for r in [_token_reading(head)] if r]
    try:
        from inflected_lexicon import dictionary_readings
        heads += [_hira(r) for r in dictionary_readings(head.surface)]
    except Exception:
        pass
    if verb_reading and head.surface in _inflected_faces(verb_reading):
        heads.append(verb_reading)
    return any(h + tail == suffix_reading for h in heads)


def _inverted_argument(source, verb_end):
    """動詞の後ろ（終助詞・助動詞のあと）の読点の先が、動詞を含まない 名詞＋を・に・が で行（文）の終わりになる所の句。"""
    import os
    if os.environ.get('CN_HOMOPHONE_INVERTED') == '0':
        return ''
    from morphology import tokenize as native_tokenize
    rest=source[verb_end:]
    cut=rest.find('、')
    if cut<0:
        return ''
    if any(t.pos in ('動詞','名詞') and not (t.pos_sub or '').startswith('非自立')
           for t in native_tokenize(source) if verb_end<=t.start and t.end<=verb_end+cut):
        return ''
    tail=rest[cut+1:].rstrip('。．！？!?」』）) 　')
    if not tail or tail[-1] not in 'をにが':
        return ''
    toks=list(native_tokenize(tail))
    if (len(toks)<2 or toks[-1].pos!='助詞' or not toks[-2].pos.startswith('名詞')
            or any(t.pos=='動詞' or t.surface=='、' for t in toks)):
        return ''
    return tail


def positive_predicate_alternatives(source, first, reading, tokenize, ime, *, supplied=(), subject_completion=False,
                                    dict_index=None):
    """Return (whole surface, original object, positive role proof) tuples.
    ime は None でもよい（辞書だけで候補を出す）。dict_index は活用形の索引（無ければ読みの格子の表）。"""
    from morphology import native_spelling_only, tokenize as native_tokenize
    from semantic_roles import (object_before, case_argument_before, candidate_evidence,
        subject_before, subject_candidate_evidence)

    use_dict=os.environ.get('CN_HOMOPHONE_DICT')!='0'
    first_tokens=list(native_tokenize(first))
    verbs=[token for token in first_tokens
           if token.pos=='動詞' and token.pos_sub=='自立' and token.start>0]
    if not verbs:
        return ()
    verb=verbs[-1]
    # The argument must be present in the original, not introduced by the
    # hypothetical conversion.  A changed prefix cannot lend its semantics.
    if source[:verb.start]!=first[:verb.start]:
        return ()
    suffix_reading=verb_reading=None
    if use_dict:
        # 述語の読みは辞書から（打った読みの後ろと合うときだけ）。合わなければ IME の逆変換（前と同じ）
        got=_dict_suffix_reading(first,_hira(reading),verb,first_tokens)
        if got:
            suffix_reading,verb_reading=got
    if suffix_reading is None:
        if ime is None:
            return ()
        reverse=ime.reverse_words(first)
        if not reverse or reverse[0]!=reading:
            return ()
        word=next((item for item in reverse[1] if item[0]==verb.start),None)
        if word is None:
            return ()
        suffix_reading=reading[word[2]:]
    if not suffix_reading:
        return ()
    object_word=object_before(source,verb.start,tokenize)
    case_argument=case_argument_before(source,verb.start,tokenize)
    if not object_word and not case_argument:
        # 倒置（焼いたよ、パンを。）: 動詞の後ろの読点の先が 名詞＋を・に・が で終わるなら、その句を動詞の前に置いた形で
        # 同じ項の読み方を使う（うに 2026-11-07「倒置で名詞が後ろに行った文は見逃す？」）。CN_HOMOPHONE_INVERTED=0 で前のまま
        inverted=_inverted_argument(source,verb.end)
        if inverted:
            moved=source[:verb.start]+inverted
            object_word=object_before(moved,len(moved),tokenize)
            case_argument=case_argument_before(moved,len(moved),tokenize)
    subject_word=(subject_before(source,verb.start,tokenize,allow_direct_topic=True)
                  if subject_completion else '')
    source_subject=(subject_candidate_evidence(subject_word,suffix_reading,'')
                    if subject_word else None)
    if not (source_subject and source_subject['shared_roles']):subject_word=''
    if not object_word and not case_argument and not subject_word:
        return ()

    def original_role_proof(suffix):
        proofs=[]
        before=source[:verb.start]
        if subject_word:
            subject_fit=subject_candidate_evidence(subject_word,suffix,'')
            if not (subject_fit and subject_fit['shared_roles']):return ()
            proofs.append(subject_fit)
        if object_word:
            proofs.append(candidate_evidence(object_word,suffix,'',before=before))
        if case_argument:
            proofs.append(candidate_evidence(case_argument[0],suffix,'',
                                             before=before,case=case_argument[1]))
        return tuple(proof for proof in proofs if proof and proof['shared_roles'])

    # A known fit for the first conversion is not an invitation to rewrite
    # its spelling from the search interface's independently ranked results.
    if original_role_proof(first[verb.start:]):
        return ()
    hits=()
    if ime is not None or not use_dict:
        try:
            from ime_candidates import SearchCandidates
            with SearchCandidates() as search:
                if search.available:
                    hits=search.candidates(suffix_reading) or ()
        except (ImportError,OSError,AttributeError):
            pass
    from_ime=set()
    if use_dict:
        # 辞書の活用形の索引から: 同じ読みの動詞の表記＋元の後ろ（助動詞など）。IME の候補一覧は、頭の語が辞書に
        # 無い語のときだけ足す（辞書に在る語は辞書の側で出るので、雲と PC で候補が同じになる）
        rest=first[verb.end:]
        # かなだけの表記（やい）は候補にしない: 打ったかなそのものに戻すだけで、同じ読みの表記の選び直しではない
        suffixes=[face+rest for face in _inflected_faces(verb_reading,dict_index)
                  if any('一'<=c<='鿿' for c in face)]
        for hit in dict.fromkeys(hits):
            toks=list(native_tokenize(hit))
            if hit not in suffixes and toks and not _in_dictionary(toks[0].surface):
                suffixes.append(hit)
                from_ime.add(hit)
    else:
        suffixes=list(dict.fromkeys(hits))
        from_ime=set(suffixes)
    if subject_word:
        # Reuse the native inflections that supplied the original reading
        # proof. Optional search availability cannot change that proof.
        from semantic_roles import native_verb_lexemes, _native_lexeme_forms
        for lemma in sorted(native_verb_lexemes(verb.reading,verb.infl_form,verb.reading)):
            for face in _native_lexeme_forms(lemma,verb.infl_form,verb.reading):
                suffix=face+first[verb.end:]
                if suffix not in suffixes:suffixes.append(suffix)
    # A candidate already supplied by native spelling uses the same source
    # boundary and positive proof even when optional TSF search is absent.
    # Preserve search order; new spellings still pass every check below.
    prefix=first[:verb.start]
    for surface in supplied:
        if surface.startswith(prefix):
            suffix=surface[verb.start:]
            if suffix not in suffixes:suffixes.append(suffix)
    alternatives=[]
    for suffix in suffixes:
        if suffix==first[verb.start:]:
            continue
        proof=original_role_proof(suffix)
        if not proof:
            continue
        surface=first[:verb.start]+suffix
        if subject_word and surface==source:continue
        if not native_spelling_only(reading,surface):
            continue
        if use_dict and suffix not in from_ime:
            # 辞書の表記は辞書の読みで確かめる（IME の phonetic の代わり）
            if not _suffix_reading_ok(suffix,suffix_reading,verb_reading):
                continue
        elif ime is None or ime.phonetic(surface)!=reading:
            continue
        alternatives.append((surface,object_word,proof[0]))
    return tuple(alternatives)
