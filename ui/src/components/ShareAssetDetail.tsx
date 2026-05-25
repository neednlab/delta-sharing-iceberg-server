/**
 * Share Asset Detail Component
 * Displays and manages assets (Schema/Table) associated with a Share
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
  Dialog,
  DialogSurface,
  DialogTitle,
  DialogBody,
  DialogActions,
  DialogContent,
  Input,
  Label,
  Dropdown,
  Option,
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
  ArrowLeftRegular,
  AddRegular,
  DeleteRegular,
  EditRegular,
  ArrowSyncRegular,
} from '@fluentui/react-icons';
import { useNavigate, useParams } from 'react-router-dom';
import { shareApi } from '../services/api';
import type { SchemaAsset, TableAsset, AddShareObjectRequest } from '../types';
import { renderSourceMapping } from '../utils/renderSourceMapping';

const useStyles = makeStyles({
  container: {
    padding: tokens.spacingHorizontalL,
  },
  header: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: tokens.spacingVerticalL,
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
  tableRow: {
    '&:hover': {
      backgroundColor: tokens.colorNeutralBackground1Hover,
    },
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
  assetTypeTag: {
    display: 'inline-block',
    padding: '2px 8px',
    borderRadius: '4px',
    fontSize: tokens.fontSizeBase200,
    fontWeight: tokens.fontWeightMedium,
  },
  schemaTag: {
    backgroundColor: tokens.colorBrandBackground2,
    color: tokens.colorBrandForeground1,
  },
  tableTag: {
    backgroundColor: tokens.colorPaletteBlueBackground2,
    color: tokens.colorPaletteBlueForeground2,
  },
  expandedRow: {
    backgroundColor: tokens.colorNeutralBackground2,
  },
  nestedTable: {
    width: '100%',
    marginLeft: tokens.spacingHorizontalL,
    borderCollapse: 'collapse',
  },
  actionButtons: {
    display: 'flex',
    gap: '4px',
  },
  bulkActionBar: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: `${tokens.spacingVerticalS} ${tokens.spacingHorizontalM}`,
    backgroundColor: tokens.colorNeutralBackground2,
    borderRadius: tokens.borderRadiusMedium,
    marginBottom: tokens.spacingVerticalM,
  },
  selectedCount: {
    fontWeight: tokens.fontWeightMedium,
  },
});

interface AddAssetForm {
  assetType: 'SCHEMA' | 'TABLE';
  sharedSchema: string;
  sharedTable: string;
  metastoreDb: string;
  metastoreTable: string;
  location: string;
}

export const ShareAssetDetail: React.FC = () => {
  const styles = useStyles();
  const navigate = useNavigate();
  const { shareId } = useParams<{ shareId: string }>();

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [schemas, setSchemas] = useState<SchemaAsset[]>([]);
  const [tables, setTables] = useState<TableAsset[]>([]);
  const [expandedSchema, setExpandedSchema] = useState<string | null>(null);
  const [isAddDialogOpen, setIsAddDialogOpen] = useState(false);
  const [isDeleteDialogOpen, setIsDeleteDialogOpen] = useState(false);
  const [isEditDialogOpen, setIsEditDialogOpen] = useState(false);
  const [itemToDelete, setItemToDelete] = useState<{ type: string; name: string; schemaName?: string } | null>(null);
  const [tableToEdit, setTableToEdit] = useState<TableAsset | null>(null);
  const [syncingSchema, setSyncingSchema] = useState<string | null>(null);
  const [syncSuccessMessage, setSyncSuccessMessage] = useState<string | null>(null);
  const [syncErrorMessage, setSyncErrorMessage] = useState<string | null>(null);
  const [dialogError, setDialogError] = useState<string | null>(null);
  const [editDialogError, setEditDialogError] = useState<string | null>(null);

  useEffect(() => {
    if (syncSuccessMessage) {
      const timer = setTimeout(() => {
        setSyncSuccessMessage(null);
      }, 5000);
      return () => clearTimeout(timer);
    }
  }, [syncSuccessMessage]);

  const [addForm, setAddForm] = useState<AddAssetForm>({
    assetType: 'SCHEMA',
    sharedSchema: '',
    sharedTable: '',
    metastoreDb: '',
    metastoreTable: '',
    location: '',
  });

  const [editForm, setEditForm] = useState({
    sharedSchema: '',
    sharedTable: '',
    metastoreDb: '',
    metastoreTable: '',
    location: '',
  });

  const loadAssets = useCallback(async () => {
    if (!shareId) return;
    setLoading(true);
    setError(null);
    try {
      const response = await shareApi.getShareObjects(decodeURIComponent(shareId));
      const sortedSchemas = (response.schemas || []).sort((a, b) =>
        a.schema_name.localeCompare(b.schema_name)
      );
      setSchemas(sortedSchemas);
      setTables(response.tables || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load assets');
    } finally {
      setLoading(false);
    }
  }, [shareId]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadAssets();
  }, [loadAssets]);

  const handleBack = () => {
    navigate('/shares');
  };

  const toggleSchemaExpansion = (schemaId: string) => {
    setExpandedSchema(expandedSchema === schemaId ? null : schemaId);
  };

  const getTablesForSchema = (schemaId: string | null) => {
    return tables.filter((t) => t.linked_schema_id === schemaId);
  };

  const getDirectTables = () => {
    return tables.filter((t) => t.linked_schema_id === null);
  };

  const handleAddAsset = async () => {
    if (!shareId) return;

    // 校验 TABLE 类型资产的 location 必须以 "cosn:" 开头
    if (addForm.assetType === 'TABLE' && addForm.location && !addForm.location.startsWith('cosn:')) {
      setDialogError('Location must start with "cosn:" (e.g., cosn://bucket-name/path/to/table)');
      return;
    }

    try {
      if (addForm.assetType === 'SCHEMA' && addForm.sharedSchema) {
        await shareApi.addShareObject(decodeURIComponent(shareId), {
          schema_name: addForm.sharedSchema,
          metastore_db: addForm.metastoreDb,
        });
        setIsAddDialogOpen(false);
        setAddForm({
          assetType: 'SCHEMA',
          sharedSchema: '',
          sharedTable: '',
          metastoreDb: '',
          metastoreTable: '',
          location: '',
        });
        setSyncingSchema(addForm.sharedSchema);
        setSyncErrorMessage(null);
        setSyncSuccessMessage(null);
        try {
          const result = await shareApi.syncSchemaTables(
            decodeURIComponent(shareId),
            addForm.sharedSchema,
            addForm.metastoreDb || undefined
          );
          loadAssets();
          setSyncSuccessMessage(
            `Schema "${addForm.sharedSchema}" added and synced: ${result.synced_count} tables synced, ${result.skipped_count} skipped, ${result.deleted_count} deleted`
          );
        } catch (syncErr) {
          setSyncErrorMessage(syncErr instanceof Error ? syncErr.message : 'Failed to sync tables');
        } finally {
          setSyncingSchema(null);
        }
      } else if (addForm.assetType === 'TABLE' && addForm.sharedTable) {
        const req: AddShareObjectRequest = {
          schema_name: addForm.sharedSchema,
          table_name: addForm.sharedTable,
          metastore_db: addForm.metastoreDb || addForm.sharedSchema,
          location: addForm.location,
        };
        if (addForm.metastoreTable) {
          req.metastore_table = addForm.metastoreTable;
        }
        await shareApi.addShareObject(decodeURIComponent(shareId), req);
        setIsAddDialogOpen(false);
        setAddForm({
          assetType: 'SCHEMA',
          sharedSchema: '',
          sharedTable: '',
          metastoreDb: '',
          metastoreTable: '',
          location: '',
        });
        loadAssets();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to add asset');
    }
  };

  const handleDeleteConfirm = async () => {
    if (!shareId || !itemToDelete) return;

    try {
      const objectType = itemToDelete.type.toLowerCase();
      await shareApi.deleteShareObject(
        decodeURIComponent(shareId),
        objectType,
        itemToDelete.name,
        itemToDelete.schemaName
      );
      setIsDeleteDialogOpen(false);
      setItemToDelete(null);
      loadAssets();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete asset');
    }
  };

  const handleEditTable = async () => {
    if (!shareId || !tableToEdit) return;

    // 校验 location 必须以 "cosn:" 开头
    if (editForm.location && !editForm.location.startsWith('cosn:')) {
      setEditDialogError('Location must start with "cosn:" (e.g., cosn://bucket-name/path/to/table)');
      return;
    }

    try {
      await shareApi.updateShareObject(
        decodeURIComponent(shareId),
        'table',
        tableToEdit.table_name,
        {
          schema_name: tableToEdit.schema_name,
          location: editForm.location,
          metastore_db: editForm.metastoreDb,
          metastore_table: editForm.metastoreTable || undefined,
          new_schema_name: editForm.sharedSchema || undefined,
        }
      );
      setIsEditDialogOpen(false);
      setTableToEdit(null);
      loadAssets();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update asset');
    }
  };

  const openEditDialog = (table: TableAsset) => {
    setTableToEdit(table);
    setEditForm({
      sharedSchema: table.schema_name,
      sharedTable: table.table_name,
      metastoreDb: table.metastore_db,
      metastoreTable: table.metastore_table,
      location: table.location,
    });
    setIsEditDialogOpen(true);
  };

  const handleSyncSchemaTables = async (schema: SchemaAsset) => {
    if (!shareId) return;

    setSyncingSchema(schema.schema_name);
    setSyncErrorMessage(null);
    setSyncSuccessMessage(null);

    try {
      const result = await shareApi.syncSchemaTables(
        decodeURIComponent(shareId),
        schema.schema_name,
        schema.metastore_db
      );
      setSyncSuccessMessage(
        `Sync completed: ${result.synced_count} synced, ${result.skipped_count} skipped, ${result.deleted_count} deleted`
      );
      loadAssets();
    } catch (err) {
      setSyncErrorMessage(err instanceof Error ? err.message : 'Failed to sync tables');
    } finally {
      setSyncingSchema(null);
    }
  };

  const confirmDelete = (type: string, name: string, schemaName?: string) => {
    setItemToDelete({ type, name, schemaName });
    setIsDeleteDialogOpen(true);
  };

  const renderAssetTypeTag = (type: 'schema' | 'table') => {
    const tagStyle = type === 'schema' ? styles.schemaTag : styles.tableTag;
    return (
      <span className={`${styles.assetTypeTag} ${tagStyle}`}>
        {type.toUpperCase()}
      </span>
    );
  };



  return (
    <div className={styles.container}>
      <Card>
        <CardHeader
          header={
            <div style={{ display: 'flex', alignItems: 'center', gap: tokens.spacingHorizontalM }}>
              <Button
                appearance="subtle"
                icon={<ArrowLeftRegular />}
                onClick={handleBack}
              >
                Back to Shares
              </Button>
              <span className={styles.title}>Share Assets: {shareId}</span>
            </div>
          }
          action={
            <Button
              appearance="primary"
              icon={<AddRegular />}
              onClick={() => setIsAddDialogOpen(true)}
            >
              Add Asset
            </Button>
          }
        />
        <CardPreview>
          {error && (
            <MessageBar intent="error" className={styles.errorBar} style={{ display: 'flex', alignItems: 'center' }}>
              <MessageBarBody style={{ display: 'flex', alignItems: 'center' }}>{error}</MessageBarBody>
            </MessageBar>
          )}

          {syncErrorMessage && (
            <MessageBar intent="error" className={styles.errorBar} style={{ display: 'flex', alignItems: 'center' }}>
              <MessageBarBody style={{ display: 'flex', alignItems: 'center' }}>{syncErrorMessage}</MessageBarBody>
            </MessageBar>
          )}

          {syncSuccessMessage && (
            <MessageBar intent="success" className={styles.errorBar} style={{ display: 'flex', alignItems: 'center' }}>
              <MessageBarBody style={{ display: 'flex', alignItems: 'center' }}>{syncSuccessMessage}</MessageBarBody>
            </MessageBar>
          )}

          {loading ? (
            <Spinner label="Loading..." />
          ) : (
            <Table className={styles.table}>
              <TableHeader>
                <TableRow>
                  <TableHeaderCell style={{ width: '30px' }}></TableHeaderCell>
                  <TableHeaderCell>Asset Type</TableHeaderCell>
                  <TableHeaderCell>Shared Schema</TableHeaderCell>
                  <TableHeaderCell>Shared Table</TableHeaderCell>
                  <TableHeaderCell>Source Mapping</TableHeaderCell>
                  <TableHeaderCell>Location</TableHeaderCell>
                  <TableHeaderCell>Actions</TableHeaderCell>
                </TableRow>
              </TableHeader>
              <TableBody>
                {schemas.map((schema) => {
                  const schemaTables = getTablesForSchema(schema.schema_id);
                  const isExpanded = expandedSchema === schema.schema_id;

                  return (
                    <React.Fragment key={schema.schema_id}>
                      <TableRow className={styles.tableRow}>
                        <TableCell>
                          {schemaTables.length > 0 && (
                            <Button
                              appearance="subtle"
                              size="small"
                              onClick={() => toggleSchemaExpansion(schema.schema_id)}
                            >
                              {isExpanded ? '▼' : '▶'}
                            </Button>
                          )}
                        </TableCell>
                        <TableCell>{renderAssetTypeTag('schema')}</TableCell>
                        <TableCell>{schema.schema_name}</TableCell>
                        <TableCell>-</TableCell>
                        <TableCell>{renderSourceMapping(schema.metastore_db, undefined, true, schema.schema_name)}</TableCell>
                        <TableCell>-</TableCell>
                        <TableCell>
                          <div className={styles.actionButtons}>
                            <Button
                              appearance="subtle"
                              size="small"
                              icon={syncingSchema === schema.schema_name ? <Spinner size="tiny" /> : <ArrowSyncRegular />}
                              onClick={() => handleSyncSchemaTables(schema)}
                              disabled={syncingSchema !== null}
                              title="Sync Tables"
                            />
                            <Button
                              appearance="subtle"
                              size="small"
                              icon={<DeleteRegular />}
                              onClick={() => confirmDelete('schema', schema.schema_name)}
                            />
                          </div>
                        </TableCell>
                      </TableRow>
                      {isExpanded &&
                        schemaTables.map((table) => (
                          <TableRow key={table.table_id} className={styles.expandedRow}>
                            <TableCell></TableCell>
                            <TableCell>{renderAssetTypeTag('table')}</TableCell>
                            <TableCell>{table.schema_name}</TableCell>
                            <TableCell>{table.table_name}</TableCell>
                            <TableCell>{renderSourceMapping(table.metastore_db, table.metastore_table, false, table.schema_name)}</TableCell>
                            <TableCell>{table.location || '-'}</TableCell>
                            <TableCell>
                              <span style={{ color: tokens.colorNeutralForeground3, fontSize: tokens.fontSizeBase200 }}>
                                (managed by schema)
                              </span>
                            </TableCell>
                          </TableRow>
                        ))}
                    </React.Fragment>
                  );
                })}
                {getDirectTables().map((table) => (
                  <TableRow key={table.table_id} className={styles.tableRow}>
                    <TableCell></TableCell>
                    <TableCell>{renderAssetTypeTag('table')}</TableCell>
                    <TableCell>{table.schema_name || '-'}</TableCell>
                    <TableCell>{table.table_name}</TableCell>
                    <TableCell>{renderSourceMapping(table.metastore_db, table.metastore_table, false, table.schema_name)}</TableCell>
                    <TableCell>{table.location || '-'}</TableCell>
                    <TableCell>
                      <div className={styles.actionButtons}>
                        <Button
                          appearance="subtle"
                          size="small"
                          icon={<EditRegular />}
                          onClick={() => openEditDialog(table)}
                        />
                        <Button
                          appearance="subtle"
                          size="small"
                          icon={<DeleteRegular />}
                          onClick={() => confirmDelete('table', table.table_name, table.schema_name || undefined)}
                        />
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
                {schemas.length === 0 && getDirectTables().length === 0 && (
                  <TableRow>
                    <TableCell colSpan={7} style={{ textAlign: 'center', padding: tokens.spacingVerticalL }}>
                      No assets configured. Click "Add Asset" to add schemas or tables.
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          )}
        </CardPreview>
      </Card>

      {/* Add Asset Dialog */}
      <Dialog open={isAddDialogOpen} onOpenChange={(_, data) => {
        setIsAddDialogOpen(data.open);
        if (!data.open) setDialogError(null);
      }}>
        <DialogSurface>
          <DialogBody>
            <DialogTitle>Add New Asset</DialogTitle>
            <DialogContent className={styles.dialogContent}>
              <div className={styles.formField}>
                <Label>Asset Type</Label>
                <Dropdown
                  value={addForm.assetType}
                  onOptionSelect={(_, data) =>
                    setAddForm({ ...addForm, assetType: data.optionValue as 'SCHEMA' | 'TABLE' })
                  }
                >
                  <Option value="SCHEMA">Schema</Option>
                  <Option value="TABLE">Table</Option>
                </Dropdown>
              </div>
              {addForm.assetType === 'SCHEMA' && (
                <>
                  <div className={styles.formField}>
                    <Label htmlFor="sharedSchema">Shared Schema</Label>
                    <Input
                      id="sharedSchema"
                      value={addForm.sharedSchema}
                      onChange={(_, data) => setAddForm({ ...addForm, sharedSchema: data.value })}
                      placeholder="Enter shared schema name"
                    />
                  </div>
                  <div className={styles.formField}>
                    <Label htmlFor="metastoreDb">Metastore DB</Label>
                    <Input
                      id="metastoreDb"
                      value={addForm.metastoreDb}
                      onChange={(_, data) => setAddForm({ ...addForm, metastoreDb: data.value })}
                      placeholder="Leave blank to use Shared Schema by default"
                    />
                  </div>
                </>
              )}
              {addForm.assetType === 'TABLE' && (
                <>
                  <div className={styles.formField}>
                    <Label htmlFor="sharedSchema">Shared Schema *</Label>
                    <Input
                      id="sharedSchema"
                      value={addForm.sharedSchema}
                      onChange={(_, data) => setAddForm({ ...addForm, sharedSchema: data.value })}
                      placeholder="Enter shared schema name (required)"
                      required
                    />
                  </div>
                  <div className={styles.formField}>
                    <Label htmlFor="sharedTable">Shared Table *</Label>
                    <Input
                      id="sharedTable"
                      value={addForm.sharedTable}
                      onChange={(_, data) => setAddForm({ ...addForm, sharedTable: data.value })}
                      placeholder="Enter shared table name (required)"
                      required
                    />
                  </div>
                  <div className={styles.formField}>
                    <Label htmlFor="metastoreDb">Metastore DB</Label>
                    <Input
                      id="metastoreDb"
                      value={addForm.metastoreDb}
                      onChange={(_, data) => setAddForm({ ...addForm, metastoreDb: data.value })}
                      placeholder="Leave blank to use Shared Schema by default"
                    />
                  </div>
                  <div className={styles.formField}>
                    <Label htmlFor="metastoreTable">Metastore Table</Label>
                    <Input
                      id="metastoreTable"
                      value={addForm.metastoreTable}
                      onChange={(_, data) => setAddForm({ ...addForm, metastoreTable: data.value })}
                      placeholder="Leave blank to use Shared Table by default"
                    />
                  </div>
                  <div className={styles.formField}>
                    <Label htmlFor="location">Location *</Label>
                    <Input
                      id="location"
                      value={addForm.location}
                      onChange={(_, data) => {
                        setAddForm({ ...addForm, location: data.value });
                        setDialogError(null);
                      }}
                      placeholder="cosn://bucket-name/path/to/table (must start with cosn:)"
                      required
                    />
                  </div>
                </>
              )}
              {dialogError && (
                <MessageBar intent="error" style={{ marginTop: '8px', display: 'flex', alignItems: 'center' }}>
                  <MessageBarBody style={{ display: 'flex', alignItems: 'center' }}>{dialogError}</MessageBarBody>
                </MessageBar>
              )}
            </DialogContent>
            <DialogActions>
              <Button appearance="secondary" onClick={() => setIsAddDialogOpen(false)}>
                Cancel
              </Button>
              <Button
                appearance="primary"
                onClick={handleAddAsset}
                disabled={
                  addForm.assetType === 'SCHEMA'
                    ? !addForm.sharedSchema
                    : !addForm.sharedTable || !addForm.sharedSchema || !addForm.location
                }
              >
                Add
              </Button>
            </DialogActions>
          </DialogBody>
        </DialogSurface>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <Dialog open={isDeleteDialogOpen} onOpenChange={(_, data) => setIsDeleteDialogOpen(data.open)}>
        <DialogSurface>
          <DialogBody>
            <DialogTitle>Confirm Delete</DialogTitle>
            <DialogContent>
              Are you sure you want to delete {itemToDelete?.type} "{itemToDelete?.name}"?
              {itemToDelete?.type === 'schema' && (
                <div style={{ marginTop: tokens.spacingVerticalS, color: tokens.colorPaletteRedForeground1 }}>
                  Warning: This will also delete all tables associated with this schema.
                </div>
              )}
            </DialogContent>
            <DialogActions>
              <Button appearance="secondary" onClick={() => setIsDeleteDialogOpen(false)}>
                Cancel
              </Button>
              <Button appearance="primary" onClick={handleDeleteConfirm}>
                Delete
              </Button>
            </DialogActions>
          </DialogBody>
        </DialogSurface>
      </Dialog>

      {/* Edit Table Dialog */}
      <Dialog open={isEditDialogOpen} onOpenChange={(_, data) => {
        setIsEditDialogOpen(data.open);
        if (!data.open) setEditDialogError(null);
      }}>
        <DialogSurface>
          <DialogBody>
            <DialogTitle>Edit Table Asset</DialogTitle>
            <DialogContent className={styles.dialogContent}>
              <div className={styles.formField}>
                <Label htmlFor="editSharedSchema">Shared Schema</Label>
                <Input
                  id="editSharedSchema"
                  value={editForm.sharedSchema}
                  onChange={(_, data) => setEditForm({ ...editForm, sharedSchema: data.value })}
                  placeholder="Enter shared schema name"
                />
              </div>
              <div className={styles.formField}>
                <Label htmlFor="editSharedTable">Shared Table</Label>
                <Input
                  id="editSharedTable"
                  value={editForm.sharedTable}
                  disabled
                />
              </div>
              <div className={styles.formField}>
                <Label htmlFor="editMetastoreDb">Metastore DB</Label>
                <Input
                  id="editMetastoreDb"
                  value={editForm.metastoreDb}
                  onChange={(_, data) => setEditForm({ ...editForm, metastoreDb: data.value })}
                  placeholder="Enter metastore database"
                />
              </div>
              <div className={styles.formField}>
                <Label htmlFor="editMetastoreTable">Metastore Table</Label>
                <Input
                  id="editMetastoreTable"
                  value={editForm.metastoreTable}
                  onChange={(_, data) => setEditForm({ ...editForm, metastoreTable: data.value })}
                  placeholder="Enter metastore table"
                />
              </div>
              <div className={styles.formField}>
                <Label htmlFor="editLocation">Location</Label>
                <Input
                  id="editLocation"
                  value={editForm.location}
                  onChange={(_, data) => {
                    setEditForm({ ...editForm, location: data.value });
                    setEditDialogError(null);
                  }}
                  placeholder="cosn://bucket-name/path/to/table (must start with cosn:)"
                />
              </div>
              {editDialogError && (
                <MessageBar intent="error" style={{ marginTop: '8px', display: 'flex', alignItems: 'center' }}>
                  <MessageBarBody style={{ display: 'flex', alignItems: 'center' }}>{editDialogError}</MessageBarBody>
                </MessageBar>
              )}
            </DialogContent>
            <DialogActions>
              <Button appearance="secondary" onClick={() => setIsEditDialogOpen(false)}>
                Cancel
              </Button>
              <Button appearance="primary" onClick={handleEditTable}>
                Save
              </Button>
            </DialogActions>
          </DialogBody>
        </DialogSurface>
      </Dialog>
    </div>
  );
};

export default ShareAssetDetail;
