"""Display delay owns a row generation; raw analysis never enters this class."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from pending_rows import PendingRowDisplay


class PendingRowsTests(unittest.TestCase):
    def make(self):
        self.now=0.
        self.scope=(('tab',1),2)
        self.calls={}
        self.number=0
        def after(delay,callback):
            self.number+=1
            self.calls[self.number]=(delay,callback)
            return self.number
        self.root=SimpleNamespace(after=Mock(side_effect=after),after_cancel=Mock())
        self.redraw=Mock()
        return PendingRowDisplay(self.root,self.redraw,lambda:self.scope,
                                 clock=lambda:self.now)

    def test_short_pending_is_never_published_and_completed_is_not_colored(self):
        d=self.make()
        self.assertIsNone(d.state(self.scope,1,'pending'))
        job=d.job;old=self.calls[job][1]
        self.now=.1
        self.assertEqual(d.state(self.scope,1,'done'),'done')
        self.assertIsNone(d.job)
        self.root.after_cancel.assert_called_once_with(job)
        self.now=.5;old()
        self.redraw.assert_not_called()
        self.assertFalse(d.deadlines)

    def test_persistent_pending_is_shown_without_extending_on_redraw(self):
        d=self.make()
        self.assertIsNone(d.state(self.scope,1,'pending'))
        job=d.job;deadline=d.job_deadline
        for now in (.05,.1,.15,.2,.299):
            self.now=now
            self.assertIsNone(d.state(self.scope,1,'pending'))
            self.assertEqual(d.job,job)
            self.assertEqual(d.job_deadline,deadline)
        self.root.after.assert_called_once()
        self.now=.31;self.calls[job][1]()
        self.redraw.assert_called_once()
        self.assertEqual(d.state(self.scope,1,'pending'),'pending')
        self.assertIsNone(d.job)
        self.assertEqual(d.state(self.scope,1,'done'),'done')

    def test_later_row_owns_its_own_deadline_and_one_timer_at_a_time(self):
        d=self.make();d.state(self.scope,1,'pending');first=d.job
        self.now=.1;d.state(self.scope,2,'pending')
        self.assertEqual(d.job,first)
        self.now=.31;self.calls[first][1]()
        self.assertEqual(d.state(self.scope,1,'pending'),'pending')
        self.assertIsNone(d.state(self.scope,2,'pending'))
        second=d.job;self.assertNotEqual(first,second)
        self.assertAlmostEqual(d.job_deadline,.4)
        self.now=.41;self.calls[second][1]()
        self.assertEqual(d.state(self.scope,2,'pending'),'pending')
        self.assertIsNone(d.job)

    def test_new_generation_invalidates_old_callback_and_same_row_deadline(self):
        d=self.make();d.state(self.scope,4,'pending');old=self.calls[d.job][1]
        self.now=.2;self.scope=(('tab',1),3)
        self.assertIsNone(d.state(self.scope,4,'pending'))
        job=d.job
        self.assertAlmostEqual(d.job_deadline,.5)
        self.now=.31;old()
        self.assertEqual(d.job,job)
        self.redraw.assert_not_called()
        self.assertIsNone(d.state(self.scope,4,'pending'))

    def test_tab_change_before_callback_does_not_redraw_or_color_another_owner(self):
        d=self.make();d.state(self.scope,1,'pending');old=self.calls[d.job][1]
        self.scope=(('tab',2),3);self.now=.4;old()
        self.redraw.assert_not_called()
        self.assertFalse(d.deadlines)
        self.assertIsNone(d.state(self.scope,1,'pending'))
        self.assertAlmostEqual(d.job_deadline,.7)

    def test_incomplete_is_immediate_and_close_cancels_display_only(self):
        d=self.make()
        self.assertEqual(d.state(self.scope,1,'incomplete'),'incomplete')
        self.root.after.assert_not_called()
        d.state(self.scope,2,'pending');job=d.job;old=self.calls[job][1]
        d.close()
        self.root.after_cancel.assert_called_once_with(job)
        self.now=.4;old()
        self.redraw.assert_not_called()
        self.assertIsNone(d.state(self.scope,2,'pending'))
        self.assertFalse(d.deadlines)


    def test_early_timer_crossing_deadline_during_repaint_cannot_lose_wakeup(self):
        d=self.make();shown=[]
        d.state(self.scope,1,'pending');first=d.job
        def repaint():
            shown.append(d.state(self.scope,1,'pending'))
            self.now=.301
        self.redraw.side_effect=repaint
        self.now=.299;self.calls[first][1]()
        self.assertEqual(shown,[None])
        self.assertIsNotNone(d.job,'deadline crossed during painting needs a wakeup')
        second=d.job;self.now=.32;self.calls[second][1]()
        self.assertEqual(shown,[None,'pending'])
        self.assertIsNone(d.job)

    def test_later_deadline_crossing_during_repaint_and_offscreen_rows_finish(self):
        d=self.make();shown=[]
        d.state(self.scope,1,'pending');first=d.job
        self.now=.01;d.state(self.scope,2,'pending')
        def repaint():
            shown.append((d.state(self.scope,1,'pending'),d.state(self.scope,2,'pending')))
            self.now=.32
        self.redraw.side_effect=repaint
        self.now=.301;self.calls[first][1]()
        self.assertEqual(shown,[('pending',None)])
        self.assertIsNotNone(d.job,'later row must keep a repaint')
        self.now=.33;self.calls[d.job][1]()
        self.assertEqual(shown[-1],('pending','pending'))
        self.assertIsNone(d.job)
        # A row scrolled out of view must not keep a one-millisecond loop alive.
        d=self.make();d.state(self.scope,3,'pending');job=d.job
        self.now=.31;self.calls[job][1]()
        self.assertIsNone(d.job)
        self.assertEqual(d.state(self.scope,3,'pending'),'pending')


if __name__=='__main__':unittest.main()
