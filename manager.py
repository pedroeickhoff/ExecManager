import os
import shutil
import signal
import psutil
import subprocess
import time
from models import Environment
from executor import run_command


class EnvironmentManager:
    def __init__(self):
        self.environments = {}

    # ---------------------------
    # Recursos disponíveis
    # ---------------------------
    def get_available_resources(self):
        cpu_count = psutil.cpu_count(logical=False) or psutil.cpu_count()
        mem = psutil.virtual_memory()
        available_memory_mb = int(mem.available / (1024 * 1024))
        return {
            'cpu_available': cpu_count,
            'memory_available': available_memory_mb
        }

    # ---------------------------
    # Criar ambiente
    # ---------------------------
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

    # ---------------------------
    # Executar programa
    # ---------------------------
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

    # ---------------------------
    # Consultar status
    # ---------------------------
    def get_status(self, namespace):
        env = self.environments.get(namespace)
        if not env:
            return {'error': 'Namespace não encontrado'}

        if getattr(env, "unit_name", None):
            try:
                st = subprocess.check_output(
                    ["systemctl", "is-active", env.unit_name],
                    stderr=subprocess.DEVNULL
                ).decode().strip()
                if st == "active":
                    env.status = "running"
                elif st in ("inactive", "deactivating"):
                    env.status = "finished"
                else:
                    env.status = st  # failed, etc.
            except subprocess.CalledProcessError:
                env.status = "unknown"

        return {
            'status': env.status,
            'cpu': env.cpu,
            'memory': env.memory,
            'io': env.io,
            'command': env.command,
            'unit': getattr(env, "unit_name", None),
            'pid': getattr(env, "main_pid", None)
        }

    # ---------------------------
    # Caminho do output
    # ---------------------------
    def get_output_path(self, namespace):
        return os.path.join("environments", namespace, "output.log")

    # ---------------------------
    # Encerrar ambiente
    # ---------------------------
    def terminate_environment(self, namespace):
        env = self.environments.get(namespace)
        if not env:
            return {'error': 'Namespace não encontrado'}

        try:
            # Encerra unit systemd se existir
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

            # Mata PID direto se ainda existir
            if getattr(env, "main_pid", None):
                try:
                    os.kill(env.main_pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass  # já morreu
                except PermissionError:
                    pass  # sem permissão, ignora

            env.status = 'terminated'

        except Exception as e:
            return {'error': f'Erro ao encerrar processo: {str(e)}'}

        # Remove o ambiente da lista
        self.environments.pop(namespace, None)

        # Remove diretório do ambiente
        env_path = os.path.join("environments", namespace)
        try:
            if os.path.exists(env_path):
                shutil.rmtree(env_path)
        except Exception as e:
            return {'error': f'Erro ao remover pasta: {str(e)}'}

        return {'message': f'Ambiente {namespace} encerrado e removido com sucesso'}


# ✅ Instância global utilizada pelo app.py
manager = EnvironmentManager()
