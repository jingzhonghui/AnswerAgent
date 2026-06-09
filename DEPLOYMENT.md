# AnswerAgent 部署手册

支持 **服务部署**（直接部署在 Linux 服务器）和 **容器部署**（Docker）两种模式。

---

## 目录

- [环境要求](#环境要求)
- [通用准备](#通用准备)
- [模式一：服务部署](#模式一服务部署)
- [模式二：容器部署](#模式二容器部署)
- [配置参考](#配置参考)
- [维护与排障](#维护与排障)

---

## 环境要求

| 组件 | 服务部署 | 容器部署 |
|------|----------|----------|
| Python | 3.10+ | — |
| Node.js | 18+（仅构建需要） | — |
| Docker | — | 24+ |
| Docker Compose | — | V2 |
| Nginx | 1.24+（反向代理） | — |

---

## 通用准备

### 1. 获取代码

```bash
git clone <仓库地址> answeragent
cd answeragent
```

### 2. 配置环境变量

```bash
cd backend
cp .env.example .env
# 编辑 .env，填入必要的配置
vi .env
```

最小配置需要以下项：

```ini
# LLM 提供商选择：openai | anthropic
LLM_PROVIDER=openai

# API 密钥
API_KEY=sk-your-key-here

# JWT 密钥（务必修改为随机字符串）
JWT_SECRET_KEY=<生成一个随机字符串，建议 32 位以上>
```

完整配置项见 [配置参考](#配置参考)。

### 3. 知识库准备

将你的知识库文档放入 `backend/knowledge/` 目录，每个知识库一个子目录：

```bash
backend/knowledge/
├── 产品文档/
│   ├── 索引.md
│   ├── overview.md
│   └── api.md
└── 技术规范/
    ├── 索引.md
    ├── architecture.md
    └── src/
        └── example.py
```

详细知识库结构说明见 [README.md](README.md#知识库结构)。

---

## 模式一：服务部署

### 架构

```
                          Nginx (:80/:443)
                         /                \
    /api/* 反向代理到 :8765              / 静态文件（前端构建产物）
               |                               |
        后端 uvicorn (:8765)            frontend/dist/
```

### 1. 后端部署

#### 1.1 安装依赖

```bash
cd backend

# 创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# （可选）安装生产级 ASGI 服务器
pip install gunicorn
```

#### 1.2 测试启动

```bash
# 确保在虚拟环境中
python -m app.main
```

访问 `http://<服务器IP>:8765/api/health` 应返回 `{"status": "ok"}`。

确认无误后按 `Ctrl+C` 停止。

#### 1.3 配置 Systemd 服务

创建 `/etc/systemd/system/answeragent.service`：

```ini
[Unit]
Description=AnswerAgent Backend API
After=network.target

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=/opt/answeragent/backend
ExecStart=/opt/answeragent/backend/.venv/bin/python -m app.main
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

# 安全限制
NoNewPrivileges=true
ProtectHome=true
ProtectSystem=full
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

> **注意**：替换 `/opt/answeragent` 为实际部署路径。如果使用 `ProtectSystem=full`，请确保 `backend/data/` 目录可写，或调整该选项。

启动服务：

```bash
sudo systemctl daemon-reload
sudo systemctl enable answeragent
sudo systemctl start answeragent
sudo systemctl status answeragent
```

#### 1.4 验证

```bash
curl http://localhost:8765/api/health
# 应返回: {"status":"ok","message":"AnswerAgent is running"}
```

### 2. 前端构建

```bash
cd frontend

# 安装依赖
npm install

# 构建生产版本
npm run build
```

构建产物在 `frontend/dist/` 目录。

> **说明**：构建后 Node.js 和 npm 不再需要，仅用 Nginx 托管静态文件。

### 3. Nginx 反向代理配置

创建 `/etc/nginx/sites-available/answeragent`：

```nginx
server {
    listen 80;
    server_name your-domain.com;  # 替换为你的域名或 IP

    # 前端静态文件
    root /opt/answeragent/frontend/dist;
    index index.html;

    # Gzip 压缩
    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml text/markdown;

    # API 反向代理
    location /api/ {
        proxy_pass http://127.0.0.1:8765;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # SSE 必需：禁用缓冲
        proxy_buffering off;
        proxy_cache off;
        chunked_transfer_encoding on;
    }

    # SPA 路由：所有非文件路径返回 index.html
    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

启用站点：

```bash
sudo ln -s /etc/nginx/sites-available/answeragent /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### 4. 更新 CORS 配置（生产环境）

`backend/app/main.py` 中的 CORS 配置当前仅允许开发环境。生产环境需修改：

```python
# 修改前
allow_origins=["http://localhost:5173"]

# 修改后 — 允许你的域名
allow_origins=[
    "https://your-domain.com",
    "http://your-domain.com",
]
```

修改后重启后端服务：

```bash
sudo systemctl restart answeragent
```

### 5. 完整部署流程

```bash
# 1. 部署后端
cd /opt/answeragent/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
vi .env    # 填入 API key 和 JWT secret

# 2. 启动后端验证
python -m app.main &
curl http://localhost:8765/api/health
kill %1

# 3. 安装 systemd 服务（见上文）

# 4. 构建前端
cd /opt/answeragent/frontend
npm install
npm run build

# 5. 配置 Nginx（见上文）

# 6. 重启服务
sudo systemctl restart answeragent
sudo systemctl reload nginx
```

---

## 模式二：容器部署

### 架构

```
         Nginx 容器 (:80)       后端容器 (:8765)
    ┌──────────────────┐    ┌──────────────────┐
    │  frontend/dist/   │    │  uvicorn         │
    │  (静态文件)        │◄──►│  FastAPI         │
    │  /api/* → 后端     │    │  SQLite + JSON   │
    └──────────────────┘    └──────┬───────────┘
                                   │
                          ┌────────┴───────────┐
                          │  Volumes (持久化)    │
                          │  - data/           │
                          │  - knowledge/      │
                          └────────────────────┘
```

### 1. 后端 Dockerfile

`backend/Dockerfile`：

```dockerfile
# ---- Build stage ----
FROM python:3.11-slim AS builder

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ---- Runtime stage ----
FROM python:3.11-slim

WORKDIR /app

# 从构建阶段复制依赖
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# 复制代码
COPY app/ app/

# 运行时目录（由 volume 挂载或入口脚本创建）
RUN mkdir -p /app/data /app/knowledge

EXPOSE 8765

# 健康检查
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8765/api/health')" || exit 1

CMD ["python", "-m", "app.main"]
```

### 2. 前端 Dockerfile

`frontend/Dockerfile`：

```dockerfile
# ---- Build stage ----
FROM node:20-alpine AS builder

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

# ---- Runtime stage ----
FROM nginx:alpine

# 复制构建产物
COPY --from=builder /app/dist /usr/share/nginx/html

# 复制 Nginx 配置
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
```

### 3. Nginx 配置（容器版）

`frontend/nginx.conf`：

```nginx
server {
    listen 80;
    server_name _;

    root /usr/share/nginx/html;
    index index.html;

    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml text/markdown;

    location /api/ {
        proxy_pass http://backend:8765;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # SSE：禁用缓冲
        proxy_buffering off;
        proxy_cache off;
        chunked_transfer_encoding on;
    }

    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

> 注意：`http://backend:8765` 中的 `backend` 是 docker-compose 中定义的服务名。

### 4. Docker Compose

`docker-compose.yml`（项目根目录）：

```yaml
version: "3.8"

services:
  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    container_name: answeragent-backend
    restart: unless-stopped
    ports:
      - "127.0.0.1:8765:8765"
    env_file:
      - ./backend/.env
    volumes:
      # 数据持久化（SQLite + 对话 JSON）
      - answeragent-data:/app/data
      # 知识库挂载（只读）
      - ./backend/knowledge:/app/knowledge:ro
    environment:
      - KNOWLEDGE_PATH=/app/knowledge
      - DATA_PATH=/app/data/conversations
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; exit(0 if urllib.request.urlopen('http://localhost:8765/api/health').status == 200 else 1)"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 15s

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    container_name: answeragent-frontend
    restart: unless-stopped
    ports:
      - "80:80"
    depends_on:
      - backend

volumes:
  answeragent-data:
    driver: local
```

### 5. 配置 CORS（容器部署）

容器部署时前后端同域（均由 Nginx 提供），无需修改 CORS 配置。但如果需要将后端独立暴露，修改 `backend/app/core/config.py` 或通过环境变量注入允许的来源。

### 6. 构建与启动

```bash
# 首次构建
docker compose build --no-cache

# 启动
docker compose up -d

# 查看日志
docker compose logs -f

# 检查健康状态
curl http://localhost/api/health

# 停止
docker compose down

# 更新后重新构建
docker compose build
docker compose up -d
```

### 7. 生产环境 Docker Compose 调整

```yaml
# docker-compose.prod.yml（可选）
services:
  backend:
    # 限制资源
    deploy:
      resources:
        limits:
          memory: 2G
        reservations:
          memory: 512M
    # 日志轮转
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"

  frontend:
    deploy:
      resources:
        limits:
          memory: 256M
        reservations:
          memory: 128M
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

使用：

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

---

## 配置参考

### 环境变量清单

| 变量 | 必需 | 默认值 | 说明 |
|------|------|--------|------|
| `LLM_PROVIDER` | 是 | `openai` | LLM 提供商：`openai` 或 `anthropic` |
| `API_KEY` | **是** | — | API 密钥（OpenAI 或 Anthropic，由 `LLM_PROVIDER` 决定协议） |
| `BASE_URL` | 否 | — | API 地址（OpenAI 兼容 API 如 DeepSeek 需填写；Anthropic 可留空） |
| `MODEL` | 否 | `gpt-4o` | 模型名称 |
| `KNOWLEDGE_PATH` | 否 | `./knowledge` | 知识库目录路径 |
| `DATA_PATH` | 否 | `./data/conversations` | 对话 JSON 文件存储路径 |
| `HISTORY_WINDOW` | 否 | `10` | 保留的对话历史轮数 |
| `JWT_SECRET_KEY` | **是** | — | JWT 签名密钥（生产环境务必修改） |
| `JWT_ALGORITHM` | 否 | `HS256` | JWT 签名算法 |
| `JWT_EXPIRE_MINUTES` | 否 | `1440` | JWT 过期时间（分钟） |
| `DEEP_MODEL_ENABLED` | 否 | `true` | 是否启用深度思考（推理）模型 |
| `DEEP_LLM_PROVIDER` | 否 | — | 推理模型 provider，空则复用 `LLM_PROVIDER` |
| `DEEP_API_KEY` | 否 | — | 推理模型 API key，空则复用 `API_KEY` |
| `DEEP_BASE_URL` | 否 | — | 推理模型 API 地址，空则复用 `BASE_URL` |
| `DEEP_MODEL` | 否 | `o1-mini` | 推理模型名称 |
| `DEEP_TEMPERATURE` | 否 | `0.1` | 推理模型采样温度 |

### 端口映射

| 服务 | 默认端口 | 说明 |
|------|----------|------|
| 后端 uvicorn | 8765 | FastAPI 应用服务端口 |
| 前端 Nginx | 80 | 容器部署的 HTTP 端口 |

### 数据目录

| 路径 | 内容 | 持久化要求 |
|------|------|-----------|
| `backend/data/answeragent.db` | 用户账户 + 对话元数据（SQLite） | **必须持久化** |
| `backend/data/conversations/*.json` | 对话消息内容 | **必须持久化** |
| `backend/knowledge/` | 知识库文档 | 建议只读挂载 |

---

## 维护与排障

### 查看日志

**服务部署：**

```bash
# 后端日志
sudo journalctl -u answeragent -f

# Nginx 日志
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log
```

**容器部署：**

```bash
docker compose logs -f backend
docker compose logs -f frontend
```

### 健康检查

```bash
curl http://localhost/api/health
# 预期响应：{"status":"ok","message":"AnswerAgent is running"}
```

### 数据备份

```bash
# 停止服务
sudo systemctl stop answeragent
# 或
docker compose down

# 备份数据目录
tar -czf answeragent-backup-$(date +%Y%m%d).tar.gz \
    backend/data/

# 恢复
tar -xzf answeragent-backup-20260607.tar.gz
sudo systemctl start answeragent
```

### 常见问题

**Q: 登录后页面空白或 API 返回 401？**

检查 JWT 密钥配置：`JWT_SECRET_KEY` 是否已设置且保持一致。重启后端后生效。

**Q: 流式输出卡住或不响应？**

确认 Nginx 已禁用缓冲（`proxy_buffering off`），这是 SSE 正常工作的必要条件。

**Q: 知识库匹配不到任何内容？**

1. 确认 `backend/knowledge/` 目录下有正确的知识库子目录
2. 检查 LLM API key 是否有效
3. 查看后端日志确认路由阶段是否有报错

**Q: 容器部署时数据库文件未持久化？**

确认 `docker-compose.yml` 中 `volumes` 配置正确，`answeragent-data` volume 已挂载到 `/app/data`。
