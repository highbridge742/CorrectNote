import unittest,contextvars,threading
import corrector as C
from ime_session import resource_scope,retain


class SourceAlignmentResumeTests(unittest.TestCase):
    def test_resume_without_scope_never_repopulates_closed_cache(self):
        token=C._CORRECTION_PATH.set(('資料 abc\t外','資材 abc\t外'))
        try:
            with resource_scope():
                views=C._candidate_source_ranges('資料 xabc\t外',4,7)
                next(views);self.assertEqual(next(views),('資料 abc\t外',3,6))
                closed,_=retain(C._SourceRangeOpcodes())
                self.assertEqual(len(closed.opcodes),1)
            self.assertEqual(closed.opcodes,{})
            self.assertEqual(next(views),('資材 abc\t外',3,6))
            self.assertEqual(closed.opcodes,{})
            views.close()
        finally:C._CORRECTION_PATH.reset(token)

    def test_suspended_generator_on_other_thread_does_not_borrow_owner_cache(self):
        token=C._CORRECTION_PATH.set(('資料 abc\t外','資材 abc\t外'))
        try:
            with resource_scope():
                views=C._candidate_source_ranges('資料 xabc\t外',4,7)
                next(views);next(views)
                owner,_=retain(C._SourceRangeOpcodes())
                saved=dict(owner.opcodes);context=contextvars.copy_context()
                results=[];errors=[]
                def resume():
                    try:results.append(next(views))
                    except BaseException as error:errors.append(error)
                thread=threading.Thread(target=lambda:context.run(resume))
                thread.start();thread.join(5)
                self.assertFalse(thread.is_alive());self.assertEqual(errors,[])
                self.assertEqual(results,[('資材 abc\t外',3,6)])
                self.assertEqual(owner.opcodes,saved)
                views.close()
            self.assertEqual(owner.opcodes,{})
        finally:C._CORRECTION_PATH.reset(token)

if __name__=='__main__':unittest.main()
