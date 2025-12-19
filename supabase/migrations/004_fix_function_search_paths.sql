-- Fix function search paths for security
-- This prevents potential SQL injection attacks by explicitly setting the search path

-- Fix handle_new_user function
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS trigger 
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    INSERT INTO public.user_profiles (id, email, full_name)
    VALUES (
        new.id,
        new.email,
        COALESCE(new.raw_user_meta_data->>'full_name', new.raw_user_meta_data->>'name', '')
    )
    ON CONFLICT (id) DO UPDATE
    SET 
        email = EXCLUDED.email,
        full_name = EXCLUDED.full_name,
        updated_at = NOW();
    RETURN new;
END;
$$ LANGUAGE plpgsql;

-- Fix update_updated_at_column function
CREATE OR REPLACE FUNCTION public.update_updated_at_column()
RETURNS trigger
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Fix is_authorized_user function
CREATE OR REPLACE FUNCTION public.is_authorized_user(user_email text)
RETURNS boolean
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    RETURN EXISTS (
        SELECT 1 FROM public.authorized_users 
        WHERE authorized_users.email = user_email
    );
END;
$$ LANGUAGE plpgsql;

-- Fix check_signup_authorization function
CREATE OR REPLACE FUNCTION public.check_signup_authorization()
RETURNS trigger
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    IF NOT public.is_authorized_user(NEW.email) THEN
        RAISE EXCEPTION 'Unauthorized email address: %', NEW.email;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Add comment explaining the security fix
COMMENT ON FUNCTION public.handle_new_user() IS 'Automatically creates user profile when new auth user is created - search_path secured';
COMMENT ON FUNCTION public.update_updated_at_column() IS 'Updates the updated_at timestamp on row changes - search_path secured';
COMMENT ON FUNCTION public.is_authorized_user(text) IS 'Checks if email is in authorized users list - search_path secured';
COMMENT ON FUNCTION public.check_signup_authorization() IS 'Validates signup against authorized users list - search_path secured';