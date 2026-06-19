"""
Bayi-Agent 主程序
"""
import asyncio
import logging
import yaml
import os
from pathlib import Path
from typing import Optional

from core.models import Intent, EntryContext, DecisionTask, TaskStatus
from core.queue import DecisionTaskQueue
from core.gateway import BayiTaskGateway
from core.analyzer import DecisionAnalyzer
from core.session_manager import SessionManager
from core.user_memory import UserMemory
from handlers.feishu_handler import FeishuHandler, handle_feishu_webhook
from utils.llm_client import LLMConfig


logger = logging.getLogger(__name__)


class BayiAgent:
    """Bayi-Agent 主类"""
    
    def __init__(self, config_path: Optional[str] = None, send_message_callback=None):
        # 加载配置
        self.config = self._load_config(config_path)
        
        # 消息发送回调（用于推送任务结果）
        self.send_message_callback = send_message_callback
        
        # 初始化会话管理器
        self.session_manager = SessionManager(
            max_history=40,  # 20 轮对话（用户+助手各 1 条）
            max_completed_tasks=10
        )
        
        # 初始化用户记忆系统
        self.user_memory = UserMemory()
        
        # 初始化组件
        self._init_components()
    
    def _load_config(self, config_path: Optional[str] = None) -> dict:
        """加载配置文件"""
        if not config_path:
            # 默认配置路径
            config_path = os.path.join(
                os.path.dirname(__file__),
                "bayi_config.yaml"
            )
        
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
        else:
            logger.warning(f"配置文件不存在: {config_path}，使用默认配置")
            return self._default_config()
    
    def _default_config(self) -> dict:
        """默认配置"""
        return {
            "entry_model": {
                "name": "agnes-2.0-flash",
                "temperature": 0.3,
                "max_tokens": 500,
                "timeout": 5
            },
            "decision_model": {
                "name": "GLM-5",
                "temperature": 0.7,
                "max_tokens": 4000,
                "timeout": 60
            },
            "queue": {
                "max_size": 100,
                "db_path": "/tmp/bayi-tasks/queue.db"
            },
            "log": {
                "level": "INFO"
            }
        }
    
    def _init_components(self):
        """初始化组件"""
        # 配置日志
        log_config = self.config.get("log", {})
        logging.basicConfig(
            level=getattr(logging, log_config.get("level", "INFO")),
            format=log_config.get("format", "[%(asctime)s] %(levelname)s | %(message)s")
        )
        
        # 初始化队列
        queue_config = self.config.get("queue", {})
        self.task_queue = DecisionTaskQueue(
            db_path=queue_config.get("db_path", "/tmp/bayi-tasks/queue.db"),
            max_queue_size=queue_config.get("max_size", 100)
        )
        
        # 初始化 LLM 配置
        entry_model = self.config.get("entry_model", {})
        self.entry_llm_config = LLMConfig(
            name=entry_model.get("name", "agnes-2.0-flash"),
            api_base=entry_model.get("api_base", ""),
            api_key=entry_model.get("api_key", ""),
            temperature=entry_model.get("temperature", 0.3),
            max_tokens=entry_model.get("max_tokens", 500),
            timeout=entry_model.get("timeout", 5)
        )
        
        decision_model = self.config.get("decision_model", {})
        self.decision_llm_config = LLMConfig(
            name=decision_model.get("name", "GLM-5"),
            api_base=decision_model.get("api_base", ""),
            api_key=decision_model.get("api_key", ""),
            temperature=decision_model.get("temperature", 0.7),
            max_tokens=decision_model.get("max_tokens", 4000),
            timeout=decision_model.get("timeout", 60)
        )
        
        simple_model = self.config.get("simple_model", entry_model)
        self.simple_llm_config = LLMConfig(
            name=simple_model.get("name", "agnes-2.0-flash"),
            api_base=simple_model.get("api_base", ""),
            api_key=simple_model.get("api_key", ""),
            temperature=simple_model.get("temperature", 0.5),
            max_tokens=simple_model.get("max_tokens", 2000),
            timeout=simple_model.get("timeout", 10)
        )
        
        # 初始化入口网关
        self.gateway = BayiTaskGateway(
            entry_model_config=self.entry_llm_config,
            decision_model_config=self.decision_llm_config,
            simple_model_config=self.simple_llm_config,
            task_queue=self.task_queue,
            session_manager=self.session_manager,
            user_memory=self.user_memory
        )
        
        # 初始化决策分析器
        context_splitter_config = self.config.get("context_splitter", {})
        model_pool = self.config.get("model_pool", {})  # 获取模型池配置
        
        self.analyzer = DecisionAnalyzer(
            decision_llm=self.gateway.decision_llm,
            max_tokens_per_subtask=context_splitter_config.get("max_tokens_per_subtask", 5000),
            max_chars_per_subtask=context_splitter_config.get("max_chars_per_subtask", 15000),
            model_pool=model_pool  # 传递模型池
        )
        
        # 初始化飞书处理器（如果配置了）
        feishu_config = self.config.get("feishu", {})
        if feishu_config.get("app_id") and feishu_config.get("app_secret"):
            self.feishu_handler = FeishuHandler(
                app_id=feishu_config["app_id"],
                app_secret=feishu_config["app_secret"],
                gateway=self.gateway,
                task_queue=self.task_queue
            )
        else:
            self.feishu_handler = None
    
    async def start(self):
        """启动服务"""
        logger.info("Bayi-Agent 启动中...")
        
        # 恢复队列状态
        await self.task_queue.restore()
        
        # 启动后台 worker
        asyncio.create_task(self._run_workers())
        
        logger.info("Bayi-Agent 启动完成")
    
    async def _run_workers(self):
        """运行后台 worker 处理队列"""
        max_workers = self.config.get("queue", {}).get("max_workers", 3)
        
        workers = [
            asyncio.create_task(self._worker())
            for _ in range(max_workers)
        ]
        
        await asyncio.gather(*workers)
    
    async def _worker(self):
        """单个 worker 处理任务"""
        while True:
            try:
                # 从队列获取任务
                task = await self.task_queue.dequeue()
                
                if not task:
                    # 队列为空，等待
                    await asyncio.sleep(1)
                    continue
                
                # 处理任务（无超时限制）
                try:
                    result = await self.analyzer.analyze(task)
                    await self.task_queue.update_status(
                        task.task_id,
                        TaskStatus.COMPLETED,
                        result=result
                    )
                    
                    # 🔧 记录完成的任务
                    if task.context:
                        self.session_manager.add_completed_task(
                            user_id=task.user_id,
                            task_id=task.task_id,
                            task_summary=task.message[:50],
                            result_summary=result[:100],
                            chat_id=task.context.chat_id
                        )
                    
                    # 🔧 发送结果给用户
                    if self.send_message_callback and task.context and task.context.chat_id:
                        try:
                            await self.send_message_callback(
                                chat_id=task.context.chat_id,
                                message=f"✅ 任务完成\n\n{result}"
                            )
                            logger.info(f"已发送任务结果: {task.task_id}")
                        except Exception as e:
                            logger.error(f"发送任务结果失败: {e}", exc_info=True)
                
                        except Exception as e:
                            logger.error(f"发送超时通知失败: {e}")
                
                except Exception as e:
                    logger.error(f"处理任务失败: {task.task_id}, error: {e}", exc_info=True)
                    await self.task_queue.update_status(
                        task.task_id,
                        TaskStatus.FAILED,
                        error=str(e)
                    )
                    
                    # 🔧 发送错误通知
                    if self.send_message_callback and task.context and task.context.chat_id:
                        try:
                            await self.send_message_callback(
                                chat_id=task.context.chat_id,
                                message=f"❌ 任务失败\n\n错误：{str(e)}"
                            )
                        except Exception as send_error:
                            logger.error(f"发送错误通知失败: {send_error}", exc_info=True)
            
            except Exception as e:
                logger.error(f"Worker 异常: {e}", exc_info=True)
                await asyncio.sleep(1)
    
    async def chat(self, message: str, context: EntryContext) -> str:
        """
        对话入口
        
        Args:
            message: 用户消息
            context: 入口上下文
        
        Returns:
            回复消息
        """
        return await self.gateway.chat(message, context)
    
    async def status(self, task_id: str) -> str:
        """
        查询任务状态
        
        Args:
            task_id: 任务 ID
        
        Returns:
            任务状态信息
        """
        return await self.gateway.status(task_id)


# 命令行入口
def main():
    """命令行入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Bayi-Agent - 轻量级子智能体框架")
    parser.add_argument(
        "-c", "--config",
        help="配置文件路径"
    )
    parser.add_argument(
        "--webhook",
        action="store_true",
        help="启动 Webhook 服务（用于飞书）"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Webhook 服务端口"
    )
    
    args = parser.parse_args()
    
    # 创建 Bayi-Agent 实例
    agent = BayiAgent(config_path=args.config)
    
    if args.webhook:
        # 启动 Webhook 服务
        from aiohttp import web
        
        async def webhook_handler(request):
            """处理 Webhook 请求"""
            try:
                data = await request.json()
                
                # 处理飞书事件
                if agent.feishu_handler:
                    result = await handle_feishu_webhook(data, agent.feishu_handler)
                    return web.json_response(result)
                else:
                    return web.json_response({"error": "Feishu not configured"}, status=400)
            
            except Exception as e:
                logger.error(f"Webhook 处理失败: {e}", exc_info=True)
                return web.json_response({"error": str(e)}, status=500)
        
        async def start_agent():
            """启动 agent"""
            await agent.start()
        
        app = web.Application()
        app.router.add_post(agent.config.get("feishu", {}).get("event_callback", "/webhook/feishu"), webhook_handler)
        
        # 启动 agent
        app.on_startup.append(lambda app: start_agent())
        
        # 运行服务
        web.run_app(app, port=args.port)
    
    else:
        # 交互模式
        import asyncio
        
        async def interactive():
            """交互模式"""
            await agent.start()
            
            print("Bayi-Agent 交互模式")
            print("输入 'quit' 退出")
            print()
            
            while True:
                try:
                    message = input("用户: ")
                    
                    if message.lower() in ["quit", "exit", "q"]:
                        print("再见！")
                        break
                    
                    # 构建默认上下文
                    context = EntryContext(
                        user_id="user-interactive",
                        channel="cli",
                        chat_type="direct",
                        active_tasks=[],
                        queue_length=0
                    )
                    
                    # 调用 agent
                    response = await agent.chat(message, context)
                    print(f"助手: {response}")
                    print()
                
                except KeyboardInterrupt:
                    print("\n再见！")
                    break
        
        asyncio.run(interactive())


if __name__ == "__main__":
    main()
