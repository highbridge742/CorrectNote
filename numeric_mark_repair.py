"""A closed numeric unit uses native counter identity and physical mark keys."""
import re
from functools import lru_cache


@lru_cache(maxsize=128)
def counter_faces(reading):
    from corrector import table_surfaces_for_reading
    from morphology import dictionary_inflections
    # The table locates spellings; exact native counter POS/reading, including
    # dependent suffixes omitted by the ordinary lexical inventory, proves them.
    return tuple(sorted(face for face in table_surfaces_for_reading(reading,limit=12)
        if any(pos.startswith('名詞,接尾,助数詞,') and rd == reading
               for pos, form, base, rd in dictionary_inflections(face) or ())))


def native_counter_allomorph(number, reading):
    """Retain numeric h-row counter sound changes before a key repair."""
    from kana_layout import MARK_OF,DAKUTEN_BASE
    if not reading or reading[0] not in MARK_OF or not number.isdecimal():return False
    base=DAKUTEN_BASE[reading[0]];mark=MARK_OF[reading[0]]
    if base not in 'はひふへほ' or not counter_faces(base+reading[1:]):return False
    ending=int(number[-1])
    # Japan Foundation counting chart, PDF pp.71 and 284:
    # https://www.jpf.go.jp/j/urawa/j_rsorcs/textbook/dl/setsumei/setsumei_all.pdf
    # Native h-row counters geminate after 1/6/8/10; 3 voices them.
    # f-row counters instead use the p allomorph after nasal 3 and 4 too.
    # A dictionary counter with that unvoiced reading must exist first.
    if mark=='゜':return ending in ((0,1,3,4,6,8) if base=='ふ' else (0,1,6,8))
    return mark=='゛' and ending==3


def frames(line):
    # Read a unit slot only after a literal number in its own closed field.
    # Written loanwords and objects with a following predicate keep their use.
    from morphology import COLUMN_SEPARATOR, normalize_marks, katakana_to_hiragana, tokenize
    from literal_examples import protected_ranges, overlaps
    from contextual_repair import key_repairs
    separators = re.compile(COLUMN_SEPARATOR.pattern + r'|[。！？!?;；]')
    edges = [0] + [match.end() for match in separators.finditer(line)]
    ends = [match.start() for match in separators.finditer(line)] + [len(line)]
    protected = protected_ranges(line)
    out = []
    for lo, hi in zip(edges, ends):
        match = re.fullmatch(r'\s*[0-9０-９]+(?:[.．][0-9０-９]+)?([ぁ-ゖ゛゜\u3099\u309a\uff9e\uff9f一-鿿]{2,10}(?:[ \u3000][ぁ-ゖ゛゜\u3099\u309a\uff9e\uff9f一-鿿]{1,10})?)\s*', line[lo:hi])
        if not match:continue
        start, end = lo+match.start(1), lo+match.end(1)
        word = line[start:end]
        if overlaps(start, end, protected):continue
        dropped = []; normalized = normalize_marks(word, dropped=dropped)
        reading = ''
        # A single internal IME segment space is inside this proven unit slot.
        # Analyze its combined spelling, retaining the original source range.
        for token in tokenize(normalized.replace(' ','').replace('\u3000','')):
            if all('ぁ' <= c <= 'ゖ' for c in token.surface):reading += token.surface
            elif token.has_reading:reading += katakana_to_hiragana(token.reading)
            else:break
        else:
            # Source identity is evaluated before looking for a repair.
            number=line[lo:lo+match.start(1)].strip()
            if not reading or native_counter_allomorph(number,reading):continue
            original_counter = counter_faces(reading)
            if original_counter and not dropped:continue
            for repair in key_repairs(reading):
                same_native = bool(original_counter and dropped and repair.operation=='same_reading')
                physical_mark = (repair.operation=='adjacent_substitution'
                    and {repair.pressed,repair.intended}=={'゛','゜'})
                if not (same_native or physical_mark):continue
                for face in counter_faces(repair.reading):
                    out.append(dict(start=start, end=end, lo=lo, hi=hi,
                        reading=reading, surface=face, repair=repair,
                        normalized_marks=tuple(dropped)))
    return out


@lru_cache(maxsize=128)
def _unit_meaning_facts(source):
    return tuple((f['start'],f['end'],f['surface'],f['reading']) for f in frames(source))


def candidate_evidence(source,start,end,surface):
    """The native counter fulfils the source's numeric unit role across routes."""
    from morphology import dictionary_inflections
    for a,b,face,reading in _unit_meaning_facts(source):
        if (a,b)==(start,end) and any(pos.startswith('名詞,接尾,助数詞,')
                for pos,form,base,rd in dictionary_inflections(surface) or ()):
            return dict(kind='numeric_mark_counter',expected_role='native_counter',
                        relation='native_numeric_unit',source_reading=reading,
                        unit_surface=surface,evidence_start=a,evidence_end=b)
    return None
