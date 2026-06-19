# -*- coding: utf-8 -*-
"""
飞书 WebSocket 长连接客户端
完全参考 Hermes 实现（gateway/platforms/feishu.py）
"""
import asyncio
import logging
import json
import threading
import re
from typing import Optional, Callable, Any

try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    logging.warning("aiohttp 未安装，图片发送功能不可用")
    AIOHTTP_AVAILABLE = False

try:
    import lark_oapi as lark
    from lark_oapi.api.im.v1 import (
        CreateMessageRequest,
        CreateMessageRequestBody,
        CreateImageRequest,
    )
    from lark_oapi.event.dispatcher_handler import EventDispatcherHandler
    from lark_oapi.ws import Client as FeishuWSClient
    from lark_oapi.core.const import FEISHU_DOMAIN
    
    LARK_AVAILABLE = True
except ImportError:
    logging.warning("lark-oapi 未安装，请运行: pip install lark-oapi")
    lark = None
    LARK_AVAILABLE = False

logger = logging.getLogger(__name__)


class FeishuWebSocketLongPoll:
    """飞书 WebSocket 长连接客户端（参考 Hermes 实现）"""
    
    def __init__(
        self,
        app_id: str,
        app_secret: str,
        message_handler: Callable
    ):
        if not LARK_AVAILABLE:
            raise ImportError("需要安装 lark-oapi: pip install lark-oapi")
        
        self.app_id = app_id
        self.app_secret = app_secret
        self.message_handler = message_handler
        
        # 客户端
        self.client: Optional[lark.Client] = None
        self.ws_client: Optional[FeishuWSClient] = None
        self.event_handler: Optional[EventDispatcherHandler] = None
        
        # 线程管理（参考 Hermes）
        self._ws_thread: Optional[threading.Thread] = None
        self._ws_thread_loop: Optional[asyncio.AbstractEventLoop] = None
        self._running = False
        
        # WebSocket 配置（参考 Hermes）
        self._ws_ping_interval = 30
        self._ws_ping_timeout = 10
        self._ws_reconnect_interval = 5
        self._ws_reconnect_nonce = 0
    
    async def start(self):
        """启动 WebSocket 长连接"""
        logger.info(f"启动飞书 WebSocket 长连接: {self.app_id}")
        
        # 创建飞书客户端（用于发送消息）
        self.client = lark.Client.builder() \
            .app_id(self.app_id) \
            .app_secret(self.app_secret) \
            .log_level(lark.LogLevel.ERROR) \
            .build()
        
        # 构建事件处理器
        self.event_handler = self._build_event_handler()
        
        # 创建 WebSocket 客户端
        self.ws_client = FeishuWSClient(
            app_id=self.app_id,
            app_secret=self.app_secret,
            log_level=lark.LogLevel.INFO,
            event_handler=self.event_handler,
            domain=FEISHU_DOMAIN
        )
        
        # 在独立线程中运行 WebSocket（参考 Hermes）
        self._running = True
        self._ws_thread = threading.Thread(
            target=self._run_ws_client_hermes_style,
            daemon=True
        )
        self._ws_thread.start()
        
        logger.info("✓ 飞书 WebSocket 长连接已启动")
        
        # 等待连接建立
        await asyncio.sleep(3)
    
    def _build_event_handler(self) -> EventDispatcherHandler:
        """构建事件处理器"""
        handler = (
            EventDispatcherHandler.builder(
                encrypt_key="",  # WebSocket 模式不需要
                verification_token=""  # WebSocket 模式不需要
            )
            .register_p2_im_message_receive_v1(self._on_message)
            .build()
        )
        return handler
    
    def _on_message(self, data: Any):
        """处理消息事件（同步函数，由飞书 SDK 调用）"""
        try:
            # 打印原始数据结构，用于调试
            logger.info(f"收到原始事件: {type(data).__name__}")
            logger.debug(f"事件详情: {data}")
            
            # 提取消息信息
            event = data.event
            message = event.message
            sender = event.sender
            
            chat_id = message.chat_id
            message_id = message.message_id
            content = message.content
            msg_type = message.message_type
            
            sender_id = sender.sender_id.open_id
            
            logger.info(f"解析消息: chat_id={chat_id}, sender_id={sender_id}, msg_type={msg_type}")
            logger.info(f"消息内容: {content[:100] if content else 'None'}")
            
            # 只处理文本和富文本消息
            if msg_type not in ["text", "post"]:
                logger.debug(f"忽略非文本消息: {msg_type}")
                return
            
            # 解析消息内容
            user_message = self._parse_message_content(content, msg_type)
            
            if not user_message or not user_message.strip():
                logger.debug(f"消息内容为空，忽略")
                return
            
            logger.info(f"收到消息 [{sender_id}]: {user_message[:50]}")
            
            # 在线程事件循环中提交异步任务
            if self._ws_thread_loop:
                asyncio.run_coroutine_threadsafe(
                    self._handle_message_async(
                        user_id=sender_id,
                        message=user_message,
                        chat_id=chat_id,
                        message_id=message_id,
                        is_group=chat_id.startswith("oc_") and not chat_id.startswith("oc_user:")
                    ),
                    self._ws_thread_loop
                )
        
        except Exception as e:
            logger.error(f"处理消息失败: {e}", exc_info=True)
    
    async def _handle_message_async(
        self,
        user_id: str,
        message: str,
        chat_id: str,
        message_id: str,
        is_group: bool
    ):
        """异步处理消息"""
        try:
            # 调用消息处理器
            response = await self.message_handler(
                user_id=user_id,
                message=message,
                chat_id=chat_id,
                message_id=message_id,
                is_group=is_group
            )
            
            # 发送回复
            if response:
                await self.send_message(chat_id, response)
        
        except Exception as e:
            logger.error(f"异步处理消息失败: {e}", exc_info=True)
    
    def _parse_message_content(self, content: str, msg_type: str) -> str:
        """
        解析消息内容
        
        支持：
        - text: 纯文本消息
        - post: 富文本消息
        
        Args:
            content: 消息内容（JSON 字符串）
            msg_type: 消息类型
        
        Returns:
            解析后的文本内容
        """
        try:
            content_data = json.loads(content)
            
            if msg_type == "text":
                # 纯文本消息
                return content_data.get("text", "")
            
            elif msg_type == "post":
                # 富文本消息
                # 格式: {"title": "", "content": [[{"tag": "text", "text": "..."}]]}
                text_parts = []
                
                # 提取标题
                title = content_data.get("title", "")
                if title:
                    text_parts.append(title)
                
                # 提取正文内容
                content_body = content_data.get("content", [])
                for paragraph in content_body:
                    if isinstance(paragraph, list):
                        for element in paragraph:
                            if isinstance(element, dict) and element.get("tag") == "text":
                                text_parts.append(element.get("text", ""))
                
                return "\n".join(text_parts)
            
            else:
                # 其他类型，尝试提取文本
                return content_data.get("text", "")
        
        except Exception as e:
            logger.debug(f"解析消息内容失败: {e}")
            return content
    
    def _run_ws_client_hermes_style(self):
        """在独立线程中运行 WebSocket 客户端（参考 Hermes）"""
        import lark_oapi.ws.client as ws_client_module
        
        try:
            # 创建线程专属的事件循环
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            # 关键：设置 ws_client_module.loop（参考 Hermes）
            ws_client_module.loop = loop
            self._ws_thread_loop = loop
            
            # 覆盖 websockets.connect 以设置 ping 参数（参考 Hermes）
            original_connect = ws_client_module.websockets.connect
            original_configure = getattr(self.ws_client, "_configure", None)
            
            def _connect_with_overrides(*args: Any, **kwargs: Any) -> Any:
                if self._ws_ping_interval is not None and "ping_interval" not in kwargs:
                    kwargs["ping_interval"] = self._ws_ping_interval
                if self._ws_ping_timeout is not None and "ping_timeout" not in kwargs:
                    kwargs["ping_timeout"] = self._ws_ping_timeout
                return original_connect(*args, **kwargs)
            
            def _apply_runtime_ws_overrides() -> None:
                try:
                    setattr(self.ws_client, "_reconnect_nonce", self._ws_reconnect_nonce)
                    setattr(self.ws_client, "_reconnect_interval", self._ws_reconnect_interval)
                    if self._ws_ping_interval is not None:
                        setattr(self.ws_client, "_ping_interval", self._ws_ping_interval)
                except Exception:
                    logger.debug("Failed to apply websocket overrides", exc_info=True)
            
            def _configure_with_overrides(conf: Any) -> Any:
                if original_configure is None:
                    raise RuntimeError("_configure called but original_configure is None")
                result = original_configure(conf)
                _apply_runtime_ws_overrides()
                return result
            
            # 应用覆盖
            ws_client_module.websockets.connect = _connect_with_overrides
            if original_configure is not None:
                setattr(self.ws_client, "_configure", _configure_with_overrides)
            _apply_runtime_ws_overrides()
            
            logger.info("WebSocket 线程启动，开始监听消息...")
            
            # 运行 WebSocket 客户端（阻塞）
            self.ws_client.start()
            
        except Exception as e:
            logger.error(f"WebSocket 线程异常: {e}", exc_info=True)
        finally:
            # 清理（参考 Hermes）
            ws_client_module.websockets.connect = original_connect
            if original_configure is not None:
                setattr(self.ws_client, "_configure", original_configure)
            
            # 取消所有待处理任务
            pending = [t for t in asyncio.all_tasks(loop) if not t.done()]
            for task in pending:
                task.cancel()
            if pending:
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            
            # 关闭循环
            try:
                loop.stop()
            except Exception:
                pass
            try:
                loop.close()
            except Exception:
                pass
            
            self._ws_thread_loop = None
            logger.info("WebSocket 线程结束")
            self._running = False
    
    async def send_message(self, chat_id: str, message: str):
        """发送消息（支持文本和图片）"""
        try:
            # 检查是否包含图片 URL
            import re
            import aiohttp
            import tempfile
            import os
            
            image_url_pattern = r'https?://[^\s]+\.(?:png|jpg|jpeg|gif|webp)'
            image_urls = re.findall(image_url_pattern, message)
            
            # 先发送文本消息
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
                logger.info(f"✓ 消息已发送: {chat_id}")
            
            # 如果有图片 URL，下载并上传到飞书
            for image_url in image_urls:
                try:
                    logger.info(f"下载图片: {image_url}")
                    
                    # 下载图片
                    async with aiohttp.ClientSession() as session:
                        async with session.get(image_url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                            if resp.status == 200:
                                image_data = await resp.read()
                                
                                # 保存到临时文件
                                with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp_file:
                                    tmp_file.write(image_data)
                                    tmp_file_path = tmp_file.name
                                
                                # 上传到飞书
                                try:
                                    # 使用飞书 SDK 上传图片
                                    from lark_oapi.api.im.v1 import CreateImageRequestBody
                                    
                                    with open(tmp_file_path, "rb") as f:
                                        # 构建上传请求
                                        upload_request = CreateImageRequest.builder().request_body(
                                            CreateImageRequestBody.builder()
                                            .image_type("message")
                                            .image(f)
                                            .build()
                                        ).build()
                                        
                                        upload_response = self.client.im.v1.image.create(upload_request)
                                        
                                        if upload_response.success():
                                            image_key = upload_response.data.image_key
                                            logger.info(f"✓ 图片上传成功: {image_key}")
                                            
                                            # 发送图片消息
                                            image_request = (
                                                CreateMessageRequest.builder()
                                                .receive_id_type("chat_id")
                                                .request_body(
                                                    CreateMessageRequestBody.builder()
                                                    .receive_id(chat_id)
                                                    .msg_type("image")
                                                    .content(json.dumps({"image_key": image_key}))
                                                    .build()
                                                )
                                                .build()
                                            )
                                            
                                            image_response = self.client.im.v1.message.create(image_request)
                                            
                                            if image_response.success():
                                                logger.info(f"✓ 图片消息已发送")
                                            else:
                                                logger.warning(f"发送图片消息失败: {image_response.code} - {image_response.msg}")
                                        else:
                                            logger.warning(f"上传图片失败: {upload_response.code} - {upload_response.msg}")
                                finally:
                                    # 删除临时文件
                                    try:
                                        os.unlink(tmp_file_path)
                                    except:
                                        pass
                            else:
                                logger.warning(f"下载图片失败: HTTP {resp.status}")
                except Exception as img_error:
                    logger.warning(f"发送图片失败: {img_error}")
        
        except Exception as e:
            logger.error(f"发送消息失败: {e}", exc_info=True)
    
    async def close(self):
        """关闭连接"""
        self._running = False
        logger.info("WebSocket 长连接已关闭")
