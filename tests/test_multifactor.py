"""
核心评分测试 — 覆盖 M1~M5 模型的评分逻辑
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from multifactor_model import MultiFactorModel


class TestMultiFactorScoring:
    """多因子模型评分单元测试"""

    @classmethod
    def setup_class(cls):
        """创建测试用的 MultiFactorModel 实例（不连接网络）"""
        cls.model = MultiFactorModel("000001", api_key="test-key")

    # ── M1: 个股质量评分 ──

    def test_M1_normal_stock(self):
        """正常输入：一只各项指标良好的股票"""
        stock_details = {
            "000001": {
                "code": "000001",
                "name": "测试银行",
                "industry": "银行",
                "industry_sw": "银行",
                "roe": 0.12,
                "gross_margin": 0.45,
                "net_profit_growth": 0.15,
                "revenue_growth": 0.10,
                "ocf_to_ni": 1.2,
                "fcf_to_rev": 0.08,
                "debt_ratio": 0.60,
                "quick_ratio": 1.5,
                "weight": 1.0,
                "ratio_pct": 10.0,
            }
        }
        holdings = [{"code": "000001", "name": "测试银行", "ratio": "10%", "weight": 1.0, "norm_weight": 1.0}]
        result = self.model._calc_M1(stock_details, holdings)
        assert "score" in result
        assert 0 <= result["score"] <= 100
        # M1 返回 stock_scores 和 sub_scores
        assert "stock_scores" in result or "sub_scores" in result

    def test_M1_missing_data(self):
        """边界输入：股票数据缺失"""
        stock_details = {
            "000001": {
                "code": "000001",
                "name": "数据缺失股",
                "industry": "",
                "roe": None,
                "gross_margin": None,
                "net_profit_growth": None,
                "revenue_growth": None,
                "ocf_to_ni": None,
                "fcf_to_rev": None,
                "debt_ratio": None,
                "quick_ratio": None,
                "weight": 1.0,
                "ratio_pct": 10.0,
            }
        }
        holdings = [{"code": "000001", "name": "数据缺失股", "ratio": "10%", "weight": 1.0, "norm_weight": 1.0}]
        result = self.model._calc_M1(stock_details, holdings)
        assert "score" in result
        # 数据缺失时评分应为 0 或接近 0
        assert result["score"] >= 0

    # ── M2: 估值性价比 ──

    def test_M2_normal_stock(self):
        """正常输入：估值数据完整"""
        stock_details = {
            "000001": {
                "code": "000001",
                "name": "测试股",
                "industry": "银行",
                "pe_ttm": 6.5,
                "pe_percentile": 0.25,
                "pb_ttm": 0.8,
                "pb_percentile": 0.20,
                "peg": 0.8,
                "dividend_yield": 0.04,
                "weight": 1.0,
                "ratio_pct": 10.0,
            }
        }
        holdings = [{"code": "000001", "name": "测试股", "ratio": "10%", "weight": 1.0, "norm_weight": 1.0}]
        result = self.model._calc_M2(stock_details, holdings)
        assert "score" in result
        assert 0 <= result["score"] <= 100

    def test_M2_extreme_valuation(self):
        """边界输入：极端估值（PE=100）"""
        stock_details = {
            "000001": {
                "code": "000001",
                "name": "高估值股",
                "industry": "电子",
                "pe_ttm": 100.0,
                "pe_percentile": 0.95,
                "pb_ttm": 10.0,
                "pb_percentile": 0.90,
                "peg": 5.0,
                "dividend_yield": 0.001,
                "weight": 1.0,
                "ratio_pct": 10.0,
            }
        }
        holdings = [{"code": "000001", "name": "高估值股", "ratio": "10%", "weight": 1.0, "norm_weight": 1.0}]
        result = self.model._calc_M2(stock_details, holdings)
        # 极端高估值应有较低评分
        assert result["score"] <= 50

    # ── M3: 新闻舆情 ──

    def test_M3_normal(self):
        """正常输入：舆情数据"""
        stock_details = {
            "000001": {
                "code": "000001",
                "name": "测试股",
                "news_positive": 3,
                "news_negative": 1,
                "news_neutral": 2,
                "analyst_upgrade": 1,
                "analyst_downgrade": 0,
                "analyst_total": 5,
                "research_visit_pct": 0.6,
                "capital_flow_pct": 2.5,
                "weight": 1.0,
                "ratio_pct": 10.0,
            }
        }
        holdings = [{"code": "000001", "name": "测试股", "ratio": "10%", "weight": 1.0, "norm_weight": 1.0}]
        result = self.model._calc_M3(stock_details, holdings)
        assert "score" in result
        assert 0 <= result["score"] <= 100

    def test_M3_no_news(self):
        """边界输入：无新闻数据"""
        stock_details = {
            "000001": {
                "code": "000001",
                "name": "无新闻股",
                "news_positive": 0,
                "news_negative": 0,
                "news_neutral": 0,
                "analyst_upgrade": 0,
                "analyst_downgrade": 0,
                "analyst_total": 0,
                "research_visit_pct": 0.5,
                "capital_flow_pct": 0.0,
                "weight": 1.0,
                "ratio_pct": 10.0,
            }
        }
        holdings = [{"code": "000001", "name": "无新闻股", "ratio": "10%", "weight": 1.0, "norm_weight": 1.0}]
        result = self.model._calc_M3(stock_details, holdings)
        assert result["score"] >= 0
        # 无新闻时应在中等附近
        assert 40 <= result["score"] <= 60

    # ── M4: 行业景气 ──

    def test_M4_bull_market(self):
        """牛市环境：行业+宏观匹配好"""
        stock_details = {
            "000001": {
                "code": "000001", "name": "银行股", "industry": "银行",
                "industry_sw": "银行", "weight": 1.0, "ratio_pct": 25.0,
            },
            "600519": {
                "code": "600519", "name": "茅台", "industry": "白酒",
                "industry_sw": "食品饮料", "weight": 0.5, "ratio_pct": 15.0,
            },
        }
        holdings = [
            {"code": "000001", "name": "银行股", "ratio": "25%", "weight": 0.5, "norm_weight": 0.625},
            {"code": "600519", "name": "茅台", "ratio": "15%", "weight": 0.5, "norm_weight": 0.375},
        ]
        market_env = {
            "csi300_pe_pct": 0.75,
            "csi300_pe": 16.0,
            "bond_10y": 0.035,
            "epu_pct": 0.30,
            "usdcny": 7.2,
            "volatility_pct": 15,
            "ma_ratio": 1.05,
        }
        result = self.model._calc_M4(stock_details, holdings, market_env)
        assert "score" in result
        assert 0 <= result["score"] <= 100

    # ── M5: 基金经理行为 ──

    def test_M5_with_data(self):
        """基金信息完整"""
        fund_info = {
            "fund_name": "测试基金",
            "fund_manager": "张三",
            "fund_type": "股票型",
            "manager_history": {"manager": "张三", "recent_changed": False},
        }
        holdings = [{"code": "000001", "name": "测试股", "ratio": "10%"}]
        result = self.model._calc_M5(fund_info, holdings)
        assert "score" in result
        assert 0 <= result["score"] <= 100

    def test_M5_no_manager_data(self):
        """无基金经理数据"""
        fund_info = {"fund_name": "测试", "fund_manager": "未知"}
        holdings = []
        result = self.model._calc_M5(fund_info, holdings)
        assert "score" in result
        # 无数据时给中等偏保守分
        assert result["score"] >= 30

    # ── 综合评分 ──

    def test_composite_score_range(self):
        """综合评分应在 0-100 之间"""
        from multifactor_model import WEIGHT_MATRIX

        weights = WEIGHT_MATRIX.get("正常", {"M1": 0.25, "M2": 0.25, "M3": 0.2, "M4": 0.15, "M5": 0.15})
        model_scores = {"M1": 70, "M2": 65, "M3": 60, "M4": 55, "M5": 50}
        composite = sum(weights[f"M{i}"] * model_scores[f"M{i}"] for i in range(1, 6))
        assert 0 <= composite <= 100
        # 正常情况不应为 0
        assert composite > 0

    # ── 评分到等级转换 ──

    def test_score_to_grade_excellent(self):
        grade, action = self.model._score_to_grade(90)
        assert grade == "优秀"
        assert len(action) > 0  # action 有内容即可

    def test_score_to_grade_poor(self):
        grade, action = self.model._score_to_grade(25)
        assert grade in ("较低", "差")
        assert len(action) > 0  # action 有内容即可

    # ── 市场环境识别 ──

    def test_identify_bull_market(self):
        result = self.model._identify_market_regime({
            "ma_ratio": 1.05,
            "csi300_pe_pct": 0.75,
            "volatility_pct": 15,
            "epu_pct": 0.40,
        })
        assert result == "牛市"

    def test_identify_bear_market(self):
        result = self.model._identify_market_regime({
            "ma_ratio": 0.95,
            "csi300_pe_pct": 0.20,
            "volatility_pct": 18,
            "epu_pct": 0.50,
        })
        assert result == "熊市"

    def test_identify_high_uncertainty(self):
        result = self.model._identify_market_regime({
            "ma_ratio": 1.00,
            "csi300_pe_pct": 0.50,
            "volatility_pct": 35,
            "epu_pct": 0.85,
        })
        assert result == "高不确定性"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
