# -*- coding: utf-8 -*-
import ast
from pathlib import Path
import random
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from context_vec import nearby_reanalysis_lines,build_nearby_words


def common_edges(previous,current):
    head=0
    while head<min(len(previous),len(current)) and previous[head]==current[head]:
        head+=1
    tail=0
    while tail<min(len(previous),len(current))-head and previous[-tail-1]==current[-tail-1]:
        tail+=1
    return head,tail


class NearbyInvalidationTests(unittest.TestCase):
    def test_replacement_insertion_and_deletion_boundaries(self):
        self.assertEqual(nearby_reanalysis_lines(5,4,10,10),[3,4,6,7])
        self.assertEqual(nearby_reanalysis_lines(5,5,10,11),[3,4,6,7])
        self.assertEqual(nearby_reanalysis_lines(5,4,10,9),[3,4,5,6])

    def test_unchanged_and_edges(self):
        self.assertEqual(nearby_reanalysis_lines(10,0,10,10),[])
        self.assertEqual(nearby_reanalysis_lines(0,0,0,0),[])
        self.assertEqual(nearby_reanalysis_lines(0,4,5,4),[0,1])
        self.assertEqual(nearby_reanalysis_lines(4,0,5,4),[2,3])

    def test_large_document_adds_at_most_four_reused_lines(self):
        self.assertEqual(nearby_reanalysis_lines(50000,49999,100000,100000),
                         [49998,49999,50001,50002])

    def test_all_changed_nearby_inputs_are_invalidated_for_splices(self):
        rng=random.Random(48)
        for _ in range(300):
            old=['word'+str(i) for i in range(rng.randrange(1,35))]
            a=rng.randrange(len(old)+1);b=rng.randrange(a,len(old)+1)
            new=old[:a]+['new'+str(i) for i in range(rng.randrange(5))]+old[b:]
            head,tail=common_edges(old,new)
            affected=set(nearby_reanalysis_lines(head,tail,len(old),len(new)))
            reused=[(i,i) for i in range(head)]
            reused += [(len(old)-tail+i,len(new)-tail+i) for i in range(tail)]
            for before,after in reused:
                old_words=build_nearby_words(len(old),before,lambda i:[old[i]])
                new_words=build_nearby_words(len(new),after,lambda i:[new[i]])
                if old_words!=new_words:
                    self.assertIn(after,affected,(old,new,before,after))

    def test_actual_analyze_discards_nearby_results_and_keeps_distant_results(self):
        tree=ast.parse(Path(__file__).with_name('app.py').read_text(encoding='utf-8'))
        methods=[n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='_analyze']
        remap=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='remap_pending_lines')
        scope={}
        exec(compile(ast.Module(body=[remap,methods[0]],type_ignores=[]),'app.py','exec'),scope)
        class Ready(Exception):pass
        old=['line'+str(i) for i in range(10)]
        current=old[:];current[5]='changed'
        original=[dict(original=line,corrected='cached:'+line) for line in old]
        captured=[]
        def visible(todo):captured.extend(todo);raise Ready()
        h=SimpleNamespace(_view_changing=lambda:False,_cancel_analysis_job=lambda:None,
            _mark_typed_from_shadow=lambda:None,editor_source_text=lambda:'\n'.join(current),
            _analyze_text='\n'.join(old),_prev_lines=old,line_results=original,
            _analyze_todo=[],_analyze_pos=0,store=object(),
            _shift_bookmarks=lambda *a:None,_trace_analysis=lambda *a:None,
            _blank_result=lambda line:dict(original=line,corrected=line,pending=True),
            _visible_first=visible)
        with patch('vocabulary.build_context_vocab_cached',return_value={}):
            with self.assertRaises(Ready):scope['_analyze'](h)
        self.assertEqual(captured,[3,4,5,6,7])
        self.assertIs(h.line_results[2],original[2])
        self.assertIs(h.line_results[8],original[8])
        self.assertTrue(all(h.line_results[i]['pending'] for i in captured))


if __name__=='__main__':unittest.main()
