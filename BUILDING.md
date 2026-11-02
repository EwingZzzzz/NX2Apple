# Building from source

## Build checks from Windows with GitHub Actions

### Download an original homebrew IPA

**Actions → Build redistributable homebrew IPA → Run workflow** builds the fixed,
committed [original homebrew program](homebrew/hello/README.md). It accepts no game
files, keys, download URLs or signing credentials. A PR changing this workflow or
its source runs the same build before merge. After merge it can be triggered from
a browser on `main` without a local Mac.

Download the `NX2Apple-Homebrew-IPA-<run ID>` artifact from a successful run, extract
the outer ZIP, and use `NX2Apple-Homebrew.ipa`. The artifact includes SHA-256 sums,
an archive file list and a JSON build report. A separate artifact contains only
homebrew build diagnostics. IPA artifacts expire after 14 days, logs after seven.
The report explicitly distinguishes building from signing, installing and running.

This is the complete unencrypted dump-folder build path through the real NSP build
script, not the upstream compile-only smoke fixture. It exercises RomFS packing,
NSO rewriting, GLSL/SPIR-V/MSL translation, iOS compilation and IPA packing. It does
not exercise encrypted NSP extraction, retail profiles, NVN translation or a game
running on a GPU. No proprietary SDK is used. The complete small homebrew RomFS is
inside the IPA. System fonts are replaced with redistributable OFL fonts before
upload, with font and third-party license notices included.

For a Windows installation test, [Sideloadly](https://sideloadly.io/index.html)
supports loading an IPA and signing it locally for a connected iPad using a free
or paid Apple account. Keep Apple credentials and any two-factor code in the local signing
tool, never in this chat, Git or Actions. Follow the tool's current Apple driver
requirements. Connect and unlock the iPad, accept its Trust prompt, and select it
in the signer. Choose the extracted IPA and complete account authentication locally.
The alternative [AltStore Classic Windows route](https://faq.altstore.io/altstore-classic/how-to-install-altstore-windows)
also requires local Apple-account authentication and device pairing.

The host currently targets iPadOS 26 or newer. Enable Developer Mode and trust the
developer profile on the iPad when requested. After installation, open **NX2Apple
Homebrew Test**. It is CPU-only and does not draw the sample shaders. Inspect its
Files app Documents folder for `log.txt`: repeated
`NX2Apple original homebrew: rewritten guest code is running` messages are the
runtime success criterion. A successful cloud build or a blank game view alone
does not prove that the rewritten code ran. Free-account signatures normally need
renewal after seven days. This tiny test does not request Increased Memory Limit,
but retail games can need it and must be checked separately.

Physical pairing, Trust/Developer Mode actions, Apple login/2FA and confirming the
on-device log require the device owner. A GitHub-hosted Mac cannot reach a USB iPad
attached to a Windows PC. Until the device log is inspected, installation and guest
execution remain untested even when the downloaded IPA is structurally valid.

The [Apple dependency preflight and private IPA workflow](.github/workflows/apple-preflight.yml)
uses GitHub's Apple Silicon `xcode-27` hosted image. It is manually triggerable with
**Actions → Apple dependency preflight and private IPA → Run workflow**. Leave
**build_ipa** unchecked for the first run. Enable Actions in your fork if GitHub asks.
The workflow must exist on the default branch before the manual button appears.
A PR changing its workflow or helpers also runs the safe preflight, so it can be
reviewed and tested before merging. Never merge this PR just to make an untested check green.

The preflight needs no game dump, keys, Apple account or signing credentials. It:

- Rejects Intel runners, finds an installed Xcode whose reported version is exactly
  27.2, selects it with `xcode-select` and `DEVELOPER_DIR`, and records the exact
  macOS version/build, Xcode version/build, and iOS SDK version/build/path.
- Installs the Brewfile's four formulas, native Python 3.14 and a venv with the
  documented Python dependencies. Capstone is constrained to 5.x as upstream requires.
  `setup-dotnet` selects SDK 10.0.x instead of relying on Homebrew's rolling SDK cask.
  It downloads the selected Xcode's separate Metal toolchain.
- Syncs the engine with `python tools/engine.py sync`, validates its patch queue,
  records the repository/pin/patched-engine commits, runs upstream's dependency and
  translator checks, and checks the shader tool fingerprints against the committed lock.
  It does not rebuild the committed shader translator or enable `--allow-other-metal`.
- Builds the open source .NET extractor and compiles an original synthetic iOS Metal
  kernel. No game is decrypted, translated, packaged, launched or installed.
- Uploads only the named preflight logs and synthetic Metal outputs as a seven-day
  Actions artifact, even after failure. No workspace-wide uploads or build caches are used.

Xcode 27.2's reported version can identify an RC on a changing hosted image. The full
build number is recorded, and the engine's Metal lock remains authoritative. A missing
27.2, iOS SDK, compiler, .NET runtime, download, or mismatched lock fails the job.
Read the failed step and the safe artifact. A queued job is not evidence of a working
runner, and a passing preflight does not establish game compatibility.

GitHub currently [documents 14 GB of storage for standard macOS hosted runners](https://docs.github.com/en/actions/reference/runners/github-hosted-runners).
The workflow measures actual free capacity, requires 8 GiB before dependency setup
and 4 GiB afterwards, and fails rather than deleting unrelated runner software.
Check the current [xcode-27 image manifest](https://github.com/actions/runner-images/blob/main/images/macos/xcode-27-arm64-Readme.md)
for installed Xcodes. Runner availability and minutes depend on the account.

### Optional private game build

This is an experimental command-line per-game IPA build, not a build of the macOS
launcher or its multi-game iOS library. It is disabled by default. Public repositories
reject it before reading any secret. GitHub does not allow public forks to become
private, so keep a public fork for source and preflight, and use a separate private
repository containing reviewed source for game builds. Do not put private data in
the fork's Git history, issues, releases, Actions inputs, artifacts, or public logs.

1. In the private repository, review and merge the source before using its default
   branch for this job. Create a `private-ipa` environment, restrict deployment to that
   branch, and configure required reviewers where your plan supports them. If your
   plan lacks environment secrets or protections, do not substitute public inputs.
2. In your own private storage, prepare a ZIP containing **only one game's legally
   owned base/update/DLC containers at the ZIP root** (`.nsp`, `.xci`, `.nsz`, `.xcz`).
   Nested paths, symlinks, duplicates, executables and keys are rejected. Use a private
   bucket with encryption at rest, access logging and a short deletion lifecycle.
   Generate direct, expiring, object-scoped HTTPS GET and PUT URLs. Redirects are
   rejected. The PUT destination must be private and accept `application/zip`.
3. Add environment secrets, never workflow input values:

   | Environment secret | Value |
   |---|---|
   | `NX2APPLE_INPUT_URL` | Expiring GET URL for your private input ZIP |
   | `NX2APPLE_INPUT_SHA256` | SHA-256 of that ZIP, e.g. `(Get-FileHash .\input.zip -Algorithm SHA256).Hash` in PowerShell |
   | `NX2APPLE_PROD_KEYS` | Contents of your own console's `prod.keys` |
   | `NX2APPLE_OUTPUT_URL` | Expiring PUT URL for a new private result ZIP |

4. Manually run on the reviewed default branch, check **build_ipa**, and set
   **required_free_gib** to your full disk budget (80 by default, minimum 20).
   Account for the downloaded ZIP, extracted containers, decompressed NSZ/XCZ,
   extracted game, shaders, derived data, IPA and result ZIP. The transport limits both
   input ZIP and expanded containers to `(budget - 10) / 5` GiB, up to 128 files.
   This is a conservative admission limit, not a guarantee. The running build is also
   stopped if free space falls below 4 GiB, and packaging checks its own space.
   Most large games will fail admission on a standard hosted runner. Use a suitably
   provisioned Apple Silicon runner for those, after verifying its installed Xcode.
5. Retrieve the result directly from **your private storage**. It contains `result.ipa`,
   the extraction's `romfs.img` images under `data/`, and `build.log`. The build uses
   `--romfs separate --gpu none`, so M4 compiles its own pipeline bases at first use.
   Select the RomFS matching the packaged update. It must be transferred separately
   to the app's Documents folder as the per-game app expects. A normal nonzero build
   exit delivers only `build.log`, then fails the job. Download, disk, timeout or
   delivery failures can leave no result. No game build success is promised.

The private step prints only fixed status messages. Raw tool output is redirected
to the private workspace and never uploaded to Actions. Transport secrets and key
contents are removed from child process environments. Private inputs, keys, output,
logs and disposable engine data are removed on completion and in an `always()` step.
Hard runner termination can interrupt cleanup, so use ephemeral hosted runners only.
The job has a three-hour timeout, with a two-hour game-build limit. Expiring storage
URLs must remain valid through the queue and build, then be revoked or expire.
No signing certificate, Apple ID password, app password, or provisioning profile is
accepted by this workflow. Never commit any of them or `prod.keys`, even to private Git.

Even a slim IPA contains rewritten copyrighted game code, shaders and possibly artwork.
It is not a permitted public CI artifact. Neither it nor game-derived images, raw logs
or caches enter Actions artifacts. Only preflight logs and synthetic outputs do.
Ownership does not itself grant redistribution rights. Keep game builds for your own use.

### M4 iPad Pro signing and installation from Windows

Windows can edit source, dispatch Actions, inspect safe logs, retrieve a private IPA
and manage private storage. It cannot run Xcode, compile Apple's native iOS targets,
or operate NX2Apple's macOS launcher. GitHub's Mac can compile remotely, but it cannot
pair with or install onto an iPad connected to your Windows PC. Hosted runners are
virtual machines, so runtime shader capture, Metal 4 GPU tests and games requiring
them may fail even when compilation checks pass.

The script produces an unsigned IPA (its ad-hoc executable signature only carries
requested entitlements). Downloading it does not make it installable. For development
or ad hoc installation, the actual signing certificate, bundle ID, registered device
and provisioning profile must agree and grant the needed entitlements. A paid team
can prepare these and sign on a trusted Mac or separately secured macOS CI using an
ephemeral keychain. This workflow deliberately does not implement that signing service.
Do not assume TestFlight or App Store distribution is appropriate for game-derived code.

[AltStore Classic documents a Windows installation route](https://faq.altstore.io/altstore-classic/how-to-install-altstore-windows)
for signing/sideloading your own IPA. Follow its current instructions locally, and
keep Apple credentials out of GitHub. Free-account installs normally need
[refreshing every seven days](https://faq.altstore.io/altstore-classic/your-altstore).
Installation through a particular signer does not prove that it preserved the
entitlements or that the game will launch. Enable Developer Mode if iPadOS requests it.

NX2Apple/nxnative may need Increased Memory Limit and extended virtual addressing.
Inspect the **signed app and embedded provisioning profile**, not just the requested
entitlements plist. Apple documents that
[additional memory is available only on supported devices](https://developer.apple.com/documentation/bundleresources/entitlements/com.apple.developer.kernel.increased-memory-limit)
and is not guaranteed. An M4 chip alone does not establish the memory entitlement,
available RAM, address-space layout, game/profile compatibility or correct signing.
Neither paid membership nor a Windows sideloading tool guarantees this game's needs
will be granted. Transfer your own matching RomFS privately after installation and
test on the real iPad. CI preflight cannot certify that final step.


The launcher (see the [README](README.md)) runs the same scripts a terminal does. This page is the by-hand route, for advanced users, for development, or when the launcher is not an option: the tools, your `prod.keys`, and the IPA built from a terminal. Contributing rules are in [CONTRIBUTING.md](CONTRIBUTING.md).

## Get the tools

This is the command-line route the launcher drives for you. The build is upstream's. Follow upstream's [README](https://github.com/seedds/nxnative) to install Xcode, Homebrew tools and the Python packages, then pack an IPA.

```bash
git clone https://github.com/<you>/NX2Apple.git
cd NX2Apple
python3 tools/engine.py sync                      # the engine (nxnative at the pin plus our patches) into engine/, about 80 MB
brew bundle --file=Brewfile                       # xcodegen, zstd, spirv-cross, glslang (the NSP script checks for it), .NET SDK
python3 -m venv .venv                             # Homebrew's Python refuses global pip installs (PEP 668)
.venv/bin/python -m pip install lz4 capstone fonttools zbic nsz "backports.zstd; python_version < '3.14'"
source .venv/bin/activate                         # so that python3 below is the venv's (in each new terminal)
```

## What you need on disk

Three things, none of which ship with the repository:

| What | Where it comes from | Used by |
|---|---|---|
| **`prod.keys`** | dumped from **your own console** (see below) | the extractor, to decrypt your game |
| **The game's NSPs** | dumped from your own cartridge or eShop purchases | the extractor |
| **Xcode + iOS SDK** | the App Store | the app build |

`prod.keys` is the console's key set — a text file of `name = hex value` lines (~230 entries:
`master_key_xx`, `titlekek_xx`, `header_key`, `key_area_key_application_xx`, …). Every Switch
homebrew tool reads this format. It is **not** tied to a specific game: one `prod.keys` decrypts
any of your games. The only requirement is that the file contains keys for the key generation
(firmware era) the game was packaged with — a current dump covers every retail game.

Where to put it is up to you. You pass the path with `-k`:

```bash
# any layout works, e.g.
~/keys/prod.keys
# or keep it beside the game's NSPs
~/Games/Hades2/prod.keys
```

```bash
python3 engine/scripts/build_ipa_from_nsp.py ~/Games/Hades2 -k ~/keys/prod.keys
```

How keys are dumped is documented across the Switch homebrew community (Lockpick_RCM from a
hacked console is the usual route). This repository does not cover that step and ships none of
it. Two practical notes from real dumps:

- **Malformed lines.** Some dumpers emit lines whose hex value has the wrong length (33 bad
  `master_kek_source_*` lines in one real dump), which makes the extraction tool refuse the whole
  file. Delete the offending lines and keep a backup of the original.
- **Updates.** An update NSP's ticket may carry a newer key generation than the base game's. The
  extractor reads the title key straight from the common ticket inside each NSP, so in practice
  both decrypt fine as long as `prod.keys` is reasonably current — verified here with a base
  game on generation 15 and its update on 16, using a keys file that only reached 15.

`backports.zstd` is needed for Tears of the Kingdom's zstd dictionaries. Other games do not use it.

## Build the IPA

The main build script packs a **slim IPA by default** (no RomFS inside, as the app reads the game's data from its folder on the device, `Documents/games/<id>/`), so the build above already produced it. To re-pack just the package later:

```bash
GAME=<title id> W=<work dir> PATCHED=<patched dir> \
  ROMFS=<RomFS dir> MSL_IOS=<shader dir> \
  engine/dm/ios/tools/build_ipa.sh <output.ipa>
```

`--full-romfs` (or `DM_FULL_ROMFS=1`) packs the RomFS into the package instead — upstream's
behaviour, only sensible for small games.

The RomFS no longer has to be packed into a shard archive: the build writes the game's data as a single `romfs.img`. Shard archives made earlier (`romfs.idx` with `romfs.00`, `romfs.01`, …) are no longer read; the launcher reports such a folder as having no game data, and the data is sent again once as a `romfs.img`.
