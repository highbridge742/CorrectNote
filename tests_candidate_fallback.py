# -*- coding: utf-8 -*-
import unittest
from unittest.mock import Mock, patch
import corrector as C


class CandidateFallbackTests(unittest.TestCase):
    def resolve(self, rows, accept=None):
        store = Mock()
        store.lookup.side_effect = lambda reading: rows.get(reading, [])
        with patch.object(C, '_chunk_is_intact', return_value=False), \
             patch.object(C, '_reading_intact', return_value=False), \
             patch.object(C, '_single_known_token', return_value=False), \
             patch.object(C, 'rebuild_window_core', return_value=None), \
             patch.object(C, '_looks_like_valid_japanese', return_value=False):
            return C._resolve_reading_list('異字', list(rows), store, None,
                                           accept_candidate=accept)

    def test_next_surface_keeps_existing_stable_order(self):
        seen=[]
        def accept(surface, category):
            seen.append(surface)
            return surface != '先頭'
        rows={'よみかた':[dict(surface=s, count=2) for s in ('先頭','次点','末尾')]}
        self.assertEqual(self.resolve(rows, accept), ('次点','その他'))
        self.assertEqual(seen, ['先頭','次点'])

    def test_no_callback_keeps_previous_first_choice(self):
        rows={'よみかた':[dict(surface=s, count=2) for s in ('先頭','次点')]}
        self.assertEqual(self.resolve(rows), ('先頭','その他'))

    def test_all_rejected_returns_none(self):
        rows={'よみかた':[dict(surface='先頭', count=2)],
              'よみかえ':[dict(surface='次点', count=2)]}
        self.assertIsNone(self.resolve(rows, lambda *candidate: False))

    def test_second_reading_after_first_reading_candidates_rejected(self):
        rows={'よみかた':[dict(surface='先頭', count=2)],
              'よみかえ':[dict(surface='次点', count=2)]}
        self.assertEqual(self.resolve(rows, lambda s,c: s=='次点'), ('次点','その他'))

    def test_original_surface_stops_even_with_callback(self):
        rows={'よみかた':[dict(surface='異字', count=2),dict(surface='次点', count=2)]}
        callback=Mock(return_value=True)
        self.assertIsNone(self.resolve(rows, callback))
        callback.assert_not_called()

    def test_shared_final_check_can_reject_first_and_accept_second(self):
        rows={'よみかた':[dict(surface='あいうえおか', count=2),dict(surface='文字', count=2)]}
        with patch.object(C,'absorb_stray_char',side_effect=lambda l,a,b,s:(a,b)), \
             patch.object(C,'_reading_spelled_in_bracket',return_value=False), \
             patch.object(C,'long_vowel_protected_span',return_value=None):
            result=self.resolve(rows,lambda s,c: C._check_replacement(
                '異字',(0,2,s,c),None,None)[0] is not None)
        self.assertEqual(result, ('文字','その他'))

    def resolve_rebuilt(self, rows, accepted, exact_only=()):
        store=Mock()
        store.lookup.side_effect=lambda reading:rows.get(reading,[])
        with patch.object(C,'_chunk_is_intact',return_value=False), \
             patch.object(C,'_reading_intact',return_value=False), \
             patch.object(C,'_single_known_token',return_value=False), \
             patch.object(C,'rebuild_window_core',return_value=(0,4,'なおした')) as rebuild:
            result=C._resolve_reading_list('異字',['よみかた'],store,None,
                accept_candidate=lambda surface,category:surface==accepted,
                exact_only=exact_only)
        return result,rebuild.call_count

    def test_rebuilt_reading_tries_second_surface_with_its_own_category(self):
        rows={'なおした':[dict(surface='長すぎる表記',count=2,category='名詞'),
                          dict(surface='次点',count=1,category='動詞')]}
        self.assertEqual(self.resolve_rebuilt(rows,'次点'),(('次点','動詞'),1))

    def test_exhausted_exact_candidates_do_not_skip_rebuild_for_same_reading(self):
        rows={'よみかた':[dict(surface='除外',count=2)],
              'なおした':[dict(surface='次点',count=2)]}
        self.assertEqual(self.resolve_rebuilt(rows,'次点'),(('次点','その他'),1))

    def test_exact_only_never_rebuilds_even_after_rejection(self):
        rows={'よみかた':[dict(surface='除外',count=2)],
              'なおした':[dict(surface='次点',count=2)]}
        self.assertEqual(self.resolve_rebuilt(rows,'次点',('よみかた',)),(None,0))


if __name__ == '__main__':
    unittest.main()
