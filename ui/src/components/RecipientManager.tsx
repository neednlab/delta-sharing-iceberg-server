/**
 * Recipient Management Component
 * 管理Recipient的CRUD操作和Token管理
 * 内部通过子组件和hooks进行模块化
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHeaderCell,
  TableCell,
  Button,
  Spinner,
  MessageBar,
  MessageBarBody,
  makeStyles,
  tokens,
  Card,
  CardHeader,
  CardPreview,
  Badge,
} from '@fluentui/react-components';
import {
  AddRegular,
  EditRegular,
  DeleteRegular,
  KeyRegular,
  ChevronLeftRegular,
  ChevronRightRegular,
} from '@fluentui/react-icons';
import type { Recipient, AppConfig } from '../types';
import { recipientApi, configApi } from '../services/api';
import { formatDate } from '../utils/formatDate';
import { getRecipientDisplayName, downloadProfile } from '../utils';
import { usePagination } from '../hooks/usePagination';
import { RecipientCreateDialog } from './RecipientCreateDialog';
import { RecipientEditDialog } from './RecipientEditDialog';
import { RecipientDeleteDialog } from './RecipientDeleteDialog';
import { TokenManagementDialog } from './TokenManagementDialog';
import { TokenRotateDialog } from './TokenRotateDialog';
import { TokenRotateResultDialog } from './TokenRotateResultDialog';

/**
 * Component Styles
 */
const useStyles = makeStyles({
  container: {
    padding: tokens.spacingHorizontalL,
  },
  title: {
    fontSize: tokens.fontSizeBase500,
    fontWeight: tokens.fontWeightSemibold,
    color: tokens.colorNeutralForeground1,
  },
  table: {
    width: '100%',
    borderCollapse: 'collapse',
  },
  tableHeaderCell: {
    textAlign: 'center',
    '& > div, & > button, & > span': {
      justifyContent: 'center',
      textAlign: 'center',
      width: '100%',
    },
  },
  tableRow: {
    '&:hover': {
      backgroundColor: tokens.colorNeutralBackground1Hover,
    },
  },
  pagination: {
    display: 'flex',
    justifyContent: 'center',
    alignItems: 'center',
    gap: tokens.spacingHorizontalM,
    marginTop: tokens.spacingVerticalL,
  },
  errorBar: {
    marginBottom: tokens.spacingVerticalM,
  },
  successBar: {
    marginBottom: tokens.spacingVerticalM,
  },
  paginationButton: {
    fontSize: '12px',
    paddingTop: '4px',
    paddingBottom: '4px',
    paddingLeft: '4px',
    paddingRight: '4px',
    width: '98px',
    height: '30px',
  },
  paginationIcon: {
    fontSize: '18px',
  },
  paginationContent: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
  },
  pageIndicator: {
    marginLeft: '20px',
    marginRight: '20px',
  },
});

/**
 * Recipient Management Component
 * 负责Recipient列表展示、分页导航和对话框编排
 */
export const RecipientManager: React.FC = () => {
  const styles = useStyles();

  const fetchRecipients = useCallback(
    (params: { maxResults?: number; pageToken?: string }) =>
      recipientApi.getRecipients(params),
    []
  );

  const {
    items: recipients,
    loading,
    error,
    currentPage,
    nextPageToken,
    goNext,
    goPrev,
    reload,
  } = usePagination(fetchRecipients, 20);

  // Dialog State
  const [isCreateDialogOpen, setIsCreateDialogOpen] = useState(false);
  const [isEditDialogOpen, setIsEditDialogOpen] = useState(false);
  const [isDeleteDialogOpen, setIsDeleteDialogOpen] = useState(false);
  const [isTokenDialogOpen, setIsTokenDialogOpen] = useState(false);
  const [selectedRecipient, setSelectedRecipient] = useState<Recipient | null>(null);

  // Success Message State
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Local Error State (for non-pagination errors like token rotation failures)
  const [localError, setLocalError] = useState<string | null>(null);

  // Combined error for display
  const displayError = error || localError;

  // App Config State
  const [appConfig, setAppConfig] = useState<AppConfig>({
    token: { max_tokens_per_recipient: 2, rotation_period_hours: 24, default_expiration_hours: 168 },
  });

  // Rotate Dialog State
  const [rotateTargetToken, setRotateTargetToken] = useState<{
    token_hash: string;
    token_prefix: string;
    created_at: number;
  } | null>(null);
  const [rotateConfirmOpen, setRotateConfirmOpen] = useState(false);
  const [rotateResultOpen, setRotateResultOpen] = useState(false);
  const [rotateNewToken, setRotateNewToken] = useState<string | null>(null);
  const [rotateOldTokenHash, setRotateOldTokenHash] = useState<string>('');

  // Dialog remount keys - reset dialog state when opened
  const [createDialogKey, setCreateDialogKey] = useState(0);
  const [editDialogKey, setEditDialogKey] = useState(0);
  const [tokenDialogKey, setTokenDialogKey] = useState(0);
  const [rotateConfirmKey, setRotateConfirmKey] = useState(0);

  /**
   * Load App Config on mount
   */
  useEffect(() => {
    configApi.fetchConfig().then(setAppConfig).catch(() => {
      setAppConfig({
        token: { max_tokens_per_recipient: 2, rotation_period_hours: 24, default_expiration_hours: 168 },
      });
    });
  }, []);

  /**
   * Show Success Message (auto dismiss)
   */
  const showSuccess = (message: string) => {
    setSuccessMessage(message);
  };

  useEffect(() => {
    if (successMessage) {
      const timer = setTimeout(() => {
        setSuccessMessage(null);
      }, 5000);
      return () => clearTimeout(timer);
    }
  }, [successMessage]);

  /**
   * Handle Rotate Token Confirmation
   */
  const handleRotateConfirm = async (expirationHours: number | undefined, requireAuthorizedShares: boolean) => {
    if (!selectedRecipient || !rotateTargetToken) return;

    const recipientName = getRecipientDisplayName(selectedRecipient);

    try {
      const result = await recipientApi.rotateToken(
        recipientName,
        rotateTargetToken.token_hash,
        requireAuthorizedShares,
        expirationHours
      );

      setRotateConfirmOpen(false);

      setRotateNewToken(result.tokenPrefix || '');
      setRotateOldTokenHash(rotateTargetToken.token_hash);

      // 自动下载Profile文件
      if (result.profileContent) {
        downloadProfile(result.profileContent, `${recipientName}.share`);
      }

      setRotateResultOpen(true);
    } catch (err) {
      setLocalError(err instanceof Error ? err.message : 'Failed to rotate token');
      setRotateConfirmOpen(false);
    }
  };

  /**
   * Handle Revoke Old Token from Rotate Result Dialog
   */
  const handleRevokeOldToken = async () => {
    if (!selectedRecipient || !rotateOldTokenHash) return;

    const recipientName = getRecipientDisplayName(selectedRecipient);
    try {
      await recipientApi.revokeToken(recipientName, rotateOldTokenHash);
      showSuccess('Old token revoked successfully');
      setRotateResultOpen(false);
    } catch (err) {
      // error is handled separately
      console.error('Failed to revoke old token:', err);
    }
  };

  /**
   * Get Status Badge
   */
  const getStatusBadge = (isActive: boolean) => {
    return isActive ? (
      <Badge appearance="filled" color="success">
        Active
      </Badge>
    ) : (
      <Badge appearance="filled" color="informative">
        Disabled
      </Badge>
    );
  };

  return (
    <div className={styles.container}>
      <Card>
        <CardHeader
          header={<span className={styles.title}>Recipient Management</span>}
          action={
            <Button
              appearance="primary"
              icon={<AddRegular />}
              onClick={() => {
                setCreateDialogKey(k => k + 1);
                setIsCreateDialogOpen(true);
              }}
            >
              Add Recipient
            </Button>
          }
        />
        <CardPreview>
          {displayError && (
            <MessageBar intent="error" className={styles.errorBar} style={{ display: 'flex', alignItems: 'center' }}>
              <MessageBarBody style={{ display: 'flex', alignItems: 'center' }}>{displayError}</MessageBarBody>
            </MessageBar>
          )}

          {successMessage && (
            <MessageBar intent="success" className={styles.successBar} style={{ display: 'flex', alignItems: 'center' }}>
              <MessageBarBody style={{ display: 'flex', alignItems: 'center' }}>{successMessage}</MessageBarBody>
            </MessageBar>
          )}

          {loading ? (
            <Spinner label="Loading..." />
          ) : (
            <>
              <Table className={styles.table}>
                <TableHeader>
                  <TableRow>
                    <TableHeaderCell className={styles.tableHeaderCell}>Recipient Name</TableHeaderCell>
                    <TableHeaderCell className={styles.tableHeaderCell}>Comment</TableHeaderCell>
                    <TableHeaderCell className={styles.tableHeaderCell}>Status</TableHeaderCell>
                    <TableHeaderCell className={styles.tableHeaderCell}>Created At</TableHeaderCell>
                    <TableHeaderCell className={styles.tableHeaderCell}>Actions</TableHeaderCell>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {recipients.map((recipient) => {
                    const recipientName = getRecipientDisplayName(recipient);
                    return (
                      <TableRow key={recipient.recipient_id} className={styles.tableRow}>
                        <TableCell>{recipientName}</TableCell>
                        <TableCell>{recipient.comment || '-'}</TableCell>
                        <TableCell>{getStatusBadge(recipient.is_active)}</TableCell>
                        <TableCell>{recipient.created_at ? formatDate(recipient.created_at) : '-'}</TableCell>
                        <TableCell>
                          <div style={{ display: 'flex', gap: '8px' }}>
                            <Button
                              icon={<KeyRegular />}
                              onClick={() => {
                                setSelectedRecipient(recipient);
                                setTokenDialogKey(k => k + 1);
                                setIsTokenDialogOpen(true);
                              }}
                              title="Token management"
                              appearance="subtle"
                              size="small"
                            />
                            <Button
                              icon={<EditRegular />}
                              onClick={() => {
                                setSelectedRecipient(recipient);
                                setEditDialogKey(k => k + 1);
                                setIsEditDialogOpen(true);
                              }}
                              title="Update"
                              appearance="subtle"
                              size="small"
                            />
                            <Button
                              icon={<DeleteRegular />}
                              onClick={() => {
                                setSelectedRecipient(recipient);
                                setIsDeleteDialogOpen(true);
                              }}
                              title="Delete"
                              appearance="subtle"
                              size="small"
                            />
                          </div>
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>

              <div className={styles.pagination}>
                <Button
                  icon={<ChevronLeftRegular className={styles.paginationIcon} />}
                  onClick={goPrev}
                  disabled={currentPage === 1}
                  className={styles.paginationButton}
                >
                  Previous
                </Button>
                <span className={styles.pageIndicator}>Page {currentPage}</span>
                <Button
                  onClick={goNext}
                  disabled={!nextPageToken}
                  className={styles.paginationButton}
                >
                  <span className={styles.paginationContent}>
                    Next
                    <ChevronRightRegular className={styles.paginationIcon} />
                  </span>
                </Button>
              </div>
            </>
          )}
        </CardPreview>
      </Card>

      {/* Create Recipient Dialog */}
      <RecipientCreateDialog
        key={`create-${createDialogKey}`}
        open={isCreateDialogOpen}
        onClose={() => setIsCreateDialogOpen(false)}
        onCreated={() => {
          showSuccess('Recipient created successfully');
          reload();
        }}
      />

      {/* Edit Recipient Dialog */}
      {selectedRecipient && (
        <RecipientEditDialog
          key={`edit-${editDialogKey}`}
          open={isEditDialogOpen}
          onClose={() => {
            setIsEditDialogOpen(false);
            setSelectedRecipient(null);
          }}
          onUpdated={() => {
            showSuccess('Recipient updated successfully');
            reload();
          }}
          recipient={selectedRecipient}
        />
      )}

      {/* Delete Recipient Dialog */}
      {selectedRecipient && (
        <RecipientDeleteDialog
          open={isDeleteDialogOpen}
          onClose={() => {
            setIsDeleteDialogOpen(false);
            setSelectedRecipient(null);
          }}
          onDeleted={() => {
            showSuccess('Recipient deleted successfully');
            reload();
          }}
          recipient={selectedRecipient}
        />
      )}

      {/* Token Management Dialog */}
      {selectedRecipient && (
        <TokenManagementDialog
          key={`token-${tokenDialogKey}`}
          open={isTokenDialogOpen}
          onClose={() => {
            setIsTokenDialogOpen(false);
            setSelectedRecipient(null);
          }}
          recipient={selectedRecipient}
          appConfig={appConfig}
          onTokenGenerated={() => {
            showSuccess('Token generated successfully. Profile file has been automatically downloaded - save it securely.');
          }}
          onTokenRevoked={() => {
            showSuccess('Token revoked successfully');
          }}
          onRotateRequest={(tokenItem) => {
            setRotateTargetToken(tokenItem);
            setRotateConfirmKey(k => k + 1);
            setRotateConfirmOpen(true);
          }}
        />
      )}

      {/* Rotate Confirmation Dialog */}
      {selectedRecipient && rotateTargetToken && (
        <TokenRotateDialog
          key={`rotate-${rotateConfirmKey}`}
          open={rotateConfirmOpen}
          onClose={() => setRotateConfirmOpen(false)}
          onRotated={handleRotateConfirm}
          targetToken={rotateTargetToken}
          recipient={selectedRecipient}
        />
      )}

      {/* Rotate Result Dialog */}
      <TokenRotateResultDialog
        open={rotateResultOpen}
        onClose={() => {
          setRotateResultOpen(false);
          setRotateNewToken(null);
        }}
        newTokenPrefix={rotateNewToken}
        oldTokenHash={rotateOldTokenHash}
        onRevokeOldToken={handleRevokeOldToken}
      />
    </div>
  );
};

export default RecipientManager;
