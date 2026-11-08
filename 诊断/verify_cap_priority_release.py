"""Integrity audit for the equal-distance centerline release."""
import hashlib,json,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
OUT=ROOT/'诊断'/'端面收缩优先';release=ROOT/'发布包'
def read(name):return json.loads((OUT/name).read_text(encoding='utf-8'))
def sha(file):return hashlib.sha256(file.read_bytes()).hexdigest()
report=read('installer-self-test.json')
for key in ('ok','frozen','offset_collisions_first','all_boundary_caps_contract','rounded_centerline_preserved','centerline_holes_preserved','elite_default','run_controls_above_tabs'):assert report[key],key
assert not report['robot_network_used']
assert report['default_bead_mm']==8 and report['default_point_spacing_mm']==5
assert {item['font'] for item in report['all_boundary_font_caps']}=={'ZITI1','ZITI2'}
assert all(abs(item['bottom_top_inset_mm'][0]-40)<.1 for item in report['all_boundary_font_caps'])
upper=read('after-font-audit.json');lower=read('after-lowercase-audit.json')
assert len(upper)==342 and all(row['ok'] for row in upper)
assert len(lower)==208 and sum(row['ok'] for row in lower)==192
assert all(row['ok'] or row.get('policy_rejected') for row in lower)
valid=[row for row in upper+lower if row['ok']]
assert max(row['repeated_length_mm'] for row in valid)<1e-6
app=release/'应用文件'/'CadWeldPlanner'
extracted=ROOT/'打包工具'/'install-smoke-20261108-cap-priority'
with zipfile.ZipFile(release/'CadWeldPlanner-Windows-x64.zip') as archive:
    for name in ('CadWeldCore.exe','CadWeldPlanner.exe'):
        assert (app/name).read_bytes()==archive.read(name)==(extracted/name).read_bytes()
    assert archive.read('_internal/assets/app.ico')==(ROOT/'工程'/'assets'/'app.ico').read_bytes()
    assert archive.read('_internal/third_party/py_straight_skeleton/LICENSE')==(ROOT/'工程'/'third_party'/'py_straight_skeleton'/'LICENSE').read_bytes()
    assert not any('robot_profiles.json' in n or 'ziti1' in n.lower() or 'ziti2' in n.lower() for n in archive.namelist())
hashes={}
for line in (release/'SHA256SUMS.txt').read_text().splitlines():
    expected,name=line.split('  ',1);assert sha(release/name)==expected;hashes[name]=expected
assert sha(ROOT/'工程'/'robot_profiles.json')=='22eb9ff7f8af00226058fc0153b4fd1d0aa637d310104c541e93fa18ef31b715'
assert sha(Path('C:/Users/Administrator/Desktop/空心实心数字字母模板字1118.dxf'))=='bf597920395435ae3089401072ae1e53123c8672af668db2ab636b4a1b4936ae'
result={'ok':True,'frozen_self_test':True,'release_and_extracted_core_match':True,'icon06_preserved':True,
        'font_valid_cases':len(valid),'font_policy_rejected':16,'max_repeated_length_mm':max(r['repeated_length_mm'] for r in valid),
        'user_drawing_and_profiles_unchanged':True,'robot_network_used':False,'timing':read('timing.json'),'sha256':hashes}
(OUT/'release-verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in result.items() if k!='timing'},indent=2))



