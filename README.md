# Attendance Manager - Gerenciador de Convidados para Festas e Eventos

O Attendance Manager é um sistema web robusto para gerenciar listas de convidados de festas e eventos, com funcionalidades avançadas como geração de QR codes, check-in em tempo real e estatísticas detalhadas.

## Funcionalidades Principais

*   **Gerenciamento de Convidados:**
    *   Adicionar, visualizar e remover convidados.
    *   Controle manual do status de entrada (marcar como entrou/não entrou).
*   **Geração de QR Code Personalizado:**
    *   QR codes únicos gerados para cada convidado, com o nome embutido visualmente.
    *   Imagens de QR code armazenadas no servidor e disponíveis para download.
*   **Check-in por QR Code:**
    *   Página dedicada (`/scanner`) para check-in rápido via câmera do dispositivo.
    *   Feedback visual e sonoro durante o check-in.
    *   Lógica de cooldown para evitar processamento repetido de QR codes.
*   **Estatísticas do Evento:**
    *   Número total de convidados, contagem de entradas e não-entradas.
    *   Porcentagem de comparecimento.
    *   Gráficos de pizza para visualização de dados.
*   **Exportação de Dados:**
    *   Exportação da lista de convidados em formato CSV e PDF.
    *   PDFs incluem estatísticas e gráficos detalhados.
*   **Colaboração em Eventos:**
    *   Compartilhamento de eventos com outros usuários para gerenciamento colaborativo.
*   **Interface Responsiva:**
    *   Design adaptado para desktops e dispositivos móveis.

## Tecnologias Utilizadas

*   **Backend:**
    *   Python 3
    *   Flask (servidor web e API)
    *   Flask-SQLAlchemy (banco de dados relacional)
    *   Flask-Login (autenticação de usuários)
    *   qrcode (geração de QR codes)
    *   Pillow (manipulação de imagens)
*   **Frontend:**
    *   HTML5, CSS3 e JavaScript (Vanilla JS)
    *   html5-qrcode (leitura de QR codes via câmera)
    *   Chart.js (gráficos interativos)
*   **Banco de Dados:**
    *   SQLite (armazenamento local)

## Setup e Execução do Projeto Localmente

### Pré-requisitos

*   Python 3.7 ou superior.
*   `pip` (gerenciador de pacotes Python).
*   Um arquivo de fonte TrueType (TTF), como `Montserrat-Regular.ttf`.

### Passos para Configuração

1.  **Clone o Repositório:**
    ```bash
    git clone <url_do_repositorio>
    cd attendance_manager
    ```

2.  **Crie e Ative um Ambiente Virtual:**
    ```bash
    python -m venv venv
    source venv/bin/activate  # macOS/Linux
    venv\Scripts\activate   # Windows
    ```

3.  **Instale as Dependências:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Configure o Ambiente:**
    *   Crie um arquivo `.env` na raiz do projeto com as seguintes variáveis:
        ```env
        SECRET_KEY=uma_chave_secreta
        ABACATE_API_KEY=sua_chave_api
        ```
    *   Certifique-se de que o arquivo de fonte TTF está na raiz do projeto.

5.  **Execute a Aplicação:**
    ```bash
    python app.py
    ```
    Acesse `http://localhost:5000/` no navegador.

6.  **Teste o Scanner em Dispositivos Móveis:**
    *   Use `ngrok` para expor o servidor local via HTTPS:
        ```bash
        ./ngrok http 5000
        ```
    *   Acesse a URL gerada no navegador do dispositivo móvel.

## Melhorias Futuras

*   Envio de convites por email com QR codes.
*   Estatísticas mais detalhadas e personalizáveis.
