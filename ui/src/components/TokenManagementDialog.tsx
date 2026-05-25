/**
 * TokenManagementDialog Component
 * Token管理对话框：展示已有Token列表、生成新Token、撤销Token
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Dialog,
  DialogSurface,
  DialogTitle,
  DialogBody,
  DialogContent,
  DialogActions,
  Button,
  Label,
  Checkbox,
  Spinner,
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHeaderCell,
  TableCell,
  Badge,
  Dropdown,
  Option,
  Input,
  Tooltip,
  makeStyles,
  tokens,
} from '@fluentui/react-components';
import {
  ArrowSyncRegular,
  DismissRegular,
} from '@fluentui/react-icons';
import type { Recipient, AppConfig } from '../types';
import { recipientApi } from '../services/api';
import { formatDate } from '../utils/formatDate';
import { getRecipientDisplayName, downloadProfile, tokenAgeStatus, EXPIRATION_OPTIONS } from '../utils';
import { useExpiration } from '../hooks/useExpiration';

const useStyles = makeStyles({
  dialogContent: {
    display: 'flex',
    flexDirection: 'column',
    gap: tokens.spacingVerticalM,
  },
  formField: {
    display: 'flex',
    flexDirection: 'column',
    gap: tokens.spacingVerticalXS,
  },
});

interface TokenEntry {
  token_hash: string;
  token_prefix: string;
  created_at: number;
  expires_at: number | null;
  is_revoked: boolean;
}

interface TokenManagementDialogProps {
  open: boolean;
  onClose: () => void;
  recipient: Recipient;
  appConfig: AppConfig;
  onTokenGenerated?: () => void;
  onTokenRevoked?: () => void;
  onRotateRequest?: (token: TokenEntry) => void;
}

export const TokenManagementDialog: React.FC<TokenManagementDialogProps> = ({
  open,
  onClose,
  recipient,
  appConfig,
  onTokenGenerated,
  onTokenRevoked,
  onRotateRequest,
}) => {
  const styles = useStyles();

  const recipientName = getRecipientDisplayName(recipient);

  const [requireAuthorizedShares, setRequireAuthorizedShares] = useState(false);
  const [tokenList, setTokenList] = useState<TokenEntry[]>([]);
  const [loadingTokens, setLoadingTokens] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const revokingTokenRef = useRef(false);

  const {
    expirationHours,
    expirationOption,
    setExpirationOption,
    customExpirationDate,
    setCustomExpirationDate,
  } = useExpiration('30 days');

  const loadTokenList = useCallback(async (includeExpired: boolean = false) => {
    setLoadingTokens(true);
    try {
      const response = await recipientApi.listTokens(recipientName, includeExpired);
      setTokenList(response.items || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load tokens');
      setTokenList([]);
    } finally {
      setLoadingTokens(false);
    }
  }, [recipientName]);

  useEffect(() => {
    /* eslint-disable react-hooks/set-state-in-effect */
    setRequireAuthorizedShares(false);
    setError(null);
    loadTokenList(false);
    /* eslint-enable react-hooks/set-state-in-effect */
  }, [loadTokenList]);



  /**
   * 生成新Token并自动下载Profile
   */
  const handleGenerateToken = async () => {
    if (!recipient) return;

    try {
      const result = await recipientApi.generateToken(
        recipientName,
        requireAuthorizedShares,
        expirationHours
      );

      // 自动下载Profile文件
      if (result.profileContent) {
        downloadProfile(result.profileContent, `${recipientName}.share`);
      }

      loadTokenList(false);
      onTokenGenerated?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to generate token');
    }
  };

  /**
   * 撤销指定Token
   */
  const handleRevokeToken = async (tokenHash: string) => {
    if (revokingTokenRef.current) return;
    revokingTokenRef.current = true;

    try {
      await recipientApi.revokeToken(recipientName, tokenHash);
      const updatedTokens = tokenList.filter(t => t.token_hash !== tokenHash);
      setTokenList(updatedTokens);
      onTokenRevoked?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to revoke token');
    } finally {
      revokingTokenRef.current = false;
    }
  };

  const handleClose = () => {
    setTokenList([]);
    onClose();
  };

  const isAtMaxTokens = tokenList.length >= appConfig.token.max_tokens_per_recipient;

  return (
    <Dialog open={open} onOpenChange={(_, data) => { if (!data.open) handleClose(); }}>
      <DialogSurface style={{ minWidth: '800px' }}>
        <DialogBody>
          <DialogTitle>Token Management - {recipientName}</DialogTitle>
          <DialogContent className={styles.dialogContent}>
            {error && (
              <div style={{ color: tokens.colorPaletteRedForeground1, marginBottom: tokens.spacingVerticalS }}>
                {error}
              </div>
            )}

            <div style={{ marginBottom: tokens.spacingVerticalL }}>
              <Label>Existing Tokens</Label>
              {loadingTokens ? (
                <Spinner size="tiny" label="Loading tokens..." />
              ) : tokenList.length === 0 ? (
                <div style={{ color: tokens.colorNeutralForeground3, padding: tokens.spacingVerticalS }}>
                  No active tokens found for this recipient.
                </div>
              ) : (
                <div style={{ maxHeight: '200px', overflowY: 'auto', border: `1px solid ${tokens.colorNeutralStroke1}`, borderRadius: tokens.borderRadiusMedium }}>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHeaderCell>Token</TableHeaderCell>
                        <TableHeaderCell>Status</TableHeaderCell>
                        <TableHeaderCell>Created At</TableHeaderCell>
                        <TableHeaderCell>Expires At</TableHeaderCell>
                        <TableHeaderCell>Action</TableHeaderCell>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {tokenList.map((tokenItem, index) => {
                        const status = tokenAgeStatus(tokenItem.created_at, appConfig.token.rotation_period_hours);
                        return (
                          <TableRow key={index}>
                            <TableCell>
                              <div style={{ display: 'flex', alignItems: 'center', gap: tokens.spacingHorizontalS }}>
                                <span>{tokenItem.token_prefix}...</span>
                              </div>
                            </TableCell>
                            <TableCell>
                              <Badge appearance="filled" color={status.color} style={{ whiteSpace: 'nowrap' }}>
                                {status.label}
                              </Badge>
                            </TableCell>
                            <TableCell style={{ whiteSpace: 'nowrap' }}>{formatDate(tokenItem.created_at)}</TableCell>
                            <TableCell style={{ whiteSpace: 'nowrap' }}>
                              {tokenItem.expires_at ? formatDate(tokenItem.expires_at) : 'Never'}
                            </TableCell>
                            <TableCell>
                              <div style={{ display: 'flex', gap: tokens.spacingHorizontalXS }}>
                                {onRotateRequest && (
                                  isAtMaxTokens ? (
                                    <Tooltip content={`Cannot rotate: token limit (${appConfig.token.max_tokens_per_recipient}) reached. Revoke an old token first.`} relationship="label">
                                      <Button
                                        appearance="subtle"
                                        icon={<ArrowSyncRegular />}
                                        disabled
                                        size="small"
                                      />
                                    </Tooltip>
                                  ) : (
                                    <Tooltip content="Rotate this token - generate a new one while keeping the old one active" relationship="label">
                                      <Button
                                        appearance="subtle"
                                        icon={<ArrowSyncRegular />}
                                        onClick={() => onRotateRequest(tokenItem)}
                                        title="Rotate Token"
                                        size="small"
                                      />
                                    </Tooltip>
                                  )
                                )}
                                <Button
                                  appearance="subtle"
                                  icon={<DismissRegular />}
                                  onClick={() => handleRevokeToken(tokenItem.token_hash)}
                                  title="Revoke"
                                  size="small"
                                >
                                  Revoke
                                </Button>
                              </div>
                            </TableCell>
                          </TableRow>
                        );
                      })}
                    </TableBody>
                  </Table>
                </div>
              )}
            </div>

            <div style={{ borderTop: `1px solid ${tokens.colorNeutralStroke1}`, paddingTop: tokens.spacingVerticalL }}>
              <Label>Generate New Token</Label>
              <div className={styles.formField} style={{ marginTop: tokens.spacingVerticalS }}>
                <Checkbox
                  checked={requireAuthorizedShares}
                  onChange={(_, data) =>
                    setRequireAuthorizedShares(data.checked === true)
                  }
                  label="Require authorized shares"
                  disabled={isAtMaxTokens}
                />
              </div>
              <div className={styles.formField} style={{ marginTop: tokens.spacingVerticalS }}>
                <Label htmlFor="tokenExpirationSelect">Expiration</Label>
                <div style={{ display: 'flex', gap: tokens.spacingHorizontalS, alignItems: 'flex-start' }}>
                  <Dropdown
                    id="tokenExpirationSelect"
                    value={expirationOption}
                    onOptionSelect={(_, data) => {
                      setExpirationOption(data.optionValue || '30 days');
                    }}
                    style={{ minWidth: '180px' }}
                    disabled={isAtMaxTokens}
                  >
                    {EXPIRATION_OPTIONS.map(opt => (
                      <Option key={opt.value} value={opt.value}>{opt.label}</Option>
                    ))}
                  </Dropdown>
                  {expirationOption === 'Custom' && (
                    <div style={{ marginLeft: tokens.spacingHorizontalS }}>
                      <Input
                        type="date"
                        id="tokenCustomDatePicker"
                        value={customExpirationDate ? customExpirationDate.toLocaleDateString('en-CA') : ''}
                        onChange={(_, data) => {
                          const dateValue = (data.value as string) ? new Date((data.value as string) + 'T00:00:00') : undefined;
                          setCustomExpirationDate(dateValue);
                        }}
                        min={new Date().toLocaleDateString('en-CA')}
                        style={{ width: '180px' }}
                      />
                    </div>
                  )}
                </div>
              </div>
              {isAtMaxTokens ? (
                <Tooltip content={`The number of active tokens has reached the limit (${appConfig.token.max_tokens_per_recipient}). Cannot generate new tokens.`} relationship="label">
                  <Button appearance="primary" disabled style={{ marginTop: tokens.spacingVerticalS }}>
                    Generate Token (Profile will download automatically)
                  </Button>
                </Tooltip>
              ) : (
                <Button appearance="primary" onClick={handleGenerateToken} style={{ marginTop: tokens.spacingVerticalS }}>
                  Generate Token (Profile will download automatically)
                </Button>
              )}
            </div>
          </DialogContent>
          <DialogActions>
            <Button appearance="secondary" onClick={handleClose}>
              Close
            </Button>
          </DialogActions>
        </DialogBody>
      </DialogSurface>
    </Dialog>
  );
};
