# -*- coding: utf-8 -*-
"""Contrast an event and the kind of result named by ``後の``.

This compares ordinary event senses, not a stored misspelling-answer pair.
The original is suspicious only when a return-of-property event is followed
by a symbolic text unit rather than a returnable document or procedure.
"""

from semantic_roles import nominal_roles, _BORROWED_RETURN_PREDICATES


_CONTENT_TRANSFORMATIONS = frozenset('変換 転換 翻字 転写'.split())


def symbolic_result_candidate(source, tokens):
    """Return (action_end, candidate_action, action_reading) or None."""
    if (not source or len(source) > 30
            or any(c in source for c in '\t\r\n「」『』“”"。、！？!?;；')):
        return None
    if len(tokens) != 4 or any(len(t) < 7 for t in tokens):
        return None
    if (''.join(t[0] for t in tokens) != source
            or any(tokens[i][4] != tokens[i+1][3] for i in range(3))):
        return None
    action, after, genitive, head = tokens
    if (action[0] not in _BORROWED_RETURN_PREDICATES
            or action[3] != 0 or not action[5]
            or not action[1].startswith('名詞:サ変接続')
            or after[0] != '後' or not after[1].startswith('名詞:接尾')
            or genitive[0] != 'の' or not genitive[1].startswith('助詞:連体化')
            or not head[1].startswith('名詞:') or not head[5]
            or not {'shape', 'text'} <= nominal_roles(head[0])):
        return None
    try:
        from ime_language import JapaneseIME
        from morphology import tokenize

        with JapaneseIME() as ime:
            if not ime.available:
                return None
            back = ime.reverse_words(source)
            if not back or not back[0]:
                return None
            first = ime.convert_words(back[0])
            if (not first or first[0] == source
                    or not first[0].endswith(source[action[4]:])):
                return None
            candidate = first[0]
            candidate_action = candidate[:action[4]]
            if candidate_action not in _CONTENT_TRANSFORMATIONS:
                return None
            parts = tokenize(candidate)
            if (len(parts) != 4 or parts[0].surface != candidate_action
                    or parts[0].pos != '名詞' or parts[0].pos_sub != 'サ変接続'):
                return None
            candidate_back = ime.reverse_words(candidate)
            if not candidate_back or candidate_back[0] != back[0]:
                return None
            action_reading = tokens[0][2]
            if not action_reading or not back[0].startswith(action_reading):
                return None
            return action[4], candidate_action, action_reading
    except (ImportError, OSError, AttributeError, ValueError):
        return None
