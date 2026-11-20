#!/usr/bin/env python3
"""Focus-policy tests for the niri wallpaper visibility watcher.

They exercise VisibilityState through niri-shaped events: the decision must be
about the globally focused window, not about active windows on every output.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import unittest
from typing import Any


# En el árbol se usa el watcher hermano; el derivation de Nix lo pasa como
# argumento porque solo copia esta carpeta de pruebas al store.
WATCHER = (
    pathlib.Path(sys.argv[1])
    if len(sys.argv) > 1
    else pathlib.Path(__file__).resolve().parents[1] / "watcher.py"
)
spec = importlib.util.spec_from_file_location("wallpaper_watcher", WATCHER)
assert spec is not None and spec.loader is not None
watcher = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = watcher
spec.loader.exec_module(watcher)


def window(window_id: int, app_id: str, workspace_id: int, focused: bool) -> dict[str, Any]:
    return {
        "id": window_id,
        "app_id": app_id,
        "workspace_id": workspace_id,
        "is_focused": focused,
    }


def workspace(
    workspace_id: int, output: str, active_window_id: int | None, focused: bool = False
) -> dict[str, Any]:
    return {
        "id": workspace_id,
        "output": output,
        "is_active": True,
        "is_focused": focused,
        "active_window_id": active_window_id,
    }


def two_output_state(focused_app_id: str | None) -> watcher.VisibilityState:
    """Two visible workspaces; only one window is globally focused."""
    state = watcher.VisibilityState()
    state.update({"WorkspacesChanged": {"workspaces": [
        workspace(1, "DP-2", 11 if focused_app_id else None, True),
        workspace(2, "DVI-D-1", 20),
    ]}})
    state.update({"WindowsChanged": {"windows": [
        window(10, "steam_proton", 1, False),
        window(11, focused_app_id or "ghostty", 1, focused_app_id is not None),
        window(20, "org.gnome.Nautilus", 2, False),
    ]}})
    return state


class FocusPolicyTests(unittest.TestCase):
    def test_ghostty_focused_on_one_output_animates_both_outputs(self) -> None:
        state = two_output_state("com.mitchellh.ghostty")

        self.assertFalse(state.should_freeze_wallpaper())

    def test_port_focused_on_one_output_animates_both_outputs(self) -> None:
        state = two_output_state("port")

        self.assertFalse(state.should_freeze_wallpaper())

    def test_opaque_focus_on_one_output_freezes(self) -> None:
        state = two_output_state("kalamar")

        self.assertTrue(state.should_freeze_wallpaper())

    def test_no_focused_window_with_two_outputs_animates(self) -> None:
        state = two_output_state("kalamar")
        self.assertTrue(state.should_freeze_wallpaper())

        self.assertTrue(state.update({"WindowFocusChanged": {"id": None}}))
        self.assertFalse(state.should_freeze_wallpaper())

    def test_focus_change_to_port_animates_and_to_opaque_freezes(self) -> None:
        state = two_output_state("port")
        self.assertFalse(state.should_freeze_wallpaper())

        self.assertTrue(state.update({"WindowFocusChanged": {"id": 20}}))
        self.assertTrue(state.should_freeze_wallpaper())

        self.assertTrue(state.update({"WindowFocusChanged": {"id": 11}}))
        self.assertFalse(state.should_freeze_wallpaper())

    def test_closing_the_focused_window_animates(self) -> None:
        state = two_output_state("com.mitchellh.ghostty")
        self.assertFalse(state.should_freeze_wallpaper())

        self.assertTrue(state.update({"WindowClosed": {"id": 11}}))
        self.assertFalse(state.should_freeze_wallpaper())


if __name__ == "__main__":
    # El primer argumento es la ruta del watcher que inyecta el derivation.
    if len(sys.argv) > 1:
        del sys.argv[1]
    unittest.main()
