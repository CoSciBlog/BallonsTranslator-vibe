<i>如果构建不成功也可以直接跑源码</i>

![录屏2023-09-11 14 26 49](https://github.com/hyrulelinks/BallonsTranslator/assets/134026642/647c0fa0-ed37-49d6-bbf4-8a8697bc873e)

```
# 第1步：打开终端并确保当前终端窗口的Python大版本号是3.12，可以用下面的命令确认版本号
python3 -V
# 如果没有安装Python 3.12，可以通过Homebrew安装
brew install python@3.12 python-tk@3.12

# 第2步：克隆仓库并进入仓库工作目录
git clone -b dev https://github.com/dmMaze/BallonsTranslator.git
cd BallonsTranslator

# 第3步：创建和启用 Python 3.12 虚拟环境
python3 -m venv venv
source venv/bin/activate

# 第4步：安装依赖
pip3 install -r requirements.txt

# 第5步：源码运行程序，会自动下载 data 文件，每个文件在20-400MB左右，合计大约1.67GB，需要比较稳定的网络，如果下载报错，请重复运行下面的命令直至不再下载报错并启动程序
# 下载完毕后运行下面的命令，如果正常运行且未报错，则继续进入打包应用程序的步骤
python3 launch.py

# 第6步：下载macos_arm64_patchmatch_libs.7z到项目根目录下的'.btrans_cache'隐藏文件夹
# 该步骤是为了防止打包好的应用程序首次启动时重新下载macos_arm64_patchmatch_libs.7z导致启动失败（大概率）
mkdir ./.btrans_cache
curl -L https://github.com/dmMaze/PyPatchMatchInpaint/releases/download/v1.0/macos_arm64_patchmatch_libs.7z -o ./.btrans_cache/macos_arm64_patchmatch_libs.7z

# 第7步：下载微软雅黑字体并放到fonts文件夹下，该步骤为可选项，不影响打包，只影响字体报错信息

# 第8步：构建 macOS 应用程序中途 sudo 命令需要输入开机密码授予权限
# 安装打包工具pyinstaller
pip3 install pyinstaller
# 删除MacOS下特有的.DS_Store文件，这些文件可能导致打包失败（中概率）
sudo find ./ -name '.DS_Store' -delete
# 开始打包.app应用程序
sudo pyinstaller launch.spec
```
> 📌打包好的应用在`./data/BallonsTranslator/dist/BallonsTranslator.app`，将应用拖到 macOS 的应用程序文件夹即完成安装，开箱即用，不需要另外配置 Python 环境。 