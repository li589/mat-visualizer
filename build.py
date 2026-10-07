#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
MAT 文件可视化工具 - 打包脚本 v1.0

使用方法:
    python build.py

打包后的可执行文件位于 dist/ 目录
"""

import os
import sys
import shutil
import zipfile
import subprocess
from datetime import datetime

# 项目根目录
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
DIST_DIR = os.path.join(ROOT_DIR, 'dist')
BUILD_DIR = os.path.join(ROOT_DIR, 'build')
SPEC_FILE = os.path.join(ROOT_DIR, 'mat_visualizer.spec')

# 版本号（从 VERSION 文件读取，避免与仓库版本不一致）
# 打包脚本刻意不 import core.version：core 包会连带加载 numpy/scipy 等运行时依赖，
# 打包阶段无需为此付出导入开销。此处兜底值与 core/version.py 保持一致。
def get_version():
    version_file = os.path.join(ROOT_DIR, 'VERSION')
    if os.path.exists(version_file):
        with open(version_file, 'r', encoding='utf-8') as f:
            version = f.read().strip()
        if version:
            return version
    print("[WARN] 未找到有效的 VERSION 文件，发布包将标记为 v0.0.0")
    return "0.0.0"

VERSION = get_version()

def print_step(message):
    """打印步骤信息"""
    print(f"\n{'='*60}")
    print(f">>> {message}")
    print('='*60)

def clean_build():
    """清理旧的构建文件"""
    print_step("清理旧的构建文件")
    
    if os.path.exists(DIST_DIR):
        shutil.rmtree(DIST_DIR)
        print(f"已删除 {DIST_DIR}")
    
    if os.path.exists(BUILD_DIR):
        shutil.rmtree(BUILD_DIR)
        print(f"已删除 {BUILD_DIR}")
    
    # 清理 __pycache__（跳过虚拟环境、.git 等大型目录，避免误删 site-packages 缓存）
    SKIP_DIRS = {'venv', '.venv', 'env', 'ENV', '.git', 'node_modules', 'dist', 'build'}
    for root, dirs, files in os.walk(ROOT_DIR):
        for d in list(dirs):
            if d == '__pycache__':
                shutil.rmtree(os.path.join(root, d), ignore_errors=True)
                dirs.remove(d)
            elif d in SKIP_DIRS:
                dirs.remove(d)
    
    print("清理完成")

def check_dependencies():
    """检查依赖"""
    print_step("检查依赖")
    
    try:
        import PyInstaller
        print(f"[OK] PyInstaller 版本：{PyInstaller.__version__}")
    except ImportError:
        print("[FAIL] PyInstaller 未安装")
        print("请运行：pip install pyinstaller")
        return False
    
    # 检查其他关键依赖
    required = ['flask', 'numpy', 'scipy', 'h5py']
    for pkg in required:
        try:
            __import__(pkg)
            print(f"[OK] {pkg}")
        except ImportError:
            print(f"[FAIL] {pkg} 未安装")
            return False
    
    return True

def build_exe():
    """执行 PyInstaller 打包"""
    print_step("开始打包")
    
    cmd = [
        sys.executable,
        '-m', 'PyInstaller',
        '--clean',
        '--noconfirm',
        SPEC_FILE
    ]
    
    print(f"执行命令：{' '.join(cmd)}")
    subprocess.run(cmd, cwd=ROOT_DIR, check=True)
    
    print("打包完成")

def verify_build():
    """验证构建结果"""
    print_step("验证构建结果")
    
    exe_name = 'MAT_Visualizer.exe' if sys.platform == 'win32' else 'MAT_Visualizer'
    exe_path = os.path.join(DIST_DIR, exe_name)
    
    if os.path.exists(exe_path):
        size = os.path.getsize(exe_path)
        size_mb = size / (1024 * 1024)
        print(f"[OK] 可执行文件已生成：{exe_path}")
        print(f"  文件大小：{size_mb:.2f} MB")
        return True
    else:
        print(f"[FAIL] 可执行文件未找到：{exe_path}")
        return False

def create_release_package():
    """创建发布包"""
    print_step("创建发布包")
    
    release_dir = os.path.join(DIST_DIR, f'MAT_Visualizer_v{VERSION}')
    if os.path.exists(release_dir):
        shutil.rmtree(release_dir)

    os.makedirs(release_dir)

    # VERSION 同时复制到 dist 根目录，使直接运行 dist/MAT_Visualizer.exe 也能读到版本号
    # （运行时从 exe 同级目录读取，发行包内也会随附一份）
    shutil.copy2(os.path.join(ROOT_DIR, 'VERSION'), os.path.join(DIST_DIR, 'VERSION'))
    
    # 复制可执行文件
    exe_name = 'MAT_Visualizer.exe' if sys.platform == 'win32' else 'MAT_Visualizer'
    src_exe = os.path.join(DIST_DIR, exe_name)
    dst_exe = os.path.join(release_dir, exe_name)
    
    if os.path.exists(src_exe):
        shutil.copy2(src_exe, dst_exe)
        print(f"[OK] 已复制可执行文件")
    
    # 复制 README、LICENSE 和 VERSION
    # VERSION 需随 exe 一起分发：启动器 UI 从 exe 同级目录读取版本号显示在窗口标题
    for file in ['README.md', 'LICENSE', 'VERSION']:
        src = os.path.join(ROOT_DIR, file)
        if os.path.exists(src):
            shutil.copy2(src, release_dir)
            print(f"[OK] 已复制 {file}")
    
    # 创建使用说明文件
    readme_txt = os.path.join(release_dir, '使用说明.txt')
    with open(readme_txt, 'w', encoding='utf-8') as f:
        f.write(f"""MAT 文件可视化工具 v{VERSION}
========================

启动方法:
1. 双击运行 MAT_Visualizer.exe
2. 弹出启动器窗口后，点击「打开网页」或手动访问 http://127.0.0.1:5000

功能特性:
- 启动器界面：显示服务状态、访问地址、运行时长
- 支持本地 MAT 文件上传
- 支持 HTTP/HTTPS 远程文件加载
- 支持 SSH/SFTP 远程文件加载
- 实时数据可视化
- 支持多种图表类型
- 数据导出功能

系统要求:
- Windows 7/10/11
- 无需额外依赖

注意事项:
- 首次启动需要几秒钟解包，请稍候
- 端口 5000 被占用时会自动切换到下一个可用端口
- 退出程序：在启动器窗口点击「退出」按钮（关闭窗口等同于退出）
- 运行日志：程序所在目录 logs/mat_visualizer.log

技术支持:
GitHub: https://github.com/li589/mat-visualizer
""")
    
    print(f"[OK] 已创建使用说明")

    # 打包为 zip（发行版分发用）
    zip_path = os.path.join(DIST_DIR, f'MAT_Visualizer_v{VERSION}.zip')
    if os.path.exists(zip_path):
        os.remove(zip_path)
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(release_dir):
            for fn in files:
                full = os.path.join(root, fn)
                arc = os.path.relpath(full, DIST_DIR)
                zf.write(full, arc)
    print(f"[OK] 已创建发行包 zip：{zip_path}")

    print(f"\n发布包位置：{release_dir}")
    
    return release_dir

def main():
    """主函数"""
    print("="*60)
    print("MAT 文件可视化工具 - 打包脚本 v1.0")
    print(f"构建时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)
    
    # 检查依赖
    if not check_dependencies():
        print("\n[FAIL] 依赖检查失败，请安装所需依赖后重试")
        sys.exit(1)
    
    # 清理构建
    clean_build()
    
    # 执行打包
    try:
        build_exe()
    except subprocess.CalledProcessError as e:
        print(f"\n[FAIL] 打包失败：{e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n[FAIL] 打包失败：{e}")
        sys.exit(1)
    
    # 验证构建
    if not verify_build():
        print("\n[FAIL] 构建验证失败")
        sys.exit(1)
    
    # 创建发布包
    create_release_package()
    
    print_step("打包成功!")
    print(f"[OK] 可执行文件：{os.path.join(DIST_DIR, 'MAT_Visualizer.exe')}")
    print(f"[OK] 发布包：{os.path.join(DIST_DIR, 'MAT_Visualizer_v' + VERSION)}")
    print("\n提示：可以直接运行 dist/MAT_Visualizer.exe 启动应用")

if __name__ == '__main__':
    main()
