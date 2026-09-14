# Warden UI

The dashboard page the `warden` plugin ships. Otari serves the built
bundle at `/plugins/warden/ui/` and the dashboard iframes it, so the page
authenticates its API calls with the dashboard session cookie and routes with
hash history.

```bash
pnpm install
pnpm dev      # SPA only; API calls proxy to http://localhost:8000 (OTARI_DEV_API to override)
pnpm lint     # tsc --noEmit
pnpm build    # writes ../src/otari_warden/static, which is committed
```

Rebuild and commit `src/otari_warden/static/` whenever `web/src` changes.
