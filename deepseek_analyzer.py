"""
DeepSeek AI 基金分析模块
集成AI分析功能，对基金进行全面分析并给出投资建议
"""
import json
import time
import random
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Union

# 日志函数
def log(message):
    """简单的日志输出"""
    print(message, flush=True)

# =============================================
# ⚠️ DeepSeek API 密钥配置 ⚠️
# =============================================
# 使用环境变量方式（推荐，更安全）
# 在命令行运行: set DEEPSEEK_API_KEY=your_key_here
# 或 Linux/Mac: export DEEPSEEK_API_KEY=your_key_here
import os
from dotenv import load_dotenv

# 先加载.env文件（确保在任何import之前读取到密钥）
dotenv_loaded = load_dotenv()
if not dotenv_loaded:
    # 如果load_dotenv找不到.env文件，尝试从当前目录和父目录查找
    for dotenv_path in ['.env', '../.env', os.path.join(os.path.dirname(__file__), '.env')]:
        if os.path.exists(dotenv_path):
            load_dotenv(dotenv_path)
            break

# 从环境变量读取API密钥
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")

# DeepSeek API 地址（通常不需要修改）
DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"

# =============================================
# API密钥获取地址: https://platform.deepseek.com/
# =============================================


class DeepSeekAnalyzer:
    """DeepSeek AI 分析器"""
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key or DEEPSEEK_API_KEY
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
    
    def analyze_fund(self, fund_info: Dict, holdings: List[Dict], 
                     market_overview: Dict = None, news: List[Dict] = None,
                     kline_data: Dict = None) -> Dict:
        """
        综合分析基金并给出投资建议
        
        Args:
            fund_info: 基金基本信息
            holdings: 持仓股票列表
            market_overview: 市场概况
            news: 相关新闻
            kline_data: 持仓股票的K线数据
            
        Returns:
            AI分析结果和建议
        """
        log("=== 开始AI基金分析 ===")
        
        # 构建分析提示词
        prompt = self._build_analysis_prompt(fund_info, holdings, market_overview, news, kline_data)
        
        try:
            # 调用DeepSeek API
            result = self._call_deepseek_api(prompt)
            log("✅ AI API调用成功 （非降级）")
            return result
        except Exception as e:
            log(f"❌ AI API调用失败，使用降级方案: {e}")
            # 返回降级方案
            return self._generate_fallback_analysis(fund_info, holdings)
    
    @staticmethod
    def _format_manager_history(manager_data: Dict) -> str:
        """格式化基金经理变更信息"""
        if not manager_data or not isinstance(manager_data, dict):
            return "暂无基金经理数据"
        
        manager = manager_data.get('manager', '未知')
        recent_changed = manager_data.get('recent_changed', False)
        change_date = manager_data.get('change_date', '')
        
        lines = [f"- 当前基金经理: {manager}"]
        if recent_changed:
            lines.append(f"- ⚠️ 近期存在基金经理变更！变更日期: {change_date}")
        else:
            lines.append("- 近期无基金经理变更")
        
        return '\n'.join(lines)
    
    @staticmethod
    def _format_fund_strategy(strategy_data: Dict) -> str:
        """格式化基金投资策略信息"""
        if not strategy_data or not isinstance(strategy_data, dict):
            return "暂无基金策略数据"
        
        style = strategy_data.get('investment_style', '未知')
        objective = strategy_data.get('investment_objective', '')
        strategy = strategy_data.get('investment_strategy', '')
        risk = strategy_data.get('risk_return', '')
        
        lines = [f"- 投资风格: {style}"]
        if objective:
            lines.append(f"- 投资目标: {objective[:150]}")
        if strategy:
            lines.append(f"- 投资策略: {strategy[:150]}")
        if risk:
            lines.append(f"- 风险特征: {risk[:150]}")
        
        return '\n'.join(lines) if len(lines) > 1 else f"暂无详细策略数据（风格: {style}）"
    
    def _build_analysis_prompt(self, fund_info: Dict, holdings: List[Dict], 
                               market_overview: Dict, news: List[Dict],
                               kline_data: Dict = None) -> str:
        """构建AI分析提示词 - 三层递进式分析"""
        
        # 格式化持仓数据
        holdings_text = ""
        if holdings:
            for h in holdings[:10]:
                holdings_text += f"- {h.get('name', 'N/A')} ({h.get('code', 'N/A')}): 持仓占比 {h.get('ratio', 'N/A')}\n"
        
        # 格式化新闻（多渠道来源）
        news_text = ""
        if news:
            news_with_source = []
            for n in news[:15]:
                src = n.get('source_type', n.get('source', '财经媒体'))
                related = n.get('related_stock', '')
                tag = f"[{src}]"
                if related:
                    tag += f"[相关股票:{related}]"
                news_with_source.append(f"- {tag} {n.get('title', 'N/A')}")
            news_text = '\n'.join(news_with_source)
        
        # 格式化市场指数
        indices_text = ""
        if market_overview and market_overview.get('indices'):
            for name, data in market_overview['indices'].items():
                if data:
                    indices_text += f"- {name}: {data.get('current', 'N/A')} (涨跌: {data.get('change', 0):+.2f}, {data.get('pct_change', 0):+.2f}%)\n"
        
        # 格式化K线数据 - 按月度汇总近1年趋势
        kline_text = ""
        if kline_data and isinstance(kline_data, dict):
            for stock_code, stock_kline in kline_data.items():
                if stock_kline and len(stock_kline) > 0:
                    stock_name = stock_kline[0].get('stock_name', '未知')
                    # 按月份分组计算月度表现
                    monthly_data = {}
                    for k in stock_kline:
                        date = k.get('date', '')
                        if len(date) >= 7:
                            month_key = date[:7]  # yyyy-mm
                            if month_key not in monthly_data:
                                monthly_data[month_key] = {'first_close': None, 'last_close': None, 'high': -999, 'low': 999, 'count': 0}
                            close = k.get('close', 0)
                            if monthly_data[month_key]['first_close'] is None:
                                monthly_data[month_key]['first_close'] = close
                            monthly_data[month_key]['last_close'] = close
                            monthly_data[month_key]['high'] = max(monthly_data[month_key]['high'], close)
                            monthly_data[month_key]['low'] = min(monthly_data[month_key]['low'], close)
                            monthly_data[month_key]['count'] += 1
                    
                    # 计算总体趋势
                    first_close = stock_kline[0].get('close', 0)
                    last_close = stock_kline[-1].get('close', 0)
                    total_change_pct = ((last_close - first_close) / first_close * 100) if first_close else 0
                    total_trend = '上涨' if total_change_pct > 0 else '下跌'
                    
                    # 生成月度趋势文字
                    months = sorted(monthly_data.keys())
                    month_trends = []
                    for m in months[-12:]:  # 最多显示12个月
                        d = monthly_data[m]
                        m_change = ((d['last_close'] - d['first_close']) / d['first_close'] * 100) if d['first_close'] else 0
                        m_trend = '📈' if m_change >= 0 else '📉'
                        month_trends.append(f"{m[-2:]}月{m_trend}({m_change:+.1f}%)")
                    
                    kline_text += f"- {stock_name}({stock_code}): 近1年{total_trend} {abs(total_change_pct):.1f}%\n  "
                    kline_text += f"  月度走势: {' → '.join(month_trends)}\n"
        
        # 用户设定的止损线（从基金信息中获取，如果有）
        stop_loss = fund_info.get('stop_loss', -20)  # 默认-20%
        current_profit_loss = fund_info.get('current_profit_loss', 0)  # 当前盈亏
        
        prompt = f"""你是一位专业的基金投资分析师。请严格遵循以下三层递进式逻辑，对基金进行深度分析并给出操作建议。

## 用户设定参数
- 个人止损线: {stop_loss}%
- 当前盈亏: {current_profit_loss}%

## 基金基本信息
- 基金名称: {fund_info.get('name', 'N/A')}
- 基金代码: {fund_info.get('code', 'N/A')}
- 最新净值: {fund_info.get('nav', fund_info.get('net_value', 'N/A'))}
- 日涨跌幅: {fund_info.get('daily_change', fund_info.get('day_growth', 'N/A'))}%
- 近1月涨跌幅: {fund_info.get('month_1_change', 'N/A')}%
- 近3月涨跌幅: {fund_info.get('month_3_change', 'N/A')}%
- 近6月涨跌幅: {fund_info.get('month_6_change', 'N/A')}%
- 近1年涨跌幅: {fund_info.get('year_1_change', 'N/A')}%
- 基金经理: {fund_info.get('manager', '未知')}
- 基金规模: {fund_info.get('scale', '未知')}
- 基金类型: {fund_info.get('fund_type', '未知')}

## 基金经理变更信息
{self._format_manager_history(fund_info.get('manager_history', {}))}

## 基金投资策略
{self._format_fund_strategy(fund_info.get('fund_strategy', {}))}

## 前十大持仓股票
{holdings_text if holdings_text else "暂无持仓数据"}

## 市场指数表现
{indices_text if indices_text else "暂无市场数据"}

## 最新财经新闻
{news_text if news_text else "暂无新闻数据"}

## 持仓股票近期K线趋势
{kline_text if kline_text else "暂无K线数据"}

## 分析框架：三层递进式决策逻辑（新闻分析占20%权重）

**权重分配说明**：以下三层分析中，每层都需要考虑新闻信息，
其中新闻分析整体占决策权重的 **20%**，具体权重分配如下：
- 第一层（致命风险过滤）：新闻占该层分析30%
- 第二层（质量评估）：新闻占该层分析15%
- 第三层（市场匹配）：新闻占该层分析20%
请在每个决策层中明确参考新闻内容来支撑结论。

### 第一层：致命风险过滤器（触发即直接"卖出"）

请严格检查以下任一条件：

1. **基金经理变更+策略漂移**：如果近180天内基金经理发生变更，且投资策略发生显著漂移 → 直接卖出

2. **行业长期逻辑破坏**：核心赛道出现不可逆转的衰退或遭遇政策性灭顶之灾 → 直接卖出

3. **触发个人硬止损线**：当前亏损 {current_profit_loss}% ≥ {stop_loss}%（止损线{stop_loss}%） → 执行纪律，直接卖出

只有上述三个条件都不满足时，才进入第二层。

### 第二层：基金自身质量评估（"烂资产"过滤器）

结合定量数据（业绩排名）和定性分析（操作风格）：

1. **定量看**：近1年、近2年同类业绩排名是否持续处于后50%或后25%？
2. **定性看**：是否存在操作风格紊乱、频繁追涨杀跌、投资主题漂移不定？

**决策**：
- 如果质量"差" → 卖出或换仓，寻找更优质产品
- 如果质量"良好" → 进入第三层

### 第三层：市场环境与资金属性匹配

此时面对的是质量没问题的基金，下跌原因是系统性风险或行业阶段性低迷。

**补仓建议**（需同时满足）：
- 逻辑未变：行业长期增长逻辑依然坚实
- 价格便宜：估值处于历史低估区（百分位<30%）
- 有闲钱：手中有可投资的增量资金

**持有观望建议**（满足任一即可）：
- 估值还不够低：还没跌出足够性价比
- 没有闲钱：仓位已重影响心理和睡眠
- 无法判断：市场前景不明朗

## 输出要求
            
请用JSON格式返回分析结果（注意：以下JSON仅为格式示例，实际分析中请根据上面提供的真实数据填写）：
            
{{ 
    "layer_triggered": 0,  // 触发哪一层（0=未触发致命风险，1=第一层卖出，2=第二层卖出，3=第三层补仓/持有）
    "final_advice": "补仓/持有/卖出",  // 最终操作建议
    "advice_level": "高确定性/中确定性/低确定性",  // 建议确定性
    "risk_filter_result": {{
        "manager_changed": false,  // 布尔值：true或false
        "strategy_drift": false,
        "industry_logic_broken": false,
        "stop_loss_triggered": false,
        "risk_summary": "致命风险描述或'无致命风险'"
    }},
    "quality_assessment": {{
        "rating": "优秀/良好/差",
        "quantitative_score": "定量评分说明",
        "qualitative_score": "定性评分说明",
        "peer_rank_1y": "近1年排名",
        "peer_rank_2y": "近2年排名"
    }},
    "market_analysis": {{
        "valuation_level": "高估/合理/低估",
        "valuation_percentile": "估值百分位",
        "industry_outlook": "行业前景分析",
        "market_outlook": "市场展望"
    }},
    "decision_reason": "详细决策理由（500字以上）",
    "action_plan": "具体操作建议",
    "confidence": 0.85,  // 置信度 0-1
    "suitable_investors": "适合人群",
    "tips": ["小贴士1", "小贴士2"]
}}

请进行深入分析，如果需要了解更多信息（如基金经理历史业绩、具体持仓分析等），请在decision_reason中说明。
只返回JSON，不要有其他文字。"""
        
        return prompt
    
    def _call_deepseek_api(self, prompt: str, retry_count: int = 2) -> Dict:
        """调用DeepSeek API"""
        
        if not self.api_key:
            raise Exception("DeepSeek API密钥未配置")
        
        data = {
            "model": "deepseek-v4-pro",
            "messages": [
                {
                    "role": "system",
                    "content": "你是一位专业的基金投资分析师，帮助用户分析基金并给出投资建议。请以JSON格式返回分析结果。"
                },
                {
                    "role": "user", 
                    "content": prompt
                }
            ],
            "temperature": 0.3,  # 较低温度保证分析稳定性
            "max_tokens": 2000
        }
        
        for attempt in range(retry_count):
            try:
                response = requests.post(
                    DEEPSEEK_API_URL,
                    headers=self.headers,
                    json=data,
                    timeout=30
                )
                
                if response.status_code == 200:
                    result = response.json()
                    content = result['choices'][0]['message']['content']
                    log(f"[AI响应原始内容] {content[:500]}...")
                    return self._parse_ai_response(content)
                elif response.status_code == 401:
                    raise Exception("API密钥无效")
                elif response.status_code == 429:
                    log("API请求频率限制，尝试重试...")
                    time.sleep(5)
                    continue
                else:
                    log(f"API返回错误: {response.status_code} - {response.text}")
                    raise Exception(f"API错误: {response.status_code}")
                    
            except requests.exceptions.Timeout:
                log("API请求超时")
                if attempt < retry_count - 1:
                    time.sleep(2)
                    continue
                raise
            except requests.exceptions.RequestException as e:
                log(f"网络请求错误: {e}")
                raise
        
        raise Exception("API请求失败")
    
    def _parse_ai_response(self, content: str) -> Dict:
        """解析AI返回的内容"""
        try:
            # 尝试提取JSON
            content = content.strip()
            if content.startswith("```json"):
                content = content[7:]
            elif content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            
            result = json.loads(content.strip())
            log("[AI解析成功] final_advice=" + str(result.get('final_advice','N/A')) + ", decision_reason_lens=" + str(len(result.get('decision_reason',''))))
            return result
        except json.JSONDecodeError as e:
            log("JSON解析失败: " + str(e) + ", 内容: " + content[:300])
            raise Exception("AI返回格式错误")
    
    def _generate_fallback_analysis(self, fund_info: Dict, holdings: List[Dict]) -> Dict:
        """生成降级分析结果（当API不可用时）"""
        log("使用降级分析方案...")
        
        # 基于基金数据生成简单分析
        fund_name = fund_info.get('name', 'N/A')
        holdings_count = len(holdings)
        
        # 简单分析持仓
        holdings_text = ""
        if holdings:
            top_holding = holdings[0]
            holdings_text = f"重仓股{top_holding.get('name', 'N/A')}占比{top_holding.get('ratio', 'N/A')}"
        
        # 判断盈亏
        nav = float(fund_info.get('net_value', fund_info.get('nav', 0)))
        buy_price = float(fund_info.get('buy_price', 0))
        profit_loss = ((nav - buy_price) / buy_price * 100) if buy_price else 0
        
        return {
            "layer_triggered": 0,
            "final_advice": "持有",
            "advice_level": "中确定性",
            "risk_filter_result": {
                "manager_changed": False,
                "strategy_drift": False,
                "industry_logic_broken": False,
                "stop_loss_triggered": False,
                "risk_summary": "无法判断（AI服务不可用）"
            },
            "quality_assessment": {
                "rating": "良好",
                "quantitative_score": "由于AI服务暂不可用，无法获取完整数据",
                "qualitative_score": "基于持仓数据的基本分析",
                "peer_rank_1y": "暂无数据",
                "peer_rank_2y": "暂无数据"
            },
            "market_analysis": {
                "valuation_level": "合理",
                "valuation_percentile": "暂无数据",
                "industry_outlook": f"基金{fund_name}持仓包含{holdings_count}只股票。{holdings_text}",
                "market_outlook": "建议密切关注市场走势和相关政策变化。"
            },
            "decision_reason": f"由于DeepSeek API服务暂时不可用（余额不足），当前显示的是基于规则的基础分析。\n\n基金{fund_name}当前净值为{nav}，持仓包含{holdings_count}只股票。{'当前盈亏' + str(round(profit_loss, 2)) + '%。' if profit_loss else ''}\n\n建议前往 https://platform.deepseek.com 充值API余额以获得更准确的AI分析。",
            "action_plan": f"当前状态：持有观望。建议充值DeepSeek API后重新使用AI分析功能，获取包含三层递进式决策的详细投资建议。",
            "confidence": 0.3,
            "suitable_investors": "所有类型的投资者",
            "tips": [
                "建议定投方式参与，降低择时风险",
                "关注基金经理历史业绩和投资风格变化",
                "分散投资，不要把所有资金放在一只基金上",
                "前往 https://platform.deepseek.com 充值API后获得更精准分析"
            ],
            "fallback": True,
            "message": "⚠️ AI服务余额不足，当前显示基础分析。请前往 DeepSeek 平台充值后重试。"
        }
    
    def chat_about_fund(self, question: str, fund_info: Union[Dict, List], holdings: List[Dict]) -> Dict:
        """AI对话问答 - 回答用户关于基金的问题，支持单基金和组合模式"""
        log(f"=== AI问答: {question[:50]}... ===")
        
        # 检测是否为组合/跨基金模式
        if isinstance(fund_info, list) or (isinstance(fund_info, dict) and fund_info.get('type') == 'portfolio'):
            if isinstance(fund_info, dict) and fund_info.get('type') == 'portfolio':
                funds = fund_info.get('funds', [])
            else:
                funds = fund_info
            # 构建多基金信息
            fund_lines = []
            for f in funds:
                name = f.get('name', f.get('fund_name', '未知'))
                code = f.get('code', f.get('fund_code', ''))
                nav = f.get('nav', f.get('net_value', 'N/A'))
                growth = f.get('day_growth', f.get('daily_change', 'N/A'))
                mgr = f.get('manager', '未知')
                ftype = f.get('fund_type', '未知')
                weight = f.get('weight', '')
                ret = f.get('total_return', '')
                tops = ''
                if f.get('top_holdings'):
                    tops = ', '.join([f"{h['name']}({h['ratio']})" for h in f['top_holdings']])
                line = f"- {name}({code})"
                if weight: line += f" 权重{weight}%"
                line += f": 净值={nav}, 涨跌={growth}%, 类型={ftype}, 经理={mgr}"
                if ret: line += f", 累计收益={ret:.2f}%"
                if tops: line += f", 重仓={tops}"
                fund_lines.append(line)
            
            prompt = f"""你是一位专业的基金投资顾问。请对比分析以下多只基金的信息，回答用户的问题。

## 多只基金信息
{chr(10).join(fund_lines)}

## 用户问题
{question}

请从以下角度分析（如适用）：
1. 各基金特点对比（收益、风险、持仓）
2. 哪只基金更适合什么场景
3. 组合整体的分散度评估
4. 具体建议
"""
        else:
            # 单基金模式（原有逻辑）
            fund_name = fund_info.get('name', 'N/A')
            fund_code = fund_info.get('code', fund_info.get('fund_code', 'N/A'))
            nav = fund_info.get('nav', fund_info.get('net_value', 'N/A'))
            day_change = fund_info.get('daily_change', fund_info.get('day_growth', 'N/A'))
            
            holdings_text = ""
            if holdings:
                for h in holdings[:8]:
                    holdings_text += f"- {h.get('name', 'N/A')}({h.get('code', 'N/A')}): 占比{h.get('ratio', 'N/A')}\n"
            
            prompt = f"""你是一位专业的基金投资顾问。请基于以下基金信息，回答用户的问题。

## 基金基本信息
- 名称: {fund_name}({fund_code})
- 净值: {nav}
- 日涨跌幅: {day_change}%
- 基金经理: {fund_info.get('manager', '未知')}
- 基金类型: {fund_info.get('fund_type', '未知')}
- 基金规模: {fund_info.get('scale', '未知')}

## 前十大持仓（部分）
{holdings_text if holdings_text else "暂无数据"}

## 用户问题
{question}


请以专业、易懂的方式回答，控制在300字以内。"""
        
        try:
            if not self.api_key:
                raise Exception("DeepSeek API密钥未配置")
            
            data = {
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": "你是一位专业的基金投资顾问，回答要简洁、专业、易懂。"},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.5,
                "max_tokens": 1500
            }
            
            response = requests.post(DEEPSEEK_API_URL, headers=self.headers, json=data, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                content = result['choices'][0]['message']['content']
                return {'answer': content}
            else:
                raise Exception(f"API错误: {response.status_code}")
        except Exception as e:
            log(f"AI问答失败: {e}")
            return {'answer': f'抱歉，AI暂时无法回答。错误: {str(e)}'}

    def ai_chat_with_prompt(self, prompt: str) -> Dict:
        """直接使用自定义prompt调用AI（支持自定义提示词，返回原始回答）"""
        log("=== AI自定义Prompt对话 ===")
        try:
            if not self.api_key:
                raise Exception("DeepSeek API密钥未配置")

            data = {
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": "你是一位专业的基金投资顾问，回答要简洁、专业、易懂。"},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.5,
                "max_tokens": 2000
            }

            response = requests.post(DEEPSEEK_API_URL, headers=self.headers, json=data, timeout=30)

            if response.status_code == 200:
                result = response.json()
                content = result['choices'][0]['message']['content']
                return {'answer': content}
            else:
                raise Exception(f"API错误: {response.status_code}")
        except Exception as e:
            log(f"AI自定义对话失败: {e}")
            return {'answer': f'抱歉，AI暂时无法回答。错误: {str(e)}'}


class StockNewsAnalyzer:
    """股票新闻和行情分析器"""
    
    @staticmethod
    def get_market_news() -> List[Dict]:
        """获取市场新闻"""
        news = []
        try:
            # 新浪财经市场新闻
            url = "https://feed.mix.sina.com.cn/api/roll/get?pageid=153&lid=2516&k=&num=10&page=1&r=0.5"
            resp = requests.get(url, timeout=10, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })
            if resp.status_code == 200:
                data = resp.json()
                for item in data.get('result', {}).get('data', []):
                    news.append({
                        'title': item.get('title', ''),
                        'datetime': item.get('ctime', ''),
                        'url': item.get('url', ''),
                        'source': '新浪财经'
                    })
        except Exception as e:
            log(f"获取市场新闻失败: {e}")
        
        return news[:10]
    
    @staticmethod
    def get_stock_realtime_price(stock_code: str) -> Optional[Dict]:
        """获取股票实时行情"""
        try:
            # 转换代码格式
            if stock_code.startswith('6'):
                symbol = f"sh{stock_code}"
            else:
                symbol = f"sz{stock_code}"
            
            url = f"https://hq.sinajs.cn/list={symbol}"
            resp = requests.get(url, timeout=10, headers={
                'User-Agent': 'Mozilla/5.0',
                'Referer': 'https://finance.sina.com.cn'
            })
            
            if resp.status_code == 200:
                content = resp.text
                # 解析返回数据
                match = content.split('"')[1] if '"' in content else ""
                if match:
                    data = match.split(',')
                    if len(data) > 10:
                        return {
                            'name': data[0],
                            'open': data[1],
                            'close': data[2],
                            'current': data[3],
                            'high': data[4],
                            'low': data[5],
                            'volume': int(data[8]) if data[8] else 0,
                            'amount': float(data[9]) if data[9] else 0,
                            'datetime': data[30] + ' ' + data[31] if len(data) > 31 else ''
                        }
        except Exception as e:
            log(f"获取股票行情失败 {stock_code}: {e}")
        
        return None
    
    @staticmethod
    def get_index_quote(index_code: str = "sh000001") -> Optional[Dict]:
        """获取指数行情"""
        try:
            url = f"https://hq.sinajs.cn/list={index_code}"
            resp = requests.get(url, timeout=10, headers={
                'User-Agent': 'Mozilla/5.0',
                'Referer': 'https://finance.sina.com.cn'
            })
            resp.encoding = 'gbk'  # 新浪API使用GBK编码
            
            if resp.status_code == 200:
                content = resp.text
                match = content.split('"')[1] if '"' in content else ""
                if match:
                    data = match.split(',')
                    if len(data) > 4:
                        name = data[0]
                        current = float(data[1])
                        change = float(data[2])
                        # 百分比可能包含%，去掉并验证合理性
                        pct_str = data[3].strip().replace('%', '')
                        try:
                            pct_change = float(pct_str)
                        except ValueError:
                            pct_change = 0.0
                        # 验证数据合理性：百分比不应超过100%
                        if abs(pct_change) > 100:
                            log(f"[警告] 指数{pct_change}%异常，使用备用计算")
                            # 用涨跌额/昨收重新计算
                            prev_close = current - change
                            if prev_close != 0:
                                pct_change = (change / prev_close) * 100
                            else:
                                pct_change = 0.0
                        return {
                            'name': name,
                            'current': current,
                            'change': change,
                            'pct_change': round(pct_change, 2),
                            'prev_close': current - change
                        }
        except Exception as e:
            log(f"获取指数行情失败: {e}")
        
        return None


# 导出类
__all__ = ['DeepSeekAnalyzer', 'StockNewsAnalyzer']


# 测试代码
if __name__ == "__main__":
    # 测试代码
    analyzer = DeepSeekAnalyzer()
    
    # 测试市场新闻
    print("测试市场新闻获取...")
    news = StockNewsAnalyzer.get_market_news()
    print(f"获取到 {len(news)} 条新闻")
    
    # 测试指数行情
    print("\n测试指数行情获取...")
    quote = StockNewsAnalyzer.get_index_quote("sh000001")
    print(f"上证指数: {quote}")
