"""First-level, guided three-point workpiece teaching. Capture is read-only."""
import queue
import threading
from dataclasses import replace
import tkinter as tk
from tkinter import ttk
from file_preferences import read_ui_setting, save_ui_setting
from frame_teaching import teach_frame, same_tcp
from robot_control import read_teaching_sample
from robot_adapters import save_profiles
from ui_theme import ScrollPane

STEPS=[('原点 O','将已标定的焊枪 TCP 尖端移到工件零点。此点对应图纸 WCS 基准点，默认 (0,0)。'),
       ('X 方向点','从 O 沿希望的工件 X 正方向移动一段距离，再记录。O → 此点定义 X 正方向。'),
       ('XY 平面点','在同一工件平面上，移动到 X 轴的 Y 正侧并记录。无需恰好落在 Y 轴上，但不能与前两点共线。')]


class TeachingPanel(ScrollPane):
    def __init__(self,parent,app):
        super().__init__(parent)
        self.app=app;self.busy=False;self.results=queue.Queue();self.loading=False
        data=read_ui_setting('teaching_profiles',{})
        self.records=data if isinstance(data,dict) else {}
        self.current=app.robot_brand.get();self.snapshots={};self.offsets=[None]*3;self.point_contexts=[None]*3
        self.point_vars=[tk.StringVar() for _ in STEPS]
        self.step_labels=[tk.StringVar() for _ in STEPS]
        self.badges=[tk.StringVar() for _ in STEPS]
        self.entries=[];self.buttons=[];self.cards=[]
        page=self.content;page.columnconfigure(0,weight=1)
        self.heading=tk.StringVar()
        step_bar=ttk.Frame(page,padding=(0,4));step_bar.grid(row=0,column=0,sticky='ew')
        # Keep teaching shortcuts inside this page, away from the run toolbar.
        for i,var in enumerate(self.step_labels):
            step_bar.columnconfigure(i,weight=1,uniform='teach')
            ttk.Button(step_bar,textvariable=var,command=lambda index=i:self.focus_point(index)).grid(row=0,column=i,sticky='ew',padx=2)
        ttk.Label(page,textvariable=self.heading,style='Title.TLabel').grid(row=1,column=0,sticky='w',pady=4)
        ttk.Label(page,text='准备：在示教器选用已标定 TCP，停止机器人程序。用示教器移动焊枪，按 1 → 2 → 3 记录。\n手动输入时，填写示教器“基座坐标”下 TCP 的 X,Y,Z（mm），不要填写关节角或用户坐标。',wraplength=560).grid(row=2,column=0,sticky='w',pady=4)
        self.diagram=tk.Canvas(page,width=340,height=170,bg='white',highlightthickness=0)
        self.diagram.grid(row=3,column=0,sticky='ew',pady=4)
        self.diagram.bind('<Configure>',lambda event:self.draw_diagram())
        for i,(name,help_text) in enumerate(STEPS):
            card=ttk.LabelFrame(page,text='{}  {}'.format(i+1,name),padding=6)
            self.cards.append(card)
            card.grid(row=i+4,column=0,sticky='ew',pady=4);card.columnconfigure(0,weight=1)
            ttk.Label(card,text=help_text,wraplength=520).grid(row=0,column=0,columnspan=2,sticky='w',pady=(0,6))
            entry=ttk.Entry(card,textvariable=self.point_vars[i],width=28)
            entry.grid(row=1,column=0,sticky='ew',padx=(0,8));self.entries.append(entry)
            button=ttk.Button(card,text='记录当前 TCP',command=lambda index=i:self.capture(index))
            button.grid(row=1,column=1,sticky='e');self.buttons.append(button)
            self.point_vars[i].trace_add('write',lambda *args,index=i:self.changed(index))
        # Feedback and apply controls remain visible even when the guide scrolls.
        footer=ttk.Frame(self,padding=8);footer.grid(row=2,column=0,columnspan=2,sticky='ew')
        footer.columnconfigure(0,weight=1);footer.columnconfigure(1,weight=1)
        self.apply_button=ttk.Button(footer,text='计算并应用',style='Primary.TButton',command=self.apply)
        self.apply_button.grid(row=0,column=0,sticky='ew',padx=(0,6),pady=4)
        ttk.Button(footer,text='清空三点',command=self.clear).grid(row=0,column=1,sticky='ew',pady=4)
        self.status=tk.StringVar()
        feedback=ttk.Label(footer,textvariable=self.status,wraplength=560)
        feedback.grid(row=1,column=0,columnspan=2,sticky='ew',pady=4)
        footer.bind('<Configure>',lambda event:feedback.configure(wraplength=max(180,footer.winfo_width()-20)))
        self.summary=tk.StringVar()
        ttk.Label(page,textvariable=self.summary,wraplength=560).grid(row=7,column=0,sticky='w',pady=8)
        ttk.Label(page,text='三点只计算工件位置和坐标轴，不标定 TCP，也不自动改变焊枪姿态。\nZ 正方向 = X × Y，请核对示意图和方向数值，确保抬升方向离开工件。\n“应用”写入本软件的机器人配置和导出脚本，不创建示教器中的命名坐标。CAD 导入始终使用 WCS。',wraplength=560,style='Muted.TLabel').grid(row=8,column=0,sticky='w',pady=8)
        self.load_brand()
        self.brand_trace=app.robot_brand.trace_add('write',self.switch_brand)
        self.poll_id=self.after(100,self.poll)

    @staticmethod
    def point(value):
        parts=value.replace('，',',').split(',')
        if len(parts)!=3:raise ValueError('每个点请填写 X,Y,Z 三个数值，单位 mm')
        import math
        result=tuple(float(v.strip()) for v in parts)
        if not all(math.isfinite(v) for v in result):raise ValueError('坐标必须是有限数值')
        return result

    def values(self):return [var.get() for var in self.point_vars]

    def context(self,c):
        return [c.host,c.port,c.state_port,c.tcp_mode,list(c.tcp) if c.tcp_mode=='configured' else []]

    def load_brand(self):
        self.loading=True
        record=self.records.get(self.current,{})
        if not isinstance(record,dict):record={}
        points=record.get('points',['','',''])
        if not isinstance(points,list) or len(points)!=3:points=['','','']
        for var,value in zip(self.point_vars,points):var.set(value if isinstance(value,str) else '')
        self.offsets=record.get('offsets',[None]*3)
        if not isinstance(self.offsets,list) or len(self.offsets)!=3:self.offsets=[None]*3
        self.point_contexts=record.get('point_contexts',[record.get('context')]*3)
        if not isinstance(self.point_contexts,list) or len(self.point_contexts)!=3:self.point_contexts=[None]*3
        self.heading.set(self.current+' · 三点示教工件坐标')
        self.loading=False;self.changed()

    def switch_brand(self,*args):
        target=self.app.robot_brand.get()
        if target==self.current:return
        self.snapshots[self.current]=(self.values(),self.offsets,self.point_contexts)
        self.current=target
        self.load_brand()
        if target in self.snapshots:
            points,offsets,contexts=self.snapshots[target]
            self.loading=True
            for var,value in zip(self.point_vars,points):var.set(value)
            self.loading=False;self.offsets=offsets;self.point_contexts=contexts;self.changed()

    def changed(self,index=None):
        if self.loading:return
        if index is not None:self.offsets[index]=None;self.point_contexts[index]=None
        valid=[]
        for i,var in enumerate(self.point_vars):
            try:self.point(var.get());ok=True
            except ValueError:ok=False
            valid.append(ok)
            self.step_labels[i].set('{} {} {}'.format(i+1,('原点 O','X方向','XY平面')[i],'✓' if ok else '○'))
            self.badges[i].set('已填写基座 TCP 坐标（mm）' if ok else '待记录，也可手动填写 X,Y,Z（mm）')
        for i,button in enumerate(self.buttons):
            button.configure(state='normal' if not self.busy and all(valid[:i]) else 'disabled')
        self.apply_button.configure(state='normal' if all(valid) and not self.busy else 'disabled')
        record=self.records.get(self.current,{})
        c=self.app.robot_configs[self.current]
        applied=(isinstance(record,dict) and record.get('points')==self.values()
                 and record.get('frame')==list(c.frame) and record.get('context')==self.context(c))
        if self.busy:self.status.set('正在只读采样 TCP，请保持焊枪静止…')
        elif applied:self.status.set('✓ 三点工件坐标已应用并保存；启动、预览和导出均使用该坐标。')
        elif any(var.get().strip() for var in self.point_vars):
            self.status.set('三点尚未应用。请完成记录并点击“计算并应用”；应用前禁止启动或导出，避免沿用旧坐标。')
        else:self.status.set('从第 1 点开始。当前脚本仍使用机器人设置中已有的工件坐标。')
        self.draw_diagram()

    def focus_point(self,index):
        self.app.workspace_tabs.select(self)
        def focus():
            height=max(self.content.winfo_height(),1)
            self.canvas.yview_moveto(max(0,(self.cards[index].winfo_y()-12)/height))
            self.entries[index].focus_set()
        self.after_idle(focus)

    def editable(self):
        if self.busy:return False
        if not self.app.can_replan():
            self.status.set('当前任务未停止，请先停止后再记录或应用工件坐标。');return False
        return True

    def draw_diagram(self):
        canvas=self.diagram;canvas.delete('all')
        axes={'x':(1,0,0),'y':(0,1,0),'z':(0,0,1)}
        try:
            frame,axes=teach_frame([self.point(v) for v in self.values()],self.current)
            self.summary.set('原点（基座 mm）：'+', '.join('{:.3f}'.format(v) for v in frame[:3])+'\n'+
                '\n'.join('{} 正方向（基座）：({:.4f}, {:.4f}, {:.4f})'.format(k.upper(),*axes[k]) for k in ('x','y','z')))
        except ValueError:self.summary.set('三个有效点齐全后显示计算出的 X/Y/Z 正方向。')
        w=max(canvas.winfo_width(),340);cx,cy=w*.42,90
        canvas.create_text(10,12,text='右手坐标：X × Y = Z（固定观察方向）',anchor='w',fill='#64748b')
        canvas.create_oval(cx-4,cy-4,cx+4,cy+4,fill='#172b46')
        canvas.create_text(cx-12,cy+10,text='O')
        from frame_teaching import project_axis
        # Faint base axes distinguish camera projection from frame handedness.
        for vector,label in [((1,0,0),'基座X'),((0,1,0),'基座Y'),((0,0,1),'基座Z')]:
            dx,dy=project_axis(vector,58)
            canvas.create_line(cx,cy,cx+dx,cy+dy,fill='#cbd5e1',dash=(3,3))
            canvas.create_text(cx+dx*1.4,cy+dy*1.4,text=label,fill='#94a3b8',anchor='e' if dx<0 else 'w',font=('TkDefaultFont',8))
        for key,color in [('x','#dc2626'),('y','#16a34a'),('z','#2563eb')]:
            dx,dy=project_axis(axes[key],48)
            canvas.create_line(cx,cy,cx+dx,cy+dy,fill=color,width=3,arrow='last')
            canvas.create_text(cx+dx+(-8 if dx<0 else 8),cy+dy,text=key.upper()+'+',fill=color,anchor='e' if dx<0 else 'w')
        canvas.create_text(10,151,text='沿 +Z 朝原点看：+X 转向 +Y 为逆时针。',anchor='w',fill='#64748b')

    def capture(self,index):
        if not self.editable():return
        try:
            c=replace(self.app.current_robot_config(check_teaching=False));c.validate(network=True)
            for value in self.values()[:index]:self.point(value)
        except Exception as exc:self.status.set(str(exc));return
        brand=self.current;context=self.context(c);self.busy=True;self.changed()
        def worker():
            try:result=(True,read_teaching_sample(c))
            except Exception as exc:result=(False,str(exc))
            self.results.put((brand,context,index,result))
        threading.Thread(target=worker,daemon=True).start()

    def poll(self):
        try:
            brand,context,index,(ok,result)=self.results.get_nowait()
            self.busy=False
            if brand!=self.current or context!=self.context(self.app.current_robot_config(check_teaching=False)):
                self.changed();self.status.set('品牌、IP 或 TCP 配置已变化，本次读数已丢弃，请重新记录。')
            elif not ok:
                self.changed();self.status.set('记录失败：'+result+'。已有点未覆盖。')
            else:
                point,offset=result
                if any(old is not None and old!=context for i,old in enumerate(self.point_contexts) if i!=index):
                    self.changed();self.status.set('其他点来自不同的机器人连接或 TCP 配置，请清空三点后重新示教。')
                elif any(old is not None and not same_tcp(old,offset,brand) for i,old in enumerate(self.offsets) if i!=index):
                    self.changed();self.status.set('三点采样使用的 TCP 不一致，请统一 TCP 后清空重教。')
                else:
                    self.point_vars[index].set(', '.join('{:.6f}'.format(v) for v in point))
                    self.offsets[index]=offset
                    self.point_contexts[index]=context
                    self.badges[index].set('✓ 已从控制器读取基座 TCP 坐标（mm）')
                    self.status.set('第 {} 点已记录；{}'.format(index+1,'请移动到下一点后记录。' if index<2 else '请核对坐标轴方向，然后计算并应用。'))
        except queue.Empty:pass
        except Exception as exc:
            self.busy=False;self.changed();self.status.set('记录失败：'+str(exc))
        self.poll_id=self.after(100,self.poll)

    def require_applied(self,c):
        if self.busy:raise ValueError('正在记录示教点，请等待采样完成')
        if not any(v.get().strip() for v in self.point_vars):return
        record=self.records.get(self.current,{})
        if (c.brand!=self.current or not isinstance(record,dict) or record.get('points')!=self.values()
                or record.get('frame')!=list(c.frame) or record.get('context')!=self.context(c)):
            self.app.workspace_tabs.select(self)
            raise ValueError('三点示教有未应用的修改或机器人配置已变化，请核对并计算应用，或清空三点记录后使用手动坐标')

    def apply(self):
        if not self.editable():return False
        try:
            old=self.app.current_robot_config(check_teaching=False)
            if any(context is not None and context!=self.context(old) for context in self.point_contexts):
                raise ValueError('已有点对应的机器人连接或 TCP 配置发生变化，请清空三点后重新示教')
            frame,axes=teach_frame([self.point(v) for v in self.values()],self.current)
            c=replace(old,frame=frame,verified=False)
            profiles=dict(self.app.robot_configs);profiles[self.current]=c
            save_profiles(profiles)
            self.app.robot_configs=profiles
            window=self.app.robot_window
            if window is not None and window.winfo_exists() and window.current==self.current:
                window.vars['frame'].set(', '.join(str(v) for v in frame))
            self.point_contexts=[self.context(c)]*3
            self.records[self.current]={'points':self.values(),'frame':list(frame),'context':self.context(c),'offsets':self.offsets,'point_contexts':self.point_contexts}
            self.changed()
            try:save_ui_setting('teaching_profiles',self.records)
            except OSError as exc:self.status.set('坐标已应用并保存；示教点记录保存失败：'+str(exc))
            self.app.profile_error=''
            return True
        except Exception as exc:
            self.status.set('未应用：'+str(exc));return False

    def clear(self):
        if not self.editable():return
        self.records.pop(self.current,None);self.snapshots.pop(self.current,None)
        self.loading=True
        for var in self.point_vars:var.set('')
        self.loading=False;self.offsets=[None]*3;self.point_contexts=[None]*3;self.changed()
        try:save_ui_setting('teaching_profiles',self.records)
        except OSError as exc:self.status.set('已清空；无法保存记录：'+str(exc))

    def destroy(self):
        if hasattr(self,'poll_id'):self.after_cancel(self.poll_id)
        if hasattr(self,'brand_trace'):self.app.robot_brand.trace_remove('write',self.brand_trace)
        super().destroy()
