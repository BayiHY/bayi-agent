"""
Bayi-Agent 核心数据模型
"""
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from enum import Enum
import time
import uuid


class Intent(Enum):
    """意图类型"""
    SIMPLE = "simple"  # 简单任务（快速完成）
    COMPLEX = "complex"  # 复杂任务（需要后台处理）
    PARALLEL = "parallel"  # 并行决策任务（优化：parallel_decisions → parallel）
    STATUS = "status"  # 查询任务状态
    HELP = "help"  # 请求帮助
    CHAT = "chat"  # 普通聊天


class TaskStatus(Enum):
    """任务状态"""
    QUEUED = "queued"  # 排队中
    PROCESSING = "processing"  # 处理中
    COMPLETED = "completed"  # 已完成
    FAILED = "failed"  # 失败


@dataclass
class EntryContext:
    """入口 LLM 最小上下文"""
    
    # ===== 必需：用户信息 =====
    user_id: str  # 用户 ID（用于区分用户）
    
    # ===== 必需：渠道信息 =====
    channel: str  # 渠道（feishu/hermes/claw）
    chat_type: str  # 聊天类型（direct/group）
    
    # ===== 必需：任务状态 =====
    active_tasks: List[str] = field(default_factory=list)  # 活跃任务列表
    queue_length: int = 0  # 队列长度
    
    # ===== 可选：上下文信息 =====
    last_task_id: Optional[str] = None  # 最近任务 ID
    
    # ===== 飞书渠道特有字段 =====
    chat_id: Optional[str] = None  # 飞书 Chat ID（oc_xxx）
    message_id: Optional[str] = None  # 飞书 Message ID（om_xxx）
    is_group: Optional[bool] = None  # 是否群聊
    
    # ===== 对话历史（新增） =====
    conversation_history: List[Dict[str, str]] = field(default_factory=list)  # [{"role": "user/assistant", "content": "..."}]
    last_completed_tasks: List[Dict[str, str]] = field(default_factory=list)  # 最近完成的任务摘要
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "user_id": self.user_id,
            "channel": self.channel,
            "chat_type": self.chat_type,
            "active_tasks": self.active_tasks,
            "queue_length": self.queue_length,
            "last_task_id": self.last_task_id,
            "chat_id": self.chat_id,
            "message_id": self.message_id,
            "is_group": self.is_group,
            "conversation_history": self.conversation_history,
            "last_completed_tasks": self.last_completed_tasks
        }


@dataclass
class DecisionTask:
    """决策任务"""
    
    task_id: str  # 任务 ID
    message: str  # 用户消息
    source: str  # 来源渠道
    user_id: str  # 用户 ID
    status: TaskStatus = TaskStatus.QUEUED
    intent: Optional[Intent] = None
    priority: int = 5  # 优先级（1-10，越小越优先）
    
    # 时间戳
    enqueued_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    
    # 结果
    result: Optional[str] = None
    error: Optional[str] = None
    
    # 上下文
    context: Optional[EntryContext] = None
    
    @staticmethod
    def create(
        message: str,
        source: str,
        user_id: str,
        priority: int = 5,
        context: Optional[EntryContext] = None
    ) -> 'DecisionTask':
        """创建新任务"""
        task_id = f"task-{uuid.uuid4().hex[:12]}"
        return DecisionTask(
            task_id=task_id,
            message=message,
            source=source,
            user_id=user_id,
            priority=priority,
            context=context
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "task_id": self.task_id,
            "message": self.message,
            "source": self.source,
            "user_id": self.user_id,
            "status": self.status.value,
            "intent": self.intent.value if self.intent else None,
            "priority": self.priority,
            "enqueued_at": self.enqueued_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "result": self.result,
            "error": self.error,
            "wait_time": self._get_wait_time(),
            "process_time": self._get_process_time()
        }
    
    def _get_wait_time(self) -> Optional[float]:
        """获取等待时间"""
        start = self.started_at or time.time()
        return start - self.enqueued_at
    
    def _get_process_time(self) -> Optional[float]:
        """获取处理时间"""
        if not self.started_at:
            return None
        end = self.completed_at or time.time()
        return end - self.started_at


@dataclass
class SubTask:
    """子任务"""
    
    id: str  # 子任务 ID
    context: str  # 子任务上下文
    dependencies: List[str] = field(default_factory=list)  # 依赖的子任务 ID
    scope: str = "all"  # 作用域
    status: TaskStatus = TaskStatus.QUEUED
    result: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "context": self.context,
            "dependencies": self.dependencies,
            "scope": self.scope,
            "status": self.status.value,
            "result": self.result
        }


@dataclass
class EntryResult:
    """入口 LLM 返回结果"""
    
    intent: Intent  # 意图
    response: str  # 口语回复
    task_ids: Optional[List[str]] = None  # 任务 ID 列表（如果有）
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "intent": self.intent.value,
            "response": self.response,
            "task_ids": self.task_ids
        }
