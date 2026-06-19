"""
用户记忆系统 - 持久化用户偏好和关键信息
"""
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional
import time


logger = logging.getLogger(__name__)


class UserMemory:
    """用户记忆管理器"""
    
    def __init__(self, memory_dir: str = "/tmp/bayi-tasks/memories"):
        """
        Args:
            memory_dir: 记忆存储目录
        """
        self.memory_dir = Path(memory_dir)
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        
        # 内存缓存
        self.cache: Dict[str, Dict[str, Any]] = {}
    
    def _get_memory_path(self, user_id: str) -> Path:
        """获取用户记忆文件路径"""
        return self.memory_dir / f"{user_id}.json"
    
    def load(self, user_id: str) -> Dict[str, Any]:
        """
        加载用户记忆
        
        Returns:
            {
                "name": "浩爷",
                "preferences": {...},
                "facts": [...],
                "last_updated": 1234567890
            }
        """
        # 检查缓存
        if user_id in self.cache:
            return self.cache[user_id]
        
        # 从文件加载
        memory_path = self._get_memory_path(user_id)
        
        if memory_path.exists():
            try:
                with open(memory_path, "r", encoding="utf-8") as f:
                    memory = json.load(f)
                    self.cache[user_id] = memory
                    return memory
            except Exception as e:
                logger.error(f"加载用户记忆失败: {user_id}, error: {e}")
        
        # 返回空记忆
        return {
            "name": None,
            "preferences": {},
            "facts": [],
            "last_updated": time.time()
        }
    
    def save(self, user_id: str, memory: Dict[str, Any]):
        """保存用户记忆"""
        memory_path = self._get_memory_path(user_id)
        memory["last_updated"] = time.time()
        
        try:
            with open(memory_path, "w", encoding="utf-8") as f:
                json.dump(memory, f, ensure_ascii=False, indent=2)
            
            # 更新缓存
            self.cache[user_id] = memory
            logger.info(f"保存用户记忆: {user_id}")
        
        except Exception as e:
            logger.error(f"保存用户记忆失败: {user_id}, error: {e}")
    
    def set_name(self, user_id: str, name: str):
        """设置用户名称"""
        memory = self.load(user_id)
        memory["name"] = name
        self.save(user_id, memory)
        logger.info(f"用户 {user_id} 设置名称: {name}")
    
    def get_name(self, user_id: str) -> Optional[str]:
        """获取用户名称"""
        memory = self.load(user_id)
        return memory.get("name")
    
    def add_fact(self, user_id: str, fact: str):
        """添加用户事实"""
        memory = self.load(user_id)
        
        if "facts" not in memory:
            memory["facts"] = []
        
        # 避免重复
        if fact not in memory["facts"]:
            memory["facts"].append(fact)
            self.save(user_id, memory)
            logger.info(f"用户 {user_id} 添加事实: {fact}")
    
    def get_facts(self, user_id: str) -> list:
        """获取用户事实"""
        memory = self.load(user_id)
        return memory.get("facts", [])
    
    def get_summary(self, user_id: str) -> str:
        """
        获取用户记忆摘要（用于注入到系统提示词）
        
        Returns:
            摘要文本，如："用户姓名：浩爷\n用户事实：..."
        """
        memory = self.load(user_id)
        parts = []
        
        if memory.get("name"):
            parts.append(f"用户姓名：{memory['name']}")
        
        facts = memory.get("facts", [])
        if facts:
            parts.append(f"用户信息：{'; '.join(facts[-5:])}")  # 最近 5 条
        
        return "\n".join(parts) if parts else ""
