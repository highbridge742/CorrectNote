# -*- coding: utf-8 -*-
import ctypes,os,threading,time,unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch
import quick_selection as Q
from selection_windows import Source,Unavailable,grid_text,MAX_TEXT
from selection_excel import selected_cells,Variant


class Object:
    def __init__(self,**values):self.values=values
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def get(self,name,*args):
        value=self.values[name]
        return value(*args) if callable(value) else value


class SelectionDataTests(unittest.TestCase):
    def test_cells_use_tabs_rows_use_newlines_and_keep_empty_or_formatted_values(self):
        self.assertEqual(grid_text([(5,4,'終'),(4,3,'001'),(4,4,''),(5,3,'￥1,200')]),'001\t\n￥1,200\t終')
        self.assertEqual(grid_text([(2,3,'甲'),(2,5,'乙')]),'甲\t\t乙')
        self.assertIsNone(grid_text([(0,0,'a'),(0,0,'b')]))
        self.assertIsNone(grid_text([(0,0,'a'),(10000,10000,'b')]))
        self.assertIsNone(grid_text([(0,0,'a'*(MAX_TEXT+1))]))

    def test_excel_reads_only_selected_cells_text_and_preserves_grid_coordinates(self):
        reads=[]
        def area(row,col,values):
            def cell(y,x):
                reads.append((row+y-1,col+x-1));return Object(Text=values[y-1][x-1])
            return Object(Row=row,Column=col,Rows=Object(Count=len(values)),Columns=Object(Count=len(values[0])),Cells=Object(Item=cell))
        areas=[area(7,4,[['甲',''],['2026/10/09','￥1,200']]),area(7,7,[['外']])]
        selection=Object(Areas=Object(Count=2,Item=lambda n:areas[n-1]))
        self.assertEqual(selected_cells(selection,lambda:None),'甲\t\t\t外\n2026/10/09\t￥1,200\t\t')
        self.assertEqual(reads,[(7,4),(7,5),(8,4),(8,5),(7,7)])
        self.assertEqual(ctypes.sizeof(Variant),24 if ctypes.sizeof(ctypes.c_void_p)==8 else 16)

    def test_excel_unavailable_or_expired_range_never_returns_partial_cells(self):
        selection=Object(Areas=Object(Count=1,Item=lambda n:Object(Row=1,Column=1,Rows=Object(Count=20000),Columns=Object(Count=2))))
        with self.assertRaises(Unavailable):selected_cells(selection,lambda:None)
        with self.assertRaises(Unavailable):selected_cells(selection,lambda:(_ for _ in ()).throw(Unavailable()))

    def test_local_selection_requires_own_process_and_active_text_pane(self):
        pane=Mock();pane.tag_ranges.return_value=('1.1','2.2');pane.get.return_value='字😀\t次\n行'
        other=Mock();app=SimpleNamespace(root=SimpleNamespace(focus_get=lambda:pane),editor=pane,result_view=other)
        own=Source(1,2,os.getpid(),3)
        self.assertEqual(Q.local_selection(app,own),'字😀\t次\n行')
        self.assertIsNone(Q.local_selection(app,Source(1,2,os.getpid()+1000,3)))
        app.root.focus_get=lambda:Mock();self.assertIsNone(Q.local_selection(app,own))
        app.root.focus_get=lambda:pane;pane.tag_ranges.return_value=();self.assertIsNone(Q.local_selection(app,own))


class SelectionOpeningTests(unittest.TestCase):
    def setUp(self):
        self.jobs={};self.id=0;self.now=0.;self.source=Source(100,101,os.getpid()+1000,102)
        def after(delay,callback):
            self.id+=1;self.jobs[self.id]=callback;return self.id
        root=SimpleNamespace(after=after,after_cancel=lambda job:self.jobs.pop(job,None))
        self.app=SimpleNamespace(root=root,_show_quick_capture=Mock())
        self.mode=patch('quick_ime.foreground_fullwidth_mode',return_value=8);self.mode.start()
        self.controllers=[];self.unblock=[]
    def tearDown(self):
        for controller in self.controllers:controller.close()
        for event in self.unblock:event.set()
        self.mode.stop()
    def controller(self,reader):
        result=Q.SelectionOpening(self.app,reader=reader,snapshot=lambda:self.source,clock=lambda:self.now)
        self.controllers.append(result);return result
    def poll(self):
        key=next(iter(self.jobs));callback=self.jobs.pop(key);callback()
    def wait(self,condition):
        deadline=time.monotonic()+1
        while not condition():
            self.assertLess(time.monotonic(),deadline);time.sleep(.001)

    def test_completed_external_text_is_read_before_opening_and_mode_is_preserved(self):
        def reader(source,deadline,cancelled):
            self.app._show_quick_capture.assert_not_called();return '甲\t乙\n丙'
        controller=self.controller(reader);controller.open('minus')
        self.wait(lambda:not controller.lock.locked());self.poll()
        self.app._show_quick_capture.assert_called_once_with('minus',8,'甲\t乙\n丙')
        self.assertFalse(self.jobs)

    def test_late_result_timeout_and_source_change_do_not_overwrite_or_steal_focus(self):
        started=threading.Event()
        def reader(source,deadline,cancelled):
            started.set();cancelled.wait(1);return '遅れた選択'
        controller=self.controller(reader);controller.open('insert');self.assertTrue(started.wait(1))
        self.now=1.;self.poll()
        self.app._show_quick_capture.assert_called_once_with('insert',8,None)
        self.wait(lambda:not controller.lock.locked());self.assertFalse(self.jobs)
        self.app._show_quick_capture.reset_mock();self.now=2.;started.clear();controller.open('insert')
        self.assertTrue(started.wait(1));self.source=Source(200,201,self.source.process,202);self.poll()
        self.app._show_quick_capture.assert_not_called();self.assertFalse(self.jobs)

    def test_visible_window_minimizes_without_reading_source_or_selection(self):
        self.app._quick_win=SimpleNamespace(winfo_exists=lambda:True,state=lambda:'normal')
        controller=self.controller(Mock());controller.open('insert')
        controller.reader.assert_not_called();self.app._show_quick_capture.assert_called_once_with('insert',None,None)

    def test_menu_internal_entry_never_reads_a_different_application(self):
        reader=Mock();controller=self.controller(reader);controller.open()
        reader.assert_not_called();self.app._show_quick_capture.assert_called_once_with(None,8,None)

    def test_close_cancels_pending_request_and_provider_cannot_reopen_window(self):
        entered=threading.Event()
        def reader(source,deadline,cancelled):entered.set();cancelled.wait(1);return '旧'
        controller=self.controller(reader);controller.open('minus');self.assertTrue(entered.wait(1));controller.close()
        self.wait(lambda:not controller.lock.locked());self.assertFalse(self.jobs)
        self.app._show_quick_capture.assert_not_called()

    def test_busy_provider_does_not_accumulate_threads(self):
        entered=threading.Event();release=threading.Event();self.unblock.append(release);calls=[]
        def reader(*args):calls.append(args);entered.set();release.wait(1);return '旧'
        controller=self.controller(reader);controller.open('minus');self.assertTrue(entered.wait(1))
        controller.open('insert');self.assertEqual(len(calls),1)
        self.app._show_quick_capture.assert_called_once_with('insert',8,None)
        release.set();self.wait(lambda:not controller.lock.locked());self.assertFalse(self.jobs)


if __name__=='__main__':unittest.main()
