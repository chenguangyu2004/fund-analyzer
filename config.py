"""
配置中心 — 统一管理所有环境变量和应用参数
所有模块通过 `from config import ...` 获取配置值
"""
import os
import sys
import json
from typing import Any, Dict

# 数据文件缓存（避免重复读取）
_data_cache: Dict[str, Any] = {}

# ═══════════════════════════════════════
# 路径常量
# ═══════════════════════════════════════
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE_DIR, "logs")
DATA_DIR = os.path.join(BASE_DIR, "data")

# ═══════════════════════════════════════
# .env 加载（兼容项目级 .env 文件）
# ═══════════════════════════════════════
try:
    from dotenv import load_dotenv

    dotenv_path = os.path.join(BASE_DIR, ".env")
    if os.path.exists(dotenv_path):
        load_dotenv(dotenv_path)
except ImportError:
    pass  # python-dotenv 未安装时使用系统环境变量

# ═══════════════════════════════════════
# DeepSeek API
# ═══════════════════════════════════════
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_API_URL = os.environ.get(
    "DEEPSEEK_API_URL", "https://api.deepseek.com/chat/completions"
)
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-pro")

# ═══════════════════════════════════════
# Flask 服务器
# ═══════════════════════════════════════
FLASK_HOST = os.environ.get("FLASK_HOST", "127.0.0.1")
FLASK_PORT = int(os.environ.get("FLASK_PORT", "5000"))
FLASK_DEBUG = os.environ.get("FLASK_DEBUG", "false").lower() == "true"

# ═══════════════════════════════════════
# 日志
# ═══════════════════════════════════════
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")

# ═══════════════════════════════════════
# HTTP 请求参数
# ═══════════════════════════════════════
REQUEST_TIMEOUT_DEFAULT = int(os.environ.get("REQUEST_TIMEOUT", "8"))
REQUEST_TIMEOUT_SHORT = int(os.environ.get("REQUEST_TIMEOUT_SHORT", "5"))
REQUEST_TIMEOUT_LONG = int(os.environ.get("REQUEST_TIMEOUT_LONG", "45"))
REQUEST_TIMEOUT_AI = int(os.environ.get("REQUEST_TIMEOUT_AI", "120"))

# ═══════════════════════════════════════
# 并发参数
# ═══════════════════════════════════════
STOCK_FETCH_WORKERS = int(os.environ.get("STOCK_FETCH_WORKERS", "5"))
MARKET_ENV_WORKERS = int(os.environ.get("MARKET_ENV_WORKERS", "4"))

# ═══════════════════════════════════════
# AI 分析参数
# ═══════════════════════════════════════
AI_MAX_TOKENS = int(os.environ.get("AI_MAX_TOKENS", "8192"))
AI_TEMPERATURE = float(os.environ.get("AI_TEMPERATURE", "0.3"))


# ═══════════════════════════════════════
# 数据文件加载（带缓存）
# ═══════════════════════════════════════
def load_data_json(filename: str, default: Any = None) -> Any:
    """
    从 data/ 目录加载 JSON 配置文件，带内存缓存。

    Args:
        filename: JSON 文件名（不含路径），如 "industry_leaders.json"
        default: 文件不存在时的回退默认值

    Returns:
        解析后的 Python 对象
    """
    if filename in _data_cache:
        return _data_cache[filename]

    filepath = os.path.join(DATA_DIR, filename)
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        _data_cache[filename] = data
        return data
    except (FileNotFoundError, json.JSONDecodeError):
        if default is not None:
            _data_cache[filename] = default
        return default
