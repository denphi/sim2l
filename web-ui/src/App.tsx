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
  typography: {
    fontFamily: '"Inter", "Roboto", "Helvetica", "Arial", sans-serif',
  },
  palette: {
    mode: 'light',
    primary: {
      main: '#2e3b4e', // Deeper, more sophisticated blue/grey
    },
    secondary: {
      main: '#eab308', // Subtle amber
    },
    background: {
      default: '#f8fafc',
      paper: '#ffffff',
    },
  },
  components: {
    MuiCard: {
      styleOverrides: {
        root: {
          elevation: 0,
          boxShadow: 'none',
          border: '1px solid #e2e8f0',
          borderRadius: '8px',
          transition: 'all 0.2s ease-in-out',
          '&:hover': {
            borderColor: '#CBD5E1',
            transform: 'translateY(-2px)',
            boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1)',
          }
        },
      },
    },
    MuiPaper: {
      styleOverrides: {
        root: {
          elevation: 0,
          boxShadow: 'none',
          border: '1px solid #e2e8f0',
          borderRadius: '8px',
        },
      },
      defaultProps: {
        elevation: 0,
      }
    },
    MuiButton: {
      styleOverrides: {
        root: {
          textTransform: 'none',
          borderRadius: '6px',
        },
      },
    },
    MuiAppBar: {
      styleOverrides: {
        root: {
          boxShadow: 'none',
          borderBottom: '1px solid #e2e8f0',
          backgroundColor: '#ffffff',
          color: '#0f172a',
        },
      },
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
