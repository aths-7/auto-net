"""日志：文件轮转 + 可选控制台输出。"""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

from . import config as config_mod

LOGGER_NAME = "campusnet"
_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"


def setup(quiet: bool = False, log_file: Optional[Path] = None, verbose: bool = False) -> logging.Logger:
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    logger.propagate = False

    # 反复调用时别叠加 handler（daemon 里会重置）
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()

    target = Path(log_file) if log_file else config_mod.log_path()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            target, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8"
        )
        file_handler.setFormatter(logging.Formatter(_FORMAT))
        logger.addHandler(file_handler)
    except OSError:
        pass  # 目录不可写就只走控制台

    if not quiet:
        stream = logging.StreamHandler()
        stream.setFormatter(logging.Formatter(_FORMAT))
        logger.addHandler(stream)

    return logger


def get() -> logging.Logger:
    logger = logging.getLogger(LOGGER_NAME)
    if not logger.handlers:
        return setup()
    return logger
