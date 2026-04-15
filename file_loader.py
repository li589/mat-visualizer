"""
统一文件加载模块
支持：本地文件、HTTP/HTTPS远程文件、SSH远程服务器文件
"""

import os
import tempfile
import urllib.request
import urllib.error
import urllib.parse
from typing import Optional, Tuple

try:
    import paramiko
    HAS_PARAMIKO = True
except ImportError:
    HAS_PARAMIKO = False


class FileLoader:
    """统一文件加载器，支持多种数据源"""

    def __init__(self, cache_dir: Optional[str] = None):
        """
        Args:
            cache_dir: 缓存目录，默认为系统临时目录
        """
        self.cache_dir = cache_dir or os.path.join(tempfile.gettempdir(), "mat_loader_cache")
        os.makedirs(self.cache_dir, exist_ok=True)

    def load(self, source: str, **kwargs) -> Tuple[str, bool]:
        """
        加载文件，自动识别数据源类型

        Args:
            source: 数据源（本地路径、HTTP/HTTPS URL、SSH路径）
            **kwargs: 额外参数（如SSH连接信息）

        Returns:
            (本地文件路径, 是否为临时文件)

        Raises:
            ValueError: 不支持的数据源类型
            FileNotFoundError: 文件不存在
            urllib.error.URLError: HTTP下载失败
            paramiko.SSHException: SSH连接失败
        """
        if source.startswith(("http://", "https://")):
            return self._load_http(source, **kwargs)
        elif source.startswith("ssh://"):
            return self._load_ssh(source, **kwargs)
        else:
            return self._load_local(source)

    def _load_local(self, filepath: str) -> Tuple[str, bool]:
        """加载本地文件"""
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"文件不存在: {filepath}")
        if not filepath.endswith(".mat"):
            raise ValueError("仅支持 .mat 文件")
        return filepath, False

    def _load_http(self, url: str, timeout: int = 30, chunk_size: int = 8192) -> Tuple[str, bool]:
        """
        从HTTP/HTTPS下载文件

        Args:
            url: 文件URL
            timeout: 超时时间（秒）
            chunk_size: 下载块大小

        Returns:
            (本地缓存路径, True)
        """
        if not url.endswith(".mat"):
            raise ValueError("仅支持 .mat 文件")

        filename = os.path.basename(url.split("?")[0])
        if not filename:
            filename = "remote_file.mat"

        cache_path = os.path.join(self.cache_dir, filename)

        try:
            request = urllib.request.Request(url, headers={"User-Agent": "MAT-File-Loader/1.0"})
            with urllib.request.urlopen(request, timeout=timeout) as response:
                with open(cache_path, "wb") as f:
                    while True:
                        chunk = response.read(chunk_size)
                        if not chunk:
                            break
                        f.write(chunk)
            return cache_path, True
        except urllib.error.URLError as e:
            raise urllib.error.URLError(f"下载失败: {str(e)}")

    def _load_ssh(self, ssh_path: str, **kwargs) -> Tuple[str, bool]:
        """
        从SSH远程服务器下载文件

        Args:
            ssh_path: SSH路径，格式 ssh://user@host:port/path/to/file.mat
            **kwargs: 额外参数
                - password: SSH密码
                - key_filename: SSH私钥路径
                - timeout: 超时时间

        Returns:
            (本地缓存路径, True)
        """
        if not HAS_PARAMIKO:
            raise ImportError("需要安装 paramiko 库: pip install paramiko")

        if not ssh_path.endswith(".mat"):
            raise ValueError("仅支持 .mat 文件")

        parsed = urllib.parse.urlparse(ssh_path)
        user = parsed.username
        host = parsed.hostname
        port = parsed.port or 22
        remote_path = urllib.parse.unquote(parsed.path or "")

        if not user or not host or not remote_path:
            raise ValueError("SSH路径格式错误，应为 ssh://user@host:port/path/to/file.mat")

        filename = os.path.basename(remote_path)
        cache_path = os.path.join(self.cache_dir, filename)

        password = kwargs.get("password")
        key_filename = kwargs.get("key_filename")
        timeout = kwargs.get("timeout", 30)

        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(
                host,
                port=port,
                username=user,
                password=password,
                key_filename=key_filename,
                timeout=timeout
            )

            sftp = ssh.open_sftp()
            sftp.get(remote_path, cache_path)
            sftp.close()
            ssh.close()

            return cache_path, True
        except paramiko.SSHException as e:
            raise paramiko.SSHException(f"SSH连接失败: {str(e)}")

    def clear_cache(self):
        """清空缓存目录"""
        import shutil
        if os.path.exists(self.cache_dir):
            shutil.rmtree(self.cache_dir)
            os.makedirs(self.cache_dir, exist_ok=True)


def parse_source(source: str) -> dict:
    """
    解析数据源，返回类型和详细信息

    Args:
        source: 数据源字符串

    Returns:
        {
            "type": "local" | "http" | "https" | "ssh",
            "source": 原始字符串,
            "info": 额外信息
        }
    """
    if source.startswith("https://"):
        return {"type": "https", "source": source, "info": {"url": source}}
    elif source.startswith("http://"):
        return {"type": "http", "source": source, "info": {"url": source}}
    elif source.startswith("ssh://"):
        parsed = urllib.parse.urlparse(source)
        remote_path = urllib.parse.unquote(parsed.path or "") or None

        return {
            "type": "ssh",
            "source": source,
            "info": {
                "user": parsed.username,
                "host": parsed.hostname,
                "port": parsed.port or 22,
                "path": remote_path
            }
        }
    else:
        return {
            "type": "local",
            "source": source,
            "info": {"path": source}
        }
