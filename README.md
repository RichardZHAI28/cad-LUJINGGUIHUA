# CAD 焊接轨迹工作台

Python 桌面应用：从 DXF 或文字轮廓生成机器人焊接轨迹，支持 ELITE CS/ES（默认）和 UR。

继续开发请先阅读 [开发交接.md](开发交接.md)。当前中心线规则为**端面等距收缩优先**，A/M/N 的交点由偏置轮廓碰撞确定；不要恢复历史版本的“直线延长优先”。

## Windows 开发环境

```powershell
git clone https://github.com/RichardZHAI28/cad-LUJINGGUIHUA.git
cd cad-LUJINGGUIHUA
```

当前基线为 Python 3.8 x64。在 clone 后的项目根目录运行：

```powershell
py -3.8 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r 工程/requirements.txt
.\.venv\Scripts\python.exe 工程/run.py
```

测试：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s 工程 -p 'test*.py'
```

Windows 的 .vendor 二进制依赖不纳入 Git；修改过的纯 Python `工程/.vendor/py_straight_skeleton` 必须保留，已单独纳入版本控制。它不是 PyPI 原包的直接替代安装步骤；兼容说明与许可见 [工程/third_party/py_straight_skeleton](工程/third_party/py_straight_skeleton)。

ZITI1/ZITI2 需在新电脑安装或在软件内导入，仓库不包含个人字体。本机机器人配置、字体映射、导出结果、安装包及构建缓存不上传；软件会使用默认配置，新电脑需自行设置机器人参数。

## 项目结构

- `工程/`：应用、测试、示例数据与图标。
- `CAD图纸/`：项目图纸和通用示例。
- `诊断/端面收缩优先/`：当前版本测试报告与对比图；历史报告内的绝对路径属于原测试电脑。
- `打包工具/`：Windows 安装包构建源码，构建环境见该目录 README。
- `发布包/安装与迁移说明.md`：应用安装与使用迁移说明。

最新基线：111 项测试中 110 通过、1 项历史 Drawing1 样本检查跳过；当前安装包离线自检通过。几何样例检查不等于真机焊接验证。新会话须先做离线检查，机器人运动测试须有明确授权和测试环境。

## 多终端协作

每次开始前运行 `git pull --ff-only`，完成后按实际改动 `git add`、`git commit`、`git push`。遇到冲突先核对双方改动，不覆盖另一终端的工作。新开发会话先阅读开发交接文件，并在阶段完成后更新它。
