from flask import Flask, request, jsonify
import psycopg2
from psycopg2.extras import RealDictCursor
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
import os

load_dotenv()

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv("DATABASE_URL")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

class Usuario(db.Model):
    __tablename__ = 'sys_usuario'
    usu_co_usuario = db.Column(db.BigInteger, primary_key=True)
    usu_no_nome = db.Column(db.String(200), nullable=False)
    usu_no_email = db.Column(db.String(200), unique=True, nullable=False)
    votos = db.relationship('Voto', backref='votante', lazy=True)

class Enquete(db.Model):
    __tablename__ = 'sys_enquete'
    enq_co_enquete = db.Column(db.BigInteger, primary_key=True)
    enq_no_nome = db.Column(db.String(60), nullable=False)
    enq_in_status = db.Column(db.String(1), nullable=False)
    enq_tx_descricao = db.Column(db.String(2000), nullable=False)
    opcoes = db.relationship('EnqueteOpcao', backref='enquete', lazy=True, cascade="all, delete")

class EnqueteOpcao(db.Model):
    __tablename__ = 'sys_enquete_opcoes'
    enqo_co_opcao = db.Column(db.BigInteger, primary_key=True)
    enq_co_enquete = db.Column(db.BigInteger, db.ForeignKey('sys_enquete.enq_co_enquete'), nullable=False)
    enqo_no_opcao = db.Column(db.String(200), nullable=False)
    votos = db.relationship('Voto', backref='opcao_votada', lazy=True)

class Voto(db.Model):
    __tablename__ = 'sys_enquete_voto'
    enqv_co_voto = db.Column(db.BigInteger, primary_key=True)
    enq_co_enquete = db.Column(db.BigInteger, db.ForeignKey('sys_enquete.enq_co_enquete'), nullable=False)
    enqo_co_opcao = db.Column(db.BigInteger, db.ForeignKey('sys_enquete_opcoes.enqo_co_opcao'), nullable=False)
    usu_co_usuario = db.Column(db.BigInteger, db.ForeignKey('sys_usuario.usu_co_usuario'), nullable=False)


def get_db_connection():
    conn = psycopg2.connect(
        os.getenv("DATABASE_URL")
    )
    return conn

@app.route('/')
def index():
    return "API de Enquetes"

@app.route('/api/enquetes', methods=['POST'])
def criar_enquete():
    data = request.json
    nome = data.get('nome')
    descricao = data.get('descricao')
    opcoes = data.get('opcoes')

    if not nome or not descricao or not opcoes or len(opcoes) < 2:
        return jsonify({'erro': 'Nome, descrição e pelo menos 2 opções para enquete são obrigatórios!'}), 400

    sql_enquete = """
        INSERT INTO sys_enquete (enq_no_nome, enq_in_status, enq_tx_descricao) 
        VALUES (%s, 'A', %s) RETURNING enq_co_enquete;
    """
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(sql_enquete, (nome, descricao))
    enquete_id = cursor.fetchone()[0]

    for opcao in opcoes:
        sql_opcao = """
            INSERT INTO sys_enquete_opcoes (enq_co_enquete, enqo_no_opcao)
            VALUES (%s, %s);
        """
        cursor.execute(sql_opcao, (enquete_id, opcao))

    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({'enquete_id': enquete_id }), 201

@app.route('/api/enquetes', methods=['GET'])
def listar_enquetes():
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT enq_no_nome FROM sys_enquete WHERE enq_in_status = 'A';")
    enquetes = cursor.fetchall()
    cursor.close()
    conn.close()

    if not enquetes:
        return jsonify({'mensagem': 'Não existe enquetes ativas.'}), 404

    return jsonify(enquetes), 200

@app.route('/api/enquetes/<int:id>', methods=['GET'])
def obter_detalhes_enquete(id):
    if id <= 0:
        return jsonify({'erro': 'O ID deve ser um número positivo.'}), 400

    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    cursor.execute("""
        SELECT 
            enq.enq_co_enquete, 
            enq.enq_no_nome, 
            enq.enq_in_status, 
            enq.enq_tx_descricao,
        json_agg(json_build_array(enqo.enqo_co_opcao, enqo.enqo_no_opcao)) AS opcoes
        FROM sys_enquete enq
        LEFT JOIN sys_enquete_opcoes enqo ON enq.enq_co_enquete = enqo.enq_co_enquete
        WHERE enq.enq_co_enquete = %s
        GROUP BY enq.enq_co_enquete;

    """, (id,))
    enquete = cursor.fetchone()

    cursor.close()
    conn.close()

    if enquete is None:
        return jsonify({'mensagem': 'Enquete não encontrada.'}), 404

    return jsonify(enquete), 200


@app.route('/api/enquetes/<int:enquete_id>/votar', methods=['POST'])
def votar(enquete_id):
    data = request.json
    user_id = data.get('user_id')
    opcao_id = data.get('opcao_id')

    if not user_id or not opcao_id or not enquete_id:
        return jsonify({'erro': 'Identificação do usuário e da opção de voto são obrigatórios para o registro!.'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO sys_enquete_voto (enq_co_enquete, enqo_co_opcao, usu_co_usuario)
        VALUES (%s, %s, %s)
        ON CONFLICT (enq_co_enquete, usu_co_usuario) DO UPDATE
        SET enqo_co_opcao = EXCLUDED.enqo_co_opcao;
    """, (enquete_id, opcao_id, user_id))
    conn.commit()

    cursor.close()
    conn.close()

    return jsonify({'mensagem': 'Voto registrado com sucesso!'}), 200


@app.route('/api/enquetes/<int:id>/resultados', methods=['GET'])
def resultados_enquete(id):
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    if not enquete_existe(id):
        return jsonify({'erro': 'Enquete não encontrada.'}), 404


    cursor.execute("""
        SELECT o.enqo_no_opcao, COUNT(v.enqo_co_opcao) as num_votos
        FROM sys_enquete_opcoes o
        LEFT JOIN sys_enquete_voto v ON o.enqo_co_opcao = v.enqo_co_opcao
        WHERE o.enq_co_enquete = %s
        GROUP BY o.enqo_co_opcao
        ORDER BY o.enqo_co_opcao;
    """, (id,))

    resultados = cursor.fetchall()
    cursor.close()
    conn.close()

    if not resultados:
        return jsonify({'mensagem': 'Não há votos registrados para esta enquete ainda.'}), 200

    return jsonify({'enquete_id': id, 'resultados': resultados}), 200


@app.route('/api/enquetes/<int:id>/opcoes', methods=['GET'])
def visualizar_opcoes_enquete(id):
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    if not enquete_existe(id):
        return jsonify({'erro': 'Enquete não encontrada.'}), 404


    cursor.execute("""
        SELECT enqo_co_opcao, enqo_no_opcao
        FROM sys_enquete_opcoes
        WHERE enq_co_enquete = %s
        ORDER BY enqo_co_opcao;
    """, (id,))

    opcoes = cursor.fetchall()
    cursor.close()
    conn.close()

    return jsonify({'enquete_id': id, 'opcoes': opcoes}), 200


@app.route('/api/enquetes/<int:id>/opcoes', methods=['POST'])
def adicionar_opcao_enquete(id):
    if not enquete_existe(id):
        return jsonify({'erro': 'Enquete não encontrada.'}), 404

    data = request.json
    nova_opcao = data.get('opcao')

    if not nova_opcao:
        return jsonify({'erro': 'A nova opção é obrigatória.'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO sys_enquete_opcoes (enq_co_enquete, enqo_no_opcao)
        VALUES (%s, %s) RETURNING enqo_co_opcao;
    """, (id, nova_opcao))

    enqo_co_opcao = cursor.fetchone()[0]
    conn.commit()
    cursor.close()
    conn.close()

    return jsonify({'mensagem': 'Opção adicionada com sucesso!', 'enqo_co_opcao': enqo_co_opcao}), 201



@app.route('/api/enquetes/<int:id>', methods=['DELETE'])
def deletar_enquete(id):
    if not enquete_existe(id):
        return jsonify({'erro': 'Enquete não encontrada.'}), 404

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM sys_enquete_voto WHERE enq_co_enquete = %s;", (id,))
    
    cursor.execute("DELETE FROM sys_enquete_opcoes WHERE enq_co_enquete = %s;", (id,))
    
    cursor.execute("DELETE FROM sys_enquete WHERE enq_co_enquete = %s;", (id,))
    
    conn.commit()
    cursor.close()
    conn.close()

    return jsonify({'mensagem': 'Enquete deletada com sucesso.'}), 200


@app.route('/api/enquetes/<int:id_enquete>/opcoes/<int:id_opcao>', methods=['DELETE'])
def deletar_opcao_enquete(id_enquete, id_opcao):
    if not enquete_existe(id_enquete):
        return jsonify({'erro': 'Enquete não encontrada.'}), 404

    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    cursor.execute("""
        SELECT COUNT(*) as total
        FROM sys_enquete_opcoes
        WHERE enq_co_enquete = %s;
    """, (id_enquete,))
    total_opcoes = cursor.fetchone()['total']

    if total_opcoes < 3:
        cursor.close()
        conn.close()
        return jsonify({'erro': 'Não é possível deletar a opção. A enquete deve ter ao menos duas opções após a exclusão.'}), 400

    cursor.execute("""
        DELETE FROM sys_enquete_opcoes
        WHERE enq_co_enquete = %s AND enqo_co_opcao = %s;
    """, (id_enquete, id_opcao))

    conn.commit()
    cursor.close()
    conn.close()

    return jsonify({'mensagem': 'Opção deletada com sucesso.'}), 200

def enquete_existe(enquete_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM sys_enquete WHERE enq_co_enquete = %s;", (enquete_id,))
    existe = cursor.fetchone() is not None
    cursor.close()
    conn.close()
    return existe



if __name__ == '__main__':
    app.run(debug=True)