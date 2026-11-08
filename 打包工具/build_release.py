"""Build Windows x64 application and offline setup. Run from project workspace."""
from pathlib import Path
import hashlib
import shutil
import subprocess
import sys
import zipfile

root=Path(__file__).resolve().parent.parent
tools=root/'打包工具'
app=root/'发布包'/'应用文件'/'CadWeldPlanner'
csc=Path('C:/Windows/Microsoft.NET/Framework64/v4.0.30319/csc.exe')

def compile_cs(source,output,extra=()):
    subprocess.run([str(csc),'/nologo','/target:winexe','/platform:x64',
        '/reference:System.Windows.Forms.dll','/reference:System.Drawing.dll',
        '/reference:System.Core.dll','/reference:System.IO.Compression.dll',
        '/reference:System.IO.Compression.FileSystem.dll','/reference:Microsoft.CSharp.dll',
        '/win32icon:'+str(root/'工程'/'assets'/'app.ico'),
        '/out:'+output,*extra,source],cwd=str(tools),check=True)

if '--repackage' not in sys.argv:
    subprocess.run([sys.executable,str(tools/'build_app.py')],cwd=str(root),check=True)
    (app/'CadWeldPlanner.exe').replace(app/'CadWeldCore.exe')
assert (app/'CadWeldCore.exe').exists()
compile_cs('Launcher.cs','Launcher.exe')
compile_cs('Installer.cs','Uninstall.exe')
shutil.copy2(tools/'Launcher.exe',app/'CadWeldPlanner.exe')
shutil.copy2(tools/'Uninstall.exe',app/'Uninstall.exe')
shutil.copy2(root/'发布包'/'安装与迁移说明.md',app/'安装与迁移说明.md')
shutil.copy2(root/'工程'/'机器人对接说明.md',app/'机器人对接说明.md')
licenses=app/'第三方许可';licenses.mkdir(exist_ok=True)
for info in (root/'工程'/'.vendor').glob('*.dist-info'):
    for file in info.rglob('*'):
        if file.is_file() and any(t in file.name.lower() for t in ('license','copying','notice')):
            target=licenses/info.name/file.relative_to(info);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(file,target)
for file in (root/'工程'/'.build-tools'/'PyInstaller').glob('COPYING*'):
    shutil.copy2(file,licenses/('PyInstaller-'+file.name))
python_license=Path(sys.base_prefix)/'LICENSE.txt'
if python_license.exists():shutil.copy2(python_license,licenses/'Python-LICENSE.txt')
examples=app/'示例图纸';examples.mkdir(exist_ok=True)
# These bundled demonstration drawings originally used the placeholder SHX
# style "txt". Give the copies an explicit bundled TrueType font; user drawings
# and originals in CAD图纸 are never changed.
sys.path.insert(0,str(root/'工程'/'.vendor'))
import ezdxf
for name in ('demo.dxf','solid_demo.dxf'):
    doc=ezdxf.readfile(root/'CAD图纸'/name)
    for style in doc.styles:
        if style.dxf.get('font','').lower() in ('txt','txt.shx'):
            style.dxf.font='DejaVuSans.ttf'
    doc.saveas(examples/name)
with zipfile.ZipFile(tools/'payload.zip','w',zipfile.ZIP_DEFLATED,compresslevel=6) as bundle:
    for file in app.rglob('*'):
        if file.is_file():bundle.write(file,file.relative_to(app))
shutil.copy2(tools/'payload.zip',root/'发布包'/'CadWeldPlanner-Windows-x64.zip')
compile_cs('Installer.cs','Setup.exe',['/resource:payload.zip,payload.zip'])
shutil.copy2(tools/'Setup.exe',root/'发布包'/'CadWeldPlanner-Setup.exe')
lines=[]
for name in ('CadWeldPlanner-Setup.exe','CadWeldPlanner-Windows-x64.zip'):
    file=root/'发布包'/name
    lines.append(hashlib.sha256(file.read_bytes()).hexdigest()+'  '+name)
(root/'发布包'/'SHA256SUMS.txt').write_text('\n'.join(lines)+'\n',encoding='ascii')
print('Release ready:',root/'发布包')
