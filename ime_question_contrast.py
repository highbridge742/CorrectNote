# -*- coding: utf-8 -*-
"""Native interrogative + nominative + nominal predicate against a derived suffix.

The source must end in a bare ``化`` derivation after an explicit question
subject. A same-reading IME candidate ending in the native question particle
is then tested by the ordinary correction gate. The IME first result alone
does not establish an anomaly.
"""


_QUESTION_SUBJECTS = frozenset(('何', 'どこ', 'どれ', 'どちら'))


def bare_question_candidate(source, tokens):
    """Return (suffix_start, candidate, reading) for one closed clause."""
    if (not source or len(source) > 30
            or any(c in source for c in '\t\r\n「」『』“”"')
            or source.count('。') + source.count('！') + source.count('？')
               + source.count('!') + source.count('?') > 1):
        return None
    core = source[:-1] if source[-1] in '。！？!?' else source
    if len(core) < 4 or any(c in core for c in '。、！？!?;；'):
        return None
    parts = [t for t in tokens if len(t) >= 7 and t[3] < len(core)]
    if (len(parts) != 4 or ''.join(t[0] for t in parts) != core
            or any(parts[i][4] != parts[i+1][3] for i in range(3))):
        return None
    subject, case, predicate, suffix = parts
    if (subject[0] not in _QUESTION_SUBJECTS or subject[3] != 0
            or not subject[1].startswith('名詞:代名詞')
            or case[0] != 'が' or not case[1].startswith('助詞:格助詞')
            or not predicate[1].startswith('名詞:')
            or '固有名詞' in predicate[1]
            or suffix[0] != '化' or not suffix[1].startswith('名詞:接尾')
            or not all(t[5] for t in parts)):
        return None
    from literal_examples import protected_ranges
    if protected_ranges(source):
        return None
    from morphology import tokenize, dictionary_inflections
    if not any(pos.startswith('助詞,') and '終助詞' in pos and rd == 'か'
               for pos, form, base, rd in dictionary_inflections('か') or ()):
        return None
    candidate = core[:-1] + 'か'
    changed = tokenize(candidate)
    if (not changed or changed[-1].surface != 'か'
            or changed[-1].pos != '助詞' or '終助詞' not in changed[-1].pos_sub
            or changed[-1].start != suffix[3]):
        return None
    try:
        from ime_language import JapaneseIME
        with JapaneseIME() as ime:
            if not ime.available:
                return None
            backward = ime.reverse_words(core)
            if not backward or not backward[0] or len(backward[1]) < 4:
                return None
            reading, source_words = backward
            first = ime.convert_words(reading)
            if (not first or first[0] != candidate or len(first[1]) < 4
                    or source_words[-1][:2] != (suffix[3], suffix[4])
                    or source_words[-1][4] != 803
                    or first[1][-1][:2] != (suffix[3], suffix[4])
                    or first[1][-1][4] != 0):
                return None
            candidate_back = ime.reverse_words(candidate)
            if not candidate_back or candidate_back[0] != reading:
                return None
    except (ImportError, OSError, AttributeError, ValueError):
        return None
    return suffix[3], candidate, reading
