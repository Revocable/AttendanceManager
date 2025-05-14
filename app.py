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
    app.logger.info(f"Pasta QR Codes: {QR_CODE_SAVE_PATH}")

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

# --- ROTAS DA API ---
@app.route('/')
def index(): return render_template('index.html')

@app.route('/scanner')
def scanner_page():
    return render_template('scanner.html')

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
        # 1. Gerar o QR Code base
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10, # Tamanho de cada "caixa" do QR code
            border=4,    # Espessura da borda do QR code
        )
        qr.add_data(qr_hash) # O dado do QR é o hash
        qr.make(fit=True)
        img_qr = qr.make_image(fill_color="black", back_color="white").convert('RGB')

        # 2. Configurações para adicionar texto
        padding_bottom_for_text = 60  # Espaço extra abaixo do QR para o texto
        text_color = (0, 0, 0)      # Preto
        background_color_canvas = (255, 255, 255) # Branco

        # Tenta carregar uma fonte. Se não encontrar, usa a padrão do Pillow (que pode ser bem básica)
        try:
            font = ImageFont.truetype("Montserrat-Regular.ttf", 30)
        except IOError:
            app.logger.warning("Fonte Montserrat não encontrada, usando fonte padrão. O texto pode não ficar ideal.")
            font = ImageFont.load_default() # Garante que temos uma fonte

        # 3. Criar uma nova imagem (canvas) maior para acomodar o QR e o texto
        new_width = img_qr.width
        new_height = img_qr.height + padding_bottom_for_text
        img_canvas = Image.new('RGB', (new_width, new_height), background_color_canvas)

        # 4. Colar o QR code no canvas
        img_canvas.paste(img_qr, (0, 0))

        # 5. Desenhar o texto no canvas
        draw = ImageDraw.Draw(img_canvas)
        
        # Calcula a largura do texto para centralizar
        # No Pillow antigo, textsize era usado. No novo, getbbox ou getlength.
        try:
            text_bbox = draw.textbbox((0,0), name, font=font)
            text_width = text_bbox[2] - text_bbox[0]
            # text_height = text_bbox[3] - text_bbox[1] # Se precisar da altura
        except AttributeError: # Fallback para versões mais antigas do Pillow
            text_width, _ = draw.textsize(name, font=font)


        text_x = (new_width - text_width) / 2
        text_y = img_qr.height + 15 # Posição Y abaixo do QR code (10px de padding)

        draw.text((text_x, text_y), name, font=font, fill=text_color)

        # 6. Salvar a imagem composta
        img_canvas.save(qr_fp)
        app.logger.info(f"QR Code com nome para '{name}' salvo em: {qr_fp}")

    except Exception as e:
        app.logger.error(f"Erro ao gerar/salvar QR com texto para '{name}': {e}")
        # Se falhar ao adicionar texto, tenta salvar o QR simples como fallback
        try:
            qrcode.make(qr_hash).save(qr_fp)
            app.logger.info(f"Fallback: QR Code simples para '{name}' salvo em: {qr_fp}")
        except Exception as e_fallback:
            app.logger.error(f"Erro crítico ao salvar QR (mesmo fallback) para {name}: {e_fallback}")
            return jsonify({'error': 'Falha crítica ao gerar imagem QR'}), 500
        # Continua para salvar no DB mesmo que só o QR simples tenha sido salvo
        # ou retorna erro se preferir não continuar sem o texto.

    new_guest = Guest(name=name, qr_hash=qr_hash, qr_image_filename=qr_fn)
    db.session.add(new_guest); db.session.commit()
    return jsonify({'id': new_guest.id, 'name': new_guest.name, 'qr_hash': new_guest.qr_hash,
                    'entered': new_guest.entered, 'qr_image_url': new_guest.qr_image_url}), 201

# ... (o resto das suas rotas: get_guests, mark_entered, toggle_entry_manually, delete_guest permanecem iguais) ...
@app.route('/api/guests', methods=['GET'])
def get_guests():
    return jsonify([{'id': g.id, 'name': g.name, 'qr_hash': g.qr_hash,
                     'entered': g.entered, 'qr_image_url': g.qr_image_url}
                    for g in Guest.query.order_by(Guest.name).all()])

@app.route('/api/guests/<qr_hash>/enter', methods=['POST'])
def mark_entered(qr_hash):
    guest = Guest.query.filter_by(qr_hash=qr_hash).first()
    is_new_entry = False
    message = ""
    if not guest:
        app.logger.warning(f"Check-in: QR Hash não encontrado: {qr_hash}")
        return jsonify({'error': 'Convidado não encontrado (QR inválido)'}), 404
    if guest.entered:
        app.logger.info(f"Check-in: '{guest.name}' já entrou.")
        message = f'{guest.name} já entrou na festa.'
    else:
        guest.entered = True
        db.session.commit()
        is_new_entry = True
        message = f'{guest.name} marcou presença!'
        app.logger.info(f"Check-in: '{guest.name}' marcado como presente.")
    return jsonify({
        'id': guest.id, 'name': guest.name, 'qr_hash': guest.qr_hash,
        'entered': guest.entered, 'message': message,
        'is_new_entry': is_new_entry
    })

@app.route('/api/guests/<qr_hash>/toggle_entry', methods=['PUT'])
def toggle_entry_manually(qr_hash):
    guest = Guest.query.filter_by(qr_hash=qr_hash).first()
    if not guest: return jsonify({'error': 'Convidado não encontrado'}), 404
    guest.entered = not guest.entered; db.session.commit()
    action = "entrou" if guest.entered else "NÃO entrou"
    return jsonify({'id': guest.id, 'name': guest.name, 'qr_hash': guest.qr_hash,
                    'entered': guest.entered, 'message': f'Status de {guest.name} alterado: {action}.'})

@app.route('/api/guests/<qr_hash>', methods=['DELETE'])
def delete_guest(qr_hash):
    guest = Guest.query.filter_by(qr_hash=qr_hash).first()
    if not guest:
        return jsonify({'error': 'Convidado não encontrado'}), 404
    if guest.qr_image_filename:
        qr_image_path = os.path.join(QR_CODE_SAVE_PATH, guest.qr_image_filename)
        try:
            if os.path.exists(qr_image_path): os.remove(qr_image_path)
        except Exception as e:
            app.logger.error(f"Erro ao remover arquivo QR '{guest.qr_image_filename}': {e}")
    db.session.delete(guest)
    db.session.commit()
    return jsonify({'message': f'Convidado {guest.name} removido com sucesso'}), 200


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
    print("Servidor Flask rodando em http://localhost:5000 (ou http://SEU_IP_LOCAL:5000)")
    print("Use ngrok (https://ngrok.com/) para criar um túnel HTTPS para testes em dispositivos móveis.")