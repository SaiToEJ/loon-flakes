#!/usr/bin/env python3
"""NVML fan curve for the GTX 1070 in saitina.

Runs as root from gpu-fan.nix. NVML is used instead of nvidia-settings because
driver 580 controls fans through NVML on Wayland, where the NV-CONTROL X
extension is unavailable. Manual fan policy is restored to the driver default
on exit so a stopped or crashed service can never leave the fan stuck.

CLI:
  --speed-at TEMP   print the curve speed for TEMP and exit (no NVML needed)
  --print-curve     print the whole curve and exit (no NVML needed)
  (no arguments)    run the control loop
"""

import argparse
import signal
import sys
import time

# Temperature in C -> fan duty in %. The final step forces full speed well
# below the driver's 96 C slowdown threshold.
CURVE = [(40, 30), (55, 40), (65, 50), (70, 65), (74, 75), (78, 90), (82, 100)]
POLL_SECONDS = 3
HYSTERESIS_C = 2
GPU_INDEX = 0


def fan_speed(temp):
    """Interpolate the curve, clamped to [30, 100]."""
    if temp <= CURVE[0][0]:
        return CURVE[0][1]
    for (t0, s0), (t1, s1) in zip(CURVE, CURVE[1:]):
        if temp <= t1:
            return round(s0 + (s1 - s0) * (temp - t0) / (t1 - t0))
    return CURVE[-1][1]


def run_daemon():
    import pynvml as N

    N.nvmlInit()
    handle = N.nvmlDeviceGetHandleByIndex(GPU_INDEX)
    fans = list(range(N.nvmlDeviceGetNumFans(handle)))
    if not fans:
        print("gpu-fan: GPU reports no controllable fans", file=sys.stderr)
        return 1

    def restore():
        for fan in fans:
            try:
                N.nvmlDeviceSetDefaultFanSpeed_v2(handle, fan)
            except N.NVMLError as err:
                print(f"gpu-fan: restore failed for fan {fan}: {err}", file=sys.stderr)

    stopping = False

    def request_stop(_signum, _frame):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    try:
        for fan in fans:
            N.nvmlDeviceSetFanControlPolicy(handle, fan, N.NVML_FAN_POLICY_MANUAL)
        print(f"gpu-fan: manual control active on {len(fans)} fan(s)", flush=True)

        last_temp = None
        while not stopping:
            temp = N.nvmlDeviceGetTemperature(handle, N.NVML_TEMPERATURE_GPU)
            target = fan_speed(temp)
            # Always re-apply at full speed, even for a 1 C step into the
            # safety zone; otherwise wait for a meaningful temperature change.
            if last_temp is None or abs(temp - last_temp) >= HYSTERESIS_C or target == 100:
                for fan in fans:
                    N.nvmlDeviceSetFanSpeed_v2(handle, fan, target)
                print(f"gpu-fan: {temp} C -> {target}%", flush=True)
                last_temp = temp
            time.sleep(POLL_SECONDS)
    except N.NVMLError as err:
        print(f"gpu-fan: NVML error: {err}", file=sys.stderr)
        return 1
    finally:
        restore()
        N.nvmlShutdown()
        print("gpu-fan: driver default fan policy restored", flush=True)
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--speed-at", type=int, metavar="TEMP")
    parser.add_argument("--print-curve", action="store_true")
    args = parser.parse_args()

    if args.speed_at is not None:
        print(fan_speed(args.speed_at))
        return 0
    if args.print_curve:
        print("tempC fan%")
        for temp, _ in CURVE:
            print(f"{temp} {fan_speed(temp)}")
        return 0
    return run_daemon()


if __name__ == "__main__":
    sys.exit(main())
