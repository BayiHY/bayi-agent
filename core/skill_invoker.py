# -*- coding: utf-8 -*-
"""
技能调用器

负责匹配技能、准备工具、执行并返回结果
"""
import logging
from typing import Dict, Any, List, Optional
from .tools import tool_registry


logger = logging.getLogger(__name__)


class SkillInvoker:
    """技能调用器"""

    # 预定义技能
    SKILLS = {
        "web-search": {
            "description": "网络搜索技能",
            "tools": ["web_search"],
            "keywords": ["搜索", "查找", "查询", "新闻", "资讯", "search", "find", "news"]
        },
        "file-operations": {
            "description": "文件操作技能",
            "tools": ["read_file", "list_dir"],
            "keywords": ["读取", "查看", "文件", "目录", "read", "file", "list", "dir"]
        },
        "code-execution": {
            "description": "代码执行技能",
            "tools": ["execute_code"],
            "keywords": ["执行", "运行", "代码", "计算", "execute", "run", "code", "calculate"]
        },
        "data-analysis": {
            "description": "数据分析技能",
            "tools": ["read_file", "execute_code"],
            "keywords": ["分析", "统计", "数据", "analysis", "statistics", "data"]
        },
        "research": {
            "description": "研究调查技能",
            "tools": ["web_search", "read_file"],
            "keywords": ["研究", "调查", "了解", "research", "investigate", "learn"]
        }
    }

    def __init__(self):
        self.registry = tool_registry

    def match_skills(self, message: str) -> List[str]:
        """
        匹配相关技能

        Args:
            message: 用户消息

        Returns:
            匹配的技能列表
        """
        matched = []
        message_lower = message.lower()

        for skill_name, skill_info in self.SKILLS.items():
            keywords = skill_info.get("keywords", [])

            # 检查关键词匹配
            for keyword in keywords:
                if keyword in message_lower:
                    matched.append(skill_name)
                    break

        return matched

    def get_tools_for_skills(self, skills: List[str]) -> List[str]:
        """
        获取技能对应的工具

        Args:
            skills: 技能列表

        Returns:
            工具列表(去重)
        """
        tools = []

        for skill_name in skills:
            skill_info = self.SKILLS.get(skill_name, {})
            tools.extend(skill_info.get("tools", []))

        # 去重
        return list(set(tools))

    async def execute_tool(
        self,
        tool_name: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行工具

        Args:
            tool_name: 工具名称
            **kwargs: 工具参数

        Returns:
            执行结果
        """
        tool = self.registry.get(tool_name)

        if not tool:
            return {
                "success": False,
                "error": f"工具不存在: {tool_name}"
            }

        logger.info(f"执行工具: {tool_name}")

        try:
            result = await tool.execute(**kwargs)
            return result
        except Exception as e:
            logger.error(f"工具执行失败: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }

    async def execute_tools_for_message(
        self,
        message: str,
        max_tools: int = 3
    ) -> Dict[str, Any]:
        """
        根据消息自动执行相关工具

        Args:
            message: 用户消息
            max_tools: 最多执行工具数

        Returns:
            {
                "skills": ["web-search"],
                "tools": ["web_search"],
                "results": {
                    "web_search": {...}
                }
            }
        """
        # 1. 匹配技能
        skills = self.match_skills(message)

        if not skills:
            return {
                "skills": [],
                "tools": [],
                "results": {}
            }

        # 2. 获取工具
        tools = self.get_tools_for_skills(skills)

        # 3. 执行工具
        results = {}

        for tool_name in tools[:max_tools]:
            # 根据工具类型准备参数
            kwargs = self._prepare_tool_args(tool_name, message)

            # 执行
            result = await self.execute_tool(tool_name, **kwargs)
            results[tool_name] = result

        return {
            "skills": skills,
            "tools": tools,
            "results": results
        }

    def _prepare_tool_args(self, tool_name: str, message: str) -> Dict[str, Any]:
        """
        准备工具参数
        
        Args:
            tool_name: 工具名称
            message: 用户消息
        
        Returns:
            工具参数
        """
        if tool_name == "web_search":
            # 提取搜索关键词
            # 简单实现：去掉常见词，保留核心内容
            keywords_to_remove = ["你能", "帮我", "查", "查找", "搜索", "查询", "一下", "的", "吗", "么", "？", "?"]
            query = message
            for kw in keywords_to_remove:
                query = query.replace(kw, " ")
            query = query.strip()
            
            # 如果清理后为空，使用原始消息
            if not query or len(query) < 2:
                query = message
            
            # 🔧 保留时间限定词（今天、昨天、本周等）
            # 不删除“今天”等时间词，让搜索更精确
            
            return {"query": query, "max_results": 5}
        
        elif tool_name == "image_generator":
            # 提取图片描述
            # 去掉常见的生成图片相关词汇
            keywords_to_remove = ["生成", "生成一张", "生成一个", "给我", "来张", "来个", "帮我", "你帮我", "图片", "图像", "照片", "生成图片", "生成图像"]
            prompt = message
            for kw in keywords_to_remove:
                prompt = prompt.replace(kw, " ")
            prompt = prompt.strip()
            
            # 如果清理后为空，使用原始消息
            if not prompt or len(prompt) < 2:
                prompt = message
            
            return {"prompt": prompt, "size": "576x1024"}

        elif tool_name == "read_file":
            # 提取文件路径
            # 简单实现:查找路径模式
            import re
            path_match = re.search(r'[/\w/\-\.]+', message)
            if path_match:
                return {"file_path": path_match.group(0)}
            return {}

        elif tool_name == "list_dir":
            # 提取目录路径
            import re
            path_match = re.search(r'[/\w/\-\.]+', message)
            if path_match:
                return {"dir_path": path_match.group(0)}
            return {"dir_path": "."}

        elif tool_name == "execute_code":
            # 提取代码
            # 简单实现:查找代码块
            import re
            code_match = re.search(r'```python\n(.*?)\n```', message, re.DOTALL)
            if code_match:
                return {"code": code_match.group(1)}
            return {}

        return {}
