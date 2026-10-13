import unittest
from unittest.mock import patch
from contextvars import copy_context
from threading import Thread
import ime_candidates as S
import ime_session as P
import tests_search_candidate_cache as F
from analysis_context import request_scope,SupersededAnalysis

class IndependentSearchScopeTests(unittest.TestCase):
 def test_superseded_during_listing_cleanup_does_not_publish(self):
  fixture=F.SearchCandidateCacheTests();obj=fixture.resource();cancelled=[False]
  with fixture.native([dict(values=['読み','詠み'])]) as native:
   release=S._release
   def cleanup(pointer):
    release(pointer)
    if (pointer.value if hasattr(pointer,'value') else pointer)==100:cancelled[0]=True
   try:
    with request_scope(lambda:cancelled[0],poll_interval=600),patch.object(S,'_release',side_effect=cleanup):
     with self.assertRaises(SupersededAnalysis):obj.candidates('よみ')
    self.assertEqual(obj._candidate_cache,{})
    self.assertCountEqual(native['freed'],native['allocated'])
   finally:obj.close()

 def test_nested_scope_exception_closes_native_and_all_cached_rows(self):
  fixture=F.SearchCandidateCacheTests();obj=fixture.resource()
  with fixture.native([dict(values=['読み']),dict(values=['別'])]) as native:
   with self.assertRaisesRegex(RuntimeError,'outer abort'):
    with P.resource_scope():
     shared,obj._retained=P.retain(obj);self.assertIs(shared,obj)
     self.assertEqual(obj.candidates('よみ'),('読み',))
     with P.resource_scope():
      same,retained=P.retain(S.SearchCandidates());self.assertIs(same,obj)
      self.assertEqual(same.candidates('べつ'),('別',))
      self.assertEqual(same.candidates('よみ'),('読み',))
      raise RuntimeError('outer abort')
   self.assertEqual(obj._candidate_cache,{});self.assertFalse(obj.available)
   self.assertEqual(native['queries'],['よみ','べつ'])
   self.assertCountEqual(native['freed'],native['allocated'])

 def test_superseded_failed_query_or_count_does_not_return_unavailable(self):
  fixture=F.SearchCandidateCacheTests()
  for failure,pointer,index in ((dict(query_hr=-1),1,4),(dict(count_hr=-1),100,5)):
   obj=fixture.resource();cancelled=[False]
   with self.subTest(failure=failure),fixture.native([failure]) as native:
    original=S._method
    def method(native_pointer,native_index,*signature):
     value=native_pointer.value if hasattr(native_pointer,'value') else native_pointer
     original_call=original(native_pointer,native_index,*signature)
     if (value,native_index)==(pointer,index):
      def invoke(*args):
       result=original_call(*args);cancelled[0]=True;return result
      return invoke
     return original_call
    try:
     with request_scope(lambda:cancelled[0],poll_interval=600),patch.object(S,'_method',side_effect=method):
      with self.assertRaises(SupersededAnalysis):obj.candidates('よみ')
     self.assertEqual(obj._candidate_cache,{})
     self.assertCountEqual(native['freed'],native['allocated'])
    finally:obj.close()

 def test_native_exception_retries_instead_of_publishing_partial(self):
  fixture=F.SearchCandidateCacheTests();obj=fixture.resource()
  with fixture.native([dict(values=['読み','詠み']),dict(values=['読み','詠み'])]) as native:
   original=S._method
   def method(pointer,index,*args):
    value=pointer.value if hasattr(pointer,'value') else pointer
    if value==201 and index==3:raise OSError('synthetic interrupted string')
    return original(pointer,index,*args)
   try:
    with patch.object(S,'_method',side_effect=method):
     with self.assertRaisesRegex(OSError,'synthetic'):obj.candidates('よみ')
    self.assertEqual(obj._candidate_cache,{})
    self.assertEqual(obj.candidates('よみ'),('読み','詠み'))
    self.assertEqual(native['queries'],['よみ','よみ'])
    self.assertCountEqual(native['freed'],native['allocated'])
   finally:obj.close()

 def test_copied_context_other_thread_cannot_get_cached_tuple(self):
  fixture=F.SearchCandidateCacheTests();obj=fixture.resource();result=[]
  with fixture.native([dict(values=['読み'])]) as native:
   try:
    with P.resource_scope():
     _,obj._retained=P.retain(obj)
     self.assertEqual(obj.candidates('よみ'),('読み',))
     context=copy_context();thread=Thread(target=lambda:context.run(lambda:result.append(obj.candidates('よみ'))))
     thread.start();thread.join(5);self.assertFalse(thread.is_alive())
    self.assertEqual(result,[None]);self.assertEqual(obj._candidate_cache,{})
    self.assertEqual(native['queries'],['よみ'])
   finally:obj.close()


class SearchPublicationTests(unittest.TestCase):
    def test_superseded_native_enumeration_is_not_published_and_all_resources_release(self):
        fixture=F.SearchCandidateCacheTests();obj=fixture.resource();cancelled=[False]
        with fixture.native([dict(values=['読み','詠み'])]) as native:
            original=S._method
            def method(pointer,index,*args):
                result=original(pointer,index,*args)
                value=pointer.value if hasattr(pointer,'value') else pointer
                if value>=200 and index==3:
                    def get(*a):
                        hr=result(*a);cancelled[0]=True;return hr
                    return get
                return result
            try:
                with request_scope(lambda:cancelled[0],poll_interval=600),patch.object(S,'_method',side_effect=method):
                    with self.assertRaises(SupersededAnalysis):obj.candidates('よみ')
                self.assertEqual(obj._candidate_cache,{})
                self.assertCountEqual(native['freed'],native['allocated'])
                self.assertIn(100,native['released'])
            finally:obj.close()


if __name__=='__main__':unittest.main()
