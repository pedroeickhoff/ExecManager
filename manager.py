from models import Environment
from executor import run_command
import os
import signal
import shutil

class EnvironmentManager:
    def __init__(self):
        self.environments = {}

    def create_environment(self, data):
        env = Environment(
            namespace=data['namespace'],
            cpu=data.get('cpu', 1),
            memory=data.get('memory', 128),
            io=data.get('io', 1),
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
        process, path = run_command(ns, env.command)
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

        # Finaliza o processo se estiver rodando
        if env.process and env.process.poll() is None:
            os.kill(env.process.pid, signal.SIGTERM)
            env.status = 'terminated'

        # Remove da memória
        del self.environments[namespace]

        # Remove a pasta física
        env_path = os.path.join("environments", namespace)
        if os.path.exists(env_path):
            shutil.rmtree(env_path)

        return {'message': f'Ambiente {namespace} encerrado e removido'}

manager = EnvironmentManager()
