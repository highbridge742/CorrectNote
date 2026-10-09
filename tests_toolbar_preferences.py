# -*- coding: utf-8 -*-
"""Toolbar settings, the real Tk layout, and F5 replacement contracts."""
import json,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import tkinter as tk
import app,ime_watch
from settings import Settings
from toolbar_preferences import BUTTONS,IDS,normalized,bracket_order,next_bracket,ToolbarPreferences
from tests_bracket_composition import BracketCompositionTests


class ToolbarModelTests(unittest.TestCase):
    def test_old_invalid_and_new_preferences_keep_all_buttons(self):
        order,hidden=normalized(['last',[], 'unknown','last','first'],['first',{},'unknown'])
        self.assertEqual(order[:2],['last','first'])
        self.assertEqual(len(order),len(IDS));self.assertEqual(set(order),set(IDS))
        self.assertEqual(hidden,{'first'})
        self.assertEqual(normalized('last',False),(list(IDS),set()))
        self.assertEqual(normalized(['first','last'])[0][-1],'layout_unified')

    def test_saved_visibility_and_order_survive_reopen_without_changing_other_preferences(self):
        with tempfile.TemporaryDirectory() as directory:
            path=str(Path(directory)/'synthetic-settings.json')
            settings=Settings(path);settings.set('dark_mode',True)
            settings.set('toolbar_order',['last','first']);settings.set('toolbar_hidden',['bracket_single'])
            settings.save();loaded=Settings(path)
            self.assertEqual(loaded.get('toolbar_order'),['last','first'])
            self.assertEqual(loaded.get('toolbar_hidden'),['bracket_single'])
            self.assertTrue(loaded.get('dark_mode'))
            Path(path).write_text(json.dumps({'toolbar_order':'bad','toolbar_hidden':False}),encoding='utf8')
            self.assertEqual(Settings(path).get('toolbar_hidden'),[])

    def test_cycle_uses_only_visible_brackets_in_display_order(self):
        order=['bracket_black','bracket_parens','bracket_quotes']
        kinds=bracket_order(order,['bracket_single','bracket_double'])
        self.assertEqual(kinds,(3,0,4))
        self.assertEqual([next_bracket(kinds,i) for i in (None,3,0,4,1)],[3,0,4,3,3])
        self.assertIsNone(next_bracket(bracket_order(hidden=list(IDS))))


class ToolbarWidgetTests(unittest.TestCase):
    def setUp(self):
        self.root=tk.Tk();self.root.geometry('1800x500');self.errors=[]
        self.root.report_callback_exception=lambda *exc:self.errors.append(exc)
        self.a=SimpleNamespace(root=self.root,settings=Settings(),_queue_toolbar_fit=lambda:None)
        self.a._toolbar_hover_hint=lambda event,active,hint:setattr(self,'hint',hint)
        self.a._tab_viewport=tk.Frame(self.root,height=20);self.a._tab_viewport.pack(fill='x')
        self.a._toolbar=tk.Frame(self.root);self.a._toolbar.pack(fill='x')
        self.a._buttons_menu=tk.Menu(self.root,tearoff=False)
        self.editor=tk.Text(self.root,undo=True,exportselection=False);self.editor.pack(fill='both',expand=True)
        self.editor.insert('1.0','合成の選択範囲');self.editor.edit_reset();self.editor.tag_add('sel','1.0','1.3')
        self.a._bracket_buttons=[]
        for key,label,attr in BUTTONS:
            button=tk.Button(self.a._toolbar,text=label)
            button.pack(side='left',padx=2)
            if type(attr) is int:self.a._bracket_buttons.append(button)
            else:setattr(self.a,attr,button)
        self.p=ToolbarPreferences(self.a,lambda:('#eeeeee','#222222','#2277bb'))
        self.root.update()

    def tearDown(self):
        self.p.close();self.root.destroy();self.assertFalse(self.errors)

    def test_menu_visibility_and_arbitrary_order_match_actual_positions(self):
        p=self.p
        p.move('layout_unified',-99);p.move('last',-99);p.set_visible('first',False)
        self.root.update()
        visible=[key for key in p.order if key not in p.hidden]
        self.assertEqual(sorted(visible,key=lambda k:p.widgets[k].winfo_x()),visible)
        self.assertFalse(p.widgets['first'].winfo_ismapped())
        index=next(i for i in range(self.a._buttons_menu.index('end')+1) if self.a._buttons_menu.type(i)=='checkbutton' and self.a._buttons_menu.entrycget(i,'label')=='1行目')
        self.a._buttons_menu.invoke(index);self.root.update()
        self.assertTrue(p.widgets['first'].winfo_ismapped())
        self.assertTrue(p.variables['first'].get())
        self.assertEqual(self.editor.get('1.0','end-1c'),'合成の選択範囲')
        self.assertEqual(tuple(map(str,self.editor.tag_ranges('sel'))),('1.0','1.3'))
        with self.assertRaises(tk.TclError):self.editor.edit_undo()

    def test_all_hidden_toolbar_can_be_restored_and_reordered_from_dialog(self):
        p=self.p
        for key in IDS:p.set_visible(key,False)
        self.root.update();self.assertEqual(self.a._toolbar.winfo_manager(),'')
        p.open();self.root.update()
        p.refresh_list(select='bracket_black');p.toggle_selected();p.move_selected(-99)
        self.root.update()
        self.assertEqual(p.selected(),'bracket_black')
        self.assertEqual(p.order[0],'bracket_black');self.assertEqual(p.kinds(),(3,))
        self.assertEqual(self.a._toolbar.winfo_manager(),'pack')
        self.assertLess(self.a._toolbar.winfo_y(),self.editor.winfo_y())
        self.a._bracket_buttons[3].event_generate('<Enter>');self.root.update()
        self.assertTrue(self.hint.endswith('F5'))
        p.reset();self.root.update();self.assertEqual(p.order,list(IDS));self.assertFalse(p.hidden)
        p.close();self.assertIsNone(p.window)


class ToolbarBracketTests(unittest.TestCase):
    setUp=BracketCompositionTests.setUp
    tearDown=BracketCompositionTests.tearDown
    press=BracketCompositionTests.press
    text=BracketCompositionTests.text

    def test_disabled_and_reordered_f5_use_real_replacement_and_escape(self):
        self.a._toolbar_preferences=SimpleNamespace(kinds=lambda:(3,0,4))
        with patch.object(ime_watch,'composition_active',return_value=False):
            for pair in ('【】','（）','“”','【】'):
                self.press();self.assertEqual(self.text(),'前'+pair+'後')
            self.assertTrue(self.a._cancel_bracket_cycle());self.assertEqual(self.text(),'前後')
            self.a._toolbar_preferences=SimpleNamespace(kinds=lambda:())
            self.press();self.assertEqual(self.text(),'前後')
            self.assertFalse(getattr(self.a,'_bracket_cycle',None))

    def test_pending_ime_repeat_skips_hidden_without_touching_text(self):
        self.a._toolbar_preferences=SimpleNamespace(kinds=lambda:(3,0))
        pending={'widget':self.editor,'kind':3,'pair':('【','】')}
        self.a._pending_bracket_composition=pending
        self.press();self.assertEqual(pending['kind'],0)
        self.press();self.assertEqual(pending['kind'],3)
        self.a._toolbar_preferences=SimpleNamespace(kinds=lambda:())
        self.press();self.assertEqual(pending['kind'],3)
        self.assertEqual(self.text(),'前後')
        self.a._pending_bracket_composition=None


if __name__=='__main__':unittest.main()
