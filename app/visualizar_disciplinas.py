import psycopg2
from config import SERVERS
from prettytable import PrettyTable

def connect_to_db(servidor_id='A'):
    """Conecta ao servidor líder (padrão é Líder A) para leitura."""
    config = SERVERS.get(servidor_id)
    connect_args = {k: v for k, v in config.items() if k != 'tipo'}
    connect_args['connect_timeout'] = 5 
    try:
        conn = psycopg2.connect(**connect_args)
        return conn
    except psycopg2.OperationalError as e:
        print(f"❌ Erro de conexão com o Líder {servidor_id}. Verifique se está online.")
        return None

def visualizar_disciplinas():
    """Visualiza apenas o catálogo de disciplinas."""
    conn = connect_to_db('A') 
    if not conn:
        return

    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT id, nome, vagas_totais FROM disciplinas ORDER BY nome;")
        rows = cursor.fetchall()
        
        if not rows:
            print("Nenhuma disciplina encontrada no catálogo.")
            return

        table = PrettyTable()
        table.field_names = ["ID", "Disciplina", "Vagas Totais"]
        
        for row in rows:
            table.add_row(row)
        
        table.align = "l"
        print("\n=== Catálogo de Disciplinas ===")
        print(table)
        print("===============================\n")

    except psycopg2.Error as e:
        print(f"❌ Erro SQL: {e}")
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

if __name__ == '__main__':
    visualizar_disciplinas()