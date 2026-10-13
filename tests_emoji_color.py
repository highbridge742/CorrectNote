# -*- coding: utf-8 -*-
"""Colour emoji laid over a tk.Text (emoji_color.py).

2026-10-13 うにさん「別のところからペーストすると絵文字は入るが、見た目に色が
付いていない。Windowsのメモ帳と同じ見た目にする」."""
import sys,unittest
import tkinter as tk
import emoji_color


class EmojiSpanTests(unittest.TestCase):
    def test_emoji_are_found_and_cjk_extension_characters_are_not(self):
        spans=lambda t:[t[a:b] for a,b in emoji_color.emoji_spans(t)]
        self.assertEqual(spans('a\U0001F600b'),['\U0001F600'])
        # 𠮷 (CJK Extension B) is outside the BMP but is a kanji, not an emoji.
        self.assertEqual(spans('\U00020BB7野家'),[])
        # Text-style unless asked for emoji presentation, as in Notepad.
        self.assertEqual(spans('\u2764'),[]);self.assertEqual(spans('\u2600'),[])
        self.assertEqual(spans('\u2764\ufe0f'),['\u2764\ufe0f'])
        self.assertEqual(spans('\u2705\u2b50'),['\u2705','\u2b50'])
        # One cluster each: skin tone, ZWJ family, flag, keycap.
        for cluster in ('\U0001F44D\U0001F3FD','\U0001F468\u200d\U0001F469\u200d\U0001F467',
                        '\U0001F1EF\U0001F1F5','1\ufe0f\u20e3'):
            self.assertEqual(spans('あ'+cluster+'い'),[cluster],cluster)


@unittest.skipUnless(sys.platform=='win32','Direct2D on Windows')
class EmojiOverlayTests(unittest.TestCase):
    def setUp(self):
        if emoji_color.renderer() is None:self.skipTest('Direct2D unavailable')
        self.root=tk.Tk();self.root.geometry('420x160+40+40')
        self.w=tk.Text(self.root,font=('Meiryo',11),padx=14,pady=12,bg='#f0f0ed')
        self.w.pack(fill='both',expand=True)
        self.overlay=emoji_color.install(self.w)
        self.root.update()
    def tearDown(self):
        self.overlay=None;self.w=None
        self.root.destroy()
    def placed(self):
        self.overlay.refresh();self.root.update()
        return [l for l in self.overlay.labels if l.winfo_ismapped()]
    def test_a_label_covers_each_emoji_at_its_glyph(self):
        self.w.insert('1.0','今日は\U0001F600です\U0001F44D。\U00020BB7')
        labels=self.placed()
        self.assertEqual(len(labels),2)
        for label,index in zip(labels,('1.3','1.6')):
            x,y,width,height=self.w.bbox(index)
            # One pixel kept free at each side for the insertion cursor.
            self.assertEqual((label.winfo_x(),label.winfo_y()),(x+1,y))
            self.assertEqual((label.winfo_width(),label.winfo_height()),(width-2,height))
        self.assertIs(emoji_color.install(self.w),self.overlay)
    def test_labels_follow_scrolling_and_deletion(self):
        self.w.insert('1.0','\n'.join('行%d \U0001F600'%i for i in range(60)))
        self.assertTrue(self.placed())
        self.w.yview_moveto(1.0);labels=self.placed()
        first=int(self.w.index('@0,0').split('.')[0])
        x,y,_,_=self.w.bbox('%d.%d'%(first+1,len('行%d '%(first+1))))
        self.assertIn((x+1,y),[(l.winfo_x(),l.winfo_y()) for l in labels])
        self.w.delete('1.0','end');self.assertEqual(self.placed(),[])
    def test_a_very_long_row_only_costs_what_is_on_screen(self):
        # tests_gui_encoded_paste pastes a 36K-character row with 1600 emoji;
        # looking at the whole row on every poll stalled the window.
        import time
        self.w.insert('1.0','長い文章 \U0001F600 '*400)
        self.root.update();self.w.see('1.1500');self.root.update()
        start=time.perf_counter();found=self.overlay.placements()
        self.assertLess(time.perf_counter()-start,0.2)
        self.assertTrue(found)
        self.assertLess(len(found),200)
        for x,y,width,h,text,bg in found:
            self.assertEqual(text,'\U0001F600')
            self.assertEqual(self.w.get('@%d,%d'%(x+width//2,y+h//2)),'\U0001F600')
    def test_background_follows_the_selection_and_the_pane(self):
        self.w.insert('1.0','\U0001F600')
        self.w.tag_configure('sel',background='#3366cc')
        # The pane has the focus (not left to the desktop's foreground window).
        self.w.focus_get=lambda:self.w
        self.assertEqual(self.overlay.placements()[0][5],'#f0f0ed')
        self.w.tag_add('sel','1.0','end')
        self.assertEqual(self.overlay.placements()[0][5],'#3366cc')
        self.w.tag_remove('sel','1.0','end');self.w.configure(bg='#25292d')
        self.assertEqual(self.overlay.placements()[0][5],'#25292d')
    def test_clicking_an_emoji_moves_the_cursor_like_the_pane(self):
        # Whatever Tk 8.6.9 does for a click at that point (its own gap
        # rounding on emoji is odd), a click on the label does the same.
        self.w.insert('1.0','あ\U0001F600い');labels=self.placed()
        label=labels[0]
        for lx in (2,label.winfo_width()-2):
            ly=label.winfo_height()//2;x=label.winfo_x()+lx;y=label.winfo_y()+ly
            self.w.mark_set('insert','1.0')
            for seq in ('<ButtonPress-1>','<ButtonRelease-1>'):
                self.w.event_generate(seq,x=x,y=y)
            self.root.update();direct=self.w.index('insert')
            self.w.mark_set('insert','1.0')
            for seq in ('<ButtonPress-1>','<ButtonRelease-1>'):
                label.event_generate(seq,x=lx,y=ly,rootx=label.winfo_rootx()+lx,
                                     rooty=label.winfo_rooty()+ly)
            self.root.update()
            self.assertEqual(self.w.index('insert'),direct,lx)
        self.assertEqual(direct!='1.0',True)

if __name__=='__main__':
    unittest.main()
