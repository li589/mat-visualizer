"""
文件服务 - 管理文件上传、加载等操作
"""

import os
import logging
from typing import Tuple, Optional
from werkzeug.utils import secure_filename

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.config import Config
from security import safe_path_join, validate_filename, sanitize_url

logger = logging.getLogger(__name__)


class FileService:
    """
    文件服务类
    
    提供文件上传、加载、验证等功能
    
    Methods:
        save_uploaded_file: 保存上传的文件
        validate_file: 验证文件
        get_file_path: 获取文件路径
        delete_file: 删除文件
    """
    
    def __init__(self, upload_dir: Optional[str] = None):
        """
        初始化文件服务
        
        Args:
            upload_dir: 上传目录，默认使用 Config.UPLOAD_DIR
        """
        self.upload_dir = upload_dir or Config.get_upload_dir()
        os.makedirs(self.upload_dir, exist_ok=True)
        logger.debug(f"FileService 初始化，上传目录：{self.upload_dir}")
    
    def save_uploaded_file(self, file, original_filename: str) -> Tuple[str, str]:
        """
        保存上传的文件
        
        Args:
            file: 文件对象
            original_filename: 原始文件名
            
        Returns:
            (保存的文件路径，安全的文件名)
            
        Raises:
            ValueError: 文件名无效
        """
        # 验证文件名
        if not validate_filename(original_filename):
            logger.warning(f"无效的文件名：{original_filename}")
            raise ValueError(f"无效的文件名：{original_filename}")
        
        # 安全检查文件名
        safe_name = secure_filename(original_filename)
        
        # 确保是 .mat 文件
        if not safe_name.endswith(".mat"):
            logger.warning(f"非 .mat 文件：{safe_name}")
            raise ValueError("仅支持 .mat 文件")
        
        # 构建安全路径
        file_path = safe_path_join(self.upload_dir, safe_name)
        
        if not file_path:
            logger.error("路径遍历攻击检测")
            raise ValueError("无效的文件路径")
        
        # 保存文件
        file.save(file_path)
        logger.info(f"文件已保存：{file_path}")
        
        return file_path, safe_name
    
    def validate_file(self, filepath: str, max_size_mb: Optional[int] = None) -> bool:
        """
        验证文件
        
        Args:
            filepath: 文件路径
            max_size_mb: 最大文件大小 (MB)，默认使用 Config.MAX_CONTENT_LENGTH_MB
            
        Returns:
            是否有效
        """
        if not os.path.exists(filepath):
            logger.warning(f"文件不存在：{filepath}")
            return False
        
        if not filepath.endswith(".mat"):
            logger.warning(f"非 .mat 文件：{filepath}")
            return False
        
        # 检查文件大小
        max_size = max_size_mb or Config.MAX_CONTENT_LENGTH_MB
        file_size_mb = os.path.getsize(filepath) / (1024 * 1024)
        
        if file_size_mb > max_size:
            logger.warning(f"文件超过大小限制：{file_size_mb:.2f}MB > {max_size}MB")
            return False
        
        return True
    
    def get_file_path(self, filename: str) -> Optional[str]:
        """
        获取文件路径
        
        Args:
            filename: 文件名
            
        Returns:
            文件路径，如果不存在则返回 None
        """
        if not validate_filename(filename):
            return None
        
        safe_name = secure_filename(filename)
        return safe_path_join(self.upload_dir, safe_name)
    
    def delete_file(self, filename: str) -> bool:
        """
        删除文件
        
        Args:
            filename: 文件名
            
        Returns:
            是否成功删除
        """
        file_path = self.get_file_path(filename)
        
        if not file_path or not os.path.exists(file_path):
            return False
        
        try:
            os.remove(file_path)
            logger.info(f"文件已删除：{file_path}")
            return True
        except Exception as e:
            logger.error(f"删除文件失败：{e}")
            return False
    
    def file_exists(self, filename: str) -> bool:
        """
        检查文件是否存在
        
        Args:
            filename: 文件名
            
        Returns:
            是否存在
        """
        file_path = self.get_file_path(filename)
        return file_path is not None and os.path.exists(file_path)
    
    def get_upload_dir(self) -> str:
        """获取上传目录"""
        return self.upload_dir
