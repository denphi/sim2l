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
  Chip,
  TextField,
  Grid,
  CircularProgress,
  IconButton,
  Tooltip,
  Button,
  Card,
  CardContent,
  Collapse,
  Divider,
  LinearProgress,
} from '@mui/material';
import {
  Refresh as RefreshIcon,
  CheckCircle as CheckCircleIcon,
  Pause as PauseIcon,
  Error as ErrorIcon,
  Delete as DeleteIcon,
  KeyboardArrowDown as KeyboardArrowDownIcon,
  KeyboardArrowUp as KeyboardArrowUpIcon,
  Input as InputIcon,
  Output as OutputIcon,
  BarChart as BarChartIcon,
  Code as CodeIcon,
  ContentCopy as ContentCopyIcon,
} from '@mui/icons-material';
import { catalogService } from '../api/catalogService';
import { SubmitRunModal } from '../components/catalog/SubmitRunModal';
import type { Simulation, OverviewStats, ExecutionStats } from '../types/catalog';

export function Catalog() {
  const [simulations, setSimulations] = useState<Simulation[]>([]);
  const [stats, setStats] = useState<OverviewStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');

  const [runModalOpen, setRunModalOpen] = useState(false);
  const [selectedSimName, setSelectedSimName] = useState('');
  const [selectedSimVersion, setSelectedSimVersion] = useState<string | undefined>(undefined);
  const [deletingSimulationId, setDeletingSimulationId] = useState<number | null>(null);
  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set());
  // Cache full simulation details (with input/output schema) fetched on expand
  const [simDetails, setSimDetails] = useState<Record<string, Simulation>>({});
  const [simExecStats, setSimExecStats] = useState<Record<string, ExecutionStats>>({});
  const [loadingDetails, setLoadingDetails] = useState<Set<string>>(new Set());

  const handleOpenRunModal = (name: string, version: string) => {
    setSelectedSimName(name);
    setSelectedSimVersion(version);
    setRunModalOpen(true);
  };

  const handleToggleRow = async (simKey: string, sim: Simulation) => {
    setExpandedRows(prev => {
      const newSet = new Set(prev);
      if (newSet.has(simKey)) {
        newSet.delete(simKey);
      } else {
        newSet.add(simKey);
      }
      return newSet;
    });

    // Fetch full details + stats when expanding for the first time
    if (!simDetails[simKey]) {
      setLoadingDetails(prev => new Set(prev).add(simKey));
      try {
        const [detail, execStats] = await Promise.allSettled([
          catalogService.getSimulation(sim.name, sim.version),
          catalogService.getExecutionStats(sim.id),
        ]);
        if (detail.status === 'fulfilled') {
          setSimDetails(prev => ({ ...prev, [simKey]: detail.value }));
        }
        if (execStats.status === 'fulfilled') {
          setSimExecStats(prev => ({ ...prev, [simKey]: execStats.value }));
        }
      } catch (_) {
        // non-fatal
      } finally {
        setLoadingDetails(prev => { const s = new Set(prev); s.delete(simKey); return s; });
      }
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    setLoading(true);
    try {
      const [simsResponse, statsResponse] = await Promise.all([
        catalogService.searchSimulations(searchTerm),
        catalogService.getOverviewStats(),
      ]);

      // Handle both array and object responses
      const sims = Array.isArray(simsResponse)
        ? simsResponse
        : (simsResponse.simulations || []);

      setSimulations(sims);
      setStats(statsResponse);
    } catch (error) {
      console.error('Failed to load catalog data:', error);
      setSimulations([]);
    } finally {
      setLoading(false);
    }
  };

  const handleSearch = () => {
    loadData();
  };

  const handleClearAll = async () => {
    const confirmed = window.confirm(
      `Delete ALL simulations from the catalog? This cannot be undone.`
    );
    if (!confirmed) return;
    try {
      const result = await catalogService.clearAllSimulations();
      window.alert(`Cleared ${result.deleted} simulation(s).`);
      await loadData();
    } catch (error) {
      console.error('Failed to clear catalog:', error);
      window.alert('Failed to clear catalog. See browser console for details.');
    }
  };

  const handleDeleteSimulation = async (sim: Simulation) => {
    const confirmed = window.confirm(
      `Delete simulation "${sim.name}" version "${sim.version}" from catalog?`
    );
    if (!confirmed) {
      return;
    }

    setDeletingSimulationId(sim.id);
    try {
      await catalogService.deleteSimulation(sim.id);
      await loadData();
    } catch (error) {
      console.error('Failed to delete simulation:', error);
      window.alert('Failed to delete simulation. See browser console for details.');
    } finally {
      setDeletingSimulationId(null);
    }
  };

  const formatDate = (dateStr?: string) => {
    if (!dateStr) return 'N/A';
    const date = new Date(dateStr);
    return date.toLocaleString();
  };

  const getStatusIcon = (status?: string) => {
    switch (status) {
      case 'active':
        return <CheckCircleIcon />;
      case 'deprecated':
        return <PauseIcon />;
      case 'disabled':
        return <ErrorIcon />;
      default:
        return <CheckCircleIcon />;
    }
  };

  const getStatusColor = (status?: string): 'success' | 'warning' | 'error' | 'default' => {
    switch (status) {
      case 'active':
        return 'success';
      case 'deprecated':
        return 'warning';
      case 'disabled':
        return 'error';
      default:
        return 'default';
    }
  };

  return (
    <Container maxWidth="xl" sx={{ mt: 4, mb: 4 }}>
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
        <Typography variant="h4">Catalog Service</Typography>
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

      {/* Statistics Cards */}
      {stats && (
        <Grid container spacing={3} mb={3}>
          <Grid item xs={12} sm={6} md={3}>
            <Card>
              <CardContent>
                <Typography color="textSecondary" gutterBottom>
                  Total Simulations
                </Typography>
                <Typography variant="h4">{stats.total_simulations}</Typography>
              </CardContent>
            </Card>
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <Card>
              <CardContent>
                <Typography color="textSecondary" gutterBottom>
                  Active Simulations
                </Typography>
                <Typography variant="h4" color="success.main">
                  {stats.active_simulations}
                </Typography>
              </CardContent>
            </Card>
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <Card>
              <CardContent>
                <Typography color="textSecondary" gutterBottom>
                  Total Executions
                </Typography>
                <Typography variant="h4">{stats.total_executions}</Typography>
              </CardContent>
            </Card>
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <Card>
              <CardContent>
                <Typography color="textSecondary" gutterBottom>
                  Success Rate
                </Typography>
                <Typography variant="h4" color="primary">
                  {stats.total_executions > 0
                    ? ((stats.successful_executions / stats.total_executions) * 100).toFixed(1)
                    : 0}
                  %
                </Typography>
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      )}

      {/* Search */}
      <Paper sx={{ p: 2, mb: 3 }}>
        <Grid container spacing={2} alignItems="center">
          <Grid item xs={12} md={8}>
            <TextField
              fullWidth
              label="Search Simulations"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              onKeyPress={(e) => e.key === 'Enter' && handleSearch()}
              placeholder="Search by name, description, or tags..."
            />
          </Grid>
        </Grid>
      </Paper>

      {/* Simulations Table */}
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
                  <TableCell>Name</TableCell>
                  <TableCell>Version</TableCell>
                  <TableCell>Status</TableCell>
                  <TableCell>Description</TableCell>
                  <TableCell>Author</TableCell>
                  <TableCell>Created</TableCell>
                  <TableCell>Updated</TableCell>
                  <TableCell align="center">Actions</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {simulations.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={9} align="center">
                      <Typography color="textSecondary" py={4}>
                        {searchTerm
                          ? 'No simulations found matching your search'
                          : 'No simulations registered yet'}
                      </Typography>
                    </TableCell>
                  </TableRow>
                ) : (
                  simulations.map((sim) => {
                    const simKey = `${sim.name}-${sim.version}`;
                    const isExpanded = expandedRows.has(simKey);
                    return (
                      <>
                        <TableRow key={simKey} hover>
                          <TableCell>
                            <IconButton
                              size="small"
                              onClick={() => handleToggleRow(simKey, sim)}
                            >
                              {isExpanded ? <KeyboardArrowUpIcon /> : <KeyboardArrowDownIcon />}
                            </IconButton>
                          </TableCell>
                          <TableCell>
                            <Typography variant="body2" fontWeight="medium">
                              {sim.name}
                            </Typography>
                            {sim.id && (
                              <Typography variant="caption" color="textSecondary">
                                ID: {sim.id}
                              </Typography>
                            )}
                          </TableCell>
                          <TableCell>
                            <Chip label={sim.version} size="small" variant="outlined" />
                          </TableCell>
                          <TableCell>
                            <Chip
                              icon={getStatusIcon(sim.status)}
                              label={sim.status || 'active'}
                              color={getStatusColor(sim.status)}
                              size="small"
                            />
                          </TableCell>
                          <TableCell>
                            <Typography variant="body2" sx={{ maxWidth: 300 }}>
                              {sim.description || 'No description'}
                            </Typography>
                          </TableCell>
                          <TableCell>
                            <Typography variant="body2">{sim.author || 'Unknown'}</Typography>
                          </TableCell>
                          <TableCell>
                            <Typography variant="body2">{formatDate(sim.created_at)}</Typography>
                          </TableCell>
                          <TableCell>
                            <Typography variant="body2">{formatDate(sim.updated_at)}</Typography>
                          </TableCell>
                          <TableCell align="center">
                            <Box display="flex" gap={1} justifyContent="center" alignItems="center">
                              <Button
                                variant="outlined"
                                size="small"
                                onClick={() => handleOpenRunModal(sim.name, sim.version)}
                                disabled={sim.status !== 'active' || deletingSimulationId === sim.id}
                              >
                                Run
                              </Button>
                              <Tooltip title="Delete simulation">
                                <span>
                                  <IconButton
                                    color="error"
                                    size="small"
                                    onClick={() => handleDeleteSimulation(sim)}
                                    disabled={deletingSimulationId === sim.id}
                                  >
                                    <DeleteIcon fontSize="small" />
                                  </IconButton>
                                </span>
                              </Tooltip>
                            </Box>
                          </TableCell>
                        </TableRow>
                        <TableRow key={`${simKey}-expanded`}>
                          <TableCell style={{ paddingBottom: 0, paddingTop: 0 }} colSpan={9}>
                            <Collapse in={isExpanded} timeout="auto" unmountOnExit>
                              <Box sx={{ margin: 2 }}>
                                {loadingDetails.has(simKey) ? (
                                  <LinearProgress sx={{ my: 2 }} />
                                ) : (() => {
                                  const detail = simDetails[simKey] || sim;
                                  const execStats = simExecStats[simKey];
                                  const inputSchema = detail.input_schema || sim.input_schema;
                                  const outputSchema = (detail as any).output_schema;

                                  return (
                                    <Grid container spacing={3}>
                                      {/* Input Parameters */}
                                      <Grid item xs={12} md={6}>
                                        <Box display="flex" alignItems="center" gap={1} mb={1}>
                                          <InputIcon fontSize="small" color="primary" />
                                          <Typography variant="subtitle1" fontWeight="bold">
                                            Input Parameters
                                          </Typography>
                                        </Box>
                                        {inputSchema && Object.keys(inputSchema).length > 0 ? (
                                          <Table size="small">
                                            <TableHead>
                                              <TableRow>
                                                <TableCell sx={{ fontWeight: 'bold' }}>Name</TableCell>
                                                <TableCell sx={{ fontWeight: 'bold' }}>Type</TableCell>
                                                <TableCell sx={{ fontWeight: 'bold' }}>Default</TableCell>
                                                <TableCell sx={{ fontWeight: 'bold' }}>Description</TableCell>
                                              </TableRow>
                                            </TableHead>
                                            <TableBody>
                                              {Object.entries(inputSchema).map(([key, def]: [string, any]) => (
                                                <TableRow key={key}>
                                                  <TableCell>
                                                    <Typography variant="body2" fontFamily="monospace" fontWeight="medium">
                                                      {key}
                                                    </Typography>
                                                  </TableCell>
                                                  <TableCell>
                                                    <Chip label={def?.type || 'Number'} size="small" color="primary" variant="outlined" />
                                                  </TableCell>
                                                  <TableCell>
                                                    <Typography variant="body2">
                                                      {def?.default !== undefined ? String(def.default) : '—'}
                                                    </Typography>
                                                  </TableCell>
                                                  <TableCell>
                                                    <Typography variant="body2" color="textSecondary">
                                                      {def?.description || key}
                                                    </Typography>
                                                  </TableCell>
                                                </TableRow>
                                              ))}
                                            </TableBody>
                                          </Table>
                                        ) : (
                                          <Typography variant="body2" color="textSecondary" sx={{ ml: 1 }}>
                                            No input parameters defined.
                                          </Typography>
                                        )}
                                      </Grid>

                                      {/* Output Schema */}
                                      <Grid item xs={12} md={6}>
                                        <Box display="flex" alignItems="center" gap={1} mb={1}>
                                          <OutputIcon fontSize="small" color="secondary" />
                                          <Typography variant="subtitle1" fontWeight="bold">
                                            Outputs
                                          </Typography>
                                        </Box>
                                        {outputSchema && Object.keys(outputSchema).length > 0 ? (
                                          <Table size="small">
                                            <TableHead>
                                              <TableRow>
                                                <TableCell sx={{ fontWeight: 'bold' }}>Name</TableCell>
                                                <TableCell sx={{ fontWeight: 'bold' }}>Type</TableCell>
                                                <TableCell sx={{ fontWeight: 'bold' }}>Description</TableCell>
                                              </TableRow>
                                            </TableHead>
                                            <TableBody>
                                              {Object.entries(outputSchema).map(([key, def]: [string, any]) => (
                                                <TableRow key={key}>
                                                  <TableCell>
                                                    <Typography variant="body2" fontFamily="monospace" fontWeight="medium">
                                                      {key}
                                                    </Typography>
                                                  </TableCell>
                                                  <TableCell>
                                                    <Chip label={def?.type || 'Number'} size="small" color="secondary" variant="outlined" />
                                                  </TableCell>
                                                  <TableCell>
                                                    <Typography variant="body2" color="textSecondary">
                                                      {def?.description || key}
                                                    </Typography>
                                                  </TableCell>
                                                </TableRow>
                                              ))}
                                            </TableBody>
                                          </Table>
                                        ) : (
                                          <Typography variant="body2" color="textSecondary" sx={{ ml: 1 }}>
                                            No output schema defined.
                                          </Typography>
                                        )}
                                      </Grid>

                                      {/* Execution Stats */}
                                      {execStats && (
                                        <Grid item xs={12}>
                                          <Divider sx={{ mb: 2 }} />
                                          <Box display="flex" alignItems="center" gap={1} mb={1}>
                                            <BarChartIcon fontSize="small" color="action" />
                                            <Typography variant="subtitle1" fontWeight="bold">
                                              Execution History
                                            </Typography>
                                          </Box>
                                          <Grid container spacing={2}>
                                            {[
                                              { label: 'Total Runs', value: execStats.total_executions, color: 'text.primary' },
                                              { label: 'Successful', value: execStats.successful, color: 'success.main' },
                                              { label: 'Failed', value: execStats.failed, color: 'error.main' },
                                              { label: 'Cached', value: execStats.cached, color: 'info.main' },
                                              { label: 'Avg Duration', value: execStats.avg_duration != null ? `${execStats.avg_duration.toFixed(2)}s` : '—', color: 'text.secondary' },
                                              { label: 'Min / Max', value: execStats.min_duration != null ? `${execStats.min_duration.toFixed(2)}s / ${execStats.max_duration.toFixed(2)}s` : '—', color: 'text.secondary' },
                                            ].map(({ label, value, color }) => (
                                              <Grid item xs={6} sm={4} md={2} key={label}>
                                                <Paper variant="outlined" sx={{ p: 1.5, textAlign: 'center' }}>
                                                  <Typography variant="caption" color="textSecondary" display="block">
                                                    {label}
                                                  </Typography>
                                                  <Typography variant="h6" color={color} fontWeight="bold">
                                                    {value}
                                                  </Typography>
                                                </Paper>
                                              </Grid>
                                            ))}
                                          </Grid>
                                        </Grid>
                                      )}

                                      {/* Tags */}
                                      {detail.tags && detail.tags.length > 0 && (
                                        <Grid item xs={12}>
                                          <Box display="flex" gap={1} flexWrap="wrap" alignItems="center">
                                            <Typography variant="caption" color="textSecondary">Tags:</Typography>
                                            {detail.tags.map((tag, idx) => (
                                              <Chip key={idx} label={tag} size="small" variant="outlined" />
                                            ))}
                                          </Box>
                                        </Grid>
                                      )}

                                      {/* Workflow Source Code */}
                                      {(() => {
                                        const src = (detail as any).metadata?.workflow_source as string | undefined;
                                        if (!src) return null;
                                        return (
                                          <Grid item xs={12}>
                                            <Divider sx={{ mb: 2 }} />
                                            <Box display="flex" alignItems="center" justifyContent="space-between" mb={1}>
                                              <Box display="flex" alignItems="center" gap={1}>
                                                <CodeIcon fontSize="small" color="action" />
                                                <Typography variant="subtitle1" fontWeight="bold">
                                                  Workflow Code
                                                </Typography>
                                                <Chip label="workflow.py" size="small" variant="outlined" />
                                              </Box>
                                              <Tooltip title="Copy code">
                                                <IconButton
                                                  size="small"
                                                  onClick={() => navigator.clipboard.writeText(src)}
                                                >
                                                  <ContentCopyIcon fontSize="small" />
                                                </IconButton>
                                              </Tooltip>
                                            </Box>
                                            <Paper
                                              variant="outlined"
                                              sx={{
                                                p: 2,
                                                backgroundColor: '#1e1e1e',
                                                overflow: 'auto',
                                                maxHeight: 400,
                                              }}
                                            >
                                              <Typography
                                                component="pre"
                                                sx={{
                                                  fontFamily: 'monospace',
                                                  fontSize: '0.8rem',
                                                  color: '#d4d4d4',
                                                  margin: 0,
                                                  whiteSpace: 'pre',
                                                }}
                                              >
                                                {src}
                                              </Typography>
                                            </Paper>
                                          </Grid>
                                        );
                                      })()}
                                    </Grid>
                                  );
                                })()}
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
      </Paper>

      {/* Info Card */}
      {simulations.length === 0 && !loading && !searchTerm && (
        <Card sx={{ mt: 3 }}>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              Getting Started
            </Typography>
            <Typography variant="body2" color="textSecondary">
              To add simulations to the catalog, run your simulations using the sim2l framework. They will
              automatically register themselves and appear here.
            </Typography>
          </CardContent>
        </Card>
      )}

      <SubmitRunModal
        open={runModalOpen}
        onClose={() => setRunModalOpen(false)}
        simulationName={selectedSimName}
        simulationVersion={selectedSimVersion}
      />
    </Container>
  );
}
