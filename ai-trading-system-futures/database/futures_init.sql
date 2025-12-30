-- Futures Trading Database Schema
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Enhanced positions table for futures
CREATE TABLE futures_positions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID,
    symbol VARCHAR(20) NOT NULL,
    side VARCHAR(10) NOT NULL, -- 'long' or 'short'
    quantity DECIMAL(18, 8) NOT NULL,
    entry_price DECIMAL(18, 8) NOT NULL,
    mark_price DECIMAL(18, 8),
    liquidation_price DECIMAL(18, 8),
    leverage INTEGER NOT NULL,
    margin_used DECIMAL(18, 8) NOT NULL,
    maintenance_margin DECIMAL(18, 8) NOT NULL,
    unrealized_pnl DECIMAL(18, 8) DEFAULT 0,
    realized_pnl DECIMAL(18, 8) DEFAULT 0,
    funding_fee DECIMAL(18, 8) DEFAULT 0,
    stop_loss DECIMAL(18, 8),
    take_profit DECIMAL(18, 8),
    status VARCHAR(20) DEFAULT 'open', -- 'open', 'closed', 'liquidated'
    position_mode VARCHAR(20) DEFAULT 'hedge', -- 'hedge', 'one_way'
    margin_mode VARCHAR(20) DEFAULT 'cross', -- 'cross', 'isolated'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Enhanced trades table for futures
CREATE TABLE futures_trades (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID,
    position_id UUID REFERENCES futures_positions(id),
    symbol VARCHAR(20) NOT NULL,
    side VARCHAR(10) NOT NULL, -- 'buy' or 'sell'
    quantity DECIMAL(18, 8) NOT NULL,
    price DECIMAL(18, 8) NOT NULL,
    leverage INTEGER NOT NULL,
    margin_used DECIMAL(18, 8) NOT NULL,
    fees DECIMAL(18, 8) DEFAULT 0,
    funding_fee DECIMAL(18, 8) DEFAULT 0,
    pnl DECIMAL(18, 8),
    order_type VARCHAR(20) DEFAULT 'limit', -- 'limit', 'market', 'stop', 'take_profit'
    time_in_force VARCHAR(10) DEFAULT 'GTC', -- 'GTC', 'IOC', 'FOK'
    exchange_order_id VARCHAR(100),
    client_order_id VARCHAR(100),
    status VARCHAR(20) DEFAULT 'pending', -- 'pending', 'filled', 'cancelled', 'failed'
    executed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Futures account information
CREATE TABLE futures_accounts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID,
    exchange VARCHAR(50) NOT NULL DEFAULT 'bitget',
    account_type VARCHAR(20) NOT NULL DEFAULT 'futures', -- 'futures', 'spot'
    margin_balance DECIMAL(18, 8) NOT NULL DEFAULT 0,
    available_balance DECIMAL(18, 8) NOT NULL DEFAULT 0,
    used_margin DECIMAL(18, 8) NOT NULL DEFAULT 0,
    unrealized_pnl DECIMAL(18, 8) NOT NULL DEFAULT 0,
    margin_ratio DECIMAL(10, 6),
    maintenance_margin DECIMAL(18, 8) NOT NULL DEFAULT 0,
    total_wallet_balance DECIMAL(18, 8) NOT NULL DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Leverage settings per symbol
CREATE TABLE leverage_settings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID,
    symbol VARCHAR(20) NOT NULL,
    leverage INTEGER NOT NULL,
    margin_mode VARCHAR(20) NOT NULL DEFAULT 'cross', -- 'cross', 'isolated'
    position_mode VARCHAR(20) NOT NULL DEFAULT 'hedge', -- 'hedge', 'one_way'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, symbol)
);

-- Risk metrics for futures
CREATE TABLE futures_risk_metrics (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID,
    total_margin_used DECIMAL(18, 8) NOT NULL DEFAULT 0,
    margin_usage_percent DECIMAL(10, 6) NOT NULL DEFAULT 0,
    liquidation_risk VARCHAR(20) NOT NULL DEFAULT 'low', -- 'low', 'medium', 'high', 'critical'
    correlation_risk DECIMAL(10, 6) NOT NULL DEFAULT 0,
    var_1d DECIMAL(18, 8) NOT NULL DEFAULT 0,
    max_drawdown DECIMAL(10, 6) NOT NULL DEFAULT 0,
    risk_score DECIMAL(10, 6) NOT NULL DEFAULT 0,
    risk_level VARCHAR(20) NOT NULL DEFAULT 'low', -- 'low', 'medium', 'high', 'critical'
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Funding rates tracking
CREATE TABLE funding_rates (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    symbol VARCHAR(20) NOT NULL,
    funding_rate DECIMAL(10, 8) NOT NULL,
    funding_time TIMESTAMP NOT NULL,
    next_funding_time TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for better performance
CREATE INDEX idx_futures_positions_user_id ON futures_positions(user_id);
CREATE INDEX idx_futures_positions_symbol ON futures_positions(symbol);
CREATE INDEX idx_futures_positions_status ON futures_positions(status);
CREATE INDEX idx_futures_trades_user_id ON futures_trades(user_id);
CREATE INDEX idx_futures_trades_symbol ON futures_trades(symbol);
CREATE INDEX idx_futures_trades_created_at ON futures_trades(created_at);
CREATE INDEX idx_leverage_settings_user_symbol ON leverage_settings(user_id, symbol);
CREATE INDEX idx_funding_rates_symbol ON funding_rates(symbol);
CREATE INDEX idx_funding_rates_funding_time ON funding_rates(funding_time);

-- Insert default user for testing
INSERT INTO futures_accounts (user_id, margin_balance, available_balance) 
VALUES (uuid_generate_v4(), 1000.00, 1000.00);
