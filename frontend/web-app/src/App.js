import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import { ThemeProvider, createTheme } from '@mui/material/styles';
import CssBaseline from '@mui/material/CssBaseline';
import { Box } from '@mui/material';

// Components
import Navbar from './components/Navbar';
import Sidebar from './components/Sidebar';

// Pages
import Dashboard from './pages/Dashboard';
import MarketScanner from './pages/MarketScanner';
import Positions from './pages/Positions';
import Analytics from './pages/Analytics';
import Settings from './pages/Settings';

// Context
import { AuthProvider } from './contexts/AuthContext';
import { DataProvider } from './contexts/DataContext';

const theme = createTheme({
  palette: {
    mode: 'dark',
    primary: {
      main: '#1976d2',
    },
    secondary: {
      main: '#dc004e',
    },
    background: {
      default: '#0a0e27',
      paper: '#1a1d3a',
    },
  },
  typography: {
    fontFamily: '"Roboto", "Helvetica", "Arial", sans-serif',
  },
});

function App() {
  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <AuthProvider>
        <DataProvider>
          <Router>
            <Box sx={{ display: 'flex' }}>
              <Navbar />
              <Sidebar />
              <Box
                component="main"
                sx={{
                  flexGrow: 1,
                  p: 3,
                  mt: 8,
                  ml: 30,
                  minHeight: '100vh',
                  backgroundColor: 'background.default',
                }}
              >
                <Routes>
                  <Route path="/" element={<Dashboard />} />
                  <Route path="/dashboard" element={<Dashboard />} />
                  <Route path="/market" element={<MarketScanner />} />
                  <Route path="/positions" element={<Positions />} />
                  <Route path="/analytics" element={<Analytics />} />
                  <Route path="/settings" element={<Settings />} />
                </Routes>
              </Box>
            </Box>
          </Router>
        </DataProvider>
      </AuthProvider>
    </ThemeProvider>
  );
}

export default App;
