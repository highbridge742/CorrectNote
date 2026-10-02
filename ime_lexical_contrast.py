# -*- coding: utf-8 -*-
"""A source-local IME contrast for a split colloquial verb.

The source grammar must be anomalous before IME conversion is consulted.
The IME first conversion is a candidate, never evidence on its own.
"""


def split_colloquial_candidate(source, tokens):
    """Return (core_end, surface, reading, anomaly_end) or None.

    A known one-character verb in conjunctive form followed immediately by an
    independent kana verb in sokuon form is a possible false segmentation.
    Accept only a whole-field, same-reading IME contrast whose changed stem
    is independently proved as a ra-row verb by its lemma and inflection.
    """
    from morphology import HAS_JANOME

    if (not HAS_JANOME or not source or len(source) > 30
            or any(c in source for c in '\t\r\n「」『』“”\"')
            or source.count('。') + source.count('！') + source.count('？')
               + source.count('!') + source.count('?') > 1):
        return None
    core = source[:-1] if source[-1] in '。！？!?' else source
    if not core or any(c in core for c in '。、！？!?;；'):
        return None
    parts = [t for t in tokens if t[3] < len(core)]
    if len(parts) < 3 or ''.join(t[0] for t in parts) != core:
        return None
    left, right = parts[:2]
    if (len(left) < 7 or len(right) < 7 or len(parts[2]) < 7
            or left[3] != 0 or left[4] != right[3] or not left[5]
            or not left[1].startswith('動詞:自立') or left[6] != '連用形'
            or len(left[0]) != 1
            or not ('一' <= left[0] <= '鿿' or 'ぁ' <= left[0] <= 'ゖ')
            or not right[1].startswith('動詞:自立')
            or right[6] != '連用タ接続' or len(right[0]) < 2
            or not right[0].endswith('っ')
            or not all('ぁ' <= c <= 'ゖ' for c in right[0])
            or parts[2][0] not in ('て', 'た', 'たら', 'たり')
            or not parts[2][1].startswith(('助詞:接続助詞', '助動詞'))):
        return None
    from literal_examples import protected_ranges

    if protected_ranges(source):
        return None
    stem_end = right[3] + 1
    if stem_end >= len(core):
        return None

    try:
        from ime_language import JapaneseIME

        with JapaneseIME() as ime:
            if not ime.available:
                return None
            inverse = ime.reverse_words(core)
            if not inverse or not inverse[0] or not inverse[1]:
                return None
            reading, source_words = inverse
            # An already unified source verb is not a split-verb anomaly.
            if source_words[0][0] == 0 and source_words[0][1] == stem_end \
                    and source_words[0][4] == 208:
                return None
            first = ime.convert_words(reading)
            if not first or len(first[1]) < 2:
                return None
            candidate, words = first
            if (candidate == core or len(candidate) != len(core)
                    or candidate[stem_end:] != core[stem_end:]):
                return None
            head = candidate[:stem_end]
            if (len(head) < 2 or not all('ァ' <= c <= 'ヶ' or c == 'ー' for c in head)
                    or words[0][0:2] != (0, stem_end)
                    or words[0][4] != 208 or words[0][5] & 16):
                return None
            head_reading = reading[words[0][2]:words[0][3]]
            if words[0][2] != 0 or not head_reading:
                return None
            lemma, lemma_reading = head + 'る', head_reading + 'る'
            back = ime.reverse_words(lemma)
            forward = ime.convert_words(lemma_reading)
            candidate_back = ime.reverse_words(candidate)
            if (not back or back[0] != lemma_reading or len(back[1]) != 2
                    or back[1][0][:5] != (0, len(head), 0, len(head_reading), 208)
                    or back[1][0][5] & 16
                    or back[1][1][:5] != (len(head), len(lemma),
                                         len(head_reading), len(lemma_reading), 0)
                    or not forward or forward[0] != lemma
                    or not candidate_back or candidate_back[0] != reading):
                return None
    except (ImportError, OSError, AttributeError, ValueError):
        return None
    return len(core), candidate, reading, right[4]
