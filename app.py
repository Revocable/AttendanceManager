import os
import hashlib
import qrcode
import requests
import random
import string
import secrets
from PIL import Image, ImageDraw, ImageFont as PILImageFont
import uuid
import pytz
import io
import csv
from fpdf import FPDF, XPos, YPos
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask import (Flask, request, jsonify, render_template, url_for, Response, 
                   send_from_directory, redirect, flash, abort, make_response)
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from dotenv import load_dotenv

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# Carrega variáveis de ambiente do .env
load_dotenv()

# --- Configuração do App ---
app = Flask(__name__)
basedir = os.path.abspath(os.path.dirname(__file__))

# Configurações do .env
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY')
if not app.config['SECRET_KEY']:
    raise ValueError("Nenhuma SECRET_KEY definida no arquivo .env")

ABACATE_API_KEY = os.environ.get('ABACATE_API_KEY')
if not ABACATE_API_KEY:
    raise ValueError("Nenhuma ABACATE_API_KEY definida no arquivo .env")

# Configuração do Banco de Dados
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'instance', 'party.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Configuração do Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = "Por favor, faça login para acessar esta página."
login_manager.login_message_category = "info"

# --- Constantes e Configuração de Pastas ---
QR_CODE_FOLDER_NAME = 'qr_codes'
PARTY_LOGOS_FOLDER_NAME = 'party_logos'
QR_CODE_SAVE_PATH = os.path.join(basedir, 'static', QR_CODE_FOLDER_NAME)
PARTY_LOGOS_SAVE_PATH = os.path.join(basedir, 'static', PARTY_LOGOS_FOLDER_NAME)
FONT_PATH = os.path.join(basedir, "Montserrat-Regular.ttf")
BRASILIA_TZ = pytz.timezone('America/Sao_Paulo')

if not os.path.exists(QR_CODE_SAVE_PATH): os.makedirs(QR_CODE_SAVE_PATH)
if not os.path.exists(PARTY_LOGOS_SAVE_PATH): os.makedirs(PARTY_LOGOS_SAVE_PATH)
if not os.path.exists(os.path.join(basedir, 'instance')): os.makedirs(os.path.join(basedir, 'instance'))

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- Modelos do Banco de Dados ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    tax_id = db.Column(db.String(20), unique=True, nullable=True)
    cellphone = db.Column(db.String(20), nullable=True)
    parties = db.relationship('Party', backref='owner', lazy=True, cascade="all, delete-orphan")
    is_vip = db.Column(db.Boolean, default=False, nullable=False)
    payment_charge_id = db.Column(db.String(120), nullable=True, unique=True)
    payment_status = db.Column(db.String(30), default='not_started', nullable=True)

    def set_password(self, password): self.password_hash = generate_password_hash(password)
    def check_password(self, password): return check_password_hash(self.password_hash, password)

class Party(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    party_code = db.Column(db.String(6), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(BRASILIA_TZ))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    guests = db.relationship('Guest', backref='party', lazy=True, cascade="all, delete-orphan")
    logo_filename = db.Column(db.String(255), nullable=True)
    shareable_link_id = db.Column(db.String(16), unique=True, nullable=False)
    public_description = db.Column(db.Text, nullable=True)
    show_guest_count = db.Column(db.Boolean, nullable=False, default=True)

class Guest(db.Model):
    id = db.Column(db.Integer, primary_key=True); name = db.Column(db.String(100), nullable=False)
    qr_hash = db.Column(db.String(64), unique=True, nullable=False)
    entered = db.Column(db.Boolean, default=False, nullable=False)
    qr_image_filename = db.Column(db.String(255), nullable=True); check_in_time = db.Column(db.DateTime, nullable=True)
    party_id = db.Column(db.Integer, db.ForeignKey('party.id'), nullable=False)
    __table_args__ = (db.UniqueConstraint('name', 'party_id', name='_name_party_uc'),)
    @property
    def qr_image_url(self): return url_for('static', filename=f'{QR_CODE_FOLDER_NAME}/{self.qr_image_filename}') if self.qr_image_filename else None
    def get_check_in_time_str(self):
        if self.check_in_time: return self.check_in_time.astimezone(BRASILIA_TZ).strftime('%d/%m/%Y %H:%M:%S')
        return "N/A"

with app.app_context():
    db.create_all()

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# --- Funções Auxiliares ---
def generate_qr_code_image(qr_data, guest_name, filename_base):
    qr_fn = f"{filename_base}.png"; qr_fp = os.path.join(QR_CODE_SAVE_PATH, qr_fn)
    try:
        qr_instance = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=10, border=4)
        qr_instance.add_data(qr_data); qr_instance.make(fit=True)
        img_qr = qr_instance.make_image(fill_color="black", back_color="white").convert('RGB')
        padding_bottom_for_text = 60; text_color = (0, 0, 0); background_color_canvas = (255, 255, 255); font_size_pil = 30
        pil_font = PILImageFont.load_default()
        if os.path.exists(FONT_PATH):
            try: pil_font = PILImageFont.truetype(FONT_PATH, font_size_pil)
            except IOError: app.logger.warning("Fonte não pôde ser carregada, usando padrão.")
        new_width = img_qr.width; new_height = img_qr.height + padding_bottom_for_text
        img_canvas = Image.new('RGB', (new_width, new_height), background_color_canvas)
        img_canvas.paste(img_qr, (0, 0)); draw = ImageDraw.Draw(img_canvas)
        try: text_bbox = draw.textbbox((0, 0), guest_name, font=pil_font); text_width = text_bbox[2] - text_bbox[0]
        except AttributeError: text_width, _ = draw.textsize(guest_name, font=pil_font)
        text_x = (new_width - text_width) / 2; text_y = img_qr.height + (padding_bottom_for_text - font_size_pil) / 2 - 5
        draw.text((text_x, text_y), guest_name, font=pil_font, fill=text_color)
        img_canvas.save(qr_fp)
        return qr_fn
    except Exception as e: app.logger.error(f"Erro ao gerar QR: {e}"); return None

def check_party_ownership(party):
    if party.user_id != current_user.id: abort(403)

# --- ROTAS DE AUTENTICAÇÃO ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated: return redirect(url_for('dashboard'))
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form.get('username')).first()
        if user and user.check_password(request.form.get('password')):
            login_user(user, remember=True); return redirect(url_for('dashboard'))
        flash('Login inválido.', 'danger')
    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_user.is_authenticated: return redirect(url_for('dashboard'))
    if request.method == 'POST':
        username = request.form.get('username'); email = request.form.get('email'); password = request.form.get('password')
        if User.query.filter_by(username=username).first():
            flash('Este nome de usuário já existe.', 'danger'); return redirect(url_for('signup'))
        if User.query.filter_by(email=email).first():
            flash('Este email já está em uso.', 'danger'); return redirect(url_for('signup'))
        new_user = User(username=username, email=email); new_user.set_password(password)
        db.session.add(new_user); db.session.commit()
        login_user(new_user)
        flash('Conta criada com sucesso!', 'success'); return redirect(url_for('dashboard'))
    return render_template('signup.html')

@app.route('/logout')
@login_required
def logout():
    logout_user(); return redirect(url_for('landing'))

# --- ROTAS PRINCIPAIS E DE GERENCIAMENTO ---
@app.route('/')
def landing():
    if current_user.is_authenticated: return redirect(url_for('dashboard'))
    return render_template('landing.html')

@app.route('/dashboard')
@login_required
def dashboard():
    parties = Party.query.filter_by(user_id=current_user.id).order_by(Party.created_at.desc()).all()
    can_create_party = current_user.is_vip or len(parties) < 1
    return render_template('dashboard.html', parties=parties, can_create_party=can_create_party)

def generate_unique_code(model, field, length=8):
    chars = string.ascii_uppercase + string.digits
    while True:
        code = ''.join(random.choices(chars, k=length))
        if not model.query.filter(getattr(model, field) == code).first():
            return code

@app.route('/party/create', methods=['POST'])
@login_required
def create_party():
    if not current_user.is_vip and len(current_user.parties) >= 1:
        flash('Você atingiu o limite de 1 festa. Faça o upgrade para VIP!', 'warning'); return redirect(url_for('upgrade'))
    party_name = request.form.get('party_name')
    if not party_name or not party_name.strip():
        flash('O nome da festa não pode ser vazio.', 'danger'); return redirect(url_for('dashboard'))
    
    party_code = generate_unique_code(Party, 'party_code', 6).upper().replace("_", "A").replace("-", "B")[:6]
    shareable_link_id = secrets.token_urlsafe(12)

    new_party = Party(
        name=party_name, owner=current_user, party_code=party_code, shareable_link_id=shareable_link_id
    )
    db.session.add(new_party); db.session.commit()
    flash(f'Festa "{party_name}" criada!', 'success'); return redirect(url_for('party_manager', party_id=new_party.id))

@app.route('/party/<int:party_id>')
@login_required
def party_manager(party_id):
    party = db.session.get(Party, party_id) or abort(404)
    check_party_ownership(party)
    can_add_guest = current_user.is_vip or len(party.guests) < 50
    return render_template('party_manager.html', party=party, can_add_guest=can_add_guest)

@app.route('/party/<int:party_id>/delete', methods=['POST'])
@login_required
def delete_party(party_id):
    party = db.session.get(Party, party_id) or abort(404)
    check_party_ownership(party)
    if party.logo_filename:
        try: os.remove(os.path.join(PARTY_LOGOS_SAVE_PATH, party.logo_filename))
        except OSError: pass
    for guest in party.guests:
        if guest.qr_image_filename:
            try: os.remove(os.path.join(QR_CODE_SAVE_PATH, guest.qr_image_filename))
            except OSError: pass
    db.session.delete(party); db.session.commit()
    flash(f'A festa "{party.name}" foi removida.', 'success'); return redirect(url_for('dashboard'))

# --- ROTAS DE CUSTOMIZAÇÃO DA PÁGINA PÚBLICA ---
@app.route('/party/<int:party_id>/upload_logo', methods=['POST'])
@login_required
def upload_logo(party_id):
    party = db.session.get(Party, party_id) or abort(404)
    check_party_ownership(party)
    if 'party_logo' not in request.files:
        flash('Nenhum arquivo selecionado.', 'danger'); return redirect(url_for('party_manager', party_id=party_id))
    file = request.files['party_logo']
    if file.filename == '':
        flash('Nenhum arquivo selecionado.', 'danger'); return redirect(url_for('party_manager', party_id=party_id))
    if file and allowed_file(file.filename):
        if party.logo_filename:
            try: os.remove(os.path.join(PARTY_LOGOS_SAVE_PATH, party.logo_filename))
            except OSError: pass
        filename = secure_filename(file.filename)
        unique_id = uuid.uuid4().hex
        ext = filename.rsplit('.', 1)[1].lower()
        new_filename = f"{party_id}_{unique_id}.{ext}"
        file.save(os.path.join(PARTY_LOGOS_SAVE_PATH, new_filename))
        party.logo_filename = new_filename
        db.session.commit()
        flash('Logo da festa atualizado com sucesso!', 'success')
    else:
        flash('Tipo de arquivo inválido. Use apenas PNG, JPG, JPEG ou GIF.', 'danger')
    return redirect(url_for('party_manager', party_id=party_id))

@app.route('/party/<int:party_id>/update_details', methods=['POST'])
@login_required
def update_party_details(party_id):
    party = db.session.get(Party, party_id) or abort(404)
    check_party_ownership(party)
    description = request.form.get('public_description')
    party.public_description = description
    db.session.commit()
    flash('Informações da página pública atualizadas!', 'success')
    return redirect(url_for('party_manager', party_id=party_id))

@app.route('/party/<int:party_id>/toggle_guest_count', methods=['POST'])
@login_required
def toggle_guest_count(party_id):
    party = db.session.get(Party, party_id) or abort(404)
    check_party_ownership(party)
    party.show_guest_count = not party.show_guest_count
    db.session.commit()
    flash('Visibilidade da contagem de convidados atualizada.', 'success')
    return redirect(url_for('party_manager', party_id=party_id))

# --- ROTAS PÚBLICAS ---
@app.route('/p/<shareable_link_id>')
def public_party_page(shareable_link_id):
    party = Party.query.filter_by(shareable_link_id=shareable_link_id).first_or_404()
    stats = get_party_stats_data(party.id)
    return render_template('public_party_card.html', party=party, stats=stats)

@app.route('/scanner', methods=['GET', 'POST'])
def public_scanner():
    if request.method == 'POST':
        party_code_input = request.form.get('party_code', '').upper()
        party = Party.query.filter_by(party_code=party_code_input).first()
        if party:
            resp = make_response(render_template('scanner.html', party=party))
            resp.set_cookie('party_code', party_code_input, max_age=30*24*60*60)
            return resp
        else:
            flash('Código da festa inválido. Tente novamente.', 'danger')
    party_code_from_cookie = request.cookies.get('party_code')
    if party_code_from_cookie:
        party = Party.query.filter_by(party_code=party_code_from_cookie).first()
        if party: return render_template('scanner.html', party=party)
    return render_template('scanner_login.html')

@app.route('/scanner/forget')
def forget_scanner():
    resp = make_response(redirect(url_for('public_scanner')))
    resp.set_cookie('party_code', '', expires=0)
    flash('Você se desconectou do scanner.', 'info')
    return resp
    
# --- ROTAS DE PAGAMENTO ---
@app.route('/upgrade')
@login_required
def upgrade():
    if current_user.is_vip: flash('Você já é um usuário VIP!', 'info'); return redirect(url_for('dashboard'))
    return render_template('upgrade.html')

@app.route('/complete_profile', methods=['GET', 'POST'])
@login_required
def complete_profile():
    if current_user.is_vip: return redirect(url_for('dashboard'))
    if request.method == 'POST':
        tax_id = request.form.get('tax_id'); cellphone = request.form.get('cellphone')
        if not tax_id or not cellphone:
            flash("CPF e Telefone são obrigatórios.", 'danger'); return render_template('complete_profile.html')
        existing_user = User.query.filter(User.tax_id == tax_id, User.id != current_user.id).first()
        if existing_user:
            flash("Este CPF já está associado a outra conta.", 'danger'); return render_template('complete_profile.html')
        current_user.tax_id = tax_id; current_user.cellphone = cellphone
        db.session.commit()
        flash("Perfil atualizado! Agora vamos para o pagamento.", 'success')
        return redirect(url_for('create_payment'))
    return render_template('complete_profile.html')

@app.route('/payment/create', methods=['POST', 'GET'])
@login_required
def create_payment():
    if current_user.is_vip: return redirect(url_for('dashboard'))
    if not all([current_user.tax_id, current_user.cellphone]):
        flash("Por favor, complete seu perfil com CPF e Telefone.", 'warning'); return redirect(url_for('complete_profile'))
    url = "https://api.abacatepay.com/v1/pixQrCode/create"
    headers = { "Authorization": f"Bearer {ABACATE_API_KEY}", "Content-Type": "application/json" }
    payload = { "amount": 10000, "expiresIn": 3600, "description": f"Upgrade para conta VIP QRPass - Usuário: {current_user.username}",
        "customer": { "name": current_user.username, "email": current_user.email, "taxId": current_user.tax_id, "cellphone": current_user.cellphone }
    }
    try:
        response = requests.post(url, json=payload, headers=headers)
        if response.status_code != 200: app.logger.error(f"Erro da API Abacate Pay: {response.status_code} - {response.text}")
        response.raise_for_status()
        response_data = response.json().get('data', {})
        pix_qr_code = response_data.get('brCodeBase64'); pix_emv = response_data.get('brCode'); pix_transaction_id = response_data.get('id')
        if not all([pix_qr_code, pix_emv, pix_transaction_id]): raise ValueError("Resposta da API de PIX incompleta.")
        current_user.payment_charge_id = pix_transaction_id; current_user.payment_status = 'pending'
        db.session.commit()
        return render_template('show_pix.html', pix_qr_code=pix_qr_code, pix_emv=pix_emv, pix_id=pix_transaction_id)
    except requests.exceptions.RequestException as e:
        app.logger.error(f"Erro de comunicação com Abacate Pay: {e}"); flash('Não foi possível gerar a cobrança PIX. Tente novamente.', 'danger')
        return redirect(url_for('upgrade'))
    except (ValueError, KeyError) as e:
        app.logger.error(f"Erro ao processar resposta da API de PIX: {e}"); flash('Ocorreu um erro inesperado ao processar o pagamento.', 'danger')
        return redirect(url_for('upgrade'))

@app.route('/payment/check_status/<pix_id>')
@login_required
def check_payment_status(pix_id):
    if current_user.payment_charge_id != pix_id: return jsonify({'status': 'error', 'message': 'Unauthorized'}), 403
    url = "https://api.abacatepay.com/v1/pixQrCode/check"; headers = {"Authorization": f"Bearer {ABACATE_API_KEY}"}; params = {"id": pix_id}
    try:
        response = requests.get(url, headers=headers, params=params); response.raise_for_status()
        data = response.json().get('data', {}); status = data.get('status')
        if status == 'PAID':
            user = db.session.get(User, current_user.id)
            if not user.is_vip: user.is_vip = True; user.payment_status = 'paid'; db.session.commit()
        return jsonify({'status': status})
    except requests.exceptions.RequestException as e:
        app.logger.error(f"Erro ao verificar status: {e}"); return jsonify({'status': 'error', 'message': 'Falha ao verificar status'}), 500

@app.route('/webhooks/abacatepay', methods=['POST'])
def abacatepay_webhook():
    payload = request.get_json(); app.logger.info(f"Webhook recebido: {payload}")
    if not payload or 'event' not in payload or 'data' not in payload: return jsonify({'status': 'error', 'message': 'Payload inválido'}), 400
    event_type = payload.get('event'); webhook_data = payload.get('data', {}); transaction_id = webhook_data.get('id')
    if event_type == 'pix_qr_code.paid' and transaction_id:
        user = User.query.filter_by(payment_charge_id=transaction_id).first()
        if user:
            app.logger.info(f"Confirmando pagamento via webhook para {user.username} (PIX ID: {transaction_id})")
            user.is_vip = True; user.payment_status = 'paid'; db.session.commit()
            return jsonify({'status': 'success'}), 200
        else: app.logger.warning(f"Usuário não encontrado para PIX ID: {transaction_id}")
    return jsonify({'status': 'received'}), 200

# --- ROTAS DA API ---
def get_party_stats_data(party_id):
    total_invited = Guest.query.filter_by(party_id=party_id).count()
    entered_count = Guest.query.filter_by(party_id=party_id, entered=True).count()
    not_entered_count = total_invited - entered_count
    percentage_entered = 0.0
    if total_invited > 0: percentage_entered = round((entered_count / total_invited) * 100, 2)
    return {'total_invited': total_invited, 'entered_count': entered_count, 'not_entered_count': not_entered_count, 'percentage_entered': percentage_entered}

@app.route('/api/party/<int:party_id>/stats', methods=['GET'])
def get_stats(party_id):
    party = db.session.get(Party, party_id) or abort(404); stats = get_party_stats_data(party_id); return jsonify(stats)

@app.route('/api/party/<int:party_id>/guests', methods=['POST'])
@login_required
def add_guest(party_id):
    party = db.session.get(Party, party_id) or abort(404); check_party_ownership(party)
    if not current_user.is_vip and len(party.guests) >= 50: return jsonify({'error': 'Limite de 50 convidados atingido.'}), 403
    data = request.get_json(); name = data['name'].strip()
    if not name: return jsonify({'error': 'Nome vazio'}), 400
    if Guest.query.filter_by(name=name, party_id=party_id).first(): return jsonify({'error': f'Convidado "{name}" já existe.'}), 409
    unique_id_for_qr = str(uuid.uuid4()); qr_hash = hashlib.sha256(unique_id_for_qr.encode('utf-8')).hexdigest()
    while Guest.query.filter_by(qr_hash=qr_hash).first():
        unique_id_for_qr = str(uuid.uuid4()); qr_hash = hashlib.sha256(unique_id_for_qr.encode('utf-8')).hexdigest()
    qr_image_filename = generate_qr_code_image(qr_hash, name, qr_hash)
    if not qr_image_filename: return jsonify({'error': 'Falha ao gerar QR'}), 500
    new_guest = Guest(name=name, qr_hash=qr_hash, qr_image_filename=qr_image_filename, party_id=party_id)
    db.session.add(new_guest); db.session.commit()
    return jsonify({'id': new_guest.id, 'name': new_guest.name, 'qr_hash': new_guest.qr_hash, 'entered': new_guest.entered, 'qr_image_url': new_guest.qr_image_url, 'check_in_time': new_guest.get_check_in_time_str() }), 201

@app.route('/api/party/<int:party_id>/guests', methods=['GET'])
@login_required
def get_guests_api(party_id):
    party = db.session.get(Party, party_id) or abort(404); check_party_ownership(party)
    search_term = request.args.get('search', None)
    query = Guest.query.filter_by(party_id=party_id)
    if search_term and search_term.strip(): query = query.filter(Guest.name.ilike(f'%{search_term.strip()}%'))
    guests_list = query.order_by(Guest.name).all()
    return jsonify([{'id': g.id, 'name': g.name, 'qr_hash': g.qr_hash, 'entered': g.entered, 'qr_image_url': g.qr_image_url, 'check_in_time': g.get_check_in_time_str()} for g in guests_list])

@app.route('/api/party/<int:party_id>/guests/<qr_hash>/enter', methods=['POST'])
def mark_entered(party_id, qr_hash):
    guest = Guest.query.filter_by(qr_hash=qr_hash, party_id=party_id).first()
    if not guest: return jsonify({'error': 'QR inválido para esta festa'}), 404
    current_time_brasilia = datetime.now(BRASILIA_TZ)
    if guest.entered:
        message = f'{guest.name} já entrou às {guest.get_check_in_time_str()}.'; is_new_entry = False
    else:
        guest.entered = True; guest.check_in_time = current_time_brasilia; db.session.commit()
        is_new_entry = True; message = f'Entrada liberada! Bem-vindo(a), {guest.name}!'
    return jsonify({'id': guest.id, 'name': guest.name, 'qr_hash': guest.qr_hash, 'entered': guest.entered, 'message': message, 'is_new_entry': is_new_entry, 'check_in_time': guest.get_check_in_time_str()})

@app.route('/api/party/<int:party_id>/guests/<qr_hash>/edit', methods=['PUT'])
@login_required
def edit_guest_name(party_id, qr_hash):
    party = db.session.get(Party, party_id) or abort(404); check_party_ownership(party); guest = Guest.query.filter_by(qr_hash=qr_hash, party_id=party_id).first_or_404()
    data = request.get_json(); new_name = data['name'].strip()
    if Guest.query.filter(Guest.name == new_name, Guest.party_id == party_id, Guest.qr_hash != qr_hash).first():
        return jsonify({'error': f'Já existe um convidado com o nome "{new_name}"'}), 409
    guest.name = new_name; new_qr_image_filename = generate_qr_code_image(guest.qr_hash, new_name, guest.qr_hash)
    if new_qr_image_filename: guest.qr_image_filename = new_qr_image_filename
    db.session.commit()
    return jsonify({'id': guest.id, 'name': guest.name, 'qr_hash': guest.qr_hash, 'entered': guest.entered, 'qr_image_url': guest.qr_image_url, 'check_in_time': guest.get_check_in_time_str(), 'message': f'Nome atualizado para "{new_name}".'}), 200

@app.route('/api/party/<int:party_id>/guests/<qr_hash>/toggle_entry', methods=['PUT'])
@login_required
def toggle_entry_manually(party_id, qr_hash):
    party = db.session.get(Party, party_id) or abort(404); check_party_ownership(party); guest = Guest.query.filter_by(qr_hash=qr_hash, party_id=party_id).first_or_404()
    current_time_brasilia = datetime.now(BRASILIA_TZ)
    guest.entered = not guest.entered
    if guest.entered: guest.check_in_time = current_time_brasilia; action = f"entrou"
    else: guest.check_in_time = None; action = "NÃO entrou"
    db.session.commit()
    return jsonify({'id': guest.id, 'name': guest.name, 'qr_hash': guest.qr_hash, 'entered': guest.entered, 'message': f'Status de {guest.name} alterado: {action}.', 'check_in_time': guest.get_check_in_time_str()})

@app.route('/api/party/<int:party_id>/guests/<qr_hash>', methods=['DELETE'])
@login_required
def delete_guest(party_id, qr_hash):
    party = db.session.get(Party, party_id) or abort(404); check_party_ownership(party); guest = Guest.query.filter_by(qr_hash=qr_hash, party_id=party_id).first_or_404()
    if guest.qr_image_filename:
        qr_image_path = os.path.join(QR_CODE_SAVE_PATH, guest.qr_image_filename)
        if os.path.exists(qr_image_path): os.remove(qr_image_path)
    db.session.delete(guest); db.session.commit()
    return jsonify({'message': f'Convidado {guest.name} removido.'}), 200

# (Classe PDF e rotas de exportação não mudam)
class PDF(FPDF):
    def __init__(self, orientation='P', unit='mm', format='A4', party_name=''):
        super().__init__(orientation, unit, format); self.montserrat_font_path = FONT_PATH; self.font_name = 'Montserrat'; self.default_font = 'Helvetica'; self.current_font_family = self.default_font; self.party_name = party_name
        if os.path.exists(self.montserrat_font_path):
            try: self.add_font(self.font_name, '', self.montserrat_font_path, uni=True); self.add_font(self.font_name, 'B', self.montserrat_font_path, uni=True); self.add_font(self.font_name, 'I', self.montserrat_font_path, uni=True); self.current_font_family = self.font_name
            except Exception: pass
    def header(self): self.set_font(self.current_font_family, 'B', 16); title = f'Relatório do Evento: {self.party_name}'; title_w = self.get_string_width(title); self.set_x((self.w - title_w) / 2); self.cell(title_w, 10, title, border=0, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C'); self.ln(5)
    def footer(self): self.set_y(-15); self.set_font(self.current_font_family, 'I', 8); self.cell(0, 10, f'Página {self.page_no()}/{{nb}}', border=0, new_x=XPos.RIGHT, new_y=YPos.TOP, align='C')
    def draw_stats_summary(self, stats_data):
        self.set_font(self.current_font_family, 'B', 11); self.cell(0, 10, "Estatísticas do evento", border=0, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='L'); self.ln(1)
        page_width = self.w - self.l_margin - self.r_margin; col_width_stat = page_width / 4; stat_box_height = 12; line_height_label = 4.5; line_height_value = 5.5; padding_top_box = (stat_box_height - (line_height_label + line_height_value)) / 2; fill_color_stat_box = (240, 240, 240); value_text_color = (0, 100, 200); label_text_color = (0, 0, 0); current_x = self.l_margin; base_y = self.get_y()
        stats_items = [("Convidados:", str(stats_data['total_invited'])), ("Entraram:", str(stats_data['entered_count'])), ("Não Entraram:", str(stats_data['not_entered_count'])), ("Comparecimento:", f"{stats_data['percentage_entered']:.2f}%")]
        for i, (label, value) in enumerate(stats_items):
            self.set_fill_color(*fill_color_stat_box); self.rect(current_x, base_y, col_width_stat, stat_box_height, 'F'); self.set_draw_color(200, 200, 200); self.rect(current_x, base_y, col_width_stat, stat_box_height, 'D')
            y_pos_label = base_y + padding_top_box; self.set_xy(current_x, y_pos_label); self.set_text_color(*label_text_color); self.set_font(self.current_font_family, '', 8.5)
            self.cell(col_width_stat, line_height_label, label, border=0, align='C'); y_pos_value = y_pos_label + line_height_label; self.set_xy(current_x, y_pos_value); self.set_text_color(*value_text_color)
            self.set_font(self.current_font_family, 'B', 10); self.cell(col_width_stat, line_height_value, value, border=0, align='C'); self.set_text_color(*label_text_color); current_x += col_width_stat
        self.set_y(base_y + stat_box_height); self.ln(5)
    def draw_pie_chart(self, stats_data, y_offset, chart_size_mm=70):
        labels = 'Entraram', 'Não Entraram'; sizes = [stats_data['entered_count'], stats_data['not_entered_count']]; colors = ['#4BC0C0', '#FF6384']
        if sum(sizes) == 0: self.cell(0, 10, "Sem dados para o gráfico.", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C'); return
        explode = (0.05, 0) if sizes[0] > 0 else (0,0)
        fig, ax = plt.subplots(figsize=(chart_size_mm / 25.4, chart_size_mm / 25.4), dpi=100)
        wedges, texts, autotexts = ax.pie(sizes, explode=explode, labels=None, colors=colors, autopct='%1.1f%%', shadow=False, startangle=90)
        for autotext in autotexts: autotext.set_color('white'); autotext.set_fontweight('bold')
        ax.axis('equal'); ax.legend(wedges, [f'{l} ({s})' for l, s in zip(labels, sizes)], loc="center left", bbox_to_anchor=(1, 0, 0.5, 1))
        img_buffer = io.BytesIO(); plt.savefig(img_buffer, format='png', bbox_inches='tight', transparent=True); plt.close(fig)
        self.image(img_buffer, x=(self.w - chart_size_mm) / 2, y=self.get_y(), w=chart_size_mm, h=chart_size_mm, type='PNG'); self.set_y(self.get_y() + chart_size_mm + 5)
    def chapter_body(self, guests_data_table):
        self.set_font(self.current_font_family, 'B', 11); self.cell(0, 10, "Lista de Convidados", border=0, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C'); self.ln(1)
        self.set_font(self.current_font_family, 'B', 9); self.set_fill_color(230, 230, 230); col_widths = {"name": 100, "status": 30, "check_in": 40}
        start_x = self.l_margin + (self.w - 2 * self.l_margin - sum(col_widths.values())) / 2
        self.set_x(start_x); self.cell(col_widths["name"], 8, 'Nome', 1, 0, 'C', 1); self.cell(col_widths["status"], 8, 'Entrou?', 1, 0, 'C', 1); self.cell(col_widths["check_in"], 8, 'Data Check-in', 1, 1, 'C', 1)
        self.set_font(self.current_font_family, '', 8.5)
        for i, guest_obj in enumerate(guests_data_table):
            self.set_x(start_x); self.set_fill_color(248, 248, 248) if i % 2 else self.set_fill_color(255, 255, 255)
            self.cell(col_widths["name"], 7, guest_obj.name, 1, 0, 'L', 1); self.cell(col_widths["status"], 7, 'Sim' if guest_obj.entered else 'Não', 1, 0, 'C', 1); self.cell(col_widths["check_in"], 7, guest_obj.get_check_in_time_str(), 1, 1, 'C', 1)

@app.route('/api/party/<int:party_id>/export/csv')
@login_required
def export_guests_csv(party_id):
    party = db.session.get(Party, party_id) or abort(404); check_party_ownership(party); guests_data = get_all_guests_for_export(party_id); si = io.StringIO(); cw = csv.writer(si)
    cw.writerow(['Nome', 'Status Entrada', 'Data Check-in'])
    for guest_obj in guests_data: cw.writerow([guest_obj.name, 'Sim' if guest_obj.entered else 'Não', guest_obj.get_check_in_time_str()])
    return Response(si.getvalue(), mimetype="text/csv", headers={"Content-disposition": f"attachment; filename=lista_{party.name.replace(' ', '_')}.csv"})

@app.route('/api/party/<int:party_id>/export/pdf')
@login_required
def export_guests_pdf(party_id):
    party = db.session.get(Party, party_id) or abort(404); check_party_ownership(party)
    if not current_user.is_vip:
        flash('A exportação em PDF é um recurso VIP.', 'warning'); return redirect(url_for('upgrade'))
    guests_for_table = get_all_guests_for_export(party_id); stats_for_chart = get_party_stats_data(party_id); pdf = PDF(party_name=party.name)
    pdf.set_auto_page_break(auto=True, margin=15); pdf.alias_nb_pages(); pdf.add_page()
    pdf.draw_stats_summary(stats_for_chart); pdf.draw_pie_chart(stats_for_chart, y_offset=0, chart_size_mm=70)
    if guests_for_table: pdf.chapter_body(guests_for_table)
    timestamp = datetime.now(BRASILIA_TZ).strftime("%Y%m%d_%H%M%S")
    filename = f"relatorio_{party.name.replace(' ', '_')}_{timestamp}.pdf"
    return Response(bytes(pdf.output()), mimetype='application/pdf', headers={'Content-Disposition': f'attachment;filename={filename}'})

if __name__ == '__main__':
    is_debug_mode = os.environ.get('FLASK_DEBUG') == 'True'
    app.run(debug=is_debug_mode, host='0.0.0.0', port=5000)