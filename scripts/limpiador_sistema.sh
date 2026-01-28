#!/bin/bash
# =============================================================================
# LIMPIADOR INTELIGENTE DE SISTEMA PARA KDE PLASMA
# Versión mejorada con múltiples opciones y seguridad
# =============================================================================

set -euo pipefail

# Colores para output
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly BLUE='\033[0;34m'
readonly NC='\033[0m' # No Color

# Configuración
readonly CONFIG_DIR="$HOME/.config/automatizacion_kde"
readonly LOG_DIR="$HOME/.local/log/automatizacion"
readonly CONFIG_FILE="$CONFIG_DIR/limpiador.conf"
readonly BACKUP_DIR="$HOME/.local/backup_limpieza"

# Crear directorios necesarios
mkdir -p "$CONFIG_DIR" "$LOG_DIR" "$BACKUP_DIR"

# Si no existe archivo de configuración, crearlo
if [[ ! -f "$CONFIG_FILE" ]]; then
    cat > "$CONFIG_FILE" << 'EOF'
# =============================================================================
# CONFIGURACIÓN LIMPIADOR DE SISTEMA
# =============================================================================

# Limpieza de paquetes
PACMAN_KEEP_VERSIONS=2
APERTURE_KEEP_VERSIONS=3
CLEAN_ORPHANS=true

# Limpieza de caché
CACHE_MAX_DAYS=30
THUMBNAIL_MAX_DAYS=60
BROWSER_CACHE=true

# Limpieza de logs
JOURNAL_MAX_DAYS=30
LOG_ROTATE_DAYS=7

# Espacio mínimo a liberar (MB)
MIN_SPACE_TO_FREE=100

# Opciones de seguridad
BACKUP_BEFORE_DELETE=false
DRY_RUN=false
VERBOSE=false

# Directorios a limpiar adicionales
EXTRA_DIRS=(
    "$HOME/.local/share/Trash"
    "$HOME/.thumbnails"
    "$HOME/.var/app/*/cache"
)

# Exclusiones (no eliminar)
EXCLUDE_PATTERNS=(
    "*.important"
    "*.config"
    "*.db"
)
EOF
    echo -e "${YELLOW}⚠️  Archivo de configuración creado en: $CONFIG_FILE${NC}"
    echo -e "${BLUE}   Puedes editarlo según tus necesidades.${NC}"
fi

# Cargar configuración
source "$CONFIG_FILE"

# Variables
readonly LOG_FILE="$LOG_DIR/limpieza_$(date +%Y-%m-%d_%H-%M-%S).log"
readonly REPORT_FILE="$LOG_DIR/reporte_limpieza_$(date +%Y-%m-%d).txt"
readonly TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

# Funciones
log() {
    local message="$1"
    local level="${2:-INFO}"
    local color="$NC"
    
    case "$level" in
        "ERROR") color="$RED" ;;
        "WARN") color="$YELLOW" ;;
        "SUCCESS") color="$GREEN" ;;
        "INFO") color="$BLUE" ;;
    esac
    
    echo -e "${color}[$(date '+%H:%M:%S')] [$level] ${message}${NC}" | tee -a "$LOG_FILE"
    
    # También al reporte
    echo "[$(date '+%H:%M:%S')] [$level] $message" >> "$REPORT_FILE"
}

space_before() {
    df -h / | awk 'NR==2 {print $4}'
}

calculate_freed_space() {
    local before="$1"
    local after="$2"
    
    # Convertir a MB
    local before_mb=$(echo "$before" | sed 's/[A-Z]//g' | awk '{if ($1 ~ /G/) print $1*1024; else print $1}')
    local after_mb=$(echo "$after" | sed 's/[A-Z]//g' | awk '{if ($1 ~ /G/) print $1*1024; else print $1}')
    
    echo $(( ${after_mb%.*} - ${before_mb%.*} ))
}

backup_file() {
    local file="$1"
    local backup_path="$BACKUP_DIR/$(date +%Y%m%d_%H%M%S)_$(basename "$file")"
    
    if [[ "$BACKUP_BEFORE_DELETE" == "true" ]]; then
        cp -r "$file" "$backup_path" 2>/dev/null && \
        log "Backup creado: $file → $backup_path" "INFO"
    fi
}

clean_pacman_cache() {
    log "Limpieza de caché de pacman..." "INFO"
    
    if command -v paccache &> /dev/null; then
        if [[ "$DRY_RUN" == "true" ]]; then
            log "  [DRY RUN] Se eliminarían versiones excepto las $PACMAN_KEEP_VERSIONS más recientes" "INFO"
            paccache -dvk "$PACMAN_KEEP_VERSIONS" 2>&1 | tee -a "$LOG_FILE"
        else
            log "  Manteniendo $PACMAN_KEEP_VERSIONS versiones de cada paquete" "INFO"
            sudo paccache -rvk "$PACMAN_KEEP_VERSIONS" 2>&1 | tee -a "$LOG_FILE"
        fi
    else
        log "paccache no encontrado, usando pacman -Sc" "WARN"
        if [[ "$DRY_RUN" == "true" ]]; then
            log "  [DRY RUN] Se limpiaría caché de pacman" "INFO"
        else
            sudo pacman -Sc --noconfirm 2>&1 | tee -a "$LOG_FILE"
        fi
    fi
}

clean_orphan_packages() {
    if [[ "$CLEAN_ORPHANS" != "true" ]]; then
        return
    fi
    
    log "Buscando paquetes huérfanos..." "INFO"
    
    if command -v pacman &> /dev/null; then
        local orphans=$(pacman -Qtdq)
        
        if [[ -n "$orphans" ]]; then
            log "  Paquetes huérfanos encontrados:" "WARN"
            echo "$orphans" | tee -a "$LOG_FILE"
            
            if [[ "$DRY_RUN" != "true" ]]; then
                log "  Eliminando paquetes huérfanos..." "INFO"
                sudo pacman -Rns --noconfirm $orphans 2>&1 | tee -a "$LOG_FILE"
            else
                log "  [DRY RUN] Se eliminarían paquetes huérfanos" "INFO"
            fi
        else
            log "  No hay paquetes huérfanos" "SUCCESS"
        fi
    fi
}

clean_user_cache() {
    log "Limpieza de caché de usuario..." "INFO"
    
    local total_deleted=0
    local total_size=0
    
    # Cache general
    if [[ -d "$HOME/.cache" ]]; then
        log "  Limpiando ~/.cache..." "INFO"
        
        # Método seguro: solo archivos antiguos
        while IFS= read -r -d $'\0' file; do
            local size=$(stat -c%s "$file" 2>/dev/null || echo 0)
            total_size=$((total_size + size))
            
            if [[ "$DRY_RUN" == "true" ]]; then
                log "    [DRY RUN] Eliminaría: $file ($((size/1024)) KB)" "INFO"
            else
                backup_file "$file"
                rm -f "$file"
                total_deleted=$((total_deleted + 1))
            fi
        done < <(find "$HOME/.cache" -type f -atime +"$CACHE_MAX_DAYS" -print0 2>/dev/null)
    fi
    
    # Thumbnails
    if [[ -d "$HOME/.thumbnails" ]] && [[ "$THUMBNAIL_MAX_DAYS" -gt 0 ]]; then
        log "  Limpiando thumbnails..." "INFO"
        
        if [[ "$DRY_RUN" == "true" ]]; then
            local thumb_count=$(find "$HOME/.thumbnails" -type f -atime +"$THUMBNAIL_MAX_DAYS" | wc -l)
            log "    [DRY RUN] Eliminaría $thumb_count thumbnails" "INFO"
        else
            find "$HOME/.thumbnails" -type f -atime +"$THUMBNAIL_MAX_DAYS" -delete 2>/dev/null
        fi
    fi
    
    log "  Cache de usuario limpiado: $total_deleted archivos ($((total_size/1024/1024)) MB)" "SUCCESS"
}

clean_browser_cache() {
    if [[ "$BROWSER_CACHE" != "true" ]]; then
        return
    fi
    
    log "Limpieza de caché de navegadores..." "INFO"
    
    # Firefox
    if [[ -d "$HOME/.mozilla/firefox" ]]; then
        for profile in "$HOME/.mozilla/firefox"/*.default*; do
            if [[ -d "$profile" ]]; then
                local cache_dir="$profile/cache2"
                if [[ -d "$cache_dir" ]]; then
                    if [[ "$DRY_RUN" == "true" ]]; then
                        local cache_size=$(du -sh "$cache_dir" | cut -f1)
                        log "    [DRY RUN] Limpiaría caché Firefox: $cache_size" "INFO"
                    else
                        rm -rf "$cache_dir"
                        log "    Cache Firefox limpiado" "SUCCESS"
                    fi
                fi
            fi
        done
    fi
    
    # Chrome/Chromium
    if [[ -d "$HOME/.config/chromium" ]]; then
        local chromium_cache="$HOME/.config/chromium/Default/Cache"
        if [[ -d "$chromium_cache" ]]; then
            if [[ "$DRY_RUN" == "true" ]]; then
                local cache_size=$(du -sh "$chromium_cache" | cut -f1)
                log "    [DRY RUN] Limpiaría caché Chromium: $cache_size" "INFO"
            else
                rm -rf "$chromium_cache"
                log "    Cache Chromium limpiado" "SUCCESS"
            fi
        fi
    fi
}

clean_logs() {
    log "Limpieza de logs..." "INFO"
    
    # Logs del sistema con journalctl
    if command -v journalctl &> /dev/null && [[ "$JOURNAL_MAX_DAYS" -gt 0 ]]; then
        log "  Rotando logs del sistema..." "INFO"
        
        if [[ "$DRY_RUN" == "true" ]]; then
            log "    [DRY RUN] Se vaciarían logs de más de $JOURNAL_MAX_DAYS días" "INFO"
            sudo journalctl --vacuum-time="$JOURNAL_MAX_DAYS"d --dry-run 2>&1 | tee -a "$LOG_FILE"
        else
            sudo journalctl --vacuum-time="$JOURNAL_MAX_DAYS"d 2>&1 | tee -a "$LOG_FILE"
            log "    Logs del sistema rotados" "SUCCESS"
        fi
    fi
    
    # Logs de usuario
    if [[ "$LOG_ROTATE_DAYS" -gt 0 ]]; then
        log "  Limpiando logs antiguos de usuario..." "INFO"
        
        local user_logs=(
            "$HOME/.local/log"
            "$HOME/.cache/*.log"
            "$HOME/*.log"
        )
        
        for log_pattern in "${user_logs[@]}"; do
            while IFS= read -r -d $'\0' log_file; do
                if [[ $(find "$log_file" -mtime +"$LOG_ROTATE_DAYS" 2>/dev/null) ]]; then
                    if [[ "$DRY_RUN" == "true" ]]; then
                        log "    [DRY RUN] Eliminaría: $log_file" "INFO"
                    else
                        backup_file "$log_file"
                        rm -f "$log_file"
                    fi
                fi
            done < <(find $log_pattern -type f -name "*.log" -print0 2>/dev/null)
        done
    fi
}

clean_tmp_dirs() {
    log "Limpieza de directorios temporales..." "INFO"
    
    local tmp_dirs=(
        "/tmp"
        "/var/tmp"
        "$HOME/tmp"
        "$HOME/.tmp"
    )
    
    for tmp_dir in "${tmp_dirs[@]}"; do
        if [[ -d "$tmp_dir" ]]; then
            log "  Limpiando $tmp_dir..." "INFO"
            
            if [[ "$DRY_RUN" == "true" ]]; then
                local tmp_count=$(find "$tmp_dir" -maxdepth 1 -type f -mtime +1 | wc -l)
                log "    [DRY RUN] Eliminaría $tmp_count archivos temporales" "INFO"
            else
                # Solo archivos de más de 1 día, no directorios
                find "$tmp_dir" -maxdepth 1 -type f -mtime +1 -delete 2>/dev/null
            fi
        fi
    done
}

clean_extra_dirs() {
    if [[ ${#EXTRA_DIRS[@]} -eq 0 ]]; then
        return
    fi
    
    log "Limpieza de directorios adicionales..." "INFO"
    
    for dir_pattern in "${EXTRA_DIRS[@]}"; do
        # Expandir ~ y wildcards
        eval "local expanded_dirs=($dir_pattern)"
        
        for dir in "${expanded_dirs[@]}"; do
            if [[ -d "$dir" ]]; then
                log "  Limpiando $dir..." "INFO"
                
                if [[ "$DRY_RUN" == "true" ]]; then
                    local dir_size=$(du -sh "$dir" 2>/dev/null | cut -f1 || echo "0")
                    log "    [DRY RUN] Limpiaría: $dir ($dir_size)" "INFO"
                else
                    # Método seguro: solo contenido, no el directorio
                    find "$dir" -mindepth 1 -maxdepth 1 -exec rm -rf {} \; 2>/dev/null
                    log "    Directorio limpiado: $dir" "SUCCESS"
                fi
            fi
        done
    done
}

generate_report() {
    local space_before="$1"
    local space_after="$2"
    local freed_space="$3"
    
    log "=== REPORTE DE LIMPIEZA ===" "INFO"
    log "Fecha y hora: $TIMESTAMP" "INFO"
    log "Espacio antes: $space_before" "INFO"
    log "Espacio después: $space_after" "INFO"
    log "Espacio liberado: ${freed_space} MB" "SUCCESS"
    log "Modo dry run: $DRY_RUN" "INFO"
    log "Log guardado en: $LOG_FILE" "INFO"
    
    if [[ "$freed_space" -lt "$MIN_SPACE_TO_FREE" ]]; then
        log "AVISO: Se liberaron menos de $MIN_SPACE_TO_FREE MB" "WARN"
    fi
}

main() {
    echo -e "${GREEN}🧹 Limpiador Inteligente de Sistema${NC}"
    echo -e "${BLUE}========================================${NC}"
    
    # Mostrar configuración
    if [[ "$VERBOSE" == "true" ]]; then
        echo -e "${YELLOW}Configuración cargada:${NC}"
        echo "  Keep versions: $PACMAN_KEEP_VERSIONS"
        echo "  Clean orphans: $CLEAN_ORPHANS"
        echo "  Cache max days: $CACHE_MAX_DAYS"
        echo "  Dry run: $DRY_RUN"
        echo ""
    fi
    
    # Medir espacio antes
    local space_before=$(space_before)
    log "Espacio disponible antes: $space_before" "INFO"
    
    # Ejecutar limpieza
    clean_pacman_cache
    clean_orphan_packages
    clean_user_cache
    clean_browser_cache
    clean_logs
    clean_tmp_dirs
    clean_extra_dirs
    
    # Medir espacio después
    local space_after=$(space_before)  # Actualizar
    local freed_space=$(calculate_freed_space "$space_before" "$space_after")
    
    # Generar reporte
    generate_report "$space_before" "$space_after" "$freed_space"
    
    # Notificación KDE
    if command -v kdialog &> /dev/null && [[ "$DRY_RUN" != "true" ]]; then
        if [[ "$freed_space" -gt 0 ]]; then
            kdialog --title "Limpieza Completada" \
                   --passivepopup "✅ Liberados ${freed_space} MB" 5
        else
            kdialog --title "Limpieza Completada" \
                   --passivepopup "⚠️  No se liberó espacio significativo" 5
        fi
    fi
    
    echo -e "${GREEN}✅ Limpieza completada!${NC}"
    echo -e "${BLUE}   Ver reporte completo en: $REPORT_FILE${NC}"
}

# Manejo de señales
trap 'log "Script interrumpido por el usuario" "ERROR"; exit 1' INT TERM

# Ejecutar
main "$@"