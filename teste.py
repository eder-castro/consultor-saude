import os
import json
from datetime import datetime

PASTA_JSON = "json_diarios"

def arquivo_dados_mais_recente():
    prefixo = ["dados_", "analise_"]
    arquivos = [
        f for f in os.listdir(PASTA_JSON)
            if f.startswith(item) and f.endswith(".json")
    ]

    if not arquivos:
        raise FileNotFoundError("Nenhum arquivo dados_*.json encontrado")

    arquivos.sort(
        key=lambda nome: datetime.strptime(
            nome.replace(prefixo[item], "").replace(".json", ""),
            "%Y-%m-%d"
        )
    )

    return os.path.join(PASTA_JSON, arquivos[-1])

# Uso
caminho_dados = arquivo_dados_mais_recente()

print("Usando arquivo:", caminho_dados)

with open(caminho_dados, "r", encoding="utf-8") as f:
    dados = json.load(f)
