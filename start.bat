@echo off
chcp 65001 >nul
echo ====================================
echo     基金分析App - 启动脚本
echo ====================================
echo.

REM 检查是否需要重启
if "%1"=="restart" (
    echo [模式] 重启模式 - 停止旧服务器...
    taskkill /F /IM python.exe >nul 2>&1
    timeout /t 2 /nobreak >nul
    echo.
    echo 旧服务器已停止
    echo.
) else (
    echo [模式] 初次启动 - 检查依赖...
    pip install -r requirements.txt

    if %errorlevel% neq 0 (
        echo.
        echo [X] 依赖安装失败，请检查网络连接或Python环境
        pause
        exit /b 1
    )
)

echo.
echo ====================================
echo [2/2] 启动应用...
echo ====================================
echo.
echo [启动中] 应用正在启动...
echo [访问地址] http://127.0.0.1:5000
echo.
echo [提示] 按 Ctrl+C 停止应用
echo [重启提示] 修改代码后，运行: start.bat restart
echo.

python app.py

pause
