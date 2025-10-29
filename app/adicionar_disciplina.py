import psycopg2
import argparse 
import time
from config import SERVERS, ALL_SERVERS
from psycopg2.extras import execute_values

DBNAME_KEY = 'dbname'

def connect_to_db(servidor_id):
    """Conecta ao banco de dados específico."""
    config = SERVERS.get(servidor_id)
    if not config:
        print(f"❌ Configuração do servidor {servidor_id} não encontrada.")
        return None
    
    
    connect_args = {k: v for k, v in config.items() if k != 'tipo'}
    connect_args['connect_timeout'] = 5 
    
    try:
        conn = psycopg2.connect(**connect_args)
        return conn
    except psycopg2.OperationalError as e:
        
        return None

def adicionar_disciplina(disciplina_nome, vagas):
    """Adiciona uma nova disciplina em todos os servidores líderes."""
    
    print(f"--- Tentando adicionar disciplina: {disciplina_nome} ({vagas} vagas) ---")
    
    success_count = 0
    total_servers = len(ALL_SERVERS)
    
    for servidor_id in ALL_SERVERS:
        conn = connect_to_db(servidor_id)
        
        
        if not conn:
            print(f"❌ Falha de Conexão: O servidor {servidor_id} está inacessível. O dado será inserido nos líderes ativos.")
            continue 
        
        cursor = conn.cursor()
        
        try:
            
            cursor.execute("SELECT COUNT(*) FROM disciplinas WHERE nome = %s", (disciplina_nome,))
            if cursor.fetchone()[0] > 0:
                print(f"⚠️ Disciplina '{disciplina_nome}' já existe no servidor {servidor_id}. Pulando.")
                conn.rollback()
                continue

            
            insert_query = """
                INSERT INTO disciplinas (nome, vagas_totais)
                VALUES (%s, %s);
            """
            cursor.execute(insert_query, (disciplina_nome, vagas))
            
            conn.commit()
            success_count += 1
            
        except psycopg2.Error as e:
            conn.rollback()
            print(f"❌ Erro PostgreSQL ao adicionar em {servidor_id}: {e}") 
        except Exception as e:
            print(f"❌ Erro inesperado em {servidor_id}: {e}")
        finally:
            if cursor: cursor.close()
            if conn: conn.close()

 
    if success_count == total_servers:
        print(f"✅ Sucesso: Disciplina '{disciplina_nome}' com {vagas} vagas")
    elif success_count > 0:
        print(f"⚠️ Aviso: Disciplina '{disciplina_nome}' com {vagas} vagas adicionada em {success_count} de {total_servers} líderes (verificar erros acima).")
    else:
        print(f"❌ Falha: Disciplina '{disciplina_nome}' não foi adicionada em nenhum líder (verificar erros acima).")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Script para adicionar uma nova disciplina no sistema distribuído.')
    parser.add_argument('--nome', required=True, type=str, 
                        help='Nome da disciplina a ser adicionada.')
    parser.add_argument('--vagas', required=True, type=int, 
                        help='Número de vagas para a disciplina.')
    
    args = parser.parse_args()
    
    adicionar_disciplina(args.nome, args.vagas)