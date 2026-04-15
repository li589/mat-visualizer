"""
缓存管理模块 - 提供 LRU 缓存和内存管理功能
"""

import gc
import logging
from collections import OrderedDict
from typing import Any, Optional, Dict
from .config import Config

logger = logging.getLogger(__name__)


class LRUCache:
    """
    LRU (Least Recently Used) 缓存实现
    
    特性:
    - 基于 OrderedDict 实现 O(1) 的访问和更新
    - 自动淘汰最少使用的数据
    - 支持内存限制
    - 线程安全（通过外部锁）
    
    Attributes:
        max_size: 最大缓存项数量
        max_memory_mb: 最大内存占用 (MB)
    """
    
    def __init__(self, max_size: int = None, max_memory_mb: int = None):
        """
        初始化 LRU 缓存
        
        Args:
            max_size: 最大缓存项数量，默认使用 Config.CACHE_MAX_SIZE
            max_memory_mb: 最大内存占用 (MB)，默认使用 Config.CACHE_MAX_MEMORY_MB
        """
        self.cache: OrderedDict = OrderedDict()
        self.max_size = max_size or Config.CACHE_MAX_SIZE
        self.max_memory_mb = max_memory_mb or Config.CACHE_MAX_MEMORY_MB
        self._memory_usage: Dict[str, int] = {}  # 跟踪每项的内存占用
    
    def get(self, key: str) -> Optional[Any]:
        """
        从缓存获取数据
        
        Args:
            key: 缓存键
            
        Returns:
            缓存值，如果不存在则返回 None
        """
        if key in self.cache:
            # 移动到末尾表示最近使用
            self.cache.move_to_end(key)
            logger.debug(f"缓存命中：{key}")
            return self.cache[key]
        logger.debug(f"缓存未命中：{key}")
        return None
    
    def put(self, key: str, value: Any, memory_mb: float = 0) -> None:
        """
        向缓存添加数据
        
        Args:
            key: 缓存键
            value: 缓存值
            memory_mb: 数据占用的内存 (MB)，用于内存管理
        """
        if key in self.cache:
            # 如果已存在，移动到末尾
            self.cache.move_to_end(key)
            logger.debug(f"缓存更新：{key}")
        else:
            logger.debug(f"缓存添加：{key}")
        
        self.cache[key] = value
        self._memory_usage[key] = int(memory_mb * 1024 * 1024) if memory_mb > 0 else 0
        
        # 检查并淘汰旧数据
        self._evict_if_needed()
    
    def remove(self, key: str) -> bool:
        """
        从缓存移除数据
        
        Args:
            key: 缓存键
            
        Returns:
            是否成功移除
        """
        if key in self.cache:
            del self.cache[key]
            if key in self._memory_usage:
                del self._memory_usage[key]
            logger.debug(f"缓存移除：{key}")
            return True
        return False
    
    def clear(self) -> None:
        """清空缓存并释放内存"""
        self.cache.clear()
        self._memory_usage.clear()
        self._force_gc()
        logger.info("缓存已清空")
    
    def get_current(self) -> Optional[Any]:
        """
        获取最近使用的缓存项
        
        Returns:
            最近使用的缓存值，如果缓存为空则返回 None
        """
        if self.cache:
            last_key = next(reversed(self.cache))
            return self.cache[last_key]
        return None
    
    def get_current_key(self) -> Optional[str]:
        """
        获取最近使用的缓存键
        
        Returns:
            最近使用的缓存键，如果缓存为空则返回 None
        """
        if self.cache:
            return next(reversed(self.cache))
        return None
    
    def get_keys(self) -> list:
        """获取所有缓存键（按使用时间排序）"""
        return list(self.cache.keys())
    
    def size(self) -> int:
        """获取缓存项数量"""
        return len(self.cache)
    
    def get_memory_usage(self) -> Dict[str, int]:
        """获取内存使用情况"""
        return self._memory_usage.copy()
    
    def _evict_if_needed(self) -> None:
        """检查是否需要淘汰旧数据"""
        # 检查数量限制
        while len(self.cache) > self.max_size:
            oldest_key = next(iter(self.cache))
            self.remove(oldest_key)
            logger.info(f"因数量限制淘汰缓存：{oldest_key}")
        
        # 检查内存限制
        total_memory = sum(self._memory_usage.values())
        max_memory_bytes = self.max_memory_mb * 1024 * 1024
        
        while total_memory > max_memory_bytes and len(self.cache) > 1:
            oldest_key = next(iter(self.cache))
            removed_memory = self._memory_usage.get(oldest_key, 0)
            self.remove(oldest_key)
            total_memory -= removed_memory
            logger.info(f"因内存限制淘汰缓存：{oldest_key}")
    
    def _force_gc(self) -> None:
        """强制垃圾回收"""
        try:
            gc.collect()
            logger.debug("已执行垃圾回收")
        except Exception as e:
            logger.warning(f"垃圾回收失败：{e}")
    
    def __contains__(self, key: str) -> bool:
        """检查缓存是否包含指定键"""
        return key in self.cache
    
    def __len__(self) -> int:
        """获取缓存项数量"""
        return len(self.cache)
    
    def __repr__(self) -> str:
        """返回缓存的字符串表示"""
        return f"LRUCache(size={len(self.cache)}, max_size={self.max_size})"


class CacheManager:
    """
    缓存管理器 - 提供统一的缓存管理接口
    
    特性:
    - 单例模式
    - 支持多个缓存实例
    - 提供缓存统计和监控
    """
    
    _instance: Optional['CacheManager'] = None
    _caches: Dict[str, LRUCache] = {}
    
    def __new__(cls) -> 'CacheManager':
        """单例模式实现"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def get_cache(self, name: str = "default") -> LRUCache:
        """
        获取或创建命名缓存
        
        Args:
            name: 缓存名称
            
        Returns:
            LRU 缓存实例
        """
        if name not in self._caches:
            self._caches[name] = LRUCache()
            logger.info(f"创建新缓存：{name}")
        return self._caches[name]
    
    def clear_cache(self, name: Optional[str] = None) -> None:
        """
        清空缓存
        
        Args:
            name: 缓存名称，如果为 None 则清空所有缓存
        """
        if name:
            if name in self._caches:
                self._caches[name].clear()
                logger.info(f"已清空缓存：{name}")
        else:
            for cache in self._caches.values():
                cache.clear()
            self._caches.clear()
            logger.info("已清空所有缓存")
    
    def get_stats(self) -> Dict[str, Any]:
        """
        获取缓存统计信息
        
        Returns:
            包含缓存统计信息的字典
        """
        stats = {
            "cache_count": len(self._caches),
            "total_items": sum(len(cache) for cache in self._caches.values()),
            "caches": {}
        }
        
        for name, cache in self._caches.items():
            stats["caches"][name] = {
                "size": len(cache),
                "max_size": cache.max_size,
                "memory_usage": cache.get_memory_usage()
            }
        
        return stats
    
    def __repr__(self) -> str:
        """返回缓存管理器的字符串表示"""
        return f"CacheManager(caches={list(self._caches.keys())})"


# 全局缓存管理器实例
cache_manager = CacheManager()
