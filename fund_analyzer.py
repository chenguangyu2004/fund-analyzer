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

    def _get_fund_holdings(self, top=10):
        """获取基金前十大持仓股票及实时行情"""
        try:
            print("[持仓] 开始获取...", flush=True)
            with open('h:/基金app/debug.log', 'a', encoding='utf-8') as f:
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

            data = response.json()
            print(f"[持仓] {market_type}数据结构: {list(data.keys())}")

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
