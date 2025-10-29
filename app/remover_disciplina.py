import psycopg2
import argparse
from config import SERVERS, ALL_SERVERS

def remover_disciplina_no_servidor(servidor_id, disciplina_nome):
    """Conecta e remove a disciplina em um único servidor."""
    config = SERVERS.get(servidor_id)
    connect_args = {k: v for k, v in config.items() if k != 'tipo'}
    connect_args['connect_timeout'] = 5 
    
    conn = None
    try:
        conn = psycopg2.connect(**connect_args)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM disciplinas WHERE nome = %s;", (disciplina_nome,))
        
        if cursor.rowcount > 0:
            conn.commit()
            return True, "SUCESSO"
        else:
            return False, "Disciplina não encontrada."

    except psycopg2.OperationalError:
        return False, "FALHA DE CONEXÃO (servidor offline)."
    except Exception as e:
        return False, f"ERRO INESPERADO: {e}"
    finally:
        if conn: conn.close()

def remover_disciplina(disciplina_nome):
    """Tenta remover a disciplina em todos os líderes, mas foca o feedback na ação local."""
    
    local_id = ALL_SERVERS[0] 
    
    print(f"\nTentando remover disciplina: '{disciplina_nome}'")
    
    all_results = {}
    
    for servidor_id in ALL_SERVERS:
        sucesso, mensagem = remover_disciplina_no_servidor(servidor_id, disciplina_nome)
        all_results[servidor_id] = {'sucesso': sucesso, 'mensagem': mensagem}

    local_result = all_results.get(local_id)
    
    print("\n--- Resultado da Operação ---")

    if local_result and local_result['sucesso']:
        print("✅ Removido com sucesso.")
        
        for servidor_id, res in all_results.items():
            if servidor_id != local_id and not res['sucesso'] and 'FALHA DE CONEXÃO' not in res['mensagem']:
                print(f"⚠️ Aviso: Falha na replicação para o {servidor_id}. (Motivo: {res['mensagem']})")
                
    else:
        msg = local_result['mensagem'] if local_result else "ID do servidor local não encontrado no config."
        print(f"❌ Falha: Não foi possível remover no líder local ({local_id}).")
        print(f"Detalhes: {msg}")
        
    print("-----------------------------\n")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Remove uma disciplina em todos os líderes.')
    parser.add_argument('--nome', required=True, help='Nome da disciplina a ser removida.')
    
    args = parser.parse_args()
    remover_disciplina(args.nome)