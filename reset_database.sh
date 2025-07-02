#!/bin/bash

# Cores para facilitar a leitura da saída
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # Sem Cor

# Função para checar se um comando foi bem-sucedido
check_success() {
    if [ $? -ne 0 ]; then
        echo -e "${RED}[ERRO] O passo '$1' falhou. Abortando o script.${NC}"
        exit 1
    fi
}

echo -e "${GREEN}==================================================${NC}"
echo -e "${GREEN}=== SCRIPT DE RESET DO BANCO DE DADOS FLASK ===${NC}"
echo -e "${GREEN}==================================================${NC}"

# --- VERIFICAÇÕES INICIAIS ---
if [ ! -f "manage.py" ]; then
    echo -e "${RED}[ERRO] O arquivo 'manage.py' não foi encontrado.${NC}"
    echo "Por favor, execute este script a partir da pasta raiz do seu projeto Flask."
    exit 1
fi

if [ -z "$VIRTUAL_ENV" ]; then
    echo -e "${YELLOW}[AVISO] Nenhum ambiente virtual (venv) parece estar ativado.${NC}"
    read -p "Deseja continuar mesmo assim? (s/n): " choice
    if [[ ! "$choice" =~ ^[sS]$ ]]; then
        echo "Script abortado pelo usuário."
        exit 0
    fi
fi

echo -e "${YELLOW}[AVISO] Este script irá apagar TODAS as tabelas do seu banco de dados.${NC}"
read -p "Pressione [Enter] para continuar ou CTRL+C para cancelar..."

# --- PASSO 1: LIMPEZA ---
echo -e "\n${GREEN}--> PASSO 1: Limpando o ambiente local e o banco de dados...${NC}"

echo "Removendo diretório 'migrations' antigo..."
rm -rf migrations
check_success "Remover 'migrations'"

echo "Limpando tabelas do banco de dados (Método Robusto)..."
# Bloco de código Python que será executado para limpar o BD.
# Usar 'python -c' é mais confiável que tentar usar um shell interativo.
PYTHON_CLEAN_SCRIPT="
from app import app, db
from sqlalchemy import text
import sys

print('--- Entrando no contexto da aplicação Flask para limpar o BD ---')
with app.app_context():
    try:
        db.drop_all()
        with db.engine.connect() as connection:
            connection.execute(text('DROP TABLE IF EXISTS alembic_version;'))
            connection.commit()
        print('--- Banco de dados limpo com sucesso ---')
    except Exception as e:
        print(f'Ocorreu um erro durante a limpeza do BD: {e}', file=sys.stderr)
        sys.exit(1)
"
# Executa o script de limpeza
python -c "$PYTHON_CLEAN_SCRIPT"
check_success "Limpeza do Banco de Dados"


# --- PASSO 2: CRIAR MIGRAÇÕES ---
echo -e "\n${GREEN}--> PASSO 2: Criando um novo histórico de migrações...${NC}"

echo "Executando: python manage.py db init"
python manage.py db init
check_success "'db init'"

echo "Executando: python manage.py db migrate"
python manage.py db migrate -m "Reset e criação inicial das tabelas"
check_success "'db migrate'"

echo "Executando: python manage.py db upgrade"
python manage.py db upgrade
check_success "'db upgrade'"


# --- FINALIZAÇÃO ---
echo -e "\n${GREEN}==================================================${NC}"
echo -e "${GREEN}         PROCESSO CONCLUÍDO COM SUCESSO!        ${NC}"
echo -e "${GREEN}==================================================${NC}"
echo "Seu banco de dados foi resetado e as tabelas foram criadas."
echo "Você já pode iniciar sua aplicação com 'python app.py'."

exit 0