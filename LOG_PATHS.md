# Bayi-Agent 日志路径文档

> 决策层和子智能体必须清楚所有日志路径，以便排查解决问题
> 
> 更新时间：2026-06-19 12:53

## 系统级日志

### Bayi-Agent 服务日志
- **路径**: `journalctl -u bayi-agent`
- **实时查看**: `journalctl -u bayi-agent -f`
- **最近 N 条**: `journalctl -u bayi-agent -n 100`
- **时间范围**: `journalctl -u bayi-agent --since "2026-06-19 12:00:00"`
- **说明**: 包含所有 Bayi-Agent 运行日志，包括：
  - WebSocket 连接状态
  - 消息接收/发送
  - 任务入队/出队
  - 智能体创建/调度
  - 代码生成/执行
  - 重试过程

### 系统服务状态
- **路径**: `systemctl status bayi-agent`
- **说明**: 查看服务运行状态、PID、内存占用等

## 应用级日志

### Bayi-Agent 主日志
- **路径**: `/var/log/syslog` (系统日志)
- **过滤**: `grep "bayi-agent" /var/log/syslog`
- **说明**: 系统级日志，包含服务启动/停止信息

### 应用内部日志
- **路径**: 由 `run.py` 配置，当前输出到 `stdout` → journalctl
- **级别**: INFO (可调整为 DEBUG)
- **格式**: `[时间戳] 级别 | 模块名 | 消息`

## 关键日志模块

### 1. 入口网关 (gateway.py)
- **模块**: `core.gateway`
- **关键日志**:
  - 消息接收
  - 意图分类
  - 入口 LLM 响应

### 2. 决策分析器 (analyzer.py)
- **模块**: `core.analyzer`
- **关键日志**:
  - 任务分析开始
  - 子任务拆分
  - 智能体调度
  - 智能体创建（技能、工具、描述）
  - 代码生成（完整代码内容）
  - 代码执行（执行成功/失败）
  - 重试过程（第 N/M 次尝试）
  - 任务完成

### 3. 任务队列 (queue.py)
- **模块**: `core.queue`
- **关键日志**:
  - 任务入队
  - 任务出队
  - 任务状态更新

### 4. 会话管理 (session_manager.py)
- **模块**: `core.session_manager`
- **关键日志**:
  - 会话创建
  - 会话更新
  - 任务记录添加

### 5. 工具执行 (tools.py)
- **模块**: `core.tools`
- **关键日志**:
  - 工具执行开始
  - 代码执行（代码内容）
  - 执行结果（输出内容）
  - 执行失败（错误信息）

### 6. WebSocket 处理器 (feishu_ws_longpoll.py)
- **模块**: `handlers.feishu_ws_longpoll`
- **关键日志**:
  - 连接状态
  - 消息接收
  - 消息发送

## 子智能体自动化脚本日志规范

### 创建自动化脚本时
子智能体在生成自动化脚本时，必须在以下位置添加日志：

1. **脚本开始**
   ```python
   logger.info(f"开始执行自动化脚本: {脚本名称}")
   logger.info(f"参数: {参数列表}")
   ```

2. **关键步骤**
   ```python
   logger.info(f"步骤 1: {步骤描述}")
   logger.info(f"步骤 1 结果: {结果摘要}")
   ```

3. **错误处理**
   ```python
   logger.error(f"步骤 N 失败: {错误信息}")
   logger.warning(f"尝试重试...")
   ```

4. **脚本结束**
   ```python
   logger.info(f"脚本执行完成: {脚本名称}")
   logger.info(f"总耗时: {耗时} 秒")
   ```

### 日志路径
- 自动化脚本日志统一输出到 `journalctl -u bayi-agent`
- 如果脚本单独运行，输出到 `/tmp/bayi-agent-scripts/{脚本名}.log`

## 日志查询示例

### 查看最近的任务执行流程
```bash
journalctl -u bayi-agent -n 200 | grep -E "(开始分析任务|智能体调度|生成的代码|执行结果|任务完成)"
```

### 查看代码执行详情
```bash
journalctl -u bayi-agent --since "12:00:00" | grep -A 20 "生成的代码"
```

### 查看重试过程
```bash
journalctl -u bayi-agent --since "12:00:00" | grep -E "(尝试|重试|失败)"
```

### 查看智能体创建过程
```bash
journalctl -u bayi-agent --since "12:00:00" | grep -E "(智能体调度|创建.*智能体|技能|工具)"
```

### 查看错误日志
```bash
journalctl -u bayi-agent -p err
```

## 决策层日志规范

### 创建/优化智能体时必须记录
1. 智能体 ID 和类型
2. 技能列表
3. 工具列表
4. 描述信息
5. 调度原因（核心/辅助任务）

### 执行任务时必须记录
1. 任务开始/结束
2. 子任务拆分详情
3. 智能体分配详情
4. **任务类型检测**（code_execution | web_search | data_analysis | text_generation | simple_query）
5. **使用模型**（模型名称）
6. 代码生成内容
7. 执行结果
8. 重试过程（如果有）

### 模型性能记录
每次任务执行后，决策层会记录模型性能：
- 模型名称
- 任务类型
- 成功/失败次数
- 成功率

日志示例：
```
任务类型: code_execution, 使用模型: GLM-5
模型性能记录: GLM-5 | code_execution | 成功率: 85.7% (6/7)
```

### 模型切换建议
当模型表现不佳时（连续失败 2 次且成功率 < 50%），决策层会自动切换子智能体的模型。

**决策层自我优化能力**：`DOCS/经验/bayi-agent-决策层自我优化能力.md`

- 自动模型切换（子智能体）
- 失败原因分析
- 智能重试策略
- 性能数据持久化

## 相关文档

- **上下文收集机制**：`DOCS/经验/bayi-agent-上下文收集机制.md`
- **模型管理**：`bayi_config.yaml` 中的 `model_pool` 配置

## 日志级别说明

- **INFO**: 正常流程日志（默认）
- **WARNING**: 重试、跳过、降级等异常但可恢复的情况
- **ERROR**: 执行失败、未分配智能体等严重问题
- **DEBUG**: 详细调试信息（需手动开启）

## 开启 DEBUG 日志

修改 `run.py`:
```python
logging.basicConfig(
    level=logging.DEBUG,  # INFO → DEBUG
    format='[%(asctime)s] %(levelname)s | %(name)s | %(message)s'
)
```

重启服务：
```bash
systemctl restart bayi-agent
```
