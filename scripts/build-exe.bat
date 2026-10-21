@echo off
rem 打包成 exe（Windows）。产物：dist\auto-net\
rem 需要 Python 3.8+，首次运行会自动建 .venv 并装 pyinstaller

setlocal
cd /d "%~dp0\.."

if not exist ".venv\Scripts\python.exe" (
    echo [1/3] 创建虚拟环境 .venv ...
    python -m venv .venv || goto :fail
) else (
    echo [1/3] 复用已有 .venv
)

echo [2/3] 安装 PyInstaller ...
".venv\Scripts\python.exe" -m pip install -q --upgrade pip
".venv\Scripts\python.exe" -m pip install -q pyinstaller || goto :fail

echo [3/3] 开始打包 ...
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean "packaging\campusnet.spec" || goto :fail

echo.
echo 打包完成：
echo   dist\auto-net\campusnet.exe         控制台版，日常用
echo   dist\auto-net\campusnet-daemon.exe  无窗口版，开机自启用
echo.
echo 快速验证： dist\auto-net\campusnet.exe --version
exit /b 0

:fail
echo.
echo 打包失败，看上面的报错。
exit /b 1
