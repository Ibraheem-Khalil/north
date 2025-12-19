## NORTH AI Template – Security & Publication Notes

- **No secrets in repo**: `.env`, `.env.production`, and other environment files must stay empty; populate them only in your own environment. Do not commit API keys, service tokens, or JWT secrets.
- **Key material required**: Set `NORTH_MASTER_KEY` and `NORTH_KDF_SALT` in your environment before using the Dropbox token manager. The code will generate defaults if missing, but that is for local smoke only and should not be used for any shared deployment.
- **Development-only flags**: `DISABLE_AUTH_VERIFICATION=true` is for local testing only. Never set it in production or in any shared demo environment.
- **External dependencies**: Weaviate, Supabase, and Dropbox must be reachable for full functionality; otherwise the app will degrade to “agent unavailable” responses. Check `/api/status` or logs before demos.
- **Frontend artifacts**: `node_modules`, `dist`, and other build outputs are ignored; regenerate locally as needed.

This is a skills template, not a hardened product. Review and adjust security controls before deploying anywhere beyond local demos.
