"""Recently opened paths use generated files and settings only."""
import json,os,tempfile,tkinter as tk,unittest
from pathlib import Path
from unittest.mock import Mock,patch
import app
from settings import Settings
from recent_files import LIMIT,normalized,remember,clear
import tests_gui_file_format


class RecentFilesModelTests(unittest.TestCase):
    def test_invalid_duplicate_case_paths_and_limit_without_filesystem_probe(self):
        with patch('os.stat',side_effect=AssertionError('no filesystem probe')),patch('os.path.realpath',side_effect=AssertionError('no realpath probe')):
            self.assertEqual(normalized('C:/memo.txt'),[])
            paths=normalized([None,{},'',True,'bad\0path','C:/Memo.txt','c:\\memo.txt']+
                ['C:/synthetic/%d.txt'%i for i in range(LIMIT+5)])
        self.assertEqual(paths[0],os.path.abspath('C:/Memo.txt'))
        self.assertEqual(len(paths),LIMIT)
        self.assertEqual(len(set(map(os.path.normcase,paths))),LIMIT)

    def test_latest_success_first_and_path_only_settings_roundtrip(self):
        with tempfile.TemporaryDirectory(prefix='correctnote-recent-') as folder:
            p=str(Path(folder)/'generated-settings.json');s=Settings(p);s.set('dark_mode',True)
            a,b,c=[str(Path(folder)/(name+'.txt')) for name in 'abc']
            remember(s,[a,b]);self.assertEqual(s.get('recent_files'),[b,a])
            remember(s,[c,b]);self.assertEqual(s.get('recent_files'),[b,c,a])
            loaded=Settings(p);self.assertEqual(loaded.get('recent_files'),[b,c,a]);self.assertTrue(loaded.get('dark_mode'))
            raw=json.loads(Path(p).read_text(encoding='utf8'))
            self.assertEqual(raw['recent_files'],[b,c,a]);self.assertTrue(all(type(v) is str for v in raw['recent_files']))
            raw['recent_files']=[a,None,a,'bad\0path'];Path(p).write_text(json.dumps(raw),encoding='utf8')
            self.assertEqual(Settings(p).get('recent_files'),[a])

    def test_clear_never_removes_the_file_or_other_settings(self):
        with tempfile.TemporaryDirectory(prefix='correctnote-recent-') as folder:
            path=Path(folder)/'owned-file.txt';path.write_text('合成本文',encoding='utf8')
            s=Settings(str(Path(folder)/'generated-settings.json'));s.set('dark_mode',True)
            remember(s,[str(path)]);clear(s)
            self.assertEqual(s.get('recent_files'),[]);self.assertTrue(s.get('dark_mode'))
            self.assertEqual(path.read_text(encoding='utf8'),'合成本文')
            self.assertEqual(Settings(s.path).get('recent_files'),[])


class RecentFilesOpenTests(unittest.TestCase):
    def setUp(self):
        tests_gui_file_format.FileFormatApplicationTests.setUp(self)
        self.a.settings=Settings(str(self.directory/'generated-settings.json'))
        self.a._warm_then_analyze=Mock()
        self.a._recent_files_menu=tk.Menu(self.root,tearoff=0)
    tearDown=tests_gui_file_format.FileFormatApplicationTests.tearDown
    def file(self,name,text='合成本文'):
        path=self.directory/name;path.write_text(text,encoding='utf8');return str(path)

    def test_shared_open_records_only_success_including_multiple_files(self):
        a,b=self.file('a.txt','最初の合成'),self.file('b.txt','次の合成')
        missing=str(self.directory/'missing.txt')
        with patch.object(app.messagebox,'showerror') as error:
            self.a._open_paths([a,missing,b]);error.assert_called_once()
        self.assertEqual(self.a.settings.get('recent_files'),[b,a])
        self.assertEqual(self.a.current_file,b);self.assertEqual(len(self.a.session.tabs),2)
        self.a._warm_then_analyze.assert_called_once()
        self.assertEqual(self.a.editor_source_text().rstrip('\n'),'次の合成')

    def test_open_tab_preserves_unsaved_text_without_reread(self):
        path=self.file('memo.txt');self.a._open_paths([path])
        self.a.editor.insert('1.0','未保存の編集');self.a._dirty=True
        before=self.a.editor_source_text();tabs=len(self.a.session.tabs)
        with patch.object(self.a,'_read_text_file',side_effect=AssertionError('must not reread current tab')):
            self.a._open_paths([path.upper()])
        self.assertEqual(self.a.editor_source_text(),before)
        self.assertEqual(len(self.a.session.tabs),tabs);self.assertTrue(self.a._dirty)
        self.assertEqual(self.a.settings.get('recent_files'),[os.path.abspath(path.upper())])

    def test_cancel_and_failure_do_not_add_or_reorder_history(self):
        path=self.file('memo.txt');remember(self.a.settings,[path]);before=self.a.settings.get('recent_files')[:]
        self.a.settings.save=Mock()
        with patch.object(app.filedialog,'askopenfilename',return_value=''):
            self.a.open_file()
        self.a.settings.save.assert_not_called()
        for path in (str(self.directory/'missing.txt'),str(self.directory)):
            with patch.object(app.messagebox,'showerror') as error:
                self.a._open_paths([path]);error.assert_called_once()
        self.a.settings.save.assert_not_called();self.assertEqual(self.a.settings.get('recent_files'),before)

    def test_menu_reuses_shared_open_and_missing_entry_reports_without_erasing(self):
        path=self.file('memo.txt');missing=str(self.directory/'missing.txt')
        remember(self.a.settings,[missing,path]);self.a._refresh_recent_files_menu();m=self.a._recent_files_menu
        self.assertEqual(m.entrycget(0,'label'),path);m.invoke(0)
        self.assertEqual(self.a.current_file,path)
        self.a._refresh_recent_files_menu()
        with patch.object(app.messagebox,'showerror') as error:
            m.invoke(1);error.assert_called_once()
        self.assertEqual(self.a.settings.get('recent_files'),[path,missing])
        m.invoke(m.index('end'));self.assertEqual(self.a.settings.get('recent_files'),[])
        self.assertEqual(m.entrycget(0,'state'),'disabled')
        self.assertEqual(m.entrycget(m.index('end'),'state'),'disabled')
        self.assertTrue(Path(path).exists())

if __name__=='__main__':unittest.main()
