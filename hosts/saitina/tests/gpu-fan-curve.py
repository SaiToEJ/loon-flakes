#!/usr/bin/env python3
"""Deterministic checks for the GTX 1070 fan curve.

Run with: python3 hosts/saitina/tests/gpu-fan-curve.py
The curve under test is exposed by gpu-fan.py through --speed-at, so these
checks never touch the GPU.
"""

import pathlib
import subprocess
import sys
import unittest

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "gpu-fan.py"


def speed_at(temp):
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--speed-at", str(temp)],
        check=True,
        capture_output=True,
        text=True,
    )
    return int(result.stdout.strip())


class FanCurveTest(unittest.TestCase):
    def test_curve_anchors(self):
        expected = {
            40: 30,
            55: 40,
            65: 50,
            70: 65,
            74: 75,
            78: 90,
            82: 100,
        }
        for temp, speed in expected.items():
            with self.subTest(temp=temp):
                self.assertEqual(speed_at(temp), speed)

    def test_interpolation(self):
        expected = {
            60: 45,
            68: 59,
            72: 70,
            80: 95,
        }
        for temp, speed in expected.items():
            with self.subTest(temp=temp):
                self.assertEqual(speed_at(temp), speed)

    def test_clamps(self):
        self.assertEqual(speed_at(20), 30)
        self.assertEqual(speed_at(95), 100)

    def test_monotonic(self):
        speeds = [speed_at(temp) for temp in range(20, 96)]
        self.assertEqual(speeds, sorted(speeds))


if __name__ == "__main__":
    unittest.main(verbosity=2)
