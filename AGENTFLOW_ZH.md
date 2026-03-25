# AgentFlow 中文文档

AgentFlow 是一个基于标签驱动的 GitHub 代理编排服务。它能够自动监控 GitHub 仓库中带有特定标签的任务，并使用本地的代码生成代理（如 Codex、Claude Code、OpenCode 等）来执行实现、审查和修复工作流。

## 用户使用文档

### 功能概述

- **GitHub 任务同步**：通过 `gh` CLI 轮询配置的 GitHub 仓库，同步带有 `agent-issue`、`agent-reviewable`、`agent-changed` 标签的任务到本地 SQLite 数据库
- **本地代理执行**：通过 PTY 运行本地代码生成代理 CLI，支持实现（implement）、审查（review）、修复（fix）三种工作模式
- **生命周期管理**：任务状态自动流转：`agent-issue` → `agent-reviewable` → `agent-approved` 或 `agent-changed` → `agent-reviewable`
- **Web 看板**：提供 FastAPI Web 界面，可视化查看任务状态和执行历史
- **CLI 工具**：提供命令行工具查看任务看板、运行记录和详细输出

### 系统要求

- Python 3.9+
- [uv](https://github.com/astral-sh/uv)（Python 包管理器和安装器）
- [GitHub CLI (gh)](https://cli.github.com/) 已通过 `gh auth login` 认证
- 至少一个可用的代码生成代理（如 [Codex](https://github.com/sundy-li/codex)、[Claude Code](https://github.com/anthropics/claude-code)、[OpenCode](https://github.com/sundy-li/opencode) 等）

### 快速开始

#### 1. 安装依赖

```bash
uv sync --dev
```

#### 2. 配置 AgentFlow

创建配置文件目录并复制示例配置：

```bash
mkdir -p config
cp config/agentflow.example.yaml config/agentflow.yaml
```

编辑 `config/agentflow.yaml`，配置 GitHub 仓库和代码生成代理：

```yaml
# 数据库配置
database:
  path: data/agentflow.db

# 调度器配置
scheduler:
  enabled: true
  poll_interval_seconds: 300  # 轮询间隔（秒）
  max_parallel_tasks: 4       # 最大并行任务数
  review_latency_hours: 0     # 审查延迟时间（小时）

# 代码生成代理配置
coding_agents:
  default:
    kind: codex
    command: codex
    args: ["--dangerously-bypass-approvals-and-sandbox"]
    timeout_seconds: 1800
  claude:
    kind: claude_code
    command: claude
    args: [--output-format, text]
    timeout_seconds: 1800
  opencode:
    kind: opencode
    command: opencode
    args: []
    timeout_seconds: 1800

# 任务类型与代理映射
task_agents:
  implement: claude    # 实现任务使用 Claude 代理
  fix: opencode        # 修复任务使用 OpenCode 代理
  review: default      # 审查任务使用默认代理

# 运行日志目录
run_logs_dir: data/runs

# GitHub 仓库配置
repos:
  - name: demo
    full_name: sundy-li/agentflow      # 上游仓库
    forked: your-github-user/agentflow # 你的 fork 仓库（用于推送）
    workspace: /absolute/path/to/your/worktree  # 本地工作目录
    default_branch: main
    enabled: true
```

**关键配置说明**：

- `full_name`：监控的上游 GitHub 仓库（格式：`owner/repo`）
- `forked`：你的 fork 仓库，用于推送代码更改
- `workspace`：本地工作目录的绝对路径，用于存放 git 工作树
- `coding_agents`：定义可用的代码生成代理配置
- `task_agents`：为不同任务类型指定使用的代理

#### 3. 启动服务

```bash
AGENTFLOW_CONFIG=config/agentflow.yaml uv run uvicorn app.main:create_app --factory --reload
```

服务启动后，可以通过以下 URL 访问：

- 健康检查：`http://127.0.0.1:8000/healthz`
- 任务看板：`http://127.0.0.1:8000/board`

#### 4. 使用 CLI 工具

查看任务看板：

```bash
uv run python -m app.cli board --config config/agentflow.yaml
```

查看运行记录：

```bash
uv run python -m app.cli runs --config config/agentflow.yaml
```

查看特定运行输出：

```bash
uv run python -m app.cli inspect <run_id> --config config/agentflow.yaml
```

实时跟踪运行输出：

```bash
uv run python -m app.cli inspect <run_id> --follow --config config/agentflow.yaml
```

### 工作流程

1. **任务发现**：AgentFlow 定期轮询配置的 GitHub 仓库，查找带有 `agent-issue` 标签的 Issue 或 Pull Request
2. **任务同步**：找到的任务被同步到本地 SQLite 数据库
3. **代理执行**：根据任务类型（实现、修复、审查）调用相应的代码生成代理
4. **状态流转**：任务完成后，AgentFlow 会自动更新 GitHub 上的标签：
   - 实现任务：`agent-issue` → `agent-reviewable`
   - 审查通过：`agent-reviewable` → `agent-approved`
   - 需要修改：`agent-reviewable` → `agent-changed`
   - 修复完成：`agent-changed` → `agent-reviewable`
5. **结果记录**：所有运行记录和输出都保存在 `data/runs` 目录和数据库中

### 支持的代理类型

- **codex**：基于 Codex 的代码生成代理
- **claude_code**：Claude Code CLI 代理
- **opencode**：OpenCode 代理

### 注意事项

1. **GitHub 认证**：确保 `gh` CLI 已正确认证（运行 `gh auth status` 验证）
2. **代理可用性**：配置的代码生成代理必须在系统的 `PATH` 中可用
3. **工作目录权限**：确保配置的 `workspace` 目录存在且可写
4. **网络连接**：需要能够访问 GitHub API

## 开发与部署文档

### 项目结构

```
agentflow/
├── app/                    # 应用程序代码
│   ├── api/               # API 路由
│   ├── constants.py       # 常量定义
│   ├── config.py          # 配置模型和加载
│   ├── db.py              # 数据库连接和迁移
│   ├── main.py            # FastAPI 应用工厂
│   ├── cli.py             # 命令行工具
│   ├── repository.py      # 数据访问层
│   ├── services/          # 业务逻辑服务
│   └── ui/                # Web 界面模板和静态文件
├── config/                # 配置文件
│   └── agentflow.example.yaml  # 示例配置
├── docs/                  # 文档
├── migrations/            # 数据库迁移脚本
├── prompts/               # 代理提示词模板
├── tests/                 # 测试代码
├── pyproject.toml        # 项目依赖和配置
└── README.md             # 项目说明
```

### 开发环境设置

#### 1. 克隆仓库

```bash
git clone <repository-url>
cd agentflow
```

#### 2. 安装开发依赖

```bash
uv sync --dev
```

#### 3. 配置开发环境

复制示例配置并修改：

```bash
cp config/agentflow.example.yaml config/agentflow.yaml
# 编辑 config/agentflow.yaml 配置本地环境
```

#### 4. 运行测试

```bash
uv run pytest -v
```

运行特定测试文件：

```bash
uv run pytest tests/unit/test_config.py -v
```

#### 5. 启动开发服务器

```bash
AGENTFLOW_CONFIG=config/agentflow.yaml uv run uvicorn app.main:create_app --factory --reload
```

### 核心组件说明

#### 配置系统 (`app/config.py`)

基于 Pydantic 的配置管理系统，支持 YAML 配置文件和环境变量。主要配置类：

- `AppSettings`：根配置
- `DatabaseSettings`：数据库配置
- `SchedulerSettings`：调度器配置
- `CodingAgentSettings`：代码生成代理配置
- `RepoSettings`：GitHub 仓库配置

#### 数据库层 (`app/db.py`, `app/repository.py`)

使用 SQLite 数据库存储任务和运行记录。包含数据库迁移和简单的数据访问层。

#### 调度器服务 (`app/services/scheduler.py`)

基于 APScheduler 的定时任务调度器，负责：
- 定期同步 GitHub 任务
- 管理代理执行的并行度
- 处理任务状态流转

#### 代码生成代理运行器 (`app/services/coding_agent_runner.py`)

负责启动和管理本地代码生成代理进程，处理超时和输出收集。

#### GitHub 客户端 (`app/services/gh_client.py`)

封装 `gh` CLI 命令，提供 GitHub API 访问能力。

### 扩展与定制

#### 添加新的代码生成代理

1. 在 `app/config.py` 的 `CodingAgentSettings` 类的 `kind` 字段中添加新的代理类型
2. 在 `app/services/coding_agent_runner.py` 中实现对新代理类型的支持
3. 更新配置文件示例中的 `coding_agents` 部分

#### 自定义任务状态流转

修改 `app/services/worker_service.py` 中的状态转换逻辑，适应不同的工作流程需求。

#### 添加新的 API 端点

在 `app/api/` 目录下创建新的路由模块，并在 `app/main.py` 中注册。

### 生产部署建议

#### 1. 使用生产级 ASGI 服务器

```bash
# 使用 gunicorn 与 uvicorn worker
gunicorn app.main:create_app --factory --workers 4 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

#### 2. 环境变量配置

使用环境变量替代配置文件：

```bash
export AGENTFLOW_CONFIG=/path/to/config/agentflow.yaml
export DATABASE_PATH=/var/lib/agentflow/data/agentflow.db
export RUN_LOGS_DIR=/var/log/agentflow/runs
```

#### 3. 进程管理

使用 systemd 或 supervisor 管理 AgentFlow 服务进程。

**systemd 服务示例** (`/etc/systemd/system/agentflow.service`)：

```ini
[Unit]
Description=AgentFlow GitHub Agent Orchestration Service
After=network.target

[Service]
Type=simple
User=agentflow
WorkingDirectory=/opt/agentflow
Environment="AGENTFLOW_CONFIG=/opt/agentflow/config/agentflow.yaml"
Environment="PATH=/opt/agentflow/.venv/bin:/usr/local/bin:/usr/bin:/bin"
ExecStart=/opt/agentflow/.venv/bin/uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

#### 4. 日志管理

AgentFlow 使用 Python 标准 logging 模块。可以通过配置日志处理器实现：
- 文件日志轮转
- 系统日志集成
- 日志聚合服务

#### 5. 监控与告警

建议监控：
- 服务健康状态 (`/healthz` 端点)
- 数据库大小和连接数
- 代理执行成功率
- GitHub API 调用频率

### 故障排除

#### 常见问题

1. **`gh` CLI 认证失败**
   ```
   Error: gh not authenticated. Run `gh auth login` first.
   ```
   解决方案：运行 `gh auth login` 完成认证。

2. **代码生成代理命令未找到**
   ```
   FileNotFoundError: [Errno 2] No such file or directory: 'codex'
   ```
   解决方案：确保代理 CLI 已安装并在 `PATH` 中，或在配置中指定完整路径。

3. **GitHub API 速率限制**
   ```
   API rate limit exceeded
   ```
   解决方案：减少轮询频率 (`poll_interval_seconds`)，或使用 GitHub 令牌提高限制。

4. **数据库锁定**
   ```
   sqlite3.OperationalError: database is locked
   ```
   解决方案：确保没有多个进程同时访问数据库，或考虑使用 PostgreSQL。

#### 调试技巧

启用详细日志：

```python
# 在 config/agentflow.yaml 中添加
logging:
  level: DEBUG
```

查看运行日志：

```bash
tail -f data/runs/*.log
```

检查数据库状态：

```bash
sqlite3 data/agentflow.db ".tables"
sqlite3 data/agentflow.db "SELECT * FROM tasks LIMIT 5;"
```

### 贡献指南

1. Fork 仓库并创建特性分支
2. 遵循现有代码风格
3. 添加或更新测试
4. 确保所有测试通过
5. 提交清晰的提交信息
6. 创建 Pull Request

### 许可证

本项目采用开源许可证，具体信息请查看项目根目录的 LICENSE 文件。

### 获取帮助

- 查看项目 [README](README.md) 获取基础信息
- 查看 [AGENTS.md](AGENTS.md) 了解代理配置详情
- 在 GitHub Issues 中报告问题或提出功能请求
- 参考示例配置和测试代码了解使用方法