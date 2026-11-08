"""Robot configuration, preview and explicitly initiated socket execution UI."""
import queue
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from pathlib import Path
from runtime_paths import OUTPUT_DIR
from ui_theme import fit_window, ScrollPane
from robot_adapters import (BRANDS, RobotConfig, render_script, save_profiles,
                            test_connection, send_script)

TCP_MODES={'沿用控制器已标定 TCP':'controller','使用下方 TCP 参数':'configured'}
ORIENTATION_MODES={'保持程序启动时的 TCP 姿态':'current','使用基座坐标系姿态':'base','使用用户坐标系姿态':'user'}

class RobotWindow(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app)
        self.app=app
        self.title('机器人配置与通信 · ELITE CS/ES / UR')
        fit_window(self,1080,850)
        self.configure(background='#f1f5f9')
        self.vars={}
        self.results=queue.Queue()
        self.busy=False
        self.current=app.robot_brand.get()
        header=ttk.Frame(self,padding=10);header.pack(fill='x')
        ttk.Label(header,text='机器人品牌 / 控制器系列').pack(side='left')
        self.brand=tk.StringVar(value=self.current)
        self.selector=ttk.Combobox(header,textvariable=self.brand,values=list(BRANDS),state='readonly',width=22)
        self.selector.pack(side='left',padx=10)
        self.selector.bind('<<ComboboxSelected>>',self.switch_brand)
        self.pose_hint=tk.StringVar()
        ttk.Label(self,textvariable=self.pose_hint,foreground='#a34c00',wraplength=750).pack(fill='x',padx=12)
        notebook=ttk.Notebook(self);notebook.pack(fill='both',expand=True,padx=10)
        settings_page=ScrollPane(notebook);settings=settings_page.content;notebook.add(settings_page,text='坐标、运动与焊接')
        network_page=ScrollPane(notebook);network=network_page.content;notebook.add(network_page,text='通信与设备')
        preview=ttk.Frame(notebook);notebook.add(preview,text='脚本预览')
        self.preview=tk.Text(preview,wrap='none',font=('Consolas',10),state='disabled',bg='#142b49',fg='#dbeafe',insertbackground='white',relief='flat',padx=16,pady=14)
        sx=ttk.Scrollbar(preview,orient='horizontal',command=self.preview.xview)
        sx.pack(side='bottom',fill='x')
        self.preview.configure(xscrollcommand=sx.set)
        sy=ttk.Scrollbar(preview,command=self.preview.yview)
        sy.pack(side='right',fill='y');self.preview.pack(fill='both',expand=True)
        self.preview.configure(yscrollcommand=sy.set)
        fields=[('frame','工件坐标相对基座（首页三点示教）：X,Y,Z(mm),Rx,Ry,Rz(rad)'),
                ('tcp','TCP 相对法兰：X,Y,Z(mm),Rx,Ry,Rz(rad)'),
                ('orientation','焊枪姿态（按下方参考模式）：Rx,Ry,Rz(rad)'),
                ('travel_speed','空移 / 升降速度 mm/s'),('acceleration','直线运动加速度 mm/s²'),
                ('blend_radius','焊接圆滑半径 mm（0 为精确停点）'),
                ('output','起熄弧标准 DO 编号'),('ignition_wait','起弧后等待 s'),('end_wait','终点保持起弧等待 s')]
        self.pose_entries={}
        for row,(key,label) in enumerate(fields,2):
            ttk.Label(settings,text=label).grid(row=row,column=0,sticky='w',pady=7)
            var=tk.StringVar();self.vars[key]=var
            entry=ttk.Entry(settings,textvariable=var,width=46)
            entry.grid(row=row,column=1,sticky='ew',padx=10)
            if key in ('tcp','orientation'):self.pose_entries[key]=entry
        settings.columnconfigure(1,weight=1)
        for row,(key,label) in enumerate([('active_high','高电平起弧（取消为低电平起弧）'),
                                         ('weld_enabled','启用焊接 DO 输出（默认不发送）')],len(fields)+2):
            var=tk.BooleanVar();self.vars[key]=var
            ttk.Checkbutton(settings,text=label,variable=var).grid(row=row,column=0,columnspan=2,sticky='w',pady=6)
        for row,(key,label,options) in enumerate([('tcp_mode','TCP 标定来源',TCP_MODES),('orientation_mode','焊枪姿态参考',ORIENTATION_MODES)]):
            ttk.Label(settings,text=label).grid(row=row,column=0,sticky='w',pady=7)
            var=tk.StringVar();self.vars[key]=var
            combo=ttk.Combobox(settings,textvariable=var,values=list(options),state='readonly',width=36)
            combo.grid(row=row,column=1,sticky='ew',padx=10)
            combo.bind('<<ComboboxSelected>>',self.update_pose_fields)
        ttk.Label(settings,text='默认沿用控制器 TCP，并在程序开始时锁定当前基座 TCP 姿态。\n仅“用户坐标系姿态”模式会将姿态随用户坐标系一起旋转。姿态单位为 rad。\n作业 Z、抬升量和焊接速度使用主界面参数。圆滑仅用于焊道内部。\n仅支持数字起熄弧；未实现焊机握手。首点接近路径及可达性须验证。',foreground='#a34c00',wraplength=700).grid(row=len(fields)+4,column=0,columnspan=2,sticky='w',pady=12)
        for row,(key,label) in enumerate([('model','机器人型号（记录用）'),('version','控制器版本（记录用）'),('name','程序名（英文字母开头）'),('host','机器人 IP'),('port','脚本端口'),('dashboard_port','运行控制端口（默认 29999）'),('state_port','只读状态端口（默认 30011）')]):
            ttk.Label(network,text=label).grid(row=row,column=0,sticky='w',pady=9)
            var=tk.StringVar();self.vars[key]=var
            ttk.Entry(network,textvariable=var,width=50).grid(row=row,column=1,sticky='ew',padx=10)
        ttk.Label(network,text='UR 脚本默认 30002；ELITE CS/ES 默认 30001。\n主界面启动、暂停、停止使用运行控制及只读状态端口。需在控制器上电并启用远程模式。\n暂停/停止不是硬件急停。ELITE EC/EA 不在此次适配范围内。',foreground='#a34c00',wraplength=700).grid(row=7,column=0,columnspan=2,sticky='w',pady=12)
        self.status=tk.StringVar(value='尚未连接。请先设置实际坐标、TCP 和姿态。')
        status_label=ttk.Label(self,textvariable=self.status,wraplength=960)
        status_label.pack(side='bottom',before=notebook,fill='x',padx=12,pady=8)
        self.bind('<Configure>',lambda e:status_label.configure(wraplength=max(200,self.winfo_width()-32)) if e.widget is self else None,add='+')
        buttons=ttk.Frame(self,padding=10);buttons.pack(side='bottom',before=status_label,fill='x')
        self.buttons=[]
        for index,(label,fn) in enumerate([('保存配置',self.save),('生成预览',lambda:self.show_preview(notebook,preview)),('导出脚本',self.export),('测试连接',self.probe)]):
            button=ttk.Button(buttons,text=label,command=fn,style='Danger.TButton' if label=='发送并执行' else ('Primary.TButton' if label=='生成预览' else 'TButton'));button.grid(row=index//3,column=index%3,sticky='ew',padx=4,pady=3);self.buttons.append(button)
        for column in range(3):buttons.columnconfigure(column,weight=1)
        self.populate(app.robot_configs[self.current])
        self.poll_id=self.after(100,self.poll)

    def destroy(self):
        if hasattr(self,'poll_id'):
            self.after_cancel(self.poll_id)
        super().destroy()

    def populate(self,c):
        for key,var in self.vars.items():
            value=getattr(c,key)
            if key in ('tcp_mode','orientation_mode'):
                options=TCP_MODES if key=='tcp_mode' else ORIENTATION_MODES
                value=next(label for label,code in options.items() if code==value)
            var.set(', '.join(str(v) for v in value) if isinstance(value,(list,tuple)) else value)
        self.pose_hint.set(BRANDS[c.brand]['pose']+'；DO 0～'+str(BRANDS[c.brand]['max_do']))
        self.update_pose_fields()
        self.preview.configure(state='normal')
        self.preview.delete('1.0','end')
        self.preview.configure(state='disabled')

    def update_pose_fields(self,event=None):
        self.pose_entries['tcp'].configure(state='normal' if TCP_MODES.get(self.vars['tcp_mode'].get())=='configured' else 'disabled')
        self.pose_entries['orientation'].configure(state='disabled' if ORIENTATION_MODES.get(self.vars['orientation_mode'].get())=='current' else 'normal')

    def read(self):
        data={key:var.get() for key,var in self.vars.items()}
        data['tcp_mode']=TCP_MODES[data['tcp_mode']]
        data['orientation_mode']=ORIENTATION_MODES[data['orientation_mode']]
        for key in ('frame','tcp','orientation'):
            data[key]=tuple(float(v.strip()) for v in data[key].replace('，',',').split(','))
        for key in ('port','dashboard_port','state_port','output'):data[key]=int(data[key])
        for key in ('travel_speed','acceleration','blend_radius','ignition_wait','end_wait'):data[key]=float(data[key])
        data['host']=data['host'].strip()
        c=RobotConfig(brand=self.current,**data)
        c.validate()
        return c

    def switch_brand(self,event=None):
        target=self.brand.get()
        try:self.app.robot_configs[self.current]=self.read()
        except Exception as exc:
            self.brand.set(self.current);messagebox.showerror('参数错误',str(exc),parent=self);return
        self.current=target
        self.populate(self.app.robot_configs[target])
        self.app.robot_brand.set(target)
        self.status.set('已切换品牌，使用该品牌独立配置；姿态数值不会跨品牌复制。')

    def save(self):
        try:
            self.app.robot_configs[self.current]=self.read()
            save_profiles(self.app.robot_configs)
            self.app.profile_error=''
            self.app.robot_brand.set(self.current)
            self.app.teaching.changed()
            self.status.set('已保存两家机器人的独立配置。')
        except Exception as exc:messagebox.showerror('保存失败',str(exc),parent=self)

    def generate(self):
        c=self.read()
        self.app.teaching.require_applied(c)
        if not self.app.rebuild():return None
        v=self.app.values()
        script=render_script(self.app.paths,v['z'],v['clearance'],v['speed'],c)
        self.preview.configure(state='normal')
        self.preview.delete('1.0','end');self.preview.insert('end',script)
        self.preview.configure(state='disabled')
        self.app.robot_configs[self.current]=c
        self.app.robot_brand.set(self.current)
        self.status.set('圆滑半径 {} mm；内部点按相邻短边的 45% 自动限幅，折返点停点。二维预览为名义轨迹，非控制器实际圆滑曲线。'.format(c.blend_radius))
        return c,script

    def show_preview(self,notebook,page):
        try:
            if self.generate():notebook.select(page)
        except Exception as exc:messagebox.showerror('生成失败',str(exc),parent=self)

    def export(self):
        try:
            result=self.generate()
            if not result:return
            c,script=result
            filename=filedialog.asksaveasfilename(parent=self,initialdir=str(OUTPUT_DIR),initialfile=c.name+('.elite.script' if c.brand=='ELITE CS/ES' else '.ur.script'),defaultextension='.script',filetypes=[('Robot script','*.script')])
            if filename:
                Path(filename).write_text(script,encoding='utf-8')
                self.status.set('已导出 '+filename+'；文件定义 '+c.name+'()，在示教器脚本节点加载后需调用该函数。')
        except Exception as exc:messagebox.showerror('导出失败',str(exc),parent=self)

    def launch(self,fn):
        if self.busy:return
        self.busy=True
        for button in self.buttons:button.configure(state='disabled')
        self.selector.configure(state='disabled')
        self.status.set('通信中…')
        def worker():
            try:self.results.put(fn())
            except Exception as exc:self.results.put('通信未确认：'+str(exc)+'。请检查示教器状态；不会自动重试。')
        threading.Thread(target=worker,daemon=True).start()

    def poll(self):
        try:
            result=self.results.get_nowait()
            self.status.set(result);self.busy=False
            for button in self.buttons:button.configure(state='normal')
            self.selector.configure(state='readonly')
        except queue.Empty:pass
        self.poll_id=self.after(100,self.poll)

    def probe(self):
        try:
            c=self.read();c.validate(network=True)
            self.launch(lambda:test_connection(c))
        except Exception as exc:messagebox.showerror('连接参数错误',str(exc),parent=self)

    def execute(self):
        try:
            result=self.generate()
            if not result:return
            c,script=result;c.validate(network=True)
            self.app.start_execution(c,script)
        except Exception as exc:messagebox.showerror('无法发送',str(exc),parent=self)
