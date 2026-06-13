/**
 * Main Application Component
 * Integrates navigation and page components
 */

import {
  FluentProvider,
  webLightTheme,
  webDarkTheme,
  makeStyles,
  tokens,
} from '@fluentui/react-components';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { ThemeProvider, useTheme } from './contexts/ThemeContext';
import { AuthProvider } from './contexts/AuthContext';
import { Navigation } from './components/Navigation';
import { ShareManager } from './components/ShareManager';
import { RecipientManager } from './components/RecipientManager';
import { ShareAssetDetail } from './components/ShareAssetDetail';
import { AuditLogViewer } from './components/AuditLogViewer';
import { ErrorBoundary } from './components/ErrorBoundary';
import ProtectedRoute from './components/ProtectedRoute';
import LoginPage from './components/LoginPage';

/**
 * Component Styles
 */
const useStyles = makeStyles({
  container: {
    display: 'flex',
    flexDirection: 'column',
    height: '100vh',
    backgroundColor: tokens.colorNeutralBackground3,
  },
  header: {
    display: 'flex',
    alignItems: 'center',
    padding: `${tokens.spacingVerticalM} ${tokens.spacingHorizontalL}`,
    backgroundColor: tokens.colorNeutralBackground1,
    borderBottom: `1px solid ${tokens.colorNeutralStroke2}`,
    gap: tokens.spacingHorizontalL,
  },
  title: {
    color: '#0078d4',
    fontSize: tokens.fontSizeBase500,
    fontWeight: tokens.fontWeightSemibold,
    whiteSpace: 'nowrap',
  },
  tabList: {
    flex: 1,
  },
  content: {
    flex: 1,
    overflow: 'auto',
    padding: tokens.spacingHorizontalM,
  },
});

/**
 * ThemedApp Component
 * Inner component that has access to theme context
 */
function ThemedApp() {
  const { theme } = useTheme();
  const currentTheme = theme === 'dark' ? webDarkTheme : webLightTheme;

  return (
    <FluentProvider theme={currentTheme}>
      <BrowserRouter>
        <Routes>
          {/* 公开路由：登录页面无需认证 */}
          <Route path="/login" element={<LoginPage />} />

          {/* 受保护路由：需要管理员登录 */}
          <Route path="/shares" element={<ProtectedRoute><Navigation /><main className={useStyles().content}><ErrorBoundary><ShareManager /></ErrorBoundary></main></ProtectedRoute>} />
          <Route path="/shares/:shareId/assets" element={<ProtectedRoute><Navigation /><main className={useStyles().content}><ErrorBoundary><ShareAssetDetail /></ErrorBoundary></main></ProtectedRoute>} />
          <Route path="/recipients" element={<ProtectedRoute><Navigation /><main className={useStyles().content}><ErrorBoundary><RecipientManager /></ErrorBoundary></main></ProtectedRoute>} />
          <Route path="/audit-logs" element={<ProtectedRoute><Navigation /><main className={useStyles().content}><ErrorBoundary><AuditLogViewer /></ErrorBoundary></main></ProtectedRoute>} />

          {/* 根路径：已登录跳转 /shares，未登录跳转 /login */}
          <Route path="/" element={<Navigate to="/shares" replace />} />
        </Routes>
      </BrowserRouter>
    </FluentProvider>
  );
}

/**
 * Main Application Component
 *
 * Uses Fluent UI theme, provides navigation and page content area
 * Uses React Router for navigation between pages
 * Supports light/dark theme switching
 *
 * @returns Application component
 */
function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <ThemedApp />
      </AuthProvider>
    </ThemeProvider>
  );
}

export default App;