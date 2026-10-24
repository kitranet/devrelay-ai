# Windows local hosting and production preflight

This runbook is for a local Windows installation of DevRelay AI. It does not create a tunnel, configure Cloudflare, change Windows power settings, or authorize public access. Keep both application listeners on loopback. The Linux Nginx/systemd templates in `deploy/` are for Linux hosts and do not configure Windows services.

## Current local preflight status

The Phase 8C.1 assessment found Python 3.12.10, Node.js 24.20.0, and npm 11.19.0. At that time, ports 3000, 8001, and 8002 had no listeners; no `cloudflared` executable, process, or matching Windows service was found; and `.devrelay-state` did not exist. The active Balanced power plan sleeps after five minutes on AC and three minutes on battery. Firewall profile inspection was unavailable to the assessment process. These are observations, not proof about Cloudflare account-side routes or other laptop applications.

## Development versus production

| Mode | Frontend | Backend | Use |
|---|---|---|---|
| Development | `next dev --webpack --hostname 127.0.0.1 --port 3000` | Uvicorn with `--reload --host 127.0.0.1 --port 8001` | Local code iteration only. Never route a public tunnel to the dev server. |
| Production preflight | Run `next build --webpack`, then `next start --hostname 127.0.0.1 --port 3000` | Uvicorn with `--host 127.0.0.1 --port 8001 --workers 1`, without reload | Validate the production frontend locally. This is not a production security certification or an unattended Windows service. |

Next.js defaults to listening on `0.0.0.0` unless a hostname is explicitly supplied. Always pass `--hostname 127.0.0.1` to both `next dev` and `next start`. Mock inference is the backend default. Explicitly set `INFERENCE_PROVIDER=mock` and `NEBIUS_LIVE_INFERENCE_ENABLED=false` for local preflight. Never place `NEBIUS_API_KEY` in frontend variables, `NEXT_PUBLIC_*`, command output, or the repository.

## One-time local prerequisites

From PowerShell, in the repository root:

```powershell
Set-Location C:\DevRelay-AI
python --version
node --version
npm.cmd --version
```

Install dependencies only if the project environment is not already prepared. Do not overwrite an existing `.env` or `frontend/.env.local` from an example file. For an existing project-local virtual environment, use its Python executable directly; activate it only if desired.

```powershell
if (-not (Test-Path .venv\Scripts\python.exe)) { python -m venv .venv }
if (-not (Test-Path .venv\Scripts\python.exe -PathType Leaf)) { throw 'Project virtual environment is unavailable.' }
```

If dependencies must be installed in a newly created environment, use the repository's declared development extra (`.venv\Scripts\python.exe -m pip install -e ".[dev]"`) and `npm.cmd ci` in `frontend/`. These commands are not needed when dependencies already exist. Keep the virtual environment, `node_modules`, `.next`, `.env` files, SQLite databases, logs, and credential material out of Git; `.gitignore` already excludes these local items.

## Local production-mode startup

Use two separate PowerShell windows. These are foreground processes; each window shows that process's sanitized application/server logs. The variables are scoped to each process window and are not written to `.env` files.

### 1. Start FastAPI

In the first window:

```powershell
Set-Location C:\DevRelay-AI
$env:ENVIRONMENT = 'production'
$env:INFERENCE_PROVIDER = 'mock'
$env:NEBIUS_LIVE_INFERENCE_ENABLED = 'false'
$env:NEBIUS_API_KEY = ''
$env:NEBIUS_TOTAL_INFERENCE_QUOTA = '0'
$env:AUTHORIZED_REPOSITORIES = '{"planning-fixture":"C:/DevRelay-AI/tests/fixtures/planning_repo"}'
$env:ENABLE_LOCAL_REVIEWS = 'false'
$env:ENABLE_ISOLATED_RUNTIME_VALIDATION = 'false'
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001 --workers 1
```

Health is `http://127.0.0.1:8001/health`. Interactive API documentation is `http://127.0.0.1:8001/docs`; keep it local and do not tunnel it. The backend is intentionally unauthenticated and must not be bound to a LAN/public address.

### 2. Build and start the production Next.js server

In a second window, use a temporary test-only credential for local checks. The password must be at least 16 characters. Do not use a real judge or account password for this preflight. `Get-Credential` prompts interactively; do not print the password or put it into a saved command/script.

```powershell
$preflightCredential = Get-Credential -UserName 'local-preflight' -Message 'Enter a temporary test-only password (16+ characters)'
$env:DEMO_AUTH_USERNAME = $preflightCredential.UserName
$env:DEMO_AUTH_PASSWORD = $preflightCredential.GetNetworkCredential().Password
$env:DEMO_AUTH_ORIGIN = 'http://127.0.0.1:3000'
$env:BACKEND_API_URL = 'http://127.0.0.1:8001'
$env:NEXT_PUBLIC_REPOSITORY_IDS = 'planning-fixture'
$env:NEXT_PUBLIC_LOCAL_REVIEWER_ID = 'local-preflight'
$env:NEXT_PUBLIC_EXECUTION_AUTHORIZER_ID = 'local-preflight'
Set-Location C:\DevRelay-AI\frontend
npm.cmd run build
npm.cmd run start -- --hostname 127.0.0.1 --port 3000
```

The exact local origin matters: unsafe browser requests are accepted only when `Origin` exactly matches `DEMO_AUTH_ORIGIN`. Use `http://127.0.0.1:3000`, not `localhost`, for this example. Process environment variables take precedence over local `.env` files. Do not inspect or overwrite an existing `.env.local`; do not include any secrets in `NEXT_PUBLIC_*` settings.

Open `http://127.0.0.1:3000` in a browser and enter the temporary credential when challenged. After the preflight, press `Ctrl+C` in each window. In the frontend window, clear only the temporary values:

```powershell
'DEMO_AUTH_USERNAME','DEMO_AUTH_PASSWORD','DEMO_AUTH_ORIGIN','BACKEND_API_URL',
'NEXT_PUBLIC_REPOSITORY_IDS','NEXT_PUBLIC_LOCAL_REVIEWER_ID','NEXT_PUBLIC_EXECUTION_AUTHORIZER_ID' |
  ForEach-Object { Remove-Item "Env:$_" -ErrorAction SilentlyContinue }
```

In the backend window, use the same pattern for `ENVIRONMENT`, `INFERENCE_PROVIDER`, `NEBIUS_LIVE_INFERENCE_ENABLED`, `NEBIUS_API_KEY`, `NEBIUS_TOTAL_INFERENCE_QUOTA`, `AUTHORIZED_REPOSITORIES`, `ENABLE_LOCAL_REVIEWS`, and `ENABLE_ISOLATED_RUNTIME_VALIDATION`. Never use `setx` for one-session preflight credentials.

## Start, stop, health, and recovery

- Start FastAPI first, then Next.js. Keep one terminal per foreground process.
- Stop Next.js and FastAPI with `Ctrl+C` in their respective terminals. There is no tunnel to stop in this local-only phase.
- Check backend health with `Invoke-RestMethod http://127.0.0.1:8001/health`. The response should be `status: ok`.
- Check listener address and owner without dumping process command lines:

  ```powershell
  Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
    Where-Object { $_.LocalPort -in 3000,8001 } |
    ForEach-Object {
      $owner = Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue
      [pscustomobject]@{ Address=$_.LocalAddress; Port=$_.LocalPort; PID=$_.OwningProcess; Name=$owner.ProcessName; Executable=$owner.Path }
    }
  ```

  Both application addresses must be `127.0.0.1`. Do not terminate a PID unless its executable and port identify the DevRelay process you started.
- If a process crashes during this manual preflight, its terminal reports the exit. Restart only that process using the same configuration in the same window. The other service may return a sanitized unavailable response while FastAPI is down. This manual procedure does not recover automatically after logoff, reboot, Windows Update, or a terminal closing.
- The backend configures structured application logs without authorization headers, prompts, full provider bodies, or credentials. Keep each terminal private; do not enable HTTP debug tracing or environment dumps. Logs are not persisted or rotated by this preflight. An unattended host needs a separately reviewed Windows service/task design with restricted log-directory ACLs and rotation; none is installed here.

## Local security checks

Perform these checks only while the two local production processes are running. Use the browser's temporary Basic Auth prompt; do not put credentials in URLs or logs.

1. Unauthenticated `GET http://127.0.0.1:3000/` must return `401`.
2. Authenticated dashboard access at the exact origin must return the page.
3. Unauthenticated `GET http://127.0.0.1:3000/api/backend/health` must independently return `401`; authenticated access should return the FastAPI health JSON.
4. The dashboard API proxy forwards only its allowlisted routes and only JSON content headers/body; it does not forward the browser `Authorization` header to FastAPI. The Vitest proxy tests cover this boundary.
5. An unauthenticated or wrong-Origin `POST` through `/api/backend/api/v1/repositories/analyze` must be denied (`401` for missing authentication; `403` for missing/wrong `Origin`). With valid temporary Basic Auth and `Origin: http://127.0.0.1:3000`, analysis of `planning-fixture` should succeed. A different repository ID must be rejected.
6. Confirm listeners on `127.0.0.1:3000` and `127.0.0.1:8001`; no DevRelay listener should use `0.0.0.0` or a LAN address. Confirm the frontend inference status says `provider=mock`, `live_inference_enabled=false`, and quota is not enabled/available for paid calls.
7. Confirm local reviews are disabled and runtime validation reports disabled/unavailable. No runtime code executes: the configured executor fails closed. Proposal generation creates only the fixed synthetic diff in memory; no endpoint applies it. Keep the fixture unchanged.

The automated backend tests include quota storage failure behavior, provider isolation, mock behavior, and execution/review restrictions. A full live server check of a deliberately unwritable Windows SQLite path is not required for this mock-only preflight; do not point the live quota database at a real or sensitive path merely to induce an error. If an explicitly configured quota DB cannot be opened, Nebius reservation fails closed and the request is not sent.

## Safe quota storage and secret handling

The SQLite quota tracks reserved request counts, not dollars. It is not created until quota/status administration needs it. The default `.devrelay-state/nebius-quota.sqlite3` is Git-ignored; for hosted operation, prefer a stable local NTFS path outside the checkout, such as `C:\ProgramData\DevRelay\state\nebius-quota.sqlite3`, and restrict its parent directory to the backend service identity and administrators. Keep it off OneDrive/network shares. The application creates the parent directory when initializing the DB; check and configure NTFS ACLs before using it. A DB path/permission failure blocks live inference. Initial `NEBIUS_TOTAL_INFERENCE_QUOTA` applies only when the database is first created; later changes use `scripts.inference_quota_admin` with the exact same `NEBIUS_QUOTA_DB_PATH`. A request-count allowance is not a cost ceiling.

For a separately approved future live-inference setup, first create the state directory and grant access only to the Windows account that will run FastAPI and administrators. Then initialize and verify the request counter while inference is still disabled:

```powershell
Set-Location C:\DevRelay-AI
$env:INFERENCE_PROVIDER = 'mock'
$env:NEBIUS_LIVE_INFERENCE_ENABLED = 'false'
$env:NEBIUS_QUOTA_DB_PATH = 'C:\ProgramData\DevRelay\state\nebius-quota.sqlite3'
$env:NEBIUS_TOTAL_INFERENCE_QUOTA = '1'
.\.venv\Scripts\python.exe -m scripts.inference_quota_admin show
```

The `show` command creates the database on first use using the initial total and prints only request counts. Confirm `total=1`, `used=0`, and `remaining=1`. Keep the same database path for the API process and operator command. Do not initialize or reset quota during this mock-only Phase 8C.1 preflight.

Live inference must remain disabled for this phase. When a separately authorized future live test requires initializing quota, set an explicit small allowance with the local admin command while `INFERENCE_PROVIDER=mock` and the live kill switch is false. Verify the DB path and remaining count locally before separately enabling the provider and kill switch. Do not reset/delete the database to restore quota, and do not assume promotional credit caps charges.

Store future backend secrets in a protected secret mechanism or a file accessible only to the backend identity. Keep the frontend process under a different restricted identity if hosting, so its environment cannot read the backend secret. Do not use frontend `.env.local` for `NEBIUS_API_KEY`, do not commit real `.env` files, and do not print credential-bearing process environments or command lines.

## Sleep and power management

Read settings without changing them:

```powershell
powercfg /getactivescheme
powercfg /query SCHEME_CURRENT SUB_SLEEP
```

At this assessment, sleep is five minutes on AC and three minutes on battery. For an explicitly approved hosting window, keep the laptop connected to AC and use **Settings → System → Power & battery → Screen and sleep** to set “When plugged in, put my device to sleep after” to **Never**. Leave the battery setting unchanged. Lock the screen; do not log off, because this manual command-window setup is tied to the user session. Restore the prior plugged-in setting to **5 minutes** after the window; the battery setting should remain **3 minutes**. Re-run the read-only `powercfg` commands to confirm restoration. This power-plan change is not performed by this runbook.

## Cloudflare Tunnel proposal (not created)

The proposed path is `Judge → HTTPS/Cloudflare Access → named Cloudflare Tunnel → http://127.0.0.1:3000 → Next.js allowlisted proxy → http://127.0.0.1:8001`. FastAPI stays loopback-only. Do not configure a route to port 8001, `/docs`, SSH, or any other service. A Cloudflare Tunnel uses outbound connections; do not add inbound firewall rules for the application. Network policy may need outbound TCP or UDP 7844 for `cloudflared`.

Prerequisites and proposed order:

1. Cloudflare account and a domain managed by Cloudflare are required for a named published application. The registrar need not necessarily change; DNS authority must be configured as Cloudflare requires. Confirm domain access and renewal cost first.
2. Create a Cloudflare Zero Trust organization and a self-hosted Access application for exactly one hostname. Before publishing that hostname, create an Allow policy with an explicit list of judge email addresses and require email One-time PIN. Do not configure an OTP-only Include rule, broad email domain, or Bypass policy.
3. After separate external-exposure approval, create a remotely managed/named Tunnel and publish exactly one route from the hostname to `http://127.0.0.1:3000`. Configure a catch-all/404 for unmatched hostnames and review every route attached to the tunnel.
4. Retain DevRelay Basic Authentication as a second gate. Set `DEMO_AUTH_ORIGIN` to the exact HTTPS origin, e.g. `https://demo.example.org`. Verify that requests preserve the browser's `Origin`, that POSTs from the correct origin work, and that missing/wrong origins remain blocked. Verify Access OTP and Basic Auth do not conflict in the supported browsers.
5. Store the tunnel token/credentials outside Git in a directory protected by Windows ACLs for the tunnel service identity and administrators. Treat the token as a bearer secret. Do not paste it into a public issue, README, screenshot, or shell history.
6. From an independent network, test denied unlisted emails, allowed judge OTP, Basic Auth, auth on application/API routes, correct and rejected Origins, all approved proxy paths, synthetic repository only, no access to port 8001, no access to unrelated hostnames/services, and shutdown/route removal. Confirm no process listens on non-loopback addresses.

Cloudflare currently publishes a Zero Trust Free tier for teams under 50 users, but free service has no uptime SLA. A domain may cost money if not already owned. The laptop, power, ISP, app processes and the Nebius account remain separate availability/cost dependencies. Do not use a Quick Tunnel as the final judge route; it is intended for temporary development and creates a random URL. Cloudflare Access OTP verifies control of an email inbox, not a real-world judge identity. The app's reviewer labels remain unverified.

## External-access gate

External access remains disabled until all of these have been reviewed and pass: corrected setup instructions; local production build/start; both loopback listener checks; authenticated dashboard and proxy checks; successful and rejected Origin tests; one configured synthetic repository; mock provider and disabled live kill switch; protected/stable quota storage; production process restart/recovery; Cloudflare Access email allow-list and OTP; exactly one published Next.js route; external tests of auth and backend isolation; a tested shutdown/incident procedure; and explicit human approval to publish the hostname. Do not expose the application just because the tunnel itself uses HTTPS.
