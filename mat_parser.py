"""
.mat 文件解析器（性能优化版）
支持 MATLAB v5 / v6 / v7 / v7.3 格式
优化：分块读取、增量解析、向量化NaN处理、内存管理
"""

import os
import gc
import re
import numpy as np
import h5py
import scipy.io
from typing import Optional

CHUNK_THRESHOLD = 1000000
MAX_VALUES_IN_MEMORY = 5000000
LAZY_LOAD_THRESHOLD = 10000000

VALID_VAR_NAME_RE = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')


def _sanitize_var_name(name: str) -> str:
    """清理变量名，替换非法字符"""
    if not name or not isinstance(name, str):
        return "unknown_var"
    name = name.strip()
    if VALID_VAR_NAME_RE.match(name):
        return name
    sanitized = re.sub(r'[^a-zA-Z0-9_]', '_', name)
    if not sanitized or sanitized[0].isdigit():
        sanitized = "var_" + sanitized
    return sanitized or "unknown_var"


def _safe_decode(val, default=""):
    """安全解码字符串，处理编码错误"""
    if isinstance(val, bytes):
        try:
            return val.decode("utf-8", errors="replace")
        except Exception:
            return default
    if isinstance(val, str):
        return val
    return str(val)


def load_mat_file(filepath: str, lazy: bool = True) -> dict:
    """加载 .mat 文件，自动检测版本并解析所有变量
    
    Args:
        filepath: 文件路径
        lazy: 是否启用懒加载（大文件仅解析元数据）
    """
    try:
        mat_data = scipy.io.loadmat(filepath, squeeze_me=True, struct_as_record=False)
        result = {}
        for key, value in mat_data.items():
            if key.startswith("__"):
                continue
            safe_key = _sanitize_var_name(key)
            try:
                result[safe_key] = _parse_variable(value, lazy=lazy)
            except Exception:
                result[safe_key] = {"type": "unknown", "value": "解析失败"}
        if result:
            return result
    except NotImplementedError:
        pass
    except Exception:
        pass

    return _load_h5py(filepath, lazy=lazy)


def _load_h5py(filepath: str, lazy: bool = True) -> dict:
    """用 h5py 读取 MATLAB v7.3 (HDF5) 文件"""
    result = {}
    try:
        with h5py.File(filepath, "r") as f:
            for key in f.keys():
                if key.startswith("#"):
                    continue
                safe_key = _sanitize_var_name(key)
                try:
                    result[safe_key] = _parse_h5_item(f[key], lazy=lazy)
                except Exception:
                    result[safe_key] = {"type": "unknown", "value": "解析失败"}
    except Exception:
        pass
    return result


def _parse_h5_item(item, lazy: bool = True):
    """递归解析 h5py 对象"""
    if isinstance(item, h5py.Group):
        fields = {}
        for sub_key in item.keys():
            if sub_key.startswith("#"):
                continue
            fields[sub_key] = _parse_h5_item(item[sub_key], lazy=lazy)
        return {"type": "struct", "fields": fields}

    if isinstance(item, h5py.Dataset):
        dtype_str = str(item.dtype)
        shape = list(item.shape)
        ndim = len(shape)
        size = int(np.prod(shape)) if shape else 0

        if item.dtype.kind in ("O", "S", "U", "b"):
            data = item[()]
            if item.dtype.kind == "O":
                return _parse_h5_object_array(item, data, lazy=lazy)
            return {"type": "string", "value": _decode_h5_string(data)}

        if item.dtype.kind == "V":
            return _parse_h5_struct(item, lazy=lazy)

        if np.issubdtype(item.dtype, np.complexfloating):
            if lazy and size > CHUNK_THRESHOLD:
                return _make_complex_lazy(item, shape, ndim, size, dtype_str)
            data = item[()]
            data = np.asarray(data)
            real_clean = _sanitize_array_fast(data.real)
            imag_clean = _sanitize_array_fast(data.imag)
            return {
                "type": "ndarray", "dtype": "complex",
                "shape": shape, "ndim": ndim, "size": size,
                "real": real_clean,
                "imag": imag_clean,
            }

        if ndim == 0:
            data = item[()]
            val = data.item()
            if isinstance(val, (np.integer,)):
                val = int(val)
            elif isinstance(val, (np.floating,)):
                val = float(val)
                if np.isnan(val) or np.isinf(val):
                    val = None
            elif isinstance(val, (np.bool_,)):
                val = bool(val)
            return {"type": "scalar", "dtype": dtype_str, "value": val}

        if lazy and size > CHUNK_THRESHOLD:
            return _make_lazy_meta(item, shape, ndim, size, dtype_str)

        data = item[()]
        data = np.asarray(data)
        values = _sanitize_array_fast(data)

        result = {
            "type": "ndarray", "dtype": dtype_str,
            "shape": shape, "ndim": ndim, "size": size,
        }

        if ndim <= 2:
            result["values"] = values
        else:
            result["slices"] = _slice_high_dim_fast(data)
            result["values"] = values

        return result

    return {"type": "unknown", "value": str(item)}


def _parse_h5_object_array(item, data, lazy: bool = True) -> dict:
    """解析h5py中的object数组（cell数组）"""
    shape = list(item.shape)
    ndim = len(shape)
    size = int(np.prod(shape)) if shape else 0

    if size > CHUNK_THRESHOLD:
        return {
            "type": "cell",
            "shape": shape,
            "ndim": ndim,
            "size": size,
            "lazy": True,
            "values": None,
        }

    values = []
    for val in data.flat:
        if isinstance(val, np.ndarray):
            values.append(_parse_variable(val, lazy=lazy))
        elif isinstance(val, h5py.Reference):
            values.append({"type": "reference", "value": str(val)})
        elif isinstance(val, bytes):
            values.append({"type": "string", "value": val.decode("utf-8", errors="replace")})
        else:
            values.append({"type": "scalar", "dtype": type(val).__name__, "value": val})

    if ndim == 1:
        return {"type": "cell", "value": values}
    else:
        return {"type": "cell", "shape": shape, "ndim": ndim, "size": size, "values": values}


def _parse_h5_struct(item, lazy: bool = True) -> dict:
    """解析h5py中的复合类型（MATLAB struct）"""
    fields = {}
    dtype = item.dtype
    if dtype.names:
        for name in dtype.names:
            try:
                if item.ndim == 0:
                    fields[name] = _parse_variable(item[name].item(), lazy=lazy)
                else:
                    fields[name] = _parse_h5_item(item[name], lazy=lazy)
            except Exception:
                fields[name] = {"type": "unknown", "value": "无法解析"}
    return {"type": "struct", "fields": fields}


def _make_lazy_meta(item, shape, ndim, size, dtype_str):
    """为大数组创建懒加载元数据（不读取实际数据）"""
    return {
        "type": "ndarray",
        "dtype": dtype_str,
        "shape": shape,
        "ndim": ndim,
        "size": size,
        "lazy": True,
        "filepath": item.file.filename,
        "dataset_path": item.name,
        "values": None,
    }


def _make_complex_lazy(item, shape, ndim, size, dtype_str):
    """为复数大数组创建懒加载元数据"""
    return {
        "type": "ndarray",
        "dtype": "complex",
        "shape": shape,
        "ndim": ndim,
        "size": size,
        "lazy": True,
        "filepath": item.file.filename,
        "dataset_path": item.name,
        "real": None,
        "imag": None,
    }


def load_variable_data(filepath: str, var_name: str, dataset_path: str = None):
    """按需加载单个变量的数据（用于懒加载场景）"""
    if dataset_path is None:
        dataset_path = var_name

    try:
        mat_data = scipy.io.loadmat(filepath, squeeze_me=True, struct_as_record=False)
        if var_name in mat_data:
            return _parse_variable(mat_data[var_name], lazy=False)
    except NotImplementedError:
        pass

    with h5py.File(filepath, "r") as f:
        if dataset_path in f:
            return _parse_h5_item(f[dataset_path], lazy=False)

    return None


def _sanitize_array_fast(arr: np.ndarray):
    """向量化快速清理NaN/Inf，避免Python循环"""
    if arr.dtype.kind in ("i", "u", "b"):
        return arr.tolist()

    if arr.dtype.kind == "f":
        mask = np.isfinite(arr)
        if not mask.all():
            result = arr.astype(object)
            result[~mask] = None
            return result.tolist()
        return arr.tolist()

    if arr.dtype.kind == "c":
        real_part = arr.real
        imag_part = arr.imag
        real_mask = np.isfinite(real_part)
        imag_mask = np.isfinite(imag_part)
        real_clean = real_part.astype(object)
        imag_clean = imag_part.astype(object)
        real_clean[~real_mask] = None
        imag_clean[~imag_mask] = None
        return {
            "real": real_clean.tolist(),
            "imag": imag_clean.tolist(),
        }

    return arr.tolist()


def _decode_h5_string(data):
    """解码 h5py 读取的字符串数据，处理编码错误"""
    if isinstance(data, np.ndarray):
        if data.dtype.kind == "O":
            if data.ndim == 0:
                return _safe_decode(data.item())
            return "\n".join(_safe_decode(v) for v in data.flat)
        if data.dtype.kind == "S":
            if data.ndim == 0:
                return _safe_decode(data.item())
            return "\n".join(
                _safe_decode(v) if isinstance(v, bytes) else str(v)
                for v in data.flat
            )
        if data.dtype.kind == "U":
            return str(data)
    if isinstance(data, bytes):
        return _safe_decode(data)
    return str(data)


# ==================== scipy 解析 ====================

def _parse_variable(value, lazy: bool = True):
    if isinstance(value, (np.integer,)):
        return {"type": "scalar", "dtype": "int", "value": int(value)}
    if isinstance(value, (np.floating,)):
        v = float(value)
        return {"type": "scalar", "dtype": "float", "value": v if not (np.isnan(v) or np.isinf(v)) else None}
    if isinstance(value, (np.bool_,)):
        return {"type": "scalar", "dtype": "bool", "value": bool(value)}
    if isinstance(value, (int, float, bool, str)):
        if isinstance(value, float) and (np.isnan(value) or np.isinf(value)):
            return {"type": "scalar", "dtype": "float", "value": None}
        return {"type": "scalar", "dtype": type(value).__name__, "value": value}
    if isinstance(value, (np.complexfloating, complex)):
        return {
            "type": "scalar", "dtype": "complex",
            "value": {"real": float(value.real), "imag": float(value.imag)},
        }
    if isinstance(value, np.ndarray) and value.dtype.kind == "U":
        return {"type": "string", "value": str(value)}
    if isinstance(value, np.ndarray) and value.dtype.kind == "O":
        return _parse_object_array(value, lazy=lazy)
    if hasattr(value, "_fieldnames"):
        fields = {}
        for fname in value._fieldnames:
            fields[fname] = _parse_variable(getattr(value, fname), lazy=lazy)
        return {"type": "struct", "fields": fields}
    if isinstance(value, np.ndarray):
        return _parse_ndarray(value, lazy=lazy)
    if isinstance(value, (list, tuple)):
        return {"type": "array", "value": [_parse_variable(v, lazy=lazy) for v in value]}
    return {"type": "unknown", "value": str(value)}


def _parse_object_array(arr: np.ndarray, lazy: bool = True) -> dict:
    """解析MATLAB cell数组（object dtype）"""
    shape = list(arr.shape)
    ndim = arr.ndim
    size = arr.size

    if ndim == 0:
        item = arr.item()
        return {"type": "cell", "value": [_parse_variable(item, lazy=lazy)]}

    if size > CHUNK_THRESHOLD:
        return {
            "type": "cell",
            "shape": shape,
            "ndim": ndim,
            "size": size,
            "lazy": True,
            "values": None,
        }

    values = []
    for item in arr.flat:
        values.append(_parse_variable(item, lazy=lazy))

    if ndim == 1:
        return {"type": "cell", "value": values}
    else:
        rows = []
        for i in range(shape[0]):
            row = values[i * shape[1]:(i + 1) * shape[1]] if ndim == 2 else values[i]
            rows.append(row)
        return {"type": "cell", "shape": shape, "ndim": ndim, "size": size, "values": values}


def _parse_ndarray(arr: np.ndarray, lazy: bool = True) -> dict:
    shape = list(arr.shape)
    ndim = arr.ndim
    size = arr.size

    if arr.dtype.kind == "C":
        if lazy and size > CHUNK_THRESHOLD:
            return {
                "type": "ndarray", "dtype": "complex",
                "shape": shape, "ndim": ndim, "size": size,
                "lazy": True,
                "real": None,
                "imag": None,
            }
        real_clean = _sanitize_array_fast(arr.real)
        imag_clean = _sanitize_array_fast(arr.imag)
        return {
            "type": "ndarray", "dtype": "complex",
            "shape": shape, "ndim": ndim, "size": size,
            "real": real_clean,
            "imag": imag_clean,
        }

    if ndim == 0:
        v = arr.item()
        if isinstance(v, (np.floating,)):
            v = float(v)
            if np.isnan(v) or np.isinf(v):
                v = None
        elif isinstance(v, (np.integer,)):
            v = int(v)
        elif isinstance(v, (np.bool_,)):
            v = bool(v)
        return {"type": "scalar", "dtype": str(arr.dtype), "value": v}

    if lazy and size > CHUNK_THRESHOLD:
        return {
            "type": "ndarray",
            "dtype": str(arr.dtype),
            "shape": shape,
            "ndim": ndim,
            "size": size,
            "lazy": True,
            "values": None,
        }

    values = _sanitize_array_fast(arr)

    result = {
        "type": "ndarray", "dtype": str(arr.dtype),
        "shape": shape, "ndim": ndim, "size": size,
    }
    if ndim <= 2:
        result["values"] = values
    else:
        result["slices"] = _slice_high_dim_fast(arr)
        result["values"] = values
    return result


def _slice_high_dim_fast(arr: np.ndarray) -> list:
    """优化的高维数组切片"""
    slices = []
    if arr.ndim <= 2:
        return slices

    num_slices = arr.shape[2]
    max_slices = 100

    step = max(1, num_slices // max_slices)
    for idx in np.ndindex(*arr.shape[2:]):
        if idx[0] % step != 0 and len(slices) >= max_slices:
            continue
        slice_data = _sanitize_array_fast(arr[(slice(None), slice(None)) + idx])
        slices.append({"indices": list(idx), "data": slice_data})
        if len(slices) >= max_slices:
            break
    return slices


def get_summary(mat_data: dict) -> str:
    lines = []
    for name, info in mat_data.items():
        dtype = info.get("type", "unknown")
        if dtype == "ndarray":
            lines.append(f"**{name}**: ndarray {info.get('shape', [])} ({info.get('dtype', '')})")
        elif dtype == "scalar":
            lines.append(f"**{name}**: scalar = {info.get('value', '')}")
        elif dtype == "struct":
            fields = list(info.get("fields", {}).keys())
            lines.append(f"**{name}**: struct with fields {fields}")
        elif dtype == "string":
            val = info.get("value", "")
            preview = val[:80] + "..." if len(val) > 80 else val
            lines.append(f'**{name}**: string = "{preview}"')
        else:
            lines.append(f"**{name}**: {dtype}")
    return "\n".join(lines)


def get_file_info(filepath: str) -> dict:
    stat = os.stat(filepath)
    version = "v7.3 (HDF5)"
    try:
        mat = scipy.io.loadmat(filepath, squeeze_me=True, struct_as_record=False)
        var_names = [k for k in mat.keys() if not k.startswith("__")]
    except NotImplementedError:
        with h5py.File(filepath, "r") as f:
            var_names = [k for k in f.keys() if not k.startswith("#")]
    return {
        "filename": os.path.basename(filepath),
        "size_bytes": stat.st_size,
        "size_human": _human_size(stat.st_size),
        "num_variables": len(var_names),
        "variable_names": var_names,
        "mat_version": version,
    }


def _human_size(nbytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if nbytes < 1024:
            return f"{nbytes:.1f} {unit}"
        nbytes /= 1024
    return f"{nbytes:.1f} TB"


def clear_memory():
    """强制垃圾回收，释放内存"""
    gc.collect()
