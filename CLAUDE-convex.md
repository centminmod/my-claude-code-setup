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
| --------- | ----- |
| LLM-Optimized Docs | <https://docs.convex.dev/llms.txt> |
| Quickstart (Next.js App Router) | <https://docs.convex.dev/quickstart/nextjs> |
| Quickstart (Next.js Pages Router) | <https://docs.convex.dev/client/nextjs/pages-router/quickstart> |
| Quickstart (React/Vite) | <https://docs.convex.dev/quickstart/react> |
| Database Schemas | <https://docs.convex.dev/database/schemas> |
| Reading Data (Queries) | <https://docs.convex.dev/database/reading-data> |
| Writing Data (Mutations) | <https://docs.convex.dev/database/writing-data> |
| Functions Overview | <https://docs.convex.dev/functions> |
| Query Functions | <https://docs.convex.dev/functions/query-functions> |
| Mutation Functions | <https://docs.convex.dev/functions/mutation-functions> |
| Actions | <https://docs.convex.dev/functions/actions> |
| HTTP Actions | <https://docs.convex.dev/functions/http-actions> |
| Scheduled Functions | <https://docs.convex.dev/scheduling/scheduled-functions> |
| Authentication Overview | <https://docs.convex.dev/auth> |
| Clerk Integration | <https://docs.convex.dev/auth/clerk> |
| Convex Auth | <https://docs.convex.dev/auth/convex-auth> |
| Custom Auth | <https://docs.convex.dev/auth/custom-auth> |
| Authorization Patterns | <https://docs.convex.dev/auth/authorization> |
| Database Indexes | <https://docs.convex.dev/database/indexes> |
| Pagination | <https://docs.convex.dev/database/pagination> |
| File Storage | <https://docs.convex.dev/file-storage> |
| Full-text Search | <https://docs.convex.dev/text-search> |
| Vector Search | <https://docs.convex.dev/vector-search> |
| TypeScript | <https://docs.convex.dev/typescript> |
| Error Handling | <https://docs.convex.dev/functions/error-handling> |
| Testing | <https://docs.convex.dev/production/testing> |
| Environment Variables | <https://docs.convex.dev/production/environment-variables> |
| Production Hosting | <https://docs.convex.dev/production/hosting> |
| Monitoring | <https://docs.convex.dev/production/monitoring> |
| Convex CLI | <https://docs.convex.dev/cli> |

**Clerk Authentication:**

| Resource | URL |
| ---------- | ----- |
| Clerk + Convex | <https://docs.convex.dev/auth/clerk> |
| Clerk Backend SDK | <https://clerk.com/docs/reference/backend/overview> |
| Clerk Next.js | <https://clerk.com/docs/reference/nextjs/overview> |
| Clerk React | <https://clerk.com/docs/reference/react/overview> |

**Cloudflare Pages Deployment:**

| Resource | URL |
| ---------- | ----- |
| Pages Overview | <https://developers.cloudflare.com/pages/> |
| Next.js on Pages | <https://developers.cloudflare.com/pages/framework-guides/nextjs/> |
| Build Configuration | <https://developers.cloudflare.com/pages/configuration/build-configuration/> |
| Pages Functions | <https://developers.cloudflare.com/pages/functions/> |

---

## Project Detection & Setup

### Step 1: Detect Existing Project Type

Inspect project files to determine language/framework:

```text
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

**VERIFY at:** <https://docs.convex.dev/production/hosting/hosting-and-running>

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

**VERIFY at:** <https://docs.convex.dev/quickstart/nextjs>

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

**VERIFY at:** <https://docs.convex.dev/client/nextjs/pages-router/quickstart>

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

**VERIFY at:** <https://docs.convex.dev/quickstart/react>

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

**VERIFY at:** <https://docs.convex.dev/database/schemas>

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

**VERIFY at:** <https://docs.convex.dev/database/reading-data>

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

**VERIFY at:** <https://docs.convex.dev/database/writing-data>

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

**VERIFY at:** <https://docs.convex.dev/functions/actions>

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

**VERIFY at:** <https://docs.convex.dev/auth/clerk>

**Setup Steps:**

1. **Install Clerk:**

```bash
npm install @clerk/nextjs  # For Next.js
# OR
npm install @clerk/clerk-react  # For React
```

1. **Configure Clerk in Convex Dashboard:**

   - Navigate to Settings → Authentication
   - Add Clerk as provider
   - Copy Issuer URL from Clerk dashboard

1. **Add Clerk to Next.js App:**

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

1. **Access Auth in Convex Functions:**

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

**VERIFY at:** <https://docs.convex.dev/client/nextjs/app-router>

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

### Advanced Server-Side Rendering (SSR)

**VERIFY at:** <https://docs.convex.dev/client/react/nextjs/server-rendering>

**Using fetchQuery for Server Components (Non-Reactive):**

```typescript
import { fetchQuery } from "convex/nextjs";
import { api } from "@/convex/_generated/api";

// Server Component - data fetched once at render time (not reactive)
export default async function StaticTasksPage() {
  const tasks = await fetchQuery(api.tasks.list, { list: "default" });

  return (
    <div>
      <h1>Tasks (Static)</h1>
      {tasks.map((task) => (
        <div key={task._id}>{task.text}</div>
      ))}
    </div>
  );
}
```

**Using fetchMutation in Server Actions:**

```typescript
import { fetchMutation } from "convex/nextjs";
import { api } from "@/convex/_generated/api";

async function createTaskAction(formData: FormData) {
  "use server";
  await fetchMutation(api.tasks.create, {
    text: formData.get("text") as string,
  });
}

export default function TaskForm() {
  return (
    <form action={createTaskAction}>
      <input name="text" placeholder="New task" />
      <button type="submit">Add</button>
    </form>
  );
}
```

**SSR with Authentication:**

```typescript
import { preloadQuery } from "convex/nextjs";
import { auth } from "@clerk/nextjs/server";
import { api } from "@/convex/_generated/api";

export default async function AuthenticatedPage() {
  // Get Convex token from Clerk
  const { getToken } = await auth();
  const token = await getToken({ template: "convex" });

  // Pass token to preloadQuery for authenticated data
  const preloadedData = await preloadQuery(
    api.tasks.getMyTasks,
    {},
    { token: token ?? undefined }
  );

  return <TaskList preloadedTasks={preloadedData} />;
}
```

**Technical Notes:**

- `preloadQuery`: Preloads data, client component becomes reactive
- `fetchQuery`: One-time fetch, no reactivity (pure server component)
- `fetchMutation`: Execute mutations from Server Actions or Route Handlers
- Token passing required for authenticated queries in SSR

---

### React (Vite) Hooks

**VERIFY at:** <https://docs.convex.dev/quickstart/react>

**src/App.tsx:**

```typescript
import { useQuery, useMutation, useAction } from "convex/react";
import { api } from "../convex/_generated/api";

export function App() {
  // Reactive query - automatically updates when data changes
  const tasks = useQuery(api.tasks.list);

  // Mutation hook - returns function to call
  const createTask = useMutation(api.tasks.create);
  const deleteTask = useMutation(api.tasks.remove);

  // Action hook - for external API calls
  const sendEmail = useAction(api.notifications.sendEmail);

  // Loading state
  if (tasks === undefined) {
    return <div>Loading...</div>;
  }

  const handleCreate = async (text: string) => {
    await createTask({ text, isCompleted: false });
  };

  const handleDelete = async (id: Id<"tasks">) => {
    await deleteTask({ id });
  };

  return (
    <div>
      {tasks.map((task) => (
        <div key={task._id}>
          {task.text}
          <button onClick={() => handleDelete(task._id)}>Delete</button>
        </div>
      ))}
      <button onClick={() => handleCreate("New task")}>Add Task</button>
    </div>
  );
}
```

**Conditional Queries:**

```typescript
// Skip query when condition not met
const userId = useAuth()?.userId;
const userTasks = useQuery(
  api.tasks.getByUser,
  userId ? { userId } : "skip"  // "skip" prevents query execution
);
```

---

### Optimistic Updates

**VERIFY at:** <https://docs.convex.dev/client/react/optimistic-updates>

Optimistic updates provide instant UI feedback before server confirmation.

**Basic Example:**

```typescript
"use client";
import { useMutation, useQuery } from "convex/react";
import { api } from "@/convex/_generated/api";

export function Counter() {
  const count = useQuery(api.counter.get);

  const increment = useMutation(api.counter.increment).withOptimisticUpdate(
    (localStore, args) => {
      const currentValue = localStore.getQuery(api.counter.get, {});
      if (currentValue !== undefined) {
        // Immediately update local state
        localStore.setQuery(api.counter.get, {}, currentValue + args.amount);
      }
    }
  );

  return (
    <div>
      <p>Count: {count ?? 0}</p>
      <button onClick={() => increment({ amount: 1 })}>+1</button>
    </div>
  );
}
```

**Chat Message Example:**

```typescript
const sendMessage = useMutation(api.messages.send).withOptimisticUpdate(
  (localStore, args) => {
    const { channel, body } = args;
    const existingMessages = localStore.getQuery(api.messages.list, { channel });

    if (existingMessages !== undefined) {
      // Add temporary message immediately
      const optimisticMessage = {
        _id: crypto.randomUUID() as Id<"messages">,
        _creationTime: Date.now(),
        channel,
        body,
        pending: true,  // Optional: mark as pending
      };

      localStore.setQuery(api.messages.list, { channel }, [
        ...existingMessages,
        optimisticMessage,
      ]);
    }
  }
);
```

**Best Practices:**

- Always create new objects (don't mutate existing)
- Check if query is loaded before updating
- Optimistic data may differ from server response (automatically corrected)
- Small mistakes are okay - UI will eventually show correct values

---

## Cloudflare Pages Deployment

### Deployment Architecture

**Hybrid Deployment Pattern:**

- **Frontend**: Deployed on Cloudflare Pages (global edge network)
- **Backend**: Hosted on Convex (managed functions + database)
- **Benefits**: Geographic distribution, automatic scaling, zero DevOps

**VERIFY at:** <https://developers.cloudflare.com/pages/framework-guides/nextjs/>

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
  - Example: `<https://happy-animal-123.convex.cloud`>

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

### Cloudflare Troubleshooting

**Common Issues and Solutions:**

| Issue | Cause | Solution |
| ------- | ------- | ---------- |
| "Convex URL not found" | Missing env var | Add `NEXT_PUBLIC_CONVEX_URL` in Pages dashboard |
| Build fails on Cloudflare | Node version | Set `NODE_VERSION=18` in env vars |
| Functions timeout | Edge runtime limits | Use Convex for heavy processing, not Pages Functions |
| Preview deploy uses prod Convex | Same URL for all | Use separate Convex projects per environment |
| WebSocket connection fails | Proxy/firewall | Ensure `*.convex.cloud` is allowed |

**Environment-Specific Deployment:**

```bash
# Create separate Convex projects for each environment
# Production
npx convex deploy --prod --project my-app-prod

# Staging (separate project)
npx convex dev --project my-app-staging
```

**DNS & Custom Domains:**

- Cloudflare Pages handles frontend domains automatically
- Convex deployment URL remains `*.convex.cloud`
- No custom domain needed for Convex (frontend proxies requests)

**Build Optimization:**

```bash
# Cloudflare Pages Build Settings
Build command: npm run build
Build output directory: .next (Next.js) or dist (Vite)
Root directory: / (or your app subdirectory)
```

**Debugging Production Issues:**

```bash
# Stream logs from production
npx convex logs --prod

# Check function execution in dashboard
npx convex dashboard
```

**Important Notes:**

- Cloudflare Pages has 100ms CPU time limit for edge functions
- Use Convex actions for heavy computation (30s limit on paid plans)
- Real-time features (WebSocket) work out-of-box with Convex
- No cold starts for Convex functions

---

## Development Commands

**VERIFY at:** <https://docs.convex.dev/cli>

### CLI Setup & Configuration

```bash
# Initialize new Convex project
npx convex init
# - Creates convex/ directory structure
# - Generates .env.local with CONVEX_DEPLOYMENT

# Log out (switch accounts)
npx convex logout
# - Removes stored Convex credentials
# - Allows switching to different account

# Open documentation
npx convex docs
# - Opens Convex documentation in browser
```

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

### Running Functions

```bash
# Execute query/mutation/action with JSON arguments
npx convex run myFunction '{"arg1": "value"}'

# Run with watch mode (re-run on function changes)
npx convex run myFunction --watch

# Push functions before running (ensures latest code)
npx convex run myFunction --push

# Run against production deployment
npx convex run myFunction --prod
```

### Production Deployment

```bash
# Deploy Convex backend to production
npx convex deploy --prod
# - Deploys to production environment
# - Runs schema migrations
# - Zero-downtime deployment
# - Returns production deployment URL

# Deploy with build command (e.g., build frontend after backend deployed)
npx convex deploy --cmd "npm run build"
# - Runs command after successful deployment
# - Sets environment variable with deployment URL

# Deploy with custom environment variable for deployment URL
npx convex deploy --cmd "npm run build" --cmd-url-env-var-name CONVEX_URL
# - Custom env var name instead of default

# Preview deployments (for CI/CD branches)
npx convex deploy --preview-create <branch-name>
# - Creates isolated preview deployment
# - Useful for PR previews, staging environments

# Run function after preview deployment
npx convex deploy --preview-create <branch-name> --preview-run setupData
# - Runs setup function after deployment
# - Useful for seeding test data

# Deploy to specific environment
npx convex deploy --prod --project my-prod-project
```

### Type Generation

```bash
# Generate TypeScript types from schema
npx convex codegen
# - Updates convex/_generated/ directory
# - Generates types from schema and functions
# - Provides end-to-end type safety
# - Automatically run by npx convex dev

# Type check without generating code
npx convex typecheck
# - Validates TypeScript code
# - Checks for type errors
# - Does not modify files
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

# Import from ZIP archive (multiple tables)
npx convex import data.zip
# - Imports all tables from ZIP
# - ZIP contains JSONL files named after tables
# - Useful for full database migrations

# Export database to JSONL
npx convex data export --path ./exports
# - Exports all tables to specified directory
# - JSONL format for easy re-import
# - Creates separate file per table

# Export with file storage included
npx convex data export --include-file-storage --path ./exports
# - Includes uploaded files in export
# - Downloads all files from storage
# - Larger export size but complete backup

# Display table data in terminal
npx convex data
# - Lists all tables

npx convex data tasks
# - Shows data from specific table

npx convex data tasks --limit 10
# - Limits results to 10 rows

npx convex data tasks --order desc
# - Orders by creation time descending
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

# Control log display during dev
npx convex dev --tail-logs always
# - Always show logs during development

npx convex dev --tail-logs disable
# - Disable automatic log tailing
# - Use npx convex logs separately

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

**VERIFY at:** <https://docs.convex.dev/typescript>

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

## Testing

**VERIFY at:** <https://docs.convex.dev/testing>

### convex-test Setup

The `convex-test` library provides a mocked Convex backend for unit testing with Vitest.

**Installation:**

```bash
npm install --save-dev convex-test vitest @edge-runtime/vm
```

**vitest.config.ts:**

```typescript
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "edge-runtime",
    server: { deps: { inline: ["convex-test"] } },
  },
});
```

**package.json scripts:**

```json
{
  "scripts": {
    "test": "vitest",
    "test:once": "vitest run",
    "test:coverage": "vitest run --coverage"
  }
}
```

### Writing Tests

**convex/messages.test.ts:**

```typescript
import { convexTest } from "convex-test";
import { expect, test } from "vitest";
import { api } from "./_generated/api";
import schema from "./schema";

test("sending and listing messages", async () => {
  const t = convexTest(schema);

  // Test mutations
  await t.mutation(api.messages.send, { body: "Hello!", author: "Alice" });
  await t.mutation(api.messages.send, { body: "Hi there!", author: "Bob" });

  // Test queries
  const messages = await t.query(api.messages.list);
  expect(messages).toMatchObject([
    { body: "Hello!", author: "Alice" },
    { body: "Hi there!", author: "Bob" },
  ]);
});

test("direct database access", async () => {
  const t = convexTest(schema);

  // Directly manipulate database for test setup
  const task = await t.run(async (ctx) => {
    await ctx.db.insert("tasks", { text: "Test task", isCompleted: false });
    return await ctx.db.query("tasks").first();
  });

  expect(task).toMatchObject({ text: "Test task" });
});
```

### Testing with Authentication

```typescript
import { convexTest } from "convex-test";
import { expect, test } from "vitest";
import { api } from "./_generated/api";
import schema from "./schema";

test("authenticated user operations", async () => {
  const t = convexTest(schema);

  // Create test user with identity
  const asAlice = t.withIdentity({ name: "Alice", email: "alice@example.com" });
  const asBob = t.withIdentity({ name: "Bob", email: "bob@example.com" });

  // Each user sees only their own data
  await asAlice.mutation(api.tasks.create, { text: "Alice's task" });
  await asBob.mutation(api.tasks.create, { text: "Bob's task" });

  const aliceTasks = await asAlice.query(api.tasks.getMyTasks);
  expect(aliceTasks).toHaveLength(1);
  expect(aliceTasks[0].text).toBe("Alice's task");
});
```

### Testing HTTP Actions

```typescript
test("http endpoint", async () => {
  const t = convexTest(schema);

  const response = await t.fetch("/api/health", { method: "GET" });
  expect(response.status).toBe(200);

  const data = await response.json();
  expect(data).toMatchObject({ status: "ok" });
});
```

### Mocking External APIs

```typescript
import { vi } from "vitest";

test("action with external API", async () => {
  // Mock fetch for external API calls
  vi.stubGlobal("fetch", vi.fn(async () => ({
    ok: true,
    json: async () => ({ result: "mocked" }),
  })));

  const t = convexTest(schema);
  const result = await t.action(api.external.callApi, { input: "test" });

  expect(result).toBe("mocked");
  vi.unstubAllGlobals();
});
```

---

## CI/CD & Deployment

**VERIFY at:** <https://docs.convex.dev/production/hosting>

### GitHub Actions Workflow

**.github/workflows/test.yml:**

```yaml
name: Test and Deploy

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: "npm"

      - run: npm ci
      - run: npm run test:once

  deploy:
    needs: test
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: "npm"

      - run: npm ci

      # Deploy Convex backend
      - run: npx convex deploy --cmd "npm run build"
        env:
          CONVEX_DEPLOY_KEY: ${{ secrets.CONVEX_DEPLOY_KEY }}
```

### Preview Deployments

**VERIFY at:** <https://docs.convex.dev/production/hosting/preview-deployments>

Preview deployments create isolated Convex backends for each PR.

**.github/workflows/preview.yml:**

```yaml
name: Preview Deployment

on:
  pull_request:
    types: [opened, synchronize]

jobs:
  preview:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"

      - run: npm ci

      # Create preview deployment
      - run: |
          npx convex deploy \
            --preview-create ${{ github.head_ref }} \
            --preview-run seedData
        env:
          CONVEX_DEPLOY_KEY: ${{ secrets.CONVEX_DEPLOY_KEY }}

      # Comment preview URL on PR
      - uses: actions/github-script@v7
        with:
          script: |
            github.rest.issues.createComment({
              owner: context.repo.owner,
              repo: context.repo.repo,
              issue_number: context.issue.number,
              body: '🚀 Preview deployment ready!'
            })
```

### Environment Setup

**Getting CONVEX_DEPLOY_KEY:**

```bash
# Generate deploy key for CI/CD
npx convex deploy-key create

# Add to GitHub Secrets:
# Settings → Secrets → Actions → New repository secret
# Name: CONVEX_DEPLOY_KEY
# Value: (paste the key)
```

**Preview Deployment Notes:**

- Auto-deleted after 5 days (14 days on Professional)
- Each PR gets isolated database
- Use `--preview-run` to seed test data
- Preview URL returned by deploy command

---

## Common Patterns & Best Practices

### Relationship Modeling

**VERIFY at:** <https://docs.convex.dev/database/document-ids#relationships>

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

**VERIFY at:** <https://docs.convex.dev/database/pagination>

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

**VERIFY at:** <https://docs.convex.dev/functions/http-actions>

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

- **HTTP endpoints**: Accessible at `<https://your-deployment.convex.site/stripe/webhook`>
- **Use cases**: Stripe webhooks, external API integrations, custom REST endpoints
- **Cannot access ctx.db directly**: Must call queries/mutations with `ctx.run*()`

---

### Scheduled Functions (Cron Jobs)

**VERIFY at:** <https://docs.convex.dev/scheduling/scheduled-functions>

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

**VERIFY at:** <https://docs.convex.dev/functions/error-handling>

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

**VERIFY at:** <https://docs.convex.dev/database/schemas#validators>

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

**VERIFY at:** <https://docs.convex.dev/file-storage>

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

## Full Text Search

**VERIFY at:** <https://docs.convex.dev/text-search>

### Defining Search Indexes

Search indexes enable full-text search over string fields using BM25 scoring.

**convex/schema.ts:**

```typescript
import { defineSchema, defineTable } from "convex/server";
import { v } from "convex/values";

export default defineSchema({
  messages: defineTable({
    body: v.string(),
    channel: v.string(),
    author: v.string(),
  }).searchIndex("search_body", {
    searchField: "body",           // Field to search
    filterFields: ["channel"],     // Up to 16 filter fields
  }),

  articles: defineTable({
    title: v.string(),
    content: v.string(),
    category: v.string(),
    published: v.boolean(),
  }).searchIndex("search_content", {
    searchField: "content",
    filterFields: ["category", "published"],
  }),
});
```

### Running Search Queries

**convex/messages.ts:**

```typescript
import { query } from "./_generated/server";
import { v } from "convex/values";

// Basic search
export const search = query({
  args: { searchTerm: v.string(), channel: v.optional(v.string()) },
  handler: async (ctx, args) => {
    let searchQuery = ctx.db
      .query("messages")
      .withSearchIndex("search_body", (q) => {
        let search = q.search("body", args.searchTerm);
        if (args.channel) {
          search = search.eq("channel", args.channel);
        }
        return search;
      });

    // Results ordered by relevance (BM25 score)
    return await searchQuery.take(10);
  },
});

// Search with additional filtering
export const searchRecent = query({
  args: { searchTerm: v.string() },
  handler: async (ctx, args) => {
    const tenMinutesAgo = Date.now() - 10 * 60 * 1000;

    return await ctx.db
      .query("messages")
      .withSearchIndex("search_body", (q) => q.search("body", args.searchTerm))
      .filter((q) => q.gt(q.field("_creationTime"), tenMinutesAgo))
      .take(10);
  },
});
```

**Search Constraints:**

- Up to 16 search terms per query
- Up to 8 filter expressions
- Maximum 1024 documents scanned per query
- Terms limited to 32 characters (case-insensitive)
- Results always returned in relevance order

---

## Vector Search

**VERIFY at:** <https://docs.convex.dev/vector-search>

### Defining Vector Indexes

Vector indexes enable semantic similarity search using embeddings.

**convex/schema.ts:**

```typescript
import { defineSchema, defineTable } from "convex/server";
import { v } from "convex/values";

export default defineSchema({
  documents: defineTable({
    title: v.string(),
    content: v.string(),
    embedding: v.array(v.float64()),  // Vector field
    category: v.optional(v.string()),
  }).vectorIndex("by_embedding", {
    vectorField: "embedding",
    dimensions: 1536,               // Must match embedding model (OpenAI: 1536)
    filterFields: ["category"],     // Optional filter fields
  }),
});
```

### Storing Embeddings

**convex/documents.ts:**

```typescript
import { action, internalMutation } from "./_generated/server";
import { v } from "convex/values";
import { internal } from "./_generated/api";

// Action to generate and store embedding
export const addDocument = action({
  args: { title: v.string(), content: v.string(), category: v.optional(v.string()) },
  handler: async (ctx, args) => {
    // Generate embedding via OpenAI
    const response = await fetch("https://api.openai.com/v1/embeddings", {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${process.env.OPENAI_API_KEY}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        model: "text-embedding-3-small",
        input: args.content,
      }),
    });

    const { data } = await response.json();
    const embedding = data[0].embedding;

    // Store document with embedding
    await ctx.runMutation(internal.documents.insertDocument, {
      title: args.title,
      content: args.content,
      embedding,
      category: args.category,
    });
  },
});

export const insertDocument = internalMutation({
  args: {
    title: v.string(),
    content: v.string(),
    embedding: v.array(v.float64()),
    category: v.optional(v.string()),
  },
  handler: async (ctx, args) => {
    await ctx.db.insert("documents", args);
  },
});
```

### Running Vector Searches

**convex/search.ts:**

```typescript
import { action, internalQuery } from "./_generated/server";
import { v } from "convex/values";
import { internal } from "./_generated/api";

// Vector search action
export const semanticSearch = action({
  args: { query: v.string(), category: v.optional(v.string()) },
  handler: async (ctx, args) => {
    // Generate query embedding
    const response = await fetch("https://api.openai.com/v1/embeddings", {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${process.env.OPENAI_API_KEY}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        model: "text-embedding-3-small",
        input: args.query,
      }),
    });

    const { data } = await response.json();
    const queryEmbedding = data[0].embedding;

    // Perform vector search
    const results = await ctx.vectorSearch("documents", "by_embedding", {
      vector: queryEmbedding,
      limit: 10,
      filter: args.category
        ? (q) => q.eq("category", args.category)
        : undefined,
    });

    // Load full documents
    const documents = await ctx.runQuery(internal.documents.getByIds, {
      ids: results.map((r) => r._id),
    });

    return documents;
  },
});

export const getByIds = internalQuery({
  args: { ids: v.array(v.id("documents")) },
  handler: async (ctx, args) => {
    const results = [];
    for (const id of args.ids) {
      const doc = await ctx.db.get(id);
      if (doc) results.push(doc);
    }
    return results;
  },
});
```

**Vector Search Constraints:**

- Up to 4 vector indexes per table
- Maximum 256 results per query
- Dimensions must match exactly (e.g., 1536 for OpenAI)
- Uses approximate nearest neighbor with cosine similarity
- Score ranges from -1 to 1 (higher = more similar)

---

## Internal Functions

**VERIFY at:** <https://docs.convex.dev/functions/internal-functions>

### What Are Internal Functions?

Internal functions can only be called by other Convex functions (not from clients). They reduce your app's attack surface.

**convex/internal.ts:**

```typescript
import { internalQuery, internalMutation, internalAction } from "./_generated/server";
import { v } from "convex/values";

// Internal query - not accessible from client
export const getSecretData = internalQuery({
  args: { userId: v.id("users") },
  handler: async (ctx, args) => {
    // Sensitive data access
    return await ctx.db
      .query("sensitiveData")
      .withIndex("by_user", (q) => q.eq("userId", args.userId))
      .collect();
  },
});

// Internal mutation - for privileged operations
export const upgradeUserPlan = internalMutation({
  args: { userId: v.id("users"), plan: v.string() },
  handler: async (ctx, args) => {
    await ctx.db.patch(args.userId, { plan: args.plan });
  },
});

// Internal action - for background processing
export const processPayment = internalAction({
  args: { userId: v.id("users"), amount: v.number() },
  handler: async (ctx, args) => {
    // Call external payment API
    // Then update user via internal mutation
    await ctx.runMutation(internal.users.upgradeUserPlan, {
      userId: args.userId,
      plan: "premium",
    });
  },
});
```

### Calling Internal Functions

```typescript
import { action, mutation } from "./_generated/server";
import { internal } from "./_generated/api";

// Public action that uses internal functions
export const handleWebhook = action({
  args: { event: v.string(), userId: v.id("users") },
  handler: async (ctx, args) => {
    if (args.event === "payment.success") {
      // Call internal mutation - safe from direct client access
      await ctx.runMutation(internal.users.upgradeUserPlan, {
        userId: args.userId,
        plan: "premium",
      });
    }
  },
});
```

**When to Use Internal Functions:**

- Privileged operations (admin-only actions)
- Operations called from scheduled functions/crons
- Business logic that should bypass client validation
- Actions called from HTTP endpoints/webhooks

---

## Components

**VERIFY at:** <https://docs.convex.dev/components>

### What Are Components?

**Convex Components** are self-contained backend modules that package code, schemas, and persistent data into isolated sandboxes. They are "like mini self-contained Convex backends" that can be safely added to any Convex app.

**Key Characteristics:**

- **Data Isolation**: Components cannot read your app's tables or call your functions unless explicitly passed in
- **Own Database Tables**: Each component maintains its own isolated database tables
- **Own File Storage**: Separate file storage independent from the main application
- **Transactional Consistency**: All writes commit atomically with the parent mutation
- **Real-time Reactivity**: Component queries are reactive by default
- **Safe Installation**: Installing components is always safe due to strict isolation

**Why Use Components Instead of npm Packages?**

| Feature | npm Package | Convex Component |
| --------- | ------------- | ------------------ |
| State Persistence | In-memory (lost on restart) | Database-backed (persistent) |
| Data Access | Direct database access | Explicit API boundaries |
| Transactional Guarantees | None (distributed inconsistencies) | Atomic commits across boundaries |
| Isolation | Shared global state | Isolated environments |
| Validation | Manual | Runtime validation at boundaries |

**Technical Explanation:**
Unlike libraries that require third-party services for stateful functionality, Components store state in the same database as your app, providing transactional guarantees and eliminating distributed protocol complexity.

---

### Installation & Configuration

**Step 1: Install Component via npm**

```bash
npm install @convex-dev/component-name
```

**Common Components:**

```bash
npm install @convex-dev/agent      # AI agents with threads/messages
npm install @convex-dev/rag        # RAG (Retrieval-Augmented Generation)
npm install @convex-dev/rate-limiter  # Rate limiting
```

**Step 2: Configure in convex.config.ts**

Create or update `convex/convex.config.ts`:

```typescript
import { defineApp } from "convex/server";
import agent from "@convex-dev/agent/convex.config";
import rateLimit from "@convex-dev/rate-limiter/convex.config";

const app = defineApp();

// Mount components with names
app.use(agent, { name: "agent" });
app.use(rateLimit, { name: "rateLimit" });

// Multiple instances of same component
app.use(agent, { name: "customerSupport" });
app.use(agent, { name: "researchAgent" });

export default app;
```

**Technical Explanation:**

- `defineApp()` creates the app configuration
- `use()` mounts components with unique names
- Each component instance has separate tables/functions
- Multiple instances enable isolated use cases (e.g., separate agents)

**Step 3: Generate Integration Code**

```bash
npx convex dev
```

This generates the `components` object in your API for accessing component functions.

---

### Using Components in Your Code

**Calling Component Functions**

Components are accessed through `components` object in generated API:

**convex/myFunctions.ts:**

```typescript
import { query, mutation, action } from "./_generated/server";
import { components } from "./_generated/api";

// Query calling component query
export const getThread = query({
  args: { threadId: v.id("threads") },
  handler: async (ctx, args) => {
    // Queries can only call component queries
    return await ctx.runQuery(components.agent.threads.getThread, {
      threadId: args.threadId,
    });
  },
});

// Mutation calling component mutation
export const createMessage = mutation({
  args: { threadId: v.id("threads"), content: v.string() },
  handler: async (ctx, args) => {
    // Mutations can call component mutations
    await ctx.runMutation(components.agent.messages.create, {
      threadId: args.threadId,
      role: "user",
      content: args.content,
    });
  },
});

// Action calling component action
export const processWithAI = action({
  args: { input: v.string() },
  handler: async (ctx, args) => {
    // Actions can call component actions
    return await ctx.runAction(components.agent.generate, {
      prompt: args.input,
    });
  },
});
```

**Important Rules:**

- Queries can only call component **queries** (maintains reactivity)
- Mutations can call component **mutations** (maintains transactions)
- Actions can call component **actions**
- Component queries are reactive by default

---

### Transaction Behavior

**All Writes Commit Together:**

```typescript
export const createUserWithProfile = mutation({
  args: { userId: v.id("users"), name: v.string() },
  handler: async (ctx, args) => {
    // Write 1: App table
    await ctx.db.insert("users", { userId: args.userId });

    // Write 2: Component table
    await ctx.runMutation(components.profiles.create, {
      userId: args.userId,
      name: args.name,
    });

    // Both writes commit atomically
    // If parent mutation fails, both rollback
  },
});
```

**Error Handling & Partial Rollback:**

```typescript
export const createWithFallback = mutation({
  args: { data: v.object({ name: v.string() }) },
  handler: async (ctx, args) => {
    // Write 1: App table
    await ctx.db.insert("items", { name: args.data.name });

    try {
      // Write 2: Component (might fail)
      await ctx.runMutation(components.analytics.track, {
        event: "item_created",
      });
    } catch (error) {
      // Component writes rollback, but parent continues
      console.error("Analytics failed:", error);
    }

    // App write still commits even if component failed
  },
});
```

**Technical Explanation:**

- All writes in a mutation commit together by default
- If parent mutation throws, all writes (app + component) rollback
- If component mutation throws but caller catches it, only component writes rollback
- No distributed protocols needed - single database transaction

---

### Monitoring & Debugging

**Dashboard Access:**

1. Open Convex Dashboard
2. Use dropdown selector to view component tables
3. Filter logs by component: `data.function.component_path`

**Example Log Filtering:**

```bash
# View logs from specific component
npx convex logs --filter 'data.function.component_path == "agent"'
```

**Testing with convex-test:**

```typescript
import { convexTest } from "convex-test";
import { expect, test } from "vitest";
import schema from "./schema";
import { components } from "./_generated/api";

test("component integration", async () => {
  const t = convexTest(schema, {
    // Register components for testing
    components: {
      agent: components.agent,
    },
  });

  const threadId = await t.mutation(components.agent.createThread, {});
  expect(threadId).toBeDefined();
});
```

---

### Authoring Custom Components

**Directory Structure:**

```text
my-component/
├── convex.config.ts   # Component configuration
├── schema.ts          # Component-specific schema
├── functions.ts       # Public API functions
├── _internal/         # Internal functions (not exposed)
└── _generated/        # Auto-generated code
```

**convex.config.ts:**

```typescript
import { defineComponent } from "convex/server";

export default defineComponent("myComponent");
```

**schema.ts:**

```typescript
import { defineSchema, defineTable } from "convex/server";
import { v } from "convex/values";

export default defineSchema({
  items: defineTable({
    name: v.string(),
    createdAt: v.number(),
  }),
});
```

**functions.ts (Public API):**

```typescript
import { query, mutation } from "./_generated/server";
import { v } from "convex/values";

// Public function (exported = accessible by apps)
export const createItem = mutation({
  args: { name: v.string() },
  handler: async (ctx, args) => {
    return await ctx.db.insert("items", {
      name: args.name,
      createdAt: Date.now(),
    });
  },
});

// Public query
export const listItems = query({
  handler: async (ctx) => {
    return await ctx.db.query("items").collect();
  },
});
```

**_internal/helpers.ts (Internal - Not Exposed):**

```typescript
import { internalMutation } from "../_generated/server";
import { v } from "convex/values";

// Internal function (not accessible by apps)
export const cleanup = internalMutation({
  args: {},
  handler: async (ctx) => {
    // Internal logic only
  },
});
```

**Key Constraints for Component Authors:**

| Constraint | Reason |
| ------------ | -------- |
| No `ctx.auth` | Authentication happens in app, not component |
| All `Id<"table">` become strings at boundary | ID types don't cross boundaries |
| No `process.env` access | Components can't access environment variables |
| Only public functions accessible | Internal functions remain hidden |

**Publishing to NPM:**

```bash
# 1. Create component from template
npx create-convex@latest --component

# 2. Build with concurrent watchers
npx convex codegen --component-dir ./my-component &
npm run build &
npx convex dev --typecheck-components

# 3. Expose NPM entry points
# package.json:
{
  "main": "./dist/index.js",
  "exports": {
    ".": "./dist/index.js",
    "./convex.config.js": "./convex.config.js",
    "./_generated/component.js": "./_generated/component.js",
    "./test": "./dist/test.js"
  }
}

# 4. Publish
npm publish
```

---

### Popular Components

**Browse All Components:** <https://convex.dev/components>

**Common Use Cases:**

- `@convex-dev/agent` - AI agents with threads, messages, tool calls
- `@convex-dev/rag` - RAG (Retrieval-Augmented Generation) for semantic search
- `@convex-dev/rate-limiter` - API rate limiting and usage tracking
- `@convex-dev/sharded-counter` - High-throughput counters (avoids OCC conflicts)
- `@convex-dev/crons` - Advanced cron scheduling
- `@convex-dev/workflow` - Durable workflow execution

#### Rate Limiter Example

```bash
npm install @convex-dev/rate-limiter
```

**convex/convex.config.ts:**

```typescript
import { defineApp } from "convex/server";
import rateLimiter from "@convex-dev/rate-limiter/convex.config";

const app = defineApp();
app.use(rateLimiter, { name: "rateLimit" });
export default app;
```

**convex/rateLimit.ts:**

```typescript
import { components } from "./_generated/api";
import { RateLimiter } from "@convex-dev/rate-limiter";

const rateLimiter = new RateLimiter(components.rateLimit, {
  apiRequests: { kind: "token bucket", rate: 100, period: 60000, capacity: 100 },
  signups: { kind: "fixed window", rate: 5, period: 3600000 },
});

export const checkApiLimit = rateLimiter.check("apiRequests");
export const consumeApiToken = rateLimiter.consume("apiRequests");
```

**Usage in mutation:**

```typescript
export const createPost = mutation({
  args: { content: v.string() },
  handler: async (ctx, args) => {
    const identity = await ctx.auth.getUserIdentity();
    if (!identity) throw new Error("Not authenticated");

    // Check rate limit before proceeding
    const { ok, retryAfter } = await rateLimiter.limit(ctx, "apiRequests", {
      key: identity.subject,
    });

    if (!ok) {
      throw new Error(`Rate limited. Retry after ${retryAfter}ms`);
    }

    return await ctx.db.insert("posts", { content: args.content });
  },
});
```

#### Sharded Counter Example

```bash
npm install @convex-dev/sharded-counter
```

**For high-frequency counters that would cause OCC conflicts:**

```typescript
import { components } from "./_generated/api";
import { ShardedCounter } from "@convex-dev/sharded-counter";

const counter = new ShardedCounter(components.shardedCounter, {
  shards: 100,  // More shards = higher throughput
});

// Increment without conflicts
export const incrementViews = mutation({
  args: { postId: v.id("posts") },
  handler: async (ctx, args) => {
    await counter.inc(ctx, args.postId, 1);
  },
});

// Read approximate count
export const getViewCount = query({
  args: { postId: v.id("posts") },
  handler: async (ctx, args) => {
    return await counter.count(ctx, args.postId);
  },
});
```

**Technical Explanation:**
Components enable composability for complex features without building from scratch, while maintaining data isolation and transactional guarantees.

---

## AI & Agents

**VERIFY at:** <https://docs.convex.dev/agents>

### Agent Component Overview

The **Convex Agent component** is a core building block for constructing AI-powered applications with persistent conversation history, tool calls, and RAG integration.

**Key Capabilities:**

- Persistent conversation threads with automatic history management
- Real-time updates across all connected clients (reactivity)
- Tool calling for external function invocation
- RAG (Retrieval-Augmented Generation) integration
- Multi-agent workflows
- Streaming text and structured object generation
- Rate limiting and usage tracking

**Use Cases:**

- AI chatbots with memory
- Multi-agent systems
- Customer support agents
- Research assistants with RAG
- Workflow automation with AI decision-making

---

### Installation & Setup

```bash
# Install Agent component
npm install @convex-dev/agent

# Install RAG component (optional, for RAG features)
npm install @convex-dev/rag
```

**Technical Explanation:**

- Agent component is a Convex component (reusable pattern)
- Manages threads, messages, and agent interactions
- Integrates seamlessly with Convex actions and queries

---

### Threads and Messages

**VERIFY at:** <https://docs.convex.dev/agents>

**convex/agents.ts:**

```typescript
import { agent } from "@convex-dev/agent";
import { OpenAI } from "openai";
import { action } from "./_generated/server";
import { api } from "./_generated/api";

// Create agent with OpenAI
const myAgent = agent({
  model: "gpt-4",
  provider: new OpenAI({ apiKey: process.env.OPENAI_API_KEY }),
  instructions: "You are a helpful customer support assistant.",
});

// Start new conversation thread
export const startThread = action({
  handler: async (ctx) => {
    const threadId = await myAgent.createThread(ctx);
    return threadId;
  },
});

// Send message to agent
export const chat = action({
  args: { threadId: v.id("threads"), message: v.string() },
  handler: async (ctx, args) => {
    // Add user message to thread
    await myAgent.addMessage(ctx, {
      threadId: args.threadId,
      role: "user",
      content: args.message,
    });

    // Generate agent response
    const response = await myAgent.generateText(ctx, {
      threadId: args.threadId,
    });

    return response;
  },
});

// Get conversation history
export const getMessages = query({
  args: { threadId: v.id("threads") },
  handler: async (ctx, args) => {
    return await myAgent.getMessages(ctx, args.threadId);
  },
});
```

**Technical Explanation:**

- **Threads**: Persistent conversation containers
- **Messages**: Individual messages with role (user/assistant/system)
- **Automatic context**: Previous messages automatically included in LLM calls
- **Hybrid search**: Built-in vector/text search over conversation history
- **Multi-user**: Threads can be shared across users and agents

---

### Tool Calls

**VERIFY at:** <https://docs.convex.dev/agents>

Enable agents to call external functions as part of their reasoning process.

**Example: Agent with Weather Tool**

```typescript
import { agent, tool } from "@convex-dev/agent";
import { OpenAI } from "openai";
import { v } from "convex/values";

// Define tool
const getWeather = tool({
  name: "get_weather",
  description: "Get current weather for a location",
  parameters: v.object({
    location: v.string(),
  }),
  handler: async (ctx, args) => {
    // Call external weather API
    const response = await fetch(
      `https://api.weather.com/current?location=${args.location}`
    );
    const data = await response.json();
    return { temperature: data.temp, conditions: data.conditions };
  },
});

// Create agent with tool
const weatherAgent = agent({
  model: "gpt-4",
  provider: new OpenAI({ apiKey: process.env.OPENAI_API_KEY }),
  instructions: "You help users with weather information.",
  tools: [getWeather],
});

export const askWeather = action({
  args: { threadId: v.id("threads"), question: v.string() },
  handler: async (ctx, args) => {
    await weatherAgent.addMessage(ctx, {
      threadId: args.threadId,
      role: "user",
      content: args.question,
    });

    // LLM will automatically call getWeather tool if needed
    const response = await weatherAgent.generateText(ctx, {
      threadId: args.threadId,
    });

    return response;
  },
});
```

**Technical Explanation:**

- **Tool definition**: Name, description, parameters, handler function
- **Automatic invocation**: LLM decides when to use tools
- **Multi-turn**: After tool call, LLM can generate final response
- **Tool response history**: Tool calls and responses persisted in thread

---

### RAG Integration

**VERIFY at:** <https://docs.convex.dev/agents/rag>

Integrate Retrieval-Augmented Generation for context-aware responses.

**Two Approaches:**

**1. Upfront Context Injection** (search before LLM call)

```typescript
import { rag } from "@convex-dev/rag";
import { agent } from "@convex-dev/agent";

// Create RAG component
const documentRAG = rag({
  embeddingModel: "text-embedding-ada-002",
});

export const chatWithDocs = action({
  args: { threadId: v.id("threads"), question: v.string() },
  handler: async (ctx, args) => {
    // 1. Search for relevant documents
    const relevantDocs = await documentRAG.search(ctx, {
      query: args.question,
      limit: 5,
    });

    // 2. Inject context into prompt
    const context = relevantDocs.map(doc => doc.content).join("\n\n");
    const prompt = `Context:\n${context}\n\nQuestion: ${args.question}`;

    await myAgent.addMessage(ctx, {
      threadId: args.threadId,
      role: "user",
      content: prompt,
    });

    // 3. Generate response with context
    return await myAgent.generateText(ctx, { threadId: args.threadId });
  },
});
```

**2. RAG as Tool Calls** (LLM decides when to search)

```typescript
// Define RAG as a tool
const searchDocuments = tool({
  name: "search_documents",
  description: "Search knowledge base for relevant information",
  parameters: v.object({
    query: v.string(),
  }),
  handler: async (ctx, args) => {
    const results = await documentRAG.search(ctx, {
      query: args.query,
      limit: 5,
    });
    return results.map(doc => doc.content);
  },
});

// Agent with RAG tool
const ragAgent = agent({
  model: "gpt-4",
  provider: new OpenAI({ apiKey: process.env.OPENAI_API_KEY }),
  instructions: "Search the knowledge base when needed to answer questions.",
  tools: [searchDocuments],
});
```

**Technical Explanation:**

- **Upfront approach**: Simpler, always includes context
- **Tool approach**: More flexible, LLM decides when to search
- **Hybrid vector/text search**: Combines semantic and keyword matching
- **Automatic embedding**: RAG component handles vector embeddings

---

### Streaming Responses

**VERIFY at:** <https://docs.convex.dev/agents>

Stream agent responses for real-time UI updates.

```typescript
export const streamChat = action({
  args: { threadId: v.id("threads"), message: v.string() },
  handler: async (ctx, args) => {
    await myAgent.addMessage(ctx, {
      threadId: args.threadId,
      role: "user",
      content: args.message,
    });

    // Stream text generation
    const stream = await myAgent.streamText(ctx, {
      threadId: args.threadId,
    });

    return stream; // Client receives incremental updates
  },
});
```

**Client Usage:**

```typescript
const streamChat = useAction(api.agents.streamChat);

const handleSend = async (message: string) => {
  const stream = await streamChat({ threadId, message });

  for await (const chunk of stream) {
    // Update UI with each chunk
    setResponse(prev => prev + chunk);
  }
};
```

**Technical Explanation:**

- **Streaming API**: Returns async iterable
- **Real-time UI**: Update UI incrementally as text generates
- **Better UX**: Users see immediate progress vs waiting for full response

---

### Rate Limiting & Usage Tracking

**VERIFY at:** <https://docs.convex.dev/agents>

Track and limit agent usage per user or team.

```typescript
import { rateLimit } from "@convex-dev/agent";

export const chatWithLimit = action({
  args: { userId: v.id("users"), message: v.string() },
  handler: async (ctx, args) => {
    // Check rate limit (e.g., 10 messages per hour)
    const allowed = await rateLimit.check(ctx, {
      key: `user_${args.userId}`,
      limit: 10,
      window: 3600, // 1 hour in seconds
    });

    if (!allowed) {
      throw new Error("Rate limit exceeded. Try again later.");
    }

    // Track usage for billing
    await ctx.runMutation(api.usage.trackMessage, {
      userId: args.userId,
      tokens: 0, // Will be updated after LLM call
    });

    const response = await myAgent.generateText(ctx, {
      threadId: args.threadId,
    });

    // Update token usage for billing
    await ctx.runMutation(api.usage.updateTokens, {
      userId: args.userId,
      tokens: response.usage.totalTokens,
    });

    return response;
  },
});
```

**Technical Explanation:**

- **Rate limiting**: Prevent abuse, comply with LLM provider limits
- **Usage tracking**: Bill per user/team based on token consumption
- **Cost control**: Monitor and cap spending per user

---

### Multi-Agent Workflows

**VERIFY at:** <https://docs.convex.dev/agents/workflows>

Coordinate multiple agents for complex tasks.

```typescript
// Research agent
const researcher = agent({
  model: "gpt-4",
  provider: new OpenAI({ apiKey: process.env.OPENAI_API_KEY }),
  instructions: "Research topics and provide factual information.",
  tools: [searchDocuments],
});

// Writing agent
const writer = agent({
  model: "gpt-4",
  provider: new OpenAI({ apiKey: process.env.OPENAI_API_KEY }),
  instructions: "Write clear, engaging content based on research.",
});

export const createArticle = action({
  args: { topic: v.string() },
  handler: async (ctx, args) => {
    // Step 1: Research agent gathers information
    const researchThread = await researcher.createThread(ctx);
    await researcher.addMessage(ctx, {
      threadId: researchThread,
      role: "user",
      content: `Research this topic: ${args.topic}`,
    });
    const research = await researcher.generateText(ctx, {
      threadId: researchThread,
    });

    // Step 2: Writing agent creates article from research
    const writerThread = await writer.createThread(ctx);
    await writer.addMessage(ctx, {
      threadId: writerThread,
      role: "user",
      content: `Write an article based on this research:\n${research.text}`,
    });
    const article = await writer.generateText(ctx, {
      threadId: writerThread,
    });

    return article.text;
  },
});
```

**Technical Explanation:**

- **Agent specialization**: Different agents for different tasks
- **Sequential workflows**: Output of one agent feeds into another
- **Durable execution**: Workflows persist across interruptions
- **Human-in-the-loop**: Can pause for human approval between steps

---

## Gotchas & Best Practices

### Query Functions Must Be Deterministic

**VERIFY at:** <https://docs.convex.dev/functions/query-functions>

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

**VERIFY at:** <https://docs.convex.dev/database/indexes#querying-indexes>

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

**VERIFY at:** <https://docs.convex.dev/production/hosting/hosting-and-running>

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

### Optimistic Concurrency Control (OCC) & Write Conflicts

**VERIFY at:** <https://docs.convex.dev/database/advanced/occ>

**What is OCC?**

Convex uses **Optimistic Concurrency Control (OCC)** to provide ACID compliance with true **serializability** (not just snapshot isolation). Instead of locking records, Convex treats each mutation as "a declarative proposal to write records on the basis of any read record versions."

**How It Works:**

```typescript
// Transaction A: Reads Alice's account (v1: $14)
const alice = await ctx.db.get(aliceId);  // version 1

// (Meanwhile, Transaction B modifies Alice's account → now v2)

// Transaction A attempts to write
await ctx.db.patch(aliceId, { balance: alice.balance - 5 });
// ❌ FAILS: Alice version changed from v1 to v2
// Convex automatically retries the entire mutation
```

**Technical Explanation:**

- At commit time, Convex checks if all read records are still at their original versions
- If any record changed, the mutation **fails and automatically retries**
- Similar to Git: "Cannot push because HEAD is out of date → rebase and try again"
- Because mutations are **deterministic**, retrying is safe and transparent

**Write Conflict Error:**

When retries exceed threshold (high contention), you'll see:

```text
OccRetryThresholdExceeded: Documents read from or written to the
table 'counters' changed while this mutation was being run and on
every subsequent retry.
```

**Common Causes:**

1. **High-frequency updates to same document:**

```typescript
// ❌ CONFLICT PRONE: Many concurrent calls updating same counter
export const incrementCounter = mutation({
  args: { counterId: v.id("counters") },
  handler: async (ctx, args) => {
    const counter = await ctx.db.get(args.counterId);
    await ctx.db.patch(args.counterId, {
      count: (counter?.count || 0) + 1
    });
  },
});

// Called 100 times/second → conflicts!
```

**✅ FIX: Use Sharded Counter component**

```bash
npm install @convex-dev/sharded-counter
```

1. **Broad data dependencies (reading entire tables):**

```typescript
// ❌ CONFLICT PRONE: Reads ALL tasks
export const addTask = mutation({
  handler: async (ctx, args) => {
    // Reading entire table creates conflict with ANY mutation that writes to tasks
    const allTasks = await ctx.db.query("tasks").collect();
    const taskCount = allTasks.length;

    await ctx.db.insert("tasks", { ...args, order: taskCount });
  },
});
```

**✅ FIX: Read only necessary data with indexes**

```typescript
export const addTask = mutation({
  args: { userId: v.id("users"), text: v.string() },
  handler: async (ctx, args) => {
    // Only read tasks for this user (using index)
    const userTasks = await ctx.db
      .query("tasks")
      .withIndex("by_user", (q) => q.eq("userId", args.userId))
      .collect();

    await ctx.db.insert("tasks", {
      userId: args.userId,
      text: args.text,
      order: userTasks.length,
    });
  },
});
```

**Best Practices to Avoid Conflicts:**

| Issue | Solution |
| ------- | ---------- |
| Hot document (many writes to same record) | Shard data across multiple documents |
| Reading entire tables | Use indexed queries with selective range expressions |
| Unexpected repeated calls | Avoid mutations in loops, debounce client calls |
| Single counter for all users | Use Sharded Counter or per-user counters |

**Technical Guarantee:**

Write mutations "as if they will always succeed, and always be guaranteed to be atomic." Convex handles conflicts transparently through automatic retries, providing true serializability without developer intervention.

**When to Use Components:**

- **Sharded Counter**: Distribute high-frequency writes across multiple documents
- **Workpool**: Prioritize critical tasks through separate queues

---

## Performance & Monitoring

**VERIFY at:** <https://docs.convex.dev/production/monitoring>

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

### Log Streams & Exception Reporting

**VERIFY at:** <https://docs.convex.dev/production/integrations/log-streams>

Stream logs to external services for monitoring and alerting. Requires Convex Pro plan.

**Available Destinations:**

- **Axiom** - Log analytics with automatic dashboard creation
- **Datadog** - APM and log management
- **Webhook** - Custom HTTP endpoints (any service)

**Setup via Dashboard:**

1. Go to Convex Dashboard → Settings → Integrations
2. Select destination (Axiom, Datadog, or Webhook)
3. Configure credentials and options
4. Enable log stream

**Log Event Types:**

| Event Type | Description |
| ------------ | ------------- |
| `console` | Function console.log/warn/error output |
| `function_execution` | Execution metrics (duration, status, errors) |
| `audit_log` | Deployment changes and admin actions |
| `scheduler_stats` | Scheduled function queue metrics |
| `storage_usage` | Database and file storage metrics |

**Webhook Security:**

```typescript
// Verify webhook signature (HMAC-SHA256)
const signature = request.headers.get("x-webhook-signature");
const timestamp = request.headers.get("x-webhook-timestamp");

// Validate using constant-time comparison
// Check timestamp to prevent replay attacks
```

**Best Practices:**

- Use Axiom for quick setup with pre-built dashboards
- Datadog for existing APM infrastructure
- Webhook for custom alerting or unsupported services
- Log streams are "best-effort" - may drop events under high load

---

## Production Guarantees & Limits

**VERIFY at:** <https://docs.convex.dev/production/state/>

### Availability & Uptime

**Availability Target:**

- **99.99% availability** (four nines) for all Convex deployments
- Maintenance downtime may occur without prior notice
- Physical outages will not compromise data durability

**Important Note:**
Convex currently does not offer formal contractual SLAs beyond their standard Terms of Service. For enterprise requirements, contact <support@convex.dev>.

**Technical Explanation:**
Database state is replicated durably across multiple physical availability zones to ensure availability even during infrastructure failures.

---

### Data Protection & Security

**Encryption:**

- **All user data encrypted at rest** in Convex deployments
- Encryption happens automatically, no configuration required

**Data Replication:**

- Database state replicated across **multiple physical availability zones**
- Protects against data center failures
- No manual failover required

**Backup Durability:**

- Regular periodic and incremental backups performed automatically
- Backups stored with **99.999999999% durability** (eleven nines)
- Comparable to Amazon S3 Standard storage class

**Technical Explanation:**
Backup durability of 11 nines means the annual probability of losing a backup is approximately 0.000000001% (1 in 100 billion). Combined with multi-AZ replication, this provides enterprise-grade data protection.

---

### Backward Compatibility Guarantee

**Commitment:**

- Code written for Convex 1.0+ will continue to work without modification
- Breaking changes will have **substantial advance notice** to affected teams
- Direct communication for any potential breaking changes

**What This Means:**
You can build production applications on Convex with confidence that future updates won't break your existing code without warning.

---

### Platform Limits

**VERIFY at:** <https://docs.convex.dev/production/state/limits>

#### Function Execution Limits

| Resource | Limit | Notes |
| ---------- | ------- | ------- |
| Query/Mutation execution | 1 second | User code only (excludes framework overhead) |
| Action execution | 10 minutes | Long-running operations |
| Concurrent Node actions (Free/Starter) | 64 | Parallel action executions |
| Concurrent Node actions (Pro) | 1,000 | Professional plan benefit |

**Technical Explanation:**

- Queries/mutations have 1-second limit because they're transactional (must be fast)
- Actions can run up to 10 minutes for external API calls, file processing, etc.
- Exceeding limits throws error; design functions to complete within timeframes

#### Document & Database Limits

| Resource | Limit | Notes |
| ---------- | ------- | ------- |
| Document size | 1 MiB | Per document maximum |
| Fields per document | 1,024 | Total field count |
| Object/array nesting depth | 16 levels | Nested structures |
| Array elements | 8,192 | Per array maximum |
| Tables per deployment | 10,000 | Total tables |
| Indexes per table | 32 | Maximum indexes |

**Common Gotcha:**
If you hit the 1 MiB document limit, split data across multiple related documents using references (e.g., store large JSON in separate "metadata" table).

#### Transaction Limits

| Resource | Limit | Notes |
| ---------- | ------- | ------- |
| Data read/written per transaction | 16 MiB | Total transaction size |
| Documents written per transaction | 16,000 | Mutation write limit |
| Documents scanned per transaction | 32,000 | Query/filter limit |
| Index range reads | 4,096 | Per transaction |

**Technical Explanation:**
These limits ensure mutations remain fast and prevent runaway transactions. If you need to process more data, use pagination or batch operations across multiple transactions.

#### Storage & Bandwidth Limits

| Plan | Database Storage | File Storage | Database Bandwidth | File Bandwidth | Function Calls |
| ------ | ------------------ | -------------- | ------------------- | ---------------- | ---------------- |
| Free | 0.5 GiB | 1 GiB | 1 GiB/month | 1 GiB/month | 1M calls/month |
| Starter | 8 GiB | 10 GiB | 8 GiB/month | 10 GiB/month | 5M calls/month |
| Professional | 50 GiB | 100 GiB | 50 GiB/month | 50 GiB/month | 25M calls/month |

**Overage Pricing:**

- Database storage: $1.00/GiB/month
- File storage: $0.15/GiB/month
- Additional bandwidth and calls: usage-based pricing

#### Search Limits

| Feature | Limit | Notes |
| --------- | ------- | ------- |
| Full-text search indexes | 4 per table | Text search capability |
| Full-text search results | 1,024 maximum | Per query |
| Vector search indexes | 4 per table | Semantic/AI search |
| Vector search results | 256 maximum | Per query |

**Technical Explanation:**
Search indexes are separate from regular indexes and have their own limits. Design your search features to work within these constraints (e.g., use pagination for large result sets).

---

### Current Limitations (As of 2025)

**No Built-In Authorization Framework:**

- Only **authentication** exists (identity verification)
- Authorization (permission checks) must be implemented manually in queries/mutations
- Pattern: Check `ctx.auth.getUserIdentity()` and validate permissions in code

**Example:**

```typescript
export const deleteTask = mutation({
  args: { taskId: v.id("tasks") },
  handler: async (ctx, args) => {
    const identity = await ctx.auth.getUserIdentity();
    if (!identity) throw new Error("Unauthorized");

    const task = await ctx.db.get(args.taskId);
    if (!task) throw new Error("Task not found");

    // ⚠️ Manual authorization check required
    if (task.userId !== identity.subject) {
      throw new Error("Forbidden: You don't own this task");
    }

    await ctx.db.delete(args.taskId);
  },
});
```

**Limited Observability:**

- Basic dashboard metrics available (function execution time, call frequency)
- Third-party integration for advanced monitoring still in development
- Recommendation: Use Sentry, LogRocket, or custom logging for production

**Not Optimized for Analytics (OLAP):**

- Convex is designed for real-time transactional operations (OLTP)
- Complex analytical queries (aggregations across large datasets) may hit limits
- Recommendation: Use streaming export to dedicated analytics database (Snowflake, BigQuery)

---

### When Limits May Increase

The Convex team notes: "Many of these limits will become more permissive over time."

If you encounter limits for your use case, contact <support@convex.dev> to discuss:

- Plan-specific limit increases
- Custom enterprise arrangements
- Roadmap for future limit expansions

---

### Compliance & Enterprise

**Current Status:**

- **Terms of Service:** <https://convex.dev/terms>
- **Privacy Policy:** <https://convex.dev/privacy>
- **No formal GDPR/SOC2 certifications mentioned** in developer documentation

**For Enterprise Requirements:**
Contact <support@convex.dev> for:

- Compliance documentation
- Security audits
- Custom agreements
- SLA contracts

---

## Production Deployment Checklist

### Pre-Deployment Verification

```text
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

```text
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

```text
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

```text
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

```text
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

```text
Environment Consistency:
- [ ] Dev environment uses dev Convex deployment
- [ ] Staging environment uses staging Convex deployment (if applicable)
- [ ] Production environment uses production Convex deployment
- [ ] Each environment has separate environment variables
- [ ] Cloudflare Pages preview deployments use dev Convex URL
- [ ] Production branch triggers production deployment
```

### Backup & Disaster Recovery

**VERIFY at:** <https://docs.convex.dev/database/backup-restore>

#### Manual Backups (Dashboard)

**Access:** Convex Dashboard → Backups → "Backup Now"

**Characteristics:**

- Creates consistent snapshot of all table data
- Processing time: seconds to hours (depending on data size)
- Retention: 7 days
- Storage limit: Free/Starter plans (2 backups max), Pro plans (unlimited, usage-based pricing)
- **Includes:** Table data only
- **Excludes:** Code, environment variables, scheduled functions, configuration

**File Storage Inclusion:**

```bash
# Dashboard option: "Include file storage"
# Or via CLI export:
npx convex export --path ~/Downloads --include-file-storage
```

#### Scheduled Backups (Pro Plan)

**Configuration:** Convex Dashboard → Backups → "Backup automatically"

**Options:**

- **Daily backups**: Retained for 7 days, specify time of day
- **Weekly backups**: Retained for 14 days, specify day/time
- **File storage**: Optional inclusion checkbox

**Technical Explanation:**
Scheduled backups require Convex Pro plan. Each backup is billed for database and file bandwidth (same as user file storage costs).

#### Restore Process

**CRITICAL:** Restoration is **destructive** - wipes existing data before restore

**Best Practice:**

```bash
# Step 1: Create backup BEFORE restoring
# Dashboard → Backup Now

# Step 2: Restore from backup
# Dashboard → Backups → Select backup → "Restore"

# Step 3: Redeploy code
npx convex dev  # Verify changes locally first
npx convex deploy --prod  # Deploy to production

# Step 4: Restore environment variables
npx convex env set VARIABLE_NAME value --prod
```

**Cross-Deployment Restore:**

```bash
# Use case: Populate dev deployment with prod data
# Dashboard → Backups → Select backup → "Restore" → Choose target deployment
```

**File Storage Behavior:**

- Existing files in deployment are **NOT deleted**
- Files from backup that don't exist in deployment are uploaded
- Result: Merge of existing files + backup files

#### Backup Download & Import

**Download Backup (ZIP):**

Dashboard: Backups → Select backup → Download → `snapshot_{timestamp}.zip`

**ZIP Structure:**

```text
snapshot_1234567890.zip
├── users/
│   └── documents.jsonl          # One document per line
├── tasks/
│   └── documents.jsonl
├── _storage/                     # Optional: file storage
│   └── files...
└── generated_schema.jsonl        # Preserves Int64, Bytes types
```

**Import ZIP:**

```bash
# Import to dev deployment
npx convex import snapshot_1234567890.zip

# Import to production (CAUTION!)
npx convex import snapshot_1234567890.zip --prod
```

**Technical Explanation:**

- ZIP imports preserve document `_id` and `_creationTime` fields
- Maintains referential integrity across table references
- Import is atomic (except with `--append` flag)
- Queries never see partially imported state

#### Import from Custom Data Sources

**Single Table Import:**

```bash
# CSV (requires headers)
npx convex import --table users users.csv

# JSONLines (one object per line)
npx convex import --table tasks tasks.jsonl

# JSON (array of objects, 8MiB limit)
npx convex import --table products products.json
```

**Import Modes:**

```bash
# Append to existing data
npx convex import --table users users.jsonl --append

# Replace all table data (destructive)
npx convex import --table users users.jsonl --replace

# Default: Fail if table already exists
npx convex import --table users users.jsonl
```

**Production Import:**

```bash
# ALWAYS test in dev first!
npx convex import --table users users.jsonl

# Then import to production
npx convex import --table users users.jsonl --prod
```

#### Disaster Recovery Scenarios

**Scenario 1: Bad Deployment**

```bash
# 1. Create immediate backup (if not already automated)
Dashboard → Backup Now

# 2. Restore from last known-good backup
Dashboard → Restore from backup (before bad deployment)

# 3. Redeploy validated code
git checkout <last-good-commit>
npx convex deploy --prod

# 4. Verify production
npx convex dashboard  # Check logs and data
```

**Scenario 2: Data Corruption**

```bash
# 1. Identify corruption scope (table/documents)
npx convex data <table-name>  # Inspect data

# 2. Export current state (for forensics)
npx convex export --path ./corrupt-state

# 3. Restore from backup
Dashboard → Restore from backup

# 4. Manual corrections (if needed)
# Write one-off mutations to fix specific records
```

**Scenario 3: Accidental Deletion**

```bash
# 1. Immediately stop further writes (if possible)
# Disable frontend or pause deployment

# 2. Restore from most recent backup
Dashboard → Restore from backup (within 7 days)

# 3. Assess data loss window
# Any data between backup and deletion is lost
# Consider manual reconstruction from logs/analytics
```

#### Streaming Export (Alternative Backup)

**VERIFY at:** <https://docs.convex.dev/production/integrations/streaming-import-export>

For continuous data replication to external databases:

```bash
# Integrate via Fivetran or Airbyte
# Provides real-time backup to:
- PostgreSQL
- Snowflake
- BigQuery
- Redshift
```

**Use Cases:**

- Real-time analytics warehouse
- Continuous backup to external system
- Compliance/audit trail requirements
- Multi-region data redundancy

**Important:** After restoring from backup, streaming export integrations must be reset.

#### Backup Limitations & Requirements

**What's Included:**

- ✅ All table data with schemas
- ✅ File storage (if option selected)
- ✅ Document IDs and creation times
- ✅ Advanced types (Int64, Bytes via generated_schema.jsonl)

**What's Excluded:**

- ❌ Deployment code (functions)
- ❌ Configuration files
- ❌ Environment variables
- ❌ Pending scheduled functions
- ❌ Authentication provider config

**After Restore, You Must:**

1. Redeploy code: `npx convex deploy --prod`
2. Restore environment variables: `npx convex env set ...`
3. Reconfigure authentication providers (Clerk, etc.)
4. Reset streaming export integrations (if using)
5. Verify scheduled functions are running

**Beta Note:** ZIP imports not supported on deployments created before Convex v1.7. Contact support for workarounds.

---

### Streaming Import/Export

**VERIFY at:** <https://docs.convex.dev/database/import-export/streaming>

For large-scale data operations, Convex supports streaming via Fivetran and Airbyte.

**Streaming Export (Pro Plan Required):**

Export data to external analytics platforms:

- **Databricks** - Data lakehouse analytics
- **Snowflake** - Cloud data warehouse
- **BigQuery** - Google Cloud analytics
- **ElasticSearch** - Advanced search and filtering

**Use Cases:**

- Heavy analytical queries not suited for Convex
- Machine learning training on historical data
- Complex reporting and BI dashboards
- Full-text search with advanced features

**Setup:**

1. Dashboard → Settings → Integrations → Fivetran/Airbyte
2. Configure destination credentials
3. Select tables to export
4. Set sync frequency

**Streaming Import:**

Import data from existing databases:

- Enables gradual Convex adoption
- Build new features on existing data
- Create reactive UI layers over legacy systems
- No custom migration tooling required

**Important Considerations:**

- Treat imported tables as **read-only** to prevent write conflicts
- Streaming export is beta feature
- Streaming import via Fivetran not currently supported
- Both integrations use incremental sync for efficiency

**CLI Export Alternative:**

```bash
# For one-time exports (not streaming)
npx convex export --path ./backup

# Export with file storage
npx convex export --include-file-storage --path ./backup

# Import from JSONL
npx convex import --table tasks ./data/tasks.jsonl
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
