from models import Environment
from executor import run_command
import os
import signal
import shutil
import psutil

class EnvironmentManager:
    def __init__(self):
        self.environments = {}

    def get_available_resources(self):
        cpu_count = psutil.cpu_count(logical=False)
        mem = psutil.virtual_memory()
        available_memory_mb = int(mem.available / (1024 * 1024))
        return {
            'cpu_available': cpu_count,
            'memory_available': available_memory_mb
        }

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

    def execute_program(self, data):
        ns = data['namespace']
        env = self.environments.get(ns)
        if not env:
            return {'error': 'Namespace não encontrado'}

        env.status = 'running'
        process, path = run_command(ns, env.command, env.cpu, env.memory)
        env.process = process
        return {'message': 'Execução iniciada', 'output_path': path}

    def get_status(self, namespace):
        env = self.environments.get(namespace)
        if not env:
            return {'error': 'Namespace não encontrado'}

        if env.process and env.process.poll() is None:
            env.status = 'running'
        elif env.process and env.process.poll() != 0:
            env.status = 'error'
        elif env.process:
            env.status = 'finished'

        return {
            'status': env.status,
            'cpu': env.cpu,
            'memory': env.memory,
            'io': env.io,
            'command': env.command
        }

    def get_output_path(self, namespace):
        return os.path.join("environments", namespace, "output.log")

    def terminate_environment(self, namespace):
        env = self.environments.get(namespace)
        if not env:
            return {'error': 'Namespace não encontrado'}

        try:
            if env.process and env.process.poll() is None:
                os.kill(env.process.pid, signal.SIGTERM)
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

        return {'message': f'Ambiente {namespace} encerrado e removido'}

manager = EnvironmentManager()
