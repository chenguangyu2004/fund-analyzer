"""
股票分析模块 - 获取股票详情、新闻、行业龙头股等
"""
import requests
import re
import json
from datetime import datetime


class StockAnalyzer:
    """股票分析类"""
    
    # 按行业分类的龙头股数据库
    INDUSTRY_LEADERS = {
        '新能源汽车': [
            {'code': '002594', 'name': '比亚迪'},
            {'code': '300750', 'name': '宁德时代'},
            {'code': '600733', 'name': '北汽蓝谷'},
            {'code': '600418', 'name': '江淮汽车'},
            {'code': '601238', 'name': '广汽集团'},
            {'code': '000980', 'name': '众泰汽车'},
            {'code': '002126', 'name': '银轮股份'},
            {'code': '300124', 'name': '汇川技术'},
            {'code': '600104', 'name': '上汽集团'},
            {'code': '000625', 'name': '长安汽车'},
        ],
        '白酒': [
            {'code': '600519', 'name': '贵州茅台'},
            {'code': '000858', 'name': '五粮液'},
            {'code': '000568', 'name': '泸州老窖'},
            {'code': '002304', 'name': '洋河股份'},
            {'code': '000596', 'name': '古井贡酒'},
            {'code': '600197', 'name': '伊力特'},
            {'code': '603369', 'name': '今世缘'},
            {'code': '000799', 'name': '酒鬼酒'},
            {'code': '603589', 'name': '口子窖'},
            {'code': '000869', 'name': '张裕A'},
        ],
        '银行': [
            {'code': '600036', 'name': '招商银行'},
            {'code': '601398', 'name': '工商银行'},
            {'code': '601288', 'name': '农业银行'},
            {'code': '600000', 'name': '浦发银行'},
            {'code': '601328', 'name': '交通银行'},
            {'code': '601818', 'name': '光大银行'},
            {'code': '601166', 'name': '兴业银行'},
            {'code': '600015', 'name': '华夏银行'},
            {'code': '601009', 'name': '南京银行'},
            {'code': '600016', 'name': '民生银行'},
        ],
        '保险': [
            {'code': '601318', 'name': '中国平安'},
            {'code': '601628', 'name': '中国人寿'},
            {'code': '601601', 'name': '中国太保'},
            {'code': '601319', 'name': '中国人保'},
            {'code': '601336', 'name': '新华保险'},
        ],
        '家电': [
            {'code': '000333', 'name': '美的集团'},
            {'code': '000651', 'name': '格力电器'},
            {'code': '600690', 'name': '海尔智家'},
            {'code': '000100', 'name': 'TCL科技'},
            {'code': '002032', 'name': '苏泊尔'},
            {'code': '002508', 'name': '老板电器'},
            {'code': '603486', 'name': '科沃斯'},
        ],
        '医药': [
            {'code': '600276', 'name': '恒瑞医药'},
            {'code': '000538', 'name': '云南白药'},
            {'code': '600196', 'name': '复星医药'},
            {'code': '300760', 'name': '迈瑞医疗'},
            {'code': '301136', 'name': '义翘神州'},
            {'code': '002821', 'name': '凯莱英'},
            {'code': '300015', 'name': '爱尔眼科'},
            {'code': '000004', 'name': '国华网安'},
        ],
        '互联网': [
            {'code': '00700', 'name': '腾讯控股'},
            {'code': '09988', 'name': '阿里巴巴'},
            {'code': '03690', 'name': '美团'},
            {'code': '09888', 'name': '网易'},
            {'code': '01810', 'name': '小米集团'},
        ],
        '光伏': [
            {'code': '300274', 'name': '阳光电源'},
            {'code': '601012', 'name': '隆基绿能'},
            {'code': '600438', 'name': '通威股份'},
            {'code': '002459', 'name': '晶澳科技'},
            {'code': '601615', 'name': '明阳智能'},
            {'code': '688599', 'name': '天合光能'},
        ],
        '半导体': [
            {'code': '688981', 'name': '中芯国际'},
            {'code': '002371', 'name': '北方华创'},
            {'code': '603986', 'name': '兆易创新'},
            {'code': '688008', 'name': '澜起科技'},
            {'code': '688012', 'name': '中微公司'},
            {'code': '300976', 'name': '达瑞电子'},
        ],
        '旅游零售': [
            {'code': '601888', 'name': '中国中免'},
            {'code': '000069', 'name': '华侨城A'},
            {'code': '600054', 'name': '黄山旅游'},
            {'code': '002059', 'name': '云南旅游'},
            {'code': '600138', 'name': '中青旅'},
        ],
        '券商': [
            {'code': '600030', 'name': '中信证券'},
            {'code': '000776', 'name': '广发证券'},
            {'code': '600837', 'name': '海通证券'},
            {'code': '601211', 'name': '国泰君安'},
            {'code': '000166', 'name': '申万宏源'},
        ],
        '房地产': [
            {'code': '600048', 'name': '保利发展'},
            {'code': '000002', 'name': '万科A'},
            {'code': '001979', 'name': '招商蛇口'},
            {'code': '600606', 'name': '绿地控股'},
            {'code': '600383', 'name': '金地集团'},
        ],
        '基建': [
            {'code': '601668', 'name': '中国建筑'},
            {'code': '601390', 'name': '中国中铁'},
            {'code': '600585', 'name': '海螺水泥'},
            {'code': '601186', 'name': '中国铁建'},
        ],
        '食品': [
            {'code': '600887', 'name': '伊利股份'},
            {'code': '603288', 'name': '海天味业'},
            {'code': '000895', 'name': '双汇发展'},
            {'code': '002714', 'name': '牧原股份'},
            {'code': '300498', 'name': '温氏股份'},
        ],
        '云计算': [
            {'code': '300442', 'name': '润泽科技'},
            {'code': '300383', 'name': '光环新网'},
            {'code': '300846', 'name': '首都在线'},
            {'code': '300170', 'name': '汉得信息'},
            {'code': '300378', 'name': '鼎捷软件'},
            {'code': '600588', 'name': '用友网络'},
            {'code': '300451', 'name': '创业慧康'},
        ],
        '人工智能': [
            {'code': '002230', 'name': '科大讯飞'},
            {'code': '300024', 'name': '机器人'},
            {'code': '300418', 'name': '昆仑万维'},
            {'code': '688787', 'name': '海天瑞声'},
            {'code': '688256', 'name': '寒武纪'},
        ],
        '软件': [
            {'code': '300624', 'name': '万兴科技'},
            {'code': '002065', 'name': '东华软件'},
            {'code': '600571', 'name': '信雅达'},
            {'code': '300229', 'name': '拓尔思'},
            {'code': '300271', 'name': '华宇软件'},
        ],
        '医疗设备': [
            {'code': '300003', 'name': '乐普医疗'},
            {'code': '300529', 'name': '健帆生物'},
            {'code': '300760', 'name': '迈瑞医疗'},
            {'code': '002432', 'name': '九安医疗'},
            {'code': '300396', 'name': '迪瑞医疗'},
        ],
        '宠物经济': [
            {'code': '301498', 'name': '乖宝宠物'},
            {'code': '300673', 'name': '佩蒂股份'},
            {'code': '002891', 'name': '中宠股份'},
            {'code': '001222', 'name': '源飞宠物'},
            {'code': '301335', 'name': '天元宠物'},
            {'code': '001206', 'name': '依依股份'},
        ],
    }
    
    # 股票代码到行业的映射
    STOCK_INDUSTRY_MAP = {
        # 新能源汽车
        '002594': '新能源汽车', '300750': '新能源汽车', '600733': '新能源汽车',
        '600418': '新能源汽车', '601238': '新能源汽车', '000980': '新能源汽车',
        '002126': '新能源汽车', '300124': '新能源汽车', '600104': '新能源汽车',
        '000625': '新能源汽车', '1211': '新能源汽车', '01211': '新能源汽车',
        # 白酒
        '600519': '白酒', '000858': '白酒', '000568': '白酒', '002304': '白酒',
        '000596': '白酒', '600197': '白酒', '603369': '白酒', '000799': '白酒',
        # 保险
        '601318': '保险', '601628': '保险', '601601': '保险', '601319': '保险',
        # 银行
        '600036': '银行', '601398': '银行', '601288': '银行', '600000': '银行',
        '601328': '银行', '601818': '银行', '601166': '银行', '600015': '银行',
        # 家电
        '000333': '家电', '000651': '家电', '600690': '家电', '000100': '家电',
        # 医药
        '600276': '医药', '000538': '医药', '600196': '医药',
        '300015': '医药', '002007': '医药',
        # 光伏
        '300274': '光伏', '601012': '光伏', '600438': '光伏', '002459': '光伏',
        # 互联网/云计算
        '00700': '互联网', '09988': '互联网', '03690': '互联网', '00788': '互联网',
        '01810': '互联网', '09888': '互联网', '300846': '云计算', '300170': '云计算',
        '300050': '云计算', '300383': '云计算', '002230': '人工智能',
        '300024': '机器人', '300418': '云计算',
        # 半导体
        '688981': '半导体', '002371': '半导体', '603986': '半导体',
        '688008': '半导体', '688012': '半导体', '300976': '半导体',
        # 宠物经济
        '301498': '宠物经济', '300673': '宠物经济', '002891': '宠物经济',
        '001222': '宠物经济', '301335': '宠物经济', '001206': '宠物经济',
        # 医疗设备
        '300003': '医疗设备', '300760': '医疗设备', '002432': '医疗设备',
        '300624': '软件', '688787': '软件',
        # 其他
        '601888': '旅游零售', '600030': '券商', '600048': '房地产',
        '601668': '基建', '601390': '基建', '600585': '基建',
    }
    
    # 行业映射扩展（根据股票名称关键词）
    INDUSTRY_KEYWORDS = {
        '新能源': '新能源汽车',
        '汽车': '新能源汽车',
        '白酒': '白酒',
        '酒': '白酒',
        '银行': '银行',
        '保险': '保险',
        '医药': '医药',
        '医疗': '医药',
        '健康': '医药',
        '光伏': '光伏',
        '能源': '光伏',
        '互联网': '互联网',
        '云': '云计算',
        '数据': '云计算',
        '软件': '软件',
        '科技': '互联网',
        '半导': '半导体',
        '芯片': '半导体',
        '宠物': '宠物经济',
        '设备': '医疗设备',
        '器械': '医疗设备',
    }
    
    def __init__(self, stock_code):
        self.stock_code = stock_code
        self.session = self._create_session()
    
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
        
        # 获取行业龙头股
        industry = result.get('industry', '')
        leaders = self._get_industry_stocks(industry, 10)
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
            print(f"[行情] 获取失败: {e}")
        
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
            print(f"[腾讯补充数据] 获取失败: {e}")
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
            print(f"[公司信息-新浪] 获取失败: {e}")
        
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
            print(f"[公司信息-EM] 获取失败: {e}")
        
        # 获取行业信息
        industry = self._get_stock_industry()
        if industry:
            result['industry'] = industry
        
        return result if result else None
    
    def _get_stock_industry(self):
        """获取股票所属行业"""
        code = self.stock_code
        
        # 1. 先从映射表获取
        industry = self.STOCK_INDUSTRY_MAP.get(code, '')
        if industry:
            return industry
        
        # 2. 如果映射表没有，尝试从公司名称获取
        stock_name = ''
        try:
            # 获取股票名称
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
                    print(f"[行业识别] 股票名称: {stock_name}")
                    # 根据名称关键词匹配行业
                    for keyword, ind in self.INDUSTRY_KEYWORDS.items():
                        if keyword in stock_name:
                            print(f"[行业识别] 匹配成功: {keyword} -> {ind}")
                            return ind
        except Exception as e:
            print(f"[行业识别] 获取名称失败: {e}")
        
        # 3. 尝试从东方财富获取行业信息
        try:
            if code.startswith('6'):
                secid = f"1.{code}"
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
                    d = data['data']
                    industry_em = d.get('f100', '')  # 东方财富行业
                    print(f"[行业识别] 东方财富行业: {industry_em}")
                    # 映射东方财富行业到我们的分类
                    industry_mapping = {
                        '新能源': '新能源汽车', '汽车': '新能源汽车', '电动车': '新能源汽车',
                        '白酒': '白酒', '啤酒': '白酒',
                        '银行': '银行',
                        '保险': '保险',
                        '医药': '医药', '中药': '医药', '医疗器械': '医疗设备', '生物': '医药',
                        '光伏': '光伏', '太阳能': '光伏',
                        '互联网': '互联网', '软件': '软件', '云计算': '云计算', '大数据': '云计算',
                        '宠物': '宠物经济',
                        '半导': '半导体', '芯片': '半导体', '集成电路': '半导体',
                        '通信': '互联网', '电子': '半导体',
                        '游戏': '软件', '传媒': '软件',
                    }
                    for keyword, ind in industry_mapping.items():
                        if industry_em and keyword in industry_em:
                            return ind
        except Exception as e:
            print(f"[行业识别] EM接口失败: {e}")
        
        print(f"[行业识别] 无法识别 {code} ({stock_name}) 的行业")
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
            print(f"[持股分析] 获取失败: {e}")
        
        # 返回一些默认信息
        return {
            'holder_count': '暂无数据',
            'report_date': '暂无数据',
            'holder_data': [],
            'note': '该数据暂不可用'
        }
    
    def get_stock_news(self, limit=10):
        """获取股票相关新闻 - 只获取公司公告和个股资讯"""
        news_list = []
        code = self.stock_code
        stock_name = ''
        
        # 先获取股票名称
        try:
            if code.startswith('6'):
                symbol = f"sh{code}"
            elif code.startswith('0') or code.startswith('3'):
                symbol = f"sz{code}"
            elif len(code) == 5:
                symbol = f"hk{code.zfill(5)}"
            else:
                symbol = f"sz{code}"
            
            url = f'https://hq.sinajs.cn/list={symbol}'
            headers = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://finance.sina.com.cn'}
            resp = self.session.get(url, headers=headers, timeout=5)
            resp.encoding = 'gbk'
            if resp.status_code == 200:
                match = re.search(r'["\']([^"\']+)["\']', resp.text)
                if match:
                    stock_name = match.group(1).split(',')[0] if ',' in match.group(1) else match.group(1)
                    print(f"[新闻] 股票名称: {stock_name}")
        except:
            pass
        
        # 1. 东方财富公司公告（最权威，最相关）
        try:
            if code.startswith('6'):
                secid = f"1.{code}"
            elif code.startswith('0') or code.startswith('3'):
                secid = f"0.{code}"
            elif len(code) == 5:
                secid = f"116.{code}"
            else:
                secid = f"0.{code}"
            
            url = f'https://np-anotice-stock.eastmoney.com/api/security/ann?sr=-1&page_size={limit}&page_index=1&ann_type=SHA%2CSZA&client_source=web&stock_list={secid}'
            headers = {
                'User-Agent': 'Mozilla/5.0',
                'Referer': 'https://data.eastmoney.com/'
            }
            
            response = self.session.get(url, headers=headers, timeout=8)
            if response.status_code == 200:
                data = response.json()
                if data and data.get('data'):
                    items = data['data'].get('list', []) or []
                    print(f"[东方财富公告] 获取到 {len(items)} 条")
                    for item in items[:limit]:
                        news_list.append({
                            'title': item.get('title', '') or item.get('notice_title', ''),
                            'publish_time': item.get('publish_time', ''),
                            'source': '东方财富',
                            'type': '公告',
                            'art_id': item.get('notice_id', '')
                        })
        except Exception as e:
            print(f"[东方财富公告] 获取失败: {e}")
        
        # 2. 东方财富个股资讯（特定于该股票）
        if len(news_list) < 5:
            try:
                if code.startswith('6'):
                    secid = f"1.{code}"
                elif code.startswith('0') or code.startswith('3'):
                    secid = f"0.{code}"
                elif len(code) == 5:
                    secid = f"116.{code}"
                else:
                    secid = f"0.{code}"
                
                url = f'https://np-listapi.eastmoney.com/comm/web/getNaviNews?client=web&navi=stock&scodes={secid}&fields=ID,TITLE,NOTICETIME,TYPES&pageindex=0&pagesize={limit}'
                headers = {
                    'User-Agent': 'Mozilla/5.0',
                    'Referer': 'https://data.eastmoney.com/'
                }
                
                response = self.session.get(url, headers=headers, timeout=8)
                if response.status_code == 200:
                    data = response.json()
                    items = data.get('data', {}).get('newsList', []) or []
                    print(f"[东方财富资讯] 获取到 {len(items)} 条")
                    for item in items[:limit]:
                        news_list.append({
                            'title': item.get('TITLE', ''),
                            'publish_time': item.get('NOTICETIME', ''),
                            'source': '东方财富',
                            'type': '资讯',
                            'art_id': item.get('ID', '')
                        })
            except Exception as e:
                print(f"[东方财富资讯] 获取失败: {e}")
        
        # 3. 如果还是没有，使用东方财富搜索API获取个股新闻
        if len(news_list) < 3:
            try:
                keyword = stock_name or code
                url = f'https://search-api-web.eastmoney.com/search/jsonp?cb=jQuery&param={{%22uid%22%3A%22%22%2C%22keyword%22%3A%22{keyword}%22%2C%22type%22%3A[%22cmsArticleWebOld%22]%2C%22client%22%3A%22web%22%2C%22clientType%22%3A%22web%22%2C%22clientVersion%22%3A%22curr%22%2C%22param%22%3A{{%22cmsArticleWebOld%22:{{%22searchScope%22%3A%22default%22%2C%22sort%22%3A%22default%22%2C%22pageIndex%22%3A1%2C%22pageSize%22%3A{limit}}}}}}}'
                headers = {
                    'User-Agent': 'Mozilla/5.0',
                    'Referer': 'https://so.eastmoney.com/'
                }
                response = self.session.get(url, headers=headers, timeout=8)
                if response.status_code == 200:
                    text = response.text
                    # 解析JSONP
                    start = text.index('(') + 1
                    end = text.rindex(')')
                    json_str = text[start:end]
                    data = json.loads(json_str)
                    items = data.get('data', {}).get('cmsArticleWebOld', {}).get('list', [])
                    print(f"[东方财富搜索] 获取到 {len(items)} 条")
                    for item in items[:limit]:
                        title = item.get('title', '') or item.get('articleTitle', '')
                        if title:
                            news_list.append({
                                'title': title,
                                'publish_time': item.get('date', item.get('showDate', '')),
                                'source': '东方财富',
                                'type': '资讯',
                                'art_id': item.get('id', item.get('articleId', ''))
                            })
            except Exception as e:
                print(f"[东方财富搜索] 获取失败: {e}")
        
        # 去重
        seen_titles = set()
        unique_news = []
        for news in news_list:
            title = news.get('title', '')
            if title and title not in seen_titles:
                seen_titles.add(title)
                unique_news.append(news)
        
        print(f"[新闻] 最终返回 {len(unique_news)} 条")
        return unique_news[:limit]
    
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
                                print(f"[解析股票 {stock['code']}] 失败: {e}")
                                stocks.append({
                                    'code': stock['code'],
                                    'name': stock['name'],
                                    'price': 0,
                                    'change_pct': 0,
                                    'industry': industry,
                                })
            except Exception as e:
                print(f"[行业股票获取] 失败: {e}")
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
            print(f"[行业股票] 未找到行业 '{industry}'")
            return []
        
        return stocks[:limit]
    
    def get_industry_leaders(self, limit=10):
        """获取行业龙头股 - 公开接口"""
        industry = self._get_stock_industry()
        return self._get_industry_stocks(industry, limit)
    
    def get_kline_data(self, period='daily', limit=60):
        """
        获取K线数据
        
        Args:
            period: K线周期 ('daily', 'weekly', 'monthly', 'minute'等)
            limit: 返回数据条数
        
        Returns:
            K线数据列表
        """
        try:
            code = self.stock_code
            
            # 确定市场前缀和secid
            if code.startswith('6'):
                symbol = f"sh{code}"
                secid = f"1.{code}"
            elif code.startswith('0') or code.startswith('3'):
                symbol = f"sz{code}"
                secid = f"0.{code}"
            elif len(code) == 5:
                symbol = f"hk{code.zfill(5)}"
                secid = f"116.{code}"
            elif code.startswith(('8', '4', '9')):
                symbol = f"bj{code}"
                secid = f"0.{code}"  # 北交所使用0前缀
            else:
                symbol = f"sz{code}"
                secid = f"0.{code}"
            
            # 使用东方财富API获取K线数据
            # period: 101=日K, 102=周K, 103=月K
            period_map = {
                'daily': '101',
                'weekly': '102', 
                'monthly': '103',
            }
            ft = period_map.get(period, '101')
            
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
                        # 格式: 日期,开盘,收盘,最高,最低,成交量,成交额,振幅,涨跌幅,涨跌额,换手率
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
                    return result
        except Exception as e:
            print(f"[K线数据] 获取失败: {e}")
        
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
            print(f"[财务数据] 获取失败: {e}")
        
        return None
