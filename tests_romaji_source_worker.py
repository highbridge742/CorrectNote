import unittest
from tests_analysis_async import initial,wait
from analysis_worker import Worker,snapshot
from last_choice import set_active


class SourceWorkerTests(unittest.TestCase):
    def test_fresh_worker_keeps_raw_keys_and_exact_spelling(self):
        a=initial();worker=Worker()
        try:
            state=snapshot(a)
            for source,expected in [('yubinkyokuで働きます。','yubinkyokuで働きます。'),('gakkou','学校')]:
                row=wait(worker,worker.submit(dict(kind='line',line=source,context={},input_method='romaji',attested=()),state))['result']
                state=None
                self.assertEqual(row['corrected'],expected)
                self.assertEqual(row['analysis_status'],'complete')
        finally:worker.close();set_active(None)
        self.assertFalse(worker.process.is_alive())


if __name__=='__main__':unittest.main()
