# -*- coding: utf-8 -*-
"""
智能体自主能力层

让专职智能体能够：
1. 编写/调用技能
2. 编写/调用工具
3. 总结/优化经验
4. 生成能力画像
"""
import json
import logging
import os
import asyncio
from typing import Dict, List, Optional, Any
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, asdict


logger = logging.getLogger(__name__)


@dataclass
class Skill:
    """技能定义"""
    name: str
    description: str
    code: str  # Python 代码
    tools_required: List[str]
    created_at: str
    success_count: int = 0
    failed_count: int = 0


@dataclass
class CustomTool:
    """自定义工具"""
    name: str
    description: str
    code: str  # Python 函数代码
    parameters: Dict[str, Any]
    created_at: str
    usage_count: int = 0


@dataclass
class Experience:
    """经验记录"""
    timestamp: str
    task: str
    approach: str
    result: str  # "success" | "failed"
    lesson: str  # 学到的教训
    tools_used: List[str]
    skills_used: List[str]


class AgentCapabilities:
    """智能体自主能力管理"""
    
    def __init__(
        self,
        agent_id: str,
        storage_path: str = "/root/.openclaw/workspace/bayi-agent/agent_data"
    ):
        self.agent_id = agent_id
        self.storage_path = Path(storage_path) / agent_id
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        # 能力存储
        self.skills: Dict[str, Skill] = {}
        self.custom_tools: Dict[str, CustomTool] = {}
        self.experiences: List[Experience] = []
        
        # 加载已有能力
        self._load_capabilities()
        
        logger.info(f"智能体 {agent_id} 能力层初始化: {len(self.skills)} 技能, {len(self.custom_tools)} 工具")
    
    def _load_capabilities(self):
        """加载已有能力"""
        # 加载技能
        skills_file = self.storage_path / "skills.json"
        if skills_file.exists():
            try:
                with open(skills_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for name, skill_data in data.items():
                        self.skills[name] = Skill(**skill_data)
            except Exception as e:
                logger.error(f"加载技能失败: {e}")
        
        # 加载自定义工具
        tools_file = self.storage_path / "custom_tools.json"
        if tools_file.exists():
            try:
                with open(tools_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for name, tool_data in data.items():
                        self.custom_tools[name] = CustomTool(**tool_data)
            except Exception as e:
                logger.error(f"加载自定义工具失败: {e}")
        
        # 加载经验
        exp_file = self.storage_path / "experiences.json"
        if exp_file.exists():
            try:
                with open(exp_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for exp_data in data:
                        self.experiences.append(Experience(**exp_data))
            except Exception as e:
                logger.error(f"加载经验失败: {e}")
    
    def _save_skills(self):
        """保存技能"""
        skills_file = self.storage_path / "skills.json"
        with open(skills_file, 'w', encoding='utf-8') as f:
            json.dump({name: asdict(skill) for name, skill in self.skills.items()}, f, indent=2, ensure_ascii=False)
    
    def _save_custom_tools(self):
        """保存自定义工具"""
        tools_file = self.storage_path / "custom_tools.json"
        with open(tools_file, 'w', encoding='utf-8') as f:
            json.dump({name: asdict(tool) for name, tool in self.custom_tools.items()}, f, indent=2, ensure_ascii=False)
    
    def _save_experiences(self):
        """保存经验"""
        exp_file = self.storage_path / "experiences.json"
        with open(exp_file, 'w', encoding='utf-8') as f:
            json.dump([asdict(exp) for exp in self.experiences], f, indent=2, ensure_ascii=False)
    
    # ========== 技能管理 ==========
    
    async def create_skill(
        self,
        name: str,
        description: str,
        code: str,
        tools_required: List[str] = None
    ) -> Skill:
        """
        创建技能
        
        Args:
            name: 技能名称
            description: 描述
            code: Python 代码
            tools_required: 所需工具列表
        
        Returns:
            创建的技能
        """
        skill = Skill(
            name=name,
            description=description,
            code=code,
            tools_required=tools_required or [],
            created_at=datetime.now().isoformat()
        )
        
        self.skills[name] = skill
        self._save_skills()
        
        logger.info(f"智能体 {self.agent_id} 创建技能: {name}")
        return skill
    
    async def invoke_skill(
        self,
        name: str,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        调用技能
        
        Args:
            name: 技能名称
            context: 执行上下文
        
        Returns:
            执行结果
        """
        skill = self.skills.get(name)
        if not skill:
            return {"success": False, "error": f"技能不存在: {name}"}
        
        try:
            # 创建执行环境
            exec_globals = {"context": context, "result": None}
            exec(skill.code, exec_globals)
            
            result = exec_globals.get("result")
            
            # 记录成功
            skill.success_count += 1
            self._save_skills()
            
            return {"success": True, "result": result}
        
        except Exception as e:
            # 记录失败
            skill.failed_count += 1
            self._save_skills()
            
            logger.error(f"技能执行失败: {name} - {e}")
            return {"success": False, "error": str(e)}
    
    def list_skills(self) -> List[Dict[str, Any]]:
        """列出所有技能"""
        return [
            {
                "name": skill.name,
                "description": skill.description,
                "success_rate": skill.success_count / max(1, skill.success_count + skill.failed_count),
                "usage": skill.success_count + skill.failed_count
            }
            for skill in self.skills.values()
        ]
    
    # ========== 自定义工具管理 ==========
    
    async def create_tool(
        self,
        name: str,
        description: str,
        code: str,
        parameters: Dict[str, Any] = None
    ) -> CustomTool:
        """
        创建自定义工具
        
        Args:
            name: 工具名称
            description: 描述
            code: Python 函数代码
            parameters: 参数定义
        
        Returns:
            创建的工具
        """
        tool = CustomTool(
            name=name,
            description=description,
            code=code,
            parameters=parameters or {},
            created_at=datetime.now().isoformat()
        )
        
        self.custom_tools[name] = tool
        self._save_custom_tools()
        
        logger.info(f"智能体 {self.agent_id} 创建工具: {name}")
        return tool
    
    async def invoke_tool(
        self,
        name: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        调用自定义工具
        
        Args:
            name: 工具名称
            **kwargs: 工具参数
        
        Returns:
            执行结果
        """
        tool = self.custom_tools.get(name)
        if not tool:
            return {"success": False, "error": f"工具不存在: {name}"}
        
        try:
            # 创建执行环境
            exec_globals = {"kwargs": kwargs, "result": None}
            exec(tool.code, exec_globals)
            
            result = exec_globals.get("result")
            
            # 记录使用
            tool.usage_count += 1
            self._save_custom_tools()
            
            return {"success": True, "result": result}
        
        except Exception as e:
            logger.error(f"工具执行失败: {name} - {e}")
            return {"success": False, "error": str(e)}
    
    def list_tools(self) -> List[Dict[str, Any]]:
        """列出所有自定义工具"""
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "usage_count": tool.usage_count
            }
            for tool in self.custom_tools.values()
        ]
    
    # ========== 经验管理 ==========
    
    async def record_experience(
        self,
        task: str,
        approach: str,
        result: str,
        lesson: str,
        tools_used: List[str] = None,
        skills_used: List[str] = None
    ):
        """
        记录经验
        
        Args:
            task: 任务描述
            approach: 采用的方法
            result: 结果 ("success" | "failed")
            lesson: 学到的教训
            tools_used: 使用的工具
            skills_used: 使用的技能
        """
        experience = Experience(
            timestamp=datetime.now().isoformat(),
            task=task,
            approach=approach,
            result=result,
            lesson=lesson,
            tools_used=tools_used or [],
            skills_used=skills_used or []
        )
        
        self.experiences.append(experience)
        self._save_experiences()
        
        logger.info(f"智能体 {self.agent_id} 记录经验: {result} - {lesson[:50]}")
    
    def summarize_experiences(self, limit: int = 20) -> Dict[str, Any]:
        """
        总结经验
        
        Args:
            limit: 分析最近 N 条经验
        
        Returns:
            经验总结
        """
        recent = self.experiences[-limit:] if len(self.experiences) > limit else self.experiences
        
        if not recent:
            return {"success_rate": 0, "common_tools": [], "lessons": []}
        
        # 统计成功率
        success_count = sum(1 for exp in recent if exp.result == "success")
        success_rate = success_count / len(recent)
        
        # 统计常用工具
        tool_count = {}
        for exp in recent:
            for tool in exp.tools_used:
                tool_count[tool] = tool_count.get(tool, 0) + 1
        
        common_tools = sorted(tool_count.items(), key=lambda x: x[1], reverse=True)[:5]
        
        # 提取教训
        lessons = [
            {"lesson": exp.lesson, "result": exp.result}
            for exp in recent[-10:]  # 最近 10 条
            if exp.lesson
        ]
        
        return {
            "success_rate": success_rate,
            "total_experiences": len(self.experiences),
            "recent_count": len(recent),
            "common_tools": [{"tool": t, "count": c} for t, c in common_tools],
            "lessons": lessons
        }
    
    # ========== 能力画像 ==========
    
    def get_capability_profile(self) -> Dict[str, Any]:
        """
        获取能力画像
        
        Returns:
            能力画像数据
        """
        # 技能统计
        skills_stats = {
            "total": len(self.skills),
            "by_success_rate": {}
        }
        
        for skill in self.skills.values():
            rate = skill.success_count / max(1, skill.success_count + skill.failed_count)
            rate_bucket = f"{int(rate * 10) * 10}-{int(rate * 10) * 10 + 10}%"
            if rate_bucket not in skills_stats["by_success_rate"]:
                skills_stats["by_success_rate"][rate_bucket] = 0
            skills_stats["by_success_rate"][rate_bucket] += 1
        
        # 工具统计
        tools_stats = {
            "total": len(self.custom_tools),
            "total_usage": sum(t.usage_count for t in self.custom_tools.values())
        }
        
        # 经验统计
        exp_summary = self.summarize_experiences()
        
        return {
            "agent_id": self.agent_id,
            "skills": skills_stats,
            "tools": tools_stats,
            "experience": exp_summary,
            "generated_at": datetime.now().isoformat()
        }
    
    # ========== 自我优化 ==========
    
    async def optimize_from_experience(self) -> Dict[str, Any]:
        """
        基于经验自我优化
        
        分析历史经验，生成优化建议
        
        Returns:
            优化建议
        """
        exp_summary = self.summarize_experiences(limit=50)
        
        suggestions = []
        
        # 1. 成功率分析
        success_rate = exp_summary.get("success_rate", 0)
        if success_rate < 0.5:
            suggestions.append({
                "type": "success_rate_low",
                "priority": "high",
                "suggestion": f"成功率仅 {success_rate:.1%}，建议优化核心方法或增加工具支持",
                "action": "review_approach"
            })
        
        # 2. 工具使用分析
        common_tools = exp_summary.get("common_tools", [])
        if common_tools:
            most_used = common_tools[0]
            suggestions.append({
                "type": "tool_usage",
                "priority": "medium",
                "suggestion": f"最常用工具: {most_used['tool']} ({most_used['count']} 次)，可考虑封装为技能",
                "action": "create_skill"
            })
        
        # 3. 失败教训分析
        lessons = exp_summary.get("lessons", [])
        failed_lessons = [l for l in lessons if l["result"] == "failed"]
        if len(failed_lessons) >= 3:
            suggestions.append({
                "type": "repeated_failures",
                "priority": "high",
                "suggestion": f"近期失败 {len(failed_lessons)} 次，需要调整策略",
                "action": "adjust_strategy",
                "lessons": [l["lesson"] for l in failed_lessons[-3:]]
            })
        
        logger.info(f"智能体 {self.agent_id} 自我优化: {len(suggestions)} 条建议")
        
        return {
            "agent_id": self.agent_id,
            "suggestions": suggestions,
            "generated_at": datetime.now().isoformat()
        }
