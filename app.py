import os
import hashlib
import qrcode
import requests
import random
import string
import secrets
import uuid
import pytz
import io
import csv
import colorsys
from fpdf import FPDF, XPos, YPos
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont as PILImageFont, ImageOps

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

load_dotenv()

app = Flask(__name__)
basedir = os.path.abspath(os.path.dirname(__file__))

# --- Configurações ---
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY')
if not app.config['SECRET_KEY']:
    raise ValueError("SECRET_KEY não definida no .env")

ABACATE_API_KEY = os.environ.get('ABACATE_API_KEY')
if not ABACATE_API_KEY:
    raise ValueError("ABACATE_API_KEY não definida no .env")

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'instance', 'party.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# --- Inicializações ---
db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = "Por favor, faça login para acessar esta página."
login_manager.login_message_category = "info"

# --- Constantes e Pastas ---
PARTY_LOGOS_FOLDER_NAME = 'party_logos'
PARTY_LOGOS_SAVE_PATH = os.path.join(basedir, 'static', PARTY_LOGOS_FOLDER_NAME)
FONT_PATH = os.path.join(basedir, "Montserrat-Regular.ttf")
BRASILIA_TZ = pytz.timezone('America/Sao_Paulo')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

# --- Criação de Pastas ---
if not os.path.exists(PARTY_LOGOS_SAVE_PATH):
    os.makedirs(PARTY_LOGOS_SAVE_PATH)
if not os.path.exists(os.path.join(basedir, 'instance')):
    os.makedirs(os.path.join(basedir, 'instance'))

@app.context_processor
def inject_current_year():
    return {'current_year': datetime.now(BRASILIA_TZ).year}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- Modelos do Banco de Dados ---
party_collaborators = db.Table('party_collaborators',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('party_id', db.Integer, db.ForeignKey('party.id'), primary_key=True)
)

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    tax_id = db.Column(db.String(20), unique=True, nullable=True)
    cellphone = db.Column(db.String(20), nullable=True)
    parties = db.relationship('Party', backref='owner', lazy=True, cascade="all, delete-orphan")
    collaborations = db.relationship('Party', secondary=party_collaborators, lazy='subquery',
                                     backref=db.backref('collaborators', lazy=True))
    is_vip = db.Column(db.Boolean, default=False, nullable=False)
    payment_charge_id = db.Column(db.String(120), nullable=True, unique=True)
    payment_status = db.Column(db.String(30), default='not_started', nullable=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

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
    share_code = db.Column(db.String(8), unique=True, nullable=False)

class Guest(db.Model):
    __tablename__ = 'guest'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    qr_hash = db.Column(db.String(64), unique=True, nullable=False)
    entered = db.Column(db.Boolean, default=False, nullable=False)
    check_in_time = db.Column(db.DateTime, nullable=True)
    party_id = db.Column(db.Integer, db.ForeignKey('party.id'), nullable=False)
    added_by_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    adder = db.relationship('User', backref='added_guests')
    __table_args__ = (db.UniqueConstraint('name', 'party_id', name='_name_party_uc'),)

    @property
    def qr_image_url(self):
        return url_for('serve_qr_code', qr_hash=self.qr_hash)

    def get_check_in_time_str(self):
        if self.check_in_time:
            return self.check_in_time.astimezone(BRASILIA_TZ).strftime('%d/%m/%Y %H:%M:%S')
        return "N/A"

with app.app_context():
    db.create_all()

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

def get_vibrant_colors(pil_img, num_colors=2):
    img = pil_img.copy().convert("RGBA")
    img.thumbnail((100, 100))
    all_colors = img.getcolors(img.size[0] * img.size[1])
    if not all_colors: return []
    vibrant_candidates = []
    for count, rgba in all_colors:
        r, g, b, a = rgba
        if a < 128: continue
        h, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
        if s > 0.35 and 0.3 < v < 0.95:
            score = (s * 0.8) + (count / (img.size[0] * img.size[1]) * 0.2)
            vibrant_candidates.append({'color': (r, g, b), 'score': score})
    if not vibrant_candidates: return []
    vibrant_candidates.sort(key=lambda x: x['score'], reverse=True)
    return [c['color'] for c in vibrant_candidates[:num_colors]]

def generate_qr_code_image(qr_data, guest_name, party, output_format='PNG'):
    try:
        CARD_WIDTH, PADDING, SPACING, LOGO_ASPECT_RATIO = 600, 40, 25, 2 / 1
        GRADIENT_START, GRADIENT_END = (15, 23, 42), (59, 130, 246)
        CARD_BG_COLOR, TEXT_COLOR, FOOTER_COLOR = (255, 255, 255, 235), (15, 23, 42), (100, 116, 139)
        GUEST_NAME_COLOR = (37, 99, 235)

        try:
            font_path_regular = FONT_PATH
            font_path_bold = font_path_regular.replace("Regular", "Bold")
            if not os.path.exists(font_path_bold): font_path_bold = font_path_regular
            font_party_name = PILImageFont.truetype(font_path_bold, 52)
            font_guest_name = PILImageFont.truetype(font_path_bold, 36)
            font_footer = PILImageFont.truetype(font_path_regular, 14)
        except IOError:
            font_party_name, font_guest_name, font_footer = (PILImageFont.load_default(s) for s in [52,36,14])

        logo_img_raw, logo_height = None, 0
        if party.logo_filename:
            logo_path = os.path.join(PARTY_LOGOS_SAVE_PATH, party.logo_filename)
            if os.path.exists(logo_path):
                logo_height = int(CARD_WIDTH / LOGO_ASPECT_RATIO)
                logo_img_raw = Image.open(logo_path).convert("RGBA")
                try:
                    vibrant_colors = get_vibrant_colors(logo_img_raw, num_colors=2)
                    if len(vibrant_colors) >= 1:
                        main_color = vibrant_colors[0]
                        GUEST_NAME_COLOR, GRADIENT_END = main_color, main_color
                        GRADIENT_START = tuple(int(c * 0.5) for c in main_color)
                except Exception as e:
                    app.logger.warning(f"Não foi possível extrair cores: {e}.")

        qr_instance = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=8, border=2)
        qr_instance.add_data(qr_data)
        qr_instance.make(fit=True)
        img_qr = qr_instance.make_image(fill_color="black", back_color="white").convert('RGB')
        
        content_height = PADDING + font_party_name.getbbox(party.name)[3] + SPACING + img_qr.size[0] + SPACING + font_guest_name.getbbox(guest_name)[3] + SPACING + font_footer.getbbox("Feito com QRPass")[3] + PADDING
        card_height = logo_height + content_height
        canvas_height, canvas_width = card_height + PADDING * 2, CARD_WIDTH + PADDING * 2

        canvas = Image.new('RGB', (canvas_width, canvas_height), GRADIENT_START)
        draw = ImageDraw.Draw(canvas)
        for y in range(canvas_height):
            ratio = y / canvas_height
            color_tuple = tuple(int(start * (1 - ratio) + end * ratio) for start, end in zip(GRADIENT_START, GRADIENT_END))
            draw.line([(0, y), (canvas_width, y)], fill=color_tuple)
        
        card_img = Image.new('RGBA', (CARD_WIDTH, card_height), (0,0,0,0))
        ImageDraw.Draw(card_img).rounded_rectangle((0, 0, CARD_WIDTH, card_height), radius=30, fill=CARD_BG_COLOR)
        
        if logo_img_raw:
            logo_fitted = ImageOps.fit(logo_img_raw, (CARD_WIDTH, logo_height), Image.Resampling.LANCZOS)
            mask = Image.new('L', logo_fitted.size, 0)
            mask_draw = ImageDraw.Draw(mask)
            mask_draw.rounded_rectangle((0, 0, *logo_fitted.size), radius=30, fill=255)
            mask_draw.rectangle((0, 30, *logo_fitted.size), fill=255)
            card_img.paste(logo_fitted, (0, 0), mask)
        
        content_draw = ImageDraw.Draw(card_img)
        current_y = logo_height + PADDING
        items = [(party.name, font_party_name, TEXT_COLOR), (img_qr, None, None), (guest_name, font_guest_name, GUEST_NAME_COLOR), ("Feito com QRPass", font_footer, FOOTER_COLOR)]
        for item, font, color in items:
            if isinstance(item, Image.Image):
                card_img.paste(item, ((CARD_WIDTH - item.width) // 2, int(current_y)))
                current_y += item.height + SPACING
            else:
                bbox = content_draw.textbbox((0, 0), item, font=font)
                content_draw.text(((CARD_WIDTH - bbox[2]) / 2, current_y), item, font=font, fill=color)
                current_y += bbox[3] + SPACING

        canvas.paste(card_img, ((canvas_width - CARD_WIDTH) // 2, (canvas_height - card_height) // 2), card_img)
        
        img_io = io.BytesIO()
        canvas.save(img_io, format=output_format)
        img_io.seek(0)
        return img_io

    except Exception as e:
        app.logger.error(f"Erro ao gerar imagem do QR Code: {e}")
        return None

@app.route('/qr/<string:qr_hash>.png')
def serve_qr_code(qr_hash):
    guest = Guest.query.filter_by(qr_hash=qr_hash).first_or_404()
    img_buffer = generate_qr_code_image(guest.qr_hash, guest.name, guest.party)
    
    if img_buffer:
        return Response(img_buffer, mimetype='image/png')
    else:
        abort(500, description="Falha ao gerar a imagem do QR Code.")

def check_collaboration_permission(party):
    if party.user_id != current_user.id and current_user not in party.collaborators:
        abort(403)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        user = User.query.filter_by(email=request.form.get('email')).first()
        if user and user.check_password(request.form.get('password')):
            login_user(user, remember=True)
            return redirect(url_for('dashboard'))
        flash('Email ou senha inválidos.', 'danger')
    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')

        if User.query.filter_by(username=username).first():
            flash('Este nome de usuário já existe.', 'danger')
            return redirect(url_for('signup'))
        
        if User.query.filter_by(email=email).first():
            flash('Este email já está em uso.', 'danger')
            return redirect(url_for('signup'))
        
        new_user = User(username=username, email=email)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()
        
        login_user(new_user)
        flash('Conta criada com sucesso!', 'success')
        return redirect(url_for('dashboard'))
    return render_template('signup.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('landing'))

@app.route('/')
def landing():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('landing.html')

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/dashboard')
@login_required
def dashboard():
    owned_parties = current_user.parties
    collaborated_parties = current_user.collaborations
    can_create_party = current_user.is_vip or len(owned_parties) < 1
    return render_template('dashboard.html', owned_parties=owned_parties, collaborated_parties=collaborated_parties, can_create_party=can_create_party)

def generate_unique_code(model, field, length=8, chars=string.ascii_uppercase + string.digits):
    while True:
        code = ''.join(random.choices(chars, k=length))
        if not model.query.filter(getattr(model, field) == code).first():
            return code

@app.route('/party/create', methods=['POST'])
@login_required
def create_party():
    if not current_user.is_vip and len(current_user.parties) >= 1:
        flash('Você atingiu o limite de 1 festa. Faça o upgrade para VIP!', 'warning')
        return redirect(url_for('upgrade'))
    
    party_name = request.form.get('party_name')
    if not party_name or not party_name.strip():
        flash('O nome da festa não pode ser vazio.', 'danger')
        return redirect(url_for('dashboard'))

    new_party = Party(name=party_name, owner=current_user, party_code=generate_unique_code(Party, 'party_code', 6), share_code=generate_unique_code(Party, 'share_code', 8), shareable_link_id=secrets.token_urlsafe(12))
    db.session.add(new_party)
    db.session.commit()
    
    flash(f'Festa "{party_name}" criada!', 'success')
    return redirect(url_for('party_manager', party_id=new_party.id))

@app.route('/party/add_collaboration', methods=['POST'])
@login_required
def add_collaboration():
    share_code = request.form.get('share_code')
    party = Party.query.filter_by(share_code=share_code).first()

    if not party:
        flash('Código de compartilhamento inválido.', 'danger')
    elif party.owner == current_user:
        flash('Você não pode se adicionar como colaborador da sua própria festa.', 'warning')
    elif current_user in party.collaborators:
        flash('Você já é um colaborador desta festa.', 'info')
    else:
        party.collaborators.append(current_user)
        db.session.commit()
        flash(f'Você agora é um colaborador da festa "{party.name}"!', 'success')
        
    return redirect(url_for('dashboard'))

@app.route('/party/<int:party_id>')
@login_required
def party_manager(party_id):
    party = db.session.get(Party, party_id) or abort(404)
    check_collaboration_permission(party)
    can_add_guest = current_user.is_vip or len(party.guests) < 50
    return render_template('party_manager.html', party=party, can_add_guest=can_add_guest)

@app.route('/party/<int:party_id>/delete', methods=['POST'])
@login_required
def delete_party(party_id):
    party = db.session.get(Party, party_id) or abort(404)
    if party.user_id != current_user.id:
        flash("Apenas o dono da festa pode deletá-la.", "danger")
        return redirect(url_for('dashboard'))
    
    if party.logo_filename:
        try: os.remove(os.path.join(PARTY_LOGOS_SAVE_PATH, party.logo_filename))
        except OSError: pass
            
    db.session.delete(party)
    db.session.commit()
    
    flash(f'A festa "{party.name}" foi removida.', 'success')
    return redirect(url_for('dashboard'))

@app.route('/party/<int:party_id>/upload_logo', methods=['POST'])
@login_required
def upload_logo(party_id):
    party = db.session.get(Party, party_id) or abort(404)
    check_collaboration_permission(party)
    if 'party_logo' not in request.files:
        flash('Nenhum arquivo selecionado.', 'danger')
        return redirect(url_for('party_manager', party_id=party_id))
    file = request.files['party_logo']
    if file.filename == '':
        flash('Nenhum arquivo selecionado.', 'danger')
        return redirect(url_for('party_manager', party_id=party_id))
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
        flash('Logo da festa atualizado!', 'success')
    else:
        flash('Tipo de arquivo inválido.', 'danger')
    return redirect(url_for('party_manager', party_id=party_id))

@app.route('/party/<int:party_id>/update_details', methods=['POST'])
@login_required
def update_party_details(party_id):
    party = db.session.get(Party, party_id) or abort(404)
    check_collaboration_permission(party)
    party.public_description = request.form.get('public_description')
    db.session.commit()
    flash('Informações da página pública atualizadas!', 'success')
    return redirect(url_for('party_manager', party_id=party_id))

@app.route('/party/<int:party_id>/toggle_guest_count', methods=['POST'])
@login_required
def toggle_guest_count(party_id):
    party = db.session.get(Party, party_id) or abort(404)
    check_collaboration_permission(party)
    party.show_guest_count = not party.show_guest_count
    db.session.commit()
    flash('Visibilidade da contagem de convidados atualizada.', 'success')
    return redirect(url_for('party_manager', party_id=party_id))

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
            flash('Código da festa inválido.', 'danger')
    party_code_from_cookie = request.cookies.get('party_code')
    if party_code_from_cookie:
        party = Party.query.filter_by(party_code=party_code_from_cookie).first()
        if party:
            return render_template('scanner.html', party=party)
    return render_template('scanner_login.html')

@app.route('/scanner/forget')
def forget_scanner():
    resp = make_response(redirect(url_for('public_scanner')))
    resp.set_cookie('party_code', '', expires=0)
    flash('Você se desconectou do scanner.', 'info')
    return resp

@app.route('/upgrade')
@login_required
def upgrade():
    if current_user.is_vip:
        flash('Você já é um usuário VIP!', 'info')
        return redirect(url_for('dashboard'))
    return render_template('upgrade.html')

@app.route('/complete_profile', methods=['GET', 'POST'])
@login_required
def complete_profile():
    if current_user.is_vip: return redirect(url_for('dashboard'))
    if request.method == 'POST':
        tax_id, cellphone = request.form.get('tax_id'), request.form.get('cellphone')
        if not tax_id or not cellphone:
            flash("CPF e Telefone são obrigatórios.", 'danger')
            return render_template('complete_profile.html')
        if User.query.filter(User.tax_id == tax_id, User.id != current_user.id).first():
            flash("Este CPF já está associado a outra conta.", 'danger')
            return render_template('complete_profile.html')
        current_user.tax_id, current_user.cellphone = tax_id, cellphone
        db.session.commit()
        flash("Perfil atualizado! Agora vamos para o pagamento.", 'success')
        return redirect(url_for('create_payment'))
    return render_template('complete_profile.html')

@app.route('/payment/create', methods=['POST', 'GET'])
@login_required
def create_payment():
    if current_user.is_vip: return redirect(url_for('dashboard'))
    if not all([current_user.tax_id, current_user.cellphone]):
        flash("Por favor, complete seu perfil.", 'warning')
        return redirect(url_for('complete_profile'))
    url = "https://api.abacatepay.com/v1/pixQrCode/create"
    headers = {"Authorization": f"Bearer {ABACATE_API_KEY}", "Content-Type": "application/json"}
    payload = {"amount": 10000, "expiresIn": 3600, "description": f"Upgrade VIP QRPass - {current_user.username}", "customer": {"name": current_user.username, "email": current_user.email, "taxId": current_user.tax_id, "cellphone": current_user.cellphone}}
    try:
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json().get('data', {})
        if not all([data.get('brCodeBase64'), data.get('brCode'), data.get('id')]):
            raise ValueError("Resposta da API de PIX incompleta.")
        current_user.payment_charge_id = data['id']
        current_user.payment_status = 'pending'
        db.session.commit()
        return render_template('show_pix.html', pix_qr_code=data['brCodeBase64'], pix_emv=data['brCode'], pix_id=data['id'])
    except Exception as e:
        app.logger.error(f"Erro na API de pagamento: {e}")
        flash('Não foi possível gerar a cobrança PIX. Tente novamente.', 'danger')
        return redirect(url_for('upgrade'))

@app.route('/payment/check_status/<pix_id>')
@login_required
def check_payment_status(pix_id):
    if current_user.payment_charge_id != pix_id: return jsonify({'status': 'error', 'message': 'Unauthorized'}), 403
    url = "https://api.abacatepay.com/v1/pixQrCode/check"
    headers, params = {"Authorization": f"Bearer {ABACATE_API_KEY}"}, {"id": pix_id}
    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        status = response.json().get('data', {}).get('status')
        if status == 'PAID' and not current_user.is_vip:
            current_user.is_vip = True
            current_user.payment_status = 'paid'
            db.session.commit()
        return jsonify({'status': status})
    except Exception as e:
        app.logger.error(f"Erro ao verificar status do pagamento: {e}")
        return jsonify({'status': 'error'}), 500

@app.route('/webhooks/abacatepay', methods=['POST'])
def abacatepay_webhook():
    payload = request.get_json()
    app.logger.info(f"Webhook recebido: {payload}")
    if not payload or 'event' not in payload or 'data' not in payload: return jsonify({'status': 'error'}), 400
    event_type, transaction_id = payload.get('event'), payload.get('data', {}).get('id')
    if event_type == 'pix_qr_code.paid' and transaction_id:
        user = User.query.filter_by(payment_charge_id=transaction_id).first()
        if user and not user.is_vip:
            user.is_vip, user.payment_status = True, 'paid'
            db.session.commit()
            app.logger.info(f"Pagamento confirmado via webhook para {user.username}")
            return jsonify({'status': 'success'}), 200
        elif user:
            app.logger.info(f"Pagamento webhook recebido para usuário já VIP: {user.username}")
    return jsonify({'status': 'received'}), 200

def get_party_stats_data(party_id):
    total_invited = Guest.query.filter_by(party_id=party_id).count()
    entered_count = Guest.query.filter_by(party_id=party_id, entered=True).count()
    return {'total_invited': total_invited, 'entered_count': entered_count, 'not_entered_count': total_invited - entered_count, 'percentage_entered': round((entered_count / total_invited) * 100, 2) if total_invited > 0 else 0.0}

@app.route('/api/party/<int:party_id>/stats', methods=['GET'])
def get_stats(party_id):
    return jsonify(get_party_stats_data(party_id))

@app.route('/api/party/<int:party_id>/guests', methods=['GET', 'POST'])
@login_required
def handle_guests(party_id):
    party = db.session.get(Party, party_id) or abort(404)
    check_collaboration_permission(party)
    
    if request.method == 'POST':
        if not current_user.is_vip and len(party.guests) >= 50:
            return jsonify({'error': 'Limite de 50 convidados atingido para contas gratuitas.'}), 403
        data = request.get_json()
        name = data.get('name', '').strip()
        if not name: return jsonify({'error': 'O nome do convidado é obrigatório.'}), 400
        if Guest.query.filter_by(name=name, party_id=party_id).first():
            return jsonify({'error': f'O convidado "{name}" já existe na lista.'}), 409
        new_guest = Guest(name=name, qr_hash=generate_unique_code(Guest, 'qr_hash', 32, string.ascii_letters + string.digits), party_id=party_id, added_by_user_id=current_user.id)
        db.session.add(new_guest)
        db.session.commit()
        return jsonify({'id': new_guest.id, 'name': new_guest.name, 'qr_hash': new_guest.qr_hash, 'entered': new_guest.entered, 'qr_image_url': new_guest.qr_image_url, 'check_in_time': new_guest.get_check_in_time_str(), 'added_by': new_guest.adder.username}), 201

    page, per_page, search_term = request.args.get('page', 1, type=int), request.args.get('per_page', 50, type=int), request.args.get('search')
    sort_by, sort_dir = request.args.get('sort_by', 'name'), request.args.get('sort_dir', 'asc')
    query = Guest.query.filter_by(party_id=party_id)
    if search_term: query = query.filter(Guest.name.ilike(f'%{search_term.strip()}%'))
    sort_columns = {'name': Guest.name, 'entered': Guest.entered, 'check_in_time': Guest.check_in_time, 'added_by': User.username}
    if sort_by == 'added_by': query = query.join(User, Guest.added_by_user_id == User.id)
    order_column = sort_columns.get(sort_by, Guest.name)
    order_func = order_column.desc() if sort_dir == 'desc' else order_column.asc()
    pagination = query.order_by(order_func.nullslast()).paginate(page=page, per_page=per_page, error_out=False)
    
    return jsonify({'guests': [{'id': g.id, 'name': g.name, 'qr_hash': g.qr_hash, 'entered': g.entered, 'qr_image_url': g.qr_image_url, 'check_in_time': g.get_check_in_time_str(), 'added_by': g.adder.username} for g in pagination.items], 'pagination': {'page': pagination.page, 'per_page': pagination.per_page, 'total_pages': pagination.pages, 'total_items': pagination.total, 'has_next': pagination.has_next, 'has_prev': pagination.has_prev}})

@app.route('/api/party/<int:party_id>/guests/<qr_hash>/enter', methods=['POST'])
def mark_entered(party_id, qr_hash):
    guest = Guest.query.filter_by(qr_hash=qr_hash, party_id=party_id).first()
    if not guest: return jsonify({'error': 'QR Code inválido para esta festa'}), 404
    if guest.entered:
        return jsonify({'id': guest.id, 'name': guest.name, 'qr_hash': guest.qr_hash, 'entered': True, 'message': f'{guest.name} já entrou às {guest.get_check_in_time_str()}.', 'is_new_entry': False, 'check_in_time': guest.get_check_in_time_str()})
    guest.entered, guest.check_in_time = True, datetime.now(BRASILIA_TZ)
    db.session.commit()
    return jsonify({'id': guest.id, 'name': guest.name, 'qr_hash': guest.qr_hash, 'entered': True, 'message': f'Entrada liberada! Bem-vindo(a), {guest.name}!', 'is_new_entry': True, 'check_in_time': guest.get_check_in_time_str()})

@app.route('/api/party/<int:party_id>/guests/<qr_hash>/edit', methods=['PUT'])
@login_required
def edit_guest_name(party_id, qr_hash):
    guest = Guest.query.filter_by(qr_hash=qr_hash, party_id=party_id).first_or_404()
    check_collaboration_permission(guest.party)
    data = request.get_json()
    new_name = data.get('name', '').strip()
    if Guest.query.filter(Guest.name == new_name, Guest.party_id == party_id, Guest.qr_hash != qr_hash).first():
        return jsonify({'error': f'Já existe um convidado com o nome "{new_name}".'}), 409
    guest.name = new_name
    db.session.commit()
    return jsonify({'id': guest.id, 'name': guest.name, 'qr_hash': guest.qr_hash, 'entered': guest.entered, 'qr_image_url': guest.qr_image_url, 'check_in_time': guest.get_check_in_time_str(), 'message': f'Nome do convidado atualizado.'}), 200

@app.route('/api/party/<int:party_id>/guests/<qr_hash>/toggle_entry', methods=['PUT'])
@login_required
def toggle_entry_manually(party_id, qr_hash):
    guest = Guest.query.filter_by(qr_hash=qr_hash, party_id=party_id).first_or_404()
    check_collaboration_permission(guest.party)
    guest.entered = not guest.entered
    guest.check_in_time = datetime.now(BRASILIA_TZ) if guest.entered else None
    action = "marcado(a) como PRESENTE" if guest.entered else "marcado(a) como AUSENTE"
    db.session.commit()
    return jsonify({'id': guest.id, 'name': guest.name, 'qr_hash': guest.qr_hash, 'entered': guest.entered, 'message': f'Status de {guest.name} alterado: {action}.', 'check_in_time': guest.get_check_in_time_str()})

@app.route('/api/party/<int:party_id>/guests/<qr_hash>', methods=['DELETE'])
@login_required
def delete_guest(party_id, qr_hash):
    guest = Guest.query.filter_by(qr_hash=qr_hash, party_id=party_id).first_or_404()
    check_collaboration_permission(guest.party)
    guest_name = guest.name
    db.session.delete(guest)
    db.session.commit()
    return jsonify({'message': f'Convidado {guest_name} removido com sucesso.'}), 200

def get_all_guests_for_export(party_id):
    return Guest.query.filter_by(party_id=party_id).order_by(Guest.name).all()

class PDF(FPDF):
    def __init__(self, orientation='P', unit='mm', format='A4', party_name=''):
        super().__init__(orientation, unit, format)
        self.montserrat_font_path = FONT_PATH
        self.font_name = 'Montserrat'
        self.default_font = 'Helvetica'
        self.current_font_family = self.default_font
        self.party_name = party_name
        if os.path.exists(self.montserrat_font_path):
            try:
                self.add_font(self.font_name, '', self.montserrat_font_path)
                self.add_font(self.font_name, 'B', self.montserrat_font_path)
                self.add_font(self.font_name, 'I', self.montserrat_font_path)
                self.current_font_family = self.font_name
            except Exception: pass 
    def header(self):
        self.set_font(self.current_font_family, 'B', 16)
        title, title_w = f'Relatório do Evento: {self.party_name}', self.get_string_width(f'Relatório do Evento: {self.party_name}')
        self.set_x((self.w - title_w) / 2)
        self.cell(title_w, 10, title, border=0, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
        self.ln(5)
    def footer(self):
        self.set_y(-15)
        self.set_font(self.current_font_family, 'I', 8)
        self.cell(0, 10, f'Página {self.page_no()}/{{nb}}', border=0, new_x=XPos.RIGHT, new_y=YPos.TOP, align='C')
    def draw_stats_summary(self, stats_data):
        self.set_font(self.current_font_family, 'B', 11)
        self.cell(0, 10, "Estatísticas do evento", border=0, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='L')
        self.ln(1)
        col_width_stat, stat_box_height = (self.w - self.l_margin - self.r_margin) / 4, 12
        line_height_label, line_height_value = 4.5, 5.5
        padding_top_box = (stat_box_height - (line_height_label + line_height_value)) / 2
        current_x, base_y = self.l_margin, self.get_y()
        stats_items = [("Convidados:", str(stats_data['total_invited'])), ("Entraram:", str(stats_data['entered_count'])), ("Não Entraram:", str(stats_data['not_entered_count'])), ("Comparecimento:", f"{stats_data['percentage_entered']:.2f}%")]
        for i, (label, value) in enumerate(stats_items):
            self.set_fill_color(240, 240, 240)
            self.rect(current_x, base_y, col_width_stat, stat_box_height, 'F')
            self.set_draw_color(200, 200, 200)
            self.rect(current_x, base_y, col_width_stat, stat_box_height, 'D')
            y_pos_label = base_y + padding_top_box
            self.set_xy(current_x, y_pos_label)
            self.set_text_color(0, 0, 0)
            self.set_font(self.current_font_family, '', 8.5)
            self.cell(col_width_stat, line_height_label, label, border=0, align='C')
            y_pos_value = y_pos_label + line_height_label
            self.set_xy(current_x, y_pos_value)
            self.set_text_color(0, 100, 200)
            self.set_font(self.current_font_family, 'B', 10)
            self.cell(col_width_stat, line_height_value, value, border=0, align='C')
            self.set_text_color(0, 0, 0)
            current_x += col_width_stat
        self.set_y(base_y + stat_box_height)
        self.ln(5)
    def draw_pie_chart(self, stats_data, y_offset, chart_size_mm=70):
        labels, sizes, colors = ('Entraram', 'Não Entraram'), [stats_data['entered_count'], stats_data['not_entered_count']], ['#4BC0C0', '#FF6384']
        if sum(sizes) == 0: self.cell(0, 10, "Sem dados para o gráfico.", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C'); return
        fig, ax = plt.subplots(figsize=(chart_size_mm / 25.4, chart_size_mm / 25.4), dpi=100)
        wedges, _, autotexts = ax.pie(sizes, explode=(0.05, 0) if sizes[0] > 0 else (0,0), labels=None, colors=colors, autopct='%1.1f%%', shadow=False, startangle=90)
        for autotext in autotexts: autotext.set_color('white'); autotext.set_fontweight('bold')
        ax.axis('equal')
        ax.legend(wedges, [f'{l} ({s})' for l, s in zip(labels, sizes)], loc="center left", bbox_to_anchor=(1, 0, 0.5, 1))
        img_buffer = io.BytesIO()
        plt.savefig(img_buffer, format='png', bbox_inches='tight', transparent=True)
        plt.close(fig)
        self.image(img_buffer, x=(self.w - chart_size_mm) / 2, y=self.get_y(), w=chart_size_mm)
        self.set_y(self.get_y() + chart_size_mm + 5)
    def chapter_body(self, guests_data_table):
        self.set_font(self.current_font_family, 'B', 11)
        self.cell(0, 10, "Lista de Convidados", border=0, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
        self.ln(1)
        self.set_font(self.current_font_family, 'B', 9)
        self.set_fill_color(230, 230, 230)
        col_widths = {"name": 100, "status": 30, "check_in": 40}
        start_x = self.l_margin + (self.w - 2 * self.l_margin - sum(col_widths.values())) / 2
        self.set_x(start_x)
        self.cell(col_widths["name"], 8, 'Nome', 1, 0, 'C', 1)
        self.cell(col_widths["status"], 8, 'Entrou?', 1, 0, 'C', 1)
        self.cell(col_widths["check_in"], 8, 'Data Check-in', 1, 1, 'C', 1)
        self.set_font(self.current_font_family, '', 8.5)
        for i, guest_obj in enumerate(guests_data_table):
            self.set_x(start_x)
            self.cell(col_widths["name"], 7, guest_obj.name, 1, 0, 'L', i % 2 == 0)
            self.cell(col_widths["status"], 7, 'Sim' if guest_obj.entered else 'Não', 1, 0, 'C', i % 2 == 0)
            self.cell(col_widths["check_in"], 7, guest_obj.get_check_in_time_str(), 1, 1, 'C', i % 2 == 0)

@app.route('/api/party/<int:party_id>/export/csv')
@login_required
def export_guests_csv(party_id):
    party = db.session.get(Party, party_id) or abort(404)
    check_collaboration_permission(party)
    guests_data = get_all_guests_for_export(party_id)
    si, cw = io.StringIO(), csv.writer(si)
    cw.writerow(['Nome', 'Status Entrada', 'Data Check-in'])
    for guest in guests_data:
        cw.writerow([guest.name, 'Sim' if guest.entered else 'Não', guest.get_check_in_time_str()])
    return Response(si.getvalue(), mimetype="text/csv", headers={"Content-disposition": f"attachment; filename=lista_{party.name.replace(' ', '_')}.csv"})

@app.route('/api/party/<int:party_id>/export/pdf')
@login_required
def export_guests_pdf(party_id):
    party = db.session.get(Party, party_id) or abort(404)
    check_collaboration_permission(party)
    if not current_user.is_vip:
        flash('A exportação em PDF é um recurso VIP.', 'warning')
        return redirect(url_for('upgrade'))
    guests_for_table, stats_for_chart = get_all_guests_for_export(party_id), get_party_stats_data(party_id)
    pdf = PDF(party_name=party.name)
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.alias_nb_pages()
    pdf.add_page()
    pdf.draw_stats_summary(stats_for_chart)
    pdf.draw_pie_chart(stats_for_chart, y_offset=0, chart_size_mm=70)
    if guests_for_table:
        pdf.chapter_body(guests_for_table)
    timestamp = datetime.now(BRASILIA_TZ).strftime("%Y%m%d_%H%M%S")
    filename = f"relatorio_{party.name.replace(' ', '_')}_{timestamp}.pdf"
    return Response(bytes(pdf.output()), mimetype='application/pdf', headers={'Content-Disposition': f'attachment;filename={filename}'})

if __name__ == '__main__':
    is_debug_mode = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    app.run(debug=is_debug_mode, host='0.0.0.0', port=5000)