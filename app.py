import os
import hashlib
import qrcode # Para gerar a imagem do QR Code base
from PIL import Image, ImageDraw, ImageFont # Para manipular a imagem e adicionar texto
from flask import Flask, request, jsonify, render_template, url_for
from flask_sqlalchemy import SQLAlchemy

# --- Configuração do App ---
app = Flask(__name__)
basedir = os.path.abspath(os.path.dirname(__file__))

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'instance', 'party.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

QR_CODE_FOLDER_NAME = 'qr_codes'
QR_CODE_STATIC_PATH = os.path.join('static', QR_CODE_FOLDER_NAME)
QR_CODE_SAVE_PATH = os.path.join(basedir, QR_CODE_STATIC_PATH)

if not os.path.exists(QR_CODE_SAVE_PATH):
    os.makedirs(QR_CODE_SAVE_PATH)
    app.logger.info(f"Pasta QR Codes criada em: {QR_CODE_SAVE_PATH}")

# --- Modelo do Banco de Dados ---
class Guest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    qr_hash = db.Column(db.String(64), unique=True, nullable=False)
    entered = db.Column(db.Boolean, default=False, nullable=False)
    qr_image_filename = db.Column(db.String(255), nullable=True)

    def __repr__(self): return f'<Guest {self.name}>'
    @property
    def qr_image_url(self):
        return url_for('static', filename=f'{QR_CODE_FOLDER_NAME}/{self.qr_image_filename}') if self.qr_image_filename else None

instance_path = os.path.join(basedir, 'instance')
if not os.path.exists(instance_path):
    os.makedirs(instance_path)

with app.app_context():
    db.create_all()

# --- ROTAS DA APLICAÇÃO (PÁGINAS HTML) ---
@app.route('/')
def index(): return render_template('index.html')

@app.route('/scanner')
def scanner_page():
    return render_template('scanner.html')

# --- ROTA PARA ESTATÍSTICAS (NOVA/CORRIGIDA) ---
@app.route('/api/stats', methods=['GET'])
def get_stats():
    total_invited = Guest.query.count()
    entered_count = Guest.query.filter_by(entered=True).count()
    not_entered_count = total_invited - entered_count # Ou Guest.query.filter_by(entered=False).count()
    
    percentage_entered = 0.0
    if total_invited > 0:
        percentage_entered = round((entered_count / total_invited) * 100, 2)

    app.logger.info(f"Estatísticas: Total={total_invited}, Entraram={entered_count}, NaoEntraram={not_entered_count}, %Entraram={percentage_entered}")

    return jsonify({
        'total_invited': total_invited,
        'entered_count': entered_count,
        'not_entered_count': not_entered_count,
        'percentage_entered': percentage_entered
    })

# --- ROTAS DA API PARA CONVIDADOS ---
@app.route('/api/guests', methods=['POST'])
def add_guest():
    data = request.get_json()
    if not data or 'name' not in data: return jsonify({'error': 'Nome obrigatório'}), 400
    name = data['name'].strip()
    if not name: return jsonify({'error': 'Nome vazio'}), 400
    if Guest.query.filter_by(name=name).first(): return jsonify({'error': f'"{name}" já existe.'}), 409
    
    qr_hash = hashlib.sha256(name.encode('utf-8')).hexdigest()
    qr_fn = f"{qr_hash}.png"
    qr_fp = os.path.join(QR_CODE_SAVE_PATH, qr_fn)

    try:
        qr = qrcode.QRCode(version=1,error_correction=qrcode.constants.ERROR_CORRECT_L,box_size=10,border=4)
        qr.add_data(qr_hash); qr.make(fit=True)
        img_qr = qr.make_image(fill_color="black", back_color="white").convert('RGB')
        
        padding_bottom_for_text = 60; text_color = (0, 0, 0); background_color_canvas = (255, 255, 255)
        font_size = 30
        font_file_name = "Montserrat-Regular.ttf" # <-- CERTIFIQUE-SE QUE ESTE ARQUIVO EXISTE
        try:
            font = ImageFont.truetype(font_file_name, font_size)
        except IOError:
            app.logger.warning(f"Fonte '{font_file_name}' não encontrada, usando fonte padrão.")
            font = ImageFont.load_default() 
        
        new_width = img_qr.width; new_height = img_qr.height + padding_bottom_for_text
        img_canvas = Image.new('RGB', (new_width, new_height), background_color_canvas)
        img_canvas.paste(img_qr, (0, 0))
        draw = ImageDraw.Draw(img_canvas)
        
        try: text_bbox = draw.textbbox((0,0), name, font=font); text_width = text_bbox[2] - text_bbox[0]
        except AttributeError: text_width, _ = draw.textsize(name, font=font)
        
        text_x = (new_width - text_width) / 2
        text_y = img_qr.height + (padding_bottom_for_text - font_size) / 2 - 5 
        draw.text((text_x, text_y), name, font=font, fill=text_color)
        img_canvas.save(qr_fp)
        app.logger.info(f"QR Code com nome para '{name}' salvo em: {qr_fp}")
    except Exception as e:
        app.logger.error(f"Erro ao gerar/salvar QR com texto para '{name}': {e}")
        try: qrcode.make(qr_hash).save(qr_fp)
        except Exception as e_fallback: app.logger.error(f"Erro crítico ao salvar QR para {name}: {e_fallback}"); return jsonify({'error': 'Falha crítica ao gerar QR'}), 500

    new_guest = Guest(name=name, qr_hash=qr_hash, qr_image_filename=qr_fn)
    db.session.add(new_guest); db.session.commit()
    return jsonify({'id': new_guest.id, 'name': new_guest.name, 'qr_hash': new_guest.qr_hash,
                    'entered': new_guest.entered, 'qr_image_url': new_guest.qr_image_url}), 201

@app.route('/api/guests', methods=['GET'])
def get_guests():
    return jsonify([{'id': g.id, 'name': g.name, 'qr_hash': g.qr_hash,
                     'entered': g.entered, 'qr_image_url': g.qr_image_url}
                    for g in Guest.query.order_by(Guest.name).all()])

@app.route('/api/guests/<qr_hash>/enter', methods=['POST'])
def mark_entered(qr_hash):
    guest = Guest.query.filter_by(qr_hash=qr_hash).first()
    is_new_entry = False; message = ""
    if not guest: return jsonify({'error': 'Convidado não encontrado (QR inválido)'}), 404
    if guest.entered: message = f'{guest.name} já entrou na festa.'
    else: guest.entered = True; db.session.commit(); is_new_entry = True; message = f'{guest.name} marcou presença!'
    return jsonify({'id': guest.id, 'name': guest.name, 'qr_hash': guest.qr_hash, 'entered': guest.entered, 'message': message, 'is_new_entry': is_new_entry})

@app.route('/api/guests/<qr_hash>/toggle_entry', methods=['PUT'])
def toggle_entry_manually(qr_hash):
    guest = Guest.query.filter_by(qr_hash=qr_hash).first()
    if not guest: return jsonify({'error': 'Convidado não encontrado'}), 404
    guest.entered = not guest.entered; db.session.commit()
    action = "entrou" if guest.entered else "NÃO entrou"
    return jsonify({'id': guest.id, 'name': guest.name, 'qr_hash': guest.qr_hash, 'entered': guest.entered, 'message': f'Status de {guest.name} alterado: {action}.'})

@app.route('/api/guests/<qr_hash>', methods=['DELETE'])
def delete_guest(qr_hash):
    guest = Guest.query.filter_by(qr_hash=qr_hash).first()
    if not guest: return jsonify({'error': 'Convidado não encontrado'}), 404
    if guest.qr_image_filename:
        qr_image_path = os.path.join(QR_CODE_SAVE_PATH, guest.qr_image_filename)
        try:
            if os.path.exists(qr_image_path): os.remove(qr_image_path)
        except Exception as e: app.logger.error(f"Erro ao remover arquivo QR '{guest.qr_image_filename}': {e}")
    db.session.delete(guest); db.session.commit()
    return jsonify({'message': f'Convidado {guest.name} removido com sucesso'}), 200

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
    print("Servidor Flask rodando em http://localhost:5000 (ou http://SEU_IP_LOCAL:5000)")
    print("Use ngrok (https://ngrok.com/) para criar um túnel HTTPS para testes em dispositivos móveis.")