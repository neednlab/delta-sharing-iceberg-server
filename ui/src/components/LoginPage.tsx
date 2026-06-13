/**
 * LoginPage Component
 *
 * 管理员登录页面。使用 Fluent UI 组件构建居中登录表单。
 * 设计风格与现有管理页面完全一致，支持明暗主题切换。
 * UI 语言为英文。
 */

import React, { useState, type FormEvent } from 'react';
import {
  Card,
  Input,
  Button,
  Label,
  makeStyles,
  tokens,
  Title2,
  MessageBar,
  MessageBarBody,
} from '@fluentui/react-components';
import { PersonRegular, LockClosedRegular } from '@fluentui/react-icons';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';

/**
 * 组件样式
 */
const useStyles = makeStyles({
  container: {
    display: 'flex',
    justifyContent: 'center',
    alignItems: 'center',
    height: '100vh',
    backgroundColor: tokens.colorNeutralBackground3,
  },
  card: {
    width: '400px',
    maxWidth: '90vw',
    padding: tokens.spacingVerticalXXL,
  },
  title: {
    textAlign: 'center',
    marginBottom: tokens.spacingVerticalL,
    color: '#0078d4',
  },
  field: {
    marginBottom: tokens.spacingVerticalM,
  },
  inputWrapper: {
    display: 'flex',
    alignItems: 'center',
    gap: tokens.spacingHorizontalS,
  },
  icon: {
    color: tokens.colorNeutralForeground3,
    flexShrink: 0,
  },
  errorBar: {
    marginBottom: tokens.spacingVerticalM,
  },
  submitButton: {
    width: '100%',
    marginTop: tokens.spacingVerticalL,
  },
});

/**
 * LoginPage Component
 *
 * 提供用户名/密码登录表单。
 * 登录成功后通过 AuthContext 更新状态并跳转到 /shares。
 *
 * @returns LoginPage 组件
 */
const LoginPage: React.FC = () => {
  const styles = useStyles();
  const navigate = useNavigate();
  const { login } = useAuth();

  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  /**
   * 处理表单提交
   */
  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!username.trim() || !password) {
      setError('Username and password are required.');
      return;
    }

    setIsSubmitting(true);
    try {
      await login(username, password);
      navigate('/shares', { replace: true });
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Login failed. Please try again.';
      setError(message);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className={styles.container}>
      <Card className={styles.card}>
        <Title2 className={styles.title}>Delta Sharing Admin</Title2>

        {error && (
          <MessageBar intent="error" className={styles.errorBar}>
            <MessageBarBody>{error}</MessageBarBody>
          </MessageBar>
        )}

        <form onSubmit={handleSubmit}>
          <div className={styles.field}>
            <Label htmlFor="login-username">Username</Label>
            <div className={styles.inputWrapper}>
              <PersonRegular className={styles.icon} fontSize={20} />
              <Input
                id="login-username"
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="Enter your username"
                autoComplete="username"
                autoFocus
              />
            </div>
          </div>

          <div className={styles.field}>
            <Label htmlFor="login-password">Password</Label>
            <div className={styles.inputWrapper}>
              <LockClosedRegular className={styles.icon} fontSize={20} />
              <Input
                id="login-password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Enter your password"
                autoComplete="current-password"
              />
            </div>
          </div>

          <Button
            type="submit"
            appearance="primary"
            className={styles.submitButton}
            disabled={isSubmitting}
          >
            {isSubmitting ? 'Signing In...' : 'Sign In'}
          </Button>
        </form>
      </Card>
    </div>
  );
};

export default LoginPage;
