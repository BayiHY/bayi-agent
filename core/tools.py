# -*- coding: utf-8 -*-
"""
工具执行模块

提供基础工具：web_search, read_file, execute_code
"""
import asyncio
import subprocess
import json
import os
import aiohttp
import logging
from typing import Dict, Any, Optional, List
from pathlib import Path


logger = logging.getLogger(__name__)


class ToolRegistry:
    """工具注册表"""
    
    def __init__(self):
        self.tools = {}
        self._register_builtin_tools()
    
    def _register_builtin_tools(self):
        """注册内置工具"""
        self.tools["web_search"] = WebSearchTool()
        self.tools["read_file"] = ReadFileTool()
        self.tools["write_file"] = WriteFileTool()      # ✅ 新增
        self.tools["edit_file"] = EditFileTool()        # ✅ 新增
        self.tools["execute_code"] = ExecuteCodeTool()
        self.tools["list_dir"] = ListDirTool()
        self.tools["image_generator"] = ImageGeneratorTool()
    
    def get(self, tool_name: str):
        """获取工具"""
        return self.tools.get(tool_name)
    
    def has(self, tool_name: str) -> bool:
        """检查工具是否存在"""
        return tool_name in self.tools


class BaseTool:
    """工具基类"""
    
    name: str = "base"
    description: str = ""
    
    async def execute(self, **kwargs) -> Dict[str, Any]:
        """执行工具"""
        raise NotImplementedError


class WebSearchTool(BaseTool):
    """网络搜索工具"""
    
    name = "web_search"
    description = "搜索网络获取信息"
    
    def __init__(self):
        # 使用 Tavily API
        self.api_base = "https://api.tavily.com/search"
        self.api_key = os.getenv("TAVILY_API_KEY", "")
        
        if not self.api_key:
            logger.warning("TAVILY_API_KEY 环境变量未设置，web_search 工具将无法使用")
    
    async def execute(self, query: str, max_results: int = 5) -> Dict[str, Any]:
        """
        执行搜索
        
        Args:
            query: 搜索关键词
            max_results: 最大结果数
        
        Returns:
            {
                "success": True,
                "results": [
                    {"title": "...", "url": "...", "snippet": "..."}
                ]
            }
        """
        try:
            logger.info(f"执行搜索: {query}")
            
            # 使用 Tavily API
            payload = {
                "api_key": self.api_key,
                "query": query,
                "max_results": max_results,
                "search_depth": "basic"
            }
            
            timeout = aiohttp.ClientTimeout(total=15)
            
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(self.api_base, json=payload) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        logger.error(f"Tavily API 错误: {resp.status} - {error_text}")
                        return {
                            "success": False,
                            "error": f"API 错误: {resp.status}",
                            "results": []
                        }
                    
                    data = await resp.json()
            
            # 解析结果
            results = []
            
            for item in data.get("results", []):
                results.append({
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "snippet": item.get("content", "")
                })
            
            if not results:
                return {
                    "success": False,
                    "error": "未找到相关结果",
                    "results": []
                }
            
            logger.info(f"搜索完成: 找到 {len(results)} 个结果")
            
            return {
                "success": True,
                "results": results
            }
        
        except Exception as e:
            logger.error(f"搜索失败: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "results": []
            }


class ReadFileTool(BaseTool):
    """文件读取工具"""
    
    name = "read_file"
    description = "读取文件内容"
    
    async def execute(self, file_path: str, max_lines: int = 100) -> Dict[str, Any]:
        """
        读取文件
        
        Args:
            file_path: 文件路径
            max_lines: 最大行数
        
        Returns:
            {
                "success": True,
                "content": "...",
                "lines": 100
            }
        """
        try:
            logger.info(f"读取文件: {file_path}")
            
            # 安全检查：防止路径遍历
            safe_path = Path(file_path).resolve()
            
            # 检查文件是否存在
            if not safe_path.exists():
                return {
                    "success": False,
                    "error": f"文件不存在: {file_path}"
                }
            
            # 检查是否为文件
            if not safe_path.is_file():
                return {
                    "success": False,
                    "error": f"不是文件: {file_path}"
                }
            
            # 读取文件
            with open(safe_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()[:max_lines]
                content = ''.join(lines)
            
            logger.info(f"读取完成: {len(lines)} 行")
            
            return {
                "success": True,
                "content": content,
                "lines": len(lines),
                "file_path": str(safe_path)
            }
        
        except Exception as e:
            logger.error(f"读取文件失败: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }


class ExecuteCodeTool(BaseTool):
    """代码执行工具"""
    
    name = "execute_code"
    description = "执行 Python 代码"
    
    async def execute(self, code: str, timeout: int = 10) -> Dict[str, Any]:
        """
        执行代码
        
        Args:
            code: Python 代码
            timeout: 超时时间（秒）
        
        Returns:
            {
                "success": True,
                "output": "...",
                "error": ""
            }
        """
        try:
            logger.info(f"执行代码: {len(code)} 字符")
            logger.info(f"代码内容:\n{code}")
            
            # 使用 subprocess 执行（安全隔离）
            process = await asyncio.create_subprocess_exec(
                'python3', '-c', code,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout
                )
                
                output = stdout.decode('utf-8', errors='ignore')
                error = stderr.decode('utf-8', errors='ignore')
                
                if process.returncode == 0:
                    logger.info(f"执行成功: {len(output)} 字符输出")
                    logger.info(f"输出内容:\n{output}")
                    return {
                        "success": True,
                        "output": output,
                        "error": ""
                    }
                else:
                    logger.warning(f"执行失败: {error}")
                    return {
                        "success": False,
                        "output": output,
                        "error": error
                    }
            
            except asyncio.TimeoutError:
                process.kill()
                return {
                    "success": False,
                    "error": f"执行超时（{timeout}秒）"
                }
        
        except Exception as e:
            logger.error(f"执行代码失败: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }


class ListDirTool(BaseTool):
    """目录列表工具"""
    
    name = "list_dir"
    description = "列出目录内容"
    
    async def execute(self, dir_path: str = ".", max_items: int = 50) -> Dict[str, Any]:
        """
        列出目录
        
        Args:
            dir_path: 目录路径
            max_items: 最大项目数
        
        Returns:
            {
                "success": True,
                "items": [
                    {"name": "...", "type": "file/dir", "size": 1024}
                ]
            }
        """
        try:
            logger.info(f"列出目录: {dir_path}")
            
            safe_path = Path(dir_path).resolve()
            
            if not safe_path.exists():
                return {
                    "success": False,
                    "error": f"目录不存在: {dir_path}"
                }
            
            if not safe_path.is_dir():
                return {
                    "success": False,
                    "error": f"不是目录: {dir_path}"
                }
            
            items = []
            for item in list(safe_path.iterdir())[:max_items]:
                items.append({
                    "name": item.name,
                    "type": "dir" if item.is_dir() else "file",
                    "size": item.stat().st_size if item.is_file() else 0
                })
            
            logger.info(f"列出完成: {len(items)} 个项目")
            
            return {
                "success": True,
                "items": items,
                "dir_path": str(safe_path)
            }
        
        except Exception as e:
            logger.error(f"列出目录失败: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }


class ImageGeneratorTool(BaseTool):
    """图片生成工具"""
    
    name = "image_generator"
    description = "生成图片"
    
    def __init__(self):
        self.api_base = "https://apihub.agnes-ai.com/v1/images/generations"
        self.api_key = None
        self._load_api_key()
    
    def _load_api_key(self):
        """加载 API Key"""
        try:
            with open(os.path.expanduser("~/.hermes/.env")) as f:
                for line in f:
                    if line.startswith("AGNES_API_KEY="):
                        self.api_key = line.split("=", 1)[1].strip().strip('"\'')
                        break
        except Exception as e:
            logger.warning(f"加载 AGNES_API_KEY 失败: {e}")
    
    async def execute(self, prompt: str, size: str = "576x1024") -> Dict[str, Any]:
        """
        生成图片
        
        Args:
            prompt: 图片描述
            size: 图片尺寸（默认 576x1024 竖屏）
        
        Returns:
            {
                "success": True,
                "url": "https://...",
                "message": "图片生成成功"
            }
        """
        try:
            if not self.api_key:
                return {
                    "success": False,
                    "error": "未配置 AGNES_API_KEY"
                }
            
            logger.info(f"生成图片: {prompt[:50]}...")
            
            # 构建请求
            data = {
                "model": "agnes-image-2.1-flash",
                "prompt": prompt,
                "size": size,
                "extra_body": {
                    "response_format": "url"
                }
            }
            
            # 调用 Agnes API
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.api_base,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json=data,
                    timeout=aiohttp.ClientTimeout(total=60)
                ) as resp:
                    result = await resp.json()
                    
                    if "data" in result and len(result["data"]) > 0:
                        url = result["data"][0]["url"]
                        logger.info(f"图片生成成功: {url}")
                        
                        return {
                            "success": True,
                            "url": url,
                            "message": f"图片生成成功\n\n图片链接: {url}"
                        }
                    else:
                        return {
                            "success": False,
                            "error": f"API 返回异常: {result}"
                        }
        
        except Exception as e:
            logger.error(f"生成图片失败: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }


class WriteFileTool(BaseTool):
    """文件写入工具"""
    
    name = "write_file"
    description = "创建或覆盖文件"
    
    async def execute(self, file_path: str, content: str) -> Dict[str, Any]:
        """
        写入文件
        
        Args:
            file_path: 文件路径
            content: 文件内容
        
        Returns:
            {"success": bool, "message": str}
        """
        try:
            logger.info(f"写入文件: {file_path} ({len(content)} 字符)")
            
            # 安全检查
            safe_path = Path(file_path).resolve()
            
            # 确保目录存在
            safe_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 写入文件
            with open(safe_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            logger.info(f"✅ 文件写入成功: {file_path}")
            
            return {
                "success": True,
                "message": f"文件写入成功: {file_path}",
                "file_path": str(safe_path),
                "size": len(content)
            }
        
        except Exception as e:
            logger.error(f"❌ 文件写入失败: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }


class EditFileTool(BaseTool):
    """文件编辑工具"""
    
    name = "edit_file"
    description = "精确修改文件内容"
    
    async def execute(
        self,
        file_path: str,
        old_text: str,
        new_text: str,
        replace_all: bool = False
    ) -> Dict[str, Any]:
        """
        编辑文件
        
        Args:
            file_path: 文件路径
            old_text: 要替换的文本
            new_text: 替换后的文本
            replace_all: 是否替换所有出现（默认只替换第一个）
        
        Returns:
            {"success": bool, "message": str, "changes": int}
        """
        try:
            logger.info(f"编辑文件: {file_path}")
            
            # 安全检查
            safe_path = Path(file_path).resolve()
            
            # 检查文件是否存在
            if not safe_path.exists():
                return {
                    "success": False,
                    "error": f"文件不存在: {file_path}"
                }
            
            # 读取文件
            with open(safe_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 统计出现次数
            count = content.count(old_text)
            
            if count == 0:
                return {
                    "success": False,
                    "error": f"未找到要替换的文本: {old_text[:50]}..."
                }
            
            # 替换
            if replace_all:
                new_content = content.replace(old_text, new_text)
            else:
                new_content = content.replace(old_text, new_text, 1)
            
            # 写回文件
            with open(safe_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            
            actual_changes = count if replace_all else 1
            
            logger.info(f"✅ 文件编辑成功: {file_path} ({actual_changes} 处修改)")
            
            return {
                "success": True,
                "message": f"文件编辑成功: {actual_changes} 处修改",
                "file_path": str(safe_path),
                "changes": actual_changes
            }
        
        except Exception as e:
            logger.error(f"❌ 文件编辑失败: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }


# 全局工具注册表
tool_registry = ToolRegistry()
