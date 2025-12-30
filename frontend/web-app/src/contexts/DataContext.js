import React, { createContext, useContext, useState, useEffect } from 'react';
import { apiService } from '../services/apiService';

const DataContext = createContext();

export const useData = () => {
  const context = useContext(DataContext);
  if (!context) {
    throw new Error('useData must be used within a DataProvider');
  }
  return context;
};

export const DataProvider = ({ children }) => {
  const [portfolioMetrics, setPortfolioMetrics] = useState(null);
  const [positions, setPositions] = useState([]);
  const [marketData, setMarketData] = useState(null);
  const [loading, setLoading] = useState(false);

  const fetchPortfolioMetrics = async () => {
    try {
      setLoading(true);
      const metrics = await apiService.getPortfolioMetrics();
      setPortfolioMetrics(metrics);
    } catch (error) {
      console.error('Error fetching portfolio metrics:', error);
    } finally {
      setLoading(false);
    }
  };

  const fetchPositions = async () => {
    try {
      const positionsData = await apiService.getPositions();
      setPositions(positionsData);
    } catch (error) {
      console.error('Error fetching positions:', error);
    }
  };

  const fetchMarketData = async () => {
    try {
      const scanResults = await apiService.scanMarket();
      setMarketData(scanResults);
    } catch (error) {
      console.error('Error fetching market data:', error);
    }
  };

  useEffect(() => {
    fetchPortfolioMetrics();
    fetchPositions();
    fetchMarketData();

    // Set up periodic updates
    const interval = setInterval(() => {
      fetchPortfolioMetrics();
      fetchPositions();
      fetchMarketData();
    }, 30000); // Update every 30 seconds

    return () => clearInterval(interval);
  }, []);

  const value = {
    portfolioMetrics,
    positions,
    marketData,
    loading,
    refreshData: () => {
      fetchPortfolioMetrics();
      fetchPositions();
      fetchMarketData();
    },
  };

  return (
    <DataContext.Provider value={value}>
      {children}
    </DataContext.Provider>
  );
};
