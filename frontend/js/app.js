/**
 * MAT 文件可视化工具 - 主应用模块
 *
 * @version 以仓库根目录 VERSION 文件为准，不在此硬编码
 * @author MAT Visualizer Team
 */

'use strict';

document.addEventListener('DOMContentLoaded', function() {
    "use strict";

    var uploadZone  = document.getElementById("uploadZone");
    var fileInfo    = document.getElementById("fileInfo");
    var infoGrid    = document.getElementById("infoGrid");
    var mainLayout  = document.getElementById("mainLayout");
    var varList     = document.getElementById("varList");
    var contentArea = document.getElementById("contentArea");
    var progressBar = document.getElementById("progressBar");
    var progressFill = document.getElementById("progressFill");

    var currentVarData = null;
    var lastPlotBox = null;
    var dataCache = {};
    var tableState = { rowOffset: 0, colOffset: 0, rowLimit: 50, colLimit: 20, totalRows: 0, totalCols: 0, currentVar: null, searchResults: [], highlightCell: null };
    var sidebarCollapsed = false;
    var isUploading = false;

    var sidebarToggle = document.getElementById("sidebarToggle");
    var activeVarIndex = -1;

    function updateTogglePosition() {
        if (!sidebarToggle) return;
        var items = varList.querySelectorAll(".var-item");
        var targetItem = null;
        if (activeVarIndex >= 0 && activeVarIndex < items.length) {
            targetItem = items[activeVarIndex];
        } else if (items.length > 0) {
            targetItem = items[0];
        }
        if (targetItem) {
            var itemRect = targetItem.getBoundingClientRect();
            var sidebarRect = document.getElementById("sidebar").getBoundingClientRect();
            sidebarToggle.style.top = (targetItem.offsetTop + targetItem.offsetHeight / 2 - 10) + "px";
        }
    }

    if (sidebarToggle) {
        sidebarToggle.addEventListener("click", function() {
            sidebarCollapsed = !sidebarCollapsed;
            var sidebar = document.getElementById("sidebar");
            var mainLayout = document.getElementById("mainLayout");
            if (sidebarCollapsed) {
                sidebar.classList.add("collapsed");
                mainLayout.classList.add("sidebar-collapsed");
                sidebarToggle.textContent = "▶";
            } else {
                sidebar.classList.remove("collapsed");
                mainLayout.classList.remove("sidebar-collapsed");
                sidebarToggle.textContent = "◀";
            }
            setTimeout(updateTogglePosition, 350);
        });
    }

    /* ==================== 上传 ==================== */
    var uploadTabs = document.querySelectorAll(".upload-tab");
    var localUpload = document.getElementById("localUpload");
    var remoteForm = document.getElementById("remoteForm");
    var remoteUrl = document.getElementById("remoteUrl");
    var sshPassword = document.getElementById("sshPassword");
    var loadRemoteBtn = document.getElementById("loadRemoteBtn");
    var compactSwitcher = document.getElementById("compactSwitcher");

    uploadTabs.forEach(function(tab) {
        tab.addEventListener("click", function() {
            uploadTabs.forEach(function(t) { t.classList.remove("active"); });
            this.classList.add("active");
            var mode = this.dataset.mode;
            if (mode === "local") {
                localUpload.style.display = "block";
                remoteForm.classList.remove("active");
            } else {
                localUpload.style.display = "none";
                remoteForm.classList.add("active");
            }
        });
    });

    if (compactSwitcher) {
        compactSwitcher.addEventListener("click", function(e) {
            var btn = e.target.closest(".btn");
            if (!btn) return;
            compactSwitcher.querySelectorAll(".btn").forEach(function(b) { b.classList.remove("active"); });
            btn.classList.add("active");
            var mode = btn.dataset.mode;
            if (mode === "local") {
                remoteForm.classList.remove("active");
                localUpload.style.display = "inline-flex";
            } else {
                localUpload.style.display = "none";
                remoteForm.classList.add("active");
            }
        });
    }

    localUpload.addEventListener("click", triggerFileInput);
    localUpload.addEventListener("dragover", function(e) {
        e.preventDefault();
        uploadZone.classList.add("dragover");
    });
    localUpload.addEventListener("dragleave", function() {
        uploadZone.classList.remove("dragover");
    });
    localUpload.addEventListener("drop", function(e) {
        e.preventDefault();
        uploadZone.classList.remove("dragover");
        if (e.dataTransfer.files.length) uploadFile(e.dataTransfer.files[0]);
    });

    loadRemoteBtn.addEventListener("click", function() {
        var url = remoteUrl.value.trim();
        if (!url) {
            alert("请输入远程文件地址");
            return;
        }
        var password = sshPassword.value.trim();
        if (url.toLowerCase().indexOf("ssh") === 0 && !password) {
            alert("SSH 方式需要输入密码");
            sshPassword.focus();
            return;
        }
        loadRemoteFile(url, password);
    });

    function getDisplayFilename(path) {
        if (!path) return "";
        var cleaned = String(path).split("?")[0].split("#")[0];
        var segments = cleaned.split(/[\\/]/);
        return segments[segments.length - 1] || "";
    }

    function setLocalUploadContent(html, displayMode) {
        if (!localUpload) return;
        localUpload.innerHTML = html;
        localUpload.style.display = displayMode || "block";
        localUpload.style.pointerEvents = "auto";
    }

    function showLoadingInUpload(message) {
        if (!localUpload) return;
        localUpload.innerHTML = '<div class="loading-spinner" style="text-align:center;padding:20px;"><div class="loading"></div>' +
            '<p style="margin-top:12px;color:var(--text-dim)">' + message + '</p></div>';
        localUpload.style.display = "block";
        localUpload.style.pointerEvents = "none";
    }

    function parseResponseError(response) {
        var contentType = response.headers.get("Content-Type") || "";
        if (contentType.indexOf("application/json") !== -1) {
            return response.json().then(function(data) {
                var message = data && data.error ? data.error : "请求失败";
                throw new Error(message);
            });
        }
        return response.text().then(function(text) {
            var message = text ? text.trim() : "";
            throw new Error(message || ("请求失败（HTTP " + response.status + "）"));
        });
    }

    function requestJson(url, options) {
        return fetch(url, options).then(function(response) {
            if (!response.ok) {
                return parseResponseError(response);
            }
            return response.json();
        });
    }

    function finishLoadingState() {
        isUploading = false;
        loadRemoteBtn.disabled = false;
        loadRemoteBtn.textContent = "加载远程文件";
    }

    function applyLoadedFile(data, displayName) {
        return new Promise(function(resolve) {
            clearCurrentData();
            setTimeout(function() {
                progressBar.style.display = "none";
                showFileInfo(data.info || {});
                showVarList(data.variables, data.var_overview);
                if (data.warning) {
                    contentArea.innerHTML = '<div class="placeholder"><span style="font-size:2rem">⚠️</span><span>' + escapeHtml(data.warning) + '</span></div>';
                }
                mainLayout.style.display = "grid";
                uploadZone.classList.add("compact");
                fileInfo.classList.add("compact", "show");
                contentArea.classList.add("expanded");
                if (compactSwitcher) compactSwitcher.style.display = "inline-flex";
                setupCompactMode();
                resetUploadSuccess(displayName);
                resolve();
            }, 200);
        });
    }

    function loadRemoteFile(url, password) {
        if (isUploading) { alert("文件正在加载中，请稍候"); return; }
        isUploading = true;
        var hadFile = hasCurrentFile();
        loadRemoteBtn.disabled = true;
        loadRemoteBtn.textContent = "加载中...";
        showLoadingInUpload('正在加载 <strong>' + escapeHtml(url) + '</strong>，请稍候…');
        setProgress(30);

        var payload = { source: url };
        if (password) payload.password = password;

        requestJson("/load_remote", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        })
        .then(function(data) {
            setProgress(100);
            return applyLoadedFile(data, getDisplayFilename((data.info && (data.info.filename || data.info.source)) || url) || "remote_file.mat");
        })
        .catch(function(err) {
            alert("加载失败：" + err.message);
            resetUpload(hadFile);
        })
        .finally(function() {
            finishLoadingState();
        });
    }

    function setupCompactMode() {
        localUpload.style.display = "inline-flex";
        remoteForm.classList.remove("active");
        if (compactSwitcher) {
            compactSwitcher.querySelectorAll(".btn").forEach(function(b) { b.classList.remove("active"); });
            compactSwitcher.querySelector('.btn[data-mode="local"]').classList.add("active");
        }
    }

    function triggerFileInput() {
        if (isUploading) return;
        var input = document.createElement("input");
        input.type = "file";
        input.accept = ".mat";
        input.addEventListener("change", function() {
            if (input.files.length) uploadFile(input.files[0]);
        });
        input.click();
    }

    function setProgress(pct) {
        progressBar.style.display = "block";
        progressFill.style.width = pct + "%";
    }

    function clearCurrentData() {
        currentVarData = null;
        dataCache = {};
        tableState = { rowOffset: 0, colOffset: 0, rowLimit: 50, colLimit: 20, totalRows: 0, totalCols: 0, currentVar: null, searchResults: [], highlightCell: null };
        activeVarIndex = -1;
        if (varList) varList.innerHTML = "";
        if (contentArea) contentArea.innerHTML = '<div class="placeholder"><span style="font-size:2rem">📊</span><span>选择左侧变量查看数据</span></div>';
    }

    function uploadFile(file) {
        if (isUploading) { alert("文件正在解析中，请稍候"); return; }
        if (!file.name.endsWith(".mat")) { alert("请选择 .mat 文件"); return; }
        isUploading = true;
        var hadFile = hasCurrentFile();
        showLoadingInUpload('正在解析 <strong>' + escapeHtml(file.name) + '</strong>，请稍候…');
        setProgress(30);

        var fd = new FormData();
        fd.append("file", file);
        setProgress(60);

        requestJson("/upload", { method: "POST", body: fd })
            .then(function(data) {
                setProgress(100);
                return applyLoadedFile(data, file.name);
            })
            .catch(function(err) {
                alert("上传失败：" + err.message);
                resetUpload(hadFile);
            })
            .finally(function() {
                finishLoadingState();
            });
    }

    function hasCurrentFile() {
        return !!(currentFileName || currentFilePath || currentSourcePath);
    }

    function restoreLocalUploadContent() {
        setLocalUploadContent(
            '<div class="icon">📁</div>' +
            '<p>拖拽 <strong>.mat</strong> 文件到此处，或 <strong style="color:var(--accent)">点击选择文件</strong></p>',
            "block"
        );
    }

    function resetUpload(showCompact) {
        progressBar.style.display = "none";
        restoreLocalUploadContent();
        
        if (showCompact) {
            uploadZone.classList.add("compact");
            fileInfo.classList.add("compact");
            contentArea.classList.add("expanded");
            if (compactSwitcher) compactSwitcher.style.display = "inline-flex";
            setupCompactMode();
            resetUploadSuccess(currentFileName || "文件");
        } else {
            uploadZone.classList.remove("compact");
            fileInfo.classList.remove("compact");
            contentArea.classList.remove("expanded");
            if (compactSwitcher) compactSwitcher.style.display = "none";
            localUpload.style.display = "block";
            remoteForm.classList.remove("active");
            uploadTabs.forEach(function(t) { t.classList.remove("active"); });
            var localTab = document.querySelector('.upload-tab[data-mode="local"]');
            if (localTab) localTab.classList.add("active");
        }
    }

    function resetUploadSuccess(filename) {
        setLocalUploadContent(
            '<div class="icon" style="font-size:1.2rem;margin:0;">✅</div>' +
            '<p style="font-size:.8rem;margin:0;color:var(--text-dim);">已加载 <strong>' + escapeHtml(filename) + '</strong> — ' +
            '<span style="color:var(--accent);cursor:pointer;">点击更换</span></p>',
            "inline-flex"
        );
    }

    /* ==================== 文件信息 ==================== */
    var allVarNames = [];
    var currentFileName = "";
    var currentFileSize = "";
    var currentMatVersion = "";
    var currentVarCount = 0;
    var currentFilePath = "";
    var currentSourcePath = "";

    function showFileInfo(info) {
        fileInfo.classList.add("show");
        allVarNames = info.variable_names || [];
        currentFileName = info.filename || "";
        currentFileSize = info.size_human || "";
        currentMatVersion = info.mat_version || "v7 及以下";
        currentVarCount = info.num_variables || 0;
        currentFilePath = info.filepath || "";
        currentSourcePath = info.source || currentFilePath;
        renderFileInfo();
    }

    function formatVarNames(names) {
        if (!names || names.length === 0) return "无";
        var isCompact = fileInfo.classList.contains("compact");
        var threshold = isCompact ? 60 : 200;
        var fullText = names.join(", ");
        if (fullText.length <= threshold) return fullText;
        var result = [];
        var len = 0;
        for (var i = 0; i < names.length; i++) {
            var entry = (i > 0 ? ", " : "") + names[i];
            if (len + entry.length > threshold) {
                result.push("...");
                break;
            }
            result.push(entry);
            len += entry.length;
        }
        return result.join("");
    }

    function makeItem(label, value, extraClass, tooltip, fullValue) {
        var cls = "info-item" + (extraClass ? " " + extraClass : "");
        var tip = tooltip ? '<div class="tooltip">' + escapeHtml(tooltip) + '</div>' : '';
        var copyValue = (typeof fullValue !== "undefined") ? fullValue : value;
        var copyBtn = '<button class="copy-btn" title="复制" data-copy-value="' + escapeHtml(String(copyValue)) + '">📋</button>';
        return '<div class="' + cls + '"><div class="label">' + label +
               '</div><div class="value">' + escapeHtml(String(value)) + '</div>' + copyBtn + tip + '</div>';
    }

    function renderFileInfo() {
        var varText = formatVarNames(allVarNames);
        var varFullText = allVarNames.length > 0 ? allVarNames.join(", ") : "无";
        var varTooltip = allVarNames.length > 0 ? allVarNames.join("\n") : "无变量";
        infoGrid.innerHTML =
            makeItem("文件名", currentFileName, "", currentSourcePath, currentSourcePath) +
            makeItem("大小", currentFileSize) +
            makeItem("格式版本", currentMatVersion) +
            makeItem("变量数", currentVarCount) +
            makeItem("变量", varText, "vars-item", varTooltip, varFullText);

        infoGrid.querySelectorAll(".copy-btn").forEach(function(btn) {
            btn.addEventListener("click", function(e) {
                e.stopPropagation();
                var text = this.dataset.copyValue;
                if (!text || text === "undefined") return;
                if (navigator.clipboard && navigator.clipboard.writeText) {
                    navigator.clipboard.writeText(text).then(function() {
                        showCopiedFeedback(btn);
                    }).catch(function() {
                        fallbackCopy(text, btn);
                    });
                } else {
                    fallbackCopy(text, btn);
                }
            });
        });
    }

    function showCopiedFeedback(btn) {
        btn.classList.add("copied");
        btn.textContent = "✓";
        setTimeout(function() {
            btn.classList.remove("copied");
            btn.textContent = "📋";
        }, 1200);
    }

    function fallbackCopy(text, btn) {
        var ta = document.createElement("textarea");
        ta.value = text;
        ta.style.position = "fixed";
        ta.style.left = "-9999px";
        document.body.appendChild(ta);
        ta.select();
        try {
            document.execCommand("copy");
            showCopiedFeedback(btn);
        } catch (err) {
            console.error("Copy failed:", err);
        }
        document.body.removeChild(ta);
    }

    /* ==================== 变量列表 ==================== */
    var varColors = [];

    function getVarColor(idx) {
        var hues = [200, 260, 340, 30, 150, 180, 280, 45, 320, 10, 170, 230, 60, 300, 120, 210, 350, 90, 250, 15];
        var h = hues[idx % hues.length];
        return {
            bg: "hsla(" + h + ", 60%, 65%, 0.12)",
            border: "hsla(" + h + ", 60%, 65%, 0.3)",
            text: "hsla(" + h + ", 60%, 70%, 0.9)",
            badge: "hsla(" + h + ", 50%, 65%, 0.15)",
        };
    }

    function showVarList(names, overview) {
        varList.innerHTML = "";
        varColors = [];
        if (!names || names.length === 0) {
            varList.innerHTML = '<li style="padding:16px;text-align:center;color:var(--text-dim);font-size:.85rem">无可用变量</li>';
            if (sidebarToggle) sidebarToggle.style.display = "none";
            return;
        }
        if (sidebarToggle) sidebarToggle.style.display = "flex";
        names.forEach(function(name, idx) {
            var li = document.createElement("li");
            li.className = "var-item";
            li.dataset.name = name;
            li.dataset.index = idx;
            var info = overview && overview[name] ? overview[name] : {};
            var firstChar = name.charAt(0);
            var color = getVarColor(idx);
            varColors.push(color);
            li.style.borderLeft = "3px solid " + color.border;
            li.innerHTML = '<span class="name" title="' + escapeHtml(name) + '" style="color:' + color.text + '">' + escapeHtml(name) + '</span>' +
                           '<span class="name-collapsed" title="' + escapeHtml(name) + '" style="background:' + color.bg + ';color:' + color.text + '">' + escapeHtml(firstChar) + '</span>' +
                           '<span><span class="badge" id="badge-' + name + '" style="background:' + color.badge + '">' +
                           (info.type || "· · ·") + '</span></span>';
            li.addEventListener("click", function() { selectVariable(name, li, idx); });
            varList.appendChild(li);
        });
        activeVarIndex = names.length > 0 ? 0 : -1;
        setTimeout(updateTogglePosition, 100);
    }

    function selectVariable(name, liEl, idx) {
        document.querySelectorAll(".var-item").forEach(function(el) {
            el.classList.remove("active");
        });
        liEl.classList.add("active");
        if (typeof idx === "number") {
            activeVarIndex = idx;
            updateTogglePosition();
        }
        contentArea.innerHTML = '<div class="placeholder"><div class="loading"></div><span>加载中…</span></div>';

        if (dataCache[name]) {
            currentVarData = dataCache[name];
            currentVarData._varName = name;
            renderVariable(name, dataCache[name]);
            return;
        }

        fetch("/variable/" + encodeURIComponent(name))
            .then(function(r) { return r.json(); })
            .then(function(data) {
                if (data.error) {
                    contentArea.innerHTML = '<div class="placeholder" style="color:var(--danger)">' +
                                            escapeHtml(data.error) + '</div>';
                    return;
                }
                data._varName = name;
                currentVarData = data;
                dataCache[name] = data;
                renderVariable(name, data);
            })
            .catch(function(err) {
                contentArea.innerHTML = '<div class="placeholder" style="color:var(--danger)">' +
                                        '请求失败: ' + escapeHtml(String(err)) + '</div>';
            });
    }

    /* ==================== 渲染变量 ==================== */
    function renderVariable(name, data) {
        var renderStart = performance.now();
        var views = getViewTypes(data);
        var html = '<div class="var-detail">';
        html += '<h2>' + escapeHtml(name) + '</h2>';
        html += '<div class="var-meta">' + describeType(data) + '</div>';
        html += '</div>';
        if (views.length) {
            html += '<div class="controls">';
            views.forEach(function(v, i) {
                html += '<button class="btn' + (i === 0 ? ' active' : '') +
                        '" data-view="' + v.key + '">' + v.label + '</button>';
            });
            html += '</div>';
        }
        html += '<div id="vizBox"></div>';
        html += '<div id="statusBar" class="status-bar" style="display:none;"></div>';
        contentArea.innerHTML = html;
        contentArea.querySelectorAll(".controls .btn").forEach(function(btn) {
            btn.addEventListener("click", function() {
                contentArea.querySelectorAll(".controls .btn").forEach(function(b) {
                    b.classList.remove("active");
                });
                this.classList.add("active");
                drawView(data, this.dataset.view);
            });
        });
        if (views.length) {
            drawView(data, views[0].key, function() {
            });
        } else {
            drawFallback(data);
        }
        var badge = document.getElementById("badge-" + name);
        if (badge) badge.textContent = data.dtype || data.type;
    }

    /* ==================== 视图类型 ==================== */
    function getViewTypes(d) {
        var v = [];
        if (d.type === "ndarray") {
            if (d.ndim === 1) {
                v.push({ key: "line", label: "📈 折线图" });
                v.push({ key: "bar", label: "📊 柱状图" });
                v.push({ key: "hist", label: "📉 直方图" });
                v.push({ key: "table", label: "📋 表格" });
            } else if (d.ndim === 2) {
                var r = d.shape ? d.shape[0] : 0;
                var c = d.shape ? d.shape[1] : 0;
                if (r <= 100 && c <= 100) v.push({ key: "heatmap", label: "🗺️ 热力图" });
                if (c <= 20) v.push({ key: "multiline", label: "📈 多线图" });
                if (isPlottable(d)) v.push({ key: "plot", label: "📐 绘图" });
                v.push({ key: "table", label: "📋 表格" });
            } else {
                v.push({ key: "heatmap", label: "🗺️ 切片热力图" });
                v.push({ key: "table", label: "📋 表格" });
            }
        } else if (d.type === "scalar") {
            v.push({ key: "gauge", label: "🎯 仪表盘" });
        } else if (d.type === "struct") {
            v.push({ key: "tree", label: "🌳 结构树" });
        } else if (d.type === "string") {
            v.push({ key: "text", label: "📝 文本" });
        } else if (d.type === "cell") {
            v.push({ key: "cellview", label: "📦 Cell视图" });
        }
        return v;
    }

    function isPlottable(d) {
        if (d.type !== "ndarray" || d.ndim !== 2) return false;
        if (!d.values || !Array.isArray(d.values)) return false;
        var sample = d.values[0];
        if (Array.isArray(sample)) {
            return sample.length > 0 && typeof sample[0] === "number";
        }
        return typeof sample === "number";
    }

    /* ==================== 绘图调度 ==================== */
    function drawView(data, viewType, onDone) {
        var box = document.getElementById("vizBox");
        if (!box) return;
        if (lastPlotBox === box) { Plotly.purge(box); }
        lastPlotBox = box;
        showStatus("");
        switch (viewType) {
            case "line":      drawLine(box, data, onDone);      break;
            case "bar":       drawBar(box, data, onDone);       break;
            case "hist":      drawHist(box, data, onDone);      break;
            case "heatmap":   drawHeatmap(box, data, onDone);   break;
            case "multiline": drawMultiLine(box, data, onDone); break;
            case "plot":      drawPlot(box, data, onDone);      break;
            case "table":     drawTable(box, data, onDone);     break;
            case "gauge":     drawGauge(box, data, onDone);     break;
            case "tree":      drawTree(box, data, onDone);      break;
            case "text":      drawText(box, data, onDone);      break;
            case "cellview":  drawCellView(box, data, onDone);  break;
            default:          drawFallback(box, data, onDone);
        }
    }

    /* ==================== 工具函数 ==================== */
    function darkLayout(title) {
        return {
            paper_bgcolor: "rgba(0,0,0,0)",
            plot_bgcolor: "rgba(0,0,0,0)",
            font: { color: "#cbd5e1", family: "Segoe UI, system-ui, sans-serif" },
            xaxis: { gridcolor: "#334155", zerolinecolor: "#475569" },
            yaxis: { gridcolor: "#334155", zerolinecolor: "#475569" },
            margin: { t: 30, b: 50, l: 60, r: 100 },
            legend: { 
                bgcolor: "rgba(15,23,42,0.9)", 
                x: 1.02, 
                y: 0.5, 
                xanchor: "left", 
                yanchor: "middle",
                bordercolor: "#334155",
                borderwidth: 1,
                font: { color: "#cbd5e1" }
            }
        };
    }

    function cleanValues(arr) {
        if (!Array.isArray(arr)) return arr;
        return arr.map(function(v) {
            if (typeof v === "number" && (isNaN(v) || !isFinite(v))) return null;
            if (Array.isArray(v)) return cleanValues(v);
            return v;
        });
    }

    function describeType(d) {
        if (d.type === "ndarray") {
            return 'ndarray [' + (d.shape || []).join(" × ") + '] · ' +
                   (d.dtype || "") + ' · ' + (d.size || 0) + ' 元素';
        }
        if (d.type === "scalar") return '标量 · ' + (d.dtype || "");
        if (d.type === "string") return '字符串 · ' + (d.value ? d.value.length : 0) + ' 字符';
        if (d.type === "struct") {
            var f = Object.keys(d.fields || {});
            return '结构体 · ' + f.length + ' 个字段';
        }
        if (d.type === "array") return '数组';
        if (d.type === "cell") {
            return 'Cell数组 · ' + (d.size || (d.value ? d.value.length : 0)) + ' 个元素';
        }
        return d.type || "未知类型";
    }

    function formatVal(v) {
        if (v === null || v === undefined) return '<span style="color:var(--text-dim)">null</span>';
        if (typeof v === "number") {
            if (isNaN(v) || !isFinite(v)) return '<span style="color:var(--text-dim)">NaN</span>';
            if (Number.isInteger(v)) return String(v);
            return parseFloat(v.toPrecision(8)).toString();
        }
        return escapeHtml(String(v));
    }

    function escapeHtml(s) {
        if (s === null || s === undefined) return '';
        var div = document.createElement("div");
        div.textContent = String(s);
        return div.innerHTML;
    }

    function sanitizeInput(str, maxLength) {
        if (str === null || str === undefined) return '';
        maxLength = maxLength || 1000;
        return String(str).substring(0, maxLength).replace(/[<>]/g, '');
    }

    function safeJsonParse(str, defaultValue) {
        try {
            return JSON.parse(str);
        } catch (e) {
            return defaultValue;
        }
    }

    function showStatus(text) {
        var bar = document.getElementById("statusBar");
        if (bar) {
            bar.style.display = "flex";
            bar.innerHTML = '<span>' + text + '</span>';
        }
    }

    /* ==================== 折线图 ==================== */
    function drawLine(box, d, onDone) {
        var vals = cleanValues(d.values);
        var MAX_POINTS = 10000;
        var sampled = vals;
        if (vals.length > MAX_POINTS) {
            var step = Math.ceil(vals.length / MAX_POINTS);
            sampled = [];
            for (var i = 0; i < vals.length; i += step) sampled.push(vals[i]);
        }
        var trace = {
            y: sampled,
            type: "scatter",
            mode: "lines+markers",
            line: { color: "#38bdf8", width: 2 },
            marker: { size: 3 }
        };
        var layout = darkLayout("折线图" + (sampled.length < vals.length ? " (采样 " + sampled.length + "/" + vals.length + " 点)" : ""));
        layout.yaxis.title = "值";
        layout.xaxis.title = "索引";
        Plotly.newPlot(box, [trace], layout, { responsive: true, displayModeBar: false }).then(function() {
            if (onDone) onDone();
        });
        showStatus("显示 " + sampled.length + " 个数据点");
    }

    /* ==================== 柱状图 ==================== */
    function drawBar(box, d, onDone) {
        var vals = cleanValues(d.values);
        var MAX_BARS = 200;
        var sampled = vals;
        if (vals.length > MAX_BARS) {
            var step = Math.ceil(vals.length / MAX_BARS);
            sampled = [];
            for (var i = 0; i < vals.length; i += step) sampled.push(vals[i]);
        }
        var trace = {
            x: sampled.map(function(_, i) { return i; }),
            y: sampled,
            type: "bar",
            marker: {
                color: sampled.map(function(v) {
                    return (v !== null && v >= 0) ? "#4ade80" : "#f87171";
                })
            }
        };
        var layout = darkLayout("柱状图" + (sampled.length < vals.length ? " (采样)" : ""));
        layout.xaxis.title = "索引";
        layout.yaxis.title = "值";
        Plotly.newPlot(box, [trace], layout, { responsive: true, displayModeBar: false }).then(function() {
            if (onDone) onDone();
        });
        showStatus("显示 " + sampled.length + " 个柱形");
    }

    /* ==================== 直方图 ==================== */
    function drawHist(box, d, onDone) {
        var vals = cleanValues(d.values).filter(function(v) { return v !== null; });
        var trace = {
            x: vals,
            type: "histogram",
            nbinsx: Math.min(50, Math.ceil(Math.sqrt(vals.length))),
            marker: { color: "#a78bfa" }
        };
        var layout = darkLayout("直方图");
        layout.xaxis.title = "值";
        layout.yaxis.title = "频次";
        Plotly.newPlot(box, [trace], layout, { responsive: true, displayModeBar: false }).then(function() {
            if (onDone) onDone();
        });
    }

    /* ==================== 热力图 ==================== */
    function drawHeatmap(box, d, onDone) {
        var z;
        if (d.ndim === 2) {
            z = cleanValues(d.values);
        } else if (d.ndim >= 3 && d.slices && d.slices.length) {
            z = cleanValues(d.slices[0].data);
        } else {
            drawFallback(box, d, onDone);
            return;
        }
        var trace = {
            z: z,
            type: "heatmap",
            colorscale: "Viridis",
            colorbar: { tickfont: { color: "#94a3b8" } }
        };
        var layout = darkLayout("热力图");
        layout.xaxis = { gridcolor: "#334155", zerolinecolor: "#475569", title: "列" };
        layout.yaxis = { gridcolor: "#334155", zerolinecolor: "#475569", title: "行", autorange: "reversed" };
        Plotly.newPlot(box, [trace], layout, { responsive: true, displayModeBar: false }).then(function() {
            if (onDone) onDone();
        });
    }

    /* ==================== 多线图 ==================== */
    function drawMultiLine(box, d, onDone) {
        var vals = d.values;
        if (!vals || !vals.length || !Array.isArray(vals[0])) { drawFallback(box, d, onDone); return; }
        var numCols = vals[0].length;
        var palette = [
            "#38bdf8","#a78bfa","#4ade80","#f87171","#fbbf24",
            "#f472b6","#22d3ee","#a3e635","#fb923c","#818cf8",
            "#e879f9","#2dd4bf","#facc15","#c084fc","#34d399"
        ];
        var traces = [];
        for (var c = 0; c < numCols; c++) {
            var col = vals.map(function(row) {
                var v = Array.isArray(row) ? row[c] : row;
                return (typeof v === "number" && (isNaN(v) || !isFinite(v))) ? null : v;
            });
            traces.push({
                y: col,
                type: "scatter",
                mode: "lines",
                name: "列 " + c,
                line: { color: palette[c % palette.length], width: 1.5 }
            });
        }
        var layout = darkLayout("多列折线图");
        layout.yaxis.title = "值";
        layout.xaxis.title = "行索引";
        layout.legend = { font: { size: 10 }, bgcolor: "rgba(0,0,0,0)" };
        Plotly.newPlot(box, traces, layout, { responsive: true, displayModeBar: false }).then(function() {
            if (onDone) onDone();
        });
    }

    /* ==================== 表格（虚拟滚动+滑块+搜索） ==================== */
    function drawTable(box, d, onDone) {
        tableState.currentVar = d;
        tableState.rowOffset = 0;
        tableState.colOffset = 0;
        tableState.rowLimit = 50;
        tableState.colLimit = 20;
        tableState.totalRows = d.shape ? d.shape[0] : 0;
        tableState.totalCols = d.shape && d.shape.length > 1 ? d.shape[1] : 1;
        tableState.searchResults = [];
        tableState.highlightCell = null;
        renderTableView(box, d);
        if (onDone) onDone();
    }

    function renderTableView(box, d) {
        var renderStart = performance.now();
        var values, rows, cols;
        if (d.ndim === 1) {
            values = d.values.map(function(v) { return [v]; });
            rows = d.values.length;
            cols = 1;
        } else if (d.ndim === 2) {
            values = d.values;
            rows = d.shape[0];
            cols = d.shape[1];
        } else {
            box.innerHTML = '<p style="color:var(--text-dim)">高维数据请切换其他视图</p>';
            return;
        }

        var isLarge = rows > 500 || cols > 100;
        var html = '';

        if (isLarge) {
            html += '<div class="table-controls">';
            html += '<div class="control-group">';
            html += '<label>行:</label>';
            html += '<input type="number" id="gotoRow" min="0" max="' + (rows-1) + '" placeholder="0-' + (rows-1) + '">';
            html += '<button class="btn" id="btnGotoRow">跳转</button>';
            html += '</div>';
            html += '<div class="control-group">';
            html += '<label>列:</label>';
            html += '<input type="number" id="gotoCol" min="0" max="' + (cols-1) + '" placeholder="0-' + (cols-1) + '">';
            html += '<button class="btn" id="btnGotoCol">跳转</button>';
            html += '</div>';
            html += '<div class="control-group">';
            html += '<label>搜索值:</label>';
            html += '<input type="text" id="searchVal" placeholder="数值">';
            html += '<button class="btn" id="btnSearch">搜索</button>';
            html += '</div>';
            html += '</div>';

            html += '<div class="slider-container">';
            html += '<label>行滑块:</label>';
            html += '<input type="range" id="rowSlider" min="0" max="' + (rows-1) + '" value="' + tableState.rowOffset + '" step="1">';
            html += '<span class="slider-value" id="rowSliderVal">行 ' + tableState.rowOffset + '-' + Math.min(tableState.rowOffset + tableState.rowLimit, rows) + ' / ' + rows + '</span>';
            html += '</div>';

            if (cols > 20) {
                html += '<div class="slider-container">';
                html += '<label>列滑块:</label>';
                html += '<input type="range" id="colSlider" min="0" max="' + (cols-1) + '" value="' + tableState.colOffset + '" step="1">';
                html += '<span class="slider-value" id="colSliderVal">列 ' + tableState.colOffset + '-' + Math.min(tableState.colOffset + tableState.colLimit, cols) + ' / ' + cols + '</span>';
                html += '</div>';
            }

            html += '<div id="searchResults"></div>';
        }

        html += '<div class="data-table-wrap" id="tableWrap"><table><thead><tr><th>#</th>';
        var startCol = tableState.colOffset;
        var endCol = Math.min(startCol + tableState.colLimit, cols);
        for (var c = startCol; c < endCol; c++) html += '<th>' + c + '</th>';
        html += '</tr></thead><tbody>';

        var startRow = tableState.rowOffset;
        var endRow = Math.min(startRow + tableState.rowLimit, rows);
        for (var r = startRow; r < endRow; r++) {
            html += '<tr><td>' + r + '</td>';
            for (var j = startCol; j < endCol; j++) {
                var v = values[r] ? values[r][j] : "";
                var cellClass = '';
                if (tableState.highlightCell && tableState.highlightCell[0] === r && tableState.highlightCell[1] === j) {
                    cellClass = ' class="highlight-cell"';
                }
                html += '<td' + cellClass + '>' + formatVal(v) + '</td>';
            }
            html += '</tr>';
        }
        html += '</tbody></table></div>';

        if (isLarge) {
            html += '<div class="pagination">';
            html += '<button class="btn" id="prevRow">◀ 上一屏行</button>';
            html += '<span class="page-info">行 ' + (startRow + 1) + '-' + endRow + ' / 共 ' + rows + ' 行</span>';
            html += '<button class="btn" id="nextRow">下一屏行 ▶</button>';
            if (cols > 20) {
                html += '<button class="btn" id="prevCol">◀ 上一屏列</button>';
                html += '<span class="page-info">列 ' + (startCol + 1) + '-' + endCol + ' / 共 ' + cols + ' 列</span>';
                html += '<button class="btn" id="nextCol">下一屏列 ▶</button>';
            }
            html += '</div>';
        }

        html += '<div class="export-panel" id="exportPanel">';
        html += '<h4>📤 导出数据</h4>';
        html += '<div class="export-options">';
        html += '<div class="export-option"><label>表头模板 (留空=无表头)</label>';
        html += '<input type="text" id="exportHeader" placeholder="例: %VarName_Col%Col_num"></div>';
        html += '<div class="export-option"><label>行范围</label>';
        html += '<div style="display:flex;gap:4px"><input type="number" id="exportRowStart" value="0" min="0" max="' + (rows-1) + '" style="width:70px">';
        html += '<span style="color:var(--text-dim);line-height:30px">-</span>';
        html += '<input type="number" id="exportRowEnd" value="' + rows + '" min="1" max="' + rows + '" style="width:70px"></div></div>';
        html += '<div class="export-option"><label>列范围</label>';
        html += '<div style="display:flex;gap:4px"><input type="number" id="exportColStart" value="0" min="0" max="' + (cols-1) + '" style="width:70px">';
        html += '<span style="color:var(--text-dim);line-height:30px">-</span>';
        html += '<input type="number" id="exportColEnd" value="' + cols + '" min="1" max="' + cols + '" style="width:70px"></div></div>';
        html += '<div class="export-option" style="justify-content:flex-end"><label><input type="checkbox" id="exportRowIndex"> 添加行号列</label></div>';
        html += '<div class="export-option" style="justify-content:flex-end"><label><input type="checkbox" id="exportTrimNulls"> 自动裁剪null/nan/空值</label></div>';
        html += '</div>';
        html += '<div class="export-btns">';
        html += '<button class="export-btn csv" data-fmt="csv">📄 导出CSV（以逗号分割）</button>';
        html += '<button class="export-btn xlsx" data-fmt="xlsx">📊 导出Excel</button>';
        html += '<button class="export-btn txt" data-fmt="txt">📝 导出TXT</button>';
        html += '<button class="export-btn npy" data-fmt="npy">🔢 导出NPY</button>';
        html += '<button class="export-btn mat" data-fmt="mat">💾 导出MAT</button>';
        html += '</div>';
        html += '<div class="export-hint">';
        html += '💡 表头占位符: <code>%Row_num</code> 行号, <code>%Col_num</code> 列号, <code>%VarName</code> 变量名';
        html += ' | 示例: <code>Data_%Col_num</code> → Data_0, Data_1... | <code>%VarName_row%Row_num</code> → myVar_row0';
        html += '</div></div>';

        box.innerHTML = html;

        if (isLarge) {
            var rowSlider = document.getElementById("rowSlider");
            var colSlider = document.getElementById("colSlider");
            var rowSliderVal = document.getElementById("rowSliderVal");
            var colSliderVal = document.getElementById("colSliderVal");

            if (rowSlider) {
                rowSlider.addEventListener("input", function() {
                    tableState.rowOffset = parseInt(this.value);
                    if (rowSliderVal) {
                        var end = Math.min(tableState.rowOffset + tableState.rowLimit, rows);
                        rowSliderVal.textContent = '行 ' + (tableState.rowOffset + 1) + '-' + end + ' / ' + rows;
                    }
                });
                rowSlider.addEventListener("change", function() {
                    renderTableView(box, d);
                });
            }

            if (colSlider) {
                colSlider.addEventListener("input", function() {
                    tableState.colOffset = parseInt(this.value);
                    if (colSliderVal) {
                        var end = Math.min(tableState.colOffset + tableState.colLimit, cols);
                        colSliderVal.textContent = '列 ' + (tableState.colOffset + 1) + '-' + end + ' / ' + cols;
                    }
                });
                colSlider.addEventListener("change", function() {
                    renderTableView(box, d);
                });
            }

            var btnGotoRow = document.getElementById("btnGotoRow");
            if (btnGotoRow) {
                btnGotoRow.addEventListener("click", function() {
                    var rowInput = document.getElementById("gotoRow");
                    var targetRow = parseInt(rowInput.value);
                    if (!isNaN(targetRow) && targetRow >= 0 && targetRow < rows) {
                        tableState.rowOffset = Math.max(0, targetRow - Math.floor(tableState.rowLimit / 2));
                        tableState.highlightCell = [targetRow, tableState.colOffset];
                        renderTableView(box, d);
                    }
                });
            }

            var btnGotoCol = document.getElementById("btnGotoCol");
            if (btnGotoCol) {
                btnGotoCol.addEventListener("click", function() {
                    var colInput = document.getElementById("gotoCol");
                    var targetCol = parseInt(colInput.value);
                    if (!isNaN(targetCol) && targetCol >= 0 && targetCol < cols) {
                        tableState.colOffset = Math.max(0, targetCol - Math.floor(tableState.colLimit / 2));
                        tableState.highlightCell = [tableState.rowOffset, targetCol];
                        renderTableView(box, d);
                    }
                });
            }

            var btnSearch = document.getElementById("btnSearch");
            if (btnSearch) {
                btnSearch.addEventListener("click", function() {
                    var searchInput = document.getElementById("searchVal");
                    var searchVal = searchInput.value.trim();
                    if (searchVal === '') return;

                    var targetNum = parseFloat(searchVal);
                    var results = [];
                    var maxResults = 50;

                    for (var r = 0; r < rows && results.length < maxResults; r++) {
                        for (var c = 0; c < cols && results.length < maxResults; c++) {
                            var cellVal = values[r] ? values[r][c] : null;
                            if (cellVal === null || cellVal === undefined) continue;
                            if (!isNaN(targetNum)) {
                                if (Math.abs(cellVal - targetNum) < 0.0001) {
                                    results.push([r, c, cellVal]);
                                }
                            } else {
                                if (String(cellVal).indexOf(searchVal) !== -1) {
                                    results.push([r, c, cellVal]);
                                }
                            }
                        }
                    }

                    tableState.searchResults = results;
                    var resultsDiv = document.getElementById("searchResults");
                    if (results.length === 0) {
                        resultsDiv.innerHTML = '<div class="search-results" id="searchNoResult" style="color:var(--danger);border-color:var(--danger)">未找到匹配的值</div>';
                        setTimeout(function() {
                            var el = document.getElementById("searchNoResult");
                            if (el) {
                                el.style.opacity = "0";
                                setTimeout(function() { if (el.parentNode) el.parentNode.removeChild(el); }, 300);
                            }
                        }, 2500);
                    } else {
                        var resHtml = '<div class="search-results">找到 ' + results.length + ' 个匹配 (最多' + maxResults + '): ';
                        results.forEach(function(res, idx) {
                            resHtml += '<span class="result-item" data-idx="' + idx + '">[' + res[0] + ',' + res[1] + ']=' + res[2] + '</span> ';
                        });
                        resHtml += '</div>';
                        resultsDiv.innerHTML = resHtml;

                        resultsDiv.querySelectorAll(".result-item").forEach(function(item) {
                            item.addEventListener("click", function() {
                                var idx = parseInt(this.dataset.idx);
                                var res = results[idx];
                                tableState.highlightCell = [res[0], res[1]];
                                tableState.rowOffset = Math.max(0, res[0] - Math.floor(tableState.rowLimit / 2));
                                tableState.colOffset = Math.max(0, res[1] - Math.floor(tableState.colLimit / 2));
                                renderTableView(box, d);
                            });
                        });
                    }
                });
            }

            var prevRowBtn = document.getElementById("prevRow");
            if (prevRowBtn) {
                prevRowBtn.addEventListener("click", function() {
                    tableState.rowOffset = Math.max(0, tableState.rowOffset - tableState.rowLimit);
                    renderTableView(box, d);
                });
            }

            var nextRowBtn = document.getElementById("nextRow");
            if (nextRowBtn) {
                nextRowBtn.addEventListener("click", function() {
                    tableState.rowOffset = Math.min(rows - tableState.rowLimit, tableState.rowOffset + tableState.rowLimit);
                    renderTableView(box, d);
                });
            }

            var prevColBtn = document.getElementById("prevCol");
            if (prevColBtn) {
                prevColBtn.addEventListener("click", function() {
                    tableState.colOffset = Math.max(0, tableState.colOffset - tableState.colLimit);
                    renderTableView(box, d);
                });
            }

            var nextColBtn = document.getElementById("nextCol");
            if (nextColBtn) {
                nextColBtn.addEventListener("click", function() {
                    tableState.colOffset = Math.min(cols - tableState.colLimit, tableState.colOffset + tableState.colLimit);
                    renderTableView(box, d);
                });
            }
        } else {
            var prevBtn = document.getElementById("prevPage");
            var nextBtn = document.getElementById("nextPage");
            if (prevBtn) {
                prevBtn.addEventListener("click", function() {
                    tableState.rowOffset = Math.max(0, tableState.rowOffset - tableState.rowLimit);
                    renderTableView(box, d);
                });
            }
            if (nextBtn) {
                nextBtn.addEventListener("click", function() {
                    tableState.rowOffset = Math.min(rows - tableState.rowLimit, tableState.rowOffset + tableState.rowLimit);
                    renderTableView(box, d);
                });
            }
        }

        var exportVarName = d._varName || currentVarData._varName || name;
        var exportBtns = document.querySelectorAll(".export-btn");
        exportBtns.forEach(function(btn) {
            btn.addEventListener("click", function() {
                var fmt = this.dataset.fmt;
                var headerTpl = document.getElementById("exportHeader").value.trim();
                var rowStart = parseInt(document.getElementById("exportRowStart").value) || 0;
                var rowEnd = parseInt(document.getElementById("exportRowEnd").value) || rows;
                var colStart = parseInt(document.getElementById("exportColStart").value) || 0;
                var colEnd = parseInt(document.getElementById("exportColEnd").value) || cols;
                var rowIndex = document.getElementById("exportRowIndex").checked;
                var trimNulls = document.getElementById("exportTrimNulls").checked;

                if (headerTpl) {
                    var validPlaceholders = ["%Row_num", "%Col_num", "%VarName"];
                    var placeholderRegex = /%[A-Za-z_]\w*/g;
                    var foundPlaceholders = headerTpl.match(placeholderRegex) || [];
                    var invalidPlaceholders = foundPlaceholders.filter(function(p) {
                        return validPlaceholders.indexOf(p) === -1;
                    });
                    if (invalidPlaceholders.length > 0) {
                        alert("表头模板包含无效的占位符: " + invalidPlaceholders.join(", ") + "\n\n有效占位符: %Row_num, %Col_num, %VarName");
                        return;
                    }
                    var invalidChars = /[<>{}\\|]/;
                    if (invalidChars.test(headerTpl)) {
                        alert("表头模板包含非法字符: < > { } \\ |");
                        return;
                    }
                }

                rowStart = Math.max(0, Math.min(rowStart, rows));
                rowEnd = Math.max(rowStart + 1, Math.min(rowEnd, rows));
                colStart = Math.max(0, Math.min(colStart, cols));
                colEnd = Math.max(colStart + 1, Math.min(colEnd, cols));

                var payload = {
                    format: fmt,
                    header: headerTpl || null,
                    row_index: rowIndex,
                    trim_nulls: trimNulls,
                    row_start: rowStart,
                    row_end: rowEnd,
                    col_start: colStart,
                    col_end: colEnd
                };

                this.textContent = "导出中...";
                this.disabled = true;

                fetch("/export/" + encodeURIComponent(exportVarName), {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(payload)
                })
                .then(function(r) {
                    if (!r.ok) return r.json().then(function(d) { throw new Error(d.error || "导出失败"); });
                    return r.blob();
                })
                .then(function(blob) {
                    var url = URL.createObjectURL(blob);
                    var a = document.createElement("a");
                    a.href = url;
                    var ext = fmt === "xlsx" ? "xlsx" : fmt === "npy" ? "npy" : fmt === "txt" ? "txt" : "csv";
                    a.download = exportVarName + "." + ext;
                    document.body.appendChild(a);
                    a.click();
                    document.body.removeChild(a);
                    URL.revokeObjectURL(url);
                })
                .catch(function(err) {
                    alert("导出失败: " + err.message);
                })
                .finally(function() {
                    var labels = { csv: "📄 导出CSV（以逗号分割）", xlsx: "📊 导出Excel", txt: "📝 导出TXT", npy: "🔢 导出NPY", mat: "💾 导出MAT" };
                    btn.textContent = labels[fmt] || "导出";
                    btn.disabled = false;
                });
            });
        });

        var statusText = "表格视图：显示 " + (endRow - startRow) + " 行 × " + (endCol - startCol) + " 列 / 共 " + rows + " 行 × " + cols + " 列";
        if (d.load_time) {
            statusText += " | 数据加载: " + d.load_time + "s";
        }
        var renderTime = ((performance.now() - renderStart) / 1000).toFixed(3);
        statusText += " | 渲染耗时: " + renderTime + "s";
        showStatus(statusText);
    }

    /* ==================== 仪表盘 ==================== */
    function drawGauge(box, d, onDone) {
        var val = d.value;
        var displayText;
        if (d.dtype === "complex") {
            var mag = Math.sqrt(val.real * val.real + val.imag * val.imag);
            displayText = val.real + " + " + val.imag + "i";
            val = mag;
        } else if (d.dtype === "bool") {
            displayText = String(val);
            val = val ? 1 : 0;
        } else {
            displayText = String(val);
        }
        if (typeof val !== "number" || isNaN(val)) val = 0;
        var lo = Math.min(0, val) - Math.abs(val) * 0.5 - 1;
        var hi = Math.max(0, val) + Math.abs(val) * 0.5 + 1;
        var trace = {
            type: "indicator",
            mode: "gauge+number",
            value: val,
            title: { text: displayText, font: { size: 20, color: "#e2e8f0" } },
            number: { font: { color: "#e2e8f0", size: 32 } },
            gauge: {
                axis: { range: [lo, hi], tickcolor: "#475569" },
                bar: { color: "#38bdf8" },
                bgcolor: "#1e293b",
                bordercolor: "#334155"
            }
        };
        var layout = {
            paper_bgcolor: "rgba(0,0,0,0)",
            font: { color: "#e2e8f0" },
            margin: { t: 50, b: 20, l: 40, r: 40 },
            height: 320
        };
        Plotly.newPlot(box, [trace], layout, { responsive: true, displayModeBar: false }).then(function() {
            if (onDone) onDone();
        });
    }

    /* ==================== 结构树 ==================== */
    function drawTree(box, d, onDone) {
        var fields = d.fields || {};
        var keys = Object.keys(fields);
        if (!keys.length) { box.innerHTML = "<p>空结构体</p>"; if (onDone) onDone(); return; }
        var html = "";
        keys.forEach(function(fname) {
            var f = fields[fname];
            html += '<div class="struct-field">';
            html += '<div class="field-name">🔹 ' + escapeHtml(fname) + '</div>';
            html += '<div class="field-info">' + describeType(f) + '</div>';
            if (f.type === "scalar") {
                html += '<div class="field-value">= <strong>' +
                        escapeHtml(JSON.stringify(f.value)) + '</strong></div>';
            } else if (f.type === "string") {
                var preview = f.value;
                if (preview && preview.length > 120) preview = preview.substring(0, 120) + "…";
                html += '<div class="field-value">= "' + escapeHtml(preview || "") + '"</div>';
            } else if (f.type === "ndarray") {
                html += '<div class="field-info">shape [' +
                        (f.shape || []).join(", ") + '] · ' + (f.dtype || "") + '</div>';
            } else if (f.type === "struct") {
                var subKeys = Object.keys(f.fields || {});
                html += '<div class="field-info">嵌套结构体，含 ' + subKeys.length +
                        ' 个字段: ' + escapeHtml(subKeys.join(", ")) + '</div>';
            }
            html += '</div>';
        });
        box.innerHTML = html;
        if (onDone) onDone();
    }

    /* ==================== 文本 ==================== */
    function drawText(box, d, onDone) {
        var val = d.value || "";
        box.innerHTML = '<pre class="text-block">' + escapeHtml(val) + '</pre>';
        if (onDone) onDone();
    }

    function drawCellView(box, d, onDone) {
        var html = '<div class="cell-view">';
        if (d.lazy) {
            html += '<p class="placeholder">Cell数组过大，请先加载完整数据</p>';
        } else if (d.value && Array.isArray(d.value)) {
            html += '<div class="cell-list">';
            d.value.forEach(function(item, idx) {
                html += '<div class="cell-item">';
                html += '<div class="cell-index">{' + idx + '}</div>';
                html += '<div class="cell-content">';
                if (item.type === "scalar") {
                    html += '<span class="cell-scalar">' + escapeHtml(String(item.value)) + '</span>';
                } else if (item.type === "string") {
                    html += '<span class="cell-string">"' + escapeHtml(String(item.value).substring(0, 100)) + '"</span>';
                } else if (item.type === "ndarray") {
                    html += '<span class="cell-ndarray">ndarray ' + JSON.stringify(item.shape) + ' (' + item.dtype + ')</span>';
                } else if (item.type === "struct") {
                    var fields = Object.keys(item.fields || {}).join(", ");
                    html += '<span class="cell-struct">struct {' + escapeHtml(fields) + '}</span>';
                } else if (item.type === "cell") {
                    html += '<span class="cell-cell">cell {' + (item.size || item.value.length) + '}</span>';
                } else {
                    html += '<span class="cell-unknown">' + escapeHtml(item.type || "unknown") + '</span>';
                }
                html += '</div></div>';
            });
            html += '</div>';
        } else if (d.values && Array.isArray(d.values)) {
            html += '<div class="cell-grid">';
            d.values.forEach(function(item, idx) {
                html += '<div class="cell-item">';
                html += '<div class="cell-index">{' + idx + '}</div>';
                html += '<div class="cell-content">';
                if (item.type === "scalar") {
                    html += '<span class="cell-scalar">' + escapeHtml(String(item.value)) + '</span>';
                } else if (item.type === "string") {
                    html += '<span class="cell-string">"' + escapeHtml(String(item.value).substring(0, 100)) + '"</span>';
                } else if (item.type === "ndarray") {
                    html += '<span class="cell-ndarray">ndarray ' + JSON.stringify(item.shape) + ' (' + item.dtype + ')</span>';
                } else if (item.type === "struct") {
                    var fields = Object.keys(item.fields || {}).join(", ");
                    html += '<span class="cell-struct">struct {' + escapeHtml(fields) + '}</span>';
                } else {
                    html += '<span class="cell-unknown">' + escapeHtml(item.type || "unknown") + '</span>';
                }
                html += '</div></div>';
            });
            html += '</div>';
        } else {
            html += '<p class="placeholder">无法解析Cell数组</p>';
        }
        html += '</div>';
        box.innerHTML = html;
        if (onDone) onDone();
    }

    /* ==================== Fallback ==================== */
    function drawFallback(box, d, onDone) {
        box.innerHTML = '<pre class="json-block">' +
                        escapeHtml(JSON.stringify(d, null, 2)) + '</pre>';
        if (onDone) onDone();
    }

    /* ==================== 绘图（网格+插值） ==================== */
    var plotState = {
        currentVar: null,
        plotType: "mesh",
        interpMethod: "none",
        colorScheme: "Viridis",
        colorDir: "正向",
        rowHighlight: null,
        colHighlight: null,
        isRendering: false,
        renderTimeout: null,
        renderStartTime: null,
        renderTimerInterval: null,
        renderGeneration: 0,
        plotZoom: 1,
        plotRotation: 0,
        loadTime: 0,
        viewportSyncTimer: null
    };

    function clamp(value, min, max) {
        return Math.max(min, Math.min(max, value));
    }

    function normalizeRotation(rotation) {
        var normalized = rotation % 360;
        return normalized < 0 ? normalized + 360 : normalized;
    }

    function getPlotViewportPadding() {
        var modebarHost = document.getElementById("plotModebarHost");
        var bottomPadding = 72;
        if (modebarHost && modebarHost.offsetHeight) {
            bottomPadding = Math.max(72, modebarHost.offsetHeight + 24);
        }
        return { top: 56, right: 24, bottom: bottomPadding, left: 24 };
    }

    function getPlotFocus(scrollContainer) {
        if (!scrollContainer) return { x: 0.5, y: 0.5 };
        var scrollWidth = Math.max(scrollContainer.scrollWidth, scrollContainer.clientWidth);
        var scrollHeight = Math.max(scrollContainer.scrollHeight, scrollContainer.clientHeight);
        return {
            x: scrollWidth <= scrollContainer.clientWidth ? 0.5 :
                (scrollContainer.scrollLeft + scrollContainer.clientWidth / 2) / scrollWidth,
            y: scrollHeight <= scrollContainer.clientHeight ? 0.5 :
                (scrollContainer.scrollTop + scrollContainer.clientHeight / 2) / scrollHeight
        };
    }

    function restorePlotFocus(scrollContainer, focus) {
        if (!scrollContainer || !focus) return;
        var maxLeft = Math.max(0, scrollContainer.scrollWidth - scrollContainer.clientWidth);
        var maxTop = Math.max(0, scrollContainer.scrollHeight - scrollContainer.clientHeight);
        scrollContainer.scrollLeft = clamp(focus.x * scrollContainer.scrollWidth - scrollContainer.clientWidth / 2, 0, maxLeft);
        scrollContainer.scrollTop = clamp(focus.y * scrollContainer.scrollHeight - scrollContainer.clientHeight / 2, 0, maxTop);
    }

    function getTransformedPlotSize(width, height) {
        var radians = normalizeRotation(plotState.plotRotation) * Math.PI / 180;
        var cos = Math.abs(Math.cos(radians));
        var sin = Math.abs(Math.sin(radians));
        return {
            width: (width * cos + height * sin) * plotState.plotZoom,
            height: (width * sin + height * cos) * plotState.plotZoom
        };
    }

    function syncPlotViewport(forceCenter) {
        var scrollContainer = document.querySelector(".plot-scroll-container");
        var scrollContent = document.querySelector(".plot-scroll-content");
        var transformWrapper = document.getElementById("plotTransformWrapper");
        var innerCanvas = document.getElementById("plotInnerCanvas");
        if (!scrollContainer || !scrollContent || !transformWrapper || !innerCanvas) return;

        var plotlyPlot = innerCanvas.querySelector(".js-plotly-plot");
        var baseWidth = Math.max(plotlyPlot ? plotlyPlot.offsetWidth : innerCanvas.offsetWidth, 320);
        var baseHeight = Math.max(plotlyPlot ? plotlyPlot.offsetHeight : innerCanvas.offsetHeight, 240);
        if (!baseWidth || !baseHeight) return;

        var focus = forceCenter ? { x: 0.5, y: 0.5 } : getPlotFocus(scrollContainer);
        var transformedSize = getTransformedPlotSize(baseWidth, baseHeight);
        var padding = getPlotViewportPadding();
        var sceneWidth = Math.max(scrollContainer.clientWidth, Math.ceil(transformedSize.width + padding.left + padding.right));
        var sceneHeight = Math.max(scrollContainer.clientHeight, Math.ceil(transformedSize.height + padding.top + padding.bottom));
        var usableWidth = Math.max(sceneWidth - padding.left - padding.right, baseWidth);
        var usableHeight = Math.max(sceneHeight - padding.top - padding.bottom, baseHeight);

        scrollContent.style.width = sceneWidth + "px";
        scrollContent.style.height = sceneHeight + "px";

        transformWrapper.style.position = "absolute";
        transformWrapper.style.width = baseWidth + "px";
        transformWrapper.style.height = baseHeight + "px";
        transformWrapper.style.left = Math.round(padding.left + (usableWidth - baseWidth) / 2) + "px";
        transformWrapper.style.top = Math.round(padding.top + (usableHeight - baseHeight) / 2) + "px";

        innerCanvas.style.width = baseWidth + "px";
        innerCanvas.style.height = baseHeight + "px";
        transformWrapper.style.transformOrigin = "50% 50%";

        var transform = "";
        if (plotState.plotZoom !== 1) transform += "scale(" + plotState.plotZoom + ") ";
        if (normalizeRotation(plotState.plotRotation) !== 0) transform += "rotate(" + normalizeRotation(plotState.plotRotation) + "deg)";
        transformWrapper.style.transform = transform.trim();

        restorePlotFocus(scrollContainer, focus);
    }

    function schedulePlotViewportSync(forceCenter) {
        if (plotState.viewportSyncTimer) {
            clearTimeout(plotState.viewportSyncTimer);
        }
        plotState.viewportSyncTimer = setTimeout(function() {
            syncPlotViewport(forceCenter);
            updateModebarPosition();
            updateLegendPosition();
            plotState.viewportSyncTimer = null;
        }, 0);
    }

    window.addEventListener("resize", function() {
        schedulePlotViewportSync(false);
    });

    var customColorSchemes = [];

    var COLOR_SCHEMES = [
        { name: "Viridis", value: "Viridis" },
        { name: "Plasma", value: "Plasma" },
        { name: "Inferno", value: "Inferno" },
        { name: "Magma", value: "Magma" },
        { name: "Cividis", value: "Cividis" },
        { name: "YlOrRd", value: "YlOrRd" },
        { name: "Blues", value: "Blues" },
        { name: "Greens", value: "Greens" },
        { name: "Hot", value: "Hot" },
        { name: "Jet", value: "Jet" },
        { name: "Rainbow", value: "Rainbow" },
        { name: "Portland", value: "Portland" },
        { name: "Picnic", value: "Picnic" },
        { name: "RdBu", value: "RdBu" },
        { name: "Brwnyl", value: "Brwnyl" },
        { name: "Agsunset", value: "Agsunset" },
    ];

    function drawPlot(box, d, onDone) {
        plotState.currentVar = d;
        plotState.plotType = "mesh";
        plotState.interpMethod = "none";
        plotState.colorScheme = "Viridis";
        plotState.colorDir = "正向";
        plotState.rowHighlight = null;
        plotState.colHighlight = null;
        plotState.isRendering = false;
        plotState.renderGeneration = 0;
        if (plotState.renderTimeout) {
            clearTimeout(plotState.renderTimeout);
            plotState.renderTimeout = null;
        }
        if (plotState.renderTimerInterval) {
            clearInterval(plotState.renderTimerInterval);
            plotState.renderTimerInterval = null;
        }
        plotState.loadTime = d.load_time || 0;
        renderPlotView(box, d);
        if (onDone) onDone();
    }

    function renderPlotView(box, d) {
        var values = d.values;
        var rows = d.shape ? d.shape[0] : 0;
        var cols = d.shape && d.shape.length > 1 ? d.shape[1] : 1;

        var validation = validatePlotData(values, rows, cols);
        if (!validation.valid) {
            box.innerHTML = '<p style="color:var(--danger)">⚠️ ' + escapeHtml(validation.message) + '</p>';
            return;
        }

        var warningHtml = validation.warning ? 
            '<div id="plotWarning" style="text-align:center;color:#f59e0b;font-size:.75rem;margin-bottom:8px;transition:opacity 0.5s;">⚠️ ' + escapeHtml(validation.warning) + '</div>' : '';

        var html = warningHtml + '<div class="plot-controls">';
        html += '<div class="control-group">';
        html += '<label>绘图类型:</label>';
        html += '<select id="plotTypeSelect">';
        html += '<option value="mesh" selected>网格图</option>';
        html += '<option value="surface">3D曲面</option>';
        html += '<option value="contour">等高线</option>';
        html += '<option value="scatter">散点图</option>';
        html += '</select>';
        html += '</div>';
        html += '<div class="control-group">';
        html += '<label>插值算法:</label>';
        html += '<select id="interpSelect">';
        html += '<option value="none" selected>无插值</option>';
        html += '<option value="linear">双线性插值</option>';
        html += '<option value="cubic">双三次插值(Bicubic)</option>';
        html += '<option value="spline">样条插值(Spline)</option>';
        html += '<option value="lanczos">Lanczos插值</option>';
        html += '<option value="nearest">最近邻插值</option>';
        html += '</select>';
        html += '</div>';
        html += '<div class="control-group">';
        html += '<label>配色方案:</label>';
        html += '<select id="colorSchemeSelect">';
        COLOR_SCHEMES.forEach(function(scheme) {
            html += '<option value="' + scheme.value + '"' +
                    (scheme.value === plotState.colorScheme ? ' selected' : '') + '>' + scheme.name + '</option>';
        });
        html += '</select>';
        html += '<span class="color-actions">';
        html += '<label>方向:</label><select id="colorDirSelect"><option value="正向" selected>正向</option><option value="反向">反向</option></select>';
        html += '<button class="btn" id="btnCustomColor" title="自定义配色">🎨 自定义</button>';
        html += '</span>';
        html += '</div>';
        html += '<div class="control-group">';
        html += '<label>定位行:</label>';
        html += '<input type="number" id="plotGotoRow" min="0" max="' + (rows-1) + '" placeholder="0-' + (rows-1) + '">';
        html += '<button class="btn" id="btnPlotGotoRow">定位</button>';
        html += '</div>';
        html += '<div class="control-group">';
        html += '<label>定位列:</label>';
        html += '<input type="number" id="plotGotoCol" min="0" max="' + (cols-1) + '" placeholder="0-' + (cols-1) + '">';
        html += '<button class="btn" id="btnPlotGotoCol">定位</button>';
        html += '<button class="btn" id="btnCancelHighlight" title="取消定位">✖ 取消</button>';
        html += '</div>';
        html += '<div class="control-group" id="performanceInfo" style="display:none;">';
        html += '<label>性能统计:</label>';
        html += '<span id="perfStats" style="font-size:0.75rem;color:var(--text-dim);"></span>';
        html += '</div>';
        html += '</div>';
        
        var plotCanvas = document.createElement('div');
        plotCanvas.id = 'plotCanvas';
        plotCanvas.className = 'plot-canvas-wrapper';
        
        var titleContainer = document.createElement('div');
        titleContainer.className = 'plot-title-container';
        var titleText = document.createElement('div');
        titleText.className = 'plot-title-text';
        titleText.textContent = '绘图';
        titleContainer.appendChild(titleText);
        plotCanvas.appendChild(titleContainer);
        
        var zoomControls = document.createElement('div');
        zoomControls.className = 'plot-zoom-controls';
        zoomControls.innerHTML = '<button class="btn btn-sm" id="btnZoomOut" title="缩小显示">➖</button>' +
            '<span id="plotZoomLevel" style="color:var(--text-dim);font-size:.7rem;min-width:40px;text-align:center;">100%</span>' +
            '<button class="btn btn-sm" id="btnZoomIn" title="放大显示">➕</button>' +
            '<button class="btn btn-sm" id="btnResetView" title="重置视图">🔄</button>' +
            '<span style="width:1px;background:var(--border);margin:0 2px;"></span>' +
            '<button class="btn btn-sm" id="btnRotateCCW" title="逆时针旋转90°">↶</button>' +
            '<button class="btn btn-sm" id="btnRotateCW" title="顺时针旋转90°">↷</button>';
        plotCanvas.appendChild(zoomControls);
        
        var scrollContainer = document.createElement('div');
        scrollContainer.className = 'plot-scroll-container';
        var scrollContent = document.createElement('div');
        scrollContent.className = 'plot-scroll-content';
        var transformWrapper = document.createElement('div');
        transformWrapper.id = 'plotTransformWrapper';
        transformWrapper.className = 'plot-transform-wrapper';
        var innerCanvas = document.createElement('div');
        innerCanvas.id = 'plotInnerCanvas';
        innerCanvas.className = 'plot-content-area';
        
        transformWrapper.appendChild(innerCanvas);
        scrollContent.appendChild(transformWrapper);
        scrollContainer.appendChild(scrollContent);
        plotCanvas.appendChild(scrollContainer);

        var overlayLayer = document.createElement('div');
        overlayLayer.id = 'plotOverlayLayer';
        overlayLayer.className = 'plot-overlay-layer';
        var modebarHost = document.createElement('div');
        modebarHost.id = 'plotModebarHost';
        modebarHost.className = 'plot-modebar-host';
        overlayLayer.appendChild(modebarHost);
        plotCanvas.appendChild(overlayLayer);
        
        var fullscreenBtn = document.createElement('button');
        fullscreenBtn.className = 'btn btn-fs-plot';
        fullscreenBtn.id = 'btnFullscreenPlot';
        fullscreenBtn.title = '全屏绘图';
        fullscreenBtn.textContent = '⛶ 全屏';
        plotCanvas.appendChild(fullscreenBtn);
        
        box.innerHTML = '';
        box.appendChild(plotCanvas);
        
        var controlsContainer = document.createElement('div');
        controlsContainer.className = 'plot-controls';
        controlsContainer.innerHTML = html;
        box.insertBefore(controlsContainer, plotCanvas);

        document.getElementById("plotTypeSelect").addEventListener("change", function() {
            plotState.plotType = this.value;
            asyncRenderPlot(box, d);
        });
        document.getElementById("interpSelect").addEventListener("change", function() {
            plotState.interpMethod = this.value;
            asyncRenderPlot(box, d);
        });
        document.getElementById("colorSchemeSelect").addEventListener("change", function() {
            plotState.colorScheme = this.value;
            asyncRenderPlot(box, d);
        });
        document.getElementById("colorDirSelect").addEventListener("change", function() {
            plotState.colorDir = this.value;
            asyncRenderPlot(box, d);
        });
        document.getElementById("btnCustomColor").addEventListener("click", function() {
            showCustomColorDialog(box, d);
        });
        document.getElementById("btnCancelHighlight").addEventListener("click", function() {
            plotState.rowHighlight = null;
            plotState.colHighlight = null;
            document.getElementById("plotGotoRow").value = "";
            document.getElementById("plotGotoCol").value = "";
            asyncRenderPlot(box, d);
        });
        document.getElementById("btnFullscreenPlot").addEventListener("click", function() {
            openFullscreenPlot(box, d);
        });
        document.getElementById("btnPlotGotoRow").addEventListener("click", function() {
            var row = parseInt(document.getElementById("plotGotoRow").value);
            if (!isNaN(row) && row >= 0 && row < rows) {
                plotState.rowHighlight = row;
                asyncRenderPlot(box, d);
                flashHighlight(box, row, null);
            }
        });
        document.getElementById("btnPlotGotoCol").addEventListener("click", function() {
            var col = parseInt(document.getElementById("plotGotoCol").value);
            if (!isNaN(col) && col >= 0 && col < cols) {
                plotState.colHighlight = col;
                asyncRenderPlot(box, d);
                flashHighlight(box, null, col);
            }
        });
        document.getElementById("btnZoomIn").addEventListener("click", function() {
            plotState.plotZoom = Math.min(5, plotState.plotZoom * 1.25);
            updatePlotZoom();
        });
        document.getElementById("btnZoomOut").addEventListener("click", function() {
            plotState.plotZoom = Math.max(0.25, plotState.plotZoom / 1.25);
            updatePlotZoom();
        });
        document.getElementById("btnResetView").addEventListener("click", function() {
            plotState.plotZoom = 1;
            plotState.plotRotation = 0;
            updatePlotZoom();
            asyncRenderPlot(box, d);
        });
        document.getElementById("btnRotateCCW").addEventListener("click", function() {
            plotState.plotRotation = (plotState.plotRotation - 90) % 360;
            updatePlotZoom();
        });
        document.getElementById("btnRotateCW").addEventListener("click", function() {
            plotState.plotRotation = (plotState.plotRotation + 90) % 360;
            updatePlotZoom();
        });

        asyncRenderPlot(box, d);
    }

    function updatePlotZoom() {
        var zoomPct = Math.round(plotState.plotZoom * 100);
        var zoomLabel = document.getElementById("plotZoomLevel");
        if (zoomLabel) zoomLabel.textContent = zoomPct + "%";
        schedulePlotViewportSync(false);
    }
    
    function updateModebarPosition() {
        var innerCanvas = document.getElementById("plotInnerCanvas");
        var modebarHost = document.getElementById("plotModebarHost");
        if (!innerCanvas || !modebarHost) return;

        var modebar = innerCanvas.querySelector('.modebar-container') || modebarHost.querySelector('.modebar-container');
        if (!modebar) return;

        var staleModebars = modebarHost.querySelectorAll('.modebar-container');
        for (var j = 0; j < staleModebars.length; j++) {
            if (staleModebars[j] !== modebar && staleModebars[j].parentNode) {
                staleModebars[j].parentNode.removeChild(staleModebars[j]);
            }
        }

        if (modebar.parentNode !== modebarHost) {
            modebarHost.appendChild(modebar);
        }

        modebar.style.position = 'absolute';
        modebar.style.bottom = '0';
        modebar.style.top = 'auto';
        modebar.style.left = '0';
        modebar.style.right = 'auto';
        modebar.style.width = 'auto';
        modebar.style.height = 'auto';
        modebar.style.zIndex = '10000';
        modebar.style.transform = 'none';
        modebar.style.background = 'transparent';
        modebar.style.borderRadius = '0';
        modebar.style.padding = '0';
        modebar.style.boxShadow = 'none';
        modebar.style.pointerEvents = 'none';

        var modebarElements = modebar.querySelectorAll('*');
        for (var i = 0; i < modebarElements.length; i++) {
            modebarElements[i].style.pointerEvents = 'auto';
        }
    }
    
    function updateLegendPosition() {
        var innerCanvas = document.getElementById("plotInnerCanvas");
        if (!innerCanvas) return;
        
        var plotlyPlot = innerCanvas.querySelector('.js-plotly-plot');
        if (!plotlyPlot) return;
        
        var legend = plotlyPlot.querySelector('.legend');
        if (!legend) return;
        
        if (normalizeRotation(plotState.plotRotation) !== 0 || plotState.plotZoom !== 1) {
            legend.style.position = "absolute";
            legend.style.top = "12px";
            legend.style.right = "12px";
            legend.style.left = "auto";
            legend.style.transform = "none";
            legend.style.background = "rgba(15,23,42,0.9)";
            legend.style.borderRadius = "6px";
            legend.style.padding = "8px";
            legend.style.zIndex = "999";
        } else {
            legend.style.position = "";
            legend.style.top = "";
            legend.style.right = "";
            legend.style.left = "";
            legend.style.transform = "";
            legend.style.zIndex = "";
        }
    }

    function validatePlotData(values, rows, cols) {
        if (!values || !Array.isArray(values)) {
            return { valid: false, message: "数据格式无效：需要二维数组" };
        }
        if (!rows || !cols || rows <= 0 || cols <= 0) {
            return { valid: false, message: "数据维度无效：行数和列数必须大于0" };
        }

        var totalPoints = rows * cols;
        var warning = null;

        if (totalPoints > 10000000) {
            warning = "数据量极大（" + formatNumber(totalPoints) + "点）：将自动采样渲染，可能丢失细节";
        } else if (totalPoints > 1000000) {
            warning = "数据较大（" + formatNumber(totalPoints) + "点）：将使用降采样加速渲染";
        }

        var validCount = 0;
        var invalidCount = 0;
        var sampleSize = Math.min(rows * cols, 1000);
        var step = Math.max(1, Math.floor((rows * cols) / sampleSize));

        for (var r = 0; r < rows && validCount + invalidCount < sampleSize; r++) {
            if (!values[r] || !Array.isArray(values[r])) {
                invalidCount++;
                continue;
            }
            for (var c = 0; c < cols && validCount + invalidCount < sampleSize; c += step) {
                var v = values[r][c];
                if (typeof v === "number" && !isNaN(v) && isFinite(v)) {
                    validCount++;
                } else {
                    invalidCount++;
                }
            }
        }

        if (validCount === 0) {
            return { valid: false, message: "无有效数值数据：所有数据点均为NaN/Inf/非数字" };
        }

        var validRatio = validCount / (validCount + invalidCount);
        if (validRatio < 0.5) {
            var lowDataWarning = "有效数据较少：仅" + Math.round(validRatio * 100) + "%的数据点有效，绘图可能不完整";
            return { 
                valid: true, 
                warning: warning ? warning + "；" + lowDataWarning : lowDataWarning
            };
        }

        return { valid: true, warning: warning };
    }

    function formatNumber(n) {
        if (n >= 1000000000) return (n / 1000000000).toFixed(1) + "B";
        if (n >= 1000000) return (n / 1000000).toFixed(1) + "M";
        if (n >= 1000) return (n / 1000).toFixed(1) + "K";
        return String(n);
    }

    function asyncRenderPlot(box, d) {
        plotState.renderGeneration++;
        var currentGen = plotState.renderGeneration;

        if (plotState.renderTimeout) {
            clearTimeout(plotState.renderTimeout);
        }
        if (plotState.renderTimerInterval) {
            clearInterval(plotState.renderTimerInterval);
        }

        var statusEl = document.getElementById("plotStatus");
        var timerEl = document.getElementById("plotTimer");
        var loadTimeEl = document.getElementById("plotLoadTime");
        if (statusEl) {
            statusEl.textContent = "正在准备数据...";
        }
        if (timerEl) {
            timerEl.textContent = "渲染时间: 0.00s";
        }
        if (loadTimeEl && plotState.loadTime) {
            loadTimeEl.textContent = "加载时间: " + plotState.loadTime.toFixed(2) + "s";
        }

        plotState.isRendering = true;
        plotState.renderStartTime = performance.now();

        plotState.renderTimerInterval = setInterval(function() {
            if (plotState.renderStartTime && timerEl) {
                var elapsed = ((performance.now() - plotState.renderStartTime) / 1000).toFixed(2);
                timerEl.textContent = "渲染: " + elapsed + "s";
            }
        }, 100);

        plotState.renderTimeout = setTimeout(function() {
            if (currentGen !== plotState.renderGeneration) {
                return;
            }
            try {
                renderPlot(box, d, currentGen);
            } catch (err) {
                if (currentGen !== plotState.renderGeneration) return;
                plotState.isRendering = false;
                if (statusEl) {
                    statusEl.textContent = "渲染失败: " + err.message;
                }
                if (plotState.renderTimerInterval) {
                    clearInterval(plotState.renderTimerInterval);
                    plotState.renderTimerInterval = null;
                }
                console.error("Plot render error:", err);
            }
        }, 50);
    }

    function renderPlot(box, d, generation) {
        var canvas = document.getElementById("plotCanvas");
        if (!canvas) return;

        var values = d.values;
        var rows = d.shape ? d.shape[0] : 0;
        var cols = d.shape && d.shape.length > 1 ? d.shape[1] : 1;

        var MAX_PLOT_POINTS = 500000;
        var MAX_SURFACE_POINTS = 100000;
        var MAX_SCATTER_POINTS = 50000;
        var totalPoints = rows * cols;
        var sampleFactor = 1;

        var targetPoints = MAX_PLOT_POINTS;
        if (plotState.plotType === "surface") {
            targetPoints = MAX_SURFACE_POINTS;
        } else if (plotState.plotType === "scatter") {
            targetPoints = MAX_SCATTER_POINTS;
        }

        if (totalPoints > targetPoints) {
            if (typeof PlotOptimizer !== 'undefined') {
                sampleFactor = PlotOptimizer.getOptimalSampleFactor(totalPoints, targetPoints);
            } else {
                sampleFactor = Math.ceil(Math.sqrt(totalPoints / targetPoints));
            }
        }

        if (typeof PlotOptimizer !== 'undefined') {
            var validation = PlotOptimizer.validateLargeData(values, rows, cols);
            if (!validation.valid) {
                var statusEl = document.getElementById("plotStatus");
                if (statusEl) {
                    statusEl.textContent = "⚠️ " + validation.message;
                }
                return;
            }
            if (validation.warning) {
                console.warn(validation.warning);
            }
        }

        var sampledValues;
        if (typeof PlotOptimizer !== 'undefined') {
            sampledValues = PlotOptimizer.optimizedSampleData(values, rows, cols, sampleFactor);
        } else {
            sampledValues = sampleData(values, rows, cols, sampleFactor);
        }
        
        var sRows = sampledValues.length;
        var sCols = sampledValues.length > 0 ? sampledValues[0].length : 0;

        var processedValues;
        if (plotState.interpMethod === "linear" && typeof PlotOptimizer !== 'undefined') {
            processedValues = PlotOptimizer.fastBilinearInterpolation(sampledValues, sRows, sCols, 2);
        } else {
            processedValues = applyInterpolation(sampledValues, sRows, sCols, plotState.interpMethod);
        }
        
        var pRows = processedValues.length;
        var pCols = processedValues.length > 0 ? processedValues[0].length : 0;

        var xArr = [], yArr = [], zArr = [];
        for (var r = 0; r < pRows; r++) {
            for (var c = 0; c < pCols; c++) {
                xArr.push(c * sampleFactor);
                yArr.push(r * sampleFactor);
                zArr.push(processedValues[r][c]);
            }
        }

        var trace;
        var layout = darkLayout("绘图");
        var cs = plotState._customColorScale || (plotState.colorDir === "反向" ? plotState.colorScheme + "_r" : plotState.colorScheme);

        if (plotState.plotType === "mesh") {
            trace = {
                x: Array.from({length: pCols}, function(_, i) { return i * sampleFactor; }),
                y: Array.from({length: pRows}, function(_, i) { return i * sampleFactor; }),
                z: processedValues,
                type: "heatmap",
                colorscale: cs,
                colorbar: { 
                    tickfont: { color: "#94a3b8" },
                    x: 1.05,
                    xanchor: "left"
                }
            };
            layout.xaxis = { gridcolor: "#334155", zerolinecolor: "#475569", title: "列", constrain: "domain" };
            layout.yaxis = { gridcolor: "#334155", zerolinecolor: "#475569", title: "行", autorange: "reversed", scaleanchor: "x", scaleratio: 1 };
            layout.width = null;
            layout.height = null;
        } else if (plotState.plotType === "surface") {
            trace = {
                x: Array.from({length: pCols}, function(_, i) { return i * sampleFactor; }),
                y: Array.from({length: pRows}, function(_, i) { return i * sampleFactor; }),
                z: processedValues,
                type: "surface",
                colorscale: cs,
                colorbar: { 
                    tickfont: { color: "#94a3b8" },
                    x: 1.05,
                    xanchor: "left"
                }
            };
            layout.scene = {
                xaxis: { title: "列", backgroundcolor: "rgba(0,0,0,0)" },
                yaxis: { title: "行", backgroundcolor: "rgba(0,0,0,0)" },
                zaxis: { title: "值", backgroundcolor: "rgba(0,0,0,0)" },
                bgcolor: "rgba(0,0,0,0)",
                aspectratio: { x: 1, y: 1, z: 1 },
                aspectmode: "cube"
            };
        } else if (plotState.plotType === "contour") {
            trace = {
                x: Array.from({length: pCols}, function(_, i) { return i * sampleFactor; }),
                y: Array.from({length: pRows}, function(_, i) { return i * sampleFactor; }),
                z: processedValues,
                type: "contour",
                colorscale: cs,
                colorbar: { 
                    tickfont: { color: "#94a3b8" },
                    x: 1.05,
                    xanchor: "left"
                }
            };
            layout.xaxis = { gridcolor: "#334155", zerolinecolor: "#475569", title: "列", constrain: "domain" };
            layout.yaxis = { gridcolor: "#334155", zerolinecolor: "#475569", title: "行", scaleanchor: "x", scaleratio: 1 };
            layout.width = null;
            layout.height = null;
        } else if (plotState.plotType === "scatter") {
            var MAX_SCATTER = 50000;
            if (xArr.length > MAX_SCATTER) {
                var scatterStep = Math.ceil(xArr.length / MAX_SCATTER);
                var newX = [], newY = [], newZ = [];
                for (var i = 0; i < xArr.length; i += scatterStep) {
                    newX.push(xArr[i]);
                    newY.push(yArr[i]);
                    newZ.push(zArr[i]);
                }
                xArr = newX;
                yArr = newY;
                zArr = newZ;
            }
            trace = {
                x: xArr,
                y: yArr,
                z: zArr,
                mode: "markers",
                type: "scatter3d",
                marker: {
                    size: 3,
                    color: zArr,
                    colorscale: cs,
                    colorbar: { 
                    tickfont: { color: "#94a3b8" },
                    x: 1.05,
                    xanchor: "left"
                }
                }
            };
            layout.scene = {
                xaxis: { title: "列", backgroundcolor: "rgba(0,0,0,0)" },
                yaxis: { title: "行", backgroundcolor: "rgba(0,0,0,0)" },
                zaxis: { title: "值", backgroundcolor: "rgba(0,0,0,0)" },
                bgcolor: "rgba(0,0,0,0)",
                aspectratio: { x: 1, y: 1, z: 1 },
                aspectmode: "cube"
            };
        }

        if (plotState.rowHighlight !== null || plotState.colHighlight !== null) {
            var shapes = [];
            if (plotState.rowHighlight !== null) {
                shapes.push({
                    type: "line",
                    x0: 0, x1: (pCols - 1) * sampleFactor,
                    y0: plotState.rowHighlight, y1: plotState.rowHighlight,
                    line: { color: "#ff4444", width: 3 }
                });
            }
            if (plotState.colHighlight !== null) {
                shapes.push({
                    type: "line",
                    x0: plotState.colHighlight, x1: plotState.colHighlight,
                    y0: 0, y1: (pRows - 1) * sampleFactor,
                    line: { color: "#ff4444", width: 3 }
                });
            }
            if (plotState.plotType === "mesh" || plotState.plotType === "contour") {
                layout.shapes = shapes;
            }
        }

        if (generation !== plotState.renderGeneration) {
            return;
        }

        var samplingInfo = sampleFactor > 1 ? "（采样率 1:" + sampleFactor + "，渲染 " + formatNumber(pRows * pCols) + " 点）" : "";
        var statusText = "渲染完成" + samplingInfo + " | Plotly WebGL 硬件加速";
        if (plotState.currentVar && plotState.currentVar.load_time) {
            statusText += " | 加载时间: " + plotState.currentVar.load_time + "s";
        }
        if (plotState.renderStartTime) {
            var elapsed = ((performance.now() - plotState.renderStartTime) / 1000).toFixed(2);
            statusText += " | 渲染时间: " + elapsed + "s";
            
            if (typeof PlotOptimizer !== 'undefined') {
                PlotOptimizer.updatePerformanceStats(parseFloat(elapsed), pRows * pCols);
            }
        }
        showStatus(statusText);
        if (plotState.renderTimerInterval) {
            clearInterval(plotState.renderTimerInterval);
            plotState.renderTimerInterval = null;
        }

        plotState.isRendering = false;
        
        if (typeof PlotOptimizer !== 'undefined' && pRows * pCols > 100000) {
            PlotOptimizer.cleanupMemory();
        }
        
        var innerCanvas = document.getElementById("plotInnerCanvas");
        Plotly.newPlot(innerCanvas, [trace], layout, { 
            responsive: true, 
            displayModeBar: true,
            modeBarButtonsToRemove: [],
            displaylogo: false
        }).then(function() {
            setTimeout(function() {
                schedulePlotViewportSync(true);
            }, 100);
        });

        var warningEl = document.getElementById("plotWarning");
        if (warningEl) {
            setTimeout(function() {
                warningEl.style.opacity = "0";
                setTimeout(function() {
                    if (warningEl.parentNode) warningEl.parentNode.removeChild(warningEl);
                }, 500);
            }, 3000);
        }
        
        if (typeof PlotOptimizer !== 'undefined') {
            var perfInfo = document.getElementById("performanceInfo");
            var perfStats = document.getElementById("perfStats");
            if (perfInfo && perfStats) {
                var report = PlotOptimizer.getPerformanceReport();
                perfStats.textContent = "渲染次数: " + report.renderCount + 
                    " | 平均耗时: " + report.averageRenderTime + 
                    " | 内存: " + report.memoryUsage;
                perfInfo.style.display = "flex";
            }
        }
    }

    function sampleData(values, rows, cols, factor) {
        if (factor <= 1) return values;

        var newRows = Math.ceil(rows / factor);
        var newCols = Math.ceil(cols / factor);
        var result = [];

        for (var r = 0; r < newRows; r++) {
            result[r] = [];
            for (var c = 0; c < newCols; c++) {
                var srcR = r * factor;
                var srcC = c * factor;
                var sum = 0;
                var count = 0;

                for (var dr = 0; dr < factor && srcR + dr < rows; dr++) {
                    for (var dc = 0; dc < factor && srcC + dc < cols; dc++) {
                        var v = getVal(values, srcR + dr, srcC + dc, rows, cols);
                        if (typeof v === "number" && !isNaN(v) && isFinite(v)) {
                            sum += v;
                            count++;
                        }
                    }
                }

                result[r][c] = count > 0 ? sum / count : 0;
            }
        }
        return result;
    }

    function applyInterpolation(values, rows, cols, method) {
        if (method === "none") return values;

        var factor = 2;
        var newRows = rows * factor;
        var newCols = cols * factor;
        var result = [];

        if (method === "nearest") {
            for (var r = 0; r < newRows; r++) {
                result[r] = [];
                for (var c = 0; c < newCols; c++) {
                    var srcR = Math.round(r / factor);
                    var srcC = Math.round(c / factor);
                    srcR = Math.max(0, Math.min(srcR, rows - 1));
                    srcC = Math.max(0, Math.min(srcC, cols - 1));
                    result[r][c] = getVal(values, srcR, srcC, rows, cols);
                }
            }
            return result;
        }

        var rIndices = [];
        var cIndices = [];
        for (var ri = 0; ri < newRows; ri++) {
            rIndices[ri] = Math.min(Math.floor(ri / factor), rows - 2);
        }
        for (var ci = 0; ci < newCols; ci++) {
            cIndices[ci] = Math.min(Math.floor(ci / factor), cols - 2);
        }

        for (var r = 0; r < newRows; r++) {
            result[r] = [];
            for (var c = 0; c < newCols; c++) {
                var r0 = rIndices[r];
                var c0 = cIndices[c];
                var fr = (r / factor) - r0;
                var fc = (c / factor) - c0;

                var v00 = getVal(values, r0, c0, rows, cols);
                var v01 = getVal(values, r0, c0 + 1, rows, cols);
                var v10 = getVal(values, r0 + 1, c0, rows, cols);
                var v11 = getVal(values, r0 + 1, c0 + 1, rows, cols);

                if (method === "linear") {
                    var top = v00 * (1 - fc) + v01 * fc;
                    var bottom = v10 * (1 - fc) + v11 * fc;
                    result[r][c] = top * (1 - fr) + bottom * fr;
                } else if (method === "lanczos") {
                    var a = 3;
                    function lanczos(t) {
                        if (t === 0) return 1;
                        if (t < 0) t = -t;
                        if (t >= a) return 0;
                        return a * Math.sin(Math.PI * t) * Math.sin(Math.PI * t / a) / (Math.PI * Math.PI * t * t);
                    }
                    var sum = 0;
                    var weightSum = 0;
                    for (var dy = -a + 1; dy < a; dy++) {
                        for (var dx = -a + 1; dx < a; dx++) {
                            var sr = r0 + dy;
                            var sc = c0 + dx;
                            if (sr < 0 || sr >= rows || sc < 0 || sc >= cols) continue;
                            var ty = lanczos(fr - dy);
                            var tx = lanczos(fc - dx);
                            var w = tx * ty;
                            sum += getVal(values, sr, sc, rows, cols) * w;
                            weightSum += w;
                        }
                    }
                    result[r][c] = weightSum > 0 ? sum / weightSum : v00;
                } else if (method === "cubic") {
                    var t = fr * fr * (3 - 2 * fr);
                    var u = fc * fc * (3 - 2 * fc);
                    var top = v00 * (1 - u) + v01 * u;
                    var bottom = v10 * (1 - u) + v11 * u;
                    result[r][c] = top * (1 - t) + bottom * t;
                } else if (method === "spline") {
                    var r1 = Math.max(0, r0 - 1);
                    var r2 = Math.min(rows - 1, r0 + 2);
                    var c1 = Math.max(0, c0 - 1);
                    var c2 = Math.min(cols - 1, c0 + 2);
                    var colVals = [];
                    for (var rr = r1; rr <= r2; rr++) {
                        var rowData = [];
                        for (var cc = c1; cc <= c2; cc++) {
                            rowData.push(getVal(values, rr, cc, rows, cols));
                        }
                        colVals.push(catmullRom(rowData, (c0 - c1) + (fc * (c2 - c1)) / (c2 - c1)));
                    }
                    result[r][c] = catmullRom(colVals, (r0 - r1) + (fr * (r2 - r1)) / (r2 - r1));
                } else {
                    result[r][c] = v00;
                }
            }
        }
        return result;
    }

    function catmullRom(p, t) {
        var t2 = t * t;
        var t3 = t2 * t;
        if (p.length < 2) return p[0] || 0;
        if (p.length === 2) {
            return p[0] * (1 - t) + p[1] * t;
        }
        var p0 = p[Math.max(0, 0)];
        var p1 = p[1];
        var p2 = p[2];
        var p3 = p[Math.min(p.length - 1, 3)];
        return 0.5 * ((2 * p1) +
            (-p0 + p2) * t +
            (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 +
            (-p0 + 3 * p1 - 3 * p2 + p3) * t3);
    }

    function getVal(values, r, c, rows, cols) {
        if (r < 0 || r >= rows || c < 0 || c >= cols) return 0;
        var row = values[r];
        if (!row || c >= row.length) return 0;
        var v = row[c];
        return (typeof v === "number" && !isNaN(v) && isFinite(v)) ? v : 0;
    }

    function flashHighlight(box, row, col) {
        var canvas = document.getElementById("plotCanvas");
        if (!canvas) return;
        canvas.style.transition = "opacity 0.15s";
        canvas.style.opacity = "0.5";
        setTimeout(function() {
            canvas.style.opacity = "1";
        }, 150);
        setTimeout(function() {
            canvas.style.opacity = "0.5";
        }, 300);
        setTimeout(function() {
            canvas.style.opacity = "1";
        }, 450);
    }

    function showCustomColorDialog(box, d) {
        var overlay = document.createElement("div");
        overlay.id = "customColorOverlay";
        overlay.style.cssText = "position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.6);z-index:10000;display:flex;align-items:center;justify-content:center;";

        var dialog = document.createElement("div");
        dialog.style.cssText = "background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:24px;width:420px;max-width:90vw;box-shadow:0 20px 60px rgba(0,0,0,0.5);";

        var html = '<h3 style="margin:0 0 16px;font-size:1.1rem;color:var(--text);">🎨 自定义配色方案</h3>';
        html += '<div style="margin-bottom:12px;">';
        html += '<label style="display:block;font-size:.8rem;color:var(--text-dim);margin-bottom:4px;">配色名称</label>';
        html += '<input type="text" id="customColorName" placeholder="留空自动命名" style="width:100%;padding:8px 12px;border-radius:6px;border:1px solid var(--border);background:var(--surface2);color:var(--text);font-size:.85rem;">';
        html += '</div>';
        html += '<div style="margin-bottom:12px;">';
        html += '<label style="display:block;font-size:.8rem;color:var(--text-dim);margin-bottom:4px;">起始颜色</label>';
        html += '<input type="color" id="customColorStart" value="#440154" style="width:100%;height:40px;border:none;border-radius:6px;cursor:pointer;">';
        html += '</div>';
        html += '<div style="margin-bottom:12px;">';
        html += '<label style="display:block;font-size:.8rem;color:var(--text-dim);margin-bottom:4px;">中间颜色（可选）</label>';
        html += '<input type="color" id="customColorMid" value="#21908C" style="width:100%;height:40px;border:none;border-radius:6px;cursor:pointer;">';
        html += '<label style="font-size:.75rem;color:var(--text-dim);margin-left:8px;"><input type="checkbox" id="useMidColor" checked> 启用</label>';
        html += '</div>';
        html += '<div style="margin-bottom:12px;">';
        html += '<label style="display:block;font-size:.8rem;color:var(--text-dim);margin-bottom:4px;">结束颜色</label>';
        html += '<input type="color" id="customColorEnd" value="#FDE725" style="width:100%;height:40px;border:none;border-radius:6px;cursor:pointer;">';
        html += '</div>';
        html += '<div style="margin-bottom:16px;display:flex;gap:8px;">';
        html += '<button class="btn" id="btnImportColors" style="padding:6px 12px;font-size:.75rem;">📥 导入</button>';
        html += '<button class="btn" id="btnExportColors" style="padding:6px 12px;font-size:.75rem;">📤 导出</button>';
        html += '</div>';
        html += '<div style="display:flex;gap:8px;justify-content:flex-end;">';
        html += '<button class="btn" id="btnCancelCustomColor" style="padding:8px 16px;">取消</button>';
        html += '<button class="btn" id="btnApplyCustomColor" style="padding:8px 16px;background:var(--accent);color:var(--bg);">应用</button>';
        html += '</div>';

        dialog.innerHTML = html;
        overlay.appendChild(dialog);
        document.body.appendChild(overlay);

        overlay.addEventListener("click", function(e) {
            if (e.target === overlay) closeCustomColorDialog();
        });
        document.getElementById("btnCancelCustomColor").addEventListener("click", closeCustomColorDialog);
        document.getElementById("btnApplyCustomColor").addEventListener("click", function() {
            applyCustomColor(box, d);
        });
        document.getElementById("btnImportColors").addEventListener("click", function() {
            importColorSchemes(box, d);
        });
        document.getElementById("btnExportColors").addEventListener("click", function() {
            exportColorSchemes();
        });
    }

    function closeCustomColorDialog() {
        var overlay = document.getElementById("customColorOverlay");
        if (overlay) overlay.remove();
    }

    function applyCustomColor(box, d) {
        var name = document.getElementById("customColorName").value.trim();
        var start = document.getElementById("customColorStart").value;
        var mid = document.getElementById("customColorMid").value;
        var end = document.getElementById("customColorEnd").value;
        var useMid = document.getElementById("useMidColor").checked;

        if (!name) {
            var count = customColorSchemes.length + 1;
            name = "自定义配色" + count;
        }
        var baseName = name;
        var suffix = 1;
        while (COLOR_SCHEMES.some(function(s) { return s.value === name; }) ||
               customColorSchemes.some(function(s) { return s.value === name; })) {
            name = baseName + "_" + suffix;
            suffix++;
        }

        var cs;
        if (useMid) {
            cs = [[0, start], [0.5, mid], [1, end]];
        } else {
            cs = [[0, start], [1, end]];
        }

        var schemeEntry = { name: name, value: name, custom: true, colors: cs };
        customColorSchemes.push(schemeEntry);
        plotState.colorScheme = name;
        plotState._customColorScale = cs;

        var select = document.getElementById("colorSchemeSelect");
        if (select) {
            var opt = document.createElement("option");
            opt.value = name;
            opt.textContent = "🎨 " + name;
            opt.selected = true;
            select.appendChild(opt);
        }

        closeCustomColorDialog();
        asyncRenderPlot(box, d);
    }

    function exportColorSchemes() {
        var data = {
            version: 1,
            type: "color-schemes",
            schemes: customColorSchemes.map(function(s) {
                return { name: s.name, value: s.value, colors: s.colors };
            })
        };
        var blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
        var url = URL.createObjectURL(blob);
        var a = document.createElement("a");
        a.href = url;
        a.download = "custom_color_schemes.json";
        a.click();
        URL.revokeObjectURL(url);
    }

    function importColorSchemes(box, d) {
        var input = document.createElement("input");
        input.type = "file";
        input.accept = ".json";
        input.onchange = function(e) {
            var file = e.target.files[0];
            if (!file) return;
            var reader = new FileReader();
            reader.onload = function(e) {
                try {
                    var data = JSON.parse(e.target.result);
                    if (!data.schemes || !Array.isArray(data.schemes)) {
                        alert("无效的配色方案文件格式");
                        return;
                    }
                    data.schemes.forEach(function(s) {
                        if (!s.name || !s.colors) return;
                        var name = s.name;
                        var baseName = name;
                        var suffix = 1;
                        while (COLOR_SCHEMES.some(function(cs) { return cs.value === name; }) ||
                               customColorSchemes.some(function(cs) { return cs.value === name; })) {
                            name = baseName + "_" + suffix;
                            suffix++;
                        }
                        var schemeEntry = { name: name, value: name, custom: true, colors: s.colors };
                        customColorSchemes.push(schemeEntry);
                    });
                    refreshColorSchemeSelect(box);
                    alert("成功导入 " + data.schemes.length + " 个配色方案");
                } catch (err) {
                    alert("导入失败: " + err.message);
                }
            };
            reader.readAsText(file);
        };
        input.click();
    }

    function refreshColorSchemeSelect(box) {
        var select = document.getElementById("colorSchemeSelect");
        if (!select) return;
        var currentVal = plotState.colorScheme;
        select.innerHTML = "";
        COLOR_SCHEMES.forEach(function(scheme) {
            var opt = document.createElement("option");
            opt.value = scheme.value;
            opt.textContent = scheme.name;
            select.appendChild(opt);
        });
        customColorSchemes.forEach(function(scheme) {
            var opt = document.createElement("option");
            opt.value = scheme.value;
            opt.textContent = "🎨 " + scheme.name;
            select.appendChild(opt);
        });
        select.value = currentVal;
    }

    function openFullscreenPlot(box, d) {
        var canvas = document.getElementById("plotCanvas");
        if (!canvas) return;

        var fsOverlay = document.createElement("div");
        fsOverlay.id = "fullscreenPlotOverlay";
        fsOverlay.style.cssText = "position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.95);z-index:10000;display:flex;flex-direction:column;";

        var toolbar = document.createElement("div");
        toolbar.style.cssText = "display:flex;justify-content:space-between;align-items:center;padding:12px 20px;background:rgba(15,23,42,0.8);border-bottom:1px solid var(--border);";
        toolbar.innerHTML = '<span style="color:var(--text-dim);font-size:.85rem;">📐 绘图 - 全屏模式 (ESC退出)</span>' +
            '<button class="btn" id="btnExitFullscreen" style="padding:6px 14px;font-size:.8rem;">✕ 退出</button>';

        var fsCanvas = document.createElement("div");
        fsCanvas.id = "fullscreenPlotCanvas";
        fsCanvas.style.cssText = "flex:1;padding:20px;";

        fsOverlay.appendChild(toolbar);
        fsOverlay.appendChild(fsCanvas);
        document.body.appendChild(fsOverlay);

        var values = d.values;
        var rows = d.shape ? d.shape[0] : 0;
        var cols = d.shape && d.shape.length > 1 ? d.shape[1] : 1;

        var MAX_PLOT_POINTS = 1000000;
        var totalPoints = rows * cols;
        var sampleFactor = 1;
        if (totalPoints > MAX_PLOT_POINTS) {
            sampleFactor = Math.ceil(Math.sqrt(totalPoints / MAX_PLOT_POINTS));
        }

        var sampledValues = sampleData(values, rows, cols, sampleFactor);
        var sRows = sampledValues.length;
        var sCols = sampledValues.length > 0 ? sampledValues[0].length : 0;
        var processedValues = applyInterpolation(sampledValues, sRows, sCols, plotState.interpMethod);
        var pRows = processedValues.length;
        var pCols = processedValues.length > 0 ? processedValues[0].length : 0;

        var cs = plotState._customColorScale || (plotState.colorDir === "反向" ? plotState.colorScheme + "_r" : plotState.colorScheme);

        var trace;
        var layout = darkLayout("绘图");

        if (plotState.plotType === "mesh") {
            trace = {
                x: Array.from({length: pCols}, function(_, i) { return i * sampleFactor; }),
                y: Array.from({length: pRows}, function(_, i) { return i * sampleFactor; }),
                z: processedValues,
                type: "heatmap",
                colorscale: cs,
                colorbar: { 
                    tickfont: { color: "#94a3b8" },
                    x: 1.05,
                    xanchor: "left"
                }
            };
            layout.xaxis = { gridcolor: "#334155", zerolinecolor: "#475569", title: "列", constrain: "domain" };
            layout.yaxis = { gridcolor: "#334155", zerolinecolor: "#475569", title: "行", autorange: "reversed", scaleanchor: "x", scaleratio: 1 };
        } else if (plotState.plotType === "surface") {
            trace = {
                x: Array.from({length: pCols}, function(_, i) { return i * sampleFactor; }),
                y: Array.from({length: pRows}, function(_, i) { return i * sampleFactor; }),
                z: processedValues,
                type: "surface",
                colorscale: cs,
                colorbar: { 
                    tickfont: { color: "#94a3b8" },
                    x: 1.05,
                    xanchor: "left"
                }
            };
            layout.scene = {
                xaxis: { title: "列", backgroundcolor: "rgba(0,0,0,0)" },
                yaxis: { title: "行", backgroundcolor: "rgba(0,0,0,0)" },
                zaxis: { title: "值", backgroundcolor: "rgba(0,0,0,0)" },
                bgcolor: "rgba(0,0,0,0)",
                aspectratio: { x: 1, y: 1, z: 1 },
                aspectmode: "cube"
            };
        } else if (plotState.plotType === "contour") {
            trace = {
                x: Array.from({length: pCols}, function(_, i) { return i * sampleFactor; }),
                y: Array.from({length: pRows}, function(_, i) { return i * sampleFactor; }),
                z: processedValues,
                type: "contour",
                colorscale: cs,
                colorbar: { 
                    tickfont: { color: "#94a3b8" },
                    x: 1.05,
                    xanchor: "left"
                }
            };
            layout.xaxis = { gridcolor: "#334155", zerolinecolor: "#475569", title: "列", constrain: "domain" };
            layout.yaxis = { gridcolor: "#334155", zerolinecolor: "#475569", title: "行", scaleanchor: "x", scaleratio: 1 };
        } else if (plotState.plotType === "scatter") {
            var xArr = [], yArr = [], zArr = [];
            for (var r = 0; r < pRows; r++) {
                for (var c = 0; c < pCols; c++) {
                    xArr.push(c * sampleFactor);
                    yArr.push(r * sampleFactor);
                    zArr.push(processedValues[r][c]);
                }
            }
            var MAX_SCATTER = 100000;
            if (xArr.length > MAX_SCATTER) {
                var scatterStep = Math.ceil(xArr.length / MAX_SCATTER);
                var newX = [], newY = [], newZ = [];
                for (var i = 0; i < xArr.length; i += scatterStep) {
                    newX.push(xArr[i]);
                    newY.push(yArr[i]);
                    newZ.push(zArr[i]);
                }
                xArr = newX;
                yArr = newY;
                zArr = newZ;
            }
            trace = {
                x: xArr,
                y: yArr,
                z: zArr,
                mode: "markers",
                type: "scatter3d",
                marker: {
                    size: 3,
                    color: zArr,
                    colorscale: cs,
                    colorbar: { 
                    tickfont: { color: "#94a3b8" },
                    x: 1.05,
                    xanchor: "left"
                }
                }
            };
            layout.scene = {
                xaxis: { title: "列", backgroundcolor: "rgba(0,0,0,0)" },
                yaxis: { title: "行", backgroundcolor: "rgba(0,0,0,0)" },
                zaxis: { title: "值", backgroundcolor: "rgba(0,0,0,0)" },
                bgcolor: "rgba(0,0,0,0)",
                aspectratio: { x: 1, y: 1, z: 1 },
                aspectmode: "cube"
            };
        }

        Plotly.newPlot(fsCanvas, [trace], layout, { responsive: true, displayModeBar: true });

        function exitFullscreen() {
            Plotly.purge(fsCanvas);
            fsOverlay.remove();
        }

        document.getElementById("btnExitFullscreen").addEventListener("click", exitFullscreen);
        document.addEventListener("keydown", function handler(e) {
            if (e.key === "Escape") {
                exitFullscreen();
                document.removeEventListener("keydown", handler);
            }
        });
    }

});

// ==================== 页脚时间更新 ====================
(function() {
    function updateFooterTime() {
        var el = document.getElementById("footerTime");
        if (!el) return;
        var now = new Date();
        var pad = function(n) { return n < 10 ? "0" + n : String(n); };
        el.textContent = now.getFullYear() + "-" + pad(now.getMonth()+1) + "-" + pad(now.getDate()) + " " +
                         pad(now.getHours()) + ":" + pad(now.getMinutes()) + ":" + pad(now.getSeconds());
    }
    updateFooterTime();
    setInterval(updateFooterTime, 1000);
})();
