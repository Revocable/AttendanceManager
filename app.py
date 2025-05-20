import os
import hashlib
import qrcode
from PIL import Image, ImageDraw, ImageFont as PILImageFont
import uuid
from flask import Flask, request, jsonify, render_template, url_for, Response
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import pytz
import io
import csv
from fpdf import FPDF, XPos, YPos

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# --- Configuração do App ---
app = Flask(__name__)
basedir = os.path.abspath(os.path.dirname(__file__))

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'instance', 'party.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

QR_CODE_FOLDER_NAME = 'qr_codes'
QR_CODE_STATIC_PATH = os.path.join('static', QR_CODE_FOLDER_NAME)
QR_CODE_SAVE_PATH = os.path.join(basedir, QR_CODE_STATIC_PATH)
FONT_PATH = os.path.join(basedir, "Montserrat-Regular.ttf")

if not os.path.exists(QR_CODE_SAVE_PATH):
    os.makedirs(QR_CODE_SAVE_PATH)
    app.logger.info(f"Pasta QR Codes criada em: {QR_CODE_SAVE_PATH}")

if not os.path.exists(FONT_PATH):
    app.logger.warning(f"ARQUIVO DE FONTE Montserrat-Regular.ttf NÃO ENCONTRADO EM: {FONT_PATH}")

BRASILIA_TZ = pytz.timezone('America/Sao_Paulo')

# --- Modelo do Banco de Dados ---
class Guest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    qr_hash = db.Column(db.String(64), unique=True, nullable=False)
    entered = db.Column(db.Boolean, default=False, nullable=False)
    qr_image_filename = db.Column(db.String(255), nullable=True)
    check_in_time = db.Column(db.DateTime, nullable=True)

    def __repr__(self): return f'<Guest {self.name}>'
    @property
    def qr_image_url(self):
        return url_for('static', filename=f'{QR_CODE_FOLDER_NAME}/{self.qr_image_filename}') if self.qr_image_filename else None

    def get_check_in_time_str(self):
        if self.check_in_time:
            if self.check_in_time.tzinfo is None:
                 return self.check_in_time.strftime('%d/%m/%Y %H:%M:%S')
            return self.check_in_time.astimezone(BRASILIA_TZ).strftime('%d/%m/%Y %H:%M:%S')
        return "N/A"

instance_path = os.path.join(basedir, 'instance')
if not os.path.exists(instance_path):
    os.makedirs(instance_path)

with app.app_context():
    db.create_all()

# --- ROTAS DA APLICAÇÃO ---
@app.route('/')
def index(): return render_template('index.html')

@app.route('/scanner')
def scanner_page():
    return render_template('scanner.html')

def get_party_stats_data():
    total_invited = Guest.query.count()
    entered_count = Guest.query.filter_by(entered=True).count()
    not_entered_count = total_invited - entered_count
    percentage_entered = 0.0
    if total_invited > 0:
        percentage_entered = round((entered_count / total_invited) * 100, 2)
    return {
        'total_invited': total_invited, 'entered_count': entered_count,
        'not_entered_count': not_entered_count, 'percentage_entered': percentage_entered
    }

@app.route('/api/stats', methods=['GET'])
def get_stats():
    stats = get_party_stats_data()
    return jsonify(stats)

@app.route('/api/guests', methods=['POST'])
def add_guest():
    data = request.get_json()
    if not data or 'name' not in data: return jsonify({'error': 'Nome obrigatório'}), 400
    name = data['name'].strip()
    if not name: return jsonify({'error': 'Nome vazio'}), 400
    if Guest.query.filter_by(name=name).first(): return jsonify({'error': f'Convidado com nome "{name}" já existe.'}), 409

    unique_id_for_qr = str(uuid.uuid4())
    qr_hash = hashlib.sha256(unique_id_for_qr.encode('utf-8')).hexdigest()

    while Guest.query.filter_by(qr_hash=qr_hash).first():
        app.logger.warning(f"Colisão de QR Hash detectada (extremamente raro!). Gerando novo para {name}.")
        unique_id_for_qr = str(uuid.uuid4())
        qr_hash = hashlib.sha256(unique_id_for_qr.encode('utf-8')).hexdigest()

    qr_fn = f"{qr_hash}.png"
    qr_fp = os.path.join(QR_CODE_SAVE_PATH, qr_fn)

    try:
        qr_instance = qrcode.QRCode(version=1,error_correction=qrcode.constants.ERROR_CORRECT_L,box_size=10,border=4)
        qr_instance.add_data(qr_hash); qr_instance.make(fit=True)
        img_qr = qr_instance.make_image(fill_color="black", back_color="white").convert('RGB')

        padding_bottom_for_text = 60; text_color = (0, 0, 0); background_color_canvas = (255, 255, 255)
        font_size_pil = 30
        
        pil_font = PILImageFont.load_default()
        if os.path.exists(FONT_PATH):
            try:
                pil_font = PILImageFont.truetype(FONT_PATH, font_size_pil)
            except IOError:
                app.logger.warning(f"Pillow: Fonte '{FONT_PATH}' não pôde ser carregada, usando fonte padrão.")
        else:
             app.logger.warning(f"Pillow: Fonte '{FONT_PATH}' não encontrada, usando fonte padrão.")

        new_width = img_qr.width; new_height = img_qr.height + padding_bottom_for_text
        img_canvas = Image.new('RGB', (new_width, new_height), background_color_canvas)
        img_canvas.paste(img_qr, (0, 0))
        draw = ImageDraw.Draw(img_canvas)

        try: text_bbox = draw.textbbox((0,0), name, font=pil_font); text_width = text_bbox[2] - text_bbox[0]
        except AttributeError: text_width, _ = draw.textsize(name, font=pil_font)

        text_x = (new_width - text_width) / 2
        text_y = img_qr.height + (padding_bottom_for_text - font_size_pil) / 2 - 5
        draw.text((text_x, text_y), name, font=pil_font, fill=text_color)
        img_canvas.save(qr_fp)
    except Exception as e:
        app.logger.error(f"Erro ao gerar/salvar QR com texto para '{name}': {e}")
        try: qrcode.make(qr_hash).save(qr_fp)
        except Exception as e_fallback: app.logger.error(f"Erro crítico ao salvar QR para {name}: {e_fallback}"); return jsonify({'error': 'Falha crítica ao gerar QR'}), 500

    new_guest = Guest(name=name, qr_hash=qr_hash, qr_image_filename=qr_fn)
    db.session.add(new_guest); db.session.commit()
    return jsonify({'id': new_guest.id, 'name': new_guest.name, 'qr_hash': new_guest.qr_hash,
                    'entered': new_guest.entered, 'qr_image_url': new_guest.qr_image_url,
                    'check_in_time': new_guest.get_check_in_time_str() }), 201

@app.route('/api/guests', methods=['GET'])
def get_guests_api():
    search_term = request.args.get('search', None)
    query = Guest.query

    if search_term and search_term.strip():
        query = query.filter(Guest.name.ilike(f'%{search_term.strip()}%'))

    guests_list = query.order_by(Guest.name).all()

    return jsonify([{'id': g.id, 'name': g.name, 'qr_hash': g.qr_hash,
                     'entered': g.entered, 'qr_image_url': g.qr_image_url,
                     'check_in_time': g.get_check_in_time_str()}
                    for g in guests_list])

@app.route('/api/guests/<qr_hash>/enter', methods=['POST'])
def mark_entered(qr_hash):
    guest = Guest.query.filter_by(qr_hash=qr_hash).first()
    is_new_entry = False; message = ""
    if not guest: return jsonify({'error': 'Convidado não encontrado (QR inválido)'}), 404

    current_time_brasilia = datetime.now(BRASILIA_TZ)

    if guest.entered:
        message = f'{guest.name} já entrou no evento às {guest.get_check_in_time_str()}.'
    else:
        guest.entered = True
        guest.check_in_time = current_time_brasilia
        db.session.commit()
        is_new_entry = True
        message = f'{guest.name} marcou presença às {guest.get_check_in_time_str()}!'
    return jsonify({'id': guest.id, 'name': guest.name, 'qr_hash': guest.qr_hash,
                    'entered': guest.entered, 'message': message, 'is_new_entry': is_new_entry,
                    'check_in_time': guest.get_check_in_time_str()})

@app.route('/api/guests/<qr_hash>/toggle_entry', methods=['PUT'])
def toggle_entry_manually(qr_hash):
    guest = Guest.query.filter_by(qr_hash=qr_hash).first()
    if not guest: return jsonify({'error': 'Convidado não encontrado'}), 404

    current_time_brasilia = datetime.now(BRASILIA_TZ)
    guest.entered = not guest.entered

    if guest.entered:
        guest.check_in_time = current_time_brasilia
        action = f"entrou às {guest.get_check_in_time_str()}"
    else:
        guest.check_in_time = None
        action = "NÃO entrou"

    db.session.commit()
    return jsonify({'id': guest.id, 'name': guest.name, 'qr_hash': guest.qr_hash,
                    'entered': guest.entered, 'message': f'Status de {guest.name} alterado: {action}.',
                    'check_in_time': guest.get_check_in_time_str()})

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

def get_all_guests_for_export():
    search_term = request.args.get('search', None)
    query = Guest.query
    if search_term and search_term.strip():
        query = query.filter(Guest.name.ilike(f'%{search_term.strip()}%'))
    return query.order_by(Guest.name).all()

@app.route('/api/guests/export/csv')
def export_guests_csv():
    guests_data = get_all_guests_for_export()
    si = io.StringIO()
    cw = csv.writer(si)
    cw.writerow(['Nome', 'Status Entrada', 'Data Check-in'])
    for guest_obj in guests_data:
        cw.writerow([
            guest_obj.name,
            'Sim' if guest_obj.entered else 'Não',
            guest_obj.get_check_in_time_str()
        ])
    output = si.getvalue()
    return Response(
        output,
        mimetype="text/csv",
        headers={"Content-disposition":"attachment; filename=lista_convidados.csv"}
    )

class PDF(FPDF):
    def __init__(self, orientation='P', unit='mm', format='A4'):
        super().__init__(orientation, unit, format)
        self.montserrat_font_path = FONT_PATH
        self.font_name = 'Montserrat'
        self.default_font = 'Helvetica'
        self.current_font_family = self.default_font

        if os.path.exists(self.montserrat_font_path):
            try:
                self.add_font(self.font_name, '', self.montserrat_font_path, uni=True)
                self.add_font(self.font_name, 'B', self.montserrat_font_path, uni=True)
                self.add_font(self.font_name, 'I', self.montserrat_font_path, uni=True)
                app.logger.info(f"Fonte Montserrat carregada em FPDF: {self.montserrat_font_path}")
                self.current_font_family = self.font_name
            except Exception as e:
                app.logger.error(f"FPDF: Erro ao carregar fonte Montserrat: {e}. Usando Helvetica.")
        else:
            app.logger.warning(f"FPDF: Arquivo de fonte Montserrat não encontrado em {self.montserrat_font_path}. Usando Helvetica.")

    def header(self):
        self.set_font(self.current_font_family, 'B', 16)
        title = 'Relatório do evento'
        title_w = self.get_string_width(title)
        self.set_x((self.w - title_w) / 2)
        self.cell(title_w, 10, title, border=0, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font(self.current_font_family, 'I', 8)
        self.cell(0, 10, f'Página {self.page_no()}/{{nb}}', border=0, new_x=XPos.RIGHT, new_y=YPos.TOP, align='C')

    def draw_stats_summary(self, stats_data):
        # Título da seção de estatísticas
        self.set_font(self.current_font_family, 'B', 11)
        title_stat_x = self.l_margin
        self.set_x(title_stat_x)
        self.cell(0, 10, "Estatísticas do evento", border=0, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='L')
        self.ln(1) 

        # Configurações para os boxes
        page_width = self.w - self.l_margin - self.r_margin
        col_width_stat = page_width / 4
        stat_box_height = 12 # Aumentar um pouco para melhor espaçamento vertical
        line_height_label = 4.5 # Altura para o rótulo
        line_height_value = 5.5 # Altura para o valor (pode ser maior se a fonte for maior)
        padding_top_box = (stat_box_height - (line_height_label + line_height_value)) / 2 # Padding superior para centralizar o bloco de texto

        fill_color_stat_box = (240, 240, 240)
        value_text_color = (0, 100, 200) 
        label_text_color = (0, 0, 0)

        current_x = self.l_margin
        base_y = self.get_y() # Y inicial para a linha de boxes

        stats_items = [
            ("Total de Convidados:", str(stats_data['total_invited'])),
            ("Entraram no evento:", str(stats_data['entered_count'])),
            ("Ainda Não Entraram:", str(stats_data['not_entered_count'])),
            ("Comparecimento:", f"{stats_data['percentage_entered']:.2f}%")
        ]

        for i, (label, value) in enumerate(stats_items):
            # Desenha a caixa de fundo
            self.set_fill_color(*fill_color_stat_box)
            self.rect(current_x, base_y, col_width_stat, stat_box_height, 'F') # 'F' para preencher apenas

            # Desenha a borda da caixa (opcional, mas o frontend tem)
            self.set_draw_color(200, 200, 200) # Cor cinza para a borda
            self.rect(current_x, base_y, col_width_stat, stat_box_height, 'D') # 'D' para desenhar borda

            # Posição Y para o primeiro texto (rótulo)
            y_pos_label = base_y + padding_top_box

            # Escreve o Rótulo (preto)
            self.set_xy(current_x, y_pos_label) # Define X e Y explicitamente
            self.set_text_color(*label_text_color)
            self.set_font(self.current_font_family, '', 8.5) # Tamanho para rótulo
            self.cell(col_width_stat, line_height_label, label, border=0, align='C')

            # Posição Y para o segundo texto (valor), abaixo do rótulo
            y_pos_value = y_pos_label + line_height_label

            # Escreve o Valor (azul)
            self.set_xy(current_x, y_pos_value) # Define X e Y explicitamente
            self.set_text_color(*value_text_color)
            self.set_font(self.current_font_family, 'B', 10) # Valor em negrito e um pouco maior
            self.cell(col_width_stat, line_height_value, value, border=0, align='C')
            
            # Reseta cor e fonte para o próximo ciclo (se necessário, mas aqui já está sendo setado no início do loop para o rótulo)
            self.set_text_color(*label_text_color) 

            current_x += col_width_stat
        
        self.set_y(base_y + stat_box_height) # Move o cursor para baixo da linha de estatísticas
        self.ln(5)

    def draw_pie_chart(self, stats_data, y_offset, chart_size_mm=70):
        labels = 'Entraram', 'Não Entraram'
        sizes = [stats_data['entered_count'], stats_data['not_entered_count']]
        colors = ['#4BC0C0', '#FF6384']
        
        if sum(sizes) == 0:
            current_y = self.get_y()
            self.set_xy((self.w - chart_size_mm) / 2, current_y + y_offset)
            self.set_font(self.current_font_family, '', 10)
            self.cell(chart_size_mm, 10, "Sem dados para o gráfico.", align='C', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.ln(5)
            return

        explode = (0,0)
        if stats_data['entered_count'] > 0 and stats_data['not_entered_count'] > 0 :
            if sizes[0] > sizes[1]: explode = (0.05, 0)
            elif sizes[1] > sizes[0]: explode = (0, 0.05)

        fig, ax = plt.subplots(figsize=(chart_size_mm/25.4, chart_size_mm/25.4), dpi=100)
        
        font_to_use_mpl = 'Montserrat' if self.current_font_family == 'Montserrat' and os.path.exists(FONT_PATH) else 'sans-serif'
        plt.rcParams['font.family'] = font_to_use_mpl

        wedges, texts, autotexts = ax.pie(
            sizes, explode=explode, labels=None, colors=colors,
            autopct='%1.1f%%', shadow=False, startangle=90,
            pctdistance=0.80, wedgeprops={'linewidth': 0.5, 'edgecolor': 'white'}
        )
        for autotext in autotexts:
            autotext.set_color('white'); autotext.set_fontsize(8); autotext.set_fontweight('bold')

        ax.axis('equal')
        
        legend_labels = [f'{label} ({size})' for label, size in zip(labels, sizes)]
        ax.legend(wedges, legend_labels, title="Distribuição de Comparecimento", 
                  loc="upper center", bbox_to_anchor=(0.5, 1.12), ncol=2, fontsize=7, title_fontsize=8)

        img_buffer = io.BytesIO()
        plt.savefig(img_buffer, format='png', bbox_inches='tight', transparent=True)
        img_buffer.seek(0)
        
        img_x = (self.w - chart_size_mm) / 2
        current_y = self.get_y()
        self.image(img_buffer, x=img_x, y=current_y + y_offset, w=chart_size_mm, h=chart_size_mm, type='PNG')
        plt.close(fig)
        self.set_y(current_y + y_offset + chart_size_mm + 5)

    def chapter_body(self, guests_data_table):
        header_bg_color = (230, 230, 230)
        row_bg_color_even = (255, 255, 255)
        row_bg_color_odd = (248, 248, 248)

        self.set_font(self.current_font_family, 'B', 11)
        self.cell(0, 10, "Lista de Convidados", border=0, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
        self.ln(1)

        self.set_font(self.current_font_family, 'B', 9)
        self.set_fill_color(*header_bg_color)
        
        col_widths = { "name": 100, "status": 30, "check_in": 40 }
        page_content_width = self.w - 2 * self.l_margin
        table_width = sum(col_widths.values())
        
        start_x = self.l_margin
        if table_width < page_content_width:
            start_x = self.l_margin + (page_content_width - table_width) / 2

        self.set_x(start_x)
        self.cell(col_widths["name"], 8, 'Nome', border=1, new_x=XPos.RIGHT, new_y=YPos.TOP, align='C', fill=True)
        self.cell(col_widths["status"], 8, 'Entrou?', border=1, new_x=XPos.RIGHT, new_y=YPos.TOP, align='C', fill=True)
        self.cell(col_widths["check_in"], 8, 'Data Check-in', border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C', fill=True)
        
        self.set_font(self.current_font_family, '', 8.5)
        for i, guest_obj in enumerate(guests_data_table):
            self.set_x(start_x)
            current_fill_color = row_bg_color_odd if i % 2 else row_bg_color_even
            self.set_fill_color(*current_fill_color)

            guest_name_display = guest_obj.name
            max_name_width = col_widths["name"] - 4
            current_name_width = self.get_string_width(guest_name_display)
            if current_name_width > max_name_width:
                while self.get_string_width(guest_name_display + "...") > max_name_width and len(guest_name_display) > 3 :
                    guest_name_display = guest_name_display[:-1]
                if len(guest_name_display) < len(guest_obj.name):
                    guest_name_display = guest_name_display + "..." if len(guest_name_display) > 0 else "..."
            
            self.cell(col_widths["name"], 7, guest_name_display, border=1, new_x=XPos.RIGHT, new_y=YPos.TOP, align='L', fill=True)
            self.cell(col_widths["status"], 7, 'Sim' if guest_obj.entered else 'Não', border=1, new_x=XPos.RIGHT, new_y=YPos.TOP, align='C', fill=True)
            self.cell(col_widths["check_in"], 7, guest_obj.get_check_in_time_str(), border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C', fill=True)
        self.ln()

@app.route('/api/guests/export/pdf')
def export_guests_pdf():
    guests_for_table = get_all_guests_for_export()
    stats_for_chart_and_summary = get_party_stats_data()
    
    pdf = PDF(orientation='P', unit='mm', format='A4')
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.alias_nb_pages()
    pdf.add_page()
    
    pdf.draw_stats_summary(stats_for_chart_and_summary)
    pdf.draw_pie_chart(stats_for_chart_and_summary, y_offset=0, chart_size_mm=70)
    
    if not guests_for_table and stats_for_chart_and_summary['total_invited'] == 0:
        pdf.set_font(pdf.current_font_family, '', 12)
        pdf.cell(0, 10, 'Nenhum dado para exibir.', border=0, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
    elif guests_for_table:
        pdf.chapter_body(guests_for_table)
        
    timestamp = datetime.now(BRASILIA_TZ).strftime("%Y%m%d_%H%M%S")
    filename = f"relatorio_evento_{timestamp}.pdf"

    pdf_output_bytearray = pdf.output() 
    pdf_output_bytes = bytes(pdf_output_bytearray)

    return Response(pdf_output_bytes,
                    mimetype='application/pdf',
                    headers={'Content-Disposition': f'attachment;filename={filename}'})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
    print("Servidor Flask rodando em http://localhost:5000 (ou http://SEU_IP_LOCAL:5000)")
    print("Use ngrok (https://ngrok.com/) para criar um túnel HTTPS para testes em dispositivos móveis.")