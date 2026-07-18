# T3 Code — architecture analysis & adoption notes for dev-boost

**Created**: 2026-07-18
**Status**: Reference notes (not a spec) — inputs for tasks #8–#12
**Source**: deep read of a clone of `pingdotgg/t3code` (Theo Browne's open-source GUI/harness
for AI coding agents), analyzed by five parallel subagents over the real source. Evidence is
cited as `path:line` against that repo.

## Why we looked
T3 Code was raised as "does something like our remote-dev setup, and better, with a mobile app
coming." It is an open-source, self-hostable **coding-agent GUI**. This note records how it works
and — given our own **dev-boost** (Fedora laptops + Ubuntu VPS on Tailscale), **browser-mcp**
(agent drives a real browser over the tailnet), and **terminal-bridge** (in-band wezterm
clipboard/links/open-url/notify) — exactly what we should steal.

## How T3 Code works (in one paragraph)
A **client** (desktop / web / mobile) talks to a **server that sits next to your code + agents**
over **one authenticated WebSocket** carrying schema-first Effect-RPC. Three axes are kept strictly
independent: **transport** (the server always binds `127.0.0.1`; the renderer always speaks
`ws://loopback`), **access** (interchangeable endpoint providers — LAN, `tailscale serve`, SSH
port-forward, Cloudflare tunnel), and **launch** (SSH launcher / desktop-embedded / cloud). Auth is
**app-layer and never trusts the network**. Agents run under an **event-sourced session model** with
a **driver-as-value registry** for parallel agents and **ACP** as the backend-neutral seam.

## Five principles worth stealing (each flagged by multiple facets)
1. **Access ≠ Launch ≠ Transport.** Bind to loopback; make reachability a swappable endpoint
   provider. One reconnect/auth path across LAN/tailnet/SSH/tunnel. (`docs/architecture/remote.md:240-333`)
2. **App-auth never trusts the transport.** Tailnet gives reach, not authorization; every request
   still needs a signed, scoped, revocable credential. (`apps/server/src/auth/*`, `ws.ts:1872`)
3. **Loopback + `tailscale serve` for TLS**, not raw `http://100.x`. One command → valid cert on the
   MagicDNS name; unblocks secure-context / PWA / mixed-content. (`packages/tailscale/src/tailscale.ts:303`)
4. **Snapshot + event-replay + durable outbox** = resilience over flaky links.
   (`apps/mobile/src/connection/environment-cache-store.ts`, `state/use-thread-outbox-drain.ts`,
   `packages/contracts/src/orchestration.ts:1137`)
5. **Adopt-don't-duplicate + idempotent hash-keyed launcher** (`managed` vs `external` servers) so
   tooling reuses/reconnects and never kills what you started by hand.
   (`packages/ssh/src/tunnel.ts:438-591`)

## Browser testing — the finding that dents our differentiation
T3 Code's latest version has **"Preview Automation"**: agent-driven browser automation on
**Playwright** (`playwright-core@1.60.0`), exposed to the agent as **MCP tools** —
`preview_status/open/navigate/snapshot/click/type/press/scroll/evaluate/waitFor/resize/recordingStart/Stop`
(`apps/server/src/mcp/toolkits/preview/tools.ts`, contract `packages/contracts/src/previewAutomation.ts`).
Playwright is *injected into an embedded "collaborative browser tab"*
(`apps/desktop/src/preview/PlaywrightInjectedRuntime.ts`, `Manager.ts`), with a hosted-browser
webview for the web client (`apps/web/src/browser/hostedBrowserWebviewStyle.ts`).

That tool surface ≈ Playwright-MCP ≈ **our browser-mcp**. So **browser-mcp is not a unique
capability.** Our differentiation narrows to *where the browser lives and who can use it*:

| | T3 Preview Automation | our **browser-mcp** |
|---|---|---|
| Browser | Playwright **injected into an embedded webview** (preview of the app you're building) | a **real, full Chrome/Chromium** on your laptop (default browser, GPU, per-session isolated real contexts) |
| Coupling | Bound to their desktop/web app + preview UI | **Agent-agnostic MCP over the tailnet** — any MCP client on the VPS |
| Best at | Testing *the app under development*, collaboratively | General web automation in a real browser you own, GUI-agnostic |

**Steal from Preview Automation** (task #12): the **versioned operation protocol** + mixed-version
routing (`previewAutomation.ts` `PREVIEW_AUTOMATION_V1_OPERATIONS`); **tool capability annotations**
(`Readonly`/`Destructive`/`Idempotent`/`OpenWorld`); **click-to-annotate** human↔agent collaboration
(`apps/web/src/lib/previewAnnotation.ts`, `previewFocus.ts`); **recording artifacts** for
evidence/replay; and **viewport presets** for responsive testing.

## What we adopt — prioritized (→ tasks)
### Tier 1 (now; high impact, aligns with in-flight work)
- **browser-mcp: app-layer Bearer/HMAC auth + loopback-bind behind `tailscale serve`** — closes
  "any tailnet node can drive my browser." (task **#8**; mirrors `McpHttpServer.ts:29-89`,
  `SessionStore` sign/verify + revocation.)
- **`tailscale serve --https` instead of raw tailnet-IP HTTP** wherever a browser/PWA touches it.
  (folded into #8 and #11)
- **Attention-first agent notifications from the VPS** (approval/input/completion/failure, deep-link
  back), routed to phone via ntfy/Web Push. (task **#10**; model
  `apps/mobile/src/features/agent-awareness/*`.)

### Tier 2 (clear wins, moderate effort)
- **Idempotent hash-keyed launcher** for per-session browser servers (`managed`/`external`,
  readiness-vs-exit race + log-tail). (task **#9**)
- **Mobile = tailnet-served PWA behind `tailscale serve`** + **Tailscale Funnel** off-mesh fallback
  (behind app-auth) + snapshot-cache/durable-outbox resilience. (task **#11**) Validates keeping
  terminal-bridge desktop-only.
- **Reachability-tier endpoint model** (loopback→lan→tailnet→funnel; client picks best). (into #11)

### Tier 3 (architectural; if/when we build an agent control plane in the spec-014 engine)
- **Contract-first RPC** (Pydantic as our `effect/Schema`): one schema = wire + validator + type,
  per-call `payload/success/error/stream`, over one authed WebSocket.
  (`packages/contracts/src/rpc.ts:685`)
- **Event-sourced sessions** (Thread/Turn + snapshot-then-replay + dedup + checkpoint/rollback) for
  multi-agent resilience. (`apps/server/src/orchestration/*`)
- **Align browser-mcp to ACP** — model "give the agent a browser" as an ACP client-capability /
  extension (reuse `request_permission`/`session_update` shapes) *and* keep MCP, so it interoperates
  with any ACP agent. Generate bindings from pinned upstream. (`packages/effect-acp/*`)
- **Driver-as-value registry** if dev-boost ever fronts multiple agent CLIs.
  (`apps/server/src/provider/ProviderDriver.ts:119`)

## What NOT to adopt
- **Don't embed tsnet** — the system `tailscale` CLI is right; T3 (a mature product) shells out to it
  and never uses tsnet. Use `tailscale status --json` for MagicDNS/IP instead of hardcoding.
- **Don't adopt the Effect runtime / unstable APIs** — port the *patterns* to Python/Pydantic; their
  code rides pre-release Effect (`.repos/effect-smol`).
- **Don't build a hosted Worker relay** — our VPS *is* the always-on rendezvous. Any broker we add
  stays control-plane only, off the data path (`infra/relay/README.md:10`).
- **Don't rely on the tailnet ACL alone** — the exact model T3 refuses; layer app-auth on top.
- **Never put tokens in query/path** — URL **fragment** or `Authorization` header only.
  (`apps/server/src/startupAccess.ts:96`)

## Strategic read
T3 Code is a **coding-agent GUI**; it does not provision your box (dev-boost), and its browser
automation is an embedded preview, not a real browser you own (browser-mcp) — but on raw capability
its Preview Automation matches browser-mcp. Treat T3 Code as a **reference architecture** whose
hard-won transport/auth/resilience plumbing we lift, while our differentiation stays **own-your-infra:
a real browser on your own machine, agent-agnostic, over your own tailnet**, plus general shell
ergonomics (terminal-bridge). It is also a strong candidate to **self-host on the dev-boost VPS as a
GUI/mobile front-end** over the tailnet.
