"""Quote calculation continuation through actual split/unified application paths."""
from pathlib import Path
import json,shutil,subprocess,sys,tempfile,time,traceback,unittest

def child():
    import tkinter as tk
    from unittest.mock import Mock,patch
    import app,analysis_work_app as work,analysis_worker
    from session import new_tab
    from tests_tk_keys import deliver_key
    assert (Path.cwd()/'.ui-test-isolated').exists()
    Path('session.json').write_text(json.dumps(dict(version=1,active=0,
        tabs=[new_tab(text=''),new_tab(text='別の資料')]),ensure_ascii=False),encoding='utf-8')
    Path('settings.json').write_text(json.dumps(dict(layout='split',input_method='kana',
        input_method_auto=False)),encoding='utf-8')
    root=tk.Tk();root.withdraw();a=None;errors=[]
    root.report_callback_exception=lambda *exc:errors.append(''.join(traceback.format_exception(*exc)))
    def until(predicate,seconds=65):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            root.update()
            assert not errors,errors
            if predicate():return
            time.sleep(.005)
        raise AssertionError(dict(status=a.status.cget('text'),error=getattr(a,'_analyze_last_error',None)))
    def done():
        return (not a._foreground_analysis_pending() and a._analyze_text==a.editor_source_text()
            and a._analyze_work==work.token(a) and a._analyze_dependencies==analysis_worker.state_key(a))
    def type_formula(w,text):
        deliver_key(w,'<Control-c>','c',67,state=4)
        if '--replace' in sys.argv:
            index=w.index('insert')
            w.replace(index,index,text)
        elif '--paste' in sys.argv:
            w.insert('insert',text)  # Native insert path; never touches the user's clipboard.
        else:
            for char in text:
                keysym='space' if char==' ' else char
                deliver_key(w,'<KeyPress>',keysym,0,char=char)
                deliver_key(w,'<KeyRelease>',keysym,0,event_type=3,char=char)
        deliver_key(w,'<KeyPress>','Return',13,char='\r')
    sequence=(('1/2','0.5'),('*4','2'),('+0.5','2.5')) if '--replace' in sys.argv else (('1-2','-1'),('+3','2'),('*4','11'))
    if '--spaced' in sys.argv:
        sequence=(('1-2','-1'),(' +3','2'),('　×4' if '--paste' in sys.argv else ' *4','11'))
    with patch.object(app.CorrectNoteApp,'_learn_now',new=lambda *args:None),patch.object(app,'GlobalHotkeys',return_value=Mock()):
        try:
            a=app.CorrectNoteApp(root);until(done)
            initial_revision=a.store.revision()
            if '--many' in sys.argv:
                a.settings.set('unified_autofix',True);a._choose_layout('unified');until(done)
                labels=('甲','乙','丙','丁');prefix='注1-2｜'
                identity='--identity' in sys.argv
                def operand(i):return ('-2','-2') if identity and i==1 else ('1-2','-1')
                def value(i,extended=False):return ('10' if extended else '1') if identity and i==1 else ('11' if extended else '2')
                a._replace_editor_text(prefix+'｜'.join(labels));until(done)
                w=a.editor;expressions=['']*4;values=['']*4
                def move(w,index):
                    start=w.search(labels[index],'1.0',stopindex='1.end');assert start
                    end=w.search('｜',start,stopindex='1.end')
                    w.mark_set('insert',end or '1.end')
                def apply(index,suffix,result):
                    move(w,index);type_formula(w,suffix);until(done)
                    expressions[index]+=suffix;values[index]=result
                    original=prefix+'｜'.join(k+v for k,v in zip(labels,expressions))
                    rendered=prefix+'｜'.join(k+v for k,v in zip(labels,values))
                    assert a.editor_source_text().rstrip('\n')==original,(index,suffix,a.editor_source_text(),original)
                    assert a.line_results[0]['corrected']==rendered,(index,suffix,a.line_results[0],rendered)
                for i in range(4):apply(i,*operand(i))
                for i in (2,0,3,1):apply(i,'+3',value(i))
                for i in (1,3,0,2):apply(i,'*4',value(i,True))
                assert len(a._input_document.calculations)==4
                a._switch_tab(1);until(done);a._switch_tab(0);until(done)
                assert a.line_results[0]['corrected']==prefix+'｜'.join(k+value(i,True) for i,k in enumerate(labels))
                with patch.object(a,'_set_window_icons_win32',side_effect=lambda win:win.withdraw()), \
                        patch.object(a,'_place_quick_window'),patch.object(a,'_focus_quick_window'):
                    a._open_quick_capture()
                q=a._quick_text;a.settings.set('quick_autofix',True)
                q.replace('1.0','end-1c',prefix+'｜'.join(labels))
                expressions=['']*4;values=['']*4
                def apply_quick(index,suffix,result):
                    move(q,index);type_formula(q,suffix)
                    expressions[index]+=suffix;values[index]=result
                    expected=prefix+'｜'.join(k+v for k,v in zip(labels,values))
                    until(lambda:a._pick_mode is None and getattr(a,'_quick_after_id',None) is None
                          and q.get('1.0','end-1c')==expected)
                    rec=a._autofix_record_for_row(1,w=q)
                    assert rec['original']==prefix+'｜'.join(k+v for k,v in zip(labels,expressions)),rec
                for i in range(4):apply_quick(i,*operand(i))
                for i in (2,0,3,1):apply_quick(i,'+3',value(i))
                for i in (1,3,0,2):apply_quick(i,'*4',value(i,True))
                print('QUOTE_CONTINUATION_APP_PASSED',flush=True)
                return
            if '--multiple' in sys.argv:
                a.settings.set('unified_autofix',True);a._choose_layout('unified');until(done)
                a._replace_editor_text('甲｜乙');until(done)
                w=a.editor;w.mark_set('insert','1.1')
                type_formula(w,'1-2');until(done)
                w.mark_set('insert','1.end');type_formula(w,'1-2');until(done)
                assert a.line_results[0]['corrected']=='甲-1｜乙-1'
                type_formula(w,'+3');until(done)
                assert a.editor_source_text().rstrip('\n')=='甲1-2｜乙1-2+3', (a.editor_source_text(),w.get('1.0','1.end'),a.line_results[0],a._input_document.calculations,a._autofix_record_for_row(1,w=w))
                assert a.line_results[0]['corrected']=='甲-1｜乙2'
                w.mark_set('insert',w.search('｜','1.0'))
                type_formula(w,'+3');until(done)
                assert a.editor_source_text().rstrip('\n')=='甲1-2+3｜乙1-2+3'
                assert a.line_results[0]['corrected']=='甲2｜乙2'
                assert len(a._input_document.calculations)==2
                with patch.object(a,'_set_window_icons_win32',side_effect=lambda win:win.withdraw()), \
                        patch.object(a,'_place_quick_window'),patch.object(a,'_focus_quick_window'):
                    a._open_quick_capture()
                q=a._quick_text;a.settings.set('quick_autofix',True)
                q.replace('1.0','end-1c','甲｜乙');q.mark_set('insert','1.1')
                def quick_result(expected):
                    until(lambda:a._pick_mode is None and getattr(a,'_quick_after_id',None) is None
                          and q.get('1.0','end-1c')==expected)
                type_formula(q,'1-2');quick_result('甲-1｜乙')
                q.mark_set('insert','1.end');type_formula(q,'1-2');quick_result('甲-1｜乙-1')
                type_formula(q,'+3');quick_result('甲-1｜乙2')
                q.mark_set('insert',q.search('｜','1.0'));type_formula(q,'+3');quick_result('甲2｜乙2')
                rec=a._autofix_record_for_row(1,w=q)
                assert rec['original']=='甲1-2+3｜乙1-2+3',rec
                print('QUOTE_CONTINUATION_APP_PASSED',flush=True)
                return
            for layout,automatic in (('split',False),('unified',False),('unified',True)):
                a.settings.set('unified_autofix',automatic);a._choose_layout(layout);until(done)
                lead='前' if '--replace' in sys.argv else '前😀'
                a._replace_editor_text(lead+'後');until(done)
                w=a.editor;w.mark_set('insert',f'1.0+{len(lead)}c');w.tag_remove('sel','1.0','end')
                expression=''
                for suffix,answer in sequence:
                    expression+=suffix;type_formula(w,suffix);until(done)
                    assert a._pick_mode is None
                    assert a.editor_source_text().rstrip('\n')==lead+expression+'後',(layout,automatic,suffix,a.editor_source_text(),w.get('1.0','end-1c'),a._input_document.calculations)
                    assert a.line_results[0]['corrected']==lead+answer+'後',(layout,automatic,suffix,a.line_results[0])
                a._switch_tab(1);until(done);a._switch_tab(0);until(done)
                assert a.line_results[0]['corrected']==lead+sequence[-1][1]+'後'
                print('EDITOR_CONTINUATION',layout,automatic,flush=True)
            with patch.object(a,'_set_window_icons_win32',side_effect=lambda win:win.withdraw()), \
                    patch.object(a,'_place_quick_window'),patch.object(a,'_focus_quick_window'):
                a._open_quick_capture()
            q=a._quick_text
            for automatic in (False,True):
                a.settings.set('quick_autofix',automatic)
                a._quick_autofix_records=[];q.replace('1.0','end-1c','前後');q.mark_set('insert','1.1')
                for suffix,answer in sequence:
                    type_formula(q,suffix)
                    until(lambda:a._pick_mode is None and getattr(a,'_quick_after_id',None) is None)
                    until(lambda:(q.get('1.0','end-1c')=='前'+answer+'後' if automatic
                          else a._quick_results[0]['corrected']=='前'+answer+'後'))
                print('QUICK_CONTINUATION',automatic,flush=True)
            print('QUOTE_CONTINUATION_APP_PASSED',flush=True)
        finally:
            if a is not None:
                try:
                    baseline_revision=initial_revision if 'initial_revision' in locals() else None
                    if baseline_revision is not None and sys.exc_info()[0] is None:
                        assert a.store.revision()==baseline_revision,'Vocabulary grew during initial-state UI check'
                        print('INITIAL_VOCABULARY_UNCHANGED',flush=True)
                finally:a._on_close()
            else:root.destroy()

class QuoteContinuationGuiTests(unittest.TestCase):
    def _run_continuation(self,paste=False,replacing=False,multiple=False,many=False,identity=False,spaced=False):
        from bundle_manifest import NAMES
        source=Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory(prefix='correctnote-quote-continuation-') as directory:
            dest=Path(directory)
            for p in source.iterdir():
                if p.is_file() and (p.suffix=='.py' or p.name in NAMES):shutil.copy2(p,dest/p.name)
            (dest/'.ui-test-isolated').touch()
            run=subprocess.run([sys.executable,'-B','-X','utf8',str(dest/Path(__file__).name),'--child']+(['--paste'] if paste else [])+(['--replace'] if replacing else [])+(['--multiple'] if multiple else [])+(['--many'] if many else [])+(['--identity'] if identity else [])+(['--spaced'] if spaced else []),
                cwd=dest,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,encoding='utf-8',timeout=240)
            self.assertEqual(run.returncode,0,run.stdout)
            self.assertIn('QUOTE_CONTINUATION_APP_PASSED',run.stdout)

    def test_original_formula_is_extended_after_a_result(self):
        self._run_continuation()
    def test_inserted_formula_suffix_keeps_the_original_expression(self):
        self._run_continuation(paste=True)
    def test_zero_width_replacement_extends_a_decimal_result(self):
        self._run_continuation(replacing=True)
    def test_four_identical_formulas_extend_in_any_order_without_touching_literal_arithmetic(self):
        self._run_continuation(paste=True,many=True)

    def test_unchanged_calculated_number_does_not_drop_other_formulas(self):
        self._run_continuation(paste=True,many=True,identity=True)

    def test_typed_leading_spaces_continue_the_original_formula(self):
        self._run_continuation(spaced=True)

    def test_inserted_leading_spaces_continue_the_original_formula(self):
        self._run_continuation(paste=True,spaced=True)

    def test_duplicate_formulas_on_one_row_keep_their_own_source(self):
        self._run_continuation(multiple=True)

if __name__=='__main__':
    if '--child' in sys.argv:child()
    else:unittest.main()
