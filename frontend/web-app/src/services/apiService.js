const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

class ApiService {
  constructor() {
    this.baseURL = API_BASE_URL;
    this.token = localStorage.getItem('authToken');
  }

  async request(endpoint, options = {}) {
    const url = `${this.baseURL}${endpoint}`;
    const config = {
      headers: {
        'Content-Type': 'application/json',
        ...(this.token && { Authorization: `Bearer ${this.token}` }),
      },
      ...options,
    };

    try {
      const response = await fetch(url, config);
      
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      
      return await response.json();
    } catch (error) {
      console.error('API request failed:', error);
      throw error;
    }
  }

  // Authentication
  async login(username, password) {
    const response = await this.request('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    });
    
    if (response.access_token) {
      this.token = response.access_token;
      localStorage.setItem('authToken', this.token);
    }
    
    return response;
  }

  async logout() {
    await this.request('/auth/logout', { method: 'POST' });
    this.token = null;
    localStorage.removeItem('authToken');
  }

  // Market Data
  async getSymbols() {
    return this.request('/market/symbols');
  }

  async getQuote(symbol) {
    return this.request(`/market/quotes/${symbol}`);
  }

  async getHistoricalData(symbol, period = '1mo', interval = '1d') {
    return this.request(`/market/historical/${symbol}?period=${period}&interval=${interval}`);
  }

  async getTradingSignals(symbol) {
    return this.request(`/market/signals/${symbol}`);
  }

  async scanMarket() {
    return this.request('/market/scan');
  }

  // Positions
  async getPositions() {
    return this.request('/trading/positions');
  }

  async createPosition(symbol, quantity, entryPrice) {
    return this.request('/trading/positions', {
      method: 'POST',
      body: JSON.stringify({
        symbol,
        quantity,
        entry_price: entryPrice,
      }),
    });
  }

  async getPosition(positionId) {
    return this.request(`/trading/positions/${positionId}`);
  }

  async updatePositionPrice(positionId, currentPrice) {
    return this.request(`/trading/positions/${positionId}/price`, {
      method: 'PUT',
      body: JSON.stringify({ current_price: currentPrice }),
    });
  }

  // Portfolio
  async getPortfolioMetrics() {
    return this.request('/portfolio/metrics');
  }

  // Analytics
  async runBacktest(strategy, parameters) {
    return this.request('/analytics/backtest', {
      method: 'POST',
      body: JSON.stringify({ strategy, parameters }),
    });
  }

  async getBacktestResults(backtestId) {
    return this.request(`/analytics/backtest/${backtestId}`);
  }

  // AI Decisions
  async analyzeDecision(symbol, signalType, signalStrength, price) {
    return this.request('/decisions/analyze', {
      method: 'POST',
      body: JSON.stringify({
        symbol,
        signal_type: signalType,
        signal_strength: signalStrength,
        price,
      }),
    });
  }

  async getDecision(decisionId) {
    return this.request(`/decisions/${decisionId}`);
  }

  // ML Models
  async getModels() {
    return this.request('/ml/models');
  }

  async getPredictions(symbol, modelId) {
    return this.request(`/ml/predictions/${symbol}?model_id=${modelId}`);
  }

  // System Health
  async getSystemHealth() {
    return this.request('/health/detailed');
  }
}

export const apiService = new ApiService();
