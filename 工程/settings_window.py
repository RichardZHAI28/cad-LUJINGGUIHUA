"""Secondary settings share the main window's variables; no duplicate values."""
import tkinter as tk
from tkinter import ttk
from ui_theme import ScrollPane,fit_window
from welding import FILL_MODES
from font_settings import FontSettings

FIELDS=[
 ('工艺','weld_width','焊缝宽度 mm','8'),('工艺','overlap','焊道重叠率 %','20'),
 ('工艺','fill_angle','排道角度 °','0'),('工艺','resolution','中心线采样间距 mm','0.2'),
 ('工艺','prune','短分支修剪 mm','0.5'),
 ('坐标与字号','origin_x','工件零点对应的图纸 WCS X','0'),('坐标与字号','origin_y','工件零点对应的图纸 WCS Y','0'),
 ('坐标与字号','angle','坐标旋转 °','0'),('坐标与字号','scale','CAD 单位 → mm 倍率','1'),
 ('坐标与字号','text_scale','整体字号倍率','1'),('坐标与字号','tolerance','曲线弦差 / CAD 单位','0.1'),
 ('运动与顺序','step','最大点间距 mm','5'),('运动与顺序','z','作业高度 Z / mm','0'),
 ('运动与顺序','lift_height','焊缝结束抬升量 mm','20'),('运动与顺序','speed','焊接速度 mm/s','10'),
 ('运动与顺序','row_tolerance','行归并容差 mm','5')]


class SettingsWindow(tk.Toplevel):
    def __init__(self,app):
        super().__init__(app)
        self.title('参数设置');fit_window(self,880,720)
        ttk.Label(self,text='修改后点击主界面“生成轨迹”更新；运行中的任务使用启动时的参数。',wraplength=700,padding=12).pack(fill='x')
        notebook=ttk.Notebook(self);self.notebook=notebook;notebook.pack(fill='both',expand=True,padx=12)
        ttk.Button(self,text='完成',command=self.destroy).pack(side='bottom',before=notebook,pady=10)
        for group in ('工艺','坐标与字号','运动与顺序'):
            page=ScrollPane(notebook);notebook.add(page,text=group);frame=page.content
            entries=[f for f in FIELDS if f[0]==group]
            start_row=0
            if group=='坐标与字号':
                ttk.Label(frame,text='图纸固定使用世界坐标 WCS。默认保留原始位置，不读取 CAD 的 UCS。\n下方基准点默认 (0,0)，对应机器人三点示教的工件原点 O；只有手动修改后才平移。',wraplength=520).grid(row=0,column=0,columnspan=2,sticky='w',pady=(0,8))
                start_row=1
            for row,(_,key,label,_) in enumerate(entries,start_row):
                ttk.Label(frame,text=label).grid(row=row,column=0,sticky='w',pady=8)
                ttk.Entry(frame,textvariable=app.inputs[key],width=20).grid(row=row,column=1,sticky='ew',padx=16,pady=5)
            frame.columnconfigure(1,weight=1)
            if group=='工艺':
                row=len(entries)
                ttk.Label(frame,text='填充方向').grid(row=row,column=0,sticky='w',pady=8)
                ttk.Combobox(frame,textvariable=app.fill_direction,values=FILL_MODES,state='readonly').grid(row=row,column=1,sticky='ew',padx=16)
                ttk.Checkbutton(frame,text='连续焊接 · 不跨孔洞连接',variable=app.continuous).grid(row=row+1,column=0,columnspan=2,sticky='w')
        self.font_page=ScrollPane(notebook);notebook.add(self.font_page,text='字体')
        self.font_settings=FontSettings(self.font_page.content,app)
        self.font_settings.pack(fill='both',expand=True)

    def show_font_issue(self,name,message):
        self.font_settings.alias.set(name)
        self.font_settings.status.set(message)
        self.notebook.select(self.font_page);self.deiconify();self.lift()
