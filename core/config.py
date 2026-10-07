"""
配置模块 - 管理应用全局配置
"""

import os
import tempfile
from typing import Optional

from .version import read_version


class Config:
    """应用配置类，集中管理所有配置项"""

    # 应用配置
    APP_NAME: str = "MAT 文件可视化工具"
    # 版本号统一来自 VERSION 文件，避免与发布包名、启动器窗口显示不一致
    VERSION: str = read_version()
    DEBUG: bool = False
    
    # 服务器配置
    HOST: str = "127.0.0.1"
    PORT: int = 5000
    
    # 文件上传配置
    MAX_CONTENT_LENGTH_MB: int = 500
    UPLOAD_DIR: str = os.path.join(tempfile.gettempdir(), "mat_uploads")
    ALLOWED_EXTENSIONS: set = {"mat"}
    
    # 缓存配置
    CACHE_MAX_SIZE: int = 3  # 最大缓存文件数
    CACHE_MAX_MEMORY_MB: int = 500  # 最大内存占用 (MB)
    
    # 性能配置
    LAZY_LOAD_THRESHOLD: int = 10000000  # 懒加载阈值 (元素数)
    MAX_VALUES_IN_MEMORY: int = 5000000  # 内存中最大元素数
    CHUNK_THRESHOLD: int = 1000000  # 分块读取阈值
    
    # 安全配置
    RATE_LIMIT_UPLOAD: int = 20  # 上传速率限制 (次/分钟)
    RATE_LIMIT_REMOTE: int = 10  # 远程加载速率限制 (次/分钟)
    RATE_LIMIT_VARIABLE: int = 100  # 变量查询速率限制 (次/分钟)
    RATE_LIMIT_EXPORT: int = 30  # 导出速率限制 (次/分钟)
    
    # 输入验证配置
    MAX_INPUT_LENGTH: int = 1000
    MAX_FILENAME_LENGTH: int = 255
    MAX_PATH_LENGTH: int = 500
    
    # 分页配置
    DEFAULT_PAGE_SIZE: int = 100  # 默认每页行数
    MAX_PAGE_SIZE: int = 500  # 最大每页行数
    
    # 导出配置
    SUPPORTED_EXPORT_FORMATS: set = {"csv", "xlsx", "txt", "npy", "mat"}
    
    @classmethod
    def init_app(cls, app):
        """初始化 Flask 应用配置"""
        app.config["MAX_CONTENT_LENGTH"] = cls.MAX_CONTENT_LENGTH_MB * 1024 * 1024
        app.config["SECRET_KEY"] = os.urandom(24)
        
        # 创建上传目录
        os.makedirs(cls.UPLOAD_DIR, exist_ok=True)
        
        # 设置调试模式
        cls.DEBUG = app.debug
    
    @classmethod
    def get_upload_dir(cls) -> str:
        """获取上传目录路径"""
        return cls.UPLOAD_DIR
    
    @classmethod
    def get_max_content_length(cls) -> int:
        """获取最大文件上传大小 (字节)"""
        return cls.MAX_CONTENT_LENGTH_MB * 1024 * 1024
    
    @classmethod
    def is_allowed_extension(cls, filename: str) -> bool:
        """检查文件扩展名是否允许"""
        return "." in filename and \
               filename.rsplit(".", 1)[1].lower() in cls.ALLOWED_EXTENSIONS
