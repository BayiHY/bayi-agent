# Bayi-Agent

> 轻量级子智能体框架，用于并行任务处理

## 简介

Bayi-Agent 是一个轻量级子智能体框架，专注于：

- **快速响应**：入口 LLM 在 1 秒内给出口语回复
- **异步处理**：复杂任务后台处理，不阻塞对话
- **智能拆解**：自动拆分大任务为子任务
- **并行调度**：支持并行决策和多智能体协作

## 核心组件

### 1. 入口网关（BayiTaskGateway）

- 接收用户消息
- 意图分类（simple/complex/parallel_decisions/status/help/chat）
- 口语回复（自然、友好）
- 任务路由

### 2. 决策队列（DecisionTaskQueue）

- 管理任务排队
- 支持持久化（SQLite）
- 提供状态查询

### 3. 决策分析器（DecisionAnalyzer）

- 收集上下文
- 拆解任务
- 调度智能体
- 聚合结果
- 审核结果 ⭐ 新增
- 记录经验 ⭐ 新增

### 4. 智能体注册表（AgentRegistry）⭐ 新增

- 智能体配置管理
- 优化记录管理
- 能力层管理
- 自动学习改进

### 5. 智能体能力层（AgentCapabilities）⭐ 新增

- 技能管理（创建/调用/统计）
- 工具管理（创建/调用/统计）
- 经验管理（记录/总结/提取）
- 能力画像（生成/展示）
- 自我优化（分析/建议/应用）

### 6. 飞书处理器（FeishuHandler）

- 处理飞书消息事件
- 群聊过滤（只响应 @提及）
- 消息发送

## 快速开始

### 安装依赖

```bash
pip install aiohttp pyyaml
```

### 启动服务

```bash
# 交互模式
python run.py

# Webhook 模式（用于飞书）
python run.py --webhook --port 8080
```

### 配置

编辑 `bayi_config.yaml`：

```yaml
# 飞书配置
feishu:
  app_id: "your-app-id"
  app_secret: "your-app-secret"

# 模型配置
entry_model:
  name: "agnes-2.0-flash"
  temperature: 0.3
  max_tokens: 500

decision_model:
  name: "GLM-5"
  temperature: 0.7
  max_tokens: 4000
```

## 使用示例

### 简单任务

```
用户: 读取 /etc/config.yaml
助手: 好的，我来帮你读取这个文件。
[立即返回文件内容]
```

### 复杂任务

```
用户: 分析一下系统架构设计方案
助手: 这个需要我仔细分析一下，想通了答复你，我们可以继续聊。查询进展：'状态 task-123'
[后台处理，稍后通知]
```

### 并行决策

```
用户: 同时分析架构设计、数据库设计和接口设计
助手: 好的，我会逐项分析这三个设计方案，处理完后答复你。查询进展：'状态 task-123'
[后台并行处理]
```

### 查询状态

```
用户: 任务 task-123 怎么样？
助手: 任务 task-123 处理中，已耗时 30.5 秒
```

## 架构设计

详细设计文档见：

- `DOCS/规划/bayi-agent-planning.md` - 整体架构
- `DOCS/规划/bayi-agent-optimization.md` - 优化方案
- `DOCS/规划/bayi-agent-entry-context.md` - 入口上下文设计
- `DOCS/规划/bayi-agent-feishu-config.md` - 飞书配置
- `DOCS/规划/decision-task-queue-design.md` - 队列设计
- `DOCS/规划/decision-analyzer-design.md` - 决策分析器设计

## 目录结构

```
bayi-agent/
├── __init__.py               # 主程序
├── bayi_config.yaml          # 配置文件
├── run.py                    # 启动脚本
├── core/
│   ├── __init__.py
│   ├── models.py             # 数据模型
│   ├── queue.py              # 任务队列
│   ├── gateway.py            # 入口网关
│   ├── analyzer.py           # 决策分析器
│   ├── agent_registry.py     # 智能体注册表 ⭐
│   ├── agent_capabilities.py # 智能体能力层 ⭐
│   ├── skill_invoker.py      # 技能调用器
│   └── tools.py              # 工具执行
├── agents/                    # 智能体数据 ⭐
│   ├── agents.json
│   └── agent_optimizations.json
├── agent_data/                # 能力数据 ⭐
│   └── {agent_id}/
│       ├── skills.json
│       ├── custom_tools.json
│       └── experiences.json
├── handlers/
│   └── feishu_handler.py     # 飞书处理器
├── utils/
│   └── llm_client.py         # LLM 客户端
└── tests/               # 测试
```

## 开发计划

- [ ] 完善错误处理和重试机制
- [ ] 添加任务进度通知
- [ ] 支持更多渠道（Telegram、Slack 等）
- [ ] 实现技能缓存机制
- [ ] 添加监控和告警

## 许可

MIT
