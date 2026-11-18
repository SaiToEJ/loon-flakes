# Paquete "open-video-downloader": launcher estable de Open Video Downloader
# (antes youtube-dl-gui, de jely2002), GUI Tauri/Vue sobre yt-dlp para bajar
# vídeo, audio, subtítulos y metadatos de cientos de sitios.
#
# Mismo criterio que pkgs/filmcraft, pkgs/eglantine y pkgs/lichii (ver allí el
# detalle de la política de versiones de AGENTS.md): no está en nixpkgs, y
# aunque publica AppImage/.deb, ninguno corre tal cual en NixOS. La política
# prohíbe pins manuales nuevos, así que esto es un launcher mutable: Nix
# instala el comando, el .desktop y los iconos; el AppImage se descarga a
# ~/.local/share/open-video-downloader-appimage/ solo si falta y NUNCA se
# actualiza en un rebuild ni en un arranque. La propia app trae actualizador
# (de la app y de yt-dlp), así que refrescar la imagen es una orden explícita:
#   open-video-downloader --update
#
# Los assets llevan el número en el nombre
# (Open.Video.Downloader_3.2.1_amd64.AppImage), así que una URL de nombre fijo
# fijaría la release en el repo. La salida sin pin es resolver el asset de la
# última release con la API pública de GitHub (jq), con respaldo al redirect
# de /releases/latest. En ningún caso el número de versión viaja en este archivo.
#
# El AppImage no corre tal cual en NixOS (runtime FHS ausente → stub-ld), por
# eso se lanza con `appimage-run`. yt-dlp y ffmpeg entran en el PATH del launcher:
# son las herramientas con las que la app descarga y post-procesa; la app las
# gestiona por sí misma, pero así el entorno siempre las provee (.control del
# .deb oficial: libwebkit2gtk-4.1, gtk3 y libayatana-appindicator, ya dentro
# del AppImage).
{ lib, writeShellApplication, appimage-run, curl, jq, yt-dlp, ffmpeg, symlinkJoin }:

let
  latestApi = "https://api.github.com/repos/jely2002/youtube-dl-gui/releases/latest";
  releasesLatest = "https://github.com/jely2002/youtube-dl-gui/releases/latest";

  launcher = writeShellApplication {
    name = "open-video-downloader";
    runtimeInputs = [ appimage-run curl jq yt-dlp ffmpeg ];
    text = ''
      # Directorio propio del launcher, separado de los datos de la app para que
      # un "borrar datos" no se lleve el binario por delante (mismo motivo que
      # en eglantine/lichii/filmcraft).
      data_dir="''${XDG_DATA_HOME:-$HOME/.local/share}/open-video-downloader-appimage"
      app="$data_dir/open-video-downloader.AppImage"

      # `--update` solo como primer argumento: es nuestro flag, no de la app.
      # Fuerza la descarga de la última release sin tocar nada más.
      force=0
      if [ "''${1:-}" = "--update" ]; then
        force=1
        shift
      fi

      # Asset amd64 de la última release, sin versión escrita en el repo. La API
      # va primero; el redirect va de respaldo por si falla (rate limit sin
      # token: 60 peticiones/hora por IP, y esto solo se consulta al instalar o
      # actualizar, nunca en cada arranque).
      resolve_url() {
        url="$(curl -fsSL --retry 3 "${latestApi}" \
          | jq -r '[.assets[]? | .browser_download_url
                    | select(test("Open\\.Video\\.Downloader_[0-9.]*_amd64\\.AppImage$"))][0] // empty' \
          || true)"
        if [ -n "$url" ]; then
          printf '%s\n' "$url"
          return 0
        fi

        latest="$(curl -fsIL -o /dev/null -w '%{url_effective}' \
          "${releasesLatest}" || true)"
        tag="$(printf '%s' "$latest" | sed -n 's#.*/tag/\([^/]*\)$#\1#p')"
        if [ -z "$tag" ]; then
          return 1
        fi
        # El tag es `app-vX.Y.Z` y el asset lleva `X.Y.Z` sin el prefijo.
        printf '%s\n' "https://github.com/jely2002/youtube-dl-gui/releases/download/$tag/Open.Video.Downloader_''${tag#app-v}_amd64.AppImage"
      }

      if [ "$force" -eq 1 ] || [ ! -x "$app" ]; then
        mkdir -p "$data_dir"
        if ! url="$(resolve_url)"; then
          echo "open-video-downloader: no se pudo resolver la última release (¿sin red?)" >&2
          exit 1
        fi
        tmp="$app.tmp.$$"
        trap 'rm -f "$tmp"' EXIT
        echo "open-video-downloader: descargando el AppImage de la última release..." >&2
        curl -fL --retry 3 --retry-delay 2 -o "$tmp" "$url"
        chmod 0755 "$tmp"
        mv -f "$tmp" "$app"
        trap - EXIT
        rm -f "$data_dir/release"
        echo "open-video-downloader: descarga completada" >&2
      fi

      # Qué release está instalada: se lee el redirect de /releases/latest, una
      # petición HEAD sin API, sin token y sin fijar versión en el repo.
      if [ ! -f "$data_dir/release" ]; then
        latest="$(curl -fsIL -o /dev/null -w '%{url_effective}' \
          "${releasesLatest}" || true)"
        tag="$(printf '%s' "$latest" | sed -n 's#.*/tag/\([^/]*\)$#\1#p')"
        printf '%s\n' "''${tag:-desconocida}" > "$data_dir/release"
        echo "open-video-downloader: instalado ($tag)" >&2
      fi

      exec appimage-run "$app" "$@"
    '';
  };
in
symlinkJoin {
  name = "open-video-downloader";
  paths = [ launcher ];

  # El .desktop y los iconos viven dentro del AppImage y ahí no los ve
  # loon-launch (Super+Space) ni el buscador. Se instalan aquí tal como los trae
  # la release oficial (StartupWMClass=open-video-downloader, verificado en el
  # .desktop del .deb). Sin MimeType: no se captura ninguna asociación de
  # archivos, eso es responsabilidad de theme.nix.
  postBuild = ''
    mkdir -p "$out/share/applications"
    cat > "$out/share/applications/open-video-downloader.desktop" <<EOF
    [Desktop Entry]
    Type=Application
    Name=Open Video Downloader
    GenericName=Video Downloader
    Comment=Download videos from all over the web
    Exec=$out/bin/open-video-downloader %U
    Icon=open-video-downloader
    Terminal=false
    StartupWMClass=open-video-downloader
    Categories=Network;AudioVideo;
    EOF

    mkdir -p "$out/share/icons"
    cp -r ${./icons}/. "$out/share/icons/"
  '';

  meta = {
    description = "GUI para descargar vídeo/audio/subtítulos con yt-dlp (launcher mutable)";
    homepage = "https://github.com/jely2002/youtube-dl-gui";
    license = lib.licenses.agpl3Only;
    platforms = lib.platforms.linux;
    mainProgram = "open-video-downloader";
  };
}
