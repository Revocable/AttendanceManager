// --- Código JavaScript COMPLETO ---

const API_BASE_URL = '';
let html5QrCode = null;
let beepAudio = null;
const OVERLAY_TIMEOUT_MS = 2500;
let overlayTimeoutId = null;
let lastScannedHash = null;
let lastScanTime = 0;
const SCAN_COOLDOWN_MS = 3000;
const SEARCH_DEBOUNCE_MS = 300;
let attendanceChartInstance = null;

function debounce(func, delay) {
    let timeout;
    return function(...args) {
        const context = this;
        clearTimeout(timeout);
        timeout = setTimeout(() => func.apply(context, args), delay);
    };
}

document.addEventListener('DOMContentLoaded', () => {
    const guestListElement = document.getElementById('guestList');
    const addGuestFormElement = document.getElementById('addGuestForm');
    const statsTotalInvitedElement = document.getElementById('statsTotalInvited');
    const searchInputElement = document.getElementById('searchInput');

    if (guestListElement || addGuestFormElement) {
        if (typeof fetchGuests === "function") {
            fetchGuests();
        }
        if (typeof fetchStats === "function" && statsTotalInvitedElement) {
             fetchStats();
        }
    }

    if (addGuestFormElement) {
        addGuestFormElement.addEventListener('submit', (event) => {
            event.preventDefault(); addGuest();
        });
    }

    if (searchInputElement) {
        searchInputElement.addEventListener('input', debouncedHandleSearch);
    }

    const qrReaderElementId = "qrReader";
    const qrReaderElement = document.getElementById(qrReaderElementId);
    if (qrReaderElement) {
        html5QrCode = new Html5Qrcode(qrReaderElementId, { verbose: false });
        // console.log("Instância Html5Qrcode criada.");
    } else {
        const scannerSection = document.querySelector('.section.scanner-section');
        if (scannerSection && getComputedStyle(scannerSection).display !== 'none') {
             console.warn("Elemento 'qrReader' não encontrado.");
        }
    }

    beepAudio = document.getElementById('beepSound');
    if (beepAudio) {
        beepAudio.onerror = () => console.error("Erro ao carregar 'beep.mp3'.");
    }

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
        if (document.getElementById('guestList')) fetchGuestsWithCurrentSearchTerm();
        if (document.getElementById('statsTotalInvited') && typeof fetchStats === "function") fetchStats();
    } catch (error) {
        console.error('Erro ao adicionar convidado:', error);
        if(guestAddedInfo) {guestAddedInfo.textContent = 'Erro de rede ao adicionar.'; guestAddedInfo.style.color = 'red';}
    }
}

async function fetchGuests(searchTerm = '') {
    const tbody = document.getElementById('guestList');
    if (!tbody) { console.warn("fetchGuests: #guestList não encontrado."); return; }

    let apiUrl = `${API_BASE_URL}/api/guests`;
    const currentSearchTerm = (typeof searchTerm === 'string') ? searchTerm.trim() : (document.getElementById('searchInput')?.value.trim() || '');

    if (currentSearchTerm) {
        apiUrl += `?search=${encodeURIComponent(currentSearchTerm)}`;
    }

    try {
        const response = await fetch(apiUrl);
        if (!response.ok) {
            console.error('Erro ao buscar convidados:', response.statusText);
            tbody.innerHTML = `<tr><td colspan="6" style="text-align:center;">Erro ao carregar lista. Tente novamente.</td></tr>`;
            return;
        }
        const guests = await response.json();
        tbody.innerHTML = '';

        if (guests.length === 0) {
            const message = currentSearchTerm ?
                            'Nenhum convidado encontrado com este critério.' :
                            'Nenhum convidado cadastrado.';
            tbody.innerHTML = `<tr><td colspan="6" style="text-align:center;">${message}</td></tr>`;
            return;
        }

        guests.forEach(guest => {
            const row = tbody.insertRow();
            row.insertCell().textContent = guest.name;
            row.insertCell().textContent = guest.qr_hash ? guest.qr_hash.substring(0, 10) + '...' : 'N/A';

            const qrCell = row.insertCell();
            if (guest.qr_image_url) {
                const img = document.createElement('img'); img.src = `${guest.qr_image_url}?t=${new Date().getTime()}`;
                img.alt = `QR ${guest.name}`; img.style.cssText = 'width:50px; height:50px; cursor:pointer; object-fit:contain; border:1px solid #eee;';
                img.onclick = () => window.open(img.src, '_blank'); qrCell.appendChild(img);
            } else { qrCell.textContent = 'N/A'; }

            const enteredCell = row.insertCell();
            enteredCell.textContent = guest.entered ? 'Sim' : 'Não';
            enteredCell.style.color = guest.entered ? 'green' : 'red';

            const checkInTimeCell = row.insertCell();
            checkInTimeCell.textContent = guest.check_in_time ? guest.check_in_time : 'N/A';

            const actionsCell = row.insertCell();
            actionsCell.classList.add('actions-cell'); // Adiciona classe para estilização CSS

            // Div para agrupar botões Editar e Marcar
            const topActionGroup = document.createElement('div');
            topActionGroup.className = 'action-button-group';

            const editButton = document.createElement('button');
            editButton.textContent = 'Editar';
            editButton.className = 'button-edit';
            editButton.onclick = () => editGuestNamePrompt(guest.qr_hash, guest.name);
            topActionGroup.appendChild(editButton);

            const toggleButton = document.createElement('button');
            toggleButton.textContent = guest.entered ? 'Marcar Não Entrou' : 'Marcar Entrou';
            toggleButton.className = guest.entered ? 'button-unmark' : 'button-mark';
            // toggleButton.style.marginLeft = '5px'; // Removido, usar gap do CSS
            toggleButton.onclick = () => toggleGuestEntry(guest.qr_hash);
            topActionGroup.appendChild(toggleButton);
            
            actionsCell.appendChild(topActionGroup);

            const removeButton = document.createElement('button');
            removeButton.textContent = 'Remover';
            removeButton.className = 'button-remove';
            // removeButton.style.marginLeft = '5px'; // Removido, CSS cuidará do display block/espaçamento
            removeButton.onclick = () => confirmDeleteGuest(guest.qr_hash, guest.name);
            actionsCell.appendChild(removeButton);
        });
    } catch (error) {
        console.error('Erro de rede ao buscar convidados:', error);
        tbody.innerHTML = `<tr><td colspan="6" style="text-align:center;">Erro de rede. Verifique sua conexão.</td></tr>`;
    }
}

async function editGuestNamePrompt(qrHash, currentName) {
    const newName = prompt("Digite o novo nome para o convidado:", currentName);
    if (newName === null) { return; }
    const trimmedNewName = newName.trim();
    if (!trimmedNewName) { alert("O nome não pode ser vazio."); return; }
    if (trimmedNewName === currentName) { return; }

    try {
        const response = await fetch(`${API_BASE_URL}/api/guests/${qrHash}/edit`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: trimmedNewName })
        });
        const result = await response.json();
        if (!response.ok) {
            alert(`Erro ao editar: ${result.error || 'Erro desconhecido.'}`);
        } else {
            alert(result.message || 'Nome atualizado com sucesso!');
            fetchGuestsWithCurrentSearchTerm();
        }
    } catch (error) {
        console.error('Erro de rede ao editar convidado:', error);
        alert('Erro de rede ao tentar editar o nome.');
    }
}

function handleSearch() {
    const searchTerm = document.getElementById('searchInput').value;
    fetchGuests(searchTerm);
}
const debouncedHandleSearch = debounce(handleSearch, SEARCH_DEBOUNCE_MS);

function fetchGuestsWithCurrentSearchTerm(manualRefresh = false) {
    const searchTerm = document.getElementById('searchInput').value;
    fetchGuests(searchTerm);
}

function confirmDeleteGuest(qrHash, guestName) { if (confirm(`Tem certeza que deseja remover "${guestName}"?`)) { deleteGuest(qrHash); } }

async function deleteGuest(qrHash) {
    try {
        const response = await fetch(`${API_BASE_URL}/api/guests/${qrHash}`, { method: 'DELETE' });
        const result = await response.json();
        if (!response.ok) { alert(`Erro ao remover: ${result.error || 'Erro.'}`); return; }
        alert(result.message || 'Removido.');
        fetchGuestsWithCurrentSearchTerm();
        if (document.getElementById('statsTotalInvited') && typeof fetchStats === "function") fetchStats();
    } catch (error) { console.error('Erro de rede ao remover:', error); alert('Erro de rede.'); }
}

async function toggleGuestEntry(qrHash) {
    try {
        const response = await fetch(`${API_BASE_URL}/api/guests/${qrHash}/toggle_entry`, { method: 'PUT' });
        const result = await response.json(); if (!response.ok) { alert(`Erro: ${result.error}`); return; }
        // console.log(result.message); // Opcional: logar a mensagem de sucesso
        fetchGuestsWithCurrentSearchTerm();
        if (document.getElementById('statsTotalInvited') && typeof fetchStats === "function") fetchStats();
    } catch (error) { console.error('Erro ao alterar status:', error); }
}

function exportGuests(format) {
    const searchTerm = document.getElementById('searchInput').value.trim();
    let exportUrl = `${API_BASE_URL}/api/guests/export/${format}`;
    if (searchTerm) { exportUrl += `?search=${encodeURIComponent(searchTerm)}`; }
    window.open(exportUrl, '_blank');
}

async function fetchStats() {
    const statsTotalInvitedEl = document.getElementById('statsTotalInvited');
    if (!statsTotalInvitedEl) { return; }
    try {
        const response = await fetch(`${API_BASE_URL}/api/stats`);
        if (!response.ok) {
            statsTotalInvitedEl.textContent = 'Erro';
            document.getElementById('statsEnteredCount').textContent = '-';
            document.getElementById('statsNotEnteredCount').textContent = '-';
            document.getElementById('statsPercentageEntered').textContent = '- %';
            return;
        }
        const stats = await response.json();
        statsTotalInvitedEl.textContent = stats.total_invited;
        document.getElementById('statsEnteredCount').textContent = stats.entered_count;
        document.getElementById('statsNotEnteredCount').textContent = stats.not_entered_count;
        document.getElementById('statsPercentageEntered').textContent = stats.percentage_entered + " %";
        if (typeof updateAttendanceChart === "function") {
             updateAttendanceChart(stats.entered_count, stats.not_entered_count);
        }
    } catch (error) {
        statsTotalInvitedEl.textContent = 'Erro de Rede'; console.error("Erro de rede ao buscar estatísticas:", error);
    }
}

function updateAttendanceChart(entered, notEntered) {
    const ctx = document.getElementById('attendanceChart');
    if (!ctx) { return; }
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
    } else {
        attendanceChartInstance = new Chart(ctx, configChart);
    }
}

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
    if (decodedText === lastScannedHash && (currentTime - lastScanTime) < SCAN_COOLDOWN_MS) { return; }
    showOverlayFeedback('processing', '<span class="spinner"></span>', `Processando...`);
    lastScannedHash = decodedText; lastScanTime = currentTime;
    processScannedQr(decodedText);
}
function onScanFailure(error) { /* console.warn(`[FRONTEND] Falha no scan: ${error}`); */ }

async function processScannedQr(qrHash) {
    try {
        const response = await fetch(`${API_BASE_URL}/api/guests/${qrHash}/enter`, { method: 'POST' });
        const result = await response.json();
        if (!response.ok) {
             showOverlayFeedback('error', '✗', result.error || 'QR inválido/não encontrado.');
        } else {
            let message = result.message;
            if (result.is_new_entry === true) {
                showOverlayFeedback('success', '✓', message);
                if (beepAudio) { beepAudio.currentTime = 0; beepAudio.play().catch(e => console.error("Erro ao tocar beep:", e)); }
            } else {
                showOverlayFeedback('warning', 'ⓘ', message);
            }
            if (document.getElementById('guestList')) fetchGuestsWithCurrentSearchTerm();
            if (document.getElementById('statsTotalInvited') && typeof fetchStats === "function") fetchStats();
        }
    } catch (error) {
        showOverlayFeedback('error', '✗', 'Erro de rede ao validar QR.'); console.error('[FRONTEND] Erro de rede:', error);
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
        fps: 10,
        qrbox: (viewfinderWidth, viewfinderHeight) => {
            let edgePercentage = 0.65;
            let qrboxEdgeSize = Math.floor(Math.min(viewfinderWidth, viewfinderHeight) * edgePercentage);
            qrboxEdgeSize = Math.max(150, qrboxEdgeSize);
            qrboxEdgeSize = Math.min(300, qrboxEdgeSize);
            return { width: qrboxEdgeSize, height: qrboxEdgeSize };
        },
        rememberLastUsedCamera: true,
        supportedScanTypes: [Html5QrcodeScanType.SCAN_TYPE_CAMERA]
    };

    if (html5QrCode.isScanning) { console.log("Scanner já ativo."); return; }

    if (textFeedback) { textFeedback.textContent = 'Iniciando câmera...'; textFeedback.className = 'processing';}

    html5QrCode.start( videoConstraints, configScanner, onScanSuccess, onScanFailure)
    .then(() => {
        if(startBtn) startBtn.style.display = 'none';
        if(stopBtn) stopBtn.style.display = 'inline-block';
        if(textFeedback) { textFeedback.textContent = 'Câmera ativa. Aponte para QR Code.'; textFeedback.className = ''; }
        console.log("Scanner iniciado.");
    }).catch(err => {
        let errorMsg = `Erro câmera: ${err}. Verifique HTTPS/permissões.`;
        if (String(err).includes("Requested camera not available")) {
            errorMsg = "Câmera não encontrada ou não permitida. Verifique as permissões.";
        }
        if(textFeedback) { textFeedback.textContent = errorMsg; textFeedback.className = 'error'; }
        if (msgContainer) msgContainer.style.display = 'block';
        if (qrScannerWrapper) qrScannerWrapper.style.display = 'none';
        if(startBtn) startBtn.style.display = 'inline-block';
        if(stopBtn) stopBtn.style.display = 'none';
        console.error("Erro ao iniciar scanner:", err);
    });
}
async function stopQrScanner() {
    if (!html5QrCode || !html5QrCode.isScanning) {} else {
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
        overlay.classList.remove('visible', 'success-bg', 'error-bg', 'warning-bg', 'processing-bg');
    }
    if(textFeedback) {
        if (!textFeedback.className.includes('error')) {
            textFeedback.textContent = 'Scanner parado.';
            textFeedback.className = '';
        }
    }
}