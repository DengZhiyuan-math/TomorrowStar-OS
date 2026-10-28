# macOS App acceptance — 2026-10-09

Result: the local Apple Silicon App is built and its native workflow is accepted.
This result does not admit personal mastery, interview calibration or JD usefulness.

## Artifact

- App: `build/macos/release/TomorrowStar.app`, version 0.1.0.
- Archive: `build/macos/release/TomorrowStar-macOS-arm64.zip`.
- Local installation: the user's Applications folder, with no existing App replaced.
- Runtime: bundled CPython 3.13.14 and the five pinned runtime distributions.
- Signature: local ad-hoc; deep and strict verification passed.
- Source snapshot: `Contents/Resources/build-manifest.json` binds the public engine files.
- Host: Apple Silicon, macOS 27.2 (26B5101f).
- Minimum build target: macOS 13. Other host versions were not tested.

## Deterministic and relocated checks

| Check | Result |
| --- | --- |
| Full offline checkout suite after the bytecode fix | 629 passed; 1 deselected; 166.65 seconds |
| Ruff check, formatting and Git whitespace check | Passed |
| Separate private Git root with a non-Git installed system root | Passed |
| Backend readiness, loopback binding and parent EOF shutdown | Passed |
| App copied outside the repository into a path containing spaces | Passed |
| Bundled Python launched from `/` with an isolated environment | Passed |
| Application create, edit, evidence association and CSV export | Passed with disposable synthetic records |
| Evidence document, graph, static assets and interview protocol | Passed |
| Foreign Host and missing CSRF token rejected | Passed |
| Engine source digests match the bundle manifest | Passed |
| Strict signature after document and graph reads | Passed for relocated and installed App |

The machine-readable relocation report is `build/macos/release/acceptance.json`.
`macos/verify.py` can repeat this acceptance without personal data.

## Native window checks

| Action | Observed result |
| --- | --- |
| Launch with a separate synthetic configuration | Both folders connected; overview loaded |
| Enter a new application and invoke `⌘Q` | Native unsaved-change sheet appeared |
| Select “返回保存” | App remained open and the entered company name was retained |
| Save a valid application with one documentary link | Application count and association updated |
| Press `⌘2` and export CSV | Native save sheet appeared; saved CSV contained the synthetic record |
| Press `⌘4` and select a JSON file | Native open sheet appeared; selected filename appeared in the form |
| Press `⌘,` and select both synthetic directories | Backend restarted; old listening port closed |
| Press `⌘3` | Documentary graph rendered with the synthetic project, Python and SQL nodes |
| Invoke `⌘Q` after saving | Native process exited with status 0; final listening port closed |

Native mutation checks used a disposable synthetic configuration. No personal
application record was added or edited. The installed App reuses the operator's
existing folder configuration.

## Environment findings

Native acceptance found that the document-reader subprocess could write Python
bytecode into the App. Strict signature verification then rejected the added files.
The reader now uses `-B`, as does the main desktop backend. Relocation acceptance
also verifies the signature after document and graph reads, not only before launch.
The initial build and its report remain diagnostic artifacts, not the final release.

The final installed App was opened with the synthetic configuration, rendered the
documentary graph, and exited. Strict signature verification still passed afterward.
The final archive SHA-256 is
`e795abe9bd7787dbcc18370179a9c4f41a685e9a4b468dc0166e011db44a0591`.

Direct GUI launch from the restricted shell aborted in macOS application
registration before the App entered its own code. Launch in the normal macOS
graphical session passed. This is an execution-environment limitation.

The restricted build shell rejected icon conversion even though the PNG dimensions
and names were valid. Running the same `iconutil` command in the normal macOS context
passed. The verified ICNS is retained as a build resource. Future builds reuse it.

Developer ID signing, Apple notarization, Intel builds and other macOS releases
remain outside this local delivery. Existing interview and scoring acceptance
gates remain in force.
