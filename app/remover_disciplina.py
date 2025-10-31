import psycopg2
from app.config import SERVERS, ALL_SERVERS

def remover_disciplina_no_servidor(servidor_id, disciplina_nome, timestamp_agora):
    """Conecta e remove (Soft Delete) a disciplina em um único servidor."""
    config = SERVERS.get(servidor_id)
    if not config:
        return False, f"Configuração do servidor {servidor_id} não encontrada."
        
    connect_args = {k: v for k, v in config.items() if k != 'tipo'}
    connect_args['connect_timeout'] = 5 
    
    conn = None
    try:
        conn = psycopg2.connect(**connect_args)
        cursor = conn.cursor()
        
        # 1. Encontra o ID da disciplina
        cursor.execute("SELECT id FROM disciplinas WHERE nome = %s AND is_deleted = false;", (disciplina_nome,))
        resultado = cursor.fetchone()
        
        if not resultado:
            return False, "Disciplina não encontrada ou já removida."

        disciplina_id = resultado[0]

        # 2. SOFT DELETE (Matrículas)
        # Marca todas as matrículas relacionadas como 'REMOVIDA'
        cursor.execute("""
            UPDATE matriculas SET status = 'REMOVIDA', data_ultima_modificacao = %s
            WHERE disciplina_id = %s
            """, (timestamp_agora, disciplina_id))
        
        # 3. SOFT DELETE (Disciplina)
        cursor.execute("""
            UPDATE disciplinas SET is_deleted = true, data_ultima_modificacao = %s
            WHERE id = %s
            """, (timestamp_agora, disciplina_id))
        
        # 4. TOMBSTONE (Disciplina)
        cursor.execute("""
            INSERT INTO deleted_disciplinas (id, timestamp) 
            VALUES (%s, %s)
            ON CONFLICT (id) DO UPDATE SET timestamp = EXCLUDED.timestamp
            """, (disciplina_id, timestamp_agora))
        
        conn.commit()
        return True, "SUCESSO (Soft Delete)"

    except psycopg2.OperationalError:
        return False, "FALHA DE CONEXÃO (servidor offline)."
    except Exception as e:
        conn.rollback() # Garante rollback em caso de erro
        return False, f"ERRO INESPERADO: {e}"
    finally:
        if conn: conn.close()

# Função principal
def remover_disciplina():
    """Função adaptada para o menu: solicita o nome da disciplina via input e tenta remover."""
    
    disciplina_nome = input("Digite o NOME da disciplina que deseja remover: ").strip()
    
    if not disciplina_nome:
        print("❌ Remoção cancelada: O nome da disciplina não pode ser vazio.")
        return

    # Pega o ID local para feedback
    local_id = ALL_SERVERS[0] if ALL_SERVERS else None
    if not local_id:
        print("❌ Configuração de ALL_SERVERS vazia.")
        return
    
    print(f"\nTentando remover disciplina: '{disciplina_nome}'")
    
    all_results = {}
    
    # Gera um timestamp único para esta operação ser replicada
    conn_local = psycopg2.connect(**{k: v for k, v in SERVERS[local_id].items() if k != 'tipo'})
    cursor_local = conn_local.cursor()
    cursor_local.execute("SELECT (NOW() AT TIME ZONE 'UTC')")
    timestamp_agora = cursor_local.fetchone()[0]
    cursor_local.close()
    conn_local.close()

    for servidor_id in ALL_SERVERS:
        sucesso, mensagem = remover_disciplina_no_servidor(servidor_id, disciplina_nome, timestamp_agora)
        all_results[servidor_id] = {'sucesso': sucesso, 'mensagem': mensagem}

    local_result = all_results.get(local_id)
    
    print("\n--- Resultado da Operação ---")

    if local_result and local_result['sucesso']:
        print("✅ Disciplina removida (Soft Delete) com sucesso no líder local.")
        
        # Verifica se houve falha na replicação
        for servidor_id, res in all_results.items():
            if servidor_id != local_id and not res['sucesso']:
                print(f"⚠️ Aviso: Falha na replicação para o {servidor_id}. (Motivo: {res['mensagem']})")
                
    else:
        msg = local_result['mensagem'] if local_result else "ID do servidor local não encontrado no config."
        print(f"❌ Falha: Não foi possível remover no líder local ({local_id}).")
        print(f"Detalhes: {msg}")
        
    print("-----------------------------\n")