
SERVERS = {
    'A': {
        'host': 'localhost',
        'port': 5432,
        'dbname': 'db_a',
        'user': 'user_a',
        'password': 'pass_a',
        'tipo': 'lider'
    },
    'B': {
        'host': '192.168.18.24', # IP da Máquina B
        'port': 5433,
        'dbname': 'db_b',
        'user': 'user_b',
        'password': 'pass_b',
        'tipo': 'lider'
    }
}

ALL_SERVERS = ['A', 'B']
LEADER_SERVERS = ['A', 'B'] 

LOCAL_SERVERS = ['A']