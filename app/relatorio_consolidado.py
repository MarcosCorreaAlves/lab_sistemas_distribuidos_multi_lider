import psycopg2
from config import SERVERS
from prettytable import PrettyTable
from collections import defaultdict

def connect_to_db(servidor_id='A'):
    """Conecta ao servidor líder (padrão é Líder A) para gerar o relatório."""
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
        print(f"❌ Erro de conexão com o servidor {servidor_id} ({config['host']}:{config['port']}). Verifique se está online.")
        return None

def gerar_relatorio_consolidado():
    """Gera um relatório completo das disciplinas, vagas e alunos matriculados (ACEITA e REJEITADA)."""
    
    conn = connect_to_db('A') 
    if not conn:
        return

    cursor = conn.cursor()
    
    try:

        cursor.execute("""
            SELECT 
                d.nome AS disciplina, 
                d.vagas_totais AS total_vagas, 
                m.nome_aluno,
                m.status,
                m.timestamp_matricula
            FROM 
                disciplinas d
            LEFT JOIN 
                matriculas m ON d.id = m.disciplina_id
            ORDER BY
                d.nome ASC, m.nome_aluno ASC;
        """)
        
        rows = cursor.fetchall()
        
        if not rows:
            print("Nenhum dado encontrado para gerar o relatório.")
            return

        relatorio = {} 
        
        for row in rows:
            disciplina, total_vagas, aluno, status, timestamp = row
            
            if disciplina not in relatorio:
                relatorio[disciplina] = {
                    'vagas': total_vagas,
                    'matriculados_aceitos': 0,
                    'todos_alunos': [] 
                }
            
            if aluno and status == 'ACEITA':
                relatorio[disciplina]['matriculados_aceitos'] += 1

            if aluno:
                relatorio[disciplina]['todos_alunos'].append({'nome': aluno, 'status': status})
        
        
        print("\n" + "="*80)
        print(f"{'RELATÓRIO CONSOLIDADO DE MATRÍCULAS E VAGAS':^80}")
        print("="*80 + "\n")

        disciplinas_ordenadas = sorted(relatorio.keys())

        for disc_nome in disciplinas_ordenadas:
            data = relatorio[disc_nome]
            vagas = data['vagas']
            aceitos = data['matriculados_aceitos']
            alunos_list = data['todos_alunos']
            
            vagas_restantes = vagas - aceitos
            
            alunos_list.sort(key=lambda x: x['nome'])
            
            print(f"| DISCIPLINA: {disc_nome} | Vagas Totais: {vagas} | Vagas Restantes: {vagas_restantes} |")
            print("—"*80)
            
            table = PrettyTable()
            table.field_names = [
                "Nº", 
                "Nome do Aluno (Ordem Alfabética)", 
                "Status da Matrícula"
            ]
            table.align = "l"
            
            for i, aluno_info in enumerate(alunos_list, 1):
                table.add_row([
                    i,
                    aluno_info['nome'],
                    aluno_info['status']
                ])
            
            if not alunos_list:
                 table.add_row(["—", "(Nenhuma matrícula registrada)", "—"])
            
            print(table)
            print("\n") 
            
    
    except psycopg2.Error as e:
        print(f"❌ Erro SQL ao gerar o relatório: {e}")
    except Exception as e:
        print(f"❌ Erro inesperado: {e}")
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

if __name__ == '__main__':
    gerar_relatorio_consolidado()