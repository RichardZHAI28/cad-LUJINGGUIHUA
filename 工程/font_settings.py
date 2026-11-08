"""Font recovery inside the secondary settings window."""
from pathlib import Path
import tkinter as tk
from tkinter import ttk,filedialog
from matplotlib import font_manager
from font_support import import_font,load_font_mappings,save_font_mappings,refresh_fonts,font_key


class FontSettings(ttk.Frame):
    def __init__(self,parent,app):
        super().__init__(parent)
        self.app=app
        self.alias=tk.StringVar();self.family=tk.StringVar()
        self.status=tk.StringVar(value='缺少原字库时，可导入字库文件或明确选择替代字体。')
        ttk.Label(self,text='TTF / OTF / TTC 是字库格式，并不是焊接模式。\n文字转为几何边界后，仍可选择三种模式；独立点状实心块仍不能提中心线。\n替代字体会改变字形，请核对 Q、R 等字母的预览。SHX 原笔画解析尚未接入。',wraplength=650).grid(row=0,column=0,columnspan=2,sticky='w',pady=(0,12))
        ttk.Label(self,text='图纸原字体名称').grid(row=1,column=0,sticky='w',pady=6)
        ttk.Entry(self,textvariable=self.alias,width=38).grid(row=1,column=1,sticky='ew',padx=12)
        ttk.Label(self,text='例如 arial.ttf、simsun.ttc、txt.shx',style='Muted.TLabel').grid(row=2,column=0,columnspan=2,sticky='w')
        ttk.Button(self,text='导入字库文件并重试…',command=self.choose_file).grid(row=3,column=0,columnspan=2,sticky='ew',pady=10)
        ttk.Label(self,text='或选择本机已安装字体').grid(row=4,column=0,sticky='w',pady=6)
        self.combo=ttk.Combobox(self,textvariable=self.family,width=38)
        self.combo.grid(row=4,column=1,sticky='ew',padx=12)
        self.populate_families()
        ttk.Button(self,text='使用所选字体并重试',command=self.choose_family).grid(row=5,column=0,columnspan=2,sticky='ew',pady=6)
        ttk.Button(self,text='刷新字体列表（安装字库后使用）',command=self.refresh).grid(row=6,column=0,columnspan=2,sticky='ew',pady=6)
        self.table=ttk.Treeview(self,columns=('alias','font'),show='headings',height=5,selectmode='browse')
        self.table.heading('alias',text='CAD 原字体');self.table.heading('font',text='已指定字库')
        self.table.column('alias',width=180);self.table.column('font',width=330)
        self.table.grid(row=7,column=0,columnspan=2,sticky='ew',pady=8)
        scroll=ttk.Scrollbar(self,command=self.table.yview)
        scroll.grid(row=7,column=2,sticky='ns',pady=8)
        self.table.configure(yscrollcommand=scroll.set)
        self.table.bind('<<TreeviewSelect>>',self.select_row)
        ttk.Button(self,text='取消选中映射',command=self.remove).grid(row=8,column=0,columnspan=2,sticky='ew',pady=6)
        ttk.Label(self,textvariable=self.status,wraplength=650).grid(row=9,column=0,columnspan=2,sticky='w',pady=10)
        self.columnconfigure(1,weight=1);self.reload()

    def populate_families(self):
        self.combo.configure(values=sorted({f.name for f in font_manager.fontManager.ttflist if Path(f.fname).is_file()}))

    def reload(self):
        for row in self.table.get_children():self.table.delete(row)
        try:
            for alias,file in sorted(load_font_mappings().items()):
                name=Path(file).name
                self.table.insert('',tk.END,values=(alias,name[17:] if len(name)>17 and name[16]=='_' else name))
        except Exception as exc:self.status.set(str(exc))

    def select_row(self,event=None):
        selection=self.table.selection()
        if selection:self.alias.set(self.table.item(selection[0],'values')[0])

    def apply_file(self,file):
        if not self.app.can_replan():return
        try:
            name=import_font(file,self.alias.get())
            self.reload();self.populate_families()
            self.status.set('已为“{}”指定字库“{}”，无需安装到 Windows。'.format(self.alias.get(),name))
            if self.app.filename:self.app.rebuild()
        except Exception as exc:self.status.set('字库未应用：'+str(exc))

    def choose_file(self):
        if not self.app.can_replan():return
        if not font_key(self.alias.get()):self.status.set('请先填写图纸原字体名称。');return
        file=filedialog.askopenfilename(parent=self.winfo_toplevel(),title='选择原字库或明确指定的替代字库',filetypes=[('字库文件','*.ttf *.otf *.ttc'),('所有文件','*.*')])
        if file:self.apply_file(file)

    def choose_family(self):
        try:
            family=self.family.get().strip()
            if not family:raise ValueError('请先选择字体')
            file=font_manager.findfont(font_manager.FontProperties(family=[family]),fallback_to_default=False)
            self.apply_file(file)
        except Exception as exc:self.status.set('字库未应用：'+str(exc))

    def refresh(self):
        if not self.app.can_replan():return
        try:
            count=refresh_fonts(force=True);self.populate_families()
            self.status.set('字体列表已刷新，新发现 {} 个字库。选择后点击“使用所选字体并重试”。'.format(count))
        except Exception as exc:self.status.set('刷新失败：'+str(exc))

    def remove(self):
        if not self.app.can_replan():return
        try:
            data=load_font_mappings();data.pop(font_key(self.alias.get()),None)
            save_font_mappings(data);self.reload();self.status.set('已取消映射，图纸原文件未修改。')
        except Exception as exc:self.status.set(str(exc))
