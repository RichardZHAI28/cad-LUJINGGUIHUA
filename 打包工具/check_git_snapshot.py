"""Read-only audit of exactly the files staged for the first GitHub push."""
import json,re,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
result=subprocess.run(['git','ls-files','-z'],cwd=str(ROOT),check=True,stdout=subprocess.PIPE)
paths=[p.decode('utf-8') for p in result.stdout.split(b'\0') if p]
blocked=[];suspects=[];total=0
secret=re.compile(r'(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----|(?:password|passwd|token|api_key)\s*[:=]\s*[\"\'][^\"\']{4,}[\"\'])',re.I)
for name in paths:
    p=ROOT/name;data=p.read_bytes();total+=len(data)
    if len(data)>50*1024*1024:blocked.append(name)
    if '/.vendor/' in name and '/py_straight_skeleton/' not in name:blocked.append(name)
    if name.endswith(('.exe','.zip','.pyd','.dll','.pyc')) or p.name in ('robot_profiles.json','ui_preferences.json','font_mappings.json'):blocked.append(name)
    if p.suffix in ('.py','.md','.json','.cs','.txt'):
        text=data.decode('utf-8-sig',errors='replace')
        for i,line in enumerate(text.splitlines(),1):
            if secret.search(line):suspects.append({'file':name,'line':i})
required=['工程/welding.py','工程/.vendor/py_straight_skeleton/algorithm.py','开发交接.md','README.md','工程/third_party/py_straight_skeleton/LICENSE']
missing=[p for p in required if p not in paths]
print(json.dumps({'files':len(paths),'bytes':total,'blocked_paths':blocked,'secret_candidates':suspects,'missing_required':missing},ensure_ascii=False,indent=2))
if blocked or suspects or missing:raise SystemExit(1)
