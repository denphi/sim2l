import { useEffect, useState } from 'react';
import {
  Box,
  Container,
  Typography,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TablePagination,
  Chip,
  TextField,
  Grid,
  Card,
  CardContent,
  CircularProgress,
  IconButton,
  Tooltip,
  Collapse,
} from '@mui/material';
import {
  Refresh as RefreshIcon,
  CheckCircle as CheckCircleIcon,
  Cancel as CancelIcon,
  Delete as DeleteIcon,
  KeyboardArrowDown as KeyboardArrowDownIcon,
  KeyboardArrowUp as KeyboardArrowUpIcon,
} from '@mui/icons-material';
import { cacheService } from '../api/cacheService';
import type { CacheEntry, CacheStats } from '../types/cache';

export function Cache() {
  const [entries, setEntries] = useState<CacheEntry[]>([]);
  const [stats, setStats] = useState<CacheStats | null>(null);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(25);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState<'all' | 'valid' | 'invalidated'>('all');
  const [deletingCacheKey, setDeletingCacheKey] = useState<string | null>(null);
  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set());

  useEffect(() => {
    loadData();
  }, [page, rowsPerPage, statusFilter]);

  const loadData = async () => {
    setLoading(true);
    try {
      const [entriesResponse, statsResponse] = await Promise.all([
        cacheService.listEntries({
          limit: rowsPerPage,
          offset: page * rowsPerPage,
          status: statusFilter === 'all' ? undefined : statusFilter,
          simulation_name: searchTerm || undefined,
        }),
        cacheService.getStats(),
      ]);

      setEntries(entriesResponse.entries);
      setTotal(entriesResponse.total);
      setStats(statsResponse);
    } catch (error) {
      console.error('Failed to load cache data:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleChangePage = (_event: unknown, newPage: number) => {
    setPage(newPage);
  };

  const handleChangeRowsPerPage = (event: React.ChangeEvent<HTMLInputElement>) => {
    setRowsPerPage(parseInt(event.target.value, 10));
    setPage(0);
  };

  const handleSearch = () => {
    setPage(0);
    loadData();
  };

  const handleDeleteEntry = async (entry: CacheEntry) => {
    const confirmed = window.confirm(
      `Delete cache entry "${entry.cache_key}" for ${entry.simulation_name}/${entry.simulation_version}?`
    );
    if (!confirmed) {
      return;
    }

    setDeletingCacheKey(entry.cache_key);
    try {
      await cacheService.deleteEntry(entry.cache_key);
      await loadData();
    } catch (error) {
      console.error('Failed to delete cache entry:', error);
      window.alert('Failed to delete cache entry. See browser console for details.');
    } finally {
      setDeletingCacheKey(null);
    }
  };

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    return date.toLocaleString();
  };

  const formatSize = (bytes: number | null | undefined) => {
    if (!bytes) return 'N/A';
    const mb = bytes / (1024 * 1024);
    if (mb < 1) return `${(bytes / 1024).toFixed(2)} KB`;
    return `${mb.toFixed(2)} MB`;
  };

  const formatSquidId = (entry: CacheEntry) => {
    if (!entry.squid_id) return 'N/A';
    if (entry.squid_id.includes('/')) return entry.squid_id;
    return `${entry.simulation_name}/${entry.simulation_version}/${entry.squid_id}`;
  };

  const toggleRowExpansion = (cacheKey: string) => {
    setExpandedRows((prev) => {
      const newSet = new Set(prev);
      if (newSet.has(cacheKey)) {
        newSet.delete(cacheKey);
      } else {
        newSet.add(cacheKey);
      }
      return newSet;
    });
  };

  const formatInputs = (entry: CacheEntry) => {
    if (!entry.metadata?.inputs) return 'N/A';
    const inputs = entry.metadata.inputs;
    const entries = Object.entries(inputs);
    if (entries.length === 0) return 'None';
    
    // Show first 2 inputs inline
    const preview = entries.slice(0, 2).map(([key, value]) => {
      const displayValue = typeof value === 'number' ? value.toFixed(2) : String(value);
      return `${key}: ${displayValue}`;
    }).join(', ');
    
    return entries.length > 2 ? `${preview}...` : preview;
  };

  return (
    <Container maxWidth="xl" sx={{ mt: 4, mb: 4 }}>
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
        <Typography variant="h4">Cache Service</Typography>
        <Tooltip title="Refresh">
          <IconButton onClick={loadData} color="primary">
            <RefreshIcon />
          </IconButton>
        </Tooltip>
      </Box>

      {/* Statistics Cards */}
      {stats && (
        <Grid container spacing={3} mb={3}>
          <Grid item xs={12} sm={6} md={3}>
            <Card>
              <CardContent>
                <Typography color="textSecondary" gutterBottom>
                  Total Entries
                </Typography>
                <Typography variant="h4">{stats.total_entries || 0}</Typography>
              </CardContent>
            </Card>
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <Card>
              <CardContent>
                <Typography color="textSecondary" gutterBottom>
                  Total Accesses
                </Typography>
                <Typography variant="h4">{stats.total_accesses || 0}</Typography>
              </CardContent>
            </Card>
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <Card>
              <CardContent>
                <Typography color="textSecondary" gutterBottom>
                  Cache Hits
                </Typography>
                <Typography variant="h4">{stats.total_hits || 0}</Typography>
              </CardContent>
            </Card>
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <Card>
              <CardContent>
                <Typography color="textSecondary" gutterBottom>
                  Hit Rate
                </Typography>
                <Typography variant="h4" color="primary">
                  {stats.hit_rate_percent?.toFixed(1) || 0}%
                </Typography>
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      )}

      {/* Filters */}
      <Paper sx={{ p: 2, mb: 3 }}>
        <Grid container spacing={2} alignItems="center">
          <Grid item xs={12} md={6}>
            <TextField
              fullWidth
              label="Search by Simulation Name"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              onKeyPress={(e) => e.key === 'Enter' && handleSearch()}
            />
          </Grid>
          <Grid item xs={12} md={3}>
            <TextField
              fullWidth
              select
              label="Status"
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value as 'all' | 'valid' | 'invalidated')}
              SelectProps={{ native: true }}
            >
              <option value="all">All</option>
              <option value="valid">Valid</option>
              <option value="invalidated">Invalidated</option>
            </TextField>
          </Grid>
        </Grid>
      </Paper>

      {/* Cache Entries Table */}
      <Paper>
        <TableContainer>
          {loading ? (
            <Box display="flex" justifyContent="center" p={4}>
              <CircularProgress />
            </Box>
          ) : (
            <Table>
              <TableHead>
                <TableRow>
                  <TableCell width={50}></TableCell>
                  <TableCell>Simulation</TableCell>
                  <TableCell>Version</TableCell>
                  <TableCell>SQUID ID</TableCell>
                  <TableCell>Input Parameters</TableCell>
                  <TableCell>Status</TableCell>
                  <TableCell align="right">Accesses</TableCell>
                  <TableCell align="right">Hits</TableCell>
                  <TableCell>Created</TableCell>
                  <TableCell align="center">Actions</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {entries.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={10} align="center">
                      <Typography color="textSecondary" py={4}>
                        No cache entries found
                      </Typography>
                    </TableCell>
                  </TableRow>
                ) : (
                  entries.map((entry) => {
                    const fullSquidId = formatSquidId(entry);
                    const isExpanded = expandedRows.has(entry.cache_key);
                    return (
                      <>
                        <TableRow key={entry.cache_key} hover>
                          <TableCell>
                            <IconButton
                              size="small"
                              onClick={() => toggleRowExpansion(entry.cache_key)}
                            >
                              {isExpanded ? <KeyboardArrowUpIcon /> : <KeyboardArrowDownIcon />}
                            </IconButton>
                          </TableCell>
                          <TableCell>
                            <Typography variant="body2" fontWeight="medium">
                              {entry.simulation_name}
                            </Typography>
                            <Typography variant="caption" color="textSecondary" sx={{ display: 'block', mt: 0.5 }}>
                              ID: {entry.simulation_id}
                            </Typography>
                          </TableCell>
                          <TableCell>{entry.simulation_version}</TableCell>
                          <TableCell>
                            <Tooltip title="Unique SQUID identifier for the execution params">
                              <Typography
                                variant="body2"
                                fontFamily="monospace"
                                fontWeight="bold"
                                sx={{
                                  cursor: 'pointer',
                                  '&:hover': { color: 'primary.main' }
                                }}
                                onClick={() => fullSquidId !== 'N/A' && navigator.clipboard.writeText(fullSquidId)}
                              >
                                {fullSquidId}
                              </Typography>
                            </Tooltip>
                          </TableCell>
                          <TableCell>
                            <Typography variant="body2" color="textSecondary">
                              {formatInputs(entry)}
                            </Typography>
                          </TableCell>
                          <TableCell>
                            <Chip
                              icon={entry.status === 'valid' ? <CheckCircleIcon /> : <CancelIcon />}
                              label={entry.status}
                              color={entry.status === 'valid' ? 'success' : 'error'}
                              size="small"
                            />
                          </TableCell>
                          <TableCell align="right">{entry.access_count}</TableCell>
                          <TableCell align="right">{entry.hit_count}</TableCell>
                          <TableCell>
                            <Typography variant="body2">
                              {formatDate(entry.created_at)}
                            </Typography>
                          </TableCell>
                          <TableCell align="center">
                            <Tooltip title="Delete cache entry">
                              <span>
                                <IconButton
                                  color="error"
                                  size="small"
                                  onClick={() => handleDeleteEntry(entry)}
                                  disabled={deletingCacheKey === entry.cache_key}
                                >
                                  <DeleteIcon fontSize="small" />
                                </IconButton>
                              </span>
                            </Tooltip>
                          </TableCell>
                        </TableRow>
                        <TableRow>
                          <TableCell style={{ paddingBottom: 0, paddingTop: 0 }} colSpan={10}>
                            <Collapse in={isExpanded} timeout="auto" unmountOnExit>
                              <Box sx={{ margin: 2 }}>
                                <Typography variant="h6" gutterBottom component="div">
                                  Entry Details
                                </Typography>
                                <Grid container spacing={2}>
                                  <Grid item xs={12} md={6}>
                                    <Paper sx={{ p: 2 }}>
                                      <Typography variant="subtitle2" color="primary" gutterBottom>
                                        Execution Info
                                      </Typography>
                                      <Typography variant="body2" sx={{ mt: 1 }}>
                                        <strong>Execution ID:</strong> {entry.execution_id}
                                      </Typography>
                                      <Typography variant="body2" sx={{ mt: 1 }}>
                                        <strong>Input Hash:</strong> {entry.input_hash}
                                      </Typography>
                                      <Typography variant="body2" sx={{ mt: 1 }}>
                                        <strong>Cache Key:</strong> {entry.cache_key}
                                      </Typography>
                                      {entry.run_db_path && (
                                        <Typography variant="body2" sx={{ mt: 1 }}>
                                          <strong>Run DB Path:</strong> {entry.run_db_path}
                                        </Typography>
                                      )}
                                      <Typography variant="body2" sx={{ mt: 1 }}>
                                        <strong>Last Accessed:</strong>{' '}
                                        {entry.last_accessed_at ? formatDate(entry.last_accessed_at) : 'Never'}
                                      </Typography>
                                      {entry.size_bytes && (
                                        <Typography variant="body2" sx={{ mt: 1 }}>
                                          <strong>Size:</strong> {formatSize(entry.size_bytes)}
                                        </Typography>
                                      )}
                                    </Paper>
                                  </Grid>
                                  <Grid item xs={12} md={6}>
                                    <Paper sx={{ p: 2 }}>
                                      <Typography variant="subtitle2" color="primary" gutterBottom>
                                        Input Parameters
                                      </Typography>
                                      {entry.metadata?.inputs ? (
                                        <Box
                                          component="pre"
                                          sx={{
                                            mt: 1,
                                            p: 1,
                                            bgcolor: 'grey.100',
                                            borderRadius: 1,
                                            overflow: 'auto',
                                            fontSize: '0.875rem',
                                          }}
                                        >
                                          {JSON.stringify(entry.metadata.inputs, null, 2)}
                                        </Box>
                                      ) : (
                                        <Typography variant="body2" color="textSecondary" sx={{ mt: 1 }}>
                                          No input parameters available
                                        </Typography>
                                      )}
                                    </Paper>
                                  </Grid>
                                </Grid>
                              </Box>
                            </Collapse>
                          </TableCell>
                        </TableRow>
                      </>
                    );
                  })
                )}
              </TableBody>
            </Table>
          )}
        </TableContainer>
        <TablePagination
          rowsPerPageOptions={[10, 25, 50, 100]}
          component="div"
          count={total}
          rowsPerPage={rowsPerPage}
          page={page}
          onPageChange={handleChangePage}
          onRowsPerPageChange={handleChangeRowsPerPage}
        />
      </Paper>
    </Container>
  );
}
