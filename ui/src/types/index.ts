/**
 * 类型定义文件
 * 定义Share、Recipient、ShareObject等核心数据类型
 */

/**
 * Share对象类型
 */
export interface Share {
  share_id: string;
  share_name: string;
  display_name?: string;
  comment?: string;
  created_at?: number;
  updated_at?: number;
  properties?: Record<string, string>;
}

/**
 * Share列表响应
 */
export interface ShareListResponse {
  items: Share[];
  next_page_token?: string;
}

/**
 * 创建Share请求
 */
export interface CreateShareRequest {
  name: string;
  display_name?: string;
  comment?: string;
  properties?: Record<string, string>;
}

/**
 * 更新Share请求
 */
export interface UpdateShareRequest {
  new_name?: string;
  comment?: string;
}

/**
 * Recipient对象类型
 */
export interface Recipient {
  recipient_id: string;
  recipient_name: string;
  id?: string;  // 兼容旧字段
  name?: string;  // 兼容旧字段
  comment?: string;
  is_active: boolean;
  created_at?: number;
  updated_at?: number;
}

/**
 * Recipient列表响应
 */
export interface RecipientListResponse {
  items: Recipient[];
  next_page_token?: string;
}

/**
 * 创建Recipient请求
 */
export interface CreateRecipientRequest {
  name: string;
  comment?: string;
}

/**
 * 更新Recipient请求
 */
export interface UpdateRecipientRequest {
  newName?: string;
  comment?: string;
  isActive?: boolean;
}

/**
 * SchemaAsset 类型 - 表示共享的Schema资产
 */
export interface SchemaAsset {
  schema_id: string;
  share_name: string;
  schema_name: string;
  metastore_db: string;
}

/**
 * TableAsset 类型 - 表示共享的Table资产
 */
export interface TableAsset {
  table_id: string;
  share_name: string;
  linked_schema_id: string | null;
  schema_name: string;
  table_name: string;
  location: string;
  metastore_db: string;
  metastore_table: string;
  auxiliary_locations: string[];
}

/**
 * ShareObject对象类型（Schema或Table）
 */
export interface ShareObject {
  object_type: 'SCHEMA' | 'TABLE';
  object_name: string;
  added_at: string;
}

/**
 * ShareObject列表响应
 */
export interface ShareObjectListResponse {
  objects: ShareObject[];
  schemas?: SchemaAsset[];
  tables?: TableAsset[];
}

/**
 * 添加ShareObject请求
 */
export interface AddShareObjectRequest {
  schema_name?: string;
  table_name?: string;
  object_type?: 'SCHEMA' | 'TABLE';
  object_name?: string;
  metastore_db?: string;
  metastore_table?: string;
  location?: string;
  auxiliary_locations?: string[];
}

/**
 * 更新ShareObject请求
 */
export interface UpdateShareObjectRequest {
  schema_name?: string;
  metastore_db?: string;
  location?: string;
  metastore_table?: string;
  auxiliary_locations?: string[];
  new_schema_name?: string;
}

/**
 * Token响应
 */
export interface TokenResponse {
  bearerToken?: string;
  token?: string;
  tokenPrefix?: string;
  recipient_id?: string;
  expiresAt?: number;
  profileContent?: ProfileContent;
  message?: string;
}

/**
 * Profile文件内容
 */
export interface ProfileContent {
  shareCredentialsVersion: number;
  endpoint: string;
  bearerToken: string;
  expirationTime?: string;
}

/**
 * API错误响应
 */
export interface ApiError {
  errorCode?: string;
  message: string;
}

/**
 * 分页参数
 */
export interface PaginationParams {
  maxResults?: number;
  pageToken?: string;
}

/**
 * 同步表响应
 */
export interface SyncTablesResponse {
  mode: string;
  dlc_database: string;
  total_count: number;
  synced_count: number;
  skipped_count: number;
  deleted_count: number;
}

/**
 * Share 授权记录 - Recipient 被授予访问 Share 的记录
 */
export interface ShareGrant {
  share_name: string;
  granted_at: number;
}

/**
 * 审计日志列表响应 - 按日志类型分组的日期列表
 */
export interface AuditLogListResponse {
  admin_audit: string[];
  client_audit: string[];
  app: string[];
}

/**
 * 审计日志查询参数
 */
export interface AuditLogQueryParams {
  date: string;
  page?: number;
  page_size?: number;
  filters?: string;  // JSON字符串，如 '{"http.status_code":"40","operation":"GET"}'
}

/**
 * 审计日志条目 - 单条日志记录（字段不固定）
 */
export type AuditLogEntry = Record<string, string | number | boolean | null>;

/**
 * 审计日志查询响应 - 分页的日志条目
 */
export interface AuditLogQueryResponse {
  log_type: string;
  date: string;
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
  entries: AuditLogEntry[];
}

/**
 * 应用配置 - 从 GET /admin/v1/config 获取的前端配置子集
 */
export interface AppConfig {
  token: {
    max_tokens_per_recipient: number;
    rotation_period_hours: number;
    default_expiration_hours: number;
  };
}

/**
 * 登录请求
 */
export interface LoginRequest {
  username: string;
  password: string;
}

/**
 * 登录响应
 */
export interface LoginResponse {
  admin_id: string;
  username: string;
  display_name: string;
}

/**
 * 当前管理员信息（与 LoginResponse 结构一致）
 */
export type AdminInfo = LoginResponse;
