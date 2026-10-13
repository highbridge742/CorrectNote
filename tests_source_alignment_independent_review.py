# CorrectNote — Copyright (C) 2026 Takahashi Yuu
# SPDX-License-Identifier: GPL-3.0-or-later
"""Independent Unicode, exact-containment, and worker cancellation contracts."""
import difflib
import queue
import unittest
from unittest.mock import patch
import analysis_context as A
import analysis_worker as W
import corrector as C
from ime_session import resource_scope, retain, _CURRENT
from tests_source_alignment_scope import frozen93_ranges

class IndependentCheckpointTests(unittest.TestCase):

    def test_new_unicode_and_repeated_field_ties_keep_stdlib_result(self):
        raw = 'kouendearukisoudesu'
        fields = '\t'.join((raw, 'fn( ' + raw + ' )', raw))
        originals = (('👩🏽\u200d💻 é ' + fields, '👩🏽\u200d💻 é 公園で歩きそうです\tfn( ' + raw + ' )\t' + raw), ('\t'.join((raw, raw, raw)), '\t'.join(('公園で歩きそうです', raw, 'こうえんで歩きそうです'))), ('a' * 205 + '💡B' + 'a' * 205, 'a' * 205 + 'B💡' + 'a' * 205), ('文' * 220 + '\r\n⇒' + '文' * 220, '文' * 219 + '\r\n⇒' + '文' * 221), ('aaaaabbabbabbcaaaaa', 'aaaaabbcabbabbaaaaa'), ('😀á⇒😀á⇒外', '😀á⇒😀á⇒外'), ('元外', ''), ('', '👩🏽\u200d💻'), ('甲乙' * 100 + '丙', '甲乙' * 99 + '丙甲乙'))
        details = []
        for (original, current) in originals:
            with self.subTest(lengths=(len(original), len(current))):
                oracle = difflib.SequenceMatcher(None, original, current, autojunk=False)
                candidate = difflib.SequenceMatcher(None, C._SourceRangeText(original), C._SourceRangeText(current), autojunk=False)
                self.assertEqual(candidate.get_matching_blocks(), oracle.get_matching_blocks())
                self.assertEqual(candidate.get_opcodes(), oracle.get_opcodes())
                details.append({'original': original, 'current': current, 'opcodes': oracle.get_opcodes()})

    def test_new_source_field_edges_keep_original_ambiguous_mapping(self):
        raw = 'kouendearukisoudesu'
        ancestor = '👩🏽\u200d💻 é ' + raw + '\tfn( ' + raw + ' )\t' + raw
        current = '👩🏽\u200d💻 é 公園で歩きそうです\tfn( ' + raw + ' )\t' + raw
        token = C._CORRECTION_PATH.set((ancestor,))
        rows = []
        try:
            first = current.index(raw)
            last = current.rindex(raw)
            intervals = ((0, 4), (first, first + len(raw)), (last, last + len(raw)), (first + 3, first + 8), (last + 3, last + 8), (first - 1, first), (last, last), (len(current), len(current)))
            with resource_scope():
                (cache, _) = retain(C._SourceRangeOpcodes())
                for (start, end) in intervals:
                    for empty in (False, True):
                        expected = list(frozen93_ranges(current, start, end, empty))
                        actual = list(C._candidate_source_ranges(current, start, end, allow_empty=empty))
                        self.assertEqual(actual, expected, (start, end, empty))
                        rows.append({'range': (start, end), 'allow_empty': empty, 'views': actual})
                self.assertEqual(len(cache.opcodes), 1)
            self.assertEqual(cache.opcodes, {})
        finally:
            C._CORRECTION_PATH.reset(token)

    def test_final_check_ignores_long_poll_cadence_before_cache_commit(self):
        original = '元' + '文' * 80 + '外'
        current = '文' * 80 + '別'
        stale = [False]
        real = difflib.SequenceMatcher
        calls = []

        class CompletedThenObsolete(real):

            def get_opcodes(self):
                result = super().get_opcodes()
                stale[0] = True
                return result
        token = C._CORRECTION_PATH.set((original,))
        try:
            with resource_scope():
                (cache, _) = retain(C._SourceRangeOpcodes())

                def check():
                    calls.append(stale[0])
                    return stale[0]
                with A.request_scope(check, poll_interval=3600), patch.object(difflib, 'SequenceMatcher', CompletedThenObsolete):
                    with self.assertRaises(A.SupersededAnalysis):
                        list(C._candidate_source_ranges(current, 0, 4))
                self.assertEqual(cache.opcodes, {})
            self.assertEqual(cache.opcodes, {})
        finally:
            C._CORRECTION_PATH.reset(token)
        self.assertEqual(calls[-1], True)
        self.assertIsNone(A._REQUEST_CHECK.get())

    def test_actual_worker_loop_supersedes_inside_index_and_matching(self):
        for stage in ('index', 'matching'):
            with self.subTest(stage=stage):
                inbox = queue.Queue()
                outputs = []
                states = []
                entered = []
                abandoned = []
                closed = []
                phase = {'matching': False, 'queued': False, 'reads': 0}
                original = '元' + '文' * 700 + '甲' + '文' * 700 + '外'
                current = '文' * 700 + '乙' + '文' * 700 + '別'
                inbox.put({'id': 1, 'task': {'kind': 'line', 'line': 'old'}, 'state': 'A'})
                real_matcher = difflib.SequenceMatcher
                real_view = C._SourceRangeText

                class MatchingPhase(real_matcher):

                    def find_longest_match(self, *args, **kwargs):
                        phase['matching'] = True
                        try:
                            return super().find_longest_match(*args, **kwargs)
                        finally:
                            phase['matching'] = False

                class ArrivalView(real_view):

                    def __getitem__(self, index):
                        phase['reads'] += 1
                        is_stage = phase['matching'] if stage == 'matching' else not phase['matching']
                        if not phase['queued'] and is_stage:
                            phase['queued'] = True
                            inbox.put({'id': 2, 'task': {'kind': 'line', 'line': 'intermediate'}, 'state': 'B'})
                            inbox.put({'id': 3, 'task': {'kind': 'line', 'line': 'latest'}, 'state': None})
                        return super().__getitem__(index)

                class Handle:

                    def close(self):
                        closed.append(True)
                owner = self

                class Runtime:
                    state = None

                    def set_state(self, state):
                        self.state = state
                        states.append(state)

                    def execute(self, task):
                        entered.append(task['line'])
                        if task['line'] == 'old':
                            token = C._CORRECTION_PATH.set((original,))
                            try:
                                with resource_scope():
                                    retain(Handle())
                                    (cache, _) = retain(C._SourceRangeOpcodes())
                                    try:
                                        list(C._candidate_source_ranges(current, 0, 3))
                                    except A.SupersededAnalysis:
                                        abandoned.append(dict(cache.opcodes))
                                        raise
                                    owner.fail('obsolete matching returned')
                            finally:
                                C._CORRECTION_PATH.reset(token)
                        owner.assertEqual(self.state, 'B')
                        owner.assertEqual(closed, [True])
                        owner.assertIsNone(_CURRENT.get())
                        owner.assertEqual(C._CORRECTION_PATH.get(), ())
                        return {'line': task['line'], 'state': self.state}

                class Connection:

                    def pump(self):
                        return True

                    def get(self, inbox):
                        return inbox.get_nowait()

                class Outbox:

                    def put(self, result):
                        outputs.append(result)
                        inbox.put(None)
                with patch.object(W, 'Runtime', Runtime), patch.object(C, '_SourceRangeText', ArrivalView), patch.object(difflib, 'SequenceMatcher', MatchingPhase):
                    W._serve_requests(inbox, Outbox(), Connection())
                self.assertTrue(phase['queued'])
                self.assertEqual(entered, ['old', 'latest'])
                self.assertEqual(states, ['A', 'B'])
                self.assertEqual(abandoned, [{}])
                self.assertEqual(outputs, [(3, {'line': 'latest', 'state': 'B'}, None)])
                self.assertIsNone(A._REQUEST_CHECK.get())
                self.assertIsNone(_CURRENT.get())
                self.assertEqual(C._CORRECTION_PATH.get(), ())

class IndependentContainmentTests(unittest.TestCase):

    def test_earliest_full_unicode_tie_and_noncontained_two_blocks(self):
        word = '👩🏽\u200d💻é\t⇒'
        cases = ((word, word + '間' + word), (word + '間' + word, word), ('abcab', 'abcabcababcab'), ('abcabcababcab', 'abcab'), ('αβα', 'αβαβα'), ('αβαβα', 'αβα'), ('aaXbb', 'aaYbb'), ('文' * 220 + '甲', '文' * 220 + '乙'), ('前' + word * 3 + '終', '別' + word * 3 + '後'), ('caba', 'abac'), ('ababxaba', 'abaxabab'), ('', word), (word, ''))
        real = difflib.SequenceMatcher
        details = []
        for (original, current) in cases:
            seen = []
            calls = []

            class Observed(real):

                def __init__(self, *args, **kwargs):
                    super().__init__(*args, **kwargs)
                    seen.append(self)

                def find_longest_match(self, *args, **kwargs):
                    calls.append(args)
                    return super().find_longest_match(*args, **kwargs)
            token = C._CORRECTION_PATH.set((original,))
            try:
                with patch.object(difflib, 'SequenceMatcher', Observed):
                    actual = list(C._candidate_source_ranges(current, 0, len(current), allow_empty=True))
                self.assertEqual(len(seen), 1)
                oracle = real(None, original, current, autojunk=False)
                self.assertEqual(seen[0].get_opcodes(), oracle.get_opcodes(), (original, current))
                self.assertEqual(seen[0].get_matching_blocks(), oracle.get_matching_blocks(), (original, current))
                contained = bool(original and current and (original in current or current in original))
                if contained:
                    self.assertFalse(calls, (original,current))
                elif not calls:
                    # Independently verify that every source or output
                    # character outside the sole stdlib match is absent
                    # from the other whole input. This proves its upper
                    # bound without assuming the candidate trim code.
                    std_blocks=oracle.get_matching_blocks()
                    self.assertEqual(len(std_blocks),2)
                    x,y,n=std_blocks[0]
                    outside_source=original[:x]+original[x+n:]
                    outside_output=current[:y]+current[y+n:]
                    self.assertTrue(not set(outside_source)&set(current)
                        or not set(outside_output)&set(original))
                blocks = seen[0].get_matching_blocks()
                if contained:
                    self.assertEqual(len(blocks), 2)
                    self.assertEqual(blocks[0].size, min(len(original), len(current)))
                    (a, b, n) = blocks[0]
                    self.assertTrue(a == 0 or b == 0)
                    self.assertTrue(a + n == len(original) or b + n == len(current))
                details.append({'original': original, 'current': current, 'contained': contained, 'blocks': blocks, 'longest_match_calls': len(calls), 'views': actual})
            finally:
                C._CORRECTION_PATH.reset(token)

    def test_each_repeated_containment_occurrence_keeps_oracle_edges(self):
        word = '💡é\t⇒外'
        longer = '先' + word + '間' + word + '末'
        rows = []
        for (original, current) in ((word, longer), (longer, word)):
            token = C._CORRECTION_PATH.set((original,))
            try:
                boundaries = (0, 1, len(current) - 1, len(current))
                if current == longer:
                    first = current.index(word)
                    second = current.rindex(word)
                    boundaries += (first, first + len(word), second, second + len(word))
                boundaries = sorted(set(boundaries))
                with resource_scope():
                    (cache, _) = retain(C._SourceRangeOpcodes())
                    for start in boundaries:
                        for end in boundaries:
                            if end < start:
                                continue
                            for empty in (False, True):
                                actual = list(C._candidate_source_ranges(current, start, end, allow_empty=empty))
                                expected = list(frozen93_ranges(current, start, end, empty))
                                self.assertEqual(actual, expected, (original, current, start, end, empty))
                                rows.append((len(original), len(current), start, end, empty))
                    self.assertEqual(len(cache.opcodes), 1)
                self.assertEqual(cache.opcodes, {})
            finally:
                C._CORRECTION_PATH.reset(token)

    def test_cancellation_at_find_return_cannot_commit_fast_or_standard_branch(self):
        for contains in (True, False):
            stale = [False]
            searches = []

            class OriginalString(str):

                def find(self, sub, *args):
                    result = super().find(sub, *args)
                    searches.append(result)
                    stale[0] = True
                    return result
            original = OriginalString('元' + '文' * 100 + '外')
            current = '文' * 100 if contains else '文' * 100 + '別'
            token = C._CORRECTION_PATH.set((original,))
            try:
                with resource_scope():
                    (cache, _) = retain(C._SourceRangeOpcodes())
                    with A.request_scope(lambda : stale[0], poll_interval=3600):
                        with self.assertRaises(A.SupersededAnalysis):
                            list(C._candidate_source_ranges(current, 0, 4))
                    self.assertEqual(cache.opcodes, {})
                self.assertEqual(cache.opcodes, {})
            finally:
                C._CORRECTION_PATH.reset(token)
            self.assertEqual(len(searches), 1)
            self.assertEqual(searches[0] >= 0, contains)
            self.assertIsNone(A._REQUEST_CHECK.get())
if __name__ == '__main__':
    unittest.main()
