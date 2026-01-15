import os
import json
import io
from datetime import datetime
from dotenv import load_dotenv

from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

import gspread

# =========================
# CONFIGURAÇÕES
# =========================

SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets"
]

load_dotenv()

SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
GDRIVE_INPUT_ID = os.getenv("GDRIVE_INPUT_ID")
GDRIVE_PROCESSED_ID = os.getenv("GDRIVE_PROCESSED_ID")

# =========================
# AUTH
# =========================

def get_google_services():
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                "credentials.json", SCOPES
            )
            creds = flow.run_local_server(port=0)

        with open("token.json", "w") as token:
            token.write(creds.to_json())

    drive_service = build("drive", "v3", credentials=creds)
    return drive_service, creds

# =========================
# FUNÇÕES DO DRIVE (CLOUD)
# =========================

def list_json_files_in_drive(service, folder_id):
    """Lista arquivos JSON dentro de uma pasta específica do Drive."""
    query = f"'{folder_id}' in parents and mimeType='application/json' and trashed=false"
    
    results = service.files().list(
        q=query,
        fields="files(id, name, createdTime)",
        orderBy="createdTime"
    ).execute()
    
    return results.get("files", [])

def read_json_from_drive(service, file_id):
    """Baixa o conteúdo do JSON para a memória."""
    request = service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    
    done = False
    while not done:
        status, done = downloader.next_chunk()
    
    # Retorna o cursor para o início e lê
    fh.seek(0)
    content = fh.read().decode('utf-8')
    return json.loads(content)

def move_file_in_drive(service, file_id, old_folder_id, new_folder_id):
    """Move o arquivo trocando o ID da pasta pai."""
    service.files().update(
        fileId=file_id,
        addParents=new_folder_id,
        removeParents=old_folder_id,
        fields="id, parents"
    ).execute()

# =========================
# PROCESSAMENTO (Igual ao anterior)
# =========================

def safe_get(data_dict, key, default=""):
    val = data_dict.get(key)
    return val if val is not None else default

def process_health_data(spreadsheet, data, filename):
    
    # 1. ALIMENTAÇÃO
    if "alimentacao" in data and isinstance(data["alimentacao"], list):
        rows = []
        for item in data["alimentacao"]:
            rows.append([
                safe_get(item, "data"),
                safe_get(item, "horario"),
                safe_get(item, "item"),
                safe_get(item, "midia_id"),
                filename
            ])
        if rows:
            spreadsheet.worksheet("alimentacao").append_rows(rows)
            print(f"   -> {len(rows)} itens de alimentação.")

    # 2. EXERCÍCIOS
    if "exercicios" in data and isinstance(data["exercicios"], list):
        rows = []
        for item in data["exercicios"]:
            rows.append([
                safe_get(item, "data"),
                safe_get(item, "tipo"),
                safe_get(item, "duracao_min", 0),
                safe_get(item, "intensidade"),
                safe_get(item, "calorias_estimadas", 0),
                safe_get(item, "midia_id"),
                filename
            ])
        if rows:
            spreadsheet.worksheet("exercicios").append_rows(rows)
            print(f"   -> {len(rows)} exercícios.")

    # 3. PESO
    if "peso" in data and isinstance(data["peso"], dict):
        p = data["peso"]
        if p.get("valor_kg"):
            row = [
                safe_get(p, "data"),
                safe_get(p, "horario"),
                safe_get(p, "valor_kg", 0.0),
                filename
            ]
            spreadsheet.worksheet("peso").append_row(row)
            print("   -> Peso registrado.")

    # 4. SONO
    if "sono" in data and isinstance(data["sono"], dict):
        s = data["sono"]
        if s.get("duracao_minutos"):
            row = [
                safe_get(s, "data"),
                safe_get(s, "inicio"),
                safe_get(s, "fim"),
                safe_get(s, "duracao_minutos", 0),
                safe_get(s, "sono_profundo_min", 0),
                safe_get(s, "sono_leve_min", 0),
                safe_get(s, "sono_rem_min", 0),
                safe_get(s, "acordado_min", 0),
                safe_get(s, "midia_id"),
                filename
            ]
            spreadsheet.worksheet("sono").append_row(row)
            print("   -> Sono registrado.")

    # 5. ANÁLISES
    if "analises" in data and isinstance(data["analises"], list):
        rows = []
        for a in data["analises"]:
            rows.append([
                safe_get(a, "data"),
                safe_get(a, "evento_tipo"),
                safe_get(a, "evento_referencia"),
                safe_get(a, "resumo"),
                safe_get(a, "pontos_positivos"),
                safe_get(a, "pontos_atencao"),
                safe_get(a, "sugestoes"),
                filename
            ])
        if rows:
            spreadsheet.worksheet("analise").append_rows(rows)
            print(f"   -> {len(rows)} análises.")

# =========================
# MAIN
# =========================

def main():
    print("Iniciando conexão com Google Drive...")
    drive_service, creds = get_google_services()
    gc = gspread.authorize(creds)
    spreadsheet = gc.open_by_key(SPREADSHEET_ID)

    # 1. Lista arquivos na nuvem
    files = list_json_files_in_drive(drive_service, GDRIVE_INPUT_ID)

    if not files:
        print("Nenhum arquivo JSON novo na pasta 'json_diarios'.")
        return

    print(f"Encontrados {len(files)} arquivos para processar.")

    for file in files:
        file_id = file['id']
        filename = file['name']
        print(f"\nProcessando: {filename} (ID: {file_id})...")

        try:
            # 2. Lê o conteúdo direto da nuvem
            data = read_json_from_drive(drive_service, file_id)

            # 3. Processa e insere na planilha
            process_health_data(spreadsheet, data, filename)

            # 4. Log
            try:
                spreadsheet.worksheet("log_json").append_row([
                    datetime.now().strftime("%Y-%m-%d"),
                    datetime.now().strftime("%H:%M:%S"),
                    filename,
                    file_id
                ])
            except:
                pass

            # 5. Move o arquivo DENTRO do Drive
            move_file_in_drive(drive_service, file_id, GDRIVE_INPUT_ID, GDRIVE_PROCESSED_ID)
            print("   -> Arquivo movido para 'json_processados'.")

        except Exception as e:
            print(f"ERRO ao processar {filename}: {e}")

if __name__ == "__main__":
    main()