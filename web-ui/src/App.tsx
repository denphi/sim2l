import { BrowserRouter as Router, Routes, Route, Link } from 'react-router-dom';
import {
  AppBar,
  Toolbar,
  Typography,
  Button,
  Container,
  Box,
  CssBaseline,
  ThemeProvider,
  createTheme,
} from '@mui/material';
import {
  Dashboard as DashboardIcon,
  Storage as StorageIcon,
  ListAlt as ListAltIcon,
  Folder as FolderIcon,
} from '@mui/icons-material';
import { Dashboard } from './pages/Dashboard';
import { Cache } from './pages/Cache';
import { Results } from './pages/Results';
import { Catalog } from './pages/Catalog';

const theme = createTheme({
  palette: {
    mode: 'light',
    primary: {
      main: '#1976d2',
    },
    secondary: {
      main: '#dc004e',
    },
  },
});

function App() {
  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <Router>
        <Box sx={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
          <AppBar position="static">
            <Toolbar>
              <Typography variant="h6" component="div" sx={{ flexGrow: 1 }}>
                sim2l Dashboard
              </Typography>
              <Button color="inherit" component={Link} to="/" startIcon={<DashboardIcon />}>
                Dashboard
              </Button>
              <Button color="inherit" component={Link} to="/cache" startIcon={<StorageIcon />}>
                Cache
              </Button>
              <Button color="inherit" component={Link} to="/results" startIcon={<ListAltIcon />}>
                Results
              </Button>
              <Button color="inherit" component={Link} to="/catalog" startIcon={<FolderIcon />}>
                Catalog
              </Button>
            </Toolbar>
          </AppBar>

          <Box component="main" sx={{ flexGrow: 1, bgcolor: 'background.default' }}>
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/cache" element={<Cache />} />
              <Route path="/results" element={<Results />} />
              <Route path="/catalog" element={<Catalog />} />
            </Routes>
          </Box>

          <Box
            component="footer"
            sx={{
              py: 3,
              px: 2,
              mt: 'auto',
              bgcolor: 'background.paper',
            }}
          >
            <Container maxWidth="sm">
              <Typography variant="body2" color="text.secondary" align="center">
                sim2l Dashboard © {new Date().getFullYear()}
              </Typography>
            </Container>
          </Box>
        </Box>
      </Router>
    </ThemeProvider>
  );
}

export default App;
