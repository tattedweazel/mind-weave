# Deployment, network access, and Google OAuth

This document is the **single place** to choose how you expose Mind Weave (localhost, LAN, public hostname, or tunnel) and how that interacts with **Google OAuth**. Package READMEs link here for details.

**Related:** [backend README](../backend/README.md) (env table, Google OAuth setup), [frontend README](../frontend/README.md) (LAN walkthrough, `VITE_API_BASE`), [SECURITY_AUDIT.md](Audits/SECURITY_AUDIT.md).

---

## Quick pick

| Your goal | Use | Google OAuth from phones / other PCs? |
|-----------|-----|--------------------------------------|
| Develop on **one machine** only | **Path A — Localhost** (default) | Yes, with `localhost` / `127.0.0.1` redirect URIs in Google Cloud |
| Use the app on **same Wi‑Fi** by **LAN IP** (e.g. `192.168.x.x`) | **Path B — LAN IP** | **No** — Google does **not** allow redirect URIs with private IPs (`10.x`, `192.168.x`, etc.). Use **password login**, or Path C / D |
| **Google sign-in** from other devices using **your domain** | **Path C — Domain + HTTPS** | Yes — register **`https://your-api-host/...`** callbacks |
| No router access, **CGNAT**, or **cannot port-forward** | **Path D — Tunnel** | Yes — register the tunnel’s **public HTTPS** URL in Google |

**LM Studio** (or any local LLM) stays on the **machine running the backend** (`LMSTUDIO_BASE_URL` → `127.0.0.1`). Clients on other devices do not need to reach LM Studio unless you intentionally run the model server elsewhere.

---

## Path A — Localhost (default)

No extra deployment steps. From `backend/` run `uv run python -m fastapi dev app/main.py`; from `frontend/` run `npm run dev`. Defaults: API `http://localhost:8000`, SPA `http://localhost:5173`, `VITE_API_BASE=http://localhost:8000`.

- Setup detail: [backend README § Setup & Running](../backend/README.md#setup--running), [frontend README § Setup & Running](../frontend/README.md#setup--running).
- Google OAuth: register redirect URIs that match **`GOOGLE_REDIRECT_URI`** and **`GOOGLE_WORKFLOW_REDIRECT_URI`** in [config defaults](#canonical-oauth-paths-and-env) (typically `http://localhost:8000/...`).

---

## Path B — Same network (LAN IP)

Use this when browsers on **other PCs or phones** on the same trusted Wi‑Fi should open the app **without** a public domain. You bind the dev servers to all interfaces and align `CORS_ORIGINS`, `TRUSTED_HOSTS`, `FRONTEND_URL`, and `VITE_API_BASE` with the host’s **LAN IP**. The SPA supports **touch** on the workflow canvas (pan, pinch zoom, fit) and uses slide-over panels on small screens so the graph remains usable on phones (see [DESIGN_SYSTEM.md](DESIGN_SYSTEM.md) — narrow viewports).

- **Full walkthrough:** [frontend README — LAN / same-network devices](../frontend/README.md#lan--same-network-devices).

### Google OAuth on LAN (important)

**Google Cloud Console will not accept** redirect URIs whose host is a **private IP address** (RFC 1918, e.g. `10.0.0.1`, `192.168.1.42`). The console error *“must end with a public top-level domain”* reflects that policy—not a bug in Mind Weave.

**On LAN you can:**

- Use **username / password login** (same account you use with Google on localhost, if you created it with a password), **or**
- Move to **Path C** (your domain) or **Path D** (tunnel) so redirect URIs use an **HTTPS URL with an acceptable hostname**.

Do **not** expect `http://10.x.x.x:8000/...` or `http://192.168.x.x:8000/...` to be registrable in Google for Web OAuth clients.

---

## Path C — Your own domain (HTTPS)

Use when you own a domain (e.g. `example.wtf`) and want **Google OAuth** from arbitrary devices. You need:

1. A **public hostname** for the API (and usually a separate hostname for the SPA).
2. **HTTPS** in front of the API (and SPA) — Google expects secure redirects for non-localhost hosts.
3. **DNS** pointing at something reachable from the internet (your home public IP, a VPS, or tunnel endpoint).
4. **Exact** redirect URIs in Google Cloud matching **`GOOGLE_REDIRECT_URI`** and **`GOOGLE_WORKFLOW_REDIRECT_URI`**.

### Suggested hostnames

Mind Weave uses **cookie-based auth** with `credentials: include`; the SPA origin must appear in **`CORS_ORIGINS`**. A common pattern:

- **`api.example.com`** — reverse proxy → `http://127.0.0.1:8000` (FastAPI).
- **`app.example.com`** — reverse proxy → Vite dev (`5173`) **or** static files from `npm run build`.

Replace `example.com` with your domain throughout.

### Operator checklist (domain + home server)

Use this when the API runs on a machine behind a **home router** with a **public IP** (or dynamic DNS).

- [ ] **DNS (registrar):** Create **A** records: `api.yourdomain.tld` and `app.yourdomain.tld` → your **public** WAN IPv4 (use your registrar’s docs). If your ISP changes IP often, use dynamic DNS or a short TTL.
- [ ] **Router:** Forward **TCP 443** (HTTPS) from WAN → the machine running **nginx** (or another reverse proxy). Forward **TCP 80** too if you use Let’s Encrypt **HTTP-01** on that box. (Do **not** expose raw `uvicorn` on 8000 to the public internet without TLS and a threat model—use the proxy.)
- [ ] **TLS:** Install **nginx** on that machine; terminate HTTPS and proxy to localhost. Example server blocks: [examples/nginx/mind-weave.conf.example](examples/nginx/mind-weave.conf.example). Obtain certificates with **Certbot** ([certbot.eff.org](https://certbot.eff.org/)) once DNS resolves and **80/443** reach this host—e.g. `certbot --nginx` with your `api` / `app` hostnames, or your OS package (`python3-certbot-nginx` on Debian/Ubuntu). Certbot may adjust your `:80` config for challenges; keep `nginx -t` clean after changes.
- [ ] **Backend `.env`:** Set **`BEHIND_REVERSE_PROXY=true`** so FastAPI trusts **`X-Forwarded-Proto`** (and related headers) from nginx on `127.0.0.1`. Without this, `request.url` and similar may still see `http` behind TLS.
- [ ] **nginx `client_max_body_size`:** Default **1m** breaks **Voice Sample Manager** saves (**`POST /api/v1/voice-samples/`** with base64 WAV) and runtime **Audio File Input** uploads. Raise it above the largest app upload cap on the API host (e.g. **100m** for the default **75 MiB** STT cap, as in [examples/nginx/mind-weave.conf.example](examples/nginx/mind-weave.conf.example)); otherwise the browser may report a **CORS** error because **413** responses from nginx often lack **`Access-Control-Allow-Origin`**.
- [ ] **Google Cloud Console** → APIs & Services → Credentials → your **OAuth 2.0 Web client**:
  - [ ] **Authorized JavaScript origins:** `https://app.yourdomain.tld` (and `http://localhost:5173` if you still dev locally with Google).
  - [ ] **Authorized redirect URIs** (must match env **exactly**):
    - `https://api.yourdomain.tld/api/v1/auth/google/callback`
    - `https://api.yourdomain.tld/api/v1/google-workflow/oauth/callback`
- [ ] **Backend `.env`:** Set `GOOGLE_REDIRECT_URI`, `GOOGLE_WORKFLOW_REDIRECT_URI`, `FRONTEND_URL`, `CORS_ORIGINS`, `TRUSTED_HOSTS` — see [domain env snippet](examples/env/domain.env.example) and [Canonical OAuth paths](#canonical-oauth-paths-and-env).
- [ ] **Frontend `frontend/.env`:** `VITE_API_BASE=https://api.yourdomain.tld` (no `/api/v1`). Rebuild or restart Vite after changes.
- [ ] **Restart** the API after changing `.env`. For production-like `APP_ENV`, use a strong `SECRET_KEY` (32+ chars); see [backend README](../backend/README.md#environment-variables).

### macOS (Homebrew) — nginx and Certbot

Use this when the machine that receives **80/443** is a Mac:

1. **Install:** `brew install nginx certbot` (or `certbot` via pip/OS package if you prefer).
2. **Paths:** Homebrew uses **`$(brew --prefix)/etc/nginx/`** (often `/opt/homebrew/etc/nginx` on Apple Silicon, `/usr/local/etc/nginx` on Intel). The default `nginx.conf` may **`include servers/*.conf`** — drop your adapted [mind-weave.conf.example](examples/nginx/mind-weave.conf.example) there, or merge the `server` blocks manually.
3. **Test and run:** `sudo nginx -t`, then `brew services start nginx` (or `sudo nginx` for a one-off). Reload after edits: `brew services restart nginx` or `sudo nginx -s reload`.
4. **Certbot with nginx:** e.g. `sudo certbot certonly --nginx -d api.yourdomain.tld -d app.yourdomain.tld` once **80** reaches this host and DNS is correct. Point `ssl_certificate` paths in the server blocks at what Certbot prints (often one SAN certificate under `live/`).
5. **Upstream processes:** Run FastAPI on **`127.0.0.1:8000`** and Vite on **`127.0.0.1:5173`** (or serve `frontend/dist` via the optional static block in the example). Only **nginx** should listen on **443** publicly.

Linux (Debian/Ubuntu) continues to use `/etc/nginx/sites-available` / `sites-enabled` as in the example file comments.

### nginx `proxy_pass` and `{"detail":"Not Found"}` (or Safari `login.json`)

If nginx **rewrites** the request URI so uvicorn sees paths **without** the `/api/v1` prefix (for example `proxy_pass http://127.0.0.1:8000/` with a trailing slash, or a `location /api/` block that strips the prefix), FastAPI returns **404** JSON `{"detail":"Not Found"}`. Mobile Safari may suggest saving that body as **`login.json`** because the path often ends in `login`.

**Fix:** For the **`api`** `server` block, use **`location / { proxy_pass http://127.0.0.1:8000; }`** — **no** URI path after the port (see [mind-weave.conf.example](examples/nginx/mind-weave.conf.example)).

**Verify from a shell:** `curl -sI https://api.yourdomain.tld/api/v1/health` → **200**. Then `curl -sI https://api.yourdomain.tld/api/v1/auth/google/login` → **302** with `Location:` pointing at `accounts.google.com` (or **307**). (`curl -I` sends **HEAD**, not GET; these routes accept HEAD so standard probes match what you expect. If you ever see **405**/**404** on `-I` only, try `curl -sS -D - -o /dev/null` without `-I` to send GET.)

### **502 Bad Gateway** from nginx

nginx is configured to **`proxy_pass http://127.0.0.1:8000`**. If uvicorn is started with **`--host <LAN_IP>`** only (e.g. `10.0.0.x`), it does **not** listen on **`127.0.0.1`**, so nginx’s upstream connection fails → **502**. Use **`--host 127.0.0.1`** or **`--host 0.0.0.0`** for the API. Confirm with `curl http://127.0.0.1:8000/api/v1/health` → **200**.

### “Invalid host header” (or Safari `login.txt`)

If the API is reached as **`https://api.yourdomain.tld`** but **`TRUSTED_HOSTS`** only lists `localhost` / a LAN IP, **`Host: api.yourdomain.tld`** is rejected → **400** with body **`Invalid host header`**. Add **`api.yourdomain.tld`** (the **API** hostname only, not `app.…`) to **`TRUSTED_HOSTS`** in **`backend/.env`** and restart uvicorn. Same pattern as [backend README — Troubleshooting](../backend/README.md#invalid-host-header-browser-or-logintxt-on-apiv1authgooglelogin).

### Hairpin NAT

Some home routers **cannot** route from a LAN client to its own public IP (NAT loopback). Symptom: **phone on Wi‑Fi** fails to load `https://app.yourdomain.tld` while **cellular** works. Try another device, fix router “NAT loopback,” use **split DNS** on the LAN, or test from cellular.

### When you cannot port-forward

If you **cannot** open **443** on the router (no admin rights, carrier-grade NAT, etc.), **Path D** is the practical option for OAuth.

---

## Path D — Tunnel (no port forwarding)

Use a **tunnel** (e.g. **Cloudflare Tunnel**, **ngrok**, similar) to obtain an **HTTPS URL** on a public hostname **without** router port forwarding. You register that **HTTPS origin** in Google Cloud and point your env at it.

**Checklist (tunnel):**

- [ ] Create an account and install the tunnel client per vendor docs.
- [ ] Obtain a **stable HTTPS URL** (e.g. `https://your-name.ngrok-free.app` or a Cloudflare Tunnel hostname).
- [ ] Route tunnel traffic to **`127.0.0.1:8000`** (API) and, if needed, a second route or path for the SPA—or run both behind one reverse proxy on localhost first.
- [ ] Add **Authorized JavaScript origins** and **Authorized redirect URIs** in Google using the **same** `https://` host(s) you expose through the tunnel.
- [ ] Set Mind Weave env vars to match; restart processes.

**Security:** A tunnel exposes whatever you forward to the **internet**. Use strong secrets, consider `OPEN_REGISTRATION=false` for anything beyond a personal lab, and read [SECURITY_AUDIT.md](Audits/SECURITY_AUDIT.md). Prefer **HTTPS** tunnel endpoints; avoid exposing unauthenticated dev-only tools.

---

## Canonical OAuth paths and env

Defaults from [`backend/app/core/config.py`](../backend/app/core/config.py) (paths are fixed; only **origin** changes):

| Purpose | Path (append to API origin) |
|---------|-----------------------------|
| Sign-in / account linking | `/api/v1/auth/google/callback` |
| Gmail / Calendar workflow OAuth | `/api/v1/google-workflow/oauth/callback` |

**Example** if API origin is `https://api.example.com`:

```env
GOOGLE_REDIRECT_URI=https://api.example.com/api/v1/auth/google/callback
GOOGLE_WORKFLOW_REDIRECT_URI=https://api.example.com/api/v1/google-workflow/oauth/callback
FRONTEND_URL=https://app.example.com
```

**`CORS_ORIGINS`** must include the SPA origin (`https://app.example.com`). **`TRUSTED_HOSTS`** must include the **API** hostname only: `api.example.com` (no `https://`, no port). **`VITE_API_BASE`** = `https://api.example.com`.

Full env table: [backend README — Environment Variables](../backend/README.md#environment-variables).

---

## Security reminders (all paths)

- **Do not** expose raw `fastapi dev` or `vite` to the **public internet** without TLS and a clear threat model; use a **reverse proxy** and **HTTPS** for public hostnames.
- Use a **strong `SECRET_KEY`** outside `APP_ENV=local`; never commit real `.env` files.
- Restrict **`OPEN_REGISTRATION`** on any deployment reachable from untrusted networks.
- **Firewall** the host: only **443** (and **80** if needed for ACME) from the internet to the proxy; **LM Studio** should stay on localhost unless you intend otherwise.
- Deeper review: [SECURITY_AUDIT.md](Audits/SECURITY_AUDIT.md).

## Outbound network requirements (cloud STT)

The provider-abstracted **`transcribe_file`** skill (see [WORKFLOW_SKILLS.md](WORKFLOW_SKILLS.md#transcribe-file-provider-abstracted--skill-transcribe_file) and [OPERATIONS.md](OPERATIONS.md#speech-transcription-providers-transcribe_file)) needs **outbound HTTPS** when an operator opts into a cloud provider:

| Provider | Outbound destinations | Notes |
|----------|-----------------------|-------|
| `local_whisper` | None (uses the local STT bridge sidecar) | Audio never leaves your server. |
| `assemblyai` | **`api.assemblyai.com:443`** by default — override with **`ASSEMBLYAI_BASE_URL`**. Audio is uploaded to **`/v2/upload`**, the transcript job is created at **`/v2/transcript`**, and the API polls **`/v2/transcript/{id}`**. The host AssemblyAI itself uses for storage may also be contacted depending on their backend. | Outbound TLS only; no inbound port required. Egress firewalls / proxies must allow this host. |

Cloud STT is listed in the editor by default (`assemblyai` is in **`TRANSCRIPTION_PROVIDERS_ENABLED`**); actual **outbound HTTPS** happens only when a run uses that provider. End users still need a personal API key under **My Settings → API Settings** (`assemblyai`); a server-wide **`ASSEMBLYAI_API_KEY`** is only consulted as a fallback. Operators who must not show cloud STT in the UI can set **`TRANSCRIPTION_PROVIDERS_ENABLED=["local_whisper"]`**.

---

## Files in this repo

| Artifact | Purpose |
|----------|---------|
| [examples/nginx/mind-weave.conf.example](examples/nginx/mind-weave.conf.example) | nginx server blocks for `api.` + `app.` → localhost (TLS placeholders + Certbot notes) |
| [examples/env/domain.env.example](examples/env/domain.env.example) | Backend + frontend env **snippets** for HTTPS deployment (`BEHIND_REVERSE_PROXY`, `APP_ENV`, `DEV_HMR_HOST`, etc.) |
| [backend/.env.example](../backend/.env.example) | Full env template (JSON lists for `CORS_ORIGINS`, etc.) |

Container orchestration (Docker Compose, Kubernetes) is not required for Mind Weave; you can add your own layer on top of the same env and proxy model.
