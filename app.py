from flask import Flask, render_template, request, jsonify
from fund_analyzer import FundAnalyzer
from stock_analyzer import StockAnalyzer
from deepseek_analyzer import DeepSeekAnalyzer, StockNewsAnalyzer
import sys
import os

# 加载 .env 文件中的环境变量（如果存在）
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # 如果没安装 python-dotenv，使用系统环境变量

app = Flask(__name__)

# 强制刷新输出
sys.stdout.reconfigure(line_buffering=True)

# 简单的日志文件写入
def log(message):
    print(message, flush=True)
    log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'debug.log')
    with open(log_path, 'a', encoding='utf-8') as f:
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
            holdings = analyzer._get_fund_holdings(0)
            print(f"持仓数据: {len(holdings)} 条")
            
            # 有持仓数据后，重新计算实时估值（基于股票涨跌）
            if holdings and len(holdings) > 0:
                recalc_estimate = analyzer._get_realtime_estimate(holdings)
                if recalc_estimate and not fund_info.get('has_realtime'):
                    # 如果天天基金接口没返回估值，用自己计算的
                    from datetime import datetime
                    now = datetime.now()
                    fund_info['realtime_net_value'] = recalc_estimate['estimated_value']
                    fund_info['realtime_day_growth'] = recalc_estimate['estimated_growth']
                    fund_info['net_value'] = recalc_estimate['estimated_value']
                    fund_info['day_growth'] = recalc_estimate['estimated_growth']
                    fund_info['has_realtime'] = True
                    fund_info['realtime_source'] = 'holdings_calculated'
                    fund_info['nav_date'] = now.strftime('%Y-%m-%d')
                    print(f"[实时估值] 使用持仓计算: {recalc_estimate}")
                elif recalc_estimate:
                    fund_info['realtime_source'] = 'fundgz_api'
        except Exception as e:
            print(f"持仓数据获取失败（跳过）: {e}")
            holdings = []

        print("=== 分析完成 ===")
        return jsonify({
            'success': True,
            'data': {
                'fund_info': fund_info,
                'profit_loss': profit_loss,
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

@app.route('/stock')
def stock_page():
    """股票详情页面"""
    return render_template('stock.html')

@app.route('/api/stock/<stock_code>')
def get_stock_detail(stock_code):
    """获取股票详情API"""
    log(f"=== 收到股票详情请求: {stock_code} ===")
    try:
        analyzer = StockAnalyzer(stock_code)
        
        # 获取股票基本信息
        stock_info = analyzer.get_stock_info()
        if not stock_info:
            stock_info = {'name': stock_code}
        elif not stock_info.get('name'):
            stock_info['name'] = stock_code
        
        # 获取相关新闻
        log("获取股票新闻...")
        news = analyzer.get_stock_news(10)
        stock_info['news'] = news
        log(f"新闻数量: {len(news)}")
        
        # 获取行业龙头股
        log("获取行业龙头股...")
        industry_leaders = analyzer.get_industry_leaders(10)
        stock_info['industry_leaders'] = industry_leaders
        log(f"行业龙头股数量: {len(industry_leaders)}")
        
        # 获取财务数据
        log("获取财务数据...")
        financial = analyzer.get_financial_report()
        if financial:
            stock_info['financial'] = financial
        
        log("=== 股票详情获取完成 ===")
        return jsonify({
            'success': True,
            'data': stock_info
        })
        
    except Exception as e:
        log(f"!!! 股票详情获取失败: {e} !!!")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': f'获取股票详情失败: {str(e)}'
        })

@app.route('/api/stock/<stock_code>/kline')
def get_stock_kline(stock_code):
    """获取股票K线数据API"""
    try:
        period = request.args.get('period', 'daily')
        limit = int(request.args.get('limit', 60))
        
        analyzer = StockAnalyzer(stock_code)
        kline_data = analyzer.get_kline_data(period, limit)
        
        return jsonify({
            'success': True,
            'data': kline_data
        })
    except Exception as e:
        log(f"!!! K线数据获取失败: {e} !!!")
        return jsonify({
            'success': False,
            'error': f'获取K线数据失败: {str(e)}'
        })

@app.route('/api/ai-analyze', methods=['POST'])
def ai_analyze_fund():
    """AI基金分析API"""
    log("=== 收到AI分析请求 ===")
    try:
        data = request.get_json()
        fund_code = data.get('fund_code', '').strip()
        fund_info = data.get('fund_info', {})
        holdings = data.get('holdings', [])
        
        log(f"基金代码: {fund_code}")
        
        if not fund_code:
            return jsonify({
                'success': False,
                'error': '基金代码不能为空'
            })
        
        # 获取市场概况和多渠道新闻
        market_overview = {}
        try:
            log("获取市场概况...")
            # 获取主要指数
            indices = {
                '上证指数': StockNewsAnalyzer.get_index_quote("sh000001"),
                '深证成指': StockNewsAnalyzer.get_index_quote("sz399001"),
                '创业板': StockNewsAnalyzer.get_index_quote("sz399006"),
                '沪深300': StockNewsAnalyzer.get_index_quote("sh000300")
            }
            market_overview['indices'] = indices
            
            # 获取多渠道新闻
            all_news = []
            
            # 来源1：基金公司官网公告（基金公告/定期报告）
            try:
                fund_analyzer_for_news = FundAnalyzer(fund_code)
                fund_news = fund_analyzer_for_news.get_fund_news(5)
                for n in fund_news:
                    n['source_type'] = '基金公告'
                all_news.extend(fund_news)
                log(f"基金公告: {len(fund_news)} 条")
            except Exception as e:
                log(f"获取基金公告失败: {e}")
            
            # 来源2：市场新闻（财经媒体 - 新浪财经）
            try:
                market_news = StockNewsAnalyzer.get_market_news()
                for n in market_news[:5]:
                    n['source_type'] = '财经媒体'
                all_news.extend(market_news[:5])
                log(f"财经媒体新闻: {len(market_news[:5])} 条")
            except Exception as e:
                log(f"获取市场新闻失败: {e}")
            
            # 来源3：持仓股票新闻（第三方平台 - 东方财富）
            for holding in holdings[:3]:  # 取前3只重仓股
                try:
                    stock_code = holding.get('code', '')
                    if stock_code:
                        s_analyzer = StockAnalyzer(stock_code)
                        stock_news = s_analyzer.get_stock_news(3)
                        for n in stock_news[:3]:
                            n['source_type'] = '持仓股资讯'
                            n['related_stock'] = holding.get('name', stock_code)
                        all_news.extend(stock_news[:3])
                except:
                    pass
            
            # 去重并按时间排序
            seen_titles = set()
            unique_news = []
            for n in all_news:
                title = n.get('title', '')[:50]
                if title and title not in seen_titles:
                    seen_titles.add(title)
                    unique_news.append(n)
            
            market_overview['news'] = unique_news[:15]
            log(f"总新闻量: {len(unique_news)} 条")
        except Exception as e:
            log(f"获取市场概况失败（跳过）: {e}")
        
        # 获取持仓股票的K线数据
        log("获取持仓股票K线趋势...")
        kline_data = {}
        try:
            for holding in holdings[:5]:  # 取前5只重仓股
                stock_code = holding.get('code', '')
                if stock_code:
                    s_analyzer = StockAnalyzer(stock_code)
                    # 获取近1年K线数据（约250个交易日）
                    stock_kline = s_analyzer.get_kline_data('daily', 250)
                    if stock_kline:
                        # 添加股票名称
                        for k in stock_kline:
                            k['stock_name'] = holding.get('name', stock_code)
                        kline_data[stock_code] = stock_kline
                        log(f"  {stock_code}: 获取到 {len(stock_kline)} 条K线")
        except Exception as e:
            log(f"获取K线数据失败（跳过）: {e}")
        log(f"共获取 {len(kline_data)} 只股票的K线数据")
        
        # 获取基金经理变更历史和投资策略
        log("获取基金经理和策略信息...")
        try:
            fund_analyzer = FundAnalyzer(fund_code)
            manager_history = fund_analyzer.get_manager_history()
            fund_strategy = fund_analyzer.get_fund_strategy()
            fund_info['manager_history'] = manager_history
            fund_info['fund_strategy'] = fund_strategy
            log(f"基金经理: {manager_history.get('manager')}, 近期变更: {manager_history.get('recent_changed')}")
        except Exception as e:
            log(f"获取经理/策略信息失败（跳过）: {e}")

        # 调用DeepSeek AI分析
        log("开始AI分析...")
        api_key = data.get('api_key', '')
        analyzer = DeepSeekAnalyzer(api_key)
        
        result = analyzer.analyze_fund(
            fund_info=fund_info,
            holdings=holdings,
            market_overview=market_overview,
            news=market_overview.get('news', []),
            kline_data=kline_data
        )
        
        log(f"AI分析完成: {result.get('final_advice', 'N/A')}")
        return jsonify({
            'success': True,
            'data': result
        })
        
    except Exception as e:
        log(f"!!! AI分析失败: {e} !!!")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': f'AI分析失败: {str(e)}'
        })

@app.route('/api/market-overview')
def get_market_overview():
    """获取市场概况API"""
    try:
        indices = {
            '上证指数': StockNewsAnalyzer.get_index_quote("sh000001"),
            '深证成指': StockNewsAnalyzer.get_index_quote("sz399001"),
            '创业板': StockNewsAnalyzer.get_index_quote("sz399006"),
            '沪深300': StockNewsAnalyzer.get_index_quote("sh000300")
        }
        
        news = StockNewsAnalyzer.get_market_news()
        
        return jsonify({
            'success': True,
            'data': {
                'indices': indices,
                'news': news[:10]
            }
        })
    except Exception as e:
        log(f"获取市场概况失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        })

@app.route('/api/check-api-key')
def check_api_key():
    """检查API密钥是否配置"""
    import os
    api_key = os.environ.get('DEEPSEEK_API_KEY', '')
    return jsonify({
        'configured': bool(api_key),
        'message': 'API密钥已配置' if api_key else '请配置DeepSeek API密钥（环境变量: DEEPSEEK_API_KEY）'
    })

@app.route('/api/ai-chat', methods=['POST'])
def ai_chat():
    """AI对话问答API"""
    log("=== 收到AI问答请求 ===")
    try:
        data = request.get_json()
        fund_codes = data.get('fund_codes', [])
        question = data.get('question', '').strip()
        fund_code = data.get('fund_code', '').strip()
        fund_info = data.get('fund_info', {})
        holdings = data.get('holdings', [])

        if fund_codes and len(fund_codes) > 1:
            # 跨基金问答模式
            multi_fund_data = []
            for code in fund_codes[:5]:
                try:
                    fa = FundAnalyzer(code)
                    fi = fa.get_fund_info()
                    holdings_data = fa._get_fund_holdings(0)
                    multi_fund_data.append({
                        'code': code,
                        'name': fi.get('fund_name', '未知') if fi else '未知',
                        'nav': fi.get('net_value', 0) if fi else 0,
                        'type': fi.get('fund_type', '未知') if fi else '未知',
                        'manager': fi.get('manager', '未知') if fi else '未知',
                        'top': [h['name'] for h in holdings_data[:3]] if holdings_data else []
                    })
                except:
                    pass
            fund_info = multi_fund_data  # 覆盖原有单只基金信息
        
        if not question:
            return jsonify({'success': False, 'error': '问题不能为空'})
        
        log(f"问题: {question[:50]}...")
        
        api_key = data.get('api_key', '')
        analyzer = DeepSeekAnalyzer(api_key)

        if isinstance(fund_info, list):
            # 跨基金模式
            fund_desc = '\n'.join([f"- {f['name']}({f['code']}): 净值={f['nav']}, 类型={f['type']}, 经理={f['manager']}, 重仓={','.join(f['top'])}" for f in fund_info])
            prompt = f"""你是专业的基金投资顾问。以下是多只基金的信息：

{fund_desc}

用户问题: {question}

请对比分析这些基金，给出专业建议。"""
            answer = analyzer.ai_chat_with_prompt(prompt)
        else:
            answer = analyzer.chat_about_fund(question, fund_info, holdings)
        
        return jsonify({'success': True, 'data': answer})
    except Exception as e:
        log(f"!!! AI问答失败: {e} !!!")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/fund/<fund_code>/benchmark')
def get_fund_benchmark(fund_code):
    """获取基金净值+沪深300基准对比数据"""
    try:
        analyzer = FundAnalyzer(fund_code)
        history = analyzer.get_fund_history(120)
        benchmark = analyzer.get_benchmark_data(120)
        if history is not None and len(history) > 0 and benchmark and len(benchmark) > 0:
            nav_list = [{'date': str(r['date']), 'value': r['net_value']} for r in history.to_dict('records')]
            first_nav = nav_list[0]['value'] if nav_list else 1
            for item in nav_list:
                item['normalized'] = round((item['value'] / first_nav) * 100, 2)
            first_bm = benchmark[0]['value'] if benchmark else 1
            for item in benchmark:
                item['normalized'] = round((item['value'] / first_bm) * 100, 2)
            return jsonify({'success': True, 'data': {'fund': nav_list, 'benchmark': benchmark}})
        return jsonify({'success': False, 'error': '获取基准数据失败'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/fund/<fund_code>/risk-metrics')
def get_fund_risk_metrics(fund_code):
    """获取基金风险指标"""
    try:
        analyzer = FundAnalyzer(fund_code)
        metrics = analyzer.get_risk_metrics(365)
        return jsonify({'success': True, 'data': metrics})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})



@app.route('/api/fund/<fund_code>/fees')
def get_fund_fees(fund_code):
    """获取基金费率结构"""
    try:
        analyzer = FundAnalyzer(fund_code)
        fees = analyzer.get_fund_fees()
        return jsonify({'success': True, 'data': fees})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/fund/<fund_code>/strategy-analysis')
def get_strategy_analysis(fund_code):
    """获取量化策略分析"""
    try:
        analyzer = FundAnalyzer(fund_code)
        
        # 长期稳定性分析（持有决策）
        long_term = analyzer.get_long_term_stability_analysis(1260)  # 5年
        
        # 下跌预测（卖出决策）
        downside = analyzer.get_downside_prediction(252)  # 1年
        
        # 上涨预测（买入决策）
        upside = analyzer.get_upside_prediction(180)  # 6个月
        
        # 综合评分
        scores = [long_term['score'], downside['score'], upside['score']]
        avg_score = sum(scores) / len(scores)
        
        # 综合建议
        if long_term['recommendation'] == '持有' and downside['recommendation'] != '卖出':
            overall = '建议持有'
            confidence = long_term['score']
        elif downside['recommendation'] == '卖出':
            overall = '建议考虑卖出'
            confidence = downside['score']
        elif upside['recommendation'] in ['买入', '可考虑买入']:
            overall = '存在买入机会'
            confidence = upside['score']
        else:
            overall = '建议观望'
            confidence = avg_score
        
        return jsonify({
            'success': True,
            'data': {
                'long_term_stability': long_term,
                'downside_prediction': downside,
                'upside_prediction': upside,
                'overall_recommendation': overall,
                'overall_score': round(avg_score, 1),
                'confidence': round(confidence, 1)
            }
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/portfolio-analyze', methods=['POST'])
def portfolio_analyze():
    """组合AI分析"""
    log("=== 收到组合AI分析请求 ===")
    try:
        data = request.get_json()
        funds = data.get('funds', [])
        question = data.get('question', '分析我的投资组合')
        if not funds:
            return jsonify({'success': False, 'error': '请提供基金列表'})
        portfolio_data = []
        for f in funds:
            try:
                analyzer = FundAnalyzer(f['code'])
                fund_info = analyzer.get_fund_info()
                holdings = analyzer._get_fund_holdings(0)
                portfolio_data.append({
                    'code': f['code'],
                    'name': fund_info.get('fund_name', '未知') if fund_info else '未知',
                    'weight': f.get('weight', 0),
                    'fund_type': fund_info.get('fund_type', '未知') if fund_info else '未知',
                    'manager': fund_info.get('manager', '未知') if fund_info else '未知',
                    'nav': fund_info.get('net_value', 0) if fund_info else 0,
                    'day_growth': fund_info.get('day_growth', 0) if fund_info else 0,
                    'total_return': (fund_info.get('net_value', 0) - f.get('buy_price', 0)) / f.get('buy_price', 1) * 100 if fund_info and f.get('buy_price', 0) > 0 else 0,
                    'top_holdings': [{'name': h['name'], 'ratio': h['ratio']} for h in holdings[:3]] if holdings else []
                })
            except Exception as e:
                log(f"[组合] 获取基金{f['code']}数据失败: {e}")
        if not portfolio_data:
            return jsonify({'success': False, 'error': '无法获取基金数据'})
        deepseek = DeepSeekAnalyzer()
        fund_lines = '\n'.join([f"- {p['name']}({p['code']}): 权重{p['weight']}%, 类型={p['fund_type']}, 经理={p['manager']}, 当日涨跌={p['day_growth']:.2f}%, 累计收益={p['total_return']:.2f}%, 重仓={','.join([h['name']+'('+h['ratio']+')' for h in p['top_holdings']])}" for p in portfolio_data])
        prompt = f"""## 投资组合分析请求
请分析以下投资组合：

{fund_lines}

用户提问: {question}

请从以下角度分析：
1. 组合整体质量评估（分散度、风险）
2. 行业集中度分析（是否有重叠持仓）
3. 风险评估和建议
4. 具体调仓建议（如果有）"""
        result = deepseek.ai_chat_with_prompt(prompt)
        return jsonify({'success': True, 'data': result})
    except Exception as e:
        log(f"组合AI分析失败: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})


if __name__ == '__main__':
    print("启动Flask服务器...")
    app.run(debug=False, host='127.0.0.1', port=5000)
