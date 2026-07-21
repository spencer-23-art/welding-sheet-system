# 焊接质量与进度驾驶舱联动平台

本项目把腾讯在线表格同步到本地 PostgreSQL，并由 FastAPI 向数据大屏和管理端提供统计接口。大屏只读取本地缓存，不会在每次展示时直接调用腾讯文档 API。

## 数据链路

```text
腾讯在线表格
  -> 定时/手动/签名 Webhook 同步
  -> welding_records 本地结构化缓存
  -> FastAPI 统计接口 + WebSocket 通知
  -> 数据大屏 / Vue 管理端
```

当前主要能力：

- 按腾讯文档表头识别焊接日期、探伤日期和一至三次探伤结果。
- 全量校准与增量轮询并存，支持 7:00–24:00 自动调用窗口。
- 焊接进度、焊工质量、探伤闭环、底片审核和审核问题分析。
- 当日腾讯 API 调用次数统计。
- JWT 登录、RBAC 权限和项目级数据范围。
- 腾讯 access token 加密落库；API 只返回是否已配置，不返回原文。

## 目录

```text
backend/
  app/
    core/          配置、数据库和 JWT
    models/        用户、文档、焊接记录、系统配置
    routers/       认证、文档、统计、腾讯同步接口
    services/      数据解析、统计、腾讯客户端和轮询器
  scripts/         一次性数据迁移脚本
  test_*.py        独立回归测试
frontend/
  src/             Vue 3 管理端
  bigscreen-assets 数据大屏静态入口及增强脚本
  nginx.conf       SPA、API、WebSocket 反向代理及安全响应头
docker-compose.yml PostgreSQL、FastAPI 和 Nginx 编排
```

## 本地开发

后端使用 Python 3.11+：

```powershell
cd backend
python -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

前端使用 Node.js 20+：

```powershell
cd frontend
npm ci
npm run dev
```

开发服务器默认只监听 `127.0.0.1`。确需局域网调试时，可显式运行 `npm run dev -- --host 0.0.0.0`。

## Docker 部署

部署前至少设置以下环境变量，禁止沿用示例默认值：

```text
POSTGRES_PASSWORD=<随机强密码>
JWT_SECRET=<至少 32 字节的随机值>
SUPERADMIN_PASSWORD=<随机强密码>
```

然后执行：

```bash
docker compose up -d --build
```

服务端口由当前编排映射为 `80` 和 `9000`。生产环境应在防火墙中只开放实际使用的端口，并在 `CORS_ORIGINS` 中配置明确来源。

注意：`JWT_SECRET` 同时用于派生腾讯 Token 的落库加密密钥。变更该值后，已有腾讯 Token 无法解密，需要在设置中重新录入。

## 测试与检查

在 `backend` 目录逐个运行全部回归测试：

```powershell
Get-ChildItem test_*.py | ForEach-Object { python $_.FullName }
```

前端检查：

```powershell
cd frontend
npx vue-tsc --noEmit
npm run build
npm audit --omit=dev
```

后端静态检查和依赖审计：

```powershell
ruff check backend
pip-audit -r backend/requirements.txt
```

Excel 历史迁移工具不进入生产镜像。需要运行 `backend/scripts/migrate_excel.py` 时，另外安装：

```powershell
pip install -r backend/requirements-migration.txt
```

## 安全边界

- 不要把 `.env`、腾讯 Token、数据库备份或部署压缩包提交到 Git。
- Nginx 已设置 CSP、禁止 MIME 嗅探、同源嵌套和浏览器权限限制。
- 使用通配 CORS 时不会开启跨站凭据；生产环境仍建议配置明确来源。
- 腾讯 Webhook 必须配置腾讯公钥并通过签名校验。
- 公网注册、腾讯配置写入权限及文档数据隔离仍需按实际账号体系进一步收紧，详见代码审计报告。
