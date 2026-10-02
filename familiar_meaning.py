# -*- coding: utf-8 -*-
"""Compare explicitly reviewed verb spellings under the same native reading."""
from functools import lru_cache

@lru_cache(maxsize=1)
def families():
    import kango_tier as K
    from morphology import dictionary_inflections
    K._load();by_reading={}
    for word,tier in K._USAGE.items():
        if not word or not 'ぁ'<=word[-1]<='ゖ':continue
        for pos,form,base,rd in dictionary_inflections(word) or ():
            if (pos.startswith('動詞,自立,') and form=='基本形' and base==word):
                by_reading.setdefault(rd,{})[word]=tier
    return {rd:words for rd,words in by_reading.items()
            if 3 in words.values() and any(t in (1,2) for t in words.values())}

def roles(frame,surface):
    from morphology import dictionary_inflections
    family=families().get(frame['lemma_reading'],{})
    tiers=[family[base] for pos,form,base,rd in dictionary_inflections(surface) or ()
           if pos.startswith('動詞,自立,') and form==frame['inflection']
           and rd==frame['reading'] and base in family]
    return frozenset('restricted_spelling' if t==3 else 'ordinary_spelling' for t in tiers)

def candidates(frame):
    from semantic_roles import _native_lexeme_forms
    family=families().get(frame['lemma_reading'],{})
    # Written ordinary forms are the default; the source's kana form stays
    # ordinary and creates no anomaly merely for omitting kanji.
    return tuple(dict.fromkeys(face for word,tier in family.items()
        if tier in (1,2) and any('一'<=c<='鿿' for c in word)
        for face in _native_lexeme_forms(word,frame['inflection'],frame['reading'])))

def frames(source):
    groups=families()
    if not groups:return ()
    from morphology import tokenize
    from literal_examples import protected_ranges,overlaps
    from context_meaning import action_verb_frame
    lexemes=frozenset(w for words in groups.values() for w in words)
    parts=tokenize(source);out=[];protected=None
    for i,t in enumerate(parts):
        if t.pos!='動詞' or t.base_form not in lexemes:continue
        for rd,words in groups.items():
            if t.base_form not in words:continue
            frame=action_verb_frame(source,parts,i,t.start,'familiar_action',
                'ordinary_spelling',('ordinary_spelling','restricted_spelling'),
                '同じ実辞書の読み・活用では、明示的に稀と評価された表記より一般的な表記を選びます',
                lexemes=words)
            if frame is None:continue
            frame['lemma_reading']=rd
            frame['reading_spelling']=False
            # Familiarity is a default. An explicit last spelling for this
            # exact reading/form is stronger than the general usage judgment.
            from last_choice import surface_for_reading
            if (surface_for_reading(frame['reading'])==frame['surface']
                or surface_for_reading(frame['reading']+frame['tail_reading'])
                    ==frame['surface']+frame['query_tail']):continue
            if not candidates(frame):continue
            if protected is None:protected=protected_ranges(source)
            if not overlaps(t.start,frame['evidence_end'],protected):out.append(frame)
    return tuple(out)
