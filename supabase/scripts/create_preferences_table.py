"""
Create user_preferences table in Supabase
"""

from supabase import create_client
import os
from dotenv import load_dotenv

load_dotenv()

# Use service key to bypass RLS
supabase = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_SERVICE_KEY")
)

# SQL to create the user_preferences table
sql = """
-- Create user_preferences table if it doesn't exist
CREATE TABLE IF NOT EXISTS public.user_preferences (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    preferences JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(user_id)
);

-- Create index for performance
CREATE INDEX IF NOT EXISTS idx_user_preferences_user_id ON public.user_preferences(user_id);

-- Enable RLS
ALTER TABLE public.user_preferences ENABLE ROW LEVEL SECURITY;

-- Drop existing policies if they exist
DROP POLICY IF EXISTS "Users can view own preferences" ON public.user_preferences;
DROP POLICY IF EXISTS "Users can insert own preferences" ON public.user_preferences;
DROP POLICY IF EXISTS "Users can update own preferences" ON public.user_preferences;

-- Create RLS policies
CREATE POLICY "Users can view own preferences" ON public.user_preferences
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own preferences" ON public.user_preferences
    FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own preferences" ON public.user_preferences
    FOR UPDATE USING (auth.uid() = user_id);
"""

print("Creating user_preferences table...")

try:
    # Execute the SQL using RPC (raw SQL execution)
    # Note: Supabase Python client doesn't have direct SQL execution, 
    # so we'll need to run this in the Supabase dashboard
    print("\nPlease run the following SQL in your Supabase SQL Editor:")
    print("=" * 60)
    print(sql)
    print("=" * 60)
    print("\nGo to: https://supabase.com/dashboard/project/YOUR_PROJECT_ID/sql/new")
    print("   (Replace YOUR_PROJECT_ID with your actual Supabase project ID)")
    print("\n1. Copy the SQL above")
    print("2. Paste it in the SQL editor")
    print("3. Click 'Run'")
    
except Exception as e:
    print(f"Error: {e}")

print("\nOnce the table is created, the preferences feature will work!")