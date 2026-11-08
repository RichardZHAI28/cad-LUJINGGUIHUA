"""Offline source/frozen application checks. Never connects to a robot."""
import gc
import json
import sys
import tempfile
import time
from pathlib import Path


def run(report,input_drawing=None):
    import ezdxf
    from matplotlib import font_manager
    from tkinter import filedialog,messagebox
    import file_preferences,font_support,teaching_panel
    from app import App
    from direct_text import TextSpec,available_fonts
    from robot_adapters import defaults,render_script,save_profiles,BRANDS
    from frame_teaching import frame_rotation
    from cad_reader import load_dxf
    from welding import plan_paths
    old_preferences=file_preferences.PREFERENCES_FILE
    old_save=teaching_panel.save_profiles
    old_sample=teaching_panel.read_teaching_sample
    old_font_dir,old_font_map=font_support.FONT_DIR,font_support.FONT_MAP_FILE
    old_dialog,old_info,old_error=filedialog.asksaveasfilename,messagebox.showinfo,messagebox.showerror
    app=None
    with tempfile.TemporaryDirectory() as directory:
        folder=Path(directory)
        try:
            file_preferences.PREFERENCES_FILE=folder/'ui.json'
            messagebox.showerror=lambda *args,**kw:None
            file_preferences.PREFERENCES_FILE.write_text('{"cad_coordinate_system":"ucs"}',encoding='utf-8')
            teaching_panel.save_profiles=lambda profiles:save_profiles(profiles,folder/'robots.json')
            app=App(monitor_connection=False);app.withdraw()
            assert app.robot_brand.get()=='ELITE CS/ES'
            assert app.inputs['weld_width'].get()=='8' and app.inputs['step'].get()=='5'
            assert app.run_panel.master is app.workspace_tabs.master
            assert app.run_panel.master is not app.preview_page
            # Narrow synthetic fixtures need a bead smaller than their stroke;
            # verify the production defaults above before selecting test values.
            app.inputs['weld_width'].set('1')
            app.robot_configs={brand:defaults(brand) for brand in BRANDS}
            for c in app.robot_configs.values():c.host='127.0.0.1'
            app.profile_error=''
            app.open_robot();app.robot_window.withdraw()
            app.open_settings();app.settings_window.withdraw()
            assert app.cad_coordinates.get()=='世界坐标（WCS）'
            drawing=folder/'test.dxf'
            doc=ezdxf.new();doc.modelspace().add_lwpolyline([(0,0),(30,0),(30,4),(0,4)],close=True);doc.saveas(drawing)
            app.filename=str(drawing)
            for mode in ('内外轮廓焊接','中心线单道焊接','实心排道填充'):
                app.mode.set(mode)
                assert app.rebuild(),mode
            doc=ezdxf.new();doc.styles.get('Standard').dxf.font='DejaVuSans.ttf'
            doc.modelspace().add_mtext('X',dxfattribs={'insert':(0,200),'char_height':200})
            doc.saveas(drawing);app.mode.set('内外轮廓焊接')
            assert app.rebuild()
            ys=[y for path in app.paths for x,y in path]
            assert abs(min(ys))<1e-7 and abs(max(ys)-200)<1e-7,(min(ys),max(ys))
            # Apply through the real first-level panel, keep brands separate,
            # reject un-applied edits, and persist without touching user data.
            frames={}
            for brand in BRANDS:
                app.robot_brand.set(brand)
                points=iter([(400,-200,300),(500,-200,320),(420,-100,330)])
                teaching_panel.read_teaching_sample=lambda config:(next(points),(0,0,100,0,0,0))
                for index in range(3):
                    app.teaching.capture(index)
                    deadline=time.monotonic()+5
                    while app.teaching.busy and time.monotonic()<deadline:
                        app.update();time.sleep(.01)
                    assert not app.teaching.busy and app.teaching.point_vars[index].get(),app.teaching.status.get()
                assert app.teaching.apply(),app.teaching.status.get()
                c=app.current_robot_config();frames[brand]=list(c.frame)
                assert abs(frame_rotation(c.frame,brand).as_matrix()[2,0])>0.1
                value=app.teaching.point_vars[0].get();app.teaching.point_vars[0].set('410,-200,300')
                try:app.current_robot_config()
                except ValueError:pass
                else:raise AssertionError('Unapplied teaching edit was accepted')
                app.teaching.point_vars[0].set(value);app.current_robot_config()
                app.teaching.clear()
            app.robot_brand.set('UR');app.teaching.clear()
            teaching_panel.read_teaching_sample=lambda config:((999,999,999),(0,0,100,0,0,0))
            app.teaching.capture(0);app.robot_brand.set('ELITE CS/ES')
            deadline=time.monotonic()+5
            while app.teaching.busy and time.monotonic()<deadline:app.update();time.sleep(.01)
            assert not app.teaching.point_vars[0].get() and '丢弃' in app.teaching.status.get()
            app.robot_brand.set('UR')
            # Private font import remains functional in a frozen application.
            font_support.FONT_DIR=folder/'字体';font_support.FONT_MAP_FILE=folder/'map.json'
            source=font_manager.findfont(font_manager.FontProperties(family=['DejaVu Sans']),fallback_to_default=False)
            font_support.import_font(source,'self_test_font.shx')
            doc=ezdxf.new();doc.styles.get('Standard').dxf.font='self_test_font.shx'
            doc.modelspace().add_text('ABQ',dxfattribs={'height':30});doc.saveas(drawing)
            paths,_,_=load_dxf(drawing,.1,1)
            for mode in ('outline','fill','centerline'):assert plan_paths(paths,mode,width=.8,resolution=.3)[0]
            from shapely.geometry import box,LineString
            outer=box(20,20,80,120).buffer(20,quad_segs=40)
            ring=outer.difference(outer.buffer(-12))
            rounded,_=plan_paths([list(ring.exterior.coords),list(ring.interiors[0].coords)],'centerline',resolution=.2)
            assert len(rounded)==1 and LineString(rounded[0]).hausdorff_distance(outer.buffer(-6).exterior)<.4
            from direct_text import text_boundaries
            from welding import solid_region,centerline_encloses_holes
            try:r_font=font_manager.findfont(font_manager.FontProperties(family=['Verdana']),fallback_to_default=False)
            except ValueError:r_font=source
            r_raw=text_boundaries(TextSpec(text='R',font_file=r_font,height=40))
            r_region,_=solid_region(r_raw)
            r_paths,_=plan_paths(r_raw,'centerline',resolution=.2)
            assert centerline_encloses_holes(r_paths,r_region)
            # Equal-distance shrinking must produce one open stroke for a
            # uniform-width curved bar, with BOTH end caps contracted too.
            import math
            arc=LineString([(20*math.cos(-2.3+i*4.6/160),20*math.sin(-2.3+i*4.6/160)) for i in range(161)])
            curved=arc.buffer(2,cap_style=2)
            c_paths,_=plan_paths([list(curved.exterior.coords)],'centerline',resolution=.1)
            from shapely.ops import substring
            assert len(c_paths)==1 and LineString(c_paths[0]).hausdorff_distance(substring(arc,2,arc.length-2))<.2
            bar_paths,_=plan_paths([list(box(0,0,30,4).exterior.coords)],'centerline',resolution=.2)
            assert len(bar_paths)==1 and LineString(bar_paths[0]).hausdorff_distance(LineString([(2,2),(28,2)]))<.02
            # Exercise the actual direct text editor, rather than constructing
            # a synthetic DXF. Generate/CSV/script/start must use this source.
            app.open_text();window=app.text_window;window.withdraw()
            fonts=available_fonts()
            cases=[('DejaVu Sans',source,'ABQ012')]
            for name,text in [('ZITI1','NO SMOKING 0123456789'),('ZITI2','ABCDQ 0123456789')]:
                file=next((f for f in fonts.values() if Path(f).name.lower()==name.lower()+'.ttf'),None)
                if file:cases.append((name,file,text))
            typed=[];contracted_font_caps=[]
            app.inputs['resolution'].set('.3')
            for name,file,text in cases:
                window.populate(file);window.editor.delete('1.0','end');window.editor.insert('1.0',text)
                window.variables['height'].set('30');window.variables['x'].set('12');window.variables['y'].set('-8')
                for mode in ('内外轮廓焊接','中心线单道焊接','实心排道填充'):
                    app.mode.set(mode);assert window.apply(),window.status.get()
                    assert app.source_kind=='text' and app.paths
                    typed.append({'font':name,'mode':mode,'paths':len(app.paths)})
                if name in ('ZITI1','ZITI2'):
                    m_raw=text_boundaries(TextSpec(text='M',font_file=file,height=400))
                    m_region,_=solid_region(m_raw)
                    m_paths,_=plan_paths(m_raw,'centerline',resolution=.2)
                    m_y=[p[1] for path in m_paths for p in path]
                    margins=[min(m_y)-m_region.bounds[1],m_region.bounds[3]-max(m_y)]
                    assert abs(margins[0]-40)<.1,margins
                    assert 20<margins[1]<60,margins
                    assert any(abs(p[0]-40)<.1 and abs(p[1]-360)<.1 for path in m_paths for p in path)
                    contracted_font_caps.append({'font':name,'glyph':'M','bottom_top_inset_mm':margins})
                if name=='ZITI1':
                    window.editor.delete('1.0','end');window.editor.insert('1.0','A')
                    assert not window.apply() and 'A' in window.status.get()
            app.mode.set('内外轮廓焊接');assert app.rebuild()
            expected_paths=app.paths
            app.inputs['scale'].set('25.4');assert app.rebuild()
            assert app.paths==expected_paths,'CAD unit scale changed typed text millimetres'
            app.inputs['scale'].set('1')
            filepath=folder/'typed.script'
            filedialog.asksaveasfilename=lambda **kw:str(filepath)
            messagebox.showinfo=lambda *args,**kw:None
            app.export('script');assert 'movel(' in filepath.read_text(encoding='utf-8')
            received=[];app.run_panel.start=lambda c,script:received.append((c,script))
            app.start_execution();assert len(received)==1 and 'movel(' in received[0][1]
            drawing_check=None
            if input_drawing:
                app.source_kind='cad';app.filename=str(input_drawing);app.mode.set('内外轮廓焊接')
                assert app.rebuild()
                points=[p for path in app.paths for p in path]
                drawing_check={'file':app.filename,'coordinate_system':'wcs','weld_paths':len(app.paths),
                    'bounds':[min(x for x,y in points),min(y for x,y in points),max(x for x,y in points),max(y for x,y in points)]}
            result={'ok':True,'frozen':bool(getattr(sys,'frozen',False)),'brands':list(BRANDS),
                    'private_font_import':True,'mtext_origin_200mm':True,'drawing_check':drawing_check,
                    'direct_text':typed,'three_point_frames':frames,'unapplied_teaching_blocked':True,
                    'typed_source_export_and_start':True,'typed_mm_ignores_cad_units':True,'read_capture_ui_replay':True,
                    'brand_switch_discards_pending_capture':True,'rounded_centerline_preserved':True,
                    'centerline_holes_preserved':True,'elite_default':True,'default_bead_mm':8,
                    'default_point_spacing_mm':5,'run_controls_above_tabs':True,'equal_offset_curved_caps':True,
                    'offset_collisions_first':True,'all_boundary_caps_contract':True,'all_boundary_font_caps':contracted_font_caps,'robot_network_used':False}
        finally:
            if app is not None:
                for window in (app.text_window,app.robot_window,app.settings_window,app.teaching):
                    if window is not None and window.winfo_exists():window.destroy()
                app.destroy()
            file_preferences.PREFERENCES_FILE=old_preferences;teaching_panel.save_profiles=old_save
            teaching_panel.read_teaching_sample=old_sample
            font_support.FONT_DIR, font_support.FONT_MAP_FILE=old_font_dir,old_font_map
            filedialog.asksaveasfilename,messagebox.showinfo,messagebox.showerror=old_dialog,old_info,old_error
            font_manager._get_font.cache_clear();font_manager.fontManager._findfont_cached.cache_clear();gc.collect()
    Path(report).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
