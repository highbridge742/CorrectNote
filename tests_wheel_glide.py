# -*- coding: utf-8 -*-
"""Longer wheel glide keeps distance, cancellation and bounded timer work."""
import unittest
from types import SimpleNamespace
from scroll_inertia import ScrollInertia


class WheelGlideTests(unittest.TestCase):
    def setUp(self):
        self.now=0.;self.jobs={};self.next_id=0;self.maximum_jobs=0
        self.scheduled=0;self.steps=[];self.owner=object()
        def after(delay,callback):
            self.assertEqual(delay,12)
            self.next_id+=1;self.jobs[self.next_id]=(self.now+delay/1000.,callback)
            self.scheduled+=1;self.maximum_jobs=max(self.maximum_jobs,len(self.jobs))
            return self.next_id
        self.root=SimpleNamespace(after=after,after_cancel=lambda key:self.jobs.pop(key,None))
        self.controller=ScrollInertia(self.root,lambda n:self.steps.append(n),lambda:self.owner,lambda:self.now)

    def advance(self,seconds):
        end=self.now+seconds
        while self.jobs:
            key,(at,callback)=min(self.jobs.items(),key=lambda item:item[1][0])
            if at>end:break
            self.now=at;del self.jobs[key];callback()
        self.now=end

    def test_tail_remains_visible_after_quarter_second_without_extra_distance(self):
        self.controller.wheel(80);self.advance(.24)
        middle=sum(self.steps)
        self.assertTrue(0<middle<80)
        self.assertIsNotNone(self.controller.job)
        self.advance(.24)
        self.assertTrue(middle<sum(self.steps)<80)
        self.assertIsNotNone(self.controller.job)
        self.advance(.25)
        self.assertEqual(sum(self.steps),80)
        self.assertFalse(self.jobs)
        self.assertEqual(self.maximum_jobs,1)
        self.assertLessEqual(self.scheduled,60)

    def test_long_burst_keeps_one_timer_and_stops_without_idle_work(self):
        for _ in range(20):
            self.controller.wheel(100);self.advance(.012)
        self.advance(1.2)
        self.assertEqual(sum(self.steps),2000)
        self.assertEqual(self.maximum_jobs,1)
        self.assertFalse(self.jobs)
        scheduled=self.scheduled;self.advance(3)
        self.assertEqual(self.scheduled,scheduled)

    def test_both_document_ends_stop_the_extended_tail(self):
        for direction in (-1,1):
            calls=[]
            self.controller.scroll=lambda pixels:calls.append(pixels) or False
            self.controller.wheel(direction*240);self.advance(.012)
            self.assertEqual(len(calls),1)
            self.assertFalse(self.jobs)
            self.assertIsNone(self.controller.kind)
            self.advance(1)
            self.assertEqual(len(calls),1)

    def test_cancel_and_reverse_remove_the_longer_pending_direction(self):
        self.controller.wheel(80);self.advance(.24)
        self.assertIsNotNone(self.controller.job)
        stale=next(iter(self.jobs.values()))[1]
        self.controller.cancel();before=list(self.steps);stale();self.advance(1)
        self.assertEqual(self.steps,before)
        self.controller.wheel(80);self.advance(.24);count=len(self.steps)
        self.controller.wheel(-30);self.advance(.8)
        self.assertEqual(sum(self.steps[count:]),-30)
        self.assertTrue(all(n<0 for n in self.steps[count:]))
        self.assertFalse(self.jobs)

    def test_delayed_frame_finishes_once_instead_of_replaying_backlog(self):
        self.controller.wheel(80)
        key,(_,callback)=next(iter(self.jobs.items()));del self.jobs[key]
        self.now=.25;callback()
        self.assertEqual(self.steps,[80])
        self.assertFalse(self.jobs)
        self.assertEqual(self.scheduled,1)


if __name__=='__main__':unittest.main()
