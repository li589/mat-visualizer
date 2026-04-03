"""
MAT 文件可视化工具 - Flask 后端（性能优化版）
启动：python app.py
访问：http://127.0.0.1:5000
优化：LRU 缓存、懒加载、内存管理、进度反馈、分页 API
安全：输入验证、XSS 防护、路径遍历防护、速率限制
"""

import os
import io
import csv
import time
import tempfile
import logging
import numpy as np
from collections import OrderedDict
from flask import Flask, render_template, request, jsonify, Response, send_file
from werkzeug.utils import secure_filename
from mat_parser import load_mat_file, get_file_info, get_summary, load_variable_data, clear_memory
from file_loader import FileLoader, parse_source
from security import (
    sanitize_string, validate_var_name, validate_filename,
    safe_path_join, validate_json_request, rate_limit,
    validate_file_size, sanitize_url, escape_html
)

try:
    import openpyxl
    HAS_OPENPYXL = True
except ImportError:
    HAS_OPENPYXL = False

# 配置日志
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024
app.config["SECRET_KEY"] = os.urandom(24)  # 用于会话安全

UPLOAD_DIR = os.path.join(tempfile.gettempdir(), "mat_uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

file_loader = FileLoader()


class LRUCache:
    """LRU缓存：限制内存占用，自动淘汰旧数据"""

    def __init__(self, max_size: int = 3, max_memory_mb: int = 500):
        self.cache = OrderedDict()
        self.max_size = max_size
        self.max_memory_mb = max_memory_mb

    def get(self, key):
        if key in self.cache:
            self.cache.move_to_end(key)
            return self.cache[key]
        return None

    def put(self, key, value):
        if key in self.cache:
            self.cache.move_to_end(key)
        self.cache[key] = value
        while len(self.cache) > self.max_size:
            self.cache.popitem(last=False)

    def clear(self):
        self.cache.clear()
        clear_memory()

    def get_current(self):
        if self.cache:
            last_key = next(reversed(self.cache))
            return self.cache[last_key]
        return None


_cache = LRUCache(max_size=3, max_memory_mb=500)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/upload", methods=["POST"])
@rate_limit(max_requests=20, window_seconds=60)  # 每分钟最多 20 次上传
def upload():
    """上传 .mat 文件并解析（仅解析元数据，不加载大数组）"""
    if "file" not in request.files:
        return jsonify({"error": "未选择文件"}), 400

    file = request.files["file"]
    original_filename = file.filename
    
    # 验证文件名
    if not original_filename or not validate_filename(original_filename):
        logger.warning(f"无效的文件名：{original_filename}")
        return jsonify({"error": "无效的文件名"}), 400
    
    if not original_filename.endswith(".mat"):
        return jsonify({"error": "仅支持 .mat 文件"}), 400
    
    # 验证文件大小
    if not validate_file_size(file, max_size_mb=500):
        return jsonify({"error": "文件大小超过限制（500MB）"}), 400

    # 安全地处理文件名
    filename = secure_filename(original_filename)
    filepath = safe_path_join(UPLOAD_DIR, filename)
    
    if not filepath:
        logger.error("路径遍历攻击检测")
        return jsonify({"error": "无效的文件路径"}), 400
    
    file.save(filepath)

    try:
        start_time = time.time()
        file_info = get_file_info(filepath)
        file_info["filepath"] = filepath
        file_info["source"] = filepath
        mat_data = load_mat_file(filepath, lazy=True)

        if not mat_data:
            if os.path.exists(filepath):
                os.remove(filepath)
            return jsonify({
                "success": True,
                "info": file_info,
                "summary": "该文件不包含可解析的变量",
                "variables": [],
                "var_overview": {},
                "parse_time": 0,
                "warning": "文件中没有可显示的变量",
            }), 200

        summary = get_summary(mat_data)
        parse_time = time.time() - start_time

        _cache.put(filename, {
            "filepath": filepath,
            "filename": filename,
            "info": file_info,
            "data": mat_data,
            "summary": summary,
            "parse_time": round(parse_time, 2),
        })

        var_overview = {}
        for name, info in mat_data.items():
            var_overview[name] = {
                "type": info.get("type"),
                "dtype": info.get("dtype", ""),
                "shape": info.get("shape", []),
                "size": info.get("size", 0),
                "lazy": info.get("lazy", False),
            }

        return jsonify({
            "success": True,
            "info": file_info,
            "summary": summary,
            "variables": list(mat_data.keys()),
            "var_overview": var_overview,
            "parse_time": round(parse_time, 2),
        })
    except Exception as e:
        logger.error(f"上传处理失败：{e}", exc_info=True)
        return jsonify({"error": f"解析失败：{escape_html(str(e))}"}), 500


@app.route("/load_remote", methods=["POST"])
@validate_json_request(['source'])
@rate_limit(max_requests=10, window_seconds=60)  # 每分钟最多 10 次远程加载
def load_remote():
    """加载远程文件（HTTP/HTTPS/SSH）"""
    req = request.get_json() or {}
    source = req.get("source", "").strip()

    # 验证和清理 URL
    if source.startswith(("http://", "https://")):
        sanitized_source = sanitize_url(source)
        if not sanitized_source:
            logger.warning(f"无效的 URL: {source}")
            return jsonify({"error": "无效的 URL 地址"}), 400
        source = sanitized_source

    if not source:
        return jsonify({"error": "请提供数据源地址"}), 400

    source_info = parse_source(source)
    source_type = source_info["type"]

    if source_type not in ["http", "https", "ssh"]:
        return jsonify({"error": "仅支持 HTTP/HTTPS/SSH 远程文件"}), 400

    try:
        start_time = time.time()
        filepath, is_temp = file_loader.load(
            source,
            password=sanitize_string(req.get("password", ""), max_length=100),
            key_filename=sanitize_string(req.get("key_filename", ""), max_length=255),
            timeout=min(int(req.get("timeout", 60)), 300)  # 最大 5 分钟
        )

        file_info = get_file_info(filepath)
        file_info["filepath"] = filepath
        file_info["source"] = source
        file_info["source_type"] = source_type

        mat_data = load_mat_file(filepath, lazy=True)

        if not mat_data:
            if is_temp and os.path.exists(filepath):
                os.remove(filepath)
            return jsonify({
                "success": True,
                "info": file_info,
                "summary": "该文件不包含可解析的变量",
                "variables": [],
                "var_overview": {},
                "parse_time": 0,
                "warning": "文件中没有可显示的变量",
            }), 200

        summary = get_summary(mat_data)
        parse_time = time.time() - start_time

        filename = file_info["filename"]
        _cache.put(filename, {
            "filepath": filepath,
            "filename": filename,
            "info": file_info,
            "data": mat_data,
            "summary": summary,
            "parse_time": round(parse_time, 2),
            "is_temp": is_temp,
        })

        var_overview = {}
        for name, info in mat_data.items():
            var_overview[name] = {
                "type": info.get("type"),
                "dtype": info.get("dtype", ""),
                "shape": info.get("shape", []),
                "size": info.get("size", 0),
                "lazy": info.get("lazy", False),
            }

        return jsonify({
            "success": True,
            "info": file_info,
            "summary": summary,
            "variables": list(mat_data.keys()),
            "var_overview": var_overview,
            "parse_time": round(parse_time, 2),
        })
    except Exception as e:
        logger.error(f"远程加载失败：{e}", exc_info=True)
        return jsonify({"error": f"加载失败：{escape_html(str(e))}"}), 500


@app.route("/variable/<name>")
@rate_limit(max_requests=100, window_seconds=60)  # 每分钟最多 100 次查询
def get_variable(name):
    """获取单个变量的详细数据（支持懒加载）"""
    # 验证变量名
    if not validate_var_name(name):
        logger.warning(f"无效的变量名：{name}")
        return jsonify({"error": "无效的变量名"}), 400
    
    cache_data = _cache.get_current()
    if cache_data is None:
        return jsonify({"error": "请先上传文件"}), 400

    data = cache_data["data"]
    if name not in data:
        return jsonify({"error": f"变量 '{escape_html(name)}' 不存在"}), 404

    var_info = data[name]

    if var_info.get("lazy"):
        start_time = time.time()
        full_data = load_variable_data(
            cache_data["filepath"],
            name,
            var_info.get("dataset_path")
        )
        load_time = time.time() - start_time
        if full_data:
            data[name] = full_data
            var_info = full_data
            var_info["load_time"] = round(load_time, 2)

    return jsonify({"name": name, "data": var_info})


@app.route("/variable/<name>/slice")
@rate_limit(max_requests=100, window_seconds=60)
def get_variable_slice(name):
    """获取数组切片（分页加载）"""
    # 验证变量名
    if not validate_var_name(name):
        logger.warning(f"无效的变量名：{name}")
        return jsonify({"error": "无效的变量名"}), 400
    
    cache_data = _cache.get_current()
    if cache_data is None:
        return jsonify({"error": "请先上传文件"}), 400

    data = cache_data["data"]
    if name not in data:
        return jsonify({"error": f"变量 '{escape_html(name)}' 不存在"}), 404

    var_info = data[name]
    if var_info.get("lazy"):
        full_data = load_variable_data(
            cache_data["filepath"],
            name,
            var_info.get("dataset_path")
        )
        if full_data:
            data[name] = full_data
            var_info = full_data

    values = var_info.get("values")
    if values is None:
        return jsonify({"error": "数据不可用"}), 404

    offset = request.args.get("offset", 0, type=int)
    limit = request.args.get("limit", 1000, type=int)
    limit = min(limit, 5000)

    if isinstance(values, list):
        sliced = values[offset:offset + limit]
        return jsonify({
            "name": name,
            "offset": offset,
            "limit": limit,
            "total": len(values),
            "data": sliced,
        })

    return jsonify({"error": "不支持的数据类型"}), 400


@app.route("/variables")
def get_all_variables():
    """获取所有变量的概览"""
    cache_data = _cache.get_current()
    if cache_data is None:
        return jsonify({"error": "请先上传文件"}), 400

    data = cache_data["data"]
    overview = {}
    for name, info in data.items():
        overview[name] = {
            "type": info.get("type"),
            "dtype": info.get("dtype", ""),
            "shape": info.get("shape", []),
            "size": info.get("size", 0),
            "lazy": info.get("lazy", False),
        }
    return jsonify(overview)


@app.route("/clear", methods=["POST"])
def clear_cache():
    """清除缓存，释放内存"""
    _cache.clear()
    return jsonify({"success": True, "message": "缓存已清除"})


@app.route("/stats")
def get_stats():
    """获取当前缓存统计信息"""
    cache_data = _cache.get_current()
    if cache_data is None:
        return jsonify({"active": False})

    return jsonify({
        "active": True,
        "filename": cache_data.get("filename"),
        "parse_time": cache_data.get("parse_time"),
        "variables": len(cache_data.get("data", {})),
    })


def _resolve_header(template, row_num, col_num, var_name):
    """解析表头模板，替换占位符"""
    if not template:
        return None
    result = template
    result = result.replace("%Row_num", str(row_num))
    result = result.replace("%Col_num", str(col_num))
    result = result.replace("%VarName", var_name)
    return result


def _get_variable_values(var_info):
    """获取变量的二维值列表"""
    if var_info.get("lazy"):
        return None
    values = var_info.get("values")
    if values is None:
        return None
    ndim = var_info.get("ndim", 1)
    if ndim == 1:
        return [[v] for v in values]
    if ndim == 2:
        return values
    return None


@app.route("/export/<name>", methods=["POST"])
@validate_json_request([])  # 需要 JSON 但不强制要求字段
@rate_limit(max_requests=30, window_seconds=60)  # 每分钟最多 30 次导出
def export_variable(name):
    """导出变量数据为 CSV/Excel/TXT/NPY 格式"""
    # 验证变量名
    if not validate_var_name(name):
        logger.warning(f"无效的变量名：{name}")
        return jsonify({"error": "无效的变量名"}), 400
    
    cache_data = _cache.get_current()
    if cache_data is None:
        return jsonify({"error": "请先上传文件"}), 400

    data = cache_data["data"]
    if name not in data:
        return jsonify({"error": f"变量 '{escape_html(name)}' 不存在"}), 404

    var_info = data[name]
    if var_info.get("lazy"):
        full_data = load_variable_data(
            cache_data["filepath"],
            name,
            var_info.get("dataset_path")
        )
        if full_data:
            data[name] = full_data
            var_info = full_data
        else:
            return jsonify({"error": "数据加载失败"}), 500

    values = _get_variable_values(var_info)
    if values is None:
        return jsonify({"error": "仅支持导出 1D/2D 数组数据"}), 400

    req = request.get_json() or {}
    fmt = sanitize_string(req.get("format", "csv"), max_length=10).lower()
    if fmt not in ["csv", "xlsx", "txt", "npy"]:
        return jsonify({"error": "不支持的导出格式"}), 400
    
    header_template = req.get("header", None)
    if header_template:
        header_template = sanitize_string(header_template, max_length=500)
    
    row_index_col = bool(req.get("row_index", False))
    trim_nulls = bool(req.get("trim_nulls", False))
    
    # 限制数值范围，防止 DoS 攻击
    try:
        row_start = max(0, min(int(req.get("row_start", 0)), 1000000))
        row_end = req.get("row_end", None)
        if row_end is not None:
            row_end = max(0, min(int(row_end), 1000000))
        
        col_start = max(0, min(int(req.get("col_start", 0)), 1000000))
        col_end = req.get("col_end", None)
        if col_end is not None:
            col_end = max(0, min(int(col_end), 1000000))
    except (ValueError, TypeError):
        return jsonify({"error": "无效的参数值"}), 400

    if row_end is None:
        row_end = len(values)
    if col_end is None:
        col_end = len(values[0]) if values else 0

    row_start = max(0, min(row_start, len(values)))
    row_end = max(row_start, min(row_end, len(values)))
    col_start = max(0, min(col_start, len(values[0]) if values else 0))
    col_end = max(col_start, min(col_end, len(values[0]) if values else 0))

    sliced_values = [row[col_start:col_end] for row in values[row_start:row_end]]

    if trim_nulls and sliced_values:
        def is_null(v):
            if v is None:
                return True
            if isinstance(v, float) and (np.isnan(v) or np.isinf(v)):
                return True
            if isinstance(v, str) and v.strip() == "":
                return True
            return False

        sliced_values = [
            [None if is_null(v) else v for v in row]
            for row in sliced_values
        ]

        sliced_values = [
            row for row in sliced_values
            if any(v is not None for v in row)
        ]

        if sliced_values:
            num_cols_temp = len(sliced_values[0])
            cols_to_keep = []
            for c in range(num_cols_temp):
                has_valid = any(row[c] is not None for row in sliced_values)
                if has_valid:
                    cols_to_keep.append(c)

            if cols_to_keep:
                sliced_values = [
                    [row[c] for c in cols_to_keep]
                    for row in sliced_values
                ]

    if not sliced_values:
        return jsonify({"error": "导出结果为空"}), 400

    num_rows = len(sliced_values)
    num_cols = len(sliced_values[0]) if sliced_values else 0

    if fmt == "npy":
        arr = np.array(sliced_values, dtype=np.float64)
        buf = io.BytesIO()
        np.save(buf, arr)
        buf.seek(0)
        return send_file(buf, mimetype="application/octet-stream",
                        as_attachment=True, download_name=f"{name}.npy")

    if fmt == "mat":
        import scipy.io
        arr = np.array(sliced_values, dtype=np.float64)
        buf = io.BytesIO()
        scipy.io.savemat(buf, {name: arr}, format="5", do_compression=True)
        buf.seek(0)
        return send_file(buf, mimetype="application/octet-stream",
                        as_attachment=True, download_name=f"{name}.mat")

    if fmt == "txt":
        buf = io.StringIO()
        if header_template:
            headers = []
            if row_index_col:
                headers.append(_resolve_header(header_template, 0, 0, name) or "Index")
            for c in range(col_start, col_end):
                h = _resolve_header(header_template, 0, c, name)
                headers.append(h or f"Col_{c}")
            buf.write("\t".join(headers) + "\n")
        for r_idx, row in enumerate(sliced_values):
            line_parts = []
            if row_index_col:
                actual_row = row_start + r_idx
                line_parts.append(_resolve_header(header_template, actual_row, 0, name) or str(actual_row))
            for v in row:
                line_parts.append(format_export_val(v))
            buf.write("\t".join(line_parts) + "\n")
        buf.seek(0)
        content = buf.getvalue()
        return Response(content, mimetype="text/plain",
                       headers={"Content-Disposition": f"attachment; filename={name}.txt"})

    if fmt == "xlsx":
        if not HAS_OPENPYXL:
            return jsonify({"error": "请安装openpyxl: pip install openpyxl"}), 500
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = name[:31]
        if header_template:
            headers = []
            if row_index_col:
                headers.append(_resolve_header(header_template, 0, 0, name) or "Index")
            for c in range(col_start, col_end):
                h = _resolve_header(header_template, 0, c, name)
                headers.append(h or f"Col_{c}")
            ws.append(headers)
        for r_idx, row in enumerate(sliced_values):
            actual_row = row_start + r_idx
            row_data = []
            if row_index_col:
                row_data.append(actual_row)
            for v in row:
                row_data.append(export_val(v))
            ws.append(row_data)
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        return send_file(buf, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        as_attachment=True, download_name=f"{name}.xlsx")

    buf = io.StringIO()
    writer = csv.writer(buf, quoting=csv.QUOTE_MINIMAL)
    if header_template:
        headers = []
        if row_index_col:
            headers.append(_resolve_header(header_template, 0, 0, name) or "Index")
        for c in range(col_start, col_end):
            h = _resolve_header(header_template, 0, c, name)
            headers.append(h or f"Col_{c}")
        writer.writerow(headers)
    for r_idx, row in enumerate(sliced_values):
        actual_row = row_start + r_idx
        csv_row = []
        if row_index_col:
            csv_row.append(actual_row)
        for v in row:
            csv_row.append(export_val(v))
        writer.writerow(csv_row)
    buf.seek(0)
    content = buf.getvalue()
    return Response(content, mimetype="text/csv",
                   headers={"Content-Disposition": f"attachment; filename={name}.csv"})


def format_export_val(v):
    """格式化导出值"""
    if v is None:
        return ""
    if isinstance(v, float):
        if np.isnan(v) or np.isinf(v):
            return ""
        return f"{v:.8g}"
    if isinstance(v, str):
        return v
    return str(v)


def export_val(v):
    """导出值（用于Excel/CSV）"""
    if v is None:
        return ""
    if isinstance(v, float):
        if np.isnan(v) or np.isinf(v):
            return ""
        return v
    if isinstance(v, str):
        return v
    return v


if __name__ == "__main__":
    app.run(debug=True, port=5000, threaded=True)
