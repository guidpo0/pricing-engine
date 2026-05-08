-- Pricing Engine PostgreSQL Schema
-- Migration: 002_selic_daily_factors.sql
-- Description: Store daily SELIC factors from BCB SGS series 12 for
-- historical LFT VNA computation. Populated by refresh_curves().
-- Safe to run multiple times (IF NOT EXISTS).

CREATE TABLE IF NOT EXISTS selic_daily_factors (
    factor_date DATE PRIMARY KEY,
    daily_factor DECIMAL(10,8) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_selic_daily_factors_date
    ON selic_daily_factors (factor_date ASC);
