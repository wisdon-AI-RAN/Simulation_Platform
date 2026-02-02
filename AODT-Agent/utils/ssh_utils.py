import paramiko

def execute_remote_script(ssh_host, ssh_port, ssh_user, password, script_path):
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(ssh_host, port=ssh_port, username=ssh_user, password=password)

        # 使用 exec_command 執行遠端腳本
        stdin, stdout, stderr = ssh.exec_command(f'sh {script_path}')

        # 讀取輸出和錯誤訊息
        out = stdout.read().decode()
        err = stderr.read().decode()
        code = stdout.channel.recv_exit_status()

        ssh.close()

        if code == 0:
            return {
                "status": "success",
                "code": code,
                "output": out
            }
        else:
            return {
                "status": "error",
                "error": err,
                "code": code
            }

    except Exception as e:
        return {
            "status": "error",
            "code": -1,
            "output": "",
            "error": f"SSH 連線失敗: {e}"
        }