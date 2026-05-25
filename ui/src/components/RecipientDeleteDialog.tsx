/**
 * RecipientDeleteDialog Component
 * 删除Recipient的确认对话框
 */

import React, { useState } from 'react';
import {
  Dialog,
  DialogSurface,
  DialogTitle,
  DialogBody,
  DialogContent,
  DialogActions,
  Button,
  tokens,
} from '@fluentui/react-components';
import type { Recipient } from '../types';
import { recipientApi } from '../services/api';
import { getRecipientDisplayName } from '../utils';

interface RecipientDeleteDialogProps {
  open: boolean;
  onClose: () => void;
  onDeleted: () => void;
  recipient: Recipient;
}

export const RecipientDeleteDialog: React.FC<RecipientDeleteDialogProps> = ({
  open,
  onClose,
  onDeleted,
  recipient,
}) => {
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const recipientName = getRecipientDisplayName(recipient);

  const handleDelete = async () => {
    setSubmitting(true);
    setError(null);
    try {
      await recipientApi.deleteRecipient(recipientName);
      onDeleted();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete recipient');
    } finally {
      setSubmitting(false);
    }
  };

  const handleClose = () => {
    if (!submitting) {
      setError(null);
      onClose();
    }
  };

  return (
    <Dialog open={open} onOpenChange={(_, data) => { if (!data.open) handleClose(); }}>
      <DialogSurface>
        <DialogBody>
          <DialogTitle>Confirm Delete</DialogTitle>
          <DialogContent>
            {error && (
              <div style={{ color: tokens.colorPaletteRedForeground1, marginBottom: tokens.spacingVerticalM }}>
                {error}
              </div>
            )}
            Are you sure you want to delete Recipient &quot;{recipientName}&quot;? This action cannot be undone.
          </DialogContent>
          <DialogActions>
            <Button appearance="secondary" onClick={handleClose} disabled={submitting}>
              Cancel
            </Button>
            <Button appearance="primary" onClick={handleDelete} disabled={submitting}>
              Delete
            </Button>
          </DialogActions>
        </DialogBody>
      </DialogSurface>
    </Dialog>
  );
};
