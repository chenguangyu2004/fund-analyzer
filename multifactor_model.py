"""
AI多因子透视诊断模型引擎
基于《AI多因子透视诊断_模型规格书 v2.0》实现5模型并行打分+动态权重+综合输出
所有定量数据从API获取，定性分析交由DeepSeek AI完成
"""
import json
import time
import requests
import re
import numpy as np
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from fund_analyzer import FundAnalyzer
from stock_analyzer import StockAnalyzer
from deepseek_analyzer import DeepSeekAnalyzer
from logger import get_logger
import config

logger = get_logger("multifactor")

# ── 行业基准数据（从 data/industry_benchmarks.json 加载）──
_bd = config.load_data_json("industry_benchmarks.json", {})
INDUSTRY_BENCHMARKS = _bd.get("industry_benchmarks", {})
VALUATION_WEIGHTS = _bd.get("valuation_weights", {})
INDUSTRY_MACRO_MAP = _bd.get("industry_macro_map", {})
WEIGHT_MATRIX = _bd.get("weight_matrix", {})


class MultiFactorModel:
    """AI多因子透视诊断模型引擎"""

    def __init__(self, fund_code: str, api_key: str = None):
        self.fund_code = fund_code
        self.api_key = api_key
        self.fund_analyzer = FundAnalyzer(fund_code)
        self.deepseek = DeepSeekAnalyzer(api_key)
        self._session = requests.Session()
        self._session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://data.eastmoney.com/'
        })

    def run_diagnosis(self) -> Dict:
        """执行完整的多因子透视诊断"""
        logger.info(f"=== 开始AI多因子透视诊断: {self.fund_code} ===")
        t0 = time.time()

        # 1. 获取基金基本信息
        try:
            fund_info = self.fund_analyzer.get_fund_info()
            logger.info(f"基金信息获取结果: {type(fund_info)}, is_None={fund_info is None}")
            if fund_info:
                logger.info(f"基金名称: {fund_info.get('fund_name')}, 净值: {fund_info.get('net_value')}")
        except Exception as e:
            logger.warning(f"获取基金信息异常: {e}")
            logger.exception("基金信息异常详情")
            fund_info = None

        if not fund_info:
            return {'success': False, 'error': '无法获取基金信息'}

        # 2. 获取持仓
        holdings = self.fund_analyzer._get_fund_holdings(0)
        if not holdings:
            holdings = []

        # 只取前20大重仓股（按规格书要求）
        holdings = holdings[:20]
        # 计算归一化权重
        total_ratio = sum(float(h.get('ratio', '0').replace('%', '')) for h in holdings)
        for h in holdings:
            raw = float(h.get('ratio', '0').replace('%', ''))
            h['weight'] = raw / 100.0
            h['norm_weight'] = raw / total_ratio if total_ratio > 0 else 0
            h['ratio_pct'] = raw

        # 3. 获取市场环境参数
        market_env = self._get_market_environment()

        # 4. 判断市场环境类型 -> 动态权重
        env_type = self._identify_market_regime(market_env)
        weights = WEIGHT_MATRIX.get(env_type, WEIGHT_MATRIX['正常'])
        logger.info(f"市场环境: {env_type}, 权重: {weights}")

        # 5. 对每只重仓股获取详细数据
        stock_details = self._fetch_stock_details_batch(holdings)

        # 将holdings的权重信息合并到stock_details中
        for h in holdings:
            code = h.get('code', '')
            if code in stock_details:
                stock_details[code]['weight'] = h.get('norm_weight', 0)
                stock_details[code]['ratio_pct'] = h.get('ratio_pct', 0)

        # 6. M1: 个股质量加权评分
        m1_result = self._calc_M1(stock_details, holdings)

        # 7. M2: 估值性价比
        m2_result = self._calc_M2(stock_details, holdings)

        # 8. M3: 新闻舆情与动量
        m3_result = self._calc_M3(stock_details, holdings)

        # 9. M4: 行业前景与宏观匹配度
        m4_result = self._calc_M4(stock_details, holdings, market_env)

        # 10. M5: 基金经理行为一致性
        m5_result = self._calc_M5(fund_info, holdings)

        # 11. 综合评分
        model_scores = {
            'M1': m1_result['score'],
            'M2': m2_result['score'],
            'M3': m3_result['score'],
            'M4': m4_result['score'],
            'M5': m5_result['score'],
        }
        composite = sum(weights[f'M{i}'] * model_scores[f'M{i}'] for i in range(1, 6))

        # 12. 交给AI做定性分析和综合解读
        ai_interpretation = self._ai_interpret(
            fund_info, holdings, model_scores, weights, composite, env_type,
            m1_result, m2_result, m3_result, m4_result, m5_result,
            stock_details, market_env
        )

        # 13. 组装输出
        elapsed = time.time() - t0
        logger.info(f"=== 诊断完成, 耗时{elapsed:.1f}s, 综合评分={composite:.1f} ===")

        grade, action = self._score_to_grade(composite)

        result = {
            'success': True,
            'fund_code': self.fund_code,
            'fund_name': fund_info.get('fund_name', ''),
            'analysis_date': datetime.now().strftime('%Y-%m-%d'),
            'market_environment': {
                'regime': env_type,
                'csi300_pe_pct': market_env.get('csi300_pe_pct'),
                'csi300_pe': market_env.get('csi300_pe'),
                'bond_10y': market_env.get('bond_10y'),
                'epu_pct': market_env.get('epu_pct'),
                'usdcny': market_env.get('usdcny'),
            },
            'composite_score': round(composite, 1),
            'composite_grade': grade,
            'action_advice': action,
            'weights': {f'M{i}': round(weights[f'M{i}'] * 100, 1) for i in range(1, 6)},
            'model_scores': {
                'M1_stock_quality': self._format_model_output(m1_result, '个股质量加权评分'),
                'M2_valuation': self._format_model_output(m2_result, '估值性价比'),
                'M3_sentiment': self._format_model_output(m3_result, '新闻舆情与动量'),
                'M4_industry': self._format_model_output(m4_result, '行业前景与宏观匹配'),
                'M5_manager': self._format_model_output(m5_result, '基金经理行为一致性'),
            },
            'holdings_analysis': self._format_holdings_analysis(stock_details, m1_result, m2_result),
            'recommendation': ai_interpretation.get('recommendation', {}),
            'risk_points': ai_interpretation.get('risk_points', []),
            'ai_summary': ai_interpretation.get('summary', ''),
            'ai_detail': ai_interpretation.get('detail', ''),
            'elapsed_seconds': round(elapsed, 1),
        }
        return result

    # ═══════════════════════════════════════
    # 市场环境识别
    # ═══════════════════════════════════════
    def _get_market_environment(self) -> Dict:
        """获取市场环境参数（沪深300 PE分位数、国债收益率、EPU等，并发请求）"""
        env = {
            'csi300_pe_pct': None, 'csi300_pe': None,
            'bond_10y': None, 'epu_pct': None,
            'usdcny': None, 'volatility_pct': None,
            'ma_ratio': None, 'cpi_yoy': None,
        }

        def fetch_csi300_kline():
            """获取沪深300 K线数据（用于MA比值和波动率）"""
            try:
                url = "https://push2his.eastmoney.com/api/qt/stock/kline/get?secid=1.000300&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61&klt=101&fqt=1&end=20500101&lmt=1260"
                resp = requests.get(url, timeout=8)
                if resp.status_code == 200:
                    data = resp.json()
                    klines = data.get('data', {}).get('klines', [])
                    if klines:
                        closes = [float(l.split(',')[2]) for l in klines]
                        result = {}
                        # MA比值
                        ma60 = np.mean(closes[-60:]) if len(closes) >= 60 else np.mean(closes)
                        ma200 = np.mean(closes[-200:]) if len(closes) >= 200 else np.mean(closes)
                        result['ma_ratio'] = round(ma60 / ma200, 4) if ma200 > 0 else 1.0
                        # 近60日年化波动率
                        if len(closes) >= 60:
                            returns = np.diff(closes[-61:]) / closes[-61:-1]
                            result['volatility_pct'] = round(float(np.std(returns) * np.sqrt(252) * 100), 2)
                        return result
            except Exception as e:
                logger.warning(f"获取CSI300 K线失败: {e}")
            return {}

        def fetch_csi300_pe():
            """获取沪深300 PE"""
            try:
                url2 = "https://push2.eastmoney.com/api/qt/stock/get?secid=1.000300&fields=f9,f23"
                resp2 = requests.get(url2, timeout=5)
                if resp2.status_code == 200:
                    d2 = resp2.json().get('data', {})
                    if d2:
                        pe_raw = d2.get('f9')
                        if pe_raw and str(pe_raw) != '-':
                            pe = float(pe_raw)
                            pct = 0.55  # 默认
                            if pe <= 10:
                                pct = 0.05
                            elif pe <= 11:
                                pct = 0.15
                            elif pe <= 12:
                                pct = 0.35
                            elif pe <= 13:
                                pct = 0.55
                            elif pe <= 14:
                                pct = 0.70
                            elif pe <= 16:
                                pct = 0.82
                            else:
                                pct = 0.92
                            return {'csi300_pe': pe, 'csi300_pe_pct': pct}
            except Exception:
                pass
            return {}

        def fetch_bond_yield():
            """获取10Y国债收益率"""
            try:
                url3 = "https://hq.sinajs.cn/list=sh000012"
                resp3 = requests.get(url3, timeout=5, headers={
                    'User-Agent': 'Mozilla/5.0', 'Referer': 'https://finance.sina.com.cn'
                })
                if resp3.status_code == 200:
                    text = resp3.text
                    m = re.search(r'"(.+)"', text)
                    if m:
                        parts = m.group(1).split(',')
                        if len(parts) > 1:
                            v = float(parts[1])
                            return {'bond_10y': v / 100 if v > 1 else v}
            except Exception:
                pass
            return {}

        def fetch_usdcny():
            """获取美元人民币汇率"""
            try:
                url4 = "https://hq.sinajs.cn/list=fx_susdcny"
                resp4 = requests.get(url4, timeout=5, headers={
                    'User-Agent': 'Mozilla/5.0', 'Referer': 'https://finance.sina.com.cn'
                })
                if resp4.status_code == 200:
                    m = re.search(r'"(.+)"', resp4.text)
                    if m:
                        parts = m.group(1).split(',')
                        if len(parts) > 1:
                            return {'usdcny': float(parts[1])}
            except Exception:
                pass
            return {}

        # 并发获取4组数据
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {
                executor.submit(fetch_csi300_kline): 'csi300_kline',
                executor.submit(fetch_csi300_pe): 'csi300_pe',
                executor.submit(fetch_bond_yield): 'bond_10y',
                executor.submit(fetch_usdcny): 'usdcny',
            }
            for future in as_completed(futures, timeout=10):
                try:
                    env.update(future.result(timeout=10))
                except Exception:
                    pass

        # 默认值填充
        if env['csi300_pe_pct'] is None:
            env['csi300_pe_pct'] = 0.55
        if env['epu_pct'] is None:
            env['epu_pct'] = 0.50

        logger.info(f"市场环境: PE_pct={env['csi300_pe_pct']}, MA_ratio={env.get('ma_ratio')}, Vol={env.get('volatility_pct')}")
        return env

    def _identify_market_regime(self, env: Dict) -> str:
        """根据5个信号识别市场环境"""
        ma_ratio = env.get('ma_ratio', 1.0) or 1.0
        pe_pct = env.get('csi300_pe_pct', 0.5) or 0.5
        vol_pct = env.get('volatility_pct', 20) or 20
        epu_pct = env.get('epu_pct', 0.5) or 0.5

        # 优先级：高不确定性 > 牛市 > 熊市 > 震荡市 > 正常
        if epu_pct > 0.80 or vol_pct > 30:
            return '高不确定性'
        if ma_ratio > 1.03 and pe_pct > 0.70:
            return '牛市'
        if ma_ratio < 0.97 and pe_pct < 0.30:
            return '熊市'
        if 0.97 <= ma_ratio <= 1.03 and vol_pct < 20:
            return '震荡市'
        return '正常'

    # ═══════════════════════════════════════
    # 股票数据批量获取
    # ═══════════════════════════════════════
    def _fetch_stock_details_batch(self, holdings: List[Dict]) -> Dict[str, Dict]:
        """批量获取所有重仓股的详细数据（并发请求，大幅提速）"""
        details = {}
        total = len(holdings)
        completed = [0]  # 用列表包装以便在闭包中修改

        def fetch_one(h):
            code = h.get('code', '')
            name = h.get('name', '')
            idx = completed[0] + 1
            completed[0] = idx
            logger.info(f"  [{idx}/{total}] 获取 {name}({code}) 详情...")
            try:
                return code, self._fetch_single_stock_detail(code, name)
            except Exception as e:
                logger.warning(f"  获取{code}详情失败: {e}")
                return code, self._empty_stock_detail(code, name)

        # 并发获取，最多5个线程
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(fetch_one, h): h for h in holdings}
            for future in as_completed(futures):
                try:
                    code, detail = future.result(timeout=30)
                    details[code] = detail
                except Exception as e:
                    h = futures[future]
                    code = h.get('code', '')
                    logger.warning(f"  {code} 并发获取超时或失败: {e}")
                    details[code] = self._empty_stock_detail(code, h.get('name', ''))

        logger.info(f"  股票数据获取完成: {len(details)} 只, 耗时已优化")
        return details

    def _fetch_single_stock_detail(self, code: str, name: str) -> Dict:
        """获取单只股票的完整数据（用于5个模型）"""
        detail = {
            'code': code, 'name': name,
            'industry': '', 'industry_sw': '',
            # M1: 质量数据
            'roe': None, 'gross_margin': None, 'net_profit_growth': None,
            'revenue_growth': None, 'ocf_to_ni': None, 'fcf_to_rev': None,
            'debt_ratio': None, 'quick_ratio': None,
            # M2: 估值数据
            'pe_ttm': None, 'pe_percentile': None, 'pb_ttm': None, 'pb_percentile': None,
            'peg': None, 'dividend_yield': None,
            # M3: 舆情数据（由AI处理）
            'news_positive': 0, 'news_negative': 0, 'news_neutral': 0,
            'social_media_ratio': 0.3, 'institution_media_ratio': 0.2,
            'analyst_upgrade': 0, 'analyst_downgrade': 0, 'analyst_total': 0,
            'research_visit_pct': 0.5,
            'capital_flow_pct': 0.0,
            # 财务完整数据
            'financial_raw': {},
        }

        sa = StockAnalyzer(code)

        # 获取行业
        try:
            industry = sa._get_stock_industry()
            detail['industry'] = industry
            detail['industry_sw'] = industry
        except Exception:
            detail['industry'] = self._guess_industry_from_name(name)

        # 获取财务数据（详细版，用于M1）
        try:
            fin_data = self._fetch_detailed_financials(code)
            detail.update(fin_data)
        except Exception as e:
            logger.warning(f"  {code}财务数据获取失败: {e}")

        # 获取估值数据（M2）
        try:
            val_data = self._fetch_valuation_data(code, detail.get('industry', ''))
            detail.update(val_data)
        except Exception as e:
            logger.warning(f"  {code}估值数据获取失败: {e}")

        # 获取新闻（M3用）
        try:
            news_list = sa.get_stock_news(10)
            detail['_news'] = news_list
            # 简单统计正面/负面/中性（AI后续会重新分析）
            pos, neg, neu = 0, 0, 0
            for n in news_list:
                title = n.get('title', '')
                if any(kw in title for kw in ['增长', '上涨', '利好', '突破', '新高', '盈利', '中标', '签约']):
                    pos += 1
                elif any(kw in title for kw in ['下降', '下跌', '利空', '亏损', '风险', '违规', '处罚', '减持']):
                    neg += 1
                else:
                    neu += 1
            detail['news_positive'] = pos
            detail['news_negative'] = neg
            detail['news_neutral'] = neu
        except Exception:
            detail['_news'] = []

        # 获取资金流向（M3）
        try:
            flow_data = self._fetch_capital_flow(code)
            detail.update(flow_data)
        except Exception:
            pass

        return detail

    def _fetch_detailed_financials(self, code: str) -> Dict:
        """获取详细财务指标（M1用：ROE、毛利率、增速、现金流、负债率）
        优先使用东方财富API，失败时用StockAnalyzer.get_financial_report()
        """
        result = {
            'roe': None, 'gross_margin': None, 'net_profit_growth': None,
            'revenue_growth': None, 'ocf_to_ni': None, 'fcf_to_rev': None,
            'debt_ratio': None, 'quick_ratio': None, 'financial_raw': {},
        }

        # 方法1：东方财富主要财务指标API
        try:
            url = f'https://datacenter-web.eastmoney.com/api/data/v1/get?reportName=RPT_F10_FINANCE_MAININDEX&columns=REPORT_DATE,BASIC_EPS,TOTAL_OPERATE_INCOME,PARENT_NETPROFIT,ROE,DEBT_ASSET_RATIO,GROSS_PROFIT_RATIO,TOTAL_OPERATE_INCOME_YOY,PARENT_NETPROFIT_YOY&filter=(SECURITY_CODE%3D%22{code}%22)&pageNumber=1&pageSize=4&sortTypes=-1&sortColumns=REPORT_DATE'
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Referer': 'https://data.eastmoney.com/',
                'Accept': 'application/json',
            }
            resp = requests.get(url, headers=headers, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                if data and data.get('result') and data['result'].get('data'):
                    items = data['result']['data']
                    if items and len(items) > 0:
                        latest = items[0]
                        # 东方财富ROE/毛利率/负债率/增速为百分比格式(如15.8代表15.8%)，需统一除以100
                        roe_raw = self._safe_float(latest.get('ROE'))
                        result['roe'] = roe_raw / 100.0 if roe_raw is not None and abs(roe_raw) > 1 else roe_raw
                        debt_raw = self._safe_float(latest.get('DEBT_ASSET_RATIO'))
                        result['debt_ratio'] = debt_raw / 100.0 if debt_raw is not None and abs(debt_raw) > 1 else debt_raw
                        gm_raw = self._safe_float(latest.get('GROSS_PROFIT_RATIO'))
                        result['gross_margin'] = gm_raw / 100.0 if gm_raw is not None and abs(gm_raw) > 1 else gm_raw
                        rg_raw = self._safe_float(latest.get('TOTAL_OPERATE_INCOME_YOY'))
                        result['revenue_growth'] = rg_raw / 100.0 if rg_raw is not None and abs(rg_raw) > 1 else rg_raw
                        npg_raw = self._safe_float(latest.get('PARENT_NETPROFIT_YOY'))
                        result['net_profit_growth'] = npg_raw / 100.0 if npg_raw is not None and abs(npg_raw) > 1 else npg_raw
                        result['financial_raw'] = latest
                        logger.info(f"  {code} 财务API成功: ROE={result['roe']}, Debt={result['debt_ratio']}")
        except Exception as e:
            logger.warning(f"  {code} 东方财富财务API失败: {e}")

        # 方法2：备用 - 使用StockAnalyzer
        if result['roe'] is None:
            try:
                sa = StockAnalyzer(code)
                fin = sa.get_financial_report()
                if fin:
                    result['roe'] = self._safe_float(fin.get('roe'))
                    result['debt_ratio'] = self._safe_float(fin.get('debt_ratio'))
                    result['financial_raw'] = fin
                    logger.info(f"  {code} 备用API成功: ROE={result['roe']}")
            except Exception as e2:
                logger.warning(f"  {code} 备用API也失败: {e2}")

        # 现金流数据（尝试）
        try:
            url2 = f'https://datacenter-web.eastmoney.com/api/data/v1/get?reportName=RPT_DMSK_FN_CASHFLOW&columns=REPORT_DATE,NETCASH_OPERATE,PARENT_NETPROFIT,FREE_CASH_FLOW,TOTAL_OPERATE_INCOME&filter=(SECURITY_CODE%3D%22{code}%22)&pageNumber=1&pageSize=2&sortTypes=-1&sortColumns=REPORT_DATE'
            resp2 = requests.get(url2, headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://data.eastmoney.com/'}, timeout=5)
            if resp2.status_code == 200:
                d2 = resp2.json()
                items2 = d2.get('result', {}).get('data', []) if d2 and d2.get('result') else []
                if items2:
                    latest2 = items2[0]
                    ocf = self._safe_float(latest2.get('NETCASH_OPERATE'))
                    np_ = self._safe_float(latest2.get('PARENT_NETPROFIT'))
                    fcf = self._safe_float(latest2.get('FREE_CASH_FLOW'))
                    rev = self._safe_float(latest2.get('TOTAL_OPERATE_INCOME'))
                    if np_ and np_ != 0:
                        result['ocf_to_ni'] = ocf / abs(np_) if ocf else None
                    if rev and rev != 0:
                        result['fcf_to_rev'] = fcf / rev if fcf else None
        except Exception:
            pass

        # 速动比率
        try:
            url3 = f'https://datacenter-web.eastmoney.com/api/data/v1/get?reportName=RPT_DMSK_FN_BALANCE&columns=REPORT_DATE,QUICK_RATIO&filter=(SECURITY_CODE%3D%22{code}%22)&pageNumber=1&pageSize=1&sortTypes=-1&sortColumns=REPORT_DATE'
            resp3 = requests.get(url3, headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://data.eastmoney.com/'}, timeout=5)
            if resp3.status_code == 200:
                d3 = resp3.json()
                items3 = d3.get('result', {}).get('data', []) if d3 and d3.get('result') else []
                if items3:
                    result['quick_ratio'] = self._safe_float(items3[0].get('QUICK_RATIO'))
        except Exception:
            pass

        return result

    def _fetch_valuation_data(self, code: str, industry: str = '') -> Dict:
        """获取估值数据（M2用：PE、PB、分位数、PEG、股息率）"""
        result = {
            'pe_ttm': None, 'pe_percentile': None,
            'pb_ttm': None, 'pb_percentile': None,
            'peg': None, 'dividend_yield': None,
        }
        try:
            # 东方财富个股估值接口
            market = '0' if code.startswith(('6', '9')) else '1'
            url = f"https://push2.eastmoney.com/api/qt/stock/get?secid={market}.{code}&fields=f9,f23,f20,f115,f116,f167"
            headers = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://quote.eastmoney.com/'}
            resp = requests.get(url, headers=headers, timeout=5)
            if resp.status_code == 200:
                d = resp.json().get('data', {})
                if d:
                    pe_raw = d.get('f9')
                    if pe_raw and str(pe_raw) != '-':
                        result['pe_ttm'] = float(pe_raw)
                    pb_raw = d.get('f23')
                    if pb_raw and str(pb_raw) != '-':
                        result['pb_ttm'] = float(pb_raw)
                    # 股息率
                    dv2 = d.get('f167')
                    if dv2 and str(dv2) != '-' and str(dv2) != '0':
                        try:
                            val = float(dv2)
                            result['dividend_yield'] = val / 100.0 if abs(val) > 1 else val
                        except (ValueError, TypeError):
                            pass

        except Exception as e:
            logger.warning(f"  {code}估值获取失败: {e}")

        # PE/PB历史分位数估算（使用传入的行业信息，避免重复创建StockAnalyzer）
        try:
            if result['pe_ttm']:
                result['pe_percentile'] = self._estimate_percentile(industry, 'pe', result['pe_ttm'])
            if result['pb_ttm']:
                result['pb_percentile'] = self._estimate_percentile(industry, 'pb', result['pb_ttm'])
        except Exception:
            pass

        # PEG计算：由 _calc_M2 中根据 stock_details 的 net_profit_growth 计算
        # 此处不在 _fetch_valuation_data 中计算PEG，因为需要stock_details中已有的增速数据

        return result

    def _estimate_percentile(self, industry: str, metric: str, current_value: float) -> Optional[float]:
        """估算PE/PB历史分位数（简化版：基于行业PE中位数推算）"""
        bench = INDUSTRY_BENCHMARKS.get(industry, {})
        pe_median = bench.get('pe_median', 25)

        if metric == 'pe' and pe_median:
            # 简化：当前PE/行业PE中位数 -> 分位数映射
            ratio = current_value / pe_median if pe_median > 0 else 1
            if ratio <= 0.6:
                return 0.10
            elif ratio <= 0.8:
                return 0.25
            elif ratio <= 1.0:
                return 0.40
            elif ratio <= 1.2:
                return 0.55
            elif ratio <= 1.5:
                return 0.70
            elif ratio <= 2.0:
                return 0.85
            else:
                return 0.95
        elif metric == 'pb':
            # PB分位数也用类似方法
            if current_value <= 1:
                return 0.15
            elif current_value <= 2:
                return 0.35
            elif current_value <= 4:
                return 0.55
            elif current_value <= 7:
                return 0.75
            else:
                return 0.90
        return 0.50

    def _fetch_capital_flow(self, code: str) -> Dict:
        """获取资金流向数据（M3用）"""
        result = {'capital_flow_pct': 0.0}
        try:
            market = '0' if code.startswith(('6', '9')) else '1'
            url = f"https://push2.eastmoney.com/api/qt/stock/get?secid={market}.{code}&fields=f62,f184,f66,f69,f72,f75,f78,f81,f164,f174"
            headers = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://quote.eastmoney.com/'}
            resp = requests.get(url, headers=headers, timeout=5)
            if resp.status_code == 200:
                d = resp.json().get('data', {})
                if d:
                    main_inflow = d.get('f62')
                    if main_inflow is not None and str(main_inflow) != '-':
                        result['capital_flow_pct'] = float(main_inflow) / 1e8
        except Exception:
            pass
        return result

    # ═══════════════════════════════════════
    # M1: 个股质量加权评分
    # ═══════════════════════════════════════
    def _calc_M1(self, stock_details: Dict, holdings: List[Dict]) -> Dict:
        """M1: 个股质量加权评分（盈利30% + 成长25% + 现金流25% + 安全20%）"""
        stock_scores = []
        for h in holdings:
            code = h.get('code', '')
            d = stock_details.get(code, {})
            nw = h.get('norm_weight', 0)

            # 盈利能力 (30%): ROE 60% + 毛利率 40%
            roe = d.get('roe')
            roe_score = self._score_roe(roe)
            gm = d.get('gross_margin')
            industry = d.get('industry', '')
            gm_score = self._score_gross_margin(gm, industry)
            profit_score = 0.60 * roe_score + 0.40 * gm_score

            # 成长性 (25%): 净利润增速 55% + 营收增速 45%
            npg = d.get('net_profit_growth')
            npg_score = self._score_net_profit_growth(npg)
            rg = d.get('revenue_growth')
            rg_score = self._score_revenue_growth(rg)
            growth_score = 0.55 * npg_score + 0.45 * rg_score

            # 现金流质量 (25%): OCF/NI 60% + FCF/Rev 40%
            ocf_ni = d.get('ocf_to_ni')
            ocf_score = self._score_ocf_ni(ocf_ni)
            fcf_rev = d.get('fcf_to_rev')
            fcf_score = self._score_fcf_rev(fcf_rev)
            cashflow_score = 0.60 * ocf_score + 0.40 * fcf_score

            # 财务安全性 (20%): 资产负债率 60% + 速动比率 40%
            da = d.get('debt_ratio')
            da_score = self._score_debt_ratio(da, industry)
            qr = d.get('quick_ratio')
            qr_score = self._score_quick_ratio(qr)
            safety_score = 0.60 * da_score + 0.40 * qr_score

            # 个股汇总
            stock_total = 0.30 * profit_score + 0.25 * growth_score + 0.25 * cashflow_score + 0.20 * safety_score
            stock_scores.append({
                'code': code, 'name': d.get('name', h.get('name', '')),
                'weight': nw,
                'profit': round(profit_score, 1), 'growth': round(growth_score, 1),
                'cashflow': round(cashflow_score, 1), 'safety': round(safety_score, 1),
                'total': round(stock_total, 1),
            })

        # 按持仓权重加权
        m1 = sum(s['total'] * s['weight'] for s in stock_scores) if stock_scores else 50

        # 子维度平均分
        avg_profit = np.mean([s['profit'] for s in stock_scores]) if stock_scores else 50
        avg_growth = np.mean([s['growth'] for s in stock_scores]) if stock_scores else 50
        avg_cashflow = np.mean([s['cashflow'] for s in stock_scores]) if stock_scores else 50
        avg_safety = np.mean([s['safety'] for s in stock_scores]) if stock_scores else 50

        return {
            'score': round(m1, 1),
            'sub_scores': {
                'profitability': round(avg_profit, 1),
                'growth': round(avg_growth, 1),
                'cashflow': round(avg_cashflow, 1),
                'safety': round(avg_safety, 1),
            },
            'stock_scores': stock_scores,
            'top_positive': max(stock_scores, key=lambda x: x['total'])['name'] if stock_scores else '',
            'top_negative': min(stock_scores, key=lambda x: x['total'])['name'] if stock_scores else '',
        }

    # M1 打分函数
    @staticmethod
    def _score_roe(roe):
        if roe is None: return 50
        if roe >= 0.25: return 100
        if roe >= 0.20: return 90
        if roe >= 0.15: return 75
        if roe >= 0.10: return 55
        if roe >= 0.05: return 35
        if roe >= 0: return 20
        return 5

    @staticmethod
    def _score_gross_margin(gm, industry=''):
        if gm is None: return 50
        bench = INDUSTRY_BENCHMARKS.get(industry, {})
        gm_median = bench.get('gm_median', 0.30)
        gm_p75 = bench.get('gm_p75', 0.50)
        if gm_median is None:
            gm_median = 0.30
        if gm_p75 is None:
            gm_p75 = 0.50
        score = 50 + 50 * (gm - gm_median) / (gm_p75 - gm_median) if gm_p75 != gm_median else 50
        return min(100, max(0, score))

    @staticmethod
    def _score_net_profit_growth(npg):
        if npg is None: return 40
        if npg >= 0.50: return 100
        if npg >= 0.30: return 85
        if npg >= 0.15: return 70
        if npg >= 0.05: return 50
        if npg >= 0: return 30
        if npg >= -0.10: return 15
        return 5

    @staticmethod
    def _score_revenue_growth(rg):
        if rg is None: return 40
        if rg >= 0.30: return 100
        if rg >= 0.20: return 85
        if rg >= 0.10: return 65
        if rg >= 0.05: return 45
        if rg >= 0: return 25
        return 10

    @staticmethod
    def _score_ocf_ni(ocf_ni):
        if ocf_ni is None: return 45
        if ocf_ni >= 1.5: return 100
        if ocf_ni >= 0.5: return 60 + 40 * (ocf_ni - 0.5)
        if ocf_ni >= 0: return 60 * ocf_ni / 0.5
        return 10

    @staticmethod
    def _score_fcf_rev(fcf_rev):
        if fcf_rev is None: return 40
        if fcf_rev >= 0.15: return 100
        if fcf_rev >= 0.10: return 85
        if fcf_rev >= 0.05: return 65
        if fcf_rev >= 0: return 40
        return 15

    @staticmethod
    def _score_debt_ratio(da, industry=''):
        if da is None: return 50
        bench = INDUSTRY_BENCHMARKS.get(industry, {})
        da_p90 = bench.get('da_p90', 0.65)
        score = 100 - 80 * da / da_p90 if da_p90 > 0 else 50
        return min(100, max(0, score))

    @staticmethod
    def _score_quick_ratio(qr):
        if qr is None: return 50
        if qr >= 1.5: return 100
        if qr >= 1.0: return 80
        if qr >= 0.7: return 55
        if qr >= 0.4: return 30
        return 10

    # ═══════════════════════════════════════
    # M2: 估值性价比
    # ═══════════════════════════════════════
    def _calc_M2(self, stock_details: Dict, holdings: List[Dict]) -> Dict:
        """M2: 估值性价比（PE分位35% + PB分位25% + PEG 25% + 股息率15%）"""
        stock_scores = []
        for h in holdings:
            code = h.get('code', '')
            d = stock_details.get(code, {})
            nw = h.get('norm_weight', 0)
            industry = d.get('industry', '')

            # 行业修正权重
            vw = VALUATION_WEIGHTS.get(industry, VALUATION_WEIGHTS['default'])

            # PE分位数得分
            pe_pct = d.get('pe_percentile')
            pe_score = self._score_pe_percentile(pe_pct)

            # PB分位数得分
            pb_pct = d.get('pb_percentile')
            pb_score = self._score_pb_percentile(pb_pct)

            # PEG得分 — 在此处计算PEG（PE_TTM / 净利润增速*100）
            npg = d.get('net_profit_growth')
            pe_ttm = d.get('pe_ttm')
            peg = None
            if pe_ttm and npg is not None and npg > 0:
                peg = pe_ttm / (npg * 100) if npg > 0 else None
            peg_score = self._score_peg(peg, npg)

            # 股息率得分
            dv = d.get('dividend_yield')
            dv_score = self._score_dividend_yield(dv)

            # 加权
            val_total = (vw['pe'] * pe_score + vw['pb'] * pb_score +
                         vw['peg'] * peg_score + vw['dividend'] * dv_score)

            stock_scores.append({
                'code': code, 'name': d.get('name', h.get('name', '')),
                'weight': nw,
                'pe_pct': pe_pct, 'pe_score': round(pe_score, 1),
                'pb_pct': pb_pct, 'pb_score': round(pb_score, 1),
                'peg': peg, 'peg_score': round(peg_score, 1),
                'dividend_yield': dv, 'dv_score': round(dv_score, 1),
                'total': round(val_total, 1),
            })

        m2 = sum(s['total'] * s['weight'] for s in stock_scores) if stock_scores else 50

        # 子维度平均分
        avg_pe = np.mean([s['pe_score'] for s in stock_scores]) if stock_scores else 50
        avg_pb = np.mean([s['pb_score'] for s in stock_scores]) if stock_scores else 50
        avg_peg = np.mean([s['peg_score'] for s in stock_scores]) if stock_scores else 50
        avg_dv = np.mean([s['dv_score'] for s in stock_scores]) if stock_scores else 50

        # 找最贵/最便宜
        sorted_by_val = sorted(stock_scores, key=lambda x: x['total'])
        top_cheap = [s['name'] for s in sorted_by_val[:3]]
        top_expensive = [s['name'] for s in sorted_by_val[-3:]]

        return {
            'score': round(m2, 1),
            'sub_scores': {
                'pe_percentile': round(avg_pe, 1),
                'pb_percentile': round(avg_pb, 1),
                'peg': round(avg_peg, 1),
                'dividend': round(avg_dv, 1),
            },
            'stock_scores': stock_scores,
            'top_cheap': top_cheap,
            'top_expensive': top_expensive,
        }

    @staticmethod
    def _score_pe_percentile(pct):
        if pct is None: return 50
        if pct <= 0.15: return 100
        if pct <= 0.30: return 85
        if pct <= 0.50: return 65
        if pct <= 0.70: return 45
        if pct <= 0.85: return 25
        return 10

    @staticmethod
    def _score_pb_percentile(pct):
        if pct is None: return 50
        return MultiFactorModel._score_pe_percentile(pct)  # 同标准

    @staticmethod
    def _score_peg(peg, npg=None):
        if npg is not None and npg < 0: return 10
        if peg is None: return 45
        if peg < 0.5: return 100
        if peg < 0.8: return 90
        if peg < 1.0: return 80
        if peg < 1.5: return 60
        if peg < 2.5: return 35
        return 15

    @staticmethod
    def _score_dividend_yield(dy):
        if dy is None: return 30
        if dy >= 0.05: return 100
        if dy >= 0.035: return 85
        if dy >= 0.025: return 70
        if dy >= 0.015: return 50
        if dy >= 0.005: return 30
        if dy > 0: return 10
        return 5

    # ═══════════════════════════════════════
    # M3: 新闻舆情与动量
    # ═══════════════════════════════════════
    def _calc_M3(self, stock_details: Dict, holdings: List[Dict]) -> Dict:
        """M3: 新闻舆情与动量（新闻情感35% + 分析师评级25% + 调研热度20% + 资金流向20%）"""
        stock_scores = []
        for h in holdings:
            code = h.get('code', '')
            d = stock_details.get(code, {})
            nw = h.get('norm_weight', 0)

            # 新闻情感得分 (35%)
            pos = d.get('news_positive', 0)
            neg = d.get('news_negative', 0)
            neu = d.get('news_neutral', 0)
            total_news = pos + neg + neu
            if total_news > 0:
                sentiment = (pos - neg) / total_news
            else:
                sentiment = 0
            news_score = self._score_sentiment(sentiment)
            # 来源降级
            sm_ratio = d.get('social_media_ratio', 0.3)
            if sm_ratio > 0.6:
                news_score = max(news_score - 15, 0)
            im_ratio = d.get('institution_media_ratio', 0.2)
            if im_ratio > 0.5:
                news_score = min(news_score + 10, 100)

            # 分析师评级变化 (25%) — 简化用估值
            rating_score = 55  # 默认"无变化"

            # 调研热度 (20%) — 简化
            visit_pct = d.get('research_visit_pct', 0.5)
            visit_score = self._score_visit(visit_pct)

            # 资金流向 (20%)
            flow_pct = d.get('capital_flow_pct', 0)
            flow_score = self._score_capital_flow(flow_pct)

            # 加权
            sentiment_total = 0.35 * news_score + 0.25 * rating_score + 0.20 * visit_score + 0.20 * flow_score

            stock_scores.append({
                'code': code, 'name': d.get('name', h.get('name', '')),
                'weight': nw,
                'sentiment': round(sentiment, 2), 'news_score': round(news_score, 1),
                'rating_score': round(rating_score, 1),
                'visit_score': round(visit_score, 1),
                'flow_score': round(flow_score, 1),
                'total': round(sentiment_total, 1),
            })

        m3 = sum(s['total'] * s['weight'] for s in stock_scores) if stock_scores else 50

        # 找舆情最积极/最消极
        sorted_by_sent = sorted(stock_scores, key=lambda x: x['total'], reverse=True)
        top_positive = [s['name'] for s in sorted_by_sent[:3]]
        alert_list = [s['name'] for s in sorted_by_sent[-3:]]

        return {
            'score': round(m3, 1),
            'sub_scores': {
                'news_sentiment': round(np.mean([s['news_score'] for s in stock_scores]), 1) if stock_scores else 50,
                'analyst_rating': round(np.mean([s['rating_score'] for s in stock_scores]), 1) if stock_scores else 50,
                'research_visit': round(np.mean([s['visit_score'] for s in stock_scores]), 1) if stock_scores else 50,
                'capital_flow': round(np.mean([s['flow_score'] for s in stock_scores]), 1) if stock_scores else 50,
            },
            'stock_scores': stock_scores,
            'top_positive': top_positive,
            'alert_list': alert_list,
        }

    @staticmethod
    def _score_sentiment(sentiment):
        if sentiment >= 0.5: return 100
        if sentiment >= 0.3: return 85
        if sentiment >= 0.1: return 70
        if sentiment >= 0: return 55
        if sentiment >= -0.1: return 40
        if sentiment >= -0.3: return 25
        return 10

    @staticmethod
    def _score_visit(pct):
        if pct >= 0.90: return 100
        if pct >= 0.75: return 85
        if pct >= 0.50: return 65
        if pct >= 0.25: return 45
        if pct > 0: return 25
        return 10

    @staticmethod
    def _score_capital_flow(flow_pct):
        if flow_pct >= 2.0: return 100
        if flow_pct >= 1.0: return 85
        if flow_pct >= 0.3: return 65
        if flow_pct >= -0.3: return 50
        if flow_pct >= -1.0: return 35
        return 15

    # ═══════════════════════════════════════
    # M4: 行业前景与宏观匹配度
    # ═══════════════════════════════════════
    def _calc_M4(self, stock_details: Dict, holdings: List[Dict], market_env: Dict) -> Dict:
        """M4: 行业前景与宏观匹配度（行业景气45% + 政策支持30% + 宏观匹配25%）"""
        # 按行业聚合权重
        industry_weights = {}
        for h in holdings:
            code = h.get('code', '')
            d = stock_details.get(code, {})
            ind = d.get('industry', '其他')
            nw = h.get('norm_weight', 0)
            industry_weights[ind] = industry_weights.get(ind, 0) + nw

        industry_scores = {}
        for ind, weight in industry_weights.items():
            # 行业景气度（45%）：简化用行业平均ROE和增速
            bench = INDUSTRY_BENCHMARKS.get(ind, {})
            ind_roe = bench.get('roe_median', 0.05)
            # PMI简化
            pmi_score = 65  # 默认中等
            # ROE趋势
            roe_trend = 0  # 默认持平
            quant_score = 55 + (ind_roe - 0.05) * 200 + roe_trend * 10

            # 产业周期
            cycle_score = 55  # 默认成熟期
            growth_industries = ['电子', '计算机', '医药生物', '电力设备', '通信', '传媒']
            if ind in growth_industries:
                cycle_score = 70
            decline_industries = ['房地产', '建筑装饰', '煤炭']
            if ind in decline_industries:
                cycle_score = 40

            prosperity_score = 0.60 * quant_score + 0.40 * cycle_score

            # 政策支持度（30%）
            policy_score = 50  # 默认中性
            support_industries = ['电力设备', '计算机', '医药生物', '通信', '电子', '国防军工']
            restrict_industries = ['房地产', '教育']
            if ind in support_industries:
                policy_score = 80
            elif ind in restrict_industries:
                policy_score = 25

            # 宏观环境适配度（25%）
            macro_bonus = 0
            bond_10y = market_env.get('bond_10y', 0.03) or 0.03
            usdcny = market_env.get('usdcny', 7.25) or 7.25
            # 利率方向判断
            if bond_10y > 0.035:  # 利率偏高
                if ind in INDUSTRY_MACRO_MAP.get('利率上行受益', []):
                    macro_bonus += 20
                if ind in INDUSTRY_MACRO_MAP.get('利率上行受损', []):
                    macro_bonus -= 20
            elif bond_10y < 0.025:  # 利率偏低
                if ind in ['电子', '计算机', '电力设备']:
                    macro_bonus += 20
                if ind in ['银行']:
                    macro_bonus -= 20
            # 汇率
            if usdcny > 7.3:
                if ind in INDUSTRY_MACRO_MAP.get('人民币贬值受益', []):
                    macro_bonus += 10
            elif usdcny < 7.0:
                if ind in INDUSTRY_MACRO_MAP.get('人民币贬值受损', []):
                    macro_bonus -= 10

            macro_score = min(100, max(0, 50 + macro_bonus))

            # 行业总分
            ind_total = 0.45 * prosperity_score + 0.30 * policy_score + 0.25 * macro_score
            industry_scores[ind] = {
                'weight': weight,
                'prosperity': round(prosperity_score, 1),
                'policy': round(policy_score, 1),
                'macro': round(macro_score, 1),
                'total': round(ind_total, 1),
            }

        # 加权汇总
        m4 = sum(s['total'] * s['weight'] for s in industry_scores.values()) if industry_scores else 50

        # 排序行业
        sorted_ind = sorted(industry_scores.items(), key=lambda x: x[1]['total'], reverse=True)
        top_industries = [f"{ind}({s['total']}分)" for ind, s in sorted_ind[:3]]

        return {
            'score': round(m4, 1),
            'sub_scores': {
                'prosperity': round(np.mean([s['prosperity'] for s in industry_scores.values()]), 1),
                'policy': round(np.mean([s['policy'] for s in industry_scores.values()]), 1),
                'macro': round(np.mean([s['macro'] for s in industry_scores.values()]), 1),
            },
            'industry_scores': industry_scores,
            'top_industries': top_industries,
        }

    # ═══════════════════════════════════════
    # M5: 基金经理行为一致性
    # ═══════════════════════════════════════
    def _calc_M5(self, fund_info: Dict, holdings: List[Dict]) -> Dict:
        """M5: 基金经理行为一致性（风格稳定性30% + 调仓质量30% + 言行一致性25% + 业绩可持续性15%）"""
        # 风格稳定性 (30%)
        # 简化：基于基金类型和持仓集中度
        top10_ratio = sum(float(h.get('ratio', '0').replace('%', '')) for h in holdings[:10])
        if top10_ratio > 60:
            style_label = '集中'
        elif top10_ratio < 40:
            style_label = '分散'
        else:
            style_label = '适中'
        # 默认风格变化次数为1（保守估计）
        style_changes = 1
        style_stability = 100 - 25 * style_changes
        style_stability = max(style_stability, 25)

        # 调仓质量 (30%)
        # 简化：用基金换手率（从策略信息推断）
        turnover = 0.85  # 默认85%（大多数基金在100%以下）
        try:
            strategy = self.fund_analyzer.get_fund_strategy()
            style_text = strategy.get('investment_style', '')
            if '指数' in style_text:
                turnover = 0.30
            elif '价值' in style_text:
                turnover = 0.60
            elif '成长' in style_text:
                turnover = 1.20
        except Exception:
            pass

        if turnover < 1.0:
            turnover_score = 100
        elif turnover < 2.0:
            turnover_score = 80
        elif turnover < 4.0:
            turnover_score = 55
        elif turnover < 6.0:
            turnover_score = 30
        else:
            turnover_score = 10

        # 调仓效果（简化：假设60%正确率）
        timing_accuracy = 0.60
        timing_score = 50 + 50 * (2 * timing_accuracy - 1)
        timing_total = 0.50 * turnover_score + 0.50 * timing_score

        # 言行一致性 (25%)
        # 简化：检查基金经理变更+策略
        manager_history = fund_info.get('manager_history', {})
        recent_changed = manager_history.get('recent_changed', False) if isinstance(manager_history, dict) else False
        consistency_misses = 1  # 默认1次不匹配
        if recent_changed:
            consistency_misses += 1
        consistency_score = 100 - 20 * consistency_misses

        # 业绩可持续性 (15%)
        # 简化：用风险指标
        try:
            risk = self.fund_analyzer.get_risk_metrics(365)
            sharpe = risk.get('sharpe_ratio', 0) or 0
            perf_score = min(100, max(0, 50 + sharpe * 30))
        except Exception:
            perf_score = 50

        # M5汇总
        m5 = 0.30 * style_stability + 0.30 * timing_total + 0.25 * consistency_score + 0.15 * perf_score

        return {
            'score': round(m5, 1),
            'sub_scores': {
                'style_stability': round(style_stability, 1),
                'timing_quality': round(timing_total, 1),
                'consistency': round(consistency_score, 1),
                'performance': round(perf_score, 1),
            },
            'style_label': style_label,
            'turnover': turnover,
            'recent_manager_change': recent_changed,
        }

    # ═══════════════════════════════════════
    # AI 定性分析与综合解读
    # ═══════════════════════════════════════
    def _ai_interpret(self, fund_info, holdings, model_scores, weights, composite, env_type,
                      m1, m2, m3, m4, m5, stock_details, market_env) -> Dict:
        """调用DeepSeek AI对5个模型结果做定性分析和综合解读（发送完整数据）"""

        def fmt_val(val, suffix=''):
            """内联格式化数值"""
            if val is None: return 'N/A'
            if isinstance(val, float):
                if abs(val) > 100: return f'{val:.1f}{suffix}'
                elif abs(val) > 1: return f'{val:.2f}{suffix}'
                else: return f'{val*100:.1f}%'
            return f'{val}{suffix}'

        # ── 构建每只重仓股的完整指标 ──
        stock_rows = []
        for i, h in enumerate(holdings[:10]):
            code = h.get('code', '')
            d = stock_details.get(code, {})
            industry = d.get('industry', '未知')
            stock_rows.append(
                f"{i+1}. {h.get('name','')}({code}) | 占比{h.get('ratio','0')}% | {industry}\n"
                f"   M1: ROE={fmt_val(d.get('roe'))} 毛利率={fmt_val(d.get('gross_margin'))} "
                f"净利增速={fmt_val(d.get('net_profit_growth'))} 营收增速={fmt_val(d.get('revenue_growth'))}"
                f" OCF/NI={fmt_val(d.get('ocf_to_ni'))} 负债率={fmt_val(d.get('debt_ratio'))}\n"
                f"   M2: PE={fmt_val(d.get('pe_ttm'))} PE分位={fmt_val(d.get('pe_percentile'))} "
                f"PB={fmt_val(d.get('pb_ttm'))} 股息率={fmt_val(d.get('dividend_yield'))}\n"
                f"   M3: 正面{d.get('news_positive',0)}/负面{d.get('news_negative',0)}/中性{d.get('news_neutral',0)} "
                f"资金流={fmt_val(d.get('capital_flow_pct'),'')}"
            )

        # ── 行业分布与M4数据 ──
        industry_map = {}
        for h in holdings[:10]:
            code = h.get('code', '')
            ind = stock_details.get(code, {}).get('industry', '未知')
            ratio = float(h.get('ratio', '0').replace('%', ''))
            industry_map[ind] = industry_map.get(ind, 0) + ratio
        industry_rows = '\n'.join([f"- {k}: {v:.1f}%" for k, v in sorted(industry_map.items(), key=lambda x: -x[1])])

        # ── 新闻摘要 ──
        all_news = []
        for h in holdings[:5]:
            code = h.get('code', '')
            news_list = stock_details.get(code, {}).get('_news', [])
            for n in news_list[:2]:
                all_news.append(f"[{h.get('name','')}] {n.get('title','')}")

        prompt = f"""## 分析任务：AI多因子透视诊断

你是一个遵循「AI多因子透视诊断模型v2.0」框架的专业分析引擎。框架包含5个定量子模型，按动态权重加权得出综合评分。

### 评分方法论（你的分析必须引用这些模型）
- **M1个股质量(权重{weights['M1']*100:.0f}%)**：回答「基金买的是不是好公司」。从盈利能力(ROE/毛利率)、成长性(净利增速/营收增速)、现金流质量(OCF/NI、FCF)、财务安全(负债率/速动比率)四个子维度评分
- **M2估值性价比(权重{weights['M2']*100:.0f}%)**：回答「好公司现在贵不贵」。从PE分位数、PB分位数、PEG、股息率评分。PE/PB分位0-15%为极度低估(100分)，85-100%为极度高估(10分)
- **M3舆情动量(权重{weights['M3']*100:.0f}%)**：回答「市场现在认可这些公司吗」。从新闻情感(NLP)、分析师评级变化、机构调研热度、北向/主力资金流向评分
- **M4行业景气(权重{weights['M4']*100:.0f}%)**：回答「赛道是顺风还是逆风」。从行业景气度(PMI/营收增速/ROE趋势)、政策支持度、宏观环境适配度评分
- **M5经理行为(权重{weights['M5']*100:.0f}%)**：回答「管钱的人靠谱吗」。从风格稳定性(4季标签变化)、调仓质量(换手率+择时)、言行一致性(季报vs操作)、业绩可持续性评分

### 评分等级标准
| 评分 | 等级 | 操作建议 |
| ≥80 | 优秀⭐⭐⭐ | 适合作为核心配置 |
| 70-79 | 良好⭐⭐ | 可持有，关注风险点 |
| 55-69 | 一般⭐ | 观望，等待更好时机 |
| 40-54 | 较低 | 建议减仓或寻找替代品 |
| <40 | 差 | 强烈建议回避 |

### 基金基本信息
- 名称: {fund_info.get('fund_name','')} | 代码: {self.fund_code}
- 经理: {fund_info.get('manager','未知')} | 类型: {fund_info.get('fund_type','未知')} | 规模: {fund_info.get('scale','未知')}
- 当前市场环境: {env_type}

### 市场环境参数
- CSI300 PE={market_env.get('csi300_pe','N/A')} PE分位数={market_env.get('csi300_pe_pct','N/A')}
- 10年国债={market_env.get('bond_10y','N/A')} | USDCNY={market_env.get('usdcny','N/A')}
- 60MA/200MA={market_env.get('ma_ratio','N/A')} | 60日波动率={market_env.get('volatility_pct','N/A')}%

### 五模型定量评分结果
| 模型 | 分数 | 权重 | 子维度分 |
|------|------|------|----------|
| M1个股质量 | {model_scores['M1']} | {weights['M1']*100:.0f}% | 盈利={m1['sub_scores']['profitability']} 成长={m1['sub_scores']['growth']} 现金流={m1['sub_scores']['cashflow']} 安全={m1['sub_scores']['safety']} |
| M2估值性价比 | {model_scores['M2']} | {weights['M2']*100:.0f}% | PE分位={m2['sub_scores']['pe_percentile']} PB分位={m2['sub_scores']['pb_percentile']} PEG={m2['sub_scores']['peg']} 股息={m2['sub_scores']['dividend']} |
| M3舆情动量 | {model_scores['M3']} | {weights['M3']*100:.0f}% | 新闻={m3['sub_scores']['news_sentiment']} 评级={m3['sub_scores']['analyst_rating']} 调研={m3['sub_scores']['research_visit']} 资金={m3['sub_scores']['capital_flow']} |
| M4行业景气 | {model_scores['M4']} | {weights['M4']*100:.0f}% | 景气={m4['sub_scores']['prosperity']} 政策={m4['sub_scores']['policy']} 宏观={m4['sub_scores']['macro']} |
| M5经理行为 | {model_scores['M5']} | {weights['M5']*100:.0f}% | 风格={m5['sub_scores']['style_stability']} 调仓={m5['sub_scores']['timing_quality']} 言行={m5['sub_scores']['consistency']} 业绩={m5['sub_scores']['performance']} |
| **综合评分** | **{composite:.1f}** | 100% | S = Σ w_i × M_i |

### 前10大重仓股完整指标
{chr(10).join(stock_rows)}

### 持仓行业分布
{industry_rows}

### 经理行为数据
风格标签={m5.get('style_label','未知')} | 年化换手率={m5.get('turnover','N/A')} | 近期变更={'是' if m5.get('recent_manager_change') else '否'}

### 近期新闻
{chr(10).join(all_news[:10]) if all_news else '暂无'}

### 输出要求（严格遵循以下结构，直接输出JSON，不要额外文字）
{{
    "summary": "150-200字综合诊断结论。开头说明综合评分和等级，然后概述五模型核心发现：M1持仓公司质量如何、M2当前估值水位、M3市场认可度、M4行业前景、M5经理水平。",
    "detail": "按以下结构输出500-800字详细分析:\\n\\n【M1 个股质量】结合ROE、毛利率、净利增速等具体数值，点评持仓公司整体质量水平和亮点/隐忧。\\n\\n【M2 估值性价比】结合PE分位数、PEG等数值，判断当前估值水平，指出最贵和最便宜的持仓。\\n\\n【M3 舆情动量】结合新闻情感分布、资金流向，判断市场当前对持仓的态度。\\n\\n【M4 行业景气】结合行业分布和市场环境，判断持仓赛道在当前宏观下的适配度。\\n\\n【M5 经理行为】结合风格稳定性、换手率、言行一致性等，评估基金经理的可靠性。",
    "recommendation": {{
        "action": "持有/加仓/减仓/卖出/观望",
        "key_reason": "一句话核心理由，基于综合评分和五模型分析",
        "watch_points": ["具体关注点1", "关注点2", "关注点3"]
    }},
    "risk_points": ["具体风险点1(含数据)", "风险点2", "风险点3", "风险点4"]
}}"""

        try:
            result = self.deepseek._call_deepseek_api(prompt)
            if not isinstance(result, dict):
                raise ValueError("AI返回非字典格式")
            result.setdefault('summary', '')
            result.setdefault('detail', '')
            result.setdefault('recommendation', {})
            result.setdefault('risk_points', [])
            if isinstance(result['recommendation'], dict):
                result['recommendation'].setdefault('action', '--')
                result['recommendation'].setdefault('key_reason', '')
                result['recommendation'].setdefault('watch_points', [])
            return result
        except Exception as e:
            logger.warning(f"AI解读失败，使用降级方案: {e}")
            grade, action = self._score_to_grade(composite)
            return {
                'summary': f"综合评分{composite:.1f}分，{grade}。持仓整体{self._qualitative_m1(m1['score'])}，估值{self._qualitative_m2(m2['score'])}。",
                'detail': f"M1个股质量{m1['score']}分，M2估值{m2['score']}分，M3舆情{m3['score']}分，M4行业{m4['score']}分，M5经理{m5['score']}分。{self._generate_fallback_detail(model_scores, m1, m2, m3, m4, m5)}",
                'recommendation': {
                    'action': action,
                    'key_reason': f"综合评分{composite:.1f}分",
                    'watch_points': ['关注重仓股下季度财报', '关注市场环境变化', '关注基金经理调仓动向']
                },
                'risk_points': [
                    '若PE分位数继续上行至85%以上，建议减仓',
                    '关注前3大重仓股财报增速是否放缓',
                    '若市场环境切换为高不确定性，需重新评估',
                    '基金经理若出现风格漂移需警惕'
                ]
            }








    # ═══════════════════════════════════════
    # 辅助函数
    # ═══════════════════════════════════════

    # ═══════════════════════════════════════
    # 辅助函数
    # ═══════════════════════════════════════
    @staticmethod
    def _safe_float(val) -> Optional[float]:
        if val is None or val == '' or val == '-':
            return None
        try:
            return float(val)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _score_to_grade(score: float) -> Tuple[str, str]:
        if score >= 80:
            return '优秀', '适合作为核心配置'
        elif score >= 70:
            return '良好', '可持有，关注风险点'
        elif score >= 55:
            return '一般', '观望，等待更好时机'
        elif score >= 40:
            return '较低', '建议减仓或寻找替代品'
        else:
            return '差', '强烈建议回避'

    @staticmethod
    def _qualitative_m1(score):
        if score >= 75: return '质量优秀'
        if score >= 55: return '质量尚可'
        return '质量堪忧'

    @staticmethod
    def _qualitative_m2(score):
        if score >= 65: return '估值合理偏低'
        if score >= 45: return '估值适中'
        return '估值偏高'

    @staticmethod
    def _generate_fallback_detail(scores, m1, m2, m3, m4, m5):
        lines = []
        if scores['M1'] >= 70:
            lines.append(f"个股质量方面表现较好（{m1['score']}分），重仓股以行业龙头为主。")
        else:
            lines.append(f"个股质量方面有待提升（{m1['score']}分），部分重仓股基本面偏弱。")
        if scores['M2'] < 50:
            lines.append(f"估值性价比偏低（{m2['score']}分），持仓整体估值偏高，需关注回调风险。")
        else:
            lines.append(f"估值性价比尚可（{m2['score']}分），当前估值处于合理区间。")
        if scores['M3'] >= 60:
            lines.append(f"市场舆情偏正面（{m3['score']}分），机构关注度和资金流向积极。")
        if scores['M4'] >= 60:
            lines.append(f"行业景气度较好（{m4['score']}分），持仓行业与当前宏观环境匹配度尚可。")
        return ' '.join(lines)

    def _format_model_output(self, result: Dict, name: str) -> Dict:
        """格式化单个模型输出"""
        score = result.get('score', 0)
        grade, _ = self._score_to_grade(score)
        return {
            'score': score,
            'grade': grade,
            'sub_scores': result.get('sub_scores', {}),
            'top_finding': result.get('top_positive', result.get('top_industries', result.get('top_cheap', ''))),
            'risk_flag': result.get('top_negative', result.get('top_expensive', result.get('alert_list', ''))),
        }

    def _format_holdings_analysis(self, stock_details: Dict, m1_result: Dict, m2_result: Dict) -> List[Dict]:
        """格式化持仓诊断"""
        analysis = []
        m1_stocks = {s['code']: s for s in m1_result.get('stock_scores', [])}
        m2_stocks = {s['code']: s for s in m2_result.get('stock_scores', [])}

        for code, detail in stock_details.items():
            m1_s = m1_stocks.get(code, {})
            m2_s = m2_stocks.get(code, {})
            quality = m1_s.get('total', 0)
            valuation = m2_s.get('total', 0)

            # 诊断评语
            if quality >= 80 and valuation >= 65:
                verdict = '质优价廉'
                tag = 'green'
            elif quality >= 80 and valuation < 50:
                verdict = '质量优秀但估值偏贵'
                tag = 'yellow'
            elif quality < 55 and valuation >= 65:
                verdict = '估值便宜但质量存疑'
                tag = 'orange'
            elif quality < 55 and valuation < 50:
                verdict = '质量与估值均不理想'
                tag = 'red'
            else:
                verdict = '质量中等，估值中性'
                tag = 'yellow'

            # 关键指标
            key_metrics = []
            if detail.get('roe') is not None:
                key_metrics.append(f"ROE {detail['roe']*100:.1f}%")
            if detail.get('pe_percentile') is not None:
                key_metrics.append(f"PE分位 {detail['pe_percentile']*100:.0f}%")

            analysis.append({
                'code': code,
                'name': detail.get('name', ''),
                'weight': detail.get('ratio_pct', 0) / 100.0,  # 占净值比例
                'quality': round(quality, 1),
                'valuation': round(valuation, 1),
                'verdict': verdict,
                'tag': tag,
                'key_metrics': ', '.join(key_metrics) if key_metrics else '数据不充分',
            })

        # 按权重排序
        analysis.sort(key=lambda x: x['weight'], reverse=True)
        return analysis

    def _guess_industry_from_name(self, name: str) -> str:
        """从股票名称猜测行业"""
        kw_map = {
            '银行': ['银行'], '食品饮料': ['茅台', '五粮液', '酒', '奶'],
            '医药生物': ['医药', '药业', '医疗', '生物'], '电子': ['电子', '芯片', '半导体'],
            '电力设备': ['电气', '电源', '锂电', '光伏'], '计算机': ['软件', '信息', '科技', '办公'],
            '汽车': ['汽车', '汽'], '房地产': ['地产', '房产'],
            '保险': ['保险', '平安', '人寿'], '证券': ['证券'],
        }
        for ind, kws in kw_map.items():
            if any(kw in name for kw in kws):
                return ind
        return '其他'

    def _empty_stock_detail(self, code: str, name: str) -> Dict:
        return {
            'code': code, 'name': name, 'industry': '其他',
            'roe': None, 'gross_margin': None, 'net_profit_growth': None,
            'revenue_growth': None, 'ocf_to_ni': None, 'fcf_to_rev': None,
            'debt_ratio': None, 'quick_ratio': None,
            'pe_ttm': None, 'pe_percentile': None, 'pb_ttm': None, 'pb_percentile': None,
            'peg': None, 'dividend_yield': None,
            'news_positive': 0, 'news_negative': 0, 'news_neutral': 0,
            'social_media_ratio': 0.3, 'institution_media_ratio': 0.2,
            'analyst_upgrade': 0, 'analyst_downgrade': 0, 'analyst_total': 0,
            'research_visit_pct': 0.5, 'capital_flow_pct': 0.0,
            'financial_raw': {}, '_news': [],
        }
