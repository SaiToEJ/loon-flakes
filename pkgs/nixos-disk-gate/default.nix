# Gate previo a switch/boot: comprueba que los UUID declarados para este host
# coincidan con los dispositivos montados y que /boot (vfat) tenga soporte en
# initrd. Evita aplicar una generación de otra rama/máquina que deje el sistema
# sin arrancar, como ocurrió con los UUID del fork.
{ pkgs }:

pkgs.writeShellScriptBin "nixos-disk-gate" ''
  set -euo pipefail

  FLAKE_DIR="''${1:-$HOME/.nixos}"
  HOST="''${2:-$(< /proc/sys/kernel/hostname)}"
  NIX_BIN="${pkgs.nix}/bin/nix"
  FINDMNT_BIN="${pkgs.util-linux}/bin/findmnt"

  root_dev="$("$NIX_BIN" eval --raw \
    "$FLAKE_DIR#nixosConfigurations.$HOST.config.fileSystems.\"/\".device" 2>/dev/null)" || {
    echo "nixos-disk-gate: no se pudo evaluar el dispositivo raíz de $HOST" >&2
    exit 1
  }
  boot_dev="$("$NIX_BIN" eval --raw \
    "$FLAKE_DIR#nixosConfigurations.$HOST.config.fileSystems.\"/boot\".device" 2>/dev/null)" || boot_dev=""

  root_uuid="''${root_dev##*/}"
  boot_uuid="''${boot_dev##*/}"
  live_root="$("$FINDMNT_BIN" -no UUID / 2>/dev/null)" || live_root=""
  live_boot="$("$FINDMNT_BIN" -no UUID /boot 2>/dev/null)" || live_boot=""

  if [[ -z "$live_root" ]]; then
    echo "nixos-disk-gate: no se pudo leer el UUID de /" >&2
    exit 1
  fi
  if [[ "$root_uuid" != "$live_root" ]]; then
    echo "nixos-disk-gate: el flake declara raíz '$root_uuid' pero / está montado desde '$live_root'." >&2
    exit 1
  fi
  if [[ "$boot_dev" == /dev/disk/by-uuid/* ]]; then
    if [[ -z "$live_boot" || "$boot_uuid" != "$live_boot" ]]; then
      echo "nixos-disk-gate: el flake declara /boot '$boot_uuid' pero /boot está montado desde '$live_boot'." >&2
      exit 1
    fi
    vfat="$("$NIX_BIN" eval \
      "$FLAKE_DIR#nixosConfigurations.$HOST.config.boot.initrd.supportedFilesystems.vfat" 2>/dev/null)" || vfat="false"
    if [[ "$vfat" != "true" ]]; then
      echo "nixos-disk-gate: /boot es vfat pero boot.initrd.supportedFilesystems.vfat no es true." >&2
      exit 1
    fi
  fi

  echo "nixos-disk-gate: UUID y vfat correctos para $HOST"
''
