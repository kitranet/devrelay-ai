# DevRelay AI Windows test-build artifact

`DevRelay-AI-TestBuild.zip` is a downloadable, source-based Windows test package. It is not a hosted application or a precompiled installer. It requires Python 3.12+, Node.js 20.9+, npm, and internet access for initial dependency installation.

The package runs FastAPI and Next.js only on loopback, exposes only the synthetic continuity-pipeline fixture, and uses deterministic mock inference. It does not call Nebius, execute repository code, apply patches, or enable local review/runtime-validation controls.

Extract the ZIP and follow `README-test-build.md` at its root, then see `docs/windows-test-build.md` for limitations and privacy details. Verify the archive with `SHA256SUMS.txt` before running it.

This local package is not an always-on hosted demo. Confirm with the hackathon organizers that this source-based test build satisfies the separate demo/test-build URL requirement before submitting the link.
