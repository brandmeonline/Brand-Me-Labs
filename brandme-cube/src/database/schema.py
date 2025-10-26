"""Database schema definitions (for reference)"""

# The actual schema is in brandme-data/schemas/cube_service.sql
# This file can be used for SQLAlchemy models if needed later

CUBES_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS cubes (
    cube_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    product_details JSONB,
    provenance JSONB,
    ownership JSONB,
    social_layer JSONB,
    esg_impact JSONB,
    lifecycle JSONB,

    visibility_settings JSONB DEFAULT '{"product_details": "public", "provenance": "public", "ownership": "private", "social_layer": "public", "esg_impact": "public", "lifecycle": "authenticated"}'::jsonb,

    blockchain_tx_hash TEXT,
    midnight_tx_hash TEXT
);
"""
