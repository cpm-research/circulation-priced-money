#!/usr/bin/env bash
# The second run on a Linux server, from this folder alone (docs/RUNNING_ON_A_SERVER.md).
#   ./run.sh all        everything, unattended. It starts in the background at once and needs nobody after that:
#                       setup, a self-test, the development map, the side sets, the count of confirmation seeds,
#                       the main run and the packing. What to send back is then in send_back/, and only there.
#   ./run.sh status     what is running and how far it is
#   ./run.sh stop       stop what this script started; ./run.sh all continues from the last finished seed
# The steps of "all", one at a time:
#   ./run.sh setup      install Python 3.12 and the pinned packages inside this folder (once; needs the internet)
#   ./run.sh check      a short self-test; writes send_back/check_report.txt
#   ./run.sh plan       print what each job below would run; runs nothing
#   ./run.sh devmap     the development map on three seeds, in the background
#   ./run.sh sides      the side sets, in the background
#   ./run.sh main       the count of confirmation seeds from the development map, then the main run, in the background
#   ./run.sh pack       bundle the finished results into send_back/
# WORKERS=64 ./run.sh all   sets the number of parallel workers (default: the cores less two, or what memory allows)
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STATE="$HERE/.server"            # the installer, Python, the packages and the logs: all in here
PY="$STATE/venv/bin/python"
LOGS="$STATE/logs"
SEND="$HERE/send_back"           # everything to send back, and nothing else
STAGE="$STATE/packing"           # where the results are laid out before they are bundled
REPORT="$SEND/check_report.txt"
PASSED="RESULT: everything works here"                    # the self-test's last line when it passes
UNDER_WAY="the self-test passed; the run is under way"    # the job's log line that ends the first minutes
DISK_GB=100                      # the free disk the whole run needs in this folder
UV_VERSION=0.13.10               # the installer; a fixed version, so setup fetches the same file every time
mkdir -p "$LOGS"
COMMIT="$(git -C "$HERE" rev-parse --short HEAD 2>/dev/null || echo unknown)"
export CPM_COMMIT="$COMMIT"

# Everything stays inside this folder: nothing is written to the home directory or to the system.
export UV_PYTHON_INSTALL_DIR="$STATE/python" UV_CACHE_DIR="$STATE/uvcache" UV_NO_MODIFY_PATH=1
export XDG_CONFIG_HOME="$STATE/config" MPLCONFIGDIR="$STATE/matplotlib" MPLBACKEND=Agg
export UV_PYTHON_PREFERENCE=only-managed      # the Python that uv fetches into this folder, never the system's
export TMPDIR="$STATE/tmp"                    # a run's working files, some GB a seed, not the system's /tmp
mkdir -p "$TMPDIR"
# One thread a worker: the work is spread over processes, not threads.
export PYTHONPATH="src:.:scripts" PYTHONDONTWRITEBYTECODE=1
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1

# The cores this process may use. nproc answers 1 when OMP_NUM_THREADS is 1, as it is above, so it is asked without.
cores="$(env -u OMP_NUM_THREADS -u OMP_THREAD_LIMIT nproc)"
mem_gb="$(awk '/MemAvailable/ {printf "%d", $2 / 1048576}' /proc/meminfo)"
mem_gb="${mem_gb:-0}"                      # 0: not read, and then the cores alone set the default
by_cores=$(( cores > 4 ? cores - 2 : cores ))
# A worker is given 3 GB, and 16 GB are left beside the workers. One worker was measured above 1.6 GB and still
# rising on a development seed, where each person's failed payments are kept by month, and the process that
# gathers such a seed holds about 12 GB more (PART_GB) until the seed is written.
PART_GB=12
by_memory=$(( (mem_gb - PART_GB - 4) / 3 ))
default_workers=$(( mem_gb > 0 && by_memory < by_cores ? by_memory : by_cores ))
[ "$default_workers" -lt 1 ] && default_workers=1
export WORKERS="${WORKERS:-$default_workers}"
READINGS="quote realised"
# One seed of a map is one task for each outside rate and launch level, 42 on the whole grid, so more workers than
# that on one seed would stand idle: a map runs as many seeds at the same time as keep the workers busy.
TASKS_A_SEED=42
map_together=$(( (WORKERS + TASKS_A_SEED - 1) / TASKS_A_SEED ))
[ "$map_together" -lt 1 ] && map_together=1
map_workers=$(( WORKERS / map_together ))
# The development map holds the most memory, so it runs one seed at a time with workers given 4 GB each: at most
# one worker a task of the seed, and no more than the run's workers.
dev_workers=$(( (mem_gb - PART_GB - 4) / 4 ))
[ "$mem_gb" -gt 0 ] || dev_workers="$WORKERS"
[ "$dev_workers" -gt "$WORKERS" ] && dev_workers="$WORKERS"
[ "$dev_workers" -gt "$TASKS_A_SEED" ] && dev_workers="$TASKS_A_SEED"
[ "$dev_workers" -lt 1 ] && dev_workers=1
# A side set is a few cells: its three seeds run at the same time with three workers each, and as many side sets at
# the same time as the workers allow.
SIDE_WORKERS=3
SIDE_TOGETHER=3
# For a trial of this script on a small machine only, never for a run that is kept: TRIAL_OPTIONS is handed to the
# runner (for example "--n 300 --r_out 0.044 --a0 0.6 --distress 0 0.02") and TRIAL_SIDES names the side sets run.
# A trial never sets the count of confirmation seeds and never runs a confirmation seed: where the run would start
# its main map, a trial runs the same commands on the three side seeds.
export TRIAL_OPTIONS="${TRIAL_OPTIONS:-}" TRIAL_SIDES="${TRIAL_SIDES:-}"

stamp() { date '+%Y-%m-%d %H:%M:%S'; }

free_disk() { df -Ph "$HERE" | awk 'NR==2 {print $4}'; }

trial() { [ -n "$TRIAL_OPTIONS$TRIAL_SIDES" ]; }

# Before every step that touches the confirmation seeds.
no_trial() {
    if trial; then
        echo "This is a trial (TRIAL_OPTIONS or TRIAL_SIDES is set): it sets no count and runs no confirmation seed."
        exit 1
    fi
}

need_setup() {
    [ -x "$PY" ] && [ -f "$STATE/setup.done" ] ||
        { echo "Python is not installed here yet. Run:  ./run.sh setup"; exit 1; }
}

setup() {
    local archive="$STATE/tools/uv.tar.gz"
    mkdir -p "$STATE/tools"
    if [ ! -x "$STATE/tools/uv" ]; then
        echo "Fetching the installer (uv $UV_VERSION) into $STATE/tools ..."
        curl -LsSf --retry 3 -o "$archive" \
            "https://github.com/astral-sh/uv/releases/download/$UV_VERSION/uv-$(uname -m)-unknown-linux-gnu.tar.gz"
        tar xzf "$archive" -C "$STATE/tools" --strip-components=1
        rm -f "$archive"
    fi
    "$STATE/tools/uv" --version
    [ -x "$PY" ] || "$STATE/tools/uv" venv --python 3.12 "$STATE/venv"
    "$STATE/tools/uv" pip install --python "$PY" -r "$HERE/requirements-lock.txt"
    "$PY" -c "import numpy, scipy, networkx, matplotlib
print('Python and packages are ready: NumPy', numpy.__version__, 'and SciPy', scipy.__version__)"
    touch "$STATE/setup.done"
    echo "Setup done."
}

check() {
    need_setup
    mkdir -p "$SEND"
    (cd "$HERE" && "$PY" -X utf8 -u scripts/machine_check.py "$WORKERS" | tee "$REPORT")
    echo
    echo "The report is in $REPORT ."
}

# One map for one way savers read the pool, each finished seed kept. The figures are drawn afterwards from the packed
# stores, not here: the stores of a map at 4,000 people are large.
map_command() {
    local seeds="$1" stem="$2" reading="$3" workers="$map_workers" together="$map_together"
    if [ "$seeds" = development ]; then workers="$dev_workers" together=1; fi
    echo "'$PY' -X utf8 scripts/run_confirmation.py --seeds $seeds --second-run base --entry-reads $reading" \
        "--workers $workers --most-workers $workers --together $together --no-figures" \
        "--output runs/${stem}_$reading $TRIAL_OPTIONS"
}

# Both ways savers read the pool, one after the other, for one seed set, into runs/<stem>_<reading> (the stem is
# the seed set's name unless a second argument gives another).
run_maps() {
    local reading stem="${2:-$1}"
    if [ "$1" = confirmation ]; then no_trial; fi
    for reading in $READINGS; do
        echo "$(stamp)  the $stem map, savers reading the $reading"
        eval "$(map_command "$1" "$stem" "$reading")"
        tidy "runs/${stem}_$reading"
        if [ "$1" = development ]; then spread "runs/${stem}_$reading"; fi
    done
}

# Once a map is joined its parts' two large stores are copies of what the joined stores hold: they are removed.
tidy() {
    if [ -f "$HERE/$1/joined.json" ]; then
        rm -f "$HERE/$1"/parts/seed_*/measures.json "$HERE/$1"/parts/seed_*/failure_counts.json
    fi
}

# A run on development seeds stores every person's failed payments by month, by far its largest record (about 50 MB
# a cell and seed at 4,000 people). On the development map one reading needs it, the spread of distress, which is
# read here into spread.json; the record is then kept compressed. Nothing reads it on a side set, where it is removed.
spread() {
    local record="$HERE/$1/failure_counts.json"
    [ -f "$record" ] || return 0
    if (cd "$HERE" && "$PY" -X utf8 scripts/spread_of_distress.py "$1" > /dev/null 2>&1); then
        gzip -1 -f "$record"
    else
        echo "$(stamp)  the spread of distress was not read for $1; its record is kept as it is"
    fi
}

# The side sets and the saver readings each runs on, one "name reading" a line, read from the code.
side_list() {
    (cd "$HERE" && "$PY" -X utf8 -c "
import os
from cpm_abm.experiment import second_run
only = os.environ.get('TRIAL_SIDES', '').split()
for name in second_run.NAMES:
    if name != 'base' and (not only or name in only):
        for reading in second_run.reads(name):
            print(name, reading)")
}

# One side set on one saver reading, in the foreground, on the development seeds: the development map holds the base
# model on the same cells and seeds, so each side set is read against it pair by pair.
side_one() {
    need_setup
    cd "$HERE"
    # shellcheck disable=SC2086
    "$PY" -X utf8 scripts/run_confirmation.py --seeds development --second-run "$1" --entry-reads "$2" \
        --workers "$SIDE_WORKERS" --most-workers "$SIDE_WORKERS" --together "$SIDE_TOGETHER" --no-figures \
        --output "runs/side_$1_$2" ${3:-} $TRIAL_OPTIONS_SIDES > "$LOGS/side_$1_$2.log" 2>&1 ||
        { echo "$(stamp)  side set $1 ($2) FAILED: see $LOGS/side_$1_$2.log"; return 1; }
    tidy "runs/side_$1_$2"
    if [ -f "runs/side_$1_$2/joined.json" ]; then rm -f "runs/side_$1_$2/failure_counts.json"; fi
    echo "$(stamp)  side set $1 ($2) done"
}
# A side set runs on its own cells, so of a trial's options only the population is handed on.
TRIAL_OPTIONS_SIDES="$(echo "$TRIAL_OPTIONS" | grep -oE -- '--n [0-9]+' || true)"
export TRIAL_OPTIONS_SIDES

# Every side set, as many at the same time as the workers allow; a side set that fails is named and the rest go on.
run_sides() {
    local together=$(( WORKERS / (SIDE_WORKERS * SIDE_TOGETHER) ))
    [ "$together" -lt 1 ] && together=1
    side_list > "$LOGS/sides.list" || { echo "$(stamp)  the list of side sets could not be read"; return 1; }
    echo "$(stamp)  $(grep -c . "$LOGS/sides.list") side sets, $together at the same time"
    xargs -r -P "$together" -L 1 "$HERE/run.sh" side-one < "$LOGS/sides.list"
}

# The count of confirmation seeds, by the registered rule from the development map, written into the code before
# any confirmation seed is started (scripts/set_second_count.py).
set_count() {
    no_trial
    (cd "$HERE" && "$PY" -X utf8 scripts/set_second_count.py runs/development_quote --beside runs/development_realised)
}

# Whether the job <name> is running: some process of its group is alive.
running() {
    [ -f "$LOGS/$1.pid" ] && kill -0 -- "-$(cat "$LOGS/$1.pid")" 2>/dev/null
}

# Start a long job detached from the terminal, with its output in the logs. The job leads a session of its own and
# writes that session's number to <name>.pid, so the job and every worker under it can be stopped as one group.
start() {
    local name="$1" other
    shift
    for other in all devmap sides main; do
        if running "$other"; then
            echo "$other is already running (process group $(cat "$LOGS/$other.pid")). See:  ./run.sh status"
            exit 1
        fi
    done
    rm -f "$LOGS/$name.pid"
    (cd "$HERE" && JOB="$*" PIDFILE="$LOGS/$name.pid" setsid nohup bash -c 'echo $$ > "$PIDFILE"; eval "$JOB"' \
        < /dev/null >> "$LOGS/$name.log" 2>&1 &)
    sleep 2
    echo "Started $name in the background with $WORKERS workers, $(stamp). It keeps running after you log out."
}

# After a single step is started by hand.
hints() {
    echo "Follow it with:  ./run.sh status    or    tail -f $LOGS/$1.log"
    echo "If it stops for any reason, give the same command again: it continues from the last finished seed."
}

# What "all" asks before it starts anything. Each is answered in seconds, so a machine that cannot do the run is
# told so at once and not hours later. The disk is asked for only before the first start: a run that continues
# has used part of it. DISK_OK=1 starts the run on less free disk than DISK_GB.
preflight() {
    local tool missing="" site free_gb
    for tool in git curl tar gzip awk sed grep df xargs setsid nohup sha256sum; do
        command -v "$tool" > /dev/null 2>&1 || missing="$missing $tool"
    done
    [ -z "$missing" ] || { echo "This machine lacks:$missing . Nothing was started."; exit 1; }
    case "$(uname -s) $(uname -m)" in
        "Linux x86_64" | "Linux aarch64") ;;
        *)  echo "The run needs Linux on x86-64 or ARM64; this is $(uname -s) $(uname -m). Nothing was started."
            exit 1 ;;
    esac
    if [ ! -f "$STATE/setup.done" ]; then
        for site in https://github.com https://pypi.org/simple/numpy/; do
            curl -sSfL --max-time 30 -o /dev/null "$site" ||
                { echo "This machine cannot reach $site, which setup needs. Nothing was started."; exit 1; }
        done
    fi
    free_gb="$(df -Pk "$HERE" | awk 'NR==2 {printf "%d", $4 / 1048576}')"
    if [ ! -d "$HERE/runs" ] && [ "${free_gb:-0}" -lt "$DISK_GB" ] && [ -z "${DISK_OK:-}" ]; then
        echo "The run needs about $DISK_GB GB of free disk in this folder; $free_gb GB is free. Nothing was started."
        echo "Move this folder to a larger disk and give the same command there."
        exit 1
    fi
}

# Show the job's log from after line <from> until the run proper is under way or the job has ended. The job is not
# tied to this terminal: stopping the display stops nothing.
follow() {
    local name="$1" from="$2" log="$LOGS/$1.log" shown="$2" total alive
    while :; do
        alive=1
        running "$name" || alive=0
        total=0
        if [ -f "$log" ]; then total="$(wc -l < "$log")"; fi
        if [ "$total" -gt "$shown" ]; then
            sed -n "$(( shown + 1 )),${total}p" "$log" | sed 's/^/    /'
            shown="$total"
        fi
        if [ "$(tail -n +"$(( from + 1 ))" "$log" 2>/dev/null | grep -c "$UNDER_WAY" || true)" -gt 0 ]; then
            return 0
        fi
        [ "$alive" = 1 ] || return 1
        sleep 2
    done
}

# The steps of the run after the self-test, in the foreground of the job "all" starts. The side sets come before the
# count is written into the code, so the development map and the side sets read against it ran on the same code.
# A step whose failure does not stop the run is started as a process of its own: inside it the first failing
# command stops the step, which bash does not do for a function called before "||".
chain() {
    need_setup
    cd "$HERE"
    run_maps development
    if [ -f "$HERE/runs/second_confirmation_count.json" ]; then
        echo "$(stamp)  the count is set: the side sets are not run again on the code it changed"
    else
        echo "$(stamp)  the side sets"
        "$HERE/run.sh" side-sets || echo "$(stamp)  some side sets failed; the run goes on without them"
    fi
    "$HERE/run.sh" pack || echo "$(stamp)  the results so far could not be packed; the run goes on"
    if trial; then
        echo "$(stamp)  a trial: the side seeds stand in for the main run; no count is set, no confirmation seed run"
        run_maps side trial_main
    else
        echo "$(stamp)  the count of confirmation seeds"
        set_count
        run_maps confirmation
    fi
    pack
    echo "$(stamp)  ALL DONE. Everything to send back is in $SEND"
}

# What "all" starts in the background: setup and the self-test, each once, then the run.
everything() {
    cd "$HERE"
    rm -rf "$TMPDIR"/cpm_*              # working files a stopped run left behind
    if [ ! -f "$STATE/setup.done" ]; then
        "$HERE/run.sh" setup ||
            { echo "$(stamp)  setup failed; once more in two minutes"; sleep 120; "$HERE/run.sh" setup; }
    fi
    if ! grep -q "^$PASSED" "$REPORT" 2>/dev/null; then
        "$HERE/run.sh" check || true
        grep -q "^$PASSED" "$REPORT" 2>/dev/null ||
            { echo "$(stamp)  THE SELF-TEST FAILED: the lines above say where. Nothing was run."; exit 1; }
    fi
    echo "$(stamp)  $UNDER_WAY"
    chain
}

all_steps() {
    local from
    if running all; then
        echo "The run is already going here."
        status
        return 0
    fi
    preflight
    echo "This machine: $cores cores, $mem_gb GB of memory free, $(free_disk) of disk free here."
    from=0
    if [ -f "$LOGS/all.log" ]; then from="$(wc -l < "$LOGS/all.log")"; fi
    start all "'$HERE/run.sh' everything"
    echo "It needs nobody from here on. Its first minutes follow (setup and a self-test);"
    echo "closing this terminal or Ctrl-C does not stop it."
    echo
    if follow all "$from"; then
        echo
        echo "The run is under way."
        echo "  How far it is:   $HERE/run.sh status"
        echo "  The results:     $SEND/   (that folder is all there is to send back, once status says FINISHED)"
        echo "  To stop it:      $HERE/run.sh stop"
    else
        echo
        echo "It stopped before the run began; the lines above say why. Once that is put right, give the same"
        echo "command again."
        exit 1
    fi
}

devmap() {
    need_setup
    start devmap "'$HERE/run.sh' maps development && echo ALL DONE"
    hints devmap
}

main_run() {
    need_setup
    start main "'$HERE/run.sh' count && '$HERE/run.sh' maps confirmation && echo ALL DONE"
    hints main
}

sides() {
    need_setup
    start sides "'$HERE/run.sh' side-sets && echo ALL DONE"
    hints sides
}

plan() {
    need_setup
    local reading name
    echo "Workers: $WORKERS (of $cores cores, $mem_gb GB of memory free):" \
        "the main map runs $map_together seeds at the same time with $map_workers workers each," \
        "the development map one seed at a time with $dev_workers workers."
    for name in development confirmation; do
        for reading in $READINGS; do
            echo "== $name map, savers reading the $reading"
            (cd "$HERE" && bash -c "$(map_command "$name" "$name" "$reading") --dry-run" 2>&1) | awk '
                /error: / { sub(/^.*error: /, "   not yet: "); print substr($0, 1, 200) }
                /^  part / { parts++; runs += $(NF - 2) }
                END { if (parts) print "   " parts " seeds, " runs " population runs in all" }' || true
        done
    done
    echo "== side sets (on the development seeds): $(side_list | wc -l) in all"
    side_list | awk '{print $1 " (" $2 ")"}' | paste -sd',' | sed 's/,/, /g' | fold -s -w 110 | sed 's/^/   /'
}

status() {
    local pidfile name state progress run sets=0 joined=0
    echo "Machine: $cores cores, $mem_gb GB of memory free, $(free_disk) of disk free here."
    for pidfile in "$LOGS"/*.pid; do
        [ -e "$pidfile" ] || { echo "Nothing has been started yet."; break; }
        name="$(basename "$pidfile" .pid)"
        if running "$name"; then
            state="RUNNING"
        elif tail -n 3 "$LOGS/$name.log" 2>/dev/null | grep -q "ALL DONE"; then
            state="FINISHED"
        else
            state="STOPPED before its end (the log's last lines follow)"
        fi
        echo "== $name: $state"
        tail -n 3 "$LOGS/$name.log" 2>/dev/null | cut -c1-160
    done
    for run in "$HERE"/runs/*; do
        [ -d "$run" ] || continue
        name="$(basename "$run")"
        progress="$run/progress.txt"
        if [ "${name#side_}" != "$name" ]; then
            sets=$(( sets + 1 ))
            if [ -f "$run/joined.json" ]; then joined=$(( joined + 1 )); fi
            continue
        fi
        [ -e "$progress" ] || continue
        state="$(grep -c "integrity passed" "$progress" || true) seeds finished"
        if [ -f "$run/joined.json" ]; then state="$state, joined"; fi
        echo "-- $name: $state; last: $(tail -n 1 "$progress" | cut -c1-110)"
    done
    if [ "$sets" -gt 0 ]; then echo "-- side sets: $joined finished of $sets started"; fi
    if [ -f "$SEND/MANIFEST.txt" ]; then
        echo "-- to send back: $SEND  ($(sed -n '3p' "$SEND/MANIFEST.txt"))"
    else
        echo "-- to send back: nothing yet; it will be in $SEND"
    fi
}

stop() {
    local pidfile name group waited
    for pidfile in "$LOGS"/*.pid; do
        [ -e "$pidfile" ] || continue
        name="$(basename "$pidfile" .pid)"
        running "$name" || continue
        group="$(cat "$pidfile")"
        echo "Stopping $name ..."
        kill -TERM -- "-$group" 2>/dev/null || true
        waited=0
        while running "$name" && [ "$waited" -lt 15 ]; do
            sleep 1
            waited=$(( waited + 1 ))
        done
        if running "$name"; then kill -KILL -- "-$group" 2>/dev/null || true; fi
    done
    echo "Stopped. Finished seeds are kept; the same command continues from them."
}

# Everything to send back, in send_back/ and nowhere else: cpm_summary.tar, every finished map's summary with the
# run's records (small); cpm_results.tar, the same with every seed's readings and the monthly series (large);
# MANIFEST.txt, which says what the two hold, whether the run was complete, and their checksums; and the self-test's
# report. The results are laid out under .server/packing first and that copy is removed once the files are written.
# Each file is written under another name and renamed when whole, so a file in send_back/ is never half written.
pack() {
    need_setup
    local out="$STAGE/cpm_second_run" found=0 run name reading held cut file
    rm -rf "$STAGE"
    mkdir -p "$out" "$SEND"
    for run in "$HERE"/runs/*; do
        [ -f "$run/joined.json" ] || continue
        found=1
        name="$(basename "$run")"
        (cd "$HERE" && "$PY" -X utf8 scripts/pack_results.py "$run" "$name" --into "$out" > /dev/null)
        cp "$run/spread.json" "$out/$name/" 2>/dev/null || true
    done
    [ "$found" = 1 ] || { rm -rf "$STAGE"; echo "No finished map found under $HERE/runs yet."; return 1; }
    for reading in $READINGS; do
        held="runs/side_banks_supported_$reading"
        cut="runs/development_$reading"
        [ -f "$HERE/$held/joined.json" ] && [ -f "$HERE/$cut/joined.json" ] || continue
        (cd "$HERE" && "$PY" -X utf8 scripts/bank_support.py "$held" "$cut" \
            --out "$out/side_banks_supported_$reading/bank_support.json" > /dev/null) ||
            echo "bank_support.py could not read $held against $cut"
    done
    (cd "$HERE" && "$PY" -X utf8 scripts/pack_results.py --sums --into "$out" > /dev/null)
    cp "$REPORT" "$HERE/runs/second_confirmation_count.json" "$out/" 2>/dev/null || true
    mkdir -p "$out/logs"
    cp "$LOGS"/*.log "$LOGS"/sides.list "$out/logs/" 2>/dev/null || true
    echo "$COMMIT" > "$out/COMMIT"
    git -C "$HERE" diff > "$out/CODE_DIFF.txt" 2>/dev/null || true
    tar cf "$SEND/cpm_results.tar.part" -C "$STAGE" cpm_second_run
    tar cf "$SEND/cpm_summary.tar.part" -C "$STAGE" --exclude='cells.json.gz*' --exclude='measures.json.gz*' \
        cpm_second_run
    for file in cpm_results.tar cpm_summary.tar; do mv -f "$SEND/$file.part" "$SEND/$file"; done
    manifest > "$SEND/MANIFEST.txt.part"
    mv -f "$SEND/MANIFEST.txt.part" "$SEND/MANIFEST.txt"
    rm -rf "$STAGE"
    echo "$(stamp)  packed into $SEND: cpm_summary.tar ($(du -h "$SEND/cpm_summary.tar" | cut -f1)) and" \
        "cpm_results.tar ($(du -h "$SEND/cpm_results.tar" | cut -f1)); MANIFEST.txt says what they hold."
}

# The text of send_back/MANIFEST.txt. Its third line says whether the run was complete when it was packed.
manifest() {
    local reading run name file sets=0 missing=""
    local state="COMPLETE: the development map, the side sets and the main run are in here."
    for reading in $READINGS; do
        [ -f "$HERE/runs/confirmation_$reading/joined.json" ] ||
            state="PARTIAL: the main run was not finished when this was packed."
    done
    [ -f "$LOGS/sides.list" ] || side_list > "$LOGS/sides.list" 2>/dev/null || true
    while read -r name reading; do
        [ -n "$name" ] || continue
        sets=$(( sets + 1 ))
        [ -f "$HERE/runs/side_${name}_$reading/joined.json" ] || missing="$missing $name($reading)"
    done < "$LOGS/sides.list"
    if [ -n "$missing" ] && [ "${state%%:*}" = COMPLETE ]; then
        state="COMPLETE BUT FOR SIDE SETS: the development map and the main run are in here; some side sets are not."
    fi
    if trial; then state="A TRIAL of the script on a small machine, not the run."; fi
    echo "Circulation-priced money: the second run."
    echo "Packed $(stamp) from the code at commit $COMMIT."
    echo "$state"
    echo
    echo "Finished maps in the two archives (name, seeds):"
    for run in "$HERE"/runs/*; do
        [ -f "$run/joined.json" ] || continue
        name="$(basename "$run")"
        echo "  $name  $(grep -c "integrity passed" "$run/progress.txt" 2>/dev/null || true)"
    done
    echo
    if [ -n "$missing" ]; then
        echo "Side sets not finished, of $sets (their logs are in logs/ inside the archives):"
        echo " $missing" | fold -s -w 110 | sed 's/^/ /'
    else
        echo "Side sets: all $sets finished."
    fi
    for reading in $READINGS; do
        file="NOT WRITTEN"
        if [ -f "$STAGE/cpm_second_run/side_banks_supported_$reading/bank_support.json" ]; then file="written"; fi
        echo "Banks with card lines held against cut (bank_support.json), savers reading the $reading: $file."
    done
    echo
    echo "Files in this folder (SHA-256, size, name):"
    for file in cpm_summary.tar cpm_results.tar check_report.txt; do
        [ -f "$SEND/$file" ] || continue
        echo "  $(sha256sum < "$SEND/$file" | cut -d' ' -f1)  $(du -h "$SEND/$file" | cut -f1)  $file"
    done
    echo
    echo "cpm_summary.tar: every finished map's summary and the run's records."
    echo "cpm_results.tar: the same, with every seed's readings and the monthly series."
    echo "Both unpack into the folder cpm_second_run/, whose file SHA256SUMS lists every store."
}

case "${1:-}" in
    all) all_steps ;;
    setup) setup ;;
    check) check ;;
    plan) plan ;;
    devmap) devmap ;;
    main) main_run ;;
    sides) sides ;;
    status) status ;;
    stop) stop ;;
    pack) pack ;;
    everything) everything ;;                         # the five below are what "all" and the jobs run
    chain) chain ;;
    maps) need_setup; cd "$HERE"; run_maps "$2" ;;
    count) need_setup; set_count ;;
    side-sets) need_setup; run_sides ;;
    side-one) side_one "$2" "$3" "${4:-}" ;;
    *) sed -n '2,16p' "$0"; exit 1 ;;
esac
