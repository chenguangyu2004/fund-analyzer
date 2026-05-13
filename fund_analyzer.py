import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json
import re
import traceback
import time

class FundAnalyzer:
    """基金分析类"""

    def __init__(self, fund_code):
        self.fund_code = fund_code
        self.fund_data = None
        self.session = requests.Session()

    def get_fund_info(self, holdings=None):
        """获取基金基本信息和净值数据
        Args:
            holdings: 可选，持仓数据（用于实时估值计算）
        """
        try:
            # 同时获取官方净值和实时估算净值
            official_data = self._get_official_net_value()
            realtime_data = self._get_realtime_estimate(holdings)

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
        """获取官方净值数据（支持 QDII 等特殊基金）"""
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/102.0.0.0 Safari/537.36',
            'Referer': 'http://fund.eastmoney.com/'
        }
        fund_name = None
        net_value = 0
        accumulated_value = 0
        nav_date = '未知'
        
        # 方法1: 从天天基金网 jjjz 页面获取
        try:
            url = f"http://fundf10.eastmoney.com/jjjz_{self.fund_code}.html"
            print(f"[官方净值] 方法1: {url}")
            response = requests.get(url, headers=headers, timeout=10)
            response.encoding = 'utf-8'
            
            if response.status_code == 200:
                # 提取基金名称
                name_patterns = [
                    r'"SHORTNAME":"([^"]+)"', r'"name":"([^"]+)"',
                    r'"NAME":"([^"]+)"', r'"fundName":"([^"]+)"',
                    r'"FUNDNAME":"([^"]+)"'
                ]
                for pattern in name_patterns:
                    name_match = re.search(pattern, response.text)
                    if name_match:
                        fund_name = name_match.group(1)
                        break
                
                if not fund_name:
                    title_match = re.search(r'<title>([^<]+?)_基金历史净值_', response.text)
                    if title_match:
                        fund_name = title_match.group(1).strip()
                    else:
                        title_match = re.search(r'<title>([^<]+)</title>', response.text)
                        if title_match:
                            fund_name = re.sub(r'\(\d{6}\)', '', title_match.group(1).replace('_', '').replace('基金详情', '').replace('天天基金网', '')).strip()
                
                # 提取净值
                net_value_match = re.search(r'"dwjz":"([\d.]+)"', response.text)
                accumulated_match = re.search(r'"ljjz":"([\d.]+)"', response.text)
                date_match = re.search(r'"jzrq":"(\d{8})"', response.text)
                
                if net_value_match:
                    net_value = float(net_value_match.group(1))
                    accumulated_value = float(accumulated_match.group(1)) if accumulated_match else net_value
                    if date_match:
                        date_str = date_match.group(1)
                        nav_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
        except Exception as e:
            print(f"[官方净值] 方法1失败: {e}")
        
        # 方法2: 通过 fundgz 实时API获取
        if net_value <= 0:
            try:
                url2 = f"http://fundgz.1234567.com.cn/js/{self.fund_code}.js"
                print(f"[官方净值] 方法2(fundgz): {url2}")
                r = requests.get(url2, headers=headers, timeout=5)
                if r.status_code == 200:
                    json_str = r.text.strip()
                    if json_str.startswith('jsonpgz(') and json_str.endswith(');'):
                        json_str = json_str[8:-2]
                    data = json.loads(json_str)
                    net_value = float(data.get('dwjz', 0))
                    accumulated_value = net_value
                    if data.get('gztime'):
                        nav_date = data['gztime'][:10]
                    print(f"[官方净值] 方法2成功: 净值={net_value}")
            except Exception as e:
                print(f"[官方净值] 方法2失败: {e}")
        
        # 方法3: 使用东方财富API
        if net_value <= 0:
            try:
                url3 = f"https://fundmobapi.eastmoney.com/FundMNewApi/FundMNFInfo?pageIndex=1&pageSize=3&plat=Android&product=EFund&Version=1&Fcodes={self.fund_code}"
                print(f"[官方净值] 方法3(东方财富API): {url3}")
                r = requests.get(url3, headers=headers, timeout=5)
                if r.status_code == 200:
                    data = r.json()
                    if data and data.get('Datas') and len(data['Datas']) > 0:
                        item = data['Datas'][0]
                        net_value = float(item.get('NAV', 0))
                        accumulated_value = float(item.get('NAV', 0))
                        nav_date = item.get('PDATE', '未知')
                        fund_name = item.get('SHORTNAME', fund_name)
                        print(f"[官方净值] 方法3成功: 净值={net_value}, 名称={fund_name}")
            except Exception as e:
                print(f"[官方净值] 方法3失败: {e}")
        
        print(f"[官方净值] 最终结果: 净值={net_value}, 日期={nav_date}, 名称={fund_name}")
        
        if net_value <= 0:
            print("[官方净值] 所有方法均失败")
            return None
        
        if fund_name:
            # 清理名称中的各种后缀
            for suffix in ['_ 基金档案 _ 天天基金网', '_基金档案_', '_ 基金历史净值 _ 天天基金网',
                           '_基金历史净值_', '_天天基金网', '基金历史净值 基金档案',
                           '基金历史净值', '基金档案', '天天基金网']:
                fund_name = fund_name.replace(suffix, '')
            fund_name = fund_name.strip()
        
        return {
            'fund_name': fund_name if fund_name else f'基金{self.fund_code}',
            'net_value': net_value,
            'accumulated_value': accumulated_value,
            'day_growth': 0,
            'nav_date': nav_date,
            'fund_manager': '未知',
            'org_name': '未知',
            'fund_type': '未知',
            'foundation_date': '未知'
        }



    def _get_realtime_estimate(self, holdings=None):
        """获取实时估算净值（基于股票持仓）
        优先使用天天基金接口，同时使用持仓股票计算作为备用
        """
        result = None
        
        # 方法1: 从天天基金获取实时估算
        try:
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
                gsz = float(data.get('gsz', 0))
                gszzl = float(data.get('gszzl', 0))
                if gsz > 0:
                    result = {
                        'estimated_value': gsz,
                        'estimated_growth': gszzl
                    }
                    print(f"[实时估值] 天天基金接口成功: 估值{gsz}, 涨跌{gszzl}%")
        except Exception as e:
            print(f"[实时估值] 天天基金接口失败: {e}")
        
        # 方法2: 如果天天基金接口失败但有持仓数据，自己计算
        if result is None and holdings and len(holdings) > 0:
            try:
                result = self._calc_value_from_holdings(holdings)
            except Exception as e:
                print(f"[实时估值] 持仓计算失败: {e}")
        
        return result

    def _calc_value_from_holdings(self, holdings):
        """基于持仓股票实时价格计算基金估值"""
        # 获取最新官方净值作为基准
        official_data = self._get_official_net_value()
        if not official_data:
            return None
        
        official_nav = float(official_data.get('net_value', 0))
        if official_nav <= 0:
            return None
        
        # 提取持仓股票的实时价格
        total_weight = 0.0
        weighted_change = 0.0
        
        for h in holdings:
            ratio_str = h.get('ratio', '0%').replace('%', '').strip()
            try:
                ratio = float(ratio_str) / 100.0  # 转换为小数
            except ValueError:
                ratio = 0.0
            
            # 如果已经获取了实时价格和涨跌幅
            change_pct = h.get('change_pct')
            if change_pct is not None:
                weighted_change += ratio * (1 + change_pct / 100.0)
                total_weight += ratio
        
        # 如果成功获取了部分股票价格
        if total_weight > 0.01:
            # 加权平均价格比率（已获实时价格的持仓）
            avg_price_ratio = weighted_change / total_weight
            
            # 剩余未获取实时价格的持仓，假设与大盘（沪深300）同步，涨跌为0
            # 使用已获取股票的平均涨跌幅作为参考
            estimated_nav = official_nav * avg_price_ratio
            estimated_change = (estimated_nav - official_nav) / official_nav * 100 if official_nav > 0 else 0
            
            print(f"[实时估值] 持仓计算成功: 官方净值{official_nav}, 估算{estimated_nav:.4f}, 涨跌{estimated_change:.2f}%, 覆盖率{total_weight*100:.1f}%")
            return {
                'estimated_value': round(estimated_nav, 4),
                'estimated_growth': round(estimated_change, 2)
            }
        
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
        """获取基金前十大持仓（支持所有基金类型：A股/QDII/港股/美股）"""
        print(f"[持仓] 开始获取 {self.fund_code} 的持仓数据...")
        
        # 方法1: 天天基金网（A股基金）
        holdings = self._fetch_holdings_eastmoney(top)
        
        # 方法4: QDII基金专用（港股持仓）
        if not holdings or len(holdings) == 0:
            print("[持仓] 方法1失败，尝试QDII港股持仓接口...")
            holdings = self._fetch_holdings_qdii(top)
        
        # 方法2: 东方财富网（QDII/港股通基金备用）
        if not holdings or len(holdings) == 0:
            print("[持仓] 方法1/4失败，尝试东方财富...")
            holdings = self._fetch_holdings_eastmoney2(top)
        
        # 方法3: 雪球/好买基金（备用）
        if not holdings or len(holdings) == 0:
            print("[持仓] 方法2失败，尝试基金公司官网/天天基金APP接口...")
            holdings = self._fetch_holdings_xueqiu(top)
        
        if not holdings or len(holdings) == 0:
            print(f"[持仓] 所有方法均无法获取持仓数据")
            return []
        
        print(f"[持仓] OK 共获取 {len(holdings)} 条持仓记录")
        
        # 批量获取股票实时价格（爬取腾讯/新浪/网易）
        if holdings:
            self._get_stock_prices(holdings)
            # 打印价格获取结果
            success = sum(1 for h in holdings if h.get('price') is not None)
            print(f"[持仓] 价格获取: {success}/{len(holdings)} 成功")
        
        return holdings

    def _fetch_holdings_eastmoney(self, top=10):
        """方法1: 天天基金网（支持A股+港股/QDII持仓）"""
        try:
            # top=0 表示获取全部持仓（最多50只）
            actual_top = top if top > 0 else 50
            url = f"http://fundf10.eastmoney.com/FundArchivesDatas.aspx?type=jjcc&code={self.fund_code}&topline={actual_top}&rt={time.time()}"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Referer': 'http://fund.eastmoney.com/'
            }
            print(f"[持仓·方法1] 请求: {url}")
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code != 200:
                return []
            
            content_match = re.search(r'content:"(.*?)",', resp.text, re.DOTALL)
            if not content_match:
                return []
            
            html = content_match.group(1).replace('\\"', '"')
            tbody_match = re.search(r'<tbody>(.*?)</tbody>', html, re.DOTALL)
            if not tbody_match:
                return []
            
            holdings = []
            rows = re.findall(r'<tr>.*?</tr>', tbody_match.group(1), re.DOTALL)
            for row in rows:
                # 提取所有链接文本（排除非股票信息）
                all_links = re.findall(r'<a[^>]*>([^<]+)</a>', row)
                # 过滤出有效的股票数据：第一个是代码（纯数字），第二个是名称
                codes = [l for l in all_links if re.match(r'^\d{5,6}$', l.strip())]
                names = [l for l in all_links if not re.match(r'^\d+$', l.strip()) and l not in ['股吧', '行情', '变动详情'] and len(l) >= 2]
                # 比例：从td中提取XX.XX%
                ratio_match = re.search(r'<td[^>]*>(\d+\.?\d*%)</td>', row)
                
                if codes and names and ratio_match:
                    stock_code = codes[0]
                    stock_name = names[0]
                    holdings.append({
                        'seq': str(len(holdings)+1),
                        'code': stock_code,
                        'name': stock_name,
                        'ratio': ratio_match.group(1),
                        'price': None,
                        'change': None,
                        'change_pct': None
                    })
            if holdings:
                print(f"[持仓·方法1] OK 获取到 {len(holdings)} 条持仓")
                for h in holdings[:3]:
                    print(f"  {h['name']} ({h['code']}) - {h['ratio']}")
            return holdings
        except Exception as e:
            print(f"[持仓·方法1] 失败: {e}")
            return []

    def _fetch_holdings_eastmoney2(self, top=10):
        """方法2: 东方财富网（支持QDII/指数基金）"""
        try:
            # 东方财富基金持仓接口（新版）
            url = f"https://fundmobapi.eastmoney.com/FundMNewApi/FundMNHold?FCODE={self.fund_code}&MobileKey=&deviceid=&plat=Iphone&product=EFund&version=1&dateType=INCLUDE&showType=SZ&pageIndex=1&pageSize={top}"
            headers = {
                'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X)',
                'Referer': 'https://fund.eastmoney.com/'
            }
            print(f"[持仓·方法2] 请求东方财富: {url[:80]}")
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                holdings = []
                if data.get('Datas') and isinstance(data['Datas'], list):
                    for item in data['Datas']:
                        code = str(item.get('ZQDM', item.get('GPDM', ''))).strip()
                        name = str(item.get('ZQMC', item.get('GPJC', ''))).strip()
                        ratio = str(item.get('JZBL', item.get('PCCG', ''))).strip()
                        if code and name:
                            holdings.append({
                                'seq': str(len(holdings)+1),
                                'code': code,
                                'name': name,
                                'ratio': ratio + '%' if ratio and '%' not in ratio else ratio,
                                'price': None,
                                'change': None,
                                'change_pct': None
                            })
                    print(f"[持仓·方法2] 获取到 {len(holdings)} 条")
                    return holdings
            return []
        except Exception as e:
            print(f"[持仓·方法2] 失败: {e}")
            return []

    def _fetch_holdings_xueqiu(self, top=10):
        """方法3: 雪球/天天基金组合（备用）"""
        try:
            # 尝试天天基金网另一个接口
            url = f"https://fundf10.eastmoney.com/jjcc_{self.fund_code}.html"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Referer': f'http://fundf10.eastmoney.com/jjcc_{self.fund_code}.html'
            }
            print(f"[持仓·方法3] 请求: {url}")
            resp = requests.get(url, headers=headers, timeout=10)
            resp.encoding = 'utf-8'
            if resp.status_code == 200:
                # 尝试从页面脚本中提取JSON数据
                json_match = re.search(r'var\s+data\s*=\s*(\[.*?\]);', resp.text, re.DOTALL)
                if json_match:
                    import json
                    data = json.loads(json_match.group(1))
                    holdings = []
                    for item in data[:top]:
                        code = str(item.get('stockcode', item.get('code', '')))
                        name = str(item.get('stockname', item.get('name', '')))
                        ratio = str(item.get('ratio', item.get('jjsz', '')))
                        if code and name:
                            holdings.append({
                                'seq': str(len(holdings)+1),
                                'code': code,
                                'name': name,
                                'ratio': ratio + '%' if ratio and '%' not in ratio else ratio,
                                'price': None,
                                'change': None,
                                'change_pct': None
                            })
                    print(f"[持仓·方法3] 获取到 {len(holdings)} 条")
                    return holdings
            return []
        except Exception as e:
            print(f"[持仓·方法3] 失败: {e}")
            return []

    def _fetch_holdings_qdii(self, top=10):
        """方法4: QDII基金专用（港股持仓）"""
        try:
            # 使用天天基金网的港股持仓接口
            url = f"http://fundf10.eastmoney.com/FundArchivesDatas.aspx?type=hkcc&code={self.fund_code}&topline={top}&rt={time.time()}"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Referer': 'http://fundf10.eastmoney.com/'
            }
            print(f"[持仓·方法4-QDII] 请求港股持仓: {url[:80]}")
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code == 200:
                content_match = re.search(r'content:"(.*?)",', resp.text, re.DOTALL)
                if content_match:
                    html = content_match.group(1).replace('\\"', '"')
                    tbody_match = re.search(r'<tbody>(.*?)</tbody>', html, re.DOTALL)
                    if tbody_match:
                        holdings = []
                        rows = re.findall(r'<tr>.*?</tr>', tbody_match.group(1), re.DOTALL)
                        for row in rows:
                            # 港股代码通常是5位数字
                            code_match = re.search(r'<td><a[^>]*>(\d{5})</a>', row)
                            name_match = re.search(r'class="[^"]*tol[^"]*"[^>]*><a[^>]*>([^<]+)</a>', row)
                            ratio_match = re.search(r'<td[^>]*>(\d+\.?\d*%)</td>', row)
                            
                            if code_match and name_match and ratio_match:
                                holdings.append({
                                    'seq': str(len(holdings)+1),
                                    'code': code_match.group(1),
                                    'name': name_match.group(1).strip(),
                                    'ratio': ratio_match.group(1),
                                    'price': None,
                                    'change': None,
                                    'change_pct': None
                                })
                        if holdings:
                            print(f"[持仓·方法4-QDII] 获取到 {len(holdings)} 条港股持仓")
                            return holdings
            return []
        except Exception as e:
            print(f"[持仓·方法4-QDII] 失败: {e}")
            return []
    
    def _get_stock_prices(self, holdings):
        """批量获取所有持仓股票实时价格（腾讯财经+新浪财经+网易财经，一定要成功）"""
        print(f"[持仓] 开始获取 {len(holdings)} 只股票实时价格...")
        
        # 收集所有需要获取的代码，构建映射
        code_map = {}
        for idx, h in enumerate(holdings):
            code_map[h['code']] = idx
        
        # 方法1：腾讯财经API（主要方式，支持A股+港股+北交所）
        success = self._fetch_tencent_prices(holdings, code_map)
        s1 = sum(1 for h in holdings if h.get('price') is not None)
        print(f"[持仓] 腾讯API完成: {s1}/{len(holdings)} 只股票有价格")
        
        # 方法2：新浪财经API（备用）
        if s1 < len(holdings):
            print("[持仓] 腾讯API不完整，尝试新浪财经...")
            self._fetch_sina_prices(holdings, code_map)
            s2 = sum(1 for h in holdings if h.get('price') is not None)
            print(f"[持仓] 新浪API完成: {s2}/{len(holdings)} 只股票有价格")
        
        # 方法3：网易财经API（备用）
        if s1 < len(holdings):
            print("[持仓] 新浪API不完整，尝试网易财经...")
            self._fetch_163_prices(holdings, code_map)
            s3 = sum(1 for h in holdings if h.get('price') is not None)
            print(f"[持仓] 网易API完成: {s3}/{len(holdings)} 只股票有价格")
        
        final = sum(1 for h in holdings if h.get('price') is not None)
        print(f"[持仓] 所有方法完成: {final}/{len(holdings)} 只股票有价格")

    def _fetch_tencent_prices(self, holdings, code_map):
        """腾讯财经API获取股票价格（支持A股+港股+美股+北交所）"""
        try:
            import random, time
            
            # 构建腾讯API代码列表
            tencent_codes = []
            valid_codes = []
            for code in code_map.keys():
                if len(code) == 5:  # 港股
                    tc = f'hk{code}'
                elif code.startswith('6'):
                    tc = f'sh{code}'
                elif code.startswith(('0', '3')):
                    tc = f'sz{code}'
                elif code.startswith(('4', '8', '9')):  # 北交所
                    tc = f'bj{code}'
                else:
                    continue
                tencent_codes.append(tc)
                valid_codes.append(code)
            
            if not tencent_codes:
                return False
            
            # 使用Session保持连接
            session = requests.Session()
            session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Referer': 'https://gu.qq.com/'
            })
            
            success_count = 0
            # 分批请求，每批10只
            for i in range(0, len(tencent_codes), 10):
                batch = tencent_codes[i:i+10]
                batch_codes = valid_codes[i:i+10]
                url = f"http://qt.gtimg.cn/q={','.join(batch)}"
                
                try:
                    resp = session.get(url, timeout=8)
                    resp.encoding = 'utf-8'
                    if resp.status_code != 200:
                        time.sleep(random.uniform(0.2, 0.5))
                        continue
                    
                    # 解析腾讯API返回
                    # 格式: var hq_str_sh600000="1~茅台~2000.00~+2.0%~..."
                    for line in resp.text.split('\n'):
                        line = line.strip()
                        if not line or '=' not in line:
                            continue
                        eq_idx = line.index('=')
                        var_name = line[:eq_idx].strip().replace('var ', '').replace('const ', '')
                        data_str = line[eq_idx+1:].strip().strip('"')
                        
                        if not data_str or '~' not in data_str:
                            continue
                        
                        parts = data_str.split('~')
                        if len(parts) < 5:
                            continue
                        
                        # 从var_name提取股票代码（去掉v_或hq_str_前缀）
                        raw_code = var_name
                        for prefix in ['v_', 'hq_str_']:
                            if raw_code.startswith(prefix):
                                raw_code = raw_code[len(prefix):]
                                break
                        
                        # 去掉市场前缀获取原始代码
                        stock_code = raw_code
                        for p in ['sh', 'sz', 'hk', 'bj']:
                            if stock_code.startswith(p) and len(stock_code) > len(p):
                                stock_code = stock_code[len(p):]
                                break
                        
                        if stock_code not in code_map:
                            continue
                        
                        try:
                            # 腾讯API字段: parts[1]=名称, parts[2]=代码, parts[3]=当前价, parts[4]=昨收
                            # 港股和A股字段位置不同，统一用公式计算涨跌幅
                            price = float(parts[3]) if len(parts) > 3 and parts[3] and float(parts[3]) > 0 else 0
                            prev_close = float(parts[4]) if len(parts) > 4 and parts[4] and float(parts[4]) > 0 else price
                            
                            if price > 0 and prev_close > 0:
                                idx = code_map[stock_code]
                                change = price - prev_close
                                change_pct = (change / prev_close) * 100
                                holdings[idx]['price'] = price
                                holdings[idx]['change'] = round(change, 4)
                                holdings[idx]['change_pct'] = round(change_pct, 2)
                                success_count += 1
                                print(f"[腾讯] OK {stock_code}: 价格={price}, 涨跌={change_pct:.2f}%")
                        except (ValueError, IndexError):
                            continue
                    
                    time.sleep(random.uniform(0.2, 0.5))
                except Exception as e:
                    print(f"[腾讯] 批次失败: {e}")
                    time.sleep(random.uniform(0.3, 0.6))
                    continue
            
            return success_count > 0
        except Exception as e:
            print(f"[腾讯] 整体失败: {e}")
            return False

    def _fetch_sina_prices(self, holdings, code_map):
        """新浪财经API获取股票价格"""
        try:
            import random, time
            
            # 构建新浪API代码列表
            sina_codes = []
            valid_codes = []
            for code in code_map.keys():
                if len(code) == 5:  # 港股
                    sc = f'hk{code}'
                elif code.startswith('6'):
                    sc = f'sh{code}'
                elif code.startswith(('0', '3')):
                    sc = f'sz{code}'
                else:
                    continue
                sina_codes.append(sc)
                valid_codes.append(code)
            
            if not sina_codes:
                return False
            
            session = requests.Session()
            session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Referer': 'https://finance.sina.com.cn/'
            })
            
            success_count = 0
            for i in range(0, len(sina_codes), 10):
                batch = sina_codes[i:i+10]
                batch_codes = valid_codes[i:i+10]
                url = f"https://hq.sinajs.cn/list={','.join(batch)}"
                
                try:
                    resp = session.get(url, timeout=8)
                    resp.encoding = 'gbk'
                    if resp.status_code != 200:
                        continue
                    
                    for line in resp.text.split('\n'):
                        line = line.strip()
                        if '=' not in line:
                            continue
                        eq_idx = line.index('=')
                        var_name = line[:eq_idx].strip()
                        data_str = line[eq_idx+1:].strip().strip('"').strip("'")
                        
                        if not data_str or ',' not in data_str:
                            continue
                        
                        # var_name格式: hq_str_sh600000
                        raw_code = var_name.replace('hq_str_', '').replace('var ', '').strip()
                        stock_code = raw_code
                        for p in ['sh', 'sz', 'hk']:
                            if stock_code.startswith(p) and len(stock_code) > len(p):
                                stock_code = stock_code[len(p):]
                                break
                        
                        if stock_code not in code_map:
                            continue
                        
                        try:
                            # 新浪格式: 名称,今开,昨收,当前价,最高,最低,买价,卖价,成交量,成交额,...
                            parts = data_str.split(',')
                            if len(parts) < 4:
                                continue
                            price = float(parts[3]) if parts[3] else 0
                            prev_close = float(parts[2]) if len(parts) > 2 and parts[2] else price
                            
                            if price > 0 and prev_close > 0:
                                idx = code_map[stock_code]
                                change = price - prev_close
                                change_pct = (change / prev_close) * 100 if prev_close > 0 else 0
                                holdings[idx]['price'] = price
                                holdings[idx]['change'] = change
                                holdings[idx]['change_pct'] = change_pct
                                success_count += 1
                                print(f"[新浪] OK {stock_code}: 价格={price}, 涨跌={change_pct:.2f}%")
                        except (ValueError, IndexError):
                            continue
                    
                    time.sleep(random.uniform(0.2, 0.5))
                except Exception as e:
                    print(f"[新浪] 批次失败: {e}")
                    time.sleep(random.uniform(0.3, 0.6))
                    continue
            
            return success_count > 0
        except Exception as e:
            print(f"[新浪] 整体失败: {e}")
            return False

    def _fetch_163_prices(self, holdings, code_map):
        """网易财经API获取股票价格"""
        try:
            import random, time
            
            session = requests.Session()
            session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Referer': 'https://money.163.com/'
            })
            
            success_count = 0
            for h in holdings:
                code = h['code']
                if code in []:
                    continue
                try:
                    if len(code) == 5:  # 港股
                        url = f"http://api.money.126.net/data/feed/1{code},money.api"
                    elif code.startswith('6'):
                        url = f"http://api.money.126.net/data/feed/0{code},money.api"
                    else:
                        url = f"http://api.money.126.net/data/feed/1{code},money.api"
                    
                    resp = session.get(url, timeout=5)
                    if resp.status_code == 200 and resp.text:
                        text = resp.text.strip()
                        if text.endswith(';'):
                            text = text[:-1]
                        
                        # 网易返回JSONP格式: _ntes_quote_callback({"000001":{"price":...}});
                        import json
                        json_match = re.search(r'\{.*\}', text, re.DOTALL)
                        if json_match:
                            data = json.loads(json_match.group(0))
                            for sym, info in data.items():
                                sc = str(info.get('code', sym)).strip()
                                # 去掉前缀匹配原始代码
                                for prefix in ['sh', 'sz', 'hk', '0', '1']:
                                    if sc.startswith(prefix) and len(sc) > len(prefix):
                                        sc = sc[len(prefix):]
                                        break
                                if sc in code_map or sym in code_map:
                                    idx = code_map.get(sc) or code_map.get(sym)
                                    price = float(info.get('price', 0))
                                    prev = float(info.get('yestclose', info.get('prevclose', 0)))
                                    if price > 0:
                                        holdings[idx]['price'] = price
                                        change = price - prev if prev > 0 else 0
                                        change_pct = (change / prev) * 100 if prev > 0 else 0
                                        holdings[idx]['change'] = change
                                        holdings[idx]['change_pct'] = change_pct
                                        success_count += 1
                                        print(f"[网易] OK {sc}: 价格={price}, 涨跌={change_pct:.2f}%")
                except Exception as e:
                    print(f"[网易] 失败 {code}: {e}")
                    time.sleep(random.uniform(0.1, 0.3))
                    continue
            
            return success_count > 0
        except Exception as e:
            print(f"[网易] 整体失败: {e}")
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
                            print(f"[持仓] OK {stock_code}: 价格={price}, 涨跌={change_pct}%")

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
                                print(f"[持仓] OK {stock_code}: 价格={holdings[idx]['price']}, 涨跌={holdings[idx]['change_pct']}%")
                            else:
                                print(f"[持仓] FAIL {stock_code}: 价格为0或空")
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


