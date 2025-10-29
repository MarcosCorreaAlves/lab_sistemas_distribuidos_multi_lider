import psycopg2
from config import CONFIG, TODOS_SERVIDORES

def consultar():
    """Consulta o estado de todos os servidores e aplica a lógica de resolução de conflitos na leitura."""
    for servidor in TODOS_SERVIDORES:
        tipo = CONFIG[servidor]['tipo'].upper()
        print("\n" + "="*15 + f" ESTADO DO {tipo} {servidor} " + "="*15)
        try:
            conn = psycopg2.connect(**{k: v for k, v in CONFIG[servidor].items() if k != 'tipo'})
            cursor = conn.cursor()

            # Pega o número total de vagas
            cursor.execute("SELECT id, nome, vagas_totais FROM disciplinas WHERE nome = 'Robótica';")
            result = cursor.fetchone()
            if not result:
                print("Disciplina 'Robótica' não encontrada. Execute 'python app/setup_database.py' primeiro.")
                continue
            
            disciplina_id, nome_disciplina, vagas_totais = result

            # Pega todas as matrículas, ordenadas pela regra de conflito (timestamp mais antigo primeiro)
            cursor.execute("""
                SELECT nome_aluno, timestamp_matricula
                FROM matriculas
                WHERE disciplina_id = %s
                ORDER BY timestamp_matricula;
            """, (disciplina_id,))

            matriculas = cursor.fetchall()
            vagas_ocupadas = 0
            alunos_aceites = []

            print(f"Disciplina: {nome_disciplina} | Vagas Totais: {vagas_totais}")
            print("-"*50)
            print("Matrículas registadas na base de dados local:")

            if not matriculas:
                print("  (Nenhuma matrícula registada)")

            for i, (nome, ts) in enumerate(matriculas):
                
                if i < vagas_totais:
                    vagas_ocupadas += 1
                    alunos_aceites.append(nome)
                    print(f"  - {nome} ({ts.strftime('%H:%M:%S.%f')}) -> Vaga Válida")
                else:
                    print(f"  - {nome} ({ts.strftime('%H:%M:%S.%f')}) -> CONFLITO! Vaga Inválida (excedeu o limite)")

            print("-"*50)
            print(f"Resultado Final (Visão do {tipo} {servidor}):")
            print(f"  Vagas Ocupadas: {vagas_ocupadas}/{vagas_totais}")
            print(f"  Alunos Matriculados: {', '.join(alunos_aceites) or 'Nenhum'}")


            cursor.close()
            conn.close()

        except psycopg2.OperationalError as e:
            print(f"❌ Erro de conexão com o servidor {servidor}: {e}")
        except Exception as e:
            print(f"❌ Erro ao consultar o servidor {servidor}: {e}")

if __name__ == "__main__":
    consultar()

