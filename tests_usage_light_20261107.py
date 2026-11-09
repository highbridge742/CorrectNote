# -*- coding: utf-8 -*-
"""A typed row's light answer (the heavy steps left out, defer_heavy) adds nothing to usage_counts; its heavy redo (the
final answer) counts the row once, and a row whose light answer needs no redo counts with that answer
(2026-11-07 うにさん「軽い答えではカウントしない」). Made-up rows in a real child, the bundled initial state."""
import unittest

import analysis_worker
import usage_counts
from tests_analysis_async import initial, wait


def counted():
    return {name: list(values) for name, values in usage_counts.snapshot().items()}


def grew(before, after):
    return {name: [after[name][k] - before.get(name, [0, 0, 0])[k] for k in range(3)]
            for name in after if after[name] != before.get(name, [0, 0, 0])}


class UsageLight(unittest.TestCase):
    def test_light_answers_are_not_counted(self):
        a = initial(); worker = analysis_worker.Worker()
        try:
            state = analysis_worker.snapshot(a)
            line = 'あしたのかいぎはじゅうじからでつ'
            prepared = wait(worker, worker.submit(dict(kind='prepare', lines=[line]), state))
            task = dict(kind='line', line=line, context=prepared['context'], input_method='kana',
                        attested=prepared['attested'])
            before = counted()
            light = wait(worker, worker.submit(dict(task, defer_heavy=True)))
            self.assertTrue(light['result'].get('deferred_stages'), light['result'])
            self.assertEqual(grew(before, counted()), {})                 # the light answer: nothing
            before = counted()
            wait(worker, worker.submit(task))                              # the heavy redo: the final answer
            after = counted()
            changed = grew(before, after)
            self.assertTrue(changed)
            self.assertEqual(max(v[0] for v in changed.values()), 1, changed)   # once per stage for the row
            self.assertTrue(all(v[2] <= v[1] <= v[0] for v in after.values()))
            # a light answer that needs no redo is the final one: it counts
            plain = '今日は天気がよい。'
            prepared = wait(worker, worker.submit(dict(kind='prepare', lines=[plain])))
            before = counted()
            got = wait(worker, worker.submit(dict(kind='line', line=plain, context=prepared['context'], input_method='kana',
                                                  attested=prepared['attested'], defer_heavy=True)))
            if not got['result'].get('deferred_stages'):
                self.assertTrue(grew(before, counted()))
        finally:
            worker.close()


if __name__ == '__main__':
    unittest.main()
