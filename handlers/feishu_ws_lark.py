# -*- coding: utf-8 -*-
"""
飞书 WebSocket 连接处理器
使用飞书官方 SDK lark-oapi（参考 Hermes 实现）
"""
import asyncio
import logging
import json
from typing import Optional, Dict, Any, Callable

try:
    import lark_oapi as lark
    from lark_oapi.api.im.v1 import (
        CreateMessageRequest,
        CreateMessageRequestBody,
    )
    LARK_AVAILABLE = True
except ImportError:
    logging.warning("lark-oapi 未安装，请运行: pip install lark-oapi")
    lark = None
    LARK_AVAILABLE = False

logger = logging.getLogger(__name__)


class FeishuWebSocketClient:
    """飞书 WebSocket 客户端（基于 lark-oapi，参考 Hermes）"""
    
    def __init__(
        self,
        app_id: str,
        app_secret: str,
        message_handler: Callable  # 异步消息处理回调
    ):
        if not LARK_AVAILABLE:
            raise ImportError("需要安装 lark-oapi: pip install lark-oapi")
        
        self.app_id = app_id
        self.app_secret = app_secret
        self.message_handler = message_handler
        
        # 飞书客户端
        self.client: Optional[lark.Client] = None
        self.ws_client: Optional[lark.ws.Client] = None
    
    async def start(self):
        """启动 WebSocket 连接"""
        logger.info(f"启动飞书 WebSocket: {self.app_id}")
        
        # 创建飞书客户端（用于发送消息）
        self.client = lark.Client.builder() \
            .app_id(self.app_id) \
            .app_secret(self.app_secret) \
            .log_level(lark.LogLevel.ERROR) \
            .build()
        
        # 创建 WebSocket 客户端
        self.ws_client = (
            lark.ws.Client.builder()
            .app_id(self.app_id)
            .app_secret(self.app_secret)
            .log_level(lark.LogLevel.INFO)
            .register_p2_im_message_receive_v1(self._on_message)
            .build()
        )
        
        logger.info("✓ 飞书 WebSocket 连接成功（等待消息...）")
        
        # 启动 WebSocket（阻塞）
        await self.ws_client.start()
    
    async def _on_message(self, data: lark.im.v1.P2ImMessageReceiveV1):
        """处理消息事件"""
        try:
            # 提取消息信息
            event = data.event
            message = event.message
            sender = event.sender
            
            chat_id = message.chat_id
            message_id = message.message_id
            content = message.content
            msg_type = message.message_type
            
            sender_id = sender.sender_id.open_id
            
            # 只处理文本消息
            if msg_type != "text":
                logger.debug(f"忽略非文本消息: {msg_type}")
                return
            
            # 解析文本内容
            try:
                content_data = json.loads(content)
                user_message = content_data.get("text", "")
            except:
                user_message = content
            
            logger.info(f"收到消息 [{sender_id}]: {user_message[:50]}")
            
            # 调用消息处理器
            response = await self.message_handler(
                user_id=sender_id,
                message=user_message,
                chat_id=chat_id,
                message_id=message_id,
                is_group=chat_id.startswith("oc_") and not chat_id.startswith("oc_user:")
            )
            
            # 发送回复
            if response:
                await self.send_message(chat_id, response)
        
        except Exception as e:
            logger.error(f"处理消息失败: {e}", exc_info=True)
    
    async def send_message(self, chat_id: str, message: str):
        """发送消息"""
        try:
            request = (
                CreateMessageRequest.builder()
                .receive_id_type("chat_id")
                .request_body(
                    CreateMessageRequestBody.builder()
                    .receive_id(chat_id)
                    .msg_type("text")
                    .content(json.dumps({"text": message}))
                    .build()
                )
                .build()
            )
            
            response = self.client.im.v1.message.create(request)
            
            if not response.success():
                logger.error(f"发送消息失败: {response.code} - {response.msg}")
            else:
                logger.debug(f"消息已发送: {chat_id}")
        
        except Exception as e:
            logger.error(f"发送消息失败: {e}", exc_info=True)
    
    async def close(self):
        """关闭连接"""
        if self.ws_client:
            await self.ws_client.stop()
        logger.info("WebSocket 连接已关闭")
