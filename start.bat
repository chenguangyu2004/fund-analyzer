@echo off
chcp 65001 >nul
echo ====================================
echo     基金分析App - 启动脚本
echo ====================================
echo.

echo [1/2] 检查并安装依赖...
pip install -r requirements.txt

if %errorlevel% neq 0 (
    echo.
    echo ❌ 依赖安装失败，请检查网络连接或Python环境
    pause
    exit /b 1
)

echo.
echo [2/2] 启动应用...
echo.
echo 🚀 应用正在启动...
echo 📱 请在浏览器中访问: http://127.0.0.1:5000
echo.
echo 按 Ctrl+C 停止应用
echo.

python app.py

pause
