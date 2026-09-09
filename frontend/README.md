# Frontend

See the repository [setup guide](../README.md) for runtime versions and API setup.

```powershell
npm.cmd ci
npm.cmd run dev
npm.cmd run verify
```

Verification runs TypeScript, ESLint, and the production build. Optional public API configuration is in `.env.example`. No frontend unit tests exist yet.
