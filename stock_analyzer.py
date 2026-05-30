"""
股票分析模块 - 获取股票详情、新闻、行业龙头股等
"""
import requests
import re
import json
from datetime import datetime
from logger import get_logger
import config

logger = get_logger("stock_analyzer")


class StockAnalyzer:
    """股票分析类"""
    
    # 行业龙头股数据库（从 data/industry_leaders.json 加载）
    INDUSTRY_LEADERS = config.load_data_json("industry_leaders.json", {})
    
    # 股票代码到行业映射（从 data/stock_industry_map.json 加载）
    STOCK_INDUSTRY_MAP = config.load_data_json("stock_industry_map.json", {})
    
    # 行业关键词映射（从 data/industry_keywords.json 加载）
    INDUSTRY_KEYWORDS = config.load_data_json("industry_keywords.json", {})
    
    def __init__(self, stock_code):
        self.stock_code = stock_code
        self.session = self._create_session()
        self._industry_cache = None  # 行业缓存，避免重复请求
        self._stock_name_cache = None  # 股票名称缓存
    
    def _create_session(self):
        """创建带反爬虫头的Session"""
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'Accept': '*/*',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Connection': 'keep-alive',
        })
        return session
    
    def get_stock_info(self):
        """获取股票详细信息"""
        result = {
            'code': self.stock_code,
            'name': self.stock_code,
            'market': self._identify_market(),
            'price': 0,
            'change': 0,
            'change_pct': 0,
            'prev_close': 0,
            'open': 0,
            'high': 0,
            'low': 0,
            'volume': 0,
            'amount': 0,
            'pe': 0,
            'pb': 0,
            'market_cap': 0,
            'update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        # 获取实时行情
        price_info = self._get_realtime_price()
        if price_info:
            result.update(price_info)
        
        # 获取补充数据（PE、PB、总市值、股息率等）
        extra_data = self._get_extra_data_from_tencent()
        if extra_data:
            result.update(extra_data)
        
        # 获取公司基本信息
        company_info = self._get_company_info()
        if company_info:
            result.update(company_info)
        
        # 获取持股分析
        holder_analysis = self._get_holder_analysis()
        if holder_analysis:
            result['holder_analysis'] = holder_analysis
        
        # 获取新闻
        news = self.get_stock_news(10)
        result['news'] = news
        
        # 获取行业龙头股（使用AI动态搜索）
        leaders = self.get_industry_leaders(10)
        result['industry_leaders'] = leaders
        
        # 获取财务数据
        financial = self.get_financial_report()
        if financial:
            result['financial'] = financial
        
        return result
    
    def _identify_market(self):
        """识别股票市场"""
        code = self.stock_code
        if len(code) == 5:
            return '港股'
        elif code.startswith('6'):
            return '上证A股'
        elif code.startswith('0') or code.startswith('3'):
            return '深证A股'
        elif code.startswith('8') or code.startswith('4') or code.startswith('9'):
            return '北交所'
        return '未知'
    
    def _get_realtime_price(self):
        """获取实时行情"""
        try:
            code = self.stock_code
            
            # 确定市场前缀和代码格式
            if len(code) == 5:
                # 港股：如果是4位数字前面加0，如"1211"变成"hk01211"
                symbol = f"hk{code.zfill(5)}"
            elif code.startswith('6'):
                symbol = f"sh{code}"
            elif code.startswith('0') or code.startswith('3'):
                symbol = f"sz{code}"
            elif code.startswith('8') or code.startswith('4') or code.startswith('9'):
                symbol = f"bj{code}"
            else:
                return None
            
            url = f'https://hq.sinajs.cn/list={symbol}'
            headers = {
                'User-Agent': 'Mozilla/5.0',
                'Referer': 'https://finance.sina.com.cn',
            }
            
            response = self.session.get(url, headers=headers, timeout=8)
            response.encoding = 'gbk'
            
            if response.status_code == 200:
                text = response.text
                match = re.search(r'["\']([^"\']+)["\']', text)
                if match:
                    data_str = match.group(1)
                    if data_str and ',' in data_str:
                        parts = data_str.split(',')
                        
                        # A股格式
                        if symbol.startswith(('sh', 'sz')) and len(parts) > 32:
                            name = parts[0]
                            open_price = self._safe_float(parts[1])
                            prev_close = self._safe_float(parts[2])
                            current = self._safe_float(parts[3])
                            high = self._safe_float(parts[4])
                            low = self._safe_float(parts[5])
                            volume = self._safe_float(parts[8])
                            amount = self._safe_float(parts[9])
                            pe = self._safe_float(parts[39]) if len(parts) > 39 else 0
                            pb = self._safe_float(parts[46]) if len(parts) > 46 else 0
                            
                            change = current - prev_close if current and prev_close else 0
                            change_pct = (change / prev_close * 100) if prev_close else 0
                            
                            return {
                                'name': name,
                                'open': open_price,
                                'prev_close': prev_close,
                                'price': current,
                                'high': high,
                                'low': low,
                                'volume': volume,
                                'amount': amount,
                                'change': round(change, 2),
                                'change_pct': round(change_pct, 2),
                                'pe': pe,
                                'pb': pb,
                            }
                        
                        # 港股格式 - 字段位置不同
                        elif symbol.startswith('hk') and len(parts) > 10:
                            name = parts[1] if len(parts) > 1 else ''
                            current = self._safe_float(parts[6])  # 现价
                            prev_close = self._safe_float(parts[7])  # 昨收
                            open_price = self._safe_float(parts[8])  # 今开
                            high = self._safe_float(parts[9])  # 最高
                            low = self._safe_float(parts[10])  # 最低
                            volume = self._safe_float(parts[12])  # 成交量
                            
                            change = current - prev_close if current and prev_close else 0
                            change_pct = (change / prev_close * 100) if prev_close else 0
                            
                            return {
                                'name': name,
                                'open': open_price,
                                'prev_close': prev_close,
                                'price': current,
                                'high': high,
                                'low': low,
                                'volume': volume,
                                'change': round(change, 2),
                                'change_pct': round(change_pct, 2),
                            }
                        
                        # 北交所格式
                        elif symbol.startswith('bj') and len(parts) > 5:
                            name = parts[0]
                            current = self._safe_float(parts[3])
                            prev_close = self._safe_float(parts[2])
                            open_price = self._safe_float(parts[1])
                            high = self._safe_float(parts[4])
                            low = self._safe_float(parts[5])
                            
                            change = current - prev_close if current and prev_close else 0
                            change_pct = (change / prev_close * 100) if prev_close else 0
                            
                            return {
                                'name': name,
                                'open': open_price,
                                'prev_close': prev_close,
                                'price': current,
                                'high': high,
                                'low': low,
                                'change': round(change, 2),
                                'change_pct': round(change_pct, 2),
                            }
        except Exception as e:
            logger.info(f"[行情] 获取失败: {e}")
        
        return None
    
    def _safe_float(self, val, default=0):
        """安全转换为浮点数"""
        if val is None or val == '' or val == '-' or val == 'None':
            return default
        try:
            return float(val)
        except:
            return default
    
    def _get_extra_data_from_tencent(self):
        """从腾讯财经API获取补充数据（PE、PB、总市值、股息率）
        新浪API返回字段有限，腾讯API包含更全面的数据
        """
        result = {}
        try:
            code = self.stock_code
            # 确定腾讯API的代码前缀
            if len(code) == 5:
                tcode = f"hk{code.zfill(5)}"
            elif code.startswith('6'):
                tcode = f"sh{code}"
            elif code.startswith(('0', '3')):
                tcode = f"sz{code}"
            elif code.startswith(('8', '4', '9')):
                tcode = f"bj{code}"
            else:
                return None
            
            url = f"http://qt.gtimg.cn/q={tcode}"
            resp = self.session.get(url, timeout=8)
            resp.encoding = 'utf-8'
            
            if resp.status_code == 200 and '~' in resp.text:
                parts = resp.text.split('~')
                # 腾讯API字段位置（A股）
                # 以下字段索引基于标准腾讯API返回格式
                if len(parts) > 50:
                    # PE (市盈率) - 通常在47或39位置
                    pe = self._safe_float(parts[47]) or self._safe_float(parts[39])
                    if pe:
                        result['pe'] = pe
                    # PB (市净率)
                    pb = self._safe_float(parts[48])
                    if pb:
                        result['pb'] = pb
                    # 总市值（元）
                    market_cap = self._safe_float(parts[78]) if len(parts) > 78 else 0
                    if not market_cap:
                        market_cap = self._safe_float(parts[45]) * 100000000  # 亿转元
                    if market_cap:
                        result['market_cap'] = market_cap
                    # 流通市值（元）
                    circ_cap = self._safe_float(parts[77]) if len(parts) > 77 else 0
                    if circ_cap:
                        result['circulating_cap'] = circ_cap
                    # 股息率（如果存在）
                    dividend = self._safe_float(parts[75]) if len(parts) > 75 else 0
                    if dividend and dividend > 0:
                        result['dividend_yield'] = dividend
            return result if result else None
        except Exception as e:
            logger.info(f"[腾讯补充数据] 获取失败: {e}")
            return None
    
    def _get_company_info(self):
        """获取公司基本信息"""
        result = {}
        
        # 先从新浪获取名称
        try:
            code = self.stock_code
            if len(code) == 5:
                symbol = f"hk{code.zfill(5)}"
            elif code.startswith('6'):
                symbol = f"sh{code}"
            elif code.startswith('0') or code.startswith('3'):
                symbol = f"sz{code}"
            elif code.startswith(('8', '4', '9')):
                symbol = f"bj{code}"
            else:
                return None
            
            url = f'https://hq.sinajs.cn/list={symbol}'
            headers = {
                'User-Agent': 'Mozilla/5.0',
                'Referer': 'https://finance.sina.com.cn',
            }
            response = self.session.get(url, headers=headers, timeout=5)
            response.encoding = 'gbk'
            
            if response.status_code == 200:
                match = re.search(r'"([^"]+)"', response.text)
                if match:
                    parts = match.group(1).split(',')
                    if len(parts) > 0 and parts[0]:
                        result['name'] = parts[0]
                        result['company_name'] = parts[0]
        except Exception as e:
            logger.info(f"[公司信息-新浪] 获取失败: {e}")
        
        # 尝试从东方财富获取更多信息
        try:
            code = self.stock_code
            if code.startswith('6'):
                secid = f"1.{code}"
            else:
                secid = f"0.{code}"
            
            url = f'https://push2.eastmoney.com/api/qt/stock/get?secid={secid}&fields=f57,f58,f100,f102,f103,f104,f105,f106,f107,f108,f109,f170,f171'
            headers = {
                'User-Agent': 'Mozilla/5.0',
                'Referer': 'https://finance.eastmoney.com/'
            }
            response = self.session.get(url, headers=headers, timeout=5)
            if response.status_code == 200:
                data = response.json()
                if data and data.get('data'):
                    d = data['data']
                    if not result.get('name'):
                        result['name'] = d.get('f58', '')
                        result['company_name'] = d.get('f58', '')
        except Exception as e:
            logger.info(f"[公司信息-EM] 获取失败: {e}")
        
        # 获取行业信息
        industry = self._get_stock_industry()
        if industry:
            result['industry'] = industry
        
        return result if result else None
    
    def _get_stock_industry(self):
        """获取股票所属行业（带缓存）"""
        if self._industry_cache is not None:
            return self._industry_cache
        result = self._get_stock_industry_impl()
        self._industry_cache = result
        return result
    
    def _get_stock_industry_impl(self):
        """获取股票所属行业 - 优先从东方财富获取申万行业分类"""
        code = self.stock_code
        
        # 1. 优先从东方财富获取行业信息（最准确）
        try:
            if code.startswith('6'):
                secid = f"1.{code}"
            elif code.startswith('0') or code.startswith('3'):
                secid = f"0.{code}"
            elif code.startswith(('8', '4', '9')):
                secid = f"0.{code}"
            else:
                secid = f"0.{code}"
            
            url = f'https://push2.eastmoney.com/api/qt/stock/get?secid={secid}&fields=f57,f58,f100'
            headers = {
                'User-Agent': 'Mozilla/5.0',
                'Referer': 'https://finance.eastmoney.com/'
            }
            response = self.session.get(url, headers=headers, timeout=5)
            if response.status_code == 200:
                data = response.json()
                if data and data.get('data'):
                    industry_em = data['data'].get('f100', '')  # 东方财富行业
                    if industry_em:
                        logger.info(f"[行业识别] 东方财富行业: {industry_em}")
                        # 映射东方财富行业到我们的分类
                        industry_mapping = {
                            '计算机': '计算机/软件服务', '软件': '计算机/软件服务', 'IT服务': '计算机/软件服务',
                            '互联网': '互联网', '传媒': '互联网',
                            '新能源': '新能源汽车', '汽车': '新能源汽车', '电动车': '新能源汽车',
                            '白酒': '白酒', '啤酒': '白酒',
                            '银行': '银行',
                            '保险': '保险',
                            '医药': '医药', '中药': '医药', '生物': '医药',
                            '医疗器械': '医疗设备',
                            '光伏': '光伏', '太阳能': '光伏',
                            '云计算': '计算机/软件服务', '大数据': '计算机/软件服务',
                            '宠物': '宠物经济',
                            '半导': '半导体', '芯片': '半导体', '集成电路': '半导体',
                            '通信': '互联网', '电子': '半导体',
                            '游戏': '互联网',
                            '家电': '家电',
                            '食品': '食品',
                            '房地产': '房地产',
                            '证券': '券商', '券商': '券商',
                            '基建': '基建', '建筑': '基建',
                        }
                        for keyword, ind in industry_mapping.items():
                            if keyword in industry_em:
                                return ind
                        # 如果没有匹配到映射，直接使用东方财富的行业名称
                        return industry_em
        except Exception as e:
            logger.info(f"[行业识别] EM接口失败: {e}")
        
        # 2. 从映射表获取
        industry = self.STOCK_INDUSTRY_MAP.get(code, '')
        if industry:
            return industry
        
        # 3. 根据公司名称关键词匹配行业
        stock_name = ''
        try:
            if code.startswith('6'):
                symbol = f"sh{code}"
            elif code.startswith('0') or code.startswith('3'):
                symbol = f"sz{code}"
            else:
                symbol = f"sz{code}"
            
            url = f'https://hq.sinajs.cn/list={symbol}'
            headers = {
                'User-Agent': 'Mozilla/5.0',
                'Referer': 'https://finance.sina.com.cn',
            }
            response = self.session.get(url, headers=headers, timeout=5)
            response.encoding = 'gbk'
            
            if response.status_code == 200:
                match = re.search(r'["\']([^"\']+)["\']', response.text)
                if match:
                    stock_name = match.group(1).split(',')[0] if ',' in match.group(1) else match.group(1)
                    logger.info(f"[行业识别] 股票名称: {stock_name}")
                    for keyword, ind in self.INDUSTRY_KEYWORDS.items():
                        if keyword in stock_name:
                            logger.info(f"[行业识别] 匹配成功: {keyword} -> {ind}")
                            return ind
        except Exception as e:
            logger.info(f"[行业识别] 获取名称失败: {e}")
        
        logger.info(f"[行业识别] 无法识别 {code} ({stock_name}) 的行业")
        return ''
    
    def _get_holder_analysis(self):
        """获取持股分析"""
        try:
            code = self.stock_code
            
            # 东方财富股东户数API
            url = f'https://datacenter-web.eastmoney.com/api/data/v1/get?reportName=RPT_F10_SHAREHOLDER_NUM&columns=END_DATE,TOTAL_SHRHLD_NUM,SHRHLD_NUM&filter=(SECURITY_CODE%3D%22{code}%22)&pageNumber=1&pageSize=4&sortTypes=-1&sortColumns=END_DATE'
            headers = {
                'User-Agent': 'Mozilla/5.0',
                'Referer': 'https://data.eastmoney.com/'
            }
            
            response = self.session.get(url, headers=headers, timeout=5)
            if response.status_code == 200:
                data = response.json()
                if data and data.get('result') and data['result'].get('data'):
                    items = data['result']['data']
                    if items:
                        latest = items[0]
                        return {
                            'holder_count': latest.get('TOTAL_SHRHLD_NUM', 0),
                            'report_date': latest.get('END_DATE', ''),
                            'holder_data': items[:4],
                        }
        except Exception as e:
            logger.info(f"[持股分析] 获取失败: {e}")
        
        # 返回一些默认信息
        return {
            'holder_count': '暂无数据',
            'report_date': '暂无数据',
            'holder_data': [],
            'note': '该数据暂不可用'
        }
    
    def get_stock_news(self, limit=20):
        """获取股票相关新闻 — 多源聚合（A股双源 + 港股双源 + 兜底搜索）"""
        news_list = []
        code = self.stock_code
        is_a_stock = len(code) == 6 and code.isdigit()
        is_hk_stock = len(code) == 5

        # 获取股票名称用于关键词搜索
        stock_name = self._stock_name_cache
        if not stock_name and is_hk_stock:
            stock_name = self._get_stock_name_from_api(code)
            self._stock_name_cache = stock_name

        # ══════════════════════════════════
        # 新浪个股新闻页（A股+港股均支持）
        # ══════════════════════════════════
        if is_a_stock:
            if code.startswith('6'):
                sina_symbol = f"sh{code}"
            elif code.startswith('0') or code.startswith('3'):
                sina_symbol = f"sz{code}"
            else:
                sina_symbol = f"sz{code}"
        elif is_hk_stock:
            sina_symbol = f"hk{code}"
        else:
            sina_symbol = None

        if sina_symbol:
            self._fetch_sina_stock_page(news_list, sina_symbol, limit)

        # ══════════════════════════════════
        # A股补充：东方财富公告
        # ══════════════════════════════════
        if is_a_stock and len(news_list) < limit:
            self._fetch_eastmoney_announce(news_list, code, limit)

        # ══════════════════════════════════
        # 港股补充：腾讯快讯
        # ══════════════════════════════════
        if is_hk_stock and len(news_list) < limit:
            self._fetch_tencent_hk_quick(news_list, code, limit)

        # ══════════════════════════════════
        # 兜底：新浪搜索（只要知道名称）
        # ══════════════════════════════════
        if len(news_list) == 0 and stock_name and stock_name != code:
            self._fetch_sina_search(news_list, stock_name, limit)

        # 去重
        seen_titles = set()
        unique_news = []
        for n in news_list:
            t = n.get('title', '')
            if t and t not in seen_titles:
                seen_titles.add(t)
                unique_news.append(n)

        logger.info(f"[新闻] 最终返回 {len(unique_news)} 条 (A股={is_a_stock} 港股={is_hk_stock})")
        return unique_news[:limit]

    # ── 新闻子方法 ──

    def _get_stock_name_from_api(self, code):
        """从腾讯API获取股票名称"""
        try:
            symbol = f"hk{code.zfill(5)}"
            url = f"http://qt.gtimg.cn/q={symbol}"
            resp = self.session.get(url, timeout=5)
            if resp.status_code == 200 and '~' in resp.text:
                parts = resp.text.split('~')
                if len(parts) > 2:
                    return parts[1]
        except Exception:
            pass
        return code

    def _fetch_sina_stock_page(self, news_list, sina_symbol, limit):
        """从新浪个股新闻页获取A股新闻"""
        try:
            url = f'https://vip.stock.finance.sina.com.cn/corp/go.php/vCB_AllNewsStock/symbol/{sina_symbol}/pageno/1.phtml'
            resp = self.session.get(url, headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://finance.sina.com.cn/'}, timeout=10)
            resp.encoding = 'gbk'

            if resp.status_code == 200:
                # 匹配: 日期 + 可选时间 + <a href="url" ...>标题</a>
                pattern = r'(\d{4}-\d{2}-\d{2})\s*[\d:]*.*?<a[^>]*href\s*=\s*["\']([^"\']+)["\'][^>]*>\s*([^<]{4,})\s*</a>'
                matches = re.findall(pattern, resp.text)
                logger.info(f"[新浪个股新闻] 解析到 {len(matches)} 条")

                for date, news_url, title in matches:
                    title = title.strip()
                    title = title.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>').replace('&quot;', '"')
                    if not title or len(title) < 4:
                        continue
                    news_list.append({
                        'title': title,
                        'publish_time': date,
                        'source': '新浪财经',
                        'type': '新闻',
                        'url': news_url if news_url.startswith('http') else f'https:{news_url}',
                    })
                    if len(news_list) >= limit:
                        break
        except Exception as e:
            logger.info(f"[新浪个股新闻] 获取失败: {e}")

    def _fetch_eastmoney_announce(self, news_list, code, limit):
        """从东方财富获取A股公司公告"""
        try:
            if code.startswith('6'):
                secid = f"1.{code}"
            else:
                secid = f"0.{code}"

            remain = limit - len(news_list)
            url = f'https://np-anotice-stock.eastmoney.com/api/security/ann?sr=-1&page_size={remain}&page_index=1&ann_type=SHA%2CSZA&client_source=web&stock_list={secid}'
            resp = self.session.get(url, headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://data.eastmoney.com/'}, timeout=8)

            if resp.status_code == 200:
                data = resp.json()
                items = (data.get('data') or {}).get('list', []) or []
                logger.info(f"[东方财富公告] 获取到 {len(items)} 条")
                for item in items:
                    title = item.get('title', '') or item.get('notice_title', '')
                    if not title:
                        continue
                    news_list.append({
                        'title': title,
                        'publish_time': str(item.get('publish_time', ''))[:10],
                        'source': '东方财富',
                        'type': '公告',
                        'url': f"https://data.eastmoney.com/notices/detail/{secid}/{item.get('notice_id', '')}.html",
                    })
                    if len(news_list) >= limit:
                        break
        except Exception as e:
            logger.info(f"[东方财富公告] 获取失败: {e}")

    def _fetch_sina_search(self, news_list, keyword, limit):
        """从新浪财经搜索API获取新闻（按股票名称关键词）"""
        try:
            from urllib.parse import quote
            remain = limit - len(news_list)
            url = f'https://feed.mix.sina.com.cn/api/roll/get?pageid=153&lid=2516&k={quote(keyword)}&num={remain}&page=1&r=0.5'
            resp = self.session.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=8)

            if resp.status_code == 200:
                data = resp.json()
                items = (data.get('result') or {}).get('data', [])
                logger.info(f"[新浪搜索] '{keyword}' → {len(items)} 条")
                for item in items:
                    title = item.get('title', '')
                    if not title:
                        continue
                    news_list.append({
                        'title': title,
                        'publish_time': item.get('ctime', '')[:10],
                        'source': '新浪财经',
                        'type': '新闻',
                        'url': item.get('url', ''),
                    })
                    if len(news_list) >= limit:
                        break
        except Exception as e:
            logger.info(f"[新浪搜索] 获取失败: {e}")

    def _fetch_tencent_hk_quick(self, news_list, code, limit):
        """从腾讯财经获取港股关联快讯"""
        try:
            symbol = f"hk{code.zfill(5)}"
            remain = limit - len(news_list)
            # 腾讯自选股快讯接口
            url = f'https://proxy.finance.qq.com/ifzqgtimg/appstock/news/info/search?symbol={symbol}&page=1&n={remain}'
            resp = self.session.get(url, headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://gu.qq.com/'}, timeout=8)

            if resp.status_code == 200:
                data = resp.json()
                items = (data.get('data') or {}).get('data', []) or []
                logger.info(f"[腾讯快讯] {symbol} → {len(items)} 条")
                for item in items:
                    title = item.get('title', '')
                    if not title:
                        continue
                    news_list.append({
                        'title': title,
                        'publish_time': item.get('publish_time', '')[:10] if item.get('publish_time') else '',
                        'source': '腾讯财经',
                        'type': '快讯',
                        'url': item.get('url', ''),
                    })
                    if len(news_list) >= limit:
                        break
        except Exception as e:
            logger.info(f"[腾讯快讯] 获取失败: {e}")
    
    def _get_industry_stocks(self, industry, limit=10):
        """获取同行业股票"""
        stocks = []
        
        # 如果有行业信息，从对应行业获取
        if industry and industry in self.INDUSTRY_LEADERS:
            leader_list = self.INDUSTRY_LEADERS[industry]
            # 过滤掉当前股票
            filtered = [s for s in leader_list if s['code'] != self.stock_code]
            
            # 使用新浪API获取价格
            try:
                # 准备股票代码
                stock_codes_for_sina = []
                for s in filtered[:limit]:
                    code = s['code']
                    if code.startswith('6'):
                        stock_codes_for_sina.append(f"sh{code}")
                    elif code.startswith(('0', '3')):
                        stock_codes_for_sina.append(f"sz{code}")
                    elif len(code) == 5:
                        stock_codes_for_sina.append(f"hk{code.zfill(5)}")
                    else:
                        stock_codes_for_sina.append(f"sz{code}")
                
                if stock_codes_for_sina:
                    codes_str = ','.join(stock_codes_for_sina)
                    url = f'https://hq.sinajs.cn/list={codes_str}'
                    headers = {
                        'User-Agent': 'Mozilla/5.0',
                        'Referer': 'https://finance.sina.com.cn',
                    }
                    response = self.session.get(url, headers=headers, timeout=8)
                    response.encoding = 'gbk'
                    
                    if response.status_code == 200:
                        text = response.text
                        # 解析每只股票的数据
                        for stock in filtered[:limit]:
                            try:
                                code = stock['code']
                                if code.startswith('6'):
                                    prefix = 'sh'
                                elif code.startswith('0') or code.startswith('3'):
                                    prefix = 'sz'
                                elif len(code) == 5:
                                    prefix = 'hk'
                                elif code.startswith(('8', '4', '9')):
                                    prefix = 'bj'
                                else:
                                    prefix = 'sz'
                                pattern = rf'hq_str_{prefix}{code}="([^"]+)"'
                                match = re.search(pattern, text)
                                if match:
                                    data_str = match.group(1)
                                    parts = data_str.split(',')
                                    if len(parts) > 5:
                                        name = parts[0]  # 名称在第一个位置
                                        current_price = self._safe_float(parts[3])  # 现价在第4个位置
                                        prev_close = self._safe_float(parts[2])  # 昨收在第3个位置
                                        change_pct = ((current_price - prev_close) / prev_close * 100) if prev_close else 0
                                        
                                        stocks.append({
                                            'code': stock['code'],
                                            'name': name if name else stock['name'],
                                            'price': current_price,
                                            'change_pct': round(change_pct, 2),
                                            'industry': industry,
                                        })
                                    else:
                                        # 数据不完整，使用基本信息
                                        stocks.append({
                                            'code': stock['code'],
                                            'name': stock['name'],
                                            'price': 0,
                                            'change_pct': 0,
                                            'industry': industry,
                                        })
                                else:
                                    # 没有匹配到数据，使用基本信息
                                    stocks.append({
                                        'code': stock['code'],
                                        'name': stock['name'],
                                        'price': 0,
                                        'change_pct': 0,
                                        'industry': industry,
                                    })
                            except Exception as e:
                                logger.info(f"[解析股票 {stock['code']}] 失败: {e}")
                                stocks.append({
                                    'code': stock['code'],
                                    'name': stock['name'],
                                    'price': 0,
                                    'change_pct': 0,
                                    'industry': industry,
                                })
            except Exception as e:
                logger.info(f"[行业股票获取] 失败: {e}")
                # 如果API失败，添加基本信息
                for stock in filtered[:limit]:
                    stocks.append({
                        'code': stock['code'],
                        'name': stock['name'],
                        'price': 0,
                        'change_pct': 0,
                        'industry': industry,
                    })
        else:
            logger.info(f"[行业股票] 未找到行业 '{industry}'")
            return []
        
        return stocks[:limit]
    
    def get_industry_leaders(self, limit=10):
        """获取行业龙头股 — 优先使用静态数据，AI仅作兜底"""
        industry = self._get_stock_industry()

        # ═══════════════════════════════════
        # 优先：静态行业龙头数据（准确、快速）
        # ═══════════════════════════════════
        if industry and industry in self.INDUSTRY_LEADERS:
            leaders = self.INDUSTRY_LEADERS[industry]
            filtered = [s for s in leaders if s['code'] != self.stock_code]
            if filtered:
                # 获取实时价格
                stocks = self._get_industry_stocks(industry, limit)
                if stocks:
                    logger.info(f"[行业龙头-静态] {industry} → {len(stocks)} 只")
                    return stocks
                # 价格获取失败时返回基础信息
                logger.info(f"[行业龙头-静态] {industry} → {len(filtered[:limit])} 只 (无价格)")
                return [{'code': s['code'], 'name': s['name'], 'price': 0, 'change_pct': 0, 'market': 'A股' if len(s['code'])==6 else '港股', 'industry': industry} for s in filtered[:limit]]

        # ═══════════════════════════════════
        # 兜底：AI动态搜索（行业不在静态数据中时）
        # ═══════════════════════════════════
        try:
            from deepseek_analyzer import DeepSeekAnalyzer
            import config as _cfg
            api_key = _cfg.DEEPSEEK_API_KEY
            
            prompt = f"""请列出"{industry or self.stock_code}"行业的龙头股，需要同时包含A股和港股。
要求：
1. 只返回JSON数组，不要其他文字
2. 每个元素包含code(股票代码，A股6位数字，港股5位数字)和name(股票名称)和market("A股"或"港股")
3. A股龙头5-6只，港股龙头3-4只，按市值从大到小排列
4. 代码必须是真实有效的股票代码
5. A股属于申万"{industry}"一级行业分类的龙头；港股属于恒生对应行业分类的龙头

示例格式：
[{{"code": "002230", "name": "科大讯飞", "market": "A股"}}, {{"code": "00700", "name": "腾讯控股", "market": "港股"}}]"""

            data = {
                "model": _cfg.DEEPSEEK_MODEL,
                "messages": [
                    {"role": "system", "content": "你是股票数据库，只返回JSON数据，不要其他文字。"},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.1,
                "max_tokens": 1000
            }
            
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            
            resp = requests.post(
                _cfg.DEEPSEEK_API_URL,
                headers=headers, json=data, timeout=30
            )
            
            if resp.status_code == 200:
                content = resp.json()['choices'][0]['message']['content'].strip()
                # 提取JSON
                json_match = re.search(r'\[.*\]', content, re.DOTALL)
                if json_match:
                    content = json_match.group(0)
                
                leaders = json.loads(content)
                logger.info(f"[行业龙头-AI] 获取到 {len(leaders)} 只")
                
                # 批量获取实时价格（腾讯API支持多代码查询）
                stock_codes_for_tencent = []
                for item in leaders[:limit]:
                    code = str(item.get('code', '')).zfill(5) if item.get('market') == '港股' else str(item.get('code', ''))
                    if not code:
                        continue
                    if len(code) == 5:
                        tc = f"hk{code}"
                    elif code.startswith('6'):
                        tc = f"sh{code}"
                    elif code.startswith(('0', '3')):
                        tc = f"sz{code}"
                    elif code.startswith(('8', '4', '9')):
                        tc = f"bj{code}"
                    else:
                        tc = f"sz{code}"
                    stock_codes_for_tencent.append((code, tc, item))
                
                # 批量请求价格
                price_map = {}
                if stock_codes_for_tencent:
                    codes_str = ','.join(tc for _, tc, _ in stock_codes_for_tencent)
                    try:
                        price_url = f"http://qt.gtimg.cn/q={codes_str}"
                        pr = requests.get(price_url, timeout=8)
                        pr.encoding = 'utf-8'
                        if pr.status_code == 200:
                            for code, tc, _ in stock_codes_for_tencent:
                                # 腾讯API每条数据以分号分隔
                                pattern = rf'v_{tc}="([^"]*)"'
                                match = re.search(pattern, pr.text)
                                if match and '~' in match.group(1):
                                    parts = match.group(1).split('~')
                                    if len(parts) > 5:
                                        price = self._safe_float(parts[3])
                                        prev_close = self._safe_float(parts[4])
                                        change_pct = round((price - prev_close) / prev_close * 100, 2) if price > 0 and prev_close > 0 else 0
                                        price_map[code] = (price, change_pct)
                    except Exception as e:
                        logger.info(f"[行业龙头-价格] 批量获取失败: {e}")
                
                # 组装结果
                stocks = []
                for item in leaders[:limit]:
                    code = str(item.get('code', '')).zfill(5) if item.get('market') == '港股' else str(item.get('code', ''))
                    name = item.get('name', '')
                    market = item.get('market', '')
                    if not code:
                        continue
                    
                    price, change_pct = price_map.get(code, (0, 0))
                    
                    stocks.append({
                        'code': code,
                        'name': name,
                        'price': price,
                        'change_pct': change_pct,
                        'market': market,
                        'industry': industry or '未知'
                    })
                
                if stocks:
                    return stocks
        except Exception as e:
            logger.info(f"[行业龙头-AI] 获取失败: {e}")
        
        # AI失败时，使用硬编码数据作为降级方案
        logger.info(f"[行业龙头] AI获取失败，使用降级方案")
        if industry and industry in self.INDUSTRY_LEADERS:
            filtered = [s for s in self.INDUSTRY_LEADERS[industry] if s['code'] != self.stock_code]
            return [{'code': s['code'], 'name': s['name'], 'price': 0, 'change_pct': 0, 'market': 'A股', 'industry': industry} for s in filtered[:limit]]
        
        return []

    # ═══════════════════════════════════════
    #  行业龙头 JSON 自动更新（每天一次）
    # ═══════════════════════════════════════
    @staticmethod
    def auto_refresh_industry_leaders():
        """后台异步：用AI扫描所有行业，发现新龙头自动写入JSON"""
        import threading
        def _run():
            try:
                from logger import get_logger as _gl
                _log = _gl("industry_refresh")
                import json, os, config as _cfg

                if not _cfg.DEEPSEEK_API_KEY:
                    _log.info("[行业刷新] 无API Key，跳过")
                    return

                # 检查上次刷新时间（每天一次）
                stamp_file = os.path.join(_cfg.DATA_DIR, ".industry_last_refresh")
                today = __import__('datetime').datetime.now().strftime("%Y-%m-%d")
                if os.path.exists(stamp_file):
                    with open(stamp_file) as f:
                        if f.read().strip() == today:
                            _log.info("[行业刷新] 今日已刷新，跳过")
                            return

                # 加载当前 JSON
                leaders_path = os.path.join(_cfg.DATA_DIR, "industry_leaders.json")
                with open(leaders_path, 'r', encoding='utf-8') as f:
                    current = json.load(f)

                existing_codes = set()
                for stocks in current.values():
                    for s in stocks:
                        existing_codes.add(s['code'])

                _log.info(f"[行业刷新] 开始扫描 {len(current)} 个行业...")

                import requests as _req
                added_any = False

                for industry in list(current.keys()):
                    try:
                        prompt = f'列出"{industry}"行业A股和港股龙头(各3-5只)，严格JSON: [{{"code":"股票代码","name":"名称","market":"A股/港股"}}]'
                        resp = _req.post(
                            _cfg.DEEPSEEK_API_URL,
                            headers={"Authorization": f"Bearer {_cfg.DEEPSEEK_API_KEY}", "Content-Type": "application/json"},
                            json={
                                "model": _cfg.DEEPSEEK_MODEL,
                                "messages": [{"role": "system", "content": "只返回JSON数组"}, {"role": "user", "content": prompt}],
                                "temperature": 0.1, "max_tokens": 800,
                            },
                            timeout=30,
                        )
                        if resp.status_code == 200:
                            content = resp.json()['choices'][0]['message']['content'].strip()
                            m = __import__('re').search(r'\[.*\]', content, __import__('re').DOTALL)
                            if m:
                                ai_leaders = json.loads(m.group(0))
                                new_entries = []
                                for item in ai_leaders:
                                    code = str(item.get('code', ''))
                                    name = item.get('name', '')
                                    if code and code not in existing_codes and len(code) in (5, 6):
                                        new_entries.append({'code': code, 'name': name})
                                        existing_codes.add(code)
                                if new_entries:
                                    current[industry].extend(new_entries)
                                    _log.info(f"[行业刷新] {industry} +{len(new_entries)}只: {[n['name'] for n in new_entries]}")
                                    added_any = True
                    except Exception as e:
                        _log.info(f"[行业刷新] {industry} 扫描失败: {e}")

                if added_any:
                    with open(leaders_path, 'w', encoding='utf-8') as f:
                        json.dump(current, f, ensure_ascii=False, indent=2)
                    # 清除 config 缓存，下次加载时读新文件
                    _cfg._data_cache.pop("industry_leaders.json", None)
                    _log.info("[行业刷新] JSON 已更新")

                # 写入时间戳（无论有无更新，避免重复扫描）
                with open(stamp_file, 'w') as f:
                    f.write(today)
                _log.info("[行业刷新] 完成")

            except Exception as e:
                try:
                    _log.info(f"[行业刷新] 失败: {e}")
                except:
                    pass

        t = threading.Thread(target=_run, daemon=True)
        t.start()

    def get_kline_data(self, period='daily', limit=60):
        """获取K线数据 - 使用腾讯财经API"""
        logger.info(f"[K线] 开始获取 {period} {self.stock_code}")
        try:
            code = self.stock_code
            
            # 确定腾讯symbol — 港股(5位)优先判断，避免0开头误判为深证
            if len(code) == 5:
                symbol = f"hk{code.zfill(5)}"
            elif code.startswith('6'):
                symbol = f"sh{code}"
            elif code.startswith('0') or code.startswith('3'):
                symbol = f"sz{code}"
            elif code.startswith(('8', '4', '9')):
                symbol = f"bj{code}"  # 北交所
            else:
                symbol = f"sz{code}"
            
            # 腾讯K线API: period参数 day/week/month
            period_map = {
                'daily': 'day',
                'weekly': 'week',
                'monthly': 'month',
            }
            p = period_map.get(period, 'day')
            
            url = f'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={symbol},{p},,,{limit},qfq'
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Referer': 'https://gu.qq.com/',
            }
            
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                stock_data = (data.get('data') or {}).get(symbol)
                if stock_data:
                    # 根据周期查找对应的key: qfqday或day, qfqweek或week
                    klines = stock_data.get(f'qfq{p}') or stock_data.get(p, [])
                    
                    result = []
                    for kline in klines:
                        # 格式: [日期, 开盘, 收盘, 最高, 最低, 成交量]
                        if len(kline) >= 6:
                            result.append({
                                'date': kline[0],
                                'open': self._safe_float(kline[1]),
                                'close': self._safe_float(kline[2]),
                                'high': self._safe_float(kline[3]),
                                'low': self._safe_float(kline[4]),
                                'volume': self._safe_float(kline[5]),
                            })
                    logger.info(f"[K线数据-腾讯] {period} 获取到 {len(result)} 条")
                    return result
                else:
                    logger.info(f"[K线数据-腾讯] symbol={symbol} 无数据")
        except Exception as e:
            logger.info(f"[K线数据-腾讯] 失败: {e}")
            logger.exception(f"error in stock_analyzer")
        
        # 降级：尝试东方财富API
        try:
            code = self.stock_code
            if code.startswith('6'):
                secid = f"1.{code}"
            elif code.startswith('0') or code.startswith('3'):
                secid = f"0.{code}"
            elif len(code) == 5:
                secid = f"116.{code}"
            elif code.startswith(('8', '4', '9')):
                secid = f"0.{code}"
            else:
                secid = f"0.{code}"
            
            period_map2 = {
                'daily': '101',
                'weekly': '102', 
                'monthly': '103',
            }
            ft = period_map2.get(period, '101')
            
            url = f'https://push2his.eastmoney.com/api/qt/stock/kline/get?secid={secid}&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61&klt={ft}&fqt=1&end=20500101&lmt={limit}'
            headers = {
                'User-Agent': 'Mozilla/5.0',
                'Referer': 'https://finance.eastmoney.com/'
            }
            
            response = self.session.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data and data.get('data') and data['data'].get('klines'):
                    klines = data['data']['klines']
                    result = []
                    for kline in klines:
                        parts = kline.split(',')
                        if len(parts) >= 6:
                            result.append({
                                'date': parts[0],
                                'open': self._safe_float(parts[1]),
                                'close': self._safe_float(parts[2]),
                                'high': self._safe_float(parts[3]),
                                'low': self._safe_float(parts[4]),
                                'volume': self._safe_float(parts[5]),
                            })
                    logger.info(f"[K线数据-东方财富] {period} 获取到 {len(result)} 条")
                    return result
        except Exception as e:
            logger.info(f"[K线数据-东方财富] 也失败: {e}")
        
        return []
    
    def get_financial_report(self):
        """获取简要财务数据"""
        try:
            code = self.stock_code
            url = f'https://datacenter-web.eastmoney.com/api/data/v1/get?reportName=RPT_F10_FINANCE_MAININDEX&columns=REPORT_DATE,BASIC_EPS,TOTAL_OPERATE_INCOME,OPERATE_PROFIT,PARENT_NETPROFIT,ROE,DEBT_ASSET_RATIO&filter=(SECURITY_CODE%3D%22{code}%22)&pageNumber=1&pageSize=4&sortTypes=-1&sortColumns=REPORT_DATE'
            
            headers = {
                'User-Agent': 'Mozilla/5.0',
                'Referer': 'https://data.eastmoney.com/'
            }
            
            response = self.session.get(url, headers=headers, timeout=5)
            if response.status_code == 200:
                data = response.json()
                if data and data.get('result') and data['result'].get('data'):
                    items = data['result']['data']
                    if items:
                        latest = items[0]
                        return {
                            'report_date': latest.get('REPORT_DATE', ''),
                            'eps': latest.get('BASIC_EPS', 0),
                            'revenue': latest.get('TOTAL_OPERATE_INCOME', 0),
                            'profit': latest.get('OPERATE_PROFIT', 0),
                            'net_profit': latest.get('PARENT_NETPROFIT', 0),
                            'roe': latest.get('ROE', 0),
                            'debt_ratio': latest.get('DEBT_ASSET_RATIO', 0),
                        }
        except Exception as e:
            logger.info(f"[财务数据] 获取失败: {e}")
        
        return None
