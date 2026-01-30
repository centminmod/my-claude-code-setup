# CLAUDE.md - Cloudflare Platform Project Template

## Project Overview
- **Project Name**: [PROJECT_NAME]
- **Description**: [BRIEF_DESCRIPTION]
- **Auth Provider**: Clerk

---

## CRITICAL: Documentation Verification Rules

### Before Writing ANY Code
1. **Determine project language/framework** by inspecting project files
2. **Lookup current documentation** for the detected stack before implementing
3. **Never assume** API signatures, binding syntax, or SDK methods

### MCP Tools (if available)
- **context7 MCP**: Query for latest documentation
- **Cloudflare MCP**: List/create resources, search docs, verify resource IDs

### Documentation URLs (for web fetch if no MCP)
Fetch and read these URLs to verify current APIs:

**Cloudflare Platform:**
| Service | URL |
|---------|-----|
| Workers | https://developers.cloudflare.com/workers/ |
| D1 (SQLite) | https://developers.cloudflare.com/d1/ |
| D1 Get Started | https://developers.cloudflare.com/d1/get-started/ |
| KV | https://developers.cloudflare.com/kv/ |
| R2 (Objects) | https://developers.cloudflare.com/r2/ |
| Durable Objects | https://developers.cloudflare.com/durable-objects/ |
| Queues | https://developers.cloudflare.com/queues/ |
| Workers AI | https://developers.cloudflare.com/workers-ai/ |
| Hyperdrive | https://developers.cloudflare.com/hyperdrive/ |
| Workflows | https://developers.cloudflare.com/workflows/ |
| Pages | https://developers.cloudflare.com/pages/ |
| Pages Git Integration | https://developers.cloudflare.com/pages/get-started/git-integration/ |
| Pages Functions | https://developers.cloudflare.com/pages/functions/ |
| Pages Functions Config | https://developers.cloudflare.com/pages/functions/wrangler-configuration/ |
| Wrangler Config | https://developers.cloudflare.com/workers/wrangler/configuration/ |
| Sandbox SDK | https://developers.cloudflare.com/sandbox/ |
| Sandbox Get Started | https://developers.cloudflare.com/sandbox/get-started/ |
| Containers | https://developers.cloudflare.com/containers/ |

**Clerk Authentication:**
| Resource | URL |
|----------|-----|
| Backend SDK Overview | https://clerk.com/docs/reference/backend/overview |
| JS Backend SDK Quickstart | https://clerk.com/docs/js-backend/getting-started/quickstart |
| authenticateRequest() Reference | https://clerk.com/docs/reference/backend/authenticate-request |
| Express SDK | https://clerk.com/docs/reference/express/overview |
| Next.js SDK | https://clerk.com/docs/reference/nextjs/overview |
| Hono Middleware (Community) | https://github.com/honojs/middleware/tree/main/packages/clerk-auth |

**Framework Deployment Guides:**
| Framework | URL |
|-----------|-----|
| Hono on Workers | https://hono.dev/docs/getting-started/cloudflare-workers |
| Next.js on Pages | https://developers.cloudflare.com/pages/framework-guides/nextjs/ |
| Remix on Pages | https://developers.cloudflare.com/pages/framework-guides/deploy-a-remix-site/ |
| Astro on Pages | https://developers.cloudflare.com/pages/framework-guides/deploy-an-astro-site/ |
| SvelteKit on Pages | https://developers.cloudflare.com/pages/framework-guides/deploy-a-svelte-kit-site/ |

**ORM/Database:**
| Tool | URL |
|------|-----|
| Drizzle + D1 | https://orm.drizzle.team/docs/get-started/d1-new |

---

## Project Detection & Setup

### Step 1: Detect Existing Project Type
Inspect project files to determine language/framework:

```
File Found                -> Stack              -> Action
-----------------------------------------------------------------
package.json              -> Node.js/TypeScript -> Check dependencies for framework
  - "hono"                -> Hono               -> Fetch Hono + CF Workers docs
  - "next"                -> Next.js            -> Fetch Next.js + CF Pages docs  
  - "@remix-run/*"        -> Remix              -> Fetch Remix + CF Pages docs
  - "astro"               -> Astro              -> Fetch Astro + CF Pages docs
  - No framework          -> Raw Worker         -> Fetch Workers docs only

requirements.txt          -> Python Workers     -> Add compatibility_flags: ["python_workers"]
pyproject.toml            -> Python Workers     -> Add compatibility_flags: ["python_workers"]
go.mod                    -> Go (WASM)          -> Fetch Go Workers docs
Cargo.toml                -> Rust (WASM)        -> Fetch Rust Workers docs
wrangler.toml/.jsonc      -> Existing config    -> Follow existing patterns

index.html (no package.json) -> Static HTML     -> Use Pages Git Integration (no build)
*.html files only         -> Static HTML        -> Use Pages Git Integration (no build)
```

### Step 2: New Project Setup (if no manifest files)
```bash
# Create new Workers project
npm create cloudflare@latest -- my-app

# Or with specific template
npm create cloudflare@latest -- my-app --template hono
```

### Step 3: Install Dependencies (after detection)
```bash
# Core (always needed for local dev)
npm install wrangler --save-dev

# Hono (if using)
npm install hono

# Clerk (choose based on framework)
npm install @clerk/backend                    # Raw Workers (also needs publishableKey!)
npm install @hono/clerk-auth @clerk/backend   # Hono (both packages required)
npm install @clerk/nextjs                     # Next.js
npm install @clerk/express                    # Express

# Drizzle ORM (if using D1)
npm install drizzle-orm
npm install drizzle-kit --save-dev
```

---

## Wrangler Configuration

### Config File (wrangler.jsonc preferred)
```jsonc
{
  "$schema": "./node_modules/wrangler/config-schema.json",
  "name": "project-name",
  "main": "src/index.ts",
  "compatibility_date": "2024-12-01",
  "compatibility_flags": ["nodejs_compat"]
}
```

### Binding Configurations

**D1 Database:**
```jsonc
"d1_databases": [
  { "binding": "DB", "database_name": "my-db", "database_id": "UUID_HERE" }
]
```

**KV Namespace:**
```jsonc
"kv_namespaces": [
  { "binding": "KV", "id": "NAMESPACE_ID", "preview_id": "PREVIEW_ID" }
]
```

**R2 Bucket:**
```jsonc
"r2_buckets": [
  { "binding": "BUCKET", "bucket_name": "my-bucket" }
]
```

**Durable Objects:**
```jsonc
"durable_objects": {
  "bindings": [{ "name": "MY_DO", "class_name": "MyDurableObject" }]
},
"migrations": [{ "tag": "v1", "new_classes": ["MyDurableObject"] }]
```

**Queues:**
```jsonc
"queues": {
  "producers": [{ "binding": "QUEUE", "queue": "my-queue" }],
  "consumers": [{ "queue": "my-queue", "max_batch_size": 10 }]
}
```

**Workers AI:**
```jsonc
"ai": { "binding": "AI" }
```

**Hyperdrive (external Postgres):**
```jsonc
"hyperdrive": [
  { "binding": "HYPERDRIVE", "id": "HYPERDRIVE_ID" }
]
```

**Static Assets:**
```jsonc
"assets": { "directory": "./public" }
```

**Sandbox SDK (Containers):**
```jsonc
"containers": [
  { "class_name": "Sandbox", "image": "./Dockerfile", "instance_type": "lite", "max_instances": 5 }
],
"durable_objects": {
  "bindings": [{ "class_name": "Sandbox", "name": "Sandbox" }]
},
"migrations": [{ "tag": "v1", "new_sqlite_classes": ["Sandbox"] }]
```

---

## Cloudflare Pages: Static HTML via GitHub

For pure static HTML sites deployed via GitHub integration (no build step required).

### Documentation
| Resource | URL |
|----------|-----|
| Pages Get Started | https://developers.cloudflare.com/pages/get-started/git-integration/ |
| Pages Functions | https://developers.cloudflare.com/pages/functions/ |
| Pages Direct Upload | https://developers.cloudflare.com/pages/get-started/direct-upload/ |

### Setup via Cloudflare Dashboard (Recommended)
1. Go to **Cloudflare Dashboard > Workers & Pages > Create > Pages > Connect to Git**
2. Select your GitHub repository
3. Configure build settings:
   - **Build command**: *(leave empty for static HTML)*
   - **Build output directory**: `/` or your HTML folder (e.g., `/public`)
4. Deploy

### Repository Structure (Static HTML)
```
/
├── index.html            # Homepage
├── about.html            # Other pages
├── css/
│   └── style.css
├── js/
│   └── app.js
├── images/
│   └── logo.png
└── _headers              # Optional: custom headers
```

### Optional: `_headers` File (for caching, security)
```
/*
  X-Frame-Options: DENY
  X-Content-Type-Options: nosniff

/css/*
  Cache-Control: public, max-age=31536000

/images/*
  Cache-Control: public, max-age=31536000
```

### Optional: `_redirects` File
```
/old-page  /new-page  301
/blog/*    /articles/:splat  302
```

### Adding API Routes (Pages Functions)
To add server-side API routes to a static site, create a `functions/` directory:

```
/
├── index.html
├── functions/
│   ├── api/
│   │   └── hello.ts      # Accessible at /api/hello
│   └── _middleware.ts    # Optional: runs on all routes
└── ...
```

**Example `functions/api/hello.ts`:**
```typescript
// VERIFY at: https://developers.cloudflare.com/pages/functions/
// PagesFunction type is globally available in Pages Functions

export const onRequest: PagesFunction = async (context) => {
  return Response.json({ message: 'Hello from Pages Function!' })
}
```

**Example `functions/api/hello.ts` with D1:**
```typescript
// Define Env interface for typed bindings
interface Env {
  DB: D1Database
}

export const onRequest: PagesFunction<Env> = async (context) => {
  const result = await context.env.DB.prepare('SELECT * FROM users LIMIT 10').all()
  return Response.json(result)
}
```

### Bindings for Pages Functions
Create `wrangler.toml` in project root for Pages Function bindings:
```toml
name = "my-static-site"
pages_build_output_dir = "./"
compatibility_date = "2024-12-01"

[[d1_databases]]
binding = "DB"
database_name = "my-db"
database_id = "UUID_HERE"

[[kv_namespaces]]
binding = "KV"
id = "NAMESPACE_ID"
```

### CLI Deployment (Alternative to GitHub)
```bash
# Install wrangler
npm install wrangler --save-dev

# Deploy directly (no GitHub needed)
wrangler pages deploy ./public --project-name=my-site

# Or create project first
wrangler pages project create my-site
wrangler pages deploy ./ --project-name=my-site
```

### Local Development
```bash
# Serve static files + Pages Functions locally
wrangler pages dev ./

# With specific port
wrangler pages dev ./ --port 3000

# With bindings (D1, KV, etc.)
wrangler pages dev ./ --d1=DB
```

### Custom Domain
1. Dashboard: **Pages project > Custom domains > Set up a custom domain**
2. Add CNAME record pointing to `<project>.pages.dev`
3. SSL provisioned automatically

---

## Sandbox SDK (Secure Code Execution)

Run untrusted code in isolated Linux containers. Each sandbox = Durable Object + Container.

### Documentation
| Resource | URL |
|----------|-----|
| Overview | https://developers.cloudflare.com/sandbox/ |
| Get Started | https://developers.cloudflare.com/sandbox/get-started/ |
| API Reference | https://developers.cloudflare.com/sandbox/api/ |
| GitHub | https://github.com/cloudflare/sandbox-sdk |

### Use Cases
- **AI Agents**: Execute LLM-generated code safely
- **CI/CD**: Automated testing pipelines
- **Cloud REPLs**: Interactive development environments
- **Data Analysis**: Run scripts with rich outputs (charts, tables)

### Instance Types
| Type | vCPU | Memory |
|------|------|--------|
| lite | 0.5 | 256 MB |
| standard | 1 | 512 MB |
| heavy | 2 | 1 GB |

### Project Setup
```bash
npm create cloudflare@latest -- my-sandbox --template=cloudflare/sandbox-sdk/examples/minimal
```

### Wrangler Configuration
```jsonc
{
  "name": "my-sandbox-app",
  "main": "src/index.ts",
  "compatibility_date": "2025-01-01",
  "containers": [{
    "class_name": "Sandbox",
    "image": "./Dockerfile",
    "instance_type": "lite",
    "max_instances": 5
  }],
  "durable_objects": {
    "bindings": [{ "class_name": "Sandbox", "name": "Sandbox" }]
  },
  "migrations": [{ "tag": "v1", "new_sqlite_classes": ["Sandbox"] }]
}
```

### Dockerfile
```dockerfile
FROM docker.io/cloudflare/sandbox:latest
RUN pip3 install --no-cache-dir pandas numpy matplotlib
EXPOSE 8080 3000  # Required for wrangler dev
```

### CRITICAL: Basic Usage Pattern
```typescript
import { getSandbox, proxyToSandbox, type Sandbox } from '@cloudflare/sandbox';
export { Sandbox } from '@cloudflare/sandbox';  // MUST re-export

type Env = { Sandbox: DurableObjectNamespace<Sandbox>; };

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // CRITICAL: proxyToSandbox MUST be called first for preview URLs
    const proxyResponse = await proxyToSandbox(request, env);
    if (proxyResponse) return proxyResponse;

    const sandbox = getSandbox(env.Sandbox, 'my-sandbox', {
      normalizeId: true,    // Required for preview URLs (lowercases ID)
      sleepAfter: '10m',    // Auto-sleep after inactivity
    });

    // Execute commands
    const result = await sandbox.exec('python3 -c "print(2 + 2)"');
    // result: { stdout, stderr, exitCode, success, duration }

    return Response.json({ output: result.stdout });
  }
};
```

### Command Execution API
```typescript
// Basic execution
const result = await sandbox.exec('python3 script.py', {
  cwd: '/workspace/project',
  env: { API_KEY: 'secret' },
  stream: true,
  onOutput: (stream, data) => console.log(data)
});

// Background processes
const process = await sandbox.startProcess('python3 -m http.server 8080', {
  processId: 'web-server',
  cwd: '/workspace/public'
});
await process.waitForPort(8080);  // Wait for readiness
await process.waitForLog(/Server running/);  // Wait for log pattern
const logs = await sandbox.getProcessLogs('web-server');
await sandbox.stopProcess('web-server');
```

### File Operations API
```typescript
// Write/read (use /workspace for persistent files)
await sandbox.writeFile('/workspace/file.txt', 'content');
await sandbox.writeFile('/workspace/img.png', base64Data, { encoding: 'base64' });
const { content } = await sandbox.readFile('/workspace/file.txt');

// Directory operations
await sandbox.mkdir('/workspace/dir', { recursive: true });
const files = await sandbox.listFiles('/workspace');
await sandbox.pathExists('/workspace/file.txt');

// Delete
await sandbox.deleteFile('/workspace/temp.txt');
await sandbox.deleteFile('/workspace/dir', { recursive: true });
```

### Sessions (Isolated Contexts)
```typescript
// Each session has own shell state, env vars, cwd
const session = await sandbox.createSession({
  id: 'user-123',
  cwd: '/workspace/user123',
  env: { USER_ID: '123' }
});

await session.exec('echo $USER_ID');
await session.writeFile('config.txt', 'data');
await sandbox.deleteSession('user-123');
```

### Code Interpreter (Rich Outputs)
```typescript
// Create context with variables
const ctx = await sandbox.createCodeContext({
  language: 'python',
  variables: { data: [1, 2, 3, 4, 5] }
});

// Execute code (state persists across runs)
const result = await ctx.runCode(`
import matplotlib.pyplot as plt
plt.plot(data, [x**2 for x in data])
plt.savefig('plot.png')
`);
// result.outputs: [{ type: 'text'|'image'|'html', content }]
```

### Port Exposure & WebSockets
```typescript
// Expose service (requires custom domain, not .workers.dev)
const { url } = await sandbox.exposePort(8080, {
  name: 'web-app',
  hostname: request.hostname
});

// WebSocket proxy
if (request.headers.get('Upgrade') === 'websocket') {
  return await sandbox.wsConnect(request, 8080);
}
```

### Bucket Mounting (Production Only)
```typescript
// Mount R2 bucket (NOT available in wrangler dev)
await sandbox.mountBucket(env.DATA_BUCKET, '/data', { readOnly: false });
await sandbox.exec('ls /data');
await sandbox.unmountBucket('/data');
```

### Lifecycle Management
```typescript
// With keepAlive: true, MUST call destroy()
const sandbox = getSandbox(env.Sandbox, 'temp', { keepAlive: true });
try {
  const result = await sandbox.exec('python script.py');
  return result.stdout;
} finally {
  await sandbox.destroy();  // REQUIRED to free resources
}
```

### Error Handling
```typescript
// Retry on CONTAINER_NOT_READY (cold start)
async function execWithRetry(sandbox, cmd) {
  for (let i = 0; i < 3; i++) {
    try {
      return await sandbox.exec(cmd);
    } catch (e) {
      if (e.code === 'CONTAINER_NOT_READY') {
        await new Promise(r => setTimeout(r, 2000));
        continue;
      }
      throw e;
    }
  }
}
```

### CLI Commands
```bash
wrangler dev                  # Local dev (requires Docker)
wrangler deploy               # Deploy to production
wrangler containers list      # Check container status
wrangler tail                 # Monitor logs
```

### Gotchas
1. **`proxyToSandbox()` MUST be called first** in fetch handler
2. **Docker required** for local development (`docker info` to verify)
3. **First deploy**: 2-3 minutes for container build
4. **Cold start**: 2-3s when waking from sleep
5. **Use `/workspace`** for persistent files (other paths are ephemeral)
6. **Preview URLs require**:
   - Custom domain (not `.workers.dev`)
   - Wildcard DNS (`*.domain.com → worker.domain.com`)
   - `normalizeId: true` in getSandbox
7. **`keepAlive: true`** requires `destroy()` call
8. **Bucket mounting** only works in production (FUSE not in dev)
9. **Code contexts are ephemeral** - recreate after container sleep/wake

---

## TypeScript Environment Types

### Generate Types
```bash
wrangler types
```

Creates `worker-configuration.d.ts`. Define your Env interface:

```typescript
// src/types.ts
interface Env {
  DB: D1Database
  KV: KVNamespace
  BUCKET: R2Bucket
  CLERK_SECRET_KEY: string
  CLERK_PUBLISHABLE_KEY: string
  // Add other bindings as needed
}
```

---

## Clerk Authentication

### Required Secrets
Local (`.dev.vars` - NEVER commit):
```
CLERK_SECRET_KEY=sk_test_xxx
CLERK_PUBLISHABLE_KEY=pk_test_xxx
```

Production:
```bash
wrangler secret put CLERK_SECRET_KEY
wrangler secret put CLERK_PUBLISHABLE_KEY
```

### Pattern: Hono + @hono/clerk-auth (Community SDK)
```typescript
// VERIFY at: https://github.com/honojs/middleware/tree/main/packages/clerk-auth
import { Hono } from 'hono'
import { clerkMiddleware, getAuth } from '@hono/clerk-auth'

const app = new Hono<{ Bindings: Env }>()

app.use('*', clerkMiddleware())

app.get('/protected', (c) => {
  const auth = getAuth(c)
  if (!auth?.userId) {
    return c.json({ error: 'Unauthorized' }, 401)
  }
  return c.json({ userId: auth.userId })
})

export default app
```

### Pattern: Raw Workers + @clerk/backend
```typescript
// VERIFY at: https://clerk.com/docs/reference/backend/authenticate-request
// IMPORTANT: Both secretKey AND publishableKey are REQUIRED
import { createClerkClient } from '@clerk/backend'

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const clerkClient = createClerkClient({
      secretKey: env.CLERK_SECRET_KEY,
      publishableKey: env.CLERK_PUBLISHABLE_KEY,  // REQUIRED!
    })
    
    // authenticateRequest returns { isAuthenticated, toAuth(), ... }
    const { isAuthenticated, toAuth } = await clerkClient.authenticateRequest(request, {
      authorizedParties: ['https://your-domain.com']  // Recommended for security
    })
    
    if (!isAuthenticated) {
      return new Response('Unauthorized', { status: 401 })
    }
    
    // Get full Auth object if needed
    const auth = toAuth()
    // auth.userId, auth.sessionId, auth.orgId available
    
    return new Response(JSON.stringify({ userId: auth.userId }), {
      headers: { 'Content-Type': 'application/json' }
    })
  }
}
```

### Testing & Automation

Clerk provides testing features for automated/E2E testing.

**Documentation:** https://clerk.com/docs/testing/overview

**Test Credentials (bypass verification):**

| Type | Pattern | Verification Code |
|------|---------|-------------------|
| Email | `+clerk_test` subaddress | `424242` |
| Phone | `+1 (XXX) 555-0100` to `0199` | `424242` |

Example: `test+clerk_test@example.com` + code `424242`

**Testing Token (bot detection bypass):**
```bash
# Get token via Backend API
curl -X GET https://api.clerk.dev/v1/testing_tokens \
  -H "Authorization: Bearer $CLERK_SECRET_KEY"
```

Add to URL: `?__clerk_testing_token=[token]`

**Workers/Pages Integration:**
```typescript
// Testing tokens are automatically handled by Clerk SDK
// Just include the token in the URL query parameter
// The SDK will recognize and process it for authentication bypass
```

---

## Development Commands

### Wrangler CLI Reference
Documentation: https://developers.cloudflare.com/workers/wrangler/commands/

```bash
# ============================================================================
# LOCAL DEVELOPMENT
# Docs: https://developers.cloudflare.com/workers/wrangler/commands/#dev
# ============================================================================

# Start local development server for Workers
# - Runs on http://localhost:8787 by default
# - Hot reloads on file changes
# - Uses .dev.vars for local secrets
# - Simulates Cloudflare runtime locally (miniflare)
wrangler dev

# Start with specific port
wrangler dev --port 3000

# Start with remote resources (connects to real D1/KV/R2 in Cloudflare)
# WARNING: This uses PRODUCTION data! Use with caution.
wrangler dev --remote

# Start for Pages project (different from Workers)
# Docs: https://developers.cloudflare.com/pages/functions/local-development/
# - Runs on http://localhost:8788 by default
# - Serves static files + Pages Functions
wrangler pages dev ./

# Pages dev with specific output directory
wrangler pages dev ./dist

# Pages dev with bindings passed via CLI (alternative to wrangler.toml)
wrangler pages dev ./ --d1=DB --kv=KV --r2=BUCKET

# ============================================================================
# DEPLOYMENT
# Docs: https://developers.cloudflare.com/workers/wrangler/commands/#deploy
# ============================================================================

# Deploy Worker to Cloudflare (production)
# - Reads wrangler.toml/wrangler.jsonc for configuration
# - Uploads code and applies bindings
# - Returns deployment URL
wrangler deploy

# Deploy specific script (overrides config)
wrangler deploy src/index.ts

# Deploy to specific environment (if using wrangler environments)
# Docs: https://developers.cloudflare.com/workers/wrangler/environments/
wrangler deploy --env staging

# Deploy Pages project directly (without Git integration)
# Docs: https://developers.cloudflare.com/workers/wrangler/commands/#deploy-1
wrangler pages deploy ./dist --project-name=my-site

# Create Pages project first (required for first deploy)
wrangler pages project create my-site

# ============================================================================
# D1 DATABASE OPERATIONS
# Docs: https://developers.cloudflare.com/d1/wrangler-commands/
# D1 is Cloudflare's serverless SQLite database
# ============================================================================

# Create a new D1 database
# Returns database_id to add to wrangler config
wrangler d1 create <database-name>

# List all D1 databases in account
wrangler d1 list

# Get info about specific database
wrangler d1 info <database-name>

# Execute SQL file against LOCAL database (for development)
# --local flag uses local SQLite, not production
wrangler d1 execute <database-name> --local --file=./schema.sql

# Execute SQL file against REMOTE/PRODUCTION database
# WARNING: This modifies production data!
wrangler d1 execute <database-name> --remote --file=./schema.sql

# Execute inline SQL locally
wrangler d1 execute <database-name> --local --command="SELECT * FROM users"

# Execute inline SQL remotely
wrangler d1 execute <database-name> --remote --command="SELECT * FROM users"

# D1 Migrations (recommended for schema changes)
# Docs: https://developers.cloudflare.com/d1/reference/migrations/

# Create a new migration file (creates migrations/ directory)
wrangler d1 migrations create <database-name> <migration-name>
# Creates: migrations/0001_<migration-name>.sql

# Apply migrations to LOCAL database
wrangler d1 migrations apply <database-name> --local

# Apply migrations to REMOTE/PRODUCTION database
wrangler d1 migrations apply <database-name> --remote

# List migration status
wrangler d1 migrations list <database-name>

# ============================================================================
# KV NAMESPACE OPERATIONS
# Docs: https://developers.cloudflare.com/kv/reference/kv-commands/
# KV is Cloudflare's key-value storage (eventually consistent)
# ============================================================================

# Create a new KV namespace
# Returns namespace ID to add to wrangler config
wrangler kv namespace create <namespace-name>

# Create preview namespace (for wrangler dev)
wrangler kv namespace create <namespace-name> --preview

# List all KV namespaces
wrangler kv namespace list

# Delete a KV namespace
wrangler kv namespace delete --namespace-id=<id>

# Put a key-value pair (local development)
wrangler kv key put --binding=KV "my-key" "my-value" --local

# Put a key-value pair (production)
wrangler kv key put --binding=KV "my-key" "my-value"

# Get a value by key
wrangler kv key get --binding=KV "my-key"

# Delete a key
wrangler kv key delete --binding=KV "my-key"

# List keys in namespace
wrangler kv key list --binding=KV

# Bulk upload from JSON file
# File format: [{"key": "k1", "value": "v1"}, ...]
wrangler kv bulk put --binding=KV ./data.json

# ============================================================================
# R2 OBJECT STORAGE OPERATIONS
# Docs: https://developers.cloudflare.com/r2/api/wrangler/
# R2 is Cloudflare's S3-compatible object storage (zero egress fees)
# ============================================================================

# Create a new R2 bucket
wrangler r2 bucket create <bucket-name>

# List all R2 buckets
wrangler r2 bucket list

# Delete an R2 bucket (must be empty)
wrangler r2 bucket delete <bucket-name>

# Upload object to bucket
wrangler r2 object put <bucket-name>/<key> --file=./myfile.txt

# Download object from bucket
wrangler r2 object get <bucket-name>/<key>

# Delete object from bucket
wrangler r2 object delete <bucket-name>/<key>

# ============================================================================
# SECRETS MANAGEMENT
# Docs: https://developers.cloudflare.com/workers/wrangler/commands/#secret
# Secrets are encrypted environment variables for production
# ============================================================================

# Add/update a secret (interactive prompt for value)
# Secret is encrypted and stored securely
wrangler secret put <SECRET_NAME>

# Add secret with value from stdin (useful for CI/CD)
echo "secret-value" | wrangler secret put <SECRET_NAME>

# List all secrets (shows names only, not values)
wrangler secret list

# Delete a secret
wrangler secret delete <SECRET_NAME>

# Add secret to specific environment
wrangler secret put <SECRET_NAME> --env staging

# ============================================================================
# TYPESCRIPT TYPES GENERATION
# Docs: https://developers.cloudflare.com/workers/wrangler/commands/#types
# Generates TypeScript types for your bindings
# ============================================================================

# Generate types from wrangler config
# Creates worker-configuration.d.ts with Env interface
wrangler types

# Output to specific file
wrangler types --env-interface CloudflareBindings

# ============================================================================
# LOGS AND DEBUGGING
# Docs: https://developers.cloudflare.com/workers/wrangler/commands/#tail
# ============================================================================

# Stream real-time logs from deployed Worker
# Shows console.log output, errors, and request info
wrangler tail

# Filter logs by status
wrangler tail --status=error

# Filter by HTTP method
wrangler tail --method=POST

# Filter by search string
wrangler tail --search="error"

# Filter by IP address
wrangler tail --ip=1.2.3.4

# Tail specific environment
wrangler tail --env staging

# Output as JSON (useful for piping to other tools)
wrangler tail --format=json

# ============================================================================
# QUEUES OPERATIONS
# Docs: https://developers.cloudflare.com/queues/configuration/wrangler-commands/
# ============================================================================

# Create a new queue
wrangler queues create <queue-name>

# List all queues
wrangler queues list

# Delete a queue
wrangler queues delete <queue-name>

# ============================================================================
# DURABLE OBJECTS
# Docs: https://developers.cloudflare.com/durable-objects/
# Note: Durable Objects are defined in code and deployed with wrangler deploy
# Migrations are specified in wrangler config
# ============================================================================

# No specific CLI commands - DO is configured in wrangler.toml:
# "durable_objects": { "bindings": [{ "name": "MY_DO", "class_name": "MyClass" }] }
# "migrations": [{ "tag": "v1", "new_classes": ["MyClass"] }]

# ============================================================================
# HYPERDRIVE (External Postgres Connection Pooling)
# Docs: https://developers.cloudflare.com/hyperdrive/
# ============================================================================

# Create Hyperdrive config (connects to external Postgres)
wrangler hyperdrive create <config-name> --connection-string="postgres://user:pass@host:5432/db"

# List Hyperdrive configs
wrangler hyperdrive list

# Get Hyperdrive config details
wrangler hyperdrive get <config-id>

# Delete Hyperdrive config
wrangler hyperdrive delete <config-id>

# ============================================================================
# WORKERS AI
# Docs: https://developers.cloudflare.com/workers-ai/
# Note: AI binding is configured in wrangler.toml: "ai": { "binding": "AI" }
# No specific CLI commands - models are accessed via env.AI.run()
# ============================================================================

# ============================================================================
# PROJECT INITIALIZATION
# Docs: https://developers.cloudflare.com/workers/get-started/guide/
# ============================================================================

# Create new project interactively
npm create cloudflare@latest

# Create with specific name
npm create cloudflare@latest my-app

# Create with specific template
npm create cloudflare@latest my-app -- --template hono
npm create cloudflare@latest my-app -- --template worker-typescript

# ============================================================================
# AUTHENTICATION
# Docs: https://developers.cloudflare.com/workers/wrangler/commands/#login
# ============================================================================

# Login to Cloudflare (opens browser)
wrangler login

# Check login status
wrangler whoami

# Logout
wrangler logout
```

---

## Platform Constraints

| Service | Constraint | Notes |
|---------|------------|-------|
| Workers | 30s CPU (paid), 10ms (free) | Use streaming for long operations |
| Workers | 128MB memory | |
| D1 | 1000 rows per query | Use LIMIT/OFFSET pagination |
| D1 | 100KB per row | |
| D1 | Transactions via `db.batch()` | |
| KV | Eventually consistent | Not for real-time coordination |
| KV | 25MB per value | |
| R2 | 5TB per object | S3-compatible API |
| Durable Objects | Single-threaded per instance | Use for coordination, WebSockets |
| Sandbox | lite: 0.5 vCPU, 256MB | standard: 1 vCPU, 512MB | heavy: 2 vCPU, 1GB |
| Sandbox | Cold start: 2-3s | First deploy: 2-3 min |

### Common Gotchas
1. **Clone Request** before reading body twice: `const clone = request.clone()`
2. **nodejs_compat flag** required for most Node.js APIs
3. **Not all Node.js APIs** available even with nodejs_compat (e.g., `async_hooks`)
4. **Clerk @clerk/backend** requires BOTH `secretKey` AND `publishableKey`
5. **D1 batch** for transactions: `await db.batch([stmt1, stmt2])`
6. **authorizedParties** recommended for Clerk to prevent CSRF attacks
7. **Clerk Bot Protection** uses Cloudflare Turnstile - blocks automated browser testing (disable in dev: Clerk Dashboard → Configure → Attack protection)
8. **Sandbox SDK**: `proxyToSandbox()` MUST be called first in fetch handler
9. **Sandbox SDK** requires Docker running locally for `wrangler dev`
10. **Sandbox containers** take 2-3 min on first deploy; use `/workspace` for persistent files
11. **Sandbox preview URLs** require custom domain (not .workers.dev), wildcard DNS, and `normalizeId: true`
12. **Sandbox `keepAlive: true`** requires explicit `destroy()` call to free resources

---

## Pre-Implementation Checklist

Before writing code:
- [ ] Detected project language/framework from manifest files
- [ ] Fetched and read relevant documentation URLs
- [ ] Verified current API signatures (especially Clerk SDK)
- [ ] Created/verified wrangler config with correct binding names
- [ ] Generated TypeScript types with `wrangler types`
- [ ] Set up `.dev.vars` for local secrets (both CLERK keys!)
- [ ] Added `.dev.vars` to `.gitignore`

---

## Project Structure (Reference)

```
/
├── src/
│   ├── index.ts          # Worker entry point
│   ├── routes/           # Route handlers
│   ├── middleware/       # Auth, logging
│   ├── services/         # Business logic
│   ├── db/
│   │   ├── schema.ts     # Drizzle schema
│   │   └── migrations/   # D1 migrations
│   └── types.ts          # Env interface, shared types
├── wrangler.jsonc        # Wrangler configuration
├── drizzle.config.ts     # Drizzle config (if using)
├── .dev.vars             # Local secrets (gitignored!)
├── .gitignore            # Must include .dev.vars
├── package.json
├── tsconfig.json
└── CLAUDE.md             # This file
```

---

## Notes
<!-- Project-specific notes, decisions, context -->