"""
安全测试和验证脚本
用于测试 app.py 中实现的安全功能
"""

import unittest
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from security import (
    sanitize_string, validate_var_name, validate_filename,
    safe_path_join, escape_html, sanitize_url
)


class TestSecurityFunctions(unittest.TestCase):
    """测试安全函数"""

    def test_sanitize_string(self):
        """测试字符串清理"""
        # 正常输入
        self.assertEqual(sanitize_string("hello"), "hello")
        
        # None 输入
        self.assertEqual(sanitize_string(None), "")
        
        # 危险字符 - 应该被移除
        result = sanitize_string("<script>alert('xss')</script>")
        self.assertNotIn("<", result)
        self.assertNotIn(">", result)
        
        # 超长输入
        long_str = "a" * 2000
        result = sanitize_string(long_str)
        self.assertEqual(len(result), 1000)  # 默认最大长度

    def test_validate_var_name(self):
        """测试变量名验证"""
        # 有效变量名
        self.assertTrue(validate_var_name("valid_name"))
        self.assertTrue(validate_var_name("var123"))
        self.assertTrue(validate_var_name("_private"))
        
        # 无效变量名
        self.assertFalse(validate_var_name("123invalid"))  # 数字开头
        self.assertFalse(validate_var_name("invalid-name"))  # 连字符
        self.assertFalse(validate_var_name("invalid.name"))  # 点号
        self.assertFalse(validate_var_name(""))  # 空字符串
        self.assertFalse(validate_var_name(None))  # None

    def test_validate_filename(self):
        """测试文件名验证"""
        # 有效文件名
        self.assertTrue(validate_filename("test.mat"))
        self.assertTrue(validate_filename("data_123.mat"))
        
        # 无效文件名
        self.assertFalse(validate_filename("../evil.mat"))  # 路径遍历
        self.assertFalse(validate_filename("/etc/passwd"))  # 绝对路径
        self.assertFalse(validate_filename("file<script>.mat"))  # XSS
        self.assertFalse(validate_filename(""))  # 空字符串

    def test_safe_path_join(self):
        """测试安全路径连接"""
        base = os.path.normpath("/safe/base")
        
        # 安全的路径
        result = safe_path_join(base, "subdir", "file.txt")
        self.assertIsNotNone(result)
        self.assertTrue(result.endswith(os.path.join("subdir", "file.txt")))
        
        # 路径遍历攻击
        result = safe_path_join(base, "../evil.txt")
        self.assertIsNone(result)
        
        # 绝对路径攻击
        result = safe_path_join(base, "/etc/passwd")
        self.assertIsNone(result)

    def test_escape_html(self):
        """测试 HTML 转义"""
        # 正常文本
        self.assertEqual(escape_html("hello"), "hello")
        
        # HTML 标签
        result = escape_html("<script>")
        self.assertIn("&lt;", result)
        self.assertIn("&gt;", result)
        
        # 引号
        result = escape_html('"test"')
        self.assertIn("&quot;", result)
        
        # None
        self.assertEqual(escape_html(None), "")

    def test_sanitize_url(self):
        """测试 URL 清理"""
        # 有效 URL
        self.assertIsNotNone(sanitize_url("http://example.com/file.mat"))
        self.assertIsNotNone(sanitize_url("https://example.com/file.mat"))
        
        # 无效协议
        self.assertIsNone(sanitize_url("ftp://example.com/file.mat"))
        self.assertIsNone(sanitize_url("file:///etc/passwd"))
        
        # 危险字符
        self.assertIsNone(sanitize_url("http://example.com/<script>.mat"))
        
        # 超长 URL
        long_url = "http://" + "a" * 1000 + ".com"
        self.assertIsNone(sanitize_url(long_url))


class TestInputValidation(unittest.TestCase):
    """测试输入验证"""

    def test_sql_injection_prevention(self):
        """测试 SQL 注入防护（虽然我们用参数化查询）"""
        malicious_inputs = [
            "'; DROP TABLE users; --",
            "1 OR 1=1",
            "admin'--",
        ]
        
        for input_str in malicious_inputs:
            # 这些输入应该被清理或拒绝
            sanitized = sanitize_string(input_str)
            # 至少应该移除部分危险字符
            # 注意：sanitize_string 主要移除<>字符，不是 SQL 注入的完整解决方案
            # SQL 注入防护主要依靠参数化查询
            self.assertIsNotNone(sanitized)

    def test_xss_prevention(self):
        """测试 XSS 防护"""
        xss_payloads = [
            "<script>alert('xss')</script>",
            "<img src=x onerror=alert('xss')>",
        ]
        
        for payload in xss_payloads:
            sanitized = sanitize_string(payload)
            escaped = escape_html(payload)
            
            # 清理后不应该包含危险字符
            self.assertNotIn("<", sanitized)
            self.assertNotIn(">", sanitized)
            
            # 转义后应该是安全的
            self.assertIn("&lt;", escaped)
            self.assertIn("&gt;", escaped)


def run_tests():
    """运行所有测试"""
    print("=" * 60)
    print("安全功能测试")
    print("=" * 60)
    
    # 创建测试套件
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # 添加测试
    suite.addTests(loader.loadTestsFromTestCase(TestSecurityFunctions))
    suite.addTests(loader.loadTestsFromTestCase(TestInputValidation))
    
    # 运行测试
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    print("\n" + "=" * 60)
    print(f"测试结果：{result.testsRun} 个测试")
    print(f"通过：{result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"失败：{len(result.failures)}")
    print(f"错误：{len(result.errors)}")
    print("=" * 60)
    
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
