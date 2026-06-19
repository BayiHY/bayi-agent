# -*- coding: utf-8 -*-
"""
飞书 WebSocket 连接处理器
不需要公网地址，主动连接飞书服务器
"""
import asyncio
import logging
import json
import hashlib
import time
from typing import Optional, Dict, Any

try:
    import websockets
except ImportError:
    logging.warning("websockets 未安装，请运行: pip install websockets")
    websockets = None

logger = logging.getLogger(__name__)


class FeishuWebSocketHandler:
    """飞书 WebSocket 消息处理器"""
    
    # 飞书 WebSocket 地址
    WS_URL = "wss://open.feishu.cn/open-apis/open-message/v1/websocket"
    
    def __init__(
        self,
        app_id: str,
        app_secret: str,
        gateway,  # BayiTaskGateway
        task_queue  # DecisionTaskQueue
    ):
        self.app_id = app_id
        self.app_secret = app_secret
        self.gateway = gateway
        self.task_queue = task_queue
        
        self.ws: Optional[Any] = None
        self.running = False
        self._heartbeat_task: Optional[asyncio.Task] = None
    
    async def connect(self):
        """连接飞书 WebSocket"""
        if not websockets:
            raise ImportError("需要安装 websockets: pip install websockets")
        
        # 获取连接凭证
        ticket = await self._get_websocket_ticket()
        
        # 连接 WebSocket
        ws_url = f"{self.WS_URL}?ticket={ticket}"
        
        logger.info(f"连接飞书 WebSocket: {self.app_id}")
        
        self.running = True
        self.ws = await websockets.connect(ws_url)
        
        logger.info("✓ 飞书 WebSocket 连接成功")
        
        # 启动心跳
        self._heartbeat_task = asyncio.create_task(self._send_heartbeat())
        
        # 接收消息
        await self._receive_messages()
    
    async def _get_websocket_ticket(self) -> str:
        """获取 WebSocket 连接 ticket"""
        import aiohttp
        
        url = "https://open.feishu.cn/open-apis/open-message/v1/websocket_ticket"
        
        headers = {
            "Authorization": f"Bearer {await self._get_tenant_token()}"
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers) as resp:
                result = await resp.json()
                
                if result.get("code") != 0:
                    raise Exception(f"获取 WebSocket ticket 失败: {result}")
                
                return result["data"]["ticket"]
    
    async def _get_tenant_token(self) -> str:
        """获取 tenant_access_token"""
        import aiohttp
        
        url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
        payload = {
            "app_id": self.app_id,
            "app_secret": self.app_secret
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as resp:
                result = await resp.json()
                
                if result.get("code") != 0:
                    raise Exception(f"获取 tenant_access_token 失败: {result}")
                
                return result.get("tenant_access_token")
    
    async def _send_heartbeat(self):
        """发送心跳"""
        while self.running:
            try:
                if self.ws:
                    await self.ws.send(json.dumps({"type": "heartbeat"}))
                    logger.debug("心跳发送")
                await asyncio.sleep(30)  # 30秒心跳
            except Exception as e:
                logger.error(f"心跳失败: {e}")
                await asyncio.sleep(5)
    
    async def _receive_messages(self):
        """接收消息"""
        while self.running:
            try:
                message = await self.ws.recv()
                data = json.loads(message)
                
                await self._handle_message(data)
            
            except websockets.exceptions.ConnectionClosed:
                logger.warning("WebSocket 连接断开，尝试重连...")
                await asyncio.sleep(5)
                await self.connect()
            
            except Exception as e:
                logger.error(f"接收消息失败: {e}", exc_info=True)
                await asyncio.sleep(1)
    
    async def _handle_message(self, data: Dict[str, Any]):
        """处理消息"""
        msg_type = data.get("type")
        
        if msg_type == "pong":
            # 心跳响应
            logger.debug("心跳响应")
            return
        
        if msg_type == "message":
            # 业务消息
            event = data.get("data", {})
            await self._process_event(event)
        
        else:
            logger.debug(f"忽略消息类型: {msg_type}")
    
    async def _process_event(self, event: Dict[str, Any]):
        """处理业务事件"""
        try:
            # 提取消息信息
            message = event.get("message", {})
            sender = event.get("sender", {})
            
            chat_id = message.get("chat_id")
            message_id = message.get("message_id")
            content = message.get("content")
            msg_type = message.get("message_type")
            
            sender_id = sender.get("sender_id", {}).get("open_id")
            
            # 解析文本消息
            if msg_type == "text":
                user_message = self._parse_text(content)
            else:
                logger.debug(f"忽略非文本消息: {msg_type}")
                return
            
            # 构建入口上下文
            from core.models import EntryContext
            
            is_group = chat_id.startswith("oc_") and not chat_id.startswith("oc_user:")
            chat_type = "group" if is_group else "direct"
            
            active_tasks = await self.task_queue.get_active_tasks(sender_id)
            queue_length = await self.task_queue.get_queue_length()
            
            context = EntryContext(
                user_id=sender_id,
                channel="feishu",
                chat_type=chat_type,
                active_tasks=active_tasks,
                queue_length=queue_length,
                chat_id=chat_id,
                message_id=message_id,
                is_group=is_group
            )
            
            # 群聊过滤
            if is_group:
                if not self._is_mentioned(message, self.app_id):
                    logger.debug("群聊消息未提及机器人，忽略")
                    return
            
            # 调用入口网关
            response = await self.gateway.chat(user_message, context)
            
            # 发送回复
            await self._send_message(chat_id, response)
            
            logger.info(f"消息处理完成: {sender_id}")
        
        except Exception as e:
            logger.error(f"处理事件失败: {e}", exc_info=True)
    
    def _parse_text(self, content: str) -> str:
        """解析文本消息"""
        try:
            data = json.loads(content)
            return data.get("text", "")
        except:
            return content
    
    def _is_mentioned(self, message: Dict[str, Any], bot_id: str) -> bool:
        """判断是否被提及"""
        mentions = message.get("mentions", [])
        for mention in mentions:
            if mention.get("id") == bot_id:
                return True
        return False
    
    async def _send_message(self, chat_id: str, message: str):
        """发送消息"""
        import aiohttp
        
        token = await self._get_tenant_token()
        
        url = "https://open.feishu.cn/open-apis/im/v1/messages"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "receive_id": chat_id,
            "msg_type": "text",
            "content": json.dumps({"text": message})
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as resp:
                result = await resp.json()
                
                if result.get("code") != 0:
                    logger.error(f"发送消息失败: {result}")
    
    async def close(self):
        """关闭连接"""
        self.running = False
        
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        
        if self.ws:
            await self.ws.close()
        
        logger.info("WebSocket 连接已关闭")