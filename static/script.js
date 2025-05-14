const API_BASE_URL = '';
let html5QrCode = null;
let beepAudio = null; // Para o som de beep
let lastScannedHash = null; // Para o cooldown do scan
let lastScanTime = 0; // Para o cooldown do scan
const SCAN_COOLDOWN_MS = 3000; // 3 segundos de cooldown

document.addEventListener('DOMContentLoaded', () => {
    fetchGuests();

    const addGuestForm = document.getElementById('addGuestForm');
    if (addGuestForm) {
        addGuestForm.addEventListener('submit', (event) => {
            event.preventDefault();
            addGuest();
        });
    }

    // Inicializa leitor de QR
    const qrReaderElementId = "qrReader";
    if (document.getElementById(qrReaderElementId)) {
        html5QrCode = new Html5Qrcode(qrReaderElementId, /* verbose= */ true);
        console.log("Instância Html5Qrcode criada.");
    } else {
        console.error("Elemento 'qrReader' não encontrado.");
    }

    // Pega referência ao áudio
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
            removeButton.className = 'button-remove'; // Para estilização
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
        console.log(result.message); // Ou um feedback mais sutil
        fetchGuests();
    } catch (error) { console.error('Erro ao alterar status:', error); }
}

// --- Funções do Scanner de QR Code ---
function onScanSuccess(decodedText, decodedResult) {
    const currentTime = Date.now();

    // Implementação do cooldown para evitar scans repetidos do mesmo QR
    if (decodedText === lastScannedHash && (currentTime - lastScanTime) < SCAN_COOLDOWN_MS) {
        console.log(`[FRONTEND] QR Code (${decodedText.substring(0,10)}...) repetido dentro do cooldown. Ignorando.`);
        const scanResultEl = document.getElementById('scanResult');
        if(scanResultEl) {
            scanResultEl.textContent = `QR já processado. Aguarde ${Math.ceil((SCAN_COOLDOWN_MS - (currentTime - lastScanTime))/1000)}s.`;
            scanResultEl.style.color = 'orange';
        }
        return; // Ignora o scan
    }

    console.log(`[FRONTEND] QR Code LIDO E DECODIFICADO NO BROWSER: ${decodedText}`);
    const scanResultEl = document.getElementById('scanResult');
    scanResultEl.textContent = `QR Lido: ${decodedText.substring(0,15)}... Processando...`;
    scanResultEl.style.color = 'blue';

    // Envia o hash para o backend e passa o tempo atual para o cooldown
    processScannedQr(decodedText, currentTime);
}

function onScanFailure(error) { /* console.warn(`[FRONTEND] Falha no scan do QR: ${error}`); */ }

async function processScannedQr(qrHash, scanTime) {
    console.log(`[FRONTEND] Enviando hash '${qrHash}' para API`);
    const scanResultEl = document.getElementById('scanResult');
    try {
        const response = await fetch(`${API_BASE_URL}/api/guests/${qrHash}/enter`, {
            method: 'POST'
        });
        const result = await response.json();

        if (!response.ok) {
             scanResultEl.textContent = `Servidor: ${result.error || 'QR inválido/não encontrado.'}`;
             scanResultEl.style.color = 'red';
             // Não atualiza lastScannedHash/Time se o backend deu erro
        } else {
            scanResultEl.textContent = `Servidor: ${result.message || (result.name + ' check-in OK!')}`;
            scanResultEl.style.color = 'green';

            // Atualiza as variáveis de cooldown APENAS SE o processamento foi um sucesso REAL
            // (ou seja, não um erro ou uma mensagem de "já entrou" se quisermos permitir re-scan após toggle manual)
            // Para "não escanear mais vezes" após o PRIMEIRO scan bem sucedido:
            lastScannedHash = qrHash;
            lastScanTime = scanTime; // Usa o tempo do scan original

            // Tocar o som se foi uma nova entrada (is_new_entry é true)
            if (result.is_new_entry === true && beepAudio) {
                beepAudio.currentTime = 0; // Reinicia o áudio caso já esteja tocando
                beepAudio.play().catch(e => console.error("Erro ao tocar beep:", e));
            }
            fetchGuests(); // Atualiza a lista
        }
    } catch (error) {
        console.error('[FRONTEND] Erro de rede ao enviar hash para API:', error);
        scanResultEl.textContent = 'Erro de rede ao validar QR Code.';
        scanResultEl.style.color = 'red';
        // Não atualiza lastScannedHash/Time em caso de erro de rede
    }
}

function startQrScanner() {
    if (!html5QrCode) { alert("Erro: Leitor QR não inicializado."); return; }

    const qrReaderEl = document.getElementById('qrReader');
    const msgContainer = document.getElementById('qrReaderMessageContainer');
    const startBtn = document.getElementById('startScanButton');
    const stopBtn = document.getElementById('stopScanButton');
    const scanResEl = document.getElementById('scanResult');

    if (msgContainer) msgContainer.style.display = 'none';
    if (qrReaderEl) qrReaderEl.style.display = 'block';

    const config = { fps: 10, qrbox: (w,h) => ({width:Math.floor(Math.min(w,h)*0.7),height:Math.floor(Math.min(w,h)*0.7)}), rememberLastUsedCamera: true, supportedScanTypes: [Html5QrcodeScanType.SCAN_TYPE_CAMERA] };
    
    if (html5QrCode.isScanning) { console.log("Scanner já ativo."); return; }

    scanResEl.textContent = 'Iniciando câmera... Conceda permissão.'; scanResEl.style.color = 'orange';
    html5QrCode.start({ facingMode: "environment" }, config, onScanSuccess, onScanFailure)
    .then(() => {
        console.log("Scanner iniciado.");
        if(startBtn) startBtn.style.display = 'none';
        if(stopBtn) stopBtn.style.display = 'inline-block';
        if(scanResEl) { scanResEl.textContent = 'Câmera ativa. Aponte para QR Code.'; scanResEl.style.color = 'black'; }
    }).catch(err => {
        console.error("Erro ao iniciar scanner:", err);
        if(scanResEl) { scanResEl.textContent = `Erro câmera: ${err}. Verifique HTTPS e permissões.`; scanResEl.style.color = 'red'; }
        if (msgContainer) msgContainer.style.display = 'block';
        if (qrReaderEl) qrReaderEl.style.display = 'none';
        if(startBtn) startBtn.style.display = 'inline-block';
        if(stopBtn) stopBtn.style.display = 'none';
    });
}

async function stopQrScanner() {
    if (!html5QrCode) { return; }
    const startBtn = document.getElementById('startScanButton'); const stopBtn = document.getElementById('stopScanButton');
    const scanResEl = document.getElementById('scanResult'); const qrReaderEl = document.getElementById('qrReader');
    const msgContainer = document.getElementById('qrReaderMessageContainer');

    if (html5QrCode.isScanning) {
        try {
            await html5QrCode.stop();
            console.log("Scanner parado.");
            if(scanResEl) scanResEl.textContent = 'Scanner parado.';
        } catch (err) {
            console.error("Erro ao parar scanner:", err);
            if(scanResEl) scanResEl.textContent = 'Erro ao parar scanner.';
        } finally {
            if(startBtn) startBtn.style.display = 'inline-block'; if(stopBtn) stopBtn.style.display = 'none';
            if (qrReaderEl) qrReaderEl.style.display = 'none'; if (msgContainer) msgContainer.style.display = 'block';
            if(scanResEl) scanResEl.style.color = 'black';
        }
    } else {
        if(startBtn) startBtn.style.display = 'inline-block'; if(stopBtn) stopBtn.style.display = 'none';
        if (qrReaderEl) qrReaderEl.style.display = 'none'; if (msgContainer) msgContainer.style.display = 'block';
        if(scanResEl && !scanResEl.textContent.includes("Erro")) { scanResEl.textContent = 'Scanner não estava ativo.'; scanResEl.style.color = 'black'; }
    }
}