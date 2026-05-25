# Delta Sharing Server for Iceberg Tables

[![English Docs](./assets/Docs-English-blue.svg)](./README.md)

---

## 项目概览

本项目实现标准的Delta Sharing protocol，在官方仅支持 Delta Lake 表格式的基础上，**新增了对 Apache Iceberg 表格式的完整支持**。服务通过解析 Iceberg 表的元数据，生成带对象存储预签名URL的文件列表返回给客户端。

> **协议参考**：整体实现遵从官方 [Delta Sharing Protocol](https://github.com/delta-io/delta-sharing/blob/main/PROTOCOL.md) 规范，包括 REST API 设计、数据交换格式、认证机制等。

当前支持基于腾讯云DLC和COS对象存储的Iceberg table，未来可扩展到其他metastore。

### 核心特性

- **✅ Iceberg 表格式支持**：解析 Iceberg 元数据层（metadata / manifest-list / manifest），提取 Parquet 数据文件
- **✅ 腾讯云 COS 集成**：自动生成 COS 预签名 URL，客户端可直接下载 Parquet 文件
- **✅ 腾讯云 DLC 集成**：通过 DLC API 自动查询 Iceberg 表的 `metadata_location` 路径，以及获取DLC database及table schema
- **✅ Recipient-Share 授权体系**：细粒度的 Share 级别访问控制
- **✅ 谓词下推与分区裁剪**：支持 predicateHints 和 jsonPredicateHints，利用文件级统计信息过滤
- **✅ 时间旅行查询**：基于 version 或 timestamp 查询历史快照数据

---

## 系统架构

### 分层架构

```
┌─────────────────────────────────────────────────────────┐
│                    API Layer                             │
│  ┌──────────────────────┐  ┌──────────────────────────┐ │
│  │  Data Plane Routes   │  │     Admin API Routes     │ │
│  │  (Delta Sharing 协议) │  │  (/admin/v1/*)          │ │
│  │  /shares             │  │  /recipients             │ │
│  │  /.../metadata       │  │  /shares                 │ │
│  │  /.../query          │  │  /tokens                 │ │
│  │  /.../version        │  │  /sync/tables            │ │
│  │  /health             │  │  /audit-logs             │ │
│  └──────────┬───────────┘  └────────────┬─────────────┘ │
├─────────────┼──────────────────────────┼────────────────┤
│             ▼                          ▼                │
│                  Service Layer                           │
│  ┌──────────┐ ┌──────────┐ ┌────────────┐ ┌──────────┐ │
│  │  Share   │ │ Iceberg  │ │ Predicate  │ │  Version │ │
│  │ Service  │ │ Service  │ │  Service   │ │  Service │ │
│  └────┬─────┘ └────┬─────┘ └─────┬──────┘ └────┬─────┘ │
│  ┌────┴─────┐ ┌────┴───────────┐ ┌───────────┐ ┌──────┐│
│  │  Auth    │ │  Authorization │ │  Token /  │ │Table ││
│  │ Service  │ │    Service     │ │ Recipient │ │Service││
│  │          │ │                │ │  Service  │ │      ││
│  └────┬─────┘ └──────┬─────────┘ └─────┬─────┘ └──┬───┘│
├───────┼───────────────┼───────────────────┼─────────────┤
│       ▼               ▼                   ▼             │
│                Repository Layer                          │
│  ┌──────────┐ ┌────────────┐ ┌──────────────────────┐   │
│  │  Share   │ │  Token     │ │ Snapshot Version     │   │
│  │Repository│ │Repository  │ │   Repository         │   │
│  └────┬─────┘ └─────┬──────┘ └──────────┬───────────┘   │
│  ┌────┴─────┐ ┌─────┴──────────────┐                    │
│  │ Recipient│ │ Recipient-Share    │                    │
│  │Repository│ │   Repository       │                    │
│  └────┬─────┘ └────────┬───────────┘                    │
├───────┼────────────────┼────────────────────────────────┤
│       ▼                ▼                                 │
│                 Core Layer                               │
│  ┌────────┐ ┌───────┐ ┌───────┐ ┌──────┐ ┌──────────┐  │
│  │Database│ │Config │ │ Cache │ │Errors│ │ Audit    │  │
│  │(8表)   │ │(YAML) │ │(CtxVar│ │(29  │ │(JSONL)   │  │
│  │        │ │       │ │  3区) │ │错误码)│ │          │  │
│  └────────┘ └───────┘ └───────┘ └──────┘ └──────────┘  │
│  ┌────────────┐ ┌──────────┐ ┌───────────────────┐      │
│  │   Auth     │ │    COS   │ │       DLC         │      │
│  │ (SHA-256)  │ │  Client  │ │     Client        │      │
│  └────────────┘ └──────────┘ └───────────────────┘      │
└─────────────────────────────────────────────────────────┘
```

### 请求生命周期

```
Client → CORS Middleware → CacheMiddleware → AuditLoggingMiddleware
    → Exception Handlers → Route Handler → Service → Repository → SQLite/COS/DLC
```

### 中间件执行顺序

1. **CORSMiddleware** — 跨域请求处理
2. **CacheMiddleware** — 请求级缓存（ContextVar）初始化与清理
3. **AuditLoggingMiddleware** — 原始 ASGI 中间件，拦截响应体记录审计日志
4. **Exception Handlers** — 三层异常捕获：DeltaSharingError → HTTPException → generic Exception

---

## 快速开始

### 环境要求

- Python >= 3.12
- uv 包管理器（推荐）

### 安装与启动

```bash
# 1. 进入 server 目录
cd server

# 2. 安装依赖
uv sync

# 3. 配置环境变量
# 创建 .env.local 文件，设置腾讯云密钥
echo "COS_SECRET_ID=your-secret-id" > .env.local
echo "COS_SECRET_KEY=your-secret-key" >> .env.local
echo "DLC_SECRET_ID=your-secret-id" >> .env.local
echo "DLC_SECRET_KEY=your-secret-key" >> .env.local

# 4. 启动服务器（默认监听 0.0.0.0:8088）
uv run python main.py
```

服务器启动后，API 根路径为 `/delta-sharing`。

### 快速验证

```bash
# 健康检查
curl http://localhost:8088/health

# 预期输出
# {"status": "healthy"}
```

---

## API 参考

### Data Plane API（Delta Sharing 协议）

所有 Data Plane API 均需携带 `Authorization: Bearer <token>` 请求头。

| 方法 | 路径 | 描述 |
|------|------|------|
| `GET` | `/shares` | 列出当前 Recipient 有权访问的所有 Share |
| `GET` | `/shares/{share}` | 获取指定 Share 详细信息 |
| `GET` | `/shares/{share}/schemas` | 列出 Share 下的所有 Schema |
| `GET` | `/shares/{share}/schemas/{schema}/tables` | 列出 Schema 下的所有 Table |
| `GET` | `/shares/{share}/all-tables` | 列出 Share 下所有 Table（跨 Schema） |
| `GET` | `/shares/{share}/schemas/{schema}/tables/{table}/metadata` | 获取表的元数据（Schema、分区列等） |
| `GET` | `/shares/{share}/schemas/{schema}/tables/{table}/version` | 获取表的当前/历史版本号 |
| `POST` | `/shares/{share}/schemas/{schema}/tables/{table}/query` | 查询表数据文件（返回预签名 URL 列表） |

#### 分页支持

`/shares`、`/schemas`、`/tables`、`/all-tables` 端点支持基于 `maxResults` 和 `pageToken` 的分页查询。`pageToken` 为上一页响应中返回的 Base64 编码的下页令牌。

#### 版本查询

`GET /.../version` 支持以下查询参数：

| 参数 | 描述 |
|------|------|
| 无参数 | 返回当前最新版本号 |
| `timestamp` | ISO8601 格式，返回最接近但不超过此时间戳的版本 |
| `startingTimestamp` | ISO8601 格式，返回此时间之后的第一个版本 |

响应头包含 `Delta-Table-Version` 字段。

#### 表查询（Query）

`POST /.../query` 支持对数据文件进行过滤和限制，请求体字段：

| 字段 | 类型 | 描述 |
|------|------|------|
| `predicateHints` | `string[]` | Spark 谓词语法字符串列表（如 `["column > 100"]`） |
| `jsonPredicateHints` | `string` | JSON 格式的谓词，支持更复杂的过滤条件 |
| `limitHint` | `int` | 限制返回的文件数量上限 |
| `version` | `int` | 按版本号进行时间旅行查询 |
| `timestamp` | `string` | 按 ISO8601 时间戳进行时间旅行查询 |
| `startingVersion` | `int` | 版本范围查询（起始） |
| `endingVersion` | `int` | 版本范围查询（结束） |

响应为 NDJSON（Newline Delimited JSON）格式，依次包含：
1. `protocol` 对象
2. `metaData` 对象（包含 schemaString、partitionColumns 等）
3. 多个 `file` 对象（每个包含预签名 URL、分区值、统计信息等）

请求头 `delta-sharing-capabilities` 可用于指定响应格式：

- `responseFormat=parquet` — 标准 Parquet 格式（默认）
- `responseFormat=delta` — Delta Lake 格式（含 DeltaProtocol、DeltaMetadata）
- `readerFeatures=...` — 声明客户端支持的特性
- `includeEndStreamAction=true` — 在响应末尾追加 EndStreamAction

#### 错误响应格式

所有错误响应均包含以下字段：

```json
{
  "errorCode": "SHARE_NOT_FOUND",
  "message": "Share not found: myshare"
}
```

错误码分类：

| 类别 | 错误码 | HTTP 状态码 |
|------|--------|------------|
| 认证 | `AUTHENTICATION_HEADER_MISSING`、`AUTHENTICATION_HEADER_INVALID`、`INVALID_TOKEN`、`TOKEN_MALFORMED` | 401 |
| 授权 | `TOKEN_EXPIRED`、`TOKEN_REVOKED`、`ACCESS_DENIED`、`SHARE_ACCESS_DENIED` | 403 |
| 资源 | `SHARE_NOT_FOUND`、`SCHEMA_NOT_FOUND`、`TABLE_NOT_FOUND`、`RECIPIENT_NOT_FOUND`、`AUTHORIZATION_NOT_FOUND`、`RESOURCE_DOES_NOT_EXIST` | 404 |
| 业务 | `RECIPIENT_ALREADY_EXISTS`、`SHARE_ALREADY_EXISTS`、`SCHEMA_ALREADY_EXISTS`、`TABLE_ALREADY_EXISTS`、`AUTHORIZATION_ALREADY_EXISTS`、`MAX_TOKENS_EXCEEDED`、`TABLE_NOT_SUPPORTED`、`RECIPIENT_INACTIVE`、`NO_SHARES_ASSIGNED`、`INVALID_PARAMETER_VALUE` | 400/409 |
| 系统 | `INTERNAL_ERROR`、`COS_ACCESS_ERROR`、`DLC_NOT_CONFIGURED`、`DLC_API_ERROR` | 500 |

---

### Admin API（管理接口）

管理接口路径前缀为 `/delta-sharing/admin/v1`，用于管理 Recipient、Share 授权、Token、Share 实体等。

#### Recipient 管理

| 方法 | 路径 | 描述 |
|------|------|------|
| `POST` | `/recipients` | 创建 Recipient（参数：name、comment） |
| `GET` | `/recipients` | 列出所有 Recipient（支持分页） |
| `GET` | `/recipients/{name}` | 获取指定 Recipient 详情 |
| `PUT` | `/recipients/{name}` | 更新 Recipient（激活/停用/修改备注） |
| `DELETE` | `/recipients/{name}` | 删除 Recipient（级联删除关联 token、授权） |

#### Share 授权管理

| 方法 | 路径 | 描述 |
|------|------|------|
| `POST` | `/recipients/{name}/shares` | 为 Recipient 授权 Share（参数：share_name） |
| `GET` | `/recipients/{name}/shares` | 查询 Recipient 的所有授权 Share |
| `DELETE` | `/recipients/{name}/shares/{share_name}` | 撤销 Recipient 对指定 Share 的访问权限 |

#### Token 管理

| 方法 | 路径 | 描述 |
|------|------|------|
| `POST` | `/recipients/{name}/tokens` | 生成新 Token（每个 Recipient 最多持有 2 个有效 Token） |
| `GET` | `/recipients/{name}/tokens` | 列出 Recipient 的所有 Token（含撤销/过期状态） |
| `DELETE` | `/recipients/{name}/tokens` | 撤销 Recipient 的所有 Token |
| `DELETE` | `/recipients/{name}/tokens/{token}` | 撤销指定 Token |
| `GET` | `/recipients/{name}/tokens/profile` | 下载 Profile 文件（一次性，下载后即时销毁） |

#### Share 实体管理

| 方法 | 路径 | 描述 |
|------|------|------|
| `POST` | `/shares` | 创建 Share |
| `GET` | `/shares` | 列出所有 Share |
| `GET` | `/shares/{name}` | 获取 Share 详情 |
| `DELETE` | `/shares/{name}` | 删除 Share |
| `POST` | `/shares/{name}/schemas` | 添加 Schema 资产 |
| `GET` | `/shares/{name}/schemas` | 列出 Schema 资产 |
| `POST` | `/shares/{name}/schemas/{schema}/tables` | 添加 Table 资产 |
| `GET` | `/shares/{name}/schemas/{schema}/tables` | 列出 Table 资产 |
| `PUT` | `/shares/{name}/schemas/{schema}/tables/{table}` | 更新 Table 资产 |
| `DELETE` | `/shares/{name}/schemas/{schema}/tables/{table}` | 删除 Table 资产 |

#### DLC 表同步

| 方法 | 路径 | 描述 |
|------|------|------|
| `POST` | `/sync/tables` | 从腾讯云 DLC 同步表元数据到本地数据库 |

支持两种同步模式：
- **full**：全量替换，删除现有表后重新同步
- **append**：增量追加，保留现有表并添加新表

#### 审计日志查询

| 方法 | 路径 | 描述 |
|------|------|------|
| `GET` | `/audit-logs` | 获取审计日志类型列表（admin、client） |
| `GET` | `/audit-logs/{type}` | 分页查询指定类型的审计日志 |

支持多列模糊匹配过滤参数：`recipient_id`、`share`、`schema`、`table`、`operation`、`http_method`。

#### 配置查询

| 方法 | 路径 | 描述 |
|------|------|------|
| `GET` | `/config` | 获取前端 Token 配置（不暴露完整配置） |

---

## 数据库模型

系统使用 SQLite（通过 SQLAlchemy 2.0 Core API）存储 8 张业务表：

### ER 图

```
┌──────────────┐       ┌────────────────────┐
│   shares     │       │    recipients      │
├──────────────┤       ├────────────────────┤
│ share_id  PK │──┐    │ recipient_id   PK  │──┐
│ share_name   │  │    │ recipient_name     │  │
│ display_name │  │    │ comment            │  │
│ comment      │  │    │ is_active          │  │
│ properties   │  │    │ created_at         │  │
│ created_at   │  │    │ updated_at         │  │
│ updated_at   │  │    └────────────────────┘  │
└──────┬───────┘  │                             │
       │          │    ┌────────────────────────┼──────────────┐
       │          │    │  recipient_shares      │              │
       │          ├───►│  (授权关系表)           │              │
       │          │    ├────────────────────────┤              │
       │          │    │ id                  PK │              │
       │          │    │ recipient_id     FK ──►│── recipients │
       │          │    │ share_id         FK ──►│── shares     │
       │    ┌─────┘    │ granted_at            │              │
       │    │          │ granted_by            │              │
       │    │          └───────────────────────┘              │
       │    │                                                 │
  ┌────┴────┴──────────┐          ┌───────────────────────────┼──────┐
  │ shared_schemas     │          │     bearer_tokens         │      │
  ├────────────────────┤          ├───────────────────────────┤      │
  │ schema_id      PK  │          │ id                    PK  │      │
  │ share_id       FK ─┼── shares │ token_hash (SHA-256)      │      │
  │ schema_name        │          │ token_prefix              │      │
  │ metastore_db       │          │ recipient_id         FK ──┼── recipients
  │ created_at         │          │ created_at                │      │
  │ updated_at         │          │ expires_at                │      │
  └────────┬───────────┘          │ is_revoked                │      │
           │                      │ revoked_at                │      │
  ┌────────┴───────────┐          │ profile_content           │      │
  │  shared_tables     │          │ profile_downloaded        │      │
  ├────────────────────┤          └───────────────────────────┘      │
  │ table_id       PK  │                                             │
  │ share_id       FK ─┼── shares      ┌─────────────────────────────┼──┐
  │ linked_schema_id   │               │  token_revocation           │  │
  │ table_name         │               ├─────────────────────────────┤  │
  │ location (COS路径)  │               │ id                      PK │  │
  │ metastore_db       │               │ token_hash (SHA-256)        │  │
  │ metastore_table    │               │ revoked_at                  │  │
  │ schema_name        │               │ reason                      │  │
  │ auxiliary_locations│               └─────────────────────────────┘  │
  │ created_at         │                                                │
  │ updated_at         │         ┌──────────────────────────────────────┘
  └────────────────────┘         │
                                 │  ┌──────────────────────────────┐
                                 │  │   snapshot_version           │
                                 │  ├──────────────────────────────┤
                                 └──│ id                       PK  │
                                    │ share_name                   │
                                    │ schema_name                  │
                                    │ table_name                   │
                                    │ snapshot_id (Iceberg)        │
                                    │ version (Delta Sharing)      │
                                    │ timestamp                    │
                                    │ created_at                   │
                                    └──────────────────────────────┘
```

### 表说明

| 表名 | 描述 | 关键字段 |
|------|------|---------|
| `shares` | 共享资源定义 | `share_name`（唯一）、`display_name`、`properties` |
| `shared_schemas` | 共享 Schema 定义 | 通过 `share_id` 关联 Share，包含 `metastore_db` |
| `shared_tables` | 共享 Table 定义 | COS `location`、`metastore_db`/`metastore_table`（DLC 查询用） |
| `recipients` | 数据接收方 | `recipient_name`（唯一）、`is_active`（软启用/停用） |
| `recipient_shares` | 授权关系 | `recipient_id` + `share_id` 唯一约束 |
| `bearer_tokens` | Bearer Token 凭证 | `token_hash`（SHA-256）、`profile_content` |
| `token_revocation` | Token 撤销记录 | `token_hash` + `revoked_at` + `reason` |
| `snapshot_version` | 快照版本追踪 | `(share_name, schema_name, table_name, snapshot_id)` 唯一约束 |

### 表绑定模式

系统支持两种 Table 绑定模式：

1. **关联 Schema 绑定**：Table 通过 `linked_schema_id` 关联到 `shared_schemas`，继承 Schema 的 `metastore_db`
2. **直接 Share 绑定**：Table 直接通过 `share_id` 关联，字段自包含

查询时 Repository 层自动合并两种模式的表。

---

## 安全机制

### Bearer Token 认证流程

```
┌──────────┐                    ┌──────────────┐              ┌──────────┐
│  Admin   │                    │  Delta        │              │  SQLite  │
│  (管理端) │                    │  Sharing      │              │  数据库   │
└────┬─────┘                    │  Server       │              └────┬─────┘
     │                          └──────┬───────┘                   │
     │  1. 创建 Recipient              │                           │
     │────────────────────────────────►│                           │
     │                                 │  INSERT INTO recipients   │
     │                                 │──────────────────────────►│
     │                                 │                           │
     │  2. 授权 Share                  │                           │
     │────────────────────────────────►│                           │
     │                                 │  INSERT INTO              │
     │                                 │  recipient_shares         │
     │                                 │──────────────────────────►│
     │                                 │                           │
     │  3. 生成 Token                  │                           │
     │────────────────────────────────►│                           │
     │                                 │  token = secrets.token()  │
     │                                 │  token_hash = SHA-256()   │
     │                                 │  INSERT token_hash        │
     │                                 │  (明文永不落库)            │
     │                                 │──────────────────────────►│
     │  返回: token 明文 + profile     │                           │
     │◄────────────────────────────────│                           │
     │                                 │                           │
     │  4. 将 token + profile 分发给    │                           │
     │     客户端                      │                           │
     │                                 │                           │
┌────┴─────┐                          │                           │
│  Client  │  5. API 请求 + Bearer    │                           │
│  (客户端) │     token               │                           │
└────┬─────┘─────────────────────────►│                           │
     │                                 │  SHA-256(token)           │
     │                                 │  SELECT token_hash        │
     │                                 │──────────────────────────►│
     │                                 │◄── token_info ────────────│
     │                                 │                           │
     │                                 │  验证:                     │
     │                                 │  - token 是否存在          │
     │                                 │  - 是否已撤销              │
     │                                 │  - 是否已过期              │
     │                                 │  - Recipient 是否激活      │
     │                                 │                           │
     │  返回数据 or 错误响应            │                           │
     │◄────────────────────────────────│                           │
```

### 安全设计要点

- **Token 明文永不落库**：仅存储 SHA-256 哈希值，原始 Token 仅在生成时返回一次
- **单次数据库查询认证**：`validate_token()` 一次查询完成所有状态检查
- **404 安全模糊化**：不存在的 Token 与已过期 Token 返回相同错误，防止信息泄露
- **WWW-Authenticate 头**：401 认证相关错误自动携带 `WWW-Authenticate: Bearer` 响应头
- **Token 配额控制**：每个 Recipient 最多持有 2 个有效 Token（可配置）
- **Profile 一次性下载**：Profile 文件被下载后立即从服务端销毁
- **Recipient 软删除**：删除操作仅设置 `is_active=0`，保留审计追踪
- **COS 预签名 URL**：数据文件不经过服务器中转，客户端通过限时 URL 直接从 COS 下载

---

## 配置指南

### 配置文件结构（config.yaml）

```yaml
# 服务器配置
server:
  host: "0.0.0.0"
  port: 8088
  admin_host: "127.0.0.1"
  admin_port: 8089
  api_prefix: "/delta-sharing"

# 腾讯云 COS 配置
cos:
  region: "ap-shanghai"
  secret_id: "${COS_SECRET_ID}"       # 支持 ${ENV_VAR} 环境变量引用
  secret_key: "${COS_SECRET_KEY}"
  endpoint: "cos.ap-shanghai.myqcloud.com"

# 腾讯云 DLC 配置
dlc:
  region: "ap-shanghai"
  secret_id: "${DLC_SECRET_ID}"       # 支持 ${ENV_VAR} 环境变量引用
  secret_key: "${DLC_SECRET_KEY}"

# 数据库配置
database:
  url: "sqlite:///./data/server.db"   # 也支持 PostgreSQL 等数据库

# Token 配置
token:
  rotation_period_hours: 24          # Token 轮换周期
  max_tokens_per_recipient: 2        # 每个 Recipient 最大有效 Token 数
  expiration_hours: 168              # Token 默认过期时间（7天）

# COS 预签名 URL 配置
presigned_url:
  expiration_hours: 6                # 默认过期时间
  min_expiration_hours: 1            # 最小过期时间
  max_expiration_hours: 168          # 最大过期时间

# Share 配置
shares:
  use_database: true                 # true=数据库模式, false=纯配置模式
  fallback_file: "./config.yaml"     # 配置模式的回退文件
  myshare:                           # 示例 Share 定义（use_database=false 时生效）
    schemas:
      myschema:
        tables:
          ice_t1:
            location: "cosn://YOUR_BUCKET/delta/ice_t1"
            metastore_db: "playground"
            metastore_table: "ice_t1"
          ice_t2:
            location: "cosn://YOUR_BUCKET/delta/ice_t2"
            metastore_db: "playground"
            metastore_table: "ice_t2"

# 日志配置
logging:
  log_dir: "./log"
  app_log_level: "INFO"              # DEBUG / INFO / WARNING / ERROR
  app_log_retention: "30 days"       # 日志保留时间
  audit_log_level: "INFO"            # 审计日志级别
```

### 环境变量

| 变量名 | 描述 | 必填 |
|--------|------|------|
| `COS_SECRET_ID` | 腾讯云 COS SecretId | 是 |
| `COS_SECRET_KEY` | 腾讯云 COS SecretKey | 是 |
| `DLC_SECRET_ID` | 腾讯云 DLC SecretId（使用 DLC 功能时需要） | 否 |
| `DLC_SECRET_KEY` | 腾讯云 DLC SecretKey（使用 DLC 功能时需要） | 否 |
| `DLC_REGION` | 腾讯云 DLC 区域（如 `ap-shanghai`） | 否 |
| `DLC_ENDPOINT` | 腾讯云 DLC API 端点（覆盖默认值） | 否 |
| `PAGE_TOKEN_SECRET` | Page Token HMAC 签名密钥，生产环境必须设置 | 否 |

### 两种管理模式

**数据库模式（推荐）**：`shares.use_database: true`

- Share、Schema、Table 通过 Admin API 管理
- 支持通过 DLC 自动同步表元数据
- Share 授权通过 `recipient_shares` 表管理

**纯配置模式（开发/简单场景）**：`shares.use_database: false`

- Share 定义直接写在 `config.yaml` 的 `shares` 段中
- 启动时自动将配置同步到数据库
- 适合快速开发和测试

---

## 开发指南

### 项目目录结构

```
server/
├── main.py                          # 应用入口点
├── config.yaml                      # 主配置文件
├── pyproject.toml                   # 项目依赖与工具配置
├── data/
│   └── server.db                    # SQLite 数据库文件
├── log/
│   ├── app_2024-05-11.jsonl         # 应用日志（按日轮转）
│   ├── admin_audit_2024-05-11.jsonl # 管理审计日志
│   └── client_audit_2024-05-11.jsonl# 客户端审计日志
├── app/
│   ├── core/                        # 核心模块
│   │   ├── config.py                # 配置管理（YAML + 环境变量）
│   │   ├── database.py              # SQLAlchemy Core 数据库引擎（8 表定义）
│   │   ├── cache.py                 # 请求级缓存（ContextVar，3 缓存区）
│   │   ├── errors.py                # 错误定义（29 错误码枚举）
│   │   ├── authentication.py        # Bearer Token 认证（SHA-256）
│   │   ├── audit.py                 # 审计日志（双流、JSONL、按日轮转）
│   │   ├── delta_capabilities.py    # Delta Sharing Capabilities 解析
│   │   ├── cos_client.py            # 腾讯云 COS 客户端封装
│   │   ├── dlc_client.py            # 腾讯云 DLC 客户端封装
│   │   └── logging_config.py        # Loguru 全局日志配置
│   ├── models/                      # 数据模型（Pydantic）
│   │   ├── share.py                 # Share/Schema/Table 响应模型
│   │   ├── query.py                 # 查询请求/响应模型
│   │   └── profile.py              # Profile 文件模型
│   ├── repositories/                # 数据访问层
│   │   ├── share_repository.py      # Share/Schema/Table CRUD
│   │   ├── recipient_repository.py  # Recipient CRUD
│   │   ├── recipient_share_repository.py  # 授权关系管理
│   │   ├── token_repository.py      # Token CRUD + Profile 管理
│   │   └── version_repository.py    # 快照版本追踪
│   ├── services/                    # 业务逻辑层
│   │   ├── share_service.py         # Share 查询（分页、recipient 过滤）
│   │   ├── iceberg_service.py       # Iceberg 元数据解析 + Schema 转换
│   │   ├── predicate_service.py     # 谓词下推 + 分区裁剪
│   │   ├── version_service.py       # 版本管理（时间旅行）
│   │   ├── authorization_service.py # 授权管理
│   │   ├── recipient_service.py     # Recipient 管理
│   │   ├── token_service.py         # Token 管理
│   │   └── table_service.py         # 表配置查询
│   ├── routes/                      # Data Plane API 路由
│   │   ├── __init__.py              # 路由导出
│   │   ├── shares.py                # Share/Schema/Table 列表端点
│   │   ├── metadata.py              # 表元数据端点
│   │   ├── query.py                 # 表查询端点
│   │   ├── version.py               # 表版本端点
│   │   └── health.py                # 健康检查端点
│   ├── api/                         # Admin API
│   │   └── admin/
│   │       ├── __init__.py          # 管理路由聚合（/admin/v1）
│   │       ├── recipients.py        # Recipient 管理端点
│   │       ├── shares.py            # Share 授权管理端点
│   │       ├── tokens.py            # Token 管理端点
│   │       ├── share_management.py  # Share 实体管理端点
│   │       ├── sync.py              # DLC 表同步端点
│   │       ├── audit_logs.py        # 审计日志查询端点
│   │       └── config.py            # 前端配置查询端点
│   └── utils/                       # 工具模块
│       ├── request_utils.py         # 请求工具（IP 提取等）
│       ├── response_utils.py        # 响应工具（NDJSON 生成等）
│       ├── time_utils.py            # 时间工具（ISO8601 解析等）
│       ├── page_token_utils.py      # Page Token HMAC 编解码
│       └── audit_utils.py           # 审计工具（带审计的错误抛出）
└── tests/                           # 测试
    ├── conftest.py                   # pytest fixtures（数据库、客户端等）
    ├── test_core.py                  # 核心模块测试
    ├── test_routes.py                # 路由集成测试
    ├── test_authz.py                 # 认证授权端到端测试
    ├── test_audit.py                 # 审计日志测试
    ├── test_cache.py                 # 请求级缓存测试
    ├── test_delta_capabilities.py    # Delta Sharing Capabilities 测试
    ├── test_dlc_client.py            # DLC 客户端测试
    ├── test_page_token_utils.py      # Page Token 编解码测试
    ├── test_predicate_service.py     # 谓词下推服务测试
    ├── test_schema_asset.py          # Schema 资产管理测试
    ├── test_time_utils.py            # 时间工具测试
    └── test_version.py               # 版本服务测试
```

---

## 技术栈与依赖

### 运行时依赖

| 依赖 | 版本 | 用途 |
|------|------|------|
| [FastAPI](https://fastapi.tiangolo.com/) | >= 0.115.0 | Web 框架，提供 REST API 和自动文档 |
| [Uvicorn](https://www.uvicorn.org/) | >= 0.30.0 | ASGI 服务器 |
| [SQLAlchemy](https://www.sqlalchemy.org/) | >= 2.0.49 | 数据库 ORM（使用 Core API，非 ORM） |
| [PyIceberg](https://py.iceberg.apache.org/) | >= 0.5.0 | Apache Iceberg 表元数据解析 |
| [fastavro](https://fastavro.readthedocs.io/) | >= 1.12.2 | Avro 文件解析（manifest-list / manifest） |
| [avro](https://avro.apache.org/) | >= 1.11.0 | Apache Avro 格式解析（Iceberg 元数据层） |
| [cos-python-sdk-v5](https://github.com/tencentyun/cos-python-sdk-v5) | >= 1.9.0 | 腾讯云 COS SDK（预签名 URL 生成） |
| [tencentcloud-sdk-python](https://github.com/TencentCloud/tencentcloud-sdk-python) | >= 3.1.76 | 腾讯云 DLC SDK（元数据位置查询） |
| [Pydantic](https://docs.pydantic.dev/) | >= 2.0.0 | 数据验证与序列化 |
| [PyYAML](https://pyyaml.org/) | >= 6.0 | YAML 配置文件解析 |
| [loguru](https://loguru.readthedocs.io/) | >= 0.7.3 | 日志管理（控制台彩色 + 文件 JSONL） |
| [python-multipart](https://github.com/Kludex/python-multipart) | >= 0.0.12 | 表单数据解析（FastAPI 依赖） |
| [httpx](https://www.python-httpx.org/) | >= 0.27.0 | HTTP 客户端（测试使用） |

### 开发依赖

| 依赖 | 版本 | 用途 |
|------|------|------|
| [pytest](https://pytest.org/) | >= 8.0.0 | 测试框架 |
| [pytest-asyncio](https://pytest-asyncio.readthedocs.io/) | >= 0.24.0 | AsyncIO 测试支持 |
| [pytest-cov](https://pytest-cov.readthedocs.io/) | >= 4.0.0 | 测试覆盖率报告 |

### Python 版本

- 最低要求：**Python 3.12**
- 包管理器：**uv**（推荐使用 `uv sync` 和 `uv run`）

---

## Iceberg 元数据解析流程

查询 Iceberg 表数据时，服务端执行的完整元数据解析流水线：

```
                         ┌──────────────────────┐
                         │  DLC API             │
                         │  (DescribeTable)      │
                         │                       │
                         │  返回 metadata_location│
                         └──────────┬───────────┘
                                    │
                                    ▼
┌───────────────────────────────────────────────────────────────┐
│ 1. 获取 metadata.json 内容                                     │
│    - 通过 COS get_object 下载 Iceberg 表根元数据文件             │
│    - 解析 JSON，提取: schemas、partition-specs、snapshots       │
│    - [缓存] 同一请求内相同 metadata 路径仅下载一次               │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           ▼
┌───────────────────────────────────────────────────────────────┐
│ 2. 选择快照 (Snapshot)                                         │
│    - 默认: 使用 current-snapshot-id                            │
│    - version 查询: 根据版本号反查 snapshot_id                   │
│    - timestamp 查询: 根据时间戳查找最近快照                     │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           ▼
┌───────────────────────────────────────────────────────────────┐
│ 3. 解析 manifest-list (Avro 文件)                               │
│    - 根据 snapshot.manifest-list 路径下载 Avro 文件             │
│    - 使用 fastavro 解析，提取所有 manifest 文件路径              │
│    - [缓存] 同一请求内相同 manifest-list 仅下载一次              │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           ▼
┌───────────────────────────────────────────────────────────────┐
│ 4. 解析 manifest 文件 (Avro 文件)                               │
│    - 对每个 manifest 文件下载并解析                              │
│    - 提取 data file 条目: file_path、file_format、              │
│      partition、record_count、file_size_in_bytes、              │
│      lower_bounds/upper_bounds/null_value_counts               │
│    - 检测 delete files（不支持时拒绝请求）                      │
│    - [缓存] 同一请求内相同 manifest 仅下载一次                   │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           ▼
┌───────────────────────────────────────────────────────────────┐
│ 5. Schema 转换                                                 │
│    - IcebergSchemaConverter: Iceberg types → JSON Schema       │
│    - 支持: int/long/float/double/string/boolean/binary/        │
│      date/time/timestamp/decimal/struct/list/map               │
│    - 生成 PySpark 兼容的 JSON Schema 字符串                     │
│    - 提取 partition_columns 列表                                │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           ▼
┌───────────────────────────────────────────────────────────────┐
│ 6. 谓词过滤 (Predicate Pushdown & Partition Pruning)            │
│    - 解析 predicateHints (Spark 语法: "column > 100")          │
│    - 解析 jsonPredicateHints (JSON 结构化谓词)                  │
│    - 分区裁剪: 基于分区列值过滤无关分区                          │
│    - 文件级过滤: 基于 lower_bounds/upper_bounds/nullCount      │
│      精确判断每个文件是否可能包含匹配数据                        │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           ▼
┌───────────────────────────────────────────────────────────────┐
│ 7. 生成预签名 URL 并构建响应                                    │
│    - 为过滤后的文件通过 COSClient 生成预签名 URL                 │
│    - 构建 NDJSON 响应: protocol → metaData → file objects      │
│    - 注入 Delta-Table-Version 和 Delta-Sharing-Capabilities    │
│      等响应头                                                   │
└───────────────────────────────────────────────────────────────┘
```

---

## 谓词下推详解

### 支持的谓词格式

**1. predicateHints（Spark 语法字符串列表）**

```
["column_a > 100", "column_b = 'value'", "column_c IS NOT NULL"]
```

解析器支持以下操作符：`=`, `!=`, `<>`, `>`, `>=`, `<`, `<=`, `IS NULL`, `IS NOT NULL`, `IN (...)`, `NOT IN (...)`, `LIKE`, `NOT LIKE`, `BETWEEN`, `NOT BETWEEN`。

**2. jsonPredicateHints（JSON 结构化谓词）**

```json
{
  "op": "and",
  "children": [
    {"op": "gt", "name": "column_a", "value": 100},
    {"op": "eq", "name": "column_b", "value": "active"}
  ]
}
```

支持逻辑操作符：`and`、`or`、`not`；比较操作符：`eq`、`neq`、`gt`、`gte`、`lt`、`lte`、`isNull`、`isNotNull`、`in`、`notIn`。

### 分区裁剪（Partition Pruning）

当请求谓词涉及分区列时，通过以下几个步骤减少需要读取的数据文件：

1. 从 Iceberg partition-spec 中提取分区列信息
2. 从每个 data file 的 `partition` 字段中提取分区值
3. 将谓词中的引用列名与分区列名进行匹配
4. 如果某文件的分区值不满足谓词条件，跳过该文件的所有内容

例如，表按 `ds` 分区，查询 `ds > '2024-01-01'` 时，仅读取 `ds` 分区值大于 `'2024-01-01'` 的文件。

### 文件级统计过滤

对于分区裁剪之后仍保留的文件，利用 Iceberg manifest 中每个 data file 的统计信息进行更细粒度的过滤：

| 统计字段 | 用途 |
|---------|------|
| `lower_bounds` | 列的最小值（用于 `>`、`>=`、`BETWEEN` 等判断） |
| `upper_bounds` | 列的最大值（用于 `<`、`<=`、`BETWEEN` 等判断） |
| `null_value_counts` | NULL 值计数（用于 `IS NULL`、`IS NOT NULL` 判断） |

**示例**：查询 `column_a = 500`，某文件统计信息 `lower_bounds['column_a'] = 1000`，则该文件必定不含目标数据，直接跳过。

### 统一过滤入口

[PredicateService.filter_files()](file:///c:/MOKURO/DEVELOP/Code/Project/delta_sharing_iceberg/server/app/services/predicate_service.py) 提供统一的过滤入口，将分区裁剪和文件级统计过滤合并为单次调用，以最大化 I/O 避免。

---

## 缓存机制

服务端使用基于 `ContextVar` 的请求级缓存，确保同一 HTTP 请求内避免对同一 COS 对象的重复下载。

### 三个缓存区

| 缓存区 | 缓存键 | 缓存内容 |
|--------|--------|---------|
| `metadata_content_cache` | COS 路径 | metadata.json 解析后的字典 |
| `manifest_list_cache` | COS 路径 | manifest-list Avro 解析后的 manifest 文件路径列表 |
| `manifest_cache` | COS 路径 | manifest Avro 解析后的数据文件条目列表 |

### 生命周期

```
请求开始 → CacheMiddleware.initialize()  # 创建空缓存字典
         → Service 层读写缓存（get/set）
请求结束 → CacheMiddleware.clear()       # 释放缓存内存（finally 保证异常路径也清理）
```

---

## License

本项目采用 [MIT License](LICENSE) 开源协议。

Copyright (c) 2025 delta-sharing-iceberg contributors
