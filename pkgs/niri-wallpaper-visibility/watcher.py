#!/usr/bin/env python3
"""Pausa mpvpaper salvo que el foco global esté en una app translúcida o no haya foco."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Any


# Política: el wallpaper animado corre a pleno cuando la ventana con el foco
# global es translúcida (ghostty, port) o cuando no hay ninguna ventana
# enfocada. Con cualquier otra ventana enfocada se congela en el último frame,
# y ahí está el ahorro: mpv deja de decodificar mientras el usuario mira el
# navegador o el chat. El foco es GLOBAL: niri mantiene una ventana "active"
# por workspace, así que mirar `active_window_id` de todos los workspaces
# activos congelaba el fondo en un monitor por una ventana del otro, y también
# cuando no había foco en ninguno (issue #4008 de niri documenta la diferencia
# entre active window y focused window). El window-rule de ghostty en
# config.kdl (opacity 0.8 + xray) es el que deja ver el fondo a través de ella.
ANIMATED_APP_IDS = frozenset({"com.mitchellh.ghostty", "port"})
PAUSE_REASON = "opaque-window"


class VisibilityState:
    def __init__(self) -> None:
        self.windows: dict[int, dict[str, Any]] = {}
        self.focused_window_id: int | None = None

    def should_freeze_wallpaper(self) -> bool:
        """True si el fondo debe congelarse: hay una ventana enfocada opaca.

        Sin ventana enfocada el fondo corre en las dos pantallas. Si el evento
        de foco llega antes que la descripción de la ventana, se congela de
        forma conservadora hasta que llegue el WindowOpenedOrChanged."""
        if self.focused_window_id is None:
            return False
        window = self.windows.get(self.focused_window_id)
        return window is None or window.get("app_id") not in ANIMATED_APP_IDS

    def update(self, event: dict[str, Any]) -> bool:
        """Aplica un evento; devuelve True si puede cambiar la visibilidad."""
        if payload := event.get("WindowsChanged"):
            # Instantánea inicial del event-stream: `is_focused` distingue la
            # única ventana con foco global de las "active" de cada monitor.
            self.windows = {window["id"]: window for window in payload["windows"]}
            focused = [w["id"] for w in self.windows.values() if w.get("is_focused")]
            self.focused_window_id = focused[0] if focused else None
            return True

        if payload := event.get("WindowOpenedOrChanged"):
            window = payload["window"]
            old = self.windows.get(window["id"])
            self.windows[window["id"]] = window
            if window.get("is_focused"):
                self.focused_window_id = window["id"]
            # Un cambio de título no altera la decisión; un cambio de app,
            # workspace o de quién tiene el foco sí puede alterarla.
            app_changed = old is None or (
                old.get("app_id"), old.get("workspace_id")
            ) != (window.get("app_id"), window.get("workspace_id"))
            gained_focus = bool(window.get("is_focused")) and (
                old is None or not old.get("is_focused")
            )
            return app_changed or gained_focus

        if payload := event.get("WindowFocusChanged"):
            # niri envía id=null cuando no hay foco (workspace vacío, overview,
            # etc.). Es la señal que faltaba para los dos monitores.
            focused = payload.get("id")
            if focused == self.focused_window_id:
                return False
            self.focused_window_id = focused
            return True

        if payload := event.get("WindowClosed"):
            window_id = payload["id"]
            removed = self.windows.pop(window_id, None)
            was_focused = self.focused_window_id == window_id
            if was_focused:
                self.focused_window_id = None
            return removed is not None or was_focused

        return False


def set_wallpaper_paused(paused: bool) -> None:
    args = ["mpvpaper-wallpaper", "pause" if paused else "resume", PAUSE_REASON]
    if paused:
        # El watcher es dueño de su motivo. Si muere sin retirarlo (crash, OOM,
        # reinicio del servicio) ese pid deja de existir y el siguiente
        # reconcile descarta el motivo en vez de dejar el fondo pausado para
        # siempre. 'resume' no necesita dueño: retira por nombre.
        args.append(f"pid:{os.getpid()}")
    subprocess.run(args, check=False, stdout=subprocess.DEVNULL)


def wallpaper_status() -> str:
    try:
        result = subprocess.run(
            ["mpvpaper-wallpaper", "status"],
            check=False,
            stdout=subprocess.PIPE,
            text=True,
        )
    except OSError:
        return ""
    return result.stdout.strip()


def pause_reasons() -> list[tuple[str, str, str]]:
    """Motivos de pausa presentes como (motivo, antigüedad, dueño).

    Se listan todos, incluido el propio `opaque-window`: si después de pedir
    animación sigue ahí, es información útil (otra instancia lo puso o el
    `resume` no llegó), no algo que deba esconderse. La antigüedad se devuelve
    aparte del motivo: si entrara en la firma de deduplicación, cambiaría cada
    segundo y el aviso se repetiría en todos los eventos.
    """
    try:
        result = subprocess.run(
            ["mpvpaper-wallpaper", "reasons"],
            check=False,
            stdout=subprocess.PIPE,
            text=True,
        )
    except OSError:
        return []
    reasons: list[tuple[str, str, str]] = []
    for line in result.stdout.splitlines():
        fields = line.split("\t")
        # reason<TAB>age<TAB>owner
        if len(fields) < 2:
            continue
        owner = fields[2] if len(fields) > 2 else "desconocido"
        reasons.append((fields[0], fields[1], owner))
    return reasons


_paused_warning: tuple[str, ...] | None = None


def warn_if_still_paused(desired_freeze: bool) -> None:
    """Avisa en el journal cuando el fondo sigue pausado pese a querer animarlo.

    Sin este aviso una pausa ajena es invisible: `status` solo dice 'paused' y el
    fondo se queda en el último frame hasta que alguien piense en correr
    `mpvpaper-wallpaper reasons`. Pasó el 2026-11-10: un motivo 'manual' de
    origen 'cli' congeló el fondo tres horas y ningún cambio de foco lo retiró,
    porque los motivos ajenos solo los retira una orden explícita `resume`.
    Se avisa una sola vez por conjunto de motivos para no inundar el journal
    con cada cambio de foco.
    """
    global _paused_warning
    if desired_freeze:
        return
    if wallpaper_status() != "paused":
        # Dejó de estar pausado: si vuelve a ocurrir, volverá a avisar.
        _paused_warning = None
        return
    reasons = pause_reasons()
    # Firma sin la antigüedad: ésta cambia cada segundo y el dedupe dejaría de
    # servir (se vio en vivo: cinco avisos en siete segundos).
    signature = tuple((reason, owner) for reason, _age, owner in reasons)
    if signature == _paused_warning:
        return
    _paused_warning = signature
    if reasons:
        detail = "por: " + ", ".join(
            f"{reason} ({age}, {owner})" for reason, age, owner in reasons
        )
    else:
        detail = (
            "sin ningún motivo registrado: es una pausa directa sobre el IPC de "
            "mpv, y el próximo `pause` la conservará como motivo 'manual'"
        )
    print(
        "niri-wallpaper-visibility: el fondo animado sigue pausado "
        f"{detail}. Reanuda con: mpvpaper-wallpaper resume",
        file=sys.stderr,
        flush=True,
    )


def main() -> int:
    if not os.environ.get("NIRI_SOCKET"):
        print("niri-wallpaper-visibility: NIRI_SOCKET no está definido", file=sys.stderr)
        return 1

    # Reconciliar al arrancar: una instancia anterior pudo morir con su motivo
    # de pausa puesto y, sin este paso, nada lo retiraría hasta el próximo
    # cambio de foco.
    subprocess.run(
        ["mpvpaper-wallpaper", "reconcile"],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    state = VisibilityState()
    applied: bool | None = None
    process = subprocess.Popen(
        ["niri", "msg", "-j", "event-stream"],
        stdout=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    assert process.stdout is not None

    try:
        for line in process.stdout:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not state.update(event):
                continue
            desired = state.should_freeze_wallpaper()
            if desired != applied:
                set_wallpaper_paused(desired)
                applied = desired
            # Se comprueba también cuando no hubo que actuar: una pausa ajena
            # puede aparecer (o desaparecer) sin que cambie la visibilidad.
            warn_if_still_paused(desired)
    finally:
        # El motivo se conserva si niri corta el stream; systemd reiniciará el
        # watcher y reconciliará el estado completo recibido al reconectar.
        if process.poll() is None:
            process.terminate()

    return process.wait()


if __name__ == "__main__":
    raise SystemExit(main())
