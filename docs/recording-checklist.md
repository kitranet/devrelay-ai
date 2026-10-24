# Windows recording checklist

This checklist produces a local, authenticated recording with the production Next.js frontend and a development-mode FastAPI backend so the local human-review controls can be shown. Both bind only to loopback. The provider is explicitly mock, Nebius calls are disabled, the only authorized repository is the synthetic fixture, and runtime validation remains disabled. This setup is for recording only; it is not public hosting or a judge-accessible deployment.

## Before recording

1. Confirm the repository is on the intended branch and has no unrelated changes. Do not record Git credentials, terminals containing secrets, `.env` files, or personal email/browser tabs.
2. Close unrelated tabs and windows. Use only `http://127.0.0.1:3000` (not `localhost`) so it matches the configured origin.
3. Keep the synthetic fixture unchanged. Do not configure another repository.
4. Choose the mock walkthrough. Never set `INFERENCE_PROVIDER=nebius` for this recording.

## Start FastAPI

Open a **new, dedicated PowerShell window** for this recording, paste these commands, and leave the window open. This uses development mode solely because local review decisions are restricted to development; Uvicorn itself runs without auto-reload. The empty API-key override ensures this backend process has no Nebius credential.

```powershell
Set-Location C:\DevRelay-AI
$env:ENVIRONMENT = 'development'
$env:INFERENCE_PROVIDER = 'mock'
$env:NEBIUS_LIVE_INFERENCE_ENABLED = 'false'
$env:NEBIUS_API_KEY = ''
$env:AUTHORIZED_REPOSITORIES = '{"planning-fixture":"C:/DevRelay-AI/tests/fixtures/planning_repo"}'
$env:ENABLE_LOCAL_REVIEWS = 'true'
$env:ENABLE_ISOLATED_RUNTIME_VALIDATION = 'false'
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001 --workers 1
```

## Build and start the production dashboard

Open a second **new, dedicated PowerShell window**. `Get-Credential` prompts for a temporary recording-only password. Choose at least 16 characters; do not reuse a personal, organization, or judge password. The password is held only in this window's process environment and is not put in the command text or source files.

```powershell
$recordingCredential = Get-Credential -UserName 'local-recording' -Message 'Enter a temporary recording-only password (16+ characters)'
$env:DEMO_AUTH_USERNAME = $recordingCredential.UserName
$env:DEMO_AUTH_PASSWORD = $recordingCredential.GetNetworkCredential().Password
$env:DEMO_AUTH_ORIGIN = 'http://127.0.0.1:3000'
$env:BACKEND_API_URL = 'http://127.0.0.1:8001'
$env:NEXT_PUBLIC_REPOSITORY_IDS = 'planning-fixture'
$env:NEXT_PUBLIC_LOCAL_REVIEWER_ID = 'demo_reviewer'
$env:NEXT_PUBLIC_EXECUTION_AUTHORIZER_ID = 'local_authorizer'
$env:NEXT_TELEMETRY_DISABLED = '1'
Set-Location C:\DevRelay-AI\frontend
npm.cmd run build
npm.cmd run start -- --hostname 127.0.0.1 --port 3000
```

Keep the environment in this window until after the dashboard is stopped. Next.js loads the build environment and the running process environment; the settings above are intentionally explicit. Never put a key in `NEXT_PUBLIC_*`.

## Check before capture

In a third PowerShell window:

```powershell
Invoke-RestMethod http://127.0.0.1:8001/health
Get-NetTCPConnection -State Listen |
  Where-Object LocalPort -in 3000, 8001 |
  Select-Object LocalAddress, LocalPort, OwningProcess
```

Both listener addresses must be `127.0.0.1`. If either is `0.0.0.0`, a LAN address, or owned by an unexpected process, stop and investigate; do not record or expose it. In a browser, open `http://127.0.0.1:3000`, authenticate with the temporary credential, and confirm the dashboard responds. Confirm the provider reads **Mock** and live inference is disabled. The browser Basic Auth prompt should be completed before screen recording starts so the credential entry is not captured.

## Record the walkthrough

1. Open Clipchamp and choose **Create new → Screen recording** (or the equivalent screen-recording option in the installed Clipchamp version). Select only the browser window, not the entire desktop, and choose the intended microphone. If prompted, allow microphone access. Do a short test recording and listen to it.
2. Start the capture only after the browser is authenticated and the dashboard shows `planning-fixture`, connected backend, and mock provider. Keep the browser at 100% zoom or adjust until the page is readable.
3. Follow the timestamps in [phase-8d-video-script.md](phase-8d-video-script.md). Analyze the repository, generate the exact calculator plan, show its citations, create the deterministic proposal, record an **Approve for consideration** decision with a brief non-sensitive justification, and generate the handoff report.
4. Keep the mock banner visible during the mock plan. If including the historical Nemotron evidence card, cut to a separate title card labeled “Separate historical live test — Phase 6B.2”; do not place it over or directly inside the mock response.
5. Do not open terminals, environment settings, API docs, browser developer tools, unrelated repositories, or credential screens while recording. Do not show a real API key, account details, private source code, filesystem paths outside the synthetic fixture, or personal information.
6. Stop by 2:55. Trim dead air and mistakes, but do not alter provider labels or make mock output look like a live response. Keep narration clear and captions readable.
7. In Clipchamp, choose **Export**, select **1080p**, and save the MP4. Microsoft documents the export flow and MP4 output in its [Clipchamp export guide](https://support.microsoft.com/en-us/clipchamp/exporting-and-saving-a-video-in-clipchamp).
8. Watch the exported file from beginning to end. Confirm the duration is less than 3:00, audio is audible, screen text is legible, no credentials or sensitive desktop content appear, and all live/mock labels are accurate.

## Stop and clean up

Press `Ctrl+C` in the Next.js window and then in the FastAPI window. Close both dedicated PowerShell windows; this discards their process-scoped recording settings without changing persistent user or machine environment values. The local review decision and history are process-local and disappear when FastAPI stops. No source file should have changed. Do not turn on runtime validation; no trusted sandbox executor is configured.

## Upload to YouTube

1. Sign in to the team’s approved YouTube account and open [YouTube Studio](https://studio.youtube.com/).
2. Select **Create → Upload videos** and choose the reviewed MP4.
3. Enter a factual title and description. Disclose that the walkthrough uses mock planning and that the historical Nemotron metrics are from a separate earlier live test, if included.
4. Set visibility to **Public** only after the team approves the final file and metadata. Verify public playback in a signed-out/private browser window and copy the final video URL into the submission materials.

YouTube's official [upload guide](https://support.google.com/youtube/answer/57407?hl=en) describes the upload and visibility steps. Do not publish a draft, raw recording, or file containing credentials.
