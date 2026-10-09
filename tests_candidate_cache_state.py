import gc,unittest,weakref
from unittest.mock import patch
import vocabulary as V

class CandidateCacheTests(unittest.TestCase):
 def setUp(self):V._FLEX_CACHE.clear();V._SIM_CACHE.clear()
 def tearDown(self):V._FLEX_CACHE.clear();V._SIM_CACHE.clear()
 def store(self,reading,surface,solid=True):
  store=V.VocabularyStore();store.add(reading,surface,solid=solid);return store
 def flex(self,store):return V.find_known_readings_flex('かた',store,max_edits=0)
 def similar(self,store):return V.find_similar_readings('かた',store,max_cost=5,min_count=2)
 def test_flex_different_stores_same_size_and_revision(self):
  a=self.store('かた','型');b=self.store('から','殻')
  self.assertEqual(a.revision(),b.revision());self.assertTrue(self.flex(a))
  self.assertEqual(self.flex(b),V._find_known_readings_flex_uncached('かた',b,max_edits=0))
 def test_flex_replace_reading_with_same_size(self):
  a=self.store('かた','型');self.assertTrue(self.flex(a))
  a.remove('かた','型');a.add('から','殻',solid=True)
  self.assertEqual(self.flex(a),[])
 def test_similar_different_stores_same_size_and_revision(self):
  a=self.store('から','殻');b=self.store('かな','仮名')
  self.assertTrue(self.similar(a));actual=self.similar(b)
  V._SIM_CACHE.clear();expected=self.similar(b)
  self.assertTrue(expected);self.assertEqual(actual,expected)
 def test_similar_replace_reading_with_same_size(self):
  a=self.store('から','殻');self.assertTrue(self.similar(a))
  a.remove('から','殻');a.add('かな','仮名',solid=True);actual=self.similar(a)
  V._SIM_CACHE.clear();expected=self.similar(a)
  self.assertTrue(expected);self.assertEqual(actual,expected)
 def test_similar_same_reading_becomes_solid(self):
  a=self.store('から','殻',solid=False);self.assertEqual(self.similar(a),[])
  a.add('から','殻',solid=True);actual=self.similar(a)
  V._SIM_CACHE.clear();expected=self.similar(a)
  self.assertTrue(expected);self.assertEqual(actual,expected)

class CandidateCacheLifetimeTests(unittest.TestCase):
 setUp=CandidateCacheTests.setUp
 tearDown=CandidateCacheTests.tearDown
 store=CandidateCacheTests.store
 flex=CandidateCacheTests.flex
 similar=CandidateCacheTests.similar
 def test_unchanged_model_reuses_completed_results(self):
  a=self.store('かた','型');a.add('から','殻',solid=True)
  with patch.object(V,'_find_known_readings_flex_uncached',wraps=V._find_known_readings_flex_uncached) as search:
   expected=self.flex(a);self.assertEqual(self.flex(a),expected);search.assert_called_once()
  with patch.object(V,'_trie_costs',wraps=V._trie_costs) as search:
   expected=self.similar(a);self.assertEqual(self.similar(a),expected);search.assert_called_once()
 def test_no_revision_adapter_uses_current_data_without_shared_cache(self):
  class Adapter:
   __slots__=('store',)
   def __init__(self,store):self.store=store
   def all_readings(self):return self.store.all_readings()
   def reading_trie(self):return self.store.reading_trie()
   def lookup(self,reading):return self.store.lookup(reading)
  a=Adapter(self.store('かた','型'));self.assertTrue(self.flex(a))
  a.store=self.store('から','殻');self.assertEqual(self.flex(a),[]);self.assertTrue(self.similar(a))
  a.store=self.store('かな','仮名');self.assertEqual(self.similar(a)[0][0],'かな')
  self.assertEqual(V._FLEX_CACHE,{});self.assertEqual(V._SIM_CACHE,{})
 def test_old_results_do_not_keep_retired_store_alive(self):
  a=self.store('かた','型');a.add('から','殻',solid=True)
  self.flex(a);self.similar(a);ref=weakref.ref(a);del a;gc.collect()
  self.assertIsNone(ref());self.assertTrue(V._FLEX_CACHE);self.assertTrue(V._SIM_CACHE)
 def test_cache_limits_still_bound_retired_model_entries(self):
  with patch.object(V,'_FLEX_CACHE_LIMIT',2),patch.object(V,'_SIM_CACHE_LIMIT',2):
   for _ in range(5):
    a=self.store('かた','型');a.add('から','殻',solid=True);self.flex(a);self.similar(a)
    self.assertLessEqual(len(V._FLEX_CACHE),2);self.assertLessEqual(len(V._SIM_CACHE),2)
 def test_synthetic_reload_same_reading_count_invalidates(self):
  import json,tempfile
  from pathlib import Path
  a=self.store('かた','型');self.assertTrue(self.flex(a))
  with tempfile.TemporaryDirectory(prefix='cache-state-',dir=Path.cwd()) as folder:
   p=Path(folder)/'fixture.json';p.write_text(json.dumps([dict(reading='から',surface='殻',solid=True)],ensure_ascii=False),encoding='utf8')
   a.load(str(p));self.assertEqual(self.flex(a),[]);self.assertTrue(self.similar(a))
   p.write_text(json.dumps([dict(reading='かな',surface='仮名',solid=True)],ensure_ascii=False),encoding='utf8')
   a.load(str(p));self.assertEqual(self.similar(a)[0][0],'かな')

if __name__=='__main__':unittest.main()
