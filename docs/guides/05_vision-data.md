# The vision data: fetch, render, split, and build the cases

How to get from a fresh clone to every vision source fetched, rendered onto the fly's lattice, split by
geometry family with the leakage test passing, and the sixteen cases rendered at their six levels. The
design behind each step is in [architecture/05](../architecture/05_vision-data.md); the environments are
those of [guide 01](01_environments.md) and [guide 03](03_network-engine.md).

## 1. Roots and space

Nothing heavy is committed. Two roots hold it, both outside the repository:

| Variable | Holds |
|---|---|
| `CONECTOMA_DATA_ROOT` | `vision/<source>/data` (the fetched clip archives), `vision/<source>/rendered` (their lattice renderings and manifest), `vision/<source>/fetch-log.jsonl`, and `vision/cases` (the case renderings and their manifest) |
| `CONECTOMA_MODELS_ROOT` | the engine's root, where the engine downloads Sintel and renders it (`flyvis/SintelDataSet`, `flyvis/renderings`) |

Space, measured: TartanAir 114.5 GB (2,244 clips of 32 frames from 148 environment-difficulty pairs),
Spring 17.1 GB (67 clips), Hypersim 0.47 GB (46 test scenes), Sintel 14.3 GB (the engine keeps its two
archives, 6.7 GB, next to what it extracts), the panoramas well under a gigabyte. The renderings are small:
a 32-frame clip on the 721-column lattice is a few hundred kilobytes compressed, and every case at every
level together is tens of megabytes.

What is committed is what CI can check: `data/derived/vision/splits.json` and `tartanair-clips.csv` (the split
of every clip and the leakage result), `data/derived/vision/cases.json` (the registry, the clips each case
drew, and what each level measured) and `data/derived/vision/flygym-eye.json` (FlyGym's eye on the lattice).

## 2. Fetch

Every fetch lists the remote archives over HTTP ranges and pulls only the selected members, each checked
against its CRC32. Each is resumable: a rerun reads the source's `fetch-log.jsonl` and skips what is done.

```bash
export CONECTOMA_DATA_ROOT=/data/conectoma/raw
export CONECTOMA_MODELS_ROOT=/data/conectoma/models
python data-pipeline/run.py fetch-vision --source tartanair      # every environment, both difficulties
python data-pipeline/run.py fetch-vision --source spring
python data-pipeline/run.py fetch-vision --source hypersim
python data-pipeline/run.py fetch-vision --source sintel         # the engine's downloader and rendering
```

`--environments` restricts TartanAir to named environments; `--workers` sets the parallel member requests
(12 by default). What the selection takes is declared in `data-pipeline/config/vision.yaml`, and every run
records the digest of that file next to its output. The panoramas of case C13 are fetched after the splits
exist (section 5), because the case draws its clips from them.

## 3. Render onto the lattice

```bash
python data-pipeline/run.py render-vision --source tartanair --workers 6
python data-pipeline/run.py render-vision --source spring
python data-pipeline/run.py render-vision --source hypersim
```

Each clip is rendered once and checked against contract 1; a rendering whose stamp (render version and
source size) is current is kept on a rerun. The command exits non-zero if any clip is rejected or fails,
and `rendered/manifest.json` lists every clip with its statistics, its SHA-256, and the reasons for any
rejection. Sintel is rendered by the engine itself during its fetch; the product's own renderer is checked
against that rendering by `tests/test_vision_cases.py` wherever both are on the machine.

## 4. Split, and the leakage gate

```bash
python data-pipeline/run.py build-splits
```

It assigns every rendered TartanAir clip to train, validation, calibration or test by its geometry family
and writes the two committed files. It exits non-zero on any leakage: a family or environment in two splits,
or two identical frames (equal lattice luminance) in two splits. The families the cases draw from are always
in test. CI re-checks the family and environment conditions from the committed table.

## 5. The cases

```bash
python data-pipeline/run.py fetch-vision --source panorama       # C13's panoramas, after the splits
python data-pipeline/run.py build-cases --workers 4              # every case at its six levels
python data-pipeline/run.py build-cases --cases C10 C11 C12      # or some of them
```

Each case draws its clips once, from test data only, and renders them at all six levels
(`data-pipeline/config/cases.yaml`). A rendering is kept on a rerun only if its stamp matches the registry's
digest, the render version and a digest of the code it depends on, so any change to that code renders the
cases again. The committed `cases.json` is written when every case is present; a run over some cases
updates the manifest and leaves the committed file alone.

The FlyGym cases (C10 to C12) render through MuJoCo's OpenGL renderer and need a context to render into;
the FlyGym test skips where none can be created, as on a headless runner.

## 6. Long runs on Windows

Fetching TartanAir and rendering it take hours. A job started from a shell is a child of that shell and dies
with it, and a Task Scheduler job registered as interactive runs its `cmd.exe` in a visible console that
closes the job if the window is closed. What survives both: a scheduled task whose action is `pythonw.exe`
running a launcher that starts the job's `.cmd` with no window at all.

```python
# launch.pyw: run a job's .cmd with no console window
import subprocess, sys
from pathlib import Path
script = Path(__file__).with_name(sys.argv[1])
subprocess.call(["cmd.exe", "/c", str(script)], creationflags=subprocess.CREATE_NO_WINDOW)
```

```powershell
$settings = New-ScheduledTaskSettingsSet -Priority 4 -ExecutionTimeLimit (New-TimeSpan -Hours 72)
$action = New-ScheduledTaskAction -Execute "<venv>\Scripts\pythonw.exe" -Argument "<dir>\launch.pyw fetch.cmd"
Register-ScheduledTask -TaskName ConectomaFetch -Action $action -Settings $settings -Force
Start-ScheduledTask -TaskName ConectomaFetch
```

The `.cmd` sets the two roots, redirects standard output and error to separate files with plain `>` and
`2>`, and ends with `echo EXITCODE=%ERRORLEVEL%`. Priority 4 matters: the scheduler's default priority also
lowers the job's I/O priority, and a download then writes at a fraction of the disk's speed.

## 7. Checks

```bash
python -m pytest tests/test_vision_data.py tests/test_vision_cases.py
```

The fetch tests run against a local range server; the renderer is checked against the engine's `BoxEye`;
contract 1 is checked by building clips that break each rule; the synthetic and panorama cases are checked
for exactness (the flow carries each frame onto the next, depth is the planes'); every variant is checked
against its unit. With `CONECTOMA_MODELS_ROOT` pointing at a root holding the engine's Sintel rendering, the
parity test compares the product's rendering of the held-out sequences with the engine's.
