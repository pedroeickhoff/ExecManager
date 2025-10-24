# Exec Environments — Guia de Instalação e Uso

Este guia explica como subir a máquina virtual com Vagrant, configurar o frontend no Apache, iniciar a API Flask e acessar o dashboard no navegador.

---

## 🧰 1. Subir a VM

No seu computador (Windows), dentro da pasta do projeto:

```powershell
vagrant up
```

> Aguarde até o Vagrant importar a box `ubuntu/focal64`, instalar os pacotes e provisionar o ambiente automaticamente.  
> Se aparecer erro de nome duplicado no VirtualBox, abra o VirtualBox, apague a VM antiga **ou** renomeie-a, e depois rode `vagrant up` novamente.

---

## 💻 2. Entrar na VM

Depois que a VM estiver em execução:

```powershell
vagrant ssh
```

> Isso abre um terminal dentro da VM Ubuntu criada pelo Vagrant.  
> Sempre que quiser acessar novamente, use o mesmo comando.

---

## 🌐 3. Publicar o frontend no Apache

Dentro da VM (no terminal aberto após `vagrant ssh`):

```bash
sudo cp -r /vagrant/frontend/* /var/www/html/exec_env_frontend/
sudo systemctl restart apache2
```

- O diretório `/vagrant` é o espelhamento da pasta do projeto no seu host (Windows).
- A pasta `frontend` deve conter os arquivos `index.html`, `style.css` e `script.js`.
- Após copiar, reinicie o Apache para aplicar as alterações.

---

## ⚙️ 4. Rodar a API Flask manualmente

Ainda dentro da VM:

```bash
cd /vagrant
sudo python3 app.py
```

- Deixe esta janela aberta enquanto estiver utilizando o sistema.

---

## 🌍 5. Acessar o Dashboard

No navegador do seu computador (host), abra:

```
http://192.168.56.10/exec_env_frontend/index.html
```

> Se não abrir:
> - Confirme que a VM está em execução: `vagrant status`
> - Verifique se o Apache está ativo: `systemctl status apache2` (dentro da VM)
> - Certifique-se de que a API Flask está rodando no terminal (`sudo python3 app.py`)

---

## 🚀 6. Fluxo de uso no Dashboard

1. **Criar Ambiente** — defina `namespace`, CPU (aceita decimais, ex.: 0.3), memória (MB) e o comando/script.
2. **Executar** — inicie a execução do ambiente criado.
3. **Status** — acompanhe o status (`running`, `finished`, `error`), PID, CPU e memória solicitados.
4. **Output** — visualize e baixe o log `output.log`.
5. **Encerrar** — encerre o ambiente, liberando os recursos.

---

## 🔌 7. Endpoints principais (API Flask)

- **POST /create** → cria um ambiente  
  Exemplo:
  ```json
  { "namespace": "teste", "command": "echo oi", "cpu": 0.5, "memory": 512, "io": 5 }
  ```
- **POST /execute** → inicia a execução do comando:
  ```json
  { "namespace": "teste" }
  ```
- **GET /status/<namespace>** → retorna `{ pid, memory_requested, cpu_requested, status, command }`
- **GET /output/<namespace>** → faz download do log
- **DELETE /terminate/<namespace>** → encerra e remove o ambiente
- **GET /resources** → mostra o saldo de CPU/Mem disponível (já considerando reservas)
- **GET /environments** → lista ambientes armazenados no banco + última métrica coletada

---

## 🧠 8. Observações importantes

- Erros de execução (ex.: comando inexistente) aparecem como `status: "error"`.
- Logs ficam em `environments/<namespace>/output.log`.
- Banco de dados MariaDB é criado automaticamente com usuário `execenv` e senha `execenvpwd`.

---

---

## 📴 9. Encerrar o ambiente

Para parar tudo:

```bash
# Dentro da VM: parar a API
Ctrl + C

# Sair da VM
exit

# No host (Windows): desligar a VM
vagrant halt
```

Pronto!  
O sistema estará disponível em: **http://192.168.56.10/exec_env_frontend/index.html**
