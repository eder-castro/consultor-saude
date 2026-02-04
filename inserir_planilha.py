from googleapiclient.http import MediaIoBaseUpload
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
GDRIVE_KNOWLEDGE_ID = os.getenv("GDRIVE_KNOWLEDGE_ID")

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
    
    media_rows = [] # Lista para acumular registros para a aba 'midias'
    
    # === BLOCO DE COMPATIBILIDADE (JANEIRO/LEGADO) ===
    # Transforma "consumo_liquidos" antigo no novo formato de lista "hidratacao"
    if "consumo_liquidos" in data and "hidratacao" not in data:
        data["hidratacao"] = []
        cl = data["consumo_liquidos"]
        # Água
        if cl.get("agua_total_ml", 0) > 0:
            data["hidratacao"].append({
                "data": safe_get(cl, "data", datetime.now().strftime("%Y-%m-%d")),
                "horario": "23:59",
                "item": "Água (Total do Dia)",
                "quantidade_ml": cl.get("agua_total_ml"),
                "midia_id": None
            })
        # Café
        if cl.get("cafe_total_doses", 0) > 0:
             data["hidratacao"].append({
                "data": safe_get(cl, "data", datetime.now().strftime("%Y-%m-%d")),
                "horario": "23:59",
                "item": f"Café ({cl.get('cafe_total_doses')} doses)",
                "quantidade_ml": 0,
                "midia_id": None
            })
    # =================================================

    # 1. ALIMENTAÇÃO
    # Colunas: data|horario|item|quantidade|midia_id|json_filename
    if "alimentacao" in data and isinstance(data["alimentacao"], list):
        rows = []
        for item in data["alimentacao"]:
            m_id = safe_get(item, "midia_id")
            item_nome = safe_get(item, "item")
            item_data = safe_get(item, "data")
            
            rows.append([
                item_data,
                safe_get(item, "horario"),
                item_nome,
                safe_get(item, "quantidade_estimada", "N/A"), # Mapeia para col 'quantidade'
                m_id,
                filename
            ])
            
            # Coleta Mídia
            if m_id:
                # Estrutura 'midias': data|tipo_evento|origem|descricao|url_imagem|midia_id|json_filename
                media_rows.append([
                    item_data, 
                    "Alimentacao", 
                    "Chat", 
                    item_nome, 
                    "", 
                    m_id, 
                    filename
                ])
                
        if rows:
            spreadsheet.worksheet("alimentacao").append_rows(rows)
            print(f"   -> {len(rows)} itens de alimentação.")

    # 2. HIDRATAÇÃO
    # Colunas: data|horario|item|quantidade|midia_id|json_filename
    if "hidratacao" in data and isinstance(data["hidratacao"], list):
        rows = []
        for item in data["hidratacao"]:
            m_id = safe_get(item, "midia_id")
            item_nome = safe_get(item, "item")
            item_data = safe_get(item, "data")
            
            rows.append([
                item_data,
                safe_get(item, "horario"),
                item_nome,
                safe_get(item, "quantidade_ml", 0), # Mapeia para col 'quantidade'
                m_id,
                filename
            ])
            
            if m_id:
                 media_rows.append([
                    item_data, 
                    "Hidratacao", 
                    "Chat", 
                    item_nome, 
                    "", 
                    m_id, 
                    filename
                ])

        if rows:
            try:
                spreadsheet.worksheet("hidratacao").append_rows(rows)
                print(f"   -> {len(rows)} registros de hidratação.")
            except:
                print("   [ERRO] Aba 'hidratacao' não encontrada.")

    # 3. EXERCÍCIOS
    # Colunas: data|tipo|duracao_min|intensidade|calorias_estimadas|midia_id|json_filename
    if "exercicios" in data and isinstance(data["exercicios"], list):
        rows = []
        for item in data["exercicios"]:
            m_id = safe_get(item, "midia_id")
            item_nome = safe_get(item, "tipo")
            item_data = safe_get(item, "data")

            rows.append([
                item_data,
                item_nome,
                safe_get(item, "duracao_min", 0),
                safe_get(item, "intensidade"),
                safe_get(item, "calorias_estimadas", 0),
                m_id,
                filename
            ])
            
            if m_id:
                media_rows.append([
                    item_data, 
                    "Exercicio", 
                    "Chat", 
                    item_nome, 
                    "", 
                    m_id, 
                    filename
                ])

        if rows:
            spreadsheet.worksheet("exercicios").append_rows(rows)
            print(f"   -> {len(rows)} exercícios.")

    # 4. PESO
    # Colunas: data|horario|valor_kg|json_filename
    if "peso" in data and isinstance(data["peso"], dict):
        p = data["peso"]
        if p.get("valor_kg"):
            # Nota: Peso na planilha não tem coluna de midia_id, mas capturamos para a aba midias se houver
            m_id = safe_get(p, "midia_id")
            p_data = safe_get(p, "data")
            p_valor = p.get("valor_kg", 0.0)

            row = [
                p_data,
                safe_get(p, "horario"),
                p_valor,
                filename
            ]
            spreadsheet.worksheet("peso").append_row(row)
            
            if m_id:
                media_rows.append([
                    p_data, 
                    "Peso", 
                    "Chat", 
                    f"Registro de Peso ({p_valor}kg)", 
                    "", 
                    m_id, 
                    filename
                ])
            print("   -> Peso registrado.")

    # 5. SONO
    # Colunas: data|inicio|fim|duracao_minutos|sono_profundo_min|sono_leve_min|sono_rem_min|acordado_min|midia_id|json_filename
    if "sono" in data and isinstance(data["sono"], dict):
        s = data["sono"]
        if s.get("duracao_minutos") or s.get("inicio"):
            m_id = safe_get(s, "midia_id")
            s_data = safe_get(s, "data")

            row = [
                s_data,
                safe_get(s, "inicio"),
                safe_get(s, "fim"),
                safe_get(s, "duracao_minutos", 0),
                safe_get(s, "sono_profundo_min", 0),
                safe_get(s, "sono_leve_min", 0),
                safe_get(s, "sono_rem_min", 0),
                safe_get(s, "acordado_min", 0),
                m_id,
                filename
            ]
            spreadsheet.worksheet("sono").append_row(row)
            
            if m_id:
                media_rows.append([
                    s_data, 
                    "Sono", 
                    "Chat", 
                    "Monitoramento de Sono", 
                    "", 
                    m_id, 
                    filename
                ])
            print("   -> Sono registrado.")

    # 6. ANÁLISES
    # Colunas: data|evento_tipo|evento_referencia|resumo|pontos_positivos|pontos_atencao|sugestoes|json_filename
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

    # === 7. GRAVAÇÃO NA ABA MIDIAS ===
    # Colunas: data|tipo_evento|origem|descricao|url_imagem|midia_id|json_filename
    if media_rows:
        try:
            # Remove duplicatas exatas para evitar sujeira
            unique_media = list(set(tuple(x) for x in media_rows))
            # Ordena por Data
            unique_media.sort(key=lambda x: x[0])
            
            spreadsheet.worksheet("midias").append_rows(unique_media)
            print(f"   -> {len(unique_media)} registros na aba 'midias'.")
        except gspread.exceptions.WorksheetNotFound:
            print("   [ERRO] Aba 'midias' não encontrada.")

def get_processed_ids(spreadsheet):
    """Lê a aba de log e retorna um SET com os IDs já processados."""
    try:
        ws = spreadsheet.worksheet("log_json")
        # Assume que o ID do arquivo está na coluna 4 (D), conforme seu script anterior
        return set(ws.col_values(4))
    except gspread.exceptions.WorksheetNotFound:
        # Se a aba não existir, cria ela e retorna vazio
        spreadsheet.add_worksheet(title="log_json", rows=1000, cols=5)
        return set()
    except Exception as e:
        print(f"Aviso: Não foi possível ler o log ({e}). Processando tudo.")
        return set()

def generate_history_report(spreadsheet, drive_service, folder_id):
    """Gera um arquivo TXT com o resumo dos últimos registros para contexto da IA."""
    print("\nGerando arquivo de histórico (Contexto)...")
    
    report_lines = ["=== HISTÓRICO RECENTE (CONTEXTO PARA IA) ===", ""]

    # 1. PEGAR ÚLTIMOS PESOS (Últimos 5 registros)
    try:
        ws_peso = spreadsheet.worksheet("peso")
        all_weights = ws_peso.get_all_values()
        # Pula cabeçalho e pega os últimos 5
        last_weights = all_weights[1:][-5:] if len(all_weights) > 1 else []
        
        report_lines.append("--- PESO RECENTE ---")
        for w in last_weights:
            # Colunas: data|horario|valor_kg
            report_lines.append(f"Data: {w[0]} | Peso: {w[2]}kg")
        report_lines.append("")
    except:
        pass

    # 2. PEGAR MÉDIA DE SONO (Últimos 5 registros)
    try:
        ws_sono = spreadsheet.worksheet("sono")
        all_sleep = ws_sono.get_all_values()
        last_sleep = all_sleep[1:][-5:] if len(all_sleep) > 1 else []
        
        report_lines.append("--- SONO RECENTE ---")
        for s in last_sleep:
            # Colunas: data|inicio|fim|duracao...
            report_lines.append(f"Data: {s[0]} | Dormiu: {s[3]} min")
        report_lines.append("")
    except:
        pass

    # 3. ÚLTIMOS INSIGHTS/ANÁLISES (Últimos 3 dias)
    try:
        ws_analise = spreadsheet.worksheet("analise")
        all_analise = ws_analise.get_all_values()
        last_analise = all_analise[1:][-3:] if len(all_analise) > 1 else []

        report_lines.append("--- INSIGHTS ANTERIORES ---")
        for a in last_analise:
            # Colunas: data|tipo|ref|resumo|positivos|atencao|sugestoes
            report_lines.append(f"[{a[0]}] {a[2]} ({a[1]}): {a[3]}")
            report_lines.append(f"   > Sugestão dada: {a[6]}")
        report_lines.append("")
    except:
        pass

    # CONVERTE PARA STRING
    content_str = "\n".join(report_lines)

    # 4. SALVAR/ATUALIZAR NO DRIVE
    file_name = "CONTEXTO_SAUDE_RECENTE.txt"
    
    # Verifica se o arquivo já existe para sobrescrever
    query = f"name = '{file_name}' and '{folder_id}' in parents and trashed = false"
    existing_files = drive_service.files().list(q=query).execute().get('files', [])

    media = MediaIoBaseUpload(io.BytesIO(content_str.encode('utf-8')), mimetype='text/plain')

    if existing_files:
        # Atualiza o existente
        file_id = existing_files[0]['id']
        drive_service.files().update(fileId=file_id, media_body=media).execute()
        print(f" -> Arquivo '{file_name}' ATUALIZADO com sucesso.")
    else:
        # Cria um novo
        file_metadata = {'name': file_name, 'parents': [folder_id]}
        drive_service.files().create(body=file_metadata, media_body=media).execute()
        print(f" -> Arquivo '{file_name}' CRIADO com sucesso.")

# =========================
# MAIN
# =========================

def main():
    print("Iniciando conexão com Google Drive...")
    drive_service, creds = get_google_services()
    gc = gspread.authorize(creds)
    spreadsheet = gc.open_by_key(SPREADSHEET_ID)

    # --- NOVO: Carrega lista de IDs já processados ---
    print("Verificando histórico de logs...")
    processed_ids = get_processed_ids(spreadsheet)
    print(f"Histórico carregado: {len(processed_ids)} arquivos já processados anteriormente.")
    # -------------------------------------------------

    # 1. Lista arquivos na nuvem
    files = list_json_files_in_drive(drive_service, GDRIVE_INPUT_ID)

    if not files:
        print("Nenhum arquivo JSON novo na pasta 'json_diarios'.")
        return

    print(f"Encontrados {len(files)} arquivos para processar.")

    for file in files:
        file_id = file['id']
        filename = file['name']

        # --- NOVO: Checagem de Duplicidade ---
        if file_id in processed_ids:
            print(f" [PULADO] {filename} já foi processado (ID no log).")
            # Opcional: Se quiser mover arquivos esquecidos na pasta de entrada, descomente abaixo:
            # move_file_in_drive(drive_service, file_id, GDRIVE_INPUT_ID, GDRIVE_PROCESSED_ID)
            continue
        # -------------------------------------

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
   
    # Gera o relatório de contexto sempre que rodar o script
    generate_history_report(spreadsheet, drive_service, GDRIVE_KNOWLEDGE_ID)
    
    print("\nProcessamento concluído.")

if __name__ == "__main__":
    main()