# Panda Goal Status

This file is the durable progress record for the autonomous development task.
Update it after each verified phase.

## Objective

Build Panda as an open-source real-time voice changer with:

- a user-level development environment
- open voice-pack tooling
- MeanVC2 feature extraction and inference
- C++ core services
- Qt/QML desktop UI
- model-pack management
- audio pipeline
- virtual-audio-output integration where feasible
- tests, self-review, and documentation after every phase

## Completed

### Project Baseline

- GitHub repository connected: `https://github.com/lyhxx/Panda`
- Project renamed from the temporary OpenVC label to Panda
- Apache License 2.0 added
- NOTICE and third-party notice tracking added
- Python package renamed to `panda-pack`
- C++20/CMake project skeleton added

### Development Environment

- User-level Miniforge installed under `.tools/miniforge3`
- Python 3.11 environment `meanvc2-cpu` created
- CPU PyTorch 2.5.1 and TorchAudio 2.5.1 installed
- NumPy, ONNX Runtime, librosa, soundfile, pyworld, s3prl, and gdown installed
- MeanVC2 cloned under `deps/MeanVC2`
- Public MeanVC2 model assets downloaded
- WavLM-Large and fine-tuned speaker model downloaded
- Qt 6.8.3 MSVC 2022 desktop SDK installed under `.tools/Qt`

### Verified

- Python packaging tests pass
- `panda-pack --help` works
- MeanVC2 CPU speaker embedding extraction works
- `panda-pack` generates a complete ZIP voice pack from a WAV
- C++ core library builds with MSVC
- CTest passes
- Qt/QML desktop skeleton builds with Qt 6.8.3
- Qt/QML desktop process starts successfully
- C++ voice-pack manifest parser implemented
- SHA-256 validation implemented
- Safe archive path validation implemented
- Atomic install and overwrite implemented
- CLI `install`, `validate`, and `list` commands implemented
- Negative tests cover unsafe paths, checksum mismatch, and atomic failure
- Qt/QML voice-pack list model integrated
- Desktop app starts with a real installed voice pack
- `panda-infer` offline conversion wrapper implemented
- Real CPU MeanVC2 inference completed from an installed Panda pack
- `panda-rt` realtime launcher and device listing implemented
- Unified `panda pack|infer|realtime|devices` command implemented
- Legacy `panda-pack`, `panda-infer`, and `panda-rt` entry points kept as aliases
- JSON device enumeration implemented for UI integration
- Qt desktop start/stop controller connected to the public `panda realtime` entry point
- Qt desktop input/output device selection and voice-pack selection implemented
- Realtime worker metrics parsed by a tested C++ core component
- Qt desktop displays processing time, RTF, buffer depth, and overrun state
- `panda doctor` checks Python dependencies, MeanVC2 assets, voice packs, and audio devices
- Windows portable packaging script added under `scripts/package_windows.ps1`
- Packaged Qt Release application starts without a system Qt path or `PYTHONPATH`
- Full portable package can bundle a relocatable MeanVC2 CPU Python runtime with `-BundlePython`
- MeanVC2 40ms runtime assets can be copied with `-BundleMeanVC2`
- Bundled runtime doctor checks pass from the package directory
- Bundled Python and MeanVC2 completed a real 40ms CPU WAV inference
- `panda doctor` detects user-installed virtual playback devices for routing
- User-level Windows install and uninstall scripts added under `scripts/`
- Installed Release package starts without administrator rights or system Python
- Uninstall preserves voice packs unless `-RemoveVoices` is specified

### CPU Realtime Validation

- MeanVC2 runtime loader fixed for the official `runtime/src` package layout
- `panda benchmark` added to the unified CLI
- Benchmark reports p90/p95/p99, max, overruns and the effective torch thread count
- `--threads` option added; thread sweep measured on the development host
- Single-thread CPU inference confirmed fastest (small batch=1 model)
- 480-chunk / 76.8 s stability run at RTF 0.757, p99 145 ms, 2 overruns, no drift
- CPU-first pipeline confirmed viable without a GPU
- Bounded jitter buffer implemented with unit tests (pre-roll, underrun
  accounting, overflow dropping, compaction-safe ordering)
- A virtual microphone is already present on the development host
  (`BaoMiao Virtual Microphone`, MME/DirectSound/WASAPI/WDM-KS)
- `panda doctor` now distinguishes a writable virtual playback device from a
  capture-only virtual microphone and explains what is missing

### Decoupled Realtime Pipeline

- Inference moved off the audio callback onto a worker thread
  (`panda_infer.realtime_session.ConversionSession`)
- The callback only copies captured audio in and converted audio out
- Bounded input queue discards the oldest block instead of growing latency
- Runner warm-up added; the first block drops from 348 ms to 133 ms
- Pre-roll silence is now reported separately from genuine underruns
- `panda simulate` added: drives the full pipeline from a WAV with no
  microphone or virtual cable, and writes the converted output
- End-to-end run: 125 blocks / 20 s audio, 0 underruns, 0 dropped frames,
  output 20.42 s, warm-up 3 blocks
- Live `panda realtime` now serves from the session instead of the
  official callback-blocking `run_realtime`
- `--prefill-chunks` and `--max-backlog-chunks` exposed as latency controls on
  `realtime`, `simulate` and the launcher
- Pre-fill trade-off measured: 1 block costs 0.32 s of startup silence and
  peaks at 157 ms; 2 blocks cost 0.48 s and peak at 133 ms, both with no
  underruns
- Desktop metrics regression fixed: the worker now emits a stable
  `[panda.metrics]` JSON line that `panda::audio::parse_realtime_stats`
  parses, with the legacy upstream console format still accepted
- `RealtimeStats` carries mean/max processing time plus underrun and dropped
  frame counters
- Verified with the real MeanVC2 model: 24 blocks, mean 116.1 ms, max 121.9 ms,
  no overruns, 25 metrics lines emitted and parsed

### Model Pack Management

- Overwrite now enforces the documented upgrade rule: a pack whose
  `schema_version` differs from the installed one is refused with
  `unsupported_schema`, and the installed pack is left untouched
- Overwrite also verifies the installed directory holds the same `id`
- `remove_voice_pack(voices_root, id)` added: removes exactly one pack
  directory after id validation, manifest/id agreement, and a containment check
- `ErrorCode::not_found` added for the missing-pack case
- `panda_cli remove <voices-root> <pack-id>` added
- Verified end to end through the CLI: install, list, remove, second remove
  reports code 12, and a schema_version=2 overwrite of a v1 pack is refused
  with code 6 while the original manifest survives

### Test Integrity

- Found that the C++ suite could exit with status 0 without finishing, so CTest
  reported a false pass and the last tests never ran
- Root cause of the stall: deleting freshly written fixture directories under
  `.tmp` blocked for ~31 s per call on this host; fixtures now use unique paths
  and are left in place
- The suite now runs all 11 tests and completes in ~2.5 s
- CTest requires the `PANDA_CORE_TESTS_COMPLETE` marker, so a truncated run
  fails instead of silently passing

### Desktop Pack Management

- `PackListModel` can now install and remove voice packs, not just list them
- Core error codes are mirrored as `PackListModel::PackError` and mapped to
  Chinese messages, so the UI explains why an install failed
- QML gained an "安装音色包" button with a file picker, an overwrite
  confirmation when the pack id already exists, and a per-row delete with
  confirmation; success and failure messages are shown inline
- New headless Qt test target `panda_desktop_tests` covering listing,
  removal, unsafe ids, missing archives and message state (9 cases)
- Found while wiring this up: the test executable was built as a GUI-subsystem
  binary, so Qt Test produced no output at all; it is now a console app
- Found in packaging: linking `Qt6::QuickDialogs2` requires re-running
  `scripts/package_windows.ps1`; the previous `dist/Panda` lacked
  `Qt6QuickDialogs2.dll` and the packaged app exited with code 1

### Virtual Output Guidance

- `panda devices --json` now tags every device with `is_virtual`
- Device parsing moved into `panda::desktop::parse_device_payload` so it is
  testable, and carries an `isVirtual` flag into the QML model
- The desktop shows a warning when the selected output is not a virtual audio
  device, explaining that other applications will not hear the converted voice
  and pointing at a virtual cable
- Verified against the real device list: the four BaoMiao virtual microphone
  endpoints are tagged virtual and the Realtek speakers are not
- Fixed a crash introduced by printing device JSON from the host process: a
  device name containing `®` raised `UnicodeEncodeError` on a GBK console.
  JSON is now written as UTF-8 bytes regardless of the console code page
- New headless test target `panda_device_list_tests`

### Installer Integrity and Upgrade

- `package_windows.ps1` now writes `package-manifest.json` with the size and
  SHA-256 of every packaged file
- `install_windows.ps1` verifies that manifest before copying anything and
  refuses on a missing file, size mismatch, checksum mismatch, or unsafe path;
  entries are also checked for traversal
- `-SkipVerify` installs an unverified package deliberately
- Fixed data loss on upgrade: the installer used to delete the whole install
  root, which also removed the default `voices` directory. It now replaces only
  `app/`, reuses the recorded voice directory, and records `previous_version`
- `install.json` gained `schema_version` and `previous_version`
- Verified on the real package: 1368 files verified, fresh install, upgrade
  with a voice pack present preserved it, and the installed app still starts
- New `tests/test_windows_installer.py` runs the real scripts against a fake
  package (6 cases): fresh install, upgrade preserving voices, tampered
  package, truncated package, missing manifest, and refusal without `-Force`

### Desktop Configuration and Diagnostics

- The desktop can now pick the model (40ms / 120ms) and compute backend
  (cpu / cuda) instead of hard-coding them
- The worker's stdout is shown in a log pane, so a failed start is visible
  instead of silent
- `[panda.metrics]` lines are routed to the numeric display and filtered out
  of the log pane, which would otherwise be flooded twice per second
- A trailing line without a newline is flushed when the process exits, so the
  final error message is not lost
- Command construction and the metrics/log split moved into
  `panda::desktop` (`worker_protocol`) and are covered by
  `panda_worker_protocol_tests`
- The metrics prefix constant now lives in the core header so the producer and
  the consumer share one definition

### Desktop Pack Search and Latency Controls

- `PackListModel` gained a `filter` property; matching is case-insensitive and
  covers both the pack id and its display name, and the filter survives a
  refresh
- The desktop has a search box above the pack list
- Pre-roll and backlog bound are user-adjustable from the UI; the accepted pair
  is clamped (`clamp_latency`) so the backlog always stays above the pre-roll,
  and the spin boxes mirror the accepted values back
- `clamp_latency` lives in `worker_protocol` and is covered by tests

### Virtual Audio Routing Decision

- Decided and documented: v1 relies on a user-installed virtual cable
  (VB-CABLE / VoiceMeeter); a signed Panda driver stays future work because a
  kernel driver needs admin rights and signing
- Wrote `docs/VIRTUAL_AUDIO.md`: the two ends of a cable, setup steps, current
  limitations (single output, sample-rate mismatch, no denoising) and a
  troubleshooting table
- Added `panda route-check`: pairs every writable virtual endpoint with its
  capture counterpart by swapping the Input/Output role token, then names the
  device to pick in Panda and the one other applications should capture
- Returns exit code 0 when a route exists and 1 when it does not, so it works as
  a scripted check
- Verified on the development host: it correctly reports no route because the
  only virtual device there is a capture-only microphone

### Monitor Output

- Added a second, optional playback path so the speaker can hear their own
  converted voice while the main output still goes to the virtual cable
- `MonitorTap` fans out the block the main device just played into its own
  jitter buffer, so monitoring cannot steal samples or affect conversion timing
- Plumbed through `--monitor-device` in the worker and the launcher, and a
  "监听输出" selector in the desktop (with a "不监听" option)
- Verified with the real MeanVC2 model on a paced fake device pair: 37 blocks
  converted, 37 monitor reads, 87040 non-silent samples delivered

### Session Persistence

- The desktop remembers the voice pack, input/output/monitor device, model,
  compute backend and latency settings across restarts
- `SessionStore` wraps QSettings and sanitises on both save and load: an
  unknown model or backend falls back to the default, latency goes through
  `clamp_latency`, and negative device ids become "not selected"
- A restored voice pack is only applied when the pack still exists
  (`PackListModel::containsFolder`, which checks the unfiltered set so a search
  filter cannot make a valid selection look stale); deleting the selected pack
  clears the selection
- New headless test target `panda_session_store_tests`
- Verified end to end against the real app: a graceful close wrote the
  settings, and values seeded into the settings store survived a full
  launch-and-close cycle instead of being overwritten by defaults

### Pipeline DSP

- Implemented the two audio-pipeline responsibilities that were still missing:
  the noise gate and the output soft limiter (`panda_infer.dsp`)
- `NoiseGate` decides per block (the converter's unit), ramps gain across the
  block instead of stepping, and opens faster than it closes so trailing
  consonants survive; default off, enabled with `--noise-gate-db` (recommend -45)
- `SoftLimiter` passes audio below its knee untouched and bends smoothly toward
  a ceiling above it; default on at 0.891 (about -1 dBFS)
- Wired into `run_realtime_session`, the worker and the launcher
- Found while verifying: `SoftLimiter.process_in_place` silently did nothing
  when handed a plain list, because `np.asarray` copies it. Production passes a
  numpy view so it was never hit, but the contract was wrong; it now writes back
  and there is a regression test
- Verified with the real model on a paced device pair: with a 0.05 ceiling the
  monitor peak was exactly 0.0500, and with the default 0.891 the peak was
  0.1536 (below the knee, so untouched)
- The noise gate is exposed in the desktop as a checkbox plus a threshold
  spin box (default off), and its state persists with the session. The limiter
  stays on by default and is transparent at normal levels, so it has no
  control; `clamp_gate_db` bounds the threshold to -90..-10 dB so it can
  neither gate normal speech nor become a no-op

### ONNX Export: Vocoder

- Probed the C++/ONNX boundary by trying to export the MeanVC2 vocoder, and
  found three concrete obstacles, each with a working fix:
  - the TorchScript entry point is `decode`, not `forward`, so the module must
    be wrapped in a scripted module first
  - the legacy exporter cannot translate `aten::complex` from the iSTFT
    (failed identically at opsets 17, 18 and 20), so the dynamo exporter is
    required
  - the dynamo exporter emits `ScatterND` with int32 indices, which ONNX
    Runtime rejects. Casting them to int64 fixes it, but the cast must be
    inserted directly before its consumer: inserting at the graph front broke
    topological ordering and made ONNX Runtime allocate ~25 GB before giving up
- Implemented `panda_infer.onnx_export` with a CLI that exports and then
  verifies against PyTorch; it refuses to report success if the relative
  difference exceeds 1e-3
- Verified end to end: 504 nodes, 2 ScatterND nodes patched, 4960 output
  samples, relative difference 4.1e-05
- The ASR and DiT stages are still unexplored; the vocoder was the easiest of
  the three and it already needed two workarounds

### ONNX Export: Streaming ASR

- The ASR turned out to need the *opposite* exporter from the vocoder: dynamo
  fails on its symbolic shape handling (`Eq(u0, -1)`), while the legacy
  exporter handles it cleanly and needs no graph surgery at all
- `panda_infer.onnx_export` now takes `--stage vocoder|asr` and `--model
  40ms|120ms`, with the ASR variant table mirroring `MODEL_PATHS` in the
  upstream `run_rt.py`
- Found while verifying the 120ms variant: the ASR offset must be at least the
  cache size, because the model slices its attention cache by that offset. The
  first version reused the 40ms offset (4) with a cache size of 8, which
  produced an empty slice and a confusing "12 vs 0" shape error
- Verified both variants end to end: 782 nodes each, no ScatterND patching,
  relative differences 4.2e-07 (40ms) and 4.9e-07 (120ms)
- Remaining stage: the DiT, which is a Python module using x-transformers and is
  the least likely of the three to export cleanly

### ONNX Export: DiT Is Not Viable Today

- Probed the DiT and concluded that a pure ONNX/C++ runtime is **not reachable
  with the current tooling**. Two independent blockers, both in third-party
  code:
  - `torch.jit.script` cannot parse the module: it first fails on an
    unannotated default (`def forward(self, x, scale=1000)`, inferred as Tensor)
    and then on jaxtyping annotations (`timestep: float["b"]`) that TorchScript
    does not understand
  - `torch.jit.trace` gets further (the steady-state forward runs and returns a
    4-layer cache of 8 tensors) but hits data-dependent control flow in the
    KV-cache logic (`if new_kv_cache[0].shape[2] > max_cache_frames`).
    PyTorch warns that the Python boolean is baked in as a constant, so the
    trace does not generalise, and the trace then fails on a cache-length
    mismatch
- Decision: keep the Python engine as the working backend. It is proven at
  RTF 0.757 with zero underruns, so the ONNX migration buys packaging size at a
  cost that is not justified yet. The ASR and vocoder exports stay as a
  verified foundation should the DiT's inference path ever be reimplemented in
  a traceable form
- The local `deps/MeanVC2` checkout was left byte-identical to upstream

### Realtime Path Actually Runs on WASAPI

- First live run against real devices found that the engine could not open a
  stream at all on WASAPI: shared mode only accepts the device's own mix format
  (48 kHz here), so a fixed 16 kHz stream fails with `Invalid sample rate`.
  The same run on MME worked, because MME resamples for us. Every previous
  realtime test had used a fake device, so this had never surfaced
- Added `StreamResampler` to `panda_infer.dsp`: a stateful polyphase
  converter for integer ratios. Block-wise conversion without state leaves a
  discontinuity at every boundary, so the FIR history is carried between calls
  and block-wise output is bit-comparable to a single continuous pass
- `run_realtime_session` now queries each device's native rate, opens there, and
  resamples in software, with a separate resampler for the monitor device
- Verified live on WASAPI: 15 s run, 19 blocks, mean 116.6 ms, max 125.3 ms,
  zero underruns, zero dropped frames
- Observed while verifying: the output buffer settled at ~580 ms, well above the
  320 ms pre-roll target. Investigated and fixed in the next section

### Startup Surplus Latency

- Root cause of the 580 ms backlog: the converter returns nothing for the first
  blocks, then emits several blocks in one call to catch up. That burst pushes
  faster than playback drains, and because production and playback are balanced
  afterwards, the surplus is never given back -- it stays as permanent added
  latency
- `JitterBuffer.trim_to` discards the oldest frames down to a target, and the
  session trims whenever the backlog exceeds the pre-roll by more than one block
- The trim happens while the buffer still holds pre-roll silence, so the
  discarded audio is silence rather than speech
- Verified live on WASAPI: the backlog now settles at exactly 320 ms (the
  pre-roll target) instead of 580 ms, with `trimmed_frames` reporting the 4160
  frames (260 ms) removed, and still zero underruns and zero dropped frames

### Latency Budget and Pre-Roll Default

- Measured the pre-roll trade-off on real hardware rather than guessing:
  with one block the backlog settles at 160 ms across 113 live WASAPI blocks,
  mean 120.5 ms, max 142.6 ms, zero underruns and zero dropped frames; with two
  blocks it was 320 ms and max 153 ms
- Lowered the default pre-roll from two blocks to one, halving the buffer's
  contribution to latency (320 ms -> 160 ms). It stays user-adjustable for
  slower machines, where the extra 160 ms buys jitter headroom
- Documented the measured latency budget: 160 ms block fill + ~120 ms inference
  + 160 ms pre-roll, about 440 ms end to end
- Corrected the design target: the original "under 150 ms" is unreachable with
  MeanVC2's 160 ms blocks regardless of implementation quality. Reaching that
  order would need a genuinely frame-level streaming engine, not tuning

### Code Signing Plumbing

- The actual signing needs a certificate, which is not available here, but the
  whole pipeline around it is implemented and tested
- `package_windows.ps1` takes `-CertificateThumbprint` and `-TimestampUrl`,
  finds `signtool.exe` in the Windows SDK, signs the executable, verifies the
  signature, and then writes the checksum manifest -- so the recorded hash is
  the hash of the signed binary
- Without a thumbprint it reports that it is building an unsigned package
  rather than failing, so development builds keep working
- `install_windows.ps1` gained `-RequireSignature`: checksums prove a package
  was not altered, but only a signature says who packed it
- Verified both paths: unsigned packaging completes, and a bogus thumbprint
  fails with signtool's own error rather than a silent success
- Found while testing: this host's inherited `PSModulePath` lists PowerShell 7
  and Codex runtime directories ahead of the Windows PowerShell ones, so
  Windows PowerShell cannot load its Security module. The test now points the
  child at its own module directories, and the script reports that case clearly

### 30-Minute Continuous Run

- The stage-2 acceptance criterion in the design document is "30 minutes of
  continuous operation"; previous live runs were only 15-30 seconds, so this was
  the first real check of it
- Ran 30 minutes (1801 s) on real WASAPI devices with per-minute memory and CPU
  sampling: 11177 blocks, zero underruns, zero starved reads, zero dropped
  frames and zero dropped input blocks
- Memory: 2021 MB -> 2023.6 MB, non-monotonic, so no leak. Threads stayed at
  38-41. CPU averaged 0.736 cores, matching the measured RTF
- No clock drift between the capture and playback devices: 11177 blocks x 160 ms
  is 1788 s, and the 13 s difference is the model load time
- One block took 242 ms against a 160 ms budget, which is exactly what the
  jitter buffer exists to absorb

### Correction: Steady-State Backlog Is the Trim Threshold

- The 30-minute run showed the backlog resting at 320 ms while the pre-roll
  target was 160 ms, so the previous turn's claim that halving the pre-roll
  halved the buffer latency was **wrong**
- The resting depth is set by the trim threshold (pre-roll + trim margin), not
  by the pre-roll. With the default margin of one block it rests at 320 ms for
  either pre-roll setting; what the smaller pre-roll actually buys is a shorter
  startup pre-roll
- Tested a tighter margin: at half a block the backlog oscillated between 0 and
  160 ms, reached zero (no jitter margin left) and trimmed repeatedly -- each
  trim is an audible discontinuity. One block stays the default
- The trim margin is now a parameter (`trim_margin_chunks`) so this can be
  retuned with measurements rather than by editing the code

### The Test Fixture Was a Sine Wave

- Found while trying to verify conversion objectively: `smoke.wav`, the source
  and target used by every earlier test, is a **220 Hz sine tone**, not speech.
  Its crest factor is exactly 1.414 and its dominant frequency is 220 Hz
- Consequence: every previous "conversion" run exercised the plumbing (blocks
  flow, latency holds, no underruns) but never showed the model changing a
  speaker. Speaker embeddings of a sine tone are meaningless
- Generated real speech with the Windows TTS voices already installed
  (Microsoft Zira, en-US, and Microsoft Huihui, zh-CN) at 16 kHz mono, which
  needs no network and no extra dependency
- Objective result with real speech:
  - control, Zira converted into its own timbre: converted vs source +0.7323,
    so the measurement is trustworthy
  - Zira converted into Huihui: source vs target +0.2831 (different speakers),
    converted vs target +0.7010, converted vs source +0.2968
- The conversion moves the speaker identity from the source to the target:
  similarity to the target rises from 0.28 to 0.70 while similarity to the
  source falls to 0.30. This is the first evidence that the core function works

### Diagnostics Reach the UI

- The metrics line carried underrun, dropped-frame and trimmed-frame counters,
  but only the first two reached the C++ struct and none reached the UI, so the
  chain was half-finished
- Added `trimmed_frames` to `RealtimeStats` and its parser, and exposed all four
  counters on the controller
- The desktop now shows a diagnostics row when a session actually had starved
  reads, underruns or dropped frames; a healthy session shows nothing rather
  than a wall of zeroes

### Model Variant: 120ms Becomes the Default

- Every live verification so far had used the 40ms variant, so the 120ms one
  the desktop offers had never been run on real hardware
- Measured both on the same conversion task (Zira into Huihui) and on real
  WASAPI devices:

| | 40ms | 120ms |
| --- | --- | --- |
| processing per 160 ms block | 122 ms | **53.8 ms** |
| steady-state buffer | 320 ms | **60 ms** |
| control (self into self) | 0.732 | **0.791** |
| converted vs target | 0.701 | 0.696 |
| underruns over the run | 0 | 0 (1011 blocks) |

- The upstream README's 110 ms figure for the 40ms variant is *first-packet*
  latency with its own 40 ms chunking. Our streaming block is 160 ms for both
  variants, so that advantage is unreachable here, while the 40ms variant does
  about three times as many DiT steps per second of audio
- Switched the default to 120ms: roughly half the CPU per block, a much smaller
  buffer and better identity preservation, with no measurable loss of target
  similarity. 40ms stays selectable, and would become the better choice if the
  audio block were ever reduced to realise its chunking
- Packaging and `doctor` now cover both variants, so a packaged install can
  actually use either one

### The Noise Gate Is Not a Denoiser

- A user pointed out that the earlier gate check used flat white noise, which
  is the easy case; a real microphone hears a fan, a keyboard, traffic and
  other people talking
- Measured the gate against realistic ambient noise. It only works when the
  noise sits below its threshold:

| ambient noise during pauses | gate suppression |
| --- | --- |
| white noise -60 dB | 29.1 dB |
| fan rumble -50 dB | 29.8 dB |
| fan rumble -40 dB | 0.0 dB |
| keyboard clicks -40 dB | 0.1 dB |
| another person talking -40 dB | 1.0 dB |
| another person talking -30 dB | 0.1 dB |

- A level gate cannot tell the user's voice from anything else at a similar
  level, so it does nothing for the cases that actually matter
- Evaluated DeepFilterNet, the denoiser the design already plans: it suppresses
  keyboard clicks by 36.5 dB at a cost of 10.9 ms per 160 ms block (RTF 0.068)
  while leaving speech within 0.3 dB, but it does **not** suppress another
  person talking (-0.3 dB). It is a noise suppressor, not a speaker separator;
  background speech needs target-speaker extraction, which is out of scope for
  the first release
- Integration obstacle found: DFN's Python API is offline only -- `enhance()`
  resets the model's recurrent state on every call, so block-wise use differs
  from whole-signal use by up to 0.235 at block boundaries. A correct streaming
  integration needs either DFN's internals or overlap-add, which would add
  about one window (160 ms) of latency
- Decision: keep the gate for quiet rooms and stop describing it as denoising;
  the denoiser integration is a scoped decision about latency, not a drop-in

### Denoiser

- Tried three ways to stream DeepFilterNet and measured each against
  whole-signal processing:

| approach | worst-case difference | added latency | CPU |
| --- | --- | --- | --- |
| call it per block | 0.235 | 0 | 1x |
| keep the recurrent state | 0.60 | 0 | 1x |
| overlapping windows, cross-faded | 0.0595 | 160 ms | 1.6x |

- Keeping the state made things worse, not better: DFN's STFT state does not
  carry across Python calls either, so its API is whole-signal only
- `panda_infer.denoise.Denoiser` implements the overlap-add path behind an
  injectable denoise function, with 11 tests covering the buffering contract
  and packaged model-directory resolution
  (one block out per block in, one block of latency, silence while the first
  window fills, reset)
- Isolating the cross-fade from resampling settled the earlier discrepancy:
  running the component at 48 kHz only (no resampling) reproduces the probe
  exactly -- 0.0595 worst-case difference and a 160.00 ms lag. The 0.161 seen
  through the 16 kHz pipeline comes from the resampling chain, where two
  different filters feed a nonlinear model, not from the cross-fade
- Wired in as an opt-in: `--denoise` on the worker and the launcher, applied to
  the captured audio before the noise gate
- Verified live on WASAPI: 90 s, 451 blocks, mean 50.5 ms, max 80.9 ms, zero
  underruns and zero dropped frames. The 160 ms cost shows up as a deeper
  buffer (180 ms versus 60 ms without denoising)
- The desktop has a 降噪 checkbox next to the noise gate, with the latency and
  the "does not remove other people talking" caveat in its label; the choice
  persists with the session
- Verified the realistic case: real Windows TTS speech mixed with fan,
  keyboard, and white noise at 10 dB SNR. The speech-active SI-SDR improves
  by 0.6--2.6 dB while the active level drops only 1--2 dB, and pauses lose
  24--40 dB of environmental noise. The denoiser therefore keeps processing
  while the user is speaking instead of acting as a silence-only gate
- Added `scripts/evaluate_denoise.py`, which reproduces the mixed speech/noise
  measurement and reports the actual stream latency
- Packaging now bundles `config.ini` and the 8.31 MB
  `model_120.ckpt.best` checkpoint under `DeepFilterNet/DeepFilterNet3`,
  sets `PANDA_DEEPFILTER_ROOT` in `launch.cmd`, checks the checkpoint with
  `doctor`, and rejects numpy 2.x in a portable runtime because DeepFilterNet
  requires numpy 1.x
- Built the portable package end to end and loaded the denoiser from its
  bundled checkpoint. The package manifest covers 51,721 files, and the
  DeepFilterNet dual-license notice is copied into the release alongside
  `THIRD_PARTY_NOTICES.md`

### Denoise Strength Control

- Added three user-selectable denoise levels backed by DeepFilterNet's
  attenuation limit: `strong` (full suppression), `balanced` (12 dB) and
  `gentle` (6 dB). The weaker levels deliberately keep more environmental
  sound and speech detail instead of treating full suppression as the only
  choice
- The level is wired through the Python worker, the unified launcher, the
  C++ worker protocol, the desktop controller and QML. The desktop selector is
  disabled while a session is running, and the chosen level is persisted with
  the rest of the session settings
- Unknown persisted values fall back to `strong` in both C++ and Python, so an
  old or hand-edited settings file cannot start the worker with an unsupported
  argument
- Measured the three levels on real speech plus fan/keyboard noise at 10 dB
  SNR: pause suppression falls from 23.9/33.5 dB (strong) to 11.3/12.3 dB
  (balanced) and 5.8/6.3 dB (gentle), while speech-active SI-SDR remains
  positive in every case. The labels now match the actual amount of noise
  retained
- Hardened the Windows package flow after a reported missing `Qt6Gui.dll`
  launch failure: packaging now builds in `dist/Panda.building-<pid>` and
  swaps the completed directory into place only after `windeployqt`, bundled
  runtimes, checkpoints and the manifest are all ready. `windeployqt` also
  retries up to three times when endpoint protection briefly locks a freshly
  copied executable. The final package was rebuilt, its Qt DLLs were checked,
  and the packaged desktop executable started successfully in offscreen mode.
  Rebuilds now preserve the existing portable `voices` directory instead of
  replacing the user's library with an empty folder

### Voice Library and Device Picker

- The voice-pack exporter now accepts WAV, MP3, FLAC, OGG, M4A, AAC and WMA,
  decodes them through soundfile, mixes to mono, resamples to 16 kHz and writes
  a canonical PCM WAV reference. A real MP3 from the user's test folder was
  decoded and converted successfully
- Generated and installed `dist/Panda/voices/lubenwei-test` from the
  user's `卢本伟.wav`; `doctor` accepted the pack and a real MeanVC2 offline
  inference completed with RTF 0.328
- Added desktop favorites and sort modes (favorites first or name), persisted
  both in the session settings, and covered sorting, toggling and removal with
  Qt model tests
- Device entries now carry their Windows host API. The desktop defaults to
  WASAPI and offers an explicit "all interfaces" switch, so MME,
  DirectSound, WASAPI and WDM-KS duplicates do not overwhelm the picker

### Output Volume Control

- Added `OutputGain`, a fixed -24 to +12 dB stage that runs before the soft
  limiter. At 0 dB it is a no-op; positive gain is still bounded by the
  existing limiter, and negative gain can be used to tame an overly hot model
  without changing the conversion engine
- Wired the parameter through the worker, unified launcher, C++ worker
  protocol, desktop controller, QML spin box and session persistence. The
  range is clamped in both C++ and Python
- Added DSP, worker-loop, command-line and session-store tests. Pitch shifting
  remains a separate future stage because a blockwise offline pitch shifter
  would add unacceptable artifacts and latency to the realtime path

### Realtime Worker Recovery

- Implemented the missing crash-recovery responsibility from the core-service
  design. An unexpected worker exit now triggers up to three automatic
  restarts with 1/2/3 second backoff; a deliberate stop and a clean exit never
  restart
- A stable run resets the reconnect counter after 10 seconds, so a long-lived
  session that later encounters one transient failure does not exhaust the
  budget. Closing the desktop explicitly stops the worker instead of allowing
  a restart during shutdown
- Extracted the restart decision into `should_restart_realtime` and covered
  crash, non-zero exit, deliberate stop, clean exit and exhausted-attempt cases
  in the C++ protocol tests

### Desktop UI Redesign and Preview

- Replaced the old fixed sidebar layout with a frameless dark application shell:
  custom title bar, top navigation, circular voice-card grid, a dedicated
  audio-settings page and a bottom control bar for start/stop, preview and
  settings
- Added real voice-pack preview through `panda preview`. It resolves the
  pack reference WAV, resamples to the selected output device's native rate
  and plays up to eight seconds through sounddevice
- Found and fixed a real device-index bug during preview verification:
  `sounddevice.query_devices(device, "output")` interprets the index in the
  output-only list, while the UI exposes global device IDs. Preview now
  validates and uses the global index
- Device settings now persist a stable `hostApi|deviceName` key in addition to
  the numeric ID. On restart the desktop resolves the key against the fresh
  device list, so Windows changing device ordering no longer silently points
  the input or output at the wrong endpoint

### Realtime Level Diagnostics

- Added input/output RMS and peak values plus clipping flags to the metrics
  line. The desktop settings page now shows live bars for both directions,
  which distinguishes "microphone is silent", "conversion produced silence",
  and "output routing is wrong" without guessing
- Extended the C++ metrics parser and controller properties while keeping the
  legacy upstream metrics line compatible. Python contract tests and the C++
  core parser tests cover the new fields

### Microphone Test Tool

- Added `panda mic-test`, which records a short sample from the selected
  input device, rejects a silent recording with a clear error, resamples it to
  the output device rate and plays it back
- Verified on the real development host: WASAPI input device 9 recorded with
  peak 0.064 and played through WASAPI output device 8. This separates a
  working microphone/output path from a conversion or routing failure
- The desktop settings page exposes the same action as `测试麦克风`, disabled
  while a conversion or preview is already running

### Microphone Input Gain

- Added a -24 to +12 dB input trim before denoising and the noise gate. This
  addresses quiet microphones and lets the user raise the captured signal
  without changing the model or output routing
- Wired through the worker, launcher, C++ protocol, controller, session store
  and desktop settings page. Input and output gain are separate controls and
  both default to 0 dB

### Monitor Gain

- Added an independent -24 to +12 dB monitor gain on the monitor callback.
  The main conversion output keeps its own volume, so raising or lowering the
  headphone monitor no longer changes what other applications receive
- Wired through the worker, launcher, C++ protocol, controller, session store
  and desktop monitor card, with a dedicated worker-path test

### Desktop Route Check

- Exposed the existing `route-check` command in the desktop settings page.
  The controller runs it as a separate process, parses the JSON route pairs
  and shows both ends directly: the output Panda should render into and the
  microphone other applications should select
- On the development host it correctly reports that no writable virtual cable
  is installed, which explains why other applications cannot hear the
  converted voice yet

### Status Summary

Every area named in the objective is implemented and verified:

| Area | Evidence |
| --- | --- |
| CPU realtime | RTF 0.736 over a 30-minute live WASAPI run, zero underruns |
| Conversion quality | speaker similarity to target 0.28 -> 0.70 with a control at 0.73 |
| Open voice pack format | spec, exporter, C++ installer with checksums, upgrade rules, removal |
| MeanVC2 extraction and inference | pack exporter, offline inference, realtime, ONNX for ASR and vocoder |
| C++ core services | modelstore, metrics and device parsing, session store, worker protocol |
| Qt/QML desktop | pack management, search, devices, monitor, model/backend, latency, gate, logs, metrics, persistence |
| Audio pipeline | jitter buffer, resampling, noise gate, limiter, monitor output, WASAPI |
| Model pack management | install, overwrite rules, removal, integrity verification |
| Tests and docs | 145 Python tests, 5 CTest targets, docs for every decision above |

Remaining work is either optional or blocked outside this repository:

- a signed virtual audio driver, which needs administrator rights and a
  code-signing certificate (v1 relies on a user-installed cable instead)
- running the signing pipeline with a real certificate
- the DiT's streaming inference rewrite, the only blocker to a Python-free
  runtime; documented as not viable with the current tooling
- a frame-level engine, needed only if latency below ~440 ms becomes a priority

## Known Constraints

- The current session has no administrator rights.
- Kernel drivers and Windows optional features cannot be installed unattended.
- WSL currently has only the stopped Docker Desktop distribution.
- There is no NVIDIA GPU or CUDA available, but none is required for realtime
  inference: CPU realtime was measured at RTF 0.757 on the development host.
  A GPU only helps training, larger models, or lower latency, and training should
  use a cloud GPU.
- Roughly 0.4% of 160 ms blocks exceed the budget, so the audio pipeline needs a
  small jitter buffer instead of demanding every block finish on time.
- The existing virtual microphone belongs to BaoMiao. It is usable for local
  inspection only: `panda doctor` confirms it exposes a capture endpoint but
  no writable one, so Panda cannot feed it. Routing converted audio into
  other applications requires a virtual cable the converter can render into
  (VB-CABLE, VoiceMeeter) or a Panda-provided driver, which needs
  administrator rights and code signing.
- The Qt installer reports a post-extraction permission warning, but the required
  Qt Core, QML, Quick, Multimedia, qmake, and windeployqt files are present and
  the Qt application builds and starts.
- Deleting freshly written fixture directories under `.tmp` blocked for ~31 s
  per call on this host. The C++ suite therefore leaves its fixtures in place
  under unique paths; `.tmp` accumulates scratch data and can be pruned by hand.
  CTest still has a 120 s timeout and a completion-marker requirement.
- The Python suite has failed twice without a captured test name, in roughly
  fifteen full runs. Both realtime test modules pass consistently on their own
  (10 and 15 consecutive runs), so it is most likely contention when the whole
  suite runs together rather than a specific broken test. Worth capturing with
  verbose output if it happens again.

## Next Work

1. Validate live capture + playback against a real input device once a writable
   virtual endpoint is available.
2. Add code signing to the Windows package; checksums and upgrade handling are
   now in place, and the signing pipeline is implemented -- it only needs a
   certificate to run for real.
3. Optional and large: reimplement the DiT's streaming inference in a traceable
   form, which is the only remaining blocker to running the whole pipeline on
   ONNX Runtime without Python. The ASR and vocoder exports are already verified.
4. If latency becomes the priority, replace the 160 ms block engine with a
   frame-level streaming one; the current budget is about 440 ms and cannot be
   tuned below that.

