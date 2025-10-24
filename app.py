from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from manager import manager

app = Flask(__name__)
CORS(app)

@app.route('/')
def home():
    return '''
    <h1>🚀 Execução de Programas via Web</h1>
    <ul>
        <li><strong>POST /create</strong> — Criar novo ambiente</li>
        <li><strong>POST /execute</strong> — Executar programa</li>
        <li><strong>GET /status/&lt;namespace&gt;</strong> — Status (pid, mem, cpu, status, command)</li>
        <li><strong>GET /environments</strong> — Listar ambientes (persistidos)</li>
        <li><strong>GET /output/&lt;namespace&gt;</strong> — Ver output</li>
        <li><strong>DELETE /terminate/&lt;namespace&gt;</strong> — Encerrar</li>
    </ul>
    '''

@app.route('/create', methods=['POST'])
def create_env():
    data = request.json
    env = manager.create_environment(data)
    return jsonify(env), 201 if 'error' not in env else 400

@app.route('/execute', methods=['POST'])
def execute():
    data = request.json
    result = manager.execute_program(data)
    return jsonify(result), 202 if 'error' not in result else 400

@app.route('/status/<namespace>', methods=['GET'])
def status(namespace):
    return jsonify(manager.get_status(namespace))

@app.route('/environments', methods=['GET'])
def list_envs():
    return jsonify(manager.list_environments())

@app.route('/output/<namespace>', methods=['GET'])
def output(namespace):
    path = manager.get_output_path(namespace)
    try:
        return send_file(path, mimetype='text/plain')
    except FileNotFoundError:
        return jsonify({'error': 'Arquivo de output não encontrado'}), 404

@app.route('/terminate/<namespace>', methods=['DELETE'])
def terminate(namespace):
    result = manager.terminate_environment(namespace)
    return jsonify(result), 200 if 'error' not in result else 400

@app.route('/resources', methods=['GET'])
def resources():
    return jsonify(manager.get_available_resources())

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
