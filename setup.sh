#!/bin/bash
# Script de instalación para la suite de automatización KDE Plasma

set -euo pipefail

# Colores
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}🐉 Instalador de Automatización KDE Plasma${NC}"
echo -e "${BLUE}============================================${NC}"

# Verificar que estamos en Linux
if [[ "$(uname)" != "Linux" ]]; then
    echo -e "${RED}❌ Este script solo funciona en Linux${NC}"
    exit 1
fi

# Verificar KDE
if [[ -z "$XDG_CURRENT_DESKTOP" ]] || [[ ! "$XDG_CURRENT_DESKTOP" =~ .*KDE.* ]]; then
    echo -e "${YELLOW}⚠️  No se detectó KDE Plasma, algunas funciones pueden no funcionar${NC}"
    read -p "¿Continuar de todas formas? (s/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Ss]$ ]]; then
        exit 1
    fi
fi

# Directorios
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="$HOME/.local/bin/automatizacion_kde"
CONFIG_DIR="$HOME/.config/automatizacion_kde"
LOG_DIR="$HOME/.local/log/automatizacion"

echo -e "${BLUE}📁 Creando directorios...${NC}"
mkdir -p "$INSTALL_DIR" "$CONFIG_DIR" "$LOG_DIR" "$HOME/.local/bin"

# Función para instalar dependencias
install_dependencies() {
    echo -e "${BLUE}📦 Instalando dependencias...${NC}"
    
    # Detectar gestor de paquetes
    if command -v pacman &> /dev/null; then
        echo "  Detectado: Arch Linux / Manjaro"
        sudo pacman -S --needed --noconfirm \
            python python-pip jq rsync \
            kdialog konsole dolphin \
            cronie at
        
    elif command -v apt &> /dev/null; then
        echo "  Detectado: Debian / Ubuntu"
        sudo apt update
        sudo apt install -y \
            python3 python3-pip jq rsync \
            kdialog konsole dolphin \
            cron at
        
    elif command -v dnf &> /dev/null; then
        echo "  Detectado: Fedora / RHEL"
        sudo dnf install -y \
            python3 python3-pip jq rsync \
            kdialog konsole dolphin \
            cronie at
        
    else
        echo -e "${YELLOW}⚠️  Gestor de paquetes no reconocido${NC}"
        echo "  Por favor, instala manualmente:"
        echo "  - Python 3"
        echo "  - jq"
        echo "  - rsync"
        echo "  - kdialog"
        echo "  - cron/at"
    fi
    
    # Instalar dependencias Python
    echo -e "${BLUE}🐍 Instalando paquetes Python...${NC}"
    pip3 install --user psutil schedule
    
    echo -e "${GREEN}✅ Dependencias instaladas${NC}"
}

# Función para copiar scripts
copy_scripts() {
    echo -e "${BLUE}📄 Copiando scripts...${NC}"
    
    # Scripts principales
    cp -r "$SCRIPT_DIR/scripts/"* "$INSTALL_DIR/"
    cp -r "$SCRIPT_DIR/config/"* "$CONFIG_DIR/"
    
    # Hacer ejecutables
    chmod +x "$INSTALL_DIR"/*.sh
    chmod +x "$INSTALL_DIR"/*.py
    
    # Enlaces simbólicos en PATH
    for script in "$INSTALL_DIR"/*.sh "$INSTALL_DIR"/*.py; do
        if [[ -f "$script" ]]; then
            script_name=$(basename "$script" .sh)
            script_name=$(basename "$script_name" .py)
            ln -sf "$script" "$HOME/.local/bin/$script_name"
        fi
    done
    
    echo -e "${GREEN}✅ Scripts copiados a $INSTALL_DIR${NC}"
}

# Función para configurar cron jobs
setup_cron() {
    echo -e "${BLUE}⏰ Configurando tareas programadas...${NC}"
    
    CRON_FILE="$CONFIG_DIR/crontab"
    
    cat > "$CRON_FILE" << 'EOF'
# =============================================================================
# TAREAS PROGRAMADAS - AUTOMATIZACIÓN KDE PLASMA
# =============================================================================

# Organizar descargas cada hora
0 * * * * $HOME/.local/bin/organizador_descargas.sh

# Backup incremental diario a las 2 AM
0 2 * * * $HOME/.local/bin/guardian_backups.py

# Limpieza de sistema los domingos a las 3 AM
0 3 * * 0 $HOME/.local/bin/limpiador_sistema.sh

# Monitor del sistema cada 5 minutos (solo alertas)
*/5 * * * * $HOME/.local/bin/monitor_sistema.py --single

# Limpiar logs antiguos el primer día de cada mes
0 0 1 * * $HOME/.local/bin/limpiador_sistema.sh --cleanup-only

# Actualizar estadísticas cada día a las 6 AM
0 6 * * * $HOME/.local/bin/monitor_sistema.py --report 24

# Programador de tareas como daemon (se reinicia si falla)
@reboot $HOME/.local/bin/programador_tareas.py --daemon
EOF
    
    # Instalar cron jobs
    if crontab -l 2>/dev/null | grep -q "AUTOMATIZACIÓN KDE PLASMA"; then
        echo -e "${YELLOW}⚠️  Cron jobs ya configurados, saltando...${NC}"
    else
        cat "$CRON_FILE" | crontab -
        echo -e "${GREEN}✅ Cron jobs configurados${NC}"
    fi
}

# Función para configurar systemd services
setup_systemd() {
    echo -e "${BLUE}⚙️  Configurando servicios systemd...${NC}"
    
    SYSTEMD_USER_DIR="$HOME/.config/systemd/user"
    mkdir -p "$SYSTEMD_USER_DIR"
    
    # Servicio para el programador de tareas
    cat > "$SYSTEMD_USER_DIR/task-scheduler.service" << EOF
[Unit]
Description=Programador de Tareas KDE
After=network.target graphical-session.target
PartOf=graphical-session.target

[Service]
Type=simple
ExecStart=$HOME/.local/bin/programador_tareas.py --daemon
Restart=on-failure
RestartSec=10
Environment=DISPLAY=:0
Environment=XDG_RUNTIME_DIR=/run/user/%I

[Install]
WantedBy=default.target
EOF
    
    # Servicio para el monitor del sistema
    cat > "$SYSTEMD_USER_DIR/system-monitor.service" << EOF
[Unit]
Description=Monitor del Sistema KDE
After=network.target graphical-session.target
PartOf=graphical-session.target

[Service]
Type=simple
ExecStart=$HOME/.local/bin/monitor_sistema.py --daemon
Restart=on-failure
RestartSec=30
Environment=DISPLAY=:0
Environment=XDG_RUNTIME_DIR=/run/user/%I

[Install]
WantedBy=default.target
EOF
    
    # Recargar y habilitar servicios
    systemctl --user daemon-reload
    
    echo -e "${GREEN}✅ Servicios systemd creados${NC}"
    echo -e "${BLUE}   Para habilitar:${NC}"
    echo -e "   systemctl --user enable task-scheduler"
    echo -e "   systemctl --user enable system-monitor"
}

# Función para crear archivos de configuración personalizados
create_configs() {
    echo -e "${BLUE}⚙️  Personalizando configuraciones...${NC}"
    
    # Obtener nombre de usuario
    USERNAME=$(whoami)
    
    # Actualizar rutas en configuraciones
    for config_file in "$CONFIG_DIR"/*.json "$CONFIG_DIR"/*.conf; do
        if [[ -f "$config_file" ]]; then
            sed -i "s/tuusuario/$USERNAME/g" "$config_file"
        fi
    done
    
    echo -e "${GREEN}✅ Configuraciones personalizadas${NC}"
}

# Función para probar instalación
test_installation() {
    echo -e "${BLUE}🧪 Probando instalación...${NC}"
    
    # Probar scripts básicos
    echo -e "${BLUE}   Probando organizador de descargas...${NC}"
    if "$INSTALL_DIR/organizador_descargas.sh" --help &> /dev/null; then
        echo -e "${GREEN}   ✅ Organizador funcionando${NC}"
    else
        echo -e "${RED}   ❌ Error con organizador${NC}"
    fi
    
    echo -e "${BLUE}   Probando monitor del sistema...${NC}"
    python3 "$INSTALL_DIR/monitor_sistema.py" --single &> /dev/null
    if [[ $? -eq 0 ]]; then
        echo -e "${GREEN}   ✅ Monitor funcionando${NC}"
    else
        echo -e "${RED}   ❌ Error con monitor${NC}"
    fi
    
    echo -e "${GREEN}✅ Pruebas completadas${NC}"
}

# Función principal
main() {
    echo -e "${BLUE}Iniciando instalación...${NC}"
    
    # Menú de opciones
    echo -e "\n${YELLOW}Selecciona las opciones de instalación:${NC}"
    echo "  1) Instalar dependencias"
    echo "  2) Copiar scripts"
    echo "  3) Configurar cron jobs"
    echo "  4) Configurar servicios systemd"
    echo "  5) Todo (instalación completa)"
    echo "  6) Salir"
    
    read -p "Opción (1-6): " -n 1 -r
    echo
    
    case $REPLY in
        1)
            install_dependencies
            ;;
        2)
            copy_scripts
            create_configs
            ;;
        3)
            setup_cron
            ;;
        4)
            setup_systemd
            ;;
        5)
            install_dependencies
            copy_scripts
            create_configs
            setup_cron
            setup_systemd
            test_installation
            ;;
        6)
            echo -e "${BLUE}👋 Instalación cancelada${NC}"
            exit 0
            ;;
        *)
            echo -e "${RED}❌ Opción inválida${NC}"
            exit 1
            ;;
    esac
    
    # Resumen final
    echo -e "\n${GREEN}🎉 Instalación completada exitosamente!${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo -e "${GREEN}📁 Scripts instalados en:${NC} $INSTALL_DIR"
    echo -e "${GREEN}⚙️  Configuración en:${NC} $CONFIG_DIR"
    echo -e "${GREEN}📊 Logs en:${NC} $LOG_DIR"
    echo -e "\n${YELLOW}📖 Comandos disponibles:${NC}"
    echo "  organizador_descargas.sh"
    echo "  guardian_backups.py"
    echo "  limpiador_sistema.sh"
    echo "  monitor_sistema.py"
    echo "  iniciador_trabajo.sh"
    echo "  programador_tareas.py"
    echo -e "\n${YELLOW}🚀 Para empezar:${NC}"
    echo "  1. Edita los archivos en $CONFIG_DIR"
    echo "  2. Configura tus rutas y preferencias"
    echo "  3. Ejecuta: organizador_descargas.sh"
    echo -e "\n${BLUE}¡Disfruta de tu sistema automatizado! 🐉${NC}"
}

# Ejecutar instalación
main "$@"