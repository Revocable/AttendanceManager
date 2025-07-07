# QRPass: A Revolução na Gestão de Eventos e Festas! 🚀

Chega de planilhas e filas! O QRPass é a solução completa e moderna para você gerenciar seus eventos, festas e convidados de forma inteligente, segura e totalmente digital. Do convite à análise pós-evento, tenha o controle na palma da sua mão.

## ✨ Por Que o QRPass é a Escolha Certa?

*   **Simplicidade e Poder:** Uma interface intuitiva que esconde um motor robusto, capaz de lidar com eventos de qualquer tamanho.
*   **Experiência Sem Atritos:** Convidados e organizadores desfrutam de um fluxo suave, desde a compra do ingresso até o check-in.
*   **Inteligência em Tempo Real:** Tome decisões baseadas em dados precisos, acompanhando o pulso do seu evento a cada segundo.
*   **Design Moderno:** Uma experiência visual agradável e responsiva, adaptada para qualquer dispositivo.

## 🌟 Funcionalidades que Você Vai Amar:

### 🎟️ **Gestão Completa de Convidados e Ingressos**
*   **Listas Dinâmicas:** Adicione convidados gratuitos ou gere links de pagamento personalizados para cada um.
*   **Status Detalhado:** Acompanhe o status de entrada (presente/ausente) e de pagamento (pago, pendente, gratuito, falhou) de cada convidado.
*   **Edição Rápida:** Altere dados de convidados a qualquer momento.
*   **Meus Ingressos:** Uma área dedicada para o usuário visualizar todos os ingressos que comprou ou foi convidado.

### 🛡️ **QR Codes Inteligentes e Check-in Descomplicado**
*   **QR Codes Únicos:** Cada convidado recebe um QR Code exclusivo, gerado dinamicamente com o nome do convidado e o logo da sua festa, garantindo segurança e personalização.
*   **Scanner Web Integrado:** Transforme qualquer smartphone ou tablet em um leitor de QR Code profissional. Sem apps para baixar, basta acessar a URL do scanner e usar o código da festa.
*   **Validação Instantânea:** Check-in rápido com feedback visual e sonoro, evitando fraudes e agilizando a entrada.

### 📊 **Estatísticas e Análises Poderosas**
*   **Dashboard em Tempo Real:** Visualize instantaneamente o total de convidados, quantos entraram, quantos faltam, e a porcentagem de comparecimento.
*   **Faturamento Detalhado:** Acompanhe a receita gerada pelos ingressos pagos.
*   **Gráficos Interativos:**
    *   **Gráfico de Pizza:** Veja a proporção de convidados que entraram vs. não entraram.
    *   **Gráfico de Linha do Tempo:** Analise o fluxo de check-ins por hora, com funcionalidades de zoom e arrastar para uma visão detalhada do pico de entradas.

### 🎨 **Personalização e Identidade Visual**
*   **Logo do Evento:** Faça upload da sua logo para personalizar os QR Codes e a página pública do evento.
*   **Fontes Exclusivas:** Escolha entre diversas fontes para o nome da sua festa nos convites, adicionando um toque único.
*   **Página Pública do Evento:** Uma URL compartilhável para sua festa, com descrição, data, local e, opcionalmente, a contagem de convidados e a opção de compra direta de ingressos.

### 🤝 **Colaboração e Controle de Acesso**
*   **Múltiplos Eventos:** Crie e gerencie quantas festas desejar, cada uma com suas configurações independentes.
*   **Compartilhamento Seguro:** Convide outros usuários para colaborar na gestão de suas festas através de um código de compartilhamento exclusivo, com controle de permissões.
*   **Perfis Completos:** Gerencie informações de perfil, incluindo CPF/CNPJ e telefone, essenciais para a geração de links de pagamento.

### 💰 **Integração de Pagamentos (PIX)**
*   **Venda de Ingressos:** Defina um preço para seus ingressos e permita que convidados paguem via PIX.
*   **Links de Pagamento:** Gere links de pagamento individuais para convidados específicos ou permita a compra direta pela página pública do evento.
*   **Status Automatizado:** O sistema atualiza automaticamente o status do pagamento via webhooks, garantindo que apenas ingressos pagos sejam validados.

### 📤 **Exportação de Dados Flexível**
*   **CSV e PDF:** Exporte sua lista de convidados completa para planilhas (CSV) ou relatórios detalhados em PDF, incluindo estatísticas e gráficos.

## 🛠️ Tecnologias Utilizadas:

*   **Backend:** Python 3, Flask, Flask-SQLAlchemy (PostgreSQL), Pillow, qrcode, requests.
*   **Frontend:** HTML5, CSS3 (Tailwind CSS), JavaScript (Vanilla JS), Chart.js, html5-qrcode, Anime.js.
*   **Banco de Dados:** PostgreSQL (para escalabilidade e robustez).

## 🚀 Setup e Execução do Projeto Localmente:

### Pré-requisitos:
*   Python 3.7+
*   `pip` (gerenciador de pacotes Python)
*   Um arquivo de fonte TrueType (TTF), como `Montserrat-Regular.ttf` (já incluído no projeto).
*   Acesso a um banco de dados PostgreSQL (pode ser local ou em nuvem).

### Passos para Configuração:

1.  **Clone o Repositório:**
    ```bash
    git clone <url_do_repositorio>
    cd AttendanceManager
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
        SECRET_KEY=sua_chave_secreta_aqui_gerada_aleatoriamente
        ABACATE_API_KEY=sua_chave_api_do_abacatepay
        DATABASE_URL=postgresql://user:password@host:port/database_name
        FLASK_DEBUG=True # Opcional: para ativar o modo debug
        ```
    *   **Importante:** A `DATABASE_URL` deve apontar para o seu banco de dados PostgreSQL.
    *   Certifique-se de que o arquivo de fonte TTF está na raiz do projeto (ou no caminho `static/fonts`).

5.  **Inicialize o Banco de Dados (Alembic):**
    *   Certifique-se de que o Alembic está configurado (o arquivo `alembic.ini` deve estar na raiz).
    *   Execute as migrações para criar as tabelas no seu banco de dados PostgreSQL:
        ```bash
        flask db upgrade
        ```

6.  **Execute a Aplicação:**
    ```bash
    python app.py
    ```
    Acesse `http://localhost:5000/` no seu navegador.

7.  **Teste o Scanner em Dispositivos Móveis (Opcional):**
    *   Para testar o scanner em dispositivos reais na sua rede local ou via internet, você pode usar ferramentas como `ngrok` para expor seu servidor local:
        ```bash
        ./ngrok http 5000
        ```
    *   Acesse a URL HTTPS gerada pelo `ngrok` no navegador do seu dispositivo móvel.

---
Feito com ❤️ por Murilo Scolari