# -*- coding: utf-8 -*-
"""A row not analysed yet: F5 and the right-click list ask the child; the window's own tables stay unread (2026-11-03)."""
import unittest
from types import SimpleNamespace
from unittest import mock

import analysis_async
import app as app_module
import ui_projection
from analysis_worker import Runtime


def _app():
    return SimpleNamespace(line_results=[{'original': '文', 'corrected': '文'}], _suspect_units_cache={},
                           _attested_surfaces={'かな': 1}, store=SimpleNamespace(_tokenize_fn=None), choices=None,
                           _known_kana_word=lambda text: False)


class EditorRow(unittest.TestCase):
    def units(self, app):
        with mock.patch.object(ui_projection, 'results', return_value=app.line_results):
            return app_module.CorrectNoteApp._editor_line_units(app, 1)

    def test_the_answer_of_the_child(self):
        with mock.patch.object(analysis_async, 'ask_child', return_value=[{'text': '文'}]) as ask, \
                mock.patch.object(app_module, 'build_suspect_units') as here:
            self.assertEqual(self.units(_app()), [{'text': '文'}])
        self.assertEqual(ask.call_args[0][1]['kind'], 'suspect_units')
        self.assertEqual(ask.call_args[0][1]['attested'], ('かな',))
        here.assert_not_called()

    def test_no_child_works_it_out_here(self):
        app = _app()
        app.store._tokenize_fn = lambda text: []
        with mock.patch.object(analysis_async, 'ask_child', return_value=None), \
                mock.patch.object(app_module, 'build_suspect_units', return_value=('文', [{'text': 'ここ'}])):
            self.assertEqual(self.units(app), [{'text': 'ここ'}])

    def test_a_row_with_kept_units_asks_nobody(self):
        app = _app()
        app._suspect_units_cache[('文', '文', False)] = ('文', [{'text': '控え'}])
        with mock.patch.object(analysis_async, 'ask_child') as ask:
            self.assertEqual(self.units(app), [{'text': '控え'}])
        ask.assert_not_called()


class WorkerKinds(unittest.TestCase):
    def test_suspect_units(self):
        import units
        run = SimpleNamespace(store=SimpleNamespace(has_reading=lambda text: False), tokenize=lambda text: [], choices=None)
        seen = {}
        def build(result, tokenize, choices, known):
            seen['known'] = known('かな'), known('ほか')
            return 'text', ['units']
        with mock.patch.object(units, 'build_suspect_units', build):
            got = Runtime.execute(run, dict(kind='suspect_units', result={}, attested=('かな',)))
        self.assertEqual(got, ['units'])
        self.assertEqual(seen['known'], (True, False))

    def test_particle_choices(self):
        import candidates
        run = SimpleNamespace(index='the index')
        with mock.patch.object(candidates, 'particle_intrusion_candidates', return_value=['c']) as made:
            got = Runtime.execute(run, dict(kind='particle_choices', text='文', start=0, end=1))
        self.assertEqual(got, ['c'])
        made.assert_called_once_with('文', 0, 1, 'the index')


if __name__ == '__main__':
    unittest.main()
