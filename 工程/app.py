import csv
from pathlib import Path
import math
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from ui_theme import apply_theme, fit_window, ScrollPane, BG, INK
from runtime_paths import OUTPUT_DIR
from file_preferences import import_directory, remember_import_directory
from cad_reader import load_dxf,CadFontError
from cad_coordinates import CAD_COORDINATES
from geometry import discretize, transform
from robot_adapters import BRANDS, DEFAULT_BRAND, defaults, load_profiles, render_script
from robot_window import RobotWindow
from settings_window import SettingsWindow,FIELDS
from run_panel import RunPanel
from weld_sequence import order_weld_paths
from welding import MODES, FILL_MODES, plan_paths
from direct_text import text_boundaries
from text_window import TextWindow
from teaching_panel import TeachingPanel


class App(tk.Tk):
    def __init__(self,monitor_connection=True):
        super().__init__()
        self.monitor_connection=monitor_connection
        self.title('CAD → ELITE / UR 机器人焊接轨迹')
        icon_dir=Path(__file__).resolve().parent/'assets'
        if sys.platform=='win32':
            self.iconbitmap(default=str(icon_dir/'app.ico'))
        else:
            self.app_icon=tk.PhotoImage(file=str(icon_dir/'app.png'))
            self.iconphoto(True,self.app_icon)
        fit_window(self,1380,900)
        self.ui_font = apply_theme(self)
        self.filename = None
        self.source_kind = 'cad'
        self.text_spec = None
        self.text_window = None
        self.paths = []
        self.inputs = {key:tk.StringVar(value=default) for _,key,_,default in FIELDS}
        self.cad_coordinates = tk.StringVar(value='世界坐标（WCS）')
        self.mode=tk.StringVar(value='内外轮廓焊接')
        self.fill_direction=tk.StringVar(value='从上向下')
        self.continuous=tk.BooleanVar(value=False)
        self.settings_window=None
        self.robot_brand = tk.StringVar(value=DEFAULT_BRAND)
        self.robot_window = None
        self.profile_error = ''
        try:
            self.robot_configs = load_profiles()
        except Exception as exc:
            self.robot_configs = {brand: defaults(brand) for brand in BRANDS}
            self.profile_error = '机器人配置未加载：'+str(exc)
        header=tk.Frame(self,bg='#142b49',padx=24,pady=16)
        header.pack(fill='x')
        heading=tk.Label(header,text='焊接轨迹工作台',font=(self.ui_font,20,'bold'),bg='#142b49',fg='white')
        heading.grid(row=0,column=0,sticky='w');header.columnconfigure(0,weight=1)
        source_buttons=tk.Frame(header,bg='#142b49');source_buttons.grid(row=0,column=1,sticky='e')
        self.import_button=ttk.Button(source_buttons,text='导入 DXF 图纸',style='Primary.TButton',command=self.open)
        self.import_button.pack(side='right')
        self.text_button=ttk.Button(source_buttons,text='输入文字 / 数字',command=self.open_text)
        self.text_button.pack(side='right',padx=8)
        def wrap_header(event):
            narrow=heading.winfo_reqwidth()+source_buttons.winfo_reqwidth()+48>header.winfo_width()
            heading.grid_configure(columnspan=2 if narrow else 1)
            source_buttons.grid_configure(row=1 if narrow else 0,column=0 if narrow else 1,columnspan=2 if narrow else 1,sticky='e',pady=(8,0) if narrow else 0)
        header.bind('<Configure>',wrap_header)
        body=ttk.Frame(self,padding=16);body.pack(fill='both',expand=True)
        sidebar=ttk.Frame(body,width=380);sidebar.pack(side='left',fill='y',padx=(0,16));sidebar.pack_propagate(False)
        self.bind('<Configure>',lambda e:sidebar.configure(width=min(max(340,int(self.winfo_width()*.32)),500)) if e.widget is self else None,add='+')
        self.file_display=tk.StringVar(value='尚未导入图纸 · 请选择 DXF 文件')
        ttk.Label(sidebar,textvariable=self.file_display,style='Muted.TLabel',anchor='w').pack(fill='x',pady=(0,8))
        quick=ScrollPane(sidebar,padding=8);quick.pack(fill='both',expand=True)
        process=quick.content
        ttk.Label(process,text='加工模式').pack(anchor='w')
        ttk.Combobox(process,textvariable=self.mode,values=list(MODES),state='readonly').pack(fill='x',pady=(5,8))
        for key,label in [('speed','焊接速度 mm/s'),('weld_width','焊缝宽度 mm'),('text_scale','整体字号倍率')]:
            ttk.Label(process,text=label).pack(anchor='w',pady=(6,0))
            ttk.Entry(process,textvariable=self.inputs[key]).pack(fill='x',pady=(3,6))
        ttk.Label(process,text='目标机器人').pack(anchor='w',pady=(8,0))
        self.brand_selector=ttk.Combobox(process,textvariable=self.robot_brand,values=list(BRANDS),state='readonly')
        self.brand_selector.pack(fill='x',pady=(3,10))
        ttk.Button(process,text='生成轨迹',style='Primary.TButton',command=self.rebuild).pack(fill='x',pady=5)
        ttk.Button(process,text='参数设置…',command=self.open_settings).pack(fill='x',pady=5)
        ttk.Button(process,text='机器人设置…',command=self.open_robot).pack(fill='x',pady=5)
        export_menu=ttk.Menubutton(process,text='导出…')
        menu=tk.Menu(export_menu,tearoff=False)
        menu.add_command(label='轨迹 CSV',command=lambda:self.export('csv'))
        menu.add_command(label='机器人脚本',command=lambda:self.export('script'))
        export_menu.configure(menu=menu);export_menu.pack(fill='x',pady=5)
        main=ttk.Frame(body);main.pack(side='left',fill='both',expand=True)
        toolbar=ttk.Frame(main);toolbar.pack(fill='x',pady=(0,10))
        ttk.Label(toolbar,text='轨迹预览',style='Title.TLabel').pack(side='left')
        self.stats=tk.StringVar(value='等待生成轨迹')
        ttk.Label(toolbar,textvariable=self.stats,style='Muted.TLabel').pack(side='right')
        self.run_panel=RunPanel(main,self);self.run_panel.pack(fill='x')
        self.workspace_tabs=ttk.Notebook(main);self.workspace_tabs.pack(fill='both',expand=True)
        self.preview_page=ttk.Frame(self.workspace_tabs);self.workspace_tabs.add(self.preview_page,text='轨迹预览 · WCS')
        plot=ttk.Frame(self.preview_page,style='Card.TFrame',padding=8);plot.pack(fill='both',expand=True)
        self.figure=Figure(figsize=(8,6),dpi=100,facecolor='white',tight_layout=True)
        self.ax=self.figure.add_subplot(111)
        self.canvas=FigureCanvasTkAgg(self.figure,plot)
        self.canvas.get_tk_widget().pack(fill='both',expand=True)
        navigation=NavigationToolbar2Tk(self.canvas,plot,pack_toolbar=False)
        navigation.pack(side='bottom',before=self.canvas.get_tk_widget(),fill='x');navigation.update()
        self.style_plot()
        self.status=tk.Text(self.preview_page,height=3,wrap='word',relief='flat',bg='#e8eef6',fg=INK,padx=12,pady=10,font=(self.ui_font,9))
        self.status.pack(side='bottom',before=plot,fill='x')
        legend=ttk.Frame(self.preview_page);legend.pack(side='bottom',before=plot,fill='x',pady=5)
        ttk.Label(legend,text='● 起点   × 终点   数字：顺序',style='Muted.TLabel').pack(side='left')
        self.teaching=TeachingPanel(self.workspace_tabs,self)
        self.workspace_tabs.add(self.teaching,text='三点示教')
        self.log('导入 DXF 或输入文字 → 生成轨迹 → 启动。CAD 固定使用 WCS。工件定位请打开“三点示教”页，按 1 O → 2 X → 3 XY 引导完成。')

    def show_preview(self):
        self.workspace_tabs.select(self.preview_page)

    def open_text(self):
        if not self.can_replan():return
        if self.text_window is not None and self.text_window.winfo_exists():self.text_window.lift()
        else:self.text_window=TextWindow(self)

    def open_settings(self):
        if self.settings_window is not None and self.settings_window.winfo_exists():self.settings_window.lift()
        else:self.settings_window=SettingsWindow(self)

    def current_robot_config(self,check_teaching=True):
        window=self.robot_window
        brand=self.robot_brand.get()
        if window is not None and window.winfo_exists() and window.current==brand:
            self.robot_configs[brand]=window.read()
        config=self.robot_configs[brand]
        if check_teaching:self.teaching.require_applied(config)
        return config

    def start_execution(self,config=None,script=None):
        panel=self.run_panel
        if panel.busy:return
        if panel.runner.state=='PAUSED':panel.resume();return
        if panel.runner.state in ('RUNNING','UNKNOWN','PAUSED_UNCONFIRMED'):
            panel.status.set('已有任务或运行状态未确认，请先停止；不会重复发送轨迹。');return
        try:
            if config is None:
                if self.profile_error:raise ValueError(self.profile_error)
                config=self.current_robot_config();config.validate(network=True)
                if not self.rebuild():return
                values=self.values()
                script=render_script(self.paths,values['z'],values['clearance'],values['speed'],config)
            self.teaching.require_applied(config)
            panel.start(config,script)
        except Exception as exc:panel.status.set('无法启动：'+str(exc))

    def style_plot(self):
        self.ax.set_facecolor('#fbfdff')
        for spine in self.ax.spines.values():spine.set_color('#dbe3ef')
        self.ax.tick_params(colors='#64748b',labelsize=9)
        self.ax.set_xlabel('X (mm)',color='#64748b')
        self.ax.set_ylabel('Y (mm)',color='#64748b')
        self.ax.grid(True,color='#e2e8f0',linewidth=0.6)

    def log(self, text):
        self.status.configure(state='normal')
        self.status.delete('1.0', 'end')
        self.status.insert('end', text)
        self.status.configure(state='disabled')

    def values(self):
        values = {k: float(v.get()) for k, v in self.inputs.items()}
        if not all(math.isfinite(v) for v in values.values()):
            raise ValueError('所有参数必须是有限数值')
        if min(values['scale'], values['text_scale'], values['step'], values['tolerance'], values['speed']) <= 0:
            raise ValueError('比例、步长、精度和速度必须大于 0')
        if values['row_tolerance'] < 0:
            raise ValueError('行归并容差不能小于 0')
        if values['prune'] < 0:
            raise ValueError('中心线短分支修剪值不能小于 0')
        if values['weld_width'] <= 0 or values['resolution'] <= 0 or not 0 <= values['overlap'] < 100:
            raise ValueError('焊缝宽度、中心线精度须大于 0；重叠率须在 0～100% 之间且不含 100%')
        if values['lift_height'] <= 0:
            raise ValueError('焊缝结束抬升量必须大于 0')
        values['clearance'] = values['z'] + values['lift_height']
        return values

    def open_robot(self):
        if self.robot_window is not None and self.robot_window.winfo_exists():
            if self.robot_window.current!=self.robot_brand.get():
                self.robot_window.brand.set(self.robot_brand.get());self.robot_window.switch_brand()
            self.robot_window.lift()
        else:
            self.robot_window = RobotWindow(self)
            if self.profile_error:
                self.robot_window.status.set(self.profile_error+'；原文件未覆盖，请检查。')

    def open(self):
        if not self.can_replan():return
        filename = filedialog.askopenfilename(parent=self, initialdir=import_directory(self.filename), filetypes=[('CAD DXF', '*.dxf')])
        if filename:
            self.filename = filename
            self.source_kind = 'cad'
            self.file_display.set(Path(filename).name)
            folder_error = ''
            try:
                remember_import_directory(filename)
            except OSError as exc:
                folder_error = '图纸可继续使用，但未能保存下次导入的默认文件夹：' + str(exc)
            self.rebuild()
            self.show_preview()
            if folder_error:
                self.log(self.status.get('1.0', 'end').rstrip()+'\n'+folder_error)

    def rebuild(self):
        if not self.can_replan():return False
        self.paths = []
        try:
            v = self.values()
            if self.source_kind=='text' and self.text_spec is not None:
                raw=text_boundaries(self.text_spec,v['text_scale'])
                warnings=[];units=4
                source='输入文字 · '+Path(self.text_spec.font_file).stem+' · '+self.text_spec.text.replace('\n',' / ')[:48]
            else:
                if not self.filename:raise ValueError('请先导入 DXF 或输入文字 / 数字')
                raw,warnings,units=load_dxf(self.filename,v['tolerance'],v['text_scale'],coordinate_system='wcs')
                source=str(self.filename)
            warnings.insert(0, '图纸固定为世界坐标 WCS，不应用 CAD UCS。WCS 基准点 ({:g}, {:g}) 对应工件原点 O；默认 (0,0) 保留原位置。'.format(v['origin_x'],v['origin_y']))
            unit_scale=1 if self.source_kind=='text' else v['scale']
            if self.source_kind=='text':warnings.append('直接输入的文字已使用 mm，不应用 CAD 单位换算倍率。')
            transformed = [[transform(p, (v['origin_x'], v['origin_y']), v['angle'], unit_scale) for p in contour] for contour in raw]
            planned, notes = plan_paths(transformed, MODES[self.mode.get()], v['weld_width'], v['overlap'], v['fill_angle'], v['resolution'], self.fill_direction.get(), self.continuous.get(), v['prune'])
            planned = order_weld_paths(planned, transformed, MODES[self.mode.get()], v['row_tolerance'])
            notes.insert(0, '默认顺序：原点一侧开始，同排沿 X 正向，再沿 Y 正向换排；同行按竖向重叠或行容差识别，避免 Q 尾部抢先。整实体依次加工，保留实体内部填充方向。')
            warnings.extend(notes)
            self.paths = [discretize(contour, v['step']) for contour in planned]
            self.ax.clear()
            for boundary in transformed:
                if len(boundary) > 1:
                    x, y = zip(*boundary)
                    self.ax.plot(x, y, color='lightgray', linewidth=0.5)
            for i, contour in enumerate(self.paths):
                x, y = zip(*contour)
                self.ax.plot(x, y, linewidth=0.8)
                self.ax.plot(x[0], y[0], 'go', markersize=3)
                self.ax.plot(x[-1], y[-1], 'rx', markersize=4)
                self.ax.annotate(str(i+1), (x[0], y[0]), xytext=(4, 4), textcoords='offset points', fontsize=8)
            self.ax.axhline(0, color='gray', linewidth=0.4)
            self.ax.axvline(0, color='gray', linewidth=0.4)
            self.ax.set_aspect('equal', adjustable='datalim')
            self.ax.grid(True, alpha=0.2)
            self.style_plot()
            self.canvas.draw()
            self.file_display.set(source if self.source_kind=='text' else Path(self.filename).name+' · WCS')
            self.stats.set('{} 条焊道  ·  {:,} 个轨迹点'.format(len(self.paths),sum(map(len,self.paths))))
            self.log(self.mode.get() + '\n' + '{}\n{} 条轮廓，{} 个轨迹点；单位标识={}（4=mm，请核对比例）。\n每条彩色连续焊道独立起熄弧，绿点为起点，红点为终点。预览 X/Y 为 WCS 经手动基准、旋转、比例映射后的工件平面坐标。\n段间动作：熄弧 → 沿工件 Z 抬升 {} mm 至 Z={} mm → 平移到下一起点上方 → 下降至 Z={} mm → 起弧。\n{}'.format(source, len(self.paths), sum(map(len, self.paths)), units, v['lift_height'], v['clearance'], v['z'], '\n'.join(warnings)))
            return True
        except Exception as exc:
            self.paths = []
            self.ax.clear()
            self.style_plot()
            self.canvas.draw()
            self.stats.set('轨迹生成失败')
            self.log('本次未生成轨迹：' + str(exc))
            if isinstance(exc,CadFontError) and self.source_kind=='cad':
                self.open_settings()
                self.settings_window.show_font_issue(exc.font_name,str(exc))
            else:messagebox.showerror('无法生成轨迹', str(exc))
            return False

    def can_replan(self):
        if getattr(getattr(self,'teaching',None),'busy',False):
            self.teaching.status.set('正在记录 TCP，请等待采样结束后再修改任务。');return False
        panel=getattr(self,'run_panel',None)
        if panel is not None and (panel.busy or panel.runner.state in ('RUNNING','PAUSED','UNKNOWN','PAUSED_UNCONFIRMED')):
            panel.status.set('当前任务未停止，请先停止后导入或重新生成轨迹。')
            return False
        return True

    def export(self, kind):
        if not self.rebuild() or not self.paths:
            return
        v = self.values()
        script = None
        try:self.current_robot_config()
        except Exception as exc:
            messagebox.showerror('工件坐标尚未就绪',str(exc),parent=self);return
        if kind != 'csv':
            try:
                c = self.current_robot_config()
                script = render_script(self.paths, v['z'], v['clearance'], v['speed'], c)
            except Exception as exc:
                messagebox.showerror('机器人参数错误', str(exc))
                return
        filename = filedialog.asksaveasfilename(initialdir=str(OUTPUT_DIR), defaultextension='.'+kind, filetypes=[(kind, '*.'+kind)])
        if not filename:
            return
        if kind == 'csv':
            with open(filename, 'w', newline='', encoding='utf-8-sig') as stream:
                writer = csv.writer(stream)
                writer.writerow(['contour', 'point', 'workpiece_x_mm', 'workpiece_y_mm', 'workpiece_z_mm'])
                for i, contour in enumerate(self.paths, 1):
                    for j, (x, y) in enumerate(contour, 1):
                        writer.writerow([i, j, x, y, v['z']])
        else:
            with open(filename, 'w', encoding='utf-8') as stream:
                stream.write(script)
        messagebox.showinfo('导出完成', filename)


if __name__ == '__main__':
    App().mainloop()
