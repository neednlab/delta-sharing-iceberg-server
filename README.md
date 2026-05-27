# Delta Sharing Server for Iceberg Tables

[![中文文档](./assets/Docs-CN.svg)](./README_CN.md)

---

## Project Overview

This project implements the standard Delta Sharing protocol, and on top of the official support for Delta Lake table format only, **adds full support for the Apache Iceberg table format**. The service parses Iceberg table metadata and generates a list of files with object storage pre-signed URLs to return to clients.

> **Protocol Reference**: The overall implementation follows the official [Delta Sharing Protocol](https://github.com/delta-io/delta-sharing/blob/main/PROTOCOL.md) specification, including REST API design, data exchange formats, authentication mechanisms, etc.

Currently supports Iceberg tables based on Tencent Cloud DLC and COS object storage, with expandability to other metastores in the future.

### Core Features

- **✅ Iceberg Table Format Support**: Parses the Iceberg metadata layer (metadata / manifest-list / manifest) to extract Parquet data files
- **✅ Tencent Cloud COS Integration**: Automatically generates COS pre-signed URLs, allowing clients to download Parquet files directly
- **✅ Tencent Cloud DLC Integration**: Automatically queries Iceberg table `metadata_location` paths via DLC API, and retrieves DLC database and table schemas
- **✅ Recipient-Share Authorization System**: Fine-grained Share-level access control
- **✅ Predicate Pushdown & Partition Pruning**: Supports `predicateHints` and `jsonPredicateHints`, leveraging file-level statistics for filtering
- **✅ Time Travel Queries**: Query historical snapshot data based on version or timestamp

---

## System Architecture

### Layered Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    API Layer                             │
│  ┌──────────────────────┐  ┌──────────────────────────┐ │
│  │  Data Plane Routes   │  │     Admin API Routes     │ │
│  │  (Delta Sharing      │  │  (/admin/v1/*)          │ │
│  │   Protocol)          │  │  /recipients             │ │
│  │  /shares             │  │  /shares                 │ │
│  │  /.../metadata       │  │  /tokens                 │ │
│  │  /.../query          │  │  /sync/tables            │ │
│  │  /.../version        │  │  /audit-logs             │ │
│  │  /health             │  │                          │ │
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
│  │(8      │ │(YAML) │ │(CtxVar│ │(29   │ │(JSONL)   │  │
│  │ tables)│ │       │ │ 3     │ │error │ │          │  │
│  │        │ │       │ │ zones)│ │codes)│ │          │  │
│  └────────┘ └───────┘ └───────┘ └──────┘ └──────────┘  │
│  ┌────────────┐ ┌──────────┐ ┌───────────────────┐      │
│  │   Auth     │ │    COS   │ │       DLC         │      │
│  │ (SHA-256)  │ │  Client  │ │     Client        │      │
│  └────────────┘ └──────────┘ └───────────────────┘      │
└─────────────────────────────────────────────────────────┘
```

### Request Lifecycle

```
Client → CORS Middleware → CacheMiddleware → AuditLoggingMiddleware
    → Exception Handlers → Route Handler → Service → Repository → SQLite/COS/DLC
```

### Middleware Execution Order

1. **CORSMiddleware** — Cross-origin request handling
2. **CacheMiddleware** — Request-level cache (ContextVar) initialization and cleanup
3. **AuditLoggingMiddleware** — Raw ASGI middleware, intercepts response body to record audit logs
4. **Exception Handlers** — Three-tier exception catching: DeltaSharingError → HTTPException → generic Exception

---

## Quick Start

### Requirements

- Python >= 3.12
- uv package manager (recommended)

### Installation & Startup

```bash
# 1. Navigate to the server directory
cd server

# 2. Install dependencies
uv sync

# 3. Configure environment variables
# Create a .env.local file and set Tencent Cloud credentials
echo "COS_SECRET_ID=your-secret-id" > .env.local
echo "COS_SECRET_KEY=your-secret-key" >> .env.local
echo "DLC_SECRET_ID=your-secret-id" >> .env.local
echo "DLC_SECRET_KEY=your-secret-key" >> .env.local

# 4. Start the server (default listen on 0.0.0.0:8088)
uv run python main.py
```

Once the server starts, the API root path is `/delta-sharing`.

### Quick Verification

```bash
# Health check
curl http://localhost:8088/health

# Expected output
# {"status": "healthy"}
```

---

## API Reference

### Data Plane API (Delta Sharing Protocol)

All Data Plane APIs require the `Authorization: Bearer <token>` request header.

| Method | Path | Description |
|------|------|------|
| `GET` | `/shares` | List all Shares accessible to the current Recipient |
| `GET` | `/shares/{share}` | Get details of a specific Share |
| `GET` | `/shares/{share}/schemas` | List all Schemas under a Share |
| `GET` | `/shares/{share}/schemas/{schema}/tables` | List all Tables under a Schema |
| `GET` | `/shares/{share}/all-tables` | List all Tables under a Share (cross-Schema) |
| `GET` | `/shares/{share}/schemas/{schema}/tables/{table}/metadata` | Get table metadata (Schema, partition columns, etc.) |
| `GET` | `/shares/{share}/schemas/{schema}/tables/{table}/version` | Get the current/historical version number of a table |
| `POST` | `/shares/{share}/schemas/{schema}/tables/{table}/query` | Query table data files (returns a list of pre-signed URLs) |

#### Pagination Support

The `/shares`, `/schemas`, `/tables`, and `/all-tables` endpoints support pagination via `maxResults` and `pageToken`. `pageToken` is a Base64-encoded next-page token returned in the previous page's response.

#### Version Query

`GET /.../version` supports the following query parameters:

| Parameter | Description |
|------|------|
| None | Returns the current latest version number |
| `timestamp` | ISO8601 format, returns the version closest to but not exceeding this timestamp |
| `startingTimestamp` | ISO8601 format, returns the first version after this timestamp |

The response header includes the `Delta-Table-Version` field.

#### Table Query

`POST /.../query` supports filtering and limiting of data files. Request body fields:

| Field | Type | Description |
|------|------|------|
| `predicateHints` | `string[]` | List of Spark predicate syntax strings (e.g., `["column > 100"]`) |
| `jsonPredicateHints` | `string` | JSON-formatted predicates, supporting more complex filter conditions |
| `limitHint` | `int` | Upper limit on the number of files returned |
| `version` | `int` | Time travel query by version number |
| `timestamp` | `string` | Time travel query by ISO8601 timestamp |
| `startingVersion` | `int` | Version range query (start) |
| `endingVersion` | `int` | Version range query (end) |

The response is in NDJSON (Newline Delimited JSON) format, containing in order:
1. `protocol` object
2. `metaData` object (containing schemaString, partitionColumns, etc.)
3. Multiple `file` objects (each containing pre-signed URL, partition values, statistics, etc.)

The request header `delta-sharing-capabilities` can be used to specify the response format:

- `responseFormat=parquet` — Standard Parquet format (default)
- `responseFormat=delta` — Delta Lake format (includes DeltaProtocol, DeltaMetadata)
- `readerFeatures=...` — Declares features supported by the client
- `includeEndStreamAction=true` — Appends an EndStreamAction at the end of the response

#### Error Response Format

All error responses include the following fields:

```json
{
  "errorCode": "SHARE_NOT_FOUND",
  "message": "Share not found: myshare"
}
```

Error code categories:

| Category | Error Codes | HTTP Status Code |
|------|--------|------------|
| Authentication | `AUTHENTICATION_HEADER_MISSING`, `AUTHENTICATION_HEADER_INVALID`, `INVALID_TOKEN`, `TOKEN_MALFORMED` | 401 |
| Authorization | `TOKEN_EXPIRED`, `TOKEN_REVOKED`, `ACCESS_DENIED`, `SHARE_ACCESS_DENIED` | 403 |
| Resource | `SHARE_NOT_FOUND`, `SCHEMA_NOT_FOUND`, `TABLE_NOT_FOUND`, `RECIPIENT_NOT_FOUND`, `AUTHORIZATION_NOT_FOUND`, `RESOURCE_DOES_NOT_EXIST` | 404 |
| Business | `RECIPIENT_ALREADY_EXISTS`, `SHARE_ALREADY_EXISTS`, `SCHEMA_ALREADY_EXISTS`, `TABLE_ALREADY_EXISTS`, `AUTHORIZATION_ALREADY_EXISTS`, `MAX_TOKENS_EXCEEDED`, `TABLE_NOT_SUPPORTED`, `RECIPIENT_INACTIVE`, `NO_SHARES_ASSIGNED`, `INVALID_PARAMETER_VALUE` | 400/409 |
| System | `INTERNAL_ERROR`, `COS_ACCESS_ERROR`, `DLC_NOT_CONFIGURED`, `DLC_API_ERROR` | 500 |

---

### Admin API (Management Interface)

The management API path prefix is `/delta-sharing/admin/v1`, used for managing Recipients, Share authorizations, Tokens, Share entities, etc.

#### Recipient Management

| Method | Path | Description |
|------|------|------|
| `POST` | `/recipients` | Create a Recipient (parameters: name, comment) |
| `GET` | `/recipients` | List all Recipients (supports pagination) |
| `GET` | `/recipients/{name}` | Get details of a specific Recipient |
| `PUT` | `/recipients/{name}` | Update Recipient (activate/deactivate/modify comment) |
| `DELETE` | `/recipients/{name}` | Delete Recipient (cascade deletes associated tokens, authorizations) |

#### Share Authorization Management

| Method | Path | Description |
|------|------|------|
| `POST` | `/recipients/{name}/shares` | Grant Share access to a Recipient (parameter: share_name) |
| `GET` | `/recipients/{name}/shares` | Query all authorized Shares for a Recipient |
| `DELETE` | `/recipients/{name}/shares/{share_name}` | Revoke a Recipient's access to a specific Share |

#### Token Management

| Method | Path | Description |
|------|------|------|
| `POST` | `/recipients/{name}/tokens` | Generate a new Token (max 2 valid Tokens per Recipient) |
| `GET` | `/recipients/{name}/tokens` | List all Tokens for a Recipient (including revoked/expired state) |
| `DELETE` | `/recipients/{name}/tokens` | Revoke all Tokens for a Recipient |
| `DELETE` | `/recipients/{name}/tokens/{token}` | Revoke a specific Token |
| `GET` | `/recipients/{name}/tokens/profile` | Download Profile file (one-time use, destroyed immediately after download) |

#### Share Entity Management

| Method | Path | Description |
|------|------|------|
| `POST` | `/shares` | Create a Share |
| `GET` | `/shares` | List all Shares |
| `GET` | `/shares/{name}` | Get Share details |
| `DELETE` | `/shares/{name}` | Delete a Share |
| `POST` | `/shares/{name}/schemas` | Add a Schema asset |
| `GET` | `/shares/{name}/schemas` | List Schema assets |
| `POST` | `/shares/{name}/schemas/{schema}/tables` | Add a Table asset |
| `GET` | `/shares/{name}/schemas/{schema}/tables` | List Table assets |
| `PUT` | `/shares/{name}/schemas/{schema}/tables/{table}` | Update a Table asset |
| `DELETE` | `/shares/{name}/schemas/{schema}/tables/{table}` | Delete a Table asset |

#### DLC Table Sync

| Method | Path | Description |
|------|------|------|
| `POST` | `/sync/tables` | Sync table metadata from Tencent Cloud DLC to local database |

Two sync modes are supported:
- **full**: Full replacement, deletes existing tables and re-syncs
- **append**: Incremental append, preserves existing tables and adds new ones

#### Audit Log Query

| Method | Path | Description |
|------|------|------|
| `GET` | `/audit-logs` | Get audit log type list (admin, client) |
| `GET` | `/audit-logs/{type}` | Paginated query of audit logs by type |

Supports multi-column fuzzy match filter parameters: `recipient_id`, `share`, `schema`, `table`, `operation`, `http_method`.

#### Configuration Query

| Method | Path | Description |
|------|------|------|
| `GET` | `/config` | Get frontend Token configuration (does not expose full config) |

---

## Database Model

The system uses SQLite (via SQLAlchemy 2.0 Core API) to store 8 business tables:

### ER Diagram

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
       │          ├───►│  (authorization        │              │
       │          │    │   relationship table)   │              │
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
  │ location (COS path)│               │ id                      PK │  │
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

### Table Descriptions

| Table Name | Description | Key Fields |
|------|------|---------|
| `shares` | Shared resource definition | `share_name` (unique), `display_name`, `properties` |
| `shared_schemas` | Shared Schema definition | Linked to Share via `share_id`, includes `metastore_db` |
| `shared_tables` | Shared Table definition | COS `location`, `metastore_db`/`metastore_table` (for DLC queries) |
| `recipients` | Data recipients | `recipient_name` (unique), `is_active` (soft enable/disable) |
| `recipient_shares` | Authorization relationships | `recipient_id` + `share_id` unique constraint |
| `bearer_tokens` | Bearer Token credentials | `token_hash` (SHA-256), `profile_content` |
| `token_revocation` | Token revocation records | `token_hash` + `revoked_at` + `reason` |
| `snapshot_version` | Snapshot version tracking | `(share_name, schema_name, table_name, snapshot_id)` unique constraint |

### Table Binding Modes

The system supports two Table binding modes:

1. **Linked Schema Binding**: Table is linked to `shared_schemas` via `linked_schema_id`, inheriting the Schema's `metastore_db`
2. **Direct Share Binding**: Table is linked directly via `share_id`, with self-contained fields

The Repository layer automatically merges tables from both modes during queries.

---

## Security Mechanisms

### Bearer Token Authentication Flow

```
┌──────────┐                    ┌──────────────┐              ┌──────────┐
│  Admin   │                    │  Delta        │              │  SQLite  │
│  (Mgmt)  │                    │  Sharing      │              │  Database│
└────┬─────┘                    │  Server       │              └────┬─────┘
     │                          └──────┬───────┘                   │
     │  1. Create Recipient            │                           │
     │────────────────────────────────►│                           │
     │                                 │  INSERT INTO recipients   │
     │                                 │──────────────────────────►│
     │                                 │                           │
     │  2. Grant Share Access          │                           │
     │────────────────────────────────►│                           │
     │                                 │  INSERT INTO              │
     │                                 │  recipient_shares         │
     │                                 │──────────────────────────►│
     │                                 │                           │
     │  3. Generate Token              │                           │
     │────────────────────────────────►│                           │
     │                                 │  token = secrets.token()  │
     │                                 │  token_hash = SHA-256()   │
     │                                 │  INSERT token_hash        │
     │                                 │  (plaintext never stored) │
     │                                 │──────────────────────────►│
     │  Returns: token plaintext +     │                           │
     │  profile                        │                           │
     │◄────────────────────────────────│                           │
     │                                 │                           │
     │  4. Distribute token + profile  │                           │
     │     to client                   │                           │
     │                                 │                           │
┌────┴─────┐                          │                           │
│  Client  │  5. API request + Bearer │                           │
│          │     token               │                           │
└────┬─────┘─────────────────────────►│                           │
     │                                 │  SHA-256(token)           │
     │                                 │  SELECT token_hash        │
     │                                 │──────────────────────────►│
     │                                 │◄── token_info ────────────│
     │                                 │                           │
     │                                 │  Verify:                  │
     │                                 │  - token exists           │
     │                                 │  - not revoked            │
     │                                 │  - not expired            │
     │                                 │  - recipient is active    │
     │                                 │                           │
     │  Returns data or error response │                           │
     │◄────────────────────────────────│                           │
```

### Security Design Highlights

- **Token Plaintext Never Stored**: Only SHA-256 hash is stored; the original Token is returned only once upon generation
- **Single Database Query Authentication**: `validate_token()` performs all state checks in a single query
- **404 Security Obfuscation**: Non-existent tokens and expired tokens return the same error, preventing information leakage
- **WWW-Authenticate Header**: 401 authentication-related errors automatically include the `WWW-Authenticate: Bearer` response header
- **Token Quota Control**: Each Recipient can hold at most 2 valid Tokens (configurable)
- **Profile One-Time Download**: Profile file is destroyed from the server immediately after download
- **Recipient Soft Delete**: Delete operations only set `is_active=0`, preserving audit trail
- **COS Pre-Signed URLs**: Data files do not transit through the server; clients download directly from COS via time-limited URLs

---

## Configuration Guide

### Configuration File Structure (config.yaml)

```yaml
# Server configuration
server:
  host: "0.0.0.0"
  port: 8088
  admin_host: "127.0.0.1"
  admin_port: 8089
  api_prefix: "/delta-sharing"

# Tencent Cloud COS configuration
cos:
  region: "ap-shanghai"
  secret_id: "${COS_SECRET_ID}"       # Supports ${ENV_VAR} environment variable references
  secret_key: "${COS_SECRET_KEY}"
  endpoint: "cos.ap-shanghai.myqcloud.com"

# Tencent Cloud DLC configuration
dlc:
  region: "ap-shanghai"
  secret_id: "${DLC_SECRET_ID}"       # Supports ${ENV_VAR} environment variable references
  secret_key: "${DLC_SECRET_KEY}"

# Database configuration
database:
  url: "sqlite:///./data/server.db"   # Also supports PostgreSQL and other databases

# Token configuration
token:
  rotation_period_hours: 24          # Token rotation period
  max_tokens_per_recipient: 2        # Max valid Tokens per Recipient
  expiration_hours: 168              # Default Token expiration time (7 days)

# COS pre-signed URL configuration
presigned_url:
  expiration_hours: 6                # Default expiration time
  min_expiration_hours: 1            # Minimum expiration time
  max_expiration_hours: 168          # Maximum expiration time

# Share configuration
shares:
  use_database: true                 # true=database mode, false=pure config mode
  fallback_file: "./config.yaml"     # Fallback file for config mode
  myshare:                           # Example Share definition (effective when use_database=false)
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

# Logging configuration
logging:
  log_dir: "./log"
  app_log_level: "INFO"              # DEBUG / INFO / WARNING / ERROR
  app_log_retention: "30 days"       # Log retention period
  audit_log_level: "INFO"            # Audit log level
```

### Environment Variables

| Variable | Description | Required |
|--------|------|------|
| `COS_SECRET_ID` | Tencent Cloud COS SecretId | Yes |
| `COS_SECRET_KEY` | Tencent Cloud COS SecretKey | Yes |
| `DLC_SECRET_ID` | Tencent Cloud DLC SecretId (required for DLC features) | No |
| `DLC_SECRET_KEY` | Tencent Cloud DLC SecretKey (required for DLC features) | No |
| `DLC_REGION` | Tencent Cloud DLC region (e.g., `ap-shanghai`) | No |
| `DLC_ENDPOINT` | Tencent Cloud DLC API endpoint (overrides default) | No |
| `PAGE_TOKEN_SECRET` | Page Token HMAC signing key, must be set in production | No |

### Two Management Modes

**Database Mode (Recommended)**: `shares.use_database: true`

- Shares, Schemas, and Tables are managed via the Admin API
- Supports automatic table metadata sync via DLC
- Share authorization managed through the `recipient_shares` table

**Pure Config Mode (Development/Simple Scenarios)**: `shares.use_database: false`

- Share definitions are written directly in the `shares` section of `config.yaml`
- Configuration is automatically synced to the database on startup
- Suitable for rapid development and testing

---

## Development Guide

### Project Directory Structure

```
server/
├── main.py                          # Application entry point
├── config.yaml                      # Main configuration file
├── pyproject.toml                   # Project dependencies & tool configuration
├── data/
│   └── server.db                    # SQLite database file
├── log/
│   ├── app_2024-05-11.jsonl         # Application logs (daily rotation)
│   ├── admin_audit_2024-05-11.jsonl # Admin audit logs
│   └── client_audit_2024-05-11.jsonl# Client audit logs
├── app/
│   ├── core/                        # Core modules
│   │   ├── config.py                # Configuration management (YAML + environment variables)
│   │   ├── database.py              # SQLAlchemy Core database engine (8 table definitions)
│   │   ├── cache.py                 # Request-level cache (ContextVar, 3 cache zones)
│   │   ├── errors.py                # Error definitions (29 error code enums)
│   │   ├── authentication.py        # Bearer Token authentication (SHA-256)
│   │   ├── audit.py                 # Audit logging (dual stream, JSONL, daily rotation)
│   │   ├── delta_capabilities.py    # Delta Sharing Capabilities parsing
│   │   ├── cos_client.py            # Tencent Cloud COS client wrapper
│   │   ├── dlc_client.py            # Tencent Cloud DLC client wrapper
│   │   └── logging_config.py        # Loguru global logging configuration
│   ├── models/                      # Data models (Pydantic)
│   │   ├── share.py                 # Share/Schema/Table response models
│   │   ├── query.py                 # Query request/response models
│   │   └── profile.py               # Profile file model
│   ├── repositories/                # Data access layer
│   │   ├── share_repository.py      # Share/Schema/Table CRUD
│   │   ├── recipient_repository.py  # Recipient CRUD
│   │   ├── recipient_share_repository.py  # Authorization relationship management
│   │   ├── token_repository.py      # Token CRUD + Profile management
│   │   └── version_repository.py    # Snapshot version tracking
│   ├── services/                    # Business logic layer
│   │   ├── share_service.py         # Share queries (pagination, recipient filtering)
│   │   ├── iceberg_service.py       # Iceberg metadata parsing + Schema conversion
│   │   ├── predicate_service.py     # Predicate pushdown + partition pruning
│   │   ├── version_service.py       # Version management (time travel)
│   │   ├── authorization_service.py # Authorization management
│   │   ├── recipient_service.py     # Recipient management
│   │   ├── token_service.py         # Token management
│   │   └── table_service.py         # Table configuration queries
│   ├── routes/                      # Data Plane API routes
│   │   ├── __init__.py              # Route exports
│   │   ├── shares.py                # Share/Schema/Table listing endpoints
│   │   ├── metadata.py              # Table metadata endpoint
│   │   ├── query.py                 # Table query endpoint
│   │   ├── version.py               # Table version endpoint
│   │   └── health.py                # Health check endpoint
│   ├── api/                         # Admin API
│   │   └── admin/
│   │       ├── __init__.py          # Admin route aggregation (/admin/v1)
│   │       ├── recipients.py        # Recipient management endpoints
│   │       ├── shares.py            # Share authorization management endpoints
│   │       ├── tokens.py            # Token management endpoints
│   │       ├── share_management.py  # Share entity management endpoints
│   │       ├── sync.py              # DLC table sync endpoint
│   │       ├── audit_logs.py        # Audit log query endpoints
│   │       └── config.py            # Frontend configuration query endpoint
│   └── utils/                       # Utility modules
│       ├── request_utils.py         # Request utilities (IP extraction, etc.)
│       ├── response_utils.py        # Response utilities (NDJSON generation, etc.)
│       ├── time_utils.py            # Time utilities (ISO8601 parsing, etc.)
│       ├── page_token_utils.py      # Page Token HMAC encoding/decoding
│       └── audit_utils.py           # Audit utilities (error throwing with audit)
└── tests/                           # Tests
    ├── conftest.py                   # pytest fixtures (database, client, etc.)
    ├── test_core.py                  # Core module tests
    ├── test_routes.py                # Route integration tests
    ├── test_authz.py                 # Authentication & authorization E2E tests
    ├── test_audit.py                 # Audit log tests
    ├── test_cache.py                 # Request-level cache tests
    ├── test_delta_capabilities.py    # Delta Sharing Capabilities tests
    ├── test_dlc_client.py            # DLC client tests
    ├── test_page_token_utils.py      # Page Token encoding/decoding tests
    ├── test_predicate_service.py     # Predicate pushdown service tests
    ├── test_schema_asset.py          # Schema asset management tests
    ├── test_time_utils.py            # Time utility tests
    └── test_version.py               # Version service tests
```

---

## Technology Stack & Dependencies

### Runtime Dependencies

| Dependency | Version | Purpose |
|------|------|------|
| [FastAPI](https://fastapi.tiangolo.com/) | >= 0.115.0 | Web framework providing REST API and auto documentation |
| [Uvicorn](https://www.uvicorn.org/) | >= 0.30.0 | ASGI server |
| [SQLAlchemy](https://www.sqlalchemy.org/) | >= 2.0.49 | Database ORM (using Core API, not ORM) |
| [PyIceberg](https://py.iceberg.apache.org/) | >= 0.5.0 | Apache Iceberg table metadata parsing |
| [fastavro](https://fastavro.readthedocs.io/) | >= 1.12.2 | Avro file parsing (manifest-list / manifest) |
| [avro](https://avro.apache.org/) | >= 1.11.0 | Apache Avro format parsing (Iceberg metadata layer) |
| [cos-python-sdk-v5](https://github.com/tencentyun/cos-python-sdk-v5) | >= 1.9.0 | Tencent Cloud COS SDK (pre-signed URL generation) |
| [tencentcloud-sdk-python](https://github.com/TencentCloud/tencentcloud-sdk-python) | >= 3.1.76 | Tencent Cloud DLC SDK (metadata location queries) |
| [Pydantic](https://docs.pydantic.dev/) | >= 2.0.0 | Data validation and serialization |
| [PyYAML](https://pyyaml.org/) | >= 6.0 | YAML configuration file parsing |
| [loguru](https://loguru.readthedocs.io/) | >= 0.7.3 | Log management (console color + file JSONL) |
| [python-multipart](https://github.com/Kludex/python-multipart) | >= 0.0.12 | Form data parsing (FastAPI dependency) |
| [httpx](https://www.python-httpx.org/) | >= 0.27.0 | HTTP client (for testing) |

### Development Dependencies

| Dependency | Version | Purpose |
|------|------|------|
| [pytest](https://pytest.org/) | >= 8.0.0 | Testing framework |
| [pytest-asyncio](https://pytest-asyncio.readthedocs.io/) | >= 0.24.0 | AsyncIO testing support |
| [pytest-cov](https://pytest-cov.readthedocs.io/) | >= 4.0.0 | Test coverage reporting |

### Python Version

- Minimum requirement: **Python 3.12**
- Package manager: **uv** (recommended to use `uv sync` and `uv run`)

---

## Iceberg Metadata Resolution Pipeline

When querying Iceberg table data, the complete metadata resolution pipeline executed by the server:

```
                         ┌──────────────────────┐
                         │  DLC API             │
                         │  (DescribeTable)      │
                         │                       │
                         │  Returns metadata_    │
                         │  location             │
                         └──────────┬───────────┘
                                    │
                                    ▼
┌───────────────────────────────────────────────────────────────┐
│ 1. Retrieve metadata.json content                             │
│    - Download the Iceberg table root metadata file via COS     │
│      get_object                                               │
│    - Parse JSON, extract: schemas, partition-specs, snapshots │
│    - [Cache] Same metadata path downloaded only once per      │
│      request                                                  │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           ▼
┌───────────────────────────────────────────────────────────────┐
│ 2. Select Snapshot                                            │
│    - Default: use current-snapshot-id                         │
│    - Version query: reverse-lookup snapshot_id by version     │
│      number                                                   │
│    - Timestamp query: find nearest snapshot by timestamp      │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           ▼
┌───────────────────────────────────────────────────────────────┐
│ 3. Parse manifest-list (Avro file)                            │
│    - Download Avro file based on snapshot.manifest-list path  │
│    - Parse with fastavro, extract all manifest file paths     │
│    - [Cache] Same manifest-list downloaded only once per      │
│      request                                                  │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           ▼
┌───────────────────────────────────────────────────────────────┐
│ 4. Parse manifest files (Avro files)                          │
│    - Download and parse each manifest file                    │
│    - Extract data file entries: file_path, file_format,       │
│      partition, record_count, file_size_in_bytes,             │
│      lower_bounds/upper_bounds/null_value_counts              │
│    - Detect delete files (reject request if unsupported)      │
│    - [Cache] Same manifest downloaded only once per request   │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           ▼
┌───────────────────────────────────────────────────────────────┐
│ 5. Schema Conversion                                          │
│    - IcebergSchemaConverter: Iceberg types → JSON Schema      │
│    - Supports: int/long/float/double/string/boolean/binary/   │
│      date/time/timestamp/decimal/struct/list/map              │
│    - Generates PySpark-compatible JSON Schema string          │
│    - Extracts partition_columns list                          │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           ▼
┌───────────────────────────────────────────────────────────────┐
│ 6. Predicate Filtering (Predicate Pushdown & Partition        │
│    Pruning)                                                   │
│    - Parse predicateHints (Spark syntax: "column > 100")      │
│    - Parse jsonPredicateHints (JSON structured predicates)    │
│    - Partition pruning: filter irrelevant partitions based on │
│      partition column values                                  │
│    - File-level filtering: based on lower_bounds/upper_bounds/│
│      nullCount to accurately determine if each file may       │
│      contain matching data                                    │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           ▼
┌───────────────────────────────────────────────────────────────┐
│ 7. Generate Pre-Signed URLs and Build Response                │
│    - Generate pre-signed URLs for filtered files via          │
│      COSClient                                                │
│    - Build NDJSON response: protocol → metaData → file objects│
│    - Inject Delta-Table-Version and Delta-Sharing-Capabilities│
│      response headers                                         │
└───────────────────────────────────────────────────────────────┘
```

---

## Predicate Pushdown Details

### Supported Predicate Formats

**1. predicateHints (Spark syntax string list)**

```
["column_a > 100", "column_b = 'value'", "column_c IS NOT NULL"]
```

The parser supports the following operators: `=`, `!=`, `<>`, `>`, `>=`, `<`, `<=`, `IS NULL`, `IS NOT NULL`, `IN (...)`, `NOT IN (...)`, `LIKE`, `NOT LIKE`, `BETWEEN`, `NOT BETWEEN`.

**2. jsonPredicateHints (JSON structured predicates)**

```json
{
  "op": "and",
  "children": [
    {"op": "gt", "name": "column_a", "value": 100},
    {"op": "eq", "name": "column_b", "value": "active"}
  ]
}
```

Supported logical operators: `and`, `or`, `not`; comparison operators: `eq`, `neq`, `gt`, `gte`, `lt`, `lte`, `isNull`, `isNotNull`, `in`, `notIn`.

### Partition Pruning

When request predicates involve partition columns, the number of data files to read is reduced through the following steps:

1. Extract partition column information from the Iceberg partition-spec
2. Extract partition values from each data file's `partition` field
3. Match referenced column names in predicates with partition column names
4. If a file's partition values do not satisfy the predicate conditions, skip all content in that file

For example, with a table partitioned by `ds`, a query `ds > '2024-01-01'` only reads files with `ds` partition values greater than `'2024-01-01'`.

### File-Level Statistics Filtering

For files retained after partition pruning, leverage the statistics of each data file in Iceberg manifests for more granular filtering:

| Statistics Field | Purpose |
|---------|------|
| `lower_bounds` | Column minimum value (for `>`, `>=`, `BETWEEN` judgments) |
| `upper_bounds` | Column maximum value (for `<`, `<=`, `BETWEEN` judgments) |
| `null_value_counts` | NULL value count (for `IS NULL`, `IS NOT NULL` judgments) |

**Example**: Query `column_a = 500`, with file statistics `lower_bounds['column_a'] = 1000`, the file definitely does not contain the target data and is skipped directly.

### Unified Filtering Entry

[PredicateService.filter_files()](file:///c:/MOKURO/DEVELOP/Code/Project/delta_sharing_iceberg/server/app/services/predicate_service.py) provides a unified filtering entry that combines partition pruning and file-level statistics filtering into a single call to maximize I/O avoidance.

---

## Caching Mechanism

The server uses a `ContextVar`-based request-level cache to ensure the same COS object is not downloaded repeatedly within a single HTTP request.

### Three Cache Zones

| Cache Zone | Cache Key | Cached Content |
|--------|--------|---------|
| `metadata_content_cache` | COS path | Parsed dictionary of metadata.json |
| `manifest_list_cache` | COS path | List of manifest file paths after manifest-list Avro parsing |
| `manifest_cache` | COS path | List of data file entries after manifest Avro parsing |

### Lifecycle

```
Request start → CacheMiddleware.initialize()  # Create empty cache dictionaries
              → Service layer reads/writes cache (get/set)
Request end   → CacheMiddleware.clear()       # Free cache memory (finally ensures cleanup even on exception paths)
```

---

## License

This project is open-sourced under the [Apache License, Version 2.0](LICENSE).

Copyright (c) 2025 delta-sharing-iceberg contributors
