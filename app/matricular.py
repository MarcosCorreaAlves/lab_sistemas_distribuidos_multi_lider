import psycopg2
import argparse
import time
from config import SERVERS, ALL_SERVERS, LOCAL_SERVERS 

# --- CONSTANTES ---
STATUS_ACEITA = 'ACEITA'
STATUS_REJEITADA = 'REJEITADA'

# --- FUNÇÕES DE CONEXÃO E UTILIDADES ---

def connect_to_db(servidor_id):
    """Conecta ao banco de dados específico."""
    config = SERVERS.get(servidor_id)
    if not config:
        raise ValueError(f"Configuração do servidor {servidor_id} não encontrada.")
    
    connect_args = {k: v for k, v in config.items() if k != 'tipo'}
    connect_args['connect_timeout'] = 5
    
    try:
        conn = psycopg2.connect(**connect_args)
        return conn
    except psycopg2.OperationalError:
        return None

def obter_disciplina_id_e_vagas(conn, disciplina_nome):
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

# --- LÓGICA DE CONSULTA DE ESTADO E DESEMPATE ---

def consultar_estado(disciplina_id):
    """
    Consulta o estado de todas as matrículas para a disciplina em todos os líderes,
    garante a consistência do timestamp (tzinfo) e remove duplicatas.
    Retorna: [(id, nome, ts_naive, status), ...]
    """
    todos_registros = []
    
    for servidor_id in ALL_SERVERS:
        conn = connect_to_db(servidor_id)
        if conn:
            cursor = conn.cursor()
            try:
                # Seleciona o ID da matrícula também para a atualização de status
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
                
                # Prepara os registros, aplicando a correção de fuso horário (tzinfo)
                registros_corrigidos = []
                for matricula_id, nome, timestamp_db, status in registros:
                    # Aplica a correção tzinfo=None (necessária para comparação)
                    if timestamp_db and timestamp_db.tzinfo is not None:
                        timestamp_naive = timestamp_db.replace(tzinfo=None)
                    else:
                        timestamp_naive = timestamp_db
                        
                    # Retornamos o ID para uso na atualização de status
                    registros_corrigidos.append((matricula_id, nome, timestamp_naive, status))
                
                todos_registros.extend(registros_corrigidos)
            finally:
                cursor.close()
                conn.close()

    # DEDUPLICAÇÃO
    registros_unicos = set(todos_registros) 
    registros_finais = list(registros_unicos)
    
    # Ordena pelo timestamp_naive (índice 2 na tupla (id, nome, ts, status))
    registros_finais.sort(key=lambda x: x[2])
    
    return registros_finais

# --- FUNÇÃO CENTRAL DE REAVALIAÇÃO ---

def reavaliar_posicao(lider_destino, disciplina_id, vagas_totais, nova_tentativa=None):
    """
    Reavalia o status de todos os alunos na fila (incluindo uma nova tentativa, se houver).
    Retorna o status da nova tentativa (se for o caso) e a lista de updates necessários.
    """
    
    registros_atuais = consultar_estado(disciplina_id)
    updates_a_replicar = []
    
    if nova_tentativa:
        # Adiciona a nova tentativa ao final da fila para ser ordenada
        # nova_tentativa: (id, nome, ts_naive, 'PENDENTE')
        registros_atuais.append(nova_tentativa)
        registros_atuais.sort(key=lambda x: x[2]) # Ordena pelo ts_naive
        
    posicao_na_fila = 0
    status_final = None

    # Itera sobre a lista ORDENADA para reavaliar o status de TODOS
    for i, (old_id, nome, ts, status_antigo) in enumerate(registros_atuais):
        posicao = i + 1
        status_calculado = STATUS_ACEITA if posicao <= vagas_totais else STATUS_REJEITADA
        
        is_nova_tentativa = nova_tentativa and old_id == nova_tentativa[0]
        
        if is_nova_tentativa:
            status_final = status_calculado
            posicao_na_fila = posicao
            print(f"Aluno {nome} (Novo) -> Status Final: {status_final} (Posição: {posicao}/{vagas_totais})")
            
        elif status_calculado != status_antigo:
            updates_a_replicar.append((old_id, nome, status_calculado, ts))
            print(f"Status Atualizado: {nome} mudou de {status_antigo} para {status_calculado}")
    
    return status_final, posicao_na_fila, updates_a_replicar


# --- FUNÇÃO PRINCIPAL DE MATRÍCULA ---

def matricular_aluno(lider_entrada, aluno_nome, disciplina_nome):
    """
    Processa a matrícula, aplica regras de negócio, reavalia e replica.
    """
    
    conn = connect_to_db(lider_entrada)
    if not conn:
        print(f"❌ Matrícula falhou: Líder {lider_entrada} está offline.")
        return

    cursor = conn.cursor()
    
    try:
        # A. OBTER INFO DA DISCIPLINA
        disciplina_id, vagas_totais = obter_disciplina_id_e_vagas(conn, disciplina_nome)
        if not disciplina_id:
            print(f"❌ Matrícula falhou: Disciplina '{disciplina_nome}' não encontrada.")
            return

        # B. VERIFICAÇÃO DE UNICIDADE (CORRIGIDA): Impede qualquer nova matrícula se já houver um registro
        registros_atuais = consultar_estado(disciplina_id)
        
        # <<<<<<<<<<<<<<< CORREÇÃO: Verifica QUALQUER registro, não apenas ACEITO >>>>>>>>>>>>>>>>>
        alunos_existentes = {nome for id, nome, ts, status in registros_atuais}

        if aluno_nome in alunos_existentes:
            print(f"❌ REJEITADA! Aluno {aluno_nome} já possui um registro de matrícula/tentativa (ACEITA ou REJEITADA) na {disciplina_nome}.")
            return

        # C. GERAR DADOS DA NOVA MATRÍCULA
        cursor.execute("SELECT gen_random_uuid(), NOW() AT TIME ZONE 'UTC'")
        matricula_id, timestamp_utc = cursor.fetchone()
        timestamp_naive = timestamp_utc.replace(tzinfo=None)
        
        # Prepara a tentativa para a função de reavaliação
        nova_tentativa = (matricula_id, aluno_nome, timestamp_naive, 'PENDENTE')

        # D. LÓGICA DE FILA E REAVALIAÇÃO
        status_final, posicao_na_fila, updates_a_replicar = reavaliar_posicao(
            lider_entrada, disciplina_id, vagas_totais, nova_tentativa
        )
        
        # E. PREPARAÇÃO DOS DADOS PARA INSERÇÃO E REPLICAÇÃO
        matr_a_inserir = (matricula_id, disciplina_id, aluno_nome, timestamp_utc, status_final)
        
        insert_query = """
            INSERT INTO matriculas (id, disciplina_id, nome_aluno, timestamp_matricula, status)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (id) DO NOTHING
        """
        update_query = "UPDATE matriculas SET status = %s WHERE id = %s"
        
        # F. APLICAÇÃO NO LÍDER LOCAL
        
        # 1. Inserir a NOVA matrícula
        cursor.execute(insert_query, matr_a_inserir)
        
        # 2. Atualizar status de matrículas antigas que mudaram
        for old_id, nome, novo_status, ts in updates_a_replicar:
            cursor.execute(update_query, (novo_status, old_id))
            
        conn.commit()
        
        # G. REPLICAÇÃO MULTI-LÍDER
        print("\n--- Replicação de Matrícula ---")
        
        replicacoes_pendentes = [(insert_query, matr_a_inserir)]
        for old_id, nome, novo_status, ts in updates_a_replicar:
             replicacoes_pendentes.append((update_query, (novo_status, old_id)))

        for servidor_id in ALL_SERVERS:
            if servidor_id == lider_entrada:
                continue
                
            replica_conn = connect_to_db(servidor_id)
            if replica_conn:
                replica_cursor = replica_conn.cursor()
                try:
                    for query, data in replicacoes_pendentes:
                        replica_cursor.execute(query, data)
                        
                    replica_conn.commit()
                    print(f"➡️ Replicação SUCESSO (Nova matrícula + {len(updates_a_replicar)} updates) para o Líder {servidor_id}.")
                except Exception as e:
                    print(f"❌ Erro ao replicar para {servidor_id}: {e}")
                    replica_conn.rollback()
                finally:
                    if replica_cursor: replica_cursor.close()
                    if replica_conn: replica_conn.close()
            else:
                print(f"❌ Falha de Conexão: Líder {servidor_id} offline. (Replicação pendente)")

        # H. Exibir resultado da nova tentativa
        print(f"\nResultado da Matrícula (Líder {lider_entrada}):")
        if status_final == STATUS_ACEITA:
            print(f"✅ SUCESSO! Aluno {aluno_nome} aceito na {disciplina_nome}. (Posição: {posicao_na_fila}/{vagas_totais})")
        else:
            print(f"❌ REJEITADA! Aluno {aluno_nome} rejeitado. Vagas esgotadas. (Posição: {posicao_na_fila}/{vagas_totais})")

    except psycopg2.Error as e:
        conn.rollback()
        print(f"❌ Erro PostgreSQL durante a matrícula: {e}")
    except Exception as e:
        print(f"❌ Erro inesperado: {e}")
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Script para matricular alunos no sistema distribuído.')
    
    parser.add_argument('--aluno', required=True, type=str,
                        help='Nome do aluno a ser matriculado.')
    parser.add_argument('--disciplina', required=True, type=str,
                        help='Nome da disciplina para matrícula.')
    
    args = parser.parse_args()

    if not LOCAL_SERVERS:
        print("❌ ERRO DE CONFIGURAÇÃO: LOCAL_SERVERS não está definido no config.py.")
        exit(1)
        
    lider_entrada = LOCAL_SERVERS[0]
    
    print(f"⏳ Tentando matricular {args.aluno} (Disciplina: {args.disciplina}) via Líder {lider_entrada}...")
    
    matricular_aluno(lider_entrada, args.aluno, args.disciplina)