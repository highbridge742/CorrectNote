# -*- coding: utf-8 -*-
"""ui_projection.replace_text finds the changed span by slices (2026-10-17, speed).

The common head and tail must be exactly those of comparing one character at
a time (the earlier code, kept here as the reference): the same replace call.
"""
import random
import unittest

import ui_projection


def reference(widget, old, new):
    if old == new:
        return False
    start = 0
    while start < min(len(old), len(new)) and old[start] == new[start]:
        start += 1
    old_end, new_end = len(old), len(new)
    while old_end > start and new_end > start and old[old_end-1] == new[new_end-1]:
        old_end -= 1
        new_end -= 1

    def index(offset):
        prefix = old[:offset]
        return '%s.0+%sc' % (prefix.count('\n')+1, len(prefix.rsplit('\n', 1)[-1]))
    widget.replace(index(start), index(old_end), new[start:new_end])
    return True


class Recorder:
    def __init__(self):
        self.calls = []

    def replace(self, *args):
        self.calls.append(args)


class ReplaceTextTests(unittest.TestCase):
    def check(self, old, new):
        a, b = Recorder(), Recorder()
        self.assertEqual((reference(a, old, new), a.calls), (ui_projection.replace_text(b, old, new), b.calls),
                         (old, new))

    def test_random_edits_give_the_same_replace(self):
        rnd = random.Random(20261017)
        alphabet = 'ab\nあい😀x'
        for _ in range(5000):
            old = ''.join(rnd.choice(alphabet) for _ in range(rnd.randint(0, 30)))
            new = list(old)
            for _ in range(rnd.randint(0, 3)):
                i = rnd.randint(0, len(new))
                op = rnd.random()
                if op < .4:
                    new.insert(i, rnd.choice(alphabet))
                elif new:
                    j = min(i, len(new) - 1)
                    if op < .7:
                        new.pop(j)
                    else:
                        new[j] = rnd.choice(alphabet)
            self.check(old, ''.join(new) if rnd.random() > .3 else old + ''.join(new))

    def test_repeated_text_at_the_seam(self):
        for old, new in (('aaaa', 'aaaaa'), ('abab', 'ab'), ('x\nx\nx', 'x\nx'), ('', 'a'), ('a', ''),
                         ('行\n行', '行\n行\n行'), ('😀😀', '😀')):
            self.check(old, new)


if __name__ == '__main__':
    unittest.main()
