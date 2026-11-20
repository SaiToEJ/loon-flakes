{ pkgs
, mpvpaperWallpaper ? pkgs.callPackage ../mpvpaper-wallpaper {
    accent-wallpaper = pkgs.callPackage ../accent-wallpaper { };
  }
}:

let
  watcher = pkgs.writeShellApplication {
    name = "niri-wallpaper-visibility";
    runtimeInputs = [ pkgs.niri pkgs.python3 mpvpaperWallpaper ];
    text = ''
      exec python3 ${./watcher.py}
    '';
  };

  # Política de foco con dos monitores: ghostty/port animan, una app opaca
  # congela y la ausencia de foco anima. Sin estos tests el bug solo se veía
  # en vivo, con el escritorio ocupado y dos workspaces activos.
  focusedTests = pkgs.runCommand "niri-wallpaper-visibility-focus-tests" {
    nativeBuildInputs = [ pkgs.python3 ];
  } ''
    ${pkgs.python3}/bin/python3 ${./tests/watcher.py} ${./watcher.py}
    touch $out
  '';
in
watcher.overrideAttrs (old: {
  passthru = (old.passthru or { }) // {
    tests = (old.passthru.tests or { }) // { focused = focusedTests; };
  };
})
