# Bayi-Agent 快速入门

## 项目概览

Bayi-Agent 是一个轻量级子智能体框架，已成功实现所有核心组件。

## 已实现功能

✅ **核心数据模型**
- `EntryContext`: 入口上下文（精简版，只包含必需字段）
- `DecisionTask`: 决策任务（支持状态流转）
- `SubTask`: 子任务（支持依赖关系）
- `EntryResult`: 入口 LLM 返回结果

✅ **决策任务队列**
- 支持 `enqueue`/`dequeue` 操作
- SQLite 持久化（重启后恢复）
- 任务状态管理（queued → processing → completed/failed）
- 状态查询和队列监控

✅ **入口网关**
- 意图分类（6 种类型）
- 口语化快速回复（< 1 秒）
- 任务路由（simple/complex/parallel_decisions）
- 任务状态查询

✅ **决策分析器**
- 上下文收集
- 任务拆分（基于 DAG）
- 智能体调度（专职/临时）
- 子任务执行和结果聚合

✅ **飞书处理器**
- 消息事件处理
- 群聊过滤（只响应 @提及）
- 消息发送
- 签名验证

## 项目结构

```
bayi-agent/
├── __init__.py              # 主程序（BayiAgent 类）
├── bayi_config.yaml         # 配置文件
├── run.py                   # 启动脚本
├── README.md                # 项目文档
├── requirements.txt         # 依赖
├── core/
│   ├── __init__.py
│   ├── models.py            # 数据模型
│   ├── queue.py             # 任务队列
│   ├── gateway.py           # 入口网关
│   └── analyzer.py          # 决策分析器
├── handlers/
│   ├── __init__.py
│   └── feishu_handler.py    # 飞书处理器
├── utils/
│   ├── __init__.py
│   └── llm_client.py        # LLM 客户端
└── tests/
    ├── __init__.py
    └── test_basic.py        # 基础测试
```

## 测试结果

```
Bayi-Agent 测试

=== 测试入口上下文 ===
✓ 入口上下文测试通过

=== 测试决策任务 ===
✓ 决策任务测试通过

=== 测试任务队列 ===
✓ 任务队列测试通过

=== 所有测试通过 ===
```

## 下一步

### 1. 配置飞书机器人

编辑 `bayi_config.yaml`：

```yaml
feishu:
  app_id: "your_app_id_here"
  app_secret: "your_app_secret_here"
```

### 2. 启动 Webhook 服务

```bash
cd /root/.openclaw/workspace/bayi-agent
python3 run.py --webhook --port 8080
```

### 3. 配置飞书事件订阅

在飞书开放平台配置：
- 事件订阅地址: `http://your-domain:8080/webhook/feishu`
- 订阅事件: `im.message.receive_v1`

### 4. 测试对话

```
用户: 你好
助手: 你好呀！有什么我可以帮你的吗？

用户: 分析一下系统架构
助手: 这个需要我仔细分析一下，想通了答复你，我们可以继续聊。查询进展：'状态 task-xxx'

用户: 状态 task-xxx
助手: 任务 task-xxx 处理中，已耗时 30.5 秒
```

## 与 OpenClaw 集成

Bayi-Agent 可以作为 OpenClaw 的子智能体使用：

```python
# 在 OpenClaw 中启动 Bayi-Agent
from bayi_agent import BayiAgent

agent = BayiAgent(config_path="bayi-agent/bayi_config.yaml")
await agent.start()

# 处理消息
response = await agent.chat(message, context)
```

## 待优化项

1. **错误处理**：添加更完善的错误处理和重试机制
2. **进度通知**：任务处理过程中的进度更新
3. **技能缓存**：避免重复加载技能
4. **监控告警**：队列积压、处理超时等告警
5. **更多渠道**：支持 Telegram、Slack 等

## 参考文档

- `DOCS/规划/bayi-agent-planning.md` - 整体架构设计
- `DOCS/规划/bayi-agent-optimization.md` - 优化方案
- `DOCS/规划/bayi-agent-entry-context.md` - 入口上下文设计
- `DOCS/规划/bayi-agent-feishu-config.md` - 飞书配置
- `DOCS/规划/decision-task-queue-design.md` - 队列设计
- `DOCS/规划/decision-analyzer-design.md` - 决策分析器设计
