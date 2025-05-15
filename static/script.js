// --- Código JavaScript COMPLETO ---

const API_BASE_URL = '';
let html5QrCode = null;
let beepAudio = null;
const OVERLAY_TIMEOUT_MS = 2500;
let overlayTimeoutId = null;
let lastScannedHash = null;
let lastScanTime = 0;
const SCAN_COOLDOWN_MS = 3000;
let attendanceChartInstance = null; // Para o gráfico de pizza

document.addEventListener('DOMContentLoaded', () => {
    // Verifica se elementos da página principal existem para carregar dados específicos
    const guestListElement = document.getElementById('guestList');
    const addGuestFormElement = document.getElementById('addGuestForm');
    const statsTotalInvitedElement = document.getElementById('statsTotalInvited'); // Elemento chave da seção de stats

    if (guestListElement || addGuestFormElement) { // Indica que estamos na index.html (ou uma página com essas features)
        if (typeof fetchGuests === "function") {
            fetchGuests(); 
        }
        if (typeof fetchStats === "function" && statsTotalInvitedElement) { // Só busca stats se a seção existir
             fetchStats();
             // Opcional: Atualizar estatísticas periodicamente
             // setInterval(fetchStats, 30000); // A cada 30 segundos
        }
    }

    if (addGuestFormElement) {
        addGuestFormElement.addEventListener('submit', (event) => {
            event.preventDefault(); addGuest();
        });
    }

    const qrReaderElementId = "qrReader";
    const qrReaderElement = document.getElementById(qrReaderElementId);
    if (qrReaderElement) {
        html5QrCode = new Html5Qrcode(qrReaderElementId, { verbose: true }); 
        console.log("Instância Html5Qrcode criada.");
    } else {
        // Só é um erro se a seção do scanner estiver visível e o leitor não for encontrado
        const scannerSection = document.querySelector('.section.scanner-section');
        if (scannerSection && getComputedStyle(scannerSection).display !== 'none') {
             console.warn("Elemento 'qrReader' não encontrado, mas a seção do scanner está presente e visível.");
        }
    }

    beepAudio = document.getElementById('beepSound');
    if (beepAudio) {
        beepAudio.onerror = () => console.error("Erro ao carregar 'beep.mp3'.");
    }

    // Esconder elementos da index.html se existirem (para a área de "novo QR")
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
    if (!nameInput) { console.warn("addGuest: #guestName não encontrado."); return; }
    const name = nameInput.value.trim();
    const guestAddedInfo = document.getElementById('guestAddedInfo');
    const newGuestQrImage = document.getElementById('newGuestQrImage');
    const downloadQrLink = document.getElementById('downloadQrLink');
    if(guestAddedInfo) guestAddedInfo.textContent = '';
    if(newGuestQrImage) {newGuestQrImage.style.display = 'none'; newGuestQrImage.src = '';}
    if(downloadQrLink) {downloadQrLink.style.display = 'none'; downloadQrLink.href = '#';}
    if (!name) { alert('Nome do convidado é obrigatório.'); return; }
    try {
        const response = await fetch(`${API_BASE_URL}/api/guests`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: name })
        });
        const result = await response.json();
        if (!response.ok) {
            if(guestAddedInfo) {guestAddedInfo.textContent = `Erro: ${result.error || 'Falha ao adicionar.'}`; guestAddedInfo.style.color = 'red';}
            return;
        }
        if(guestAddedInfo) {guestAddedInfo.textContent = `Convidado "${result.name}" adicionado.`; guestAddedInfo.style.color = 'green';}
        if (result.qr_image_url) {
            const imageUrl = `${result.qr_image_url}?t=${new Date().getTime()}`;
            if(newGuestQrImage) {newGuestQrImage.src = imageUrl; newGuestQrImage.style.display = 'block';}
            if(downloadQrLink) {downloadQrLink.href = imageUrl; downloadQrLink.download = `qrcode_${result.name.replace(/\s+/g, '_')}.png`; downloadQrLink.style.display = 'block';}
        }
        nameInput.value = '';
        if (document.getElementById('guestList')) fetchGuests();
        if (document.getElementById('statsTotalInvited') && typeof fetchStats === "function") fetchStats();
    } catch (error) {
        console.error('Erro ao adicionar convidado:', error); 
        if(guestAddedInfo) {guestAddedInfo.textContent = 'Erro de rede ao adicionar.'; guestAddedInfo.style.color = 'red';}
    }
}
async function fetchGuests() {
    const tbody = document.getElementById('guestList');
    if (!tbody) { console.warn("fetchGuests: #guestList não encontrado."); return; }
    try {
        const response = await fetch(`${API_BASE_URL}/api/guests`);
        if (!response.ok) { console.error('Erro ao buscar convidados:', response.statusText); return; }
        const guests = await response.json(); 
        tbody.innerHTML = '';
        if (guests.length === 0) { tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;">Nenhum convidado cadastrado.</td></tr>'; return; }
        guests.forEach(guest => {
            const row = tbody.insertRow(); row.insertCell().textContent = guest.name;
            row.insertCell().textContent = guest.qr_hash ? guest.qr_hash.substring(0, 10) + '...' : 'N/A';
            const qrCell = row.insertCell();
            if (guest.qr_image_url) {
                const img = document.createElement('img'); img.src = `${guest.qr_image_url}?t=${new Date().getTime()}`;
                img.alt = `QR ${guest.name}`; img.style.cssText = 'width:50px; height:50px; cursor:pointer; object-fit:contain; border:1px solid #eee;';
                img.onclick = () => window.open(img.src, '_blank'); qrCell.appendChild(img);
            } else { qrCell.textContent = 'N/A'; }
            const enteredCell = row.insertCell(); enteredCell.textContent = guest.entered ? 'Sim' : 'Não'; enteredCell.style.color = guest.entered ? 'green' : 'red';
            const actionsCell = row.insertCell();
            const toggleButton = document.createElement('button'); toggleButton.textContent = guest.entered ? 'Marcar Não Entrou' : 'Marcar Entrou';
            toggleButton.className = guest.entered ? 'button-unmark' : 'button-mark'; toggleButton.onclick = () => toggleGuestEntry(guest.qr_hash); actionsCell.appendChild(toggleButton);
            const removeButton = document.createElement('button'); removeButton.textContent = 'Remover'; removeButton.className = 'button-remove';
            removeButton.style.marginLeft = '5px'; removeButton.onclick = () => confirmDeleteGuest(guest.qr_hash, guest.name); actionsCell.appendChild(removeButton);
        });
    } catch (error) { console.error('Erro ao buscar convidados:', error); }
}
function confirmDeleteGuest(qrHash, guestName) { if (confirm(`Tem certeza que deseja remover "${guestName}"?`)) { deleteGuest(qrHash); } }
async function deleteGuest(qrHash) {
    try {
        const response = await fetch(`${API_BASE_URL}/api/guests/${qrHash}`, { method: 'DELETE' });
        const result = await response.json();
        if (!response.ok) { alert(`Erro ao remover: ${result.error || 'Erro.'}`); return; }
        alert(result.message || 'Removido.'); 
        if (document.getElementById('guestList')) fetchGuests();
        if (document.getElementById('statsTotalInvited') && typeof fetchStats === "function") fetchStats();
    } catch (error) { console.error('Erro de rede ao remover:', error); alert('Erro de rede.'); }
}
async function toggleGuestEntry(qrHash) {
    try {
        const response = await fetch(`${API_BASE_URL}/api/guests/${qrHash}/toggle_entry`, { method: 'PUT' });
        const result = await response.json(); if (!response.ok) { alert(`Erro: ${result.error}`); return; }
        console.log(result.message); 
        if (document.getElementById('guestList')) fetchGuests();
        if (document.getElementById('statsTotalInvited') && typeof fetchStats === "function") fetchStats();
    } catch (error) { console.error('Erro ao alterar status:', error); }
}

// --- Funções de Estatísticas ---
async function fetchStats() {
    const statsTotalInvitedEl = document.getElementById('statsTotalInvited');
    if (!statsTotalInvitedEl) { // Se o elemento principal das stats não existe, não faz nada
        console.log("fetchStats: Elementos de estatísticas não encontrados na página.");
        return;
    }
    console.log("fetchStats: Buscando estatísticas...");

    try {
        const response = await fetch(`${API_BASE_URL}/api/stats`);
        if (!response.ok) {
            console.error("Erro ao buscar estatísticas:", response.statusText);
            statsTotalInvitedEl.textContent = 'Erro';
            document.getElementById('statsEnteredCount').textContent = '-';
            document.getElementById('statsNotEnteredCount').textContent = '-';
            document.getElementById('statsPercentageEntered').textContent = '- %';
            return;
        }
        const stats = await response.json();
        console.log("fetchStats: Estatísticas recebidas:", stats);

        statsTotalInvitedEl.textContent = stats.total_invited;
        document.getElementById('statsEnteredCount').textContent = stats.entered_count;
        document.getElementById('statsNotEnteredCount').textContent = stats.not_entered_count;
        document.getElementById('statsPercentageEntered').textContent = stats.percentage_entered + " %";
        
        if (typeof updateAttendanceChart === "function") {
             updateAttendanceChart(stats.entered_count, stats.not_entered_count);
        }
    } catch (error) {
        console.error("Erro de rede ao buscar estatísticas:", error);
        statsTotalInvitedEl.textContent = 'Erro de Rede';
        document.getElementById('statsEnteredCount').textContent = '-';
        document.getElementById('statsNotEnteredCount').textContent = '-';
        document.getElementById('statsPercentageEntered').textContent = '- %';
    }
}

function updateAttendanceChart(entered, notEntered) {
    const ctx = document.getElementById('attendanceChart');
    if (!ctx) {
        console.warn("updateAttendanceChart: Canvas 'attendanceChart' não encontrado.");
        return;
    }
    console.log("updateAttendanceChart: Atualizando gráfico com Entraram:", entered, "Não Entraram:", notEntered);

    const data = {
        labels: ['Entraram', 'Não Entraram'],
        datasets: [{
            label: 'Comparecimento', data: [entered, notEntered],
            backgroundColor: ['rgba(75, 192, 192, 0.7)', 'rgba(255, 99, 132, 0.7)'],
            borderColor: ['rgba(75, 192, 192, 1)', 'rgba(255, 99, 132, 1)'],
            borderWidth: 1, hoverOffset: 4
        }]
    };
    const configChart = {
        type: 'pie', data: data,
        options: {
            responsive: true, maintainAspectRatio: false,
            plugins: {
                legend: { position: 'top' },
                title: { display: true, text: 'Distribuição de Comparecimento' },
                tooltip: { callbacks: {
                    label: function(context) {
                        let label = context.label || ''; if (label) { label += ': '; }
                        if (context.parsed !== null) {
                            const total = context.dataset.data.reduce((a, b) => a + b, 0);
                            const percentage = total > 0 ? ((context.parsed / total) * 100).toFixed(1) + '%' : '0%';
                            label += context.parsed + ' (' + percentage + ')';
                        } return label;
                    }
                }}
            }
        }
    };
    if (attendanceChartInstance) {
        attendanceChartInstance.data.datasets[0].data = [entered, notEntered];
        attendanceChartInstance.update();
        console.log("updateAttendanceChart: Gráfico atualizado.");
    } else {
        attendanceChartInstance = new Chart(ctx, configChart);
        console.log("updateAttendanceChart: Gráfico criado.");
    }
}

// --- Funções do Scanner de QR Code ---
function showOverlayFeedback(type, icon, message) {
    const overlay = document.getElementById('scanOverlayFeedback');
    const textFeedback = document.getElementById('scanResultText'); 
    if (overlayTimeoutId) { clearTimeout(overlayTimeoutId); }
    if (overlay) {
        overlay.innerHTML = `<span class="overlay-icon">${icon}</span><span class="overlay-message">${message}</span>`;
        overlay.className = 'scan-overlay visible'; 
        if (type === 'success') overlay.classList.add('success-bg');
        else if (type === 'error') overlay.classList.add('error-bg');
        else if (type === 'warning') overlay.classList.add('warning-bg'); 
        if (type !== 'processing') { 
            overlayTimeoutId = setTimeout(() => {
                overlay.classList.remove('visible', 'success-bg', 'error-bg', 'warning-bg');
            }, OVERLAY_TIMEOUT_MS);
        }
    }
    if(textFeedback) {
        textFeedback.textContent = (type === 'processing') ? `Processando QR...` : message;
        textFeedback.className = type; 
    }
}
function onScanSuccess(decodedText, decodedResult) {
    const currentTime = Date.now();
    if (decodedText === lastScannedHash && (currentTime - lastScanTime) < SCAN_COOLDOWN_MS) {
        console.log(`[FRONTEND] QR (${decodedText.substring(0,10)}...) cooldown. Ignorando.`);
        return; 
    }
    console.log(`[FRONTEND] QR LIDO: ${decodedText}`);
    showOverlayFeedback('processing', '<span class="spinner"></span>', `Processando...`);
    lastScannedHash = decodedText; lastScanTime = currentTime;
    processScannedQr(decodedText);
}
function onScanFailure(error) { /* console.warn(`[FRONTEND] Falha no scan: ${error}`); */ }
async function processScannedQr(qrHash) {
    console.log(`[FRONTEND] Enviando hash '${qrHash}' para API`);
    try {
        const response = await fetch(`${API_BASE_URL}/api/guests/${qrHash}/enter`, { method: 'POST' });
        const result = await response.json();
        if (!response.ok) {
             showOverlayFeedback('error', '✗', result.error || 'QR inválido/não encontrado.');
        } else {
            const guestName = result.name || "Convidado";
            let message = result.message || (guestName + ' check-in OK!');
            if (result.is_new_entry === true) {
                showOverlayFeedback('success', '✓', message);
                if (beepAudio) { beepAudio.currentTime = 0; beepAudio.play().catch(e => console.error("Erro ao tocar beep:", e)); }
            } else {
                showOverlayFeedback('warning', 'ⓘ', message);
            }
            if (document.getElementById('guestList')) fetchGuests(); // Atualiza lista se estiver na index.html
            if (document.getElementById('statsTotalInvited') && typeof fetchStats === "function") fetchStats(); // Atualiza stats se estiver na index.html
        }
    } catch (error) {
        console.error('[FRONTEND] Erro de rede:', error);
        showOverlayFeedback('error', '✗', 'Erro de rede ao validar QR.');
    }
}
function startQrScanner() {
    if (!html5QrCode) { alert("Erro: Leitor QR não inicializado."); return; }
    const qrScannerWrapper = document.getElementById('qrScannerWrapper');
    const msgContainer = document.getElementById('qrReaderMessageContainer');
    const startBtn = document.getElementById('startScanButton');
    const stopBtn = document.getElementById('stopScanButton');
    const textFeedback = document.getElementById('scanResultText');

    if (msgContainer) msgContainer.style.display = 'none';
    if (qrScannerWrapper) qrScannerWrapper.style.display = 'block'; 

    const videoConstraints = { facingMode: "environment" };
    const configScanner = { 
        fps: 15, 
        qrbox: (viewfinderWidth, viewfinderHeight) => {
            let edgePercentage = 0.70; 
            let qrboxEdgeSize = Math.floor(Math.min(viewfinderWidth, viewfinderHeight) * edgePercentage);
            qrboxEdgeSize = Math.max(120, qrboxEdgeSize); 
            qrboxEdgeSize = Math.min(260, qrboxEdgeSize); 
            console.log(`Viewfinder: ${viewfinderWidth}x${viewfinderHeight}, QRBox: ${qrboxEdgeSize}x${qrboxEdgeSize}`);
            return { width: qrboxEdgeSize, height: qrboxEdgeSize };
        },
        rememberLastUsedCamera: true, 
        supportedScanTypes: [Html5QrcodeScanType.SCAN_TYPE_CAMERA]
    };
    
    if (html5QrCode.isScanning) { console.log("Scanner já ativo."); return; }

    if (textFeedback) { textFeedback.textContent = 'Iniciando câmera...'; textFeedback.className = 'processing';}
    
    html5QrCode.start( videoConstraints, configScanner, onScanSuccess, onScanFailure)
    .then(() => {
        console.log("Scanner iniciado.");
        if(startBtn) startBtn.style.display = 'none';
        if(stopBtn) stopBtn.style.display = 'inline-block';
        if(textFeedback) { textFeedback.textContent = 'Câmera ativa. Aponte para QR Code.'; textFeedback.className = ''; }
    }).catch(err => {
        console.error("Erro ao iniciar scanner:", err);
        if(textFeedback) { textFeedback.textContent = `Erro câmera: ${err}. Verifique HTTPS/permissões.`; textFeedback.className = 'error'; }
        if (msgContainer) msgContainer.style.display = 'block';
        if (qrScannerWrapper) qrScannerWrapper.style.display = 'none';
        if(startBtn) startBtn.style.display = 'inline-block';
        if(stopBtn) stopBtn.style.display = 'none';
    });
}
async function stopQrScanner() {
    if (!html5QrCode || !html5QrCode.isScanning) {
        console.log("Tentativa de parar scanner que não está ativo ou inicializado.");
    } else {
        try { await html5QrCode.stop(); console.log("Scanner parado."); }
        catch (err) { console.error("Erro ao tentar parar o scanner:", err); }
    }
    const startBtn = document.getElementById('startScanButton'); 
    const stopBtn = document.getElementById('stopScanButton');
    const textFeedback = document.getElementById('scanResultText'); 
    const qrScannerWrapper = document.getElementById('qrScannerWrapper');
    const msgContainer = document.getElementById('qrReaderMessageContainer');
    const overlay = document.getElementById('scanOverlayFeedback');

    if(startBtn) startBtn.style.display = 'inline-block'; 
    if(stopBtn) stopBtn.style.display = 'none';
    if (qrScannerWrapper) qrScannerWrapper.style.display = 'none';
    if (msgContainer) msgContainer.style.display = 'block';
    if (overlay) { 
        overlay.classList.remove('visible');
        overlay.classList.remove('success-bg', 'error-bg', 'warning-bg', 'processing-bg');
    }
    if(textFeedback) {
        if (!textFeedback.className.includes('error')) { 
            textFeedback.textContent = 'Scanner parado ou não estava ativo.'; 
            textFeedback.className = '';
        }
    }
}