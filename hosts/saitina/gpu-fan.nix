# Curva de ventilador de la GTX 1070 (Pascal) controlada por NVML.
#
# El driver 580 ya no necesita Coolbits para mover el ventilador, y desde la
# serie 570 nvidia-settings usa NVML precisamente para funcionar en Wayland,
# donde no existe la extension X de NV-CONTROL. Por eso el servicio habla
# NVML directamente: no depende de DISPLAY ni de Xwayland.
#
# El script restaura la politica automatica del driver al salir; si el
# servicio se detiene o falla, la tarjeta vuelve a su curva de fabrica.
{ pkgs, ... }:

let
  py = pkgs.python3.withPackages (p: [ p.nvidia-ml-py ]);
  fanCtl = pkgs.writeText "gpu-fan.py" (builtins.readFile ./gpu-fan.py);
in
{
  systemd.services.gpu-fan-curve = {
    description = "GTX 1070 NVML fan curve";
    wantedBy = [ "multi-user.target" ];

    serviceConfig = {
      Type = "simple";
      Restart = "on-failure";
      RestartSec = 5;
      Environment = "PYTHONUNBUFFERED=1";
      ExecStart = "${py}/bin/python ${fanCtl}";
    };
  };
}
