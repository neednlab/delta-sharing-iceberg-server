/**
 * AuthContext - 管理员认证状态管理
 *
 * 提供全局认证状态，包括：
 * - 登录/登出操作
 * - 会话恢复（页面刷新时通过 /auth/me 验证 Cookie）
 * - 为 ProtectedRoute 提供 isAuthenticated 判断
 */

import React, { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from 'react';
import { authApi } from '../services/api';
import type { AdminInfo } from '../types';

/**
 * AuthContext 值类型
 */
interface AuthContextValue {
  /** 是否已认证 */
  isAuthenticated: boolean;
  /** 当前管理员信息，未认证时为 null */
  adminInfo: AdminInfo | null;
  /** 是否正在检查认证状态（初始加载时） */
  isLoading: boolean;
  /** 登录操作 */
  login: (username: string, password: string) => Promise<void>;
  /** 登出操作 */
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

/**
 * useAuth Hook
 *
 * 在组件中访问认证状态。
 * 必须在 AuthProvider 内部使用。
 *
 * @returns AuthContextValue
 */
// eslint-disable-next-line react-refresh/only-export-components
export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}

/**
 * AuthProvider 组件
 *
 * 包裹整个应用，提供认证状态管理。
 * 挂载时自动检查当前 Cookie 中的 JWT 是否有效。
 */
// eslint-disable-next-line react-refresh/only-export-components
export const AuthProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [adminInfo, setAdminInfo] = useState<AdminInfo | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // 应用启动时检查会话状态
  useEffect(() => {
    const checkAuth = async () => {
      try {
        const info = await authApi.getCurrentAdmin();
        setIsAuthenticated(true);
        setAdminInfo(info);
      } catch {
        // 未登录或 Token 过期，保持未认证状态
        setIsAuthenticated(false);
        setAdminInfo(null);
      } finally {
        setIsLoading(false);
      }
    };

    checkAuth();
  }, []);

  /**
   * 登录操作
   * 调用 /auth/login API，成功后更新状态。
   */
  const login = useCallback(async (username: string, password: string) => {
    const info = await authApi.login({ username, password });
    setIsAuthenticated(true);
    setAdminInfo(info);
  }, []);

  /**
   * 登出操作
   * 调用 /auth/logout API 清除 Cookie，重置本地状态。
   */
  const logout = useCallback(async () => {
    try {
      await authApi.logout();
    } catch {
      // 即使 API 调用失败，也清除本地状态
    }
    setIsAuthenticated(false);
    setAdminInfo(null);
  }, []);

  const value: AuthContextValue = {
    isAuthenticated,
    adminInfo,
    isLoading,
    login,
    logout,
  };

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
};

export default AuthContext;
