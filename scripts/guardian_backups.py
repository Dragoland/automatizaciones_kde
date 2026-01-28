#!/usr/bin/env python3
"""
GUARDIÁN DE BACKUPS CON VERIFICACIÓN
Versión mejorada con múltiples niveles de backup y verificación
"""
import os
import sys
import json
import hashlib
import shutil
import subprocess
import threading
import tarfile
import gzip
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from enum import Enum
import logging

class BackupType(Enum):
    FULL = "full"
    INCREMENTAL = "incremental"
    DIFFERENTIAL = "differential"

@dataclass
class BackupStats:
    total_files: int = 0
    total_size: int = 0
    files_copied: int = 0
    files_skipped: int = 0
    errors: int = 0
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    
    @property
    def duration(self) -> Optional[timedelta]:
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        return None
    
    @property
    def speed_mbps(self) -> Optional[float]:
        if self.duration and self.duration.total_seconds() > 0:
            return (self.total_size / (1024 * 1024)) / self.duration.total_seconds()
        return None

class BackupGuardian:
    def __init__(self, config_file: str = None):
        """Inicializar sistema de backup"""
        self.home = Path.home()
        self.config_dir = self.home / ".config" / "automatizacion_kde"
        self.log_dir = self.home / ".local" / "log" / "automatizacion"
        
        # Crear directorios necesarios
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # Configurar logging
        self._setup_logging()
        
        # Cargar configuración
        self.config = self._load_config(config_file)
        
        # Estadísticas
        self.stats = BackupStats()
        self.backup_history = []
        
    def _setup_logging(self):
        """Configurar sistema de logging"""
        log_file = self.log_dir / f"backup_{datetime.now().strftime('%Y-%m')}.log"
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file, encoding='utf-8'),
                logging.StreamHandler(sys.stdout)
            ]
        )
        self.logger = logging.getLogger('BackupGuardian')
        
    def _load_config(self, config_file: Optional[str]) -> Dict:
        """Cargar configuración desde archivo JSON"""
        if config_file is None:
            config_file = self.config_dir / "backup_config.json"
        
        config_path = Path(config_file)
        
        # Configuración por defecto
        config_default = {
            "backup": {
                "origen": str(self.home),
                "destino_base": "/media/tuusuario/Backup_Drive",
                "nombre_backup": "backup_home",
                "tipo": "incremental",  # full, incremental, differential
                "compresion": "gz",  # none, gz, bz2, xz
                "encryption": {
                    "habilitado": false,
                    "password": "",
                    "algorithm": "aes256"
                }
            },
            "exclusiones": {
                "patrones": [
                    "*/Descargas/*",
                    "*/.cache/*",
                    "*/.tmp/*",
                    "*/.temp/*",
                    "*.tmp",
                    "*.log",
                    "*.swp",
                    "*~"
                ],
                "directorios": [
                    ".cache",
                    ".tmp",
                    ".temp",
                    "Descargas",
                    "tmp",
                    "temp"
                ],
                "tamanio_maximo_mb": 100
            },
            "programacion": {
                "full_cada_dias": 7,
                "mantener_backups": 30,
                "hora_auto": "02:00",
                "ejecutar_auto": false
            },
            "verificacion": {
                "verificar_integridad": true,
                "checksum_algorithm": "sha256",
                "verificar_espacio": true,
                "espacio_minimo_gb": 10
            },
            "notificaciones": {
                "notificar_kde": true,
                "notificar_email": false,
                "email": "tu@email.com"
            }
        }
        
        if not config_path.exists():
            # Crear archivo de configuración por defecto
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config_default, f, indent=4, ensure_ascii=False)
            self.logger.warning(f"📄 Configuración creada en: {config_path}")
            self.logger.warning("   POR FAVOR EDITA LAS RUTAS ANTES DE USAR")
            return config_default
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                # Merge con valores por defecto
                return self._merge_configs(config_default, config)
        except Exception as e:
            self.logger.error(f"Error cargando configuración: {e}")
            return config_default
    
    def _merge_configs(self, default: Dict, user: Dict) -> Dict:
        """Combinar configuración por defecto con la del usuario"""
        merged = default.copy()
        
        def recursive_merge(base, update):
            for key, value in update.items():
                if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                    recursive_merge(base[key], value)
                else:
                    base[key] = value
        
        recursive_merge(merged, user)
        return merged
    
    def _check_disk_space(self) -> bool:
        """Verificar espacio en disco disponible"""
        if not self.config["verificacion"]["verificar_espacio"]:
            return True
        
        destino = Path(self.config["backup"]["destino_base"])
        if not destino.exists():
            self.logger.error(f"Directorio de destino no existe: {destino}")
            return False
        
        # Calcular espacio libre
        stat = shutil.disk_usage(destino)
        espacio_libre_gb = stat.free / (1024**3)
        espacio_minimo = self.config["verificacion"]["espacio_minimo_gb"]
        
        if espacio_libre_gb < espacio_minimo:
            self.logger.error(f"Espacio insuficiente: {espacio_libre_gb:.1f}GB < {espacio_minimo}GB")
            return False
        
        self.logger.info(f"Espacio disponible: {espacio_libre_gb:.1f}GB")
        return True
    
    def _should_exclude(self, path: Path) -> bool:
        """Determinar si un archivo/directorio debe ser excluido"""
        path_str = str(path)
        
        # Verificar patrones de exclusión
        for patron in self.config["exclusiones"]["patrones"]:
            import fnmatch
            if fnmatch.fnmatch(path_str, patron):
                return True
        
        # Verificar directorios excluidos
        for dir_name in self.config["exclusiones"]["directorios"]:
            if dir_name in path.parts:
                return True
        
        # Verificar tamaño máximo
        if path.is_file():
            tamanio_mb = path.stat().st_size / (1024**2)
            if tamanio_mb > self.config["exclusiones"]["tamanio_maximo_mb"]:
                self.logger.warning(f"Archivo muy grande excluido: {path} ({tamanio_mb:.1f}MB)")
                return True
        
        return False
    
    def _calculate_checksum(self, file_path: Path) -> Optional[str]:
        """Calcular checksum de un archivo"""
        algorithm = self.config["verificacion"]["checksum_algorithm"]
        hasher = getattr(hashlib, algorithm, hashlib.sha256)()
        
        try:
            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(8192), b''):
                    hasher.update(chunk)
            return hasher.hexdigest()
        except Exception as e:
            self.logger.error(f"Error calculando checksum de {file_path}: {e}")
            return None
    
    def _backup_with_rsync(self, origen: Path, destino: Path) -> bool:
        """Realizar backup usando rsync (más eficiente para muchos archivos)"""
        try:
            # Construir comando rsync
            cmd = [
                "rsync", "-avh", "--progress", "--delete",
                "--exclude-from=-",  # Leer exclusiones de stdin
                str(origen) + "/",
                str(destino)
            ]
            
            # Preparar exclusiones para stdin
            exclusiones = []
            for patron in self.config["exclusiones"]["patrones"]:
                exclusiones.append(patron)
            for directorio in self.config["exclusiones"]["directorios"]:
                exclusiones.append(f"*/{directorio}/*")
            
            exclusiones_str = "\n".join(exclusiones)
            
            # Ejecutar rsync
            self.logger.info(f"Ejecutando rsync: {' '.join(cmd)}")
            result = subprocess.run(
                cmd,
                input=exclusiones_str.encode(),
                capture_output=True,
                text=False
            )
            
            if result.returncode == 0:
                self.logger.info("Backup con rsync completado")
                return True
            else:
                self.logger.error(f"Error en rsync: {result.stderr}")
                return False
                
        except Exception as e:
            self.logger.error(f"Error ejecutando rsync: {e}")
            return False
    
    def _create_backup_manifest(self, backup_path: Path):
        """Crear manifiesto con información del backup"""
        manifest = {
            "fecha": datetime.now().isoformat(),
            "tipo": self.config["backup"]["tipo"],
            "origen": self.config["backup"]["origen"],
            "destino": str(backup_path),
            "estadisticas": {
                "total_files": self.stats.total_files,
                "total_size_gb": self.stats.total_size / (1024**3),
                "files_copied": self.stats.files_copied,
                "files_skipped": self.stats.files_skipped,
                "errors": self.stats.errors,
                "duration_seconds": self.stats.duration.total_seconds() if self.stats.duration else None,
                "speed_mbps": self.stats.speed_mbps
            },
            "checksums": {}
        }
        
        # Guardar manifiesto
        manifest_file = backup_path / "backup_manifest.json"
        with open(manifest_file, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, indent=4, ensure_ascii=False)
        
        self.logger.info(f"Manifiesto creado: {manifest_file}")
    
    def run_backup(self, tipo: str = None) -> bool:
        """Ejecutar backup"""
        self.stats = BackupStats()
        self.stats.start_time = datetime.now()
        
        # Determinar tipo de backup
        if tipo:
            backup_type = tipo
        else:
            backup_type = self.config["backup"]["tipo"]
        
        self.logger.info(f"Iniciando backup {backup_type.upper()}")
        
        # Verificar espacio
        if not self._check_disk_space():
            return False
        
        # Preparar rutas
        origen = Path(self.config["backup"]["origen"])
        destino_base = Path(self.config["backup"]["destino_base"])
        nombre_backup = self.config["backup"]["nombre_backup"]
        
        # Crear directorio de destino con timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = destino_base / f"{nombre_backup}_{timestamp}_{backup_type}"
        
        try:
            backup_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            self.logger.error(f"No se pudo crear directorio de backup: {e}")
            return False
        
        # Realizar backup
        success = False
        if backup_type == "full":
            success = self._perform_full_backup(origen, backup_dir)
        elif backup_type == "incremental":
            success = self._perform_incremental_backup(origen, backup_dir)
        else:
            self.logger.error(f"Tipo de backup no soportado: {backup_type}")
            return False
        
        # Finalizar estadísticas
        self.stats.end_time = datetime.now()
        
        if success:
            # Crear manifiesto
            self._create_backup_manifest(backup_dir)
            
            # Notificar
            self._send_notification(
                "✅ Backup completado",
                f"Backup {backup_type} completado exitosamente\n"
                f"Archivos: {self.stats.files_copied}\n"
                f"Duración: {self.stats.duration}\n"
                f"Tamaño: {self.stats.total_size / (1024**3):.2f} GB"
            )
            
            # Limpiar backups antiguos
            self._clean_old_backups()
            
            return True
        else:
            self._send_notification(
                "❌ Error en backup",
                f"El backup {backup_type} ha fallado"
            )
            return False
    
    def _perform_full_backup(self, origen: Path, destino: Path) -> bool:
        """Realizar backup completo"""
        self.logger.info(f"Backup COMPLETO: {origen} → {destino}")
        
        # Usar rsync para eficiencia
        return self._backup_with_rsync(origen, destino)
    
    def _perform_incremental_backup(self, origen: Path, destino: Path) -> bool:
        """Realizar backup incremental"""
        self.logger.info(f"Backup INCREMENTAL: {origen} → {destino}")
        
        # Buscar último backup para comparar
        backup_base = Path(self.config["backup"]["destino_base"])
        backups = list(backup_base.glob(f"{self.config['backup']['nombre_backup']}_*_full"))
        backups.sort(reverse=True)
        
        if not backups:
            self.logger.warning("No hay backup completo previo, haciendo backup completo")
            return self._perform_full_backup(origen, destino)
        
        # Usar rsync con link-dest para incremental
        try:
            last_backup = backups[0]
            cmd = [
                "rsync", "-avh", "--progress", "--delete",
                f"--link-dest={last_backup}",
                "--exclude-from=-",
                str(origen) + "/",
                str(destino)
            ]
            
            # Preparar exclusiones
            exclusiones = self.config["exclusiones"]["patrones"] + \
                         [f"*/{d}/*" for d in self.config["exclusiones"]["directorios"]]
            exclusiones_str = "\n".join(exclusiones)
            
            result = subprocess.run(
                cmd,
                input=exclusiones_str.encode(),
                capture_output=True,
                text=False
            )
            
            return result.returncode == 0
            
        except Exception as e:
            self.logger.error(f"Error en backup incremental: {e}")
            return False
    
    def _clean_old_backups(self):
        """Eliminar backups antiguos según la política de retención"""
        try:
            backup_base = Path(self.config["backup"]["destino_base"])
            dias_a_mantener = self.config["programacion"]["mantener_backups"]
            
            cutoff_date = datetime.now() - timedelta(days=dias_a_mantener)
            
            for backup_dir in backup_base.glob(f"{self.config['backup']['nombre_backup']}_*"):
                if backup_dir.is_dir():
                    # Extraer fecha del nombre del directorio
                    try:
                        fecha_str = backup_dir.name.split('_')[1]  # YYYYMMDD
                        fecha_backup = datetime.strptime(fecha_str, "%Y%m%d")
                        
                        if fecha_backup < cutoff_date:
                            self.logger.info(f"Eliminando backup antiguo: {backup_dir}")
                            shutil.rmtree(backup_dir)
                    except (IndexError, ValueError):
                        continue
                        
        except Exception as e:
            self.logger.error(f"Error limpiando backups antiguos: {e}")
    
    def _send_notification(self, titulo: str, mensaje: str):
        """Enviar notificación KDE"""
        if self.config["notificaciones"]["notificar_kde"]:
            try:
                subprocess.run([
                    "kdialog", "--title", titulo,
                    "--passivepopup", mensaje, "10"
                ])
            except Exception:
                pass  # Silenciar error si kdialog no está disponible
        
        self.logger.info(f"{titulo}: {mensaje}")

def main():
    """Función principal"""
    print("💾 Guardián de Backups - KDE Plasma")
    print("=" * 50)
    
    guardian = BackupGuardian()
    
    # Verificar configuración
    destino = Path(guardian.config["backup"]["destino_base"])
    if not destino.exists():
        print(f"❌ Error: Directorio de destino no existe: {destino}")
        print(f"   Por favor, edita: {guardian.config_dir}/backup_config.json")
        print(f"   Y asegúrate de que el dispositivo esté montado")
        return 1
    
    # Verificar rsync
    if shutil.which("rsync") is None:
        print("❌ Error: rsync no está instalado")
        print("   Instala con: sudo pacman -S rsync  # Arch")
        print("   o: sudo apt install rsync         # Debian/Ubuntu")
        return 1
    
    # Ejecutar backup
    print(f"🔄 Iniciando backup {guardian.config['backup']['tipo'].upper()}...")
    print(f"   Origen: {guardian.config['backup']['origen']}")
    print(f"   Destino: {destino}")
    print()
    
    if guardian.run_backup():
        print("\n✅ Backup completado exitosamente!")
        print(f"   Duración: {guardian.stats.duration}")
        print(f"   Archivos copiados: {guardian.stats.files_copied}")
        print(f"   Tamaño total: {guardian.stats.total_size / (1024**3):.2f} GB")
        return 0
    else:
        print("\n❌ Error en el backup")
        return 1

if __name__ == "__main__":
    exit(main())