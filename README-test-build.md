# DevRelay AI Windows test build

This downloadable package runs DevRelay AI locally on Windows. It is a source-based test build, not a hosted site or a precompiled installer.

## Quick start

Prerequisites: Windows 10/11, Python 3.12+, Node.js 20.9+, npm, and internet access for the first dependency install.

1. Extract the ZIP to a new folder.
2. In PowerShell, change to that folder and run:

   ```powershell
   powershell.exe -ExecutionPolicy Bypass -File .\scripts\windows-test-build\Install-DevRelayTestBuild.ps1
   powershell.exe -ExecutionPolicy Bypass -File .\scripts\windows-test-build\Start-DevRelayTestBuild.ps1
   ```

3. Choose a temporary password of at least 16 characters when prompted. Sign in at `http://127.0.0.1:3000` with username `local-demo`.
4. Stop both service windows with **Ctrl+C**.

The build is restricted to the synthetic continuity-pipeline fixture, binds both services to loopback, and uses deterministic mock inference. It makes no Nebius call. The mock does not diagnose the incident; it demonstrates the local static-analysis and handoff interface. See [the full test-build notes](docs/windows-test-build.md).
