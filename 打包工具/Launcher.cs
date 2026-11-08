using System;
using System.IO;
using System.Linq;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Windows.Forms;
class Launcher {
 [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)]static extern bool DefineDosDevice(uint flags,string name,string target);
 static string Quote(string value){return "\""+value.Replace("\"","\\\"")+"\"";}
 [STAThread] static int Main(string[] args){
  string mapping=null,target=null;
  try{
   string root=AppDomain.CurrentDomain.BaseDirectory.TrimEnd('\\');
   string launchRoot=root;
   if(root.Any(ch=>ch>127)){
    string[] used=Environment.GetLogicalDrives();
    for(char drive='Z';drive>='D';drive--){string name=drive+":";if(!used.Any(p=>p.StartsWith(name,StringComparison.OrdinalIgnoreCase))){
     target="\\??\\"+root;
     if(DefineDosDevice(9,name,target)){mapping=name;launchRoot=name+"\\";break;}
    }}
    if(mapping==null)throw new Exception("无法为中文目录建立兼容路径，请将程序安装到英文路径。");
   }
   string exe=Path.Combine(launchRoot,"CadWeldCore.exe");
   if(!File.Exists(exe))throw new Exception("程序文件缺失，请完整解压或重新安装。");
   ProcessStartInfo info=new ProcessStartInfo(exe,String.Join(" ",args.Select(Quote))){UseShellExecute=false,CreateNoWindow=true,WorkingDirectory=launchRoot};
   using(Process child=Process.Start(info)){child.WaitForExit();return child.ExitCode;}
  }catch(Exception ex){MessageBox.Show(ex.Message,"焊接轨迹工作台启动失败");return 1;}
  finally{if(mapping!=null)DefineDosDevice(15,mapping,target);}
 }
}
