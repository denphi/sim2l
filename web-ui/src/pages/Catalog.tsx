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
} from '@mui/material';
import {
  Refresh as RefreshIcon,
  CheckCircle as CheckCircleIcon,
  Pause as PauseIcon,
  Error as ErrorIcon,
  Delete as DeleteIcon,
  KeyboardArrowDown as KeyboardArrowDownIcon,
  KeyboardArrowUp as KeyboardArrowUpIcon,
} from '@mui/icons-material';
import { catalogService } from '../api/catalogService';
import { SubmitRunModal } from '../components/catalog/SubmitRunModal';
import type { Simulation, OverviewStats } from '../types/catalog';

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

  const handleOpenRunModal = (name: string, version: string) => {
    setSelectedSimName(name);
    setSelectedSimVersion(version);
    setRunModalOpen(true);
  };

  const handleToggleRow = (simKey: string) => {
    setExpandedRows(prev => {
      const newSet = new Set(prev);
      if (newSet.has(simKey)) {
        newSet.delete(simKey);
      } else {
        newSet.add(simKey);
      }
      return newSet;
    });
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
                              onClick={() => handleToggleRow(simKey)}
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
                                <Typography variant="h6" gutterBottom component="div">
                                  Parameters
                                </Typography>
                                {sim.input_schema && Object.keys(sim.input_schema).length > 0 ? (
                                  <Table size="small" aria-label="parameters">
                                    <TableHead>
                                      <TableRow>
                                        <TableCell><strong>Parameter</strong></TableCell>
                                        <TableCell><strong>Type</strong></TableCell>
                                        <TableCell><strong>Description</strong></TableCell>
                                        <TableCell><strong>Default</strong></TableCell>
                                      </TableRow>
                                    </TableHead>
                                    <TableBody>
                                      {Object.entries(sim.input_schema).map(([key, schemaDef]: [string, any]) => (
                                        <TableRow key={key}>
                                          <TableCell component="th" scope="row">
                                            <Typography variant="body2" fontWeight="medium">
                                              {schemaDef.label || key}
                                            </Typography>
                                          </TableCell>
                                          <TableCell>
                                            <Chip 
                                              label={schemaDef.type || 'string'} 
                                              size="small" 
                                              variant="outlined"
                                            />
                                          </TableCell>
                                          <TableCell>
                                            <Typography variant="body2" color="textSecondary">
                                              {schemaDef.description || 'N/A'}
                                            </Typography>
                                          </TableCell>
                                          <TableCell>
                                            <Typography variant="body2">
                                              {schemaDef.default !== undefined ? String(schemaDef.default) : 'N/A'}
                                            </Typography>
                                          </TableCell>
                                        </TableRow>
                                      ))}
                                    </TableBody>
                                  </Table>
                                ) : (
                                  <Typography variant="body2" color="textSecondary">
                                    No parameters defined for this simulation.
                                  </Typography>
                                )}
                                {sim.tags && sim.tags.length > 0 && (
                                  <Box sx={{ mt: 2 }}>
                                    <Typography variant="subtitle2" gutterBottom>
                                      Tags:
                                    </Typography>
                                    <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
                                      {sim.tags.map((tag, idx) => (
                                        <Chip key={idx} label={tag} size="small" />
                                      ))}
                                    </Box>
                                  </Box>
                                )}
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
