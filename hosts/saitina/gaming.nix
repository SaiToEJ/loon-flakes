# Capacidad de juegos de saitina: Steam de nixpkgs (sin la pila custom
# Millennium/Accela, retirada aguas arriba) y TwintailLauncher.
{ pkgs, ... }:

{
  programs.steam.enable = true;

  environment.systemPackages = [
    (pkgs.callPackage ../../pkgs/twintaillauncher { })
  ];
}
