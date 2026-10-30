# Windows downloadable test build

This is a reproducible **local test build package**, not a hosted demo. The archive contains source and launch instructions; it does not bundle Python, Node.js, or third-party dependencies. Organizers should confirm that this format meets the separate demo/test-build URL requirement before it is entered on Devpost.

**Download:** [DevRelay-AI-TestBuild.zip](https://raw.githubusercontent.com/kitranet/devrelay-ai/acdf44d7a332e8762f29761dcd86ca775bf3c849/test-build-dist/DevRelay-AI-TestBuild.zip) · [SHA-256 checksum](https://raw.githubusercontent.com/kitranet/devrelay-ai/acdf44d7a332e8762f29761dcd86ca775bf3c849/test-build-dist/SHA256SUMS.txt)

## What it runs

- FastAPI on `127.0.0.1:8001` and production Next.js on `127.0.0.1:3000`.
- Only the synthetic `continuity-pipeline-fixture` repository.
- Deterministic mock inference, with the Nebius key cleared, live inference disabled, and quota set to zero.
- A local Basic Auth gate using a password entered interactively. The password is not written to files or passed on a command line.
- Local review and runtime validation disabled.

The demo is offline with respect to inference. The installer downloads ordinary Python and npm dependencies, but it makes no model/API request. The mock can show static analysis and the plan-only workflow; it does not reason over the source and is not evidence of a real Nemotron answer. Runtime validation remains `not_run`; no code is applied or executed.

## Requirements

- Windows 10 or 11, 64-bit.
- Python 3.12 or newer on `PATH`.
- Node.js 20.9 or newer and npm on `PATH`.
- An internet connection for the initial dependency installation.
- A local browser.

## Install and run

1. Download the ZIP archive and extract it to a new folder, for example `C:\DevRelay-TestBuild`.
2. Open PowerShell in the extracted folder. If Windows blocks the scripts, use a one-session policy bypass as shown below; this does not change the machine policy:

   ```powershell
   powershell.exe -ExecutionPolicy Bypass -File .\scripts\windows-test-build\Install-DevRelayTestBuild.ps1
   ```

3. After installation completes, start the app:

   ```powershell
   powershell.exe -ExecutionPolicy Bypass -File .\scripts\windows-test-build\Start-DevRelayTestBuild.ps1
   ```

4. Choose a temporary password of at least 16 characters when prompted. The input is hidden. In the browser's sign-in dialog, enter username `local-demo` and that password.
5. Select the continuity pipeline fixture, analyze it, generate the mock plan, inspect its citations, then create a plan-only handoff. The screen labels mock inference. Do not describe it as a Nemotron result.
6. Stop both servers by pressing **Ctrl+C** in each server window.

The launcher checks ports before starting and will not stop a process already using port 3000 or 8001. Close the identified service yourself, then run the launcher again.

## Privacy and limitations

- No credentials, `.env` files, SQLite state, build output, `node_modules`, virtual environment, or recordings are included in the ZIP.
- Telemetry is generated locally under `.devrelay-state/`; it can contain sanitized run metadata. Keep that folder private and do not upload it.
- The frontend accepts a temporary local password. No public endpoint is created, and FastAPI is not exposed outside loopback.
- No live Nebius request, code execution, patch application, reviewer approval, or runtime validation is performed by this test build.
- It requires local Python/Node setup and is less convenient than a hosted URL. A GitHub-generated source ZIP with this launcher is a downloadable test package, but it is not a precompiled installer or an always-on application.
