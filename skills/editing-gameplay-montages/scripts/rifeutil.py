"""RIFE (AI frame interpolation) loader shared by prep / densify / repair / fixends / ingest / rife_compare.

The Python binding reads the network layout from the NAME of the model directory, so the path
must keep "rife-v4.25" (or whichever version) in it.

Environment:
  RIFE_GPU    Vulkan device number, default 0 (a laptop with an integrated and a dedicated GPU may list the dedicated one
              as 1: the lines the binding prints when it starts name them). RIFE_GPU=-1 (or "cpu") runs on the CPU, see below.
  RIFE_MODEL  full path of the model folder (the one that holds flownet.bin), default models/rife-v4.25.

CPU fallback (RIFE_GPU=-1): works with the same network (the pictures differ from the GPU's in the last digits), but slow. Measured with a 1344x1080 frame pair on a
12-thread CPU, other programs running: 2.4 s per sub-frame (8 to 12 threads; 6.8 s with the 2 threads the GPU path uses),
against 0.17 s on a GTX 1650: 15 times slower. A 30 s edit needs about 15 000 to 25 000 sub-frames: 10 to 17 hours on the
CPU, 45 to 70 minutes on that GPU. python ranges.py prints the sub-frame count of the edit; multiply it by your PC's s/frame.

Without a usable Vulkan GPU the binding does NOT stop: it silently runs on the CPU (also for an out-of-range RIFE_GPU,
measured: 8 s per frame with 2 threads), and a 3 s edit would take an hour without a word. load() therefore checks the
GPU count first and only goes to the CPU when RIFE_GPU=-1 asks for it."""
import os, sys

DEFAULT = "rife-v4.25"          # best of seven versions on real gameplay triplets (see rife_compare.py)
LAYOUT = ("rife-v2", "rife-v3", "rife-v4", "rife4", "rife-4")      # the binding picks the network layout from these in the path
JPG = None                       # set on first use (cv2 flags), see write_jpg


def finish(code=0):
    """Call as the very last statement of a script that loaded the model. The Vulkan runtime behind the
    binding crashes while the process unloads (segmentation fault, exit code 139; 5 on Windows) although all the work
    is done and written; this ends the process without running the unload handlers, with the exit code given (0)."""
    sys.stdout.flush()
    sys.stderr.flush()
    if os.name == "nt":
        import ctypes
        k = ctypes.windll.kernel32
        k.GetCurrentProcess.restype = ctypes.c_void_p
        k.TerminateProcess(ctypes.c_void_p(k.GetCurrentProcess()), code)
    os._exit(code)


def die(msg, code=1):
    """Print a message and end the process the way finish() does (a plain sys.exit would end in the Vulkan crash code once the GPU was opened)."""
    sys.stdout.flush()
    print(msg, file=sys.stderr, flush=True)
    finish(code)


def model_dir(name=DEFAULT):
    env = os.environ.get("RIFE_MODEL")
    cands = [env] if env else [f"models/{name}", f"dl_rife_models/{name}",
                               os.path.expanduser(f"~/.claude/skills/editing-gameplay-montages/models/{name}")]
    for c in cands:
        if c and os.path.exists(os.path.join(c, "flownet.bin")):
            path = os.path.abspath(c)
            break
    else:
        if env:
            die(f"RIFE_MODEL={env} has no flownet.bin: it must be the model folder itself (e.g. .../models/{name}), not the folder above it. "
                f"Unset RIFE_MODEL to use ./models/{name}.")
        die(f"RIFE model {name} not found (it needs flownet.bin and flownet.param). Looked for: "
            + ", ".join(os.path.abspath(c) for c in cands) + f". The scripts run from the project folder ({os.getcwd()}): "
            f"copy the skill's models folder into it (cp -r $SK/models . , pipeline.md Setup), keep the folder name {name}, "
            "or set RIFE_MODEL to the full path of the model folder.")
    if not os.path.exists(os.path.join(path, "flownet.param")):
        die(f"{path} has flownet.bin but no flownet.param: the model folder is incomplete, copy it again from the skill's models folder.")
    if not any(t in path.replace("\\", "/") for t in LAYOUT):
        die(f"{path}: the Python binding reads the network layout from the folder name, and '{os.path.basename(path)}' has no RIFE version in it "
            f"(rife-v4.25, rife-v4.6 ...). Rename the folder back to {name} (or set RIFE_MODEL to a folder whose name has one).")
    return path


def gpu_setting():
    raw = os.environ.get("RIFE_GPU", "0").strip().lower()
    if raw == "cpu":
        return -1
    try:
        return int(raw)
    except ValueError:
        die(f"RIFE_GPU={raw!r} is not a number: use the Vulkan device number (0, 1, ...), or -1 for the CPU (about 15 times slower).")


def load(name=DEFAULT):
    model = model_dir(name)                           # cheap checks first: no GPU is opened for a missing model
    try:
        from rife_ncnn_vulkan_python import Rife
        from rife_ncnn_vulkan_python import rife_ncnn_vulkan_wrapper as wrapper
    except ImportError as e:
        die(f"cannot load the RIFE binding ({e}). It is installed with the requirements, for Python 3.11 only (it has no wheels for newer "
            f"versions): run the scripts with the project's venv ({sys.executable} is not it, or lacks it): "
            "uv pip install --python venv311/Scripts/python.exe -r requirements.txt"
            + (" . A 'DLL load failed' also means the Microsoft Visual C++ Redistributable (x64) is missing: install it from microsoft.com." if "DLL" in str(e) else ""))
    gpu = gpu_setting()
    n = wrapper.get_gpu_count()                      # prints one line per device it finds (name, queues): that is the list to pick from
    if gpu >= 0 and gpu >= n:
        if n == 0:
            die("No Vulkan GPU is usable, so RIFE (the in-between frames) has nothing to run on: the graphics driver is missing, too old, "
                "or this is a remote session / virtual machine. Install the current driver from your GPU maker (NVIDIA, AMD or Intel: their site, "
                "not Windows' basic display driver), restart, and run this again.\n"
                "No GPU at all? RIFE_GPU=-1 runs it on the CPU instead: it works, but about 15 times slower (measured 2.4 s per sub-frame on a "
                "12-thread CPU against 0.17 s on a GTX 1650): a 30 s edit takes 10 to 17 hours. python ranges.py prints the number of sub-frames "
                "of your edit; at 2.4 s each is the time you would wait.   Example:  RIFE_GPU=-1 python prep.py ranges.json   (resumable, "
                "stop it with Ctrl+C and start it again any time).")
        die(f"RIFE_GPU={gpu}, but the binding found only {n} Vulkan GPU{'s' if n > 1 else ''} (listed just above, numbered "
            f"{'0' if n == 1 else '0 to %d' % (n - 1)}). Unset RIFE_GPU{'' if n == 1 else ' or set it to one of those numbers'}; "
            "RIFE_GPU=-1 runs on the CPU (about 15 times slower).")
    if gpu < 0:
        threads = os.cpu_count() or 2
        print(f"RIFE on the CPU (RIFE_GPU=-1, {threads} threads): about 2.4 s per sub-frame on a 12-thread PC, 15 times slower than a GPU. "
              "The work is resumable: Ctrl+C stops it, the same command continues.", file=sys.stderr, flush=True)
    else:
        threads = 2
    return Rife(gpuid=gpu, model=model, num_threads=threads)


def write_jpg(path, bgr):
    """Store a sub-frame: encoded, written under a temporary name and renamed, so a stopped script (Ctrl+C, closed window, power cut)
    never leaves a truncated file that the resume would take for finished work. A write that fails (disk full, folder not
    writable, antivirus lock) stops the script with the reason; cv2.imwrite alone returns False and the script goes on."""
    import cv2
    global JPG
    if JPG is None:
        JPG = [cv2.IMWRITE_JPEG_QUALITY, 95, cv2.IMWRITE_JPEG_SAMPLING_FACTOR, cv2.IMWRITE_JPEG_SAMPLING_FACTOR_444]
    ok, buf = cv2.imencode(".jpg", bgr, JPG)
    if not ok:
        die(f"cannot encode {path} as JPEG (picture {getattr(bgr, 'shape', None)})")
    tmp = path + ".part"
    try:
        with open(tmp, "wb") as f:
            buf.tofile(f)
        os.replace(tmp, path)
    except OSError as e:
        try:
            os.remove(tmp)
        except OSError:
            pass
        import shutil
        try:
            free = "%.1f GB free" % (shutil.disk_usage(os.path.dirname(os.path.abspath(path))).free / 2**30)
        except OSError:
            free = "drive not readable"
        if e.errno == 28:
            why = (f"the disk is full ({free}). Free some space (the store needs about 0.4 MB per sub-frame, python ranges.py prints the total), "
                   "or move the project folder to a bigger drive")
        else:
            why = (f"{e.strerror or e} ({free}). Check that the folder is writable, not read-only or synced / locked by another program "
                   "(OneDrive, antivirus 'controlled folder access'), and that the path is not too long")
        die(f"Cannot write {path}: {why}. Everything written so far is intact: run the same command again and it continues where it stopped.")


def is_jpeg_complete(path):
    """True when the file is a whole JPEG (starts with FFD8, ends with FFD9). A truncated file still decodes, with a grey bottom."""
    try:
        with open(path, "rb") as f:
            head = f.read(2)
            f.seek(-2, 2)
            tail = f.read(2)
    except OSError:
        return False
    return head == b"\xff\xd8" and tail == b"\xff\xd9"


class Tween:
    """Interpolation that stays inside the linear zone of RIFE's time step.

    Measured on v4.25 (ncnn) in October 2026: for a time step below about 0.08 the network returns the first
    frame unchanged, above 0.92 the second one, and it only catches up by about 0.25 (steps between 0.25 and
    0.75 are linear). In a 16x grid that made the sub-frames 15/16, 0 and 1/16 identical: slow motion stalled
    for an eighth of a frame at every real frame. So a step outside 0.2..0.8 is done in two stages, through
    the 0.25 or 0.75 frame. tag = anything that identifies the pair (the two stage frames are cached per pair)."""

    def __init__(self, rife):
        self.rife, self.tag, self.q = rife, None, {}

    def __call__(self, a, b, t, tag=None):
        if 0.2 <= t <= 0.8:
            return self.rife.process_cv2(a, b, t)
        if tag is None or tag != self.tag:
            self.tag, self.q = tag, {}
        if t < 0.2:
            if "lo" not in self.q:
                self.q["lo"] = self.rife.process_cv2(a, b, 0.25)
            return self.rife.process_cv2(a, self.q["lo"], t / 0.25)
        if "hi" not in self.q:
            self.q["hi"] = self.rife.process_cv2(a, b, 0.75)
        return self.rife.process_cv2(self.q["hi"], b, (t - 0.75) / 0.25)
