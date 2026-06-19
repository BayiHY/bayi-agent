# Bayi-Agent 部署指南

## 部署方式

### 方式 1: 独立部署（推荐）

适合：作为独立微服务运行，有自己的飞书机器人。

#### 1.1 安装依赖

```bash
cd /root/.openclaw/workspace/bayi-agent
pip3 install -r requirements.txt
```

#### 1.2 配置飞书机器人

编辑 `bayi_config.yaml`：

```yaml
feishu:
  app_id: "your_app_id_here"
  app_secret: "your_app_secret_here"
  event_callback: "/webhook/feishu"
```

#### 1.3 启动服务

**方式 A: 直接运行**

```bash
python3 run.py --webhook --port 8765
```

**方式 B: systemd 服务（推荐生产环境）**

```bash
# 安装服务
sudo cp /root/.openclaw/workspace/bayi-agent/bayi-agent.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable bayi-agent
sudo systemctl start bayi-agent

# 查看状态
sudo systemctl status bayi-agent

# 查看日志
journalctl -u bayi-agent -f
```

#### 1.4 配置飞书事件订阅

在飞书开放平台：

1. 进入应用 → 事件订阅
2. 配置请求地址：`http://你的公网IP:8765/webhook/feishu`
3. 订阅事件：`im.message.receive_v1`

**如果需要公网地址，可以使用 ngrok：**

```bash
ngrok http 8765
# 得到类似: https://abc123.ngrok.io
# 配置飞书: https://abc123.ngrok.io/webhook/feishu
```

---

### 方式 2: OpenClaw 集成

适合：在 OpenClaw 中直接使用 bayi-agent 功能。

#### 2.1 作为 Python 模块使用

```python
from bayi_agent.openclaw_adapter import bayi_chat, bayi_status

# 对话
result = await bayi_chat("分析系统架构", "user-123")
print(result)

# 查询状态
status = await bayi_status("task-123")
print(status)
```

#### 2.2 作为子智能体调用

```python
# 在 OpenClaw 中通过 sessions_spawn 调用
result = await sessions_spawn(
    agentId="bayi-agent",
    task="分析系统架构设计方案",
    context="fork"  # 共享当前上下文
)
```

---

## 健康检查

独立部署后，可以访问健康检查接口：

```bash
curl http://localhost:8765/health
```

返回：
```json
{
  "status": "ok",
  "queue_length": 5,
  "processing": "task-123"
}
```

---

## 监控和日志

### 查看日志

**systemd 服务日志：**
```bash
journalctl -u bayi-agent -f
```

**任务日志：**
```bash
tail -f /tmp/bayi-tasks/task-123.log
```

### 监控队列状态

```bash
# 通过 API
curl http://localhost:8765/queue/status

# 或直接查询 SQLite
sqlite3 /tmp/bayi-tasks/queue.db "SELECT * FROM tasks WHERE status='queued'"
```

---

## 性能指标

| 指标 | 目标 | 说明 |
|------|------|------|
| 入口 LLM 响应 | < 1s | 意图分类 + 口语回复 |
| 简单任务执行 | < 3s | 立即执行 |
| 队列入队延迟 | < 10ms | 任务入队时间 |
| 最大队列长度 | 100 | 防止内存溢出 |
| Worker 数量 | 3 | 并行处理任务 |

---

## 故障排查

### 服务无法启动

```bash
# 检查端口占用
lsof -i:8765

# 检查依赖
pip3 check

# 手动运行查看错误
python3 run.py --webhook --port 8765
```

### 飞书消息无响应

1. 检查飞书事件订阅配置
2. 检查 App Secret 是否正确
3. 查看日志：`journalctl -u bayi-agent -n 50`
4. 测试 webhook：

```bash
curl -X POST http://localhost:8765/webhook/feishu \
  -H "Content-Type: application/json" \
  -d '{"type":"url_verification","challenge":"test"}'
```

### 队列积压

```bash
# 查看队列状态
curl http://localhost:8765/health

# 清理已完成任务
python3 -c "
import asyncio
from core.queue import DecisionTaskQueue

async def clear():
    q = DecisionTaskQueue()
    await q.clear_completed()
    print('已清理完成')

asyncio.run(clear())
"
```

---

## 开机自启

```bash
sudo systemctl enable bayi-agent
sudo systemctl start bayi-agent
```

---

## 更新和重启

```bash
# 更新代码
cd /root/.openclaw/workspace/bayi-agent
git pull  # 如果使用 git

# 重启服务
sudo systemctl restart bayi-agent

# 查看状态
sudo systemctl status bayi-agent
```
