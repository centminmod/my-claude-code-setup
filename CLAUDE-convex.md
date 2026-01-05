# CLAUDE.md - Convex Database Project Template

## Project Overview
- **Project Name**: [PROJECT_NAME]
- **Description**: [BRIEF_DESCRIPTION]
- **Database**: Convex
- **Hosting**: Cloudflare Pages
- **Auth Provider**: Clerk (recommended) / Convex Auth / Custom

---

## CRITICAL: Documentation Verification Rules

### Before Writing ANY Code
1. **Determine project language/framework** by inspecting project files
2. **Lookup current documentation** for the detected stack before implementing
3. **Never assume** API signatures, function syntax, or hook patterns

### MCP Tools (if available)
- **context7 MCP**: Query for latest Convex documentation
- **Cloudflare MCP**: Search Cloudflare Pages deployment docs

### Documentation URLs (for web fetch if no MCP)
Fetch and read these URLs to verify current APIs:

**Convex Platform:**
| Service | URL |
|---------|-----|
| LLM-Optimized Docs | https://docs.convex.dev/llms.txt |
| Quickstart (Next.js App Router) | https://docs.convex.dev/quickstart/nextjs |
| Quickstart (Next.js Pages Router) | https://docs.convex.dev/client/nextjs/pages-router/quickstart |
| Quickstart (React/Vite) | https://docs.convex.dev/quickstart/react |
| Database Schemas | https://docs.convex.dev/database/schemas |
| Reading Data (Queries) | https://docs.convex.dev/database/reading-data |
| Writing Data (Mutations) | https://docs.convex.dev/database/writing-data |
| Functions Overview | https://docs.convex.dev/functions |
| Query Functions | https://docs.convex.dev/functions/query-functions |
| Mutation Functions | https://docs.convex.dev/functions/mutation-functions |
| Actions | https://docs.convex.dev/functions/actions |
| HTTP Actions | https://docs.convex.dev/functions/http-actions |
| Scheduled Functions | https://docs.convex.dev/scheduling/scheduled-functions |
| Authentication Overview | https://docs.convex.dev/auth |
| Clerk Integration | https://docs.convex.dev/auth/clerk |
| Convex Auth | https://docs.convex.dev/auth/convex-auth |
| Custom Auth | https://docs.convex.dev/auth/custom-auth |
| Authorization Patterns | https://docs.convex.dev/auth/authorization |
| Database Indexes | https://docs.convex.dev/database/indexes |
| Pagination | https://docs.convex.dev/database/pagination |
| File Storage | https://docs.convex.dev/file-storage |
| Full-text Search | https://docs.convex.dev/text-search |
| Vector Search | https://docs.convex.dev/vector-search |
| TypeScript | https://docs.convex.dev/typescript |
| Error Handling | https://docs.convex.dev/functions/error-handling |
| Testing | https://docs.convex.dev/production/testing |
| Environment Variables | https://docs.convex.dev/production/environment-variables |
| Production Hosting | https://docs.convex.dev/production/hosting |
| Monitoring | https://docs.convex.dev/production/monitoring |
| Convex CLI | https://docs.convex.dev/cli |

**Clerk Authentication:**
| Resource | URL |
|----------|-----|
| Clerk + Convex | https://docs.convex.dev/auth/clerk |
| Clerk Backend SDK | https://clerk.com/docs/reference/backend/overview |
| Clerk Next.js | https://clerk.com/docs/reference/nextjs/overview |
| Clerk React | https://clerk.com/docs/reference/react/overview |

**Cloudflare Pages Deployment:**
| Resource | URL |
|----------|-----|
| Pages Overview | https://developers.cloudflare.com/pages/ |
| Next.js on Pages | https://developers.cloudflare.com/pages/framework-guides/nextjs/ |
| Build Configuration | https://developers.cloudflare.com/pages/configuration/build-configuration/ |
| Pages Functions | https://developers.cloudflare.com/pages/functions/ |

---

## Project Detection & Setup

### Step 1: Detect Existing Project Type
Inspect project files to determine language/framework:

```
File Found                -> Stack              -> Action
-----------------------------------------------------------------
convex/ directory         -> Existing Convex    -> Check convex.json, schema.ts
package.json + "convex"   -> Convex project     -> Verify setup, check framework
  - "next" + app/         -> Next.js App Router -> Fetch Next.js App Router + Convex docs
  - "next" + pages/       -> Next.js Pages      -> Fetch Next.js Pages Router + Convex docs
  - "react" (Vite)        -> React + Vite       -> Fetch React + Convex docs
  - No framework          -> Add React/Next.js  -> User choice

No convex/ directory      -> New project        -> Run: npx create convex@latest
                                                  OR: npm install convex && npx convex dev
```

### Step 2: New Project Setup (if no convex/)

**Option 1: Create new Next.js project with Convex**
```bash
# VERIFY at: https://docs.convex.dev/quickstart/nextjs
npx create-next-app@latest my-app
cd my-app
npm install convex
npx convex dev
```

**Option 2: Add Convex to existing project**
```bash
# VERIFY at: https://docs.convex.dev/quickstart
npm install convex
npx convex dev  # Initializes convex/ directory and cloud project
```

**Option 3: Use Convex template (interactive)**
```bash
npx create convex@latest  # Interactive setup with framework selection
```

### Step 3: Install Dependencies (after detection)

**Core (always needed):**
```bash
npm install convex  # Convex client and server SDK
```

**Clerk Authentication (recommended):**
```bash
# For Next.js
npm install @clerk/nextjs

# For React
npm install @clerk/clerk-react
```

**Convex Auth (alternative, beta):**
```bash
# Built into Convex, configure via dashboard
# https://docs.convex.dev/auth/convex-auth
```

---

## Convex Configuration

### convex.json (Project Configuration)

**VERIFY at:** https://docs.convex.dev/production/hosting/hosting-and-running

```json
{
  "functions": "convex/",
  "node": {
    "externalPackages": ["sharp", "openai"]  // Node.js packages for actions
  }
}
```

**Technical Explanation:**
- `functions`: Directory containing Convex backend functions (queries, mutations, actions)
- `externalPackages`: Node.js packages that can be imported in actions (not queries/mutations)
- Most configuration is managed in Convex dashboard, not this file

---

### Environment Variables

**.env.local (Local Development):**
```bash
# VERIFY at: https://docs.convex.dev/production/environment-variables

# Frontend environment variable (accessible in browser)
# MUST start with NEXT_PUBLIC_ for Next.js
NEXT_PUBLIC_CONVEX_URL=https://your-deployment.convex.cloud

# For React (Vite):
VITE_CONVEX_URL=https://your-deployment.convex.cloud

# Backend environment variables are SET VIA CLI, not in .env
# Example:
# npx convex env set STRIPE_SECRET_KEY sk_test_...
# npx convex env set OPENAI_API_KEY sk-...
```

**Technical Explanation:**
- **Frontend vars**: Must be prefixed (`NEXT_PUBLIC_` or `VITE_`) - bundled into client code
- **Backend vars**: Set via CLI for security - accessible only in actions via `process.env`
- **Separate deployments**: Dev and prod have separate environment variables
- **Access in code**:
  - Frontend: `process.env.NEXT_PUBLIC_CONVEX_URL` (Next.js) or `import.meta.env.VITE_CONVEX_URL` (Vite)
  - Backend actions: `process.env.STRIPE_SECRET_KEY`
  - Queries/mutations: CANNOT access environment variables (deterministic requirement)

---

### ConvexProvider Setup Patterns

#### Next.js App Router

**VERIFY at:** https://docs.convex.dev/quickstart/nextjs

**app/ConvexClientProvider.tsx:**
```typescript
// ConvexClientProvider MUST be a client component
"use client";

import { ConvexProvider, ConvexReactClient } from "convex/react";
import { ReactNode } from "react";

// Initialize Convex client with deployment URL
const convex = new ConvexReactClient(process.env.NEXT_PUBLIC_CONVEX_URL!);

export function ConvexClientProvider({ children }: { children: ReactNode }) {
  return <ConvexProvider client={convex}>{children}</ConvexProvider>;
}
```

**Technical Explanation:**
- **"use client" required**: React Server Components can't use context providers
- **ConvexReactClient**: Manages WebSocket connection for real-time updates
- **Singleton pattern**: Create client once outside component to prevent reconnections

**app/layout.tsx:**
```typescript
// VERIFY at: https://docs.convex.dev/quickstart/nextjs
import { ConvexClientProvider } from "./ConvexClientProvider";

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <ConvexClientProvider>{children}</ConvexClientProvider>
      </body>
    </html>
  );
}
```

**Server-Side Rendering (SSR) with App Router:**
```typescript
// VERIFY at: https://docs.convex.dev/client/nextjs/app-router
import { preloadQuery } from "convex/nextjs";
import { api } from "@/convex/_generated/api";

export default async function ServerComponent() {
  // Preload query data on server
  const preloadedTasks = await preloadQuery(api.tasks.get);

  return <ClientComponent preloadedTasks={preloadedTasks} />;
}
```

---

#### Next.js Pages Router

**VERIFY at:** https://docs.convex.dev/client/nextjs/pages-router/quickstart

**pages/_app.tsx:**
```typescript
import { ConvexProvider, ConvexReactClient } from "convex/react";
import type { AppProps } from "next/app";

// Initialize Convex client
const convex = new ConvexReactClient(process.env.NEXT_PUBLIC_CONVEX_URL!);

function MyApp({ Component, pageProps }: AppProps) {
  return (
    <ConvexProvider client={convex}>
      <Component {...pageProps} />
    </ConvexProvider>
  );
}

export default MyApp;
```

**Technical Explanation:**
- **_app.tsx pattern**: Wraps all pages with ConvexProvider
- **Client-side only**: Pages Router has limited SSR support for Convex
- **API routes**: Use for server-side Convex operations

**API Route Example (pages/api/tasks.ts):**
```typescript
// VERIFY at: https://docs.convex.dev/client/nextjs/pages-router/server-rendering
import { ConvexHttpClient } from "convex/browser";
import { api } from "@/convex/_generated/api";
import type { NextApiRequest, NextApiResponse } from "next";

const client = new ConvexHttpClient(process.env.NEXT_PUBLIC_CONVEX_URL!);

export default async function handler(req: NextApiRequest, res: NextApiResponse) {
  const tasks = await client.query(api.tasks.get);
  res.status(200).json({ tasks });
}
```

---

#### React (Vite)

**VERIFY at:** https://docs.convex.dev/quickstart/react

**src/main.tsx:**
```typescript
import React from "react";
import ReactDOM from "react-dom/client";
import { ConvexProvider, ConvexReactClient } from "convex/react";
import App from "./App";

// Initialize Convex client with Vite environment variable
const convex = new ConvexReactClient(import.meta.env.VITE_CONVEX_URL);

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ConvexProvider client={convex}>
      <App />
    </ConvexProvider>
  </React.StrictMode>
);
```

**Technical Explanation:**
- **import.meta.env**: Vite's environment variable syntax (NOT process.env)
- **VITE_ prefix**: Required for Vite to include variable in build
- **Client-side only**: Pure React apps are client-rendered

---

## Database Operations

### Schema Definition

**VERIFY at:** https://docs.convex.dev/database/schemas

**convex/schema.ts:**
```typescript
import { defineSchema, defineTable } from "convex/server";
import { v } from "convex/values";

// Schema defines both database structure AND TypeScript types
export default defineSchema({
  tasks: defineTable({
    text: v.string(),
    isCompleted: v.boolean(),
    userId: v.id("users"),  // Reference to users table
    createdAt: v.number(),  // Timestamp (Date.now())
  })
    .index("by_user", ["userId"])           // Index for queries by user
    .index("by_user_status", ["userId", "isCompleted"])  // Compound index
    .searchIndex("search_text", {          // Full-text search
      searchField: "text",
    }),

  users: defineTable({
    name: v.string(),
    email: v.string(),
    clerkId: v.optional(v.string()),  // Optional field for Clerk integration
  })
    .index("by_clerk_id", ["clerkId"]),
});
```

**Technical Explanation:**
- **defineSchema**: Creates schema with type generation
- **defineTable**: Defines table structure with validators
- **Validators**: `v.string()`, `v.number()`, `v.boolean()`, `v.id("tableName")`, `v.optional()`, etc.
- **Indexes**: Required for efficient queries - must use `.withIndex()` in queries
- **Search indexes**: Enable full-text search with `searchFilter()`
- **Type safety**: Schema automatically generates TypeScript types in `convex/_generated/`

---

### Queries (Reading Data)

**VERIFY at:** https://docs.convex.dev/database/reading-data

**convex/tasks.ts:**
```typescript
import { query } from "./_generated/server";
import { v } from "convex/values";

// Get all tasks for a user
export const get = query({
  args: { userId: v.id("users") },
  handler: async (ctx, args) => {
    // Queries MUST use indexes for filtering
    const tasks = await ctx.db
      .query("tasks")
      .withIndex("by_user", (q) => q.eq("userId", args.userId))
      .collect();  // Returns all matching documents

    return tasks;
  },
});

// Get single task by ID
export const getById = query({
  args: { id: v.id("tasks") },
  handler: async (ctx, args) => {
    return await ctx.db.get(args.id);  // Returns task or null
  },
});

// Paginated query
export const getPaginated = query({
  args: { userId: v.id("users"), paginationOpts: v.object({ }) },
  handler: async (ctx, args) => {
    return await ctx.db
      .query("tasks")
      .withIndex("by_user", (q) => q.eq("userId", args.userId))
      .paginate(args.paginationOpts);  // Returns { page, continueCursor, isDone }
  },
});
```

**Query Methods:**
- `.collect()` - Returns all matching documents as array
- `.take(n)` - Returns first n documents
- `.first()` - Returns first document or null
- `.unique()` - Returns single document or throws if multiple/zero
- `.paginate(opts)` - Returns paginated results with cursor

**Technical Explanation:**
- **Deterministic requirement**: Queries MUST return same result for same inputs
- **❌ Cannot use**: `Math.random()`, `Date.now()`, external API calls
- **Automatic caching**: Convex caches query results for performance
- **Real-time reactivity**: `useQuery()` hook automatically re-runs when data changes
- **withIndex() required**: Must explicitly use indexes - Convex doesn't auto-select

---

### Mutations (Writing Data)

**VERIFY at:** https://docs.convex.dev/database/writing-data

**convex/tasks.ts:**
```typescript
import { mutation } from "./_generated/server";
import { v } from "convex/values";

// Insert new task
export const create = mutation({
  args: {
    text: v.string(),
    userId: v.id("users"),
  },
  handler: async (ctx, args) => {
    // db.insert() returns the new document's ID
    const taskId = await ctx.db.insert("tasks", {
      text: args.text,
      userId: args.userId,
      isCompleted: false,
      createdAt: Date.now(),  // OK in mutations (not queries)
    });

    return taskId;  // Return ID of newly created document
  },
});

// Update task (shallow merge)
export const update = mutation({
  args: {
    id: v.id("tasks"),
    text: v.string(),
  },
  handler: async (ctx, args) => {
    // db.patch() performs shallow merge - adds/updates fields
    await ctx.db.patch(args.id, {
      text: args.text,
    });
  },
});

// Replace entire document
export const replace = mutation({
  args: {
    id: v.id("tasks"),
    task: v.object({
      text: v.string(),
      isCompleted: v.boolean(),
      userId: v.id("users"),
      createdAt: v.number(),
    }),
  },
  handler: async (ctx, args) => {
    // db.replace() overwrites entire document
    await ctx.db.replace(args.id, args.task);
  },
});

// Delete task
export const remove = mutation({
  args: { id: v.id("tasks") },
  handler: async (ctx, args) => {
    await ctx.db.delete(args.id);
  },
});
```

**Technical Explanation:**
- **Automatic transactions**: "The entire mutation function is automatically a single transaction"
- **Atomicity**: Multiple db operations in one mutation execute as single atomic unit
- **No BEGIN/COMMIT**: Convex handles transaction management automatically
- **db.patch() vs db.replace()**:
  - `patch()`: Shallow merge - adds new fields, updates existing
  - `replace()`: Complete overwrite - removes fields not in new object

---

### Actions (External API Calls)

**VERIFY at:** https://docs.convex.dev/functions/actions

**convex/actions.ts:**
```typescript
import { action } from "./_generated/server";
import { v } from "convex/values";
import { api } from "./_generated/api";

// Actions can call external APIs (queries/mutations cannot)
export const sendEmail = action({
  args: {
    to: v.string(),
    subject: v.string(),
    body: v.string(),
  },
  handler: async (ctx, args) => {
    // Access environment variables (set via: npx convex env set)
    const apiKey = process.env.SENDGRID_API_KEY;

    // Call external API (Stripe, OpenAI, etc.)
    const response = await fetch("https://api.sendgrid.com/v3/mail/send", {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${apiKey}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        personalizations: [{ to: [{ email: args.to }] }],
        subject: args.subject,
        content: [{ type: "text/plain", value: args.body }],
        from: { email: "noreply@example.com" },
      }),
    });

    if (!response.ok) {
      throw new Error("Failed to send email");
    }

    // Actions can call mutations to save results to database
    await ctx.runMutation(api.emailLogs.create, {
      to: args.to,
      subject: args.subject,
      sentAt: Date.now(),
    });

    return { success: true };
  },
});
```

**Technical Explanation:**
- **Non-deterministic operations**: Actions can use `Date.now()`, `Math.random()`, external APIs
- **No direct database access**: Actions cannot use `ctx.db` directly
- **Can call queries/mutations**: Use `ctx.runQuery()` and `ctx.runMutation()`
- **Environment variables**: Access via `process.env` (set with `npx convex env set`)
- **Use cases**: Stripe payments, OpenAI calls, sending emails, webhooks

---

## Authentication Integration

### Clerk Integration (Recommended)

**VERIFY at:** https://docs.convex.dev/auth/clerk

**Setup Steps:**

1. **Install Clerk:**
```bash
npm install @clerk/nextjs  # For Next.js
# OR
npm install @clerk/clerk-react  # For React
```

2. **Configure Clerk in Convex Dashboard:**
- Navigate to Settings → Authentication
- Add Clerk as provider
- Copy Issuer URL from Clerk dashboard

3. **Add Clerk to Next.js App:**

**app/layout.tsx:**
```typescript
// VERIFY at: https://docs.convex.dev/auth/clerk
import { ClerkProvider } from "@clerk/nextjs";
import { ConvexClientProvider } from "./ConvexClientProvider";

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <ClerkProvider>
      <html lang="en">
        <body>
          <ConvexClientProvider>{children}</ConvexClientProvider>
        </body>
      </html>
    </ClerkProvider>
  );
}
```

**app/ConvexClientProvider.tsx:**
```typescript
"use client";

import { ClerkProvider, useAuth } from "@clerk/nextjs";
import { ConvexProviderWithClerk } from "convex/react-clerk";
import { ConvexReactClient } from "convex/react";

const convex = new ConvexReactClient(process.env.NEXT_PUBLIC_CONVEX_URL!);

export function ConvexClientProvider({ children }: { children: ReactNode }) {
  return (
    <ConvexProviderWithClerk client={convex} useAuth={useAuth}>
      {children}
    </ConvexProviderWithClerk>
  );
}
```

4. **Access Auth in Convex Functions:**

**convex/tasks.ts:**
```typescript
import { query, mutation } from "./_generated/server";
import { v } from "convex/values";

// Get authenticated user's tasks
export const getMy = query({
  handler: async (ctx) => {
    // Get authenticated user (returns null if not logged in)
    const identity = await ctx.auth.getUserIdentity();

    if (!identity) {
      throw new Error("Not authenticated");
    }

    // identity.subject = Clerk user ID
    // identity.email, identity.name, etc.

    const tasks = await ctx.db
      .query("tasks")
      .withIndex("by_user", (q) =>
        q.eq("userId", identity.subject)
      )
      .collect();

    return tasks;
  },
});
```

**Technical Explanation:**
- **JWT verification**: Convex automatically verifies Clerk JWT tokens
- **ctx.auth.getUserIdentity()**: Returns user info or null if not authenticated
- **identity.subject**: Clerk user ID (use as userId in your database)
- **Authorization in code**: Check auth at function level (no RLS framework)

---

## Framework-Specific Patterns

### Next.js App Router Hooks

**VERIFY at:** https://docs.convex.dev/client/nextjs/app-router

**Client Component (app/TaskList.tsx):**
```typescript
"use client";

import { useQuery, useMutation } from "convex/react";
import { api } from "@/convex/_generated/api";

export function TaskList() {
  // useQuery: Real-time reactive query
  const tasks = useQuery(api.tasks.getMy);

  // useMutation: Returns mutation function
  const createTask = useMutation(api.tasks.create);
  const updateTask = useMutation(api.tasks.update);

  // tasks is undefined while loading
  if (tasks === undefined) {
    return <div>Loading...</div>;
  }

  const handleCreate = async () => {
    await createTask({ text: "New task", userId: "user_123" });
  };

  return (
    <div>
      {tasks.map((task) => (
        <div key={task._id}>{task.text}</div>
      ))}
      <button onClick={handleCreate}>Add Task</button>
    </div>
  );
}
```

**Server Component with preloadQuery:**
```typescript
// VERIFY at: https://docs.convex.dev/client/nextjs/app-router
import { preloadQuery } from "convex/nextjs";
import { api } from "@/convex/_generated/api";
import { TaskList } from "./TaskList";

export default async function TasksPage() {
  // Preload query on server for faster initial load
  const preloadedTasks = await preloadQuery(api.tasks.getMy);

  return <TaskList preloadedTasks={preloadedTasks} />;
}
```

---

## Cloudflare Pages Deployment

### Deployment Architecture

**Hybrid Deployment Pattern:**
- **Frontend**: Deployed on Cloudflare Pages (global edge network)
- **Backend**: Hosted on Convex (managed functions + database)
- **Benefits**: Geographic distribution, automatic scaling, zero DevOps

**VERIFY at:** https://developers.cloudflare.com/pages/framework-guides/nextjs/

### Setup Steps

**1. Create Cloudflare Pages Project:**
- Dashboard → Workers & Pages → Create → Pages → Connect to Git
- Select GitHub repository
- Configure build settings:
  - **Framework preset**: Next.js
  - **Build command**: `npm run build`
  - **Build output directory**: `.next` (Next.js) or `dist` (Vite)

**2. Set Environment Variables:**
- Pages dashboard → Settings → Environment variables
- Add `NEXT_PUBLIC_CONVEX_URL` with your Convex deployment URL
  - Get from: `npx convex dashboard` → Settings → Deployment URL
  - Example: `https://happy-animal-123.convex.cloud`

**3. Deploy:**
- Push to GitHub → Cloudflare automatically builds and deploys
- Preview deployments for all branches
- Production deployment on main branch

### Environment Variable Management

**Local (.env.local):**
```bash
NEXT_PUBLIC_CONVEX_URL=https://your-dev-deployment.convex.cloud
```

**Production (Cloudflare Pages Dashboard):**
```bash
NEXT_PUBLIC_CONVEX_URL=https://your-prod-deployment.convex.cloud
```

**Convex Backend Variables:**
```bash
# Dev environment
npx convex env set STRIPE_SECRET_KEY sk_test_...

# Production environment
npx convex env set STRIPE_SECRET_KEY sk_live_... --prod
```

**Technical Explanation:**
- **Build-time variables**: `NEXT_PUBLIC_*` bundled during build on Cloudflare
- **Runtime variables**: Cloudflare Pages Functions can access runtime environment
- **Separate Convex deployments**: Use different Convex URLs for dev/staging/prod

---

## Development Commands

**VERIFY at:** https://docs.convex.dev/cli

### Local Development

```bash
# Start Convex development server
npx convex dev
# - Starts local dev with hot reload
# - Syncs schema and functions to cloud deployment
# - Watches convex/ directory for changes
# - Provides real-time logs
# - Creates separate dev deployment (not production)

# Run alongside Next.js dev server
npm run dev  # In separate terminal
```

### Production Deployment

```bash
# Deploy Convex backend to production
npx convex deploy --prod
# - Deploys to production environment
# - Runs schema migrations
# - Zero-downtime deployment
# - Returns production deployment URL

# Deploy to specific environment
npx convex deploy --prod --project my-prod-project
```

### Data Operations

```bash
# Import data from JSONL file
npx convex import --table tasks data/tasks.jsonl
# - JSONL format required (one JSON object per line)
# - Batch imports for efficiency
# - Schema validation on import
# - Example JSONL:
# {"text":"Task 1","isCompleted":false}
# {"text":"Task 2","isCompleted":true}

# Export database to JSONL
npx convex data export
# - Exports all tables
# - JSONL format for easy re-import
```

### Environment Variables

```bash
# Set environment variable (dev environment)
npx convex env set STRIPE_SECRET_KEY sk_test_...

# Set environment variable (production)
npx convex env set STRIPE_SECRET_KEY sk_live_... --prod

# List environment variables
npx convex env list
npx convex env list --prod

# Remove environment variable
npx convex env unset STRIPE_SECRET_KEY
```

**Technical Explanation:**
- Environment variables accessible in **actions only** (via `process.env`)
- Separate dev/prod environments
- Secrets never exposed in client code

### Monitoring & Debugging

```bash
# Stream function logs
npx convex logs
# - Real-time logs from all functions
# - Shows query/mutation/action execution
# - Useful for debugging

# Open Convex dashboard
npx convex dashboard
# - Web-based database explorer
# - View data, run queries, monitor functions
# - Performance metrics
```

### Other Commands

```bash
# Initialize new Convex project
npx convex init

# Run TypeScript type checking
npx convex typecheck

# Show current deployment info
npx convex data
```

---

## TypeScript Patterns

**VERIFY at:** https://docs.convex.dev/typescript

### Generated Types

Convex automatically generates TypeScript types in `convex/_generated/`:

```typescript
// Auto-generated after running: npx convex dev
import { api } from "@/convex/_generated/api";
import type { Id } from "@/convex/_generated/dataModel";

// Use generated API for type-safe function calls
const tasks = await client.query(api.tasks.get, { userId: "user_123" });
//    ^? Task[] - fully typed based on your schema

// Use Id<"tableName"> for document IDs
const taskId: Id<"tasks"> = "j57a8c9d0e1f2g3h4i5j6k7l";
```

**Technical Explanation:**
- **convex/_generated/api**: Exports typed function references
- **convex/_generated/dataModel**: Exports `Doc<>`, `Id<>` types based on schema
- **Automatic updates**: Types regenerate when schema or functions change
- **End-to-end type safety**: Client calls are type-checked against server functions

### Client Hook Typing

```typescript
import { useQuery, useMutation } from "convex/react";
import { api } from "@/convex/_generated/api";

// useQuery returns T | undefined during loading
const tasks = useQuery(api.tasks.get, { userId: "user_123" });
//    ^? Task[] | undefined

// useMutation returns typed mutation function
const createTask = useMutation(api.tasks.create);
//    ^? (args: { text: string; userId: Id<"users"> }) => Promise<Id<"tasks">>

// Full IntelliSense support
await createTask({
  text: "New task",
  userId: "user_123",  // Type error if wrong type
});
```

---

## Common Patterns & Best Practices

### Relationship Modeling

**VERIFY at:** https://docs.convex.dev/database/document-ids#relationships

**No JOIN syntax - fetch related documents in parallel:**

```typescript
import { query } from "./_generated/server";
import { v } from "convex/values";

export const getTasksWithUsers = query({
  handler: async (ctx) => {
    // 1. Get all tasks
    const tasks = await ctx.db.query("tasks").collect();

    // 2. Fetch related users in parallel
    const usersPromises = tasks.map(task => ctx.db.get(task.userId));
    const users = await Promise.all(usersPromises);

    // 3. Combine results
    return tasks.map((task, i) => ({
      ...task,
      user: users[i],
    }));
  },
});
```

**Technical Explanation:**
- **v.id("tableName")**: Creates typed reference to another table
- **No JOINs**: Fetch related documents separately, combine in JavaScript
- **Denormalization trade-off**: Sometimes duplicate data for performance

---

### Pagination with usePaginatedQuery

**VERIFY at:** https://docs.convex.dev/database/pagination

**Client Component:**
```typescript
import { usePaginatedQuery } from "convex/react";
import { api } from "@/convex/_generated/api";

export function InfiniteTaskList() {
  const { results, status, loadMore } = usePaginatedQuery(
    api.tasks.getPaginated,
    { userId: "user_123" },
    { initialNumItems: 20 }
  );

  return (
    <div>
      {results.map(task => <div key={task._id}>{task.text}</div>)}

      {status === "CanLoadMore" && (
        <button onClick={() => loadMore(20)}>Load More</button>
      )}
    </div>
  );
}
```

**Technical Explanation:**
- **Cursor-based pagination**: More efficient than OFFSET for large datasets
- **usePaginatedQuery**: Manages pagination state automatically
- **CanLoadMore status**: Indicates if more items available

---

### HTTP Actions (Webhooks)

**VERIFY at:** https://docs.convex.dev/functions/http-actions

**convex/http.ts:**
```typescript
import { httpRouter } from "convex/server";
import { httpAction } from "./_generated/server";
import { api } from "./_generated/api";

const http = httpRouter();

// Stripe webhook endpoint
http.route({
  path: "/stripe/webhook",
  method: "POST",
  handler: httpAction(async (ctx, request) => {
    const signature = request.headers.get("stripe-signature");
    const body = await request.text();

    // Verify Stripe signature
    // ... stripe verification logic ...

    // Call mutation to update database
    await ctx.runMutation(api.payments.processWebhook, { body });

    return new Response(JSON.stringify({ received: true }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  }),
});

// Public API endpoint
http.route({
  path: "/api/tasks",
  method: "GET",
  handler: httpAction(async (ctx, request) => {
    const tasks = await ctx.runQuery(api.tasks.getAll);

    return new Response(JSON.stringify(tasks), {
      headers: { "Content-Type": "application/json" },
    });
  }),
});

export default http;
```

**Technical Explanation:**
- **HTTP endpoints**: Accessible at `https://your-deployment.convex.site/stripe/webhook`
- **Use cases**: Stripe webhooks, external API integrations, custom REST endpoints
- **Cannot access ctx.db directly**: Must call queries/mutations with `ctx.run*()`

---

### Scheduled Functions (Cron Jobs)

**VERIFY at:** https://docs.convex.dev/scheduling/scheduled-functions

**convex/crons.ts:**
```typescript
import { cronJobs } from "convex/server";
import { internal } from "./_generated/api";

const crons = cronJobs();

// Run daily at midnight UTC
crons.daily(
  "cleanup expired tasks",
  { hourUTC: 0, minuteUTC: 0 },
  internal.tasks.cleanupExpired
);

// Run every hour
crons.hourly(
  "send reminder emails",
  { minuteUTC: 0 },
  internal.emails.sendReminders
);

// Custom cron syntax
crons.cron(
  "weekly report",
  "0 9 * * 1",  // Every Monday at 9 AM UTC
  internal.reports.generateWeekly
);

export default crons;
```

**Technical Explanation:**
- **Cron syntax**: Standard cron expressions
- **Internal functions**: Use `internal.*` to prevent public access
- **Use cases**: Daily aggregations, cleanup tasks, periodic syncs

---

### Error Handling

**VERIFY at:** https://docs.convex.dev/functions/error-handling

**convex/tasks.ts:**
```typescript
import { ConvexError } from "convex/values";
import { mutation } from "./_generated/server";
import { v } from "convex/values";

export const create = mutation({
  args: { text: v.string() },
  handler: async (ctx, args) => {
    const identity = await ctx.auth.getUserIdentity();

    if (!identity) {
      // ConvexError propagates to client with proper typing
      throw new ConvexError("Must be logged in to create tasks");
    }

    if (args.text.length > 500) {
      throw new ConvexError({
        message: "Task text too long",
        maxLength: 500,
        actual: args.text.length,
      });
    }

    const taskId = await ctx.db.insert("tasks", {
      text: args.text,
      userId: identity.subject,
      isCompleted: false,
      createdAt: Date.now(),
    });

    return taskId;
  },
});
```

**Client Error Handling:**
```typescript
const createTask = useMutation(api.tasks.create);

try {
  await createTask({ text: "Very long task text..." });
} catch (error) {
  if (error instanceof ConvexError) {
    // Access error data
    console.error(error.data);  // { message, maxLength, actual }
  }
}
```

**Technical Explanation:**
- **ConvexError**: Type-safe error propagation to client
- **Automatic retry**: Transient failures (network issues) automatically retried
- **Error typing**: Client receives properly typed error data

---

### Validation Patterns

**VERIFY at:** https://docs.convex.dev/database/schemas#validators

**Custom Validators:**
```typescript
import { v } from "convex/values";

// Define custom validator
const emailValidator = v.string().regex(/^[^\s@]+@[^\s@]+\.[^\s@]+$/);

// Use in mutation
export const createUser = mutation({
  args: {
    email: emailValidator,
    name: v.string(),
  },
  handler: async (ctx, args) => {
    // args.email is validated before handler runs
    return await ctx.db.insert("users", {
      email: args.email,
      name: args.name,
    });
  },
});
```

**Technical Explanation:**
- **Runtime validation**: Arguments validated before function executes
- **Schema-level validation**: Enforced on write operations
- **Type safety**: Validators generate TypeScript types

---

### File Storage

**VERIFY at:** https://docs.convex.dev/file-storage

**File Upload Action:**
```typescript
import { action } from "./_generated/server";
import { v } from "convex/values";

export const generateUploadUrl = action({
  handler: async (ctx) => {
    // Generate signed upload URL (valid for 1 hour)
    return await ctx.storage.generateUploadUrl();
  },
});

export const saveFile = action({
  args: { storageId: v.string(), filename: v.string() },
  handler: async (ctx, args) => {
    // Save file metadata to database
    await ctx.runMutation(api.files.create, {
      storageId: args.storageId,
      filename: args.filename,
      uploadedAt: Date.now(),
    });
  },
});
```

**Client Upload:**
```typescript
const generateUploadUrl = useMutation(api.files.generateUploadUrl);
const saveFile = useMutation(api.files.saveFile);

const handleUpload = async (file: File) => {
  // 1. Get upload URL
  const uploadUrl = await generateUploadUrl();

  // 2. Upload file
  const result = await fetch(uploadUrl, {
    method: "POST",
    headers: { "Content-Type": file.type },
    body: file,
  });

  const { storageId } = await result.json();

  // 3. Save metadata
  await saveFile({ storageId, filename: file.name });
};
```

---

## Gotchas & Best Practices

### Query Functions Must Be Deterministic

**VERIFY at:** https://docs.convex.dev/functions/query-functions

**❌ DON'T DO THIS:**
```typescript
export const getBad = query({
  handler: async (ctx) => {
    // ❌ Non-deterministic - breaks caching
    const random = Math.random();
    const now = Date.now();
    const external = await fetch("https://api.example.com");

    return { random, now, external };
  },
});
```

**✅ DO THIS:**
```typescript
// Queries: Only database reads
export const getGood = query({
  handler: async (ctx) => {
    return await ctx.db.query("tasks").collect();
  },
});

// Actions: Non-deterministic operations
export const doNonDeterministic = action({
  handler: async (ctx) => {
    const now = Date.now();  // ✅ OK in actions
    const external = await fetch("https://api.example.com");  // ✅ OK

    return { now, external };
  },
});
```

**Why:**
- Queries are cached and must return same result for same inputs
- Enables real-time reactivity and performance optimizations

---

### Index Usage Requirements

**VERIFY at:** https://docs.convex.dev/database/indexes#querying-indexes

**❌ This will scan entire table (slow):**
```typescript
// No index usage - scans all documents
const tasks = await ctx.db
  .query("tasks")
  .filter((q) => q.eq(q.field("userId"), "user_123"))
  .collect();
```

**✅ Use indexes explicitly:**
```typescript
// Efficiently uses "by_user" index
const tasks = await ctx.db
  .query("tasks")
  .withIndex("by_user", (q) => q.eq("userId", "user_123"))
  .collect();
```

**Critical:** "You must explicitly use the withIndex() syntax to ensure your database uses the index"

**Technical Explanation:**
- Convex doesn't auto-select indexes like SQL databases
- Performance impact: Without indexes, queries scan entire table
- Define indexes in schema, use with `.withIndex()` in queries

---

### Local vs Production Environments

**VERIFY at:** https://docs.convex.dev/production/hosting/hosting-and-running

**Separate Deployments:**
- `npx convex dev` → Creates/uses **dev deployment**
- `npx convex deploy --prod` → Deploys to **production**

**Environment Variables:**
```bash
# Dev environment
npx convex env set STRIPE_SECRET_KEY sk_test_...

# Production environment
npx convex env set STRIPE_SECRET_KEY sk_live_... --prod
```

**Frontend URLs:**
```bash
# .env.local (development)
NEXT_PUBLIC_CONVEX_URL=https://dev-deployment.convex.cloud

# Cloudflare Pages (production)
NEXT_PUBLIC_CONVEX_URL=https://prod-deployment.convex.cloud
```

**Best Practice:**
- Always develop against dev deployment
- Only deploy to production after thorough testing

---

## Performance & Monitoring

**VERIFY at:** https://docs.convex.dev/production/monitoring

### Convex Dashboard Features

Access at: `npx convex dashboard`

**Monitoring Capabilities:**
- **Real-time function logs**: View all query/mutation/action executions
- **Query performance metrics**: Execution time, call frequency
- **Database size and usage**: Track storage and document counts
- **Function execution tracking**: Identify slow functions

### Performance Best Practices

**Index Optimization:**
```typescript
// Define indexes for frequently queried fields
export default defineSchema({
  tasks: defineTable({
    userId: v.id("users"),
    status: v.string(),
    createdAt: v.number(),
  })
    .index("by_user", ["userId"])
    .index("by_user_status", ["userId", "status"])  // Compound index
    .index("by_created", ["createdAt"])
});
```

**Pagination for Large Datasets:**
```typescript
// Don't fetch all documents at once
const allTasks = await ctx.db.query("tasks").collect();  // ❌ Slow

// Use pagination
const tasks = await ctx.db.query("tasks").take(100);  // ✅ Faster
```

**Batch Operations:**
```typescript
// Fetch related documents in parallel
const tasks = await ctx.db.query("tasks").collect();
const users = await Promise.all(
  tasks.map(task => ctx.db.get(task.userId))
);
```

---

## Production Deployment Checklist

### Pre-Deployment Verification

```
Project Setup:
- [ ] Detected project framework (Next.js App Router / Pages Router / React Vite)
- [ ] Fetched and verified current Convex documentation
- [ ] Created convex/ directory with schema.ts
- [ ] Defined all necessary indexes in schema
- [ ] Tested local development with npx convex dev
- [ ] Set up .env.local with NEXT_PUBLIC_CONVEX_URL
- [ ] Verified authentication provider integration (Clerk / Convex Auth / Custom)
```

### Cloudflare Pages Configuration

```
Pages Setup:
- [ ] Created Cloudflare Pages project
- [ ] Connected GitHub repository
- [ ] Configured build command (npm run build)
- [ ] Configured build output directory (.next / dist)
- [ ] Set environment variable: NEXT_PUBLIC_CONVEX_URL (production URL)
- [ ] Configured custom domain (if applicable)
- [ ] Set up preview deployments for branches
- [ ] Verified build succeeds on Cloudflare
```

### Convex Backend Configuration

```
Convex Production Deployment:
- [ ] Deployed to production: npx convex deploy --prod
- [ ] Verified production deployment URL
- [ ] Set all production environment variables:
    npx convex env set VARIABLE_NAME value --prod
- [ ] Configured authentication provider:
    - [ ] Clerk: Added production issuer URL in Convex dashboard
    - [ ] Custom: Configured JWT verification
- [ ] Ran schema migrations (automatic on deploy)
- [ ] Tested production database connection
- [ ] Imported any necessary seed data: npx convex import --prod
```

### Security Checklist

```
Security Verification:
- [ ] All secrets in environment variables (never in code)
- [ ] API keys use production values (not test keys)
- [ ] CORS configured if using HTTP actions
- [ ] Authentication required on all sensitive queries/mutations
- [ ] Authorization checks in function code (ctx.auth.getUserIdentity())
- [ ] Rate limiting considered for public endpoints
- [ ] Input validation on all mutation arguments
- [ ] No sensitive data in client-side code
```

### Testing & Monitoring

```
Production Verification:
- [ ] Tested end-to-end user flows in production
- [ ] Verified real-time updates working (WebSocket connection)
- [ ] Checked Convex dashboard for errors
- [ ] Confirmed all queries using proper indexes
- [ ] Tested authentication flow (login/logout/protected routes)
- [ ] Verified file uploads (if using file storage)
- [ ] Tested webhooks (if using HTTP actions)
- [ ] Set up error tracking (Sentry, LogRocket, etc.)
- [ ] Configured monitoring alerts
- [ ] Documented deployment process
```

### Environment Alignment

```
Environment Consistency:
- [ ] Dev environment uses dev Convex deployment
- [ ] Staging environment uses staging Convex deployment (if applicable)
- [ ] Production environment uses production Convex deployment
- [ ] Each environment has separate environment variables
- [ ] Cloudflare Pages preview deployments use dev Convex URL
- [ ] Production branch triggers production deployment
```

---

## Notes
<!-- Project-specific notes, decisions, context -->

**Convex vs Traditional Databases:**
- No SQL/ORM - JavaScript/TypeScript functions
- Automatic transactions in mutations
- Real-time reactive queries via WebSockets
- Explicit index usage required
- Managed backend (zero server configuration)

**When to Use Convex:**
- JAMstack architecture (Cloudflare Pages + Convex backend)
- Real-time collaborative applications
- Type-safe full-stack development
- Rapid prototyping with instant backend
- Projects needing automatic scaling without DevOps

**Integration Architecture:**
- **Frontend**: Cloudflare Pages (global edge, static assets)
- **Backend**: Convex (managed functions, database, real-time)
- **Benefits**: Geographic distribution, automatic scaling, zero infrastructure management
