-- Pricing Engine PostgreSQL Schema
-- Migration: 001_initial_schema.sql

-- ============================================
-- Tabelas de Ativos Rastreados (controle)
-- ============================================

CREATE TABLE IF NOT EXISTS tracked_tickers (
    ticker VARCHAR(20) PRIMARY KEY,
    added_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS tracked_tickers_us (
    ticker VARCHAR(20) PRIMARY KEY,
    added_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS tracked_crypto_slugs (
    slug VARCHAR(50) PRIMARY KEY,
    added_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS tracked_currencies (
    currency_pair VARCHAR(20) PRIMARY KEY,
    added_at TIMESTAMP DEFAULT NOW()
);

-- ============================================
-- Tabelas de Histórico de Cotações
-- ============================================

CREATE TABLE IF NOT EXISTS stock_quotes_history (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(20) NOT NULL,
    unit_price DECIMAL(18,6),
    currency VARCHAR(3) DEFAULT 'BRL',
    recorded_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS stock_quotes_us_history (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(20) NOT NULL,
    unit_price DECIMAL(18,6),
    currency VARCHAR(3) DEFAULT 'USD',
    recorded_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS crypto_quotes_history (
    id SERIAL PRIMARY KEY,
    slug VARCHAR(50) NOT NULL,
    unit_price DECIMAL(18,6),
    currency VARCHAR(3) DEFAULT 'USD',
    recorded_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS currency_quotes_history (
    id SERIAL PRIMARY KEY,
    currency_pair VARCHAR(20) NOT NULL,
    unit_price DECIMAL(18,6),
    recorded_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

-- ============================================
-- Tabelas de Histórico de Dados de Mercado
-- ============================================

CREATE TABLE IF NOT EXISTS curves_history (
    id SERIAL PRIMARY KEY,
    pre_curve JSONB,
    ipca_curve JSONB,
    selic_rate DECIMAL(10,6),
    lft_vna DECIMAL(18,6),
    recorded_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS inflation_history (
    id SERIAL PRIMARY KEY,
    vna DECIMAL(18,6),
    ipca_monthly JSONB,
    recorded_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

-- ============================================
-- Índices para performance
-- ============================================

CREATE INDEX IF NOT EXISTS idx_stock_quotes_ticker_recorded 
ON stock_quotes_history(ticker, recorded_at DESC);

CREATE INDEX IF NOT EXISTS idx_stock_quotes_us_ticker_recorded 
ON stock_quotes_us_history(ticker, recorded_at DESC);

CREATE INDEX IF NOT EXISTS idx_crypto_quotes_slug_recorded 
ON crypto_quotes_history(slug, recorded_at DESC);

CREATE INDEX IF NOT EXISTS idx_currency_quotes_pair_recorded 
ON currency_quotes_history(currency_pair, recorded_at DESC);

CREATE INDEX IF NOT EXISTS idx_curves_recorded 
ON curves_history(recorded_at DESC);

CREATE INDEX IF NOT EXISTS idx_inflation_recorded 
ON inflation_history(recorded_at DESC);