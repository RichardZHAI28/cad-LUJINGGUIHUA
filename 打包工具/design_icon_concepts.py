"""Ten original vector Windows shortcut icon proposals; no application changes."""
import sys,math,json,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
sys.path[:0]=[str(ROOT/'工程'/'.vendor'),str(ROOT/'工程')]
import matplotlib
matplotlib.use('Agg')
from matplotlib.figure import Figure
from matplotlib.patches import FancyBboxPatch,Circle,Polygon,PathPatch
from matplotlib.path import Path as MPath
from matplotlib.textpath import TextPath
from matplotlib.font_manager import FontProperties
from matplotlib.transforms import Affine2D
from PIL import Image,ImageDraw,ImageFont

OUT=ROOT/'输出结果'/'快捷图标方案'/'20261108'
OUT.mkdir(parents=True,exist_ok=True)
matplotlib.rcParams['svg.hashsalt']='cadweld-20261108'
WHITE='#f8fbff';BLUE='#2563eb';NAVY='#142b49';CYAN='#52d8ff';ORANGE='#ff923b'
FONT=Path('C:/Windows/Fonts/msyh.ttc');BOLD=Path('C:/Windows/Fonts/msyhbd.ttc')


class Icon:
    def __init__(self):
        self.fig=Figure(figsize=(4,4),dpi=256)
        self.ax=self.fig.add_axes((0,0,1,1));self.ax.set_xlim(0,100);self.ax.set_ylim(100,0)
        self.ax.set_aspect('equal');self.ax.axis('off')
        self.layer=0

    def z(self):
        self.layer+=1
        return self.layer

    def box(self,x,y,w,h,r,fill,edge=None,width=1,alpha=1):
        self.ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle='round,pad=0,rounding_size='+str(r),facecolor=fill,
            edgecolor=edge or 'none',linewidth=width*2.88,alpha=alpha,zorder=self.z()))

    def tile(self,color):
        self.box(5,7,90,90,21,'#0c2340',alpha=.12)
        self.box(4,4,92,92,21,color)

    def poly(self,points,color,edge=None,width=1):
        self.ax.add_patch(Polygon(points,closed=True,facecolor=color,edgecolor=edge or 'none',linewidth=width*2.88,joinstyle='round',zorder=self.z()))

    def circle(self,x,y,r,color,edge=None,width=1):
        self.ax.add_patch(Circle((x,y),r,facecolor=color,edgecolor=edge or 'none',linewidth=width*2.88,zorder=self.z()))

    def line(self,points,color=WHITE,width=6,alpha=1,dashes=None):
        x,y=zip(*points)
        line,=self.ax.plot(x,y,color=color,linewidth=width*2.88,solid_capstyle='round',solid_joinstyle='round',alpha=alpha,zorder=self.z())
        if dashes:line.set_dashes(dashes)

    def path(self,commands,color=WHITE,width=6,fill='none'):
        verts=[];codes=[]
        for item in commands:
            if item[0]=='M':verts.append(item[1:]);codes.append(MPath.MOVETO)
            elif item[0]=='L':verts.append(item[1:]);codes.append(MPath.LINETO)
            elif item[0]=='C':
                verts.extend([item[1:3],item[3:5],item[5:7]]);codes.extend([MPath.CURVE4]*3)
            elif item[0]=='Z':verts.append(verts[0]);codes.append(MPath.CLOSEPOLY)
        self.ax.add_patch(PathPatch(MPath(verts,codes),facecolor=fill,edgecolor=color,linewidth=width*2.88,capstyle='round',joinstyle='round',zorder=self.z()))

    def spark(self,x,y,r=8,color=ORANGE):
        points=[]
        for i in range(8):
            a=i*math.pi/4;radius=r if i%2==0 else r*.28
            points.append((x+radius*math.cos(a),y+radius*math.sin(a)))
        self.poly(points,color)

    def save(self,name,title):
        self.fig.savefig(OUT/(name+'.svg'),transparent=True,metadata={'Title':title,'Date':None})
        self.fig.savefig(OUT/(name+'.png'),transparent=True)
        png=Image.open(OUT/(name+'.png')).convert('RGBA')
        png.save(OUT/(name+'.ico'),sizes=[(s,s) for s in (16,24,32,48,64,128,256)])
        return png


def arc_path(i):
    i.tile(NAVY)
    i.path([('M',24,73),('C',12,45,28,19,54,26),('C',76,31,84,49,73,62)],WHITE,8)
    i.circle(24,73,6,CYAN);i.circle(35,31,4.5,CYAN)
    i.circle(73,62,11,NAVY);i.spark(73,62,12)
    i.circle(83,36,2.3,ORANGE)


def robot_arm(i):
    i.tile('#e6f1ff')
    i.box(19,78,39,9,3,NAVY)
    i.line([(34,77),(34,63),(47,34),(70,44),(64,60)],BLUE,15)
    i.line([(35,62),(47,34)],'#63b5ff',5)
    for x,y in [(34,63),(47,34),(70,44)]:
        i.circle(x,y,7,NAVY);i.circle(x,y,3.5,WHITE)
    i.line([(64,59),(71,68)],NAVY,8)
    i.line([(72,78),(83,78)],NAVY,3)
    i.spark(75,73,8)


def cad_sheet(i):
    i.tile('#153e70')
    i.path([('M',25,16),('L',61,16),('L',77,32),('L',77,83),('L',25,83),('Z',)],'#8ddcff',3,fill='#1a4b82')
    i.poly([(61,16),(61,32),(77,32)],CYAN)
    for x in (36,48,60):i.line([(x,39),(x,74)],CYAN,1,alpha=.18)
    for y in (43,54,65):i.line([(31,y),(69,y)],CYAN,1,alpha=.18)
    i.path([('M',61,45),('C',45,34,32,51,40,64),('C',46,73,58,71,64,61)],WHITE,5)
    i.circle(64,61,4.5,ORANGE)


def single_letter(i):
    i.tile(BLUE)
    i.line([(23,77),(50,24),(77,77)],'#174ab6',14)
    i.line([(23,77),(50,24),(77,77)],WHITE,9)
    i.line([(34,57),(66,57)],WHITE,8)
    i.circle(50,24,4.5,CYAN);i.circle(23,77,4.5,CYAN)
    i.spark(77,77,9,ORANGE)


def three_points(i):
    i.tile('#f1f8ff')
    for x in (28,49,70):i.line([(x,19),(x,82)],'#dbe7f4',1.2)
    for y in (30,51,72):i.line([(18,y),(84,y)],'#dbe7f4',1.2)
    i.line([(40,25),(78,73)],'#a5b6cc',2.6,dashes=[2.5,2.5])
    i.line([(27,73),(78,73)],BLUE,6)
    i.line([(27,73),(40,25)],'#0e9f8d',6)
    for x,y,c in [(27,73,ORANGE),(78,73,BLUE),(40,25,'#0e9f8d')]:
        i.circle(x,y,8,WHITE);i.circle(x,y,5.7,c)


def fill_route(i):
    i.tile('#0e3545')
    i.box(17,18,66,64,13,'#174a60')
    i.path([('M',28,28),('L',70,28),('C',83,28,83,42,70,42),('L',30,42),
        ('C',17,42,17,56,30,56),('L',70,56),('C',83,56,83,70,70,70),('L',28,70)],'#77f2e3',6)
    i.circle(28,28,4,WHITE);i.circle(28,70,5,ORANGE)


def torch_focus(i):
    i.tile('#edf3fc')
    i.circle(43,60,26,'none',BLUE,3.5)
    i.circle(43,60,14,'none','#7ab7ff',4)
    i.line([(13,60),(24,60)],NAVY,3)
    i.line([(43,80),(43,90)],NAVY,3)
    i.poly([(58,16),(82,36),(66,53),(45,34)],NAVY)
    i.line([(59,24),(73,36)],CYAN,4)
    i.line([(51,43),(42,54)],NAVY,8)
    i.spark(40,59,9)


def double_contour(i):
    i.tile('#29204f')
    i.box(20,17,60,66,23,'none',WHITE,5)
    i.box(34,31,32,38,13,'none','#a5a1ff',4.5)
    i.circle(75,71,9,'#29204f');i.spark(75,71,11,'#ffb155')


def workpiece(i):
    i.tile('#e7f3ff')
    i.poly([(50,18),(80,35),(50,53),(20,35)],'#51c9ff')
    i.poly([(20,35),(50,53),(50,84),(20,66)],BLUE)
    i.poly([(50,53),(80,35),(80,66),(50,84)],NAVY)
    i.line([(50,55),(50,81)],ORANGE,5)
    i.spark(50,52,9,'#ffb45c')


def weld_stamp(i):
    i.tile('#d5522d')
    i.box(11,11,78,78,14,'none','#ffb18b',1.5)
    text=TextPath((0,0),'焊',size=1,prop=FontProperties(fname=str(BOLD)))
    b=text.get_extents();s=min(62/b.width,62/b.height)
    transform=Affine2D().translate(-b.xmin,-b.ymax).scale(s,-s).translate(19+(62-b.width*s)/2,19+(62-b.height*s)/2)
    i.ax.add_patch(PathPatch(text.transformed(transform),facecolor='#fffaf0',edgecolor='none',zorder=i.z()))
    i.spark(83,19,6,'#ffd28b')


CONCEPTS=[
 ('01_arc_path','轨迹焊弧','路径节点 × 焊接火花',arc_path),
 ('02_robot_arm','机器人焊接','机械臂 × 焊枪',robot_arm),
 ('03_cad_sheet','CAD 图纸','工程图纸 × 加工轨迹',cad_sheet),
 ('04_single_letter','单道字形','字母 A × 中心线',single_letter),
 ('05_three_points','三点定位','原点 × X/Y 方向',three_points),
 ('06_fill_route','往复排道','连续轨迹 × 实心填充',fill_route),
 ('07_torch_focus','精准焊接','焊枪 × 定位中心',torch_focus),
 ('08_double_contour','内外轮廓','双层边界 × 焊接',double_contour),
 ('09_workpiece','立体工件','CAD 实体 × 焊缝',workpiece),
 ('10_weld_stamp','焊字徽章','中文识别 × 工业印章',weld_stamp),
]


def font(size,bold=False):return ImageFont.truetype(str(BOLD if bold else FONT),size)


def centered(draw,text,x,y,f,color):
    b=draw.textbbox((0,0),text,font=f)
    draw.text((round(x-(b[2]-b[0])/2),y),text,font=f,fill=color)


def board(images):
    sheet=Image.new('RGB',(2304,1360),'#edf2f8');draw=ImageDraw.Draw(sheet)
    draw.text((52,36),'焊接轨迹工作台  /  快捷图标 · 10 种方案',font=font(44,True),fill=NAVY)
    draw.text((54,104),'不同图形方向，统一检查桌面缩小后的辨识度。按编号选择即可。',font=font(24),fill='#62748b')
    card_w,card_h=424,526
    for idx,((name,title,desc,_),png) in enumerate(zip(CONCEPTS,images)):
        x=52+(idx%5)*444;y=170+(idx//5)*548
        draw.rounded_rectangle((x,y,x+card_w,y+card_h),radius=24,fill='white',outline='#dae4ef',width=2)
        draw.text((x+21,y+16),name[:2],font=font(30,True),fill=BLUE)
        preview=png.resize((238,238),Image.Resampling.LANCZOS)
        sheet.paste(preview,(x+93,y+59),preview)
        centered(draw,title,x+card_w/2,y+311,font(28,True),NAVY)
        centered(draw,desc,x+card_w/2,y+356,font(20),'#62748b')
        for tray_x,bg in [(x+19,'#f1f5fa'),(x+218,'#142b49')]:
            draw.rounded_rectangle((tray_x,y+405,tray_x+185,y+483),radius=12,fill=bg)
            for size,dx in ((32,27),(48,105)):
                thumb=png.resize((size,size),Image.Resampling.LANCZOS)
                sheet.paste(thumb,(tray_x+dx,y+405+(78-size)//2),thumb)
        centered(draw,'浅色桌面 32 / 48 px',x+111,y+490,font(14),'#62748b')
        centered(draw,'深色桌面 32 / 48 px',x+310,y+490,font(14),'#62748b')
    draw.text((54,1299),'每款均已导出 SVG、透明 PNG 和 Windows 多尺寸 ICO。编号不属于图标本体。',font=font(23),fill='#62748b')
    sheet.save(OUT/'快捷图标_10种方案.png')


def main():
    images=[];manifest=[]
    for name,title,desc,draw in CONCEPTS:
        icon=Icon();draw(icon);images.append(icon.save(name,title))
        with Image.open(OUT/(name+'.ico')) as ico:
            sizes=sorted(ico.ico.sizes())
            assert sizes==[(s,s) for s in (16,24,32,48,64,128,256)]
        assert images[-1].getpixel((0,0))[3]==0
        manifest.append({'id':name[:2],'title':title,'concept':desc,'svg':name+'.svg','png':name+'.png','ico':name+'.ico','ico_sizes':[s[0] for s in sizes]})
    board(images)
    (OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# 快捷图标：10 种方案','','原创矢量方案，供选择。每款 PNG 为 1024×1024 透明背景，ICO 包含 16/24/32/48/64/128/256 像素；SVG 可继续编辑。当前程序图标尚未替换。','','| 编号 | 名称 | 设计方向 |','|---|---|---|']
    lines.extend('| {} | {} | {} |'.format(row['id'],row['title'],row['concept']) for row in manifest)
    lines+=['','优先推荐：01（软件综合定位）、02（机器人业务）、09（CAD 与焊接结合）。10 更适合突出中文“焊”字。','',
        '桌面小图见总览各卡片底部的 32px、48px 浅色/深色预览；选定编号后可接入程序窗口、EXE、安装器和快捷方式。']
    (OUT/'方案说明.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    archive=OUT.parent/'快捷图标_十种方案_20261108.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as bundle:
        for p in sorted(OUT.iterdir()):
            if p.is_file():bundle.write(p,p.name)
    print(json.dumps({'icons':len(manifest),'validated_sizes':7,'overview':str(OUT/'快捷图标_10种方案.png'),'archive':str(archive)},ensure_ascii=True))


if __name__=='__main__':main()
