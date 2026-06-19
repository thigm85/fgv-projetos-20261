import subprocess
import json

def get_terraform_output():
    try:
        result = subprocess.run(['terraform', 'output', '-json'], capture_output=True, text=True, cwd='terraform')
        if result.returncode != 0:
            raise Exception(f"Erro no terraform output: {result.stderr}")
        outputs = json.loads(result.stdout)
        return {
            'endpoint': outputs['rds_endpoint']['value'].split(':')[0],
            'port': str(outputs['rds_port']['value']),
            'username': outputs['rds_username']['value'],
            'password': outputs['rds_password']['value'],
            'database': outputs['rds_database']['value']
        }
    except Exception as e:
        print(f"Erro ao pegar outputs do Terraform: {e}")
        return None

if __name__ == "__main__":
    config = get_terraform_output()
    if config:
        with open('rds_config.txt', 'w') as f:
            for key, value in config.items():
                f.write(f"{key}={value}\n")
        print("Arquivo de config gerado: rds_config.txt")
    else:
        print("Falhou em gerar config.")