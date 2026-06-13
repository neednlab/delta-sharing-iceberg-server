/**
 * API服务层
 * 封装对后端ADMIN REST API的调用
 */

import type {
  Share,
  ShareListResponse,
  CreateShareRequest,
  Recipient,
  RecipientListResponse,
  CreateRecipientRequest,
  UpdateRecipientRequest,
  ShareObject,
  ShareObjectListResponse,
  AddShareObjectRequest,
  UpdateShareObjectRequest,
  TokenResponse,
  PaginationParams,
  ApiError,
  SyncTablesResponse,
  AuditLogListResponse,
  AuditLogQueryResponse,
  AuditLogQueryParams,
  AppConfig,
  ShareGrant,
  LoginRequest,
  LoginResponse,
  AdminInfo,
} from '../types';

/**
 * API基础URL
 * 使用相对路径，通过Vite代理转发到后端服务
 */
const API_BASE_URL = '/delta-sharing/admin/v1';

/**
 * 统一的 API fetch 封装，自动携带 credentials: 'include'
 * 确保浏览器随请求发送 HttpOnly Cookie（JWT admin_token）
 *
 * @param url - 请求 URL
 * @param options - fetch 选项
 * @returns fetch Response 对象
 */
async function apiFetch(url: string, options?: RequestInit): Promise<Response> {
  return fetch(url, {
    ...options,
    credentials: 'include',
  });
}

/**
 * 处理API响应
 * 先以文本形式读取响应体以确保正确消费 stream，
 * 避免浏览器对 204 等空响应报告 net::ERR_ABORTED
 *
 * @param response - fetch响应对象
 * @returns 解析后的JSON数据
 * @throws ApiError 当响应状态不为ok时抛出错误
 */
export async function handleResponse<T>(response: Response): Promise<T> {
  const text = await response.text();

  if (!response.ok) {
    let errorMessage = `HTTP ${response.status}: ${response.statusText}`;
    try {
      if (text) {
        const errorData = JSON.parse(text) as ApiError;
        errorMessage = errorData.message || errorMessage;
      }
    } catch {
      // 如果无法解析JSON错误，使用默认错误信息
    }
    throw new Error(errorMessage);
  }

  // 处理 204 No Content 或空响应体
  if (response.status === 204 || !text) {
    return {} as T;
  }

  return JSON.parse(text) as T;
}

/**
 * 构建带查询参数的URL
 * @param baseUrl - 基础URL
 * @param params - 查询参数对象
 * @returns 完整的URL字符串
 */
export function buildUrl(baseUrl: string, params?: Record<string, string | number | boolean | undefined>): string {
  if (!params) return baseUrl;

  const url = new URL(baseUrl, window.location.origin);
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      url.searchParams.append(key, String(value));
    }
  });

  return url.pathname + url.search;
}

/**
 * Share相关API
 */
export const shareApi = {
  /**
   * 获取Share列表
   * @param params - 分页参数
   * @returns Share列表响应
   */
  async getShares(params?: PaginationParams): Promise<ShareListResponse> {
    const url = buildUrl(`${API_BASE_URL}/shares`, {
      maxResults: params?.maxResults,
      pageToken: params?.pageToken,
    });

    const response = await apiFetch(url);
    return handleResponse<ShareListResponse>(response);
  },

  /**
   * 创建Share
   * @param data - 创建Share请求数据
   * @returns 创建的Share对象
   */
  async createShare(data: CreateShareRequest): Promise<Share> {
    const response = await apiFetch(`${API_BASE_URL}/shares`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(data),
    });
    return handleResponse<Share>(response);
  },

  /**
   * 更新Share名称
   * @param shareName - 当前Share名称
   * @param newName - 新Share名称
   * @returns 更新后的Share对象
   */
  async renameShare(shareName: string, newName: string): Promise<Share> {
    const response = await apiFetch(
      `${API_BASE_URL}/shares/${encodeURIComponent(shareName)}/rename`,
      {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ new_name: newName }),
      }
    );
    return handleResponse<Share>(response);
  },

  /**
   * 删除Share
   * @param shareName - Share名称
   */
  async deleteShare(shareName: string): Promise<void> {
    const response = await apiFetch(
      `${API_BASE_URL}/shares/${encodeURIComponent(shareName)}`,
      {
        method: 'DELETE',
      }
    );
    await handleResponse<void>(response);
  },

  /**
   * 获取Share的objects列表
   * @param shareName - Share名称
   * @returns ShareObject列表响应
   */
  async getShareObjects(shareName: string): Promise<ShareObjectListResponse> {
    const response = await apiFetch(
      `${API_BASE_URL}/shares/${encodeURIComponent(shareName)}/objects`
    );
    return handleResponse<ShareObjectListResponse>(response);
  },

  /**
   * 添加ShareObject
   * @param shareName - Share名称
   * @param data - 添加ShareObject请求数据
   * @returns 添加的ShareObject
   */
  async addShareObject(shareName: string, data: AddShareObjectRequest): Promise<ShareObject> {
    const response = await apiFetch(
      `${API_BASE_URL}/shares/${encodeURIComponent(shareName)}/objects`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(data),
      }
    );
    return handleResponse<ShareObject>(response);
  },

  /**
   * 更新ShareObject
   * @param shareName - Share名称
   * @param objectType - Object类型 (schema或table)
   * @param objectName - Object名称
   * @param data - 更新ShareObject请求数据
   * @returns 更新后的ShareObject
   */
  async updateShareObject(
    shareName: string,
    objectType: string,
    objectName: string,
    data: UpdateShareObjectRequest
  ): Promise<ShareObject> {
    const response = await apiFetch(
      `${API_BASE_URL}/shares/${encodeURIComponent(shareName)}/objects/${objectType}/${encodeURIComponent(objectName)}`,
      {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(data),
      }
    );
    return handleResponse<ShareObject>(response);
  },

  /**
   * 删除ShareObject
   * @param shareName - Share名称
   * @param objectType - Object类型 (schema或table)
   * @param objectName - Object名称
   * @param schemaName - Schema名称（删除table时需要，用于精确定位）
   */
  async deleteShareObject(
    shareName: string,
    objectType: string,
    objectName: string,
    schemaName?: string
  ): Promise<void> {
    const url = buildUrl(
      `${API_BASE_URL}/shares/${encodeURIComponent(shareName)}/objects/${objectType}/${encodeURIComponent(objectName)}`,
      { schema_name: schemaName || undefined }
    );
    const response = await apiFetch(url, {
      method: 'DELETE',
    });
    await handleResponse<void>(response);
  },

  /**
   * 同步Schema下的所有Table
   * @param shareName - Share名称
   * @param schemaName - Schema名称
   * @param dlcDatabase - DLC数据库名称（可选）
   * @returns 同步结果
   */
  async syncSchemaTables(
    shareName: string,
    schemaName: string,
    dlcDatabase?: string
  ): Promise<SyncTablesResponse> {
    const response = await apiFetch(`${API_BASE_URL}/sync/tables`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        share_name: shareName,
        schema_name: schemaName,
        dlc_database: dlcDatabase,
        mode: 'append',
      }),
    });
    return handleResponse<SyncTablesResponse>(response);
  },
};

/**
 * Recipient相关API
 */
export const recipientApi = {
  /**
   * 获取Recipient列表
   * @param params - 分页参数
   * @returns Recipient列表响应
   */
  async getRecipients(params?: PaginationParams): Promise<RecipientListResponse> {
    const url = buildUrl(`${API_BASE_URL}/recipients`, {
      maxResults: params?.maxResults,
      pageToken: params?.pageToken,
    });

    const response = await apiFetch(url);
    return handleResponse<RecipientListResponse>(response);
  },

  /**
   * 创建Recipient
   * @param data - 创建Recipient请求数据
   * @returns 创建的Recipient对象
   */
  async createRecipient(data: CreateRecipientRequest): Promise<Recipient> {
    const response = await apiFetch(`${API_BASE_URL}/recipients`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        name: data.name,
        comment: data.comment,
      }),
    });
    return handleResponse<Recipient>(response);
  },

  /**
   * 更新Recipient
   * @param name - Recipient名称
   * @param data - 更新Recipient请求数据
   * @returns 更新后的Recipient对象
   */
  async updateRecipient(name: string, data: UpdateRecipientRequest): Promise<Recipient> {
    const response = await apiFetch(`${API_BASE_URL}/recipients/${encodeURIComponent(name)}`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        newName: data.newName,
        comment: data.comment,
        isActive: data.isActive,
      }),
    });
    return handleResponse<Recipient>(response);
  },

  /**
   * 删除Recipient
   * @param name - Recipient名称
   */
  async deleteRecipient(name: string): Promise<void> {
    const response = await apiFetch(
      `${API_BASE_URL}/recipients/${encodeURIComponent(name)}`,
      {
        method: 'DELETE',
      }
    );
    await handleResponse<void>(response);
  },

  /**
   * 生成Recipient Token
   * @param name - Recipient名称
   * @param requireAuthorizedShares - 是否需要授权Share
   * @param expirationHours - Token过期小时数，undefined使用配置默认值，0表示永不过期
   * @returns Token响应
   */
  async generateToken(
    name: string,
    requireAuthorizedShares: boolean = false,
    expirationHours?: number
  ): Promise<TokenResponse> {
    const url = buildUrl(
      `${API_BASE_URL}/recipients/${encodeURIComponent(name)}/token`,
      {
        requireAuthorizedShares,
        expirationHours,
      }
    );

    const response = await apiFetch(url, {
      method: 'POST',
    });
    return handleResponse<TokenResponse>(response);
  },

  /**
   * 获取Recipient已授权的Share列表
   * @param name - Recipient名称
   * @returns 授权的Share列表
   */
  async getRecipientShares(name: string): Promise<{ items: Array<{ share_name: string; granted_at: number }> }> {
    const response = await apiFetch(
      `${API_BASE_URL}/recipients/${encodeURIComponent(name)}/shares`
    );
    return handleResponse<{ items: Array<{ share_name: string; granted_at: number }> }>(response);
  },

  /**
   * 授权Share给Recipient
   * @param name - Recipient名称
   * @param shareName - Share名称
   * @returns 授权记录
   */
  async grantShareToRecipient(name: string, shareName: string): Promise<ShareGrant> {
    const url = buildUrl(
      `${API_BASE_URL}/recipients/${encodeURIComponent(name)}/shares`,
      {
        share_name: shareName,
      }
    );
    const response = await apiFetch(url, {
      method: 'POST',
    });
    return handleResponse<ShareGrant>(response);
  },

  /**
   * 撤销Recipient对Share的授权
   * @param name - Recipient名称
   * @param shareName - Share名称
   */
  async revokeShareFromRecipient(name: string, shareName: string): Promise<void> {
    const response = await apiFetch(
      `${API_BASE_URL}/recipients/${encodeURIComponent(name)}/shares/${encodeURIComponent(shareName)}`,
      {
        method: 'DELETE',
      }
    );
    await handleResponse<void>(response);
  },

  /**
   * 获取Recipient的Token列表
   * @param name - Recipient名称
   * @param includeExpired - 是否包含已过期的Token
   * @returns Token列表响应
   */
  async listTokens(
    name: string,
    includeExpired: boolean = false
  ): Promise<{ items: Array<{ token_hash: string; token_prefix: string; created_at: number; expires_at: number | null; is_revoked: boolean }> }> {
    const url = buildUrl(
      `${API_BASE_URL}/recipients/${encodeURIComponent(name)}/tokens`,
      {
        includeExpired,
      }
    );
    const response = await apiFetch(url);
    return handleResponse<{ items: Array<{ token_hash: string; token_prefix: string; created_at: number; expires_at: number | null; is_revoked: boolean; profile_downloaded: boolean }> }>(response);
  },

  /**
   * 撤销Recipient的指定Token
   * @param name - Recipient名称
   * @param tokenHash - 要撤销的Token的SHA-256哈希值
   */
  async revokeToken(name: string, tokenHash: string): Promise<void> {
    const response = await apiFetch(
      `${API_BASE_URL}/recipients/${encodeURIComponent(name)}/tokens/${encodeURIComponent(tokenHash)}`,
      {
        method: 'DELETE',
      }
    );
    await handleResponse<void>(response);
  },

  /**
   * Token 轮换 - 生成新 Token 并保留旧 Token 有效
   * 内部调用 generateToken API，语义上等价于"新建+保留旧"
   * 与 generateToken 的区别在于前端回调和结果展示方式不同
   *
   * @param name - Recipient 名称
   * @param requireAuthorizedShares - 是否需要授权 Share
   * @param expirationHours - Token 过期小时数
   * @returns Token 响应，包含新旧 Token 信息和 OldTokenHash
   */
  async rotateToken(
    name: string,
    oldTokenHash: string,
    requireAuthorizedShares: boolean = false,
    expirationHours?: number
  ): Promise<TokenResponse & { oldTokenHash: string }> {
    const result = await this.generateToken(name, requireAuthorizedShares, expirationHours);
    return { ...result, oldTokenHash };
  },
};

/**
 * AuditLog相关API
 */
export const auditLogApi = {
  /**
   * 获取审计日志文件列表（按日志类型分组的日期列表）
   * @returns 审计日志列表响应
   */
  async getLogFiles(): Promise<AuditLogListResponse> {
    const url = `${API_BASE_URL}/audit-logs`;
    const response = await apiFetch(url);
    return handleResponse<AuditLogListResponse>(response);
  },

  /**
   * 查询指定类型和日期的审计日志条目
   * @param logType - 日志类型（admin_audit / client_audit / app）
   * @param params - 查询参数（日期、分页、过滤条件）
   * @returns 审计日志查询响应
   */
  async getLogEntries(
    logType: string,
    params: AuditLogQueryParams
  ): Promise<AuditLogQueryResponse> {
    const url = buildUrl(`${API_BASE_URL}/audit-logs/${encodeURIComponent(logType)}`, {
      date: params.date,
      page: params.page,
      page_size: params.page_size,
      filters: params.filters,
    });
    const response = await apiFetch(url);
    return handleResponse<AuditLogQueryResponse>(response);
  },
};

/**
 * 配置相关 API
 */
export const configApi = {
  /**
   * 获取前端需要的应用配置子集
   * @returns 应用配置（token 相关配置）
   */
  async fetchConfig(): Promise<AppConfig> {
    const url = `${API_BASE_URL}/config`;
    const response = await apiFetch(url);
    return handleResponse<AppConfig>(response);
  },
};

/**
 * 认证相关 API
 */
export const authApi = {
  /**
   * 管理员登录
   * @param data - 登录请求（username + password）
   * @returns 登录响应（admin_id + username + display_name）
   */
  async login(data: LoginRequest): Promise<LoginResponse> {
    const response = await apiFetch(`${API_BASE_URL}/auth/login`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(data),
    });
    return handleResponse<LoginResponse>(response);
  },

  /**
   * 管理员登出 - 清除服务端 Cookie
   */
  async logout(): Promise<void> {
    const response = await apiFetch(`${API_BASE_URL}/auth/logout`, {
      method: 'POST',
    });
    await handleResponse<void>(response);
  },

  /**
   * 获取当前登录管理员信息 - 用于验证会话有效性
   * @returns 当前管理员信息
   */
  async getCurrentAdmin(): Promise<AdminInfo> {
    const response = await apiFetch(`${API_BASE_URL}/auth/me`);
    return handleResponse<AdminInfo>(response);
  },
};

/**
 * 导出所有API
 */
export const api = {
  share: shareApi,
  recipient: recipientApi,
  auditLog: auditLogApi,
  config: configApi,
  auth: authApi,
};

export default api;
