
import sys, subprocess, ensurepip, traceback, os

def _run(cmd):
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=False)
        return p.returncode, p.stdout
    except Exception as e:
        return 1, f"Exception: {e}\n{traceback.format_exc()}"

def install_deps(packages):
    log = []
    try:
        ensurepip.bootstrap()
        log.append("ensurepip: ok")
    except Exception as e:
        log.append(f"ensurepip failed: {e}")

    python = sys.executable or sys.argv[0]
    if not python:
        return False, "Unable to locate Blender's Python executable."

    # Upgrade pip
    code, out = _run([python, "-m", "pip", "install", "--upgrade", "pip"])
    log.append(out)

    # Install requested packages
    cmd = [python, "-m", "pip", "install"] + list(packages)
    code, out = _run(cmd)
    log.append(out)

    ok = (code == 0)
    return ok, "\n".join(log)
