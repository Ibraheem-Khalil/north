# Supabase Backend

This folder contains all Supabase-related code and configuration for NORTH AI's authentication and data storage.

## Structure

- **migrations/** - Database schema migrations and SQL files
- **scripts/** - Setup and utility scripts for Supabase
- **functions/** - Supabase Edge Functions (serverless functions)
- **scripts/manual/** - Manual smoke checks (not unit tests; no hardcoded creds)

## Configuration

Supabase credentials are stored in the root `.env` file:
- `SUPABASE_URL` - Your Supabase project URL
- `SUPABASE_ANON_KEY` - Public anonymous key for client-side operations
- `SUPABASE_SERVICE_KEY` - Service role key for server-side operations

## Key Files

- `scripts/setup_supabase.py` - Initial database setup script
- `scripts/manual/auth_smoke.py` - Manual auth smoke test (API must be running)
- `scripts/manual/conversation_storage_smoke.py` - Manual persistence smoke test
