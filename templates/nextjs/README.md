# Next.js / React project template

Web stack runtimes (Node 22, pnpm, bun) and fresh language intelligence
(TypeScript, ESLint, Tailwind CSS LSP + prettier formatter) are provisioned by
the `web` profile. Scaffold a new app with either package manager:

## pnpm

```sh
pnpm create next-app@latest my-app
cd my-app
pnpm dev
```

## bun

```sh
bun create next-app my-app
cd my-app
bun dev
```

`.fresh/config.json` here sets a 2-space tab and wires the `prettier` formatter
so JS/TS files format on save inside the fresh editor.
