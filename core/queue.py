"""
决策任务队列 - 管理决策任务的排队和处理
支持持久化（SQLite）和内存模式
"""
import asyncio
import time
import sqlite3
import json
import os
import logging
from typing import Dict, List, Optional, Any
from pathlib import Path

from core.models import DecisionTask, TaskStatus


logger = logging.getLogger(__name__)


class DecisionTaskQueue:
    """决策任务队列（支持优先级和持久化）"""
    
    def __init__(
        self,
        db_path: str = "/tmp/bayi-tasks/queue.db",
        max_queue_size: int = 100
    ):
        # 🔧 优先级队列（4个级别）
        self.priority_queues = {
            0: asyncio.Queue(),  # P0: status（最高优先级）
            1: asyncio.Queue(),  # P1: simple
            2: asyncio.Queue(),  # P2: complex
            3: asyncio.Queue(),  # P3: background
        }
        self.tasks: Dict[str, DecisionTask] = {}
        self.processing: Optional[str] = None
        self.max_queue_size = max_queue_size
        self.db_path = db_path
        
        # 确保目录存在
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        
        # 初始化数据库
        self._init_db()
    
    def _init_db(self):
        """初始化数据库"""
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                task_id TEXT PRIMARY KEY,
                message TEXT,
                source TEXT,
                user_id TEXT,
                status TEXT,
                intent TEXT,
                priority INTEGER,
                enqueued_at REAL,
                started_at REAL,
                completed_at REAL,
                result TEXT,
                error TEXT,
                context TEXT
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_status ON tasks(status)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_user ON tasks(user_id)
        """)
        conn.commit()
        conn.close()
    
    async def enqueue(self, task: DecisionTask) -> bool:
        """
        任务入队（支持优先级）
        
        Args:
            task: 决策任务
        
        Returns:
            是否成功入队
        """
        from core.models import Intent
        
        # 🔧 根据意图分配优先级
        priority = self._get_priority(task)
        task.priority = priority
        
        # 检查队列大小（所有优先级队列总和）
        total_size = sum(q.qsize() for q in self.priority_queues.values())
        if total_size >= self.max_queue_size:
            raise Exception("队列已满")
        
        task_id = task.task_id
        
        # 内存存储
        self.tasks[task_id] = task
        
        # 持久化
        self._persist_task(task)
        
        # 加入对应优先级队列
        await self.priority_queues[priority].put(task_id)
        
        logger.info(f"任务入队: {task_id} | 优先级 P{priority} | {task.message[:50]}...")
        
        return True
    
    def _get_priority(self, task: DecisionTask) -> int:
        """
        根据意图获取优先级
        
        P0: status（最高优先级）
        P1: simple
        P2: complex
        P3: 其他
        """
        from core.models import Intent
        
        if task.intent == Intent.STATUS:
            return 0  # 最高优先级
        elif task.intent == Intent.SIMPLE:
            return 1
        elif task.intent == Intent.COMPLEX:
            return 2
        else:
            return 3
    
    async def dequeue(self) -> Optional[DecisionTask]:
        """
        任务出队（优先处理高优先级）
        
        Returns:
            任务信息或 None（队列为空）
        """
        # 🔧 按优先级顺序检查队列
        for priority in [0, 1, 2, 3]:
            if not self.priority_queues[priority].empty():
                task_id = await self.priority_queues[priority].get()
                break
        else:
            # 所有队列都空
            return None
        task = self.tasks.get(task_id)
        
        if task:
            # 更新状态
            task.status = TaskStatus.PROCESSING
            task.started_at = time.time()
            self.processing = task_id
            
            # 持久化更新
            self._update_task_status(task_id, TaskStatus.PROCESSING)
            
            logger.info(f"任务出队: {task_id}")
        
        return task
    
    async def update_status(
        self,
        task_id: str,
        status: TaskStatus,
        result: Optional[str] = None,
        error: Optional[str] = None
    ):
        """
        更新任务状态
        
        Args:
            task_id: 任务ID
            status: 新状态
            result: 结果内容（可选）
            error: 错误信息（可选）
        """
        task = self.tasks.get(task_id)
        if not task:
            logger.warning(f"任务不存在: {task_id}")
            return
        
        task.status = status
        task.result = result
        task.error = error
        
        if status in [TaskStatus.COMPLETED, TaskStatus.FAILED]:
            task.completed_at = time.time()
            self.processing = None
        
        # 持久化更新
        self._update_task_status(task_id, status, result, error)
        
        logger.info(f"任务状态更新: {task_id} → {status.value}")
    
    async def get_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        获取任务状态
        """
        task = self.tasks.get(task_id)
        if not task:
            # 尝试从数据库加载
            task = self._load_task(task_id)
            if not task:
                return {"status": "not_found"}
        
        return task.to_dict()
    
    async def get_queue_status(self) -> Dict[str, Any]:
        """
        获取队列状态
        """
        pending = []
        for task_id, task in self.tasks.items():
            if task.status == TaskStatus.QUEUED:
                pending.append({
                    "task_id": task_id,
                    "message": task.message[:50],
                    "status": task.status.value,
                    "wait_time": time.time() - task.enqueued_at
                })
        
        return {
            "queue_length": self.queue.qsize(),
            "processing": self.processing,
            "pending": pending
        }
    
    async def get_active_tasks(self, user_id: str) -> List[str]:
        """
        获取用户的活跃任务列表
        """
        active = []
        for task_id, task in self.tasks.items():
            if task.user_id == user_id and task.status in [
                TaskStatus.QUEUED,
                TaskStatus.PROCESSING
            ]:
                active.append(task_id)
        return active
    
    async def get_queue_length(self) -> int:
        """
        获取队列长度（所有优先级队列总和）
        """
        return sum(q.qsize() for q in self.priority_queues.values())
    
    async def clear_completed(self):
        """
        清理已完成的任务
        """
        completed_ids = [
            task_id for task_id, task in self.tasks.items()
            if task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED]
        ]
        
        for task_id in completed_ids:
            del self.tasks[task_id]
        
        logger.info(f"清理已完成任务: {len(completed_ids)} 个")
    
    async def get_position(self, task_id: str) -> int:
        """
        获取任务在队列中的位置
        
        Returns:
            位置（1开始），如果不在队列中返回 -1
        """
        position = 1
        temp_list = list(self.queue._queue)
        
        for tid in temp_list:
            if tid == task_id:
                return position
            position += 1
        
        return -1
    
    async def clear(self) -> int:
        """
        清空任务队列
        
        Returns:
            清理的任务数量
        """
        # 清空数据库
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("SELECT COUNT(*) FROM tasks")
        db_count = cursor.fetchone()[0]
        conn.execute("DELETE FROM tasks")
        conn.commit()
        conn.close()
        
        # 清空内存队列（所有优先级队列）
        queue_count = 0
        for priority in [0, 1, 2, 3]:
            while not self.priority_queues[priority].empty():
                try:
                    self.priority_queues[priority].get_nowait()
                    queue_count += 1
                except asyncio.QueueEmpty:
                    break
        
        # 清空任务字典
        self.tasks.clear()
        self.processing = None
        
        logger.info(f"清空任务队列: {db_count} 个任务")
        
        return db_count
    
    async def restore(self):
        """
        重启后恢复队列状态
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("""
            SELECT task_id, message, source, user_id, status, intent, 
                   priority, enqueued_at, started_at, completed_at, 
                   result, error, context
            FROM tasks
            WHERE status IN ('queued', 'processing')
            ORDER BY enqueued_at
        """)
        
        restored = 0
        for row in cursor:
            (
                task_id, message, source, user_id, status, intent,
                priority, enqueued_at, started_at, completed_at,
                result, error, context_json
            ) = row
            
            # 创建任务对象
            task = DecisionTask(
                task_id=task_id,
                message=message,
                source=source,
                user_id=user_id,
                status=TaskStatus(status),
                priority=priority,
                enqueued_at=enqueued_at
            )
            
            if started_at:
                task.started_at = started_at
            if completed_at:
                task.completed_at = completed_at
            if result:
                task.result = result
            if error:
                task.error = error
            
            # 恢复到内存
            self.tasks[task_id] = task
            
            # 如果是排队中，加入队列
            if status == "queued":
                await self.queue.put(task_id)
            
            restored += 1
        
        conn.close()
        
        logger.info(f"恢复任务: {restored} 个")
    
    # ===== 持久化方法 =====
    
    def _persist_task(self, task: DecisionTask):
        """持久化任务"""
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            INSERT OR REPLACE INTO tasks (
                task_id, message, source, user_id, status, intent,
                priority, enqueued_at, started_at, completed_at,
                result, error, context
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            task.task_id,
            task.message,
            task.source,
            task.user_id,
            task.status.value,
            task.intent.value if task.intent else None,
            task.priority,
            task.enqueued_at,
            task.started_at,
            task.completed_at,
            task.result,
            task.error,
            json.dumps(task.context.to_dict()) if task.context else None
        ))
        conn.commit()
        conn.close()
    
    def _update_task_status(
        self,
        task_id: str,
        status: TaskStatus,
        result: Optional[str] = None,
        error: Optional[str] = None
    ):
        """更新任务状态（持久化）"""
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            UPDATE tasks 
            SET status = ?, started_at = ?, completed_at = ?, result = ?, error = ?
            WHERE task_id = ?
        """, (
            status.value,
            time.time() if status == TaskStatus.PROCESSING else None,
            time.time() if status in [TaskStatus.COMPLETED, TaskStatus.FAILED] else None,
            result,
            error,
            task_id
        ))
        conn.commit()
        conn.close()
    
    def _load_task(self, task_id: str) -> Optional[DecisionTask]:
        """从数据库加载任务"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("""
            SELECT task_id, message, source, user_id, status, intent,
                   priority, enqueued_at, started_at, completed_at,
                   result, error, context
            FROM tasks
            WHERE task_id = ?
        """, (task_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return None
        
        (
            task_id, message, source, user_id, status, intent,
            priority, enqueued_at, started_at, completed_at,
            result, error, context_json
        ) = row
        
        task = DecisionTask(
            task_id=task_id,
            message=message,
            source=source,
            user_id=user_id,
            status=TaskStatus(status),
            priority=priority,
            enqueued_at=enqueued_at
        )
        
        if started_at:
            task.started_at = started_at
        if completed_at:
            task.completed_at = completed_at
        if result:
            task.result = result
        if error:
            task.error = error
        
        return task
