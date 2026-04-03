"""
JSON 序列化工具（性能优化版）：处理 NaN / Inf / -Inf
优化：向量化处理、减少递归深度、使用orjson加速
"""

import math
import json
import numpy as np

try:
    import orjson
    HAS_ORJSON = True
except ImportError:
    HAS_ORJSON = False


def sanitize(obj):
    """递归将 NaN / Inf 转为 None，使 json.dumps 输出合法 JSON"""
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, (np.floating,)):
        v = float(obj)
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, dict):
        return {k: sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [sanitize(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return sanitize(obj.tolist())
    return obj


def sanitize_fast(obj):
    """快速清理：利用mat_parser已清理的数据，减少重复处理"""
    if obj is None:
        return None
    if isinstance(obj, (int, bool, str)):
        return obj
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: sanitize_fast(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [sanitize_fast(v) for v in obj]
    return obj


def jsonify(data, use_fast: bool = True):
    """sanitize + json.dumps，返回合法 JSON 字符串"""
    if use_fast:
        cleaned = sanitize_fast(data)
    else:
        cleaned = sanitize(data)

    if HAS_ORJSON:
        return orjson.dumps(cleaned).decode("utf-8")
    return json.dumps(cleaned, ensure_ascii=False)


def jsonify_chunked(data, max_size: int = 5000000):
    """分块序列化：对大数组进行截断或采样"""
    if isinstance(data, dict):
        result = {}
        for key, value in data.items():
            if isinstance(value, dict) and value.get("type") == "ndarray":
                result[key] = _chunk_array(value, max_size)
            else:
                result[key] = value
        return jsonify(result)
    return jsonify(data)


def _chunk_array(arr_info: dict, max_size: int):
    """对大数组进行采样或截断"""
    if arr_info.get("lazy"):
        return arr_info

    size = arr_info.get("size", 0)
    if size <= max_size:
        return arr_info

    values = arr_info.get("values")
    if values is None:
        return arr_info

    if isinstance(values, list):
        step = max(1, len(values) // max_size)
        sampled = values[::step][:max_size]
        result = dict(arr_info)
        result["values"] = sampled
        result["sampled"] = True
        result["original_size"] = size
        return result

    return arr_info
