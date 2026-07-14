# 焊接在线表格平台（基于 Univer 的私有化企业表格系统）

目标：打造类金山在线表格的**私有化部署**系统，数据完全存于自有服务器，支持多人在线编辑，
并提供 REST API 供数据可视化大屏调用。核心表格引擎使用 **Univer**，不自研编辑器。

技术栈：Vue3 + TypeScript + Element Plus + Univer / FastAPI + PostgreSQL + Redis + SQLAlchemy + JWT / Docker Compose + Nginx。
设计以 **2 核 2G** 服务器可运行为约束。

---

## 第一阶段交付说明（项目初始化 / Docker 环境 / 用户系统 / RBAC）

### 1. 本阶段修改/新增的文件

```
welding-sheet-system/
├── docker-compose.yml            # Postgres + Redis + Backend + Frontend 编排（含资源限制）
├── .gitignore
├── backend/
│   ├── requirements.txt          # FastAPI/SQLAlchemy/passlib/PyJWT 等
│   ├── Dockerfile                # 轻量 python:3.11-slim 镜像
│   ├── .env.example              # 环境变量示例（DATABASE_URL / JWT_SECRET 等）
│   ├── seed.py                   # 首次启动建表 + 权限/角色/超级管理员种子（幂等）
│   ├── test_smoke.py             # 阶段一冒烟测试（TestClient，全断言通过）
│   └── app/
│       ├── main.py               # FastAPI 入口（lifespan 自动 seed + CORS + 路由挂载）
│       ├── config.py             # 配置（Pydantic-Settings，DATABASE_URL 可切换 SQLite/PG）
│       ├── database.py           # SQLAlchemy 引擎/会话（连接池 pre_ping）
│       ├── security.py           # bcrypt 哈希 + JWT 签发/校验
│       ├── dependencies.py       # get_current_user / require_permissions / require_roles
│       ├── models/rbac.py        # User / Role / Permission / user_roles / role_permissions
│       ├── schemas/user.py       # Pydantic 请求响应模型
│       └── routers/
│           ├── auth.py           # 注册 / 登录 / 刷新 / 当前用户
│           ├── users.py          # 用户管理（列表/创建/修改/禁用/删除，保护超级管理员）
│           └── roles.py          # 角色与权限查询/创建
└── frontend/
    ├── package.json / vite.config.ts / tsconfig*.json / index.html
    ├── Dockerfile                # 多阶段：node 构建 -> nginx 托管
    ├── nginx.conf                # SPA + /api 反代到 backend
    └── src/
        ├── main.ts / App.vue / styles/main.css
        ├── api/client.ts         # axios + JWT 拦截 + 无感刷新（刷新锁）
        ├── store/auth.ts         # Pinia 鉴权状态（token/user/权限/角色）
        ├── router/index.ts       # 路由 + 页面级权限守卫
        ├── layout/MainLayout.vue # 顶栏 + 侧边菜单（按权限显示）
        └── views/
            ├── LoginView.vue     # 登录（用户名/手机/邮箱）
            ├── RegisterView.vue  # 开放注册（默认 employee）
            ├── DashboardView.vue # 工作台（当前阶段占位）
            └── AdminUsersView.vue# 用户管理（增删改/禁用/分配角色）
```

**权限模型（RBAC）**
- 5 个角色：`superadmin`(全部) / `admin` / `project_manager` / `employee` / `guest`
- 14 个权限编码，资源类型含 `page`(页面) / `api`(接口) / `sheet`(表格)（行级 `row` 第二阶段用）
- 已实现：**页面权限**（路由守卫 + 菜单显隐）、**API 权限**（依赖装饰器拦截）

### 2. 如何运行

#### 方式 A：本地开发（最快验证，后端用 SQLite）
```bash
# 后端
cd backend
python -m venv venv && venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env            # 默认 DATABASE_URL 即 SQLite
uvicorn app.main:app --host 0.0.0.0 --port 8000
# 打开 http://127.0.0.1:8000/docs 可见 Swagger

# 前端（另开终端）
cd frontend
npm install
npm run dev                     # http://localhost:5173 ，/api 已代理到 8000
```

#### 方式 B：Docker Compose（生产形态，PostgreSQL）
```bash
cd welding-sheet-system
# 可选：设置更强 JWT_SECRET
export JWT_SECRET=$(python -c "import secrets;print(secrets.token_hex(32))")
docker compose up -d --build
# 访问 http://<服务器IP>:8080
```
默认账号：`admin / Admin@123456`（首次启动自动 seed，请尽快修改密码与 JWT_SECRET）。

### 3. 如何测试

- **自动化冒烟**（后端，无需起服务）：
  ```bash
  cd backend && python test_smoke.py
  ```
  覆盖：健康检查、超级管理员登录、`/api/me`、角色/权限列表、开放注册、员工被 RBAC 拦截(403)、
  管理员创建用户并分配角色、禁用用户、保护超级管理员(403)。全绿。
- **接口清单（第一阶段）**：
  - `POST /api/register`、`POST /api/login`、`POST /api/refresh`、`GET /api/me`
  - `GET/POST /api/users`、`PATCH/DELETE /api/users/{id}`
  - `GET /api/roles`、`GET /api/permissions`、`POST /api/roles`
  - `GET /health`
- **前端手测**：访问 `/login` 用 admin 登录 → 工作台显示角色/权限；有 `page:admin` 权限可见
  「用户管理」菜单，可增删改用户；普通员工注册后登录看不到该菜单且调用 `/api/users` 返回 403。

---

## 第二阶段交付说明（Univer 集成 + 文档管理 + 表格保存链路）

### 1. 本阶段新增/修改的文件
（在阶段一基础上新增）
```
backend/app/
  models/document.py        # Document 表：文件夹/表格、owner、parent、project、回收站、workbook_data(JSON)
  schemas/document.py       # Document 相关 Pydantic 模型
  routers/documents.py      # 文档管理：列表/搜索/创建/重命名/软删除/恢复
  routers/sheets.py         # 表格 workbook_data 保存/加载
  seed.py                   # 增加示例文档（焊接数据库文件夹 + 管线焊口记录表）
  main.py / __init__        # 挂载新路由与模型
frontend/src/
  api/documents.ts          # 文档 API 封装（含 loadSheet/saveSheet）
  components/UniverEditor.vue  # Univer 预设模式封装（core+filter+条件格式+数据验证），30s 自动保存
  views/DocumentsView.vue   # 文档管理页（面包屑/搜索/新建/回收站/重命名/删除/恢复）
  views/SheetEditorView.vue # 表格编辑页（加载 Univer、手动保存）
  router/index.ts           # 增加 /sheets 列表 与 /sheets/:id/edit 编辑路由
  env.d.ts                  # 为 Univer 语言包补类型声明
```

### 2. 如何运行
与阶段一相同（Docker Compose 或本地 SQLite）。前端 `npm install` 已包含 Univer 依赖
（`@univerjs/presets` 及 `preset-sheets-*` 系列，统一 **0.25.1**）。

### 3. 如何测试
- **自动化冒烟（后端）**：`cd backend && python test_smoke.py`
  在阶段一 10 项基础上新增 10 项：根目录含示例文件夹、创建文件夹、创建表格、保存 workbook_data、
  加载数据一致、重命名、软删除、回收站可见并恢复、搜索、员工无 `sheet:create` 权限被拦截(403)。全绿。
- **接口清单（第二阶段）**：
  - `GET  /api/documents?parent_id=&include_deleted=&q=` 文档列表 / 搜索（跨目录）
  - `POST /api/documents` 创建（文件夹或表格）
  - `PATCH /api/documents/{id}` 重命名
  - `DELETE /api/documents/{id}` 软删除（进回收站）
  - `POST /api/documents/{id}/restore` 恢复
  - `GET  /api/sheets/{id}` 加载表格 workbook_data
  - `POST /api/sheets/{id}/save` 保存表格 workbook_data（落 PostgreSQL JSONB / SQLite TEXT）
- **前端手测**：登录 → 侧边「我的表格」→ 新建文件夹/表格 → 打开表格（Univer 画布渲染，支持编辑/公式/筛选/
  条件格式/下拉选择）→ 自动(30s)或手动保存 → 刷新页面重新打开，数据仍在（源自后端）。

### 4. 关键设计
- **Univer 集成**：预设模式 `@univerjs/presets` + `UniverSheetsCorePreset`（统一 0.25.1），增强预设
  （筛选 / 条件格式 / 数据验证）已一并注册。保存链路：
  `univerAPI.getActiveWorkbook().save()` → `POST /api/sheets/{id}/save` → PostgreSQL；
  加载：`GET /api/sheets/{id}` → `univerAPI.createWorkbook(snapshot)`。
- **数据归属**：表格的 Univer workbookData 存于 `documents.workbook_data`（JSONB）；owner / project_id /
  department_id 字段已预留，供第三阶段行权限隔离。
- **回收站**：软删除（`is_deleted` / `deleted_at`），支持恢复。
- **权限**：创建/编辑/删除表格受 RBAC 的 `sheet:*` 权限 + owner 校验约束。

---

## 后续阶段（按你的四阶段推进，逐步交付）
- **第三阶段**：多人协作（Redis + Univer 协同）、数据行权限（project_id/owner_id/department_id 隔离）、统计 API（`/api/statistics` 供大屏）。
- **第四阶段**：部署与压测（2 核 2G 调优）、日志系统、Excel 导入导出（Univer 快照方式）。

> 注：第二阶段前端已通过 `npm run build` 验证（Univer 打进 `SheetEditorView` 独立 chunk，gzip ~1.7MB，属正常体量）。
> Element Plus 仍全量引入，后续可切按需引入瘦身。
