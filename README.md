# MAT 文件可视化工具

一个基于 Flask 和 Plotly.js 的 MATLAB 数据文件（.mat）可视化工具，支持上传、解析、查看和导出 MAT 文件数据。

## ✨ 功能特性

- 🖥️ **启动器界面** - 启动后弹出小窗口，显示服务状态、访问地址、运行时长，提供「打开网页 / 复制地址 / 打开日志目录 / 退出」按钮
- 📤 **文件上传** - 支持本地上传和远程加载（HTTP/HTTPS/SSH）
- 📊 **数据可视化** - 自动识别数据类型，提供折线图、热力图、柱状图等多种视图
- 📋 **数据表格** - 支持分页浏览和搜索
- 📥 **数据导出** - 支持 CSV、Excel、TXT、NPY、MAT 等多种格式
- 🔒 **安全可靠** - 完善的输入验证、XSS 防护、速率限制
- ⚡ **性能优化** - 懒加载、LRU 缓存、分块读取

## 🚀 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 启动应用

```bash
python app.py
```

运行后会弹出一个**启动器窗口**，显示服务状态与访问地址。

### 3. 访问应用

点击启动器窗口的「打开网页」按钮，或在浏览器中打开：http://127.0.0.1:5000

### 命令行参数

```bash
python app.py            # 图形界面模式（默认）
python app.py --open     # 服务就绪后自动打开浏览器
python app.py --no-ui    # 纯控制台模式（服务器 / 无桌面环境）
```

也可通过环境变量 `MAT_VIS_NO_UI=1` 强制控制台模式。

## 📋 启动器窗口说明

| 区域 | 说明 |
|------|------|
| 状态行 | `● 服务运行中`（绿）/ `服务无响应`（黄）/ `✗ 启动失败`（红） |
| 访问地址 | 实际监听地址，点击「复制地址」可复制到剪贴板 |
| 已运行 | 运行时长（时:分:秒） |
| 日志目录 | 点击「打开日志目录」可定位到 `logs/mat_visualizer.log` |
| 退出 | 停止本地服务并关闭窗口 |

行为约定：

- **端口冲突**：5000 端口被其他程序占用时，自动改用下一个可用端口并提示
- **重复启动**：检测到已有实例运行时，不再启动第二个服务，直接询问是否打开网页
- **关闭窗口 = 退出**：会先确认，确认后停止服务

## 📦 依赖说明

**核心依赖** (requirements.txt):
- Flask >= 2.3.0
- Werkzeug >= 2.3.0
- NumPy >= 1.24.0
- SciPy >= 1.10.0
- h5py >= 3.8.0

**可选依赖** (optional-requirements.txt):
- paramiko >= 2.11.0 (SSH 远程文件加载)

## 🔧 配置（可选）

复制 `.env.example` 为 `.env` 并修改配置：

```bash
cp .env.example .env
```

主要配置项：
- `SECRET_KEY`: 密钥（生产环境务必修改）
- `HOST`: 监听地址（默认 127.0.0.1）
- `PORT`: 监听端口（默认 5000）
- `MAX_CONTENT_LENGTH_MB`: 最大上传文件大小（默认 500MB）

## 📊 支持的文件格式

- MATLAB v5/v6/v7 (.mat)
- MATLAB v7.3 (HDF5 格式)

## 🛡️ 安全特性

- ✅ 文件名和变量名白名单验证
- ✅ 路径遍历防护
- ✅ XSS 攻击防护
- ✅ 文件上传大小限制
- ✅ 速率限制（防滥用）
- ✅ 上传目录隔离

## 📝 使用说明

1. **上传文件**: 拖拽 .mat 文件或点击选择文件
2. **查看变量**: 点击左侧变量列表查看数据
3. **切换视图**: 根据数据类型自动提供多种视图选项
4. **导出数据**: 点击导出按钮选择格式下载

## 📁 项目结构

```
pro/
├── app.py                      # 主应用入口
├── requirements.txt            # Python 依赖
├── optional-requirements.txt   # 可选依赖
├── .env.example                # 环境变量模板
├── security.py                 # 安全模块
├── file_loader.py              # 文件加载器
├── core/                       # 核心模块
│   ├── config.py              # 配置管理
│   ├── parser.py              # MAT 文件解析
│   ├── cache.py               # 缓存管理
│   ├── exporter.py            # 数据导出
│   └── ui.py                  # 启动器界面（Tkinter 窗口 + 服务线程）
├── services/                   # 服务模块
│   ├── file_service.py        # 文件服务
│   └── data_service.py        # 数据服务
└── frontend/                   # 前端资源
    ├── html/
    │   └── index.html
    └── js/
        └── app.js
```

## 🔐 安全建议

1. 生产环境务必修改 `SECRET_KEY`
2. 关闭调试模式 (`FLASK_DEBUG=False`)
3. 使用 Nginx 反向代理
4. 配置 HTTPS
5. 定期更新依赖

## 🐛 故障排查

**看不到启动器窗口**：
- 确认运行的是图形界面模式（未设置 `MAT_VIS_NO_UI`）
- 查看 `logs/mat_visualizer.log`，日志会记录窗口创建结果与服务异常
- 桌面环境异常时可临时用 `python app.py --no-ui` 以控制台模式启动

**访问地址不是 5000**：
- 5000 端口被占用时会自动顺延端口，以启动器窗口显示的地址为准

**上传失败**:
- 检查文件大小是否超过限制
- 确认文件为有效的 .mat 格式

**SSH 连接失败**:
- 安装可选依赖：`pip install -r optional-requirements.txt`
- 检查 SSH 地址格式：`ssh://user@host:port/path/to/file.mat`

## 📄 许可证

MIT License

---

**版本**: v1.1.0  
**最后更新**: 2026-10-07
