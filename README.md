# MAT 文件可视化工具 📊

一个功能强大的 MATLAB .mat 文件可视化工具，支持多种数据格式和交互式可视化。

## ✨ 特性

- 🔍 **多格式支持**: 支持 MATLAB v5/v6/v7/v7.3 (.mat) 文件格式
- 📈 **丰富可视化**: 表格、热图、曲面图、等高线图、3D 散点图等多种视图
- 🚀 **高性能**: LRU 缓存、懒加载、内存管理、分页 API
- 🛡️ **安全可靠**: 输入验证、XSS 防护、路径遍历防护、速率限制
- 🎨 **美观界面**: 现代化暗色主题，响应式设计
- 📤 **数据导出**: 支持导出为 CSV、Excel、TXT、NPY 格式
- 🌐 **远程加载**: 支持 HTTP/HTTPS/SSH 远程文件加载

## 🚀 快速开始

### 环境要求

- Python 3.8+
- Flask
- NumPy
- SciPy
- h5py
- Plotly.js (前端自动加载)

### 安装依赖

```bash
pip install flask numpy scipy h5py
```

可选（Excel 导出支持）：
```bash
pip install openpyxl
```

### 运行

```bash
python app.py
```

访问 http://127.0.0.1:5000

## 📖 使用说明

1. **上传文件**: 点击上传区域选择 .mat 文件
2. **查看变量**: 在左侧变量列表中选择要查看的变量
3. **切换视图**: 使用顶部按钮切换不同的可视化视图
4. **数据导出**: 点击导出按钮将数据保存为所需格式

### 高级功能

- **远程文件**: 支持加载 HTTP/HTTPS/SSH 远程文件
- **数据采样**: 大数据集自动采样，可调节采样率
- **交互操作**: 缩放、旋转、平移等交互功能
- **配色方案**: 多种预设配色方案，支持自定义

## 🛡️ 安全特性

本项目已进行全面的安全加固：

- ✅ 输入验证：所有用户输入都经过严格验证
- ✅ XSS 防护：HTML 转义和输入清理
- ✅ 路径遍历防护：安全的文件路径处理
- ✅ 速率限制：防止暴力攻击和 DoS
- ✅ 文件大小限制：防止资源耗尽

运行安全测试：
```bash
python test_security.py
```

## 📁 项目结构

```
pro/
├── app.py                 # Flask 主应用
├── security.py            # 安全工具模块
├── mat_parser.py          # MAT 文件解析器
├── file_loader.py         # 文件加载器
├── json_utils.py          # JSON 工具函数
├── test_security.py       # 安全测试套件
├── templates/
│   └── index.html         # 前端页面
├── test_files/            # 测试文件
└── SECURITY_REPORT.md     # 安全报告文档
```

## 🧪 测试

运行安全测试：
```bash
python test_security.py
```

## 📊 性能优化

- **LRU 缓存**: 限制内存使用，自动淘汰旧数据
- **懒加载**: 大文件仅解析元数据，按需加载
- **向量化**: 使用 NumPy 向量化操作提升性能
- **分页显示**: 避免一次性加载大量数据

## 📝 API 文档

### 主要端点

- `POST /upload` - 上传 .mat 文件
- `POST /load_remote` - 加载远程文件
- `GET /variable/<name>` - 获取变量数据
- `GET /variable/<name>/slice` - 获取数组切片
- `POST /export/<name>` - 导出变量数据
- `POST /clear` - 清除缓存

## 🔒 安全建议

生产环境部署时建议：

1. 启用 HTTPS
2. 配置防火墙
3. 设置合适的文件上传大小限制
4. 定期更新依赖库
5. 启用访问日志记录

## 📄 许可证

MIT License

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📞 联系方式

如有问题或建议，请提交 Issue。

---

**版本**: v1.0 (安全增强版)  
**更新时间**: 2026-04-03
