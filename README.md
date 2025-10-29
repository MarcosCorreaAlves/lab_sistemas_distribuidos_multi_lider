# 📚 Sistema de Matrículas Distribuído - Laboratório de Consistência Multi-Líder

Este projeto simula um sistema de gerenciamento de matrículas acadêmicas em um ambiente distribuído, utilizando dois ou mais bancos de dados PostgreSQL em uma arquitetura de replicação **Multi-Líder**. O objetivo principal é estudar e resolver desafios de **consistência de dados**, **ordenação temporal (timestamps)** e **desempate de filas** em um cenário de processamento distribuído.

O sistema garante a unicidade da matrícula do aluno por disciplina e reavalia dinamicamente o status (`ACEITA` ou `REJEITADA`) dos alunos na fila sempre que uma nova matrícula é feita ou uma vaga é liberada.

---

## 🛠️ Tecnologias Utilizadas

- **Python 3:** Linguagem principal para os scripts de cliente e lógica de negócios.
- **PostgreSQL:** SGBD robusto utilizado para os nós (Líderes A e B) do sistema distribuído.
- **Docker & Docker Compose:** Utilizados para orquestrar e isolar os ambientes de banco de dados e garantir a reprodutibilidade.
- **`psycopg2-binary`:** Driver Python para conexão com o PostgreSQL.

---

## ⚙️ Configuração e Inicialização

### Pré-requisitos

1. **Docker & Docker Compose:** Instalados e em execução.
2. **Python 3:** Instalado no ambiente de execução dos scripts.
3. **Dependências Python:**

```bash
pip install psycopg2-binary prettytable python-dateutil
