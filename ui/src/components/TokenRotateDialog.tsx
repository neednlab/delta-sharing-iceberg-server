/**
 * TokenRotateDialog Component
 * Token轮换确认对话框：展示旧Token前缀、轮换步骤说明、新Token过期设置
 */

import React from 'react';
import {
  Dialog,
  DialogSurface,
  DialogTitle,
  DialogBody,
  DialogContent,
  DialogActions,
  Button,
  Label,
  MessageBar,
  MessageBarBody,
  Dropdown,
  Option,
  Input,
  makeStyles,
  tokens,
} from '@fluentui/react-components';
import type { Recipient } from '../types';
import { useExpiration } from '../hooks/useExpiration';
import { EXPIRATION_OPTIONS } from '../utils';

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
  tokenDisplay: {
    backgroundColor: tokens.colorNeutralBackground2,
    padding: tokens.spacingHorizontalM,
    borderRadius: tokens.borderRadiusMedium,
    fontFamily: 'monospace',
    wordBreak: 'break-all',
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: tokens.spacingHorizontalS,
  },
});

interface TokenRotateDialogProps {
  open: boolean;
  onClose: () => void;
  onRotated: (expirationHours: number | undefined, requireAuthorizedShares: boolean) => void;
  targetToken: {
    token_hash: string;
    token_prefix: string;
    created_at: number;
  };
  recipient: Recipient;
  requireAuthorizedShares?: boolean;
}

export const TokenRotateDialog: React.FC<TokenRotateDialogProps> = ({
  open,
  onClose,
  onRotated,
  targetToken,
  requireAuthorizedShares = false,
}) => {
  const styles = useStyles();

  const {
    expirationHours,
    expirationOption,
    setExpirationOption,
    customExpirationDate,
    setCustomExpirationDate,
  } = useExpiration('30 days');

  const handleClose = () => {
    onClose();
  };

  const handleRotate = () => {
    onRotated(expirationHours, requireAuthorizedShares);
  };

  return (
    <Dialog open={open} onOpenChange={(_, data) => { if (!data.open) handleClose(); }}>
      <DialogSurface style={{ minWidth: '500px' }}>
        <DialogBody>
          <DialogTitle>Rotate Token</DialogTitle>
          <DialogContent className={styles.dialogContent}>
            <MessageBar intent="info" style={{ marginBottom: tokens.spacingVerticalM }}>
              <MessageBarBody>
                Token rotation creates a new token while keeping the old one active.
                This ensures zero downtime for your data consumers.
              </MessageBarBody>
            </MessageBar>

            <div className={styles.formField}>
              <Label>Old Token</Label>
              <div className={styles.tokenDisplay}>
                <span>{targetToken.token_prefix}...</span>
              </div>
            </div>

            <div className={styles.formField}>
              <Label>Rotation Steps</Label>
              <div style={{ paddingLeft: tokens.spacingHorizontalM, color: tokens.colorNeutralForeground2 }}>
                <div style={{ marginBottom: tokens.spacingVerticalXS }}>1. A new token will be generated</div>
                <div style={{ marginBottom: tokens.spacingVerticalXS }}>2. Profile file will be automatically downloaded with the new token</div>
                <div style={{ marginBottom: tokens.spacingVerticalXS }}>3. The old token remains active (zero downtime)</div>
                <div style={{ marginBottom: tokens.spacingVerticalXS }}>4. Revoke the old token after client migration</div>
              </div>
            </div>

            <div className={styles.formField}>
              <Label htmlFor="rotateExpirationSelect">New Token Expiration</Label>
              <div style={{ display: 'flex', gap: tokens.spacingHorizontalS, alignItems: 'flex-start' }}>
                <Dropdown
                  id="rotateExpirationSelect"
                  value={expirationOption}
                  onOptionSelect={(_, data) => {
                    setExpirationOption(data.optionValue || '30 days');
                  }}
                  style={{ minWidth: '180px' }}
                >
                  {EXPIRATION_OPTIONS.map(opt => (
                    <Option key={opt.value} value={opt.value}>{opt.label}</Option>
                  ))}
                </Dropdown>
                {expirationOption === 'Custom' && (
                  <div style={{ marginLeft: tokens.spacingHorizontalS }}>
                    <Input
                      type="date"
                      id="rotateCustomDatePicker"
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
          </DialogContent>
          <DialogActions>
            <Button appearance="secondary" onClick={handleClose}>
              Cancel
            </Button>
            <Button appearance="primary" onClick={handleRotate}>
              Rotate Token
            </Button>
          </DialogActions>
        </DialogBody>
      </DialogSurface>
    </Dialog>
  );
};
