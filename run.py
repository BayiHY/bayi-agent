#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bayi-Agent 启动脚本
支持：独立部署 + OpenClaw 集成
"""
import sys
import os
import asyncio
import logging
from pathlib import Path

# 添加项目路径
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s | %(name)s | %(message)s'
)
logger = logging.getLogger(__name__)


def _load_feishu_config():
    """加载飞书配置"""
    import yaml
    config_path = os.environ.get("BAYI_CONFIG", os.path.join(os.path.dirname(__file__), "bayi_config.yaml"))
    
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
            return config.get("feishu", {})
    
    return {}


async def run_interactive():
    """交互模式"""
    from __init__ import BayiAgent
    
    agent = BayiAgent()
    await agent.start()
    
    print("\n" + "="*50)
    print("Bayi-Agent 交互模式")
    print("输入 'quit' 退出")
    print("="*50 + "\n")
    
    while True:
        try:
            message = input("用户: ").strip()
            
            if not message:
                continue
            
            if message.lower() in ["quit", "exit", "q"]:
                print("\n再见！")
                break
            
            # 构建默认上下文
            from core.models import EntryContext
            context = EntryContext(
                user_id="user-cli",
                channel="cli",
                chat_type="direct",
                active_tasks=[],
                queue_length=await agent.task_queue.get_queue_length()
            )
            
            # 调用 agent
            response = await agent.chat(message, context)
            print(f"\n助手: {response}\n")
        
        except KeyboardInterrupt:
            print("\n\n再见！")
            break
        except Exception as e:
            logger.error(f"处理消息失败: {e}", exc_info=True)
            print(f"\n错误: {e}\n")


async def run_websocket():
    """WebSocket 模式（主动连接飞书，不需要公网地址）"""
    from __init__ import BayiAgent
    from handlers.feishu_ws_longpoll import FeishuWebSocketLongPoll
    
    # 创建 WebSocket 客户端（先创建，用于发送消息回调）
    feishu_config = _load_feishu_config()
    
    # 创建消息处理回调
    async def message_handler(user_id, message, chat_id, message_id, is_group):
        # 构建入口上下文
        from core.models import EntryContext
        
        chat_type = "group" if is_group else "direct"
        active_tasks = await agent.task_queue.get_active_tasks(user_id)
        queue_length = await agent.task_queue.get_queue_length()
        
        # 🔧 获取对话历史和任务记录
        conversation_history = agent.session_manager.get_history(
            user_id=user_id,
            chat_id=chat_id,
            limit=20  # 最近 20 轮对话
        )
        last_completed_tasks = agent.session_manager.get_completed_tasks(
            user_id=user_id,
            chat_id=chat_id,
            limit=5
        )
        
        context = EntryContext(
            user_id=user_id,
            channel="feishu",
            chat_type=chat_type,
            active_tasks=active_tasks,
            queue_length=queue_length,
            chat_id=chat_id,
            message_id=message_id,
            is_group=is_group,
            conversation_history=conversation_history,
            last_completed_tasks=last_completed_tasks
        )
        
        # 调用入口网关
        response = await agent.gateway.chat(message, context)
        
        # 🔧 记录对话历史
        agent.session_manager.add_message(
            user_id=user_id,
            message=message,
            response=response,
            chat_id=chat_id
        )
        
        return response
    
    # 创建 WebSocket 客户端
    ws_client = FeishuWebSocketLongPoll(
        app_id=feishu_config["app_id"],
        app_secret=feishu_config["app_secret"],
        message_handler=message_handler
    )
    
    # 创建 agent，传入发送消息回调
    agent = BayiAgent(send_message_callback=ws_client.send_message)
    await agent.start()
    
    # 启动 WebSocket 连接
    
    logger.info("="*50)
    logger.info("Bayi-Agent WebSocket 长连接模式")
    logger.info(f"App ID: {feishu_config['app_id']}")
    logger.info("主动连接飞书，不需要公网地址")
    logger.info("✅ 已启用任务结果自动推送")
    logger.info("="*50)
    
    try:
        await ws_client.start()
        # 保持运行
        while True:
            await asyncio.sleep(3600)
    except KeyboardInterrupt:
        logger.info("收到停止信号")
    finally:
        await ws_client.close()


async def run_webhook(port: int):
    """Webhook 模式（独立部署）"""
    from aiohttp import web
    from __init__ import BayiAgent
    from handlers.feishu_handler import handle_feishu_webhook
    
    agent = BayiAgent()
    await agent.start()
    
    async def webhook_handler(request):
        """处理 Webhook 请求"""
        try:
            data = await request.json()
            
            # 处理飞书事件
            if agent.feishu_handler:
                result = await handle_feishu_webhook(data, agent.feishu_handler)
                return web.json_response(result)
            else:
                logger.warning("飞书处理器未配置")
                return web.json_response({"error": "Feishu not configured"}, status=400)
        
        except Exception as e:
            logger.error(f"Webhook 处理失败: {e}", exc_info=True)
            return web.json_response({"error": str(e)}, status=500)
    
    async def health_check(request):
        """健康检查"""
        return web.json_response({
            "status": "ok",
            "queue_length": await agent.task_queue.get_queue_length(),
            "processing": agent.task_queue.processing
        })
    
    # 创建应用
    app = web.Application()
    
    # 飞书 webhook
    feishu_path = agent.config.get("feishu", {}).get("event_callback", "/webhook/feishu")
    app.router.add_post(feishu_path, webhook_handler)
    
    # 健康检查
    app.router.add_get("/health", health_check)
    
    # 启动服务
    logger.info(f"Bayi-Agent Webhook 服务启动: http://0.0.0.0:{port}")
    logger.info(f"飞书 Webhook: http://0.0.0.0:{port}{feishu_path}")
    
    runner = web.AppRunner(app)
    await runner.setup()
    
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    
    # 保持运行
    try:
        while True:
            await asyncio.sleep(3600)
    except KeyboardInterrupt:
        logger.info("收到停止信号")
    finally:
        await runner.cleanup()


def run_daemon():
    """守护进程模式（systemd）"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Bayi-Agent - 轻量级子智能体框架")
    parser.add_argument("--port", type=int, default=8765, help="Webhook 端口")
    parser.add_argument("--config", help="配置文件路径")
    
    args = parser.parse_args()
    
    # 设置配置路径
    if args.config:
        os.environ["BAYI_CONFIG"] = args.config
    
    # 运行
    asyncio.run(run_webhook(args.port))


def main():
    """主入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Bayi-Agent - 轻量级子智能体框架")
    parser.add_argument("--webhook", action="store_true", help="启动 Webhook 服务")
    parser.add_argument("--websocket", action="store_true", help="启动 WebSocket 服务（推荐，不需要公网地址）")
    parser.add_argument("--daemon", action="store_true", help="守护进程模式（systemd）")
    parser.add_argument("--port", type=int, default=8765, help="Webhook 端口")
    parser.add_argument("--config", help="配置文件路径")
    
    args = parser.parse_args()
    
    # 设置配置路径
    if args.config:
        os.environ["BAYI_CONFIG"] = args.config
    
    if args.websocket:
        # WebSocket 模式（推荐）
        asyncio.run(run_websocket())
    elif args.webhook or args.daemon:
        # Webhook 模式
        asyncio.run(run_webhook(args.port))
    else:
        # 交互模式
        asyncio.run(run_interactive())


if __name__ == "__main__":
    main()
