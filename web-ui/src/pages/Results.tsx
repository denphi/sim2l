import React, { useEffect, useState } from 'react';
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
  Chip,
  TextField,
  Grid,
  CircularProgress,
  IconButton,
  Tooltip,
  Card,
  CardContent,
  Collapse,
  Button,
} from '@mui/material';
import {
  Refresh as RefreshIcon,
  CheckCircle as CheckCircleIcon,
  Error as ErrorIcon,
  HourglassEmpty as HourglassEmptyIcon,
  KeyboardArrowDown as KeyboardArrowDownIcon,
  KeyboardArrowUp as KeyboardArrowUpIcon,
  Search as SearchIcon,
  Clear as ClearIcon,
  Delete as DeleteIcon,
} from '@mui/icons-material';
import { resultsService } from '../api/resultsService';
import type { ExecutionResult } from '../types/results';

export function Results() {
  const [results, setResults] = useState<ExecutionResult[]>([]);
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(25);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [versionFilter, setVersionFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [inputFilter, setInputFilter] = useState('');
  const [outputFilter, setOutputFilter] = useState('');
  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set());
  const [deletingExecutionId, setDeletingExecutionId] = useState<string | null>(null);

  useEffect(() => {
    loadData();
  }, [page, rowsPerPage, statusFilter]);

  const parseFilterWithOperators = (filterString: string): any => {
    if (!filterString.trim()) return {};

    try {
      // Try parsing as JSON first
      return JSON.parse(filterString);
    } catch {
      // Parse as key:operator:value or key:value pairs
      // Supported formats:
      // - temperature:300 (equals)
      // - temperature:>:300 (greater than)
      // - temperature:>=:300 (greater than or equal)
      // - temperature:<:400 (less than)
      // - temperature:<=:400 (less than or equal)
      const filters: any = {};

      filterString.split(',').forEach(pair => {
        const parts = pair.split(':').map(s => s.trim());

        if (parts.length === 2) {
          // Simple key:value format (equals)
          const [key, value] = parts;
          if (key && value) {
            filters[key] = isNaN(Number(value)) ? value : Number(value);
          }
        } else if (parts.length === 3) {
          // key:operator:value format
          const [key, operator, value] = parts;
          if (key && operator && value) {
            const numValue = isNaN(Number(value)) ? value : Number(value);

            // Map operators to MongoDB-style query operators
            switch (operator) {
              case '>':
                filters[key] = { $gt: numValue };
                break;
              case '>=':
                filters[key] = { $gte: numValue };
                break;
              case '<':
                filters[key] = { $lt: numValue };
                break;
              case '<=':
                filters[key] = { $lte: numValue };
                break;
              case '=':
              case '==':
                filters[key] = numValue;
                break;
              default:
                // Unknown operator, treat as equals
                filters[key] = numValue;
            }
          }
        }
      });

      return filters;
    }
  };

  const loadData = async () => {
    setLoading(true);
    try {
      // Parse filter strings to JSON objects with operator support
      const inputFilters = parseFilterWithOperators(inputFilter);
      const outputFilters = parseFilterWithOperators(outputFilter);

      const response = await resultsService.listResults({
        limit: rowsPerPage,
        offset: page * rowsPerPage,
        simulation: searchTerm || undefined,
        version: versionFilter || undefined,
        status: statusFilter === 'all' ? undefined : statusFilter,
        input_filters: Object.keys(inputFilters).length > 0 ? inputFilters : undefined,
        output_filters: Object.keys(outputFilters).length > 0 ? outputFilters : undefined,
      });

      setResults(response.results || []);
    } catch (error) {
      console.error('Failed to load results:', error);
      setResults([]);
    } finally {
      setLoading(false);
    }
  };

  const handleSearch = () => {
    setPage(0);
    loadData();
  };

  const handleClearFilters = () => {
    setSearchTerm('');
    setVersionFilter('');
    setStatusFilter('all');
    setInputFilter('');
    setOutputFilter('');
    setPage(0);
    setTimeout(loadData, 0);
  };

  const handleClearAll = async () => {
    const confirmed = window.confirm(
      `Delete ALL results? This cannot be undone.`
    );
    if (!confirmed) return;
    try {
      const result = await resultsService.clearAllResults();
      window.alert(`Cleared ${result.deleted} result(s).`);
      await loadData();
    } catch (error) {
      console.error('Failed to clear results:', error);
      window.alert('Failed to clear results. See browser console for details.');
    }
  };

  const handleDeleteResult = async (result: ExecutionResult) => {
    const confirmed = window.confirm(
      `Delete result "${result.execution_id}" for ${result.simulation_name}/${result.simulation_version}?`
    );
    if (!confirmed) {
      return;
    }

    setDeletingExecutionId(result.execution_id);
    try {
      await resultsService.deleteResult(result.execution_id);
      await loadData();
    } catch (error) {
      console.error('Failed to delete result:', error);
      window.alert('Failed to delete result. See browser console for details.');
    } finally {
      setDeletingExecutionId(null);
    }
  };

  const toggleRowExpanded = (executionId: string) => {
    const newExpanded = new Set(expandedRows);
    if (newExpanded.has(executionId)) {
      newExpanded.delete(executionId);
    } else {
      newExpanded.add(executionId);
    }
    setExpandedRows(newExpanded);
  };

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    return date.toLocaleString();
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'success':
        return <CheckCircleIcon />;
      case 'failed':
        return <ErrorIcon />;
      default:
        return <HourglassEmptyIcon />;
    }
  };

  const getStatusColor = (status: string): 'success' | 'error' | 'warning' | 'default' => {
    switch (status) {
      case 'success':
        return 'success';
      case 'failed':
        return 'error';
      case 'running':
        return 'warning';
      default:
        return 'default';
    }
  };

  const formatSquidId = (result: ExecutionResult) => {
    if (!result.squid_id) return 'N/A';
    if (result.squid_id.includes('/')) return result.squid_id;
    return `${result.simulation_name}/${result.simulation_version}/${result.squid_id}`;
  };

  return (
    <Container maxWidth="xl" sx={{ mt: 4, mb: 4 }}>
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
        <Typography variant="h4">Results Service</Typography>
        <Box display="flex" gap={1} alignItems="center">
          <Button
            variant="outlined"
            color="error"
            size="small"
            onClick={handleClearAll}
          >
            Clear All
          </Button>
          <Tooltip title="Refresh">
            <IconButton onClick={loadData} color="primary">
              <RefreshIcon />
            </IconButton>
          </Tooltip>
        </Box>
      </Box>

      {/* Summary Card */}
      <Grid container spacing={3} mb={3}>
        <Grid item xs={12}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Execution Results
              </Typography>
              <Typography variant="body2" color="textSecondary" paragraph>
                Browse and search simulation results by <strong>what was computed</strong> - input and output parameters.
                Each result has a unique <strong>SQUID ID</strong> that identifies its specific parameter set.
              </Typography>
              <Typography variant="body2" color="textSecondary">
                Filter by input/output parameters, expand rows to view full details, and copy SQUID IDs for reproducibility.
                For execution timing and cache performance, see the Cache Service.
              </Typography>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Filters */}
      <Paper sx={{ p: 2, mb: 3 }}>
        <Grid container spacing={2} alignItems="center">
          <Grid item xs={12} md={3}>
            <TextField
              fullWidth
              label="Simulation Name"
              placeholder="thermal_analysis"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              onKeyPress={(e) => e.key === 'Enter' && handleSearch()}
            />
          </Grid>
          <Grid item xs={12} md={2}>
            <TextField
              fullWidth
              label="Version"
              placeholder="1.0.0"
              value={versionFilter}
              onChange={(e) => setVersionFilter(e.target.value)}
              onKeyPress={(e) => e.key === 'Enter' && handleSearch()}
            />
          </Grid>
          <Grid item xs={12} md={2}>
            <TextField
              fullWidth
              select
              label="Status"
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              SelectProps={{ native: true }}
            >
              <option value="all">All</option>
              <option value="success">Success</option>
              <option value="failed">Failed</option>
              <option value="running">Running</option>
            </TextField>
          </Grid>
          <Grid item xs={12} md={5}>
            <TextField
              fullWidth
              label="Input Filters"
              placeholder="temperature:>=:300,power:<:15"
              value={inputFilter}
              onChange={(e) => setInputFilter(e.target.value)}
              onKeyPress={(e) => e.key === 'Enter' && handleSearch()}
              helperText="Supports: key:value, key:>:value, key:>=:value, key:<:value, key:<=:value"
            />
          </Grid>
          <Grid item xs={12} md={5}>
            <TextField
              fullWidth
              label="Output Filters"
              placeholder="max_temperature:>=:450,converged:true"
              value={outputFilter}
              onChange={(e) => setOutputFilter(e.target.value)}
              onKeyPress={(e) => e.key === 'Enter' && handleSearch()}
              helperText="Supports: key:value, key:>:value, key:>=:value, key:<:value, key:<=:value"
            />
          </Grid>
          <Grid item xs={12} md={7}>
            <Box display="flex" gap={1} alignItems="center">
              <Button
                variant="contained"
                startIcon={<SearchIcon />}
                onClick={handleSearch}
              >
                Search
              </Button>
              <Button
                variant="outlined"
                startIcon={<ClearIcon />}
                onClick={handleClearFilters}
              >
                Clear Filters
              </Button>
              <Typography variant="caption" color="textSecondary" sx={{ ml: 2 }}>
                Use operators: = (equals), &gt; (greater), &gt;= (greater or equal), &lt; (less), &lt;= (less or equal)
              </Typography>
            </Box>
          </Grid>
        </Grid>
      </Paper>

      {/* Results Table */}
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
                  <TableCell width="50px" />
                  <TableCell>SQUID ID</TableCell>
                  <TableCell>Simulation</TableCell>
                  <TableCell>Status</TableCell>
                  <TableCell align="center">Actions</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {results.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={5} align="center">
                      <Typography color="textSecondary" py={4}>
                        No execution results found
                      </Typography>
                    </TableCell>
                  </TableRow>
                ) : (
                  results.map((result) => {
                    const fullSquidId = formatSquidId(result);
                    return (
                      <React.Fragment key={result.execution_id}>
                        <TableRow hover>
                          <TableCell>
                            <IconButton
                              size="small"
                              onClick={() => toggleRowExpanded(result.execution_id)}
                            >
                              {expandedRows.has(result.execution_id) ? (
                                <KeyboardArrowUpIcon />
                              ) : (
                                <KeyboardArrowDownIcon />
                              )}
                            </IconButton>
                          </TableCell>
                          <TableCell>
                            <Tooltip title="Full SQUID ID - unique identifier for this parameter set">
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
                            <Typography variant="body2" fontWeight="medium">
                              {result.simulation_name}
                            </Typography>
                            <Typography variant="caption" color="textSecondary">
                              v{result.simulation_version}
                            </Typography>
                          </TableCell>
                          <TableCell>
                            <Chip
                              icon={getStatusIcon(result.status)}
                              label={result.status}
                              color={getStatusColor(result.status)}
                              size="small"
                            />
                          </TableCell>
                          <TableCell align="center">
                            <Tooltip title="Delete result">
                              <span>
                                <IconButton
                                  color="error"
                                  size="small"
                                  onClick={() => handleDeleteResult(result)}
                                  disabled={deletingExecutionId === result.execution_id}
                                >
                                  <DeleteIcon fontSize="small" />
                                </IconButton>
                              </span>
                            </Tooltip>
                          </TableCell>
                        </TableRow>
                        <TableRow>
                          <TableCell style={{ paddingBottom: 0, paddingTop: 0 }} colSpan={5}>
                            <Collapse in={expandedRows.has(result.execution_id)} timeout="auto" unmountOnExit>
                              <Box sx={{ margin: 2 }}>
                                {/* SQUID ID Header */}
                                <Paper sx={{ p: 2, mb: 2, bgcolor: 'primary.50', border: '2px solid', borderColor: 'primary.main' }}>
                                  <Typography variant="subtitle2" color="primary.dark" gutterBottom>
                                    SQUID ID (Unique Parameter Identifier)
                                  </Typography>
                                  <Box display="flex" alignItems="center" gap={2}>
                                    <Typography
                                      variant="h6"
                                      fontFamily="monospace"
                                      fontWeight="bold"
                                      sx={{ wordBreak: 'break-all' }}
                                    >
                                      {result.squid_id || 'N/A'}
                                    </Typography>
                                    <Chip
                                      label="Copy"
                                      size="small"
                                      onClick={() => {
                                        navigator.clipboard.writeText(result.squid_id || '');
                                      }}
                                      sx={{ cursor: 'pointer' }}
                                    />
                                  </Box>
                                  <Typography variant="caption" color="textSecondary" sx={{ mt: 1, display: 'block' }}>
                                    This ID uniquely identifies this specific combination of input parameters.
                                    Use it to find all executions with identical inputs.
                                  </Typography>
                                </Paper>

                                <Grid container spacing={2}>
                                  <Grid item xs={12} md={6}>
                                    <Typography variant="h6" gutterBottom component="div">
                                      Input Parameters
                                    </Typography>
                                    <Paper variant="outlined" sx={{ p: 2, bgcolor: 'grey.50' }}>
                                      {result.input_params && Object.keys(result.input_params).length > 0 ? (
                                        <Box component="pre" sx={{ margin: 0, fontSize: '0.875rem' }}>
                                          {JSON.stringify(result.input_params, null, 2)}
                                        </Box>
                                      ) : (
                                        <Typography color="textSecondary">No input parameters</Typography>
                                      )}
                                    </Paper>
                                  </Grid>
                                  <Grid item xs={12} md={6}>
                                    <Typography variant="h6" gutterBottom component="div">
                                      Output Parameters
                                    </Typography>
                                    <Paper variant="outlined" sx={{ p: 2, bgcolor: 'grey.50' }}>
                                      {result.output_params && Object.keys(result.output_params).length > 0 ? (
                                        <Box component="pre" sx={{ margin: 0, fontSize: '0.875rem', maxHeight: 300, overflow: 'auto' }}>
                                          {JSON.stringify(result.output_params, null, 2)}
                                        </Box>
                                      ) : (
                                        <Typography color="textSecondary">No output parameters</Typography>
                                      )}
                                    </Paper>
                                  </Grid>

                                  {/* Execution Metadata */}
                                  <Grid item xs={12}>
                                    <Typography variant="h6" gutterBottom component="div">
                                      Execution Metadata
                                    </Typography>
                                    <Paper variant="outlined" sx={{ p: 2, bgcolor: 'grey.50' }}>
                                      <Grid container spacing={2}>
                                        <Grid item xs={12} sm={6} md={3}>
                                          <Typography variant="caption" color="textSecondary">Execution ID</Typography>
                                          <Typography variant="body2" fontFamily="monospace">
                                            {result.execution_id}
                                          </Typography>
                                        </Grid>
                                        <Grid item xs={12} sm={6} md={3}>
                                          <Typography variant="caption" color="textSecondary">Started</Typography>
                                          <Typography variant="body2">
                                            {result.started_at ? formatDate(result.started_at) : 'N/A'}
                                          </Typography>
                                        </Grid>
                                        <Grid item xs={12} sm={6} md={3}>
                                          <Typography variant="caption" color="textSecondary">Duration</Typography>
                                          <Typography variant="body2">
                                            {result.execution_time_ms ? `${(result.execution_time_ms / 1000).toFixed(3)}s` : 'N/A'}
                                          </Typography>
                                        </Grid>
                                        <Grid item xs={12} sm={6} md={3}>
                                          <Typography variant="caption" color="textSecondary">Cache Hit</Typography>
                                          <Typography variant="body2">
                                            {result.cache_hit ? '✓ Yes' : '✗ No'}
                                          </Typography>
                                        </Grid>
                                      </Grid>
                                    </Paper>
                                  </Grid>
                                </Grid>
                              </Box>
                            </Collapse>
                          </TableCell>
                        </TableRow>
                      </React.Fragment>
                    );
                  })
                )}
              </TableBody>
            </Table>
          )}
        </TableContainer>
        <Box sx={{ p: 2, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Typography variant="body2" color="textSecondary">
            Showing {results.length} result{results.length !== 1 ? 's' : ''}
            {results.length >= rowsPerPage ? ` (increase limit to see more)` : ''}
          </Typography>
          <TextField
            select
            size="small"
            label="Results per page"
            value={rowsPerPage}
            onChange={(e) => {
              setRowsPerPage(parseInt(e.target.value, 10));
              setPage(0);
            }}
            SelectProps={{ native: true }}
            sx={{ minWidth: 150 }}
          >
            <option value={10}>10</option>
            <option value={25}>25</option>
            <option value={50}>50</option>
            <option value={100}>100</option>
            <option value={250}>250</option>
          </TextField>
        </Box>
      </Paper>
    </Container>
  );
}
