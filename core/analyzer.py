"""
决策分析器
职责：收集上下文、拆解任务、调度智能体
"""
import asyncio
import logging
import re
from typing import List, Dict, Optional, Any
from dataclasses import dataclass

from core.models import DecisionTask, SubTask, TaskStatus
from utils.llm_client import LLMClient
from .skill_invoker import SkillInvoker
from .agent_registry import AgentRegistry, AgentConfig as RegistryAgentConfig


logger = logging.getLogger(__name__)


@dataclass
class AgentConfig:
    """智能体配置"""
    agent_id: str
    agent_type: str  # "specialized" 或 "temporary" 或 "custom"
    skills: List[str]
    tools: List[str]
    description: str
    
    @classmethod
    def from_registry(cls, registry_config: RegistryAgentConfig) -> 'AgentConfig':
        """从注册表配置创建"""
        return cls(
            agent_id=registry_config.agent_id,
            agent_type=registry_config.agent_type,
            skills=registry_config.skills,
            tools=registry_config.tools,
            description=registry_config.description
        )


class DecisionAnalyzer:
    """决策分析器"""
    
    # 预定义专职智能体
    SPECIALIZED_AGENTS = {
        "architect": {
            "skills": ["architecture-analysis", "design-patterns"],
            "tools": ["read_file", "web_search"],
            "description": "架构分析专家"
        },
        "analyst": {
            "skills": ["data-analysis", "statistics"],
            "tools": ["read_file", "execute_code"],
            "description": "数据分析专家"
        },
        "researcher": {
            "skills": ["web-search", "document-analysis"],
            "tools": ["web_search", "read_file"],
            "description": "研究调查专家"
        },
        "coder": {
            "skills": ["code-analysis", "debugging"],
            "tools": ["read_file", "execute_code"],
            "description": "代码分析专家"
        }
    }
    
    def __init__(
        self,
        decision_llm: LLMClient,
        max_tokens_per_subtask: int = 5000,
        max_chars_per_subtask: int = 15000,
        model_pool: Dict[str, Any] = None
    ):
        self.decision_llm = decision_llm
        self.max_tokens_per_subtask = max_tokens_per_subtask
        self.max_chars_per_subtask = max_chars_per_subtask
        self.skill_invoker = SkillInvoker()  # 技能调用器
        self.model_pool = model_pool or {}  # 模型池
        self.model_performance = {}  # 模型性能记录 {model_name: {task_type: {success: N, failed: M}}}
        self.current_llm = None  # 当前子智能体使用的 LLM
        
        # 🔧 新增：智能体注册表
        self.agent_registry = AgentRegistry()
        
        logger.info("决策分析器初始化完成")
        if model_pool:
            logger.info(f"模型池配置: {list(model_pool.keys())}")
        
        # 加载性能数据
        self._load_performance()
        
        # 打印智能体统计
        stats = self.agent_registry.get_stats()
        logger.info(f"智能体注册表: {stats['total_agents']} 个智能体, {stats['total_optimizations']} 条优化记录")
    
    async def analyze(self, task: DecisionTask) -> str:
        """
        分析并处理任务
        
        流程：
        1. 收集上下文
        2. 拆分任务（如需要）
        3. 调度智能体
        4. 执行并聚合结果
        
        Args:
            task: 决策任务
        
        Returns:
            处理结果
        """
        logger.info(f"开始分析任务: {task.task_id}")
        
        try:
            # Step 1: 收集上下文
            full_context = await self._collect_context(task)
            
            # Step 2: 分析任务结构
            task_structure = await self._analyze_task_structure(task.message, full_context)
            
            # Step 3: 拆分任务（如需要）
            subtasks = await self._split_task(task_structure, full_context)
            
            # Step 4: 调度智能体
            agent_assignments = await self._schedule_agents(subtasks)
            
            # Step 5: 执行子任务
            results = await self._execute_subtasks(subtasks, agent_assignments, task.message)
            
            # Step 6: 聚合结果
            final_result = self._aggregate_results(results)
            
            logger.info(f"任务完成: {task.task_id}")
            
            # 🔧 新增：保存性能数据
            self._save_performance()
            
            return final_result
        
        except Exception as e:
            logger.error(f"任务分析失败: {task.task_id}, error: {e}", exc_info=True)
            raise
    
    async def _collect_context(self, task: DecisionTask) -> str:
        """
        收集完整上下文
        
        包括：
        - 用户消息
        - 对话历史（最近 20 轮）
        - 完成的任务记录
        - **队列实时任务状态** ⭐ 新增
        - 任务上下文
        - 工作空间信息（动态扫描）
        - 相关知识检索（新增）
        """
        context_parts = [f"用户消息：{task.message}"]
        
        # 🔧 注入对话历史（决策分析器需要上下文）
        if task.context and task.context.conversation_history:
            history_lines = []
            for h in task.context.conversation_history[-40:]:  # 最近 20 轮
                role = "用户" if h["role"] == "user" else "助手"
                history_lines.append(f"{role}: {h['content'][:100]}")
            context_parts.append(f"\n## 对话历史\n{chr(10).join(history_lines)}")
        
        # 🔧 注入任务记录
        if task.context and task.context.last_completed_tasks:
            task_lines = []
            for t in task.context.last_completed_tasks[-5:]:  # 最近 5 个任务
                task_lines.append(f"- {t['task_summary']} → {t['result_summary']}")
            context_parts.append(f"\n## 最近完成的任务\n{chr(10).join(task_lines)}")
        
        # 🔧 新增：注入队列实时任务状态
        if hasattr(self, 'task_queue') and self.task_queue:
            try:
                # 获取当前用户的所有任务
                all_tasks = []
                for task_id, t in self.task_queue.tasks.items():
                    if t.user_id == task.user_id:
                        status_emoji = {
                            "queued": "⏳",
                            "processing": "🔄", 
                            "completed": "✅",
                            "failed": "❌"
                        }.get(t.status.value, "❓")
                        all_tasks.append(f"{status_emoji} {task_id[:20]}... | {t.status.value} | {t.message[:30]}")
                
                if all_tasks:
                    context_parts.append(f"\n## 当前任务状态（实时）\n{chr(10).join(all_tasks[-10:])}")
            except Exception as e:
                logger.warning(f"获取队列实时状态失败: {e}")
        
        # 添加任务上下文
        if task.context:
            context_parts.append(f"\n渠道：{task.context.channel}")
            context_parts.append(f"聊天类型：{task.context.chat_type}")
        
        # 🔧 动态扫描工作空间信息
        workspace_info = await self._scan_workspace()
        context_parts.append(f"\n## 工作空间信息\n{workspace_info}")
        
        # 🔧 新增：相关知识检索
        relevant_knowledge = await self._retrieve_relevant_knowledge(task.message)
        if relevant_knowledge:
            context_parts.append(f"\n## 相关知识\n{relevant_knowledge}")
        
        return "\n".join(context_parts)
    
    async def _scan_workspace(self) -> str:
        """
        动态扫描工作空间
        
        Returns:
            工作空间信息字符串
        """
        import os
        from pathlib import Path
        
        workspace_root = "/root/.openclaw/workspace"
        info_lines = [f"工作空间根目录: {workspace_root}"]
        
        try:
            # 扫描常见目录
            common_dirs = [
                ("DOCS/规划/", "规划文档"),
                ("DOCS/经验/", "经验文档"),
                ("memory/", "记忆文件"),
                ("bayi-agent/", "Bayi-Agent 项目")
            ]
            
            info_lines.append("\n常见文档目录:")
            for dir_path, desc in common_dirs:
                full_path = os.path.join(workspace_root, dir_path)
                if os.path.exists(full_path):
                    # 统计文件数量
                    file_count = sum(1 for _, _, files in os.walk(full_path) for f in files if not f.startswith('.'))
                    info_lines.append(f"  ✓ {dir_path} ({desc}, {file_count} 个文件)")
                else:
                    info_lines.append(f"  ✗ {dir_path} (不存在)")
            
            # 检查当前工作目录
            cwd = os.getcwd()
            info_lines.append(f"\n当前工作目录: {cwd}")
            
        except Exception as e:
            logger.warning(f"扫描工作空间失败: {e}")
            info_lines.append(f"扫描失败: {e}")
        
        return "\n".join(info_lines)
    
    async def _retrieve_relevant_knowledge(self, message: str) -> str:
        """
        检索相关知识
        
        根据用户消息关键词，从文档目录检索相关内容
        
        Args:
            message: 用户消息
        
        Returns:
            相关知识字符串
        """
        import os
        from pathlib import Path
        
        # 提取关键词
        keywords = []
        message_lower = message.lower()
        
        # 关键词映射
        keyword_map = {
            "bayi": ["bayi-agent", "bayiagent"],
            "规划": ["plan", "规划", "roadmap"],
            "文档": ["doc", "文档", "readme"],
            "任务": ["task", "任务"],
            "智能体": ["agent", "智能体"],
            "决策": ["decision", "决策"],
        }
        
        for key, kw_list in keyword_map.items():
            if key in message_lower:
                keywords.extend(kw_list)
        
        if not keywords:
            return ""
        
        # 检索相关文件
        workspace_root = "/root/.openclaw/workspace"
        search_dirs = ["DOCS/规划/", "DOCS/经验/", "memory/"]
        
        relevant_files = []
        try:
            for search_dir in search_dirs:
                full_dir = os.path.join(workspace_root, search_dir)
                if not os.path.exists(full_dir):
                    continue
                
                for root, dirs, files in os.walk(full_dir):
                    # 跳过隐藏目录
                    dirs[:] = [d for d in dirs if not d.startswith('.')]
                    
                    for file in files:
                        if file.startswith('.'):
                            continue
                        
                        file_lower = file.lower()
                        # 检查文件名是否匹配关键词
                        if any(kw in file_lower for kw in keywords):
                            rel_path = os.path.relpath(os.path.join(root, file), workspace_root)
                            relevant_files.append(rel_path)
        
        except Exception as e:
            logger.warning(f"检索相关知识失败: {e}")
            return ""
        
        if not relevant_files:
            return ""
        
        # 返回找到的相关文件
        knowledge_lines = [f"找到 {len(relevant_files)} 个相关文件:"]
        for i, file_path in enumerate(relevant_files[:10], 1):  # 最多显示 10 个
            knowledge_lines.append(f"  {i}. {file_path}")
        
        if len(relevant_files) > 10:
            knowledge_lines.append(f"  ... 还有 {len(relevant_files) - 10} 个文件")
        
        return "\n".join(knowledge_lines)
    
    async def _analyze_task_structure(
        self,
        message: str,
        context: str
    ) -> Dict[str, Any]:
        """
        分析任务结构
        
        返回：
        - task_type: "single" | "parallel" | "sequential"
        - subtask_count: 子任务数量
        - required_skills: 需要的技能
        - required_tools: 需要的工具
        """
        prompt = f"""分析以下任务的结构。

任务消息：{message}

上下文：
{context}

输出 JSON 格式：
{{
  "task_type": "single|parallel|sequential",
  "subtask_count": 1,
  "required_skills": ["skill1", "skill2"],
  "required_tools": ["tool1", "tool2"],
  "complexity": "low|medium|high",
  "estimated_time": 30
}}

只输出 JSON，不要解释。"""

        response = await self.decision_llm.chat([
            {"role": "user", "content": prompt}
        ])
        
        try:
            # 提取 JSON
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                return eval(json_match.group(0))  # 简单实现，生产环境用 json.loads
        except Exception as e:
            logger.warning(f"解析任务结构失败: {e}")
        
        # 默认返回
        return {
            "task_type": "single",
            "subtask_count": 1,
            "required_skills": [],
            "required_tools": [],
            "complexity": "medium"
        }
    
    async def _split_task(
        self,
        task_structure: Dict[str, Any],
        full_context: str
    ) -> List[SubTask]:
        """
        拆分任务
        
        策略：
        1. 判断是否需要拆分（上下文大小、任务类型）
        2. 按模块/阶段拆分
        3. 确保每个子任务独立
        """
        # 判断是否需要拆分
        context_size = len(full_context)
        
        if (context_size < self.max_chars_per_subtask and 
            task_structure.get("subtask_count", 1) == 1):
            # 不需要拆分
            return [
                SubTask(
                    id="main",
                    context=full_context,
                    dependencies=[],
                    scope="all"
                )
            ]
        
        # 需要拆分
        prompt = f"""将以下任务拆分为多个独立的子任务。

完整上下文：
{full_context}

任务类型：{task_structure.get('task_type', 'single')}

输出 JSON 数组格式：
[
  {{
    "id": "subtask-1",
    "context": "子任务上下文",
    "dependencies": [],
    "scope": "scope-name"
  }}
]

只输出 JSON 数组，不要解释。"""

        response = await self.decision_llm.chat([
            {"role": "user", "content": prompt}
        ])
        
        try:
            # 提取 JSON 数组
            json_match = re.search(r'\[.*\]', response, re.DOTALL)
            if json_match:
                subtasks_data = eval(json_match.group(0))
                return [
                    SubTask(**item) for item in subtasks_data
                ]
        except Exception as e:
            logger.warning(f"解析子任务失败: {e}")
        
        # 失败 → 返回单个任务
        return [
            SubTask(
                id="main",
                context=full_context,
                dependencies=[],
                scope="all"
            )
        ]
    
    async def _schedule_agents(
        self,
        subtasks: List[SubTask]
    ) -> Dict[str, AgentConfig]:
        """
        调度智能体
        
        策略：
        1. 核心任务 → 从注册表获取智能体（优先使用已优化的）
        2. 辅助任务 → 创建临时智能体
        3. 如果注册表中没有合适的，使用预定义模板
        """
        logger.info(f"开始调度智能体，子任务数量: {len(subtasks)}")
        assignments = {}
        
        for idx, subtask in enumerate(subtasks):
            logger.info(f"--- 调度子任务 {subtask.id} (index: {idx}) ---")
            
            # 判断任务类型
            is_core = idx == 0 or not subtask.dependencies
            logger.info(f"任务类型: {'核心任务' if is_core else '辅助任务'}")
            
            if is_core:
                # 核心任务 → 选择专职智能体
                agent_type = self._select_specialized_agent(subtask.context)
                logger.info(f"选择专职智能体类型: {agent_type}")
                
                # 🔧 从注册表获取（包含历史优化）
                agent_id = f"specialized-{agent_type}"
                registry_agent = self.agent_registry.get(agent_id)
                
                if registry_agent:
                    # 使用注册表中的智能体（可能已被优化）
                    agent = AgentConfig.from_registry(registry_agent)
                    logger.info(f"从注册表加载智能体: {agent.agent_id}")
                    logger.info(f"  - 优化次数: {registry_agent.optimization_count}")
                    logger.info(f"  - 成功/失败: {registry_agent.success_count}/{registry_agent.failed_count}")
                    
                    # 🔧 自动学习改进
                    if registry_agent.optimization_count > 0:
                        self.agent_registry.auto_improve(agent_id)
                        # 重新获取更新后的配置
                        registry_agent = self.agent_registry.get(agent_id)
                        agent = AgentConfig.from_registry(registry_agent)
                        logger.info(f"  - 自动学习后工具: {agent.tools}")
                else:
                    # 注册表中没有，使用预定义模板
                    agent_config = self.SPECIALIZED_AGENTS.get(
                        agent_type,
                        self.SPECIALIZED_AGENTS["researcher"]
                    )
                    
                    agent = AgentConfig(
                        agent_id=agent_id,
                        agent_type="specialized",
                        skills=agent_config["skills"],
                        tools=agent_config["tools"],
                        description=agent_config["description"]
                    )
                    
                    # 注册到注册表
                    from core.agent_registry import AgentConfig as RegistryConfig
                    self.agent_registry.register(RegistryConfig(
                        agent_id=agent.agent_id,
                        agent_type=agent.agent_type,
                        skills=agent.skills,
                        tools=agent.tools,
                        description=agent.description
                    ))
                
                logger.info(f"智能体配置: {agent.agent_id}")
                logger.info(f"  - 技能: {agent.skills}")
                logger.info(f"  - 工具: {agent.tools}")
                logger.info(f"  - 描述: {agent.description}")
                
                assignments[subtask.id] = agent
            
            else:
                # 辅助任务 → 临时智能体
                agent = AgentConfig(
                    agent_id=f"temp-{idx}",
                    agent_type="temporary",
                    skills=["general"],
                    tools=["read_file", "search_web"],
                    description="临时助手"
                )
                
                logger.info(f"创建临时智能体: {agent.agent_id}")
                logger.info(f"  - 技能: {agent.skills}")
                logger.info(f"  - 工具: {agent.tools}")
                
                assignments[subtask.id] = agent
        
        logger.info(f"智能体调度完成，共分配 {len(assignments)} 个智能体")
        return assignments
    
    def _select_specialized_agent(self, context: str) -> str:
        """
        选择专职智能体
        
        匹配规则（按优先级）：
        - 新闻/搜索/查询/网络 → web-surfer（专门处理网络信息）
        - 代码/调试/执行/脚本 → coder
        - 架构/设计 → architect
        - 数据/统计 → analyst
        - 其他 → researcher
        """
        context_lower = context.lower()
        
        # 🔧 优先匹配 web-surfer（新闻、搜索、网络信息）
        if any(kw in context_lower for kw in [
            "新闻", "资讯", "热点", "搜索", "查询", "网络", "网页", "抓取", "爬取",
            "news", "information", "search", "query", "web", "crawl", "scrape", "browse"
        ]):
            return "web-surfer"
        
        # 🔧 匹配 coder（代码、调试、执行、脚本）
        elif any(kw in context_lower for kw in [
            "代码", "调试", "执行", "脚本", "编程", "函数",
            "code", "debug", "execute", "script", "programming", "function"
        ]):
            return "coder"
        
        # 🔧 匹配 architect
        elif any(kw in context_lower for kw in ["架构", "设计", "architecture", "design"]):
            return "architect"
        
        # 🔧 匹配 analyst
        elif any(kw in context_lower for kw in ["数据", "统计", "分析", "data", "statistics", "analysis"]):
            return "analyst"
        
        # 🔧 默认 researcher
        else:
            return "researcher"
    
    async def _execute_subtasks(
        self,
        subtasks: List[SubTask],
        agent_assignments: Dict[str, AgentConfig],
        original_message: str = ""
    ) -> Dict[str, str]:
        """
        执行子任务
        
        策略：
        1. 按依赖关系排序
        2. 并行执行无依赖的任务
        3. 串行执行有依赖的任务
        """
        logger.info(f"开始执行子任务，总数: {len(subtasks)}")
        results = {}
        
        # 简单实现：串行执行
        # 生产环境可以实现更复杂的并行调度
        for idx, subtask in enumerate(subtasks):
            logger.info(f"========== 执行子任务 {idx+1}/{len(subtasks)}: {subtask.id} ==========")
            logger.info(f"子任务上下文: {subtask.context[:200]}...")
            
            agent = agent_assignments.get(subtask.id)
            
            if not agent:
                logger.error(f"❌ 子任务 {subtask.id} 未分配智能体")
                results[subtask.id] = "未分配智能体"
                continue
            
            logger.info(f"分配的智能体: {agent.agent_id} ({agent.agent_type})")
            
            # Step 1: 执行工具获取实时数据
            tool_results = await self._execute_tools_for_agent(agent, subtask.context, original_message)
            
            # Step 2: 构建增强的上下文
            enhanced_context = subtask.context
            if tool_results:
                enhanced_context += f"\n\n**工具执行结果**:\n{tool_results}"
            
            # Step 3: 调用 LLM 生成回复
            # 🔧 如果有 execute_code 工具，让 LLM 先生成代码
            if "execute_code" in agent.tools:
                logger.info(f"智能体 {agent.agent_id} 有 execute_code 工具，开始生成代码")
                
                # 🔧 确定任务类型和模型
                task_type = self._detect_task_type(enhanced_context)
                
                # 🔧 使用子智能体专用的 LLM（可以切换模型）
                current_llm = self.current_llm or self.decision_llm
                model_name = getattr(current_llm, 'model', 'unknown')
                logger.info(f"任务类型: {task_type}, 子智能体使用模型: {model_name}")
                
                max_retries = 5
                for attempt in range(1, max_retries + 1):
                    logger.info(f"=== 第 {attempt}/{max_retries} 次尝试 ===")
                    
                    # 🔧 检查是否需要切换模型（子智能体专用）
                    if attempt >= 3 and self._should_switch_model(model_name, task_type):
                        backup_model_config = self._get_backup_model(task_type, current_model=model_name)
                        if backup_model_config:
                            logger.warning(f"🔄 子智能体自动切换模型: {model_name} → {backup_model_config.get('name')}")
                            current_llm = self._create_llm_client(backup_model_config)
                            self.current_llm = current_llm
                            model_name = backup_model_config.get('name')
                            logger.info(f"子智能体新模型: {model_name}")
                    
                    # 🔧 构建代码生成提示词，包含智能体配置和优化信息
                    tools_info = f"\n可用工具: {', '.join(agent.tools)}" if agent.tools else ""
                    skills_info = f"\n技能: {', '.join(agent.skills)}" if agent.skills else ""
                    
                    code_prompt = f"""你是 {agent.description}。{skills_info}{tools_info}

任务：{enhanced_context}

请生成 Python 代码来完成这个任务。
要求：
1. 只输出可执行的 Python 代码，不要解释
2. 代码要简洁高效
3. 使用 print() 输出结果
4. 如果需要网络请求，使用 requests 库
5. 如果需要解析 HTML，使用 BeautifulSoup

重要提示：
- 如果需要查找文档或文件，请先检查工作空间信息中提到的目录
- 不要只搜索当前项目目录，要根据任务需求搜索正确的目录
- 常见文档位置：DOCS/规划/、DOCS/经验/、memory/

代码："""
                    
                    code_response = await current_llm.chat([
                        {"role": "user", "content": code_prompt}
                    ])
                    
                    # 提取代码（去掉 markdown 标记）
                    import re
                    code = code_response.strip()
                    code = re.sub(r'^```python\s*', '', code)
                    code = re.sub(r'^```\s*', '', code)
                    code = re.sub(r'\s*```$', '', code)
                    
                    logger.info(f"生成的代码（{len(code)} 字符）:")
                    logger.info(code)
                    
                    # 执行代码
                    tool = self.skill_invoker.registry.get("execute_code")
                    if tool:
                        logger.info("开始执行代码...")
                        code_result = await tool.execute(code=code, timeout=15)
                        
                        if code_result.get("success"):
                            output = code_result.get('output', '')
                            logger.info(f"执行成功，输出（{len(output)} 字符）:")
                            logger.info(output)
                            # 检查输出是否有效（非空且不是错误信息）
                            if output and len(output.strip()) > 0 and 'error' not in output.lower()[:50]:
                                # 🔧 新增：决策审核 - 检查结果是否真正回答了用户问题，并优化智能体
                                review_result = await self._review_execution_result(
                                    output, enhanced_context, original_message, attempt, max_retries, agent
                                )
                                
                                if review_result["pass"]:
                                    result = f"{output}"
                                    logger.info(f"✅ 尝试 {attempt} 成功，审核通过，返回结果")
                                    # 🔧 记录模型性能
                                    self._record_model_performance(model_name, task_type, success=True)
                                    # 🔧 记录智能体成功经验
                                    await self.agent_registry.record_agent_experience(
                                        agent_id=agent.agent_id,
                                        task=subtask.context[:100],
                                        approach="代码执行",
                                        result="success",
                                        lesson=review_result.get("reason", "成功完成任务"),
                                        tools_used=agent.tools,
                                        skills_used=agent.skills
                                    )
                                    break
                                else:
                                    # 审核不通过，重试
                                    logger.warning(f"❌ 尝试 {attempt}/{max_retries}: 审核不通过 - {review_result['reason']}")
                                    # 🔧 记录失败（审核失败也算失败）
                                    self._record_model_performance(model_name, task_type, success=False)
                                    # 🔧 记录智能体失败经验
                                    await self.agent_registry.record_agent_experience(
                                        agent_id=agent.agent_id,
                                        task=subtask.context[:100],
                                        approach="代码执行",
                                        result="failed",
                                        lesson=f"审核不通过: {review_result['reason']}。建议: {review_result['suggestion']}",
                                        tools_used=agent.tools,
                                        skills_used=agent.skills
                                    )
                                    
                                    # 🔧 检查是否需要切换模型
                                    if attempt >= 3 and self._should_switch_model(model_name, task_type):
                                        backup_model_config = self._get_backup_model(task_type, current_model=model_name)
                                        if backup_model_config:
                                            logger.warning(f"🔄 审核失败率过高，自动切换模型: {model_name} → {backup_model_config.get('name')}")
                                            current_llm = self._create_llm_client(backup_model_config)
                                            self.current_llm = current_llm
                                            model_name = backup_model_config.get('name')
                                            logger.info(f"子智能体新模型: {model_name}")
                                    
                                    if attempt < max_retries:
                                        # 🔧 构建重试上下文，包含智能体优化信息
                                        optimization_info = ""
                                        agent_opt = review_result.get('agent_optimization', {})
                                        if agent_opt:
                                            tools_added = agent_opt.get('tools_add', [])
                                            prompt_hint = agent_opt.get('prompt_enhancement', '')
                                            skill_hint = agent_opt.get('skill_adjustment', '')
                                            
                                            if tools_added:
                                                optimization_info += f"\n🔧 可用工具已更新: {', '.join(tools_added)}"
                                            if prompt_hint:
                                                optimization_info += f"\n💡 提示: {prompt_hint}"
                                            if skill_hint:
                                                optimization_info += f"\n🎯 技能建议: {skill_hint}"
                                        
                                        enhanced_context += f"\n\n⚠️ 上次执行结果审核不通过。\n原因: {review_result['reason']}\n建议: {review_result['suggestion']}{optimization_info}\n请换一种更准确的方法。"
                                        continue
                                    else:
                                        result = f"尝试 {max_retries} 次后审核仍未通过：\n{output}\n\n审核意见: {review_result['reason']}"
                                        logger.error(f"❌ 尝试 {max_retries} 次后审核仍未通过")
                            else:
                                # 输出无效，重试
                                logger.warning(f"❌ 尝试 {attempt}/{max_retries}: 输出无效，准备重试")
                                # 🔧 记录失败
                                self._record_model_performance(model_name, task_type, success=False)
                                
                                # 🔧 检查是否需要切换模型
                                if attempt == 3 and self._should_switch_model(model_name, task_type):
                                    logger.warning("模型表现不佳，尝试切换备用模型")
                                    # 这里可以切换模型，但需要重构 LLMClient
                                    # 暂时记录日志
                                    
                                if attempt < max_retries:
                                    enhanced_context += f"\n\n上次尝试失败：输出为空或包含错误。请换一种方法。"
                                    continue
                                else:
                                    result = f"尝试 {max_retries} 次后仍未成功：\n{output}"
                                    logger.error(f"❌ 尝试 {max_retries} 次后仍未成功")
                        else:
                            # 执行失败，重试
                            error_msg = code_result.get('error', '')
                            logger.warning(f"❌ 尝试 {attempt}/{max_retries}: 执行失败 - {error_msg}")
                            # 🔧 记录失败
                            self._record_model_performance(model_name, task_type, success=False)
                            
                            # 🔧 分析失败原因
                            failure_reason = self._analyze_failure(error_msg, code)
                            logger.warning(f"失败原因分析: {failure_reason}")
                            
                            # 🔧 智能重试：根据失败原因调整提示词
                            if attempt < max_retries:
                                # 根据失败原因提供精准的修复建议
                                if "超时" in failure_reason:
                                    if "死循环" in failure_reason:
                                        enhanced_context += "\n\n⚠️ 上次代码超时（可能死循环）。修复建议：\n1. 检查循环条件，确保循环能终止\n2. 添加循环计数器，限制最大迭代次数\n3. 避免在循环中进行耗时操作\n4. 使用 break 语句提前退出循环"
                                    elif "网络请求" in failure_reason:
                                        enhanced_context += "\n\n⚠️ 上次网络请求超时。修复建议：\n1. 设置更短的超时时间（timeout=10）\n2. 使用 try-except 捕获超时异常\n3. 考虑使用异步请求或并发请求\n4. 检查 URL 是否可访问"
                                    else:
                                        enhanced_context += "\n\n⚠️ 上次代码执行超时。修复建议：\n1. 减少循环次数或优化算法复杂度\n2. 避免使用 time.sleep() 或减少等待时间\n3. 减少数据量或分批处理\n4. 使用更高效的数据结构（如 set 替代 list）"
                                
                                elif "缺少依赖库" in failure_reason:
                                    # 提取缺失的库名
                                    import re
                                    module_match = re.search(r"'([^']+)'", failure_reason)
                                    if module_match:
                                        module_name = module_match.group(1)
                                        enhanced_context += f"\n\n⚠️ 上次代码缺少依赖库 '{module_name}'。修复建议：\n1. 使用 Python 标准库替代：os, sys, json, re, datetime, collections, itertools\n2. 检查该库是否在 requirements.txt 中\n3. 如果必须使用第三方库，请明确说明\n4. 避免使用未安装的库"
                                    else:
                                        enhanced_context += "\n\n⚠️ 上次代码缺少依赖库。修复建议：\n1. 只使用 Python 标准库：os, sys, json, re, datetime 等\n2. 不要使用第三方库（如 pandas, numpy, requests 等）\n3. 如果必须使用网络请求，请说明需要的库"
                                
                                elif "语法错误" in failure_reason:
                                    enhanced_context += "\n\n⚠️ 上次代码有语法错误。修复建议：\n1. 检查括号是否匹配：()、[]、{}\n2. 检查缩进是否正确（使用 4 个空格）\n3. 检查引号是否匹配：''、\"\"\"\"\"\"\n4. 检查语句结尾是否有冒号：if、for、while、def、class\n5. 检查字符串是否正确转义"
                                
                                elif "网络连接" in failure_reason:
                                    enhanced_context += "\n\n⚠️ 上次网络连接失败。修复建议：\n1. 检查 URL 是否正确且可访问\n2. 使用 https:// 而不是 http://\n3. 检查网络是否可用\n4. 使用其他备用 API 或数据源"
                                
                                elif "文件不存在" in failure_reason:
                                    enhanced_context += "\n\n⚠️ 上次文件不存在。修复建议：\n1. 检查文件路径是否正确\n2. 使用 os.path.exists() 先检查文件是否存在\n3. 使用绝对路径而不是相对路径\n4. 检查文件名大小写是否正确"
                                
                                elif "输出为空" in failure_reason:
                                    enhanced_context += "\n\n⚠️ 上次输出为空。修复建议：\n1. 检查代码逻辑是否有输出语句（print）\n2. 检查条件判断是否正确\n3. 检查搜索条件是否过严\n4. 添加调试输出，查看中间结果"
                                
                                elif "权限不足" in failure_reason:
                                    enhanced_context += "\n\n⚠️ 上次权限不足。修复建议：\n1. 使用 /tmp/ 目录或其他有权限的目录\n2. 避免写入系统目录\n3. 检查文件权限"
                                
                                else:
                                    enhanced_context += f"\n\n⚠️ 上次尝试失败：{failure_reason}\n修复建议：请修复代码或换一种方法。"
                                
                                continue
                            else:
                                result = f"尝试 {max_retries} 次后仍未成功\n\n失败原因：{failure_reason}\n\n错误详情：{error_msg[:200]}"
                                logger.error(f"❌ 尝试 {max_retries} 次后仍未成功: {failure_reason}")
                    else:
                        result = "代码执行工具不可用"
                        logger.error("代码执行工具不可用")
                        break
            else:
                # 普通回复
                logger.info(f"智能体 {agent.agent_id} 没有代码执行工具，直接生成回复")
                prompt = f"""你是 {agent.description}。

任务上下文：
{enhanced_context}

请完成上述任务。"""

                result = await self.decision_llm.chat([
                    {"role": "user", "content": prompt}
                ])
            
            results[subtask.id] = result
            subtask.result = result
            subtask.status = TaskStatus.COMPLETED
        
        return results
    
    async def _execute_tools_for_agent(
        self,
        agent: AgentConfig,
        context: str,
        original_message: str = ""
    ) -> str:
        """
        为智能体执行工具
        
        Args:
            agent: 智能体配置
            context: 任务上下文
            original_message: 原始用户消息（用于提取工具参数）
        
        Returns:
            工具执行结果（格式化字符串）
        """
        # 检查智能体是否有工具
        if not agent.tools:
            return ""
        
        logger.info(f"为智能体 {agent.agent_id} 执行工具: {agent.tools}")
        
        results = []
        
        for tool_name in agent.tools:
            # 准备工具参数（使用原始消息）
            kwargs = self.skill_invoker._prepare_tool_args(tool_name, original_message or context)
            
            # 🔧 检查必要参数是否存在且有效
            if tool_name == "execute_code" and "code" not in kwargs:
                logger.debug(f"跳过工具 {tool_name}：缺少必要参数 'code'")
                continue
            
            if tool_name == "read_file":
                if "file_path" not in kwargs:
                    logger.debug(f"跳过工具 {tool_name}：缺少必要参数 'file_path'")
                    continue
                # 🔧 额外检查：文件路径必须包含路径分隔符或扩展名
                file_path = kwargs.get("file_path", "")
                if "/" not in file_path and "\\" not in file_path and "." not in file_path:
                    logger.debug(f"跳过工具 {tool_name}：'{file_path}' 不像有效的文件路径")
                    continue
            
            # 🔧 额外检查：web_search 需要有有效关键词
            if tool_name == "web_search":
                query = kwargs.get("query", "")
                if not query or len(query.strip()) < 2:
                    logger.debug(f"跳过工具 {tool_name}：查询关键词过短或为空")
                    continue
            
            # 执行工具
            result = await self.skill_invoker.execute_tool(tool_name, **kwargs)
            
            if result.get("success"):
                # 格式化结果
                formatted = self._format_tool_result(tool_name, result)
                results.append(formatted)
            else:
                # 记录失败
                error = result.get("error", "未知错误")
                results.append(f"**{tool_name}** 执行失败: {error}")
        
        return "\n\n".join(results) if results else ""
    
    def _format_tool_result(self, tool_name: str, result: Dict[str, Any]) -> str:
        """
        格式化工具结果
        """
        if tool_name == "web_search":
            results = result.get("results", [])
            if not results:
                return "**搜索结果**: 未找到相关信息"
            
            lines = ["**搜索结果**:"]
            for i, r in enumerate(results, 1):
                lines.append(f"{i}. {r.get('title', '无标题')}")
                lines.append(f"   {r.get('snippet', '')[:100]}")
                if r.get('url'):
                    lines.append(f"   链接: {r.get('url')}")
            return "\n".join(lines)
        
        elif tool_name == "read_file":
            content = result.get("content", "")
            lines = result.get("lines", 0)
            file_path = result.get("file_path", "")
            content_preview = content[:500] if len(content) > 500 else content
            return f"**文件内容** ({file_path}, {lines} 行):\n{content_preview}"
        
        elif tool_name == "list_dir":
            items = result.get("items", [])
            dir_path = result.get("dir_path", "")
            lines = [f"**目录列表** ({dir_path}):"]
            for item in items[:20]:
                type_icon = "📁" if item["type"] == "dir" else "📄"
                lines.append(f"{type_icon} {item['name']}")
            return "\n".join(lines)
        
        elif tool_name == "execute_code":
            output = result.get("output", "")
            return f"**代码执行结果**:\n{output}"
        
        else:
            return f"**{tool_name}**: {result}"
    
    def _aggregate_results(self, results: Dict[str, str]) -> str:
        """
        聚合结果
        """
        if len(results) == 1:
            return list(results.values())[0]
        
        # 多个结果 → 合并
        aggregated = []
        for subtask_id, result in results.items():
            aggregated.append(f"### 子任务 {subtask_id}\n\n{result}")
        
        return "\n\n---\n\n".join(aggregated)
    
    def _detect_task_type(self, context: str) -> str:
        """
        检测任务类型
        
        Returns:
            code_execution | web_search | data_analysis | text_generation | simple_query
        """
        context_lower = context.lower()
        
        if any(kw in context_lower for kw in ["代码", "执行", "计算", "脚本", "code", "execute", "script"]):
            return "code_execution"
        elif any(kw in context_lower for kw in ["搜索", "查询", "新闻", "search", "news"]):
            return "web_search"
        elif any(kw in context_lower for kw in ["分析", "统计", "数据", "analysis", "statistics", "data"]):
            return "data_analysis"
        elif any(kw in context_lower for kw in ["生成", "写", "创作", "generate", "write", "create"]):
            return "text_generation"
        else:
            return "simple_query"
    
    def _record_model_performance(self, model_name: str, task_type: str, success: bool):
        """
        记录模型性能
        
        Args:
            model_name: 模型名称
            task_type: 任务类型
            success: 是否成功
        """
        if model_name not in self.model_performance:
            self.model_performance[model_name] = {}
        
        if task_type not in self.model_performance[model_name]:
            self.model_performance[model_name][task_type] = {"success": 0, "failed": 0}
        
        if success:
            self.model_performance[model_name][task_type]["success"] += 1
        else:
            self.model_performance[model_name][task_type]["failed"] += 1
        
        # 记录日志
        stats = self.model_performance[model_name][task_type]
        total = stats["success"] + stats["failed"]
        success_rate = stats["success"] / total if total > 0 else 0
        
        logger.info(f"模型性能记录: {model_name} | {task_type} | 成功率: {success_rate:.1%} ({stats['success']}/{total})")
    
    async def _review_execution_result(
        self,
        output: str,
        context: str,
        original_message: str,
        attempt: int,
        max_retries: int,
        agent_config: AgentConfig = None
    ) -> dict:
        """
        审核执行结果是否真正回答了用户问题，并根据结果优化智能体逻辑
        
        Args:
            output: 执行输出
            context: 任务上下文
            original_message: 原始用户消息
            attempt: 当前尝试次数
            max_retries: 最大重试次数
            agent_config: 当前智能体配置
        
        Returns:
            {
                "pass": bool,
                "reason": str,
                "suggestion": str,
                "agent_optimization": {  # 智能体优化建议
                    "tools_add": [],
                    "tools_remove": [],
                    "prompt_enhancement": "",
                    "skill_adjustment": ""
                }
            }
        """
        # 提取用户原始问题
        user_question = original_message
        
        # 构建审核提示（增强版：包含智能体优化建议）
        agent_info = ""
        if agent_config:
            agent_info = f"""
【当前智能体配置】
- ID: {agent_config.agent_id}
- 技能: {agent_config.skills}
- 工具: {agent_config.tools}
- 描述: {agent_config.description}
"""
        
        review_prompt = f"""你是一个结果审核员和智能体优化专家。请判断执行结果是否正确回答了用户问题，并提供智能体优化建议。

【用户问题】
{user_question}

【执行结果】
{output}
{agent_info}
【审核标准】
1. 结果是否直接回答了用户问题？
2. 是否存在明显的逻辑错误或误解？
3. 结果是否有实际价值（不是空泛的建议）？

【回复格式】（必须严格遵循 JSON 格式）
{{
  "status": "PASS" 或 "FAIL",
  "reason": "原因说明",
  "suggestion": "改进建议",
  "agent_optimization": {{
    "tools_add": ["需要新增的工具"],
    "tools_remove": ["应该移除的工具"],
    "prompt_enhancement": "提示词增强建议",
    "skill_adjustment": "技能调整建议"
  }}
}}

只输出 JSON，不要解释。"""

        try:
            # 使用入口 LLM 进行审核（快速、低成本）
            review_response = await self.decision_llm.chat([
                {"role": "system", "content": "你是一个严谨的结果审核员和智能体优化专家。只输出 JSON 格式的回复。"},
                {"role": "user", "content": review_prompt}
            ])
            
            review_response = review_response.strip()
            logger.info(f"审核响应: {review_response[:200]}")
            
            # 解析 JSON
            import json
            # 提取 JSON 块
            json_match = re.search(r'\{.*\}', review_response, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group(0))
                
                # 标准化返回格式
                review_result = {
                    "pass": result.get("status") == "PASS",
                    "reason": result.get("reason", ""),
                    "suggestion": result.get("suggestion", ""),
                    "agent_optimization": result.get("agent_optimization", {})
                }
                
                # 🔧 应用智能体优化
                if not review_result["pass"] and agent_config:
                    await self._apply_agent_optimization(
                        agent_config, 
                        review_result["agent_optimization"],
                        user_question
                    )
                
                return review_result
            else:
                # 无法解析 JSON，尝试旧格式
                if review_response.startswith("PASS"):
                    return {
                        "pass": True,
                        "reason": "审核通过",
                        "suggestion": "",
                        "agent_optimization": {}
                    }
                else:
                    return {
                        "pass": False,
                        "reason": "审核未通过",
                        "suggestion": "请换一种方法",
                        "agent_optimization": {}
                    }
        
        except Exception as e:
            logger.error(f"审核过程出错: {e}")
            return {
                "pass": True,  # 审核出错时保守通过
                "reason": f"审核过程出错: {e}",
                "suggestion": "",
                "agent_optimization": {}
            }
    
    async def _apply_agent_optimization(
        self,
        agent_config: AgentConfig,
        optimization: dict,
        user_question: str
    ):
        """
        应用智能体优化建议
        
        Args:
            agent_config: 智能体配置
            optimization: 优化建议
            user_question: 用户问题（用于记录上下文）
        """
        try:
            logger.info(f"智能体优化建议: {agent_config.agent_id}")
            logger.info(f"  - 新增工具: {optimization.get('tools_add', [])}")
            logger.info(f"  - 移除工具: {optimization.get('tools_remove', [])}")
            logger.info(f"  - 提示词增强: {optimization.get('prompt_enhancement', '')[:50]}")
            logger.info(f"  - 技能调整: {optimization.get('skill_adjustment', '')[:50]}")
            
            # 🔧 使用注册表优化智能体
            optimized = self.agent_registry.optimize_agent(
                agent_config.agent_id,
                optimization
            )
            
            if optimized:
                # 同步更新当前智能体配置
                agent_config.tools = optimized.tools
                agent_config.skills = optimized.skills
                logger.info(f"  ✓ 智能体已优化并持久化")
            
        except Exception as e:
            logger.error(f"应用智能体优化失败: {e}")
    
    def _should_switch_model(self, model_name: str, task_type: str) -> bool:
        """
        判断是否需要切换模型
        
        条件：连续失败 2 次且成功率 < 50%
        """
        if model_name not in self.model_performance:
            return False
        
        if task_type not in self.model_performance[model_name]:
            return False
        
        stats = self.model_performance[model_name][task_type]
        total = stats["success"] + stats["failed"]
        
        if total < 2:
            return False
        
        success_rate = stats["success"] / total
        consecutive_failures = stats["failed"]
        
        # 连续失败 2 次且成功率 < 50%
        should_switch = consecutive_failures >= 2 and success_rate < 0.5
        
        if should_switch:
            logger.warning(f"模型 {model_name} 在任务 {task_type} 上表现不佳，建议切换")
            logger.warning(f"  - 成功率: {success_rate:.1%} ({stats['success']}/{total})")
            logger.warning(f"  - 连续失败: {consecutive_failures} 次")
        
        return should_switch
    
    def _analyze_failure(self, error_msg: str, code: str = "") -> str:
        """
        决策层分析失败原因
        
        深度分析错误信息，提供结构化的失败原因和修复建议
        
        Args:
            error_msg: 错误信息
            code: 执行的代码
        
        Returns:
            失败原因描述（包含具体错误类型和修复建议）
        """
        error_lower = error_msg.lower()
        
        # 🔧 超时错误
        if "timeout" in error_lower or "timed out" in error_lower:
            # 分析代码中可能导致超时的原因
            if "while" in code or "for" in code:
                return "超时（代码中存在循环，可能死循环或循环次数过多），需要优化循环逻辑或减少循环次数"
            elif "sleep" in code:
                return "超时（代码中有 sleep 等待），需要减少等待时间或移除不必要的 sleep"
            elif "request" in code or "http" in code:
                return "超时（网络请求超时），需要设置更短的超时时间或使用异步请求"
            else:
                return "超时（代码执行时间过长），需要优化算法复杂度或减少数据量"
        
        # 🔧 依赖库错误
        elif "modulenotfounderror" in error_lower or "no module named" in error_lower:
            # 提取缺失的库名
            import re
            module_match = re.search(r"no module named '([^']+)'", error_lower)
            if module_match:
                module_name = module_match.group(1)
                return f"缺少依赖库 '{module_name}'，请使用 Python 标准库替代，或检查该库是否已安装"
            return "缺少依赖库，请使用 Python 标准库（os, sys, json, re, datetime 等）或检查库是否安装"
        
        # 🔧 语法错误
        elif "syntaxerror" in error_lower:
            # 提取语法错误位置
            line_match = re.search(r"line (\\d+)", error_msg)
            if line_match:
                line_num = line_match.group(1)
                return f"代码语法错误（第 {line_num} 行），需要检查括号匹配、缩进、引号等语法问题"
            return "代码语法错误，需要检查括号匹配、缩进、引号等语法问题"
        
        # 🔧 网络错误
        elif "connectionerror" in error_lower or "network" in error_lower or "connection refused" in error_lower:
            return "网络连接错误，需要检查 URL 是否正确、网络是否可用，或使用其他 API"
        
        # 🔧 API 错误
        elif "api" in error_lower and ("key" in error_lower or "auth" in error_lower):
            return "API 认证错误，需要检查 API Key 是否正确或是否已过期"
        
        # 🔧 文件错误
        elif "filenotfounderror" in error_lower or "no such file" in error_lower:
            return "文件不存在，需要检查文件路径是否正确或文件是否存在"
        
        # 🔧 权限错误
        elif "permissionerror" in error_lower or "permission denied" in error_lower:
            return "权限不足，需要检查文件或目录权限，或使用其他路径"
        
        # 🔧 输出为空
        elif "empty" in error_lower or len(error_msg.strip()) == 0:
            # 分析代码逻辑
            if "search" in code or "find" in code or "match" in code:
                return "输出为空（搜索/匹配未找到结果），需要检查搜索条件或正则表达式是否正确"
            elif "if" in code:
                return "输出为空（条件判断未满足），需要检查条件逻辑是否正确"
            else:
                return "输出为空（代码可能没有输出语句或逻辑错误），需要添加 print() 语句或检查逻辑"
        
        # 🔧 其他错误
        elif "error" in error_lower[:50]:
            return f"执行错误: {error_msg[:100]}"
        
        else:
            return f"未知错误: {error_msg[:100] if error_msg else '无错误信息'}"
    
    def _get_backup_model(self, task_type: str, current_model: str = None) -> Optional[Dict[str, Any]]:
        """
        获取备用模型
        
        Args:
            task_type: 任务类型
            current_model: 当前模型名称（避免切换到相同模型）
        
        Returns:
            备用模型配置，如果没有则返回 None
        """
        # 按优先级尝试备用模型
        fallback_keys = ["fallback_1", "fallback_2", "primary"]
        
        for key in fallback_keys:
            model = self.model_pool.get(key)
            if model:
                model_name = model.get('name')
                # 🔧 避免切换到相同模型
                if current_model and model_name == current_model:
                    logger.info(f"跳过相同模型: {model_name}")
                    continue
                logger.info(f"选择备用模型: {model_name} (类型: {key})")
                return model
        
        logger.warning("没有可用的备用模型")
        return None
    
    def _create_llm_client(self, model_config: Dict[str, Any]) -> LLMClient:
        """
        创建 LLM 客户端
        
        Args:
            model_config: 模型配置
        
        Returns:
            LLM 客户端实例
        """
        from utils.llm_client import LLMConfig, LLMClient
        
        config = LLMConfig(
            name=model_config.get("name"),
            api_base=model_config.get("api_base", ""),
            api_key=model_config.get("api_key", ""),
            temperature=model_config.get("temperature", 0.7),
            max_tokens=model_config.get("max_tokens", 2000),
            timeout=model_config.get("timeout", 30)
        )
        
        return LLMClient(config)
    
    def _save_performance(self):
        """
        决策层保存性能数据到文件
        
        保存内容：
        - 模型性能记录（成功/失败次数）
        - 最近失败原因（用于分析模型表现）
        - 性能统计摘要
        """
        import json
        import os
        from datetime import datetime
        
        try:
            # 保存到 bayi-agent 目录
            performance_file = "/root/.openclaw/workspace/bayi-agent/model_performance.json"
            
            # 添加元数据
            performance_data = {
                "last_updated": datetime.now().isoformat(),
                "models": self.model_performance,
                "summary": self._generate_performance_summary()
            }
            
            with open(performance_file, "w", encoding="utf-8") as f:
                json.dump(performance_data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"性能数据已保存: {performance_file}")
        
        except Exception as e:
            logger.warning(f"保存性能数据失败: {e}")
    
    def _load_performance(self):
        """
        决策层加载性能数据
        
        加载内容：
        - 历史性能记录
        - 最近失败原因
        - 性能统计摘要
        """
        import json
        import os
        
        try:
            performance_file = "/root/.openclaw/workspace/bayi-agent/model_performance.json"
            
            if os.path.exists(performance_file):
                with open(performance_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                # 兼容旧格式（只有 models 数据）
                if "models" in data:
                    self.model_performance = data.get("models", {})
                    last_updated = data.get("last_updated", "未知")
                else:
                    self.model_performance = data
                    last_updated = "未知"
                
                logger.info(f"性能数据已加载: {performance_file}")
                logger.info(f"最后更新时间: {last_updated}")
                logger.info(f"历史性能记录: {len(self.model_performance)} 个模型")
                
                # 输出性能摘要
                summary = data.get("summary", "")
                if summary:
                    logger.info(f"性能摘要:\n{summary}")
        
        except Exception as e:
            logger.warning(f"加载性能数据失败: {e}")
            self.model_performance = {}
    
    def _generate_performance_summary(self) -> str:
        """
        生成性能摘要
        
        Returns:
            性能摘要字符串
        """
        if not self.model_performance:
            return "暂无性能数据"
        
        summary_lines = []
        
        for model_name, tasks in self.model_performance.items():
            total_success = sum(t.get("success", 0) for t in tasks.values())
            total_failed = sum(t.get("failed", 0) for t in tasks.values())
            total_tasks = total_success + total_failed
            
            if total_tasks > 0:
                success_rate = total_success / total_tasks
                summary_lines.append(
                    f"{model_name}: 成功率 {success_rate:.1%} ({total_success}/{total_tasks})"
                )
        
        return "\n".join(summary_lines)
