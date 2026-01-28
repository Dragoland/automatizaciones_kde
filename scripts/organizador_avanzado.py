#!/usr/bin/env python3
"""
ORGANIZADOR AVANZADO DE DESCARGAS
Versión Python con características avanzadas
"""
import os
import shutil
import json
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
import mimetypes

class OrganizadorAvanzado:
    def __init__(self, config_file: str = None):
        """Inicializar organizador con configuración"""
        self.home = Path.home()
        self.config_dir = self.home / ".config" / "automatizacion_kde"
        self.log_dir = self.home / ".local" / "log" / "automatizacion"
        
        # Crear directorios necesarios
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # Cargar configuración
        self.config = self._cargar_configuracion(config_file)
        self.log_file = self.log_dir / f"organizador_avanzado_{datetime.now().strftime('%Y-%m-%d')}.log"
        
        # Inicializar mimetypes
        mimetypes.init()
        
    def _cargar_configuracion(self, config_file: Optional[str]) -> Dict:
        """Cargar configuración desde archivo JSON"""
        if config_file is None:
            config_file = self.config_dir / "organizador_avanzado.json"
        
        config_path = Path(config_file)
        
        # Configuración por defecto
        config_default = {
            "rutas": {
                "descargas": str(self.home / "Descargas"),
                "destinos": {
                    "documentos": str(self.home / "Documentos"),
                    "imagenes": str(self.home / "Imágenes"),
                    "videos": str(self.home / "Vídeos"),
                    "musica": str(self.home / "Música"),
                    "archivos": str(self.home / "Archivos_Comprimidos"),
                    "software": str(self.home / "Software"),
                    "otros": str(self.home / "Otros")
                }
            },
            "categorias": {
                "documentos": [".pdf", ".doc", ".docx", ".txt", ".rtf", ".odt", ".md", ".xlsx", ".pptx"],
                "imagenes": [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".webp", ".svg"],
                "videos": [".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".webm"],
                "musica": [".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac"],
                "archivos": [".zip", ".rar", ".7z", ".tar.gz", ".tar.bz2"],
                "software": [".deb", ".rpm", ".appimage", ".exe", ".msi", ".pkg"]
            },
            "opciones": {
                "organizar_por_fecha": True,
                "usar_mimetype": True,
                "verificar_duplicados": True,
                "crear_log": True,
                "notificar_kde": True
            }
        }
        
        if not config_path.exists():
            # Crear archivo de configuración por defecto
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config_default, f, indent=4, ensure_ascii=False)
            print(f"📄 Configuración creada en: {config_path}")
            print("   Por favor, edita las rutas antes de usar.")
            return config_default
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError:
            print(f"❌ Error en configuración. Usando valores por defecto.")
            return config_default
    
    def _log(self, mensaje: str, nivel: str = "INFO"):
        """Registrar mensaje en log"""
        if not self.config["opciones"]["crear_log"]:
            return
        
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_entry = f"[{timestamp}] [{nivel}] {mensaje}\n"
        
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(log_entry)
        
        if nivel == "ERROR" or nivel == "WARN":
            print(f"[{nivel}] {mensaje}")
    
    def _calcular_hash(self, ruta_archivo: Path) -> str:
        """Calcular hash MD5 del archivo para detección de duplicados"""
        hasher = hashlib.md5()
        try:
            with open(ruta_archivo, 'rb') as f:
                for bloque in iter(lambda: f.read(4096), b''):
                    hasher.update(bloque)
            return hasher.hexdigest()
        except Exception as e:
            self._log(f"Error calculando hash: {e}", "ERROR")
            return ""
    
    def _detectar_tipo_mimetype(self, ruta_archivo: Path) -> Optional[str]:
        """Detectar tipo de archivo usando mimetype"""
        tipo_mime, _ = mimetypes.guess_type(ruta_archivo)
        if tipo_mime:
            return tipo_mime.split('/')[0]  # 'image', 'video', etc.
        return None
    
    def _obtener_destino(self, archivo: Path, extension: str) -> Optional[Path]:
        """Determinar destino basado en extensión y tipo"""
        extension = extension.lower()
        
        # Primero buscar por extensión en categorías
        for categoria, extensiones in self.config["categorias"].items():
            if extension in extensiones:
                destino_base = Path(self.config["rutas"]["destinos"][categoria])
                
                # Organizar por fecha si está habilitado
                if self.config["opciones"]["organizar_por_fecha"] and categoria in ["imagenes", "videos"]:
                    fecha = datetime.fromtimestamp(archivo.stat().st_mtime)
                    destino = destino_base / fecha.strftime("%Y") / fecha.strftime("%m")
                    destino.mkdir(parents=True, exist_ok=True)
                    return destino
                return destino_base
        
        # Si no se encontró por extensión, usar mimetype
        if self.config["opciones"]["usar_mimetype"]:
            tipo_mime = self._detectar_tipo_mimetype(archivo)
            if tipo_mime:
                destino_base = Path(self.config["rutas"]["destinos"]["otros"]) / tipo_mime
                destino_base.mkdir(parents=True, exist_ok=True)
                return destino_base
        
        # Por defecto, ir a "otros"
        destino_base = Path(self.config["rutas"]["destinos"]["otros"])
        destino_base.mkdir(parents=True, exist_ok=True)
        return destino_base
    
    def organizar(self):
        """Método principal de organización"""
        descargas = Path(self.config["rutas"]["descargas"])
        
        if not descargas.exists():
            self._log(f"Directorio de descargas no existe: {descargas}", "ERROR")
            return
        
        self._log("=== INICIANDO ORGANIZACIÓN AVANZADA ===")
        
        estadisticas = {
            "total": 0,
            "movidos": 0,
            "errores": 0,
            "duplicados": 0,
            "hashes_calculados": {}
        }
        
        for archivo in descargas.iterdir():
            if not archivo.is_file():
                continue
            
            estadisticas["total"] += 1
            nombre_archivo = archivo.name
            
            # Saltar archivos ocultos y temporales
            if nombre_archivo.startswith('.') or nombre_archivo.endswith('~'):
                continue
            
            # Obtener extensión
            extension = archivo.suffix
            
            # Obtener destino
            destino = self._obtener_destino(archivo, extension)
            
            if not destino:
                self._log(f"No se pudo determinar destino para: {nombre_archivo}", "WARN")
                continue
            
            # Verificar duplicados por hash
            nombre_destino = destino / nombre_archivo
            if self.config["opciones"]["verificar_duplicados"] and nombre_destino.exists():
                hash_origen = self._calcular_hash(archivo)
                hash_destino = self._calcular_hash(nombre_destino)
                
                if hash_origen and hash_destino and hash_origen == hash_destino:
                    estadisticas["duplicados"] += 1
                    self._log(f"Duplicado detectado y eliminado: {nombre_archivo}", "INFO")
                    archivo.unlink()  # Eliminar duplicado
                    continue
                else:
                    # Renombrar si existe pero es diferente
                    contador = 1
                    while nombre_destino.exists():
                        nuevo_nombre = f"{archivo.stem}_{contador}{archivo.suffix}"
                        nombre_destino = destino / nuevo_nombre
                        contador += 1
            
            # Mover archivo
            try:
                shutil.move(str(archivo), str(nombre_destino))
                estadisticas["movidos"] += 1
                self._log(f"📁 Movido: {nombre_archivo} → {destino.name}")
                
                # Registrar hash si está habilitado
                if self.config["opciones"]["verificar_duplicados"]:
                    hash_archivo = self._calcular_hash(nombre_destino)
                    if hash_archivo:
                        estadisticas["hashes_calculados"][str(nombre_destino)] = hash_archivo
                        
            except Exception as e:
                estadisticas["errores"] += 1
                self._log(f"❌ Error moviendo {nombre_archivo}: {e}", "ERROR")
        
        # Mostrar resumen
        self._log("=== RESUMEN ===")
        self._log(f"Total procesados: {estadisticas['total']}")
        self._log(f"Archivos movidos: {estadisticas['movidos']}")
        self._log(f"Duplicados eliminados: {estadisticas['duplicados']}")
        self._log(f"Errores: {estadisticas['errores']}")
        
        # Notificación KDE
        if self.config["opciones"]["notificar_kde"] and estadisticas['movidos'] > 0:
            try:
                import subprocess
                subprocess.run([
                    "kdialog", "--title", "Organizador Avanzado",
                    "--passivepopup", f"✅ Organizados {estadisticas['movidos']} archivos", "5"
                ])
            except Exception:
                pass  # Silenciar error si kdialog no está disponible
        
        return estadisticas

def main():
    """Función principal"""
    print("🧹 Organizador Avanzado de Descargas")
    print("=" * 50)
    
    organizador = OrganizadorAvanzado()
    
    # Verificar configuración
    descargas = Path(organizador.config["rutas"]["descargas"])
    if not descargas.exists():
        print(f"❌ Error: Directorio de descargas no existe: {descargas}")
        print(f"   Por favor, edita: {organizador.config_dir}/organizador_avanzado.json")
        return 1
    
    # Ejecutar organización
    print("🔄 Organizando archivos...")
    resultados = organizador.organizar()
    
    print("\n✅ Organización completada!")
    print(f"   Archivos procesados: {resultados['total']}")
    print(f"   Archivos movidos: {resultados['movidos']}")
    print(f"   Log guardado en: {organizador.log_file}")
    
    return 0

if __name__ == "__main__":
    exit(main())