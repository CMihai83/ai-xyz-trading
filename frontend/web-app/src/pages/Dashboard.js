import React, { useState, useEffect } from 'react';
import {
  Grid,
  Paper,
  Typography,
  Box,
  Card,
  CardContent,
  LinearProgress,
  Chip,
} from '@mui/material';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
} from 'recharts';
import { useData } from '../contexts/DataContext';

const Dashboard = () => {
  const { portfolioMetrics, marketData, positions } = useData();
  const [performanceData, setPerformanceData] = useState([]);

  useEffect(() => {
    // Generate sample performance data
    const data = [];
    for (let i = 0; i < 30; i++) {
      data.push({
        date: new Date(Date.now() - (29 - i) * 24 * 60 * 60 * 1000).toLocaleDateString(),
        value: 100000 + Math.random() * 20000 - 10000,
        pnl: (Math.random() - 0.5) * 5000,
      });
    }
    setPerformanceData(data);
  }, []);

  const COLORS = ['#0088FE', '#00C49F', '#FFBB28', '#FF8042', '#8884D8'];

  return (
    <Box>
      <Typography variant="h4" gutterBottom>
        Trading Dashboard
      </Typography>

      {/* Key Metrics */}
      <Grid container spacing={3} sx={{ mb: 3 }}>
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Typography color="textSecondary" gutterBottom>
                Portfolio Value
              </Typography>
              <Typography variant="h5">
                ${portfolioMetrics?.total_value?.toLocaleString() || '0'}
              </Typography>
              <Typography
                variant="body2"
                color={portfolioMetrics?.total_pnl >= 0 ? 'success.main' : 'error.main'}
              >
                {portfolioMetrics?.total_pnl >= 0 ? '+' : ''}
                ${portfolioMetrics?.total_pnl?.toLocaleString() || '0'}
              </Typography>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Typography color="textSecondary" gutterBottom>
                Active Positions
              </Typography>
              <Typography variant="h5">
                {portfolioMetrics?.position_count || 0}
              </Typography>
              <Typography variant="body2" color="textSecondary">
                Positions
              </Typography>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Typography color="textSecondary" gutterBottom>
                Unrealized P&L
              </Typography>
              <Typography variant="h5">
                ${portfolioMetrics?.total_unrealized_pnl?.toLocaleString() || '0'}
              </Typography>
              <Typography variant="body2" color="textSecondary">
                Unrealized
              </Typography>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Typography color="textSecondary" gutterBottom>
                Realized P&L
              </Typography>
              <Typography variant="h5">
                ${portfolioMetrics?.total_realized_pnl?.toLocaleString() || '0'}
              </Typography>
              <Typography variant="body2" color="textSecondary">
                Realized
              </Typography>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Charts */}
      <Grid container spacing={3}>
        {/* Performance Chart */}
        <Grid item xs={12} md={8}>
          <Paper sx={{ p: 2 }}>
            <Typography variant="h6" gutterBottom>
              Portfolio Performance
            </Typography>
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={performanceData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="date" />
                <YAxis />
                <Tooltip />
                <Line
                  type="monotone"
                  dataKey="value"
                  stroke="#8884d8"
                  strokeWidth={2}
                />
              </LineChart>
            </ResponsiveContainer>
          </Paper>
        </Grid>

        {/* Position Allocation */}
        <Grid item xs={12} md={4}>
          <Paper sx={{ p: 2 }}>
            <Typography variant="h6" gutterBottom>
              Position Allocation
            </Typography>
            <ResponsiveContainer width="100%" height={300}>
              <PieChart>
                <Pie
                  data={portfolioMetrics?.positions || []}
                  cx="50%"
                  cy="50%"
                  labelLine={false}
                  label={({ symbol, pnl_percent }) => `${symbol} (${pnl_percent?.toFixed(1)}%)`}
                  outerRadius={80}
                  fill="#8884d8"
                  dataKey="current_value"
                >
                  {(portfolioMetrics?.positions || []).map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          </Paper>
        </Grid>

        {/* Recent Signals */}
        <Grid item xs={12} md={6}>
          <Paper sx={{ p: 2 }}>
            <Typography variant="h6" gutterBottom>
              Recent Trading Signals
            </Typography>
            <Box>
              {marketData?.scan_results?.slice(0, 5).map((signal, index) => (
                <Box key={index} sx={{ mb: 2, p: 1, border: '1px solid #333', borderRadius: 1 }}>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <Typography variant="subtitle1">{signal.symbol}</Typography>
                    <Chip
                      label={signal.signals[0]?.type || 'HOLD'}
                      color={signal.signals[0]?.type === 'BUY' ? 'success' : 'error'}
                      size="small"
                    />
                  </Box>
                  <Typography variant="body2" color="textSecondary">
                    {signal.signals[0]?.reason || 'No signals'}
                  </Typography>
                  <LinearProgress
                    variant="determinate"
                    value={(signal.signals[0]?.strength || 0) * 100}
                    sx={{ mt: 1 }}
                  />
                </Box>
              ))}
            </Box>
          </Paper>
        </Grid>

        {/* Market Overview */}
        <Grid item xs={12} md={6}>
          <Paper sx={{ p: 2 }}>
            <Typography variant="h6" gutterBottom>
              Market Overview
            </Typography>
            <Grid container spacing={2}>
              <Grid item xs={6}>
                <Typography variant="body2" color="textSecondary">
                  S&P 500
                </Typography>
                <Typography variant="h6" color="success.main">
                  4,150.25 (+0.75%)
                </Typography>
              </Grid>
              <Grid item xs={6}>
                <Typography variant="body2" color="textSecondary">
                  NASDAQ
                </Typography>
                <Typography variant="h6" color="success.main">
                  12,850.50 (+1.25%)
                </Typography>
              </Grid>
              <Grid item xs={6}>
                <Typography variant="body2" color="textSecondary">
                  VIX
                </Typography>
                <Typography variant="h6" color="error.main">
                  18.75 (-2.15%)
                </Typography>
              </Grid>
              <Grid item xs={6}>
                <Typography variant="body2" color="textSecondary">
                  USD/EUR
                </Typography>
                <Typography variant="h6">
                  1.0850 (+0.15%)
                </Typography>
              </Grid>
            </Grid>
          </Paper>
        </Grid>
      </Grid>
    </Box>
  );
};

export default Dashboard;
