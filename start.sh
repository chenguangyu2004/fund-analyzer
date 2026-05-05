#!/bin/bash

echo "===================================="
echo "    基金分析App - 启动脚本"
echo "===================================="
echo ""

# 检查是否需要重启
if [ "$1" == "restart" ]; then
    echo "[模式] 重启模式 - 停止旧服务器..."
    # 只停止占用5000端口的进程
    lsof -ti:5000 | xargs kill -9 2>/dev/null
    sleep 2
    echo ""
    echo "旧服务器已停止"
    echo ""
fi

echo "[1/2] 检查并安装依赖..."
pip3 install -r requirements.txt

if [ $? -ne 0 ]; then
    echo ""
    echo "❌ 依赖安装失败，请检查网络连接或Python环境"
    exit 1
fi

echo ""
echo "[2/2] 启动应用..."
echo ""
echo "🚀 应用正在启动..."
echo "📱 请在浏览器中访问: http://127.0.0.1:5000"
echo ""
echo "按 Ctrl+C 停止应用"
echo ""
echo "[重启提示] 修改代码后，运行: ./start.sh restart"
echo ""

python3 app.py
