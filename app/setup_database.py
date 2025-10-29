import psycopg2
from config import SERVERS, ALL_SERVERS 
import time

DBNAME_KEY = 'dbname' 

def create_tables(cursor):
    """Cria as tabelas 'disciplinas' e 'matriculas' se não existirem."""
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS disciplinas (
            id SERIAL PRIMARY KEY,
            nome VARCHAR(100) NOT NULL UNIQUE,
            vagas_totais INTEGER NOT NULL
        );
    """)

    cursor.execute("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\";")
    
    # Adicionando ON DELETE CASCADE para garantir que a exclusão da disciplina apague as matrículas
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS matriculas (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            disciplina_id INTEGER REFERENCES disciplinas(id) ON DELETE CASCADE,
            nome_aluno VARCHAR(100) NOT NULL,
            timestamp_matricula TIMESTAMPTZ DEFAULT (NOW() AT TIME ZONE 'UTC'),
            status VARCHAR(20) DEFAULT 'ACEITA'
        );
    """)

def create_database_if_not_exists(servidor_config):
    """Conecta-se ao banco padrão 'postgres' e cria o banco de destino (ex: 'db_a')."""
    
    db_desejado = servidor_config[DBNAME_KEY]
    
    temp_config = {k: v for k, v in servidor_config.items()}
    temp_config[DBNAME_KEY] = 'postgres'

    conn_temp = None
    try:
        
        connect_args = {k: v for k, v in temp_config.items() if k not in ['tipo', 'dbname']}
        connect_args['dbname'] = 'postgres' 
        conn_temp = psycopg2.connect(**connect_args)
        conn_temp.autocommit = True
        cursor = conn_temp.cursor()
        
        # Verifica se o banco de dados já existe
        cursor.execute(f"SELECT 1 FROM pg_database WHERE datname='{db_desejado}'")
        if not cursor.fetchone():
            owner_user = servidor_config['user'] 
            cursor.execute(f"CREATE DATABASE {db_desejado} OWNER {owner_user};")
            print(f"✅ Banco de dados '{db_desejado}' criado com sucesso para o servidor.")
        
        cursor.close()
        return True

    except psycopg2.OperationalError as e:
        # Se falhar ao conectar ao DB 'postgres', o servidor está inacessível
        print(f"❌ Erro FATAL ao conectar ou criar banco temporário: {e}")
        return False
    
    finally:
        if conn_temp:
            conn_temp.close()


def setup():
    """Cria tabelas em todos os servidores e NÃO insere dados de teste."""
    
    for servidor in ALL_SERVERS: # <-- CORRIGIDO: Agora é 'for' minúsculo
        
        servidor_config = SERVERS[servidor]
        
        if not create_database_if_not_exists(servidor_config):
            print(f"⚠️ Pulando a configuração de tabelas para o servidor {servidor} devido à falha na criação do DB.")
            continue
        
        try:
            connect_args = {k: v for k, v in servidor_config.items() if k != 'tipo'}

            conn = psycopg2.connect(**connect_args)
            cursor = conn.cursor()
            
            create_tables(cursor)
            
            # Linha TRUNCATE REMOVIDA/COMENTADA: Não zera mais os dados ao rodar o setup
            # Linha de INSERÇÃO de "Robótica" REMOVIDA: Começa sem disciplinas
            
            conn.commit()
            cursor.close()
            conn.close()
            
            tipo = servidor_config['tipo'].upper()
            print(f"✅ Base de dados do {tipo} {servidor} configurada/verificada com sucesso (Tabelas criadas/atualizadas).")

        except psycopg2.OperationalError as e:
            print(f"❌ Erro de conexão com o servidor {servidor}: {e}")
            print("   DICA: Verifique a conectividade da rede (ping) e o firewall.")
        except Exception as e:
            print(f"❌ Erro ao configurar o servidor {servidor}: {e}")

if __name__ == "__main__":
    setup()