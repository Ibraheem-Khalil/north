"""
Setup Supabase database tables for NORTH chatbot
Run this once to create all necessary tables
"""

import os
from dotenv import load_dotenv
from supabase import create_client, Client
import sys

# Load environment variables
load_dotenv()

# Get Supabase credentials
url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_ANON_KEY")

if not url or not key:
    print("Error: Supabase credentials not found in .env file")
    sys.exit(1)

# Create Supabase client
supabase: Client = create_client(url, key)

print("Connected to Supabase successfully!")
print(f"Project URL: {url}")

# SQL to create tables
sql_commands = [
    """
    -- Create users table (extends Supabase auth.users)
    CREATE TABLE IF NOT EXISTS public.user_profiles (
        id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
        email TEXT UNIQUE NOT NULL,
        full_name TEXT,
        company TEXT DEFAULT 'Example Company',
        role TEXT DEFAULT 'user',
        preferences JSONB DEFAULT '{}',
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
    );
    """,
    
    """
    -- Create conversations table
    CREATE TABLE IF NOT EXISTS public.conversations (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id UUID REFERENCES public.user_profiles(id) ON DELETE CASCADE,
        conversation_id TEXT NOT NULL,
        message TEXT NOT NULL,
        response TEXT NOT NULL,
        metadata JSONB DEFAULT '{}',
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        UNIQUE(conversation_id, created_at)
    );
    """,
    
    """
    -- Create index for faster queries
    CREATE INDEX IF NOT EXISTS idx_conversations_user_id ON public.conversations(user_id);
    CREATE INDEX IF NOT EXISTS idx_conversations_conversation_id ON public.conversations(conversation_id);
    CREATE INDEX IF NOT EXISTS idx_conversations_created_at ON public.conversations(created_at DESC);
    """,
    
    """
    -- Create session tracking table
    CREATE TABLE IF NOT EXISTS public.user_sessions (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id UUID REFERENCES public.user_profiles(id) ON DELETE CASCADE,
        session_token TEXT UNIQUE NOT NULL,
        last_activity TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        metadata JSONB DEFAULT '{}',
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
    );
    """,
    
    """
    -- Create file references table (for Dropbox links in conversations)
    CREATE TABLE IF NOT EXISTS public.file_references (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        conversation_id TEXT NOT NULL,
        file_path TEXT NOT NULL,
        file_name TEXT NOT NULL,
        dropbox_link TEXT,
        file_type TEXT,
        metadata JSONB DEFAULT '{}',
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
    );
    """,
    
    """
    -- Enable Row Level Security (RLS)
    ALTER TABLE public.user_profiles ENABLE ROW LEVEL SECURITY;
    ALTER TABLE public.conversations ENABLE ROW LEVEL SECURITY;
    ALTER TABLE public.user_sessions ENABLE ROW LEVEL SECURITY;
    ALTER TABLE public.file_references ENABLE ROW LEVEL SECURITY;
    """,
    
    """
    -- Create RLS policies for user_profiles
    CREATE POLICY "Users can view own profile" ON public.user_profiles
        FOR SELECT USING (auth.uid() = id);
    
    CREATE POLICY "Users can update own profile" ON public.user_profiles
        FOR UPDATE USING (auth.uid() = id);
    """,
    
    """
    -- Create RLS policies for conversations
    CREATE POLICY "Users can view own conversations" ON public.conversations
        FOR SELECT USING (auth.uid() = user_id);
    
    CREATE POLICY "Users can insert own conversations" ON public.conversations
        FOR INSERT WITH CHECK (auth.uid() = user_id);
    """,
    
    """
    -- Create RLS policies for user_sessions
    CREATE POLICY "Users can view own sessions" ON public.user_sessions
        FOR SELECT USING (auth.uid() = user_id);
    
    CREATE POLICY "Users can manage own sessions" ON public.user_sessions
        FOR ALL USING (auth.uid() = user_id);
    """,
    
    """
    -- Create RLS policies for file_references
    CREATE POLICY "Users can view file references from their conversations" ON public.file_references
        FOR SELECT USING (
            conversation_id IN (
                SELECT conversation_id FROM public.conversations 
                WHERE user_id = auth.uid()
            )
        );
    """,
    
    """
    -- Create updated_at trigger function
    CREATE OR REPLACE FUNCTION update_updated_at_column()
    RETURNS TRIGGER AS $$
    BEGIN
        NEW.updated_at = NOW();
        RETURN NEW;
    END;
    $$ language 'plpgsql';
    """,
    
    """
    -- Apply updated_at trigger to user_profiles
    CREATE TRIGGER update_user_profiles_updated_at 
        BEFORE UPDATE ON public.user_profiles 
        FOR EACH ROW 
        EXECUTE FUNCTION update_updated_at_column();
    """
]

print("\nNote: Supabase Python client doesn't support direct SQL execution.")
print("You'll need to run these commands in the Supabase SQL editor.")

print("\n" + "="*50)
print("IMPORTANT: Database setup requires manual steps!")
print("="*50)
print("\n1. Go to your Supabase Dashboard")
print(f"2. Open: https://supabase.com/dashboard/project/YOUR_PROJECT_ID/sql/new")
print("   (Replace YOUR_PROJECT_ID with your actual Supabase project ID)")
print("3. Copy and paste the following SQL commands:")
print("\n--- COPY EVERYTHING BELOW THIS LINE ---\n")

# Print all SQL commands for manual execution
for sql in sql_commands:
    if sql.strip():
        print(sql.strip())
        print()

print("--- END OF SQL COMMANDS ---")
print("\n4. Click 'Run' in the SQL editor")
print("5. All tables will be creatjued with proper security policies")
print("\nOnce done, your Supabase is ready for the chatbot!")

# Test the connection
try:
    # Try to query a simple table
    result = supabase.auth.get_session()
    print(f"\n[OK] Supabase connection verified!")
except Exception as e:
    print(f"\n[WARNING] Connection test: {e}")
    print("This is normal if you haven't set up authentication yet.")