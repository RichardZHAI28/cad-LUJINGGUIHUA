import sys
from pathlib import Path
import os
root=Path(__file__).resolve().parent.parent
source=root/'工程'
sys.path[:0]=[str(source/'.build-tools'),str(source/'.vendor'),str(source)]
import PyInstaller.__main__
PyInstaller.__main__.run([str(source/'run.py'),'--name','CadWeldPlanner','--noconfirm','--windowed','--onedir',
 '--distpath',str(root/'发布包'/'应用文件'),'--workpath',str(root/'打包工具'/'build'),'--specpath',str(root/'打包工具'),
 '--icon',str(source/'assets'/'app.ico'),'--add-data',str(source/'assets')+os.pathsep+'assets',
 '--add-data',str(source/'third_party')+os.pathsep+'third_party',
 '--paths',str(source),'--paths',str(source/'.vendor'),'--hidden-import','matplotlib.backends.backend_tkagg',
 '--collect-data','ezdxf','--collect-binaries','shapely','--exclude-module','pytest','--exclude-module','IPython',
 '--exclude-module','scikit_image','--exclude-module','skimage'])
