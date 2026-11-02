CREATE INDEX IF NOT EXISTS signals_scanner_symbol_created_idx
    ON signals (symbol, created_at DESC)
    WHERE source = 'scanner';
