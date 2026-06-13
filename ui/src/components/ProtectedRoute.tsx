/**
 * ProtectedRoute Component
 *
 * 路由守卫组件。未认证用户访问受保护页面时自动重定向到 /login。
 * 认证检查期间显示加载状态（Spinner）。
 */

import React from 'react';
import { Navigate } from 'react-router-dom';
import { Spinner, makeStyles, tokens } from '@fluentui/react-components';
import { useAuth } from '../contexts/AuthContext';

/**
 * 组件样式
 */
const useStyles = makeStyles({
  loadingContainer: {
    display: 'flex',
    justifyContent: 'center',
    alignItems: 'center',
    height: '100vh',
    backgroundColor: tokens.colorNeutralBackground3,
  },
});

/**
 * ProtectedRoute Component
 *
 * 包裹受保护页面组件：
 * - isLoading: 显示 Spinner 加载指示器
 * - isAuthenticated: 渲染子组件
 * - 未认证: 重定向到 /login
 *
 * @param children - 受保护的子组件
 * @returns ProtectedRoute 组件
 */
const ProtectedRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const styles = useStyles();
  const { isAuthenticated, isLoading } = useAuth();

  if (isLoading) {
    return (
      <div className={styles.loadingContainer}>
        <Spinner label="Loading..." />
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
};

export default ProtectedRoute;
