# -*- coding: utf-8 -*-
"""
智能体注册表

负责管理智能体的创建、注册、持久化和学习
"""
import json
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from pathlib import Path
from datetime import datetime
import os


logger = logging.getLogger(__name__)


@dataclass
class AgentConfig:
    """智能体配置"""
    agent_id: str
    agent_type: str  # "specialized" | "temporary" | "custom"
    skills: List[str]
    tools: List[str]
    description: str
    capabilities: List[str] = None  # 能力标签
    created_at: str = ""
    updated_at: str = ""
    optimization_count: int = 0
    success_count: int = 0
    failed_count: int = 0
    
    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        if not self.updated_at:
            self.updated_at = datetime.now().isoformat()
        if self.capabilities is None:
            self.capabilities = []


class AgentRegistry:
    """智能体注册表"""
    
    # 预定义专职智能体模板
    BUILTIN_AGENTS = {
        "architect": {
            "skills": ["architecture-analysis", "design-patterns"],
            "tools": ["read_file", "web_search", "execute_code"],
            "description": "架构分析专家",
            "capabilities": ["code_analysis", "pattern_recognition", "optimization"]
        },
        "analyst": {
            "skills": ["data-analysis", "statistics"],
            "tools": ["read_file", "execute_code", "web_search"],
            "description": "数据分析专家",
            "capabilities": ["data_processing", "visualization", "statistical_analysis"]
        },
        "researcher": {
            "skills": ["web-search", "document-analysis"],
            "tools": ["web_search", "read_file", "execute_code"],
            "description": "研究调查专家",
            "capabilities": ["information_retrieval", "fact_checking", "summarization"]
        },
        "coder": {
            "skills": ["code-analysis", "debugging", "code-generation"],
            "tools": ["read_file", "execute_code", "web_search"],
            "description": "代码分析专家",
            "capabilities": ["code_generation", "debugging", "refactoring"]
        },
        "web-surfer": {
            "skills": ["web-browsing", "information-extraction"],
            "tools": ["web_search", "execute_code"],
            "description": "网络浏览专家",
            "capabilities": ["web_scraping", "api_integration", "content_extraction"]
        }
    }
    
    def __init__(self, storage_path: str = "/root/.openclaw/workspace/bayi-agent/agents"):
        self.storage_path = Path(storage_path)
        self.agents: Dict[str, AgentConfig] = {}
        self.optimizations: Dict[str, List[dict]] = {}  # {agent_id: [optimization_records]}
        self.capabilities: Dict[str, Any] = {}  # {agent_id: AgentCapabilities}
        
        # 确保存储目录存在
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        # 加载已有智能体
        self._load_agents()
        self._load_optimizations()
        
        logger.info(f"智能体注册表初始化完成，已加载 {len(self.agents)} 个智能体")
    
    def _load_agents(self):
        """加载已保存的智能体"""
        agents_file = self.storage_path / "agents.json"
        
        if agents_file.exists():
            try:
                with open(agents_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for agent_id, agent_data in data.items():
                        self.agents[agent_id] = AgentConfig(**agent_data)
                logger.info(f"从 {agents_file} 加载了 {len(self.agents)} 个智能体")
            except Exception as e:
                logger.error(f"加载智能体失败: {e}")
        
        # 注册内置智能体
        for agent_type, config in self.BUILTIN_AGENTS.items():
            agent_id = f"specialized-{agent_type}"
            if agent_id not in self.agents:
                self.agents[agent_id] = AgentConfig(
                    agent_id=agent_id,
                    agent_type="specialized",
                    skills=config["skills"],
                    tools=config["tools"],
                    description=config["description"],
                    capabilities=config.get("capabilities", [])
                )
    
    def _load_optimizations(self):
        """加载优化记录"""
        opt_file = self.storage_path / "agent_optimizations.json"
        
        if opt_file.exists():
            try:
                with open(opt_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for record in data:
                        agent_id = record.get("agent_id")
                        if agent_id:
                            if agent_id not in self.optimizations:
                                self.optimizations[agent_id] = []
                            self.optimizations[agent_id].append(record)
                logger.info(f"加载了 {sum(len(v) for v in self.optimizations.values())} 条优化记录")
            except Exception as e:
                logger.error(f"加载优化记录失败: {e}")
    
    def _save_agents(self):
        """保存智能体配置"""
        agents_file = self.storage_path / "agents.json"
        
        try:
            data = {agent_id: asdict(agent) for agent_id, agent in self.agents.items()}
            with open(agents_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.info(f"智能体配置已保存到 {agents_file}")
        except Exception as e:
            logger.error(f"保存智能体失败: {e}")
    
    def register(self, agent: AgentConfig) -> bool:
        """
        注册智能体
        
        Args:
            agent: 智能体配置
        
        Returns:
            是否注册成功
        """
        try:
            agent.updated_at = datetime.now().isoformat()
            self.agents[agent.agent_id] = agent
            self._save_agents()
            logger.info(f"智能体已注册: {agent.agent_id} ({agent.agent_type})")
            return True
        except Exception as e:
            logger.error(f"注册智能体失败: {e}")
            return False
    
    def unregister(self, agent_id: str) -> bool:
        """
        注销智能体
        
        Args:
            agent_id: 智能体 ID
        
        Returns:
            是否注销成功
        """
        if agent_id in self.agents:
            del self.agents[agent_id]
            self._save_agents()
            logger.info(f"智能体已注销: {agent_id}")
            return True
        return False
    
    def get(self, agent_id: str) -> Optional[AgentConfig]:
        """
        获取智能体配置
        
        Args:
            agent_id: 智能体 ID
        
        Returns:
            智能体配置，不存在则返回 None
        """
        return self.agents.get(agent_id)
    
    def list_agents(self, agent_type: str = None) -> List[AgentConfig]:
        """
        列出智能体
        
        Args:
            agent_type: 过滤类型（可选）
        
        Returns:
            智能体列表
        """
        if agent_type:
            return [a for a in self.agents.values() if a.agent_type == agent_type]
        return list(self.agents.values())
    
    def create_custom_agent(
        self,
        name: str,
        skills: List[str],
        tools: List[str],
        description: str
    ) -> AgentConfig:
        """
        创建自定义智能体
        
        Args:
            name: 智能体名称
            skills: 技能列表
            tools: 工具列表
            description: 描述
        
        Returns:
            创建的智能体配置
        """
        agent_id = f"custom-{name}"
        
        # 检查是否已存在
        if agent_id in self.agents:
            logger.warning(f"智能体已存在: {agent_id}，将更新配置")
            agent = self.agents[agent_id]
            agent.skills = skills
            agent.tools = tools
            agent.description = description
            agent.updated_at = datetime.now().isoformat()
        else:
            agent = AgentConfig(
                agent_id=agent_id,
                agent_type="custom",
                skills=skills,
                tools=tools,
                description=description
            )
        
        self.register(agent)
        return agent
    
    def update_agent(
        self,
        agent_id: str,
        skills: List[str] = None,
        tools: List[str] = None,
        description: str = None
    ) -> Optional[AgentConfig]:
        """
        更新智能体配置
        
        Args:
            agent_id: 智能体 ID
            skills: 新技能列表（可选）
            tools: 新工具列表（可选）
            description: 新描述（可选）
        
        Returns:
            更新后的智能体配置
        """
        agent = self.agents.get(agent_id)
        if not agent:
            logger.warning(f"智能体不存在: {agent_id}")
            return None
        
        if skills is not None:
            agent.skills = skills
        if tools is not None:
            agent.tools = tools
        if description is not None:
            agent.description = description
        
        agent.updated_at = datetime.now().isoformat()
        self._save_agents()
        logger.info(f"智能体已更新: {agent_id}")
        return agent
    
    def optimize_agent(
        self,
        agent_id: str,
        optimization: dict
    ) -> Optional[AgentConfig]:
        """
        优化智能体（应用优化建议）
        
        Args:
            agent_id: 智能体 ID
            optimization: 优化建议
        
        Returns:
            优化后的智能体配置
        """
        agent = self.agents.get(agent_id)
        if not agent:
            logger.warning(f"智能体不存在: {agent_id}")
            return None
        
        # 应用工具优化
        tools_add = optimization.get('tools_add', [])
        tools_remove = optimization.get('tools_remove', [])
        
        for tool in tools_add:
            if tool not in agent.tools:
                agent.tools.append(tool)
                logger.info(f"  ✓ 智能体 {agent_id} 添加工具: {tool}")
        
        for tool in tools_remove:
            if tool in agent.tools:
                agent.tools.remove(tool)
                logger.info(f"  ✓ 智能体 {agent_id} 移除工具: {tool}")
        
        # 更新统计信息
        agent.optimization_count += 1
        agent.updated_at = datetime.now().isoformat()
        
        # 记录优化
        if agent_id not in self.optimizations:
            self.optimizations[agent_id] = []
        self.optimizations[agent_id].append({
            "timestamp": datetime.now().isoformat(),
            "optimization": optimization
        })
        
        # 保存
        self._save_agents()
        self._save_optimizations()
        
        logger.info(f"智能体已优化: {agent_id} (累计 {agent.optimization_count} 次)")
        return agent
    
    def record_execution(self, agent_id: str, success: bool):
        """
        记录执行结果
        
        Args:
            agent_id: 智能体 ID
            success: 是否成功
        """
        agent = self.agents.get(agent_id)
        if agent:
            if success:
                agent.success_count += 1
            else:
                agent.failed_count += 1
            agent.updated_at = datetime.now().isoformat()
            self._save_agents()
    
    def learn_from_optimizations(self, agent_id: str) -> dict:
        """
        从优化记录中学习
        
        分析历史优化记录，提取常见模式
        
        Args:
            agent_id: 智能体 ID
        
        Returns:
            学习结果 {"common_tools_add": [...], "suggestions": [...]}
        """
        optimizations = self.optimizations.get(agent_id, [])
        
        if not optimizations:
            return {"common_tools_add": [], "suggestions": []}
        
        # 分析工具添加模式
        tools_add_count = {}
        for opt_record in optimizations:
            opt = opt_record.get("optimization", {})
            for tool in opt.get("tools_add", []):
                tools_add_count[tool] = tools_add_count.get(tool, 0) + 1
        
        # 找出频繁添加的工具（出现 2 次以上）
        common_tools_add = [
            tool for tool, count in tools_add_count.items()
            if count >= 2
        ]
        
        # 分析提示词增强建议
        prompt_suggestions = []
        for opt_record in optimizations:
            opt = opt_record.get("optimization", {})
            prompt = opt.get("prompt_enhancement", "")
            if prompt:
                prompt_suggestions.append(prompt)
        
        result = {
            "common_tools_add": common_tools_add,
            "suggestions": prompt_suggestions[-3:] if prompt_suggestions else [],  # 最近 3 条
            "optimization_count": len(optimizations)
        }
        
        logger.info(f"智能体 {agent_id} 学习结果: {result}")
        return result
    
    def auto_improve(self, agent_id: str) -> Optional[AgentConfig]:
        """
        自动改进智能体
        
        基于历史优化记录自动调整智能体配置
        
        Args:
            agent_id: 智能体 ID
        
        Returns:
            改进后的智能体配置
        """
        agent = self.agents.get(agent_id)
        if not agent:
            return None
        
        # 学习优化模式
        learning = self.learn_from_optimizations(agent_id)
        
        # 自动添加常用工具
        common_tools = learning.get("common_tools_add", [])
        auto_optimization = {
            "tools_add": [],
            "tools_remove": [],
            "prompt_enhancement": "",
            "skill_adjustment": ""
        }
        
        for tool in common_tools:
            if tool not in agent.tools:
                auto_optimization["tools_add"].append(tool)
                logger.info(f"智能体 {agent_id} 自动学习添加工具: {tool}")
        
        if auto_optimization["tools_add"]:
            return self.optimize_agent(agent_id, auto_optimization)
        
        return agent
    
    def _save_optimizations(self):
        """保存优化记录"""
        opt_file = self.storage_path / "agent_optimizations.json"
        
        try:
            all_records = []
            for agent_id, records in self.optimizations.items():
                all_records.extend(records)
            
            with open(opt_file, 'w', encoding='utf-8') as f:
                json.dump(all_records, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"保存优化记录失败: {e}")
    
    def get_stats(self) -> dict:
        """
        获取统计信息
        
        Returns:
            统计数据
        """
        stats = {
            "total_agents": len(self.agents),
            "by_type": {},
            "total_optimizations": sum(len(v) for v in self.optimizations.values()),
            "total_success": sum(a.success_count for a in self.agents.values()),
            "total_failed": sum(a.failed_count for a in self.agents.values())
        }
        
        for agent in self.agents.values():
            agent_type = agent.agent_type
            if agent_type not in stats["by_type"]:
                stats["by_type"][agent_type] = 0
            stats["by_type"][agent_type] += 1
        
        return stats
    
    # ========== 能力层管理 ==========
    
    def get_capabilities(self, agent_id: str) -> Optional[Any]:
        """
        获取智能体的能力层
        
        Args:
            agent_id: 智能体 ID
        
        Returns:
            AgentCapabilities 实例
        """
        if agent_id not in self.capabilities:
            from .agent_capabilities import AgentCapabilities
            self.capabilities[agent_id] = AgentCapabilities(agent_id)
        
        return self.capabilities[agent_id]
    
    async def create_skill_for_agent(
        self,
        agent_id: str,
        skill_name: str,
        description: str,
        code: str,
        tools_required: List[str] = None
    ) -> Optional[dict]:
        """
        为智能体创建技能
        
        Args:
            agent_id: 智能体 ID
            skill_name: 技能名称
            description: 描述
            code: Python 代码
            tools_required: 所需工具
        
        Returns:
            创建的技能
        """
        capabilities = self.get_capabilities(agent_id)
        if not capabilities:
            return None
        
        skill = await capabilities.create_skill(
            name=skill_name,
            description=description,
            code=code,
            tools_required=tools_required
        )
        
        # 更新智能体配置
        agent = self.agents.get(agent_id)
        if agent and skill_name not in agent.skills:
            agent.skills.append(skill_name)
            self._save_agents()
        
        return {
            "name": skill.name,
            "description": skill.description,
            "tools_required": skill.tools_required
        }
    
    async def create_tool_for_agent(
        self,
        agent_id: str,
        tool_name: str,
        description: str,
        code: str,
        parameters: dict = None
    ) -> Optional[dict]:
        """
        为智能体创建自定义工具
        
        Args:
            agent_id: 智能体 ID
            tool_name: 工具名称
            description: 描述
            code: Python 函数代码
            parameters: 参数定义
        
        Returns:
            创建的工具
        """
        capabilities = self.get_capabilities(agent_id)
        if not capabilities:
            return None
        
        tool = await capabilities.create_tool(
            name=tool_name,
            description=description,
            code=code,
            parameters=parameters
        )
        
        # 更新智能体配置
        agent = self.agents.get(agent_id)
        if agent and tool_name not in agent.tools:
            agent.tools.append(tool_name)
            self._save_agents()
        
        return {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters
        }
    
    async def record_agent_experience(
        self,
        agent_id: str,
        task: str,
        approach: str,
        result: str,
        lesson: str,
        tools_used: List[str] = None,
        skills_used: List[str] = None
    ):
        """
        记录智能体经验
        
        Args:
            agent_id: 智能体 ID
            task: 任务描述
            approach: 采用的方法
            result: 结果 ("success" | "failed")
            lesson: 学到的教训
            tools_used: 使用的工具
            skills_used: 使用的技能
        """
        capabilities = self.get_capabilities(agent_id)
        if capabilities:
            await capabilities.record_experience(
                task=task,
                approach=approach,
                result=result,
                lesson=lesson,
                tools_used=tools_used,
                skills_used=skills_used
            )
    
    def get_agent_capability_profile(self, agent_id: str) -> Optional[dict]:
        """
        获取智能体能力画像
        
        Args:
            agent_id: 智能体 ID
        
        Returns:
            能力画像数据
        """
        capabilities = self.get_capabilities(agent_id)
        if not capabilities:
            return None
        
        return capabilities.get_capability_profile()
    
    async def optimize_agent_from_experience(self, agent_id: str) -> Optional[dict]:
        """
        基于经验优化智能体
        
        Args:
            agent_id: 智能体 ID
        
        Returns:
            优化建议
        """
        capabilities = self.get_capabilities(agent_id)
        if not capabilities:
            return None
        
        return await capabilities.optimize_from_experience()
    
    def list_agent_capabilities(self, agent_id: str) -> Optional[dict]:
        """
        列出智能体的所有能力
        
        Args:
            agent_id: 智能体 ID
        
        Returns:
            能力列表
        """
        capabilities = self.get_capabilities(agent_id)
        if not capabilities:
            return None
        
        return {
            "agent_id": agent_id,
            "skills": capabilities.list_skills(),
            "custom_tools": capabilities.list_tools(),
            "experience_summary": capabilities.summarize_experiences()
        }
