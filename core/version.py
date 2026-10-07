"""
版本号模块 - 版本号的单一真相源

版本号以应用目录下的 VERSION 文件为准，不再在代码中硬编码：

    - 打包脚本 build.py 读取它决定发布包名（MAT_Visualizer_v<版本>）
    - 运行时 Config.VERSION 读取它，供日志、接口等使用
    - 启动器 UI 读取它作为窗口标题与界面显示的版本号

读取路径与运行时环境相关：
    - 打包后：exe 所在目录（build.py 会把 VERSION 随包分发）
    - 源码模式：项目根目录
"""

import logging
import os
import sys

logger = logging.getLogger(__name__)

# VERSION 文件缺失时的兜底值。用 0.0.0 而不是某个历史版本号，
# 目的是让异常状态在界面上显而易见，避免"看起来是正常版本"的误导。
DEFAULT_VERSION = "0.0.0"


def get_app_dir() -> str:
    """获取应用工作目录：打包后为 exe 所在目录，源码模式为项目根目录"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read_version(default: str = DEFAULT_VERSION) -> str:
    """
    读取版本号

    Args:
        default: VERSION 文件不存在或为空时的兜底版本号

    Returns:
        VERSION 文件中的版本号；读取失败时返回 default 并记录警告
    """
    version_file = os.path.join(get_app_dir(), "VERSION")
    try:
        with open(version_file, encoding="utf-8") as f:
            version = f.read().strip()
        if version:
            return version
        logger.warning("VERSION 文件为空：%s", version_file)
    except OSError as e:
        logger.warning("读取 VERSION 文件失败：%s（%s）", version_file, e)
    return default