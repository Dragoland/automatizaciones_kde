#!/bin/bash
# =============================================================================
# INICIADOR DE ENTORNO DE TRABAJO PARA KDE PLASMA
# Versión mejorada con perfiles configurables y manejo de estado
# =============================================================================

set -euo pipefail

# Colores
readonly GREEN='\033[0;32m'
readonly BLUE='\033[0;34m'
readonly YELLOW='\033[1;33m'
readonly RED='\033[0;31m'
readonly NC='\033[0m'

# Configuración
readonly CONFIG_DIR="$HOME/.config/automatizacion_kde"
readonly PROFILES_DIR="$CONFIG_DIR/work_profiles"
readonly LOG_DIR="$HOME/.local/log/automatizacion"
readonly STATE_FILE="$CONFIG_DIR/work_env.state"
readonly CONFIG_FILE="$CONFIG_DIR/work_env.json"

# Crear directorios necesarios
mkdir -p "$CONFIG_DIR" "$PROFILES_DIR" "$LOG_DIR"

# Si no existe configuración, crear
if [[ ! -f "$CONFIG_FILE" ]]; then
    cat > "$CONFIG_FILE" << 'EOF'
{
    "profiles": {
        "default": {
            "description": "Perfil de trabajo por defecto",
            "applications": {
                "code_editor": {
                    "command": "code",
                    "args": ["$PROJECTS_PATH"],
                    "enabled": true,
                    "wait_seconds": 2
                },
                "terminals": [
                    {
                        "command": "konsole",
                        "args": ["--new-tab", "--workdir", "$PROJECTS_PATH", "-p", "Breeze"],
                        "profile": "Breeze",
                        "title": "Proyectos"
                    },
                    {
                        "command": "konsole",
                        "args": ["--new-tab", "--workdir", "$DOCS_PATH", "-p", "Breeze"],
                        "profile": "Breeze",
                        "title": "Documentación"
                    }
                ],
                "file_manager": {
                    "command": "dolphin",
                    "args": ["$PROJECTS_PATH"],
                    "enabled": true
                },
                "browser": {
                    "command": "firefox",
                    "args": [],
                    "enabled": false
                },
                "communication": {
                    "command": "discord",
                    "args": [],
                    "enabled": false
                }
            },
            "system": {
                "desktop": 2,
                "volume": 30,
                "notifications": true,
                "screen_layout": "default"
            },
            "paths": {
                "projects": "$HOME/proyectos",
                "docs": "$HOME/documentacion",
                "downloads": "$HOME/Descargas"
            },
            "custom_commands": [
                "echo '🚀 Entorno configurado'",
                "notify-send 'Work Environment' 'Ready to work!'"
            ]
        },
        "development": {
            "description": "Perfil para desarrollo",
            "applications": {
                "terminals": [
                    {
                        "command": "konsole",
                        "args": ["--new-tab", "--workdir", "$PROJECTS_PATH", "-e", "tmux"],
                        "title": "Terminal con TMUX"
                    }
                ]
            },
            "extends": "default"
        }
    },
    "settings": {
        "default_profile": "default",
        "save_state": true,
        "restore_state": true,
        "log_level": "info",
        "notify_completion": true
    }
}
EOF
    echo -e "${YELLOW}📄 Archivo de configuración creado en: $CONFIG_FILE${NC}"
    echo -e "${BLUE}   Edítalo para configurar tu entorno de trabajo.${NC}"
fi

# Cargar configuración
if ! command -v jq &> /dev/null; then
    echo -e "${RED}❌ Error: jq no está instalado${NC}"
    echo "   Instala con: sudo pacman -S jq  # Arch"
    echo "   o: sudo apt install jq         # Debian/Ubuntu"
    exit 1
fi

CONFIG=$(cat "$CONFIG_FILE")

# Funciones
log() {
    local message="$1"
    local level="${2:-INFO}"
    
    case "$level" in
        "ERROR") echo -e "${RED}[ERROR] $message${NC}" ;;
        "WARN") echo -e "${YELLOW}[WARN] $message${NC}" ;;
        "INFO") echo -e "${BLUE}[INFO] $message${NC}" ;;
        "SUCCESS") echo -e "${GREEN}[SUCCESS] $message${NC}" ;;
    esac
    
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [$level] $message" >> "$LOG_DIR/work_env.log"
}

check_command() {
    local cmd="$1"
    if ! command -v "$cmd" &> /dev/null; then
        log "Comando no encontrado: $cmd" "WARN"
        return 1
    fi
    return 0
}

expand_path() {
    local path="$1"
    # Expandir ~ y variables de entorno
    eval "echo \"$path\""
}

save_state() {
    local profile="$1"
    local timestamp=$(date +%s)
    
    cat > "$STATE_FILE" << EOF
{
    "profile": "$profile",
    "timestamp": "$timestamp",
    "applications": []
}
EOF
    log "Estado guardado para perfil: $profile" "INFO"
}

restore_state() {
    if [[ -f "$STATE_FILE" ]]; then
        local last_profile=$(jq -r '.profile' "$STATE_FILE")
        log "Estado anterior encontrado: $last_profile" "INFO"
        return 0
    fi
    return 1
}

launch_application() {
    local name="$1"
    local config="$2"
    
    local enabled=$(echo "$config" | jq -r '.enabled // true')
    if [[ "$enabled" != "true" ]]; then
        log "Aplicación deshabilitada: $name" "INFO"
        return
    fi
    
    local cmd=$(echo "$config" | jq -r '.command')
    if ! check_command "$cmd"; then
        return
    fi
    
    # Construir argumentos
    local args=""
    local raw_args=$(echo "$config" | jq -r '.args[]?')
    
    if [[ -n "$raw_args" ]]; then
        while IFS= read -r arg; do
            # Expandir variables en argumentos
            arg=$(expand_path "$arg")
            args="$args \"$arg\""
        done <<< "$raw_args"
    fi
    
    # Ejecutar en background
    eval "$cmd $args &"
    local pid=$!
    
    # Esperar si está configurado
    local wait_time=$(echo "$config" | jq -r '.wait_seconds // 0')
    if [[ "$wait_time" -gt 0 ]]; then
        sleep "$wait_time"
    fi
    
    log "Aplicación lanzada: $name (PID: $pid)" "SUCCESS"
}

configure_system() {
    local system_config="$1"
    
    # Configurar escritorio virtual
    local desktop=$(echo "$system_config" | jq -r '.desktop // empty')
    if [[ -n "$desktop" ]] && command -v qdbus &> /dev/null; then
        qdbus org.kde.KWin /KWin setCurrentDesktop "$desktop"
        log "Cambiado a escritorio: $desktop" "INFO"
    fi
    
    # Configurar volumen
    local volume=$(echo "$system_config" | jq -r '.volume // empty')
    if [[ -n "$volume" ]] && command -v pactl &> /dev/null; then
        pactl set-sink-volume @DEFAULT_SINK@ "${volume}%"
        log "Volumen ajustado a: ${volume}%" "INFO"
    fi
    
    # Deshabilitar notificaciones si es necesario
    local notifications=$(echo "$system_config" | jq -r '.notifications // true')
    if [[ "$notifications" == "false" ]] && command -v kdeconnect-cli &> /dev/null; then
        kdeconnect-cli --pause
        log "Notificaciones pausadas" "INFO"
    fi
}

execute_custom_commands() {
    local commands="$1"
    
    while IFS= read -r cmd; do
        if [[ -n "$cmd" ]]; then
            log "Ejecutando comando personalizado: $cmd" "INFO"
            eval "$cmd"
        fi
    done <<< "$commands"
}

load_profile() {
    local profile_name="$1"
    
    log "Cargando perfil: $profile_name" "INFO"
    
    # Obtener configuración del perfil
    local profile_config=$(echo "$CONFIG" | jq -r ".profiles.\"$profile_name\"")
    if [[ "$profile_config" == "null" ]]; then
        log "Perfil no encontrado: $profile_name" "ERROR"
        return 1
    fi
    
    # Verificar si extiende otro perfil
    local extends=$(echo "$profile_config" | jq -r '.extends // empty')
    if [[ -n "$extends" ]] && [[ "$extends" != "null" ]]; then
        log "Extendiendo perfil base: $extends" "INFO"
        load_profile "$extends"
    fi
    
    # Expandir paths
    local projects_path=$(echo "$profile_config" | jq -r '.paths.projects // "$HOME/proyectos"')
    local docs_path=$(echo "$profile_config" | jq -r '.paths.docs // "$HOME/documentacion"')
    
    PROJECTS_PATH=$(expand_path "$projects_path")
    DOCS_PATH=$(expand_path "$docs_path")
    
    # Crear directorios si no existen
    mkdir -p "$PROJECTS_PATH" "$DOCS_PATH"
    
    # Configurar sistema
    local system_config=$(echo "$profile_config" | jq -r '.system // {}')
    configure_system "$system_config"
    
    # Lanzar aplicaciones
    local apps_config=$(echo "$profile_config" | jq -r '.applications // {}')
    
    # Editor de código
    local code_editor=$(echo "$apps_config" | jq -r '.code_editor // {}')
    if [[ "$code_editor" != "null" ]] && [[ "$code_editor" != "{}" ]]; then
        launch_application "Editor de Código" "$code_editor"
    fi
    
    # Terminales
    local terminals=$(echo "$apps_config" | jq -r '.terminals // []')
    if [[ "$terminals" != "[]" ]]; then
        echo "$terminals" | jq -c '.[]' | while read -r terminal; do
            launch_application "Terminal" "$terminal"
        done
    fi
    
    # Gestor de archivos
    local file_manager=$(echo "$apps_config" | jq -r '.file_manager // {}')
    if [[ "$file_manager" != "null" ]] && [[ "$file_manager" != "{}" ]]; then
        launch_application "Gestor de Archivos" "$file_manager"
    fi
    
    # Navegador
    local browser=$(echo "$apps_config" | jq -r '.browser // {}')
    if [[ "$browser" != "null" ]] && [[ "$browser" != "{}" ]]; then
        launch_application "Navegador" "$browser"
    fi
    
    # Comunicación
    local communication=$(echo "$apps_config" | jq -r '.communication // {}')
    if [[ "$communication" != "null" ]] && [[ "$communication" != "{}" ]]; then
        launch_application "Comunicación" "$communication"
    fi
    
    # Comandos personalizados
    local custom_commands=$(echo "$profile_config" | jq -r '.custom_commands // [] | .[]')
    execute_custom_commands "$custom_commands"
    
    return 0
}

list_profiles() {
    echo -e "${BLUE}Perfiles disponibles:${NC}"
    echo "$CONFIG" | jq -r '.profiles | keys[]' | while read -r profile; do
        local desc=$(echo "$CONFIG" | jq -r ".profiles.\"$profile\".description // \"Sin descripción\"")
        echo "  ${GREEN}$profile${NC}: $desc"
    done
}

create_profile() {
    local name="$1"
    local template="${2:-default}"
    
    local profile_file="$PROFILES_DIR/${name}.json"
    
    if [[ -f "$profile_file" ]]; then
        log "El perfil ya existe: $name" "WARN"
        return 1
    fi
    
    # Crear desde template
    cat > "$profile_file" << EOF
{
    "description": "Perfil personalizado: $name",
    "extends": "$template",
    "applications": {
        "code_editor": {
            "command": "code",
            "args": ["\$PROJECTS_PATH"],
            "enabled": true
        }
    },
    "system": {
        "desktop": 2,
        "volume": 30
    }
}
EOF
    
    log "Perfil creado: $name (template: $template)" "SUCCESS"
    echo "Edita: $profile_file"
}

main() {
    local profile=""
    local action="start"
    
    # Parsear argumentos
    while [[ $# -gt 0 ]]; do
        case $1 in
            --profile|-p)
                profile="$2"
                shift 2
                ;;
            --list|-l)
                action="list"
                shift
                ;;
            --create|-c)
                action="create"
                shift
                ;;
            --help|-h)
                show_help
                exit 0
                ;;
            *)
                echo -e "${RED}Argumento desconocido: $1${NC}"
                show_help
                exit 1
                ;;
        esac
    done
    
    case "$action" in
        "list")
            list_profiles
            ;;
        "create")
            if [[ -z "$profile" ]]; then
                read -p "Nombre del nuevo perfil: " profile
            fi
            create_profile "$profile"
            ;;
        "start")
            # Determinar perfil a usar
            if [[ -z "$profile" ]]; then
                profile=$(echo "$CONFIG" | jq -r '.settings.default_profile')
            fi
            
            echo -e "${GREEN}🚀 Iniciador de Entorno de Trabajo${NC}"
            echo -e "${BLUE}===================================${NC}"
            
            # Restaurar estado si está habilitado
            local restore=$(echo "$CONFIG" | jq -r '.settings.restore_state')
            if [[ "$restore" == "true" ]]; then
                restore_state
            fi
            
            # Cargar perfil
            if load_profile "$profile"; then
                # Guardar estado si está habilitado
                local save=$(echo "$CONFIG" | jq -r '.settings.save_state')
                if [[ "$save" == "true" ]]; then
                    save_state "$profile"
                fi
                
                # Notificación de completado
                local notify=$(echo "$CONFIG" | jq -r '.settings.notify_completion')
                if [[ "$notify" == "true" ]] && command -v kdialog &> /dev/null; then
                    kdialog --title "Entorno de Trabajo" \
                           --passivepopup "✅ Perfil '$profile' cargado" 5
                fi
                
                echo -e "${GREEN}✅ Entorno configurado con perfil: $profile${NC}"
                echo -e "${BLUE}   Proyectos: $PROJECTS_PATH${NC}"
                echo -e "${BLUE}   Documentación: $DOCS_PATH${NC}"
            else
                echo -e "${RED}❌ Error cargando el perfil${NC}"
                exit 1
            fi
            ;;
    esac
}

show_help() {
    cat << EOF
Uso: $0 [OPCIONES]

Opciones:
  -p, --profile NOMBRE   Usar perfil específico
  -l, --list             Listar perfiles disponibles
  -c, --create NOMBRE    Crear nuevo perfil
  -h, --help             Mostrar esta ayuda

Ejemplos:
  $0                     # Usar perfil por defecto
  $0 -p development      # Usar perfil de desarrollo
  $0 -l                  # Listar perfiles
  $0 -c myprofile        # Crear nuevo perfil

EOF
}

# Manejar señales
trap 'log "Script interrumpido" "ERROR"; exit 1' INT TERM

# Ejecutar
main "$@"