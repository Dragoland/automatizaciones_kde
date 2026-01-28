# Automatización KDE Plasma

![Bash](https://img.shields.io/badge/Bash-4EAA25?style=for-the-badge&logo=gnu-bash&logoColor=white)
![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)
![KDE](https://img.shields.io/badge/KDE-Plasma-1D99F3?style=for-the-badge&logo=kde&logoColor=white)
![Arch Linux](https://img.shields.io/badge/Arch_Linux-1793D1?style=for-the-badge&logo=arch-linux&logoColor=white)

Colección de scripts de automatización para KDE Plasma que transforman tareas repetitivas en procesos automáticos, permitiéndote pasar de usuario a orquestador de tu entorno digital.

## 📦 Instalación

### Requisitos previos
- **Sistema operativo**: Linux (recomendado Arch Linux con KDE Plasma)
- **Python**: 3.8 o superior
- **Dependencias de KDE**: `kdialog` (para notificaciones)
- **Herramientas**: `rsync`, `paccache`, `at`

### Instalación rápida
```bash
git clone https://github.com/Dragoland/automatizacion-kde.git
cd automatizacion-kde
chmod +x scripts/*.sh
pip install -r requirements.txt
```

## 🚀 Scripts disponibles

### 1. 📁 Organizador Automático de Descargas
Organiza automáticamente los archivos descargados en carpetas específicas.

**Configuración básica (`config/config.sh`)**:
```bash
# Rutas personalizables
DOWNLOADS_DIR="$HOME/Descargas"
DOCS_DIR="$HOME/Documentos"
IMAGES_DIR="$HOME/Imágenes"
VIDEOS_DIR="$HOME/Vídeos"
ARCHIVES_DIR="$HOME/Archivos_Comprimidos"
SOFTWARE_DIR="$HOME/Software"
```

**Uso**:
```bash
./scripts/organizador_descargas.sh
# o
python scripts/organizador_avanzado.py
```

### 2. 💾 Guardián de Backups con Verificación
Sistema de backup inteligente con verificación de integridad.

**Configuración (`config/backup_config.py`)**:
```python
ORIGIN_PATH = Path.home()
BACKUP_PATH = Path("/ruta/a/tu/disco/backup")  # ¡MODIFICA ESTO!
EXCLUDE_PATTERNS = [
    "Descargas/",
    ".cache/",
    "tmp/",
    "*.tmp"
]
```

**Uso**:
```bash
python scripts/guardian_backups.py
```

### 3. 🧹 Limpiador Inteligente de Sistema
Limpia caché, paquetes huérfanos y optimiza el sistema.

**Configuración**:
Edita `scripts/limpiador_sistema.sh` para ajustar:
- Número de versiones de paquetes a mantener
- Días para limpiar caché
- Directorios adicionales a limpiar

**Uso**:
```bash
./scripts/limpiador_sistema.sh
```

### 4. 🔍 Monitor de Sistema y Alertas
Monitoriza recursos del sistema y envía alertas.

**Umbrales configurables (`config/monitor_config.py`)**:
```python
ALERT_THRESHOLDS = {
    'cpu_percent': 85,
    'memory_percent': 90,
    'temperature_celsius': 80,
    'disk_percent': 90
}
```

**Uso**:
```bash
python scripts/monitor_sistema.py
```

### 5. 🚀 Iniciador de Entorno de Trabajo
Prepara automáticamente tu espacio de trabajo con todas las aplicaciones.

**Configuración personalizable (`config/work_env.json`)**:
```json
{
    "code_editor": "code",
    "projects_path": "~/proyectos",
    "terminals": [
        {"profile": "Profile1", "directory": "~/proyectos"},
        {"profile": "Profile2", "directory": "~/documentacion"}
    ],
    "file_manager": "dolphin",
    "default_desktop": 2,
    "default_volume": 30
}
```

**Uso**:
```bash
./scripts/iniciador_trabajo.sh
```

### 6. 📅 Programador de Tareas con Interfaz
Programa recordatorios y tareas desde la línea de comandos.

**Uso interactivo**:
```bash
python scripts/programador_tareas.py
```

## ⚙️ Automatización avanzada

### Configurar ejecución automática

#### Método 1: Cron (tareas periódicas)
```bash
# Editar crontab
crontab -e

# Añadir estas líneas (ajusta las rutas):
# Organizar descargas cada hora
0 * * * * /ruta/completa/scripts/organizador_descargas.sh

# Limpieza diaria a las 2 AM
0 2 * * * /ruta/completa/scripts/limpiador_sistema.sh

# Backup semanal los domingos a las 3 AM
0 3 * * 0 /ruta/completa/scripts/guardian_backups.py
```

#### Método 2: Systemd (servicios persistentes)
```bash
# Copiar el servicio
cp config/systemd/monitor_sistema.service ~/.config/systemd/user/

# Habilitar y arrancar
systemctl --user enable monitor_sistema.service
systemctl --user start monitor_sistema.service
```

#### Método 3: Autostart de KDE Plasma
```bash
# Copiar archivo .desktop
cp config/autostart/iniciador_trabajo.desktop ~/.config/autostart/
```

## 🔧 Personalización

### 1. Archivo de configuración principal
Crea `~/.config/automatizacion_kde/config.ini`:
```ini
[paths]
descargas = /home/tuusuario/Descargas
documentos = /home/tuusuario/Documentos
backup = /media/tuusuario/disco_backup

[preferencias]
notificaciones = si
log_level = info
idioma = es
```

### 2. Script de inicialización
Ejecuta `./setup.sh` para configurar tu entorno:
```bash
#!/bin/bash
echo "Configurando automatización KDE..."
echo "Por favor, introduce tus preferencias:"

read -p "Ruta de descargas [~/Descargas]: " descargas
read -p "Ruta de backup [/media/backup]: " backup
read -p "¿Activar notificaciones? [si/no]: " notificaciones

# Crear archivo de configuración
cat > ~/.config/automatizacion_kde/personal.json << EOF
{
    "usuario": "$USER",
    "descargas": "${descargas:-~/Descargas}",
    "backup": "${backup:-/media/backup}",
    "notificaciones": "${notificaciones:-si}"
}
EOF

echo "✅ Configuración completada!"
```

## 📊 Estructura del proyecto
```
automatizacion-kde/
├── scripts/                    # Scripts principales
│   ├── organizador_descargas.sh
│   ├── organizador_avanzado.py
│   ├── guardian_backups.py
│   ├── limpiador_sistema.sh
│   ├── monitor_sistema.py
│   ├── iniciador_trabajo.sh
│   └── programador_tareas.py
├── config/                     # Configuraciones
│   ├── config.sh
│   ├── backup_config.py
│   ├── monitor_config.py
│   ├── work_env.json
│   ├── systemd/               # Servicios systemd
│   └── autostart/             # Inicio automático KDE
├── logs/                      # Logs generados
├── tests/                     # Tests de los scripts
├── docs/                      # Documentación
├── requirements.txt           # Dependencias Python
├── setup.sh                   # Script de instalación
└── README.md                  # Este archivo
```

## 🛡️ Seguridad y precauciones

### Antes de usar:
1. **Backup de tus datos**: Haz una copia de seguridad completa
2. **Revisa las rutas**: Asegúrate que coinciden con tu sistema
3. **Prueba en modo seguro**: Usa el flag `--dry-run` cuando esté disponible

### Modo prueba:
```bash
# Probar organizador sin mover archivos
python scripts/organizador_avanzado.py --dry-run

# Probar backup sin copiar
python scripts/guardian_backups.py --test
```

## 🐛 Solución de problemas

### Problemas comunes:

1. **"kdialog no encontrado"**:
   ```bash
   sudo pacman -S kdialog  # Arch Linux
   sudo apt install kdialog # Debian/Ubuntu
   ```

2. **Permisos denegados**:
   ```bash
   chmod +x scripts/*.sh
   chmod +x scripts/*.py
   ```

3. **Rutas incorrectas**:
   Verifica y actualiza las rutas en `config/config.sh`

### Logs de depuración:
Los scripts generan logs en `~/.local/log/automatizacion/`
```bash
tail -f ~/.local/log/automatizacion/errores.log
```

## 🤝 Contribuciones

¡Las contribuciones son bienvenidas! Por favor:

1. Haz fork del repositorio
2. Crea una rama para tu funcionalidad (`git checkout -b feature/nueva-funcionalidad`)
3. Commit de tus cambios (`git commit -m 'Añadir nueva funcionalidad'`)
4. Push a la rama (`git push origin feature/nueva-funcionalidad`)
5. Abre un Pull Request

## 📄 Licencia

Este proyecto está licenciado bajo la Licencia MIT - ver el archivo [LICENSE](LICENSE) para más detalles.

## ⚠️ Descargo de responsabilidad

Estos scripts son proporcionados "TAL CUAL", sin garantías de ningún tipo. El usuario es responsable de:
- Leer y entender los scripts antes de ejecutarlos
- Adaptar las rutas y configuraciones a su sistema
- Mantener backups actualizados de sus datos
- Probar en un entorno seguro antes de usar en producción

## 🌐 Enlaces

- **Repositorio**: https://github.com/Dragoland/automatizacion-kde
- **Reportar issues**: https://github.com/Dragoland/automatizacion-kde/issues
- **Canal de Telegram**: https://t.me/diario_del_informatico

## 📞 Soporte

¿Problemas o preguntas?
1. Revisa la [sección de troubleshooting](#-solución-de-problemas)
2. Abre un [issue en GitHub](https://github.com/Dragoland/automatizacion-kde/issues)
3. Únete a la discusión en Telegram

---

**Automatización no es pereza, es inteligencia aplicada.** ✨

*Con ❤️ por Dragoland para la comunidad KDE Plasma*  
*"Transformando frustraciones en soluciones elegantes"*

---
*Última actualización: $(date)*  
*Scripts probados en: Arch Linux + KDE Plasma 6*


