import psycopg2
from config import SERVERS, ALL_SERVERS, LOCAL_SERVERS 
from prettytable import PrettyTable
from collections import defaultdict

DBNAME_KEY = 'dbname'

def connect_to_db(servidor_id):
    """Conecta ao banco de dados específico, excluindo a chave 'tipo'."""
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
        # Silenciar a mensagem de erro se a Máquina A estiver offline
        # print(f"❌ Erro de conexão com o servidor {servidor_id}: {e}")
        return None

def visualizar_estado():
    """Conecta aos servidores LOCAIS e exibe o estado das matrículas em tabelas separadas."""

    print("--- Visualização do Estado Local do Sistema ---")
    
    for servidor_id in LOCAL_SERVERS:
        conn = connect_to_db(servidor_id)
        
        if conn:
            cursor = conn.cursor()
            
            try:
                # 1. Consulta SQL: Busca todas as matrículas
                cursor.execute("""
                    SELECT 
                        d.nome AS disciplina, 
                        d.vagas_totais, 
                        m.nome_aluno,
                        m.timestamp_matricula,
                        m.status
                    FROM matriculas m
                    JOIN disciplinas d ON m.disciplina_id = d.id
                    ORDER BY d.nome, m.timestamp_matricula;
                """)
                
                rows = cursor.fetchall()
                
                print(f"\n--- Servidor: {servidor_id} ---")
                
                if not rows:
                    print("Nenhuma matrícula encontrada nesta base de dados.")
                    
                    # Se não há matrículas, exibe apenas as disciplinas vazias (melhor visualização)
                    cursor.execute("SELECT nome, vagas_totais FROM disciplinas ORDER BY nome;")
                    disciplinas_vazias = cursor.fetchall()
                    if disciplinas_vazias:
                         print("\n--- Catálogo de Disciplinas (Sem Matrículas) ---")
                         for nome, vagas in disciplinas_vazias:
                              print(f"Disciplina: {nome} (Vagas Totais: {vagas})")
                    return

                # 2. Agrupamento: Organiza as matrículas por disciplina
                disciplinas_data = defaultdict(list)
                disciplinas_vagas = {} # Para armazenar vagas
                
                for row in rows:
                    disciplina_nome, vagas, aluno, timestamp, status = row
                    disciplinas_data[disciplina_nome].append((aluno, timestamp, status))
                    disciplinas_vagas[disciplina_nome] = vagas
                
                # 3. Impressão Separada: Cria uma tabela para cada disciplina
                for disciplina_nome in sorted(disciplinas_data.keys()):
                    
                    vagas = disciplinas_vagas[disciplina_nome]
                    print(f"\nDisciplina: {disciplina_nome} (Vagas Totais: {vagas})")
                    
                    table = PrettyTable()
                    table.field_names = ["Aluno", "Timestamp", "Status"]
                    
                    for aluno, timestamp, status in disciplinas_data[disciplina_nome]:
                        # Formata o timestamp para exibição
                        ts_str = timestamp.strftime("%Y-%m-%d %H:%M:%S") 
                        table.add_row([aluno, ts_str, status])
                    
                    print(table)
                
            except psycopg2.Error as e:
                print(f"❌ Erro SQL ao consultar {servidor_id}: {e}")
            finally:
                if 'cursor' in locals() and cursor:
                    cursor.close()
                if 'conn' in locals() and conn:
                    conn.close()
        else:
            print(f"--- Servidor: {servidor_id} ---")
            print("❌ Servidor inacessível ou offline.")

if __name__ == '__main__':
    visualizar_estado()