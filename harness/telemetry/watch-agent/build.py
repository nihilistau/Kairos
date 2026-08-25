"""Build, install and arm the watch agent — without gradle.

WHY NO GRADLE. There is none on this machine, and pulling the AGP toolchain in for one
activity, one service and one receiver would be several hundred megabytes of dependency
resolution to compile four files. The platform SDK is enough as long as the app touches no
androidx, which is exactly why the agent uses SensorManager instead of Health Services.

    aapt2 compile+link  ->  javac  ->  d8  ->  zipalign  ->  apksigner

    python build.py                    # build only
    python build.py --install          # ...and install to the connected watch
    python build.py --install --arm    # ...and grant the sensor permissions and start it

Env: ANDROID_SERIAL (adb's own), TELEMETRY_ADB (path to adb), TELEMETRY_ENDPOINT (where the
agent posts). Deliberately NOT SP_* — those are harness runtime knobs and belong in
serve.py's table; a build tool's variables are not gateway configuration and G-SEM-CONSERVE
is right to say so.

`--arm` is a separate word on purpose: installing an app that reads his heart is one
decision, and turning it on is another.
"""
from __future__ import annotations

import argparse
import glob
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "build")
PKG = "com.telemetry.agent"

SDK = os.environ.get("ANDROID_SDK_ROOT") or os.environ.get("ANDROID_HOME") or \
    os.path.join(os.environ.get("LOCALAPPDATA", ""), "Android", "Sdk")
JAVA_HOME = os.environ.get("JAVA_HOME") or r"C:\Program Files\Android\Android Studio\jre"
ADB = os.environ.get("TELEMETRY_ADB") or "adb"


def _newest(pattern: str) -> str:
    hits = sorted(glob.glob(pattern))
    if not hits:
        raise SystemExit("not found: %s" % pattern)
    return hits[-1]


def _run(cmd: list, **kw) -> str:
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode != 0:
        raise SystemExit("FAILED: %s\n%s\n%s" % (" ".join(str(c) for c in cmd[:3]),
                                                 r.stdout[-3000:], r.stderr[-3000:]))
    return (r.stdout or "") + (r.stderr or "")


def build() -> str:
    bt = _newest(os.path.join(SDK, "build-tools", "*"))
    plat = _newest(os.path.join(SDK, "platforms", "android-*"))
    android_jar = os.path.join(plat, "android.jar")
    aapt2 = os.path.join(bt, "aapt2.exe" if os.name == "nt" else "aapt2")
    zipalign = os.path.join(bt, "zipalign.exe" if os.name == "nt" else "zipalign")
    javac = os.path.join(JAVA_HOME, "bin", "javac.exe" if os.name == "nt" else "javac")
    java = os.path.join(JAVA_HOME, "bin", "java.exe" if os.name == "nt" else "java")
    # THE .bat WRAPPERS ARE JAVA-8 ERA. d8.bat and apksigner.bat both pass
    # `-Djava.ext.dirs`, which Java 9 REMOVED — so with any modern JDK they die with
    # "Could not create the Java Virtual Machine" before doing anything. The jars
    # themselves are fine; only the launcher scripts are stale. Invoke the jars.
    d8 = [java, "-cp", os.path.join(bt, "lib", "d8.jar"), "com.android.tools.r8.D8"]
    apksigner = [java, "-jar", os.path.join(bt, "lib", "apksigner.jar")]
    keytool = os.path.join(JAVA_HOME, "bin", "keytool.exe" if os.name == "nt" else "keytool")
    for p, what in ((android_jar, "android.jar"), (aapt2, "aapt2"), (javac, "javac")):
        if not os.path.exists(p):
            raise SystemExit("missing %s at %s" % (what, p))
    print("sdk       : %s" % plat)
    print("build-tools: %s" % os.path.basename(bt))

    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    os.makedirs(os.path.join(OUT, "classes"), exist_ok=True)

    # 1. resources -> a base APK with the manifest compiled in.
    base = os.path.join(OUT, "base.apk")
    _run([aapt2, "link", "-I", android_jar,
          "--manifest", os.path.join(HERE, "AndroidManifest.xml"),
          "--java", os.path.join(OUT, "gen"), "--min-sdk-version", "30",
          "--target-sdk-version", "33", "-o", base])
    print("aapt2     : ok")

    # 2. java -> classes
    srcs = glob.glob(os.path.join(HERE, "java", "**", "*.java"), recursive=True)
    srcs += glob.glob(os.path.join(OUT, "gen", "**", "*.java"), recursive=True)
    _run([javac, "-source", "8", "-target", "8", "-nowarn",
          "-classpath", android_jar, "-d", os.path.join(OUT, "classes")] + srcs)
    print("javac     : %d file(s)" % len(srcs))

    # 3. classes -> dex
    classes = glob.glob(os.path.join(OUT, "classes", "**", "*.class"), recursive=True)
    _run(d8 + ["--min-api", "30", "--lib", android_jar,
               "--output", OUT] + classes)
    print("d8        : ok")

    # 4. dex into the apk, align, sign
    unsigned = os.path.join(OUT, "unsigned.apk")
    shutil.copy(base, unsigned)
    _run(["jar" if not os.name == "nt" else os.path.join(JAVA_HOME, "bin", "jar.exe"),
          "uf", unsigned, "-C", OUT, "classes.dex"])
    aligned = os.path.join(OUT, "aligned.apk")
    _run([zipalign, "-f", "4", unsigned, aligned])

    ks = os.path.join(HERE, "debug.keystore")
    if not os.path.exists(ks):
        _run([keytool, "-genkeypair", "-keystore", ks, "-storepass", "android",
              "-keypass", "android", "-alias", "agent", "-keyalg", "RSA", "-keysize", "2048",
              "-validity", "10000", "-dname", "CN=telemetry-agent"])
        print("keystore  : generated (debug only, never a release key)")
    apk = os.path.join(OUT, "telemetry-agent.apk")
    _run(apksigner + ["sign", "--ks", ks, "--ks-pass", "pass:android",
                      "--key-pass", "pass:android", "--out", apk, aligned])
    print("apk       : %s (%d KB)" % (apk, os.path.getsize(apk) // 1024))
    return apk


def install(apk: str, serial: str, arm: bool) -> None:
    dev = ["-s", serial] if serial else []
    print(_run([ADB] + dev + ["install", "-r", "-g", apk]).strip()[-300:])
    if not arm:
        print("installed. Not armed — run with --arm to grant sensors and start it.")
        return
    # -g above grants what it can; the health permissions are named explicitly because
    # they are the ones that decide whether this reads his heart at all, and a silent
    # failure here looks exactly like a watch that is not being worn.
    for perm in ("android.permission.BODY_SENSORS",
                 "android.permission.BODY_SENSORS_BACKGROUND",
                 "android.permission.ACTIVITY_RECOGNITION",
                 "android.permission.health.READ_HEART_RATE",
                 "android.permission.POST_NOTIFICATIONS"):
        out = _run([ADB] + dev + ["shell", "pm", "grant", PKG, perm]).strip()
        print("  grant %-52s %s" % (perm, out or "ok"))
    url = os.environ.get("TELEMETRY_ENDPOINT", "")
    cmd = [ADB] + dev + ["shell", "am", "start-foreground-service",
                         "-n", "%s/.AgentService" % PKG]
    if url:
        cmd += ["--es", "url", url]
    print(_run(cmd).strip())
    print("armed.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--install", action="store_true")
    ap.add_argument("--arm", action="store_true")
    ap.add_argument("--serial", default=os.environ.get("ANDROID_SERIAL", ""))
    a = ap.parse_args()
    apk = build()
    if a.install:
        install(apk, a.serial, a.arm)
