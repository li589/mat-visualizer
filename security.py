"""
安全工具模块 - 提供输入验证、XSS 防护、路径遍历防护等安全功能
"""

import re
import os
import html
import logging
from typing import Optional, Any, Dict, List
from functools import wraps
from flask import request, jsonify, abort

# 配置日志
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

# 安全的变量名模式（只允许字母、数字、下划线）
SAFE_VAR_NAME_PATTERN = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')

# 安全的文件名模式
SAFE_FILENAME_PATTERN = re.compile(r'^[a-zA-Z0-9_\-\.]+$')

# 禁止的字符（用于防止 XSS）
DANGEROUS_CHARS = re.compile(r'[<>"\'`]')

# 最大输入长度限制
MAX_INPUT_LENGTH = 1000
MAX_FILENAME_LENGTH = 255
MAX_PATH_LENGTH = 500


def sanitize_string(value: Any, max_length: int = MAX_INPUT_LENGTH) -> str:
    """
    清理字符串输入，移除潜在危险字符
    
    Args:
        value: 输入值
        max_length: 最大长度限制
        
    Returns:
        清理后的字符串
    """
    if value is None:
        return ''
    
    str_value = str(value)
    
    # 限制长度
    if len(str_value) > max_length:
        str_value = str_value[:max_length]
        logger.warning(f"输入超过最大长度 {max_length}，已截断")
    
    # 移除危险字符
    str_value = DANGEROUS_CHARS.sub('', str_value)
    
    return str_value.strip()


def validate_var_name(name: str) -> bool:
    """
    验证变量名是否安全
    
    Args:
        name: 变量名
        
    Returns:
        是否安全
    """
    if not name or not isinstance(name, str):
        return False
    
    if len(name) > MAX_INPUT_LENGTH:
        return False
    
    return bool(SAFE_VAR_NAME_PATTERN.match(name))


def validate_filename(filename: str) -> bool:
    """
    验证文件名是否安全
    
    Args:
        filename: 文件名
        
    Returns:
        是否安全
    """
    if not filename or not isinstance(filename, str):
        return False
    
    if len(filename) > MAX_FILENAME_LENGTH:
        return False
    
    # 检查是否包含路径遍历字符
    if '..' in filename or '/' in filename or '\\' in filename:
        return False
    
    return bool(SAFE_FILENAME_PATTERN.match(filename))


def safe_path_join(base_path: str, *paths: str) -> Optional[str]:
    """
    安全地连接路径，防止路径遍历攻击
    
    Args:
        base_path: 基础路径
        *paths: 要连接的路径部分
        
    Returns:
        安全的路径，如果检测到攻击则返回 None
    """
    # 检查所有路径部分是否包含路径遍历
    for path in paths:
        if not path:
            continue
        
        # 检查路径遍历攻击
        if '..' in path:
            logger.warning(f"检测到路径遍历攻击：{path}")
            return None
        
        # 检查绝对路径
        if os.path.isabs(path):
            logger.warning(f"检测到绝对路径：{path}")
            return None
    
    # 连接路径
    result = os.path.join(base_path, *paths)
    
    # 规范化路径
    result = os.path.normpath(result)
    
    # 确保结果在基础路径内
    base_path = os.path.normpath(base_path)
    if not result.startswith(base_path):
        logger.warning(f"路径超出基础目录：{result}")
        return None
    
    # 检查总长度
    if len(result) > MAX_PATH_LENGTH:
        logger.warning(f"路径超过最大长度：{len(result)}")
        return None
    
    return result


def escape_html(text: str) -> str:
    """
    HTML 转义，防止 XSS 攻击
    
    Args:
        text: 原始文本
        
    Returns:
        转义后的文本
    """
    if text is None:
        return ''
    return html.escape(str(text), quote=True)


def validate_json_request(required_fields: List[str] = None):
    """
    装饰器：验证 JSON 请求
    
    Args:
        required_fields: 必需的字段列表
        
    Usage:
        @app.route('/api', methods=['POST'])
        @validate_json_request(['field1', 'field2'])
        def api():
            data = request.get_json()
            # ...
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # 检查 Content-Type
            if not request.is_json:
                return jsonify({'error': 'Content-Type 必须是 application/json'}), 400
            
            data = request.get_json()
            if data is None:
                return jsonify({'error': '无效的 JSON 数据'}), 400
            
            # 检查必需字段
            if required_fields:
                missing = [field for field in required_fields if field not in data]
                if missing:
                    return jsonify({'error': f'缺少必需字段：{", ".join(missing)}'}), 400
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def rate_limit(max_requests: int = 100, window_seconds: int = 60):
    """
    简单的速率限制装饰器
    
    Args:
        max_requests: 最大请求次数
        window_seconds: 时间窗口（秒）
    """
    from collections import defaultdict
    import time
    
    request_history = defaultdict(list)
    
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            client_ip = request.remote_addr
            current_time = time.time()
            
            # 清理过期记录
            request_history[client_ip] = [
                t for t in request_history[client_ip]
                if current_time - t < window_seconds
            ]
            
            # 检查是否超限
            if len(request_history[client_ip]) >= max_requests:
                logger.warning(f"速率限制：{client_ip}")
                return jsonify({'error': '请求过于频繁，请稍后再试'}), 429
            
            # 记录请求
            request_history[client_ip].append(current_time)
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def validate_file_size(file, max_size_mb: int = 500) -> bool:
    """
    验证文件大小
    
    Args:
        file: 文件对象
        max_size_mb: 最大文件大小（MB）
        
    Returns:
        是否合法
    """
    try:
        # 获取当前文件位置
        current_pos = file.tell()
        
        # 移动到文件末尾获取大小
        file.seek(0, 2)
        file_size = file.tell()
        
        # 恢复文件位置
        file.seek(current_pos)
        
        # 检查大小
        max_size_bytes = max_size_mb * 1024 * 1024
        if file_size > max_size_bytes:
            logger.warning(f"文件过大：{file_size / 1024 / 1024:.2f}MB")
            return False
        
        return True
    except Exception as e:
        logger.error(f"文件大小检查失败：{e}")
        return False


def sanitize_url(url: str) -> Optional[str]:
    """
    验证和清理 URL，只允许 HTTP/HTTPS
    
    Args:
        url: 原始 URL
        
    Returns:
        清理后的 URL，如果不合法则返回 None
    """
    if not url or not isinstance(url, str):
        return None
    
    url = url.strip()
    
    if len(url) > MAX_PATH_LENGTH:
        return None
    
    # 只允许 HTTP/HTTPS
    if not (url.startswith('http://') or url.startswith('https://')):
        logger.warning(f"不支持的 URL 协议：{url}")
        return None
    
    # 检查是否包含危险字符
    if DANGEROUS_CHARS.search(url):
        logger.warning(f"URL 包含危险字符：{url}")
        return None
    
    return url
