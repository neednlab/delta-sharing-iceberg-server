/**
 * RecipientEditDialog Component
 * 编辑Recipient的对话框，包含名称、注释、状态切换和授权Share管理
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
  Input,
  Label,
  Textarea,
  Checkbox,
  Spinner,
  Switch,
  makeStyles,
  tokens,
} from '@fluentui/react-components';
import type { Recipient, Share } from '../types';
import { recipientApi, shareApi } from '../services/api';
import { getRecipientDisplayName } from '../utils';

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

interface RecipientEditDialogProps {
  open: boolean;
  onClose: () => void;
  onUpdated: () => void;
  recipient: Recipient;
}

export const RecipientEditDialog: React.FC<RecipientEditDialogProps> = ({
  open,
  onClose,
  onUpdated,
  recipient,
}) => {
  const styles = useStyles();

  const recipientName = getRecipientDisplayName(recipient);

  const [name, setName] = useState(recipientName);
  const [comment, setComment] = useState(recipient.comment || '');
  const [isActive, setIsActive] = useState(recipient.is_active);
  const [availableShares, setAvailableShares] = useState<Share[]>([]);
  const [selectedShares, setSelectedShares] = useState<string[]>([]);
  const [loadingShares, setLoadingShares] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const isSubmittingRef = useRef(false);

  const loadShares = useCallback(async () => {
    setLoadingShares(true);
    try {
      const response = await shareApi.getShares({ maxResults: 100 });
      setAvailableShares(response.items || []);
    } catch (err) {
      console.error('Failed to load shares:', err);
    } finally {
      setLoadingShares(false);
    }
  }, []);

  useEffect(() => {
    /* eslint-disable react-hooks/set-state-in-effect */
    loadShares();

    recipientApi.getRecipientShares(recipientName).then(response => {
      setSelectedShares(response.items.map(item => item.share_name));
    }).catch(() => {
      setSelectedShares([]);
      });
    /* eslint-enable react-hooks/set-state-in-effect */
  }, [recipientName, loadShares]);

  const handleUpdate = async () => {
    if (isSubmittingRef.current) return;
    isSubmittingRef.current = true;
    setSubmitting(true);
    setError(null);

    const effectiveName = name !== recipientName ? name : recipientName;

    const errors: string[] = [];

    try {
      await recipientApi.updateRecipient(recipientName, {
        newName: name !== recipientName ? name : undefined,
        comment: comment || undefined,
        isActive,
      });

      const currentSharesResponse = await recipientApi.getRecipientShares(effectiveName);
      const currentShareNames = currentSharesResponse.items.map(item => item.share_name);

      const sharesToAdd = selectedShares.filter(s => !currentShareNames.includes(s));
      const sharesToRemove = currentShareNames.filter(s => !selectedShares.includes(s));

      for (const shareName of sharesToAdd) {
        try {
          await recipientApi.grantShareToRecipient(effectiveName, shareName);
        } catch (err) {
          const msg = err instanceof Error ? err.message : String(err);
          errors.push(`Failed to grant share ${shareName}: ${msg}`);
        }
      }

      for (const shareName of sharesToRemove) {
        try {
          await recipientApi.revokeShareFromRecipient(effectiveName, shareName);
        } catch (err) {
          const msg = err instanceof Error ? err.message : String(err);
          errors.push(`Failed to revoke share ${shareName}: ${msg}`);
        }
      }

      if (errors.length > 0) {
        setError(`Some operations failed:\n${errors.join('\n')}`);
      } else {
        onUpdated();
        onClose();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update recipient');
    } finally {
      isSubmittingRef.current = false;
      setSubmitting(false);
    }
  };

  const handleClose = () => {
    if (!submitting) {
      onClose();
    }
  };

  return (
    <Dialog open={open} onOpenChange={(_, data) => { if (!data.open) handleClose(); }}>
      <DialogSurface>
        <DialogBody>
          <DialogTitle>Update Recipient</DialogTitle>
          <DialogContent className={styles.dialogContent}>
            {error && (
              <div style={{ color: tokens.colorPaletteRedForeground1, marginBottom: tokens.spacingVerticalS }}>
                {error}
              </div>
            )}
            <div className={styles.formField}>
              <Label htmlFor="editRecipientName" required>
                Recipient Name
              </Label>
              <Input
                id="editRecipientName"
                value={name}
                onChange={(_, data) => setName(data.value)}
                placeholder="Enter recipient name"
              />
            </div>
            <div className={styles.formField}>
              <Label htmlFor="editRecipientComment">Comment</Label>
              <Textarea
                id="editRecipientComment"
                value={comment}
                onChange={(_, data) => setComment(data.value)}
                placeholder="Enter comment"
                resize="vertical"
              />
            </div>
            <div className={styles.formField}>
              <Label>Status</Label>
              <Switch
                checked={isActive}
                onChange={(_, data) => setIsActive(data.checked)}
                label={isActive ? 'Active' : 'Disabled'}
              />
            </div>
            <div className={styles.formField}>
              <Label>Authorized Shares</Label>
              {loadingShares ? (
                <Spinner size="tiny" label="Loading shares..." />
              ) : availableShares.length === 0 ? (
                <span style={{ color: tokens.colorNeutralForeground3 }}>No shares available</span>
              ) : (
                <div style={{ maxHeight: '200px', overflowY: 'auto', border: `1px solid ${tokens.colorNeutralStroke1}`, borderRadius: tokens.borderRadiusMedium, padding: tokens.spacingHorizontalS }}>
                  {availableShares.map((share) => (
                    <Checkbox
                      key={share.share_id}
                      checked={selectedShares.includes(share.share_name)}
                      onChange={(_, data) => {
                        if (data.checked) {
                          setSelectedShares([...selectedShares, share.share_name]);
                        } else {
                          setSelectedShares(selectedShares.filter(s => s !== share.share_name));
                        }
                      }}
                      label={share.share_name}
                    />
                  ))}
                </div>
              )}
            </div>
          </DialogContent>
          <DialogActions>
            <Button appearance="secondary" onClick={handleClose} disabled={submitting}>
              Cancel
            </Button>
            <Button
              appearance="primary"
              onClick={handleUpdate}
              disabled={!name || submitting}
            >
              Update
            </Button>
          </DialogActions>
        </DialogBody>
      </DialogSurface>
    </Dialog>
  );
};
