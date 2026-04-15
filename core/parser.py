"""
数据解析模块 - 提供 MAT 文件解析功能
"""

import re
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
import numpy as np
import h5py
import scipy.io

from .config import Config

logger = logging.getLogger(__name__)

# 变量名验证正则
VALID_VAR_NAME_RE = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')


@dataclass
class VariableData:
    """
    变量数据结构
    
    Attributes:
        name: 变量名
        var_type: 变量类型 (scalar, ndarray, string, struct, cell 等)
        dtype: 数据类型
        shape: 形状
        ndim: 维度数
        size: 元素总数
        value: 值（标量或字符串）
        values: 值列表（数组）
        real: 实部（复数）
        imag: 虚部（复数）
        fields: 字段（结构体）
        lazy: 是否懒加载
        filepath: 文件路径（懒加载时使用）
        dataset_path: 数据集路径（懒加载时使用）
    """
    name: str
    var_type: str = "unknown"
    dtype: str = ""
    shape: List[int] = field(default_factory=list)
    ndim: int = 0
    size: int = 0
    value: Any = None
    values: Any = None
    real: Any = None
    imag: Any = None
    fields: Dict[str, Any] = field(default_factory=dict)
    lazy: bool = False
    filepath: Optional[str] = None
    dataset_path: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        result = {
            "type": self.var_type,
            "dtype": self.dtype,
            "shape": self.shape,
            "ndim": self.ndim,
            "size": self.size,
            "lazy": self.lazy,
        }
        
        if self.value is not None:
            result["value"] = self.value
        
        if self.values is not None:
            result["values"] = self.values
        
        if self.real is not None:
            result["real"] = self.real
        
        if self.imag is not None:
            result["imag"] = self.imag
        
        if self.fields:
            result["fields"] = self.fields
        
        if self.filepath:
            result["filepath"] = self.filepath
        
        if self.dataset_path:
            result["dataset_path"] = self.dataset_path
        
        return result


class MATParser:
    """
    MAT 文件解析器
    
    特性:
    - 自动检测 MATLAB 文件版本 (v5/v6/v7/v7.3)
    - 支持懒加载大文件
    - 向量化数据处理
    - 内存优化
    
    Methods:
        parse: 解析 MAT 文件
        parse_variable: 解析单个变量
        load_lazy_data: 加载懒加载数据
    """
    
    def __init__(self, lazy_threshold: int = None):
        """
        初始化解析器
        
        Args:
            lazy_threshold: 懒加载阈值（元素数），默认使用 Config.LAZY_LOAD_THRESHOLD
        """
        self.lazy_threshold = lazy_threshold or Config.LAZY_LOAD_THRESHOLD
        logger.debug(f"MATParser 初始化，懒加载阈值：{self.lazy_threshold}")
    
    @staticmethod
    def detect_mat_version(filepath: str) -> str:
        """
        检测 MAT 文件版本
        
        Args:
            filepath: 文件路径
            
        Returns:
            版本字符串 (v5, v6, v7, v7.3)
        """
        try:
            with open(filepath, 'rb') as f:
                header = f.read(128)
                
                if len(header) < 128:
                    return "未知"
                
                header_str = header[:116].decode('ascii', errors='ignore').strip()
                
                if header_str.startswith('MATLAB 5.0'):
                    return "v5"
                elif header_str.startswith('MATLAB 7.3'):
                    return "v7.3"
                elif 'MATLAB' in header_str:
                    if '7.0' in header_str or '7.1' in header_str or '7.2' in header_str:
                        return "v7"
                    elif '6.0' in header_str or '6.1' in header_str or '6.5' in header_str:
                        return "v6"
                    else:
                        return "v7 及以下"
                else:
                    try:
                        with h5py.File(filepath, 'r') as h5f:
                            return "v7.3 (HDF5)"
                    except:
                        return "v7 及以下"
        except Exception as e:
            logger.error(f"检测 MAT 版本失败：{e}")
            return "未知"
    
    def parse(self, filepath: str, lazy: bool = True) -> Dict[str, VariableData]:
        """
        解析 MAT 文件
        
        Args:
            filepath: 文件路径
            lazy: 是否启用懒加载
            
        Returns:
            变量名字典，值为 VariableData 对象
        """
        logger.info(f"开始解析 MAT 文件：{filepath}, 懒加载：{lazy}")
        
        # 尝试使用 scipy.io 解析（适用于 v5/v6/v7）
        try:
            return self._parse_scipy(filepath, lazy)
        except NotImplementedError:
            logger.debug("scipy.io 不支持此格式，尝试 h5py")
        except Exception as e:
            logger.warning(f"scipy.io 解析失败：{e}")
        
        # 使用 h5py 解析（适用于 v7.3 HDF5 格式）
        return self._parse_h5py(filepath, lazy)
    
    def _parse_scipy(self, filepath: str, lazy: bool) -> Dict[str, VariableData]:
        """使用 scipy.io 解析 MAT 文件"""
        result = {}
        mat_data = scipy.io.loadmat(filepath, squeeze_me=True, struct_as_record=False)
        
        for key, value in mat_data.items():
            if key.startswith("__"):
                continue
            
            safe_key = self._sanitize_var_name(key)
            try:
                result[safe_key] = self._parse_variable(value, lazy, name=safe_key)
            except Exception as e:
                logger.error(f"解析变量 {safe_key} 失败：{e}")
                result[safe_key] = VariableData(
                    name=safe_key,
                    var_type="unknown",
                    value="解析失败"
                )
        
        if not result:
            logger.warning("scipy.io 未解析到任何变量")
            return {}
        
        logger.info(f"scipy.io 解析完成，共 {len(result)} 个变量")
        return result
    
    def _parse_h5py(self, filepath: str, lazy: bool) -> Dict[str, VariableData]:
        """使用 h5py 解析 MAT 文件 (v7.3 HDF5 格式)"""
        result = {}
        
        try:
            with h5py.File(filepath, "r") as f:
                for key in f.keys():
                    if key.startswith("#"):
                        continue
                    
                    safe_key = self._sanitize_var_name(key)
                    try:
                        result[safe_key] = self._parse_h5_item(
                            f[key], lazy, name=safe_key, filepath=filepath
                        )
                    except Exception as e:
                        logger.error(f"解析变量 {safe_key} 失败：{e}")
                        result[safe_key] = VariableData(
                            name=safe_key,
                            var_type="unknown",
                            value="解析失败"
                        )
        except Exception as e:
            logger.error(f"h5py 解析失败：{e}")
            return {}
        
        logger.info(f"h5py 解析完成，共 {len(result)} 个变量")
        return result
    
    def _parse_variable(self, value: Any, lazy: bool, name: str = "") -> VariableData:
        """
        解析单个变量
        
        Args:
            value: 变量值
            lazy: 是否懒加载
            name: 变量名
            
        Returns:
            VariableData 对象
        """
        if not name:
            name = "unknown"
        
        # 标量
        if np.isscalar(value) or (isinstance(value, np.ndarray) and value.ndim == 0):
            return self._parse_scalar(value, name)
        
        # 字符串
        if isinstance(value, str):
            return VariableData(name=name, var_type="string", value=value)
        
        # NumPy 数组
        if isinstance(value, np.ndarray):
            return self._parse_ndarray(value, lazy, name)
        
        # 结构体
        if hasattr(value, '_fieldnames'):
            return self._parse_struct(value, lazy, name)
        
        # Cell 数组
        if hasattr(value, 'dtype') and value.dtype.kind == 'O':
            return self._parse_cell(value, lazy, name)
        
        return VariableData(name=name, var_type="unknown", value="未知类型")
    
    def _parse_scalar(self, value: Any, name: str) -> VariableData:
        """解析标量"""
        if isinstance(value, (np.integer, int)):
            return VariableData(
                name=name,
                var_type="scalar",
                dtype="int",
                value=int(value)
            )
        
        if isinstance(value, (np.floating, float)):
            # 处理 NaN 和 Inf
            if np.isnan(value) or np.isinf(value):
                return VariableData(
                    name=name,
                    var_type="scalar",
                    dtype="float",
                    value=None
                )
            return VariableData(
                name=name,
                var_type="scalar",
                dtype="float",
                value=float(value)
            )
        
        if isinstance(value, (np.bool_, bool)):
            return VariableData(
                name=name,
                var_type="scalar",
                dtype="bool",
                value=bool(value)
            )
        
        if isinstance(value, (np.complexfloating, complex)):
            real_val = value.real if np.isfinite(value.real) else None
            imag_val = value.imag if np.isfinite(value.imag) else None
            return VariableData(
                name=name,
                var_type="scalar",
                dtype="complex",
                value={"real": real_val, "imag": imag_val}
            )
        
        return VariableData(
            name=name,
            var_type="scalar",
            dtype=type(value).__name__,
            value=value
        )
    
    def _parse_ndarray(self, arr: np.ndarray, lazy: bool, name: str) -> VariableData:
        """解析 NumPy 数组"""
        shape = list(arr.shape)
        ndim = arr.ndim
        size = int(np.prod(shape)) if shape else 0
        dtype_str = str(arr.dtype)
        
        # 复数数组
        if np.issubdtype(arr.dtype, np.complexfloating):
            return self._parse_complex_array(arr, lazy, name, shape, ndim, size, dtype_str)
        
        # 字符串数组
        if arr.dtype.kind in ("S", "U", "O"):
            return self._parse_string_array(arr, name, shape, ndim, size)
        
        # 懒加载大数组
        if lazy and size > self.lazy_threshold:
            return self._make_lazy_array(name, shape, ndim, size, dtype_str)
        
        # 普通数组
        values = self._sanitize_array(arr)
        
        result = VariableData(
            name=name,
            var_type="ndarray",
            dtype=dtype_str,
            shape=shape,
            ndim=ndim,
            size=size,
            values=values
        )
        
        return result
    
    def _parse_complex_array(self, arr: np.ndarray, lazy: bool, name: str,
                            shape: List[int], ndim: int, size: int,
                            dtype_str: str) -> VariableData:
        """解析复数数组"""
        if lazy and size > self.lazy_threshold:
            return VariableData(
                name=name,
                var_type="ndarray",
                dtype="complex",
                shape=shape,
                ndim=ndim,
                size=size,
                lazy=True
            )
        
        # 向量化清理 NaN/Inf
        real_mask = np.isfinite(arr.real)
        imag_mask = np.isfinite(arr.imag)
        
        real_clean = arr.real.astype(object)
        imag_clean = arr.imag.astype(object)
        real_clean[~real_mask] = None
        imag_clean[~imag_mask] = None
        
        return VariableData(
            name=name,
            var_type="ndarray",
            dtype="complex",
            shape=shape,
            ndim=ndim,
            size=size,
            real=real_clean.tolist(),
            imag=imag_clean.tolist()
        )
    
    def _parse_string_array(self, arr: np.ndarray, name: str,
                           shape: List[int], ndim: int, size: int) -> VariableData:
        """解析字符串数组"""
        try:
            if arr.dtype.kind == "O":
                values = [self._safe_decode(v) for v in arr.flat]
            else:
                values = arr.tolist()
        except Exception as e:
            logger.warning(f"字符串数组解析失败：{e}")
            values = None
        
        return VariableData(
            name=name,
            var_type="ndarray",
            dtype="string",
            shape=shape,
            ndim=ndim,
            size=size,
            values=values
        )
    
    def _parse_struct(self, value: Any, lazy: bool, name: str) -> VariableData:
        """解析结构体"""
        fields = {}
        
        if hasattr(value, '_fieldnames'):
            for field_name in value._fieldnames:
                try:
                    field_value = getattr(value, field_name)
                    fields[field_name] = self._parse_variable(
                        field_value, lazy, name=f"{name}.{field_name}"
                    )
                except Exception as e:
                    logger.error(f"解析结构体字段 {field_name} 失败：{e}")
                    fields[field_name] = VariableData(
                        name=field_name,
                        var_type="unknown",
                        value="解析失败"
                    )
        
        return VariableData(
            name=name,
            var_type="struct",
            fields={k: v.to_dict() for k, v in fields.items()}
        )
    
    def _parse_cell(self, value: Any, lazy: bool, name: str) -> VariableData:
        """解析 Cell 数组"""
        shape = list(value.shape)
        ndim = value.ndim
        size = int(np.prod(shape)) if shape else 0
        
        # 大 Cell 数组懒加载
        if lazy and size > self.lazy_threshold:
            return VariableData(
                name=name,
                var_type="cell",
                shape=shape,
                ndim=ndim,
                size=size,
                lazy=True
            )
        
        values = []
        for val in value.flat:
            if isinstance(val, np.ndarray):
                parsed = self._parse_variable(val, lazy)
                values.append(parsed.to_dict())
            else:
                parsed = self._parse_scalar(val, name)
                values.append(parsed.to_dict())
        
        return VariableData(
            name=name,
            var_type="cell",
            shape=shape,
            ndim=ndim,
            size=size,
            values=values
        )
    
    def _parse_h5_item(self, item: Any, lazy: bool, name: str,
                      filepath: str) -> VariableData:
        """解析 h5py 对象"""
        if isinstance(item, h5py.Group):
            return self._parse_h5_group(item, lazy, name, filepath)
        
        if isinstance(item, h5py.Dataset):
            return self._parse_h5_dataset(item, lazy, name, filepath)
        
        return VariableData(name=name, var_type="unknown", value="未知类型")
    
    def _parse_h5_group(self, item: h5py.Group, lazy: bool,
                       name: str, filepath: str) -> VariableData:
        """解析 h5py Group（结构体）"""
        fields = {}
        
        for sub_key in item.keys():
            if sub_key.startswith("#"):
                continue
            
            try:
                fields[sub_key] = self._parse_h5_item(
                    item[sub_key], lazy, name=f"{name}.{sub_key}", filepath=filepath
                ).to_dict()
            except Exception as e:
                logger.error(f"解析字段 {sub_key} 失败：{e}")
                fields[sub_key] = {"type": "unknown", "value": "解析失败"}
        
        return VariableData(
            name=name,
            var_type="struct",
            fields=fields
        )
    
    def _parse_h5_dataset(self, item: h5py.Dataset, lazy: bool,
                         name: str, filepath: str) -> VariableData:
        """解析 h5py Dataset"""
        dtype_str = str(item.dtype)
        shape = list(item.shape)
        ndim = len(shape)
        size = int(np.prod(shape)) if shape else 0
        
        # 字符串类型
        if item.dtype.kind in ("O", "S", "U", "b"):
            data = item[()]
            if item.dtype.kind == "O":
                return self._parse_h5_object_array(item, data, lazy, name, filepath)
            return VariableData(
                name=name,
                var_type="string",
                value=self._decode_h5_string(data)
            )
        
        # 复合类型（结构体）
        if item.dtype.kind == "V":
            return self._parse_h5_struct(item, lazy, name, filepath)
        
        # 复数类型
        if np.issubdtype(item.dtype, np.complexfloating):
            return self._parse_h5_complex(item, lazy, name, filepath, shape, ndim, size, dtype_str)
        
        # 标量
        if ndim == 0:
            data = item[()]
            val = data.item()
            return self._parse_scalar(val, name)
        
        # 懒加载大数组
        if lazy and size > self.lazy_threshold:
            return VariableData(
                name=name,
                var_type="ndarray",
                dtype=dtype_str,
                shape=shape,
                ndim=ndim,
                size=size,
                lazy=True,
                filepath=filepath,
                dataset_path=item.name
            )
        
        # 普通数组
        data = item[()]
        data = np.asarray(data)
        values = self._sanitize_array(data)
        
        return VariableData(
            name=name,
            var_type="ndarray",
            dtype=dtype_str,
            shape=shape,
            ndim=ndim,
            size=size,
            values=values
        )
    
    def _parse_h5_object_array(self, item: h5py.Dataset, data: Any, lazy: bool,
                              name: str, filepath: str) -> VariableData:
        """解析 h5py Object 数组（Cell 数组）"""
        shape = list(item.shape)
        ndim = len(shape)
        size = int(np.prod(shape)) if shape else 0
        
        if lazy and size > self.lazy_threshold:
            return VariableData(
                name=name,
                var_type="cell",
                shape=shape,
                ndim=ndim,
                size=size,
                lazy=True,
                filepath=filepath,
                dataset_path=item.name
            )
        
        values = []
        for val in data.flat:
            if isinstance(val, np.ndarray):
                parsed = self._parse_variable(val, lazy)
                values.append(parsed.to_dict())
            elif isinstance(val, h5py.Reference):
                values.append({"type": "reference", "value": str(val)})
            elif isinstance(val, bytes):
                values.append({"type": "string", "value": val.decode("utf-8", errors="replace")})
            else:
                parsed = self._parse_scalar(val, name)
                values.append(parsed.to_dict())
        
        return VariableData(
            name=name,
            var_type="cell",
            shape=shape,
            ndim=ndim,
            size=size,
            values=values
        )
    
    def _parse_h5_struct(self, item: h5py.Dataset, lazy: bool,
                        name: str, filepath: str) -> VariableData:
        """解析 h5py 复合类型（结构体）"""
        fields = {}
        dtype = item.dtype
        
        if dtype.names:
            for field_name in dtype.names:
                try:
                    if item.ndim == 0:
                        field_data = item[field_name].item()
                        fields[field_name] = self._parse_variable(
                            field_data, lazy, name=f"{name}.{field_name}"
                        ).to_dict()
                    else:
                        fields[field_name] = self._parse_h5_item(
                            item[field_name], lazy, name=f"{name}.{field_name}", filepath=filepath
                        ).to_dict()
                except Exception as e:
                    logger.error(f"解析字段 {field_name} 失败：{e}")
                    fields[field_name] = {"type": "unknown", "value": "解析失败"}
        
        return VariableData(
            name=name,
            var_type="struct",
            fields=fields
        )
    
    def _parse_h5_complex(self, item: h5py.Dataset, lazy: bool, name: str,
                         filepath: str, shape: List[int], ndim: int,
                         size: int, dtype_str: str) -> VariableData:
        """解析 h5py 复数数据集"""
        if lazy and size > self.lazy_threshold:
            return VariableData(
                name=name,
                var_type="ndarray",
                dtype="complex",
                shape=shape,
                ndim=ndim,
                size=size,
                lazy=True,
                filepath=filepath,
                dataset_path=item.name
            )
        
        data = item[()]
        data = np.asarray(data)
        
        # 向量化清理
        real_mask = np.isfinite(data.real)
        imag_mask = np.isfinite(data.imag)
        
        real_clean = data.real.astype(object)
        imag_clean = data.imag.astype(object)
        real_clean[~real_mask] = None
        imag_clean[~imag_mask] = None
        
        return VariableData(
            name=name,
            var_type="ndarray",
            dtype="complex",
            shape=shape,
            ndim=ndim,
            size=size,
            real=real_clean.tolist(),
            imag=imag_clean.tolist()
        )
    
    def _sanitize_array(self, arr: np.ndarray) -> Any:
        """
        清理数组中的 NaN 和 Inf
        
        Args:
            arr: NumPy 数组
            
        Returns:
            清理后的列表
        """
        if arr.dtype.kind in ("i", "u", "b"):
            return arr.tolist()
        
        if arr.dtype.kind == "f":
            mask = np.isfinite(arr)
            if not mask.all():
                result = arr.astype(object)
                result[~mask] = None
                return result.tolist()
            return arr.tolist()
        
        return arr.tolist()
    
    def _sanitize_var_name(self, name: str) -> str:
        """
        清理变量名，替换非法字符
        
        Args:
            name: 原始变量名
            
        Returns:
            安全的变量名
        """
        if not name or not isinstance(name, str):
            return "unknown_var"
        
        name = name.strip()
        
        if VALID_VAR_NAME_RE.match(name):
            return name
        
        # 替换非法字符
        sanitized = re.sub(r'[^a-zA-Z0-9_]', '_', name)
        
        # 确保不以数字开头
        if not sanitized or sanitized[0].isdigit():
            sanitized = "var_" + sanitized
        
        return sanitized or "unknown_var"
    
    def _safe_decode(self, val: Any, default: str = "") -> str:
        """
        安全解码字符串
        
        Args:
            val: 值
            default: 默认值
            
        Returns:
            解码后的字符串
        """
        if isinstance(val, bytes):
            try:
                return val.decode("utf-8", errors="replace")
            except Exception:
                return default
        if isinstance(val, str):
            return val
        return str(val)
    
    def _decode_h5_string(self, data: Any) -> Any:
        """解码 h5py 字符串数据"""
        if isinstance(data, np.ndarray):
            if data.dtype.kind == "O":
                return [self._safe_decode(v) for v in data.flat]
            return data.tolist()
        return self._safe_decode(data)
    
    def _make_lazy_array(self, name: str, shape: List[int], ndim: int,
                        size: int, dtype_str: str) -> VariableData:
        """创建懒加载数组元数据"""
        return VariableData(
            name=name,
            var_type="ndarray",
            dtype=dtype_str,
            shape=shape,
            ndim=ndim,
            size=size,
            lazy=True
        )
