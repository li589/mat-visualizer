"""
MAT 文件可视化工具 - Flask 应用主入口（重构版 v2.0）

架构说明:
- 服务层：services/ 提供业务逻辑
- 核心层：core/ 提供基础功能（缓存、解析、导出）
- 安全层：security.py 提供安全验证
- 工具层：file_loader.py 提供文件加载

启动方式:
    python app.py

访问地址:
    http://127.0.0.1:5000
"""

import os
import time
import logging
from flask import Flask, render_template, request, jsonify, send_file
from werkzeug.utils import secure_filename

from core import Config
from services import FileService, DataService
from security import (
    validate_filename, validate_var_name, validate_file_size,
    sanitize_url, escape_html, rate_limit, validate_json_request
)
from file_loader import FileLoader, parse_source

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 初始化 Flask 应用
app = Flask(__name__, template_folder="frontend/html", static_folder="frontend", static_url_path="")
Config.init_app(app)

# 初始化服务
file_service = FileService()
data_service = DataService()
file_loader = FileLoader()


def format_size_human(file_size: int) -> str:
    if file_size < 1024:
        return f"{file_size} B"
    if file_size < 1024 * 1024:
        return f"{file_size / 1024:.2f} KB"
    if file_size < 1024 * 1024 * 1024:
        return f"{file_size / (1024 * 1024):.2f} MB"
    return f"{file_size / (1024 * 1024 * 1024):.2f} GB"


def build_var_overview(mat_data):
    var_overview = {}
    for name, var in mat_data.items():
        var_overview[name] = {
            "type": var.var_type,
            "dtype": var.dtype,
            "shape": var.shape,
            "size": var.size,
            "lazy": var.lazy,
        }
    return var_overview


# ==================== 路由定义 ====================

@app.route("/")
def index():
    """渲染主页"""
    return render_template("index.html")


@app.route("/upload", methods=["POST"])
@rate_limit(max_requests=Config.RATE_LIMIT_UPLOAD, window_seconds=60)
def upload():
    """
    上传 MAT 文件
    
    Returns:
        JSON 响应，包含文件信息和变量列表
    """
    if "file" not in request.files:
        return jsonify({"error": "未选择文件"}), 400

    file = request.files["file"]
    original_filename = file.filename

    # 验证文件名
    if not validate_filename(original_filename):
        logger.warning(f"无效的文件名：{original_filename}")
        return jsonify({"error": "无效的文件名"}), 400

    if not original_filename.endswith(".mat"):
        return jsonify({"error": "仅支持 .mat 文件"}), 400

    # 验证文件大小
    if not validate_file_size(file, max_size_mb=Config.MAX_CONTENT_LENGTH_MB):
        return jsonify({"error": f"文件大小超过限制（{Config.MAX_CONTENT_LENGTH_MB}MB）"}), 400

    try:
        # 保存文件
        filename = secure_filename(original_filename)
        filepath, _ = file_service.save_uploaded_file(file, filename)

        # 获取文件大小
        file_size = os.path.getsize(filepath)
        size_human = format_size_human(file_size)

        # 检测 MAT 文件版本
        from core.parser import MATParser
        mat_version = MATParser.detect_mat_version(filepath)

        # 加载和解析文件
        start_time = time.time()
        mat_data = data_service.load_file(filepath, lazy=True)

        if not mat_data:
            logger.warning(f"文件未解析到变量：{filename}")
            return jsonify({
                "success": True,
                "info": {
                    "filename": filename,
                    "filepath": filepath,
                    "size_human": size_human,
                    "mat_version": mat_version,
                    "num_variables": 0,
                    "variable_names": [],
                },
                "summary": "该文件不包含可解析的变量",
                "variables": [],
                "var_overview": {},
                "parse_time": 0,
            }), 200

        # 构建响应
        parse_time = time.time() - start_time
        var_overview = build_var_overview(mat_data)

        logger.info(f"文件上传成功：{filename}, 变量数：{len(mat_data)}, 耗时：{parse_time:.2f}s")

        return jsonify({
            "success": True,
            "info": {
                "filename": filename,
                "filepath": filepath,
                "size_human": size_human,
                "mat_version": mat_version,
                "num_variables": len(mat_data),
                "variable_names": list(mat_data.keys()),
            },
            "summary": f"共 {len(mat_data)} 个变量",
            "variables": list(mat_data.keys()),
            "var_overview": var_overview,
            "parse_time": round(parse_time, 2),
        })

    except ValueError as e:
        logger.error(f"上传验证失败：{e}")
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error(f"上传处理失败：{e}", exc_info=True)
        return jsonify({"error": f"解析失败：{escape_html(str(e))}"}), 500


@app.route("/load_remote", methods=["POST"])
@validate_json_request(['source'])
@rate_limit(max_requests=Config.RATE_LIMIT_REMOTE, window_seconds=60)
def load_remote():
    """
    加载远程文件（HTTP/HTTPS/SSH）
    
    Returns:
        JSON 响应，包含文件信息和变量列表
    """
    req = request.get_json() or {}
    source = req.get("source", "").strip()
    password = req.get("password")

    # 验证 URL
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
        # 加载远程文件
        local_path, _ = file_loader.load(source, password=password)
        filename = os.path.basename(local_path)
        file_size = os.path.getsize(local_path)
        size_human = format_size_human(file_size)
        from core.parser import MATParser
        mat_version = MATParser.detect_mat_version(local_path)

        # 解析文件
        mat_data = data_service.load_file(local_path, lazy=True)

        if not mat_data:
            return jsonify({
                "success": True,
                "info": {
                    "filename": filename,
                    "source": source,
                    "filepath": local_path,
                    "size_human": size_human,
                    "mat_version": mat_version,
                    "num_variables": 0,
                    "variable_names": [],
                },
                "summary": "该文件不包含可解析的变量",
                "variables": [],
                "var_overview": {},
                "parse_time": 0,
            }), 200

        parse_time = time.time() - start_time
        var_overview = build_var_overview(mat_data)

        logger.info(f"远程文件加载成功：{source}, 变量数：{len(mat_data)}")

        return jsonify({
            "success": True,
            "info": {
                "filename": filename,
                "source": source,
                "filepath": local_path,
                "size_human": size_human,
                "mat_version": mat_version,
                "num_variables": len(mat_data),
                "variable_names": list(mat_data.keys()),
            },
            "summary": f"共 {len(mat_data)} 个变量",
            "variables": list(mat_data.keys()),
            "var_overview": var_overview,
            "parse_time": round(parse_time, 2),
        })

    except Exception as e:
        logger.error(f"远程加载失败：{e}", exc_info=True)
        return jsonify({"error": f"加载失败：{escape_html(str(e))}"}), 500


@app.route("/variable/<path:name>")
@rate_limit(max_requests=Config.RATE_LIMIT_VARIABLE, window_seconds=60)
def get_variable(name):
    """
    获取变量数据
    
    Args:
        name: 变量名（URL 编码）
    
    Returns:
        JSON 响应，包含变量详细数据
    """
    if not validate_var_name(name):
        return jsonify({"error": "无效的变量名"}), 400

    # 获取当前缓存的文件数据
    start_time = time.time()
    file_data = data_service.get_current_file()

    if not file_data:
        return jsonify({"error": "请先上传文件"}), 400

    var_data = file_data.get(name)

    if not var_data:
        return jsonify({"error": f"变量不存在：{name}"}), 404

    load_time = time.time() - start_time
    result = var_data.to_dict()
    result["load_time"] = round(load_time, 3)
    
    return jsonify(result)


@app.route("/variable/<path:name>/slice")
@rate_limit(max_requests=Config.RATE_LIMIT_VARIABLE, window_seconds=60)
def get_variable_slice(name):
    """
    获取数组切片数据（用于分页显示）
    
    Args:
        name: 变量名
    
    Returns:
        JSON 响应，包含切片数据
    """
    if not validate_var_name(name):
        return jsonify({"error": "无效的变量名"}), 400

    # 获取分页参数
    row_start = max(0, min(int(request.args.get("row_start", 0)), 1000000))
    row_end = max(0, min(int(request.args.get("row_end", 1000000)), 1000000))
    col_start = max(0, min(int(request.args.get("col_start", 0)), 1000000))
    col_end = max(0, min(int(request.args.get("col_end", 1000000)), 1000000))

    file_data = data_service.get_current_file()

    if not file_data:
        return jsonify({"error": "请先上传文件"}), 400

    var_data = file_data.get(name)

    if not var_data:
        return jsonify({"error": f"变量不存在：{name}"}), 404

    # 返回切片数据
    if var_data.values:
        sliced_data = var_data.values[row_start:row_end]
        if isinstance(sliced_data[0], list):
            sliced_data = [row[col_start:col_end] for row in sliced_data]
    else:
        sliced_data = []

    return jsonify({
        "data": sliced_data,
        "row_start": row_start,
        "row_end": row_end,
        "col_start": col_start,
        "col_end": col_end,
    })


@app.route("/export/<path:name>", methods=["POST"])
@validate_json_request(['format'])
@rate_limit(max_requests=Config.RATE_LIMIT_EXPORT, window_seconds=60)
def export_variable(name):
    """
    导出变量数据
    
    Args:
        name: 变量名
    
    Returns:
        文件流
    """
    if not validate_var_name(name):
        return jsonify({"error": "无效的变量名"}), 400

    req = request.get_json() or {}
    export_format = req.get("format", "csv").lower()
    
    if export_format not in Config.SUPPORTED_EXPORT_FORMATS:
        return jsonify({"error": f"不支持的导出格式：{export_format}"}), 400

    try:
        filepath = data_service.get_current_filepath()

        if not filepath:
            return jsonify({"error": "请先上传文件"}), 400

        # 导出参数
        row_start = int(req.get("row_start", 0))
        row_end = int(req.get("row_end", 1000000))
        col_start = int(req.get("col_start", 0))
        col_end = int(req.get("col_end", 1000000))
        header = req.get("header")
        row_index = req.get("row_index", False)
        trim_nulls = req.get("trim_nulls", False)

        # 导出数据
        file_data = data_service.get_current_file()
        var_data = file_data.get(name)

        if not var_data:
            return jsonify({"error": f"变量不存在：{name}"}), 404

        data = var_data.values if var_data.values is not None else var_data.value

        if data is None:
            return jsonify({"error": "变量数据为空"}), 400

        # 执行导出
        exported = data_service.export_variable(
            filepath, name, export_format,
            header=header,
            row_index=row_index,
            trim_nulls=trim_nulls,
            row_start=row_start,
            row_end=row_end,
            col_start=col_start,
            col_end=col_end
        )

        # 返回文件流
        filename = f"{name}.{export_format}"
        return send_file(
            io.BytesIO(exported),
            mimetype='application/octet-stream',
            as_attachment=True,
            download_name=filename
        )

    except Exception as e:
        logger.error(f"导出失败：{e}", exc_info=True)
        return jsonify({"error": f"导出失败：{escape_html(str(e))}"}), 500


@app.route("/clear", methods=["POST"])
def clear():
    """清空缓存"""
    data_service.clear_cache()
    logger.info("缓存已清空")
    return jsonify({"success": True, "message": "缓存已清空"})


@app.route("/cache/stats")
def get_cache_stats():
    """获取缓存统计信息"""
    stats = data_service.get_cache_stats()
    return jsonify(stats)


# ==================== 错误处理 ====================

@app.errorhandler(404)
def not_found(error):
    """404 错误处理"""
    return jsonify({"error": "接口不存在"}), 404


@app.errorhandler(500)
def internal_error(error):
    """500 错误处理"""
    logger.error(f"服务器内部错误：{error}")
    return jsonify({"error": "服务器内部错误"}), 500


# ==================== 应用启动 ====================

if __name__ == "__main__":
    print("系统启动...")
    logger.info(f"启动 {Config.APP_NAME} v{Config.VERSION}")
    logger.info(f"访问地址：http://{Config.HOST}:{Config.PORT}")
    app.run(host=Config.HOST, port=Config.PORT, debug=Config.DEBUG)
