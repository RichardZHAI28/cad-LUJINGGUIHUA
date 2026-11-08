"""Shared light desktop theme for the welding planner."""
import tkinter.font as tkfont
import tkinter as tk
from tkinter import ttk

BG='#f1f5f9'
INK='#172b46'
BLUE='#2563eb'

def fit_window(window, width, height):
    """Use Tk logical pixels, including the current desktop DPI scaling."""
    available_w=max(320,window.winfo_screenwidth()-40)
    available_h=max(240,window.winfo_screenheight()-90)
    width=min(width,available_w);height=min(height,available_h)
    window.geometry('{}x{}+10+10'.format(width,height))
    window.minsize(min(800,available_w),min(500,available_h))


class ScrollPane(ttk.Frame):
    """Scrollable settings area; wheel bindings belong only to this pane."""
    def __init__(self,parent,padding=12):
        super().__init__(parent)
        self.canvas=tk.Canvas(self,background=BG,highlightthickness=0,width=1,height=1)
        vertical=ttk.Scrollbar(self,orient='vertical',command=self.canvas.yview)
        horizontal=ttk.Scrollbar(self,orient='horizontal',command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=vertical.set,xscrollcommand=horizontal.set)
        self.canvas.grid(row=0,column=0,sticky='nsew')
        vertical.grid(row=0,column=1,sticky='ns');horizontal.grid(row=1,column=0,sticky='ew')
        self.rowconfigure(0,weight=1);self.columnconfigure(0,weight=1)
        self.content=ttk.Frame(self.canvas,padding=padding)
        self.item=self.canvas.create_window(0,0,window=self.content,anchor='nw')
        self.content.bind('<Configure>',self._layout)
        self.canvas.bind('<Configure>',self._layout)
        # A private bindtag avoids bind_all callbacks leaking to other windows.
        self.tag='ScrollPane'+str(id(self))
        for sequence in ('<MouseWheel>','<Button-4>','<Button-5>'):
            self.bind_class(self.tag,sequence,self._wheel)
        self.content.bind('<Map>',lambda event:self._tag_children(self.content))
        self.bind('<Destroy>',self._destroy,add='+')

    def _tag_children(self,widget):
        tags=widget.bindtags()
        if self.tag not in tags:widget.bindtags((self.tag,)+tags)
        for child in widget.winfo_children():self._tag_children(child)

    def _layout(self,event=None):
        self.canvas.itemconfigure(self.item,width=max(self.canvas.winfo_width(),self.content.winfo_reqwidth()))
        self.canvas.configure(scrollregion=self.canvas.bbox('all'))

    def _wheel(self,event):
        if getattr(event,'num',None)==4:units=-1
        elif getattr(event,'num',None)==5:units=1
        else:units=-int(event.delta/120) if abs(event.delta)>=120 else (-1 if event.delta>0 else 1)
        self.canvas.yview_scroll(units*3,'units')
        return 'break'

    def _destroy(self,event):
        if event.widget is self:
            for sequence in ('<MouseWheel>','<Button-4>','<Button-5>'):
                self.unbind_class(self.tag,sequence)

def apply_theme(root):
    families=set(tkfont.families(root))
    font=next((name for name in ('Microsoft YaHei UI','Microsoft YaHei','Noto Sans CJK SC','WenQuanYi Micro Hei') if name in families),'TkDefaultFont')
    root.option_add('*Font',(font,10))
    root.configure(background=BG)
    style=ttk.Style(root);style.theme_use('clam')
    style.configure('.',font=(font,10),background=BG,foreground=INK)
    style.configure('TFrame',background=BG)
    style.configure('Card.TFrame',background='white')
    style.configure('TLabel',background=BG,foreground=INK)
    style.configure('Card.TLabel',background='white')
    style.configure('Muted.TLabel',foreground='#64748b')
    style.configure('Title.TLabel',font=(font,15,'bold'))
    style.configure('TButton',padding=(14,9),background='#e2e8f0',borderwidth=0,foreground=INK)
    style.map('TButton',background=[('active','#cbd5e1')],foreground=[('disabled','#94a3b8')])
    style.configure('Primary.TButton',background=BLUE,foreground='white')
    style.map('Primary.TButton',background=[('active','#1d4ed8'),('disabled','#cbd5e1')],foreground=[('disabled','#64748b')])
    style.configure('Danger.TButton',background='#fef2f2',foreground='#b91c1c')
    style.map('Danger.TButton',background=[('active','#fee2e2')])
    style.configure('TEntry',padding=7,fieldbackground='white',bordercolor='#cbd5e1',lightcolor='#cbd5e1',darkcolor='#cbd5e1')
    style.configure('TCombobox',padding=6,fieldbackground='white',background='#e2e8f0',arrowsize=14)
    style.map('TCombobox',fieldbackground=[('readonly','white')],selectbackground=[('readonly','white')],selectforeground=[('readonly',INK)])
    style.configure('TNotebook',background=BG,borderwidth=0)
    style.configure('TNotebook.Tab',padding=(13,9),background='#e2e8f0')
    style.map('TNotebook.Tab',background=[('selected','white')],foreground=[('selected',BLUE)])
    style.configure('TCheckbutton',padding=(0,6),background=BG)
    style.configure('TLabelframe',background=BG,bordercolor='#dbe3ef')
    style.configure('TLabelframe.Label',font=(font,10,'bold'),foreground=BLUE,background=BG)
    return font
