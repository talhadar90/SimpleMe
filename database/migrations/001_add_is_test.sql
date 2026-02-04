-- Migration: Add is_test column to orders table
-- Run this in Supabase SQL Editor

ALTER TABLE orders ADD COLUMN IF NOT EXISTS is_test BOOLEAN DEFAULT false;

-- Create index for filtering test orders
CREATE INDEX IF NOT EXISTS idx_orders_is_test ON orders(is_test);

-- Verify
SELECT 'is_test column added successfully!' as message;
