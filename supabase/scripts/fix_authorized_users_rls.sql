-- Fix RLS for authorized_users table
-- This table should be read-only for authenticated users

-- Enable RLS on authorized_users table
ALTER TABLE authorized_users ENABLE ROW LEVEL SECURITY;

-- Create a policy that allows authenticated users to read the table
-- (They need this to check if emails are authorized)
CREATE POLICY "Authenticated users can read authorized emails" ON authorized_users
    FOR SELECT 
    TO authenticated
    USING (true);

-- No INSERT, UPDATE, or DELETE policies - only admins can modify this table through Supabase dashboard
-- This makes the table read-only for all regular users