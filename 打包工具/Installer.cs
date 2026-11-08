using System;
using System.IO;
using System.IO.Compression;
using System.Reflection;
using System.Diagnostics;
using System.Drawing;
using System.Windows.Forms;
using Microsoft.Win32;

class Installer {
 const string Id="CadWeldPlanner-1.0";
 const string Key="Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\CadWeldPlanner";
 static string Target;
 static bool Silent;
 static bool ExtractOnly;
 [STAThread] static int Main(string[] args) {
  Application.EnableVisualStyles();
  try {
   if(args.Length>0 && args[0]=="--uninstall")return Uninstall();
   if(args.Length==2 && args[0]=="--remove")return RemoveInstalled(args[1]);
   Target=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"Programs","CadWeldPlanner");
   foreach(string a in args){if(a=="/SILENT")Silent=true;if(a.StartsWith("/EXTRACT=")){ExtractOnly=true;Silent=true;Target=a.Substring(9).Trim('"');}if(a.StartsWith("/DIR="))Target=a.Substring(5).Trim('"');}
   if(Silent){Install(false);return 0;}
   Form f=new Form();f.Icon=Icon.ExtractAssociatedIcon(Assembly.GetExecutingAssembly().Location);f.Text="焊接轨迹工作台 · 安装";f.ClientSize=new Size(610,320);f.StartPosition=FormStartPosition.CenterScreen;f.FormBorderStyle=FormBorderStyle.FixedDialog;f.MaximizeBox=false;f.Font=new Font("Microsoft YaHei UI",10);
   Label title=new Label();title.Text="安装焊接轨迹工作台";title.Font=new Font(f.Font.FontFamily,17,FontStyle.Bold);title.SetBounds(24,22,550,38);f.Controls.Add(title);
   Label desc=new Label();desc.Text="Windows 64 位 · 包含 Python 运行环境\n安装后可离线运行，支持 UR / ELITE CS/ES 脚本生成。";desc.SetBounds(24,70,550,55);f.Controls.Add(desc);
   TextBox path=new TextBox();path.Text=Target;path.SetBounds(24,145,460,30);f.Controls.Add(path);
   Button browse=new Button();browse.Text="浏览…";browse.SetBounds(490,143,94,32);browse.Click+=(s,e)=>{using(FolderBrowserDialog d=new FolderBrowserDialog()){if(d.ShowDialog()==DialogResult.OK)path.Text=Path.Combine(d.SelectedPath,"CadWeldPlanner");}};f.Controls.Add(browse);
   CheckBox desktop=new CheckBox();desktop.Text="创建桌面快捷方式";desktop.Checked=true;desktop.SetBounds(24,188,350,28);f.Controls.Add(desktop);
   Label status=new Label();status.Text="安装仅作用于当前用户，无需管理员权限。";status.SetBounds(24,230,550,25);f.Controls.Add(status);
   Button install=new Button();install.Text="安装";install.SetBounds(450,266,134,34);install.Click+=(s,e)=>{install.Enabled=false;browse.Enabled=false;status.Text="正在解压安装，请稍候…";Application.DoEvents();try{Target=path.Text;Install(desktop.Checked);MessageBox.Show("安装完成。请从开始菜单或安装目录启动。\n机器人标定参数需要在新电脑重新设置。","安装完成");f.Close();}catch(Exception ex){MessageBox.Show(ex.Message,"安装失败");install.Enabled=true;browse.Enabled=true;}};f.Controls.Add(install);
   Application.Run(f);return 0;
  }catch(Exception ex){if(Silent)File.WriteAllText(Path.Combine(Path.GetTempPath(),"CadWeldPlanner-install-error.txt"),ex.ToString());else MessageBox.Show(ex.ToString(),"安装失败");return 1;}
 }
 static string SafeTarget(string value) {
  string p=Path.GetFullPath(value).TrimEnd(Path.DirectorySeparatorChar);
  if(p.Length<10 || p==Path.GetPathRoot(p).TrimEnd('\\'))throw new Exception("请选择专用的程序安装文件夹。");
  if(Directory.Exists(p) && Directory.GetFileSystemEntries(p).Length>0 && (!File.Exists(Path.Combine(p,".cadweld-install")) || File.ReadAllText(Path.Combine(p,".cadweld-install"))!=Id))throw new Exception("目标不是本软件专用目录，请选择新的空文件夹。");
  return p;
 }
 static void Install(bool desktop) {
  Target=SafeTarget(Target);Directory.CreateDirectory(Target);
  using(Stream stream=Assembly.GetExecutingAssembly().GetManifestResourceStream("payload.zip")) {
   if(stream==null)throw new Exception("安装包缺少程序数据。");
   using(ZipArchive zip=new ZipArchive(stream,ZipArchiveMode.Read))foreach(ZipArchiveEntry entry in zip.Entries){
    string dest=Path.GetFullPath(Path.Combine(Target,entry.FullName));
    if(!dest.StartsWith(Target+Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase))throw new Exception("安装包路径无效。");
    if(String.IsNullOrEmpty(entry.Name)){Directory.CreateDirectory(dest);continue;}
    Directory.CreateDirectory(Path.GetDirectoryName(dest));using(Stream source=entry.Open())using(FileStream file=File.Create(dest))source.CopyTo(file);
   }
  }
  File.WriteAllText(Path.Combine(Target,".cadweld-install"),Id);
  if(ExtractOnly)return;
  string executable=Path.Combine(Target,"CadWeldPlanner.exe");
  Shortcut(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Programs),"焊接轨迹工作台.lnk"),executable);
  if(desktop)Shortcut(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory),"焊接轨迹工作台.lnk"),executable);
  using(RegistryKey k=Registry.CurrentUser.CreateSubKey(Key)){
   k.SetValue("DisplayName","焊接轨迹工作台");k.SetValue("DisplayVersion","1.0.0");k.SetValue("InstallLocation",Target);k.SetValue("DisplayIcon",executable);k.SetValue("UninstallString","\""+Path.Combine(Target,"Uninstall.exe")+"\" --uninstall");k.SetValue("NoModify",1);k.SetValue("NoRepair",1);
  }
 }
 static void Shortcut(string path,string exe){
  Directory.CreateDirectory(Path.GetDirectoryName(path));
  Type type=Type.GetTypeFromProgID("WScript.Shell");dynamic shell=Activator.CreateInstance(type);dynamic link=shell.CreateShortcut(path);link.TargetPath=exe;link.WorkingDirectory=Path.GetDirectoryName(exe);link.IconLocation=exe+",0";link.Description="CAD 图纸离散与机器人焊接轨迹规划";link.Save();
 }
 static int Uninstall(){
  if(MessageBox.Show("卸载焊接轨迹工作台？用户图纸、输出和机器人配置将保留。","卸载",MessageBoxButtons.YesNo)!=DialogResult.Yes)return 0;
  string source=Assembly.GetExecutingAssembly().Location;
  string target=Path.GetDirectoryName(source);
  if(!File.Exists(Path.Combine(target,".cadweld-install")))throw new Exception("安装标识不存在，已取消卸载。");
  string temporary=Path.Combine(Path.GetTempPath(),"CadWeldUninstall-"+Guid.NewGuid().ToString("N")+".exe");File.Copy(source,temporary);
  Process.Start(new ProcessStartInfo(temporary,"--remove \""+target+"\""){UseShellExecute=false});return 0;
 }
 static int RemoveInstalled(string target){
  target=Path.GetFullPath(target).TrimEnd('\\');
  if(target.Length<10 || !File.Exists(Path.Combine(target,".cadweld-install")) || File.ReadAllText(Path.Combine(target,".cadweld-install"))!=Id)throw new Exception("安装目录检查失败。");
  System.Threading.Thread.Sleep(1500);
  Directory.Delete(target,true);
  foreach(Environment.SpecialFolder folder in new[]{Environment.SpecialFolder.Programs,Environment.SpecialFolder.DesktopDirectory}){
   string shortcut=Path.Combine(Environment.GetFolderPath(folder),"焊接轨迹工作台.lnk");if(File.Exists(shortcut))File.Delete(shortcut);
  }
  Registry.CurrentUser.DeleteSubKeyTree(Key,false);
  MessageBox.Show("卸载完成。用户数据已保留。","焊接轨迹工作台");return 0;
 }
}
