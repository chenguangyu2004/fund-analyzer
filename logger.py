"""
统一日志模块 — 封装 RotatingFileHandler + 控制台输出
所有模块通过 `from logger import get_logger` 获取 logger 实例
"""
import logging
import os
import sys
from logging.handlers import RotatingFileHandler

_loggers = {}


def get_logger(name: str = "fund_analyzer", log_dir: str = None) -> logging.Logger:
    """
    获取指定名称的 logger 实例（单例模式）。

    Args:
        name: logger 名称，默认 "fund_analyzer"
        log_dir: 日志目录，默认项目根目录下的 logs/

    Returns:
        配置好的 Logger 实例
    """
    if name in _loggers:
        return _loggers[name]

    if log_dir is None:
        log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")

    os.makedirs(log_dir, exist_ok=True)

    logger = logging.getLogger(name)

    # 避免重复 handler（reload 场景）
    if logger.handlers:
        _loggers[name] = logger
        return logger

    logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

    # 格式
    fmt = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 文件 handler — RotatingFileHandler (5 MB × 3 个轮转)
    fh = RotatingFileHandler(
        os.path.join(log_dir, "app.log"),
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    # 控制台 handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    _loggers[name] = logger
    return logger
