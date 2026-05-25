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
import { Navigation } from './components/Navigation';
import { ShareManager } from './components/ShareManager';
import { RecipientManager } from './components/RecipientManager';
import { ShareAssetDetail } from './components/ShareAssetDetail';
import { AuditLogViewer } from './components/AuditLogViewer';
import { ErrorBoundary } from './components/ErrorBoundary';

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
        <div className={useStyles().container}>
          <Navigation />
          <main className={useStyles().content}>
            <Routes>
              <Route path="/" element={<Navigate to="/shares" replace />} />
              <Route path="/shares" element={<ErrorBoundary><ShareManager /></ErrorBoundary>} />
              <Route path="/shares/:shareId/assets" element={<ErrorBoundary><ShareAssetDetail /></ErrorBoundary>} />
              <Route path="/recipients" element={<ErrorBoundary><RecipientManager /></ErrorBoundary>} />
              <Route path="/audit-logs" element={<ErrorBoundary><AuditLogViewer /></ErrorBoundary>} />
            </Routes>
          </main>
        </div>
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
      <ThemedApp />
    </ThemeProvider>
  );
}

export default App;