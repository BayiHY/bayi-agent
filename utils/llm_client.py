"""
LLM 客户端封装
支持多种模型后端（Agnes API、GLM 等）
"""
import aiohttp
import asyncio
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass


logger = logging.getLogger(__name__)


@dataclass
class LLMConfig:
    """LLM 配置"""
    name: str
    api_base: str = ""
    api_key: str = ""
    temperature: float = 0.7
    max_tokens: int = 2000
    timeout: int = 30
    max_retries: int = 2  # 最大重试次数


class LLMClient:
    """LLM 客户端"""
    
    def __init__(self, config: LLMConfig):
        self.config = config
        self.session = None
        self.model = config.name  # 🔧 添加 model 属性
    
    async def chat(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> str:
        """
        调用 LLM
        
        Args:
            messages: 消息列表 [{"role": "system/user/assistant", "content": "..."}]
            tools: 工具列表（可选）
            **kwargs: 其他参数
        
        Returns:
            LLM 响应文本
        """
        # 根据模型名称选择 API
        model_name = self.config.name.lower()
        
        if model_name.startswith("agnes"):
            return await self._call_agnes_api(messages, tools, **kwargs)
        elif "glm" in model_name or model_name.startswith("jdcloud"):
            return await self._call_glm_api(messages, tools, **kwargs)
        else:
            # 默认使用 Agnes API（OpenAI 兼容）
            return await self._call_agnes_api(messages, tools, **kwargs)
    
    async def _call_agnes_api(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> str:
        """
        调用 Agnes API（带重试机制）
        
        Agnes API 通常与 OpenAI API 兼容
        """
        # 使用环境变量或默认配置
        api_base = self.config.api_base or os.environ.get(
            "AGNES_API_BASE",
            "https://api.agnes.ai/v1"
        )
        api_key = self.config.api_key or os.environ.get("AGNES_API_KEY", "")
        
        # 如果没有配置 API key，返回模拟响应
        if not api_key:
            logger.warning("未配置 AGNES_API_KEY，使用模拟响应")
            return self._get_mock_response(messages)
        
        headers = {
            "Content-Type": "application/json"
        }
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        
        payload = {
            "model": self.config.name,
            "messages": messages,
            "temperature": kwargs.get("temperature", self.config.temperature),
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens)
        }
        
        if tools:
            payload["tools"] = tools
        
        timeout = aiohttp.ClientTimeout(total=self.config.timeout)
        max_retries = getattr(self.config, 'max_retries', 2)
        
        logger.debug(f"调用 Agnes API: {api_base}/chat/completions, model={self.config.name}")
        
        # 重试机制
        for attempt in range(max_retries + 1):
            try:
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.post(
                        f"{api_base}/chat/completions",
                        headers=headers,
                        json=payload
                    ) as resp:
                        result = await resp.json()
                        
                        if "error" in result:
                            error_msg = result["error"].get("message", str(result["error"]))
                            logger.error(f"Agnes API error: {error_msg}")
                            raise Exception(f"Agnes API error: {error_msg}")
                        
                        content = result["choices"][0]["message"]["content"]
                        logger.debug(f"Agnes API 响应成功: {len(content)} 字符")
                        return content
            
            except asyncio.TimeoutError:
                if attempt < max_retries:
                    logger.warning(f"Agnes API 超时，重试 {attempt + 1}/{max_retries}")
                    await asyncio.sleep(1)  # 等待1秒后重试
                    continue
                else:
                    logger.error(f"Agnes API 超时 ({self.config.timeout}s)，已重试 {max_retries} 次")
                    raise Exception(f"API 调用超时，请稍后重试")
            
            except Exception as e:
                if attempt < max_retries and "Connection" in str(e):
                    logger.warning(f"连接失败，重试 {attempt + 1}/{max_retries}: {e}")
                    await asyncio.sleep(1)
                    continue
                else:
                    logger.error(f"Agnes API 调用失败: {e}", exc_info=True)
                    raise
        
        # 不应该到这里
        raise Exception("API 调用失败，未知错误")

    def _get_mock_response(self, messages: List[Dict[str, str]]) -> str:
        """生成模拟响应（用于测试或 API 不可用时）"""
        # 提取用户消息
        user_message = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                user_message = msg.get("content", "")
                break
        
        # 简单的意图判断和响应
        if "你好" in user_message or "hello" in user_message.lower():
            return "你好！我是 Bayi-Agent，很高兴为你服务。有什么我可以帮助你的吗？"
        elif "帮助" in user_message or "help" in user_message.lower():
            return "我可以帮你：\n1. 简单问答\n2. 文件读取\n3. 任务分析\n\n请问有什么需要我帮忙的？"
        else:
            return f"收到你的消息：{user_message[:50]}。我正在思考中..."

    async def _call_glm_api(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> str:
        """
        调用 GLM API（智谱 AI）
        """
        # 使用配置或环境变量
        api_base = self.config.api_base or os.environ.get(
            "GLM_API_BASE",
            "https://open.bigmodel.cn/api/paas/v4"
        )
        api_key = self.config.api_key or os.environ.get("BIGMODEL_API_KEY", "")
        
        if not api_key:
            logger.warning("未配置 GLM API Key，使用模拟响应")
            return self._get_mock_response(messages)
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        
        payload = {
            "model": self.config.name,
            "messages": messages,
            "temperature": kwargs.get("temperature", self.config.temperature),
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens)
        }
        
        if tools:
            payload["tools"] = tools
        
        timeout = aiohttp.ClientTimeout(total=self.config.timeout)
        
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    f"{api_base}/chat/completions",
                    headers=headers,
                    json=payload
                ) as resp:
                    result = await resp.json()
                    
                    if "error" in result:
                        raise Exception(f"GLM API error: {result['error']}")
                    
                    return result["choices"][0]["message"]["content"]
        except Exception as e:
            logger.warning(f"GLM API 调用失败: {e}")
            # 降级处理：返回模拟响应
            return self._get_mock_response(messages)


import os  # 在文件顶部导入，但这里为了演示放在这里
