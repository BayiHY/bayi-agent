# Bayi-Agent

> 轻量级多模型协同智能体框架 - 让 AI 助手更快、更智能

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.8+-green.svg)](https://www.python.org/)

## ✨ 核心特性

- **🚀 快速响应**：入口模型 1 秒内给出口语回复，用户无需等待
- **🧠 智能拆解**：自动识别复杂任务，拆分为可并行执行的子任务
- **🔄 多模型协同**：入口模型 + 决策模型 + 模型池，各司其职
- **🤖 自主智能体**：支持动态创建专职智能体，自动优化能力
- **📊 自我进化**：记录执行经验，持续改进成功率
- **💬 多渠道支持**：飞书、Telegram、Slack 等多平台接入

## 🏗️ 架构设计

```
用户消息 → 入口网关 → 意图分类 → 任务路由
                              ↓
                    ┌─────────┴─────────┐
                    ↓                   ↓
              简单任务              复杂任务
           (入口模型直接回复)        ↓
                              决策分析器
                                  ↓
                          ┌───────┴───────┐
                          ↓               ↓
                    拆分子任务       调度智能体
                          ↓               ↓
                      执行工具      生成代码/调用技能
                          ↓               ↓
                          └───────┬───────┘
                                  ↓
                            结果聚合 → 审核验证 → 用户通知
```

## 🚀 快速开始

### 1. 安装

```bash
git clone https://github.com/BayiHY/bayi-agent.git
cd bayi-agent
pip install -r requirements.txt
```

### 2. 配置

复制配置模板并填入你的 API 密钥：

```bash
cp bayi_config.yaml.example bayi_config.yaml
```

编辑 `bayi_config.yaml`：

```yaml
# 飞书配置（可选）
feishu:
  app_id: "your_app_id_here"
  app_secret: "your_app_secret_here"

# 入口模型（快速响应）
entry_model:
  name: "agnes-2.0-flash"
  api_base: "https://apihub.agnes-ai.com/v1"
  api_key: "your_api_key_here"
  temperature: 0.3
  max_tokens: 500

# 决策模型（复杂任务分析）
decision_model:
  name: "GLM-5"
  api_base: "https://modelservice.jdcloud.com/coding/openai/v1"
  api_key: "your_api_key_here"
  temperature: 0.7
  max_tokens: 4000

# 模型池（模型切换和降级）
model_pool:
  primary:
    name: "GLM-5"
    api_key: "your_api_key_here"
  fallback_1:
    name: "agnes-2.0-flash"
    api_key: "your_api_key_here"
```

### 3. 启动

**交互模式**（测试用）：
```bash
python run.py
```

**WebSocket 模式**（飞书集成）：
```bash
python run.py --websocket
```

**Webhook 模式**（HTTP 服务）：
```bash
python run.py --webhook --port 8080
```

**Systemd 服务**（生产环境推荐）：
```bash
sudo cp bayi-agent.service /etc/systemd/system/
sudo systemctl enable bayi-agent
sudo systemctl start bayi-agent
```

### 4. 测试对话

```
用户: 你好
助手: 你好呀！有什么我可以帮你的吗？

用户: 帮我分析一下这个项目的架构设计
助手: 好的，这个需要我仔细分析一下，想通了答复你，我们可以继续聊。
      查询进展：'状态 task-123'

用户: 状态 task-123
助手: 任务 task-123 已完成，耗时 45.2 秒
      
      【架构分析结果】
      该项目采用三层架构设计...
```

## 📚 核心组件

### 1. 入口网关（Gateway）

- **意图分类**：识别 6 种任务类型
  - `simple` - 简单任务（直接回复）
  - `complex` - 复杂任务（后台处理）
  - `parallel_decisions` - 并行决策（多任务拆分）
  - `status` - 状态查询
  - `help` - 帮助信息
  - `chat` - 闲聊
  
- **快速响应**：< 1 秒给出口语化回复
- **任务路由**：智能分发到合适的处理通道

### 2. 决策分析器（Analyzer）

- **上下文收集**：自动收集相关信息
- **任务拆分**：基于 DAG 的子任务拆解
- **智能体调度**：动态创建专职智能体
- **代码生成**：根据任务生成执行代码
- **结果审核**：验证执行结果质量
- **经验记录**：记录成功/失败经验

### 3. 智能体注册表（AgentRegistry）

- 管理专职智能体配置
- 记录优化历史
- 持久化能力数据

### 4. 智能体能力层（AgentCapabilities）

- **技能管理**：创建、调用、统计
- **工具管理**：注册、执行、监控
- **经验管理**：记录、总结、提取
- **自我优化**：分析表现、自动改进

### 5. 模型池（ModelPool）

- 主力模型 + 备用模型配置
- 自动模型切换（成功率 < 50% 时）
- 任务类型到模型的映射

## 🔧 工具和技能

### 内置工具

- `web_search` - 网络搜索（Tavily API）
- `read_file` - 读取文件
- `execute_code` - 执行 Python 代码
- `list_dir` - 列出目录
- `image_generator` - 生成图片

### 自定义技能

支持通过 OpenClaw 技能系统扩展：

```yaml
agents:
  specialized:
    architect:
      skills: ["architecture-analysis", "design-patterns"]
      tools: ["read_file", "search_web", "draw_diagram"]
      description: "架构分析专家"
```

## 📊 性能监控

### 日志查看

```bash
# 实时日志
journalctl -u bayi-agent -f

# 最近 100 条
journalctl -u bayi-agent -n 100

# 错误日志
journalctl -u bayi-agent -p err
```

### 关键指标

- **响应时间**：入口模型平均响应 < 1 秒
- **成功率**：决策模型任务成功率 > 70%
- **模型切换**：自动切换阈值 50% 成功率

详细日志说明见 [LOG_PATHS.md](LOG_PATHS.md)

## 🔒 安全和隐私

### 配置文件保护

- `bayi_config.yaml` 已被 `.gitignore` 排除
- 所有敏感信息从环境变量读取
- 配置模板使用占位符

### 环境变量

```bash
export TAVILY_API_KEY="your_tavily_key"
export FEISHU_APP_ID="cli_xxx"
export FEISHU_APP_SECRET="your_secret"
export ENTRY_MODEL_API_KEY="your_key"
export DECISION_MODEL_API_KEY="your_key"
```

详细配置说明见 [CONFIG.md](CONFIG.md)

## 📖 文档

- [CONFIG.md](CONFIG.md) - 配置文件详细说明
- [DEPLOYMENT.md](DEPLOYMENT.md) - 部署指南
- [QUICKSTART.md](QUICKSTART.md) - 快速入门
- [LOG_PATHS.md](LOG_PATHS.md) - 日志路径说明

## 🛠️ 开发

### 运行测试

```bash
python -m pytest tests/
```

### 项目结构

```
bayi-agent/
├── core/                     # 核心模块
│   ├── gateway.py           # 入口网关
│   ├── analyzer.py          # 决策分析器
│   ├── agent_registry.py    # 智能体注册表
│   ├── agent_capabilities.py # 智能体能力层
│   ├── queue.py             # 任务队列
│   ├── models.py            # 数据模型
│   └── tools.py             # 工具执行
├── handlers/                 # 渠道处理器
│   ├── feishu_handler.py    # 飞书处理
│   └── feishu_websocket.py  # WebSocket 连接
├── utils/                    # 工具函数
│   └── llm_client.py        # LLM 客户端
├── agents/                   # 智能体配置（运行时）
├── agent_data/              # 智能体数据（运行时）
├── bayi_config.yaml.example # 配置模板
└── run.py                   # 启动脚本
```

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📄 许可

MIT License

## 🙏 致谢

- OpenClaw - 智能体框架基础
- Agnes AI - 模型 API 支持
- 飞书开放平台 - 渠道集成

---

**注意**：本项目仅供学习和研究使用，请勿用于生产环境的安全关键场景。
