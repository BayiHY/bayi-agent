# -*- coding: utf-8 -*-
"""
Bayi-Agent 测试
"""
import asyncio
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.models import Intent, EntryContext, DecisionTask, TaskStatus
from core.queue import DecisionTaskQueue
from utils.llm_client import LLMConfig


async def test_queue():
    """测试任务队列"""
    print("=== 测试任务队列 ===")
    
    queue = DecisionTaskQueue(db_path="/tmp/bayi-tasks/test_queue.db")
    
    # 创建任务
    task = DecisionTask.create(
        message="测试任务",
        source="test",
        user_id="test-user"
    )
    
    # 入队
    await queue.enqueue(task)
    print(f"任务入队: {task.task_id}")
    
    # 查询状态
    status = await queue.get_status(task.task_id)
    print(f"任务状态: {status}")
    
    # 出队
    dequeued_task = await queue.dequeue()
    print(f"任务出队: {dequeued_task.task_id}")
    
    # 更新状态
    await queue.update_status(task.task_id, TaskStatus.COMPLETED, result="测试完成")
    print(f"任务完成")
    
    # 查询最终状态
    final_status = await queue.get_status(task.task_id)
    print(f"最终状态: {final_status}")
    
    print("✓ 任务队列测试通过\n")


async def test_entry_context():
    """测试入口上下文"""
    print("=== 测试入口上下文 ===")
    
    context = EntryContext(
        user_id="test-user",
        channel="feishu",
        chat_type="direct",
        active_tasks=["task-123"],
        queue_length=5,
        last_task_id="task-123",
        chat_id="oc_test",
        message_id="om_test",
        is_group=False
    )
    
    print(f"用户 ID: {context.user_id}")
    print(f"渠道: {context.channel}")
    print(f"活跃任务: {context.active_tasks}")
    print(f"队列长度: {context.queue_length}")
    
    print("✓ 入口上下文测试通过\n")


async def test_decision_task():
    """测试决策任务"""
    print("=== 测试决策任务 ===")
    
    task = DecisionTask.create(
        message="分析系统架构",
        source="feishu",
        user_id="test-user",
        priority=5
    )
    
    print(f"任务 ID: {task.task_id}")
    print(f"消息: {task.message}")
    print(f"状态: {task.status}")
    print(f"优先级: {task.priority}")
    
    # 更新状态
    task.status = TaskStatus.PROCESSING
    task.started_at = 100.0
    
    print(f"更新后状态: {task.status}")
    print(f"等待时间: {task._get_wait_time():.2f} 秒")
    
    print("✓ 决策任务测试通过\n")


async def main():
    """主测试函数"""
    print("Bayi-Agent 测试\n")
    
    await test_entry_context()
    await test_decision_task()
    await test_queue()
    
    print("=== 所有测试通过 ===")


if __name__ == "__main__":
    asyncio.run(main())
