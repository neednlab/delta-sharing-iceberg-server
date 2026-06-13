# Delta Sharing Admin UI

Delta Sharing for Iceberg 项目的管理后台前端界面，基于 React + TypeScript + Vite + Fluent UI 构建，为 Delta Sharing Server 的 [Admin API](http://localhost:8089/delta-sharing/admin/v1) 提供可视化管理能力。

---

## 目录

- [功能概览](#功能概览)
- [技术栈](#技术栈)
- [系统架构](#系统架构)
- [快速开始](#快速开始)
- [页面与路由](#页面与路由)
- [组件说明](#组件说明)
- [API 服务层](#api-服务层)
- [状态管理](#状态管理)
- [代理配置](#代理配置)
- [测试](#测试)
- [构建与部署](#构建与部署)
- [项目目录结构](#项目目录结构)
- [开发规范](#开发规范)

---

## 功能概览

Admin UI 提供三大核心管理功能模块，覆盖 Delta Sharing Server 的全部管理能力：

- **Share 管理** — Share 实体的创建、重命名、删除；Schema / Table 资产的增删改查；从腾讯云 DLC 同步表元数据
- **Recipient 管理** — Recipient 的创建、编辑（激活/停用/备注）、删除；Share 授权与撤销；Bearer Token 的生成、轮换、撤销、Profile 下载
- **审计日志查看** — 按日志类型（admin_audit / client_audit / app）查看审计日志，支持分页、日期选择、多列模糊过滤
- **管理员认证** — 用户名密码登录系统，JWT Cookie 认证，路由守卫，Logout 功能

辅助特性：
- 🔐 管理员登录认证（用户名 + 密码，bcrypt 密码哈希存储）
- 🚪 Logout 按钮（清除会话，返回登录页）
- 🌓 亮色 / 暗色主题切换（持久化到 localStorage）
- 📄 基于 pageToken 的分页导航
- 🛡️ ErrorBoundary 页面级错误兜底
- 🔄 Token 过期选项管理（预设选项 + 自定义日期）

---

## 技术栈

| 类别 | 技术 | 版本 | 说明 |
|------|------|------|------|
| 运行时 | [React](https://react.dev/) | ^19.2 | UI 框架 |
| 运行时 | [TypeScript](https://www.typescriptlang.org/) | ~6.0 | 类型安全 |
| 运行时 | [Vite](https://vitejs.dev/) | ^8.0 | 构建工具与开发服务器 |
| 运行时 | [React Router](https://reactrouter.com/) | ^7.14 | 客户端路由 |
| UI 库 | [Fluent UI React Components](https://react.fluentui.dev/) | ^9.73 | Microsoft 设计系统组件库 |
| UI 库 | [Fluent UI React Icons](https://react.fluentui.dev/) | ^2.0 | 图标库 |
| 测试 | [Vitest](https://vitest.dev/) | ^4.1 | 单元测试框架 |
| 测试 | [Testing Library](https://testing-library.com/) | ^16.3 | 组件测试工具 |
| 测试 | [MSW](https://mswjs.io/) | ^2.14 | API Mock |
| 规范 | [ESLint](https://eslint.org/) | ^9.39 | 代码规范检查 |
| 环境 | Python / uv | >=3.12 | 运行 [main.py](file:///c:/MOKURO/DEVELOP/Code/Project/delta_sharing_iceberg/ui/main.py)（当前为占位脚本） |

---

## 系统架构

### 整体架构

```
┌─────────────────────────────────────────────────────────┐
│                     Admin UI (Port 5173)                 │
│  ┌──────────┐  ┌──────────────┐  ┌───────────────────┐  │
│  │  Login   │  │  Share       │  │  Recipient        │  │
│  │  Page    │  │  Manager     │  │   Manager         │  │
│  └────┬─────┘  └──────┬───────┘  └────────┬──────────┘  │
│       │               │                   │             │
│  ┌────┴───────┬───────┴───────────────────┴──────────┐  │
│  │  AuthContext + ProtectedRoute (路由守卫)           │  │
│  └───────────────────────┬───────────────────────────┘  │
│                          │                              │
│  ┌───────────────────────┴──────────────────────────┐  │
│  │               API Service Layer                    │  │
│  │  authApi / shareApi / recipientApi / auditLogApi  │  │
│  │  (所有请求携带 credentials: 'include' → Cookie)    │  │
│  └───────────────────────┬──────────────────────────┘  │
└──────────────────────────┼──────────────────────────────┘
                           │  fetch() + Cookie
              ┌────────────┴────────────┐
              │    Vite Dev Proxy       │
              │                         │
              │ /delta-sharing/admin →  │  Admin API (port 8089)
              │ /delta-sharing       →  │  Data Plane API (port 8088)
              └─────────────────────────┘
                           │
              ┌────────────┴────────────────────┐
              │     Delta Sharing Server         │
              │     (FastAPI + SQLite + COS)     │
              │     + admin_users 表 + JWT 认证   │
              └─────────────────────────────────┘
```

### 应用组件树

```
<App>
  <ThemeProvider>                  ← 主题状态管理
    <AuthProvider>                  ← 认证状态管理 (JWT Cookie)
      <FluentProvider>             ← Fluent UI 主题注入
        <BrowserRouter>            ← 客户端路由
          <Routes>
            /login  → <LoginPage />            ← 公开路由
            /       → Navigate → /shares
            /shares → <ProtectedRoute>
                         <Navigation />        ← 顶部导航栏 + Logout 按钮
                         <ErrorBoundary>
                           <ShareManager />
                         </ErrorBoundary>
                       </ProtectedRoute>
            /shares/:shareId/assets → <ProtectedRoute>...</ProtectedRoute>
            /recipients → <ProtectedRoute>...</ProtectedRoute>
            /audit-logs → <ProtectedRoute>...</ProtectedRoute>
          </Routes>
        </BrowserRouter>
      </FluentProvider>
    </AuthProvider>
  </ThemeProvider>
</App>
```

---

## 快速开始

### 环境要求

- **Node.js** >= 18（推荐 20+）
- **npm** >= 9
- **Python** >= 3.12（仅用于 `uv run main.py`，当前为占位脚本）
- **Delta Sharing Server** 需要在本地 8088（Data Plane）和 8089（Admin）端口运行

### 安装与启动

```bash
# 1. 进入 ui 目录
cd ui

# 2. 安装依赖
npm install

# 3. 启动开发服务器（默认监听 http://localhost:5173）
npm run dev
```

> **重要**：确保后端服务已经启动。Admin UI 通过 Vite 代理将 API 请求转发到后端：
> - `/delta-sharing/admin/*` → `http://localhost:8089`
> - `/delta-sharing/*`（非 admin） → `http://localhost:8088`

### 快速验证

```bash
# 运行 ESLint 代码检查
npm run lint

# 运行单元测试
npm run test

# 构建生产包
npm run build

# 预览生产构建
npm run preview
```

### 初始化管理员账户

首次使用前，需要在服务端创建管理员账户：

```bash
# 进入 server 目录
cd ../server

# 创建管理员（需要在开发模式下运行）
$env:ENV="development"
uv run python scripts/init_admin.py --username admin --password yourpassword

# 之后即可在 UI 登录页使用该账户登录
```

---

## 页面与路由

| 路由 | 页面组件 | 功能描述 |
|------|---------|---------|
| `/login` | `LoginPage` | 管理员登录页面，用户名密码认证 |
| `/` | — | 自动重定向到 `/shares`（需登录） |
| `/shares` | `ShareManager` | Share 实体列表，支持创建、重命名、删除 Share（需登录） |
| `/shares/:shareId/assets` | `ShareAssetDetail` | 管理 Share 下的 Schema 和 Table 资产（需登录） |
| `/recipients` | `RecipientManager` | Recipient 列表，支持创建、编辑、删除 Recipient（需登录） |
| `/audit-logs` | `AuditLogViewer` | 审计日志查看器，支持按类型、日期、自定义过滤条件查询（需登录） |

### 路由导航

路由切换由顶部 `Navigation` 组件中的 [TabList](file:///c:/MOKURO/DEVELOP/Code/Project/delta_sharing_iceberg/ui/src/components/Navigation.tsx) 控制，通过 `react-router-dom` 的 `NavLink` 实现页面切换：

- **Share Management** (`/shares`) — 管理共享资源定义
- **Recipient Management** (`/recipients`) — 管理数据接收方
- **Audit Log** (`/audit-logs`) — 查看审计日志

---

## 组件说明

### 核心页面组件

| 组件 | 文件 | 描述 |
|------|------|------|
| [LoginPage](file:///c:/MOKURO/DEVELOP/Code/Project/delta_sharing_iceberg/ui/src/components/LoginPage.tsx) | `LoginPage.tsx` | 管理员登录页面，Fluent UI Card + Input + Button 表单，支持错误提示 |
| [ShareManager](file:///c:/MOKURO/DEVELOP/Code/Project/delta_sharing_iceberg/ui/src/components/ShareManager.tsx) | `ShareManager.tsx` | Share 管理页面，提供 Share 列表展示、分页、创建/重命名/删除操作 |
| [ShareAssetDetail](file:///c:/MOKURO/DEVELOP/Code/Project/delta_sharing_iceberg/ui/src/components/ShareAssetDetail.tsx) | `ShareAssetDetail.tsx` | Share 资产详情页，管理 Schema 和 Table 资产的增删改查，支持 DLC 同步 |
| [RecipientManager](file:///c:/MOKURO/DEVELOP/Code/Project/delta_sharing_iceberg/ui/src/components/RecipientManager.tsx) | `RecipientManager.tsx` | Recipient 管理页面，聚合了 Recipient CRUD 和 Token 管理功能 |
| [AuditLogViewer](file:///c:/MOKURO/DEVELOP/Code/Project/delta_sharing_iceberg/ui/src/components/AuditLogViewer.tsx) | `AuditLogViewer.tsx` | 审计日志查看器，支持日志类型切换、日期选择、多列过滤、分页 |

### 通用组件

| 组件 | 文件 | 描述 |
|------|------|------|
| [Navigation](file:///c:/MOKURO/DEVELOP/Code/Project/delta_sharing_iceberg/ui/src/components/Navigation.tsx) | `Navigation.tsx` | 顶部导航栏，包含 Logo、标题、TabList（页面切换）、Logout 按钮和主题切换按钮 |
| [ErrorBoundary](file:///c:/MOKURO/DEVELOP/Code/Project/delta_sharing_iceberg/ui/src/components/ErrorBoundary.tsx) | `ErrorBoundary.tsx` | React 错误边界，捕获子组件渲染异常并显示友好的 fallback UI（含 Retry 按钮） |
| [ProtectedRoute](file:///c:/MOKURO/DEVELOP/Code/Project/delta_sharing_iceberg/ui/src/components/ProtectedRoute.tsx) | `ProtectedRoute.tsx` | 路由守卫组件，未登录自动重定向到 `/login`，认证检查期间显示 Spinner |

### Recipient 管理子组件

| 组件 | 文件 | 描述 |
|------|------|------|
| `RecipientCreateDialog` | `RecipientCreateDialog.tsx` | 创建 Recipient 对话框，输入名称和备注 |
| `RecipientEditDialog` | `RecipientEditDialog.tsx` | 编辑 Recipient 对话框，修改名称/备注/激活状态，管理 Share 授权 |
| `RecipientDeleteDialog` | `RecipientDeleteDialog.tsx` | 删除 Recipient 确认对话框 |
| `TokenManagementDialog` | `TokenManagementDialog.tsx` | Token 管理对话框，展示 Token 列表、生成新 Token、撤销 Token、下载 Profile |
| `TokenRotateDialog` | `TokenRotateDialog.tsx` | Token 轮换对话框，设置过期时间后生成新 Token 并保留旧 Token |
| `TokenRotateResultDialog` | `TokenRotateResultDialog.tsx` | Token 轮换结果展示对话框，显示新旧 Token 信息和 Profile 下载 |

---

## API 服务层

API 调用封装在 [src/services/api.ts](file:///c:/MOKURO/DEVELOP/Code/Project/delta_sharing_iceberg/ui/src/services/api.ts) 中，通过原生 `fetch()` 与后端 Admin API 通信。

### 基础架构

```typescript
const API_BASE_URL = '/delta-sharing/admin/v1';
```

所有 API 请求均使用相对路径，通过 Vite 开发服务器的代理转发到后端。`handleResponse<T>()` 作为统一的响应处理器，负责错误解析和类型安全的 JSON 反序列化。

### API 分组

| 分组 | 函数 | 描述 |
|------|------|------|
| `authApi` | `login()` | 管理员登录，提交 username + password |
| | `logout()` | 管理员登出，清除服务端 Cookie |
| | `getCurrentAdmin()` | 获取当前登录管理员信息（验证会话有效性） |
| `shareApi` | `getShares()` | 获取 Share 列表（支持分页） |
| | `createShare()` | 创建 Share |
| | `renameShare()` | 重命名 Share |
| | `deleteShare()` | 删除 Share |
| | `getShareObjects()` | 获取 Share 下所有资产（Schema + Table） |
| | `addShareObject()` | 添加资产（Schema 或 Table） |
| | `updateShareObject()` | 更新资产配置 |
| | `deleteShareObject()` | 删除资产 |
| | `syncSchemaTables()` | 从 DLC 同步 Schema 下的表 |
| `recipientApi` | `getRecipients()` | 获取 Recipient 列表（支持分页） |
| | `createRecipient()` | 创建 Recipient |
| | `updateRecipient()` | 更新 Recipient 信息 |
| | `deleteRecipient()` | 删除 Recipient |
| | `getRecipientShares()` | 获取 Recipient 的已授权 Share 列表 |
| | `grantShareToRecipient()` | 授权 Share 给 Recipient |
| | `revokeShareFromRecipient()` | 撤销 Recipient 的 Share 授权 |
| | `generateToken()` | 生成 Bearer Token |
| | `listTokens()` | 列出 Recipient 的所有 Token |
| | `revokeToken()` | 撤销指定 Token |
| | `rotateToken()` | Token 轮换（生成新 + 保留旧） |
| `auditLogApi` | `getLogFiles()` | 获取审计日志文件列表（按类型分组的日期列表） |
| | `getLogEntries()` | 分页查询指定类型和日期的审计日志条目 |
| `configApi` | `fetchConfig()` | 获取前端需要的应用配置（Token 相关参数） |

### 对应后端 API

Admin UI 的 API 服务层完整映射了服务端的 [Admin API](http://localhost:8089/delta-sharing/admin/v1)：

| 前端 API | 对应后端端点 |
|---------|-------------|
| `authApi.login()` | `POST /admin/v1/auth/login` |
| `authApi.logout()` | `POST /admin/v1/auth/logout` |
| `authApi.getCurrentAdmin()` | `GET /admin/v1/auth/me` |
| `shareApi.getShares()` | `GET /admin/v1/shares` |
| `shareApi.createShare()` | `POST /admin/v1/shares` |
| `shareApi.renameShare()` | `PUT /admin/v1/shares/{name}/rename` |
| `shareApi.deleteShare()` | `DELETE /admin/v1/shares/{name}` |
| `shareApi.syncSchemaTables()` | `POST /admin/v1/sync/tables` |
| `recipientApi.getRecipients()` | `GET /admin/v1/recipients` |
| `recipientApi.createRecipient()` | `POST /admin/v1/recipients` |
| `recipientApi.grantShareToRecipient()` | `POST /admin/v1/recipients/{name}/shares` |
| `recipientApi.generateToken()` | `POST /admin/v1/recipients/{name}/token` |
| `auditLogApi.getLogEntries()` | `GET /admin/v1/audit-logs/{type}` |
| `configApi.fetchConfig()` | `GET /admin/v1/config` |

---

## 状态管理

Admin UI 采用轻量级状态管理策略，未引入 Redux / Zustand 等全局状态库，而是根据场景选择合适的方案：

### 组件本地状态 (useState)

页面组件（`ShareManager`、`RecipientManager`、`AuditLogViewer`）直接使用 `useState` 管理数据列表、加载状态、错误消息、对话框开关等页面级状态。

### React Context（主题 + 认证）

[ThemeContext](file:///c:/MOKURO/DEVELOP/Code/Project/delta_sharing_iceberg/ui/src/contexts/ThemeContext.tsx) 管理亮色/暗色主题的切换，状态持久化到 `localStorage`（key: `delta-sharing-ui-theme`），通过 `<html data-theme>` 属性同步到 DOM。

[AuthContext](file:///c:/MOKURO/DEVELOP/Code/Project/delta_sharing_iceberg/ui/src/contexts/AuthContext.tsx) 管理管理员认证状态：
- 挂载时通过 `GET /auth/me` 验证 Cookie 中的 JWT 有效性，恢复登录状态
- `login(username, password)` → `POST /auth/login` → 服务端设置 `admin_token` HttpOnly Cookie
- `logout()` → `POST /auth/logout` → 清除 Cookie + 重置本地状态
- 为 `ProtectedRoute` 提供 `isAuthenticated` / `isLoading` 判断

### 自定义 Hooks

| Hook | 文件 | 描述 |
|------|------|------|
| [usePagination](file:///c:/MOKURO/DEVELOP/Code/Project/delta_sharing_iceberg/ui/src/hooks/usePagination.ts) | `usePagination.ts` | 通用分页 Hook，封装基于 pageToken 的分页状态。支持前一页/后一页导航、重新加载、自动竞态（AbortController 取消过期请求）。泛型设计，可复用于任意列表 API |
| [useExpiration](file:///c:/MOKURO/DEVELOP/Code/Project/delta_sharing_iceberg/ui/src/hooks/useExpiration.ts) | `useExpiration.ts` | Token 过期选项状态管理 Hook，封装预设选项和自定义日期的状态管理，通过 `useMemo` 计算最终过期小时数 |

### 数据流

```
Component (useState + usePagination)
  → custom Hook (数据获取/分页逻辑)
    → API Service (fetch + credentials:'include' → Cookie)
      → Vite Dev Proxy
        → Delta Sharing Server (FastAPI + JWT Auth)

Component (useAuth)
  → AuthContext (login/logout + session restore)
    → authApi (POST /auth/login, /auth/logout, GET /auth/me)
```

---

## 代理配置

在开发模式下，Vite 开发服务器通过 [vite.config.ts](file:///c:/MOKURO/DEVELOP/Code/Project/delta_sharing_iceberg/ui/vite.config.ts) 中的代理配置解决 CORS 跨域问题：

```typescript
// vite.config.ts
export default defineConfig({
  server: {
    port: 5173,
    proxy: {
      '/delta-sharing/admin': {
        target: 'http://localhost:8089',   // Admin API
        changeOrigin: true,
        secure: false,
      },
      '/delta-sharing': {
        target: 'http://localhost:8088',   // Data Plane API
        changeOrigin: true,
        secure: false,
      },
    },
  },
});
```

> **代理匹配规则**：`/delta-sharing/admin` 规则必须排在通用的 `/delta-sharing` 规则之前，Vite 按配置顺序进行前缀匹配，确保 Admin API 请求被精确路由到 8089 端口。

### 生产环境配置

生产部署时，建议通过 Nginx 反向代理同时提供前端静态资源和后端 API：

```nginx
# Nginx 示例
server {
    listen 80;
    server_name delta-sharing.example.com;

    # 前端静态资源
    location / {
        root /path/to/ui/dist;
        try_files $uri $uri/ /index.html;
    }

    # Admin API
    location /delta-sharing/admin {
        proxy_pass http://localhost:8089;
    }

    # Data Plane API
    location /delta-sharing {
        proxy_pass http://localhost:8088;
    }
}
```

---

## 测试

### 测试框架

```bash
# 运行全部测试
npm run test

# 监听模式（开发时使用）
npm run test:watch
```

### 测试配置

测试通过 [vitest.config.ts](file:///c:/MOKURO/DEVELOP/Code/Project/delta_sharing_iceberg/ui/vitest.config.ts) 配置：

- **测试环境**: `jsdom`（模拟浏览器 DOM）
- **全局 API**: 启用（无需显式 import `describe`/`it`/`expect`）
- **Setup 文件**: `src/test-utils/setup.ts`（加载 `@testing-library/jest-dom/vitest` 匹配器）
- **路径别名**: `@` → `./src`
- **测试文件匹配**: `src/__tests__/**/*.test.{ts,tsx}`

### 测试工具

| 工具 | 用途 |
|------|------|
| [Vitest](https://vitest.dev/) | 测试运行器 |
| [Testing Library (React)](https://testing-library.com/) | 组件渲染与查询 |
| [user-event](https://testing-library.com/docs/user-event/intro/) | 模拟用户交互 |
| [MSW](https://mswjs.io/) | HTTP 请求拦截与 Mock |
| [@testing-library/jest-dom](https://github.com/testing-library/jest-dom) | 额外 DOM 断言匹配器（如 `toBeInTheDocument`） |

### 测试覆盖

| 测试文件 | 覆盖范围 |
|---------|---------|
| `src/__tests__/services/api.test.ts` | API 服务层各接口的请求与响应处理 |
| `src/__tests__/hooks/usePagination.test.ts` | usePagination Hook 的分页逻辑 |
| `src/__tests__/hooks/useExpiration.test.ts` | useExpiration Hook 的过期计算逻辑 |
| `src/__tests__/utils/auditLogHelpers.test.ts` | 审计日志辅助工具函数 |
| `src/__tests__/utils/calculateExpirationHours.test.ts` | 过期小时数计算工具 |
| `src/__tests__/utils/formatDate.test.ts` | 日期格式化工具 |

---

## 构建与部署

### 构建生产包

```bash
npm run build
```

此命令执行两步操作：
1. `tsc -b` — TypeScript 类型检查
2. `vite build` — Vite 打包构建

构建产物输出到 `dist/` 目录，包含：
- `index.html` — 入口 HTML
- `assets/` — JS/CSS/图片等静态资源（带内容哈希命名，支持长期缓存）

### 本地预览生产构建

```bash
npm run preview
```

Vite 将以本地静态服务器方式提供 `dist/` 目录内容，用于在部署前验证生产构建。

### 部署步骤

1. 运行 `npm run build` 构建生产包
2. 将 `dist/` 目录部署到 Nginx、CDN 或其他 Web 服务器
3. 配置反向代理将 `/delta-sharing/` 路径转发到后端服务

---

## 项目目录结构

```
ui/
├── index.html                          # HTML 入口文件
├── package.json                        # npm 依赖与脚本
├── pyproject.toml                      # Python/uv 项目配置
├── main.py                             # Python 入口脚本（占位）
├── vite.config.ts                      # Vite 构建配置 + 开发代理
├── vitest.config.ts                    # Vitest 测试配置
├── tsconfig.json                       # TypeScript 根配置（项目引用）
├── tsconfig.app.json                   # 应用代码 TypeScript 配置
├── tsconfig.node.json                  # Node 端 TypeScript 配置
├── eslint.config.js                    # ESLint 规范配置
├── .gitignore                          # Git 忽略规则
├── .python-version                     # Python 版本声明
│
├── public/
│   ├── favicon.svg                     # 网站图标
│   └── icons.svg                       # SVG 图标资源
│
├── src/
│   ├── main.tsx                        # React 应用入口（createRoot）
│   ├── App.tsx                         # 根组件（路由 + 主题 + 认证 + 页面布局）
│   ├── index.css                       # 全局 CSS 样式
│   │
│   ├── assets/
│   │   ├── hero.png                    # 展示图片
│   │   ├── iceberg-logo-icon.png       # 导航栏 Logo
│   │   ├── react.svg                   # React 图标
│   │   └── vite.svg                    # Vite 图标
│   │
│   ├── components/
│   │   ├── index.ts                    # 组件统一导出
│   │   ├── Navigation.tsx              # 顶部导航栏（TabList + Logout + 主题切换）
│   │   ├── ErrorBoundary.tsx           # React 错误边界
│   │   ├── LoginPage.tsx               # 管理员登录页面
│   │   ├── ProtectedRoute.tsx          # 路由守卫（未登录 → /login）
│   │   ├── ShareManager.tsx            # Share 管理页面
│   │   ├── ShareAssetDetail.tsx        # Share 资产详情页面
│   │   ├── RecipientManager.tsx        # Recipient 管理页面
│   │   ├── RecipientCreateDialog.tsx   # 创建 Recipient 对话框
│   │   ├── RecipientEditDialog.tsx     # 编辑 Recipient 对话框
│   │   ├── RecipientDeleteDialog.tsx   # 删除 Recipient 确认对话框
│   │   ├── TokenManagementDialog.tsx   # Token 管理对话框
│   │   ├── TokenRotateDialog.tsx       # Token 轮换对话框
│   │   ├── TokenRotateResultDialog.tsx # Token 轮换结果展示对话框
│   │   └── AuditLogViewer.tsx          # 审计日志查看器
│   │
│   ├── contexts/
│   │   ├── ThemeContext.tsx            # 亮色/暗色主题上下文
│   │   └── AuthContext.tsx             # 管理员认证状态上下文
│   │
│   ├── hooks/
│   │   ├── index.ts                    # Hooks 统一导出
│   │   ├── usePagination.ts            # 通用分页 Hook
│   │   └── useExpiration.ts            # Token 过期选项 Hook
│   │
│   ├── services/
│   │   ├── index.ts                    # 服务统一导出
│   │   └── api.ts                      # REST API 服务层
│   │
│   ├── types/
│   │   └── index.ts                    # TypeScript 类型定义
│   │
│   ├── utils/
│   │   ├── index.ts                    # 工具函数统一导出
│   │   ├── auditLogHelpers.tsx         # 审计日志渲染辅助
│   │   ├── calculateExpirationHours.ts  # 过期小时数计算
│   │   ├── downloadProfile.ts          # Profile 文件下载
│   │   ├── expirationOptions.ts        # Token 过期预设选项
│   │   ├── formatDate.ts               # 日期格式化
│   │   ├── formatTimestamp.ts          # 时间戳格式化
│   │   ├── getNestedValue.ts           # 嵌套对象值获取
│   │   ├── recipientUtils.ts           # Recipient 显示名称获取
│   │   ├── renderCellValue.ts          # 表格单元格值渲染
│   │   ├── renderSourceMapping.ts      # DLC 源映射渲染
│   │   └── tokenAgeStatus.ts           # Token 年龄状态判断
│   │
│   ├── test-utils/
│   │   ├── index.ts                    # 测试工具统一导出
│   │   ├── setup.ts                    # 测试全局设置
│   │   ├── render.tsx                  # 自定义 render 函数
│   │   └── mocks/
│   │       ├── handlers.ts             # MSW 请求处理器
│   │       └── server.ts               # MSW Mock 服务器
│   │
│   └── __tests__/
│       ├── hooks/
│       │   ├── useExpiration.test.ts
│       │   └── usePagination.test.ts
│       ├── services/
│       │   └── api.test.ts
│       └── utils/
│           ├── auditLogHelpers.test.ts
│           ├── calculateExpirationHours.test.ts
│           └── formatDate.test.ts
│
└── dist/                               # 生产构建输出（npm run build）
    └── ...
```

---

## 开发规范

### TypeScript

- 编译目标: **ES2023**
- JSX 模式: `react-jsx`（无需显式 import React）
- 模块解析: `bundler` 模式（匹配 Vite 行为）
- 启用 `verbatimModuleSyntax` 确保类型导入使用 `import type` 语法
- 启用 `noUnusedLocals` 和 `noUnusedParameters` 避免死代码

### ESLint 规范

配置位于 [eslint.config.js](file:///c:/MOKURO/DEVELOP/Code/Project/delta_sharing_iceberg/ui/eslint.config.js)，采用 ESLint v9 flat config 格式：

- 继承 `@eslint/js` 推荐规则
- 继承 `typescript-eslint` 推荐规则
- 启用 `react-hooks` 规则（检查 Hook 依赖）
- 启用 `react-refresh` 规则（确保 HMR 正常工作）
- 忽略 `dist/` 目录

### 代码风格

- 使用 **函数组件 + TypeScript 泛型**，避免类组件（除 ErrorBoundary 需要 `componentDidCatch` 外）
- 使用 `makeStyles`（Fluent UI）编写组件样式，利用 design tokens 保持设计一致性
- 工具函数和类型定义统一通过 `index.ts` 桶文件导出
- **前端页面语言始终使用英文**
- 关键代码和不易理解的部分必须添加注释

```bash
# ESLint 代码检查
npm run lint
```

### 与后端项目的协调

Admin UI 是 Delta Sharing Server 的前端管理界面，二者的 API 契约通过后端的 [Admin API](http://localhost:8089/delta-sharing/admin/v1) 定义。在开发过程中：

1. **修改后端 API** 时需同步更新前端的 `src/services/api.ts` 对应方法
2. **新增后端 Admin API** 时需在前端 `src/types/index.ts` 中定义对应的 TypeScript 类型
3. **Vite 代理配置**中的端口号需与后端服务端口保持一致（默认 8088/8089）

---

## 相关资源

- [Delta Sharing 协议官方文档](https://github.com/delta-io/delta-sharing)
- [Delta Sharing Server 后端 README](../server/README.md)
- [Fluent UI React v9 文档](https://react.fluentui.dev/)
- [Vite 文档](https://vitejs.dev/)
- [Vitest 文档](https://vitest.dev/)
- [React Router v7 文档](https://reactrouter.com/)
