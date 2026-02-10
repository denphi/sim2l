import { useEffect, useState } from 'react';
import {
  Box,
  Container,
  Grid,
  Card,
  CardContent,
  Typography,
  Chip,
  Paper,
} from '@mui/material';
import {
  CheckCircle as CheckCircleIcon,
  Error as ErrorIcon,
  Storage as StorageIcon,
  PlayArrow as PlayArrowIcon,
  Folder as FolderIcon,
} from '@mui/icons-material';
import { apiClient } from '../api/client';
import { cacheService } from '../api/cacheService';
import { catalogService } from '../api/catalogService';

export function Dashboard() {
  const [serviceHealth, setServiceHealth] = useState<Record<string, any>>({});
  const [cacheStats, setCacheStats] = useState<any>(null);
  const [overviewStats, setOverviewStats] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 10000); // Refresh every 10s
    return () => clearInterval(interval);
  }, []);

  const loadData = async () => {
    try {
      const [health, cache, overview] = await Promise.all([
        apiClient.checkAllServices(),
        cacheService.getStats().catch(() => null),
        catalogService.getOverviewStats().catch(() => null),
      ]);

      setServiceHealth(health);
      setCacheStats(cache);
      setOverviewStats(overview);
      setLoading(false);
    } catch (error) {
      console.error('Failed to load dashboard data:', error);
      setLoading(false);
    }
  };

  const ServiceStatusCard = ({ name, status }: { name: string; status: any }) => {
    const isHealthy = status?.status === 'healthy';

    return (
      <Card>
        <CardContent>
          <Box display="flex" alignItems="center" justifyContent="space-between">
            <Box>
              <Typography variant="h6">{name} Service</Typography>
              <Typography variant="body2" color="text.secondary">
                {status?.backend || 'Unknown'}
              </Typography>
            </Box>
            <Chip
              icon={isHealthy ? <CheckCircleIcon /> : <ErrorIcon />}
              label={isHealthy ? 'Healthy' : 'Unhealthy'}
              color={isHealthy ? 'success' : 'error'}
            />
          </Box>
        </CardContent>
      </Card>
    );
  };

  const StatCard = ({ title, value, icon }: { title: string; value: number; icon: any }) => (
    <Card>
      <CardContent>
        <Box display="flex" alignItems="center" gap={2}>
          <Box sx={{ color: 'primary.main' }}>{icon}</Box>
          <Box>
            <Typography variant="h4">{value.toLocaleString()}</Typography>
            <Typography variant="body2" color="text.secondary">
              {title}
            </Typography>
          </Box>
        </Box>
      </CardContent>
    </Card>
  );

  if (loading) {
    return (
      <Container maxWidth="lg" sx={{ mt: 4 }}>
        <Typography>Loading...</Typography>
      </Container>
    );
  }

  return (
    <Container maxWidth="lg" sx={{ mt: 4, mb: 4 }}>
      <Typography variant="h3" gutterBottom>
        sim2l Dashboard
      </Typography>

      <Grid container spacing={3}>
        {/* Service Health Status */}
        <Grid item xs={12}>
          <Paper sx={{ p: 2 }}>
            <Typography variant="h5" gutterBottom>
              Service Health
            </Typography>
            <Grid container spacing={2}>
              <Grid item xs={12} md={4}>
                <ServiceStatusCard name="Cache" status={serviceHealth.cache} />
              </Grid>
              <Grid item xs={12} md={4}>
                <ServiceStatusCard name="Results" status={serviceHealth.results} />
              </Grid>
              <Grid item xs={12} md={4}>
                <ServiceStatusCard name="Catalog" status={serviceHealth.catalog} />
              </Grid>
            </Grid>
          </Paper>
        </Grid>

        {/* Statistics */}
        <Grid item xs={12}>
          <Paper sx={{ p: 2 }}>
            <Typography variant="h5" gutterBottom>
              Overview Statistics
            </Typography>
            <Grid container spacing={2}>
              <Grid item xs={12} sm={6} md={3}>
                <StatCard
                  title="Cache Entries"
                  value={cacheStats?.total_entries || 0}
                  icon={<StorageIcon fontSize="large" />}
                />
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <StatCard
                  title="Cache Hits"
                  value={cacheStats?.total_hits || 0}
                  icon={<CheckCircleIcon fontSize="large" />}
                />
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <StatCard
                  title="Total Simulations"
                  value={overviewStats?.total_simulations || 0}
                  icon={<FolderIcon fontSize="large" />}
                />
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <StatCard
                  title="Total Executions"
                  value={overviewStats?.total_executions || 0}
                  icon={<PlayArrowIcon fontSize="large" />}
                />
              </Grid>
            </Grid>
          </Paper>
        </Grid>

        {/* Cache Hit Rate */}
        {cacheStats && (
          <Grid item xs={12} md={6}>
            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  Cache Performance
                </Typography>
                <Typography variant="h3" color="primary">
                  {cacheStats.hit_rate_percent?.toFixed(1) || '0.0'}%
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  Hit Rate
                </Typography>
                <Box mt={2}>
                  <Typography variant="body2">
                    Total Requests: {cacheStats.total_requests || 0}
                  </Typography>
                  <Typography variant="body2">
                    Total Accesses: {cacheStats.total_accesses || 0}
                  </Typography>
                </Box>
              </CardContent>
            </Card>
          </Grid>
        )}

        {/* Execution Stats */}
        {overviewStats && (
          <Grid item xs={12} md={6}>
            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  Execution Performance
                </Typography>
                <Box mt={2}>
                  <Typography variant="body1">
                    Successful: {overviewStats.successful_executions || 0} /{' '}
                    {overviewStats.total_executions || 0}
                  </Typography>
                  <Typography variant="body1">
                    Cached: {overviewStats.cached_executions || 0}
                  </Typography>
                  <Typography variant="body1">
                    Active Simulations: {overviewStats.active_simulations || 0}
                  </Typography>
                </Box>
              </CardContent>
            </Card>
          </Grid>
        )}
      </Grid>
    </Container>
  );
}
