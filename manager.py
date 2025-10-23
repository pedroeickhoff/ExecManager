import os
import shutil
import signal
import psutil
import subprocess
import time
from models import Environment
from executor import run_command


def _systemd_props(unit_name: str) -> dict:
    """
    Lê propriedades relevantes do systemd para uma unit (service ou scope).
    Usa "Chave=Valor" para evitar desalinhamento.
    Se a unit já foi coletada (not-found) ou não existe, retorna {'LoadState': 'not-found'}.
    """
    keys = [
        "LoadState",       # loaded|not-found
        "ActiveState",     # active|inactive|failed|deactivating|activating|reloading
        "SubState",        # running|dead|exited|start|stop-...|...
        "Result",          # success|timeout|signal|core-dump (services)
        "ExecMainStatus",  # exit code numérico (services)
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
    Converte propriedades do systemd para nossos estados.
      - LoadState=not-found  -> finished (unit coletada após fim)
      - ActiveState=active/reloading -> running
      - ActiveState=activating       -> starting
      - ActiveState=deactivating     -> finishing
      - ActiveState=inactive         -> finished (usa Result/SubState quando existir)
      - ActiveState=failed           -> error
      - Fallback: se SubState=running -> running; senão unknown
    """
    load = props.get("LoadState")
    active = props.get("ActiveState")
    sub = props.get("SubState")
    result = props.get("Result")

    if load == "not-found":
        return "finished"

    if active in ("active", "reloading"):
        return "running"

    if active == "activating":
        return "starting"

    if active == "deactivating":
        return "finishing"

    if active == "inactive":
        if result == "success":
            return "finished"
        if sub in ("dead", "exited", "stop-sigterm", "stop-sigkill", "stop"):
            return "finished"
        return "finished"

    if active == "failed":
        return "error"

    if sub == "running":
        return "running"

    return "unknown"


class EnvironmentManager:
    def __init__(self):
        self.environments = {}

    # Recursos disponíveis
    def get_available_resources(self):
        cpu_count = psutil.cpu_count(logical=False) or psutil.cpu_count()
        mem = psutil.virtual_memory()
        available_memory_mb = int(mem.available / (1024 * 1024))
        return {
            'cpu_available': cpu_count,
            'memory_available': available_memory_mb
        }

    # Criar ambiente
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
        return vars(env)

    # Executar programa
    def execute_program(self, data):
        ns = data['namespace']
        env = self.environments.get(ns)
        if not env:
            return {'error': 'Namespace não encontrado'}

        env.status = 'running'
        unit_name, main_pid, path = run_command(ns, env.command, env.cpu, env.memory)
        env.unit_name = unit_name
        env.main_pid = main_pid

        return {
            'message': 'Execução iniciada',
            'output_path': path,
            'unit': unit_name,
            'pid': main_pid
        }

    # Consultar status
    def get_status(self, namespace):
        env = self.environments.get(namespace)
        if not env:
            return {'error': 'Namespace não encontrado'}

        if getattr(env, "unit_name", None):
            props = _systemd_props(env.unit_name)
            env.status = _map_systemd_to_status(props)

            # opcional: tentar atualizar main_pid se ainda não temos (service > scope)
            if not getattr(env, "main_pid", None) and props.get("ActiveState") in ("active", "reloading", "activating"):
                try:
                    mpid = subprocess.check_output(
                        ["systemctl", "show", env.unit_name, "-p", "MainPID", "--value"],
                        stderr=subprocess.DEVNULL
                    ).decode().strip()
                    if mpid and mpid != "0":
                        env.main_pid = int(mpid)
                except Exception:
                    pass

        return {
            'status': env.status,
            'cpu': env.cpu,
            'memory': env.memory,
            'io': env.io,
            'command': env.command,
            'unit': getattr(env, "unit_name", None),
            'pid': getattr(env, "main_pid", None)
        }

    # Caminho do output
    def get_output_path(self, namespace):
        return os.path.join("environments", namespace, "output.log")

    # Encerrar ambiente
    def terminate_environment(self, namespace):
        env = self.environments.get(namespace)
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
