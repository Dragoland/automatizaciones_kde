#!/usr/bin/env python3
"""
MONITOR DE SISTEMA Y ALERTAS PARA KDE PLASMA
Versión mejorada con múltiples métricas y alertas inteligentes
"""
import os
import sys
import json
import time
import sqlite3
import smtplib
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from enum import Enum
import logging
import psutil
import GPUtil
import requests

class AlertLevel(Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"

@dataclass
class SystemMetrics:
    """Métricas del sistema"""
    timestamp: str
    cpu_percent: float
    cpu_temp: Optional[float]
    memory_percent: float
    memory_used_gb: float
    memory_total_gb: float
    disk_percent: float
    disk_used_gb: float
    disk_total_gb: float
    swap_percent: float
    network_sent_mb: float
    network_recv_mb: float
    uptime_hours: float
    processes: int
    load_avg_1min: float
    load_avg_5min: float
    load_avg_15min: float

@dataclass
class Alert:
    """Estructura de alerta"""
    level: AlertLevel
    source: str
    message: str
    value: float
    threshold: float
    timestamp: str

class SystemMonitor:
    def __init__(self, config_file: str = None):
        """Inicializar monitor del sistema"""
        self.home = Path.home()
        self.config_dir = self.home / ".config" / "automatizacion_kde"
        self.log_dir = self.home / ".local" / "log" / "automatizacion"
        self.db_dir = self.home / ".local" / "share" / "automatizacion"
        
        # Crear directorios necesarios
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.db_dir.mkdir(parents=True, exist_ok=True)
        
        # Configurar logging
        self._setup_logging()
        
        # Cargar configuración
        self.config = self._load_config(config_file)
        
        # Inicializar base de datos
        self.db_path = self.db_dir / "system_monitor.db"
        self._init_database()
        
        # Variables para cálculo de promedios
        self.metrics_history: List[SystemMetrics] = []
        self.max_history_size = 60  # Mantener 60 mediciones
        
        # Estadísticas
        self.alerts_today = 0
        self.start_time = datetime.now()
        
    def _setup_logging(self):
        """Configurar sistema de logging"""
        log_file = self.log_dir / f"monitor_{datetime.now().strftime('%Y-%m')}.log"
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file, encoding='utf-8'),
                logging.StreamHandler(sys.stdout)
            ]
        )
        self.logger = logging.getLogger('SystemMonitor')
        
    def _load_config(self, config_file: Optional[str]) -> Dict:
        """Cargar configuración desde archivo JSON"""
        if config_file is None:
            config_file = self.config_dir / "monitor_config.json"
        
        config_path = Path(config_file)
        
        # Configuración por defecto
        config_default = {
            "umbrales": {
                "cpu_percent": 85.0,
                "cpu_temp": 80.0,
                "memory_percent": 90.0,
                "disk_percent": 90.0,
                "swap_percent": 80.0,
                "load_avg_5min": 4.0,
                "process_limit": 500
            },
            "monitoreo": {
                "intervalo_segundos": 60,
                "guardar_historial": true,
                "historial_dias": 7,
                "monitorear_gpu": false,
                "monitorear_red": true,
                "monitorear_procesos": true
            },
            "alertas": {
                "notificar_kde": true,
                "notificar_email": false,
                "email_from": "monitor@dominio.com",
                "email_to": "admin@dominio.com",
                "smtp_server": "smtp.gmail.com",
                "smtp_port": 587,
                "smtp_username": "",
                "smtp_password": "",
                "cooldown_minutos": 30,
                "alertas_por_dia": 10
            },
            "acciones": {
                "auto_reiniciar_servicios": false,
                "servicios_a_reiniciar": ["nginx", "postgresql"],
                "limpiar_cache_alerta": false,
                "cache_limite_mb": 1000
            }
        }
        
        if not config_path.exists():
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config_default, f, indent=4, ensure_ascii=False)
            self.logger.warning(f"📄 Configuración creada en: {config_path}")
            return config_default
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            self.logger.error(f"Error cargando configuración: {e}")
            return config_default
    
    def _init_database(self):
        """Inicializar base de datos SQLite"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Tabla de métricas
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    cpu_percent REAL,
                    cpu_temp REAL,
                    memory_percent REAL,
                    memory_used_gb REAL,
                    memory_total_gb REAL,
                    disk_percent REAL,
                    disk_used_gb REAL,
                    disk_total_gb REAL,
                    swap_percent REAL,
                    network_sent_mb REAL,
                    network_recv_mb REAL,
                    uptime_hours REAL,
                    processes INTEGER,
                    load_avg_1min REAL,
                    load_avg_5min REAL,
                    load_avg_15min REAL
                )
            ''')
            
            # Tabla de alertas
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    level TEXT NOT NULL,
                    source TEXT NOT NULL,
                    message TEXT NOT NULL,
                    value REAL,
                    threshold REAL,
                    acknowledged INTEGER DEFAULT 0
                )
            ''')
            
            # Índices para búsquedas rápidas
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_metrics_timestamp ON metrics(timestamp)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_alerts_timestamp ON alerts(timestamp)')
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            self.logger.error(f"Error inicializando base de datos: {e}")
    
    def get_cpu_metrics(self) -> Dict[str, Any]:
        """Obtener métricas de CPU"""
        try:
            # Porcentaje de uso
            cpu_percent = psutil.cpu_percent(interval=1)
            
            # Temperatura (puede requerir privilegios)
            cpu_temp = None
            try:
                if hasattr(psutil, "sensors_temperatures"):
                    temps = psutil.sensors_temperatures()
                    if 'coretemp' in temps:
                        cpu_temp = temps['coretemp'][0].current
            except:
                pass
            
            # Load average
            load_avg = psutil.getloadavg()
            
            return {
                "percent": cpu_percent,
                "temperature": cpu_temp,
                "load_avg_1min": load_avg[0],
                "load_avg_5min": load_avg[1],
                "load_avg_15min": load_avg[2]
            }
        except Exception as e:
            self.logger.error(f"Error obteniendo métricas de CPU: {e}")
            return {}
    
    def get_memory_metrics(self) -> Dict[str, Any]:
        """Obtener métricas de memoria"""
        try:
            memory = psutil.virtual_memory()
            swap = psutil.swap_memory()
            
            return {
                "percent": memory.percent,
                "used_gb": memory.used / (1024**3),
                "total_gb": memory.total / (1024**3),
                "swap_percent": swap.percent,
                "swap_used_gb": swap.used / (1024**3),
                "swap_total_gb": swap.total / (1024**3)
            }
        except Exception as e:
            self.logger.error(f"Error obteniendo métricas de memoria: {e}")
            return {}
    
    def get_disk_metrics(self) -> Dict[str, Any]:
        """Obtener métricas de disco"""
        try:
            disk = psutil.disk_usage('/')
            
            return {
                "percent": disk.percent,
                "used_gb": disk.used / (1024**3),
                "total_gb": disk.total / (1024**3),
                "free_gb": disk.free / (1024**3)
            }
        except Exception as e:
            self.logger.error(f"Error obteniendo métricas de disco: {e}")
            return {}
    
    def get_network_metrics(self) -> Dict[str, Any]:
        """Obtener métricas de red"""
        try:
            net_io = psutil.net_io_counters()
            
            return {
                "sent_mb": net_io.bytes_sent / (1024**2),
                "recv_mb": net_io.bytes_recv / (1024**2),
                "packets_sent": net_io.packets_sent,
                "packets_recv": net_io.packets_recv
            }
        except Exception as e:
            self.logger.error(f"Error obteniendo métricas de red: {e}")
            return {}
    
    def get_system_metrics(self) -> SystemMetrics:
        """Obtener todas las métricas del sistema"""
        timestamp = datetime.now().isoformat()
        
        # Obtener métricas individuales
        cpu_metrics = self.get_cpu_metrics()
        memory_metrics = self.get_memory_metrics()
        disk_metrics = self.get_disk_metrics()
        network_metrics = self.get_network_metrics()
        
        # Obtener otras métricas
        processes = len(psutil.pids())
        uptime_seconds = time.time() - psutil.boot_time()
        
        # Crear objeto de métricas
        metrics = SystemMetrics(
            timestamp=timestamp,
            cpu_percent=cpu_metrics.get("percent", 0.0),
            cpu_temp=cpu_metrics.get("temperature"),
            memory_percent=memory_metrics.get("percent", 0.0),
            memory_used_gb=memory_metrics.get("used_gb", 0.0),
            memory_total_gb=memory_metrics.get("total_gb", 0.0),
            disk_percent=disk_metrics.get("percent", 0.0),
            disk_used_gb=disk_metrics.get("used_gb", 0.0),
            disk_total_gb=disk_metrics.get("total_gb", 0.0),
            swap_percent=memory_metrics.get("swap_percent", 0.0),
            network_sent_mb=network_metrics.get("sent_mb", 0.0),
            network_recv_mb=network_metrics.get("recv_mb", 0.0),
            uptime_hours=uptime_seconds / 3600,
            processes=processes,
            load_avg_1min=cpu_metrics.get("load_avg_1min", 0.0),
            load_avg_5min=cpu_metrics.get("load_avg_5min", 0.0),
            load_avg_15min=cpu_metrics.get("load_avg_15min", 0.0)
        )
        
        # Guardar en historial
        self.metrics_history.append(metrics)
        if len(self.metrics_history) > self.max_history_size:
            self.metrics_history.pop(0)
        
        # Guardar en base de datos si está habilitado
        if self.config["monitoreo"]["guardar_historial"]:
            self._save_metrics_to_db(metrics)
        
        return metrics
    
    def _save_metrics_to_db(self, metrics: SystemMetrics):
        """Guardar métricas en base de datos"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO metrics (
                    timestamp, cpu_percent, cpu_temp, memory_percent,
                    memory_used_gb, memory_total_gb, disk_percent,
                    disk_used_gb, disk_total_gb, swap_percent,
                    network_sent_mb, network_recv_mb, uptime_hours,
                    processes, load_avg_1min, load_avg_5min, load_avg_15min
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                metrics.timestamp, metrics.cpu_percent, metrics.cpu_temp,
                metrics.memory_percent, metrics.memory_used_gb,
                metrics.memory_total_gb, metrics.disk_percent,
                metrics.disk_used_gb, metrics.disk_total_gb,
                metrics.swap_percent, metrics.network_sent_mb,
                metrics.network_recv_mb, metrics.uptime_hours,
                metrics.processes, metrics.load_avg_1min,
                metrics.load_avg_5min, metrics.load_avg_15min
            ))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            self.logger.error(f"Error guardando métricas en DB: {e}")
    
    def check_alerts(self, metrics: SystemMetrics) -> List[Alert]:
        """Verificar condiciones de alerta"""
        alerts = []
        umbrales = self.config["umbrales"]
        
        # Verificar CPU
        if metrics.cpu_percent > umbrales["cpu_percent"]:
            alerts.append(Alert(
                level=AlertLevel.WARNING if metrics.cpu_percent < 95 else AlertLevel.CRITICAL,
                source="CPU",
                message=f"Uso de CPU elevado: {metrics.cpu_percent:.1f}%",
                value=metrics.cpu_percent,
                threshold=umbrales["cpu_percent"],
                timestamp=metrics.timestamp
            ))
        
        # Verificar temperatura CPU
        if metrics.cpu_temp and metrics.cpu_temp > umbrales["cpu_temp"]:
            alerts.append(Alert(
                level=AlertLevel.CRITICAL,
                source="CPU Temperature",
                message=f"Temperatura crítica: {metrics.cpu_temp:.1f}°C",
                value=metrics.cpu_temp,
                threshold=umbrales["cpu_temp"],
                timestamp=metrics.timestamp
            ))
        
        # Verificar memoria
        if metrics.memory_percent > umbrales["memory_percent"]:
            alerts.append(Alert(
                level=AlertLevel.WARNING if metrics.memory_percent < 95 else AlertLevel.CRITICAL,
                source="Memory",
                message=f"Memoria casi llena: {metrics.memory_percent:.1f}%",
                value=metrics.memory_percent,
                threshold=umbrales["memory_percent"],
                timestamp=metrics.timestamp
            ))
        
        # Verificar disco
        if metrics.disk_percent > umbrales["disk_percent"]:
            alerts.append(Alert(
                level=AlertLevel.CRITICAL,
                source="Disk",
                message=f"Disco casi lleno: {metrics.disk_percent:.1f}%",
                value=metrics.disk_percent,
                threshold=umbrales["disk_percent"],
                timestamp=metrics.timestamp
            ))
        
        # Verificar swap
        if metrics.swap_percent > umbrales["swap_percent"]:
            alerts.append(Alert(
                level=AlertLevel.WARNING,
                source="Swap",
                message=f"Uso de swap elevado: {metrics.swap_percent:.1f}%",
                value=metrics.swap_percent,
                threshold=umbrales["swap_percent"],
                timestamp=metrics.timestamp
            ))
        
        # Verificar load average
        if metrics.load_avg_5min > umbrales["load_avg_5min"]:
            alerts.append(Alert(
                level=AlertLevel.WARNING,
                source="Load Average",
                message=f"Load average elevado (5min): {metrics.load_avg_5min:.2f}",
                value=metrics.load_avg_5min,
                threshold=umbrales["load_avg_5min"],
                timestamp=metrics.timestamp
            ))
        
        # Verificar número de procesos
        if metrics.processes > umbrales["process_limit"]:
            alerts.append(Alert(
                level=AlertLevel.WARNING,
                source="Processes",
                message=f"Número alto de procesos: {metrics.processes}",
                value=float(metrics.processes),
                threshold=float(umbrales["process_limit"]),
                timestamp=metrics.timestamp
            ))
        
        return alerts
    
    def handle_alerts(self, alerts: List[Alert]):
        """Manejar alertas detectadas"""
        if not alerts:
            return
        
        # Verificar límite diario de alertas
        if self.alerts_today >= self.config["alertas"]["alertas_por_dia"]:
            self.logger.warning("Límite diario de alertas alcanzado")
            return
        
        for alert in alerts:
            # Guardar alerta en base de datos
            self._save_alert_to_db(alert)
            
            # Incrementar contador
            self.alerts_today += 1
            
            # Enviar notificación KDE
            if self.config["alertas"]["notificar_kde"]:
                self._send_kde_notification(alert)
            
            # Enviar email si está configurado
            if self.config["alertas"]["notificar_email"]:
                self._send_email_alert(alert)
            
            # Ejecutar acciones automáticas si es crítica
            if alert.level == AlertLevel.CRITICAL:
                self._execute_automatic_actions(alert)
    
    def _save_alert_to_db(self, alert: Alert):
        """Guardar alerta en base de datos"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO alerts (timestamp, level, source, message, value, threshold)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                alert.timestamp,
                alert.level.value,
                alert.source,
                alert.message,
                alert.value,
                alert.threshold
            ))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            self.logger.error(f"Error guardando alerta en DB: {e}")
    
    def _send_kde_notification(self, alert: Alert):
        """Enviar notificación KDE"""
        try:
            import subprocess
            
            icon = "dialog-warning"
            if alert.level == AlertLevel.CRITICAL:
                icon = "dialog-error"
            elif alert.level == AlertLevel.INFO:
                icon = "dialog-information"
            
            title = f"⚠️ Alerta del Sistema: {alert.source}"
            message = f"{alert.message}\nValor: {alert.value} | Umbral: {alert.threshold}"
            
            subprocess.run([
                "kdialog", "--title", title,
                "--icon", icon,
                "--passivepopup", message, "10"
            ])
            
        except Exception as e:
            self.logger.error(f"Error enviando notificación KDE: {e}")
    
    def _send_email_alert(self, alert: Alert):
        """Enviar alerta por email"""
        try:
            config = self.config["alertas"]
            
            if not all([config["smtp_username"], config["smtp_password"], config["email_to"]]):
                return
            
            subject = f"[{alert.level.value.upper()}] Alerta del Sistema: {alert.source}"
            body = f"""
            Alerta del Sistema Monitor
            
            Nivel: {alert.level.value.upper()}
            Fuente: {alert.source}
            Mensaje: {alert.message}
            Valor Actual: {alert.value}
            Umbral: {alert.threshold}
            Timestamp: {alert.timestamp}
            
            Sistema: {os.uname().nodename}
            """
            
            msg = f"Subject: {subject}\n\n{body}"
            
            with smtplib.SMTP(config["smtp_server"], config["smtp_port"]) as server:
                server.starttls()
                server.login(config["smtp_username"], config["smtp_password"])
                server.sendmail(config["email_from"], config["email_to"], msg)
                
        except Exception as e:
            self.logger.error(f"Error enviando email: {e}")
    
    def _execute_automatic_actions(self, alert: Alert):
        """Ejecutar acciones automáticas para alertas críticas"""
        config = self.config["acciones"]
        
        # Limpiar cache si está habilitado
        if config["limpiar_cache_alerta"]:
            self._clean_system_cache()
        
        # Reiniciar servicios si está habilitado
        if config["auto_reiniciar_servicios"]:
            for servicio in config["servicios_a_reiniciar"]:
                self._restart_service(servicio)
    
    def _clean_system_cache(self):
        """Limpiar caché del sistema"""
        try:
            # Limpiar caché de página
            with open("/proc/sys/vm/drop_caches", "w") as f:
                f.write("3\n")
            self.logger.info("Cache del sistema limpiado automáticamente")
        except Exception as e:
            self.logger.error(f"Error limpiando cache: {e}")
    
    def _restart_service(self, service_name: str):
        """Reiniciar servicio del sistema"""
        try:
            import subprocess
            subprocess.run(["sudo", "systemctl", "restart", service_name], check=True)
            self.logger.info(f"Servicio {service_name} reiniciado automáticamente")
        except Exception as e:
            self.logger.error(f"Error reiniciando servicio {service_name}: {e}")
    
    def generate_report(self, hours: int = 24) -> Dict[str, Any]:
        """Generar reporte de las últimas horas"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Calcular timestamp límite
            limit_time = (datetime.now() - timedelta(hours=hours)).isoformat()
            
            # Obtener métricas del período
            cursor.execute('''
                SELECT 
                    AVG(cpu_percent) as avg_cpu,
                    MAX(cpu_percent) as max_cpu,
                    AVG(memory_percent) as avg_memory,
                    MAX(memory_percent) as max_memory,
                    AVG(disk_percent) as avg_disk,
                    COUNT(*) as samples
                FROM metrics 
                WHERE timestamp > ?
            ''', (limit_time,))
            
            stats = cursor.fetchone()
            
            # Obtener alertas del período
            cursor.execute('''
                SELECT level, COUNT(*) as count
                FROM alerts 
                WHERE timestamp > ?
                GROUP BY level
            ''', (limit_time,))
            
            alert_counts = cursor.fetchall()
            
            conn.close()
            
            return {
                "period_hours": hours,
                "metrics": {
                    "avg_cpu": stats[0] if stats[0] else 0,
                    "max_cpu": stats[1] if stats[1] else 0,
                    "avg_memory": stats[2] if stats[2] else 0,
                    "max_memory": stats[3] if stats[3] else 0,
                    "avg_disk": stats[4] if stats[4] else 0,
                    "samples": stats[5] if stats[5] else 0
                },
                "alerts": {level: count for level, count in alert_counts},
                "generated_at": datetime.now().isoformat()
            }
            
        except Exception as e:
            self.logger.error(f"Error generando reporte: {e}")
            return {}
    
    def run_monitoring_cycle(self):
        """Ejecutar un ciclo completo de monitoreo"""
        self.logger.info("Iniciando ciclo de monitoreo...")
        
        # Obtener métricas
        metrics = self.get_system_metrics()
        
        # Verificar alertas
        alerts = self.check_alerts(metrics)
        
        # Manejar alertas
        if alerts:
            self.handle_alerts(alerts)
        
        # Log de estado
        self.logger.info(
            f"Estado - CPU: {metrics.cpu_percent:.1f}%, "
            f"Mem: {metrics.memory_percent:.1f}%, "
            f"Disk: {metrics.disk_percent:.1f}%"
        )
        
        return metrics, alerts
    
    def start_continuous_monitoring(self):
        """Iniciar monitoreo continuo"""
        intervalo = self.config["monitoreo"]["intervalo_segundos"]
        
        self.logger.info(f"Iniciando monitoreo continuo (intervalo: {intervalo}s)")
        
        try:
            while True:
                self.run_monitoring_cycle()
                time.sleep(intervalo)
                
        except KeyboardInterrupt:
            self.logger.info("Monitoreo detenido por el usuario")
        except Exception as e:
            self.logger.error(f"Error en monitoreo continuo: {e}")

def main():
    """Función principal"""
    print("🔍 Monitor de Sistema y Alertas - KDE Plasma")
    print("=" * 50)
    
    monitor = SystemMonitor()
    
    # Verificar dependencias
    try:
        import psutil
    except ImportError:
        print("❌ Error: psutil no está instalado")
        print("   Instala con: pip install psutil")
        return 1
    
    # Opciones de ejecución
    import argparse
    parser = argparse.ArgumentParser(description="Monitor del Sistema")
    parser.add_argument("--daemon", action="store_true", help="Ejecutar como daemon continuo")
    parser.add_argument("--single", action="store_true", help="Ejecutar un solo ciclo")
    parser.add_argument("--report", type=int, default=24, help="Generar reporte de N horas")
    parser.add_argument("--verbose", action="store_true", help="Modo verbose")
    
    args = parser.parse_args()
    
    if args.daemon:
        print("👁️  Iniciando monitoreo continuo...")
        print("   Presiona Ctrl+C para detener")
        print()
        monitor.start_continuous_monitoring()
        
    elif args.report:
        print(f"📊 Generando reporte de las últimas {args.report} horas...")
        report = monitor.generate_report(args.report)
        
        if report:
            print(f"\nReporte del Sistema:")
            print(f"  Período: {report['period_hours']} horas")
            print(f"  Muestras: {report['metrics']['samples']}")
            print(f"\nMétricas Promedio:")
            print(f"  CPU: {report['metrics']['avg_cpu']:.1f}%")
            print(f"  Memoria: {report['metrics']['avg_memory']:.1f}%")
            print(f"  Disco: {report['metrics']['avg_disk']:.1f}%")
            print(f"\nMétricas Máximas:")
            print(f"  CPU: {report['metrics']['max_cpu']:.1f}%")
            print(f"  Memoria: {report['metrics']['max_memory']:.1f}%")
            
            if report['alerts']:
                print(f"\nAlertas en el período:")
                for level, count in report['alerts'].items():
                    print(f"  {level}: {count}")
        else:
            print("❌ No se pudo generar el reporte")
            
    else:
        # Modo single por defecto
        print("🔄 Ejecutando ciclo de monitoreo...")
        metrics, alerts = monitor.run_monitoring_cycle()
        
        print(f"\n📈 Métricas Actuales:")
        print(f"  CPU: {metrics.cpu_percent:.1f}%")
        print(f"  Memoria: {metrics.memory_percent:.1f}% ({metrics.memory_used_gb:.1f}/{metrics.memory_total_gb:.1f} GB)")
        print(f"  Disco: {metrics.disk_percent:.1f}% ({metrics.disk_used_gb:.1f}/{metrics.disk_total_gb:.1f} GB)")
        print(f"  Procesos: {metrics.processes}")
        print(f"  Uptime: {metrics.uptime_hours:.1f} horas")
        
        if alerts:
            print(f"\n⚠️  Alertas Detectadas:")
            for alert in alerts:
                print(f"  [{alert.level.value}] {alert.source}: {alert.message}")
        else:
            print(f"\n✅ Sistema en estado normal")
    
    return 0

if __name__ == "__main__":
    exit(main())