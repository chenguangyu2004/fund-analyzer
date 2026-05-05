import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json
import re
import traceback

class FundAnalyzer:
    """基金分析类"""

    def __init__(self, fund_code):
        self.fund_code = fund_code
        self.fund_data = None
        self.session = requests.Session()

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

            # 获取详细的基金信息（经理、规模、涨跌幅等）
            extra_info = self._get_fund_extra_info()
            growth_rates = self._get_fund_growth_rates()

            # 合并数据
            self.fund_data = {
                'fund_code': self.fund_code,
                'fund_name': official_data.get('fund_name', f'基金{self.fund_code}'),
                'fund_full_name': official_data.get('fund_name', f'基金{self.fund_code}'),
                'fund_type': extra_info.get('fund_type', official_data.get('fund_type', '未知')),
                'fund_manager': extra_info.get('fund_manager', '未知'),
                'manager': extra_info.get('fund_manager', '未知'),  # 兼容前端字段名
                'org_name': official_data.get('org_name', '未知'),
                'foundation_date': official_data.get('foundation_date', '未知'),
                'scale': extra_info.get('scale', '未知'),

                # 各阶段涨跌幅
                'month_1_change': growth_rates.get('month_1'),
                'month_3_change': growth_rates.get('month_3'),
                'month_6_change': growth_rates.get('month_6'),
                'year_1_change': growth_rates.get('year_1'),

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
            print(f"基金经理: {self.fund_data['manager']}, 规模: {self.fund_data['scale']}, 类型: {self.fund_data['fund_type']}")
            print(f"涨跌幅: 1月={self.fund_data['month_1_change']}, 3月={self.fund_data['month_3_change']}, 6月={self.fund_data['month_6_change']}, 1年={self.fund_data['year_1_change']}")
            return self.fund_data

        except Exception as e:
            print(f"获取基金信息失败: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _get_fund_extra_info(self):
        """获取基金经理、规模、类型等额外信息"""
        result = {'fund_manager': '未知', 'fund_type': '未知', 'scale': '未知'}
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'http://fund.eastmoney.com/'
        }
        try:
            # 使用东方财富基金搜索API（最可靠，包含基金经理、类型等）
            url = f"https://fundsuggest.eastmoney.com/FundSearch/api/FundSearchAPI.ashx?m=1&key={self.fund_code}"
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if data and data.get('Datas'):
                    for item in data['Datas']:
                        base = item.get('FundBaseInfo')
                        if base:
                            # 基金经理
                            jjjl = base.get('JJJL', '')
                            if jjjl:
                                result['fund_manager'] = jjjl
                            # 基金类型
                            ftype = base.get('FTYPE', '')
                            if ftype:
                                result['fund_type'] = ftype
                            break
        except Exception as e:
            print(f"[额外信息-搜索API] 获取失败: {e}")
        
        # 备用：从get_manager_history获取经理
        if result['fund_manager'] == '未知':
            try:
                mgr_result = self.get_manager_history()
                result['fund_manager'] = mgr_result.get('manager', '未知')
            except:
                pass
        
        # 备用：从基金名称判断类型
        if result['fund_type'] == '未知':
            try:
                url_js = f"http://fund.eastmoney.com/pingzhongdata/{self.fund_code}.js"
                resp_js = requests.get(url_js, headers=headers, timeout=10)
                resp_js.encoding = 'utf-8'
                if resp_js.status_code == 200:
                    name_match = re.search(r'fS_name\s*=\s*"([^"]+)"', resp_js.text)
                    if name_match:
                        fund_name = name_match.group(1)
                        type_kw = {
                            '货币': '货币型', '债券': '债券型', '指数': '指数型',
                            '混合': '混合型', '股票': '股票型', 'FOF': 'FOF型',
                            'QDII': 'QDII型', 'ETF': '指数型'
                        }
                        for kw, ftype in type_kw.items():
                            if kw in fund_name:
                                result['fund_type'] = ftype
                                break
            except:
                pass
        
        return result
    
    def _get_fund_growth_rates(self):
        """获取各阶段涨跌幅（近1月、近3月、近6月、近1年）"""
        rates = {'month_1': None, 'month_3': None, 'month_6': None, 'year_1': None}
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'http://fund.eastmoney.com/'
        }
        try:
            # 天天基金网pingzhongdata JS文件，包含各阶段收益率
            url = f"http://fund.eastmoney.com/pingzhongdata/{self.fund_code}.js"
            resp = requests.get(url, headers=headers, timeout=10)
            resp.encoding = 'utf-8'
            if resp.status_code == 200:
                text = resp.text
                # 各阶段收益率变量: syl_1y(近1月), syl_3y(近3月), syl_6y(近6月), syl_1n(近1年)
                rate_map = {
                    'syl_1y': 'month_1',
                    'syl_3y': 'month_3',
                    'syl_6y': 'month_6',
                    'syl_1n': 'year_1'
                }
                for var_name, key in rate_map.items():
                    m = re.search(rf'var\s+{var_name}\s*=\s*"([^"]+)"', text)
                    if m:
                        val = float(m.group(1))
                        rates[key] = val
        except Exception as e:
            print(f"[涨跌幅] 获取失败: {e}")
        
        return rates

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

    def _get_fund_holdings(self, top=10):
        """获取基金前十大持仓股票及实时行情"""
        try:
            print("[持仓] 开始获取...", flush=True)
            import os
            log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'debug.log')
            with open(log_path, 'a', encoding='utf-8') as f:
                f.write("[持仓] 开始获取...\n")
            # 从天天基金网获取持仓数据
            url = f"http://fundf10.eastmoney.com/FundArchivesDatas.aspx?type=jjcc&code={self.fund_code}&topline={top}&rt=0.1234567"
            print(f"[持仓] 请求: {url}")
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/102.0.0.0 Safari/537.36',
                'Referer': 'http://fund.eastmoney.com/'
            }
            
            response = requests.get(url, headers=headers, timeout=10)
            
            # 提取content字段
            content_match = re.search(r'content:"(.*?)",', response.text, re.DOTALL)
            if not content_match:
                print("[持仓] 未找到content字段")
                return []
            
            html_content = content_match.group(1).replace('\\"', '"')
            
            # 提取每一行
            tbody_match = re.search(r'<tbody>(.*?)</tbody>', html_content, re.DOTALL)
            if not tbody_match:
                print("[持仓] 未找到tbody")
                return []
            
            tbody = tbody_match.group(1)
            rows = re.findall(r'<tr>.*?</tr>', tbody, re.DOTALL)
            
            holdings = []
            for row in rows:
                # 提取序号
                seq_match = re.search(r'<td>(\d+)</td>', row)
                seq = seq_match.group(1) if seq_match else ''
                
                # 提取股票代码
                code_match = re.search(r'<td><a[^>]*>(\d+)</a></td>', row)
                code = code_match.group(1) if code_match else ''
                
                # 提取股票名称
                name_match = re.search(r'<td[^>]*class=["\']?tol["\']?[^>]*><a[^>]*>([^<]+)</a></td>', row)
                name = name_match.group(1) if name_match else ''
                
                # 提取占比
                ratio_match = re.search(r'<td[^>]*>(\d+\.?\d*%)</td>', row)
                ratio = ratio_match.group(1) if ratio_match else ''
                
                if code and name and ratio:
                    holdings.append({
                        'seq': seq,
                        'code': code,
                        'name': name,
                        'ratio': ratio,
                        'price': None,  # 稍后获取实时价格
                        'change': None,  # 稍后获取涨跌幅
                        'change_pct': None
                    })
            
            print(f"[持仓] 找到 {len(holdings)} 条持仓记录")
            
            # 批量获取股票实时价格
            if holdings:
                self._get_stock_prices(holdings)
            
            return holdings
        
        except Exception as e:
            print(f"[持仓] 获取失败: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def _get_stock_prices(self, holdings):
        """批量获取股票实时价格"""
        # 尝试多种方法突破反爬虫限制
        print(f"[持仓] 开始获取实时价格...", flush=True)

        # 尝试方法1: 使用session池和随机延迟
        if self._try_session_pool(holdings):
            return

        # 尝试方法2: 使用备用API
        if self._try_backup_apis(holdings):
            return

        # 如果都失败，则跳过
        print(f"[持仓] 所有方法均失败，跳过实时价格获取", flush=True)
        return

    def _try_session_pool(self, holdings):
        """使用session池和随机延迟尝试获取价格"""
        try:
            import random
            import time

            session = requests.Session()
            session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
                'Accept': '*/*',
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                'Connection': 'keep-alive',
            })

            success_count = 0

            # 分批获取，每批3只股票，随机延迟
            for i in range(0, len(holdings), 3):
                batch = holdings[i:i+3]
                code_map = {}

                for h in batch:
                    code = h['code']
                    code_map[code] = holdings.index(h)

                if code_map:
                    try:
                        # 使用腾讯财经API (这个API对批量查询更友好)
                        tencent_codes = []
                        beijing_codes = []  # 北交所股票单独处理
                        hk_codes = []  # 港股单独处理

                        for code in code_map.keys():
                            # 先判断是否为港股（5位代码）
                            if len(code) == 5:
                                # 港股（5位数字）
                                hk_codes.append(code)
                            elif code.startswith('6'):
                                tencent_codes.append(f'sh{code}')
                            elif code.startswith('0') or code.startswith('3'):
                                tencent_codes.append(f'sz{code}')
                            elif code.startswith('8') or code.startswith('4') or code.startswith('9'):
                                # 北交所股票，腾讯API不支持，尝试其他方式
                                beijing_codes.append(code)

                        codes_str = ','.join(tencent_codes)
                        url = f'http://qt.gtimg.cn/q={codes_str}'

                        print(f"[持仓] 请求腾讯API: {len(tencent_codes)} 只股票")
                        response = session.get(url, timeout=5)
                        response.encoding = 'utf-8'

                        if response.status_code == 200:
                            # 腾讯API返回格式: v_sh600519="..." 或 var hq_str_sh600519="..."
                            # 尝试多种匹配模式
                            patterns = [
                                r'v_(\w{2}\d+?)="([^"]+)"',  # v_sh600519="..."
                                r'var hq_str_(\w+?)="([^"]+)"'  # var hq_str_sh600519="..."
                            ]

                            for pattern in patterns:
                                matches = re.findall(pattern, response.text)
                                for market_code, data_str in matches:
                                    if data_str and '~' in data_str:
                                        # 腾讯API用~分隔数据
                                        parts = data_str.split('~')
                                        # 提取股票代码 (去掉市场前缀)
                                        stock_code = market_code[2:] if len(market_code) > 2 and market_code[:2] in ['sh', 'sz'] else market_code

                                        # 腾讯API字段索引 (可能需要调整):
                                        # 1=名称, 2=代码, 3=当前价, 4=昨收, ...
                                        if len(parts) > 3 and stock_code in code_map:
                                            try:
                                                price = float(parts[3]) if parts[3] else 0
                                                prev_close = float(parts[4]) if parts[4] else price

                                                if price > 0:
                                                    idx = code_map[stock_code]
                                                    change = price - prev_close
                                                    change_pct = (change / prev_close * 100) if prev_close > 0 else 0

                                                    holdings[idx]['price'] = price
                                                    holdings[idx]['change'] = change
                                                    holdings[idx]['change_pct'] = change_pct
                                                    print(f"[持仓] ✓ {stock_code}: 价格={price}, 涨跌={change_pct:.2f}%")
                                            except (ValueError, IndexError):
                                                continue

                        # 尝试获取北交所股票数据（使用东方财富网）
                        if beijing_codes:
                            for code in beijing_codes:
                                try:
                                    # 东方财富北交所API - 使用不同的secid格式
                                    url = f'http://push2.eastmoney.com/api/qt/stock/get?secid=0.{code}&fields=f2,f3,f4,f5,f12,f13,f14,f15,f16,f17,f18,f20,f21,f23,f24,f25,f26,f27,f28,f29,f30,f31,f32,f33,f34,f35,f36,f37,f38,f39,f40,f41,f42,f43,f44,f45,f46,f47,f48,f49,f50,f51,f52,f53,f54,f55,f56,f57,f58,f60,f61,f62,f63,f64,f65,f66,f67,f68,f69,f70,f71,f72,f73,f74,f75,f76,f77,f78,f79,f80,f81,f82,f84,f85,f86,f87,f88,f89,f90,f91,f92,f93,f94,f95,f96,f97,f98,f99,f100,f107,f108,f109,f110,f111,f112,f113,f114,f115,f116,f117,f118,f119,f120,f121,f122,f123,f124,f125,f126,f127,f128,f129,f130,f131,f132,f133,f134,f135,f136,f137,f138,f139,f140,f141,f142,f143,f144,f145,f146,f147,f148,f149,f150,f151,f152,f153,f154,f155,f156,f157,f158,f159,f160,f161,f162,f163,f164,f165,f166,f167,f168,f169,f170,f171,f172,f173,f174,f175,f176,f177,f178,f179,f180,f181,f182,f183,f184,f185,f186,f187,f188,f189,f190,f191,f192,f193,f194,f195,f196,f197,f198,f199,f200,f201,f202,f203,f204,f205,f206,f207,f208,f209,f210,f211,f212,f213,f214,f215,f216,f217,f218,f219,f220,f221,f222,f223,f224,f225,f226,f227,f228,f229,f230,f231,f232,f233,f234,f235,f236,f237,f238,f239,f240,f241,f242,f243,f244,f245,f246,f247,f248,f249,f250,f251,f252,f253,f254,f255,f256,f257,f258,f259,f260,f261,f262,f263,f264,f265,f266,f267,f268,f269,f270,f271,f272,f273,f274,f275,f276,f277,f278,f279,f280,f281,f282,f283,f284,f285,f286,f287,f288,f289,f290,f291,f292,f293,f294,f295,f296,f297,f298,f299,f300'
                                    response = session.get(url, timeout=3)
                                    if response.status_code == 200:
                                        data = response.json()
                                        if data and 'data' in data and data['data']:
                                            stock_data = data['data']
                                            price = stock_data.get('f43', 0)  # 最新价
                                            prev_close = stock_data.get('f60', 0)  # 昨收价
                                            if price and price > 0 and code in code_map:
                                                idx = code_map[code]
                                                change = price - prev_close
                                                change_pct = (change / prev_close * 100) if prev_close > 0 else 0

                                                holdings[idx]['price'] = price
                                                holdings[idx]['change'] = change
                                                holdings[idx]['change_pct'] = change_pct
                                                print(f"[持仓] ✓ {code}(北交所): 价格={price}, 涨跌={change_pct:.2f}%")
                                except Exception as e:
                                    # 北交所API失败不影响其他股票，继续
                                    pass

                        # 尝试获取港股数据（使用腾讯或新浪API）
                        if hk_codes:
                            # 腾讯API也支持港股，格式：hk代码
                            tencent_hk_codes = [f'hk{code}' for code in hk_codes]
                            hk_str = ','.join(tencent_hk_codes)

                            try:
                                url = f'http://qt.gtimg.cn/q={hk_str}'
                                print(f"[持仓] 请求腾讯港股API: {len(hk_codes)} 只股票")
                                response = session.get(url, timeout=5)
                                response.encoding = 'utf-8'

                                if response.status_code == 200:
                                    # 港股解析
                                    pattern = r'v_(hk\d+?)="([^"]+)"'
                                    matches = re.findall(pattern, response.text)

                                    for market_code, data_str in matches:
                                        if data_str and '~' in data_str:
                                            parts = data_str.split('~')
                                            # 港股代码格式：hk代码，去掉hk前缀
                                            stock_code = market_code[2:] if len(market_code) > 2 else market_code

                                            # 港股API字段索引可能略有不同
                                            if len(parts) > 3 and stock_code in code_map:
                                                try:
                                                    price = float(parts[3]) if parts[3] else 0
                                                    prev_close = float(parts[4]) if len(parts) > 4 and parts[4] else price

                                                    if price > 0:
                                                        idx = code_map[stock_code]
                                                        change = price - prev_close
                                                        change_pct = (change / prev_close * 100) if prev_close > 0 else 0

                                                        holdings[idx]['price'] = price
                                                        holdings[idx]['change'] = change
                                                        holdings[idx]['change_pct'] = change_pct
                                                        print(f"[持仓] ✓ {stock_code}(港股): 价格={price}, 涨跌={change_pct:.2f}%")
                                                except (ValueError, IndexError):
                                                    continue
                            except Exception as e:
                                print(f"[持仓] 港股API请求失败: {e}")
                                pass

                        # 检查是否获取到了数据
                        batch_success = sum(1 for h in batch if h['price'] is not None)
                        success_count += batch_success

                        # 随机延迟避免被封
                        if i + 3 < len(holdings):
                            delay = random.uniform(0.3, 0.8)
                            time.sleep(delay)

                    except Exception as e:
                        print(f"[持仓] 批量获取失败: {e}")
                        continue

            # 检查最终结果
            if success_count > 0:
                print(f"[持仓] 成功获取 {success_count}/{len(holdings)} 只股票价格")
                return True
            else:
                return False

        except Exception as e:
            print(f"[持仓] Session池方法失败: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _try_backup_apis(self, holdings):
        """尝试备用API"""
        try:
            # 尝试网易财经API
            success_count = 0
            for h in holdings:
                code = h['code']
                try:
                    # 网易财经API格式
                    if code.startswith('6'):
                        url = f'http://api.money.126.net/data/feed/0{code},money.api'
                    else:
                        url = f'http://api.money.126.net/data/feed/1{code},money.api'

                    headers = {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                        'Referer': 'https://money.163.com/'
                    }

                    response = requests.get(url, headers=headers, timeout=3)
                    if response.status_code == 200 and response.text:
                        # 网易返回JSONP格式
                        import json
                        text = response.text.strip()
                        if text.endswith(';'):
                            text = text[:-1]

                        # 尝试提取JSON数据
                        match = re.search(r'\{[^}]+\}', text)
                        if match:
                            try:
                                data = json.loads(match.group(0))
                                # 网易API返回格式复杂，这里简化处理
                                print(f"[持仓] 网易API返回: {code}")
                            except:
                                pass

                except Exception as e:
                    print(f"[持仓] 网易API失败 {code}: {e}")
                    continue

            if success_count > 0:
                print(f"[持仓] 备用API获取 {success_count}/{len(holdings)} 只股票")
                return True
            else:
                return False

        except Exception as e:
            print(f"[持仓] 备用API方法失败: {e}")
            return False
    
    def _fetch_prices(self, holdings, stock_codes, code_map, market_type):
        """从指定市场获取价格 - 使用腾讯 API"""
        try:
            # 使用腾讯财经 API，对批量查询更友好
            # 格式: http://qt.gtimg.cn/q=sh600000,sz000001
            # 腾讯股票代码格式: 市场代码+股票代码
            tencent_codes = []
            for full_code in stock_codes[:50]:
                tencent_codes.append(full_code.replace('.', ''))  # 去掉点号

            codes_str = ','.join(tencent_codes)
            url = f"http://qt.gtimg.cn/q={codes_str}"

            print(f"[持仓] 请求腾讯API ({market_type}): {len(tencent_codes)} 只股票")
            response = requests.get(url, timeout=10)
            response.encoding = 'utf-8'
            print(f"[持仓] 腾讯API响应状态: {response.status_code}")

            # 腾讯返回格式: var hq_str_sh600000="xxxx,xxxx,...";
            # 解析所有股票数据
            matched_count = 0
            print(f"[持仓] 腾讯API响应长度: {len(response.text)} 字符")

            for i, full_code in enumerate(stock_codes[:50]):
                market_code, stock_code = full_code.split('.')
                # 在响应中查找对应的股票数据
                pattern = f'var hq_str_{market_code}{stock_code}="([^"]+)"'
                match = re.search(pattern, response.text)
                if match and match.group(1) != '':
                    data_str = match.group(1)
                    # 格式: 开盘,最高,最低,收盘,成交量,成交额,涨跌幅,涨跌额,日期,时间
                    parts = data_str.split(',')
                    if len(parts) >= 4:
                        price = float(parts[3]) if parts[3] else 0
                        change_pct = float(parts[6]) if len(parts) > 6 and parts[6] else 0
                        change = float(parts[7]) if len(parts) > 7 and parts[7] else 0

                        if price > 0 and full_code in code_map:
                            idx = code_map[full_code]
                            holdings[idx]['price'] = price
                            holdings[idx]['change'] = change
                            holdings[idx]['change_pct'] = change_pct
                            matched_count += 1
                            print(f"[持仓] ✓ {stock_code}: 价格={price}, 涨跌={change_pct}%")

            print(f"[持仓] {market_type}匹配了 {matched_count} 只股票")

            if matched_count > 0:
                return True  # 已获取部分数据，返回成功

            # 再次解析（备用格式）
            try:
                data = response.json()
            except:
                data = {}

            if 'data' in data:
                print(f"[持仓] data字段: {list(data['data'].keys())}")
                if 'diff' in data['data']:
                    diff_count = len(data['data']['diff'])
                    print(f"[持仓] 找到 {diff_count} 条股票数据")
                    matched_count = 0
                    for item in data['data']['diff']:
                        market_code = item.get('f13', '')
                        stock_code = item.get('f12', '')
                        full_code = f"{market_code}.{stock_code}"
                        if full_code in code_map:
                            idx = code_map[full_code]
                            price = item.get('f2', 0)
                            if price and price != 0:
                                holdings[idx]['price'] = price
                                holdings[idx]['change'] = item.get('f4', 0)  # 涨跌额
                                holdings[idx]['change_pct'] = item.get('f3', 0)  # 涨跌幅
                                matched_count += 1
                                print(f"[持仓] ✓ {stock_code}: 价格={holdings[idx]['price']}, 涨跌={holdings[idx]['change_pct']}%")
                            else:
                                print(f"[持仓] ✗ {stock_code}: 价格为0或空")
                        else:
                            print(f"[持仓] ? {full_code}: 不在映射中")
                    print(f"[持仓] {market_type}匹配了 {matched_count} 只股票")
                else:
                    print(f"[持仓] 没有找到diff字段")
            else:
                print(f"[持仓] 没有找到data字段, 完整响应: {data}")

        except Exception as e:
            print(f"[持仓] 获取{market_type}价格失败: {e}")
            import traceback
            traceback.print_exc()

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

    def get_manager_history(self):
        """获取基金经理变更历史
        从天天基金网获取基金经理变更记录
        """
        try:
            url = f"http://fund.eastmoney.com/f10/jjjl_{self.fund_code}.html"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Referer': 'http://fund.eastmoney.com/'
            }
            resp = requests.get(url, headers=headers, timeout=10)
            resp.encoding = 'utf-8'
            
            if resp.status_code != 200:
                return {'manager': '未知', 'history': [], 'recent_changed': False}
            
            text = resp.text
            
            # 尝试从页面中提取基金经理
            manager = '未知'
            # 更新后的匹配模式，适应基金经理页面HTML结构
            manager_patterns = [
                # 匹配表格中的经理姓名链接
                r'<a[^>]*href="[^"]*jjjl[^"]*"[^>]*>([^<]{2,6})</a>',
                # 匹配姓名列中的纯文本
                r'<td[^>]*>\s*([\u4e00-\u9fff]{2,4})\s*</td>',
                # 匹配JSON格式
                r'"jjjl"\s*[:=]\s*"([^"]+)"',
                r'"MANAGER"\s*[:=]\s*"([^"]+)"',
                # 匹配文字
                r'基金经理[：:]\s*([^<\n&]{2,10})',
                r'<span class="manager-name">([^<]+)</span>',
            ]
            for pattern in manager_patterns:
                m = re.search(pattern, text)
                if m:
                    mgr = m.group(1).strip()
                    # 过滤掉非名字内容
                    if mgr and mgr not in ['经理', '基金', '基金经理', 'unknown', '&nbsp;', '姓名', '任职'] and len(mgr) >= 2:
                        manager = mgr
                        break
            
            # 检查近期是否有基金经理变更（近180天）
            # 通过检查基金公告中是否有"基金经理变更"关键词
            recent_changed = False
            change_date = ''
            try:
                # 搜索基金公告
                news_url = f"https://np-anotice-stock.eastmoney.com/api/security/ann?sr=-1&page_size=5&page_index=1&ann_type=SHA%2CSZA&client_source=web&stock_list=0.{self.fund_code}"
                news_resp = requests.get(news_url, headers=headers, timeout=5)
                if news_resp.status_code == 200:
                    news_data = news_resp.json()
                    items = news_data.get('data', {}).get('list', [])
                    for item in items:
                        title = item.get('title', '') or item.get('notice_title', '')
                        if '基金经理' in title and '变更' in title:
                            recent_changed = True
                            change_date = item.get('publish_time', '')
                            break
            except:
                pass
            
            return {
                'manager': manager,
                'recent_changed': recent_changed,
                'change_date': change_date,
                'history': [{'manager': manager}]  # 简化处理，仅返回当前经理
            }
        except Exception as e:
            print(f"[经理历史] 获取失败: {e}")
            return {'manager': '未知', 'history': [], 'recent_changed': False}
    
    def get_fund_strategy(self):
        """获取基金投资策略和风格
        从天天基金网基金档案页获取
        """
        try:
            url = f"http://fundf10.eastmoney.com/tsdata_{self.fund_code}.html"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Referer': 'http://fund.eastmoney.com/'
            }
            resp = requests.get(url, headers=headers, timeout=10)
            resp.encoding = 'utf-8'
            
            result = {
                'investment_objective': '',
                'investment_strategy': '',
                'risk_return': '',
                'industry_allocation': '',
                'investment_style': '未知'
            }
            
            if resp.status_code == 200:
                text = resp.text
                
                # 提取投资目标
                obj_match = re.search(r'投资目标[：:]\s*(.*?)(?:[。\n]|</)', text, re.DOTALL)
                if obj_match:
                    result['investment_objective'] = obj_match.group(1).strip()[:200]
                
                # 提取投资策略
                strat_match = re.search(r'投资策略[：:]\s*(.*?)(?:[。\n]|</)', text, re.DOTALL)
                if strat_match:
                    result['investment_strategy'] = strat_match.group(1).strip()[:200]
                
                # 提取风险收益特征
                risk_match = re.search(r'(?:风险收益|风险特征)[：:]\s*(.*?)(?:[。\n]|</)', text, re.DOTALL)
                if risk_match:
                    result['risk_return'] = risk_match.group(1).strip()[:200]
                
                # 判断投资风格
                if '成长' in text:
                    result['investment_style'] = '成长型'
                elif '价值' in text:
                    result['investment_style'] = '价值型'
                elif '平衡' in text or '混合' in text:
                    result['investment_style'] = '平衡型'
                elif '指数' in text:
                    result['investment_style'] = '指数型'
                elif '货币' in text:
                    result['investment_style'] = '货币型'
                elif '债券' in text:
                    result['investment_style'] = '债券型'
            
            return result
        except Exception as e:
            print(f"[基金策略] 获取失败: {e}")
            return {
                'investment_objective': '',
                'investment_strategy': '',
                'risk_return': '',
                'industry_allocation': '',
                'investment_style': '未知'
            }

    def get_fund_news(self, limit=10):
        """获取基金相关新闻和公告"""
        news_list = []
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'http://fund.eastmoney.com/'
        }
        
        # 1. 东方财富基金公告
        try:
            url = f"https://np-anotice-stock.eastmoney.com/api/security/ann?sr=-1&page_size={limit}&page_index=1&ann_type=SHA%2CSZA&client_source=web&stock_list=0.{self.fund_code}"
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                items = data.get('data', {}).get('list', [])
                for item in items[:limit]:
                    title = item.get('title', '') or item.get('notice_title', '')
                    if title:
                        news_list.append({
                            'title': title,
                            'datetime': item.get('publish_time', ''),
                            'source': '东方财富公告',
                            'type': '公告'
                        })
        except Exception as e:
            print(f"[基金新闻-公告] 获取失败: {e}")
        
        # 2. 天天基金网基金资讯
        if len(news_list) < limit:
            try:
                url = f"https://fundf10.eastmoney.com/jjgg_{self.fund_code}.html"
                resp = requests.get(url, headers=headers, timeout=10)
                resp.encoding = 'utf-8'
                if resp.status_code == 200:
                    items = re.findall(r'<li><a[^>]*href="([^"]*)"[^>]*title="([^"]*)"', resp.text)
                    for href, title in items[:limit]:
                        if title and len(title) > 5:
                            news_list.append({
                                'title': title,
                                'datetime': '',
                                'source': '天天基金网',
                                'type': '资讯'
                            })
            except Exception as e:
                print(f"[基金新闻-天天基金] 获取失败: {e}")
        
        # 去重
        seen = set()
        unique = []
        for n in news_list:
            t = n.get('title', '')
            if t and t not in seen:
                seen.add(t)
                unique.append(n)
        
        return unique[:limit]

    @staticmethod
    def get_benchmark_for_period(code, start_date, end_date):
        """为组合分析提供跨基金基准数据

        Args:
            code: 基金代码
            start_date: 起始日期 (YYYY-MM-DD)
            end_date: 截止日期 (YYYY-MM-DD)

        Returns:
            list[dict]: 基准净值数据列表
        """
        try:
            import datetime as dt
            sd = dt.datetime.strptime(start_date, '%Y-%m-%d')
            ed = dt.datetime.strptime(end_date, '%Y-%m-%d')
            days = (ed - sd).days

            # 临时实例化以复用数据获取逻辑
            analyzer = FundAnalyzer(code)
            df = analyzer.get_fund_history(days + 30)  # 多取一些确保覆盖
            if df is None:
                return []

            df = df.sort_values('date')
            df = df[(df['date'] >= start_date) & (df['date'] <= end_date)]

            records = []
            for _, row in df.iterrows():
                records.append({
                    'date': row['date'],
                    'value': row['net_value']
                })
            return records

        except Exception as e:
            traceback.print_exc()
            print(f"[基准数据-区间] 获取失败: {e}")
            return []

    def get_benchmark_data(self, days=120):
        """获取沪深300指数历史数据用于基准对比"""
        try:
            url = f'https://push2his.eastmoney.com/api/qt/stock/kline/get?secid=1.000300&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61&klt=101&fqt=1&end=20500101&lmt={days}'
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Referer': 'https://quote.eastmoney.com/'
            }
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if data and data.get('data') and data['data'].get('klines'):
                    klines = data['data']['klines']
                    result = []
                    for line in klines:
                        parts = line.split(',')
                        result.append({
                            'date': parts[0],
                            'value': float(parts[2])  # 收盘价
                        })
                    return result
            return []
        except Exception as e:
            print(f"[基准] 获取沪深300失败: {e}")
            return []

    def get_risk_metrics(self, days=365):
        """从历史净值计算风险指标"""
        try:
            df = self.get_fund_history(days)
            if df is None or len(df) < 20:
                return {'sharpe_ratio': None, 'max_drawdown': None, 'volatility': None,
                        'sortino_ratio': None, 'calmar_ratio': None, 'annualized_return': None}

            # 按日期升序排列
            df = df.sort_values('date')
            values = df['net_value'].values.astype(float)

            # 日收益率
            daily_returns = (values[1:] - values[:-1]) / values[:-1]

            # 年化收益率
            total_return = (values[-1] - values[0]) / values[0]
            n_days = len(values) - 1
            annualized_return = (1 + total_return) ** (252 / n_days) - 1 if n_days > 0 else 0

            # 年化波动率
            volatility = float(np.std(daily_returns, ddof=1) * np.sqrt(252))

            # 无风险利率 2%
            risk_free_rate = 0.02

            # 夏普比率
            sharpe_ratio = (annualized_return - risk_free_rate) / volatility if volatility > 0 else 0

            # 最大回撤
            peak = np.maximum.accumulate(values)
            drawdown = (values - peak) / peak
            max_drawdown = float(np.min(drawdown))

            # 索提诺比率（只用下行波动）
            downside = daily_returns[daily_returns < 0]
            downside_vol = float(np.std(downside, ddof=1) * np.sqrt(252)) if len(downside) > 0 else volatility
            sortino_ratio = (annualized_return - risk_free_rate) / downside_vol if downside_vol > 0 else 0

            # Calmar比率
            calmar_ratio = annualized_return / abs(max_drawdown) if max_drawdown != 0 else 0

            return {
                'sharpe_ratio': round(sharpe_ratio, 3),
                'max_drawdown': round(max_drawdown * 100, 2),
                'volatility': round(volatility * 100, 2),
                'sortino_ratio': round(sortino_ratio, 3),
                'calmar_ratio': round(calmar_ratio, 3),
                'annualized_return': round(annualized_return * 100, 2)
            }
        except Exception as e:
            print(f"[风险指标] 计算失败: {e}")
            import traceback
            traceback.print_exc()
            return {'sharpe_ratio': None, 'max_drawdown': None, 'volatility': None,
                    'sortino_ratio': None, 'calmar_ratio': None, 'annualized_return': None}

    def get_long_term_stability_analysis(self, days=1260):
        """
        长期稳定性模块（持有决策）
        Sharpe比率 + 最大回撤分析（智能降级：优先5年→3年→1年）
        规则：Sharpe > 1 且 回撤 < 15% → 得分 > 70 → 持有
        """
        try:
            # 智能降级策略：优先使用更长期数据，数据不足时降级
            df = self.get_fund_history(days)
            actual_days = days
            data_years = '5年'
            
            if df is None or len(df) < 60:
                # 尝试3年数据
                df = self.get_fund_history(756)
                actual_days = 756
                data_years = '3年'
            
            if df is None or len(df) < 30:
                # 尝试1年数据
                df = self.get_fund_history(252)
                actual_days = 252
                data_years = '1年'
            
            if df is None or len(df) < 20:
                return {'score': 0, 'recommendation': '数据不足', 'sharpe_ratio': None, 
                        'max_drawdown': None, 'volatility': None, 'reason': '历史数据不足1年，无法分析'}

            df = df.sort_values('date')
            values = df['net_value'].values.astype(float)
            daily_returns = (values[1:] - values[:-1]) / values[:-1]
            
            # 年化指标
            total_return = (values[-1] - values[0]) / values[0]
            n_days = len(values) - 1
            annualized_return = (1 + total_return) ** (252 / n_days) - 1 if n_days > 0 else 0
            volatility = float(np.std(daily_returns, ddof=1) * np.sqrt(252))
            risk_free_rate = 0.02
            sharpe_ratio = (annualized_return - risk_free_rate) / volatility if volatility > 0 else 0
            
            # 最大回撤
            peak = np.maximum.accumulate(values)
            drawdown = (values - peak) / peak
            max_drawdown = float(np.min(drawdown)) * 100

            # 根据数据期限调整评估标准
            # 1年数据：标准略宽松（市场短期波动大）
            # 3年数据：标准适中
            # 5年数据：标准严格
            if actual_days <= 252:
                # 1年数据标准
                sharpe_threshold = 0.8
                dd_threshold = -20
                sharpe_good = 1.2
                dd_good = -12
            elif actual_days <= 756:
                # 3年数据标准
                sharpe_threshold = 0.6
                dd_threshold = -25
                sharpe_good = 1.0
                dd_good = -15
            else:
                # 5年数据标准
                sharpe_threshold = 0.5
                dd_threshold = -25
                sharpe_good = 0.8
                dd_good = -15

            # 计算得分
            sharpe_score = min(sharpe_ratio * 40, 50) if sharpe_ratio > 0 else max(sharpe_ratio * 40, -20)
            dd_score = 50 if max_drawdown > dd_threshold else max(50 + (max_drawdown - dd_threshold) * 2, 10)
            total_score = min(sharpe_score + dd_score, 100)

            # 决策
            if sharpe_ratio > sharpe_good and max_drawdown > dd_good:
                recommendation = '持有'
                reason = f'基于{data_years}数据：Sharpe={sharpe_ratio:.2f}，最大回撤={max_drawdown:.1f}%，长期稳定性优秀'
            elif sharpe_ratio > sharpe_threshold and max_drawdown > dd_threshold - 10:
                recommendation = '谨慎持有'
                reason = f'基于{data_years}数据：Sharpe={sharpe_ratio:.2f}，最大回撤={max_drawdown:.1f}%，表现尚可'
            elif sharpe_ratio < 0 or max_drawdown < -40:
                recommendation = '不建议持有'
                reason = f'基于{data_years}数据：Sharpe={sharpe_ratio:.2f}<0或回撤={max_drawdown:.1f}%<-40%，风险较大'
            else:
                recommendation = '观望'
                reason = f'基于{data_years}数据：Sharpe={sharpe_ratio:.2f}，回撤={max_drawdown:.1f}%，建议观望'

            return {
                'score': round(total_score, 1),
                'recommendation': recommendation,
                'sharpe_ratio': round(sharpe_ratio, 3),
                'max_drawdown': round(max_drawdown, 2),
                'volatility': round(volatility * 100, 2),
                'annualized_return': round(annualized_return * 100, 2),
                'data_period': data_years,
                'actual_days': n_days,
                'reason': reason
            }
        except Exception as e:
            print(f"[长期稳定性] 分析失败: {e}")
            return {'score': 0, 'recommendation': '分析失败', 'reason': str(e)}

    def get_downside_prediction(self, days=252):
        """
        1年内下跌预测模块（卖出决策）
        线性回归趋势 + VaR（价值-at-风险，蒙特卡洛模拟1年路径）
        规则：趋势斜率 < -5% 且 VaR > 10% → 得分 > 70 → 卖出
        """
        try:
            # 智能降级：优先1年数据，不足时用半年数据
            df = self.get_fund_history(days)
            if df is None or len(df) < 20:
                # 尝试半年数据
                df = self.get_fund_history(126)
            
            if df is None or len(df) < 15:
                return {'score': 0, 'recommendation': '数据不足', 'trend_slope': None, 
                        'var_95': None, 'reason': '历史数据不足，无法进行下跌风险预测'}

            df = df.sort_values('date').tail(252)  # 使用最近数据
            values = df['net_value'].values.astype(float)
            dates = np.arange(len(values))
            daily_returns = (values[1:] - values[:-1]) / values[:-1]

            # 线性回归趋势
            if len(values) > 5:
                z = np.polyfit(dates, values, 1)
                trend_slope = (z[0] / values.mean()) * 252 * 100  # 年化斜率百分比
            else:
                trend_slope = 0

            # VaR计算 (95%置信度，使用历史模拟法)
            var_95 = np.percentile(daily_returns, 5) * 100 if len(daily_returns) > 0 else 0
            var_95 = abs(var_95)

            # 蒙特卡洛模拟
            mu = np.mean(daily_returns)
            sigma = np.std(daily_returns)
            n_simulations = 1000
            n_days_ahead = 252
            simulated_returns = np.random.normal(mu, sigma, (n_simulations, n_days_ahead))
            portfolio_values = values[-1] * np.exp(np.cumsum(simulated_returns, axis=1))
            final_values = portfolio_values[:, -1]
            prob_loss = np.mean(final_values < values[-1]) * 100
            expected_return_1y = np.mean((final_values - values[-1]) / values[-1]) * 100

            # 根据数据量调整评估标准
            data_days = len(values)
            if data_days < 60:
                # 数据较少，放宽标准
                trend_threshold = -3
                var_threshold = 8
            else:
                trend_threshold = -5
                var_threshold = 10

            # 计算得分
            trend_score = min(max(-trend_slope * 5, 0), 40) if trend_slope < 0 else 0
            var_score = min((var_95 - 5) * 4, 30) if var_95 > 5 else 0
            prob_score = min(prob_loss * 0.6, 30) if prob_loss > 30 else 0
            total_score = min(trend_score + var_score + prob_score, 100)

            # 决策
            if trend_slope < trend_threshold and var_95 > var_threshold and total_score > 70:
                recommendation = '卖出'
                reason = f'趋势斜率={trend_slope:.1f}%<{trend_threshold}%，VaR(95%)={var_95:.1f}%>{var_threshold}%，下跌概率>{prob_loss:.0f}%，建议卖出'
            elif trend_slope < -2 or var_95 > 8:
                recommendation = '谨慎'
                reason = f'趋势斜率={trend_slope:.1f}%，VaR(95%)={var_95:.1f}%，存在下行风险'
            elif expected_return_1y > 10:
                recommendation = '可持有'
                reason = f'预期1年收益={expected_return_1y:.1f}%，趋势向好'
            else:
                recommendation = '观望'
                reason = f'趋势斜率={trend_slope:.1f}%，VaR(95%)={var_95:.1f}%，需观察'

            return {
                'score': round(total_score, 1),
                'recommendation': recommendation,
                'trend_slope': round(trend_slope, 2),
                'var_95': round(var_95, 2),
                'prob_loss_1y': round(prob_loss, 1),
                'expected_return_1y': round(expected_return_1y, 2),
                'data_days': data_days,
                'reason': reason
            }
        except Exception as e:
            print(f"[下跌预测] 分析失败: {e}")
            return {'score': 0, 'recommendation': '分析失败', 'reason': str(e)}

    def get_upside_prediction(self, days=180):
        """
        1年内上涨预测模块（买入决策）
        MACD动量 + ARIMA时间序列预测
        规则：MACD金叉 且 预测回报 > 5% → 得分 > 70 → 买入
        """
        try:
            # 智能降级：优先6个月数据，不足时用3个月
            df = self.get_fund_history(days)
            if df is None or len(df) < 30:
                # 尝试3个月数据
                df = self.get_fund_history(60)
            
            if df is None or len(df) < 20:
                return {'score': 0, 'recommendation': '数据不足', 'macd_signal': None,
                        'predicted_return': None, 'reason': '历史数据不足，无法进行上涨动能预测'}

            df = df.sort_values('date')
            values = df['net_value'].values.astype(float)

            # MACD计算（使用更短的周期适应小数据量）
            min_period = min(12, len(values) // 2) if len(values) > 20 else 6
            max_period = min(26, len(values) // 2) if len(values) > 40 else 20
            signal_period = min(9, len(values) // 4) if len(values) > 30 else 6
            
            ema12 = self._ema(values, max(min_period, 6))
            ema26 = self._ema(values, max(max_period, 12))
            macd_line = ema12 - ema26
            signal_line = self._ema(macd_line, max(signal_period, 4))
            macd_histogram = macd_line - signal_line

            # MACD状态检测
            macd_current = macd_line[-1] if len(macd_line) > 0 else 0
            macd_prev = macd_line[-3] if len(macd_line) > 3 else macd_line[0] if len(macd_line) > 0 else 0
            signal_current = signal_line[-1] if len(signal_line) > 0 else 0
            signal_prev = signal_line[-3] if len(signal_line) > 3 else signal_line[0] if len(signal_line) > 0 else 0

            # 金叉检测
            golden_cross = macd_prev < signal_prev and macd_current > signal_current
            macd_positive = macd_current > 0
            histogram_rising = len(macd_histogram) > 2 and macd_histogram[-1] > macd_histogram[-2]

            # 简单趋势预测
            n_predict = min(30, len(values) // 2)
            recent_values = values[-n_predict:] if n_predict > 5 else values
            x = np.arange(len(recent_values))
            z = np.polyfit(x, recent_values, 1)
            predicted_30d = recent_values[-1] + z[0] * 30
            predicted_return = ((predicted_30d - values[-1]) / values[-1]) * 100

            # 动量指标
            momentum_10d = (values[-1] - values[-11]) / values[-11] * 100 if len(values) > 10 else 0
            momentum_20d = (values[-1] - values[-21]) / values[-21] * 100 if len(values) > 20 else 0

            # 根据数据量调整标准
            data_days = len(values)
            if data_days < 60:
                predict_threshold = 3  # 数据少时降低要求
            else:
                predict_threshold = 5

            # 计算得分
            macd_score = 30 if (golden_cross or (macd_positive and histogram_rising)) else (15 if macd_positive else 0)
            predict_score = min(max(predicted_return * 4, 0), 40) if predicted_return > 0 else 0
            momentum_score = min(max(momentum_20d * 2, 0), 30) if momentum_20d > 0 else 0
            total_score = min(macd_score + predict_score + momentum_score, 100)

            # 决策
            if (golden_cross or (macd_positive and histogram_rising)) and predicted_return > predict_threshold and total_score > 70:
                recommendation = '买入'
                reason = f'MACD{"金叉" if golden_cross else "正向"}，动量转正，预测收益={predicted_return:.1f}%>{predict_threshold}%，上涨概率较高'
            elif macd_positive and predicted_return > 0:
                recommendation = '可考虑买入'
                reason = f'MACD>0，预测收益={predicted_return:.1f}%，短期动量={momentum_10d:.1f}%'
            elif predicted_return > 8:
                recommendation = '持有观察'
                reason = f'预测收益={predicted_return:.1f}%，但需等待MACD确认'
            else:
                recommendation = '观望'
                reason = f'MACD{"金叉" if golden_cross else ("正向" if macd_positive else "负向")}，预测收益={predicted_return:.1f}%'

            return {
                'score': round(total_score, 1),
                'recommendation': recommendation,
                'macd_signal': '金叉' if golden_cross else ('正向' if macd_positive else '负向'),
                'macd_histogram': round(macd_histogram[-1], 6) if len(macd_histogram) > 0 else 0,
                'predicted_return': round(predicted_return, 2),
                'momentum_20d': round(momentum_20d, 2),
                'momentum_10d': round(momentum_10d, 2),
                'data_days': data_days,
                'reason': reason
            }
        except Exception as e:
            print(f"[上涨预测] 分析失败: {e}")
            return {'score': 0, 'recommendation': '分析失败', 'reason': str(e)}

    def _ema(self, data, period):
        """计算指数移动平均"""
        ema = [data[0]]
        multiplier = 2 / (period + 1)
        for i in range(1, len(data)):
            ema.append((data[i] - ema[-1]) * multiplier + ema[-1])
        return np.array(ema)

    def get_fund_fees(self):
        """从天天基金网爬取费率结构"""
        result = {'management_fee': '未知', 'custodian_fee': '未知', 'service_fee': '未知',
                  'subscription_fees': [], 'redemption_fees': []}
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'http://fund.eastmoney.com/'
        }
        try:
            url = f"http://fundf10.eastmoney.com/jjfl_{self.fund_code}.html"
            resp = requests.get(url, headers=headers, timeout=10)
            resp.encoding = 'utf-8'
            if resp.status_code == 200:
                text = resp.text
                # 管理费
                m = re.search(r'管理费率[：:]\s*([^<]+)', text)
                if m: result['management_fee'] = m.group(1).strip()
                # 托管费
                m = re.search(r'托管费率[：:]\s*([^<]+)', text)
                if m: result['custodian_fee'] = m.group(1).strip()
                # 销售服务费
                m = re.search(r'销售服务费率[：:]\s*([^<]+)', text)
                if m: result['service_fee'] = m.group(1).strip()
                # 申购费阶梯
                sub_pattern = re.findall(r'申购金额[^<]*<td[^>]*>([^<]+)</td>', text)
                sub_rates = re.findall(r'<td[^>]*>([\d.]+%[^<]*)</td>', text)
                # 赎回费
                red_pattern = re.findall(r'持有期限[^<]*<td[^>]*>([^<]+)</td>', text)
                red_rates = re.findall(r'<td[^>]*>([\d.]+%[^<]*)</td>', text)
        except Exception as e:
            print(f"[费率] 获取失败: {e}")
        return result


