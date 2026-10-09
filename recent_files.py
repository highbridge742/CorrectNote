"""Recently opened file paths only; no document text, counts or timestamps."""
import os

LIMIT=20


def normalized(paths):
    if not isinstance(paths,(tuple,list)):return []
    result=[];seen=set()
    for path in paths:
        if not isinstance(path,str) or not path or '\0' in path:continue
        try:
            path=os.path.abspath(path)
            key=os.path.normcase(path)
        except (OSError,ValueError):continue
        if key in seen:continue
        seen.add(key);result.append(path)
        if len(result)>=LIMIT:break
    return result


def remember(settings,opened):
    """Called only after the shared open operation has accepted these paths."""
    values=list(reversed(opened))+normalized(settings.get('recent_files'))
    result=normalized(values)
    if result!=settings.get('recent_files'):
        settings.set('recent_files',result);settings.save()


def clear(settings):
    settings.set('recent_files',[]);settings.save()


def populate(menu,paths,open_paths,clear_history):
    menu.delete(0,'end');paths=normalized(paths)
    if paths:
        for path in paths:
            menu.add_command(label=path,command=lambda p=path:open_paths([p]))
    else:menu.add_command(label='（履歴はありません）',state='disabled')
    menu.add_separator()
    menu.add_command(label='履歴を消去',command=clear_history,state='normal' if paths else 'disabled')
