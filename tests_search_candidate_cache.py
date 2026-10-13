import ctypes as C
from contextlib import contextmanager
from threading import get_ident
from unittest.mock import patch
import unittest
import ime_candidates as S


class SearchCandidateCacheTests(unittest.TestCase):
    def resource(self,retained=True):
        obj=S.SearchCandidates();obj.available=True;obj._owner=get_ident();obj._retained=retained
        obj._search=C.c_void_p(1)
        return obj

    @contextmanager
    def native(self,answers):
        records=dict(queries=[],released=[],freed=[],allocated=[],buffers=[])
        answers=iter(answers);current={}
        def allocate(value):
            buffer=C.create_unicode_buffer(value);records['buffers'].append(buffer)
            address=C.addressof(buffer);records['allocated'].append(address);return address
        def method(pointer,index,*signature):
            pointer=pointer.value if hasattr(pointer,'value') else pointer
            if pointer==1 and index==4:
                def query(search,reading,application,out):
                    current.clear();current.update(next(answers));records['queries'].append(C.wstring_at(reading))
                    if current.get('query_hr',0)<0:return current['query_hr']
                    out._obj.value=100;return current.get('query_hr',0)
                return query
            if pointer==100 and index==5:
                def count(listing,out):out._obj.value=len(current.get('values',[]));return current.get('count_hr',0)
                return count
            if pointer==100 and index==4:
                def item(listing,position,out):
                    if position in current.get('missing_items',()):return -1
                    out._obj.value=200+position;return current.get('item_hr',0)
                return item
            if pointer>=200 and index==3:
                def value(item,out):
                    position=pointer-200
                    if position in current.get('missing_values',()):return -1
                    out._obj.value=allocate(current['values'][position]);return current.get('value_hr',0)
                return value
            raise AssertionError((pointer,index))
        with patch.object(S,'_method',side_effect=method),patch.object(S._oleaut32,'SysAllocString',side_effect=allocate), \
             patch.object(S._oleaut32,'SysFreeString',side_effect=lambda p:records['freed'].append(p.value if hasattr(p,'value') else p)), \
             patch.object(S,'_release',side_effect=lambda p:records['released'].append(p.value if hasattr(p,'value') else p)):
            yield records

    def test_successful_same_reading_keeps_order_and_duplicates_once(self):
        obj=self.resource()
        with self.native([dict(values=['話します','離します','話します'])]) as native:
            expected=('話します','離します','話します')
            self.assertEqual(obj.candidates('はなします'),expected)
            self.assertEqual(obj.candidates('はなします'),expected)
            self.assertEqual(native['queries'],['はなします'])
            self.assertCountEqual(native['freed'],native['allocated'])
            obj.close();self.assertFalse(obj._candidate_cache)

    def test_empty_complete_enumeration_is_a_successful_result(self):
        obj=self.resource()
        with self.native([dict(values=[])]) as native:
            self.assertEqual(obj.candidates('よみ'),());self.assertEqual(obj.candidates('よみ'),())
            self.assertEqual(len(native['queries']),1);obj.close()

    def test_failed_query_and_count_are_retried_not_cached(self):
        for failure in (dict(query_hr=-1),dict(count_hr=-1)):
            obj=self.resource()
            with self.subTest(failure=failure),self.native([failure,dict(values=['読み'])]) as native:
                self.assertIsNone(obj.candidates('よみ'))
                self.assertEqual(obj.candidates('よみ'),('読み',))
                self.assertEqual(obj.candidates('よみ'),('読み',))
                self.assertEqual(len(native['queries']),2);obj.close()

    def test_partial_item_or_string_enumeration_is_retried(self):
        for key in ('missing_items','missing_values'):
            obj=self.resource()
            with self.subTest(key=key),self.native([dict(values=['話','離'],**{key:{1}}),dict(values=['話','離'])]) as native:
                self.assertEqual(obj.candidates('はな'),('話',))
                self.assertEqual(obj.candidates('はな'),('話','離'))
                self.assertEqual(obj.candidates('はな'),('話','離'))
                self.assertEqual(len(native['queries']),2);obj.close()

    def test_nonzero_success_status_keeps_original_result_without_cache(self):
        for key in ('query_hr','count_hr','item_hr','value_hr'):
            obj=self.resource()
            with self.subTest(key=key),self.native([dict(values=['話'],**{key:1}),dict(values=['離'])]) as native:
                self.assertEqual(obj.candidates('はな'),('話',))
                self.assertEqual(obj.candidates('はな'),('離',))
                self.assertEqual(len(native['queries']),2);obj.close()

    def test_unscoped_different_reading_and_other_resource_never_borrow_hits(self):
        obj=self.resource();other=self.resource()
        with self.native([dict(values=['一']),dict(values=['二']),dict(values=['三']),dict(values=['四'])]) as native:
            self.assertEqual(obj.candidates('よみ'),('一',))
            self.assertEqual(obj.candidates('べつ'),('二',))
            self.assertEqual(other.candidates('よみ'),('三',))
            obj._retained=False;self.assertEqual(obj.candidates('よみ'),('四',))
            self.assertEqual(len(native['queries']),4);obj.close();other.close()

    def test_foreign_owner_and_unavailable_cannot_read_cached_results(self):
        obj=self.resource()
        with self.native([dict(values=['話'])]) as native:
            self.assertEqual(obj.candidates('はな'),('話',))
            obj._owner=-1;self.assertIsNone(obj.candidates('はな'));obj._owner=get_ident()
            obj.available=False;self.assertIsNone(obj.candidates('はな'));obj.available=True
            self.assertEqual(len(native['queries']),1);obj.close()

    def test_cancellation_is_checked_before_returning_a_cached_result(self):
        import analysis_context as A
        obj=self.resource()
        with self.native([dict(values=['話'])]) as native:
            self.assertEqual(obj.candidates('はな'),('話',))
            with patch.object(A,'check_current_request',side_effect=RuntimeError('cancelled')):
                with self.assertRaisesRegex(RuntimeError,'cancelled'):obj.candidates('はな')
            self.assertEqual(len(native['queries']),1);obj.close()

    def test_owned_scope_closes_and_later_scope_does_not_reuse_results(self):
        import ime_session as P
        with self.native([dict(values=['話']),dict(values=['離'])]) as native:
            with P.resource_scope():
                obj=self.resource();shared,obj._retained=P.retain(obj)
                self.assertIs(shared,obj);self.assertEqual(obj.candidates('はな'),('話',))
                with P.resource_scope():self.assertIs(P.retain(self.resource())[0],obj)
            self.assertFalse(obj._candidate_cache);self.assertFalse(obj.available)
            with P.resource_scope():
                later=self.resource();shared,later._retained=P.retain(later)
                self.assertIs(shared,later);self.assertEqual(later.candidates('はな'),('離',))
            self.assertEqual(len(native['queries']),2)

if __name__=='__main__':unittest.main()
