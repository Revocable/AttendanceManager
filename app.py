import os
import hashlib
import hmac
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
import base64

from urllib.parse import urlparse, urljoin

from fpdf import FPDF, XPos, YPos
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont as PILImageFont, ImageOps

from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask import (Flask, request, jsonify, render_template, url_for, Response,
                   send_from_directory, redirect, flash, abort, make_response)
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField
from wtforms.validators import DataRequired, Email, EqualTo, Length, ValidationError
from flask_wtf.csrf import CSRFProtect
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from dotenv import load_dotenv
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

load_dotenv()

basedir = os.path.abspath(os.path.dirname(__file__))

# --- Configuração de Caminhos e Pastas Persistentes ---
# Na Render, defina uma variável de ambiente STORAGE_BASE_PATH como '/var/data/qrpass_data'
# Localmente, se a variável não estiver definida, usará './data' no diretório do projeto.
STORAGE_BASE_PATH = os.environ.get('STORAGE_BASE_PATH')
if not STORAGE_BASE_PATH:
    STORAGE_BASE_PATH = os.path.join(basedir, 'data')

# Garante que o caminho de armazenamento seja absoluto para evitar erros do SQLite.
if not os.path.isabs(STORAGE_BASE_PATH):
    STORAGE_BASE_PATH = os.path.join(basedir, STORAGE_BASE_PATH)

# Define os nomes das subpastas para uma gestão centralizada
DB_FOLDER_NAME = 'database'
PARTY_LOGOS_FOLDER_NAME = 'party_logos'
PAYMENT_QRCODES_FOLDER_NAME = 'payment_qrcodes'

# Constrói os caminhos completos para os artefatos persistentes
DB_FULL_PATH = os.path.join(STORAGE_BASE_PATH, DB_FOLDER_NAME, 'party.db')
PARTY_LOGOS_SAVE_PATH = os.path.join(STORAGE_BASE_PATH, PARTY_LOGOS_FOLDER_NAME)
PAYMENT_QRCODES_SAVE_PATH = os.path.join(STORAGE_BASE_PATH, PAYMENT_QRCODES_FOLDER_NAME)

# Garante que todos os diretórios de armazenamento necessários existam ANTES de a aplicação iniciar.
# Isso previne erros de 'arquivo não encontrado' durante a inicialização.
os.makedirs(os.path.dirname(DB_FULL_PATH), exist_ok=True)
os.makedirs(PARTY_LOGOS_SAVE_PATH, exist_ok=True)
os.makedirs(PAYMENT_QRCODES_SAVE_PATH, exist_ok=True)
# A pasta 'instance' é mantida por segurança, caso alguma extensão a utilize.
os.makedirs(os.path.join(basedir, 'instance'), exist_ok=True)
print(f"Diretórios de armazenamento verificados/criados em: {STORAGE_BASE_PATH}")


# Inicializa o Flask.
app = Flask(__name__)

# --- Configurações ---
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY')
if not app.config['SECRET_KEY']:
    raise ValueError("SECRET_KEY não definida no .env")

ABACATE_API_KEY = os.environ.get('ABACATE_API_KEY')
if not ABACATE_API_KEY:
    raise ValueError("ABACATE_API_KEY não definida no .env")

ABACATE_WEBHOOK_SECRET = os.environ.get('ABACATE_WEBHOOK_SECRET')
if not ABACATE_WEBHOOK_SECRET:
    raise ValueError("ABACATE_WEBHOOK_SECRET não definida no .env")

# Converte as barras invertidas do Windows para barras normais para a URI
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + DB_FULL_PATH.replace('\\', '/')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB

# --- Inicializações ---
db = SQLAlchemy(app)
csrf = CSRFProtect(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = "Por favor, faça login para acessar esta página."
login_manager.login_message_category = "info"

# --- Constantes e Pastas ---
# A fonte é um recurso da aplicação, não precisa ser persistente no disco de dados
FONT_PATH = os.path.join(basedir, "Montserrat-Regular.ttf")
BRASILIA_TZ = pytz.timezone('America/Sao_Paulo')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}


def is_safe_url(target):
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return test_url.scheme in ('http', 'https') and ref_url.netloc == test_url.netloc

@app.context_processor
def inject_current_year():
    return {'current_year': datetime.now(BRASILIA_TZ).year}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- ROTA para servir arquivos persistentes ---
@app.route('/persistent/<path:filename>')
def serve_persistent_file(filename):
    """
    Serve arquivos da pasta de armazenamento persistente.
    A 'path:filename' captura o caminho completo do arquivo a partir da raiz do STORAGE_BASE_PATH.
    Ex: /persistent/party_logos/meu_logo.png
    """
    try:
        # Sanitize o filename para previnir Path Traversal
        if '..' in filename or filename.startswith('/'):
            abort(404)

        # Importante: filename pode conter subdiretórios (ex: 'party_logos/meu_logo.png')
        # send_from_directory lida com isso automaticamente.
        return send_from_directory(STORAGE_BASE_PATH, filename)
    except Exception as e:
        app.logger.error(f"Erro ao servir arquivo persistente {filename}: {e}")
        abort(404)


# --- Funções Auxiliares ---
def save_base64_as_png(base64_string, charge_id):
    """Decodifica uma string base64 e a salva como um arquivo PNG."""
    if not base64_string or not charge_id:
        return None
    try:
        if "data:image/png;base64," in base64_string:
            clean_base64_string = base64_string.split(",")[1]
        else:
            clean_base64_string = base64_string
        img_data = base64.b64decode(clean_base64_string)
        img = Image.open(io.BytesIO(img_data))
        filename = f"{charge_id}.png"
        save_path = os.path.join(PAYMENT_QRCODES_SAVE_PATH, filename)
        img.save(save_path, 'PNG')
        return filename
    except Exception as e:
        app.logger.error(f"Erro ao salvar imagem base64 para charge_id {charge_id}: {e}")
        return None

def delete_pix_qr_code_file(guest):
    """Deleta o arquivo de imagem do QR Code do PIX associado a um convidado."""
    if guest and guest.pix_qr_code_filename:
        try:
            file_path = os.path.join(PAYMENT_QRCODES_SAVE_PATH, guest.pix_qr_code_filename)
            if os.path.exists(file_path):
                os.remove(file_path)
                app.logger.info(f"Arquivo QR Code PIX {guest.pix_qr_code_filename} deletado com sucesso.")
            else:
                app.logger.warning(f"Arquivo QR Code PIX {guest.pix_qr_code_filename} não encontrado para deleção.")
        except Exception as e:
            app.logger.error(f"Erro ao deletar o arquivo QR Code PIX {guest.pix_qr_code_filename}: {e}")

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
    ticket_price = db.Column(db.Float, default=0.0, nullable=False)
    allow_public_purchase = db.Column(db.Boolean, default=False, nullable=False)

class Guest(db.Model):
    __tablename__ = 'guest'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    qr_hash = db.Column(db.String(64), unique=True, nullable=False)
    entered = db.Column(db.Boolean, default=False, nullable=False)
    check_in_time = db.Column(db.DateTime, nullable=True)
    party_id = db.Column(db.Integer, db.ForeignKey('party.id'), nullable=False)
    added_by_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    adder = db.relationship('User', foreign_keys=[added_by_user_id], backref='added_guests')
    payment_status = db.Column(db.String(30), default='not_applicable', nullable=False)
    payment_charge_id = db.Column(db.String(120), unique=True, nullable=True)
    pix_qr_code_filename = db.Column(db.String(255), nullable=True)
    pix_emv_code = db.Column(db.Text, nullable=True)
    pix_created_at = db.Column(db.DateTime, nullable=True)
    purchase_link_id = db.Column(db.String(64), unique=True, nullable=True)
    purchased_by_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    purchaser = db.relationship('User', foreign_keys=[purchased_by_user_id], backref='purchased_tickets')
    purchase_price = db.Column(db.Float, nullable=True) # NOVO CAMPO para registrar o preço pago

    @property
    def qr_image_url(self):
        # A rota 'serve_qr_code' gera a imagem dinamicamente, não serve de um arquivo estático no disco
        return url_for('serve_qr_code', qr_hash=self.qr_hash)

    @property
    def pix_qr_code_url(self):
        if self.pix_qr_code_filename:
            # AGORA USA A NOVA ROTA '/persistent/' para arquivos salvos no disco persistente
            return url_for('serve_persistent_file', filename=f"{PAYMENT_QRCODES_FOLDER_NAME}/{self.pix_qr_code_filename}")
        return None

    def get_check_in_time_str(self):
        if self.check_in_time:
            return self.check_in_time.astimezone(BRASILIA_TZ).strftime('%d/%m/%Y %H:%M:%S')
        return "N/A"

with app.app_context():
    # Isso criará o arquivo do banco de dados na pasta DB_FULL_PATH
    # Para bancos de dados existentes, isso adicionará a coluna 'purchase_price' como NULL.
    # Se você já tem dados 'paid' e deseja que eles contribuam para o faturamento,
    # precisaria de uma migração de dados ou um script one-off para popular 'purchase_price'
    # para esses registros existentes com o valor de party.ticket_price na época.
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
            # Fallback para fontes padrão se as personalizadas não puderem ser carregadas
            app.logger.warning(f"Fonte personalizada não encontrada em {FONT_PATH}. Usando fonte padrão.")
            font_party_name, font_guest_name, font_footer = (PILImageFont.load_default(s) for s in [52,36,14])


        logo_img_raw, logo_height = None, 0
        if party.logo_filename:
            # O caminho aqui está correto, ele tenta carregar a imagem do disco persistente
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
    if guest.payment_status == 'paid' or guest.payment_status == 'not_applicable':
        img_buffer = generate_qr_code_image(guest.qr_hash, guest.name, guest.party)
        if img_buffer:
            return Response(img_buffer, mimetype='image/png')
        else:
            abort(500, description="Falha ao gerar a imagem do QR Code.")
    else:
        flash("O ingresso ainda não foi pago.", "warning")
        if guest.payment_charge_id:
            return redirect(url_for('show_ticket_payment', payment_charge_id=guest.payment_charge_id))
        elif guest.purchase_link_id:
            return redirect(url_for('buy_ticket_owner_invite', purchase_link_id=guest.purchase_link_id))
        else:
            abort(403, description="Ingresso não disponível.")

def check_collaboration_permission(party):
    if party.user_id != current_user.id and current_user not in party.collaborators:
        abort(403)

# --- Formulários WTForms ---
class SignupForm(FlaskForm):
    username = StringField('Nome de Usuário', validators=[DataRequired(), Length(min=4, max=80)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Senha', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Confirmar Senha', validators=[DataRequired(), EqualTo('password')])

    def validate_username(self, username):
        if User.query.filter_by(username=username.data).first():
            raise ValidationError('Este nome de usuário já existe.')

    def validate_email(self, email):
        if User.query.filter_by(email=email.data).first():
            raise ValidationError('Este email já está em uso.')

class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Senha', validators=[DataRequired()])

class PartyForm(FlaskForm):
    party_name = StringField('Nome da Festa', validators=[DataRequired(), Length(max=120)])

class CollaborationForm(FlaskForm):
    share_code = StringField('Código de Compartilhamento', validators=[DataRequired()])

class PartyDetailsForm(FlaskForm):
    public_description = StringField('Descrição Pública')
    ticket_price = StringField('Preço do Ingresso')
    allow_public_purchase = StringField('Permitir Compra Pública')

class GuestForm(FlaskForm):
    name = StringField('Nome do Convidado', validators=[DataRequired(), Length(max=100)])

class CompleteProfileForm(FlaskForm):
    tax_id = StringField('CPF/CNPJ', validators=[DataRequired(), Length(min=11, max=14)])
    cellphone = StringField('Telefone', validators=[DataRequired(), Length(min=10, max=13)])

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and user.check_password(form.password.data):
            login_user(user, remember=True)
            next_page = request.args.get('next')
            if not is_safe_url(next_page):
                return abort(400)
            return redirect(next_page or url_for('dashboard'))
        else:
            flash('Login inválido. Verifique seu email e senha.', 'danger')
    
    return render_template('login.html', form=form)

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    form = SignupForm()
    if form.validate_on_submit():
        new_user = User(username=form.username.data, email=form.email.data)
        new_user.set_password(form.password.data)
        db.session.add(new_user)
        db.session.commit()

        login_user(new_user)
        flash('Conta criada com sucesso!', 'success')
        next_page = request.args.get('next')
        if not is_safe_url(next_page):
            return abort(400)
        return redirect(next_page or url_for('dashboard'))

    return render_template('signup.html', form=form)

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
    party_form = PartyForm()
    collaboration_form = CollaborationForm()
    return render_template(
        'dashboard.html',
        owned_parties=owned_parties,
        collaborated_parties=collaborated_parties,
        party_form=party_form,
        collaboration_form=collaboration_form
    )

def generate_unique_code(model, field, length=8, chars=string.ascii_uppercase + string.digits):
    while True:
        code = ''.join(random.choices(chars, k=length))
        if not db.session.query(model).filter(getattr(model, field) == code).first():
            return code

@app.route('/party/create', methods=['POST'])
@login_required
def create_party():
    form = PartyForm()
    if form.validate_on_submit():
        party_name = form.party_name.data
        new_party = Party(name=party_name, owner=current_user, party_code=generate_unique_code(Party, 'party_code', 6), share_code=generate_unique_code(Party, 'share_code', 8), shareable_link_id=secrets.token_urlsafe(12))
        db.session.add(new_party)
        db.session.commit()
        flash(f'Festa "{party_name}" criada!', 'success')
        return redirect(url_for('party_manager', party_id=new_party.id))
    else:
        flash('O nome da festa não pode ser vazio.', 'danger')
        return redirect(url_for('dashboard'))

@app.route('/party/add_collaboration', methods=['POST'])
@login_required
def add_collaboration():
    form = CollaborationForm()
    if form.validate_on_submit():
        share_code = form.share_code.data
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
    else:
        flash('Código de compartilhamento inválido.', 'danger')

    return redirect(url_for('dashboard'))

@app.route('/party/<int:party_id>')
@login_required
def party_manager(party_id):
    party = db.session.get(Party, party_id) or abort(404)
    check_collaboration_permission(party)
    return render_template('party_manager.html', party=party)

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
    form = PartyDetailsForm()
    if form.validate_on_submit():
        party.public_description = form.public_description.data

        try:
            ticket_price_str = form.ticket_price.data.replace(',', '.')
            party.ticket_price = float(ticket_price_str)
            if party.ticket_price < 0:
                raise ValueError("Preço do ingresso não pode ser negativo.")
        except (ValueError, AttributeError):
            flash('Preço do ingresso inválido. Use um número (ex: 50.00).', 'danger')
            return redirect(url_for('party_manager', party_id=party_id))

        party.allow_public_purchase = 'allow_public_purchase' in request.form

        db.session.commit()
        flash('Informações da festa atualizadas!', 'success')
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

# --- ROTA MODIFICADA ---
@app.route('/party/<int:party_id>/register_guest_for_payment', methods=['POST'])
@login_required
def register_guest_for_payment(party_id):
    party = db.session.get(Party, party_id) or abort(404)
    check_collaboration_permission(party)
    data = request.get_json()
    guest_name = data.get('guest_name_for_payment', '').strip()

    if party.ticket_price <= 0:
        return jsonify({'status': 'error','message': 'Defina um preço para o ingresso na seção "Opções da Festa".'}), 400
    if not guest_name:
        return jsonify({'status': 'error','message': 'Nome do convidado para pagamento é obrigatório.'}), 400

    # Validação do perfil do usuário
    if not current_user.tax_id or not current_user.cellphone:
        # Constrói a URL para completar o perfil, com o 'next' para voltar à página da festa
        next_url = url_for('party_manager', party_id=party_id)
        complete_profile_url = url_for('complete_profile', next=next_url)

        # Retorna um JSON com a ação de redirecionamento
        return jsonify({
            'status': 'error',
            'message': 'Seu perfil precisa ter CPF/CNPJ e Telefone para gerar links de pagamento. Redirecionando...',
            'action': 'redirect',
            'url': complete_profile_url
        }), 400

    qr_hash = generate_unique_code(Guest, 'qr_hash', 32, string.ascii_letters + string.digits)
    purchase_link_id = generate_unique_code(Guest, 'purchase_link_id', 24)

    try:
        customer_info = { "name": guest_name, "email": current_user.email, "taxId": current_user.tax_id, "cellphone": current_user.cellphone }
        charge_data = create_abacatepay_charge(amount=party.ticket_price, description=f"Ingresso {party.name} - {guest_name}", customer_info=customer_info)
        qr_filename = save_base64_as_png(charge_data.get('brCodeBase64'), charge_data['id'])
        if not qr_filename:
            raise ValueError("Falha ao criar o arquivo PNG do QR Code.")

        new_guest = Guest(
            name=guest_name,
            qr_hash=qr_hash,
            party_id=party_id,
            added_by_user_id=current_user.id,
            payment_status='pending_owner_invite',
            payment_charge_id=charge_data['id'],
            pix_qr_code_filename=qr_filename,
            pix_emv_code=charge_data.get('brCode'),
            pix_created_at=datetime.now(BRASILIA_TZ),
            purchase_link_id=purchase_link_id,
            purchase_price=party.ticket_price # NOVO: Salva o preço atual da festa
        )
        db.session.add(new_guest)
        db.session.commit()

        payment_link = url_for('buy_ticket_owner_invite', purchase_link_id=purchase_link_id, _external=True)
        return jsonify({
            'status': 'success',
            'message': f'Link de pagamento gerado para {guest_name}.',
            'payment_link': payment_link
        })
    except Exception as e:
        app.logger.error(f"Erro ao gerar link de pagamento: {e}")
        return jsonify({'status': 'error', 'message': 'Erro ao se comunicar com o serviço de pagamento.'}), 500

@app.route('/buy_ticket/owner_invite/<string:purchase_link_id>')
def buy_ticket_owner_invite(purchase_link_id):
    guest = Guest.query.filter_by(purchase_link_id=purchase_link_id).first_or_404()
    party = guest.party
    if guest.payment_status == 'paid':
        return redirect(url_for('show_ticket_payment', payment_charge_id=guest.payment_charge_id))
    if guest.payment_charge_id and guest.payment_status in ['pending', 'pending_owner_invite']:
        return redirect(url_for('show_ticket_payment', payment_charge_id=guest.payment_charge_id))

    if not guest.payment_charge_id or not guest.pix_qr_code_filename or guest.payment_status == 'failed':
        try:
            customer_info = { "name": guest.name, "email": guest.adder.email if guest.adder and guest.adder.email else "sememail@qrpass.com.br", "taxId": guest.adder.tax_id if guest.adder and guest.adder.tax_id else "00000000000", "cellphone": guest.adder.cellphone if guest.adder and guest.adder.cellphone else "00000000000" }
            charge_data = create_abacatepay_charge(amount=party.ticket_price, description=f"Ingresso {party.name} - {guest.name}", customer_info=customer_info)
            qr_filename = save_base64_as_png(charge_data.get('brCodeBase64'), charge_data['id'])
            if not qr_filename:
                raise ValueError("Falha ao criar o arquivo PNG do QR Code.")

            guest.payment_charge_id = charge_data['id']
            guest.payment_status = 'pending_owner_invite'
            guest.pix_qr_code_filename = qr_filename
            guest.pix_emv_code = charge_data.get('brCode')
            guest.pix_created_at = datetime.now(BRASILIA_TZ)
            guest.purchase_price = party.ticket_price # NOVO: Salva o preço atual da festa
            db.session.commit()
        except Exception as e:
            app.logger.error(f"Erro na API ao gerar PIX para convite: {e}")
            flash('Não foi possível gerar a cobrança PIX. Tente novamente.', 'danger')
            return render_template('show_ticket_payment.html', guest=guest, payment_pending=False, error_message="Falha ao gerar Pix.")

    return redirect(url_for('show_ticket_payment', payment_charge_id=guest.payment_charge_id))

@app.route('/buy_ticket/party/<int:party_id>', methods=['GET', 'POST'])
def buy_ticket_public(party_id):
    party = db.session.get(Party, party_id) or abort(404)
    if not party.allow_public_purchase:
        flash('Compra de ingressos online não está disponível para esta festa.', 'info')
        return redirect(url_for('public_party_page', shareable_link_id=party.shareable_link_id))

    if not current_user.is_authenticated:
        flash('Faça login ou cadastre-se para comprar seu ingresso.', 'info')
        return redirect(url_for('login', next=request.url))

    if not current_user.tax_id or not current_user.cellphone:
        flash("Por favor, complete seu perfil com CPF/CNPJ e Telefone para comprar ingressos.", 'warning')
        return redirect(url_for('complete_profile', next=request.url))

    if party.ticket_price == 0:
        existing_guest = Guest.query.filter_by(party_id=party_id, purchased_by_user_id=current_user.id, payment_status='paid').first()
        if existing_guest:
            flash(f'Você já possui um ingresso para {party.name}! Você pode visualizá-lo abaixo.', 'info')
            return render_template('show_ticket_payment.html', guest=existing_guest, payment_pending=False)

        guest_name = current_user.username
        qr_hash = generate_unique_code(Guest, 'qr_hash', 32, string.ascii_letters + string.digits)

        new_guest = Guest(
            name=guest_name,
            qr_hash=qr_hash,
            party_id=party_id,
            added_by_user_id=current_user.id,
            payment_status='paid',
            purchased_by_user_id=current_user.id,
            purchase_price=0.0 # NOVO: Preço 0.0 para ingresso gratuito
        )
        db.session.add(new_guest)
        db.session.commit()
        flash(f'Seu ingresso para {party.name} está pronto! Bem-vindo(a), {guest_name}!', 'success')
        return render_template('show_ticket_payment.html', guest=new_guest, payment_pending=False)

    if request.method == 'POST':
        guest_name = request.form.get('guest_name', current_user.username).strip()
        if not guest_name:
            flash('Nome do convidado é obrigatório.', 'danger')
            return render_template('buy_ticket_public.html', party=party, ticket_price_display=f"{party.ticket_price:.2f}".replace('.', ','))

        existing_paid_guest = Guest.query.filter_by(party_id=party_id, purchased_by_user_id=current_user.id, payment_status='paid').first()
        if existing_paid_guest:
            flash(f'Você já possui um ingresso pago para {party.name} em seu nome!', 'info')
            return redirect(url_for('show_ticket_payment', payment_charge_id=existing_paid_guest.payment_charge_id))

        try:
            customer_info = { "name": guest_name, "email": current_user.email, "taxId": current_user.tax_id, "cellphone": current_user.cellphone }
            description = f"Ingresso {party.name} - {guest_name}"
            charge_data = create_abacatepay_charge(amount=party.ticket_price, description=description, customer_info=customer_info)
            qr_filename = save_base64_as_png(charge_data.get('brCodeBase64'), charge_data['id'])
            if not qr_filename:
                raise ValueError("Falha ao criar o arquivo PNG do QR Code.")

            existing_pending_guest = Guest.query.filter_by(party_id=party_id, purchased_by_user_id=current_user.id, payment_status='pending').first()

            if existing_pending_guest:
                guest_to_update = existing_pending_guest
                guest_to_update.name = guest_name
            else:
                qr_hash = generate_unique_code(Guest, 'qr_hash', 32, string.ascii_letters + string.digits)
                guest_to_update = Guest(name=guest_name, qr_hash=qr_hash, party_id=party_id, added_by_user_id=current_user.id, purchased_by_user_id=current_user.id)
                db.session.add(guest_to_update)

            guest_to_update.payment_charge_id = charge_data['id']
            guest_to_update.payment_status = 'pending'
            guest_to_update.pix_qr_code_filename = qr_filename
            guest_to_update.pix_emv_code = charge_data.get('brCode')
            guest_to_update.pix_created_at = datetime.now(BRASILIA_TZ)
            guest_to_update.purchase_price = party.ticket_price # NOVO: Salva o preço atual da festa
            db.session.commit()
            return redirect(url_for('show_ticket_payment', payment_charge_id=charge_data['id']))
        except Exception as e:
            app.logger.error(f"Erro na API ao comprar ingresso: {e}")
            flash('Erro ao gerar a cobrança Pix. Tente novamente mais tarde.', 'danger')
            return render_template('buy_ticket_public.html', party=party, ticket_price_display=f"{party.ticket_price:.2f}".replace('.', ','), guest_name=guest_name)

    return render_template('buy_ticket_public.html', party=party, ticket_price_display=f"{party.ticket_price:.2f}".replace('.', ','))

@app.route('/show_ticket_payment/<string:payment_charge_id>')
def show_ticket_payment(payment_charge_id):
    guest_ticket_payment = Guest.query.filter_by(payment_charge_id=payment_charge_id).first_or_404()

    pix_creation_iso = guest_ticket_payment.pix_created_at.isoformat() if guest_ticket_payment.pix_created_at else None

    if guest_ticket_payment.payment_status == 'paid':
        flash(f"Seu ingresso para {guest_ticket_payment.party.name} já foi pago!", "success")
        return render_template('show_ticket_payment.html',
                               guest=guest_ticket_payment,
                               payment_pending=False,
                               pix_creation_iso=pix_creation_iso)

    elif guest_ticket_payment.payment_status in ['pending', 'pending_owner_invite']:
        return render_template('show_ticket_payment.html',
                               guest=guest_ticket_payment,
                               payment_pending=True,
                               pix_creation_iso=pix_creation_iso)
    else:
        flash("Sua cobrança expirou ou falhou. Por favor, gere uma nova.", "warning")
        if guest_ticket_payment.purchase_link_id:
            return redirect(url_for('buy_ticket_owner_invite', purchase_link_id=guest_ticket_payment.purchase_link_id))
        elif guest_ticket_payment.purchased_by_user_id:
            return redirect(url_for('buy_ticket_public', party_id=guest_ticket_payment.party_id))
        else:
            return redirect(url_for('public_party_page', shareable_link_id=guest_ticket_payment.party.shareable_link_id))

def create_abacatepay_charge(amount, description, customer_info):
    url = "https://api.abacatepay.com/v1/pixQrCode/create"
    headers = {"Authorization": f"Bearer {ABACATE_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "amount": int(amount * 100),
        "expiresIn": 3600,
        "description": description,
        "customer": customer_info
    }
    masked_payload = payload.copy()
    if 'customer' in masked_payload:
        masked_payload['customer'] = {
            'name': masked_payload['customer'].get('name'),
            'email': '***',
            'taxId': '***',
            'cellphone': '***'
        }
    app.logger.info(f"Chamando AbacatePay create com payload: {masked_payload}")
    response = requests.post(url, json=payload, headers=headers)
    response.raise_for_status()
    data = response.json().get('data', {})
    if not all([data.get('brCodeBase64'), data.get('brCode'), data.get('id')]):
        raise ValueError("Resposta da API de PIX incompleta ou sem dados do QR Code.")
    return data

def check_abacatepay_status(charge_id):
    url = "https://api.abacatepay.com/v1/pixQrCode/check"
    headers = {"Authorization": f"Bearer {ABACATE_API_KEY}"}
    params = {"id": charge_id}
    app.logger.info(f"Chamando AbacatePay check para charge_id: {charge_id}")
    response = requests.get(url, headers=headers, params=params)
    response.raise_for_status()
    data = response.json().get('data', {})
    if not data.get('status'):
        raise ValueError("Resposta da API de PIX incompleta (status ausente).")
    return data

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

@app.route('/complete_profile', methods=['GET', 'POST'])
@login_required
def complete_profile():
    form = CompleteProfileForm()
    if form.validate_on_submit():
        tax_id = form.tax_id.data.strip()
        cellphone = form.cellphone.data.strip()

        if not tax_id.isdigit() or len(tax_id) not in [11, 14]:
            flash("CPF/CNPJ inválido. Digite apenas números.", 'danger')
            return render_template('complete_profile.html', form=form)
        if not cellphone.isdigit() or len(cellphone) not in [10, 11, 12, 13]:
             flash("Telefone inválido. Digite apenas números.", 'danger')
             return render_template('complete_profile.html', form=form)

        if User.query.filter(User.tax_id == tax_id, User.id != current_user.id).first():
            flash("Este CPF/CNPJ já está associado a outra conta.", 'danger')
            return render_template('complete_profile.html', form=form)

        current_user.tax_id, current_user.cellphone = tax_id, cellphone
        db.session.commit()
        flash("Perfil atualizado! Agora você já pode comprar ingressos.", 'success')

        next_page = request.args.get('next')
        return redirect(next_page or url_for('dashboard'))

    return render_template('complete_profile.html', form=form)

@app.route('/payment/check_status/<pix_id>')
def check_payment_status(pix_id):
    is_guest_ticket_payment = Guest.query.filter_by(payment_charge_id=pix_id).first()

    if not is_guest_ticket_payment:
        return jsonify({'status': 'error', 'message': 'Cobrança não encontrada.'}), 404

    try:
        data = check_abacatepay_status(pix_id)
        status = data.get('status')

        if status == 'PAID':
            if is_guest_ticket_payment.payment_status != 'paid':
                is_guest_ticket_payment.payment_status = 'paid'
                # NOVO: Garante que purchase_price esteja definido no momento do pagamento
                if is_guest_ticket_payment.purchase_price is None:
                    # Este caso idealmente não deveria ocorrer se o preço é definido na criação da cobrança,
                    # mas serve como fallback de segurança.
                    is_guest_ticket_payment.purchase_price = is_guest_ticket_payment.party.ticket_price
                db.session.commit()
                delete_pix_qr_code_file(is_guest_ticket_payment)
                return jsonify({'status': 'PAID', 'type': 'ticket_purchase', 'guest_name': is_guest_ticket_payment.name, 'qr_image_url': is_guest_ticket_payment.qr_image_url})
            else:
                delete_pix_qr_code_file(is_guest_ticket_payment)
                return jsonify({'status': 'PAID', 'message': 'Pagamento já processado.'})

        elif status == 'EXPIRED':
            if is_guest_ticket_payment.payment_status in ['pending', 'pending_owner_invite']:
                is_guest_ticket_payment.payment_status = 'failed'
                db.session.commit()
            return jsonify({'status': 'EXPIRED'})

        return jsonify({'status': status})
    except Exception as e:
        app.logger.error(f"Erro ao verificar status do pagamento via API: {e}")
        return jsonify({'status': 'error', 'message': 'Erro ao consultar status do pagamento.'}), 500

@csrf.exempt
@app.route('/webhooks/abacatepay', methods=['POST'])
def abacatepay_webhook():
    # 1. Verificação da Assinatura (Segurança)
    signature_header = request.headers.get('Abacate-Signature')
    if not signature_header:
        app.logger.warning("Webhook AbacatePay recebido sem assinatura.")
        return jsonify({'status': 'error', 'message': 'Signature missing'}), 400

    try:
        # O corpo do request precisa ser lido como bytes
        payload_bytes = request.get_data()
        # Cria a assinatura esperada usando o segredo do webhook
        expected_signature = hmac.new(ABACATE_WEBHOOK_SECRET.encode('utf-8'), payload_bytes, hashlib.sha256).hexdigest()

        # Compara a assinatura recebida com a esperada de forma segura
        if not hmac.compare_digest(signature_header, expected_signature):
            app.logger.warning("Webhook AbacatePay com assinatura inválida.")
            return jsonify({'status': 'error', 'message': 'Invalid signature'}), 403
    except Exception as e:
        app.logger.error(f"Erro ao verificar a assinatura do webhook: {e}")
        return jsonify({'status': 'error', 'message': 'Signature verification failed'}), 500

    # 2. Processamento do Payload (após validação)
    payload = request.get_json()
    app.logger.info(f"Webhook recebido e validado: {payload}")

    if not payload or 'event' not in payload or 'data' not in payload:
        app.logger.warning("Webhook AbacatePay com payload inválido.")
        return jsonify({'status': 'error', 'message': 'Invalid payload'}), 400

    event_type = payload.get('event')
    transaction_id = payload.get('data', {}).get('id')

    if event_type == 'pix_qr_code.paid' and transaction_id:
        guest = Guest.query.filter_by(payment_charge_id=transaction_id).first()
        if guest and guest.payment_status != 'paid':
            guest.payment_status = 'paid'
            # NOVO: Garante que purchase_price esteja definido no momento do pagamento
            if guest.purchase_price is None:
                # Este caso idealmente não deveria ocorrer se o preço é definido na criação da cobrança,
                # mas serve como fallback de segurança.
                guest.purchase_price = guest.party.ticket_price
            db.session.commit()
            delete_pix_qr_code_file(guest)
            app.logger.info(f"Pagamento de ingresso confirmado via webhook para {guest.name} (Festa: {guest.party.name})")
            return jsonify({'status': 'success', 'message': 'Guest ticket status updated'}), 200
        elif guest:
            app.logger.info(f"Pagamento webhook recebido para ingresso já pago: {guest.name}")
            delete_pix_qr_code_file(guest)
            return jsonify({'status': 'success', 'message': 'Ticket already paid'}), 200

    app.logger.info(f"Webhook processado (evento não relevante ou ID não encontrado): {event_type}, {transaction_id}")
    return jsonify({'status': 'received', 'message': 'Event not processed or already handled'}), 200


def get_party_stats_data(party_id):
    total_invited = Guest.query.filter_by(party_id=party_id).count()
    entered_count = Guest.query.filter_by(party_id=party_id, entered=True).count()
    party = Party.query.get(party_id)

    # NOVO: Calcular faturamento total de ingressos pagos
    total_revenue = db.session.query(db.func.sum(Guest.purchase_price)).filter(
        Guest.party_id == party_id,
        Guest.payment_status == 'paid'
    ).scalar() or 0.0 # Garante que seja 0.0 se não houver vendas ou preço for nulo

    if party and party.ticket_price > 0:
        total_paid_guests = Guest.query.filter_by(party_id=party_id, payment_status='paid').count()
        entered_paid_guests = Guest.query.filter_by(party_id=party_id, payment_status='paid', entered=True).count()
        return {
            'total_invited': total_invited,
            'total_paid_tickets': total_paid_guests,
            'entered_count': entered_paid_guests,
            'not_entered_count': total_paid_guests - entered_paid_guests,
            'percentage_entered': round((entered_paid_guests / total_paid_guests) * 100, 2) if total_paid_guests > 0 else 0.0,
            'total_revenue': total_revenue # Adiciona o faturamento
        }
    else:
        return {
            'total_invited': total_invited,
            'total_paid_tickets': 0,
            'entered_count': entered_count,
            'not_entered_count': total_invited - entered_count,
            'percentage_entered': round((entered_count / total_invited) * 100, 2) if total_invited > 0 else 0.0,
            'total_revenue': total_revenue # Adiciona o faturamento (mesmo para festas gratuitas, será 0)
        }

@app.route('/api/party/<int:party_id>/stats', methods=['GET'])
def get_stats(party_id):
    return jsonify(get_party_stats_data(party_id))

@app.route('/api/party/<int:party_id>/guests', methods=['GET', 'POST'])
@login_required
def handle_guests(party_id):
    party = db.session.get(Party, party_id) or abort(404)
    check_collaboration_permission(party)

    if request.method == 'POST':
        data = request.get_json()
        name = data.get('name', '').strip()
        if not name: return jsonify({'error': 'O nome do convidado é obrigatório.'}), 400

        new_guest = Guest(
            name=name,
            qr_hash=generate_unique_code(Guest, 'qr_hash', 32, string.ascii_letters + string.digits),
            party_id=party_id,
            added_by_user_id=current_user.id,
            payment_status='not_applicable',
            purchase_price=0.0 # NOVO: Preço 0.0 para convidado gratuito
        )
        db.session.add(new_guest)
        db.session.commit()
        return jsonify({
            'id': new_guest.id, 'name': new_guest.name, 'qr_hash': new_guest.qr_hash, 'entered': new_guest.entered,
            'qr_image_url': new_guest.qr_image_url, 'check_in_time': new_guest.get_check_in_time_str(),
            'added_by': new_guest.adder.username, 'payment_status': new_guest.payment_status
        }), 201

    page, per_page, search_term = request.args.get('page', 1, type=int), request.args.get('per_page', 50, type=int), request.args.get('search')
    sort_by, sort_dir = request.args.get('sort_by', 'name'), request.args.get('sort_dir', 'asc')
    query = Guest.query.filter_by(party_id=party_id)
    if search_term: query = query.filter(Guest.name.ilike(f'%{search_term.strip()}%'))

    sort_columns = {'name': Guest.name, 'entered': Guest.entered, 'check_in_time': Guest.check_in_time, 'added_by': User.username, 'payment_status': Guest.payment_status}

    if sort_by == 'added_by':
        query = query.join(User, Guest.added_by_user_id == User.id)

    order_column = sort_columns.get(sort_by, Guest.name)
    order_func = order_column.desc() if sort_dir == 'desc' else order_column.asc()

    pagination = query.order_by(order_func.nullslast()).paginate(page=page, per_page=per_page, error_out=False)

    guests_data = []
    for g in pagination.items:
        purchased_by_name = g.purchaser.username if g.purchaser else None

        guests_data.append({
            'id': g.id, 'name': g.name, 'qr_hash': g.qr_hash, 'entered': g.entered, 'qr_image_url': g.qr_image_url,
            'check_in_time': g.get_check_in_time_str(), 'added_by': g.adder.username if g.adder else 'N/A',
            'payment_status': g.payment_status, 'purchased_by': purchased_by_name, 'purchase_link_id': g.purchase_link_id,
            'purchase_price': g.purchase_price # NOVO: Inclui o preço de compra na API
        })

    return jsonify({
        'guests': guests_data,
        'pagination': {
            'page': pagination.page, 'per_page': pagination.per_page, 'total_pages': pagination.pages,
            'total_items': pagination.total, 'has_next': pagination.has_next, 'has_prev': pagination.has_prev
        }
    })

@app.route('/api/party/<int:party_id>/guests/<qr_hash>/enter', methods=['POST'])
def mark_entered(party_id, qr_hash):
    guest = Guest.query.filter_by(qr_hash=qr_hash, party_id=party_id).first()
    if not guest: return jsonify({'error': 'QR Code inválido para esta festa'}), 404

    if guest.party.ticket_price > 0 and guest.payment_status != 'paid':
        return jsonify({
            'id': guest.id, 'name': guest.name, 'qr_hash': guest.qr_hash, 'entered': False,
            'message': f'Ingresso de {guest.name} não foi pago (Status: {guest.payment_status}).',
            'is_new_entry': False, 'check_in_time': guest.get_check_in_time_str(), 'error_type': 'payment_pending'
        }), 403

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

    guest.name = new_name
    db.session.commit()
    return jsonify({'id': guest.id, 'name': guest.name, 'qr_hash': guest.qr_hash, 'entered': guest.entered, 'qr_image_url': guest.qr_image_url, 'check_in_time': guest.get_check_in_time_str(), 'message': f'Nome do convidado atualizado.'}), 200

@app.route('/api/party/<int:party_id>/guests/<qr_hash>/toggle_entry', methods=['PUT'])
@login_required
def toggle_entry_manually(party_id, qr_hash):
    guest = Guest.query.filter_by(qr_hash=qr_hash, party_id=party_id).first_or_404()
    check_collaboration_permission(guest.party)

    if guest.party.ticket_price > 0 and guest.payment_status != 'paid' and not guest.entered:
        return jsonify({'error': f'O ingresso de {guest.name} não foi pago e não pode ser marcado como "Entrou" manualmente.'}), 403

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

    if guest.payment_status == 'paid':
        flash(f"Atenção: Você está deletando um ingresso que JÁ FOI PAGO por {guest_name}.", "warning")

    delete_pix_qr_code_file(guest)

    db.session.delete(guest)
    db.session.commit()
    return jsonify({'message': f'Convidado {guest_name} removido com sucesso.'}), 200

class PDF(FPDF):
    def __init__(self, orientation='P', unit='mm', format='A4', party_name=''):
        super().__init__(orientation, unit, format)
        self.montserrat_font_path = FONT_PATH # A fonte continua vindo do diretório da aplicação
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
            except Exception:
                app.logger.warning(f"Erro ao carregar fonte Montserrat de {self.montserrat_font_path}. Usando fonte padrão.")
                pass
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
        col_width_stat = (self.w - self.l_margin - self.r_margin) / 4.5
        stat_box_height = 14
        line_height_label, line_height_value = 5, 6
        padding_top_box = (stat_box_height - (line_height_label + line_height_value)) / 2

        current_x, base_y = self.l_margin, self.get_y()

        stats_items = [
            ("Convidados (Total):", str(stats_data['total_invited'])),
            ("Ingressos Pagos:", str(stats_data['total_paid_tickets'])),
            ("Entraram:", str(stats_data['entered_count'])),
            ("Não Entraram:", str(stats_data['not_entered_count'])),
            ("Comparecimento:", f"{stats_data['percentage_entered']:.2f}%"),
            ("Faturamento Total:", f"R$ {stats_data['total_revenue']:.2f}") # NOVO: Adiciona faturamento
        ]

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
            self.set_text_color(0, 100, 200) # Mantém a cor para valores
            # Cor específica para faturamento
            if label == "Faturamento Total:":
                self.set_text_color(0, 150, 0) # Verde para faturamento
            self.set_font(self.current_font_family, 'B', 10)
            self.cell(col_width_stat, line_height_value, value, border=0, align='C')
            self.set_text_color(0, 0, 0) # Reseta a cor

            current_x += col_width_stat
            # Quebra de linha após 4 colunas ou no final
            if (i + 1) % 4 == 0 and (i + 1) < len(stats_items):
                current_x = self.l_margin
                base_y += stat_box_height + 5 # Ajusta espaço para próxima linha
                self.ln(5) # Linha vazia para separar
        self.set_y(base_y + stat_box_height)
        self.ln(5)


    def draw_pie_chart(self, stats_data, y_offset, chart_size_mm=70):
        labels, sizes, colors = ('Entraram', 'Não Entraram'), [stats_data['entered_count'], stats_data['not_entered_count']], ['#4BC0C0', '#FF6384']

        if sum(sizes) == 0:
            self.set_font(self.current_font_family, 'I', 10)
            self.cell(0, 10, "Sem dados de comparecimento de ingressos pagos para o gráfico.", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
            self.ln(5)
            return

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

        # Adicionar coluna "Preço Pago" ao cabeçalho da tabela
        col_widths = {"name": 55, "payment_status": 22, "purchase_price": 20, "purchased_by": 28, "status": 20, "check_in": 30, "added_by": 25}
        total_width = sum(col_widths.values())
        start_x = self.l_margin + (self.w - 2 * self.l_margin - total_width) / 2

        self.set_x(start_x)
        self.cell(col_widths["name"], 8, 'Nome', 1, 0, 'C', 1)
        self.cell(col_widths["payment_status"], 8, 'Pagamento', 1, 0, 'C', 1)
        self.cell(col_widths["purchase_price"], 8, 'Preço Pago', 1, 0, 'C', 1) # NOVO
        self.cell(col_widths["purchased_by"], 8, 'Comprado Por', 1, 0, 'C', 1)
        self.cell(col_widths["status"], 8, 'Entrou?', 1, 0, 'C', 1)
        self.cell(col_widths["check_in"], 8, 'Data Check-in', 1, 0, 'C', 1)
        self.cell(col_widths["added_by"], 8, 'Adicionado Por', 1, 1, 'C', 1)

        self.set_font(self.current_font_family, '', 8.5)
        for i, guest_obj in enumerate(guests_data_table):
            self.set_x(start_x)
            fill = i % 2 == 0

            payment_status_display = {
                'not_applicable': 'Gratuito',
                'pending_owner_invite': 'Aguard. Pgto.',
                'pending': 'Aguard. Pgto.',
                'paid': 'Pago',
                'failed': 'Falhou'
            }.get(guest_obj.payment_status, guest_obj.payment_status)

            # Formatação do preço de compra
            purchase_price_display = f"R$ {guest_obj.purchase_price:.2f}" if guest_obj.purchase_price is not None else 'N/A'

            purchased_by_name = guest_obj.purchaser.username if guest_obj.purchaser else 'N/A'
            added_by_name = guest_obj.adder.username if guest_obj.adder else 'N/A'


            self.cell(col_widths["name"], 7, guest_obj.name, 1, 0, 'L', fill)
            self.cell(col_widths["payment_status"], 7, payment_status_display, 1, 0, 'C', fill)
            self.cell(col_widths["purchase_price"], 7, purchase_price_display, 1, 0, 'C', fill) # NOVO
            self.cell(col_widths["purchased_by"], 7, purchased_by_name, 1, 0, 'C', fill)
            self.cell(col_widths["status"], 7, 'Sim' if guest_obj.entered else 'Não', 1, 0, 'C', fill)
            self.cell(col_widths["check_in"], 7, guest_obj.get_check_in_time_str(), 1, 0, 'C', fill)
            self.cell(col_widths["added_by"], 7, added_by_name, 1, 1, 'C', fill)

@app.route('/api/party/<int:party_id>/export/csv')
@login_required
def export_guests_csv(party_id):
    party = db.session.get(Party, party_id) or abort(404)
    check_collaboration_permission(party)
    guests_data = get_all_guests_for_export(party_id)
    si = io.StringIO()
    cw = csv.writer(si)

    # NOVO: Adiciona "Preço Pago" ao cabeçalho do CSV
    cw.writerow(['Nome', 'Status Entrada', 'Data Check-in', 'Status Pagamento', 'Preço Pago', 'Comprado Por', 'Adicionado Por'])

    for guest in guests_data:
        payment_status_display = {
            'not_applicable': 'Gratuito',
            'pending_owner_invite': 'Aguardando Pagamento (Dono)',
            'pending': 'Aguardando Pagamento',
            'paid': 'Pago',
            'failed': 'Pagamento Falhou'
        }.get(guest.payment_status, guest.payment_status)

        # Formatação do preço de compra
        purchase_price_export = f"{guest.purchase_price:.2f}".replace('.', ',') if guest.purchase_price is not None else 'N/A'

        purchased_by_name = guest.purchaser.username if guest.purchaser else 'N/A'
        added_by_name = guest.adder.username if guest.adder else 'N/A'

        cw.writerow([
            guest.name,
            'Sim' if guest.entered else 'Não',
            guest.get_check_in_time_str(),
            payment_status_display,
            purchase_price_export, # NOVO
            purchased_by_name,
            added_by_name
        ])
    return Response(si.getvalue(), mimetype="text/csv", headers={"Content-disposition": f"attachment; filename=lista_{party.name.replace(' ', '_')}.csv"})

@app.route('/api/party/<int:party_id>/export/pdf')
@login_required
def export_guests_pdf(party_id):
    party = db.session.get(Party, party_id) or abort(404)
    check_collaboration_permission(party)

    guests_for_table, stats_for_chart = get_all_guests_for_export(party_id), get_party_stats_data(party_id)

    pdf = PDF(party_name=party.name)
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.alias_nb_pages()
    pdf.add_page()

    pdf.draw_stats_summary(stats_for_chart)
    # Reajustar o Y do gráfico se a tabela de stats cresceu
    # pdf.draw_pie_chart(stats_for_chart, y_offset=pdf.get_y(), chart_size_mm=70) # Remover y_offset, já está no get_y()

    if guests_for_table:
        pdf.chapter_body(guests_for_table)
    else:
        pdf.set_font(pdf.current_font_family, 'I', 10)
        self.cell(0, 10, "Nenhum convidado na lista.", 0, 1, 'C')

    timestamp = datetime.now(BRASILIA_TZ).strftime("%Y%m%d_%H%M%S")
    filename = f"relatorio_{party.name.replace(' ', '_')}_{timestamp}.pdf"
    return Response(bytes(pdf.output()), mimetype='application/pdf', headers={'Content-Disposition': f'attachment;filename={filename}'})

def get_all_guests_for_export(party_id):
    return Guest.query.filter_by(party_id=party_id).all()

if __name__ == '__main__':
    is_debug_mode = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    app.run(debug=is_debug_mode, host='0.0.0.0', port=5000)