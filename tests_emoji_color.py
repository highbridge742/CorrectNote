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



class EmojiCursorTests(unittest.TestCase):
    """2026-10-14 うにさん「絵文字の右にカーソルを置き、左キーを1回押すと表示が
    変になり、絵文字の左側へカーソルが移動しません」: no step stops between the
    two UTF-16 halves of an emoji, and no delete removes only one of them."""
    E='\U0001F600'
    def setUp(self):
        from analysis_work import observe_text
        self.root=tk.Tk();self.root.withdraw()
        self.w=tk.Text(self.root,undo=True);self.w.pack();observe_text(self.w)
    def tearDown(self):
        self.w=None;self.root.destroy()
    def put(self,text,where):
        w=self.w;w.delete('1.0','end');w.insert('1.0',text);w.mark_set('insert',where)
    def test_left_and_right_step_over_the_whole_emoji(self):
        self.put('a'+self.E+'b','1.0 lineend -1c')
        self.w.event_generate('<<PrevChar>>')
        self.assertEqual(self.w.get('insert'),self.E)
        self.w.event_generate('<<PrevChar>>')
        self.assertEqual(self.w.get('insert'),'a')
        self.w.event_generate('<<NextChar>>');self.w.event_generate('<<NextChar>>')
        self.assertEqual(self.w.get('insert'),'b')
        self.put(self.E+self.E+'b','1.0 lineend -1c')
        self.w.event_generate('<<PrevChar>>');self.w.event_generate('<<PrevChar>>')
        self.assertTrue(self.w.compare('insert','==','1.0'))
    def test_backspace_and_delete_remove_the_whole_emoji_only(self):
        self.put('a'+self.E+'b','1.0 lineend -1c');self.w.delete('insert-1c')
        self.assertEqual(self.w.get('1.0','end-1c'),'ab')
        self.put('a'+self.E+'b','1.0 lineend -2c');self.w.delete('insert')
        self.assertEqual(self.w.get('1.0','end-1c'),'ab')
        self.put('a'+self.E+'b','1.0');self.w.delete('insert')
        self.assertEqual(self.w.get('1.0','end-1c'),self.E+'b')
        self.put('a'+self.E+'b','1.0 lineend');self.w.delete('insert-1c')
        self.assertEqual(self.w.get('1.0','end-1c'),'a'+self.E)
        self.put('a'+self.E+'b','1.0 lineend -1c');self.w.delete('insert-1c')
        self.w.edit_undo()
        self.assertEqual(self.w.get('1.0','end-1c'),'a'+self.E+'b')


class ClusterCursorTests(unittest.TestCase):
    """2026-10-15 うにさん「❤この文字が2文字の幅を使っていて、カーソル移動で
    うまく跨げません」: a character made of several code points (❤ + U+FE0F,
    a skin tone, a ZWJ family, a flag, a keycap, a combining mark, a tag
    flag) moves, selects, deletes and takes clicks as one (text_edit)."""
    CLUSTERS=('❤️','\U0001F44D\U0001F3FD',
              '\U0001F468‍\U0001F469‍\U0001F467','\U0001F1EF\U0001F1F5',
              '1️⃣','が',
              '\U0001F3F4\U000E0067\U000E0062\U000E0065\U000E006E\U000E0067\U000E007F')
    def setUp(self):
        from analysis_work import observe_text
        self.root=tk.Tk();self.root.geometry('480x120+40+40')
        self.w=tk.Text(self.root,undo=True,font=('Meiryo',12));self.w.pack(fill='both',expand=True)
        observe_text(self.w)
    def tearDown(self):
        self.w=None;self.root.destroy()
    def put(self,text,where):
        w=self.w;w.delete('1.0','end');w.insert('1.0',text)
        w.tag_remove('sel','1.0','end');w.mark_set('insert',where)
    def at(self,index='insert'):
        return len(self.w.get('1.0',index))
    def selected(self):
        return self.w.get('sel.first','sel.last') if self.w.tag_ranges('sel') else ''
    def test_cluster_bounds(self):
        from text_edit import cluster_bounds
        units=lambda s:len(s.encode('utf-16-le'))//2
        for c in self.CLUSTERS:
            self.assertEqual(cluster_bounds('a'+c+'b'),[0,1,1+units(c),2+units(c)],ascii(c))
        # Flags pair up; halfwidth ﾞ stays a letter of its own; ZWJ between kana joins nothing after it.
        self.assertEqual(cluster_bounds('\U0001F1EF\U0001F1F5\U0001F1FA\U0001F1F8'),[0,4,8])
        self.assertEqual(cluster_bounds('ｶﾞ'),[0,1,2])
        self.assertEqual(cluster_bounds('あ‍い'),[0,2,3])
        self.assertEqual(cluster_bounds(''),[0])
    def test_left_and_right_step_over_the_whole_cluster(self):
        for c in self.CLUSTERS:
            with self.subTest(c=ascii(c)):
                self.put('a'+c+'b','1.0 lineend -1c')
                self.w.event_generate('<<PrevChar>>');self.assertEqual(self.at(),1)
                self.w.event_generate('<<PrevChar>>');self.assertEqual(self.at(),0)
                self.w.event_generate('<<NextChar>>');self.assertEqual(self.at(),1)
                self.w.event_generate('<<NextChar>>');self.assertEqual(self.at(),1+len(c))
        self.put('\U0001F1EF\U0001F1F5\U0001F1FA\U0001F1F8','1.0 lineend')
        self.w.event_generate('<<PrevChar>>');self.assertEqual(self.at(),2)
    def test_shift_left_and_right_select_the_whole_cluster(self):
        for c in self.CLUSTERS:
            with self.subTest(c=ascii(c)):
                self.put('a'+c+'b','1.0 lineend -1c')
                self.w.event_generate('<<SelectPrevChar>>')
                self.assertEqual((self.selected(),self.at()),(c,1))
                self.w.event_generate('<<SelectPrevChar>>')
                self.assertEqual((self.selected(),self.at()),('a'+c,0))
                self.w.event_generate('<<SelectNextChar>>')
                self.assertEqual((self.selected(),self.at()),(c,1))
                self.put('a'+c+'b','1.1')
                self.w.event_generate('<<SelectNextChar>>')
                self.assertEqual((self.selected(),self.at()),(c,1+len(c)))
    def test_selection_ends_and_cursor_jumps_leave_the_middle(self):
        heart=self.CLUSTERS[0]
        self.put('a'+heart+'b','1.0')
        self.w.tag_add('sel','1.2','1.3');self.assertEqual(self.selected(),heart)
        self.w.tag_remove('sel','1.0','end')
        self.w.tag_add('sel','1.0','1.2');self.assertEqual(self.selected(),'a'+heart)
        # A jump into the middle goes on in its direction.
        self.w.mark_set('insert','1.2');self.assertEqual(self.at(),3)
        self.w.mark_set('insert','1.0 lineend');self.w.mark_set('insert','1.2')
        self.assertEqual(self.at(),1)
    def test_backspace_and_delete_remove_the_whole_cluster(self):
        for c in self.CLUSTERS:
            with self.subTest(c=ascii(c)):
                # Tk's own BackSpace and Delete (text.tcl).
                self.put('a'+c+'b','1.0 lineend -1c');self.w.delete('insert-1c')
                self.assertEqual(self.w.get('1.0','end-1c'),'ab')
                self.w.edit_undo();self.assertEqual(self.w.get('1.0','end-1c'),'a'+c+'b')
                self.put('a'+c+'b','1.1');self.w.delete('insert')
                self.assertEqual(self.w.get('1.0','end-1c'),'ab')
        # A program's own range is kept: only the selector goes.
        self.put('a❤️b','1.0');self.w.delete('1.2','1.3')
        self.assertEqual(self.w.get('1.0','end-1c'),'a❤b')
    def test_a_click_stops_at_the_nearer_edge_of_the_cluster(self):
        self.root.update()
        for c in self.CLUSTERS[:4]:
            with self.subTest(c=ascii(c)):
                self.put('あ'+c+'い','1.0');self.root.update()
                start=self.w.bbox('1.1');self.w.mark_set('right_edge','1.0 lineend -1c')
                end=self.w.bbox('right_edge')
                if not start or not end or start[1]!=end[1]:self.skipTest('no layout')
                x0,y,x1=start[0],start[1]+start[3]//2,end[0]
                gap=lambda x:self.at(self.w.tk.call('::tk::TextClosestGap',self.w._w,x,y))
                for x in range(x0,x1):
                    self.assertIn(gap(x),(1,1+len(c)),x)   # never inside
                self.assertEqual(gap(x0+1),1)
                self.assertEqual(gap(x1-2),1+len(c))
        # The pane's own click (one press: generated presses share time 0 and
        # would count as a double click) on the right of ❤️'s wide selector.
        self.put('あ'+self.CLUSTERS[0]+'い','1.0');self.root.update()
        x,y,w,h=self.w.bbox('1.2')
        for seq in ('<ButtonPress-1>','<ButtonRelease-1>'):
            self.w.event_generate(seq,x=x+w-2,y=y+h//2)
        self.assertEqual(self.at(),3)
    def test_panes_without_the_observer_keep_tks_procedure(self):
        top=tk.Toplevel(self.root);top.geometry('200x80+40+200')
        plain=tk.Text(top);plain.pack();plain.insert('1.0','abc');self.root.update()
        x,y,_,_=plain.bbox('1.1')
        self.assertEqual(plain.index(self.root.tk.call('::tk::TextClosestGap',plain._w,x+1,y+2)),'1.1')


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
    def settle(self):
        self.overlay.refresh()
    def placed(self):
        self.settle();self.overlay.refresh();self.root.update()
        return [l for l in self.overlay.labels if l.winfo_ismapped()]
    def test_a_label_covers_each_emoji_at_its_glyph(self):
        self.w.insert('1.0','今日は\U0001F600です\U0001F44D。\U00020BB7')
        labels=self.placed()
        self.assertEqual(len(labels),2)
        # The second emoji's column depends on how this Tk counts the first one.
        second='1.%d'%(5+emoji_color.emoji_columns(self.w))
        for label,index in zip(labels,('1.3',second)):
            x,y,width,height=self.w.bbox(index)
            # One pixel kept free at each side for the insertion cursor.
            self.assertEqual((label.winfo_x(),label.winfo_y()),(x+1,y))
            self.assertEqual((label.winfo_width(),label.winfo_height()),(width-2,height))
        self.assertIs(emoji_color.install(self.w),self.overlay)
    def test_a_label_ends_where_the_next_letter_starts(self):
        # Tk draws a skin tone with no width and answers its bbox with the
        # next letter's box; the colour must not cover that letter (nor the
        # cursor in front of it).
        for cluster in ('\U0001F44D\U0001F3FD','❤️','\U0001F1EF\U0001F1F5'):
            with self.subTest(c=ascii(cluster)):
                self.w.delete('1.0','end');self.w.insert('1.0','a'+cluster+'b')
                labels=self.placed();self.assertEqual(len(labels),1)
                self.w.mark_set('letter','1.0 lineend -1c')
                x=self.w.bbox('letter')[0]
                self.assertLessEqual(labels[0].winfo_x()+labels[0].winfo_width(),x-1)
    def test_a_selector_takes_no_room_of_its_own(self):
        # 2026-10-15 うにさん「絵文字が2つ幅でした」: ❤️ is as wide as 😀; the
        # selector is only hidden, the text keeps it.
        self.w.insert('1.0','a❤️b\na\U0001F600b\na❤︎b')
        labels=self.placed();self.assertEqual(len(labels),2)
        heart,smile=labels
        self.assertLessEqual(abs(heart.winfo_width()-smile.winfo_width()),1)
        self.assertEqual(self.w.get('1.0','end-1c'),'a❤️b\na\U0001F600b\na❤︎b')
        # A joined emoji takes one emoji's room too (👨‍👩‍👧 was three).
        self.w.insert('end','\na\U0001F468‍\U0001F469‍\U0001F467b')
        labels=self.placed();self.assertEqual(len(labels),3)
        self.assertLessEqual(abs(labels[2].winfo_width()-smile.winfo_width()),1)
        for row in (1,3):
            self.w.mark_set('letter','%d.0 lineend -1c'%row)
            # the base and the letter after it touch: no blank for the selector
            base=self.w.bbox('%d.1'%row);letter=self.w.bbox('letter')
            self.assertEqual(base[0]+base[2],letter[0],row)
    def test_the_pane_is_drawn_again_after_its_view_moves(self):
        # 2026-10-15 うにさん「スクロール時に絵文字が変です」「スクロールした瞬間
        # だけです」・選択「色を保つ」: Tk scrolls by copying pixels, labels
        # included. The label columns are marked to be drawn afresh before Tk
        # redraws, and in the overlay's own turn the labels are laid and the
        # drawing finished; the colour stays on.
        self.w.insert('1.0','\n'.join('行%d \U0001F600'%i for i in range(80)))
        self.assertTrue(self.placed())
        exposed=[]
        self.w.bind('<Expose>',lambda e:exposed.append((e.x,e.width,e.height)),add=True)
        self.overlay.refresh();self.assertEqual(exposed,[])        # nothing moved
        self.w.yview_scroll(9,'pixels')                             # the pane's own command
        self.assertTrue(exposed)                                    # marked before Tk redraws
        self.overlay._idle()                                        # the overlay's own turn
        labels=[l for l in self.overlay.labels if l.winfo_ismapped()];self.assertTrue(labels)
        x,width,height=exposed[-1];label=labels[0]
        # the label columns, the pane's whole height; labels already moved
        self.assertEqual(height,self.w.winfo_height())
        self.assertLessEqual(x,label.winfo_x());self.assertGreaterEqual(x+width,label.winfo_x()+label.winfo_width())
        want=[(p[0],p[1]) for p in self.overlay.placements()]
        self.assertEqual(sorted((l.winfo_x(),l.winfo_y()) for l in labels),sorted(want))
        count=len(exposed);self.root.after(120,self.root.quit);self.root.mainloop()
        self.assertGreater(len(exposed),count)                    # once more, a little later
        count=len(exposed);self.overlay.refresh();self.assertEqual(len(exposed),count)
        # A row above grows (fonts change while the view stays): drawn again too.
        import tkinter.font as tkfont
        big=tkfont.Font(root=self.root,font=self.w.cget('font'));big.configure(size=big.actual('size')+8)
        self.w.tag_configure('tall',font=big);self.w.tag_add('tall','@0,0 linestart','@0,0 lineend')
        count=len(exposed);self.overlay.refresh();self.assertGreater(len(exposed),count)
    def hidden(self):
        """{(row, col)} of characters carrying a glyph-hiding tag."""
        # Character by character in this Tk's row.col (emoji_columns), never
        # through the indexes tag_ranges returns (Tk 8.6.9 reads them back
        # one column off after an emoji).
        out=set();cols=emoji_color.emoji_columns(self.w)
        width_of=len if cols==1 else emoji_color._units
        last=int(self.w.index('end-1c').split('.')[0])
        for row in range(1,last+1):
            line=self.w.get('%d.0'%row,'%d.end'%row)
            for i in range(len(line)):
                names=self.w.tag_names('%d.%d'%(row,width_of(line[:i])))
                if any(str(t).startswith(emoji_color.HIDE_TAG) for t in names):out.add((row,i))
        return out
    def test_tks_own_glyph_is_drawn_in_the_background_colour(self):
        # 2026-10-15 うにさん: a row coming in at the top while scrolling showed
        # black and white emoji until its colour label was placed. Tk's glyph
        # of every emoji the colour is laid over is drawn in the colour behind
        # it; nothing else is touched and nothing moves.
        lines=['a\U0001F600b','x❤️y','\U0001F44D\U0001F3FD!','\U0001F468‍\U0001F469‍\U0001F467.',
               '\U00020BB7野❤家','普通の行']
        self.w.insert('1.0','\n'.join(lines))
        self.placed()
        want=set()
        for row,line in enumerate(lines,1):
            for a,b in emoji_color.emoji_spans(line):
                want.update((row,i) for i in range(a,b))
        self.assertEqual(self.hidden(),want)                       # 𠮷 and a text ❤ stay
        bg=self.overlay._hex(self.w.cget('bg'))
        for tag in self.w.tag_names():
            if str(tag).startswith(emoji_color.HIDE_TAG):
                self.assertEqual(self.overlay._hex(self.w.tag_cget(tag,'foreground')),bg)
        boxes=[self.w.bbox('%d.0 lineend -1c'%r) for r in range(1,7)]
        rows=[self.w.dlineinfo('%d.0'%r) for r in range(1,7)]
        self.overlay._unhide_all();self.root.update()
        self.assertEqual([self.w.bbox('%d.0 lineend -1c'%r) for r in range(1,7)],boxes)
        self.assertEqual([self.w.dlineinfo('%d.0'%r) for r in range(1,7)],rows)
    def test_rows_about_to_scroll_in_and_new_emoji_are_hidden_already(self):
        self.w.insert('1.0','\n'.join('行%d \U0001F600'%i for i in range(200)))
        self.placed()
        top=int(self.w.index('@0,0').split('.')[0]);bottom=int(self.w.index('@0,%d'%self.w.winfo_height()).split('.')[0])
        rows={row for row,_ in self.hidden()}
        span=bottom-top+1
        self.assertIn(bottom+span//2,rows)                         # half a screen below the view
        self.assertNotIn(bottom+100,rows)                          # far away: left alone
        # typed or Win+. : hidden before Tk draws it (no idle turn in between)
        self.w.insert('%d.0'%top,'\U0001F44D')
        self.assertIn((top,0),self.hidden())
    def test_no_colour_no_hiding(self):
        self.w.insert('1.0','a\U0001F600b')
        self.placed();self.assertTrue(self.hidden())
        from unittest.mock import patch
        def broken(*args,**kwargs):raise OSError('no Direct2D')
        # The renderer is shared by every pane: patch it only here.
        with patch.object(self.overlay.r,'render',broken):
            self.overlay.images.clear()
            self.w.insert('end','\U0001F604')
            with self.assertRaises(Exception):self.overlay.refresh()
            self.assertEqual(self.hidden(),set())
            self.overlay._hide_glyphs();self.assertEqual(self.hidden(),set())
    def test_the_emoji_font_follows_the_letters_size(self):
        # 2026-10-15 うにさん「右クリック2回の縮小モードで、❤️ が縮小されません」:
        # the font ❤ is drawn in follows the size around it, both ways.
        import tkinter.font as tkfont
        self.w.insert('1.0','a❤️b');self.placed()
        size=lambda:[t for t in self.w.tag_names('1.1') if str(t).startswith(emoji_color.FONT_TAG)]
        big=size();self.assertEqual(len(big),1)
        small=tkfont.Font(root=self.root,font=self.w.cget('font'));small.configure(size=5)
        self.w.configure(font=small);self.placed()
        self.assertEqual(len(size()),1);self.assertNotEqual(size(),big)
        self.assertEqual(int(self.root.tk.call('font','actual',self.w.tag_cget(size()[0],'font'),'-size')),5)
        self.w.configure(font=('Meiryo',11));self.placed()
        self.assertEqual(size(),big)
    def test_a_heart_before_bigger_letters_gets_its_colour(self):
        # 2026-10-15: in a row where the letters after ❤️ had a bigger
        # part-of-speech font, the hidden U+FE0F's empty box sat a pixel off
        # the ❤'s top; ❤️ was skipped while its glyph was hidden (a blank).
        import tkinter.font as tkfont
        self.w.insert('1.0','\U0001F60A❤️ 絵文字の行\nabc')
        big=tkfont.Font(root=self.root,font=self.w.cget('font'));big.configure(size=big.actual('size')+2)
        self.w.tag_configure('pos_big',font=big);self.w.tag_add('pos_big','1.3','1.end')
        texts=[p[4] for p in (self.placed() and self.overlay.placements())]
        self.assertIn('❤️',texts)
        self.assertEqual(self.overlay._skipped,set())
    def test_an_emoji_left_without_a_label_keeps_tks_glyph(self):
        from unittest.mock import patch
        self.w.insert('1.0','a\U0001F600b \U0001F604')
        self.placed();self.assertIn((1,1),self.hidden())
        def unplaced():
            self.overlay._skipped={(1,1)}
            return []
        with patch.object(self.overlay,'placements',unplaced):
            self.overlay.refresh()
        self.assertNotIn((1,1),self.hidden())                  # no label: the glyph shows
        self.assertIn((1,4),self.hidden())                     # the other one stays hidden
    def test_emoji_columns_match_how_this_tk_reads_row_col(self):
        # Tk 8.6.9 reads an emoji as one column, Tk 8.6.12+ (Python 3.11, CI) as two.
        n=emoji_color.emoji_columns(self.w)
        self.assertIn(n,(1,2))
        self.w.insert('1.0','a\U0001F600b')
        self.assertEqual(self.w.get('1.1'),'\U0001F600')
        self.assertEqual(self.w.get('1.%d'%(1+n)),'b')
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

@unittest.skipUnless(sys.platform=='win32','Direct2D on Windows')
class MarkedEntryEmojiTests(unittest.TestCase):
    """2026-10-15 うにさん「検索ウインドウで、色が付かず、また、ペーストすると
    空白がついて来ます」: the search field (marked_entry) colours emoji and
    shows no blank for U+FE0F; its value keeps the selector."""
    def setUp(self):
        if emoji_color.renderer() is None:self.skipTest('Direct2D unavailable')
        from marked_entry import MarkedEntry
        self.root=tk.Tk();self.root.geometry('360x60+40+40')
        self.value=tk.StringVar(self.root,'')
        self.e=MarkedEntry(self.root,textvariable=self.value,tab_colors=lambda:('#eee','#ddd'),
                           width=30,font=('Yu Gothic UI',10))
        self.e.pack(fill='x');self.root.update()
    def tearDown(self):
        self.e=None;self.root.destroy()
    def painted(self):
        self.e._paint_marks();self.root.update()
        return [l for l in self.e._emoji if l.winfo_ismapped()]
    def test_value_keeps_the_selector_and_shows_no_blank(self):
        # The value keeps every character; the field shows the emoji whose
        # colour is laid over it as blank space of the same length (Tk's own
        # black and white glyph never shows: 2026-10-15 うにさん「検索ウインドウ
        # で、色のない絵文字が見えます」), U+FE0F of the rest as zero width.
        self.value.set('a\u2764\ufe0fb\U0001F600c\U00020BB7d\u2764\ufe0e')
        self.assertEqual(self.e.get(),'a\u2764\ufe0fb\U0001F600c\U00020BB7d\u2764\ufe0e')
        shown=str(self.root.tk.call(self.e._native,'get'))
        self.assertEqual(shown,'a\u3000\u2009b\u3000\u2009c\U00020BB7d\u2764\u200b')
        self.e.selection_range(0,'end')
        self.assertEqual(self.root.tk.call('tk::EntryGetSelection',self.e._w),self.e.get())
        # typed or pasted through the field's own insert as well
        self.value.set('');self.e.insert(0,'\u2764\ufe0f\U0001F600')
        self.assertEqual(self.value.get(),'\u2764\ufe0f\U0001F600')
        self.assertEqual(str(self.root.tk.call(self.e._native,'get')),'\u3000\u2009\u3000\u2009')
    def test_without_colour_the_glyph_stays(self):
        import marked_entry
        from unittest.mock import patch
        with patch.object(marked_entry,'_EMOJI_BLANK',[False]):
            self.assertEqual(marked_entry.MarkedEntry._show('a\U0001F600\u2764\ufe0f'),'a\U0001F600\u2764\u200b')
    def test_emoji_are_coloured_over_the_field(self):
        self.value.set('検索\U0001F600と❤️')
        labels=self.painted();self.assertEqual(len(labels),2)
        for label in labels:
            self.assertGreater(label.winfo_width(),3)
        self.value.set('文字だけ');self.assertEqual(self.painted(),[])


if __name__=='__main__':
    unittest.main()
