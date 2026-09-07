# EF Core migration discipline (.NET projects only)

## Scope guard — READ FIRST
This rule applies **only to .NET projects that use EF Core migrations**. Detect by: a `*.csproj`
referencing `Microsoft.EntityFrameworkCore*` **and** a `Migrations/` folder (or an EF `DbContext`).
If the current project is not .NET, or has no EF Core / migrations, **this rule does not apply —
ignore it entirely.** Do not mention it for non-.NET work.

## The discipline (binding for in-scope projects)
1. **Migrations are generated with `dotnet ef`, never hand-authored.** Always use
   `dotnet ef migrations add <Name> --context <DbContext>` (ensure a design-time
   `IDesignTimeDbContextFactory` exists). This produces the migration `.cs` **and its
   `.Designer.cs`** (the `[Migration]`/`[DbContext]` attributes + model snapshot) **and** updates
   `…ModelSnapshot.cs` — as one consistent set.
2. **Why:** a hand-authored migration missing its `.Designer.cs` is **invisible to EF** (`dotnet ef`
   doesn't list it and `Database.Migrate()` skips it), so on a **fresh database its tables are never
   created** while the snapshot still declares them → runtime failure. Build/test gates do NOT catch
   this; a persisted dev DB masks it. (Real incidents: TechGovern 026/029.)
3. **Forward-only.** Schema changes = a **new** `migrations add` (e.g. a CHECK change diffs to
   Drop+Add); never edit an already-applied migration. Migrations apply on startup via
   `Database.Migrate()` (or `dotnet ef database update`).
4. **Verify durability before considering a migration done:**
   - `dotnet ef migrations list` count **==** number of migration `.cs` files (every `.cs` has a
     sibling `.Designer.cs`).
   - `dotnet ef migrations has-pending-model-changes` → **none** (snapshot ⇔ model consistent).
   - A clean `dotnet ef database update` against a **throwaway DB** (e.g. a disposable Postgres
     container) applies cleanly and creates the expected tables. Tear it down after.
5. **Parallel / multi-agent execution (e.g. worktree-isolated agents):** agents in isolated
   worktrees lack a design-time DB and must **NOT** author migrations. The **controller/integrator
   regenerates the migration via `dotnet ef` at the build/integration gate**, against the merged
   model — never accept a hand-written migration `.cs` from a sub-agent.
