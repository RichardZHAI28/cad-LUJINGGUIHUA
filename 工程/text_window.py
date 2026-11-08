"""Direct text editor; the applied source stays active for generate/export/start."""
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog
from matplotlib import ft2font
from direct_text import TextSpec, available_fonts, text_boundaries
from file_preferences import read_ui_setting, save_ui_setting
from font_support import import_font, load_font_mappings, font_key, refresh_fonts
from ui_theme import ScrollPane, fit_window


class TextWindow(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title('输入文字与数字 → 焊接轨迹')
        fit_window(self,820,740)
        pane=ScrollPane(self);pane.pack(fill='both',expand=True)
        page=pane.content;page.columnconfigure(1,weight=1)
        ttk.Label(page,text='输入内容',style='Title.TLabel').grid(row=0,column=0,columnspan=2,sticky='w',pady=8)
        self.editor=tk.Text(page,height=5,width=36,wrap='word',undo=True)
        self.editor.grid(row=1,column=0,columnspan=2,sticky='ew',pady=8)
        self.font=tk.StringVar();self.variables={}
        ttk.Label(page,text='当前字体（按真实字库生成）').grid(row=2,column=0,sticky='w',pady=8)
        self.combo=ttk.Combobox(page,textvariable=self.font,state='readonly',width=34)
        self.combo.grid(row=2,column=1,sticky='ew',padx=8)
        self.combo.bind('<<ComboboxSelected>>',self.show_coverage)
        buttons=ttk.Frame(page);buttons.grid(row=3,column=0,columnspan=2,sticky='ew')
        ttk.Button(buttons,text='导入字库…',command=self.choose_font).pack(side='left',padx=(0,8))
        ttk.Button(buttons,text='刷新字体',command=self.refresh).pack(side='left')
        self.coverage=tk.StringVar()
        ttk.Label(page,textvariable=self.coverage,wraplength=620,style='Muted.TLabel').grid(row=4,column=0,columnspan=2,sticky='w',pady=8)
        for row,(key,label) in enumerate([('height','大写字高 mm'),('x','文字左下角 WCS X / mm'),('y','文字左下角 WCS Y / mm'),('line_spacing','行距 / 字高倍率（≥1）')],5):
            self.variables[key]=tk.StringVar()
            ttk.Label(page,text=label).grid(row=row,column=0,sticky='w',pady=6)
            ttk.Entry(page,textvariable=self.variables[key],width=18).grid(row=row,column=1,sticky='ew',padx=8,pady=6)
        ttk.Label(page,text='支持多行，按原字形保留内外边界。生成后使用主界面选择的中心线、实心填充或内外轮廓模式。\n文字左下角以全部可见笔画的包围框为准；整体字号倍率仍在主界面调整。',wraplength=620).grid(row=9,column=0,columnspan=2,sticky='w',pady=10)
        self.status=tk.StringVar()
        ttk.Label(page,textvariable=self.status,wraplength=620).grid(row=10,column=0,columnspan=2,sticky='w',pady=8)
        footer=ttk.Frame(self,padding=10);footer.pack(side='bottom',before=pane,fill='x')
        ttk.Button(footer,text='生成文字轨迹',style='Primary.TButton',command=self.apply).pack(side='right')
        spec=app.text_spec
        if spec is None:
            data=read_ui_setting('direct_text',{})
            try:spec=TextSpec(**data) if isinstance(data,dict) else TextSpec()
            except TypeError:spec=TextSpec()
        self.editor.insert('1.0',spec.text)
        for key,var in self.variables.items():var.set(str(getattr(spec,key)))
        self.populate(spec.font_file)

    def populate(self, selected=''):
        self.fonts=available_fonts()
        self.combo.configure(values=list(self.fonts))
        label=next((label for label,file in self.fonts.items() if file==selected),'')
        if selected and not label and Path(selected).is_file():
            face=ft2font.FT2Font(selected)
            label=face.family_name+' · '+Path(selected).name
            self.fonts[label]=selected;self.combo.configure(values=list(self.fonts))
        if selected and not label:
            # Missing saved fonts must not silently change the workpiece shape.
            self.font.set('');self.coverage.set('上次字库已缺失，请重新选择或导入：'+Path(selected).name)
        else:
            self.font.set(label or next(iter(self.fonts),''));self.show_coverage()

    def show_coverage(self,event=None):
        file=self.fonts.get(self.font.get())
        if not file:return
        codes=ft2font.FT2Font(file).get_charmap()
        stem=Path(file).stem.casefold()
        if 'ziti1' in stem or 'ziti2' in stem:
            self.coverage.set('此字库支持：'+''.join(chr(c) for c in sorted(codes) if c>32)+'；不支持的字符会提示，不自动替换。')
        else:self.coverage.set('所选字库：'+Path(file).name+'。缺少字符时会明确提示。')

    def refresh(self):
        selected=self.fonts.get(self.font.get(),'')
        refresh_fonts(force=True);self.populate(selected)

    def choose_font(self):
        if not self.app.can_replan():return
        file=filedialog.askopenfilename(parent=self,title='选择文字字库',filetypes=[('字库','*.ttf *.otf *.ttc')])
        if not file:return
        try:
            import_font(file,Path(file).name)
            self.populate(load_font_mappings()[font_key(Path(file).name)])
            self.status.set('字库已导入软件，无需安装到系统。')
        except Exception as exc:self.status.set(str(exc))

    def read(self):
        if self.font.get() not in self.fonts:raise ValueError('请选择文字字体')
        return TextSpec(text=self.editor.get('1.0','end-1c'),font_file=self.fonts[self.font.get()],
                        **{key:float(var.get()) for key,var in self.variables.items()})

    def apply(self):
        if not self.app.can_replan():return False
        try:
            spec=self.read()
            text_boundaries(spec,self.app.values()['text_scale'])
            self.app.text_spec=spec;self.app.source_kind='text'
            if not self.app.rebuild():
                self.status.set('文字边界已读取；请检查主界面的加工模式或参数。');return False
            try:save_ui_setting('direct_text',spec.to_dict())
            except OSError as exc:
                self.status.set('轨迹已生成，但未能保存输入偏好：'+str(exc));return True
            self.status.set('已生成。继续修改内容后可再次生成；启动、导出均使用当前文字轨迹。')
            self.app.show_preview()
            return True
        except Exception as exc:
            self.status.set('未生成：'+str(exc));return False
