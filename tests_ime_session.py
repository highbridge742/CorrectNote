# -*- coding: utf-8 -*-
"""Scoped IME ownership must survive failure, nesting and copied contexts."""
from contextvars import Context,copy_context
from threading import Thread,get_ident
from unittest.mock import patch
import ctypes as C
import unittest
import ime_session as P
import ime_language as L
import ime_candidates as S


class IMESessionTests(unittest.TestCase):
    def test_optional_windows_apis_are_unavailable_without_breaking_imports(self):
        import subprocess,sys
        script = """
import ctypes as C
for name in ('OleDLL','WinDLL','WINFUNCTYPE'):
    if hasattr(C,name):delattr(C,name)
import ime_candidates as S
import ime_language as L
assert C.sizeof(S.GUID)==16
assert C.sizeof(S.HRESULT)==4
for factory in (S.SearchCandidates,L.JapaneseIME):
    with factory() as native:
        assert not native.available
        assert native.error
assert not native.available
"""
        result=subprocess.run([sys.executable,'-B','-S','-X','utf8','-c',script],
                              capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_resources_are_lazy_nested_and_released_once_in_reverse_order(self):
        events=[]
        class One:
            def close(self):events.append('one')
        class Two:
            def close(self):events.append('two')
        a=One();b=Two()
        self.assertEqual(P.retain(a),(a,False))
        with P.resource_scope():
            self.assertEqual(P._CURRENT.get()[1],{})
            self.assertEqual(P.retain(a),(a,True))
            with P.resource_scope():
                self.assertEqual(P.retain(One()),(a,True))
                self.assertEqual(P.retain(b),(b,True))
            self.assertFalse(events)
        self.assertEqual(events,['two','one'])
        self.assertIsNone(P._CURRENT.get())

    def test_failure_closes_every_resource_and_preserves_body_error(self):
        events=[]
        class Bad:
            def close(self):events.append('bad');raise OSError('native failure')
        class Good:
            def close(self):events.append('good')
        with self.assertRaisesRegex(ValueError,'body'):
            with P.resource_scope():
                P.retain(Good());P.retain(Bad());raise ValueError('body')
        self.assertEqual(events,['bad','good']);self.assertIsNone(P._CURRENT.get())

    def test_copied_context_never_borrows_another_threads_com_resource(self):
        records=[]
        class Resource:
            def close(self):records.append(('closed',get_ident(),self))
        original=Resource()
        with P.resource_scope():
            P.retain(original);context=copy_context()
            def worker():
                value=Resource();self.assertEqual(P.retain(value),(value,False))
                with P.resource_scope():
                    self.assertEqual(P.retain(value),(value,True))
                    self.assertIsNot(P.retain(Resource())[0],original)
            errors=[]
            def run():
                try:context.run(worker)
                except BaseException as exc:errors.append(exc)
            thread=Thread(target=run);thread.start();thread.join(10)
            self.assertFalse(thread.is_alive());self.assertFalse(errors)
            self.assertEqual(len(records),1);self.assertIsNot(records[0][2],original)
            self.assertIs(P.retain(Resource())[0],original)
        self.assertEqual(len(records),2);self.assertIs(records[1][2],original)
        self.assertNotEqual(records[0][1],records[1][1])

    def test_partial_native_open_still_releases_all_owned_pointers_once(self):
        for module,kind,names,state in ((L,L.JapaneseIME,('_language','_common'),'_open'),
                                       (S,S.SearchCandidates,('_search','_provider','_manager'),'_active')):
            obj=kind();obj._owner=get_ident();obj._com=True;setattr(obj,state,True)
            for n,name in enumerate(names,1):setattr(obj,name,C.c_void_p(n))
            calls=[]
            def release(pointer):
                if pointer:calls.append(pointer.value)
                if pointer and pointer.value==1:raise OSError('release failure')
            with patch.object(module,'_method',side_effect=OSError('close failure')), \
                 patch.object(module,'_release',side_effect=release), \
                 patch.object(module._ole32,'CoUninitialize') as uninitialize:
                obj.close();obj.close()
                self.assertEqual(calls,list(range(1,len(names)+1)))
                uninitialize.assert_called_once_with()
            self.assertFalse(obj.available);self.assertFalse(obj._com)
            self.assertTrue(obj.error);self.assertTrue(all(not getattr(obj,n) for n in names))

    def test_foreign_close_is_rejected_before_any_release(self):
        for module,kind in ((L,L.JapaneseIME),(S,S.SearchCandidates)):
            obj=kind();obj._owner=-1;obj._com=True
            with patch.object(module,'_release') as release:
                with self.assertRaises(RuntimeError):obj.close()
                release.assert_not_called();self.assertTrue(obj._com)
            obj._owner=None;obj._com=False

    def test_engine_scope_survives_nested_entry_and_final_contract(self):
        import corrector as engine
        visited=[]
        def body(line,*args,**kwargs):visited.append(P._CURRENT.get());return {}
        wrapped=engine._with_line_result(body)
        with patch.object(engine,'_line_result_contract',side_effect=lambda *a: visited.append(P._CURRENT.get()) or {}):
            wrapped('normal')
        self.assertEqual(len(visited),2);self.assertIs(visited[0],visited[1])
        self.assertIsNotNone(visited[0]);self.assertFalse(visited[0][1]);self.assertIsNone(P._CURRENT.get())


class NativeIMESessionTests(unittest.TestCase):
    def test_same_line_shares_native_objects_but_later_line_reopens(self):
        with P.resource_scope():
            with L.JapaneseIME() as first:
                if not first.available:self.skipTest(first.error)
                # WDD flags are implementation-defined native metadata, not
                # stable grammar/segmentation. Compare the text and each
                # independently decoded range/POS; ownership stays exact.
                def stable(value):
                    self.assertIsNotNone(value)
                    return value[0],tuple(word[:5] for word in value[1])
                expected=stable(first.convert_words('しりょうをかくにんします'))
            self.assertTrue(first.available)
            with L.JapaneseIME() as second:
                self.assertIs(second,first)
                self.assertEqual(stable(second.convert_words('しりょうをかくにんします')),expected)
            with S.SearchCandidates() as search:
                if search.available:search.candidates('かくにん')
            with S.SearchCandidates() as repeated:self.assertIs(repeated,search)
        self.assertFalse(first.available);self.assertFalse(search.available)
        with P.resource_scope():
            with L.JapaneseIME() as later:
                self.assertIsNot(later,first)
                self.assertEqual(stable(later.convert_words('しりょうをかくにんします')),expected)
        self.assertFalse(later.available)


if __name__=='__main__':unittest.main()
