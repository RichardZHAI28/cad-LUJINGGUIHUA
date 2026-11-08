# Windows 构建

构建环境：Windows x64、系统 Python 3.8、工程/.vendor 中的运行依赖、工程/.build-tools 中的 PyInstaller。C# 安装器及中文路径启动器使用系统 .NET Framework 编译器。

运行 python 打包工具/build_release.py 构建全部产物。PyInstaller 会重建 发布包/应用文件/CadWeldPlanner，请勿往该目录存放个人数据。
仅重新生成安装器和压缩包：python 打包工具/build_release.py --repackage。

程序用户数据路径通过 runtime_paths.py 管理，打包时不包含 robot_profiles.json。测试时可通过 CAD_WELD_DATA_DIR 指定测试数据目录；独立程序支持 --self-test --report 报告路径，验证启动、三种模式和两家脚本生成，不连接机器人。

Launcher.cs 处理旧版 Tcl 在中文路径下的编码问题，仅在路径含非 ASCII 字符时临时映射空闲盘符，子进程退出后移除映射。Installer.cs 支持当前用户安装、快捷方式、卸载登记、保留用户数据，以及 /EXTRACT=专用空目录 的解压验证模式。

验证记录见 launcher-self-test.json、installed-self-test.json。尚未在另一台干净电脑上验证。安装器和程序未进行数字签名。
