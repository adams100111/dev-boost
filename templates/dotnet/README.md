# .NET + Aspire dev-stack template

A starting point for a .NET 10 LTS solution orchestrated by [.NET Aspire](https://learn.microsoft.com/dotnet/aspire/).
Provisioned by dev-boost's `dotnet` profile:

- **.NET 10 LTS SDK** (`dotnet-sdk`, Fedora in-distro)
- **Aspire CLI** (`aspire`, a global dotnet tool — binary `aspire`)
- **fresh** C# intelligence (`dotnet-lsp`): `csharp-ls` language server +
  [csharpier](https://csharpier.com/) formatter (wired in `.fresh/config.json`)

## Create a new solution

```sh
# Scaffold an Aspire solution (App Host + service defaults + sample apps).
aspire new

# …or start from this template's AppHost.cs as your *.AppHost/Program.cs.
```

## Run it

```sh
# From the App Host project directory — Aspire boots the dashboard,
# the shared infra containers, and every wired service project.
dotnet run
```

The dashboard URL is printed on startup. `AppHost.cs` declares shared infra
(Postgres + Redis) with `.WithDataVolume()` and
`.WithLifetime(ContainerLifetime.Persistent)`, so the containers and their data
**persist across `dotnet run` restarts** — your local database is not wiped
between debug sessions.

## Editing in fresh

`.fresh/config.json` enables `csharp-ls` and sets **csharpier** as the C#
formatter (`dotnet csharpier`), with `format_on_save`. Both tools are installed
globally by the `dotnet-lsp` module; open this folder in `fresh` and C#
intelligence works out of the box.

## Upgrading the language server

`csharp-ls` is the clean, pinnable default. For richer analysis you can switch to
the Roslyn-based `roslyn-ls` (ships inside the C# extension; no clean standalone
pinned install) — update `lsp.csharp.command` in your fresh config accordingly.
