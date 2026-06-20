# Laravel project template (ddev)

This directory is a starting point for a **container-based Laravel project** driven
by [ddev](https://ddev.com). The host has only the `ddev` orchestrator — PHP,
Composer, the web server and the database all run inside ddev's containers, so the
host stays clean and the toolchain is reproducible.

Language intelligence (PHP **intelephense**) is provisioned globally for the
[fresh](https://github.com/sinelaw/fresh) editor by the `laravel-lsp` module. The
PHP **formatter** is [Laravel Pint](https://laravel.com/docs/pint), which is a
*per-project* composer dev-dependency — `.fresh/config.json` here wires the
formatter to `vendor/bin/pint`, run inside the container via `ddev`.

## Create a new Laravel project

From an empty project directory:

```sh
# 1. Configure the ddev project (Laravel uses the `public/` web root).
ddev config --project-type=laravel --docroot=public

# 2. Scaffold Laravel inside the container (installs PHP + Composer deps there).
ddev composer create laravel/laravel

# 3. Start the containers (web + db) and trust the local HTTPS cert.
ddev start
```

`ddev start` prints the local URL (e.g. `https://<project>.ddev.site`). Common
follow-ups all run inside the container:

```sh
ddev artisan migrate          # run migrations
ddev composer require <pkg>   # add a dependency
ddev exec vendor/bin/pint     # format PHP (same command the editor uses)
```

## Formatting

`.fresh/config.json` sets the PHP formatter to `vendor/bin/pint` executed through
`ddev exec`, so `format_on_save` uses the project's pinned Pint version rather than
anything on the host. Pint itself comes from Laravel's default `composer.json`
dev-dependencies; add it explicitly with `ddev composer require --dev laravel/pint`
if your project does not already include it.
