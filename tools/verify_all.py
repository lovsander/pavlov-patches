#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PAPPA: one command to check EVERY port, without PowerShell.

    python3 tools/verify_all.py                 build + conformance vectors + own tests
    python3 tools/verify_all.py --full          + pipeline of every port + numeric compare
    python3 tools/verify_all.py --vectors-only  only build + conformance vectors
    python3 tools/verify_all.py --only r,julia  only the listed ports
    python3 tools/verify_all.py --list          show the table and the exact commands
    python3 tools/verify_all.py --os posix      force the POSIX command set on any machine
    python3 tools/verify_all.py --dry-run       print what would run, execute nothing

Exit code: 0 = every executed gate passed (skips allowed), 1 = something failed,
2 = nothing could be executed on this machine.

Why this file exists: every other entry point in the repository (`verify_all.ps1` and
the per-port `build_*.ps1`) needs Windows PowerShell, and some of them additionally
need `C:\\msys64`, MSVC presets or Excel COM. Windows itself is fine with the .ps1
scripts (they are the primary, fully exercised path); this driver is the portable
one: the same gates, the same summary, the same exit codes, but stdlib-only Python 3
and per-OS commands (`.exe` suffix, `python3` vs `python`, `gcc-release` vs
`msvc-release`, `:` vs `;` in classpaths).

A port whose toolchain is absent is reported as SKIP with the reason and does NOT
fail the run: the repository must stay readable on a machine that has only a couple
of the toolchains installed. `vba` is SKIP on POSIX by design - VBA 7 lives inside
Excel, and Excel is Windows-only.

NOTE: executable text below is ASCII only on purpose (console code pages on Windows
are not UTF-8); Cyrillic lives in comments, where mangling is harmless.
"""

import argparse
import glob
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
WINDOWS = os.name == "nt"
EXT = ".exe" if WINDOWS else ""
CPSEP = ";" if WINDOWS else ":"
VECTORS = "spec/conformance/vectors"


def rel(path):
    """Repo-relative path with native separators ('.' for the repo root).

    Paths outside the repository (e.g. kotlin-stdlib.jar inside Android Studio) are
    returned as they are: they are still needed on the command line.
    """
    p = Path(path)
    if p == REPO:
        return "."
    try:
        return str(p.relative_to(REPO))
    except ValueError:
        return str(p)



def sh(*parts):
    """Native path inside the repository."""
    return str(REPO.joinpath(*parts))


def which(name):
    return shutil.which(name)


def first_existing(candidates):
    for c in candidates:
        if c and Path(c).exists():
            return str(c)
    return None


def tool(*names):
    """First name found in PATH (also tries name + .exe on Windows)."""
    for n in names:
        found = which(n)
        if found:
            return found
        if WINDOWS and not n.lower().endswith(".exe"):
            found = which(n + ".exe")
            if found:
                return found
    return None


def find_recursive(base, pattern):
    """Recursive search under a directory (Windows toolchains love deep paths)."""
    if not base or not Path(base).is_dir():
        return None
    hits = sorted(glob.glob(str(Path(base) / "**" / pattern), recursive=True))
    return hits[0] if hits else None



def python_candidates():
    """Every python we can think of, best first.

    Why this matters: on Windows `python`/`python3` in PATH may be the Microsoft Store
    alias (WindowsApps\\python3.exe). That stub works from an interactive console but
    returns 9009 with no output when started as a child process, so a naive
    `shutil.which("python")` gives a "working" path that cannot run anything.
    Every candidate is therefore probed by actually starting it.
    """
    out = []
    if sys.executable:
        out.append(sys.executable)
    for name in ("python3", "python", "py"):
        exe = tool(name)
        if exe:
            out.append(exe)
    home = Path.home()
    patterns = [
        str(home / "miniconda3" / "envs" / "*" / ("python.exe" if WINDOWS else "python")),
        str(home / "anaconda3" / "envs" / "*" / ("python.exe" if WINDOWS else "python")),
        str(home / ".conda" / "envs" / "*" / ("python.exe" if WINDOWS else "python")),
        str(Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Python" / "Python3*" /
            "python.exe"),
    ]
    for pattern in patterns:
        # the repo's reference environment is the conda env "geom-toolkit"
        out += sorted(glob.glob(pattern),
                      key=lambda p: (0 if "geom-toolkit" in p.lower() else 1, p))

    seen, uniq = set(), []
    for c in out:
        if c and c not in seen:
            seen.add(c)
            uniq.append(c)
    return uniq


def probe_python(exe, need_numpy):
    code = "import numpy" if need_numpy else "print(1)"
    try:
        done = subprocess.run([exe, "-c", code], capture_output=True, timeout=120)
    except (OSError, subprocess.SubprocessError):
        return False
    return done.returncode == 0


def resolve_python(need_numpy=False):
    """First interpreter that actually starts (and has numpy, if asked)."""
    for exe in python_candidates():
        if probe_python(exe, need_numpy):
            return exe
    return None



def step(folder, argv):
    """One external command: working directory (repo-relative) + argv."""
    return {"dir": folder, "argv": [str(a) for a in argv]}


def port(name, title, tools, sample="", note="", build=None, vectors=None, tests=None,
         pipeline=None):
    return {
        "name": name,
        "title": title,
        "tools": list(tools),
        "sample": sample,
        "note": note,
        "build": list(build or []),
        "vectors": vectors,
        "tests": tests,
        "pipeline": pipeline,
    }


def sources_glob(folder, pattern):
    hits = sorted(glob.glob(sh(folder, "src", "**", pattern), recursive=True))
    return [rel(p) for p in hits]


def kotlin_stdlib(kotlinc):
    """kotlin-stdlib.jar sits next to the compiler: .../kotlinc/bin/kotlinc -> .../kotlinc/lib."""
    if not kotlinc:
        return None
    root = Path(kotlinc).resolve().parents[1]
    return first_existing([str(root / "lib" / "kotlin-stdlib.jar")])


def fortran_port(gfortran, vectors_dir):
    """Fortran has no build system here: modules are compiled in dependency order, then
    programs/tests are linked against all objects (as in fortran/build_fortran.ps1)."""
    modules = ["pappa_kinds", "pappa_signal", "pappa_linalg", "pappa_json", "pappa_model",
               "pappa_cleaner", "pappa_detector", "pappa_csv", "pappa_document",
               "pappa_conformance"]
    programs = ["pappa", "selftest", "conformance"]
    flags = ["-std=f2018", "-O2", "-Wall", "-fcheck=bounds", "-J.", "-I."]
    if WINDOWS:
        flags.append("-static")          # no libgfortran next to the exe otherwise
    build = [step("fortran", [gfortran] + flags + ["-c", f"src/{m}.f90", "-o", f"build/{m}.o"])
             for m in modules]
    objs = ["build/" + m + ".o" for m in modules]
    build += [step("fortran", [gfortran] + flags + ["-o", f"bin/{p}{EXT}", f"src/{p}.f90"] + objs)
              for p in programs]
    build.append(step("fortran", [gfortran] + flags +
                      ["-o", f"bin/test_json{EXT}", "tests/test_json.f90"] + objs))
    return port(
        "fortran",
        "Fortran 2018 (gfortran, no external libraries)",
        [gfortran],
        sample="synthetic_sphere_fortran",
        note="modules in dependency order, then programs; tests link tests/test_json.f90",
        build=build,
        vectors=step("fortran", [f"bin/conformance{EXT}", "../" + vectors_dir]),
        tests=step("fortran", [f"bin/test_json{EXT}", str(REPO)]),
        pipeline=step(".", [f"fortran/bin/pappa{EXT}", "--input", "python/synthetic_data.csv",
                            "--out-dir", "samples/synthetic_sphere_fortran",
                            "--name", "synthetic_sphere", "--quiet"]),
    )


def build_table(vectors_dir, py_numpy, posix, py_any=None):
    """The port table. Windows and POSIX differ only in command details."""
    rows = []
    py_any = py_any or py_numpy or tool("python3", "python")

    rows.append(port(
        "spec",
        "Spec: JSON Schema of documents and manifests (no dependencies)",
        [py_any],
        note="checks samples/**/sample.json and sections/*.pappa.json against spec/*.schema.json",
        vectors=step(".", [py_any or "python", "spec/check_schema.py"]),
    ))

    rows.append(port(
        "python",
        "Python (reference implementation, needs numpy)",
        [py_numpy],
        sample="synthetic_sphere",
        note="reference: builds the reference sample; other ports are compared against it",
        pipeline=step(".", [py_numpy or "python", "python/studies/build_sample.py",
                            "--name", "synthetic_sphere"]),
    ))

    cmake = tool("cmake") or "cmake"
    ctest = tool("ctest") or "ctest"
    preset = "gcc-release" if posix else "msvc-release"
    cpp_build = []
    if posix:
        cpp_build.append(step("cpp", [cmake, "--preset", preset]))
    cpp_build.append(step("cpp", [cmake, "--build", "--preset", preset]))
    cpp_pipeline = ("cpp/build-cmake/" + preset + "/pappa_pipeline"
                    if posix else
                    "cpp/build-cmake/msvc-release/Release/pappa_pipeline.exe")
    rows.append(port(
        "cpp",
        "C++17 (CMake preset " + preset + " + ctest)",
        [tool("cmake"), tool("ctest")],
        sample="synthetic_sphere_cpp",
        note="POSIX build does not need Visual Studio: cmake --preset gcc-release",
        build=cpp_build,
        vectors=step("cpp", [ctest, "--preset", preset, "-R", "conformance_vectors",
                             "--output-on-failure"]),
        tests=step("cpp", [ctest, "--preset", preset, "--output-on-failure"]),
        pipeline=step(".", [cpp_pipeline, "--input", "python/synthetic_data.csv", "--out-dir",
                            "samples/synthetic_sphere_cpp", "--name", "synthetic_sphere",
                            "--quiet"]),
    ))

    gcc = first_existing([r"C:\msys64\mingw64\bin\gcc.exe"]) if WINDOWS else tool("gcc", "cc")
    gcc = gcc or tool("gcc", "cc")
    c_defs = ["-DPP_MAX_POINTS=8192", "-DPP_MAX_PATCHES=16", "-DPP_MAX_WINDOW=4096"]
    c_common = ["-std=c99", "-O2", "-Wall", "-Wextra"] + c_defs
    c_build = [] if not gcc else [
        step(".", [gcc] + c_common + ["-o", "c/pappa_c" + EXT, "c/emit.c", "c/pappa.c",
                                      "c/document.c", "-lm"]),
        step(".", [gcc] + c_common + ["-shared", "-o",
                                      "c/pappa" + (".dll" if WINDOWS else ".so"), "c/pappa.c"]),
    ]
    rows.append(port(
        "c",
        "C99 (core without dependencies; the Python checkers drive it)",
        [gcc, py_numpy],
        sample="synthetic_sphere_c",
        note="check_c_port.py / check_c_pipeline.py build and drive the port themselves",
        build=c_build,
        vectors=step(".", [py_numpy or "python", "python/studies/check_c_port.py"]),
        tests=step(".", [py_numpy or "python", "python/studies/check_c_pipeline.py"]),
        pipeline=step(".", ["c/pappa_c" + EXT, "--input", "python/synthetic_data.csv",
                            "--out-dir", "samples/synthetic_sphere_c",
                            "--name", "synthetic_sphere"]),
    ))

    rows.append(port(
        "go",
        "Go (go test + conformance runner)",
        [tool("go")],
        sample="synthetic_sphere_go",
        build=[step("go", [tool("go") or "go", "build", "./..."])],
        vectors=step("go", [tool("go") or "go", "run", "./cmd/conformance", "../" + vectors_dir]),
        tests=step("go", [tool("go") or "go", "test", "./..."]),
        pipeline=step("go", [tool("go") or "go", "run", "./cmd/pappa", "-input",
                             "../python/synthetic_data.csv", "-out-dir",
                             "../samples/synthetic_sphere_go", "-name", "synthetic_sphere",
                             "-quiet"]),
    ))

    rows.append(port(
        "js",
        "JavaScript (Node, ESM, node --test)",
        [tool("node")],
        sample="synthetic_sphere_js",
        vectors=step("js", [tool("node") or "node", "cmd/conformance.js", ".."]),
        tests=step("js", [tool("node") or "node", "--test"]),
        pipeline=step("js", [tool("node") or "node", "cmd/pappa.js", "--input",
                             "../python/synthetic_data.csv", "--out-dir",
                             "../samples/synthetic_sphere_js", "--name", "synthetic_sphere",
                             "--quiet"]),
    ))

    javac, java = tool("javac"), tool("java")
    java_src = sources_glob("java", "*.java")
    rows.append(port(
        "java",
        "Java (plain javac; SelfTest = vectors + smoke fit)",
        [javac, java],
        sample="synthetic_sphere_java",
        note="one SelfTest run covers both the vectors and the smoke fit",
        build=[step(".", [javac or "javac", "-d", "java/out"] + java_src)] if java_src else [],
        vectors=step(".", [java or "java", "-cp", "java/out", "pappa.cli.ConformanceMain",
                           vectors_dir]),
        tests=step(".", [java or "java", "-cp", "java/out", "pappa.SelfTest", vectors_dir]),
        pipeline=step(".", [java or "java", "-cp", "java/out", "pappa.cli.PappaMain",
                            "--input", "python/synthetic_data.csv", "--out-dir",
                            "samples/synthetic_sphere_java", "--name", "synthetic_sphere",
                            "--quiet"]),
    ))

    kotlinc, kjava = tool("kotlinc"), tool("java")
    if not kotlinc and WINDOWS:
        # Android Studio ships a full kotlinc; there is no separate installation needed.
        kotlinc = find_recursive(os.environ.get("ProgramFiles", "C:/Program Files"),
                                 "kotlinc/bin/kotlinc.bat")
    kt_src = sources_glob("kotlin", "*.kt")
    stdlib = kotlin_stdlib(kotlinc)
    kt_cp = "kotlin/out" + (CPSEP + rel(stdlib) if stdlib else "")
    rows.append(port(
        "kotlin",
        "Kotlin (kotlinc; SelfTest = vectors + smoke fit)",
        [kotlinc, kjava],
        sample="synthetic_sphere_kotlin",
        note="needs kotlin-stdlib.jar on the classpath when run through java",
        build=[step(".", [kotlinc or "kotlinc", "-d", "kotlin/out"] + kt_src)] if kt_src else [],
        vectors=step(".", [kjava or "java", "-cp", kt_cp, "pappa.cli.ConformanceMain",
                           vectors_dir]),
        tests=step(".", [kjava or "java", "-cp", kt_cp, "pappa.SelfTest", vectors_dir]),
        pipeline=step(".", [kjava or "java", "-cp", kt_cp, "pappa.cli.PappaMain", "--input",
                            "python/synthetic_data.csv", "--out-dir",
                            "samples/synthetic_sphere_kotlin", "--name", "synthetic_sphere",
                            "--quiet"]),
    ))

    cargo = first_existing([str(Path.home() / ".cargo" / "bin" / ("cargo.exe" if WINDOWS else "cargo"))])
    cargo = cargo or tool("cargo")
    rows.append(port(
        "rust",
        "Rust (cargo --offline, zero crates)",
        [cargo],
        sample="synthetic_sphere_rust",
        build=[step("rust", [cargo or "cargo", "build", "--release", "--offline"])],
        vectors=step("rust", ["target/release/conformance" + EXT, "../" + vectors_dir]),
        tests=step("rust", [cargo or "cargo", "test", "--release", "--offline"]),
        pipeline=step(".", ["rust/target/release/pappa" + EXT, "--input",
                            "python/synthetic_data.csv", "--out-dir",
                            "samples/synthetic_sphere_rust", "--name", "synthetic_sphere",
                            "--quiet"]),
    ))

    fpc = tool("fpc")
    if not fpc and WINDOWS:
        fpc = first_existing(sorted(glob.glob(r"C:\FPC\*\bin\*\fpc.exe")))
    p_rows = []
    if fpc:
        for prog in ("conformance", "selftest", "pappa"):
            p_rows.append(step("pascal", [fpc, "-Fusrc", "-FUlib", "-FEbin",
                                          f"-obin/{prog}{EXT}", f"src/{prog}.lpr"]))
    rows.append(port(
        "pascal",
        "Free Pascal (FPC, nothing beyond the RTL)",
        [fpc],
        sample="synthetic_sphere_pascal",
        note="FPC wants glued option values (-Fusrc, not '-Fu src')",
        build=p_rows,
        vectors=step("pascal", [f"bin/conformance{EXT}", "../" + vectors_dir]),
        tests=step("pascal", [f"bin/selftest{EXT}", "../" + vectors_dir]),
        pipeline=step(".", ["pascal/bin/pappa" + EXT, "--input", "python/synthetic_data.csv",
                            "--out-dir", "samples/synthetic_sphere_pascal",
                            "--name", "synthetic_sphere", "--quiet"]),
    ))

    swift = tool("swift")
    sdkroot = None
    if WINDOWS:
        hits = sorted(glob.glob(str(Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" /
                                    "Swift" / "Platforms" / "*" / "Windows.platform" /
                                    "Developer" / "SDKs" / "Windows.sdk")))
        sdkroot = hits[0] if hits else None
    swift_row = port(
        "swift",
        "Swift (SwiftPM)",
        [swift],
        sample="synthetic_sphere_swift",
        note="on Windows SDKROOT must point at Windows.sdk (the driver sets it)",
        build=[step("swift", [swift or "swift", "build", "-c", "release"])],
        vectors=step("swift", [".build/release/ConformanceCLI" + EXT, "../" + vectors_dir]),
        tests=step("swift", [swift or "swift", "test"]),
        pipeline=step(".", ["swift/.build/release/PappaCLI" + EXT, "--input",
                            "python/synthetic_data.csv", "--out-dir",
                            "samples/synthetic_sphere_swift", "--name", "synthetic_sphere",
                            "--quiet"]),
    )
    if sdkroot:
        swift_row["env"] = {"SDKROOT": sdkroot}
    rows.append(swift_row)

    julia = tool("julia")
    if not julia and WINDOWS:
        julia = first_existing(sorted(glob.glob(str(Path.home() / ".julia" / "juliaup" / "*" /
                                                    "bin" / "julia.exe"))) +
                               sorted(glob.glob(r"C:\Julia\*\bin\julia.exe")))
    j_row = port(
        "julia",
        "Julia (package Pappa, stdlib only, works offline)",
        [julia],
        sample="synthetic_sphere_julia",
        build=[step(".", [julia or "julia", "--project=julia", "-e",
                          "using Pappa; println(Pappa.PORT_VERSION)"])],
        vectors=step(".", [julia or "julia", "--project=julia", "julia/bin/conformance.jl",
                           vectors_dir]),
        tests=step(".", [julia or "julia", "--project=julia", "julia/test/runtests.jl"]),
        pipeline=step(".", [julia or "julia", "--project=julia", "julia/bin/pappa.jl",
                            "--input", "python/synthetic_data.csv", "--out-dir",
                            "samples/synthetic_sphere_julia", "--name", "synthetic_sphere"]),
    )
    j_row["env"] = {"JULIA_PKG_OFFLINE": "true"}      # no dependencies: no network needed
    rows.append(j_row)

    rscript = tool("Rscript")
    if not rscript and WINDOWS:
        roots = [Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "R",
                 Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "R", Path("C:/R")]
        hits = []
        for root in roots:
            if root.is_dir():
                hits += sorted(glob.glob(str(root / "*" / "bin" / "Rscript.exe")), reverse=True)
        rscript = first_existing(hits)
    rows.append(port(
        "r",
        "R (base R only: own JSON, CSV, statistics)",
        [rscript],
        sample="synthetic_sphere_r",
        vectors=step(".", [rscript or "Rscript", "--vanilla", "r/bin/conformance.R", vectors_dir]),
        tests=step(".", [rscript or "Rscript", "--vanilla", "r/tests/runtests.R"]),
        pipeline=step(".", [rscript or "Rscript", "--vanilla", "r/bin/pappa.R", "--input",
                            "python/synthetic_data.csv", "--out-dir",
                            "samples/synthetic_sphere_r", "--name", "synthetic_sphere"]),
    ))

    octave = tool("octave-cli", "octave")
    if not octave and WINDOWS:
        hits = []
        for root in (Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "GNU Octave",
                     Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "GNU Octave",
                     Path("C:/Octave")):
            if root.is_dir():
                for sub in sorted(glob.glob(str(root / "*")), reverse=True):
                    hits += [str(Path(sub) / "mingw64" / "bin" / "octave-cli.exe"),
                             str(Path(sub) / "bin" / "octave-cli.exe")]
        octave = first_existing(hits)
    # --no-gui exists only in the Windows build; octave-cli on Linux does not need it.
    oct_flags = ["--quiet", "--no-init-file"] + (["--no-gui"] if WINDOWS else [])
    rows.append(port(
        "octave",
        "GNU Octave (core only: own JSON, CSV, statistics)",
        [octave],
        sample="synthetic_sphere_octave",
        note="bin/*.m scripts; the self-test covers vectors + smoke fit + document round-trip",
        vectors=step(".", [octave or "octave-cli"] + oct_flags +
                     ["octave/bin/conformance.m", vectors_dir]),
        tests=step(".", [octave or "octave-cli"] + oct_flags +
                   ["octave/bin/selftest.m", vectors_dir]),
        pipeline=step(".", [octave or "octave-cli"] + oct_flags +
                     ["octave/bin/pipeline.m", "--input", "python/synthetic_data.csv",
                      "--out-dir", "samples/synthetic_sphere_octave", "--name",
                      "synthetic_sphere"]),
    ))

    dotnet = first_existing([str(Path(os.environ.get("ProgramFiles", "C:/Program Files")) /
                                 "dotnet" / ("dotnet.exe" if WINDOWS else "dotnet"))])
    dotnet = dotnet or tool("dotnet")
    for name, proj, dll in (
            ("csharp", "csharp/Pappa.csproj", "csharp/bin/Release/net10.0/pappa.dll"),
            ("fsharp", "fsharp/Pappa.fsproj", "fsharp/bin/Release/net10.0/pappa.dll")):
        exe = dll[:-4] + EXT
        # The apphost is not always produced (Linux/macOS): dotnet <dll> always works.
        runner = [exe] if WINDOWS else [dotnet or "dotnet", dll]
        rows.append(port(
            name,
            ("C#" if name == "csharp" else "F#") +
            " (.NET 10, zero NuGet packages; SelfTest = vectors + smoke + round-trip)",
            [dotnet],
            sample="synthetic_sphere_" + name,
            note="one exe, three subcommands: conformance | selftest | pipeline",
            build=[step(".", [dotnet or "dotnet", "build", proj, "-c", "Release", "--nologo"])],
            vectors=step(".", runner + ["conformance", vectors_dir]),
            tests=step(".", runner + ["selftest", vectors_dir]),
            pipeline=step(".", runner + ["pipeline", "--input", "python/synthetic_data.csv",
                                         "--out-dir", "samples/synthetic_sphere_" + name,
                                         "--name", "synthetic_sphere", "--quiet"]),
        ))

    gfortran = first_existing([r"C:\msys64\mingw64\bin\gfortran.exe",
                               r"C:\TDM-GCC-64\bin\gfortran.exe"]) if WINDOWS else tool("gfortran")
    gfortran = gfortran or tool("gfortran")
    rows.append(fortran_port(gfortran, vectors_dir))

    if not posix:
        excel = first_existing([str(Path(os.environ.get("ProgramFiles", "C:/Program Files")) /
                                    "Microsoft Office" / "root" / "Office16" / "EXCEL.EXE")])
        powershell = tool("powershell")
        rows.append(port(
            "vba",
            "VBA 7 in Microsoft Excel (modules imported through COM)",
            [excel, powershell],
            sample="synthetic_sphere_vba",
            note="needs Excel 2016+ and a one-time AccessVBOM; every run goes through a job",
            build=[step(".", [powershell or "powershell", "-NoProfile", "-ExecutionPolicy",
                              "Bypass", "-File", "vba/build_vba.ps1"])],
            vectors=step(".", [powershell or "powershell", "-NoProfile", "-ExecutionPolicy",
                               "Bypass", "-File", "vba/build_vba.ps1", "-Vectors"]),
            tests=step(".", [powershell or "powershell", "-NoProfile", "-ExecutionPolicy",
                             "Bypass", "-File", "vba/build_vba.ps1", "-Test"]),
            pipeline=step(".", [powershell or "powershell", "-NoProfile", "-ExecutionPolicy",
                                "Bypass", "-File", "vba/build_vba.ps1", "-Pipeline"]),
        ))

    return rows


def tool_ok(names):
    """True when at least one of the probe entries exists / is in PATH."""
    for n in names:
        if not n:
            continue
        if Path(n).exists() or which(n):
            return True
    return False


def run_step(s, extra_env, dry_run):
    """Run one command; returns (exit code, combined output)."""
    cwd = str(REPO if s["dir"] == "." else REPO / s["dir"])
    argv = s["argv"]
    if dry_run:
        print("        $ " + " ".join(argv))
        return 0, ""
    env = dict(os.environ)
    # Python-based checkers print Cyrillic/Δ; with a pipe as stdout Python picks the
    # locale code page (cp1251/cp866 on Windows) and dies with UnicodeEncodeError.
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    env.update(extra_env or {})
    # Windows quirk: a RELATIVE argv[0] is resolved against the directory of THIS
    # process, not against cwd= of the child. Resolve it ourselves.
    if not os.path.isabs(argv[0]):
        candidate = Path(cwd) / argv[0]
        if candidate.exists():
            argv = [str(candidate)] + list(argv[1:])
    # Another one: CreateProcess cannot start a .bat/.cmd directly (kotlinc.bat from
    # Android Studio is exactly that), so it has to go through cmd.exe.
    if WINDOWS and argv[0].lower().endswith((".bat", ".cmd")):
        argv = ["cmd", "/c"] + argv
    try:
        done = subprocess.run(argv, cwd=cwd, env=env, capture_output=True)
    except OSError as exc:
        return 127, "cannot start: " + str(exc)
    text = (done.stdout or b"") + (done.stderr or b"")
    return done.returncode, text.decode("utf-8", "replace").strip()


def tail(text, lines=3):
    keep = [l for l in (text or "").splitlines() if l.strip()]
    if not keep:
        return "(no output)"
    return " | ".join(keep[-lines:])


def describe(row, key):
    s = row.get(key)
    if not s:
        return "(not defined)"
    return " ".join(s["argv"]) + ("" if s["dir"] == "." else "   [cwd " + s["dir"] + "]")


def main(argv):
    ap = argparse.ArgumentParser(add_help=True,
                                description="PAPPA: build and verify every port (no PowerShell)")
    ap.add_argument("--full", action="store_true",
                    help="also run the pipeline of every port and compare with the reference")
    ap.add_argument("--vectors-only", action="store_true", help="only build + conformance vectors")
    ap.add_argument("--no-build", action="store_true", help="skip the build steps")
    ap.add_argument("--only", default="", help="comma-separated list of ports")
    ap.add_argument("--list", action="store_true", help="show the table and exit")
    ap.add_argument("--os", dest="os_name", choices=["auto", "windows", "posix"], default="auto",
                    help="command set to use (auto = this machine)")
    ap.add_argument("--dry-run", action="store_true", help="print the commands, run nothing")
    args = ap.parse_args(argv[1:])

    posix = {"auto": not WINDOWS, "windows": False, "posix": True}[args.os_name]
    py_numpy = resolve_python(True)          # reference sample + numeric checkers
    py_any = resolve_python(False) or py_numpy
    rows = build_table(VECTORS, py_numpy, posix, py_any)

    if args.only:
        wanted = [w.strip().lower() for w in args.only.split(",") if w.strip()]
        rows = [r for r in rows if r["name"].lower() in wanted]
        if not rows:
            print("no port matches --only '" + args.only + "' (see --list)", file=sys.stderr)
            return 2

    print("PAPPA: %d ports, command set: %s, python with numpy: %s"
          % (len(rows), "posix" if posix else "windows", py_numpy or "not found"))

    if args.list or args.dry_run:
        for r in rows:
            print()
            print("  %-8s %s" % (r["name"], r["title"]))
            for label, key in (("Build", "build"), ("Vectors", "vectors"),
                               ("Tests", "tests"), ("Pipeline", "pipeline")):
                if key == "build":
                    for s in r["build"]:
                        print("          %-9s %s" % (label, " ".join(s["argv"]) +
                                                     ("" if s["dir"] == "." else
                                                      "   [cwd " + s["dir"] + "]")))
                elif r.get(key):
                    print("          %-9s %s" % (label, describe(r, key)))
            if r["note"]:
                print("          note      %s" % r["note"])
            if r.get("env"):
                print("          env       %s" % ", ".join("%s=%s" % kv for kv in
                                                            r["env"].items()))
        if args.dry_run:
            print()
            print("dry run: nothing was executed")
        return 0
    return run_rows(rows, args, py_numpy)


def run_rows(rows, args, py_numpy):
    vectors_dir = str(REPO / VECTORS)
    ref_dir = REPO / "samples" / "synthetic_sphere"

    # --- the reference sample is what --full compares every port against ---
    if args.full and py_numpy and not (ref_dir / "sample.json").exists():
        print("[reference] building samples/synthetic_sphere with Python")
        code, text = run_step(step(".", [py_numpy, "python/studies/build_sample.py",
                                         "--name", "synthetic_sphere"]), None, False)
        if code != 0:
            print("  FAILED (exit %d): %s" % (code, tail(text)))

    table = []
    for r in rows:
        status = "OK"
        cols = {"vectors": "-", "tests": "-", "pipeline": "-", "verify": "-"}
        note = r["note"]

        if not tool_ok(r["tools"]):
            print("[skip]      %-8s toolchain not found on this machine" % r["name"])
            table.append((r["name"], "SKIP", "SKIP", "SKIP", "SKIP", "SKIP",
                          "toolchain not found"))
            continue

        failed = False
        if r["build"] and not args.no_build:
            for s in r["build"]:
                code, text = run_step(s, r.get("env"), False)
                if code != 0:
                    print("[fail]      %-8s build exit %d: %s" % (r["name"], code, tail(text)))
                    failed = True
                    break
        if failed:
            table.append((r["name"], "FAIL", "-", "-", "-", "FAIL", "build exit code"))
            continue

        gates = [("Vectors", "vectors", r.get("vectors"))]
        if not args.vectors_only:
            gates.append(("Tests", "tests", r.get("tests")))
            if args.full:
                gates.append(("Pipeline", "pipeline", r.get("pipeline")))
        for label, key, s in gates:
            if not s:
                continue
            code, text = run_step(s, r.get("env"), False)
            if code == 0:
                cols[key] = "OK"
                print("[ok]        %-8s %s" % (r["name"], label))
            else:
                cols[key] = "FAIL"
                status = "FAIL"
                print("[fail]      %-8s %s exit %d: %s" % (r["name"], label, code, tail(text)))

        # --- --full: numeric comparison of the port's sample against the reference ---
        if args.full and not args.vectors_only and r["sample"] and r["name"] != "python":
            sample = REPO / "samples" / r["sample"]
            if (py_numpy and (sample / "sample.json").exists()
                    and (ref_dir / "sample.json").exists()):
                code, text = run_step(step(".", [py_numpy, "python/studies/verify_port.py",
                                                 "--py-dir", str(ref_dir),
                                                 "--cpp-dir", str(sample)]), None, False)
                if code == 0:
                    cols["verify"] = "OK"
                    print("[ok]        %-8s verify_port: %s" % (r["name"], tail(text, 1)))
                else:
                    cols["verify"] = "FAIL"
                    status = "FAIL"
                    print("[fail]      %-8s verify_port exit %d: %s"
                          % (r["name"], code, tail(text)))
            else:
                cols["verify"] = "SKIP"
                if not note:
                    note = "no sample folder for the numeric compare"
                print("[skip]      %-8s numeric compare: no sample folder" % r["name"])

        if r["name"] == "python":
            cols["vectors"] = "n/a"
            cols["tests"] = "n/a"
        table.append((r["name"], cols["vectors"], cols["tests"], cols["pipeline"],
                      cols["verify"], status, note))

    print()
    print("%-10s %-8s %-6s %-9s %-7s %s"
          % ("Port", "Vectors", "Tests", "Pipeline", "Verify", "Status"))
    for row in table:
        print("%-10s %-8s %-6s %-9s %-7s %s" % row[:6])

    done = sum(1 for row in table if row[5] == "OK")
    skipped = sum(1 for row in table if row[5] == "SKIP")
    bad = sum(1 for row in table if row[5] == "FAIL")
    print("summary: %d OK, %d SKIP, %d FAIL (of %d ports)" % (done, skipped, bad, len(table)))
    if bad:
        return 1
    if done == 0:
        return 2
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    sys.exit(main(sys.argv))







