
"""任务查询入口逻辑修复补丁"""
import os
import json

TASK_FILE = "/root/.openclaw/workspace/memory/active_tasks.json"

def query_current_task():
    """查询当前活跃任务 - 修复版"""
    if os.path.exists(TASK_FILE):
        try:
            with open(TASK_FILE, 'r', encoding='utf-8') as f:
                tasks = json.load(f)
            active = [t for t in tasks if t.get('status') == 'processing']
            if active:
                return active
        except:
            pass
    return None

def format_task_response(tasks):
    """格式化任务响应"""
    if not tasks:
        return "暂无活跃任务"
    result = "📊 任务状态查询结果\n\n**活跃任务：**\n"
    for t in tasks:
        result += f"\n🔄 **{t.get('id', 'unknown')}**\n"
        result += f"   状态：{t.get('status', 'unknown')}\n"
        result += f"   内容：{t.get('content', '')[:30]}...\n"
    return result
