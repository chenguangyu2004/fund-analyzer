import requests
import pandas as pd
from datetime import datetime, timedelta
import json
import re

class FundAnalyzer:
    """基金分析类"""

    def __init__(self, fund_code):
        self.fund_code = fund_code
        self.fund_data = None

    def get_fund_info(self):
        """获取基金基本信息和净值数据"""
        try:
            # 同时获取官方净值和实时估算净值
            official_data = self._get_official_net_value()
            realtime_data = self._get_realtime_estimate()

            if not official_data:
                print("无法获取官方净值数据")
                return None

            try:
                current_time = datetime.now()
            except:
                current_time = None

            is_trading_time = False
            if current_time:
                is_trading_time = (9 <= current_time.hour < 15) and current_time.weekday() < 5

            update_time = ''
            if current_time:
                try:
                    update_time = current_time.strftime('%H:%M:%S')
                except:
                    update_time = ''

            # 合并数据
            self.fund_data = {
                'fund_code': self.fund_code,
                'fund_name': official_data.get('fund_name', f'基金{self.fund_code}'),
                'fund_full_name': official_data.get('fund_name', f'基金{self.fund_code}'),
                'fund_type': official_data.get('fund_type', '未知'),
                'fund_manager': official_data.get('fund_manager', '未知'),
                'org_name': official_data.get('org_name', '未知'),
                'foundation_date': official_data.get('foundation_date', '未知'),

                # 官方收盘净值数据
                'official_net_value': official_data.get('net_value', 0),
                'official_accumulated_value': official_data.get('accumulated_value', 0),
                'official_day_growth': official_data.get('day_growth', 0),
                'official_nav_date': official_data.get('nav_date', '未知'),

                # 实时估算净值数据
                'realtime_net_value': realtime_data.get('estimated_value') if realtime_data else None,
                'realtime_day_growth': realtime_data.get('estimated_growth') if realtime_data else None,

                # 用于计算的净值（优先使用实时估算）
                'net_value': realtime_data.get('estimated_value') if realtime_data else official_data.get('net_value', 0),
                'accumulated_value': official_data.get('accumulated_value', 0),
                # 日增长率优先使用实时数据
                'day_growth': realtime_data.get('estimated_growth') if realtime_data else official_data.get('day_growth', 0),
                'nav_date': official_data.get('nav_date', '未知'),

                'has_realtime': realtime_data is not None,
                'is_trading_time': is_trading_time,
                'update_time': update_time
            }

            print(f"官方净值: {self.fund_data['official_net_value']}, 实时估值: {self.fund_data['realtime_net_value']}")
            return self.fund_data

        except Exception as e:
            print(f"获取基金信息失败: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _get_official_net_value(self):
        """获取官方净值数据"""
        try:
            # 从天天基金网获取官方净值数据
            url = f"http://fundf10.eastmoney.com/jjjz_{self.fund_code}.html"
            print(f"正在请求官方数据: {url}")
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/102.0.0.0 Safari/537.36',
                'Referer': 'http://fund.eastmoney.com/'
            }
            response = requests.get(url, headers=headers, timeout=10)
            response.encoding = 'utf-8'
            print(f"天天基金响应状态: {response.status_code}")

            if response.status_code != 200:
                return None

            import re
            # 从HTML中提取JSON数据 - 尝试多种格式的基金名称
            fund_name = None
            name_patterns = [
                r'"SHORTNAME":"([^"]+)"',
                r'"name":"([^"]+)"',
                r'"NAME":"([^"]+)"',
                r'"fundName":"([^"]+)"',
                r'"FUNDNAME":"([^"]+)"'
            ]

            for pattern in name_patterns:
                name_match = re.search(pattern, response.text)
                if name_match:
                    fund_name = name_match.group(1)
                    break

            # 如果还是没找到，尝试从页面标题中获取
            if not fund_name:
                title_match = re.search(r'<title>([^<]+?)_基金历史净值_', response.text)
                if title_match:
                    fund_name = title_match.group(1).strip()
                else:
                    title_match = re.search(r'<title>([^<]+)</title>', response.text)
                    if title_match:
                        title_text = title_match.group(1)
                        # 清理标题文本
                        fund_name = title_text.replace('基金详情', '').replace('基金历史净值', '').replace('_基金档案_', '').replace('_天天基金网', '').strip()
                        # 移除括号内的代码
                        fund_name = re.sub(r'\(\d{6}\)', '', fund_name).strip()

            net_value_match = re.search(r'"dwjz":"([\d.]+)"', response.text)
            accumulated_match = re.search(r'"ljjz":"([\d.]+)"', response.text)
            date_match = re.search(r'"jzrq":"(\d{8})"', response.text)

            print(f"净值匹配: name={name_match}, net={net_value_match}, acc={accumulated_match}, date={date_match}")

            nav_date = '未知'
            if date_match:
                date_str = date_match.group(1)
                nav_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"

            net_value = float(net_value_match.group(1)) if net_value_match else 0
            accumulated_value = float(accumulated_match.group(1)) if accumulated_match else net_value

            # 如果没有找到净值数据，尝试从实时API获取
            if net_value == 0:
                try:
                    realtime_url = f"http://fundgz.1234567.com.cn/js/{self.fund_code}.js"
                    r = requests.get(realtime_url, headers=headers, timeout=5)
                    if r.status_code == 200:
                        json_str = r.text.strip()
                        if json_str.startswith('jsonpgz('):
                            json_str = json_str[8:-2]
                        data = json.loads(json_str)
                        net_value = float(data.get('dwjz', 0))
                        accumulated_value = net_value  # 如果没有累计净值，使用单位净值
                        print(f"从实时API获取到净值: {net_value}")
                except:
                    pass

            print(f"解析结果: 净值={net_value}, 累计={accumulated_value}, 日期={nav_date}, 名称={fund_name}")

            if net_value == 0:
                print("警告: 无法获取官方净值数据")
                return None

            # 清理基金名称
            if fund_name:
                fund_name = fund_name.replace('_ 基金档案 _ 天天基金网', '')
                fund_name = fund_name.replace('_基金档案_', '')
                fund_name = fund_name.replace('_天天基金网', '')
                fund_name = fund_name.strip()

            return {
                'fund_name': fund_name if fund_name else f'基金{self.fund_code}',
                'net_value': net_value,
                'accumulated_value': accumulated_value,
                'day_growth': 0,  # 官方净值没有增长率，从实时数据获取
                'nav_date': nav_date,
                'fund_manager': '未知',
                'org_name': '未知',
                'fund_type': '未知',
                'foundation_date': '未知'
            }

        except Exception as e:
            print(f"获取官方净值失败: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _get_realtime_estimate(self):
        """获取实时估算净值（基于股票持仓）"""
        try:
            # 尝试从天天基金获取实时估算
            url = f"http://fundgz.1234567.com.cn/js/{self.fund_code}.js"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/102.0.0.0 Safari/537.36',
                'Referer': 'http://fund.eastmoney.com/'
            }
            response = requests.get(url, headers=headers, timeout=5)
            if response.status_code == 200:
                json_str = response.text.strip()
                if json_str.startswith('jsonpgz(') and json_str.endswith(');'):
                    json_str = json_str[8:-2]

                data = json.loads(json_str)
                return {
                    'estimated_value': float(data.get('gsz', 0)),
                    'estimated_growth': float(data.get('gszzl', 0))
                }
        except Exception as e:
            print(f"获取实时估算失败: {e}")
        return None

    def get_fund_history(self, days=30):
        """获取历史净值数据"""
        try:
            print("[历史数据] 开始获取...")
            # 从天天基金网获取历史净值
            url = f"http://fund.eastmoney.com/f10/F10DataApi.aspx?type=lsjz&code={self.fund_code}&page=1&per=100"
            print(f"[历史数据] 请求: {url}")
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/102.0.0.0 Safari/537.36',
                'Referer': 'http://fund.eastmoney.com/'
            }
            response = requests.get(url, headers=headers, timeout=10)
            response.encoding = 'utf-8'
            print(f"[历史数据] 响应状态: {response.status_code}")

            # 直接从响应文本中提取content字段的HTML内容
            # 格式: var apidata={ content:"<table>...</table>", ... }
            import re
            response_text = response.text

            # 提取content字段中的HTML
            content_match = re.search(r'content:"(.*?)",', response_text, re.DOTALL)
            if not content_match:
                print("[历史数据] 未找到content字段")
                return None

            # 解码HTML实体和转义字符
            content = content_match.group(1)
            # 反转义引号等字符
            content = content.replace('\\"', '"').replace("\\'", "'")
            content = content.replace('\\n', '\n').replace('\\r', '\r')

            # 匹配表格行：净值日期, 单位净值, 累计净值, 日增长率, 申购状态, 赎回状态, 分红送配
            # 注意：HTML中可能有class属性，需要更灵活的正则表达式
            pattern = r'<tr><td>(\d{4}-\d{2}-\d{2})</td><td[^>]*>([\d.]+)</td><td[^>]*>([\d.]+)</td><td[^>]*>([^<]+)</td><td[^>]*>([^<]+)</td><td[^>]*>([^<]+)</td><td[^>]*>([^<]*)</td></tr>'
            matches = re.findall(pattern, content)

            print(f"[历史数据] 找到 {len(matches)} 条数据")

            if not matches:
                return None

            # 转换为DataFrame
            records = []
            for match in matches[:days]:  # 只取需要的天数
                records.append({
                    'date': match[0],  # 净值日期
                    'net_value': float(match[1]),  # 单位净值
                    'accumulated_value': float(match[2])  # 累计净值
                })

            print(f"[历史数据] 处理了 {len(records)} 条记录")

            # 创建DataFrame，避免使用可能导致错误的操作
            df = pd.DataFrame(records)
            # 简单排序，不使用可能导致错误的参数
            df = df.iloc[::-1]  # 反转，最新的在前

            return df

        except Exception as e:
            print(f"[历史数据] 获取失败: {e}")
            import traceback
            traceback.print_exc()
            return None

    def calculate_profit_loss(self, buy_price, shares):
        """计算盈亏"""
        if not self.fund_data:
            return None
        
        net_value = self.fund_data.get('net_value', 0)
        day_growth = self.fund_data.get('day_growth', 0)
        
        # 计算当前价值
        current_value = net_value * shares
        cost_value = buy_price * shares
        
        # 总盈亏
        total_profit = current_value - cost_value
        total_profit_percent = (current_value - cost_value) / cost_value * 100 if cost_value > 0 else 0
        
        # 当日盈亏（估算）
        day_profit = current_value * (day_growth / 100) if day_growth else 0
        
        result = {
            'current_value': current_value,
            'cost_value': cost_value,
            'total_profit': total_profit,
            'total_profit_percent': total_profit_percent,
            'day_profit': day_profit,
            'day_profit_percent': day_growth
        }
        
        return result

    def analyze_strategy(self, fund_data=None, days=30):
        """分析买卖策略"""
        if fund_data is None:
            fund_data = self.fund_data
        
        if not fund_data:
            return None
        
        # 获取历史数据
        history_df = self.get_fund_history(days)
        strategy = {
            'recommendation': '观望',
            'reasons': [],
            'risk_level': '中',
            'confidence': 0
        }
        
        try:
            if history_df is not None and len(history_df) > 5:
                net_values = history_df['net_value'].values
                current_value = float(fund_data['net_value'])
                
                # 计算均值
                avg_value = float(net_values.mean())
                
                # 计算趋势
                recent_trend = (net_values[-5:].mean() - net_values[-10:-5].mean()) / net_values[-10:-5].mean() * 100 if len(net_values) >= 10 else 0
                
                # 计算波动率
                volatility = float(net_values.std() / net_values.mean() * 100)
                
                # 计算当前相对于均值的位置
                position_percent = (current_value - avg_value) / avg_value * 100
                
                # 分析逻辑
                if position_percent > 5 and recent_trend > 2:
                    strategy['recommendation'] = '持有或减仓'
                    strategy['reasons'].append(f'当前净值高于近{days}日均值{position_percent:.2f}%')
                    strategy['risk_level'] = '中高'
                
                elif position_percent < -5 and recent_trend < -2:
                    if volatility > 10:
                        strategy['recommendation'] = '观望'
                        strategy['reasons'].append(f'基金波动较大，当前处于低位但风险较高')
                    else:
                        strategy['recommendation'] = '考虑加仓'
                        strategy['reasons'].append(f'当前净值低于近{days}日均值{position_percent:.2f}%')
                    strategy['risk_level'] = '中'
                
                elif recent_trend > 3:
                    strategy['recommendation'] = '持有'
                    strategy['reasons'].append(f'近期趋势向好，上涨{recent_trend:.2f}%')
                    strategy['risk_level'] = '中'
                
                elif recent_trend < -3:
                    strategy['recommendation'] = '谨慎或减仓'
                    strategy['reasons'].append(f'近期趋势向下，下跌{recent_trend:.2f}%')
                    strategy['risk_level'] = '中高'
                
                # 波动率分析
                if volatility > 15:
                    strategy['risk_level'] = '高'
                    strategy['reasons'].append(f'波动率较高({volatility:.2f}%)，风险较大')
                elif volatility < 5:
                    strategy['risk_level'] = '低'
                    strategy['reasons'].append(f'波动率较低({volatility:.2f}%)，相对稳健')
                
                # 计算信心度
                if abs(position_percent) > 3 or abs(recent_trend) > 2:
                    strategy['confidence'] = min(80, 60 + abs(position_percent) + abs(recent_trend))
                else:
                    strategy['confidence'] = 40
            
            else:
                # 无法获取历史数据时，基于日增长率判断
                day_growth = fund_data.get('day_growth', 0)
                if day_growth > 1:
                    strategy['recommendation'] = '持有'
                    strategy['reasons'].append('当日表现较好')
                elif day_growth < -1:
                    strategy['recommendation'] = '观望'
                    strategy['reasons'].append('当日表现不佳')
                else:
                    strategy['reasons'].append('波动较小，建议观望')
                strategy['confidence'] = 50
        
        except Exception as e:
            print(f"策略分析失败: {e}")
            strategy['reasons'].append('数据不足，建议获取更多信息后再决策')
            strategy['confidence'] = 30
        
        return strategy
