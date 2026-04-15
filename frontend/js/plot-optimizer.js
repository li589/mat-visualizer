/**
 * 绘图模块性能优化工具
 * 
 * 功能：
 * - Web Worker 异步计算
 * - 内存管理
 * - 性能监控
 * - 大数据处理优化
 */

'use strict';

var PlotOptimizer = (function() {
    var memoryLimit = 512 * 1024 * 1024; // 512MB
    var warningThreshold = 0.8; // 80% 内存警告阈值
    var maxRenderTime = 30000; // 最大渲染时间 30 秒
    
    var performanceStats = {
        lastRenderTime: 0,
        averageRenderTime: 0,
        renderCount: 0,
        memoryUsage: 0,
        dataPointsProcessed: 0
    };
    
    var memoryMonitor = {
        totalAllocated: 0,
        peakUsage: 0,
        currentUsage: 0
    };

    function estimateMemoryUsage(rows, cols, bytesPerElement) {
        bytesPerElement = bytesPerElement || 8;
        return rows * cols * bytesPerElement;
    }

    function checkMemoryLimit(requiredMemory) {
        var usage = performance.memory || { usedJSHeapSize: 0, jsHeapSizeLimit: memoryLimit };
        var currentUsage = usage.usedJSHeapSize || 0;
        var limit = usage.jsHeapSizeLimit || memoryLimit;
        
        memoryMonitor.currentUsage = currentUsage;
        memoryMonitor.peakUsage = Math.max(memoryMonitor.peakUsage, currentUsage);
        
        if (currentUsage + requiredMemory > limit * warningThreshold) {
            return {
                safe: false,
                current: currentUsage,
                limit: limit,
                required: requiredMemory,
                message: "内存使用接近限制，可能影响性能"
            };
        }
        
        return { safe: true };
    }

    function getOptimalSampleFactor(totalPoints, maxPoints) {
        maxPoints = maxPoints || 500000;
        
        if (totalPoints <= maxPoints) {
            return 1;
        }
        
        var factor = Math.ceil(Math.sqrt(totalPoints / maxPoints));
        
        if (factor > 10) {
            factor = Math.ceil(factor / 2) * 2;
        }
        
        return factor;
    }

    function optimizedSampleData(values, rows, cols, factor) {
        if (factor <= 1) return values;
        
        var newRows = Math.ceil(rows / factor);
        var newCols = Math.ceil(cols / factor);
        var result = new Array(newRows);
        
        for (var r = 0; r < newRows; r++) {
            result[r] = new Float64Array(newCols);
            var srcR = r * factor;
            
            for (var c = 0; c < newCols; c++) {
                var srcC = c * factor;
                var sum = 0;
                var count = 0;
                
                var maxDr = Math.min(factor, rows - srcR);
                var maxDc = Math.min(factor, cols - srcC);
                
                for (var dr = 0; dr < maxDr; dr++) {
                    var row = values[srcR + dr];
                    if (!row) continue;
                    
                    for (var dc = 0; dc < maxDc; dc++) {
                        var v = row[srcC + dc];
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

    function fastBilinearInterpolation(values, rows, cols, factor) {
        factor = factor || 2;
        var newRows = rows * factor;
        var newCols = cols * factor;
        var result = new Array(newRows);
        
        for (var r = 0; r < newRows; r++) {
            result[r] = new Float64Array(newCols);
            var r0 = Math.min(Math.floor(r / factor), rows - 2);
            var fr = (r / factor) - r0;
            
            for (var c = 0; c < newCols; c++) {
                var c0 = Math.min(Math.floor(c / factor), cols - 2);
                var fc = (c / factor) - c0;
                
                var v00 = getValFast(values, r0, c0, rows, cols);
                var v01 = getValFast(values, r0, c0 + 1, rows, cols);
                var v10 = getValFast(values, r0 + 1, c0, rows, cols);
                var v11 = getValFast(values, r0 + 1, c0 + 1, rows, cols);
                
                var top = v00 * (1 - fc) + v01 * fc;
                var bottom = v10 * (1 - fc) + v11 * fc;
                result[r][c] = top * (1 - fr) + bottom * fr;
            }
        }
        
        return result;
    }

    function getValFast(values, r, c, rows, cols) {
        if (r < 0 || r >= rows || c < 0 || c >= cols) return 0;
        var row = values[r];
        if (!row || c >= row.length) return 0;
        var v = row[c];
        return (typeof v === "number" && !isNaN(v) && isFinite(v)) ? v : 0;
    }

    function createDataChunk(values, rows, cols, chunkSize) {
        chunkSize = chunkSize || 1000;
        var chunks = [];
        
        for (var r = 0; r < rows; r += chunkSize) {
            var endR = Math.min(r + chunkSize, rows);
            var chunk = {
                startRow: r,
                endRow: endR,
                data: values.slice(r, endR)
            };
            chunks.push(chunk);
        }
        
        return chunks;
    }

    function renderWithTimeout(renderFunc, timeout) {
        timeout = timeout || maxRenderTime;
        
        return new Promise(function(resolve, reject) {
            var timeoutId = setTimeout(function() {
                reject(new Error("渲染超时（" + (timeout / 1000) + "秒）"));
            }, timeout);
            
            try {
                renderFunc(function(result) {
                    clearTimeout(timeoutId);
                    resolve(result);
                });
            } catch (err) {
                clearTimeout(timeoutId);
                reject(err);
            }
        });
    }

    function updatePerformanceStats(renderTime, dataPoints) {
        performanceStats.lastRenderTime = renderTime;
        performanceStats.renderCount++;
        performanceStats.dataPointsProcessed += dataPoints;
        
        var alpha = 0.3;
        performanceStats.averageRenderTime = 
            alpha * renderTime + (1 - alpha) * performanceStats.averageRenderTime;
    }

    function getPerformanceReport() {
        return {
            lastRenderTime: performanceStats.lastRenderTime.toFixed(3) + "s",
            averageRenderTime: performanceStats.averageRenderTime.toFixed(3) + "s",
            renderCount: performanceStats.renderCount,
            dataPointsProcessed: formatNumber(performanceStats.dataPointsProcessed),
            memoryUsage: formatBytes(memoryMonitor.currentUsage),
            peakMemory: formatBytes(memoryMonitor.peakUsage)
        };
    }

    function formatBytes(bytes) {
        if (bytes < 1024) return bytes + " B";
        if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(2) + " KB";
        if (bytes < 1024 * 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(2) + " MB";
        return (bytes / (1024 * 1024 * 1024)).toFixed(2) + " GB";
    }

    function formatNumber(n) {
        if (n >= 1000000000) return (n / 1000000000).toFixed(1) + "B";
        if (n >= 1000000) return (n / 1000000).toFixed(1) + "M";
        if (n >= 1000) return (n / 1000).toFixed(1) + "K";
        return String(n);
    }

    function validateLargeData(values, rows, cols) {
        var totalPoints = rows * cols;
        var estimatedMemory = estimateMemoryUsage(rows, cols);
        
        var memoryCheck = checkMemoryLimit(estimatedMemory);
        if (!memoryCheck.safe) {
            return {
                valid: false,
                message: "数据量过大，内存不足",
                details: memoryCheck,
                suggestion: "建议使用采样或分块加载"
            };
        }
        
        var sampleFactor = getOptimalSampleFactor(totalPoints);
        
        return {
            valid: true,
            sampleFactor: sampleFactor,
            estimatedMemory: estimatedMemory,
            memoryCheck: memoryCheck,
            warning: totalPoints > 1000000 ? 
                "大数据集（" + formatNumber(totalPoints) + " 点），将使用采样渲染" : null
        };
    }

    function cleanupMemory() {
        if (typeof gc === 'function') {
            gc();
        }
        
        memoryMonitor.currentUsage = 0;
    }

    return {
        estimateMemoryUsage: estimateMemoryUsage,
        checkMemoryLimit: checkMemoryLimit,
        getOptimalSampleFactor: getOptimalSampleFactor,
        optimizedSampleData: optimizedSampleData,
        fastBilinearInterpolation: fastBilinearInterpolation,
        createDataChunk: createDataChunk,
        renderWithTimeout: renderWithTimeout,
        updatePerformanceStats: updatePerformanceStats,
        getPerformanceReport: getPerformanceReport,
        validateLargeData: validateLargeData,
        cleanupMemory: cleanupMemory,
        memoryMonitor: memoryMonitor,
        performanceStats: performanceStats
    };
})();

if (typeof window !== 'undefined') {
    window.PlotOptimizer = PlotOptimizer;
}
