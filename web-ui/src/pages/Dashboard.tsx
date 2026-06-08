import { useEffect, useRef, useState } from 'react';
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

  // Review item #T14: replace the unconditional 10s setInterval with a
  // self-scheduling poll loop that backs off when the API is unreachable.
  // The previous setup fired four requests every ten seconds whether the
  // services were up or not — which slammed a downed backend with a
  // refresh storm. The new schedule:
  //   - 10s when the last poll succeeded
  //   - 20s / 40s / 60s on consecutive failures, capped at 60s
  // ``cancelled`` lets the unmount cleanup short-circuit a pending poll.
  const consecutiveFailures = useRef(0);

  useEffect(() => {
    let cancelled = false;
    let timeout: ReturnType<typeof setTimeout> | null = null;

    const tick = async () => {
      if (cancelled) return;
      try {
        const [health, cache, overview] = await Promise.all([
          apiClient.checkAllServices(),
          cacheService.getStats().catch(() => null),
          catalogService.getOverviewStats().catch(() => null),
        ]);
        if (cancelled) return;
        setServiceHealth(health);
        setCacheStats(cache);
        setOverviewStats(overview);
        consecutiveFailures.current = 0;
      } catch (error) {
        if (cancelled) return;
        console.error('Failed to load dashboard data:', error);
        consecutiveFailures.current = Math.min(consecutiveFailures.current + 1, 3);
      } finally {
        if (!cancelled) {
          setLoading(false);
          const delay = 10_000 * Math.max(1, Math.pow(2, consecutiveFailures.current));
          // 10s / 20s / 40s / 80s — clamp to 60s so we don't go idle for
          // longer than the user's notion of "live" dashboard.
          timeout = setTimeout(tick, Math.min(delay, 60_000));
        }
      }
    };

    tick();
    return () => {
      cancelled = true;
      if (timeout) clearTimeout(timeout);
    };
  }, []);

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
