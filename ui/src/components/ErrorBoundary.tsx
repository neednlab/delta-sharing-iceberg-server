/**
 * ErrorBoundary Component
 * Catches unhandled rendering errors in child page components and displays
 * a user-friendly fallback UI instead of a white screen crash.
 *
 * Uses React class component pattern since componentDidCatch is only available
 * in class components (React 19 stable API).
 */

import React from 'react';
import { MessageBar, MessageBarBody, Button, makeStyles, tokens } from '@fluentui/react-components';
import { ErrorCircleRegular, ArrowSyncRegular } from '@fluentui/react-icons';

const useStyles = makeStyles({
  container: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    padding: tokens.spacingHorizontalXXL,
    gap: tokens.spacingHorizontalL,
    minHeight: '300px',
  },
  messageBar: {
    maxWidth: '600px',
    width: '100%',
  },
});

interface ErrorBoundaryProps {
  children: React.ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends React.Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo): void {
    console.error('ErrorBoundary caught an error:', error, errorInfo);
  }

  handleRetry = (): void => {
    this.setState({ hasError: false, error: null });
  };

  render(): React.ReactNode {
    if (this.state.hasError) {
      return <ErrorFallback error={this.state.error} onRetry={this.handleRetry} />;
    }

    return this.props.children;
  }
}

function ErrorFallback({ error, onRetry }: { error: Error | null; onRetry: () => void }) {
  const styles = useStyles();

  return (
    <div className={styles.container}>
      <ErrorCircleRegular style={{ fontSize: '48px', color: tokens.colorPaletteRedForeground1 }} />
      <MessageBar intent="error" className={styles.messageBar}>
        <MessageBarBody>
          <div style={{ fontWeight: tokens.fontWeightSemibold, marginBottom: tokens.spacingVerticalXS }}>
            An unexpected error occurred
          </div>
          <div style={{ wordBreak: 'break-word' }}>
            {error?.message || 'Unknown error'}
          </div>
        </MessageBarBody>
      </MessageBar>
      <Button
        appearance="primary"
        icon={<ArrowSyncRegular />}
        onClick={onRetry}
      >
        Retry
      </Button>
    </div>
  );
}
