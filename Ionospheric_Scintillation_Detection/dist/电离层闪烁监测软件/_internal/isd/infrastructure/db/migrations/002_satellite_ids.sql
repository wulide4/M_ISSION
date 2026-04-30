-- Add satellite_ids column to results table for per-satellite PRN labels
ALTER TABLE results ADD COLUMN satellite_ids_json TEXT NOT NULL DEFAULT '[]';
