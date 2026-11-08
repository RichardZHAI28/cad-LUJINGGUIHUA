import sys
from pathlib import Path
vendor=Path(__file__).resolve().parent/'.vendor'
if not getattr(sys,'frozen',False) and vendor.exists():sys.path.insert(0,str(vendor))
if getattr(sys,'frozen',False) and sys.platform=='win32':
    import os,ctypes
    # Tcl 8.6 distributed with Python 3.8 can misread non-ASCII library paths.
    def short_path(path):
        buffer=ctypes.create_unicode_buffer(32768)
        count=ctypes.windll.kernel32.GetShortPathNameW(str(path),buffer,len(buffer))
        return buffer.value if count else str(path)
    for variable,folder in [('TCL_LIBRARY','_tcl_data'),('TK_LIBRARY','_tk_data')]:
        os.environ[variable]=short_path(Path(sys._MEIPASS)/folder)
from runtime_paths import prepare,DATA_ROOT
prepare()

def main():
    from app import App
    if '--self-test' in sys.argv:
        from self_test import run
        report=Path(sys.argv[sys.argv.index('--report')+1]) if '--report' in sys.argv else DATA_ROOT/'self-test.json'
        drawing=sys.argv[sys.argv.index('--self-test-input')+1] if '--self-test-input' in sys.argv else None
        run(report,drawing)
    else:App().mainloop()

if __name__=='__main__':
    try:
        main()
    except Exception:
        import traceback
        if '--report' in sys.argv:
            Path(sys.argv[sys.argv.index('--report')+1]).write_text(traceback.format_exc(),encoding='utf-8')
        else:
            from tkinter import messagebox
            messagebox.showerror('启动失败',traceback.format_exc())
        raise SystemExit(1)
