# -*- coding: utf-8 -*-
"""
Bayi-Agent OpenClaw 集成适配器

提供两种集成方式：
1. 直接导入：作为 Python 模块使用
2. 子智能体：通过 sessions_spawn 调用
"""
import asyncio
import sys
from pathlib import Path
from typing import Optional, Dict, Any

# 添加项目路径
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.models import EntryContext, Intent
from __init__ import BayiAgent


class BayiAgentAdapter:
    """Bayi-Agent OpenClaw 适配器"""
    
    _instance: Optional[BayiAgent] = None
    
    @classmethod
    async def get_agent(cls) -> BayiAgent:
        """获取 Bayi-Agent 实例（单例）"""
        if cls._instance is None:
            cls._instance = BayiAgent()
            await cls._instance.start()
        return cls._instance
    
    @classmethod
    async def chat(
        cls,
        message: str,
        user_id: str,
        channel: str = "openclaw",
        chat_type: str = "direct",
        **kwargs
    ) -> str:
        """
        对话接口（OpenClaw 集成）
        
        Args:
            message: 用户消息
            user_id: 用户 ID
            channel: 渠道（openclaw/feishu/hermes）
            chat_type: 聊天类型（direct/group）
            **kwargs: 其他上下文参数
        
        Returns:
            回复消息
        """
        agent = await cls.get_agent()
        
        # 构建入口上下文
        context = EntryContext(
            user_id=user_id,
            channel=channel,
            chat_type=chat_type,
            active_tasks=await agent.task_queue.get_active_tasks(user_id),
            queue_length=await agent.task_queue.get_queue_length(),
            **kwargs
        )
        
        # 调用 agent
        return await agent.chat(message, context)
    
    @classmethod
    async def status(cls, task_id: str) -> str:
        """
        查询任务状态
        
        Args:
            task_id: 任务 ID
        
        Returns:
            任务状态信息
        """
        agent = await cls.get_agent()
        return await agent.status(task_id)
    
    @classmethod
    async def queue_status(cls) -> Dict[str, Any]:
        """
        查询队列状态
        
        Returns:
            队列状态
        """
        agent = await cls.get_agent()
        return await agent.task_queue.get_queue_status()


# OpenClaw Skill 接口（可选）
async def bayi_chat(
    message: str,
    user_id: str,
    **kwargs
) -> str:
    """
    OpenClaw Skill 接口
    
    用法：
    ```python
    from bayi_agent.openclaw_adapter import bayi_chat
    
    result = await bayi_chat("分析系统架构", "user-123")
    ```
    """
    return await BayiAgentAdapter.chat(message, user_id, **kwargs)


async def bayi_status(task_id: str) -> str:
    """
    查询任务状态（OpenClaw Skill 接口）
    """
    return await BayiAgentAdapter.status(task_id)


async def bayi_queue_status() -> Dict[str, Any]:
    """
    查询队列状态（OpenClaw Skill 接口）
    """
    return await BayiAgentAdapter.queue_status()


# 命令行测试
if __name__ == "__main__":
    import sys
    
    async def test():
        """测试"""
        message = sys.argv[1] if len(sys.argv) > 1 else "你好"
        
        result = await bayi_chat(message, "test-user")
        print(f"用户: {message}")
        print(f"助手: {result}")
    
    asyncio.run(test())
