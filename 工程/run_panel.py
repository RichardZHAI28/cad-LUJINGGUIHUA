"""Visible run controls, asynchronous commands, controller-confirmed status."""
import queue
import threading
import time
from dataclasses import replace
from tkinter import ttk
import tkinter as tk
from robot_control import RobotRunner,connection_report,connection_text


class RunPanel(ttk.Frame):
    def __init__(self,parent,app):
        super().__init__(parent,padding=(0,0,0,8))
        self.app=app;self.runner=RobotRunner();self.busy=False;self.polling=False;self.stopping=False;self.last_error=False
        self.events=queue.Queue();self.generation=0
        self.connection_key=None;self.connection_polling=False;self.connection_due=0
        self.start_button=ttk.Button(self,text='启动',style='Primary.TButton',command=app.start_execution)
        self.pause_button=ttk.Button(self,text='暂停',command=lambda:self.launch('pause',self.runner.pause))
        self.stop_button=ttk.Button(self,text='停止',style='Danger.TButton',command=self.stop)
        for col,button in enumerate((self.start_button,self.pause_button,self.stop_button)):
            button.grid(row=0,column=col,sticky='ew',padx=(0,6));self.columnconfigure(col,weight=1)
        self.status=tk.StringVar(value='请选择轨迹并启动；停止为程序停止。')
        self.label=ttk.Label(self,textvariable=self.status,wraplength=600)
        self.label.grid(row=2,column=0,columnspan=3,sticky='ew',pady=(4,0))
        self.connection_status=tk.StringVar(value='● 未配置机器人 IP · ELITE 脚本 30001 / 状态 30011 / 控制 29999')
        self.connection_label=ttk.Label(self,textvariable=self.connection_status,wraplength=550,foreground='#64748b')
        self.connection_label.grid(row=1,column=0,columnspan=2,sticky='ew',pady=(6,0))
        ttk.Button(self,text='刷新连接',command=lambda:setattr(self,'connection_due',0)).grid(row=1,column=2,sticky='e',pady=(6,0))
        self.bind('<Configure>',lambda e:(self.label.configure(wraplength=max(150,e.width-12)),self.connection_label.configure(wraplength=max(150,e.width*2//3-12))))
        self.after_id=self.after(100,self.poll)

    def destroy(self):
        self.after_cancel(self.after_id)
        super().destroy()

    def launch(self,kind,work):
        if self.busy and kind!='stop':return
        self.busy=True;self.generation+=1;generation=self.generation
        self.last_error=False
        self.start_button.configure(state='disabled');self.pause_button.configure(state='disabled')
        self.status.set({'start':'启动请求中…','resume':'继续请求中…','pause':'暂停请求中…','stop':'停止请求中…'}[kind])
        def worker():
            try:self.events.put((generation,kind,True,work()))
            except Exception as exc:self.events.put((generation,kind,False,str(exc)+'；未自动重试，请检查示教器。'))
        threading.Thread(target=worker,daemon=True).start()

    def start(self,config,script):
        if self.busy:return
        self.runner.cancel.clear()
        self.launch('start',lambda:self.runner.start(config,script))

    def resume(self):self.launch('resume',self.runner.resume)

    def stop(self):
        if self.stopping:return
        self.stopping=True
        self.runner.cancel.set()
        if self.runner.config is None:
            try:config=self.app.current_robot_config()
            except Exception as exc:self.stopping=False;self.status.set(str(exc));return
        else:config=None
        # Stop stays usable while a start/read request is outstanding.
        self.launch('stop',lambda:self.runner.stop(config))

    def poll(self):
        try:
            while True:
                generation,kind,success,message=self.events.get_nowait()
                if kind=='connection':
                    self.connection_polling=False
                    if generation!=self.connection_key:continue
                    if success:
                        self.connection_status.set('● '+connection_text(message))
                        self.connection_label.configure(foreground='#15803d' if message['connected'] and message['remote_ready'] else '#b45309')
                    else:
                        self.connection_status.set('● 连接失败：'+str(message));self.connection_label.configure(foreground='#b91c1c')
                elif kind=='feedback':
                    self.polling=False
                    if generation!=self.generation or self.busy:continue
                    if success:
                        state=message['state']
                        if state=='STOPPED' and self.runner.state in ('RUNNING','PAUSED','PAUSED_UNCONFIRMED'):self.runner.state='COMPLETED'
                        text={'RUNNING':'运行中','PAUSED':'控制器已暂停','STOPPED':'运行结束 / 已停止'}[state]
                        if state=='PAUSED' and self.runner.config.brand=='UR':text='UR 已暂停，请停止后重新启动；本版不自动续跑'
                        if message['emergency'] or message['protective']:text='控制器安全停止，请检查示教器'
                        if not self.last_error:self.status.set(text+' · '+self.runner.config.brand+' '+self.runner.config.host)
                    else:self.status.set('状态连接中断：'+str(message)+'；请检查示教器，不会自动重发任务。')
                elif generation==self.generation:
                    if kind=='stop':self.stopping=False
                    self.last_error=not success
                    self.busy=False;self.status.set(message)
        except queue.Empty:pass
        self.poll_connection()
        ur_paused=self.runner.state=='PAUSED' and self.runner.config is not None and self.runner.config.brand=='UR'
        self.start_button.configure(text='继续' if self.runner.state=='PAUSED' and not ur_paused else '启动',state='disabled' if self.busy or ur_paused or self.runner.state in ('RUNNING','UNKNOWN','PAUSED_UNCONFIRMED') else 'normal')
        self.pause_button.configure(state='normal' if not self.busy and self.runner.state=='RUNNING' else 'disabled')
        self.app.brand_selector.configure(state='disabled' if self.busy or self.runner.state in ('RUNNING','PAUSED','UNKNOWN','PAUSED_UNCONFIRMED') else 'readonly')
        self.app.import_button.configure(state='disabled' if self.busy or self.runner.state in ('RUNNING','PAUSED','UNKNOWN','PAUSED_UNCONFIRMED') else 'normal')
        if not self.busy and not self.polling and self.runner.config is not None:
            self.polling=True;generation=self.generation
            def feedback():
                try:self.events.put((generation,'feedback',True,self.runner.refresh()))
                except Exception as exc:self.events.put((generation,'feedback',False,str(exc)))
            threading.Thread(target=feedback,daemon=True).start()
            self.after_id=self.after(1000,self.poll)
        else:self.after_id=self.after(100,self.poll)

    def poll_connection(self):
        if not getattr(self.app,'monitor_connection',True):return
        try:
            c=replace(self.app.current_robot_config(check_teaching=False))
            key=(c.brand,c.host,c.port,c.state_port,c.dashboard_port)
        except Exception as exc:
            self.connection_key=None;self.connection_status.set('● 连接参数待填写：'+str(exc));return
        if key!=self.connection_key:
            self.connection_key=key;self.connection_due=0
            self.connection_status.set('● 检查连接…' if c.host else '● 未配置机器人 IP · 请打开机器人设置')
            self.connection_label.configure(foreground='#64748b')
        if not c.host or self.connection_polling or time.monotonic()<self.connection_due:return
        self.connection_polling=True;self.connection_due=time.monotonic()+4
        def probe():
            try:self.events.put((key,'connection',True,connection_report(c)))
            except Exception as exc:self.events.put((key,'connection',False,str(exc)))
        threading.Thread(target=probe,daemon=True).start()
