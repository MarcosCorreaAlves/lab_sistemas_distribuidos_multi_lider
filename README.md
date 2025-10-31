# 📚 Sistema de Matrículas Distribuído - Laboratório de Consistência Multi-Líder

Este projeto simula um sistema de gerenciamento de matrículas acadêmicas em um ambiente distribuído, utilizando dois ou mais bancos de dados PostgreSQL em uma arquitetura de replicação **Multi-Líder**.

O principal foco é o estudo e a resolução de desafios de **consistência de dados**, **ordenação temporal (timestamps)** e **desempate de filas** em um cenário onde as transações podem ocorrer simultaneamente em diferentes nós.

---

## 🏗️ Arquitetura e Fluxo de Consistência

O sistema é composto por scripts de cliente Python que interagem com líderes de banco de dados orquestrados pelo Docker Compose.

### 1. Modelo de Dados Central (Tabela `matriculas`)

A tabela `matriculas` armazena o estado distribuído. O campo crucial para a consistência e ordenação é o `timestamp_matricula`, que utiliza o horário UTC para garantir que a ordem global das transações seja determinística, independentemente de qual líder a requisição atingiu primeiro.

### 2. Lógica Central de Desempate (Matrícula e Remoção)

A regra de negócio garante:
* **Unicidade:** Um aluno só pode ter um registro (tentativa) por disciplina.
* **Ordem:** O critério de desempate é **Time-Based (First-Come, First-Served - FCFS)**.

O processo de **Reavaliação de Status** (implementado em `matricular.py` e `remover.py`) é executado em cada transação de escrita (inserção ou deleção) e segue o fluxo:

1.  **Consulta Global:** O líder de entrada consulta **todos** os outros líderes para obter o estado completo da fila daquela disciplina.
2.  **Filtragem e Ordenação:** A lista de todas as matrículas é **filtrada** (para remover duplicatas históricas e garantir unicidade por aluno) e **ordenada** rigorosamente pelo `timestamp_matricula`.
3.  **Determinação de Status:** O sistema itera sobre a lista ordenada. As primeiras **`Vagas_Totais`** matrículas recebem o status `ACEITA`; as demais recebem `REJEITADA`.
4.  **Atualização e Replicação:** O líder de entrada aplica os *updates* de status necessários (e.g., promovendo um aluno de `REJEITADA` para `ACEITA` após uma remoção) e replica tanto a transação inicial quanto os *updates* de status para todos os outros líderes.

---

## 🛠️ Tecnologias Utilizadas

| Ferramenta | Tipo | Propósito |
| :--- | :--- | :--- |
| **Python 3** | Linguagem | Scripts de cliente e lógica de negócios. |
| **PostgreSQL** | SGBD | Bancos de dados distribuídos (Líder A e Líder B). |
| **Docker Compose** | Orquestração | Gerencia e isola os ambientes de banco de dados. |
| `psycopg2-binary` | Driver Python | Conexão Python/PostgreSQL. |

---

## 📂 Estrutura de Arquivos e Funções dos Scripts

Aqui está a descrição dos arquivos principais do projeto:

| Arquivo | Localização | Funcionalidade Principal |
| :--- | :--- | :--- |
| `docker-compose.yml` | Raiz | Define os serviços Docker (Líderes A, B, etc.) e mapeia volumes e redes. |
| `init-scripts/init.sql` | `init-scripts/` | Contém comandos SQL para criar a tabela `matriculas` e a extensão `uuid-ossp` em cada banco de dados. |
| `app/config.py` | `app/` | Armazena as credenciais de conexão (host, porta, usuário) para todos os líderes (A, B, etc.). |
| **`app/setup_database.py`** | `app/` | Script inicial. Cria o schema (`CREATE TABLE`) e insere as disciplinas iniciais no sistema. |
| **`app/matricular.py`** | `app/` | **Transação de Inserção.** Lógica principal para processar matrículas, verificar unicidade, reavaliar a fila de espera globalmente e replicar o resultado. |
| **`app/remover.py`** | `app/` | **Transação de Deleção.** Remove um aluno e dispara a reavaliação global para promover o próximo aluno da fila para `ACEITA`. |
| **`app/visualizar.py`** | `app/` | **Transação de Leitura.** Consulta o estado de todas as matrículas em **todos** os líderes para verificar a consistência e a ordenação da fila. |
| **`app/consultar_estado.py`** | `app/` | *(Auxiliar)* Função central de leitura que unifica a consulta do estado de matrículas em todos os líderes (usada em `matricular.py` e `remover.py`). |
| **`app/adicionar_disciplina.py`** | `app/` | Permite adicionar novas disciplinas ao sistema dinamicamente. |
| **`app/remover_disciplina.py`** | `app/` | Permite remover uma disciplina inteira do sistema. |
| **`app/relatorio_consolidado.py`** | `app/` | Gera um relatório unificado do estado do sistema a partir de todos os líderes. |
| **`app/visualizar_disciplinas.py`** | `app/` | Exibe uma lista das disciplinas cadastradas no sistema e suas vagas. |

---
