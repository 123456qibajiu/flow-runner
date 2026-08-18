@echo off
chcp 65001 >nul
echo 正在安装 PyInstaller...
pip install pyinstaller
echo.
echo 正在打包 exe...
pyinstaller --onefile --windowed --name "流程自动化工具" main.py
echo.
echo 打包完成！exe 在 dist\ 目录下
pause
