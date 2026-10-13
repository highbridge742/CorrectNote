import unittest
from tests_analysis_async import initial,wait
from analysis_worker import Worker,snapshot
from last_choice import set_active


class RepairWorkerTests(unittest.TestCase):
    def test_new_source_proof_survives_worker_transport(self):
        a=initial();worker=Worker()
        try:
            state=snapshot(a)
            source='shiryouwohozinshimasu'
            row=wait(worker,worker.submit(dict(kind='line',line=source,context={},input_method='romaji',attested=()),state))['result']
            self.assertEqual(row['corrected'],'資料を保存します')
            self.assertEqual(row['analysis_status'],'complete')
            self.assertEqual(row['diagnosis']['language_state'],'anomaly_repaired')
            self.assertEqual(row['odd_spans'],[])
        finally:worker.close();set_active(None)
        self.assertFalse(worker.process.is_alive())


if __name__=='__main__':unittest.main()
