const API_BASE_URL = '';
let html5QrCode = null;
let beepAudio = null;
const OVERLAY_TIMEOUT_MS = 2500; // Quanto tempo a sobreposição fica visível
let overlayTimeoutId = null; // Para controlar o timeout da sobreposição

// Variáveis para o cooldown lógico (sem feedback visual para o cooldown em si)
let lastScannedHash = null;
let lastScanTime = 0;
const SCAN_COOLDOWN_MS = 3000; // 3 segundos de cooldown lógico

document.addEventListener('DOMContentLoaded', () => {
    fetchGuests();

    const addGuestForm = document.getElementById('addGuestForm');
    if (addGuestForm) {
        addGuestForm.addEventListener('submit', (event) => {
            event.preventDefault();
            addGuest();
        });
    }

    const qrReaderElementId = "qrReader";
    if (document.getElementById(qrReaderElementId)) {
        // verbose: true pode ajudar a depurar problemas da biblioteca html5-qrcode
        html5QrCode = new Html5Qrcode(qrReaderElementId, /* verbose= */ true);
        console.log("Instância Html5Qrcode criada.");
    } else {
        console.error("Elemento 'qrReader' não encontrado. Scanner não será funcional.");
    }

    beepAudio = document.getElementById('beepSound');
    if (beepAudio) {
        beepAudio.onerror = () => console.error("Erro ao carregar 'beep.mp3'. Verifique o caminho e o arquivo.");
    } else {
        console.warn("Elemento de áudio 'beepSound' não encontrado.");
    }

    // Esconder feedback inicial
    const newGuestQrImage = document.getElementById('newGuestQrImage');
    if (newGuestQrImage) newGuestQrImage.style.display = 'none';
    const downloadQrLink = document.getElementById('downloadQrLink');
    if (downloadQrLink) downloadQrLink.style.display = 'none';
    const guestAddedInfo = document.getElementById('guestAddedInfo');
    if (guestAddedInfo) guestAddedInfo.textContent = '';
});

// --- Funções de Convidado ---
async function addGuest() {
    const nameInput = document.getElementById('guestName');
    const name = nameInput.value.trim();
    const guestAddedInfo = document.getElementById('guestAddedInfo');
    const newGuestQrImage = document.getElementById('newGuestQrImage');
    const downloadQrLink = document.getElementById('downloadQrLink');

    guestAddedInfo.textContent = '';
    newGuestQrImage.style.display = 'none'; newGuestQrImage.src = '';
    downloadQrLink.style.display = 'none'; downloadQrLink.href = '#';

    if (!name) { alert('Nome do convidado é obrigatório.'); return; }

    try {
        const response = await fetch(`${API_BASE_URL}/api/guests`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: name })
        });
        const result = await response.json();
        if (!response.ok) {
            guestAddedInfo.textContent = `Erro: ${result.error || 'Falha ao adicionar.'}`;
            guestAddedInfo.style.color = 'red';
            return;
        }
        guestAddedInfo.textContent = `Convidado "${result.name}" adicionado.`;
        guestAddedInfo.style.color = 'green';
        if (result.qr_image_url) {
            const imageUrl = `${result.qr_image_url}?t=${new Date().getTime()}`;
            newGuestQrImage.src = imageUrl;
            newGuestQrImage.style.display = 'block';
            downloadQrLink.href = imageUrl;
            downloadQrLink.download = `qrcode_${result.name.replace(/\s+/g, '_')}.png`;
            downloadQrLink.style.display = 'block';
        }
        nameInput.value = '';
        fetchGuests();
    } catch (error) {
        console.error('Erro ao adicionar convidado:', error);
        guestAddedInfo.textContent = 'Erro de rede ao adicionar.';
        guestAddedInfo.style.color = 'red';
    }
}

async function fetchGuests() {
    try {
        const response = await fetch(`${API_BASE_URL}/api/guests`);
        if (!response.ok) { console.error('Erro ao buscar convidados:', response.statusText); return; }
        const guests = await response.json();
        const tbody = document.getElementById('guestList');
        tbody.innerHTML = '';
        if (guests.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;">Nenhum convidado cadastrado.</td></tr>';
            return;
        }
        guests.forEach(guest => {
            const row = tbody.insertRow();
            row.insertCell().textContent = guest.name;
            row.insertCell().textContent = guest.qr_hash ? guest.qr_hash.substring(0, 10) + '...' : 'N/A';
            
            const qrCell = row.insertCell();
            if (guest.qr_image_url) {
                const img = document.createElement('img');
                img.src = `${guest.qr_image_url}?t=${new Date().getTime()}`;
                img.alt = `QR ${guest.name}`;
                img.style.cssText = 'width:50px; height:50px; cursor:pointer; object-fit:contain; border:1px solid #eee;';
                img.onclick = () => window.open(img.src, '_blank');
                qrCell.appendChild(img);
            } else { qrCell.textContent = 'N/A'; }

            const enteredCell = row.insertCell();
            enteredCell.textContent = guest.entered ? 'Sim' : 'Não';
            enteredCell.style.color = guest.entered ? 'green' : 'red';

            const actionsCell = row.insertCell();
            const toggleButton = document.createElement('button');
            toggleButton.textContent = guest.entered ? 'Marcar Não Entrou' : 'Marcar Entrou';
            toggleButton.className = guest.entered ? 'button-unmark' : 'button-mark';
            toggleButton.onclick = () => toggleGuestEntry(guest.qr_hash);
            actionsCell.appendChild(toggleButton);

            const removeButton = document.createElement('button');
            removeButton.textContent = 'Remover';
            removeButton.className = 'button-remove';
            removeButton.style.marginLeft = '5px';
            removeButton.onclick = () => confirmDeleteGuest(guest.qr_hash, guest.name);
            actionsCell.appendChild(removeButton);
        });
    } catch (error) { console.error('Erro ao buscar convidados:', error); }
}

function confirmDeleteGuest(qrHash, guestName) {
    if (confirm(`Tem certeza que deseja remover o convidado "${guestName}"? Esta ação não pode ser desfeita.`)) {
        deleteGuest(qrHash);
    }
}

async function deleteGuest(qrHash) {
    try {
        const response = await fetch(`${API_BASE_URL}/api/guests/${qrHash}`, {
            method: 'DELETE'
        });
        const result = await response.json();
        if (!response.ok) {
            alert(`Erro ao remover: ${result.error || 'Erro desconhecido.'}`);
            return;
        }
        alert(result.message || 'Convidado removido.');
        fetchGuests(); // Atualiza a lista
    } catch (error) {
        console.error('Erro de rede ao remover:', error);
        alert('Erro de rede ao tentar remover convidado.');
    }
}

async function toggleGuestEntry(qrHash) {
    try {
        const response = await fetch(`${API_BASE_URL}/api/guests/${qrHash}/toggle_entry`, { method: 'PUT' });
        const result = await response.json();
        if (!response.ok) { alert(`Erro: ${result.error}`); return; }
        console.log(result.message); 
        fetchGuests();
    } catch (error) { console.error('Erro ao alterar status:', error); }
}
// --- Fim das Funções de Convidado ---


function showOverlayFeedback(type, icon, message) {
    const overlay = document.getElementById('scanOverlayFeedback');
    const textFeedback = document.getElementById('scanResultText'); // Para o texto abaixo do scanner

    if (overlayTimeoutId) {
        clearTimeout(overlayTimeoutId); // Limpa timeout anterior se houver
    }

    if (overlay) {
        overlay.innerHTML = `<span class="overlay-icon">${icon}</span><span class="overlay-message">${message}</span>`;
        overlay.className = 'scan-overlay visible'; // Remove classes de cor antigas, adiciona base e visible
        if (type === 'success') overlay.classList.add('success-bg');
        else if (type === 'error') overlay.classList.add('error-bg');
        else if (type === 'warning') overlay.classList.add('warning-bg');
        // Não adiciona fundo para 'processing' por padrão, apenas o spinner no ícone

        if (type !== 'processing') { // Não aplicar timeout para "Processando"
            overlayTimeoutId = setTimeout(() => {
                overlay.classList.remove('visible');
                // Limpa as classes de cor para a próxima vez
                overlay.classList.remove('success-bg', 'error-bg', 'warning-bg');
            }, OVERLAY_TIMEOUT_MS);
        }
    }

    // Atualiza também o texto persistente abaixo do scanner
    if(textFeedback) {
        // Para 'processing', a mensagem de texto é mais simples. Para outros, usa a mensagem completa.
        textFeedback.textContent = (type === 'processing') ? `Processando QR...` : message;
        textFeedback.className = type; // Aplica a classe de cor (success, error, warning)
    }
}


function onScanSuccess(decodedText, decodedResult) {
    const currentTime = Date.now();

    // Cooldown LÓGICO: Se o mesmo QR for escaneado dentro do cooldown, ignora SILENCIOSAMENTE.
    if (decodedText === lastScannedHash && (currentTime - lastScanTime) < SCAN_COOLDOWN_MS) {
        console.log(`[FRONTEND] QR (${decodedText.substring(0,10)}...) repetido DENTRO DO COOLDOWN LÓGICO. Ignorando.`);
        return; // Ignora o scan, não mostra nada novo, não processa.
    }

    // Se não estiver em cooldown lógico, mostra "Processando..." na sobreposição e no texto.
    console.log(`[FRONTEND] QR LIDO (não em cooldown): ${decodedText}`);
    showOverlayFeedback('processing', '<span class="spinner"></span>', `Processando...`);
    
    // Atualiza lastScannedHash e lastScanTime AQUI, antes de enviar para o backend.
    // Isso garante que, se o usuário escanear o mesmo QR rapidamente enquanto
    // o primeiro ainda está sendo processado, o segundo scan será pego pelo cooldown.
    lastScannedHash = decodedText;
    lastScanTime = currentTime;

    processScannedQr(decodedText);
}

function onScanFailure(error) {
    // Este callback é chamado frequentemente pela biblioteca.
    // console.warn(`[FRONTEND] Falha no scan do QR (não necessariamente um erro): ${error}`);
}

async function processScannedQr(qrHash) {
    console.log(`[FRONTEND] Enviando hash '${qrHash}' para API /api/guests/${qrHash}/enter`);
    // "Processando" já foi mostrado por onScanSuccess via showOverlayFeedback

    try {
        const response = await fetch(`${API_BASE_URL}/api/guests/${qrHash}/enter`, {
            method: 'POST'
        });
        const result = await response.json();

        if (!response.ok) { // Erro do servidor (4xx, 5xx)
             showOverlayFeedback('error', '✗', result.error || 'QR inválido ou não encontrado.');
        } else { // Sucesso do servidor (2xx)
            const guestName = result.name || "Convidado";
            let message = result.message || (guestName + ' check-in OK!');

            if (result.is_new_entry === true) {
                showOverlayFeedback('success', '✓', message);
                if (beepAudio) {
                    beepAudio.currentTime = 0; // Reinicia o áudio
                    beepAudio.play().catch(e => console.error("Erro ao tocar beep:", e));
                }
            } else {
                // Já entrou antes (is_new_entry é false ou não existe, mas QR é válido)
                showOverlayFeedback('warning', 'ⓘ', message);
            }
            fetchGuests(); // Atualiza a lista de convidados
        }
    } catch (error) { // Erro de rede ou outros erros do fetch
        console.error('[FRONTEND] Erro de rede ao enviar hash para API:', error);
        showOverlayFeedback('error', '✗', 'Erro de rede ao validar QR.');
    }
}

function startQrScanner() {
    if (!html5QrCode) { alert("Erro: Leitor QR não inicializado. Verifique o console."); return; }

    const qrScannerWrapper = document.getElementById('qrScannerWrapper');
    const msgContainer = document.getElementById('qrReaderMessageContainer');
    const startBtn = document.getElementById('startScanButton');
    const stopBtn = document.getElementById('stopScanButton');
    const textFeedback = document.getElementById('scanResultText'); // Para a mensagem de texto abaixo

    if (msgContainer) msgContainer.style.display = 'none';
    if (qrScannerWrapper) qrScannerWrapper.style.display = 'block'; // Mostra o wrapper do scanner

    // Configurações para o scanner
    const config = { 
        fps: 10, 
        // qrbox define a área de scan. Ajuste se necessário.
        qrbox: (viewfinderWidth, viewfinderHeight) => {
            const minDimension = Math.min(viewfinderWidth, viewfinderHeight);
            let qrBoxSize = Math.floor(minDimension * 0.8); // Tenta usar 80% do menor lado
            if (qrBoxSize < 100) qrBoxSize = 100; // Tamanho mínimo
            if (qrBoxSize > 280) qrBoxSize = 280; // Tamanho máximo para wrapper de 300px
            return { width: qrBoxSize, height: qrBoxSize };
        },
        rememberLastUsedCamera: true, 
        supportedScanTypes: [Html5QrcodeScanType.SCAN_TYPE_CAMERA] 
    };
    
    if (html5QrCode.isScanning) { 
        console.log("Scanner já está ativo."); 
        return; 
    }

    if (textFeedback) {
        textFeedback.textContent = 'Iniciando câmera...';
        textFeedback.className = 'processing'; // Reutiliza a classe para cor/estilo
    }
    
    html5QrCode.start(
        { facingMode: "environment" }, // Tenta usar a câmera traseira
        config,
        onScanSuccess,
        onScanFailure
    ).then(() => {
        console.log("Scanner iniciado com sucesso.");
        if(startBtn) startBtn.style.display = 'none';
        if(stopBtn) stopBtn.style.display = 'inline-block';
        if(textFeedback) { 
            textFeedback.textContent = 'Câmera ativa. Aponte para um QR Code.';
            textFeedback.className = ''; // Limpa classe de estado
        }
    }).catch(err => {
        console.error("Erro ao iniciar o scanner:", err);
        if(textFeedback) { 
            textFeedback.textContent = `Erro ao iniciar câmera: ${err}. Verifique HTTPS e permissões.`;
            textFeedback.className = 'error';
        }
        // Reverte a UI em caso de falha ao iniciar
        if (msgContainer) msgContainer.style.display = 'block';
        if (qrScannerWrapper) qrScannerWrapper.style.display = 'none';
        if(startBtn) startBtn.style.display = 'inline-block';
        if(stopBtn) stopBtn.style.display = 'none';
    });
}

async function stopQrScanner() {
    if (!html5QrCode) { return; }

    const startBtn = document.getElementById('startScanButton'); 
    const stopBtn = document.getElementById('stopScanButton');
    const textFeedback = document.getElementById('scanResultText'); 
    const qrScannerWrapper = document.getElementById('qrScannerWrapper');
    const msgContainer = document.getElementById('qrReaderMessageContainer');
    const overlay = document.getElementById('scanOverlayFeedback');

    if (html5QrCode.isScanning) {
        try {
            await html5QrCode.stop();
            console.log("Scanner parado com sucesso.");
            if(textFeedback) {
                textFeedback.textContent = 'Scanner parado.';
                textFeedback.className = ''; // Limpa classes de estado
            }
        } catch (err) {
            console.error("Erro ao tentar parar o scanner:", err);
            if(textFeedback) {
                textFeedback.textContent = `Erro ao parar scanner.`;
                textFeedback.className = 'error';
            }
        } finally {
            // Garante que a UI seja atualizada mesmo se stop() falhar
            if(startBtn) startBtn.style.display = 'inline-block';
            if(stopBtn) stopBtn.style.display = 'none';
            if (qrScannerWrapper) qrScannerWrapper.style.display = 'none';
            if (msgContainer) msgContainer.style.display = 'block';
            if (overlay) { // Esconde e limpa a sobreposição
                overlay.classList.remove('visible');
                overlay.classList.remove('success-bg', 'error-bg', 'warning-bg', 'processing-bg');
            }
        }
    } else { // Se não estava escaneando, apenas garante o estado correto da UI
        console.log("Scanner não estava ativo, mas atualizando UI de parada.");
        if(startBtn) startBtn.style.display = 'inline-block';
        if(stopBtn) stopBtn.style.display = 'none';
        if (qrScannerWrapper) qrScannerWrapper.style.display = 'none';
        if (msgContainer) msgContainer.style.display = 'block';
        if(textFeedback && !textFeedback.textContent.includes("Erro")) { 
            textFeedback.textContent = 'Scanner não estava ativo.';
            textFeedback.className = '';
        }
        if (overlay) {
            overlay.classList.remove('visible');
            overlay.classList.remove('success-bg', 'error-bg', 'warning-bg', 'processing-bg');
        }
    }
}