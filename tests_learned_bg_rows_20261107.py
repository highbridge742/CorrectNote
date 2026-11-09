# -*- coding: utf-8 -*-
"""Other tabs after automatic learning (2026-11-07): the revision moved only by learning is taken as not moved, so each
row is checked by what it used (used_keys) instead of the whole tab being read again with the same answers."""
from types import SimpleNamespace
import unittest

import tab_analysis


def key(revision, vocab=1, recent=()):
    # state_key: 0 id(store) 1 store.revision 2 choices 3 _analysis_state_revision 4 id(dict) 5 ready 6 id(vec)
    # 7 (input method, keyboard) 8 recent 9 (id(ime), ime revision)
    return (10, vocab, (0, 0), revision, 20, True, 30, ('kana', 'jis'), tuple(recent), (40, 0))


class LearnedSinceTests(unittest.TestCase):
    def test_learning_only_steps_are_taken_as_not_moved(self):
        app = SimpleNamespace(_learning_revisions={5: 4, 4: 3})
        moved = tab_analysis.learned_since(app, key(3, vocab=1), key(5, vocab=7))
        # only element 3 is brought to now; the vocabulary still says it moved (each row is checked by used_keys)
        self.assertEqual(moved, key(5, vocab=1))

    def test_another_bump_on_the_way_keeps_the_old_key(self):
        # 4 came from something else (input method, dictionary, an explicit choice): the whole tab is read again
        app = SimpleNamespace(_learning_revisions={5: 4})
        self.assertEqual(tab_analysis.learned_since(app, key(3), key(5)), key(3))
        self.assertEqual(tab_analysis.learned_since(SimpleNamespace(), key(3), key(4)), key(3))

    def test_nothing_to_do(self):
        app = SimpleNamespace(_learning_revisions={5: 4})
        self.assertIsNone(tab_analysis.learned_since(app, None, key(5)))
        self.assertEqual(tab_analysis.learned_since(app, key(5, vocab=2), key(5, vocab=3)), key(5, vocab=2))
        self.assertEqual(tab_analysis.learned_since(app, ('short',), key(5)), ('short',))

    def test_the_parked_value_is_not_changed_in_place(self):
        app = SimpleNamespace(_learning_revisions={5: 4}, _fg_parked={}, _completed_tabs={})
        value = dict(dependencies=key(4), results=[])
        app._fg_parked['o'] = value
        current = key(5)
        real = tab_analysis.state_key
        tab_analysis.state_key = lambda a: current
        try:
            got = tab_analysis.previous_values(app, 'o')
        finally:
            tab_analysis.state_key = real
        self.assertEqual(got['dependencies'], current)
        self.assertEqual(value['dependencies'], key(4))


if __name__ == '__main__':
    unittest.main()
