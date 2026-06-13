/**
 * Navigation Component
 * Implements top navigation bar with React Router
 */


import {
  TabList,
  Tab,
  makeStyles,
  tokens,
  Title1,
  Button,
} from '@fluentui/react-components';
import {
  ShareRegular,
  PeopleRegular,
  DocumentSearchRegular,
  WeatherMoonRegular,
  WeatherSunnyRegular,
  PersonRegular,
} from '@fluentui/react-icons';
import { useLocation, NavLink, useNavigate } from 'react-router-dom';
import { useTheme } from '../contexts/ThemeContext';
import { useAuth } from '../contexts/AuthContext';
import Logo from '../assets/iceberg-logo-icon.png';

/**
 * Page Type
 */
export type PageType = 'shares' | 'recipients' | 'audit-logs';

/**
 * Component Styles
 */
const useStyles = makeStyles({
  header: {
    display: 'flex',
    alignItems: 'center',
    padding: `${tokens.spacingVerticalM} ${tokens.spacingHorizontalL}`,
    backgroundColor: tokens.colorNeutralBackground1,
    borderBottom: `1px solid ${tokens.colorNeutralStroke2}`,
    gap: tokens.spacingHorizontalL,
  },
  logo: {
    width: '32px',
    height: '32px',
    objectFit: 'contain',
  },
  title: {
    color: '#0078d4',
    fontWeight: tokens.fontWeightSemibold,
    whiteSpace: 'nowrap',
  },
  tabList: {
    flex: 1,
  },
  navLink: {
    textDecoration: 'none',
    color: 'inherit',
  },
  toolbarActions: {
    display: 'flex',
    alignItems: 'center',
    gap: tokens.spacingHorizontalXS,
  },
});

/**
 * Navigation Component
 *
 * Provides top navigation bar with Share Management and Recipient Management page switching
 * Uses React Router for navigation state management
 * Includes theme toggle button for light/dark mode switching
 *
 * @returns Navigation component
 */
export const Navigation: React.FC = () => {
  const styles = useStyles();
  const location = useLocation();
  const navigate = useNavigate();
  const { theme, toggleTheme } = useTheme();
  const { logout } = useAuth();

  const getActivePage = (): PageType => {
    if (location.pathname.startsWith('/shares')) return 'shares';
    if (location.pathname.startsWith('/recipients')) return 'recipients';
    if (location.pathname.startsWith('/audit-logs')) return 'audit-logs';
    return 'shares';
  };

  const activePage = getActivePage();

  /**
   * 处理登出
   * 调用 AuthContext.logout() 清除会话并跳转到登录页
   */
  const handleLogout = async () => {
    await logout();
    navigate('/login', { replace: true });
  };

  return (
    <header className={styles.header}>
      <img src={Logo} alt="Iceberg Logo" className={styles.logo} />
      <Title1 className={styles.title}>Delta Sharing for Iceberg</Title1>
      <TabList
        className={styles.tabList}
        selectedValue={activePage}
      >
        <Tab
          value="shares"
          icon={<ShareRegular />}
        >
          <NavLink to="/shares" className={styles.navLink}>Share Management</NavLink>
        </Tab>
        <Tab
          value="recipients"
          icon={<PeopleRegular />}
        >
          <NavLink to="/recipients" className={styles.navLink}>Recipient Management</NavLink>
        </Tab>
        <Tab
          value="audit-logs"
          icon={<DocumentSearchRegular />}
        >
          <NavLink to="/audit-logs" className={styles.navLink}>Audit Log</NavLink>
        </Tab>
      </TabList>
      <div className={styles.toolbarActions}>
        <Button
          appearance="subtle"
          icon={<PersonRegular />}
          onClick={handleLogout}
          title="Logout"
          aria-label="Logout"
        />
        <Button
          appearance="subtle"
          icon={theme === 'dark' ? <WeatherSunnyRegular /> : <WeatherMoonRegular />}
          onClick={toggleTheme}
          title={theme === 'dark' ? 'Switch to Light Mode' : 'Switch to Dark Mode'}
          aria-label={theme === 'dark' ? 'Switch to Light Mode' : 'Switch to Dark Mode'}
        />
      </div>
    </header>
  );
};

export default Navigation;