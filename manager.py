import os
import shutil
import signal
import psutil
import subprocess
import time
from models import Environment
from executor import run_command
from db import query, execute

def _systemd_props(unit_name: str) -> dict:
    """
    Lê propriedades relevantes do systemd para uma unit (service/scope).
    Retorna dict com chaves de interesse; se não existir, LoadState=not-found.
    """
    keys = [
        "LoadState",
        "ActiveState",
        "SubState",
        "Result",
        "ExecMainStatus",
        "MainPID",
    ]
    args = ["systemctl", "show", unit_name]
    for k in keys:
        args.extend(["-p", k])
    try:
        out = subprocess.check_output(args, stderr=subprocess.DEVNULL).decode().splitlines()
    except subprocess.CalledProcessError:
        return {"LoadState": "not-found"}
    props = {}
    for line in out:
        if not line or "=" not in line:
            continue
        k, v = line.split("=", 1)
        if k in keys:
            props[k] = v if v != "" else None
    if "ActiveState" not in props:
        props["LoadState"] = "not-found"
    return props

def _map_systemd_to_status(props: dict) -> str:
    """
    Converte propriedades do systemd para estados do app.

    Regras principais:
      - ActiveState=active/reloading           -> running
      - ActiveState=activating                 -> starting
      - ActiveState=deactivating               -> finishing
      - ActiveState=failed                     -> error
      - ActiveState=inactive:
            Result=success                     -> finished
            Result=exit-code (ou != success)   -> error
            SubStates típicos de parada        -> finished
      - LoadState=not-found                    -> finished (unit coletada após término)
      - ExecMainStatus != 0                    -> error (fallback)
      - Caso não classifique, usa SubState=running -> running, senão unknown
    """
    load = props.get("LoadState")
    active = props.get("ActiveState")
    sub = props.get("SubState")
    result = (props.get("Result") or "").strip().lower()
    exec_status = props.get("ExecMainStatus")

    if load == "not-found":
        return "finished"

    if active in ("active", "reloading"):
        return "running"

    if active == "activating":
        return "starting"

    if active == "deactivating":
        return "finishing"

    if active == "failed":
        return "error"

    if active == "inactive":
        # Se o systemd marcou sucesso explícito
        if result == "success":
            return "finished"
        # Muitas falhas caem como "exit-code"
        if result == "exit-code":
            return "error"
        # ExecMainStatus não-nulo e != 0 indica erro do processo principal
        try:
            if exec_status is not None and str(exec_status).strip() != "" and int(exec_status) != 0:
                return "error"
        except ValueError:
            pass
        # SubStates de parada "normais" -> finished
        if sub in ("dead", "exited", "stop-sigterm", "stop-sigkill", "stop"):
            return "finished"
        # Default conservador para inactive sem sucesso explícito: finished
        return "finished"

    # Fallbacks
    if sub == "running":
        return "running"

    # Se há ExecMainStatus != 0 (mesmo sem active=failed), trate como erro
    try:
        if exec_status is not None and str(exec_status).strip() != "" and int(exec_status) != 0:
            return "error"
    except ValueError:
        pass

    return "unknown"

def _read_proc_io(pid: int):
    """Retorna (read_bytes, write_bytes) do /proc/<pid>/io se possível."""
    try:
        with open(f"/proc/{pid}/io", "r") as f:
            data = f.read().splitlines()
        vals = {}
        for line in data:
            if ":" in line:
                k, v = line.split(":", 1)
                vals[k.strip()] = int(v.strip())
        r = vals.get("read_bytes") or vals.get("rchar") or 0
        w = vals.get("write_bytes") or vals.get("wchar") or 0
        return int(r), int(w)
    except Exception:
        return 0, 0

class EnvironmentManager:
    def __init__(self):
        self.environments = {}

    def get_available_resources(self):
        cpu_count = psutil.cpu_count(logical=False) or psutil.cpu_count()
        mem = psutil.virtual_memory()
        available_memory_mb = int(mem.available / (1024 * 1024))
        return {'cpu_available': cpu_count, 'memory_available': available_memory_mb}

    # --- Persistência: helpers ---
    def _db_upsert_env(self, env: Environment):
        execute(
            """
            INSERT INTO environments (namespace, command, cpu, memory, io, unit_name, last_status, last_pid, process_name)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, COALESCE(%s,''))
            ON DUPLICATE KEY UPDATE
              command=VALUES(command),
              cpu=VALUES(cpu),
              memory=VALUES(memory),
              io=VALUES(io),
              unit_name=VALUES(unit_name),
              last_status=VALUES(last_status),
              last_pid=VALUES(last_pid),
              process_name=VALUES(process_name)
            """,
            (env.namespace, env.command, env.cpu, env.memory, env.io, env.unit_name, env.status, env.main_pid, None)
        )

    def _db_insert_metric(self, namespace: str, status: str, pid: int, cpu_pct: float, rss_mb: int, io_read: int, io_write: int):
        execute(
            """
            INSERT INTO env_metrics (namespace, status, cpu_pct, rss_mb, io_read, io_write, pid)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (namespace, status, cpu_pct, rss_mb, io_read, io_write, pid)
        )
        execute(
            """
            UPDATE environments
               SET last_status=%s, last_pid=%s
             WHERE namespace=%s
            """,
            (status, pid or 0, namespace)
        )

    # --- CRUD lógico ---
    def create_environment(self, data):
        resources = self.get_available_resources()
        requested_cpu = float(data.get('cpu', 1))
        requested_memory = int(data.get('memory', 128))

        if requested_cpu > resources['cpu_available']:
            return {'error': f'CPU solicitada ({requested_cpu}) excede o disponível ({resources["cpu_available"]})'}

        if requested_memory > resources['memory_available']:
            return {'error': f'Memória solicitada ({requested_memory}MB) excede o disponível ({resources["memory_available"]}MB)'}

        env = Environment(
            namespace=data['namespace'],
            cpu=requested_cpu,
            memory=requested_memory,
            io=int(data.get('io', 1)),
            command=data.get('command', '')
        )
        self.environments[env.namespace] = env
        env.status = 'created'
        self._db_upsert_env(env)
        return vars(env)

    def execute_program(self, data):
        ns = data['namespace']
        env = self.environments.get(ns)
        if not env:
            rows = query("SELECT * FROM environments WHERE namespace=%s", (ns,))
            if not rows:
                return {'error': 'Namespace não encontrado'}
            row = rows[0]
            env = Environment(ns, row['cpu'], row['memory'], row['io'], row['command'])
            env.unit_name = row.get('unit_name')
            env.main_pid = row.get('last_pid') or None
            self.environments[ns] = env

        env.status = 'running'
        unit_name, main_pid, path = run_command(ns, env.command, env.cpu, env.memory)
        env.unit_name = unit_name
        env.main_pid = main_pid
        self._db_upsert_env(env)
        return {'message': 'Execução iniciada', 'output_path': path, 'unit': unit_name, 'pid': main_pid}

    def _sample_metrics(self, env: Environment, props: dict):
        pid = env.main_pid
        cpu_pct = 0.0
        rss_mb = 0
        io_r = 0
        io_w = 0
        pname = ""

        if pid and pid > 0:
            try:
                p = psutil.Process(pid)
                pname = p.name()
                cpu_pct = p.cpu_percent(interval=0.05)
                rss_mb = int((p.memory_info().rss or 0) / (1024 * 1024))
                io_r, io_w = _read_proc_io(pid)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        status = _map_systemd_to_status(props)
        env.status = status
        if pname:
            execute("UPDATE environments SET process_name=%s WHERE namespace=%s", (pname, env.namespace))
        self._db_insert_metric(env.namespace, status, pid or 0, float(cpu_pct), int(rss_mb), int(io_r), int(io_w))

        return {
            'status': status,
            'cpu_pct': cpu_pct,
            'rss_mb': rss_mb,
            'io_read': io_r,
            'io_write': io_w,
            'pid': pid,
            'process_name': pname or ""
        }

    def get_status(self, namespace):
        env = self.environments.get(namespace)
        if not env:
            rows = query("SELECT * FROM environments WHERE namespace=%s", (namespace,))
            if not rows:
                return {'error': 'Namespace não encontrado'}
            row = rows[0]
            env = Environment(namespace, row['cpu'], row['memory'], row['io'], row['command'])
            env.unit_name = row.get('unit_name')
            env.main_pid = row.get('last_pid') or None
            self.environments[namespace] = env

        status = env.status or "unknown"
        if getattr(env, "unit_name", None):
            props = _systemd_props(env.unit_name)
            if (not getattr(env, "main_pid", None)) or env.main_pid == 0:
                mpid = props.get("MainPID")
                try:
                    if mpid and mpid.strip() and mpid.strip() != "0":
                        env.main_pid = int(mpid.strip())
                except Exception:
                    pass
            metrics = self._sample_metrics(env, props)
            status = metrics['status']

        # retorno minimalista conforme solicitado
        return {
            'pid': env.main_pid,
            'memory_requested': env.memory,
            'cpu_requested': env.cpu,
            'status': status,
            'command': env.command,
        }

    def list_environments(self):
        rows = query("""
            SELECT e.namespace, e.command, e.cpu, e.memory, e.io, e.unit_name,
                   e.created_at, e.last_status, e.last_pid, e.process_name,
                   m.cpu_pct, m.rss_mb, m.io_read, m.io_write, m.ts
              FROM environments e
              LEFT JOIN (
                 SELECT t1.* FROM env_metrics t1
                 JOIN (
                   SELECT namespace, MAX(id) AS max_id
                     FROM env_metrics GROUP BY namespace
                 ) t2 ON t1.namespace = t2.namespace AND t1.id = t2.max_id
              ) m ON e.namespace = m.namespace
             ORDER BY e.created_at DESC
        """)
        for r in rows:
            r['cpu_pct'] = r.get('cpu_pct') or 0.0
            r['rss_mb'] = r.get('rss_mb') or 0
            r['io_read'] = r.get('io_read') or 0
            r['io_write'] = r.get('io_write') or 0
            r['process_name'] = r.get('process_name') or ""
        return rows

    def get_output_path(self, namespace):
        return os.path.join("environments", namespace, "output.log")

    def terminate_environment(self, namespace):
        env = self.environments.get(namespace)
        if not env:
            rows = query("SELECT * FROM environments WHERE namespace=%s", (namespace,))
            if rows:
                row = rows[0]
                env = Environment(namespace, row['cpu'], row['memory'], row['io'], row['command'])
                env.unit_name = row.get('unit_name')
                env.main_pid = row.get('last_pid') or None

        if not env:
            return {'error': 'Namespace não encontrado'}

        try:
            if getattr(env, "unit_name", None):
                subprocess.run(["sudo", "systemctl", "kill", env.unit_name],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                time.sleep(0.5)
                subprocess.run(["sudo", "systemctl", "kill", "--signal=SIGKILL", env.unit_name],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                subprocess.run(["sudo", "systemctl", "stop", env.unit_name],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                subprocess.run(["sudo", "systemctl", "reset-failed", env.unit_name],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            if getattr(env, "main_pid", None):
                try:
                    os.kill(env.main_pid, signal.SIGTERM)
                except (ProcessLookupError, PermissionError):
                    pass

            env.status = 'terminated'
            self._db_insert_metric(env.namespace, env.status, env.main_pid or 0, 0.0, 0, 0, 0)
            execute("UPDATE environments SET last_status=%s WHERE namespace=%s", ('terminated', env.namespace))

        except Exception as e:
            return {'error': f'Erro ao encerrar processo: {str(e)}'}

        self.environments.pop(namespace, None)

        env_path = os.path.join("environments", namespace)
        try:
            if os.path.exists(env_path):
                shutil.rmtree(env_path)
        except Exception as e:
            return {'error': f'Erro ao remover pasta: {str(e)}'}

        return {'message': f'Ambiente {namespace} encerrado e removido com sucesso'}

# Instância global usada no app.py
manager = EnvironmentManager()
