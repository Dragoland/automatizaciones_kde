#!/usr/bin/env python3
"""
PROGRAMADOR DE TAREAS CON INTERFAZ PARA KDE PLASMA
Versión mejorada con base de datos, interfaz web y múltiples triggers
"""
import os
import sys
import json
import sqlite3
import subprocess
import threading
import schedule
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from enum import Enum
import logging
import hashlib
import pickle

class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class TaskType(Enum):
    COMMAND = "command"
    SCRIPT = "script"
    NOTIFICATION = "notification"
    REMINDER = "reminder"

class TriggerType(Enum):
    TIME = "time"
    INTERVAL = "interval"
    FILE_CHANGE = "file_change"
    SYSTEM_EVENT = "system_event"

@dataclass
class Task:
    """Estructura de tarea programada"""
    id: Optional[int] = None
    name: str = ""
    description: str = ""
    task_type: TaskType = TaskType.COMMAND
    command: str = ""
    arguments: List[str] = None
    working_dir: str = ""
    trigger_type: TriggerType = TriggerType.TIME
    trigger_data: Dict[str, Any] = None
    status: TaskStatus = TaskStatus.PENDING
    created_at: str = ""
    scheduled_for: str = ""
    executed_at: str = ""
    result_code: int = 0
    output: str = ""
    enabled: bool = True
    notify_on_completion: bool = True
    max_retries: int = 3
    retry_count: int = 0
    
    def __post_init__(self):
        if self.arguments is None:
            self.arguments = []
        if self.trigger_data is None:
            self.trigger_data = {}

class TaskScheduler:
    def __init__(self, config_file: str = None):
        """Inicializar programador de tareas"""
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
        self.db_path = self.db_dir / "task_scheduler.db"
        self._init_database()
        
        # Scheduler
        self.scheduler = schedule.Scheduler()
        self.running = False
        self.scheduler_thread = None
        
        # Cache de hashes para detección de cambios
        self.file_hashes = {}
        
    def _setup_logging(self):
        """Configurar sistema de logging"""
        log_file = self.log_dir / f"task_scheduler_{datetime.now().strftime('%Y-%m')}.log"
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file, encoding='utf-8'),
                logging.StreamHandler(sys.stdout)
            ]
        )
        self.logger = logging.getLogger('TaskScheduler')
        
    def _load_config(self, config_file: Optional[str]) -> Dict:
        """Cargar configuración desde archivo JSON"""
        if config_file is None:
            config_file = self.config_dir / "task_scheduler.json"
        
        config_path = Path(config_file)
        
        # Configuración por defecto
        config_default = {
            "scheduler": {
                "check_interval_seconds": 60,
                "max_concurrent_tasks": 3,
                "cleanup_completed_days": 30,
                "enable_web_interface": false,
                "web_port": 8080
            },
            "notifications": {
                "notify_kde": true,
                "notify_email": false,
                "email_from": "scheduler@dominio.com",
                "email_to": "user@dominio.com",
                "notification_sound": "/usr/share/sounds/freedesktop/stereo/complete.oga"
            },
            "security": {
                "allowed_commands": [
                    "echo", "notify-send", "kdialog",
                    "python", "bash", "sh"
                ],
                "blocked_commands": [
                    "rm -rf /", "dd if=/dev/random",
                    "mkfs", "shutdown", "reboot"
                ],
                "require_confirmation": true
            },
            "backup": {
                "backup_before_run": false,
                "backup_dir": "~/.local/backup_tasks",
                "keep_backups": 7
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
            
            # Tabla de tareas
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    description TEXT,
                    task_type TEXT NOT NULL,
                    command TEXT NOT NULL,
                    arguments TEXT,
                    working_dir TEXT,
                    trigger_type TEXT NOT NULL,
                    trigger_data TEXT,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    scheduled_for TEXT,
                    executed_at TEXT,
                    result_code INTEGER,
                    output TEXT,
                    enabled INTEGER DEFAULT 1,
                    notify_on_completion INTEGER DEFAULT 1,
                    max_retries INTEGER DEFAULT 3,
                    retry_count INTEGER DEFAULT 0
                )
            ''')
            
            # Tabla de logs de ejecución
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS execution_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id INTEGER NOT NULL,
                    execution_time TEXT NOT NULL,
                    duration_seconds REAL,
                    result_code INTEGER,
                    output TEXT,
                    FOREIGN KEY (task_id) REFERENCES tasks (id)
                )
            ''')
            
            # Tabla de dependencias
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS task_dependencies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id INTEGER NOT NULL,
                    depends_on_id INTEGER NOT NULL,
                    FOREIGN KEY (task_id) REFERENCES tasks (id),
                    FOREIGN KEY (depends_on_id) REFERENCES tasks (id)
                )
            ''')
            
            # Índices
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_tasks_scheduled ON tasks(scheduled_for)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_logs_task_id ON execution_logs(task_id)')
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            self.logger.error(f"Error inicializando base de datos: {e}")
    
    def _save_task_to_db(self, task: Task) -> int:
        """Guardar tarea en base de datos"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            if task.id is None:
                # Nueva tarea
                cursor.execute('''
                    INSERT INTO tasks (
                        name, description, task_type, command, arguments,
                        working_dir, trigger_type, trigger_data, status,
                        created_at, scheduled_for, enabled, notify_on_completion,
                        max_retries, retry_count
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    task.name,
                    task.description,
                    task.task_type.value,
                    task.command,
                    json.dumps(task.arguments),
                    task.working_dir,
                    task.trigger_type.value,
                    json.dumps(task.trigger_data),
                    task.status.value,
                    task.created_at or datetime.now().isoformat(),
                    task.scheduled_for,
                    1 if task.enabled else 0,
                    1 if task.notify_on_completion else 0,
                    task.max_retries,
                    task.retry_count
                ))
                task.id = cursor.lastrowid
            else:
                # Actualizar tarea existente
                cursor.execute('''
                    UPDATE tasks SET
                        name = ?, description = ?, task_type = ?, command = ?,
                        arguments = ?, working_dir = ?, trigger_type = ?,
                        trigger_data = ?, status = ?, scheduled_for = ?,
                        enabled = ?, notify_on_completion = ?, max_retries = ?,
                        retry_count = ?
                    WHERE id = ?
                ''', (
                    task.name,
                    task.description,
                    task.task_type.value,
                    task.command,
                    json.dumps(task.arguments),
                    task.working_dir,
                    task.trigger_type.value,
                    json.dumps(task.trigger_data),
                    task.status.value,
                    task.scheduled_for,
                    1 if task.enabled else 0,
                    1 if task.notify_on_completion else 0,
                    task.max_retries,
                    task.retry_count,
                    task.id
                ))
            
            conn.commit()
            conn.close()
            return task.id
            
        except Exception as e:
            self.logger.error(f"Error guardando tarea en DB: {e}")
            return -1
    
    def _load_task_from_db(self, task_id: int) -> Optional[Task]:
        """Cargar tarea desde base de datos"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('SELECT * FROM tasks WHERE id = ?', (task_id,))
            row = cursor.fetchone()
            conn.close()
            
            if not row:
                return None
            
            return Task(
                id=row[0],
                name=row[1],
                description=row[2],
                task_type=TaskType(row[3]),
                command=row[4],
                arguments=json.loads(row[5] if row[5] else '[]'),
                working_dir=row[6],
                trigger_type=TriggerType(row[7]),
                trigger_data=json.loads(row[8] if row[8] else '{}'),
                status=TaskStatus(row[9]),
                created_at=row[10],
                scheduled_for=row[11],
                executed_at=row[12] if row[12] else "",
                result_code=row[13] if row[13] else 0,
                output=row[14] if row[14] else "",
                enabled=bool(row[15]),
                notify_on_completion=bool(row[16]),
                max_retries=row[17] if row[17] else 3,
                retry_count=row[18] if row[18] else 0
            )
            
        except Exception as e:
            self.logger.error(f"Error cargando tarea desde DB: {e}")
            return None
    
    def _log_execution(self, task_id: int, execution_time: str,
                      duration: float, result_code: int, output: str):
        """Registrar ejecución en base de datos"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO execution_logs 
                (task_id, execution_time, duration_seconds, result_code, output)
                VALUES (?, ?, ?, ?, ?)
            ''', (task_id, execution_time, duration, result_code, output))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            self.logger.error(f"Error registrando ejecución: {e}")
    
    def _check_command_security(self, command: str) -> bool:
        """Verificar seguridad del comando"""
        # Comandos permitidos
        allowed = self.config["security"]["allowed_commands"]
        blocked = self.config["security"]["blocked_commands"]
        
        # Verificar comandos bloqueados
        for blocked_cmd in blocked:
            if blocked_cmd in command:
                self.logger.warning(f"Comando bloqueado detectado: {blocked_cmd}")
                return False
        
        # Verificar si el comando está en la lista de permitidos
        # (solo para comandos simples)
        cmd_base = command.split()[0] if ' ' in command else command
        if allowed and cmd_base not in allowed:
            self.logger.warning(f"Comando no permitido: {cmd_base}")
            return False
        
        return True
    
    def _execute_task(self, task: Task) -> bool:
        """Ejecutar una tarea"""
        if not task.enabled:
            self.logger.info(f"Tarea deshabilitada: {task.name}")
            return False
        
        # Verificar seguridad
        if not self._check_command_security(task.command):
            self.logger.error(f"Tarea bloqueada por seguridad: {task.name}")
            task.status = TaskStatus.FAILED
            task.output = "Comando bloqueado por seguridad"
            self._save_task_to_db(task)
            return False
        
        self.logger.info(f"Ejecutando tarea: {task.name}")
        
        # Actualizar estado
        task.status = TaskStatus.RUNNING
        self._save_task_to_db(task)
        
        start_time = time.time()
        success = False
        
        try:
            # Preparar entorno de trabajo
            working_dir = task.working_dir or str(self.home)
            
            # Preparar comando completo
            if task.arguments:
                full_cmd = [task.command] + task.arguments
            else:
                full_cmd = task.command
            
            # Ejecutar según tipo de tarea
            if task.task_type == TaskType.COMMAND:
                if isinstance(full_cmd, str):
                    # Comando como string
                    result = subprocess.run(
                        full_cmd,
                        shell=True,
                        cwd=working_dir,
                        capture_output=True,
                        text=True,
                        timeout=300  # 5 minutos timeout
                    )
                else:
                    # Comando como lista
                    result = subprocess.run(
                        full_cmd,
                        cwd=working_dir,
                        capture_output=True,
                        text=True,
                        timeout=300
                    )
                
                task.result_code = result.returncode
                task.output = result.stdout + result.stderr
                success = result.returncode == 0
                
            elif task.task_type == TaskType.SCRIPT:
                # Ejecutar script
                script_path = task.command
                if not os.path.isabs(script_path):
                    script_path = os.path.join(working_dir, script_path)
                
                result = subprocess.run(
                    [sys.executable, script_path] + task.arguments,
                    cwd=working_dir,
                    capture_output=True,
                    text=True,
                    timeout=300
                )
                
                task.result_code = result.returncode
                task.output = result.stdout + result.stderr
                success = result.returncode == 0
                
            elif task.task_type == TaskType.NOTIFICATION:
                # Enviar notificación
                if task.command == "kdialog":
                    subprocess.run(["kdialog", "--title", task.name] + task.arguments)
                elif task.command == "notify-send":
                    subprocess.run(["notify-send", task.name] + task.arguments)
                
                task.result_code = 0
                task.output = "Notificación enviada"
                success = True
                
            elif task.task_type == TaskType.REMINDER:
                # Recordatorio simple
                message = task.command
                if task.arguments:
                    message += " " + " ".join(task.arguments)
                
                self._send_notification("Recordatorio", message)
                task.result_code = 0
                task.output = "Recordatorio mostrado"
                success = True
            
            # Calcular duración
            duration = time.time() - start_time
            
            # Actualizar estado
            if success:
                task.status = TaskStatus.COMPLETED
                self.logger.info(f"Tarea completada: {task.name} ({duration:.2f}s)")
            else:
                task.status = TaskStatus.FAILED
                self.logger.error(f"Tarea fallida: {task.name} ({duration:.2f}s)")
            
            task.executed_at = datetime.now().isoformat()
            self._save_task_to_db(task)
            
            # Registrar ejecución
            self._log_execution(
                task.id,
                task.executed_at,
                duration,
                task.result_code,
                task.output[:1000]  # Limitar tamaño
            )
            
            # Enviar notificación si está habilitado
            if success and task.notify_on_completion:
                self._send_notification(
                    "✅ Tarea Completada",
                    f"{task.name}\nDuración: {duration:.1f}s"
                )
            elif not success:
                self._send_notification(
                    "❌ Tarea Fallida",
                    f"{task.name}\nError: {task.result_code}"
                )
            
            return success
            
        except subprocess.TimeoutExpired:
            self.logger.error(f"Tarea timeout: {task.name}")
            task.status = TaskStatus.FAILED
            task.output = "Timeout (5 minutos)"
            task.executed_at = datetime.now().isoformat()
            self._save_task_to_db(task)
            
            self._send_notification(
                "⏰ Tarea Timeout",
                f"{task.name}\nExcedió el tiempo límite"
            )
            return False
            
        except Exception as e:
            self.logger.error(f"Error ejecutando tarea {task.name}: {e}")
            task.status = TaskStatus.FAILED
            task.output = str(e)
            task.executed_at = datetime.now().isoformat()
            self._save_task_to_db(task)
            return False
    
    def _send_notification(self, title: str, message: str):
        """Enviar notificación KDE"""
        if self.config["notifications"]["notify_kde"]:
            try:
                subprocess.run([
                    "kdialog", "--title", title,
                    "--passivepopup", message, "10"
                ])
            except Exception:
                pass  # Silenciar error si kdialog no está disponible
    
    def _schedule_time_trigger(self, task: Task):
        """Programar tarea con trigger de tiempo"""
        try:
            trigger_data = task.trigger_data
            
            if "datetime" in trigger_data:
                # Fecha/hora específica
                scheduled_time = datetime.fromisoformat(trigger_data["datetime"])
                now = datetime.now()
                
                if scheduled_time > now:
                    # Calcular delay en segundos
                    delay = (scheduled_time - now).total_seconds()
                    
                    # Programar con schedule
                    def job():
                        self._execute_task(task)
                    
                    schedule.every(delay).seconds.do(job).tag(f"task_{task.id}")
                    
            elif "cron" in trigger_data:
                # Expresión cron
                cron_expr = trigger_data["cron"]
                # Implementar parsing de cron (simplificado)
                # Aquí se podría usar python-crontab o similar
                pass
            
        except Exception as e:
            self.logger.error(f"Error programando trigger de tiempo: {e}")
    
    def _schedule_interval_trigger(self, task: Task):
        """Programar tarea con trigger de intervalo"""
        try:
            trigger_data = task.trigger_data
            
            if "seconds" in trigger_data:
                seconds = trigger_data["seconds"]
                schedule.every(seconds).seconds.do(
                    lambda: self._execute_task(task)
                ).tag(f"task_{task.id}")
                
            elif "minutes" in trigger_data:
                minutes = trigger_data["minutes"]
                schedule.every(minutes).minutes.do(
                    lambda: self._execute_task(task)
                ).tag(f"task_{task.id}")
                
            elif "hours" in trigger_data:
                hours = trigger_data["hours"]
                schedule.every(hours).hours.do(
                    lambda: self._execute_task(task)
                ).tag(f"task_{task.id}")
                
            elif "days" in trigger_data:
                days = trigger_data["days"]
                schedule.every(days).days.do(
                    lambda: self._execute_task(task)
                ).tag(f"task_{task.id}")
                
        except Exception as e:
            self.logger.error(f"Error programando trigger de intervalo: {e}")
    
    def schedule_task(self, task: Task) -> bool:
        """Programar una tarea"""
        # Guardar tarea en base de datos
        task_id = self._save_task_to_db(task)
        if task_id == -1:
            return False
        
        task.id = task_id
        
        # Programar según tipo de trigger
        if task.trigger_type == TriggerType.TIME:
            self._schedule_time_trigger(task)
            
        elif task.trigger_type == TriggerType.INTERVAL:
            self._schedule_interval_trigger(task)
            
        elif task.trigger_type == TriggerType.FILE_CHANGE:
            # Implementar detección de cambios de archivo
            pass
            
        elif task.trigger_type == TriggerType.SYSTEM_EVENT:
            # Implementar triggers de eventos del sistema
            pass
        
        self.logger.info(f"Tarea programada: {task.name} (ID: {task.id})")
        return True
    
    def create_task_interactive(self):
        """Crear tarea interactivamente"""
        try:
            print("\n📝 Crear Nueva Tarea")
            print("=" * 40)
            
            # Obtener entrada del usuario
            name = input("Nombre de la tarea: ").strip()
            description = input("Descripción (opcional): ").strip()
            
            # Tipo de tarea
            print("\nTipo de tarea:")
            print("  1. Comando de shell")
            print("  2. Script Python/Bash")
            print("  3. Notificación")
            print("  4. Recordatorio")
            
            type_choice = input("Selecciona (1-4): ").strip()
            task_types = {
                "1": TaskType.COMMAND,
                "2": TaskType.SCRIPT,
                "3": TaskType.NOTIFICATION,
                "4": TaskType.REMINDER
            }
            task_type = task_types.get(type_choice, TaskType.COMMAND)
            
            # Comando/acción
            if task_type in [TaskType.COMMAND, TaskType.SCRIPT]:
                command = input("Comando o ruta del script: ").strip()
                args_input = input("Argumentos (separados por espacio): ").strip()
                arguments = args_input.split() if args_input else []
                working_dir = input("Directorio de trabajo (opcional): ").strip()
            elif task_type == TaskType.NOTIFICATION:
                command = "kdialog"
                message = input("Mensaje de notificación: ").strip()
                arguments = ["--msgbox", message]
                working_dir = ""
            else:  # REMINDER
                command = input("Texto del recordatorio: ").strip()
                arguments = []
                working_dir = ""
            
            # Tipo de trigger
            print("\n¿Cuándo ejecutar?")
            print("  1. En fecha/hora específica")
            print("  2. Cada X tiempo (intervalo)")
            print("  3. Ahora mismo")
            
            trigger_choice = input("Selecciona (1-3): ").strip()
            
            trigger_data = {}
            if trigger_choice == "1":
                trigger_type = TriggerType.TIME
                date_str = input("Fecha y hora (YYYY-MM-DD HH:MM): ").strip()
                trigger_data["datetime"] = date_str
                
            elif trigger_choice == "2":
                trigger_type = TriggerType.INTERVAL
                print("\nIntervalo:")
                print("  1. Segundos")
                print("  2. Minutos")
                print("  3. Horas")
                print("  4. Días")
                
                interval_choice = input("Selecciona (1-4): ").strip()
                value = input("Valor: ").strip()
                
                intervals = {
                    "1": "seconds",
                    "2": "minutes",
                    "3": "hours",
                    "4": "days"
                }
                trigger_data[intervals.get(interval_choice, "minutes")] = int(value)
                
            else:
                trigger_type = TriggerType.TIME
                trigger_data["datetime"] = datetime.now().isoformat()
            
            # Configuración adicional
            notify = input("\n¿Notificar al completar? (s/n): ").strip().lower() == 's'
            enabled = input("¿Habilitar tarea? (s/n): ").strip().lower() == 's'
            
            # Crear objeto Task
            task = Task(
                name=name,
                description=description,
                task_type=task_type,
                command=command,
                arguments=arguments,
                working_dir=working_dir,
                trigger_type=trigger_type,
                trigger_data=trigger_data,
                status=TaskStatus.PENDING,
                created_at=datetime.now().isoformat(),
                scheduled_for=trigger_data.get("datetime", ""),
                notify_on_completion=notify,
                enabled=enabled
            )
            
            # Programar tarea
            if self.schedule_task(task):
                print(f"\n✅ Tarea '{name}' programada exitosamente!")
                
                # Ejecutar inmediatamente si se solicitó
                if trigger_choice == "3":
                    print("Ejecutando tarea ahora...")
                    self._execute_task(task)
                    
                return True
            else:
                print("❌ Error programando la tarea")
                return False
                
        except KeyboardInterrupt:
            print("\n❌ Operación cancelada")
            return False
        except Exception as e:
            print(f"❌ Error: {e}")
            return False
    
    def list_tasks(self, filter_status: str = None):
        """Listar tareas programadas"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            query = "SELECT id, name, task_type, trigger_type, status, scheduled_for FROM tasks"
            params = []
            
            if filter_status:
                query += " WHERE status = ?"
                params.append(filter_status)
            
            query += " ORDER BY scheduled_for"
            
            cursor.execute(query, params)
            tasks = cursor.fetchall()
            conn.close()
            
            if not tasks:
                print("No hay tareas programadas.")
                return
            
            print("\n📋 Tareas Programadas")
            print("=" * 80)
            print(f"{'ID':<5} {'Nombre':<20} {'Tipo':<12} {'Trigger':<12} {'Estado':<12} {'Programada':<20}")
            print("-" * 80)
            
            for task in tasks:
                task_id, name, task_type, trigger_type, status, scheduled = task
                scheduled_str = scheduled[:19] if scheduled else "Inmediato"
                print(f"{task_id:<5} {name[:18]:<20} {task_type[:10]:<12} "
                      f"{trigger_type[:10]:<12} {status[:10]:<12} {scheduled_str:<20}")
            
            print()
            
        except Exception as e:
            self.logger.error(f"Error listando tareas: {e}")
    
    def run_scheduler(self):
        """Ejecutar el scheduler en segundo plano"""
        self.running = True
        
        def scheduler_loop():
            while self.running:
                try:
                    schedule.run_pending()
                except Exception as e:
                    self.logger.error(f"Error en scheduler loop: {e}")
                
                time.sleep(self.config["scheduler"]["check_interval_seconds"])
        
        self.scheduler_thread = threading.Thread(target=scheduler_loop, daemon=True)
        self.scheduler_thread.start()
        
        self.logger.info("Scheduler iniciado")
    
    def stop_scheduler(self):
        """Detener el scheduler"""
        self.running = False
        if self.scheduler_thread:
            self.scheduler_thread.join(timeout=5)
        
        self.logger.info("Scheduler detenido")
    
    def cleanup_old_tasks(self):
        """Limpiar tareas antiguas completadas"""
        try:
            days = self.config["scheduler"]["cleanup_completed_days"]
            cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Eliminar logs antiguos
            cursor.execute('''
                DELETE FROM execution_logs 
                WHERE execution_time < ?
            ''', (cutoff_date,))
            
            # Eliminar tareas completadas antiguas
            cursor.execute('''
                DELETE FROM tasks 
                WHERE status IN ('completed', 'failed', 'cancelled')
                AND executed_at < ?
            ''', (cutoff_date,))
            
            deleted = cursor.rowcount
            conn.commit()
            conn.close()
            
            if deleted > 0:
                self.logger.info(f"Limpiadas {deleted} tareas antiguas")
                
        except Exception as e:
            self.logger.error(f"Error limpiando tareas antiguas: {e}")

def main():
    """Función principal"""
    print("📅 Programador de Tareas - KDE Plasma")
    print("=" * 50)
    
    scheduler = TaskScheduler()
    
    # Verificar dependencias
    try:
        import schedule
    except ImportError:
        print("❌ Error: schedule no está instalado")
        print("   Instala con: pip install schedule")
        return 1
    
    # Opciones de ejecución
    import argparse
    parser = argparse.ArgumentParser(description="Programador de Tareas")
    parser.add_argument("--daemon", action="store_true", help="Ejecutar como daemon")
    parser.add_argument("--create", action="store_true", help="Crear nueva tarea")
    parser.add_argument("--list", action="store_true", help="Listar tareas")
    parser.add_argument("--run", type=int, help="Ejecutar tarea específica (ID)")
    parser.add_argument("--cleanup", action="store_true", help="Limpiar tareas antiguas")
    
    args = parser.parse_args()
    
    if args.daemon:
        print("🔄 Iniciando scheduler como daemon...")
        print("   Presiona Ctrl+C para detener")
        print()
        
        try:
            scheduler.run_scheduler()
            
            # Mantener el programa activo
            while True:
                time.sleep(1)
                
        except KeyboardInterrupt:
            print("\nDeteniendo scheduler...")
            scheduler.stop_scheduler()
            
    elif args.create:
        scheduler.create_task_interactive()
        
    elif args.list:
        filter_status = input("Filtrar por estado (dejar vacío para todos): ").strip()
        scheduler.list_tasks(filter_status if filter_status else None)
        
    elif args.run:
        task = scheduler._load_task_from_db(args.run)
        if task:
            print(f"Ejecutando tarea: {task.name}")
            scheduler._execute_task(task)
        else:
            print(f"❌ Tarea no encontrada: ID {args.run}")
            
    elif args.cleanup:
        print("🧹 Limpiando tareas antiguas...")
        scheduler.cleanup_old_tasks()
        print("✅ Limpieza completada")
        
    else:
        # Modo interactivo simple
        print("\nOpciones:")
        print("  1. Crear nueva tarea")
        print("  2. Listar tareas")
        print("  3. Ejecutar scheduler en background")
        print("  4. Limpiar tareas antiguas")
        print("  5. Salir")
        
        choice = input("\nSelecciona (1-5): ").strip()
        
        if choice == "1":
            scheduler.create_task_interactive()
        elif choice == "2":
            scheduler.list_tasks()
        elif choice == "3":
            # Ejecutar en segundo plano
            scheduler.run_scheduler()
            print("✅ Scheduler ejecutándose en background")
            print("   Para detener: pkill -f programador_tareas.py")
        elif choice == "4":
            scheduler.cleanup_old_tasks()
        else:
            print("👋 ¡Hasta luego!")
    
    return 0

if __name__ == "__main__":
    exit(main())