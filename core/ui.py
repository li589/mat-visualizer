"""
启动器 UI 模块

背景：
    打包版使用 PyInstaller `console=False`，运行后没有控制台窗口，
    用户既看不到启动反馈，也无法知道何时可以访问网页。本模块提供一个
    轻量 Tkinter 窗口，把服务状态、访问地址、运行时长等信息展示出来，
    并提供「打开网页 / 复制地址 / 打开日志目录 / 退出」四个操作按钮。

设计要点：
    - Tkinter 只能在主线程创建和更新，因此 UI 跑在主线程，
      Flask 服务通过 werkzeug 的 make_server 跑在后台守护线程，可干净关闭。
    - tkinter 采用延迟导入：服务器 / 无显示环境导入本模块不会失败，
      launch() 会自动回退到纯控制台模式。
    - 日志重定向到文件，UI 提供「打开日志目录」入口，方便无控制台环境下排障。
    - 重复双击时检测已有实例，避免第二个实例抢端口导致用户困惑。

命令行：
    python app.py              # 图形界面模式（默认）
    python app.py --no-ui      # 纯控制台模式
    set MAT_VIS_NO_UI=1        # 环境变量强制控制台模式
"""

import logging
import os
import socket
import sys
import tempfile
import threading
import time
import urllib.request
import webbrowser
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# 存活探测用的接口（GET 返回 JSON，稳定且开销小）
_HEALTH_PATH = "/cache/stats"
# 健康检查间隔（秒）
_HEALTH_INTERVAL = 3.0
# 启动确认轮询次数与间隔
_START_POLL_TIMES = 30
_START_POLL_INTERVAL = 0.2
# 连续健康检查失败多少次后提示无响应
_HEALTH_FAIL_TOLERANCE = 2


# ==================== 基础工具 ====================

def is_frozen() -> bool:
    """是否运行在 PyInstaller 打包环境"""
    return bool(getattr(sys, "frozen", False))


def get_app_dir() -> str:
    """获取应用工作目录：打包版为 exe 所在目录，源码模式为项目根目录"""
    if is_frozen():
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read_version(default: str = "1.0.0") -> str:
    """读取 VERSION 文件中的版本号，失败则使用默认值"""
    version_file = os.path.join(get_app_dir(), "VERSION")
    try:
        if os.path.exists(version_file):
            with open(version_file, "r", encoding="utf-8") as f:
                version = f.read().strip()
            if version:
                return version
    except OSError:
        logger.warning("读取 VERSION 文件失败：%s", version_file)
    return default


def setup_file_logging(app_name: str = "mat_visualizer") -> Tuple[str, str]:
    """
    把日志写入文件。

    打包版 console=False 时控制台不可见，stdout/stderr 全部丢失，
    出问题无从排查，因此统一落盘到 logs/ 目录（不可写时退回临时目录）。

    返回：(日志目录, 日志文件路径)
    """
    log_dir = os.path.join(get_app_dir(), "logs")
    try:
        os.makedirs(log_dir, exist_ok=True)
        probe = os.path.join(log_dir, ".write_probe")
        with open(probe, "w", encoding="utf-8") as f:
            f.write("ok")
        os.remove(probe)
    except OSError:
        log_dir = os.path.join(tempfile.gettempdir(), f"{app_name}_logs")
        os.makedirs(log_dir, exist_ok=True)

    log_file = os.path.join(log_dir, f"{app_name}.log")
    root_logger = logging.getLogger()
    # Flask 导入时会把 root logger 的级别压到 WARNING，导致业务 INFO 日志
    # （含本模块的启动过程日志）被静默丢弃；打包版无控制台，必须落盘，
    # 因此这里显式恢复 INFO。
    root_logger.setLevel(logging.INFO)
    tag = "_mat_visualizer_file_handler"
    if not any(getattr(h, tag, False) for h in root_logger.handlers):
        try:
            handler = logging.FileHandler(log_file, encoding="utf-8")
            handler.setFormatter(logging.Formatter(
                "%(asctime)s - %(levelname)s - %(name)s - %(message)s"
            ))
            setattr(handler, tag, True)
            root_logger.addHandler(handler)
        except OSError:
            logger.warning("无法创建日志文件：%s", log_file)
    return log_dir, log_file


def is_port_busy(host: str, port: int, timeout: float = 0.3) -> bool:
    """端口是否已被占用"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        return sock.connect_ex((host, port)) == 0


def is_service_alive(url: str, timeout: float = 1.5) -> bool:
    """探测 HTTP 服务是否正常响应"""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


def find_free_port(host: str, preferred: int, tries: int = 20) -> Optional[int]:
    """从 preferred 开始向后寻找空闲端口"""
    for port in range(preferred, preferred + tries):
        if not is_port_busy(host, port):
            return port
    return None


def open_path(path: str) -> None:
    """用系统默认程序打开文件或目录"""
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform.startswith("darwin"):
            os.system(f'open "{path}"')
        else:
            os.system(f'xdg-open "{path}"')
    except OSError:
        logger.warning("无法打开：%s", path)


# ==================== 服务线程 ====================

class ServerRunner:
    """在后台守护线程中运行 Flask 服务，支持干净停止"""

    def __init__(self, app, host: str, port: int):
        from werkzeug.serving import make_server

        self.host = host
        self.port = port
        # 绑定端口在此完成：端口被占用会直接抛 OSError，由调用方处理
        self._server = make_server(host, port, app, threaded=True)
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="mat-visualizer-server",
            daemon=True,
        )

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def start(self) -> None:
        self._thread.start()
        logger.info("服务已启动：%s", self.url)

    def stop(self, timeout: float = 3.0) -> None:
        """停止服务并等待线程退出"""
        try:
            self._server.shutdown()
        except Exception:
            logger.debug("服务停止时出现异常", exc_info=True)
        if self._thread.is_alive():
            self._thread.join(timeout=timeout)
        logger.info("服务已停止")


# ==================== 图形界面 ====================

def _run_ui(app, config, log_dir: str, version: str, open_browser_on_start: bool) -> None:
    """构建并运行 Tkinter 窗口（仅在有图形环境的机器调用）"""
    import tkinter as tk
    from tkinter import messagebox, ttk

    host = config.HOST
    preferred_port = config.PORT
    base_url = f"http://{host}:{preferred_port}"

    # 已有实例在运行：不重复启动，直接引导用户打开网页
    if is_port_busy(host, preferred_port) and is_service_alive(base_url + _HEALTH_PATH):
        logger.info("检测到已有实例在运行：%s", base_url)
        _handle_existing_instance(base_url)
        return

    # 端口被其他程序占用：自动向后寻找空闲端口
    port_switched = False
    port = preferred_port
    if is_port_busy(host, preferred_port):
        port = find_free_port(host, preferred_port + 1)
        if port is None:
            messagebox.showerror(
                "启动失败",
                f"端口 {preferred_port} 被其他程序占用，且之后 {20} 个端口均不可用。\n"
                "请关闭占用程序后重试。",
            )
            sys.exit(1)
        port_switched = True
        logger.info("端口 %d 被占用，自动改用 %d", preferred_port, port)

    try:
        runner = ServerRunner(app, host, port)
    except OSError as e:
        messagebox.showerror("启动失败", f"无法监听端口 {port}：\n{e}")
        sys.exit(1)

    # ---------------- 窗口 ----------------
    root = tk.Tk()
    root.title(f"{config.APP_NAME} v{version}")
    root.resizable(False, False)

    style = ttk.Style()
    for theme in ("vista", "winnative", "clam"):
        if theme in style.theme_names():
            style.theme_use(theme)
            break

    state = {"alive": True, "fail_count": 0}

    wrap = ttk.Frame(root, padding=(20, 16, 20, 14))
    wrap.pack(fill="both", expand=True)

    ttk.Label(
        wrap, text=config.APP_NAME,
        font=("Microsoft YaHei UI", 14, "bold"),
    ).pack(anchor="w")
    ttk.Label(wrap, text=f"版本 {version}", foreground="#6b7280").pack(anchor="w", pady=(2, 12))

    ttk.Separator(wrap).pack(fill="x", pady=(0, 14))

    status_var = tk.StringVar(value="● 正在启动服务 ...")
    status_label = ttk.Label(
        wrap, textvariable=status_var,
        font=("Microsoft YaHei UI", 10, "bold"), foreground="#b45309",
    )
    status_label.pack(anchor="w")

    hint_var = tk.StringVar()
    hint_label = ttk.Label(wrap, textvariable=hint_var, foreground="#b45309")
    hint_label.pack(anchor="w", pady=(4, 0))

    url_var = tk.StringVar(value=runner.url)
    url_row = ttk.Frame(wrap)
    url_row.pack(fill="x", pady=(14, 0))
    ttk.Label(url_row, text="访问地址", width=8).pack(side="left")
    entry = ttk.Entry(url_row, textvariable=url_var, state="readonly", width=26)
    entry.pack(side="left", padx=(4, 0))
    entry.configure(justify="center")

    info_row = ttk.Frame(wrap)
    info_row.pack(fill="x", pady=(10, 0))
    elapsed_var = tk.StringVar(value="已运行 00:00:00")
    ttk.Label(info_row, textvariable=elapsed_var, foreground="#374151").pack(side="left")
    ttk.Label(info_row, text=f"日志目录：{log_dir}", foreground="#9ca3af").pack(side="right")

    btn_row = ttk.Frame(wrap)
    btn_row.pack(fill="x", pady=(16, 0))

    # ---------------- 行为 ----------------
    def open_web() -> None:
        webbrowser.open(runner.url)

    def copy_url() -> None:
        root.clipboard_clear()
        root.clipboard_append(runner.url)
        root.bell()  # 无声提示：地址已复制

    def open_logs() -> None:
        open_path(log_dir)

    def on_exit() -> None:
        if not messagebox.askyesno("退出", "退出会停止本地服务，确定退出吗？"):
            return
        state["alive"] = False
        runner.stop()
        root.destroy()

    ttk.Button(btn_row, text="打开网页", command=open_web).pack(side="left")
    ttk.Button(btn_row, text="复制地址", command=copy_url).pack(side="left", padx=(8, 0))
    ttk.Button(btn_row, text="打开日志目录", command=open_logs).pack(side="left", padx=(8, 0))
    ttk.Button(btn_row, text="退出", command=on_exit).pack(side="right")

    ttk.Label(
        wrap, text="关闭窗口等同于退出，会同时停止本地服务",
        foreground="#9ca3af",
    ).pack(anchor="w", pady=(12, 0))

    root.protocol("WM_DELETE_WINDOW", on_exit)

    # ---------------- 服务启动与健康检查 ----------------
    def confirm_started(attempt: int = 0) -> None:
        if not state["alive"]:
            return
        if is_service_alive(runner.url + _HEALTH_PATH, timeout=0.8):
            status_var.set("● 服务运行中")
            status_label.configure(foreground="#15803d")
            if port_switched:
                hint_var.set(f"端口 {preferred_port} 被占用，已自动切换到 {port}")
            else:
                hint_var.set("")
            if open_browser_on_start:
                open_web()
            tick()
            watchdog()
        elif attempt < _START_POLL_TIMES:
            root.after(int(_START_POLL_INTERVAL * 1000), confirm_started, attempt + 1)
        else:
            status_var.set("✗ 服务启动失败")
            status_label.configure(foreground="#b91c1c")
            hint_var.set(f"请查看日志：{log_dir}")

    def tick() -> None:
        """刷新运行时长"""
        if not state["alive"]:
            return
        seconds = int(time.time() - started_at)
        elapsed_var.set("已运行 {:02d}:{:02d}:{:02d}".format(
            seconds // 3600, seconds % 3600 // 60, seconds % 60
        ))
        root.after(1000, tick)

    def watchdog() -> None:
        """周期性健康检查，服务异常时在界面上提示"""
        if not state["alive"]:
            return
        if is_service_alive(runner.url + _HEALTH_PATH, timeout=2.0):
            state["fail_count"] = 0
        else:
            state["fail_count"] += 1
            if state["fail_count"] >= _HEALTH_FAIL_TOLERANCE:
                status_var.set("● 服务无响应")
                status_label.configure(foreground="#b45309")
        root.after(int(_HEALTH_INTERVAL * 1000), watchdog)

    started_at = time.time()
    runner.start()
    logger.info("启动 %s v%s", config.APP_NAME, version)

    # 居中显示
    root.update_idletasks()
    width, height = root.winfo_width(), root.winfo_height()
    x = max((root.winfo_screenwidth() - width) // 2, 0)
    y = max((root.winfo_screenheight() - height) // 3, 0)
    root.geometry(f"{width}x{height}+{x}+{y}")
    root.update_idletasks()
    logger.info(
        "启动器窗口已创建：id=%s viewable=%s geometry=%s",
        root.winfo_id(), root.winfo_viewable(), root.winfo_geometry(),
    )

    root.after(100, confirm_started)
    root.mainloop()
    logger.info("启动器窗口已关闭，退出主流程")


def _handle_existing_instance(url: str) -> None:
    """已有实例在运行时，询问是否直接打开网页"""
    from tkinter import messagebox

    if messagebox.askyesno("应用已在运行", f"应用已经在运行：\n{url}\n\n现在打开网页吗？"):
        webbrowser.open(url)


# ==================== 控制台模式 ====================

def _run_headless(app, config, log_file: str, version: str) -> None:
    """无图形环境回退：前台运行服务，日志仍写入文件"""
    url = f"http://{config.HOST}:{config.PORT}"
    print(f"{config.APP_NAME} v{version}")
    print(f"访问地址：{url}")
    print(f"日志文件：{log_file}")
    print("按 Ctrl+C 停止服务")
    try:
        app.run(host=config.HOST, port=config.PORT, debug=config.DEBUG, threaded=True)
    except OSError as e:
        print(f"[FAIL] 启动失败（端口 {config.PORT} 可能已被占用）：{e}")
        sys.exit(1)


# ==================== 对外入口 ====================

def launch(app, config, open_browser_on_start: bool = False,
           headless: bool = False) -> None:
    """
    启动应用：优先图形界面，不可用时回退控制台模式

    Args:
        app: Flask 应用实例
        config: 配置类
        open_browser_on_start: 服务就绪后是否自动打开浏览器
        headless: 强制控制台模式
    """
    version = read_version(getattr(config, "VERSION", "1.0.0"))
    log_dir, log_file = setup_file_logging()

    use_headless = headless or bool(os.environ.get("MAT_VIS_NO_UI"))
    if use_headless:
        _run_headless(app, config, log_file, version)
        return

    try:
        import tkinter  # noqa: F401  延迟导入，探测图形环境是否可用
    except Exception as e:  # ImportError 或 TclError
        logger.warning("图形界面不可用，回退控制台模式：%s", e)
        _run_headless(app, config, log_file, version)
        return

    try:
        _run_ui(app, config, log_dir, version, open_browser_on_start)
    except Exception as e:
        logger.error("图形界面启动失败，回退控制台模式：%s", e, exc_info=True)
        _run_headless(app, config, log_file, version)