@echo off
rem 一键：认证 -> 开自启动 -> 后台守护（无窗口）
rem 双击运行即可，需要已经跑过 campusnet init

setlocal
cd /d "%~dp0\.."

where python >nul 2>nul
if errorlevel 1 (
    echo 找不到 python，请先把 Python 加进 PATH
    pause
    exit /b 1
)

echo [1/3] 认证测试...
python -m campusnet login
if errorlevel 1 (
    echo.
    echo 认证失败，先修好再开自启动。排障：python -m campusnet doctor
    pause
    exit /b 1
)

echo.
echo [2/3] 开启开机自启动...
python -m campusnet autostart on

echo.
echo [3/3] 启动后台守护...
start "" pythonw -m campusnet daemon --quiet

echo.
echo 完成。状态：python -m campusnet status
pause
