"""Mac-only fresh-process scale replay with a sampled RSS stop budget."""
import hashlib
import json
import os
import platform
import re
import resource
from statistics import median
import subprocess
import sys
import tempfile
import time

from benchmarks.ir02_smoke import QUERIES, ROOT, corpus, digest_answer, load


RSS_BYTES = 512 * 1024**2
SECONDS = 30
REFERENCE = ROOT / "benchmarks/results/m5-scale-91a1f83.json"


def emit(**event):
    print(json.dumps(event), flush=True)


def worker(size, version):
    emit(stage="corpus")
    data = corpus(size, version)
    emit(stage="load", corpus_bytes=len(data), corpus_sha256=hashlib.sha256(data).hexdigest())
    start = time.perf_counter_ns()
    kb = load(data)
    load_ns = time.perf_counter_ns() - start
    emit(stage="queries", load_ns=load_ns)
    timings = {key: [] for key in QUERIES}
    answers = {}
    reference = json.loads(REFERENCE.read_bytes())["runs"][version + "-0"]["canonical_answer_sha256"]
    for i in range(4):
        for key, query in QUERIES.items():
            start = time.perf_counter_ns()
            value = kb.query(*query)
            duration = time.perf_counter_ns() - start
            answers[key] = digest_answer(key, value, version)
            if answers[key] != reference[key]:
                raise ValueError(f"{key} answer differs from the 1k reference")
            if i:
                timings[key].append(duration)
    emit(stage="finished", query_ns=timings, query_median_ns={k: median(v) for k, v in timings.items()},
         answer_sha256=answers, process_peak_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)


def availability():
    status = subprocess.check_output(["/usr/bin/memory_pressure", "-Q"], text=True)
    return int(re.search(r"free percentage:\s*(\d+)%", status).group(1))


def sample(size, version, seed, physical_bytes):
    free_percent = availability()
    result = {"seed": seed, "preflight_free_percent": free_percent}
    if physical_bytes < 8 * 1024**3 or free_percent < 25:
        return dict(result, outcome="preflight_limited")
    with tempfile.TemporaryFile() as log:
        start = time.monotonic()
        proc = subprocess.Popen(
            [sys.executable, "-m", "benchmarks.bounded_scale", "--worker", str(size), version],
            cwd=ROOT, env=dict(os.environ, PYTHONHASHSEED=str(seed)), stdout=log)
        peak = 0
        stop = None
        try:
            while proc.poll() is None:
                reading = subprocess.run(["/bin/ps", "-o", "rss=", "-p", str(proc.pid)],
                                         capture_output=True, text=True)
                if proc.poll() is not None:
                    break
                if reading.returncode or not reading.stdout.strip().isdigit():
                    raise RuntimeError("child RSS monitoring unavailable")
                peak = max(peak, int(reading.stdout) * 1024)
                if peak >= RSS_BYTES or time.monotonic() - start >= SECONDS:
                    stop = "rss" if peak >= RSS_BYTES else "wall_seconds"
                    break
                time.sleep(0.05)
        finally:
            if proc.poll() is None:
                proc.kill()
            proc.wait()
        log.seek(0)
        events = [json.loads(line) for line in log]
    if not stop and proc.returncode:
        raise RuntimeError(f"child failed with exit {proc.returncode}")
    if not stop and (not events or events[-1]["stage"] != "finished"):
        raise RuntimeError("child did not return a complete measurement")
    if not stop and events[-1]["process_peak_bytes"] >= RSS_BYTES:
        stop = "rss"
    return dict(result, outcome="limited" if stop else "success", stop_resource=stop,
                sampled_peak_bytes=peak, elapsed_s=time.monotonic()-start, events=events)


def measure():
    if sys.platform != "darwin":
        raise SystemExit("this protocol requires macOS RSS units and utilities")
    physical_bytes = int(subprocess.check_output(["/usr/sbin/sysctl", "-n", "hw.memsize"]))
    report = {"head": subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip(),
              "system":platform.platform(), "python": platform.python_version(),
              "cpu": subprocess.check_output(["/usr/sbin/sysctl","-n","machdep.cpu.brand_string"],text=True).strip(),
              "physical_bytes":physical_bytes,"rss_stop_bytes":RSS_BYTES,"wall_stop_seconds":SECONDS,"cells":[]}
    for size in (100000, 1000000):
        for version in ("0.2", "0.3"):
            samples = []
            for seed in (0,1,2):
                result = sample(size, version, seed, physical_bytes)
                samples.append(result)
                if result["outcome"] != "success":
                    break
            if len({event["corpus_sha256"] for run in samples for event in run.get("events", [])
                    if "corpus_sha256" in event}) > 1:
                raise ValueError("corpus differs across processes")
            report["cells"].append({"assertions":size,"ir":version,"samples":samples})
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--worker":
        worker(int(sys.argv[2]), sys.argv[3])
    elif len(sys.argv) == 1:
        measure()
    else:
        raise SystemExit("Usage: python -m benchmarks.bounded_scale")
