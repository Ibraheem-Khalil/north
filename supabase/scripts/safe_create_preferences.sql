-- Safe version - Create user_preferences table if it doesn't exist
CREATE TABLE IF NOT EXISTS public.user_preferences (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    preferences JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(user_id)
);

-- Create index for performance (IF NOT EXISTS prevents errors)
CREATE INDEX IF NOT EXISTS idx_user_preferences_user_id ON public.user_preferences(user_id);

-- Enable RLS (safe - won't error if already enabled)
ALTER TABLE public.user_preferences ENABLE ROW LEVEL SECURITY;

-- Create RLS policies only if they don't exist
DO $$ 
BEGIN
    -- Check and create "view" policy
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies 
        WHERE tablename = 'user_preferences' 
        AND policyname = 'Users can view own preferences'
    ) THEN
        CREATE POLICY "Users can view own preferences" ON public.user_preferences
            FOR SELECT USING (auth.uid() = user_id);
    END IF;

    -- Check and create "insert" policy
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies 
        WHERE tablename = 'user_preferences' 
        AND policyname = 'Users can insert own preferences'
    ) THEN
        CREATE POLICY "Users can insert own preferences" ON public.user_preferences
            FOR INSERT WITH CHECK (auth.uid() = user_id);
    END IF;

    -- Check and create "update" policy
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies 
        WHERE tablename = 'user_preferences' 
        AND policyname = 'Users can update own preferences'
    ) THEN
        CREATE POLICY "Users can update own preferences" ON public.user_preferences
            FOR UPDATE USING (auth.uid() = user_id);
    END IF;
END $$;