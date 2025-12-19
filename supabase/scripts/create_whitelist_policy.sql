-- Create whitelist policy for extra security
-- This adds database-level protection even if someone bypasses the API

-- Create a table to store authorized emails
CREATE TABLE IF NOT EXISTS authorized_users (
    email TEXT PRIMARY KEY,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    notes TEXT
);

-- Insert authorized emails
INSERT INTO authorized_users (email, notes) VALUES
    ('admin@example.com', 'Admin - Example User'),
    ('user1@example.com', 'User One'),
    ('user2@example.com', 'User Two'),
    ('user3@example.com', 'User Three')
ON CONFLICT (email) DO NOTHING;

-- Create a function to check if a user is authorized
CREATE OR REPLACE FUNCTION is_authorized_user(user_email TEXT)
RETURNS BOOLEAN AS $$
BEGIN
    RETURN EXISTS (
        SELECT 1 FROM authorized_users 
        WHERE LOWER(email) = LOWER(user_email)
    );
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Update RLS policies for conversations table
ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;

-- Drop existing policies if they exist
DROP POLICY IF EXISTS "Users can only see their own conversations" ON conversations;
DROP POLICY IF EXISTS "Users can only create their own conversations" ON conversations;
DROP POLICY IF EXISTS "Users can only update their own conversations" ON conversations;
DROP POLICY IF EXISTS "Users can only delete their own conversations" ON conversations;

-- Create new policies with whitelist check
CREATE POLICY "Only authorized users can see their own conversations" ON conversations
    FOR SELECT USING (
        auth.uid() = user_id 
        AND is_authorized_user(auth.email())
    );

CREATE POLICY "Only authorized users can create conversations" ON conversations
    FOR INSERT WITH CHECK (
        auth.uid() = user_id 
        AND is_authorized_user(auth.email())
    );

CREATE POLICY "Only authorized users can update their conversations" ON conversations
    FOR UPDATE USING (
        auth.uid() = user_id 
        AND is_authorized_user(auth.email())
    );

CREATE POLICY "Only authorized users can delete their conversations" ON conversations
    FOR DELETE USING (
        auth.uid() = user_id 
        AND is_authorized_user(auth.email())
    );

-- Update RLS policies for user_preferences table
ALTER TABLE user_preferences ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users can read their own preferences" ON user_preferences;
DROP POLICY IF EXISTS "Users can update their own preferences" ON user_preferences;

CREATE POLICY "Only authorized users can read preferences" ON user_preferences
    FOR SELECT USING (
        auth.uid() = user_id 
        AND is_authorized_user(auth.email())
    );

CREATE POLICY "Only authorized users can update preferences" ON user_preferences
    FOR ALL USING (
        auth.uid() = user_id 
        AND is_authorized_user(auth.email())
    );

-- Add a trigger to prevent unauthorized signups at the database level
CREATE OR REPLACE FUNCTION check_signup_authorization()
RETURNS TRIGGER AS $$
BEGIN
    IF NOT is_authorized_user(NEW.email) THEN
        RAISE EXCEPTION 'Unauthorized: Email % is not on the whitelist', NEW.email;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply trigger to auth.users table (requires admin access)
-- Note: This might need to be run in Supabase dashboard with admin privileges
-- DROP TRIGGER IF EXISTS check_signup_authorization_trigger ON auth.users;
-- CREATE TRIGGER check_signup_authorization_trigger
--     BEFORE INSERT ON auth.users
--     FOR EACH ROW
--     EXECUTE FUNCTION check_signup_authorization();

GRANT EXECUTE ON FUNCTION is_authorized_user TO authenticated;
GRANT SELECT ON authorized_users TO authenticated;
