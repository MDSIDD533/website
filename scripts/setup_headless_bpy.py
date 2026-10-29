#!/usr/bin/env python3
"""Bootstrap helper for headless Linux environments running Blender (`bpy`).

Blender's official PyPI `bpy` wheel runs in headless background mode (`bpy.app.background == True`)
and uses Intel Embree CPU path tracing (`CYCLES`), which does not open X11/GL windows. However,
`bpy/__init__.so` dynamically links against client X11/GL shared library SONAMEs. On minimal
headless servers where system X11/GL packages are absent, this script builds minimal no-op
SONAME shims inside `bpy/lib/` (matching `$ORIGIN/lib` RUNPATH) so `import bpy` succeeds cleanly.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


CANDIDATE_SHIM_LIBS = [
    "libXrender.so.1",
    "libXxf86vm.so.1",
    "libXfixes.so.3",
    "libXi.so.6",
    "libxkbcommon.so.0",
    "libSM.so.6",
    "libICE.so.6",
    "libGL.so.1",
]


_CACHED_BPY_PROBE: dict[str, object] | None = None


def probe_bpy_subprocess(force_refresh: bool = False) -> dict[str, object]:
    """Probe `import bpy` on the main thread of an isolated subprocess and cache the result."""
    global _CACHED_BPY_PROBE
    if _CACHED_BPY_PROBE is not None and not force_refresh:
        return dict(_CACHED_BPY_PROBE)

    import importlib.util

    spec = importlib.util.find_spec("bpy")
    if not spec or not spec.origin:
        res: dict[str, object] = {"available": False, "version": "", "error": "bpy package is not installed"}
        _CACHED_BPY_PROBE = res
        return dict(res)

    proc = subprocess.run(
        [sys.executable, "-c", "import bpy; print(bpy.app.version_string)"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=20,
        check=False,
    )
    if proc.returncode == 0:
        ver = (proc.stdout or "").strip().splitlines()[-1] if (proc.stdout or "").strip() else "4.2"
        res = {"available": True, "version": ver, "error": ""}
        _CACHED_BPY_PROBE = res
        return dict(res)

    res = {"available": False, "version": "", "error": (proc.stderr or proc.stdout or "").strip()}
    return dict(res)


def ensure_headless_bpy() -> dict[str, object]:
    """Verify `import bpy` works in an isolated subprocess; build headless X11/GL shims in `bpy/lib` only if needed."""
    probe = probe_bpy_subprocess()
    if probe.get("available"):
        return {"available": True, "version": probe.get("version", ""), "shims_installed": False}

    err_msg = str(probe.get("error", ""))
    if ".so" not in err_msg:
        return {"available": False, "error": err_msg, "shims_installed": False}

    # Locate installed bpy package directory without importing it
    import importlib.util

    spec = importlib.util.find_spec("bpy")
    if not spec or not spec.origin:
        return {"available": False, "error": "bpy package is not installed", "shims_installed": False}

    bpy_so = Path(spec.origin).resolve()
    bpy_lib_dir = bpy_so.parent / "lib"
    if not bpy_lib_dir.is_dir() or not shutil.which("gcc") or not shutil.which("ldd"):
        return {
            "available": False,
            "error": "Missing bpy/lib, gcc, or ldd to build headless X11/GL stubs",
            "shims_installed": False,
        }

    ldd_initial = subprocess.run(
        ["ldd", str(bpy_so)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=False
    ).stdout
    missing = [lib for lib in CANDIDATE_SHIM_LIBS if f"{lib} => not found" in ldd_initial]
    if not missing:
        return {"available": False, "error": "No missing X11/GL libs detected", "shims_installed": False}

    with tempfile.TemporaryDirectory(prefix="sidd_bpy_shims_") as tmp:
        tmp_path = Path(tmp)
        for lib in missing:
            c_file = tmp_path / f"{lib}.c"
            c_file.write_text("int __sidd_headless_stub(void) { return 0; }\n", encoding="utf-8")
            subprocess.check_call(
                ["gcc", "-shared", "-fPIC", f"-Wl,-soname,{lib}", str(c_file), "-o", str(tmp_path / lib)]
            )

        env = os.environ.copy()
        env["LD_LIBRARY_PATH"] = f"{tmp_path}:{bpy_lib_dir}"
        ldd_reloc = subprocess.run(
            ["ldd", "-r", str(bpy_so)],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        ).stdout

        xkb_syms: set[str] = set()
        xkb_vers: set[str] = set()
        other_syms: set[str] = set()
        for line in ldd_reloc.splitlines():
            match = re.search(r"undefined symbol:\s+([A-Za-z0-9_]+)(?:,\s*version\s+([A-Za-z0-9_.]+))?", line)
            if not match:
                continue
            sym, ver = match.group(1), match.group(2)
            if sym.startswith("Py") or sym.startswith("_Py"):
                continue
            if sym.startswith("xkb_"):
                xkb_syms.add(sym)
                if ver:
                    xkb_vers.add(ver)
            else:
                other_syms.add(sym)

        if "libxkbcommon.so.0" in missing and xkb_syms:
            xkb_c = tmp_path / "xkb_full.c"
            xkb_c.write_text(
                "\n".join(f"long {s}(void) {{ return 0; }}" for s in sorted(xkb_syms)) + "\n",
                encoding="utf-8",
            )
            xkb_map = tmp_path / "xkb.map"
            xkb_map.write_text(
                "\n".join(f"{v} {{ global: *; }};" for v in sorted(xkb_vers or {"V_0.5.0"})) + "\n",
                encoding="utf-8",
            )
            subprocess.check_call(
                [
                    "gcc",
                    "-shared",
                    "-fPIC",
                    "-Wl,-soname,libxkbcommon.so.0",
                    f"-Wl,--version-script={xkb_map}",
                    str(xkb_c),
                    "-o",
                    str(tmp_path / "libxkbcommon.so.0"),
                ]
            )

        if other_syms:
            target_lib = "libGL.so.1" if "libGL.so.1" in missing else missing[0]
            gl_c = tmp_path / "gl_full.c"
            gl_c.write_text(
                "\n".join(f"long {s}(void) {{ return 0; }}" for s in sorted(other_syms)) + "\n",
                encoding="utf-8",
            )
            subprocess.check_call(
                [
                    "gcc",
                    "-shared",
                    "-fPIC",
                    f"-Wl,-soname,{target_lib}",
                    str(gl_c),
                    "-o",
                    str(tmp_path / target_lib),
                ]
            )

        for lib in missing:
            shutil.copy2(tmp_path / lib, bpy_lib_dir / lib)

    verified = probe_bpy_subprocess(force_refresh=True)
    if verified.get("available"):
        return {
            "available": True,
            "version": verified.get("version", ""),
            "shims_installed": True,
            "libs": missing,
        }
    return {"available": False, "error": verified.get("error", "Probe failed"), "shims_installed": False}


if __name__ == "__main__":
    result = ensure_headless_bpy()
    print(result)
    sys.exit(0 if result.get("available") else 1)
