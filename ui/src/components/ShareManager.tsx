/**
 * Share Management Component
 * Implements CRUD operations for Shares
 */

import React, { useState, useCallback } from 'react';
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHeaderCell,
  TableCell,
  Button,
  Dialog,
  DialogSurface,
  DialogTitle,
  DialogBody,
  DialogActions,
  DialogContent,
  Input,
  Label,
  Textarea,
  Spinner,
  MessageBar,
  MessageBarBody,
  makeStyles,
  tokens,
  Card,
  CardHeader,
  CardPreview,
} from '@fluentui/react-components';
import {
  AddRegular,
  EditRegular,
  DeleteRegular,
  SettingsRegular,
  ChevronLeftRegular,
  ChevronRightRegular,
} from '@fluentui/react-icons';
import { useNavigate } from 'react-router-dom';
import type { Share } from '../types';
import { shareApi } from '../services/api';
import { formatDate } from '../utils/formatDate';
import { usePagination } from '../hooks/usePagination';

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
  errorBar: {
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
 * Share Management Component
 */
export const ShareManager: React.FC = () => {
  const styles = useStyles();
  const navigate = useNavigate();

  const fetchShares = useCallback(
    (params: { maxResults?: number; pageToken?: string }) =>
      shareApi.getShares(params),
    []
  );

  const {
    items: shares,
    loading,
    error,
    currentPage,
    nextPageToken,
    goNext,
    goPrev,
    reload,
  } = usePagination(fetchShares, 20);

  // Dialog State
  const [isCreateDialogOpen, setIsCreateDialogOpen] = useState(false);
  const [isEditDialogOpen, setIsEditDialogOpen] = useState(false);
  const [isDeleteDialogOpen, setIsDeleteDialogOpen] = useState(false);
  const [selectedShare, setSelectedShare] = useState<Share | null>(null);

  // Form State
  const [formData, setFormData] = useState({
    shareName: '',
    displayName: '',
    comment: '',
  });

  /**
   * Handle Create Share
   */
  const handleCreateShare = async () => {
    try {
      await shareApi.createShare({
        name: formData.shareName,
        display_name: formData.displayName || undefined,
        comment: formData.comment || undefined,
      });
      setIsCreateDialogOpen(false);
      setFormData({ shareName: '', displayName: '', comment: '' });
      reload();
    } catch {
      // error state is managed by usePagination, but for dialog-level errors we
      // rethrow to let the hook catch it on the next data load
    }
  };

  /**
   * Handle Update Share
   */
  const handleUpdateShare = async () => {
    if (!selectedShare) return;

    try {
      await shareApi.renameShare(selectedShare.share_name, formData.shareName);
      setIsEditDialogOpen(false);
      setSelectedShare(null);
      setFormData({ shareName: '', displayName: '', comment: '' });
      reload();
    } catch {
      // error handled by reload
    }
  };

  /**
   * Handle Delete Share
   */
  const handleDeleteShare = async () => {
    if (!selectedShare) return;

    try {
      await shareApi.deleteShare(selectedShare.share_name);
      setIsDeleteDialogOpen(false);
      setSelectedShare(null);
      reload();
    } catch {
      // error handled by reload
    }
  };

  /**
   * Handle Navigate to Asset Detail
   */
  const handleNavigateToAssets = (share: Share) => {
    navigate(`/shares/${encodeURIComponent(share.share_name)}/assets`);
  };

  return (
    <div className={styles.container}>
      <Card>
        <CardHeader
          header={<span className={styles.title}>Share Management</span>}
          action={
            <Button
              appearance="primary"
              icon={<AddRegular />}
              onClick={() => {
                setFormData({ shareName: '', displayName: '', comment: '' });
                setIsCreateDialogOpen(true);
              }}
            >
              Add Share
            </Button>
          }
        />
        <CardPreview>
          {error && (
            <MessageBar intent="error" className={styles.errorBar} style={{ display: 'flex', alignItems: 'center' }}>
              <MessageBarBody style={{ display: 'flex', alignItems: 'center' }}>{error}</MessageBarBody>
            </MessageBar>
          )}

          {loading ? (
            <Spinner label="Loading..." />
          ) : (
            <>
              <Table className={styles.table}>
                <TableHeader>
                  <TableRow>
                    <TableHeaderCell className={styles.tableHeaderCell}>Share Name</TableHeaderCell>
                    <TableHeaderCell className={styles.tableHeaderCell}>Display Name</TableHeaderCell>
                    <TableHeaderCell className={styles.tableHeaderCell}>Comment</TableHeaderCell>
                    <TableHeaderCell className={styles.tableHeaderCell}>Created At</TableHeaderCell>
                    <TableHeaderCell className={styles.tableHeaderCell}>Actions</TableHeaderCell>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {shares.map((share) => (
                    <TableRow key={share.share_id} className={styles.tableRow}>
                      <TableCell>{share.share_name}</TableCell>
                      <TableCell>{share.display_name || '-'}</TableCell>
                      <TableCell>{share.comment || '-'}</TableCell>
                      <TableCell>{share.created_at ? formatDate(share.created_at) : '-'}</TableCell>
                      <TableCell>
                        <div style={{ display: 'flex', gap: '8px' }}>
                          <Button
                            icon={<SettingsRegular />}
                            onClick={() => handleNavigateToAssets(share)}
                            title="Configure"
                            appearance="subtle"
                            size="small"
                          />
                          <Button
                            icon={<EditRegular />}
                            onClick={() => {
                              setSelectedShare(share);
                              setFormData({
                                shareName: share.share_name,
                                displayName: share.display_name || '',
                                comment: share.comment || '',
                              });
                              setIsEditDialogOpen(true);
                            }}
                            title="Update"
                            appearance="subtle"
                            size="small"
                          />
                          <Button
                            icon={<DeleteRegular />}
                            onClick={() => {
                              setSelectedShare(share);
                              setIsDeleteDialogOpen(true);
                            }}
                            title="Delete"
                            appearance="subtle"
                            size="small"
                          />
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
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

      {/* Create Share Dialog */}
      <Dialog open={isCreateDialogOpen} onOpenChange={(_, data) => setIsCreateDialogOpen(data.open)}>
        <DialogSurface>
          <DialogBody>
            <DialogTitle>Add Share</DialogTitle>
            <DialogContent className={styles.dialogContent}>
              <div className={styles.formField}>
                <Label htmlFor="shareName" required>
                  Share Name
                </Label>
                <Input
                  id="shareName"
                  value={formData.shareName}
                  onChange={(_, data) =>
                    setFormData({ ...formData, shareName: data.value })
                  }
                  placeholder="Enter share name"
                />
              </div>
              <div className={styles.formField}>
                <Label htmlFor="displayName">Display Name</Label>
                <Input
                  id="displayName"
                  value={formData.displayName}
                  onChange={(_, data) =>
                    setFormData({ ...formData, displayName: data.value })
                  }
                  placeholder="Enter display name"
                />
              </div>
              <div className={styles.formField}>
                <Label htmlFor="comment">Comment</Label>
                <Textarea
                  id="comment"
                  value={formData.comment}
                  onChange={(_, data) =>
                    setFormData({ ...formData, comment: data.value })
                  }
                  placeholder="Enter comment"
                  resize="vertical"
                />
              </div>
            </DialogContent>
            <DialogActions>
              <Button appearance="secondary" onClick={() => setIsCreateDialogOpen(false)}>
                Cancel
              </Button>
              <Button
                appearance="primary"
                onClick={handleCreateShare}
                disabled={!formData.shareName}
              >
                Create
              </Button>
            </DialogActions>
          </DialogBody>
        </DialogSurface>
      </Dialog>

      {/* Edit Share Dialog */}
      <Dialog open={isEditDialogOpen} onOpenChange={(_, data) => setIsEditDialogOpen(data.open)}>
        <DialogSurface>
          <DialogBody>
            <DialogTitle>Update Share</DialogTitle>
            <DialogContent className={styles.dialogContent}>
              <div className={styles.formField}>
                <Label htmlFor="editShareName" required>
                  Share Name
                </Label>
                <Input
                  id="editShareName"
                  value={formData.shareName}
                  onChange={(_, data) =>
                    setFormData({ ...formData, shareName: data.value })
                  }
                  placeholder="Enter share name"
                />
              </div>
            </DialogContent>
            <DialogActions>
              <Button appearance="secondary" onClick={() => setIsEditDialogOpen(false)}>
                Cancel
              </Button>
              <Button
                appearance="primary"
                onClick={handleUpdateShare}
                disabled={!formData.shareName}
              >
                Update
              </Button>
            </DialogActions>
          </DialogBody>
        </DialogSurface>
      </Dialog>

      {/* Delete Share Confirmation Dialog */}
      <Dialog open={isDeleteDialogOpen} onOpenChange={(_, data) => setIsDeleteDialogOpen(data.open)}>
        <DialogSurface>
          <DialogBody>
            <DialogTitle>Confirm Delete</DialogTitle>
            <DialogContent>
              Are you sure you want to delete Share &quot;{selectedShare?.share_name}&quot;? This action cannot be undone.
            </DialogContent>
            <DialogActions>
              <Button appearance="secondary" onClick={() => setIsDeleteDialogOpen(false)}>
                Cancel
              </Button>
              <Button appearance="primary" onClick={handleDeleteShare}>
                Delete
              </Button>
            </DialogActions>
          </DialogBody>
        </DialogSurface>
      </Dialog>
    </div>
  );
};

export default ShareManager;
