"""
飞书消息处理器
处理飞书消息事件、构建入口上下文、发送消息
"""
import asyncio
import aiohttp
import logging
import json
import hashlib
from typing import Optional, Dict, Any

from core.models import EntryContext, DecisionTask, Intent
from core.queue import DecisionTaskQueue
from core.gateway import BayiTaskGateway


logger = logging.getLogger(__name__)


class FeishuHandler:
    """飞书消息处理器"""
    
    def __init__(
        self,
        app_id: str,
        app_secret: str,
        gateway: BayiTaskGateway,
        task_queue: DecisionTaskQueue
    ):
        self.app_id = app_id
        self.app_secret = app_secret
        self.gateway = gateway
        self.task_queue = task_queue
        
        # Tenant access token 缓存
        self._tenant_token: Optional[str] = None
        self._token_expires_at: float = 0
    
    async def handle_message(self, event: Dict[str, Any]) -> Optional[str]:
        """
        处理飞书消息事件
        
        Args:
            event: 飞书事件数据
        
        Returns:
            回复消息（可选）
        """
        try:
            # 提取消息信息
            message = event.get("message", {})
            sender = event.get("sender", {})
            
            chat_id = message.get("chat_id")
            message_id = message.get("message_id")
            content = message.get("content")
            msg_type = message.get("message_type")
            
            # 提取发送者信息
            sender_id = sender.get("sender_id", {}).get("open_id")
            
            # 解析消息内容
            if msg_type == "text":
                user_message = self._parse_text_message(content)
            else:
                # 只处理文本消息
                logger.debug(f"忽略非文本消息: {msg_type}")
                return None
            
            # 构建入口上下文
            context = await self._build_entry_context(
                chat_id=chat_id,
                message_id=message_id,
                sender_id=sender_id,
                content=content
            )
            
            # 群聊过滤：只响应 @提及 的消息
            if context.is_group:
                if not self._is_mentioned(message, self.app_id):
                    logger.debug("群聊消息未提及机器人，忽略")
                    return None
            
            # 调用入口网关
            response = await self.gateway.chat(user_message, context)
            
            # 发送回复
            await self.send_message(chat_id, response, message_id)
            
            return response
        
        except Exception as e:
            logger.error(f"处理飞书消息失败: {e}", exc_info=True)
            return None
    
    async def _build_entry_context(
        self,
        chat_id: str,
        message_id: str,
        sender_id: str,
        content: str
    ) -> EntryContext:
        """从飞书消息事件构建入口上下文"""
        
        # 判断是否群聊
        is_group = chat_id.startswith("oc_") and not chat_id.startswith("oc_user:")
        chat_type = "group" if is_group else "direct"
        
        # 获取活跃任务
        active_tasks = await self.task_queue.get_active_tasks(sender_id)
        queue_length = await self.task_queue.get_queue_length()
        
        # 获取最近任务 ID
        last_task_id = active_tasks[0] if active_tasks else None
        
        return EntryContext(
            user_id=sender_id,
            channel="feishu",
            chat_type=chat_type,
            active_tasks=active_tasks,
            queue_length=queue_length,
            last_task_id=last_task_id,
            chat_id=chat_id,
            message_id=message_id,
            is_group=is_group
        )
    
    def _parse_text_message(self, content: str) -> str:
        """
        解析文本消息内容
        
        Args:
            content: JSON 字符串，如 '{"text":"hello"}'
        
        Returns:
            文本内容
        """
        try:
            data = json.loads(content)
            return data.get("text", "")
        except:
            return content
    
    def _is_mentioned(self, message: Dict[str, Any], bot_id: str) -> bool:
        """
        判断消息是否 @提及 了机器人
        
        Args:
            message: 消息对象
            bot_id: 机器人 ID
        
        Returns:
            是否被提及
        """
        # 检查 mentions 字段
        mentions = message.get("mentions", [])
        for mention in mentions:
            if mention.get("id") == bot_id:
                return True
        
        # 检查文本中是否包含 @机器人名称
        content = message.get("content", "")
        if "@_user" in content or f"<at user_id=\"{bot_id}\">" in content:
            return True
        
        return False
    
    async def send_message(
        self,
        chat_id: str,
        message: str,
        reply_to: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        发送飞书消息
        
        Args:
            chat_id: Chat ID
            message: 消息内容
            reply_to: 引用回复的消息 ID（可选）
        
        Returns:
            API 响应
        """
        # 获取 tenant_access_token
        token = await self._get_tenant_access_token()
        
        # 构建请求
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
        
        if reply_to:
            # 飞书引用回复需要用 reply_message API
            # 这里简化处理，直接发送新消息
            pass
        
        # 发送消息
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as resp:
                result = await resp.json()
                
                if result.get("code") != 0:
                    logger.error(f"发送飞书消息失败: {result}")
                
                return result
    
    async def _get_tenant_access_token(self) -> str:
        """
        获取 tenant_access_token
        
        带缓存，避免频繁请求
        """
        import time
        
        # 检查缓存
        if self._tenant_token and time.time() < self._token_expires_at:
            return self._tenant_token
        
        # 请求新 token
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
                
                self._tenant_token = result.get("tenant_access_token")
                # 提前 5 分钟过期
                self._token_expires_at = time.time() + result.get("expire", 7200) - 300
                
                return self._tenant_token
    
    def verify_signature(
        self,
        signature: str,
        timestamp: str,
        nonce: str,
        body: str
    ) -> bool:
        """
        验证飞书请求签名
        
        Args:
            signature: 签名
            timestamp: 时间戳
            nonce: 随机数
            body: 请求体
        
        Returns:
            是否验证通过
        """
        # 拼接字符串
        s = f"{timestamp}{nonce}{self.app_secret}{body}"
        
        # 计算 SHA256
        hash_value = hashlib.sha256(s.encode()).hexdigest()
        
        # 验证签名
        return hash_value == signature


# Webhook 处理函数（用于 FastAPI/Flask）
async def handle_feishu_webhook(
    event: Dict[str, Any],
    handler: FeishuHandler
) -> Dict[str, Any]:
    """
    处理飞书 Webhook 事件
    
    Args:
        event: 飞书事件
        handler: 飞书消息处理器
    
    Returns:
        响应数据
    """
    # 处理 URL 验证
    if event.get("type") == "url_verification":
        return {"challenge": event.get("challenge")}
    
    # 处理消息事件
    if event.get("header", {}).get("event_type") == "im.message.receive_v1":
        # 异步处理，避免阻塞
        asyncio.create_task(handler.handle_message(event))
    
    return {"code": 0}
