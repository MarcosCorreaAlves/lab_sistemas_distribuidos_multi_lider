import psycopg2
import argparse
import time
from config import SERVERS, ALL_SERVERS, LOCAL_SERVERS

# --- CONSTANTES ---
STATUS_ACEITA = 'ACEITA'
STATUS_REJEITADA = 'REJEITADA'
DBNAME_KEY = 'dbname'

# --- FUNÇÕES DE CONEXÃO E UTILIDADES ---

def connect_to_db(servidor_id):
    """Conecta ao banco de dados específico. Retorna None em caso de falha."""
    config = SERVERS.get(servidor_id) 
    if not config:
        print(f"❌ Configuração do servidor {servidor_id} não encontrada.")
        return None
    
    connect_args = {k: v for k, v in config.items() if k != 'tipo'}
    connect_args['connect_timeout'] = 10 
    
    try:
        conn = psycopg2.connect(**connect_args)
        return conn
    except psycopg2.OperationalError:
        return None

def obter_disciplina_id(conn, disciplina_nome):
    """Busca o ID e o total de vagas da disciplina pelo nome."""
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id, vagas_totais FROM disciplinas WHERE nome = %s", (disciplina_nome,))
        result = cursor.fetchone()
        if result:
            return result[0], result[1]
        return None, None
    finally:
        cursor.close()

def consultar_estado(disciplina_id):
    """
    Consulta o estado de todas as matrículas para a disciplina em todos os líderes,
    garante a consistência do timestamp (tzinfo) e remove duplicatas.
    Retorna: [(id, nome, ts_naive, status), ...]
    """
    todos_registros = []
    
    # IMPORTANTE: Esta consulta é distribuída e PODE conter o aluno removido,
    # se a replicação ainda não chegou em todos os líderes.
    for servidor_id in ALL_SERVERS:
        conn = connect_to_db(servidor_id)
        if conn:
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    SELECT 
                        id, nome_aluno, timestamp_matricula, status
                    FROM 
                        matriculas
                    WHERE 
                        disciplina_id = %s
                    ORDER BY 
                        timestamp_matricula;
                """, (disciplina_id,))
                
                registros = cursor.fetchall()
                
                registros_corrigidos = []
                for matricula_id, nome, timestamp_db, status in registros:
                    if timestamp_db and timestamp_db.tzinfo is not None:
                        timestamp_naive = timestamp_db.replace(tzinfo=None)
                    else:
                        timestamp_naive = timestamp_db
                        
                    registros_corrigidos.append((matricula_id, nome, timestamp_naive, status))
                
                todos_registros.extend(registros_corrigidos)
            finally:
                cursor.close()
                conn.close()

    # DEDUPLICAÇÃO
    registros_unicos = set(todos_registros) 
    registros_finais = list(registros_unicos)
    registros_finais.sort(key=lambda x: x[2])
    
    return registros_finais

def reavaliar_e_atualizar_status(lider_destino, disciplina_id, vagas_totais, ids_removidos_local):
    """
    Executa a lógica de desempate em todos os registros da disciplina,
    FILTRANDO o aluno que acabou de ser removido.
    """
    
    # 1. Consulta o estado distribuído (pode incluir o aluno removido de outros líderes)
    registros_atuais = consultar_estado(disciplina_id)
    updates_a_replicar = []
    
    # 2. FILTRO DE CONSISTÊNCIA LOCAL: Remove o aluno que acabou de ser deletado no commit local
    registros_limpos = [
        r for r in registros_atuais if r[0] not in ids_removidos_local
    ]
    
    # 3. FILTRO DE DUPLICATAS HISTÓRICAS: Mantém apenas o registro MAIS ANTIGO de cada aluno
    registros_filtrados = {}
    for old_id, nome, ts, status_antigo in registros_limpos:
        if nome not in registros_filtrados or ts < registros_filtrados[nome][2]:
            registros_filtrados[nome] = (old_id, nome, ts, status_antigo)

    registros_finais = list(registros_filtrados.values())
    registros_finais.sort(key=lambda x: x[2]) # Reordena após a filtragem
    
    # 4. Determina os novos status
    print("\n--- Reavaliação de Status Pós-Remoção ---")
    
    # Itera sobre a lista ORDENADA e FILTRADA
    for i, (old_id, nome, ts, status_antigo) in enumerate(registros_finais):
        posicao = i + 1
        status_calculado = STATUS_ACEITA if posicao <= vagas_totais else STATUS_REJEITADA
        
        # <<< SAÍDA DE DEBUG PARA RASTREAR O ERRO >>>
        print(f"[DEBUG] Aluno: {nome} | Posição: {posicao}/{vagas_totais} | DB Status: {status_antigo} | Calc Status: {status_calculado}")
        # <<< FIM DEBUG >>>
        
        # Se o status mudou (por exemplo, de REJEITADA para ACEITA)
        if status_calculado != status_antigo:
            updates_a_replicar.append((old_id, nome, status_calculado, ts))
            print(f"Status Atualizado: {nome} subiu para {status_calculado} (Posição: {posicao}/{vagas_totais})")

    if not updates_a_replicar:
        print("Nenhuma alteração de status necessária. Vagas remanescentes.")
        return updates_a_replicar

    # 5. Aplica as atualizações no líder de destino
    conn = connect_to_db(lider_destino)
    if not conn:
        print(f"❌ Falha ao aplicar updates: Líder {lider_destino} está offline.")
        return []

    cursor = conn.cursor()
    update_query = "UPDATE matriculas SET status = %s WHERE id = %s"
    
    try:
        for old_id, nome, novo_status, ts in updates_a_replicar:
            cursor.execute(update_query, (novo_status, old_id))
        
        conn.commit()
        print(f"✅ Status de {len(updates_a_replicar)} alunos atualizados no Líder {lider_destino}.")
        
    except psycopg2.Error as e:
        conn.rollback()
        print(f"❌ Erro PostgreSQL durante a atualização de status: {e}")
        return []
    except Exception as e:
        print(f"❌ Erro inesperado durante a atualização: {e}")
        return []
    finally:
        if cursor: cursor.close()
        if conn: conn.close()
        
    return updates_a_replicar

def remover_aluno(lider_destino, aluno, disciplina_nome):
    """
    Remove a matrícula, e se a remoção for bem-sucedida, reavalia e atualiza o estado.
    """
    
    conn = connect_to_db(lider_destino)
    if not conn:
        print(f"❌ Remoção falhou em {lider_destino} devido à falha de conexão.")
        return

    cursor = conn.cursor()
    
    # 1. Obter o ID e Vagas da disciplina
    disciplina_id, vagas_totais = obter_disciplina_id(conn, disciplina_nome)
    
    if not disciplina_id:
        print(f"❌ Falha: Disciplina '{disciplina_nome}' não encontrada no líder {lider_destino}.")
        conn.close()
        return

    try:
        # 2. DELETE: Identifica e remove todas as ocorrências do aluno
        cursor.execute("SELECT id FROM matriculas WHERE nome_aluno = %s AND disciplina_id = %s", (aluno, disciplina_id))
        ids_a_remover = [row[0] for row in cursor.fetchall()]
        
        if not ids_a_remover:
            print(f"⚠️ Aviso: Aluno '{aluno}' não encontrado matriculado em '{disciplina_nome}' em {lider_destino} para remoção.")
            conn.rollback()
            return
            
        # Executa o DELETE final
        cursor.execute(f"DELETE FROM matriculas WHERE id IN %s", (tuple(ids_a_remover),))
            
        conn.commit()
        print(f"✅ Remoção aceite em {lider_destino}: {len(ids_a_remover)} registro(s) de '{aluno}' em '{disciplina_nome}' removido(s).")
        
        # 3. REAVALIAR E ATUALIZAR STATUS (Passa a lista de IDs removidos localmente)
        if vagas_totais > 0:
            updates_a_replicar = reavaliar_e_atualizar_status(lider_destino, disciplina_id, vagas_totais, set(ids_a_remover))
        else:
            updates_a_replicar = []
            
        # 4. REPLICAÇÃO: Remove os IDs e replica as atualizações de status
        print("\n--- Replicação de Remoção e Updates ---")
        
        delete_replication_query = "DELETE FROM matriculas WHERE id IN %s"
        delete_replication_data = (tuple(ids_a_remover),)
        
        update_replication_query = "UPDATE matriculas SET status = %s WHERE id = %s"
        
        for servidor_id in ALL_SERVERS:
            if servidor_id == lider_destino:
                continue 
                
            replica_conn = connect_to_db(servidor_id)
            if replica_conn:
                replica_cursor = replica_conn.cursor()
                try:
                    # a) Remove os IDs
                    replica_cursor.execute(delete_replication_query, delete_replication_data)
                    
                    # b) Replica os Updates de Status
                    for old_id, nome, novo_status, ts in updates_a_replicar:
                        replica_cursor.execute(update_replication_query, (novo_status, old_id))
                        
                    replica_conn.commit()
                    print(f"➡️ Replicação sucesso (Remoção + {len(updates_a_replicar)} updates) para o servidor {servidor_id}.")
                except Exception as e:
                    print(f"❌ Erro ao replicar para {servidor_id}: {e}")
                    replica_conn.rollback()
                finally:
                    if replica_cursor: replica_cursor.close()
                    if replica_conn: replica_conn.close()
            else:
                print(f"❌ Falha de Conexão: Líder {servidor_id} inacessível para replicação.")
            
    except psycopg2.Error as e:
        conn.rollback()
        print(f"❌ Erro PostgreSQL durante a remoção: {e}")
    except Exception as e:
        print(f"❌ Erro inesperado: {e}")
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Script para remover alunos no sistema distribuído e reavaliar vagas.')
    
    parser.add_argument('--aluno', required=True, type=str, help='Nome do aluno a ser removido.')
    parser.add_argument('--disciplina', required=True, type=str, help='Nome da disciplina da qual o aluno será removido.')
    
    args = parser.parse_args()
    
    if not LOCAL_SERVERS:
        print("❌ ERRO DE CONFIGURAÇÃO: LOCAL_SERVERS não está definido no config.py.")
        exit(1)
        
    lider_destino = LOCAL_SERVERS[0]
    
    print(f"⏳ Tentando remover {args.aluno} de '{args.disciplina}' via Líder {lider_destino}...")
    
    remover_aluno(lider_destino, args.aluno, args.disciplina)