from flask import Flask, render_template, request, jsonify
from fund_analyzer import FundAnalyzer
import sys

app = Flask(__name__)

# 强制刷新输出
sys.stdout.reconfigure(line_buffering=True)

# 简单的日志文件写入
def log(message):
    print(message, flush=True)
    with open('h:/基金app/debug.log', 'a', encoding='utf-8') as f:
        f.write(f"{message}\n")

@app.route('/')
def index():
    """主页"""
    return render_template('index.html')

@app.route('/test')
def test():
    """测试接口"""
    log("测试接口被访问")
    return "OK"

@app.route('/api/analyze', methods=['POST'])
def analyze_fund():
    """分析基金API"""
    log("=== 收到分析请求 ===")
    try:
        data = request.get_json()
        fund_code = data.get('fund_code', '').strip()
        buy_price = float(data.get('buy_price', 0))
        shares = float(data.get('shares', 0))

        log(f"基金代码: {fund_code}, 成本: {buy_price}, 份额: {shares}")

        # 验证输入
        if not fund_code or len(fund_code) != 6 or not fund_code.isdigit():
            return jsonify({
                'success': False,
                'error': '基金代码格式错误，请输入6位数字'
            })

        if buy_price <= 0:
            return jsonify({
                'success': False,
                'error': '持仓成本必须大于0'
            })

        if shares <= 0:
            return jsonify({
                'success': False,
                'error': '持有份额必须大于0'
            })

        # 创建分析器并获取信息
        print("创建分析器...")
        analyzer = FundAnalyzer(fund_code)
        
        print("获取基金信息...")
        fund_info = analyzer.get_fund_info()
        if not fund_info:
            print("基金信息获取失败")
            return jsonify({
                'success': False,
                'error': '无法获取基金信息，请检查基金代码是否正确'
            })
        print(f"基金信息: {fund_info}")

        # 计算盈亏
        profit_loss = analyzer.calculate_profit_loss(buy_price, shares)

        # 分析策略
        strategy = analyzer.analyze_strategy()

        # 获取历史数据（可选，失败了也不影响主要功能）
        history_data = []
        try:
            print("获取历史数据...")
            history_df = analyzer.get_fund_history(30)
            if history_df is not None and len(history_df) > 0:
                history_data = [
                    {
                        'date': str(row['date']),
                        'net_value': float(row['net_value'])
                    }
                    for _, row in history_df.iterrows()
                ]
            print(f"历史数据: {len(history_data)} 条")
        except Exception as e:
            print(f"历史数据获取失败（跳过）: {e}")
            history_data = []

        # 获取前十大持仓
        holdings = []
        try:
            print("获取持仓数据...")
            holdings = analyzer._get_fund_holdings(10)
            print(f"持仓数据: {len(holdings)} 条")
        except Exception as e:
            print(f"持仓数据获取失败（跳过）: {e}")
            holdings = []

        print("=== 分析完成 ===")
        return jsonify({
            'success': True,
            'data': {
                'fund_info': fund_info,
                'profit_loss': profit_loss,
                'strategy': strategy,
                'history': history_data,
                'holdings': holdings
            }
        })

    except Exception as e:
        print(f"!!! 分析失败: {e} !!!")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': f'分析失败: {str(e)}'
        })

if __name__ == '__main__':
    print("启动Flask服务器...")
    app.run(debug=False, host='127.0.0.1', port=5000)
