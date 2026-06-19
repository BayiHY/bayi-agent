"""
会话管理器 - 管理对话历史和任务记录
"""
import logging
from typing import Dict, List, Optional
from collections import defaultdict
import time


logger = logging.getLogger(__name__)


class SessionManager:
    """会话管理器（内存版）"""
    
    def __init__(self, max_history: int = 20, max_completed_tasks: int = 10):
        """
        Args:
            max_history: 最大对话历史条数
            max_completed_tasks: 最大完成任务记录数
        """
        self.max_history = max_history
        self.max_completed_tasks = max_completed_tasks
        
        # 会话存储：{session_key: SessionData}
        self.sessions: Dict[str, 'SessionData'] = {}
    
    def _get_session_key(self, user_id: str, chat_id: Optional[str] = None) -> str:
        """生成会话 key"""
        if chat_id:
            return f"{user_id}:{chat_id}"
        return user_id
    
    def add_message(
        self,
        user_id: str,
        message: str,
        response: str,
        chat_id: Optional[str] = None
    ):
        """
        添加对话记录
        
        Args:
            user_id: 用户 ID
            message: 用户消息
            response: 助手回复
            chat_id: 聊天 ID（可选）
        """
        key = self._get_session_key(user_id, chat_id)
        
        if key not in self.sessions:
            self.sessions[key] = SessionData()
        
        session = self.sessions[key]
        
        # 添加用户消息
        session.history.append({
            "role": "user",
            "content": message,
            "timestamp": time.time()
        })
        
        # 添加助手回复
        session.history.append({
            "role": "assistant",
            "content": response,
            "timestamp": time.time()
        })
        
        # 限制历史长度
        if len(session.history) > self.max_history * 2:
            session.history = session.history[-self.max_history * 2:]
        
        logger.debug(f"会话 {key} 添加对话记录，当前历史长度: {len(session.history)}")
    
    def add_completed_task(
        self,
        user_id: str,
        task_id: str,
        task_summary: str,
        result_summary: str,
        chat_id: Optional[str] = None
    ):
        """
        添加完成的任务记录
        
        Args:
            user_id: 用户 ID
            task_id: 任务 ID
            task_summary: 任务摘要（用户消息前 50 字）
            result_summary: 结果摘要（前 100 字）
            chat_id: 聊天 ID（可选）
        """
        key = self._get_session_key(user_id, chat_id)
        
        if key not in self.sessions:
            self.sessions[key] = SessionData()
        
        session = self.sessions[key]
        
        # 添加任务记录
        session.completed_tasks.append({
            "task_id": task_id,
            "task_summary": task_summary,
            "result_summary": result_summary,
            "timestamp": time.time()
        })
        
        # 限制任务记录长度
        if len(session.completed_tasks) > self.max_completed_tasks:
            session.completed_tasks = session.completed_tasks[-self.max_completed_tasks:]
        
        logger.info(f"会话 {key} 添加任务记录: {task_id}")
    
    def get_history(
        self,
        user_id: str,
        chat_id: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict[str, str]]:
        """
        获取对话历史
        
        Args:
            user_id: 用户 ID
            chat_id: 聊天 ID（可选）
            limit: 限制条数
        
        Returns:
            对话历史列表
        """
        key = self._get_session_key(user_id, chat_id)
        
        if key not in self.sessions:
            return []
        
        session = self.sessions[key]
        history = session.history[-limit * 2:]  # 限制条数（用户+助手）
        
        # 转换为简单格式（去掉 timestamp）
        return [
            {"role": h["role"], "content": h["content"]}
            for h in history
        ]
    
    def get_completed_tasks(
        self,
        user_id: str,
        chat_id: Optional[str] = None,
        limit: int = 5
    ) -> List[Dict[str, str]]:
        """
        获取完成的任务记录
        
        Args:
            user_id: 用户 ID
            chat_id: 聊天 ID（可选）
            limit: 限制条数
        
        Returns:
            任务记录列表
        """
        key = self._get_session_key(user_id, chat_id)
        
        if key not in self.sessions:
            return []
        
        session = self.sessions[key]
        return session.completed_tasks[-limit:]
    
    def clear_session(self, user_id: str, chat_id: Optional[str] = None):
        """清空会话"""
        key = self._get_session_key(user_id, chat_id)
        
        if key in self.sessions:
            del self.sessions[key]
            logger.info(f"会话 {key} 已清空")


class SessionData:
    """会话数据"""
    
    def __init__(self):
        self.history: List[Dict[str, str]] = []  # 对话历史
        self.completed_tasks: List[Dict[str, str]] = []  # 完成的任务
        self.created_at: float = time.time()
