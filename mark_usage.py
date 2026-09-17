# -*- coding: utf-8 -*-
"""Intentional mark notation and short transcribed voices.

Design and counterexamples: GPT-6 / 2026-09-11 / 48-YK.
This identifies uses of the original glyphs, without correction candidates.
"""
import re
from functools import lru_cache

KNOWLEDGE_VERSION = '2026-09-13a'
_MARKS = '\u3099\u309a\u309b\u309c'
_VOICE_BASES = frozenset('叫ぶ 喚く 唸る 呻く 泣く 吠える 鳴く 怒鳴る 呟く うなる うめく つぶやく'.split())
_VOICE = re.compile(r'(?<![ぁ-ゖァ-ヶー' + _MARKS + r'])([ぁ-ゖァ-ヶー' + _MARKS + r']{2,12}?)と')
_VOWEL_VOICE = re.compile(r'[あいうえおんぁぃぅぇぉっアイウエオンァィゥェォッー' + _MARKS + r']{2,12}')
_NAMED_SYMBOL = re.compile(r'(?:濁点|半濁点|記号|文字|印)(?:は|が|[:：])\s*([' + _MARKS + r'])')
_FORM_DESCRIPTION = re.compile(r'(?<![ぁ-ゖァ-ヶ一-鿿])([ぁ-ゖァ-ヶ][' + _MARKS + r'])(?=は(?:濁点|半濁点)を付けた形)')


@lru_cache(maxsize=2048)
def intentional_ranges(line):
    """Keep codepoint positions; composing the mark would erase the notation."""
    if not any(c in _MARKS for c in line):
        return ()
    out = [match.span(1) for match in _NAMED_SYMBOL.finditer(line)]
    out.extend(match.span(1) for match in _FORM_DESCRIPTION.finditer(line))
    from morphology import tokenize
    from pos_grammar import _exclamation_shape
    for match in _VOICE.finditer(line):
        surface = match.group(1)
        if not any(c in _MARKS for c in surface):
            continue
        bare = ''.join(chr(ord(c)-0x60) if 'ァ' <= c <= 'ヶ' else c
                       for c in surface if c not in _MARKS)
        morae = sum(c not in 'ぁぃぅぇぉゃゅょっー' for c in bare)
        repeated = len(bare) >= 2 and len(bare) % 2 == 0 and bare[:len(bare)//2] == bare[len(bare)//2:]
        if (not bare or bare[0] in 'ぁぃぅぇぉゃゅょっー' or not 1 <= morae <= 2
                or not (_exclamation_shape(bare) or repeated)):
            continue
        following = tokenize(line[match.end():])
        if (following and following[0].start == 0 and following[0].has_reading
                and following[0].pos == '動詞' and following[0].base_form in _VOICE_BASES):
            out.append(match.span(1))
    # 母音・鼻音だけの短い声は、語彙の一部を切り取らず、引用/文末も確認する。
    # 前の格助詞は声のモーラへ数えない（子供がう゛う゛と泣く）。
    for match in _VOWEL_VOICE.finditer(line):
        surface=match.group()
        if not any(c in _MARKS for c in surface):
            continue
        bare=''.join(chr(ord(c)-0x60) if 'ァ'<=c<='ヶ' else c
                     for c in surface if c not in _MARKS)
        morae=sum(c not in 'ぁぃぅぇぉっー' for c in bare)
        repeated=len(bare)>=2 and len(bare)%2==0 and bare[:len(bare)//2]==bare[len(bare)//2:]
        if (not bare or bare[0] in 'ぁぃぅぇぉっー' or not 1<=morae<=2
                or not (_exclamation_shape(bare) or repeated)):
            continue
        a,b=match.span()
        previous=line[a-1:a] if a else ''
        if previous and ('ぁ'<=previous<='ゖ' or 'ァ'<=previous<='ヶ' or previous in _MARKS+'ー'):
            left=[t for t in tokenize(line) if t.end==a]
            if not left or not left[-1].has_reading or left[-1].pos!='助詞':
                continue
        pairs={'「':'」','『':'』','“':'”','‘':'’','"':'"'}
        quoted=bool(previous in pairs and line[b:b+1]==pairs[previous])
        rest=line[b:]
        if quoted or not rest or rest[:1] in '。！？!?…':
            out.append((a,b))
            continue
        if rest.startswith('と'):
            following=tokenize(rest[1:])
            if (following and following[0].start==0 and following[0].has_reading
                    and following[0].pos=='動詞' and following[0].base_form in _VOICE_BASES):
                out.append((a,b))
    return tuple(sorted(set(out)))


@lru_cache(maxsize=4096)
def unattached_positions(line):
    """A mark inside Japanese text must attach, or have an explicit notation use.

    Composition rules remain in morphology.normalize_marks. This asks that
    existing function whether the preceding character can actually receive it.
    A mark after a number, separator, or at the start is not a word-internal claim.
    """
    if not any(c in _MARKS for c in line):
        return ()
    from morphology import normalize_marks
    from literal_examples import protected_ranges, overlaps
    protected=protected_ranges(line)
    def japanese(char):
        return 'ぁ'<=char<='ゖ' or 'ァ'<=char<='ヶ' or '一'<=char<='鿿' or char=='ー'
    out=[]
    for i,char in enumerate(line):
        if (char not in _MARKS or not i or i+1>=len(line)
                or not japanese(line[i-1]) or not japanese(line[i+1])
                or overlaps(i,i+1,protected)):
            continue
        dropped=[]
        merged=normalize_marks(line[i-1:i+1],dropped=dropped)
        if not dropped and len(merged)==1:
            continue
        out.append(i)
    return tuple(out)




def normalization_seam_is_complete(text, seam, tokenize):
    """48-AAO: known token fragments do not prove a repaired word.

    GPT-6 / 2026-09-12. Require an unchanged ordinary noun reading or
    complete native clause spanning both sides of the deleted mark.
    Reuse the same grammatical evidence as the common intact entry.
    A token beginning at the seam cannot certify the preceding fragment.
    """
    from reading_segments import native_nominal_context, completed_native_reading_clause
    parts=list(tokenize(text) or ())
    from reading_segments import _native_nominal_reading_faces
    from contextual_repair import (_completed_predicate_token,
        _modern_euphonic_link, _modern_te_allowed)
    # The exact whole noun reading supplies a word across the seam even
    # when the analyzer splits がめん into a conjunction and a fragment.
    # Do not start after an unfinished lexical item or inside a noun chain.
    for i,head in enumerate(parts):
        a=head[3]
        if not seam-18<=a<seam:continue
        prior=parts[i-1] if i else None
        if prior and prior[4]==a and not (
                prior[1].startswith(('助詞','連体詞','接続詞','記号'))
                or _completed_predicate_token(prior)):
            continue
        for b in range(seam+1,min(len(text),a+18)+1):
            # An inserted mark can make a known token swallow the noun's
            # last kana and its case. The repair already has an anomaly;
            # the exact whole noun and unchanged native case prove this cut.
            boundary=any(t[3]==b for t in parts) or b==len(text)
            if not boundary:
                from morphology import dictionary_inflections
                boundary=any(pos.startswith(('助詞,格助詞,','助詞,係助詞,','助詞,連体化,'))
                    and rd==text[b:b+1]
                    for pos,form,lemma,rd in dictionary_inflections(text[b:b+1]) or ())
            if boundary and _native_nominal_reading_faces(text[a:b]):
                return True
    def past_leaves_bare_verb(index):
        return (parts[index][0] in ('た','だ') and index+1<len(parts)
                and parts[index+1][3]==parts[index][4]
                and parts[index+1][1].startswith('動詞'))
    # Native modern euphony certifies an unchanged verb + its connective.
    # Classical/unknown forms return no proof; both sides belong to the seam.
    for index,(left,right) in enumerate(zip(parts,parts[1:])):
        if not (left[4]==right[3] and left[3]<seam<=right[4]
                and left[5] and right[5] and left[1].startswith('動詞')):
            continue
        # A past ending cannot certify a cut which leaves another bare
        # verb directly after it (てれ + た + めし instead of ためし).
        if past_leaves_bare_verb(index+1):
            continue
        link=_modern_euphonic_link(right[0],right[1],right[6])
        if seam==right[4] and not (right[0] in ('て','で') and right[1].startswith('助詞:接続助詞')):
            continue
        if link is not None and _modern_te_allowed(left[0],left[2],link) is True:
            return True
    # 48-ABB: an actual adverb + adverbial particle is complete at
    # its own boundary (すぐ + に). The word and both native roles must
    # agree; noun fragments with coincidentally familiar kana do not.
    from morphology import dictionary_inflections
    for left,right in zip(parts,parts[1:]):
        if not (left[4]==right[3]==seam and left[5] and right[5]
                and left[1].startswith('副詞:助詞類接続')
                and right[1]=='助詞:副詞化'):
            continue
        if (any(pos.startswith('副詞,助詞類接続,') and rd==left[2]
                for pos,form,base,rd in dictionary_inflections(left[0]) or ())
                and any(pos.startswith('助詞,副詞化,') and rd==right[2]
                for pos,form,base,rd in dictionary_inflections(right[0]) or ())):
            return True
    starts={t[3] for t in parts if seam-24<=t[3]<seam}
    ends={t[4] for t in parts if seam<t[4]<=seam+24}
    # A case followed by an unchanged modern predicate establishes the
    # boundary too. Reuse native forms and the candidate grammar engine;
    # neither arbitrary known fragments nor a frequency score supplies it.
    from reading_segments import completed_sahen_reading
    from contextual_repair import _allows_grammatical_tail, _productive_predicate
    from morphology import dictionary_inflections
    if any(native_nominal_context(text,a,seam,tokenize) for a in starts):
        head=next((t for t in parts if t[3]==seam),None)
        for b in sorted(ends):
            fragment=text[seam:b]
            if completed_sahen_reading(fragment,allow_nonpolite=True):
                return True
            if head and head[5] and head[1].startswith(('動詞','名詞:サ変接続')) and head[4]<=b:
                forms=[row for row in dictionary_inflections(head[0]) or ()
                       if row[0].startswith(('動詞,','名詞,サ変接続,')) and row[3]==head[2]]
                suffix=text[head[4]:b]
                if (forms and _allows_grammatical_tail(forms,suffix,head[2],head[0])
                        and _productive_predicate(fragment,head[0])):
                    return True
    # 48-ABG: a complete unchanged native predicate can also span
    # the deleted mark (おくれ + ました). Validate the entire functional
    # tail using the same grammar and native forms as generated repairs.
    # A following content word cannot be consumed as an auxiliary.
    for head in parts:
        if not (head[3] in starts and head[5] and head[1].startswith('動詞:自立')):
            continue
        forms=[row for row in dictionary_inflections(head[0]) or ()
               if row[0].startswith('動詞,自立,') and row[3]==head[2]]
        for b in sorted(ends):
            if head[4]>b:continue
            terminal=next((i for i,t in enumerate(parts) if t[4]==b),None)
            if terminal is not None and past_leaves_bare_verb(terminal):continue
            suffix=text[head[4]:b]
            if (forms and _allows_grammatical_tail(forms,suffix,head[2],head[0])
                    and _productive_predicate(text[head[3]:b],head[0])):
                return True
    for a in sorted(starts,reverse=True):
        for b in sorted(ends):
            fragment=text[a:b]
            if (native_nominal_context(text,a,b,tokenize)
                    or completed_native_reading_clause(fragment)):
                return True
    return False


def incomplete_mark_deletion(source, changed, tokenize):
    """The shared final gate also checks mark-only legacy candidates."""
    if tokenize is None or not any(c in _MARKS for c in source):
        return False
    i=j=0;dropped=[]
    while i<len(source):
        if j<len(changed) and source[i]==changed[j]:
            i+=1;j+=1
        elif source[i] in _MARKS:
            dropped.append(i);i+=1
        else:
            return False
    if j!=len(changed) or not dropped:
        return False
    anomalous=set(unattached_positions(source))
    return any(position in anomalous and not normalization_seam_is_complete(
        changed,position-n,tokenize) for n,position in enumerate(dropped))


def normalized_intrusions(source, normalized, dropped, tokenize, store=None,
                          dictionary=None, decisions=None):
    """48-ZO: deleting an unattached mark is itself a one-key repair.

    GPT-6 / 2026-09-11. The original anomaly comes first. Its neighboring
    readings and physical keystrokes must explain the deletion, and the
    same source-coordinate replacement and grammar checks must accept it.
    This does not infer that every dropped mark should disappear.
    """
    if not dropped or tokenize is None:
        return False
    positions=sorted(set(dropped))
    if not set(positions)<=set(unattached_positions(source)):
        return False
    if normalized!=''.join(c for i,c in enumerate(source) if i not in positions):
        return False
    import corrector as C
    from contextual_repair import key_repairs
    from reading_likelihood import adjacent_readings
    from oddness import structural_anomaly_in_range
    original=list(tokenize(source) or ())
    changed=list(tokenize(normalized) or ())
    for n,position in enumerate(positions):
        left,right=adjacent_readings(source,original,position,position+1)
        if not left or not right:
            return False
        mark='゛' if source[position] in ('゛','\u3099') else '゜'
        segment=left[-1]+mark+right[0]
        if not any(row.operation=='adjacent_intrusion' and row.reading==left[-1]+right[0]
                   for row in key_repairs(segment)):
            return False
        replacement=(position,position+1,'','かな入力')
        accepted,reason=C._check_replacement(source,replacement,store,tokenize,
                                             dictionary,decisions)
        if accepted!=replacement:
            return False
        seam=position-n
        if not normalization_seam_is_complete(normalized,seam,tokenize):
            return False
        neighboring=[t for t in changed if t[3]<seam+1 and seam-1<t[4]]
        if not neighboring or any(not t[5] for t in neighboring):
            return False
        if structural_anomaly_in_range(normalized,max(0,seam-1),min(len(normalized),seam+1),
                                        tokenize,store,dictionary):
            return False
    return True
