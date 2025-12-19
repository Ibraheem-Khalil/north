-- Migration to fix RLS performance issues identified by Supabase linter
-- This addresses:
-- 1. Auth RLS Initialization Plan - wrapping auth.uid() in subqueries
-- 2. Multiple Permissive Policies - consolidating duplicate policies

-- ============================================
-- STEP 1: Drop all existing RLS policies
-- ============================================

-- Drop user_profiles policies
DROP POLICY IF EXISTS "Users can view own profile" ON public.user_profiles;
DROP POLICY IF EXISTS "Users can update own profile" ON public.user_profiles;

-- Drop conversations policies  
DROP POLICY IF EXISTS "Users can view own conversations" ON public.conversations;
DROP POLICY IF EXISTS "Users can insert own conversations" ON public.conversations;
DROP POLICY IF EXISTS "Only authorized users can see their own conversations" ON public.conversations;
DROP POLICY IF EXISTS "Only authorized users can create conversations" ON public.conversations;
DROP POLICY IF EXISTS "Only authorized users can update their conversations" ON public.conversations;
DROP POLICY IF EXISTS "Only authorized users can delete their conversations" ON public.conversations;

-- Drop user_preferences policies
DROP POLICY IF EXISTS "Users can view own preferences" ON public.user_preferences;
DROP POLICY IF EXISTS "Users can insert own preferences" ON public.user_preferences;
DROP POLICY IF EXISTS "Users can update own preferences" ON public.user_preferences;
DROP POLICY IF EXISTS "Only authorized users can read preferences" ON public.user_preferences;
DROP POLICY IF EXISTS "Only authorized users can update preferences" ON public.user_preferences;

-- Drop user_sessions policies
DROP POLICY IF EXISTS "Users can view own sessions" ON public.user_sessions;
DROP POLICY IF EXISTS "Users can manage own sessions" ON public.user_sessions;

-- Drop file_references policies
DROP POLICY IF EXISTS "Users can view file references from their conversations" ON public.file_references;

-- ============================================
-- STEP 2: Create optimized RLS policies
-- ============================================

-- User Profiles policies (consolidated and optimized)
CREATE POLICY "user_profiles_select_policy" ON public.user_profiles
    FOR SELECT USING (id = (SELECT auth.uid()));

CREATE POLICY "user_profiles_update_policy" ON public.user_profiles
    FOR UPDATE USING (id = (SELECT auth.uid()));

-- Conversations policies (consolidated and optimized)
CREATE POLICY "conversations_select_policy" ON public.conversations
    FOR SELECT USING (user_id = (SELECT auth.uid()));

CREATE POLICY "conversations_insert_policy" ON public.conversations
    FOR INSERT WITH CHECK (user_id = (SELECT auth.uid()));

CREATE POLICY "conversations_update_policy" ON public.conversations
    FOR UPDATE USING (user_id = (SELECT auth.uid()));
 
CREATE POLICY "conversations_delete_policy" ON public.conversations
    FOR DELETE USING (user_id = (SELECT auth.uid()));

-- User Preferences policies (consolidated and optimized)
CREATE POLICY "user_preferences_select_policy" ON public.user_preferences
    FOR SELECT USING (user_id = (SELECT auth.uid()));

CREATE POLICY "user_preferences_insert_policy" ON public.user_preferences
    FOR INSERT WITH CHECK (user_id = (SELECT auth.uid()));

CREATE POLICY "user_preferences_update_policy" ON public.user_preferences
    FOR UPDATE USING (user_id = (SELECT auth.uid()));

-- User Sessions policies (consolidated and optimized - if table exists)
DO $$ 
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'user_sessions') THEN
        EXECUTE 'CREATE POLICY "user_sessions_all_policy" ON public.user_sessions
            FOR ALL USING (user_id = (SELECT auth.uid()))';
    END IF;
END $$;

-- File References policies (optimized - if table exists)
DO $$ 
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'file_references') THEN
        -- First check if there's a direct user_id column
        IF EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'file_references' AND column_name = 'user_id') THEN
            EXECUTE 'CREATE POLICY "file_references_select_policy" ON public.file_references
                FOR SELECT USING (user_id = (SELECT auth.uid()))';
        -- Otherwise, check through conversations table
        ELSIF EXISTS (SELECT 1 FROM information_schema.columns 
                      WHERE table_name = 'file_references' AND column_name = 'conversation_id') THEN
            EXECUTE 'CREATE POLICY "file_references_select_policy" ON public.file_references
                FOR SELECT USING (
                    EXISTS (
                        SELECT 1 FROM public.conversations 
                        WHERE conversations.id = file_references.conversation_id 
                        AND conversations.user_id = (SELECT auth.uid())
                    )
                )';
        END IF;
    END IF;
END $$;

-- ============================================
-- STEP 3: Ensure RLS is enabled on all tables
-- ============================================

ALTER TABLE public.user_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_preferences ENABLE ROW LEVEL SECURITY;

-- Enable RLS on optional tables if they exist
DO $$ 
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'user_sessions') THEN
        EXECUTE 'ALTER TABLE public.user_sessions ENABLE ROW LEVEL SECURITY';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'file_references') THEN
        EXECUTE 'ALTER TABLE public.file_references ENABLE ROW LEVEL SECURITY';
    END IF;
END $$;

-- ============================================
-- STEP 4: Add comment to track migration
-- ============================================

COMMENT ON SCHEMA public IS 'RLS policies optimized - Fixed auth.uid() performance and consolidated duplicate policies';