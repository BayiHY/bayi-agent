# Bayi-Agent 配置说明

本文档说明 Bayi-Agent 的配置文件结构和敏感信息处理方式。

## 快速开始

1. 复制配置模板：
   ```bash
   cp bayi_config.yaml.example bayi_config.yaml
   ```

2. 编辑 `bayi_config.yaml`，填入你的实际 API 密钥和配置

3. 确保 `bayi_config.yaml` 不会被提交到版本控制（已在 `.gitignore` 中排除）

## 配置文件结构

### 1. 飞书渠道配置

```yaml
feishu:
  app_id: "cli_xxx"           # 飞书应用 ID
  app_secret: "xxx"           # 飞书应用密钥
  encrypt_key: ""             # 加密密钥（可选）
  event_callback: "/webhook/feishu"
```

**获取方式**：
- 访问 [飞书开放平台](https://open.feishu.cn/)
- 创建企业自建应用
- 在「凭证与基础信息」页面获取 App ID 和 App Secret

### 2. Tavily API 配置（网络搜索）

```yaml
tavily:
  api_key: "your_tavily_key_here"  # Tavily API 密钥
  api_base: "https://api.tavily.com/search"
```

**获取方式**：
- 访问 [Tavily](https://tavily.com/)
- 注册账号并创建 API Key

### 3. 模型配置

Bayi-Agent 使用多个模型协同工作：

#### 入口模型（entry_model）
- **用途**：意图分类 + 口语回复
- **建议模型**：agnes-2.0-flash（快速响应）
- **配置项**：
  ```yaml
  entry_model:
    name: "agnes-2.0-flash"
    api_base: "https://apihub.agnes-ai.com/v1"
    api_key: "your_key"
    temperature: 0.3          # 低温度保证一致性
    max_tokens: 500           # 短回复足够
    timeout: 30
  ```

#### 决策模型（decision_model）
- **用途**：复杂任务分析、子任务拆分
- **建议模型**：GLM-5、GPT-4
- **配置项**：
  ```yaml
  decision_model:
    name: "GLM-5"
    api_base: "https://modelservice.jdcloud.com/coding/openai/v1"
    api_key: "your_key"
    temperature: 0.7          # 中等温度平衡创造性和准确性
    max_tokens: 4000
    timeout: 60
  ```

#### 模型池（model_pool）
用于模型切换和降级策略：

```yaml
model_pool:
  primary:     # 主力模型（代码执行、数据分析）
    name: "GLM-5"
    temperature: 0.7
    max_tokens: 4000
  
  fallback_1:  # 备用模型（网络搜索、文本生成）
    name: "agnes-2.0-flash"
    temperature: 0.5
    max_tokens: 3000
  
  fallback_2:  # 简单任务模型
    name: "agnes-2.0-flash"
    temperature: 0.3
    max_tokens: 2000
```

### 4. 任务路由配置

定义不同任务类型使用的模型：

```yaml
model_routing:
  code_execution: "primary"      # 代码执行 → 主力模型
  web_search: "fallback_1"       # 网络搜索 → 备用模型1
  data_analysis: "primary"       # 数据分析 → 主力模型
  text_generation: "fallback_1"  # 文本生成 → 备用模型1
  simple_query: "fallback_2"     # 简单查询 → 备用模型2
```

### 5. 队列配置

```yaml
queue:
  max_size: 100              # 队列最大容量
  max_workers: 3             # 最大并发工作线程
  db_path: "/tmp/bayi-tasks/queue.db"
  log_dir: "/tmp/bayi-tasks/"
```

### 6. 智能体配置

```yaml
agents:
  max_temporary: 5           # 最大临时智能体数量
  specialized:               # 专业智能体配置
    architect:
      skills: ["architecture-analysis", "design-patterns"]
      tools: ["read_file", "search_web", "draw_diagram"]
      description: "架构分析专家"
    # ... 其他智能体
```

## 敏感信息保护

### 已排除的文件（.gitignore）

以下文件包含敏感信息，已被 `.gitignore` 排除：

- `bayi_config.yaml` - 主配置文件（包含所有 API 密钥）
- `*.secret.yaml` / `*.secret.json` - 其他秘密配置
- `.env` / `.env.*` - 环境变量文件
- `agent_data/` - 运行时智能体数据
- `agents/*.json` - 智能体配置（可能包含敏感信息）
- `model_performance.json` - 模型性能数据

### 硬编码 API Key 处理

代码中的硬编码 API Key 已移除或改为从环境变量读取：

- `core/tools.py` - Tavily API Key 改为 `TAVILY_API_KEY` 环境变量
- 其他 API Key 从 `bayi_config.yaml` 读取

### 环境变量方式（推荐）

可以通过环境变量覆盖配置：

```bash
export TAVILY_API_KEY="your_tavily_key_here"
export FEISHU_APP_ID="cli_xxx"
export FEISHU_APP_SECRET="xxx"
export ENTRY_MODEL_API_KEY="sk-xxx"
export DECISION_MODEL_API_KEY="pk-xxx"
```

## 配置验证

启动前检查配置：

```bash
# 检查配置文件是否存在
ls -la bayi_config.yaml

# 验证 YAML 格式
python3 -c "import yaml; yaml.safe_load(open('bayi_config.yaml'))"

# 检查必需的配置项
python3 -c "
import yaml
config = yaml.safe_load(open('bayi_config.yaml'))
required = ['feishu', 'entry_model', 'decision_model']
missing = [k for k in required if k not in config]
if missing:
    print(f'缺少配置项: {missing}')
    exit(1)
print('✅ 配置验证通过')
"
```

## 故障排查

### 配置文件未找到

```
错误: bayi_config.yaml 不存在
解决: cp bayi_config.yaml.example bayi_config.yaml
```

### API Key 无效

```
错误: 401 Unauthorized
解决: 检查对应的 api_key 是否正确配置
```

### 模型连接失败

```
错误: Connection timeout
解决: 
1. 检查 api_base 是否正确
2. 检查网络连接
3. 增加 timeout 配置值
```

## 相关文档

- [README.md](README.md) - 项目概述
- [DEPLOYMENT.md](DEPLOYMENT.md) - 部署指南
- [LOG_PATHS.md](LOG_PATHS.md) - 日志路径说明
