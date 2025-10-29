-- Habilita a extensão para gerar UUIDs (se necessário)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Tabela para guardar as disciplinas e o número de vagas
CREATE TABLE IF NOT EXISTS disciplinas (
    id SERIAL PRIMARY KEY,
    nome VARCHAR(100) NOT NULL UNIQUE,
    vagas_totais INT NOT NULL
);

-- Tabela para registar as matrículas dos alunos
CREATE TABLE IF NOT EXISTS matriculas (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(), -- Usa UUIDs
    disciplina_id INT REFERENCES disciplinas(id),
    nome_aluno VARCHAR(100) NOT NULL,
    timestamp_matricula TIMESTAMPTZ DEFAULT (NOW() AT TIME ZONE 'UTC'),
    status VARCHAR(20) DEFAULT 'ACEITA'
);
