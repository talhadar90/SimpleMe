-- SimpleMe Orders Database Schema
-- Run this in Supabase SQL Editor: https://supabase.com/dashboard/project/dhsblngaosaxxmwbiusa/sql

-- Create orders table
CREATE TABLE IF NOT EXISTS orders (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,

    -- Shopify info
    shopify_order_id TEXT,
    order_number TEXT,

    -- Our job info
    job_id TEXT UNIQUE NOT NULL,

    -- Customer info
    customer_name TEXT,
    customer_email TEXT,

    -- Order status
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
    error_message TEXT,

    -- Input data
    input_image_path TEXT,
    accessories JSONB DEFAULT '[]'::jsonb,

    -- Card customization
    title TEXT,
    subtitle TEXT,
    text_color TEXT DEFAULT 'red',
    background_type TEXT DEFAULT 'transparent',
    background_color TEXT DEFAULT 'white',
    background_image_path TEXT,

    -- Test order flag
    is_test BOOLEAN DEFAULT false,

    -- Output files (paths on server)
    stl_path TEXT,
    texture_path TEXT,
    blend_path TEXT,

    -- Output URLs (for download)
    stl_url TEXT,
    texture_url TEXT,
    blend_url TEXT,

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create indexes for common queries
CREATE INDEX IF NOT EXISTS idx_orders_job_id ON orders(job_id);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_shopify_order_id ON orders(shopify_order_id);
CREATE INDEX IF NOT EXISTS idx_orders_customer_email ON orders(customer_email);
CREATE INDEX IF NOT EXISTS idx_orders_created_at ON orders(created_at DESC);

-- Enable Row Level Security (RLS)
ALTER TABLE orders ENABLE ROW LEVEL SECURITY;

-- Policy: Allow service role full access (for backend)
CREATE POLICY "Service role has full access" ON orders
    FOR ALL
    USING (true)
    WITH CHECK (true);

-- Function to auto-update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Trigger to auto-update updated_at
DROP TRIGGER IF EXISTS update_orders_updated_at ON orders;
CREATE TRIGGER update_orders_updated_at
    BEFORE UPDATE ON orders
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Verify table created
SELECT 'Orders table created successfully!' as message;
