"""
数据服务 - 管理数据加载、解析、缓存等操作
"""

import logging
from typing import Dict, Any, Optional
import os

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.config import Config
from core.cache import LRUCache, cache_manager
from core.parser import MATParser, VariableData
from core.exporter import DataExporter, ExportFormat

logger = logging.getLogger(__name__)


class DataService:
    """
    数据服务类
    
    提供数据加载、解析、缓存、导出等功能
    
    Methods:
        load_file: 加载 MAT 文件
        get_variable: 获取变量数据
        export_variable: 导出变量
        clear_cache: 清空缓存
        get_cache_stats: 获取缓存统计
    """
    
    def __init__(self):
        """初始化数据服务"""
        self.parser = MATParser()
        self.exporter = DataExporter()
        self.cache = LRUCache(
            max_size=Config.CACHE_MAX_SIZE,
            max_memory_mb=Config.CACHE_MAX_MEMORY_MB
        )
        logger.debug("DataService 初始化")
    
    def load_file(self, filepath: str, lazy: bool = True) -> Dict[str, VariableData]:
        """
        加载 MAT 文件
        
        Args:
            filepath: 文件路径
            lazy: 是否启用懒加载
            
        Returns:
            变量名字典
        """
        logger.info(f"加载文件：{filepath}, 懒加载：{lazy}")
        
        # 检查缓存
        cached = self.cache.get(filepath)
        if cached is not None:
            logger.info(f"使用缓存数据：{filepath}")
            return cached
        
        # 解析文件
        data = self.parser.parse(filepath, lazy)
        
        if not data:
            logger.warning(f"文件未解析到任何数据：{filepath}")
            return {}
        
        # 存入缓存
        self.cache.put(filepath, data)
        logger.info(f"文件加载完成，共 {len(data)} 个变量")
        
        return data
    
    def get_variable(self, filepath: str, var_name: str) -> Optional[VariableData]:
        """
        获取变量数据
        
        Args:
            filepath: 文件路径
            var_name: 变量名
            
        Returns:
            变量数据，如果不存在则返回 None
        """
        # 从缓存获取文件数据
        file_data = self.cache.get(filepath)
        
        if file_data is None:
            # 加载文件
            file_data = self.load_file(filepath)
        
        if not file_data:
            return None
        
        # 获取变量
        return file_data.get(var_name)
    
    def export_variable(self, filepath: str, var_name: str,
                       format: str, **kwargs) -> bytes:
        """
        导出变量
        
        Args:
            filepath: 文件路径
            var_name: 变量名
            format: 导出格式
            **kwargs: 额外参数
            
        Returns:
            导出的二进制数据
            
        Raises:
            ValueError: 变量不存在或格式不支持
        """
        var_data = self.get_variable(filepath, var_name)
        
        if var_data is None:
            raise ValueError(f"变量不存在：{var_name}")
        
        if var_data.values is None and var_data.value is None:
            raise ValueError("变量数据为空")
        
        # 导出数据
        data = var_data.values if var_data.values is not None else var_data.value
        return self.exporter.export(data, format, **kwargs)
    
    def clear_cache(self, filepath: Optional[str] = None) -> None:
        """
        清空缓存
        
        Args:
            filepath: 文件路径，如果为 None 则清空所有缓存
        """
        if filepath:
            self.cache.remove(filepath)
            logger.info(f"已清除缓存：{filepath}")
        else:
            self.cache.clear()
            logger.info("已清空所有缓存")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """
        获取缓存统计信息
        
        Returns:
            缓存统计字典
        """
        return {
            "size": self.cache.size(),
            "max_size": self.cache.max_size,
            "keys": self.cache.get_keys(),
            "memory_usage": self.cache.get_memory_usage()
        }
    
    def get_current_file(self) -> Optional[Dict[str, VariableData]]:
        """
        获取当前缓存的文件数据
        
        Returns:
            文件数据，如果缓存为空则返回 None
        """
        return self.cache.get_current()
    
    def get_current_filepath(self) -> Optional[str]:
        """
        获取当前缓存的文件路径
        
        Returns:
            文件路径，如果缓存为空则返回 None
        """
        return self.cache.get_current_key()
