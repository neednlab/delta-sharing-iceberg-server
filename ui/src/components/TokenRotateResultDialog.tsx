/**
 * TokenRotateResultDialog Component
 * Token轮换结果对话框：展示成功图标、新Token前缀、"Revoke Old Token"按钮和后续步骤指导
 * 不暴露明文Token，不包含Copy按钮（P0安全修复）
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
  makeStyles,
  tokens,
} from '@fluentui/react-components';
import { CheckmarkCircleRegular } from '@fluentui/react-icons';

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

interface TokenRotateResultDialogProps {
  open: boolean;
  onClose: () => void;
  newTokenPrefix: string | null;
  oldTokenHash: string;
  onRevokeOldToken?: () => void;
}

export const TokenRotateResultDialog: React.FC<TokenRotateResultDialogProps> = ({
  open,
  onClose,
  newTokenPrefix,
  oldTokenHash,
  onRevokeOldToken,
}) => {
  const styles = useStyles();

  const handleClose = () => {
    onClose();
  };

  return (
    <Dialog open={open} onOpenChange={(_, data) => { if (!data.open) handleClose(); }}>
      <DialogSurface style={{ minWidth: '520px' }}>
        <DialogBody>
          <DialogTitle style={{ display: 'flex', alignItems: 'center', gap: tokens.spacingHorizontalS }}>
            <CheckmarkCircleRegular style={{ color: tokens.colorPaletteGreenForeground1, fontSize: '24px' }} />
            Token Rotated Successfully
          </DialogTitle>
          <DialogContent className={styles.dialogContent}>
            {/* 新 Token 前缀展示（与 Token 列表表格格式一致，不暴露明文 token） */}
            <div className={styles.formField}>
              <Label>New Token</Label>
              <div className={styles.tokenDisplay}>
                <span>
                  {newTokenPrefix ? `${newTokenPrefix}...` : 'New token generated successfully'}
                </span>
              </div>
            </div>

            {/* Profile 已自动下载确认 */}
            <div style={{ color: tokens.colorNeutralForeground2, fontSize: tokens.fontSizeBase200 }}>
              Profile file has been automatically downloaded with the new token.
            </div>

            {/* 后续步骤指引 */}
            <MessageBar intent="warning" style={{ display: 'flex', alignItems: 'center' }}>
              <MessageBarBody>
                <div style={{ fontWeight: tokens.fontWeightSemibold, marginBottom: tokens.spacingVerticalXS }}>
                  Next Steps:
                </div>
                <div style={{ paddingLeft: tokens.spacingHorizontalS }}>
                  <div>1. Distribute the new profile to your data consumer</div>
                  <div>2. Confirm the consumer has switched successfully</div>
                  <div>3. Return to this dialog and revoke the old token</div>
                </div>
              </MessageBarBody>
            </MessageBar>
          </DialogContent>
          <DialogActions>
            {/* Revoke Old Token 快捷按钮 */}
            {oldTokenHash && onRevokeOldToken && (
              <Button
                appearance="outline"
                onClick={onRevokeOldToken}
              >
                Revoke Old Token
              </Button>
            )}
            <Button appearance="secondary" onClick={handleClose}>
              Close
            </Button>
          </DialogActions>
        </DialogBody>
      </DialogSurface>
    </Dialog>
  );
};
