# Monitor principal: el KJW24FV anuncia 60 Hz como modo preferido, pero soporta
# 1920x1080@164.998 en DP-2. Lo fijamos aquí para que sobreviva a rebuilds.
{ ... }:

{
  programs.niri.defaultMonitorConfig = ''
    output "DP-2" {
      mode "1920x1080@164.998"
      position x=1366 y=0
    }
  '';
}
