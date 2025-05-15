# Attendance Manager - Gerenciador de Convidados para Festas e Eventos

O Attendance Manager é um sistema web simples para gerenciar a lista de convidados de uma festa ou evento, gerar QR codes únicos para check-in, e acompanhar o comparecimento em tempo real.

## Funcionalidades Principais

*   **Gerenciamento de Convidados:**
    *   Adicionar novos convidados à lista.
    *   Visualizar a lista completa de convidados.
    *   Remover convidados da lista.
*   **Geração de QR Code Único:**
    *   Para cada convidado adicionado, um QR code único é gerado (baseado em um hash do nome).
    *   O nome do convidado é embutido visualmente abaixo do QR code na imagem gerada.
    *   Os QR codes são armazenados como imagens `.png` no servidor.
    *   Possibilidade de baixar a imagem do QR code gerado.
*   **Check-in por QR Code:**
    *   Uma página dedicada (`/scanner`) permite o check-in rápido de convidados usando a câmera do dispositivo para escanear os QR codes.
    *   Feedback visual (✓ para sucesso, ✗ para erro, ⓘ para "já entrou") e sonoro (beep) durante o check-in.
    *   Cooldown lógico para evitar processamento repetido do mesmo QR code em rápida sucessão.
    *   A página principal (`/`) também possui uma funcionalidade de scanner rápido para testes.
*   **Controle de Entrada Manual:**
    *   Possibilidade de alterar manualmente o status de entrada de um convidado (marcar como entrou/não entrou) diretamente na lista de convidados.
*   **Estatísticas do Evento:**
    *   Visualização na página principal do número total de convidados.
    *   Contagem de quantos convidados já entraram.
    *   Contagem de quantos ainda não entraram.
    *   Porcentagem de comparecimento.
    *   Gráfico de pizza representando a distribuição de comparecimento (Entraram vs. Não Entraram).
*   **Interface Responsiva:**
    *   Layout adaptado para funcionar em desktops e dispositivos móveis.

## Tecnologias Utilizadas

*   **Backend:**
    *   Python 3
    *   Flask (para o servidor web e API)
    *   Flask-SQLAlchemy (para interação com o banco de dados)
    *   qrcode (para gerar a matriz do QR code)
    *   Pillow (para manipular imagens e adicionar texto aos QR codes)
*   **Frontend:**
    *   HTML5
    *   CSS3 (com design responsivo)
    *   JavaScript (Vanilla JS para interações e lógica do cliente)
    *   html5-qrcode (biblioteca JS para leitura de QR code via câmera)
    *   Chart.js (biblioteca JS para o gráfico de pizza de estatísticas)
*   **Banco de Dados:**
    *   SQLite (para simplicidade e portabilidade)
 
## Setup e Execução do Projeto Localmente

### Pré-requisitos

*   Python 3.7 ou superior instalado.
*   `pip` (gerenciador de pacotes Python) instalado.
*   Um arquivo de fonte TrueType (TTF), por exemplo, `Montserrat-Regular.ttf` ou `arial.ttf`. Coloque este arquivo na raiz do projeto (mesmo nível que `app.py`). O código em `app.py` tentará carregar "Montserrat-Regular.ttf" por padrão; ajuste o nome do arquivo em `app.py` se usar outra fonte.

### Passos para Configuração

1.  **Clone o Repositório (ou crie a estrutura de pastas e copie os arquivos):**
    ```bash
    # Se estiver usando git
    # git clone <url_do_repositorio>
    # cd attendance_manager
    ```

2.  **Crie e Ative um Ambiente Virtual (Recomendado):**
    ```bash
    python -m venv venv
    # No Windows:
    # venv\Scripts\activate
    # No macOS/Linux:
    # source venv/bin/activate
    ```

3.  **Instale as Dependências Python:**
    Certifique-se de que o arquivo `requirements.txt` está atualizado com:
    ```
    Flask
    Flask-SQLAlchemy
    qrcode
    Pillow
    # Adicione outras dependências se tiver usado, como Flask-Login, etc.
    ```
    Então, execute:
    ```bash
    pip install -r requirements.txt
    ```

4.  **Verifique o Arquivo de Fonte:**
    *   Confirme que o arquivo de fonte TTF (ex: `Montserrat-Regular.ttf`) está na raiz do projeto.
    *   Verifique em `app.py`, na função `add_guest`, a linha:
        ```python
        font_file_name = "Montserrat-Regular.ttf" 
        # ...
        font = ImageFont.truetype(font_file_name, font_size)
        ```
        Ajuste `font_file_name` se necessário.

5.  **Execute a Aplicação Flask:**
    ```bash
    python app.py
    ```
    O servidor Flask iniciará, geralmente em `http://127.0.0.1:5000/` ou `http://localhost:5000/`. Se você configurou `host='0.0.0.0'`, ele também estará acessível pelo IP da sua máquina na rede local.

6.  **Acesse no Navegador:**
    *   Abra seu navegador e vá para `http://localhost:5000/` para acessar a página de gerenciamento.
    *   Acesse `http://localhost:5000/scanner` para a página dedicada ao scanner.

### Testando o Scanner em Dispositivos Móveis (Requer HTTPS)

Para que a funcionalidade de scanner da câmera funcione em dispositivos móveis (como iPhone ou Android), a página precisa ser acessada via HTTPS.

1.  **Use `ngrok` (Recomendado para desenvolvimento local):**
    *   Baixe o ngrok: [ngrok.com/download](https://ngrok.com/download)
    *   Com seu servidor Flask rodando (ex: na porta 5000), abra outro terminal e execute:
        ```bash
        ./ngrok http 5000
        ```
    *   O ngrok fornecerá uma URL pública `https://xxxxxxx.ngrok.io`.
    *   Acesse esta URL `https://` no navegador do seu dispositivo móvel. A câmera deverá funcionar após conceder as permissões.

## Possíveis Melhorias Futuras

*   Autenticação de administrador para a página de gerenciamento.
*   Exportar/Importar lista de convidados.
*   Suporte a múltiplos eventos.
*   Envio de convites com QR code por email.
*   Estatísticas mais detalhadas e gráficos.
