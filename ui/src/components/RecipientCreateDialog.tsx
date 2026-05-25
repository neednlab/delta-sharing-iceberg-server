/**
 * RecipientCreateDialog Component
 * 创建Recipient的对话框，包含名称、注释和授权Share选择
 */

import React, { useState, useEffect, useCallback } from 'react';
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
  makeStyles,
  tokens,
} from '@fluentui/react-components';
import type { Share } from '../types';
import { recipientApi, shareApi } from '../services/api';

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

interface RecipientCreateDialogProps {
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
}

export const RecipientCreateDialog: React.FC<RecipientCreateDialogProps> = ({
  open,
  onClose,
  onCreated,
}) => {
  const styles = useStyles();

  const [name, setName] = useState('');
  const [comment, setComment] = useState('');
  const [availableShares, setAvailableShares] = useState<Share[]>([]);
  const [selectedShares, setSelectedShares] = useState<string[]>([]);
  const [loadingShares, setLoadingShares] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

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
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadShares();
  }, [loadShares]);

  const handleCreate = async () => {
    setSubmitting(true);
    setError(null);
    try {
      await recipientApi.createRecipient({
        name,
        comment: comment || undefined,
      });

      for (const shareName of selectedShares) {
        try {
          await recipientApi.grantShareToRecipient(name, shareName);
        } catch (err) {
          console.error(`Failed to grant share ${shareName}:`, err);
        }
      }

      onCreated();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create recipient');
    } finally {
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
          <DialogTitle>Add Recipient</DialogTitle>
          <DialogContent className={styles.dialogContent}>
            {error && (
              <div style={{ color: tokens.colorPaletteRedForeground1, marginBottom: tokens.spacingVerticalS }}>
                {error}
              </div>
            )}
            <div className={styles.formField}>
              <Label htmlFor="createRecipientName" required>
                Recipient Name
              </Label>
              <Input
                id="createRecipientName"
                value={name}
                onChange={(_, data) => setName(data.value)}
                placeholder="Enter recipient name"
              />
            </div>
            <div className={styles.formField}>
              <Label htmlFor="createRecipientComment">Comment</Label>
              <Textarea
                id="createRecipientComment"
                value={comment}
                onChange={(_, data) => setComment(data.value)}
                placeholder="Enter comment"
                resize="vertical"
              />
            </div>
            <div className={styles.formField}>
              <Label>Authorize Shares (Optional)</Label>
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
              onClick={handleCreate}
              disabled={!name || submitting}
            >
              Create
            </Button>
          </DialogActions>
        </DialogBody>
      </DialogSurface>
    </Dialog>
  );
};
