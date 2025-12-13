# CLAUDE.md - Cloudflare Quick Template

## Project: [NAME]
Auth: Clerk | Platform: Cloudflare Workers/Pages

---

## CRITICAL: Verify Before Coding

### Step 1: Detect Stack
Inspect project files:
- `package.json` -> Node/TS (check deps: hono, next, remix, astro)
- `requirements.txt` / `pyproject.toml` -> Python Workers
- `go.mod` -> Go | `Cargo.toml` -> Rust
- `index.html` (no package.json) -> Static HTML (use Pages Git Integration)
- No files? -> Run `npm create cloudflare@latest`

### Step 2: Fetch Documentation
Use MCP tools if available, otherwise web fetch these URLs:

**Cloudflare:**
| Service | URL |
|---------|-----|
| Workers | https://developers.cloudflare.com/workers/ |
| D1 Get Started | https://developers.cloudflare.com/d1/get-started/ |
| KV | https://developers.cloudflare.com/kv/ |
| R2 | https://developers.cloudflare.com/r2/ |
| Durable Objects | https://developers.cloudflare.com/durable-objects/ |
| Pages | https://developers.cloudflare.com/pages/ |
| Pages Git Integration | https://developers.cloudflare.com/pages/get-started/git-integration/ |
| Pages Functions | https://developers.cloudflare.com/pages/functions/ |

**Clerk:**
| Resource | URL |
|----------|-----|
| JS Backend SDK | https://clerk.com/docs/js-backend/getting-started/quickstart |
| authenticateRequest() | https://clerk.com/docs/reference/backend/authenticate-request |
| Hono Middleware | https://github.com/honojs/middleware/tree/main/packages/clerk-auth |
| Next.js | https://clerk.com/docs/reference/nextjs/overview |

**Frameworks:**
| Framework | URL |
|-----------|-----|
| Hono | https://hono.dev/docs/getting-started/cloudflare-workers |
| Next.js | https://developers.cloudflare.com/pages/framework-guides/nextjs/ |
| Drizzle+D1 | https://orm.drizzle.team/docs/get-started/d1-new |

---

## Wrangler Config Reference

```jsonc
{
  "$schema": "./node_modules/wrangler/config-schema.json",
  "name": "app",
  "main": "src/index.ts",
  "compatibility_date": "2024-12-01",
  "compatibility_flags": ["nodejs_compat"],
  "d1_databases": [{ "binding": "DB", "database_name": "x", "database_id": "x" }],
  "kv_namespaces": [{ "binding": "KV", "id": "x" }],
  "r2_buckets": [{ "binding": "BUCKET", "bucket_name": "x" }]
}
```

---

## Cloudflare Pages: Static HTML via GitHub

For static HTML sites (no build step). Docs: https://developers.cloudflare.com/pages/get-started/git-integration/

### Setup (Dashboard)
1. **Dashboard > Workers & Pages > Create > Pages > Connect to Git**
2. Select GitHub repo
3. Build command: *(empty)* | Output directory: `/` or `/public`
4. Deploy

### Static Site Structure
```
/
├── index.html
├── about.html
├── css/style.css
├── js/app.js
├── _headers          # Optional: caching/security headers
└── _redirects        # Optional: redirect rules
```

### Adding API Routes (Pages Functions)
```
/
├── index.html
├── functions/
│   └── api/
│       └── hello.ts  # -> /api/hello
```

**functions/api/hello.ts:**
```typescript
// Use PagesFunction<Env> when you have bindings (D1, KV, etc.)
export const onRequest: PagesFunction = async (context) => {
  return Response.json({ message: 'Hello!' })
}
```

### CLI Commands
```bash
wrangler pages dev ./              # Local dev
wrangler pages deploy ./ --project-name=my-site  # Deploy
```

---

## Clerk Patterns (VERIFY CURRENT API BEFORE USE)

**Hono (@hono/clerk-auth):**
```typescript
import { Hono } from 'hono'
import { clerkMiddleware, getAuth } from '@hono/clerk-auth'

const app = new Hono<{ Bindings: Env }>()
app.use('*', clerkMiddleware())
app.get('/api/*', (c) => {
  const auth = getAuth(c)
  if (!auth?.userId) return c.json({ error: 'Unauthorized' }, 401)
  return c.json({ userId: auth.userId })
})
export default app
```

**Raw Workers (@clerk/backend):**
```typescript
import { createClerkClient } from '@clerk/backend'

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // BOTH keys required!
    const clerkClient = createClerkClient({
      secretKey: env.CLERK_SECRET_KEY,
      publishableKey: env.CLERK_PUBLISHABLE_KEY,
    })
    
    const { isAuthenticated, toAuth } = await clerkClient.authenticateRequest(request, {
      authorizedParties: ['https://your-domain.com']
    })
    
    if (!isAuthenticated) {
      return new Response('Unauthorized', { status: 401 })
    }
    
    const auth = toAuth()
    return new Response(JSON.stringify({ userId: auth.userId }))
  }
}
```

---

## Secrets
- `.dev.vars` for local (gitignore!)
- `wrangler secret put KEY` for prod
- **Required for Clerk:** `CLERK_SECRET_KEY` AND `CLERK_PUBLISHABLE_KEY`

---

## Commands Reference

### Wrangler CLI Documentation
Full reference: https://developers.cloudflare.com/workers/wrangler/commands/

```bash
# ============================================================================
# PROJECT SETUP
# Docs: https://developers.cloudflare.com/workers/get-started/guide/
# ============================================================================
npm create cloudflare@latest              # Interactive project creation
npm create cloudflare@latest my-app       # Named project
npm create cloudflare@latest -- --template hono  # With template

# ============================================================================
# LOCAL DEVELOPMENT
# Workers: https://developers.cloudflare.com/workers/wrangler/commands/#dev
# Pages: https://developers.cloudflare.com/pages/functions/local-development/
# ============================================================================
wrangler dev                    # Workers dev server (localhost:8787)
wrangler dev --port 3000        # Custom port
wrangler dev --remote           # Use REAL cloud resources (CAUTION!)

wrangler pages dev ./           # Pages dev server (localhost:8788)
wrangler pages dev ./dist       # Pages with build output dir
wrangler pages dev ./ --d1=DB   # Pages with D1 binding

# ============================================================================
# DEPLOYMENT
# Docs: https://developers.cloudflare.com/workers/wrangler/commands/#deploy
# ============================================================================
wrangler deploy                 # Deploy Worker to production
wrangler deploy --env staging   # Deploy to environment

wrangler pages deploy ./dist --project-name=my-site  # Deploy Pages
wrangler pages project create my-site                 # Create Pages project first

# ============================================================================
# D1 DATABASE (SQLite)
# Docs: https://developers.cloudflare.com/d1/wrangler-commands/
# ============================================================================
wrangler d1 create <db-name>    # Create DB (returns database_id for config)
wrangler d1 list                # List all databases

# Execute SQL (--local for dev, --remote for production)
wrangler d1 execute <db> --local --file=./schema.sql   # Local
wrangler d1 execute <db> --remote --file=./schema.sql  # PRODUCTION (careful!)
wrangler d1 execute <db> --local --command="SELECT * FROM users"

# Migrations (recommended for schema changes)
# Docs: https://developers.cloudflare.com/d1/reference/migrations/
wrangler d1 migrations create <db> <name>   # Create migration file
wrangler d1 migrations apply <db> --local   # Apply locally
wrangler d1 migrations apply <db> --remote  # Apply to production

# ============================================================================
# KV STORAGE (Key-Value, eventually consistent)
# Docs: https://developers.cloudflare.com/kv/reference/kv-commands/
# ============================================================================
wrangler kv namespace create <name>         # Create namespace (returns id)
wrangler kv namespace create <name> --preview  # Create preview namespace
wrangler kv namespace list                  # List namespaces

wrangler kv key put --binding=KV "key" "value" --local  # Put (local)
wrangler kv key put --binding=KV "key" "value"          # Put (production)
wrangler kv key get --binding=KV "key"                  # Get value
wrangler kv key list --binding=KV                       # List keys

# ============================================================================
# R2 OBJECT STORAGE (S3-compatible)
# Docs: https://developers.cloudflare.com/r2/api/wrangler/
# ============================================================================
wrangler r2 bucket create <name>            # Create bucket
wrangler r2 bucket list                     # List buckets
wrangler r2 object put <bucket>/<key> --file=./file.txt  # Upload
wrangler r2 object get <bucket>/<key>       # Download

# ============================================================================
# SECRETS (Encrypted env vars for production)
# Docs: https://developers.cloudflare.com/workers/wrangler/commands/#secret
# ============================================================================
wrangler secret put <NAME>                  # Add secret (prompts for value)
echo "value" | wrangler secret put <NAME>   # Add from stdin (CI/CD)
wrangler secret list                        # List secret names
wrangler secret delete <NAME>               # Delete secret

# ============================================================================
# TYPESCRIPT & DEBUGGING
# ============================================================================
wrangler types                  # Generate Env types from config
                                # Docs: https://developers.cloudflare.com/workers/wrangler/commands/#types

wrangler tail                   # Stream production logs
wrangler tail --status=error    # Filter by status
wrangler tail --format=json     # JSON output
                                # Docs: https://developers.cloudflare.com/workers/wrangler/commands/#tail

# ============================================================================
# AUTH
# ============================================================================
wrangler login                  # Login to Cloudflare (opens browser)
wrangler whoami                 # Check current user
wrangler logout                 # Logout
```

### Key Command Patterns for AI

```bash
# Pattern: Local vs Remote operations
# --local  = Uses local simulation (safe for development)
# --remote = Uses PRODUCTION resources (be careful!)

# Pattern: Bindings in Pages dev
# Pass bindings via CLI when no wrangler.toml:
wrangler pages dev ./ --d1=DB --kv=CACHE --r2=STORAGE

# Pattern: Environment-specific operations
wrangler deploy --env staging
wrangler secret put API_KEY --env staging
wrangler tail --env staging

# Pattern: Get resource IDs for wrangler config
wrangler d1 create my-db      # Output includes database_id
wrangler kv namespace create CACHE  # Output includes namespace id
# Add these IDs to wrangler.toml/wrangler.jsonc bindings
```

---

## Key Constraints
| Limit | Value |
|-------|-------|
| D1 rows/query | 1000 (use pagination) |
| KV consistency | Eventually consistent |
| Workers CPU | 30s paid / 10ms free |
| R2 object size | 5TB max |

**Gotchas:**
- Clone request before reading body twice
- Use `nodejs_compat` flag for Node APIs
- Clerk `@clerk/backend` needs BOTH secretKey AND publishableKey
- D1 transactions: `await db.batch([stmt1, stmt2])`
- Set `authorizedParties` in Clerk to prevent CSRF

---

## Notes
<!-- Project-specific notes -->