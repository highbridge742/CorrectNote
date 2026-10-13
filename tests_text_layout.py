# -*- coding: utf-8 -*-
import tkinter as tk
import unittest
from text_layout import align_rows,strip_inserted_rows,_PREFIX


class PairedRowTests(unittest.TestCase):
    def setUp(self):
        self.root=tk.Tk();self.root.geometry('600x400+0+0')
        self.left=tk.Text(self.root,width=30,height=20,wrap='char',spacing1=2,spacing3=4)
        self.right=tk.Text(self.root,width=30,height=20,wrap='char',spacing1=2,spacing3=4)
        self.left.pack(side='left');self.right.pack(side='left')
        long='長い行です。'*12
        self.left.insert('1.0','一\n'+'短い\n'+'三\n四\n五')
        self.right.insert('1.0','一\n'+long+'\n三\n四\n五')
        self.root.update()
    def tearDown(self):
        self.root.destroy()
    def padding(self,w,row):
        tags=[t for t in w.tag_names(f'{row}.0') if t.startswith(_PREFIX)]
        return int(tags[-1][len(_PREFIX):]) if tags else 0
    def test_rows_pair_by_number_by_default(self):
        align_rows(self.left,self.right);self.root.update()
        self.assertGreater(self.padding(self.left,2),0)
        self.assertEqual(self.left.dlineinfo('3.0')[1],self.right.dlineinfo('3.0')[1])
    def test_enter_does_not_pad_new_rows_and_lagging_rows_are_not_paired(self):
        align_rows(self.left,self.right);self.root.update()
        start=self.left.index('2.1');self.left.insert('2.1','\n')
        strip_inserted_rows(self.left,start,'\n')
        self.assertEqual(self.padding(self.left,3),0)
        # The correction pane still shows the old rows: row 2 and 3 of the
        # memo have no partner, the rows after follow their own text.
        sources=['一','短い','三','四','五']
        lines=self.left.get('1.0','end-1c').split('\n')
        def partner(row):
            if row<=1:return row
            if row>len(lines)-3:return row+len(sources)-len(lines)
            return None
        align_rows(self.left,self.right,partners=partner);self.root.update()
        self.assertEqual(self.padding(self.left,2),0)
        self.assertEqual(self.padding(self.left,3),0)
        self.assertEqual(self.padding(self.right,2),0)
        self.assertEqual(self.left.dlineinfo('5.0')[1]-self.left.dlineinfo('4.0')[1],
                         self.right.dlineinfo('4.0')[1]-self.right.dlineinfo('3.0')[1])



class SizedTabStopTests(unittest.TestCase):
    """Tab stops leave a full-width gap after words drawn larger (POS size)."""
    def setUp(self):
        self.root=tk.Tk()
        self.w=tk.Text(self.root,font=('TkDefaultFont',10));self.w.pack()
    def tearDown(self):
        self.root.destroy()
    def test_stop_is_measured_with_the_sized_font(self):
        import tkinter.font as tkfont
        import app
        from pos_font import POS_FONT_TAGS
        a=app.CorrectNoteApp.__new__(app.CorrectNoteApp)
        line='資料資料資料資料資料\tx'
        self.w.insert('1.0',line)
        tag=POS_FONT_TAGS['名詞']
        self.w.tag_configure(tag,font=('TkDefaultFont',24))
        self.w.tag_add(tag,'1.0','1.10')
        big=tkfont.Font(font=('TkDefaultFont',24)).measure(line[:10])
        zk=tkfont.Font(font=self.w.cget('font')).measure('　')
        stops=a._line_tab_stops(self.w,line,1)
        self.assertGreaterEqual(stops[0],big+zk)
        # Without the row the old measure (pane font) is kept.
        plain=a._line_tab_stops(self.w,line)
        self.assertLess(plain[0],big)


if __name__=='__main__':
    unittest.main()
