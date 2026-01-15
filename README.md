# 🍎 Gemini Health Tracker & Automation

Este projeto é uma solução pessoal de **Quantified Self** (monitoramento de dados pessoais) que utiliza Inteligência Artificial para estruturar registros de saúde e automação em Python para análise de dados.

## 🚀 Como funciona

O fluxo de dados consiste em 3 etapas principais:

1.  **Coleta (Chat com IA):** Utilizo um prompt personalizado no **Google Gemini** ("Consultor de Saúde") para enviar fotos de refeições, treinos, peso e sono ao longo do dia.
2.  **Processamento (JSON):** Ao final do dia, o Gemini gera um relatório estruturado em formato JSON (contendo dados normalizados e análises granulares), que salvo manualmente em uma pasta no **Google Drive**.
3.  **Automação (Python Script):** Um script Python roda localmente, conecta-se à API do Google Drive, lê os arquivos JSON, processa os dados e insere as linhas nas abas correspondentes de uma planilha no **Google Sheets**.

## 🛠️ Tecnologias Utilizadas

* **Python 3.x**
* **Google Gemini** (Gerador de Dados Estruturados)
* **Google Drive API** (Armazenamento e Gestão de Arquivos)
* **Google Sheets API** (Banco de Dados / Frontend de Análise)
* **Bibliotecas:** `gspread`, `google-auth`, `python-dotenv`

## 📂 Estrutura do Projeto

* `inserir_planilha.py`: Script principal que orquestra a leitura do Drive e escrita no Sheets.
* `prompts/`: (Opcional) Contém o prompt de sistema utilizado no Gemini.
* `json_diarios/`: Pasta de entrada no Google Drive (Cloud).
* `json_processados/`: Pasta de arquivo no Google Drive (Cloud).

## ⚙️ Configuração

### Pré-requisitos
1.  Conta no Google Cloud Platform (GCP) com APIs do Drive e Sheets habilitadas.
2.  Arquivo `credentials.json` (OAuth 2.0 Client ID).
3.  Planilha no Google Sheets criada com as abas: `alimentacao`, `exercicios`, `peso`, `sono`, `analise`, `log_json`.

### Variáveis de Ambiente (.env)
Crie um arquivo `.env` na raiz com as seguintes chaves:

```env
SPREADSHEET_ID="ID_DA_SUA_PLANILHA"
GDRIVE_INPUT_ID="ID_DA_PASTA_DE_ENTRADA_NO_DRIVE"
GDRIVE_PROCESSED_ID="ID_DA_PASTA_DE_PROCESSADOS_NO_DRIVE"