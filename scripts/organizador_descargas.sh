#!/bin/bash
# =============================================================================
# ORGANIZADOR AUTOMÁTICO DE DESCARGAS PARA KDE PLASMA
# Versión mejorada con validaciones y logs detallados
# =============================================================================

# Configuración - USUARIO: MODIFICA ESTAS RUTAS
readonly CONFIG_DIR="$HOME/.config/automatizacion_kde"
readonly LOG_DIR="$HOME/.local/log/automatizacion"
readonly CONFIG_FILE="$CONFIG_DIR/organizador.conf"

# Crear directorios necesarios
mkdir -p "$CONFIG_DIR" "$LOG_DIR"

# Si no existe archivo de configuración, crearlo
if [[ ! -f "$CONFIG_FILE" ]]; then
    cat > "$CONFIG_FILE" << 'EOF'
# =============================================================================
# CONFIGURACIÓN ORGANIZADOR DE DESCARGAS
# Modifica estas rutas según tu sistema
# =============================================================================

# Ruta de descargas (cambia 'tuusuario' por tu nombre de usuario real)
DOWNLOADS="$HOME/Descargas"

# Directorios destino
DOCS="$HOME/Documentos"
IMAGES="$HOME/Imágenes"
VIDEOS="$HOME/Vídeos"
ARCHIVOS="$HOME/Archivos_Comprimidos"
MUSICA="$HOME/Música"
SOFTWARE="$HOME/Software"
TORRENTS="$HOME/Torrents"

# Extensiones a organizar
EXT_DOCS="pdf docx txt odt md xlsx pptx"
EXT_IMAGES="jpg jpeg png gif webp bmp tiff svg"
EXT_VIDEOS="mp4 avi mkv mov flv wmv m4v webm"
EXT_ARCHIVOS="zip tar.gz rar 7z pkg.tar.zst tar.bz2"
EXT_MUSICA="mp3 flac wav ogg m4a"
EXT_SOFTWARE="deb rpm appimage exe msi pkg"
EXT_TORRENTS="torrent"

# Logging
ACTIVAR_LOG="si"  # si/no
LOG_DETALLADO="no" # si/no
EOF
    echo "⚠️  Archivo de configuración creado en: $CONFIG_FILE"
    echo "   Por favor, edítalo con tus rutas antes de ejecutar el script."
    exit 1
fi

# Cargar configuración
source "$CONFIG_FILE"

# Variables de log
readonly LOG_FILE="$LOG_DIR/organizador_$(date +%Y-%m-%d).log"
readonly ERROR_LOG="$LOG_DIR/errores_organizador.log"

# Funciones de utilidad
log_message() {
    local message="$1"
    local level="${2:-INFO}"
    
    if [[ "$ACTIVAR_LOG" == "si" ]]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] [$level] $message" >> "$LOG_FILE"
    fi
    
    if [[ "$LOG_DETALLADO" == "si" || "$level" == "ERROR" ]]; then
        echo "[$level] $message"
    fi
}

crear_directorio() {
    local dir="$1"
    local tipo="$2"
    
    if [[ ! -d "$dir" ]]; then
        mkdir -p "$dir"
        log_message "Creado directorio de $tipo: $dir"
    fi
}

validar_extension() {
    local archivo="$1"
    local extensiones="$2"
    
    for ext in $extensiones; do
        if [[ "${archivo,,}" == *".$ext" ]]; then
            return 0
        fi
    done
    return 1
}

mover_archivo() {
    local origen="$1"
    local destino="$2"
    local tipo="$3"
    
    if [[ ! -f "$origen" ]]; then
        log_message "Archivo no encontrado: $origen" "ERROR"
        return 1
    fi
    
    local nombre_archivo=$(basename "$origen")
    
    # Verificar si ya existe en destino
    if [[ -f "$destino/$nombre_archivo" ]]; then
        local timestamp=$(date +%Y%m%d_%H%M%S)
        local nuevo_nombre="${nombre_archivo%.*}_$timestamp.${nombre_archivo##*.}"
        destino="$destino/$nuevo_nombre"
        log_message "Archivo duplicado, renombrado a: $nuevo_nombre" "WARN"
    else
        destino="$destino/$nombre_archivo"
    fi
    
    # Mover archivo
    if mv "$origen" "$destino" 2>/dev/null; then
        log_message "Movido $tipo: $nombre_archivo → $(dirname "$destino")"
        return 0
    else
        log_message "Error moviendo: $nombre_archivo" "ERROR"
        echo "[ERROR] No se pudo mover: $origen" >> "$ERROR_LOG"
        return 1
    fi
}

# Verificar existencia de directorios
crear_directorio "$DOWNLOADS" "descargas"
crear_directorio "$DOCS" "documentos"
crear_directorio "$IMAGES" "imágenes"
crear_directorio "$VIDEOS" "videos"
crear_directorio "$ARCHIVOS" "archivos comprimidos"
crear_directorio "$MUSICA" "música"
crear_directorio "$SOFTWARE" "software"
crear_directorio "$TORRENTS" "torrents"

log_message "=== INICIANDO ORGANIZACIÓN DE DESCARGAS ==="

# Contadores
contador_total=0
contador_movidos=0
contador_errores=0

# Procesar cada archivo
for archivo in "$DOWNLOADS"/*; do
    # Saltar si no es archivo regular
    [[ ! -f "$archivo" ]] && continue
    
    contador_total=$((contador_total + 1))
    local nombre_archivo=$(basename "$archivo")
    
    # Saltar archivos ocultos
    [[ "$nombre_archivo" == .* ]] && continue
    
    # Determinar tipo y destino
    local destino=""
    local tipo=""
    
    if validar_extension "$archivo" "$EXT_DOCS"; then
        destino="$DOCS"
        tipo="documento"
    elif validar_extension "$archivo" "$EXT_IMAGES"; then
        destino="$IMAGES"
        tipo="imagen"
    elif validar_extension "$archivo" "$EXT_VIDEOS"; then
        destino="$VIDEOS"
        tipo="video"
    elif validar_extension "$archivo" "$EXT_ARCHIVOS"; then
        destino="$ARCHIVOS"
        tipo="archivo comprimido"
    elif validar_extension "$archivo" "$EXT_MUSICA"; then
        destino="$MUSICA"
        tipo="audio"
    elif validar_extension "$archivo" "$EXT_SOFTWARE"; then
        destino="$SOFTWARE"
        tipo="software"
    elif validar_extension "$archivo" "$EXT_TORRENTS"; then
        destino="$TORRENTS"
        tipo="torrent"
    else
        log_message "Extensión no reconocida: $nombre_archivo" "WARN"
        continue
    fi
    
    # Mover archivo
    if mover_archivo "$archivo" "$destino" "$tipo"; then
        contador_movidos=$((contador_movidos + 1))
    else
        contador_errores=$((contador_errores + 1))
    fi
done

# Resumen
log_message "=== RESUMEN DE ORGANIZACIÓN ==="
log_message "Total archivos procesados: $contador_total"
log_message "Archivos organizados: $contador_movidos"
log_message "Archivos con errores: $contador_errores"
log_message "Archivos no reconocidos: $((contador_total - contador_movidos - contador_errores))"

# Notificación KDE si está disponible
if command -v kdialog &> /dev/null && [[ "$contador_movidos" -gt 0 ]]; then
    kdialog --title "Organizador de Descargas" \
           --passivepopup "✅ Organizados $contador_movidos archivos" 5
fi

echo "✅ Organización completada. Ver logs en: $LOG_FILE"
exit 0