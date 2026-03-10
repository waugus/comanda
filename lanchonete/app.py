import os
import json
import time
from flask import Flask, render_template, request, redirect, url_for, session, g, jsonify, Response, stream_with_context
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime
from functools import wraps
from database import (
    get_db_connection, close_connection, migrar_db_imagem,
    migrar_db_destaque_produto,
    migrar_db_status_comanda, migrar_db_imagem_categoria, migrar_db_pagamentos,
    migrar_db_personalizacoes, migrar_db_pedidos_online, migrar_db_bairros_entrega,
    migrar_db_itens_comanda_texto, criar_tabelas,
    criar_usuario_padrao, criar_garcom_padrao, criar_motoboy_padrao,
    criar_categorias_padrao
)


app = Flask(__name__)
app.secret_key = "segredo_comanda"
app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'static', 'uploads')
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
app.config['TAXA_ENTREGA'] = 5.00
app.config['TEMPO_ENTREGA'] = "35-50 min"
app.config['TEMPO_RETIRADA'] = "15-25 min"
db_inicializado = False


def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']


def inicializar_sistema():
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    migrar_db_imagem()
    migrar_db_destaque_produto()
    migrar_db_imagem_categoria()
    migrar_db_status_comanda()
    migrar_db_pagamentos()
    migrar_db_personalizacoes()
    migrar_db_pedidos_online()
    migrar_db_bairros_entrega()
    migrar_db_itens_comanda_texto()
    criar_tabelas()
    criar_usuario_padrao()
    criar_garcom_padrao()
    criar_motoboy_padrao()
    criar_categorias_padrao()

@app.teardown_appcontext
def teardown_db_connection(exception):
    close_connection(exception)


@app.before_request
def ensure_db_inicializado():
    global db_inicializado
    if not db_inicializado:
        inicializar_sistema()
        db_inicializado = True


# ===============================
# LOGIN REQUIRED
# ===============================


def login_required_decorator(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("logado"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function

def gerente_required_decorator(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("logado"):
            return redirect(url_for("login"))
        if session.get("tipo") != "gerente":
            return redirect(url_for("index")) # Redireciona para a página inicial se não for gerente
        return f(*args, **kwargs)
    return decorated_function

def motoboy_required_decorator(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("logado"):
            return redirect(url_for("login"))
        if session.get("tipo") != "motoboy":
            return redirect(url_for("index"))
        return f(*args, **kwargs)
    return decorated_function


# ===============================
# CARRINHO PEDIDO ONLINE
# ===============================
def get_cart():
    cart = session.get("cart", [])
    if not isinstance(cart, list):
        cart = []
    return cart


def save_cart(cart):
    session["cart"] = cart


def calcular_total_cart(cart):
    return sum((item["preco"] * item["qtd"]) for item in cart)


def enriquecer_cart_com_destaque(cart):
    if not cart:
        return []

    produto_ids = sorted({item.get("produto_id") for item in cart if item.get("produto_id")})
    if not produto_ids:
        return [dict(item) for item in cart]

    con = get_db_connection()
    cur = con.cursor()
    placeholders = ",".join(["?"] * len(produto_ids))
    cur.execute(
        f"SELECT id, destaque FROM produtos WHERE id IN ({placeholders})",
        tuple(produto_ids)
    )
    destaques = {row["id"]: bool(row["destaque"]) for row in cur.fetchall()}

    cart_enriquecido = []
    for item in cart:
        novo_item = dict(item)
        novo_item["destaque_atual"] = bool(destaques.get(item.get("produto_id"), False))
        cart_enriquecido.append(novo_item)

    return cart_enriquecido


def carregar_bairros_entrega(ativos=True):
    con = get_db_connection()
    cur = con.cursor()
    if ativos:
        cur.execute("SELECT * FROM bairros_entrega WHERE ativo = 1 ORDER BY nome")
    else:
        cur.execute("SELECT * FROM bairros_entrega ORDER BY nome")
    return cur.fetchall()

def finalizar_pedido_publico(cart_redirect, template_carrinho, template_sucesso):
    cart = get_cart()
    if not cart:
        return redirect(cart_redirect)
    cart_enriquecido = enriquecer_cart_com_destaque(cart)

    nome = (request.form.get("nome") or "").strip()
    telefone = (request.form.get("telefone") or "").strip()
    tipo = (request.form.get("tipo") or "").strip()
    endereco = ""
    bairro_id = (request.form.get("bairro_id") or "").strip()
    rua = (request.form.get("rua") or "").strip()
    numero = (request.form.get("numero") or "").strip()
    complemento = (request.form.get("complemento") or "").strip()

    taxa_entrega = 0.0
    bairro_nome = ""
    tempo_entrega = app.config.get("TEMPO_ENTREGA")
    tempo_retirada = app.config.get("TEMPO_RETIRADA")
    maps_url = ""

    if not nome or not telefone or not tipo:
        total = calcular_total_cart(cart)
        cart_count = sum(item["qtd"] for item in cart)
        return render_template(
            template_carrinho,
            cart=cart_enriquecido,
            total=total,
            cart_count=cart_count,
            taxa_entrega=app.config.get("TAXA_ENTREGA"),
            tempo_entrega=app.config.get("TEMPO_ENTREGA"),
            tempo_retirada=app.config.get("TEMPO_RETIRADA"),
            bairros=carregar_bairros_entrega(),
            erro="Preencha nome, telefone e tipo do pedido."
        )

    if tipo == "Entrega" and (not rua or not numero):
        total = calcular_total_cart(cart)
        cart_count = sum(item["qtd"] for item in cart)
        return render_template(
            template_carrinho,
            cart=cart_enriquecido,
            total=total,
            cart_count=cart_count,
            taxa_entrega=app.config.get("TAXA_ENTREGA"),
            tempo_entrega=app.config.get("TEMPO_ENTREGA"),
            tempo_retirada=app.config.get("TEMPO_RETIRADA"),
            bairros=carregar_bairros_entrega(),
            erro="Informe rua e numero para entrega."
        )

    if tipo == "Entrega":
        if not bairro_id:
            total = calcular_total_cart(cart)
            cart_count = sum(item["qtd"] for item in cart)
            return render_template(
                template_carrinho,
                cart=cart_enriquecido,
                total=total,
                cart_count=cart_count,
                taxa_entrega=app.config.get("TAXA_ENTREGA"),
                tempo_entrega=app.config.get("TEMPO_ENTREGA"),
                tempo_retirada=app.config.get("TEMPO_RETIRADA"),
                bairros=carregar_bairros_entrega(),
                erro="Selecione o bairro para entrega."
            )

        con = get_db_connection()
        cur = con.cursor()
        cur.execute(
            "SELECT * FROM bairros_entrega WHERE id = ? AND ativo = 1",
            (bairro_id,)
        )
        bairro = cur.fetchone()
        if not bairro:
            total = calcular_total_cart(cart)
            cart_count = sum(item["qtd"] for item in cart)
            return render_template(
                template_carrinho,
                cart=cart_enriquecido,
                total=total,
                cart_count=cart_count,
                taxa_entrega=app.config.get("TAXA_ENTREGA"),
                tempo_entrega=app.config.get("TEMPO_ENTREGA"),
                tempo_retirada=app.config.get("TEMPO_RETIRADA"),
                bairros=carregar_bairros_entrega(),
                erro="Bairro invalido para entrega."
            )

        taxa_entrega = float(bairro["taxa"] or 0.0)
        bairro_nome = bairro["nome"]
        tempo_entrega = bairro["tempo_entrega"] or tempo_entrega
        tempo_retirada = bairro["tempo_retirada"] or tempo_retirada
        if rua or numero:
            endereco = f"{rua} {numero}".strip()
        if complemento and endereco:
            endereco = f"{endereco}, {complemento}"
        if endereco and bairro_nome:
            endereco = f"{endereco} - {bairro_nome}"
        elif bairro_nome:
            endereco = bairro_nome

    con = get_db_connection()
    cur = con.cursor()
    data = datetime.now().strftime("%Y-%m-%d")
    cur.execute(
        "INSERT INTO comandas (cliente, cpf, status, data) VALUES (?, ?, 'Aberta', ?)",
        (nome, telefone, data)
    )
    comanda_id = cur.lastrowid

    for item in cart:
        produto_id = item["produto_id"]
        preco = item["preco"]
        qtd = item["qtd"]
        removidos = item.get("removidos", [])
        observacao = (item.get("observacao") or "").strip()
        acrescimos_texto = (item.get("acrescimos_texto") or "").strip()
        tem_personalizacao = bool(removidos or observacao or acrescimos_texto)
        total_itens = qtd if tem_personalizacao else 1
        qtd_por_item = 1 if tem_personalizacao else qtd

        for _ in range(total_itens):
            cur.execute("""
                INSERT INTO itens_comanda (comanda_id, produto_id, qtd, preco, acrescimos, observacoes)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (comanda_id, produto_id, qtd_por_item, preco, acrescimos_texto, observacao))
            item_comanda_id = cur.lastrowid

            for ingrediente in removidos:
                cur.execute(
                    "INSERT INTO item_personalizacoes (item_comanda_id, tipo, texto) VALUES (?, ?, ?)",
                    (item_comanda_id, "remover", f"Sem {ingrediente}")
                )

            if observacao:
                cur.execute(
                    "INSERT INTO item_personalizacoes (item_comanda_id, tipo, texto) VALUES (?, ?, ?)",
                    (item_comanda_id, "obs", f"Obs: {observacao}")
                )

    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cur.execute("""
        INSERT INTO pedidos_online (
            comanda_id, nome, telefone, tipo, endereco, bairro,
            taxa_entrega, tempo_entrega, tempo_retirada, maps_url,
            status, criado_em, atualizado_em
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Recebido', ?, ?)
    """, (
        comanda_id, nome, telefone, tipo, endereco, bairro_nome,
        taxa_entrega, tempo_entrega, tempo_retirada, maps_url,
        agora, agora
    ))
    pedido_id = cur.lastrowid
    con.commit()

    session.pop("cart", None)
    return render_template(
        template_sucesso,
        pedido_id=pedido_id
    )


# ===============================
# CÁLCULO TOTAL COMANDA
# ===============================
def calcular_total_comanda(comanda_id):
    con = get_db_connection()
    cur = con.cursor()

    cur.execute("""
        SELECT SUM(i.qtd * i.preco) 
        FROM itens_comanda i 
        WHERE i.comanda_id = ?
    """, (comanda_id,))
    subtotal_produtos = cur.fetchone()[0] or 0.0

    cur.execute("""
        SELECT SUM(a.preco)
        FROM item_acrescimos ia
        JOIN acrescimos a ON a.id = ia.acrescimo_id
        JOIN itens_comanda i ON i.id = ia.item_comanda_id
        WHERE i.comanda_id = ?
          AND i.acrescimos IS NULL
    """, (comanda_id,))
    subtotal_acrescimos = cur.fetchone()[0] or 0.0

    total = subtotal_produtos + subtotal_acrescimos
    return subtotal_produtos, total


# ===============================
# LOGIN
# ===============================


@app.route("/login")
def login():
    return render_template("login.html")


@app.route("/entrar", methods=["POST"])
def entrar():
    usuario = request.form.get("usuario")
    senha = request.form.get("senha")

    con = get_db_connection()
    cur = con.cursor()

    cur.execute("SELECT * FROM usuarios WHERE usuario = ?", (usuario,))
    user = cur.fetchone()

    if user and check_password_hash(user["senha"], senha):
        session.clear()
        session["logado"] = True
        session["usuario"] = user["usuario"]
        session["tipo"] = user["tipo"]  # 👈 ESSENCIAL
        return redirect(url_for("index"))

    return render_template("login.html", erro="Usuário ou senha inválidos")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


# ===============================
# INDEX
# ===============================
@app.route("/")
@login_required_decorator
def index():

    con = get_db_connection()
    cur = con.cursor()

    cur.execute("SELECT * FROM comandas WHERE status = 'Aberta' ORDER BY id DESC")
    comandas = cur.fetchall()
    return render_template("index.html", comandas=comandas)


# ===============================
# NOVA COMANDA
# ===============================
@app.route("/nova")
@login_required_decorator
def nova():

    return render_template("nova_comanda.html")


@app.route("/criar_comanda", methods=["POST"])
@login_required_decorator
def criar_comanda():

    nome = request.form["nome"]
    cpf = request.form["cpf"]

    con = get_db_connection()
    cur = con.cursor()

    cur.execute(
        "INSERT INTO comandas (cliente, cpf, status, data) VALUES (?, ?, 'Aberta', ?)",
        (nome, cpf, datetime.now().strftime("%Y-%m-%d"))
    )

    con.commit()
    comanda_id = cur.lastrowid

    return redirect(url_for("comanda", id=comanda_id))


# ===============================
# VER COMANDA
# ===============================
@app.route("/comanda/<int:id>")
@login_required_decorator
def comanda(id):

    con = get_db_connection()
    cur = con.cursor()

    cur.execute("SELECT * FROM comandas WHERE id = ?", (id,))
    comanda = cur.fetchone()

    if not comanda:
        return redirect(url_for("index"))

    cur.execute("""
        SELECT 
            i.id,
            p.nome,
            i.qtd,
            i.preco,
            i.acrescimos AS acrescimos_texto,
            i.observacoes AS observacoes_texto,
            p.imagem
        FROM itens_comanda i
        JOIN produtos p ON p.id = i.produto_id
        WHERE i.comanda_id = ?
    """, (id,))
    itens_raw = cur.fetchall()
    itens = []
    for i in itens_raw:
        item = dict(i)
        cur.execute("""
            SELECT a.nome, a.preco
            FROM acrescimos a
            JOIN item_acrescimos ia ON a.id = ia.acrescimo_id
            WHERE ia.item_comanda_id = ?
        """, (i['id'],))
        item['acrescimos'] = cur.fetchall()
        cur.execute("""
            SELECT texto
            FROM item_personalizacoes
            WHERE item_comanda_id = ?
            ORDER BY id
        """, (i['id'],))
        item['personalizacoes'] = cur.fetchall()
        itens.append(item)

    subtotal, total = calcular_total_comanda(id)

    return render_template(
        "comanda.html",
        comanda=comanda,
        itens=itens,
        subtotal=subtotal,
        total=total
    )


# ===============================
# COZINHA (PEDIDOS EM ABERTO)
# ===============================
@app.route("/cozinha")
@login_required_decorator
def cozinha():
    pedidos = carregar_pedidos_cozinha()
    return render_template("cozinha.html", pedidos=pedidos)


def carregar_pedidos_cozinha():
    con = get_db_connection()
    cur = con.cursor()

    cur.execute("""
        SELECT 
            c.id AS comanda_id,
            c.cliente,
            i.id AS item_id,
            i.qtd,
            i.acrescimos AS acrescimos_texto,
            i.observacoes AS observacoes_texto,
            p.nome AS produto_nome
        FROM comandas c
        JOIN itens_comanda i ON i.comanda_id = c.id
        JOIN produtos p ON p.id = i.produto_id
        WHERE c.status = 'Aberta'
        ORDER BY c.id ASC, i.id ASC
    """)
    rows = cur.fetchall()

    pedidos_map = {}
    for r in rows:
        comanda_id = r["comanda_id"]
        if comanda_id not in pedidos_map:
            pedidos_map[comanda_id] = {
                "comanda_id": comanda_id,
                "cliente": r["cliente"],
                "itens": []
            }

        acrescimos_texto = (r["acrescimos_texto"] or "").strip()
        observacoes_texto = (r["observacoes_texto"] or "").strip()

        if not acrescimos_texto:
            cur.execute("""
                SELECT a.nome
                FROM acrescimos a
                JOIN item_acrescimos ia ON a.id = ia.acrescimo_id
                WHERE ia.item_comanda_id = ?
            """, (r["item_id"],))
            acrescimos_legado = [a["nome"] for a in cur.fetchall()]
            if acrescimos_legado:
                acrescimos_texto = ", ".join(acrescimos_legado)

        if not observacoes_texto:
            cur.execute("""
                SELECT texto
                FROM item_personalizacoes
                WHERE item_comanda_id = ?
                ORDER BY id
            """, (r["item_id"],))
            personalizacoes = [p["texto"] for p in cur.fetchall()]
            if personalizacoes:
                observacoes_texto = "; ".join(personalizacoes)

        pedidos_map[comanda_id]["itens"].append({
            "produto": r["produto_nome"],
            "qtd": r["qtd"],
            "acrescimos_texto": acrescimos_texto,
            "observacoes_texto": observacoes_texto
        })

    pedidos = list(pedidos_map.values())

    return pedidos


@app.route("/cozinha/fechar/<int:comanda_id>", methods=["POST"])
@login_required_decorator
def cozinha_fechar_comanda(comanda_id):
    # Mantido apenas por compatibilidade com telas antigas; nao altera a comanda.
    return ("", 204)


@app.route("/cozinha/dados")
@login_required_decorator
def cozinha_dados():
    pedidos = carregar_pedidos_cozinha()
    return jsonify({"pedidos": pedidos})


@app.route("/cozinha/stream")
@login_required_decorator
def cozinha_stream():
    @stream_with_context
    def event_stream():
        last_payload = None
        while True:
            pedidos = carregar_pedidos_cozinha()
            payload = json.dumps({"pedidos": pedidos}, ensure_ascii=False)
            if payload != last_payload:
                last_payload = payload
                yield f"data: {payload}\n\n"
            time.sleep(1.5)

    return Response(event_stream(), mimetype="text/event-stream")


# ===============================
# LISTAR CATEGORIAS
# ===============================
@app.route("/categorias/<int:id>")
@login_required_decorator
def categorias(id):

    con = get_db_connection()
    cur = con.cursor()

    cur.execute("SELECT * FROM categorias")
    categorias = cur.fetchall()

    return render_template(
        "categorias.html",
        categorias=categorias,
        id=id
    )


# ===============================
# GERENCIAR CATEGORIAS
# ===============================
@app.route("/gerenciar_categorias")
@gerente_required_decorator
def gerenciar_categorias():
    con = get_db_connection()
    cur = con.cursor()
    cur.execute("SELECT * FROM categorias ORDER BY nome")
    categorias = cur.fetchall()
    return render_template("gerenciar_categorias.html", categorias=categorias)


@app.route("/gerenciar/categorias/adicionar", methods=["GET", "POST"])
@gerente_required_decorator
def adicionar_categoria():
    con = get_db_connection()
    cur = con.cursor()

    if request.method == "POST":
        nome = request.form["nome"]
        imagem = None

        if "imagem" in request.files:
            file = request.files["imagem"]
            if file and file.filename and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                caminho = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(caminho)
                imagem = filename

        cur.execute(
            "INSERT INTO categorias (nome, imagem) VALUES (?, ?)",
            (nome, imagem)
        )
        con.commit()
        return redirect(url_for("gerenciar_categorias"))

    return render_template("adicionar_categoria.html")


@app.route("/gerenciar/categorias/editar/<int:id>", methods=["GET", "POST"])
@gerente_required_decorator
def editar_categoria(id):
    con = get_db_connection()
    cur = con.cursor()

    cur.execute("SELECT * FROM categorias WHERE id = ?", (id,))
    categoria = cur.fetchone()
    if not categoria:
        return redirect(url_for("gerenciar_categorias"))

    if request.method == "POST":
        nome = request.form["nome"]
        imagem = categoria["imagem"]

        if "imagem" in request.files:
            file = request.files["imagem"]
            if file and file.filename and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                caminho = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(caminho)
                imagem = filename

        cur.execute(
            "UPDATE categorias SET nome = ?, imagem = ? WHERE id = ?",
            (nome, imagem, id)
        )
        con.commit()
        return redirect(url_for("gerenciar_categorias"))

    return render_template("editar_categoria.html", categoria=categoria)


@app.route("/gerenciar/categorias/excluir/<int:id>")
@gerente_required_decorator
def excluir_categoria(id):
    con = get_db_connection()
    cur = con.cursor()
    cur.execute("SELECT imagem FROM categorias WHERE id = ?", (id,))
    categoria = cur.fetchone()

    cur.execute("DELETE FROM categorias WHERE id = ?", (id,))
    con.commit()

    if categoria and categoria["imagem"]:
        try:
            os.remove(os.path.join(app.config['UPLOAD_FOLDER'], categoria["imagem"]))
        except FileNotFoundError:
            pass

    return redirect(url_for("gerenciar_categorias"))


# ===============================
# GERENCIAR BAIRROS ENTREGA
# ===============================
@app.route("/gerenciar/bairros")
@gerente_required_decorator
def gerenciar_bairros():
    con = get_db_connection()
    cur = con.cursor()
    cur.execute("SELECT * FROM bairros_entrega ORDER BY nome")
    bairros = cur.fetchall()
    return render_template("gerenciar_bairros.html", bairros=bairros)


@app.route("/gerenciar/bairros/adicionar", methods=["GET", "POST"])
@gerente_required_decorator
def adicionar_bairro():
    if request.method == "POST":
        nome = (request.form.get("nome") or "").strip()
        taxa_raw = (request.form.get("taxa") or "0").strip()
        tempo_entrega = (request.form.get("tempo_entrega") or "").strip()
        tempo_retirada = (request.form.get("tempo_retirada") or "").strip()
        ativo = 1 if request.form.get("ativo") == "on" else 0

        try:
            taxa = float(taxa_raw.replace(",", "."))
        except ValueError:
            taxa = 0.0

        con = get_db_connection()
        cur = con.cursor()
        cur.execute(
            "INSERT INTO bairros_entrega (nome, taxa, tempo_entrega, tempo_retirada, ativo) VALUES (?, ?, ?, ?, ?)",
            (nome, taxa, tempo_entrega, tempo_retirada, ativo)
        )
        con.commit()
        return redirect(url_for("gerenciar_bairros"))

    return render_template("adicionar_bairro.html")


@app.route("/gerenciar/bairros/editar/<int:id>", methods=["GET", "POST"])
@gerente_required_decorator
def editar_bairro(id):
    con = get_db_connection()
    cur = con.cursor()
    cur.execute("SELECT * FROM bairros_entrega WHERE id = ?", (id,))
    bairro = cur.fetchone()
    if not bairro:
        return redirect(url_for("gerenciar_bairros"))

    if request.method == "POST":
        nome = (request.form.get("nome") or "").strip()
        taxa_raw = (request.form.get("taxa") or "0").strip()
        tempo_entrega = (request.form.get("tempo_entrega") or "").strip()
        tempo_retirada = (request.form.get("tempo_retirada") or "").strip()
        ativo = 1 if request.form.get("ativo") == "on" else 0

        try:
            taxa = float(taxa_raw.replace(",", "."))
        except ValueError:
            taxa = 0.0

        cur.execute(
            "UPDATE bairros_entrega SET nome = ?, taxa = ?, tempo_entrega = ?, tempo_retirada = ?, ativo = ? WHERE id = ?",
            (nome, taxa, tempo_entrega, tempo_retirada, ativo, id)
        )
        con.commit()
        return redirect(url_for("gerenciar_bairros"))

    return render_template("editar_bairro.html", bairro=bairro)


@app.route("/gerenciar/bairros/excluir/<int:id>")
@gerente_required_decorator
def excluir_bairro(id):
    con = get_db_connection()
    cur = con.cursor()
    cur.execute("DELETE FROM bairros_entrega WHERE id = ?", (id,))
    con.commit()
    return redirect(url_for("gerenciar_bairros"))


# ===============================
# PEDIDO ONLINE (PUBLICO)
# ===============================
@app.route("/pedido")
def pedido_index():
    con = get_db_connection()
    cur = con.cursor()
    cur.execute("SELECT * FROM categorias ORDER BY nome")
    categorias = cur.fetchall()
    cart = get_cart()
    cart_count = sum(item["qtd"] for item in cart)
    return render_template(
        "pedido_categorias.html",
        categorias=categorias,
        cart_count=cart_count
    )


@app.route("/pedido/categoria/<int:categoria_id>")
def pedido_categoria(categoria_id):
    con = get_db_connection()
    cur = con.cursor()
    cur.execute("SELECT * FROM categorias WHERE id = ?", (categoria_id,))
    categoria = cur.fetchone()
    if not categoria:
        return redirect(url_for("pedido_index"))

    cur.execute(
        "SELECT * FROM produtos WHERE categoria_id = ? ORDER BY destaque DESC, nome",
        (categoria_id,)
    )
    produtos = cur.fetchall()
    cart = get_cart()
    cart_count = sum(item["qtd"] for item in cart)
    cart_total = calcular_total_cart(cart)
    ingredientes_padrao = ["milho", "tomate", "cebola", "alface"]
    acrescimos_opcoes = [
        {"nome": "calabresa", "preco": 1.50},
        {"nome": "bacon", "preco": 2.50},
        {"nome": "hamburguer", "preco": 2.50},
        {"nome": "presunto", "preco": 0.50},
        {"nome": "ovo", "preco": 1.50},
        {"nome": "frango", "preco": 3.00},
        {"nome": "queijo", "preco": 1.00},
        {"nome": "cheddar", "preco": 0.50},
        {"nome": "catupiry", "preco": 0.50}
    ]

    return render_template(
        "pedido_produtos.html",
        categoria=categoria,
        produtos=produtos,
        ingredientes_padrao=ingredientes_padrao,
        acrescimos_opcoes=acrescimos_opcoes,
        cart_count=cart_count,
        cart=cart,
        cart_total=cart_total
    )


@app.route("/pedido/api/cart")
def pedido_api_cart():
    cart = get_cart()
    total = calcular_total_cart(cart)
    count = sum(item["qtd"] for item in cart)
    payload = []
    for i, item in enumerate(cart):
        payload.append({
            "index": i,
            "nome": item.get("nome", ""),
            "qtd": item.get("qtd", 0),
            "preco": float(item.get("preco", 0)),
            "imagem": item.get("imagem"),
            "acrescimos_texto": item.get("acrescimos_texto", ""),
            "observacao": item.get("observacao", ""),
            "remove_url": url_for("pedido_remover", index=i)
        })
    return jsonify({
        "count": count,
        "total": float(total),
        "items": payload
    })


@app.route("/pedido/adicionar", methods=["POST"])
def pedido_adicionar():
    produto_id = int(request.form["produto_id"])
    qtd = int(request.form.get("qtd", 0))
    removidos = request.form.getlist("removidos")
    observacao = (request.form.get("observacao") or "").strip()
    next_url = request.form.get("next") or url_for("pedido_index")

    if qtd <= 0:
        return redirect(next_url)

    con = get_db_connection()
    cur = con.cursor()
    cur.execute("SELECT id, nome, preco, imagem FROM produtos WHERE id = ?", (produto_id,))
    produto = cur.fetchone()
    if not produto:
        return redirect(next_url)

    acrescimos_texto = ""
    acrescimo_valor = 0.0
    acrescimos_selecionados = request.form.getlist(f"acrescimo_{produto_id}")
    if acrescimos_selecionados:
        nomes = []
        for item in acrescimos_selecionados:
            try:
                nome, preco_str = item.split("|", 1)
                nomes.append(nome)
                acrescimo_valor += float(preco_str)
            except ValueError:
                continue
        acrescimos_texto = ", ".join(nomes)
    else:
        acrescimos_texto = (request.form.get(f"acrescimos_{produto_id}") or "").strip()
        acrescimo_valor_raw = (request.form.get(f"acrescimo_valor_{produto_id}") or "").strip()
        if acrescimo_valor_raw:
            try:
                acrescimo_valor = float(acrescimo_valor_raw.replace(",", "."))
            except ValueError:
                acrescimo_valor = 0.0

    preco_final = max(0.0, float(produto["preco"]) + acrescimo_valor)

    cart = get_cart()
    chave = (
        produto_id,
        tuple(sorted(removidos)),
        observacao,
        acrescimos_texto,
        round(acrescimo_valor, 2)
    )
    item_encontrado = False
    for item in cart:
        if (
            item["produto_id"] == chave[0] and
            tuple(sorted(item["removidos"])) == chave[1] and
            item["observacao"] == chave[2] and
            item.get("acrescimos_texto", "") == chave[3] and
            round(float(item.get("acrescimo_valor", 0.0)), 2) == chave[4]
        ):
            item["qtd"] += qtd
            item_encontrado = True
            break

    if not item_encontrado:
        cart.append({
            "produto_id": produto["id"],
            "nome": produto["nome"],
            "preco": preco_final,
            "imagem": produto["imagem"],
            "qtd": qtd,
            "removidos": removidos,
            "observacao": observacao,
            "acrescimos_texto": acrescimos_texto,
            "acrescimo_valor": acrescimo_valor
        })

    save_cart(cart)
    return redirect(next_url)


@app.route("/pedido/carrinho")
def pedido_carrinho():
    cart = get_cart()
    cart_enriquecido = enriquecer_cart_com_destaque(cart)
    total = calcular_total_cart(cart)
    return render_template(
        "pedido_carrinho.html",
        cart=cart_enriquecido,
        total=total,
        taxa_entrega=app.config.get("TAXA_ENTREGA"),
        tempo_entrega=app.config.get("TEMPO_ENTREGA"),
        tempo_retirada=app.config.get("TEMPO_RETIRADA"),
        bairros=carregar_bairros_entrega()
    )


@app.route("/pedido/remover/<int:index>", methods=["POST"])
def pedido_remover(index):
    cart = get_cart()
    if 0 <= index < len(cart):
        cart.pop(index)
        save_cart(cart)
    return redirect(url_for("pedido_carrinho"))


@app.route("/pedido/finalizar", methods=["POST"])
def pedido_finalizar():
    return finalizar_pedido_publico(
        url_for("pedido_carrinho"),
        "pedido_carrinho.html",
        "pedido_sucesso.html"
    )


# ===============================
# CLIENTE (MINI SITE)
# ===============================
@app.route("/cliente")
def cliente_index():
    con = get_db_connection()
    cur = con.cursor()
    cur.execute("""
        SELECT p.id, p.nome, p.preco, p.imagem, p.categoria_id
        FROM produtos p
        WHERE p.destaque = 1
        ORDER BY p.nome
        LIMIT 6
    """)
    destaques = cur.fetchall()
    cart = get_cart()
    cart_count = sum(item["qtd"] for item in cart)
    return render_template(
        "cliente_index.html",
        cart_count=cart_count,
        destaques=destaques
    )


@app.route("/cliente/cardapio")
def cliente_cardapio():
    con = get_db_connection()
    cur = con.cursor()
    cur.execute("SELECT * FROM categorias ORDER BY nome")
    categorias = cur.fetchall()
    cart = get_cart()
    cart_count = sum(item["qtd"] for item in cart)
    return render_template(
        "cliente_categorias.html",
        categorias=categorias,
        cart_count=cart_count
    )


@app.route("/cliente/categoria/<int:categoria_id>")
def cliente_categoria(categoria_id):
    con = get_db_connection()
    cur = con.cursor()
    cur.execute("SELECT * FROM categorias WHERE id = ?", (categoria_id,))
    categoria = cur.fetchone()
    if not categoria:
        return redirect(url_for("cliente_cardapio"))

    cur.execute(
        "SELECT * FROM produtos WHERE categoria_id = ? ORDER BY destaque DESC, nome",
        (categoria_id,)
    )
    produtos = cur.fetchall()
    cart = get_cart()
    cart_count = sum(item["qtd"] for item in cart)
    ingredientes_padrao = ["milho", "tomate", "cebola", "alface"]
    acrescimos_opcoes = [
        {"nome": "calabresa", "preco": 1.50},
        {"nome": "bacon", "preco": 2.50},
        {"nome": "hamburguer", "preco": 2.50},
        {"nome": "presunto", "preco": 0.50},
        {"nome": "ovo", "preco": 1.50},
        {"nome": "frango", "preco": 3.00},
        {"nome": "queijo", "preco": 1.00},
        {"nome": "cheddar", "preco": 0.50},
        {"nome": "catupiry", "preco": 0.50}
    ]

    return render_template(
        "cliente_produtos.html",
        categoria=categoria,
        produtos=produtos,
        ingredientes_padrao=ingredientes_padrao,
        acrescimos_opcoes=acrescimos_opcoes,
        cart_count=cart_count
    )


@app.route("/cliente/adicionar", methods=["POST"])
def cliente_adicionar():
    produto_id = int(request.form["produto_id"])
    qtd = int(request.form.get("qtd", 0))
    removidos = request.form.getlist("removidos")
    observacao = (request.form.get("observacao") or "").strip()
    next_url = request.form.get("next") or url_for("cliente_cardapio")

    if qtd <= 0:
        return redirect(next_url)

    con = get_db_connection()
    cur = con.cursor()
    cur.execute("SELECT id, nome, preco, imagem FROM produtos WHERE id = ?", (produto_id,))
    produto = cur.fetchone()
    if not produto:
        return redirect(next_url)

    acrescimos_texto = ""
    acrescimo_valor = 0.0
    acrescimos_selecionados = request.form.getlist(f"acrescimo_{produto_id}")
    if acrescimos_selecionados:
        nomes = []
        for item in acrescimos_selecionados:
            try:
                nome, preco_str = item.split("|", 1)
                nomes.append(nome)
                acrescimo_valor += float(preco_str)
            except ValueError:
                continue
        acrescimos_texto = ", ".join(nomes)
    else:
        acrescimos_texto = (request.form.get(f"acrescimos_{produto_id}") or "").strip()
        acrescimo_valor_raw = (request.form.get(f"acrescimo_valor_{produto_id}") or "").strip()
        if acrescimo_valor_raw:
            try:
                acrescimo_valor = float(acrescimo_valor_raw.replace(",", "."))
            except ValueError:
                acrescimo_valor = 0.0

    preco_final = max(0.0, float(produto["preco"]) + acrescimo_valor)

    cart = get_cart()
    chave = (
        produto_id,
        tuple(sorted(removidos)),
        observacao,
        acrescimos_texto,
        round(acrescimo_valor, 2)
    )
    item_encontrado = False
    for item in cart:
        if (
            item["produto_id"] == chave[0] and
            tuple(sorted(item["removidos"])) == chave[1] and
            item["observacao"] == chave[2] and
            item.get("acrescimos_texto", "") == chave[3] and
            round(float(item.get("acrescimo_valor", 0.0)), 2) == chave[4]
        ):
            item["qtd"] += qtd
            item_encontrado = True
            break

    if not item_encontrado:
        cart.append({
            "produto_id": produto["id"],
            "nome": produto["nome"],
            "preco": preco_final,
            "imagem": produto["imagem"],
            "qtd": qtd,
            "removidos": removidos,
            "observacao": observacao,
            "acrescimos_texto": acrescimos_texto,
            "acrescimo_valor": acrescimo_valor
        })

    save_cart(cart)
    return redirect(next_url)


@app.route("/cliente/confirmar", methods=["POST"])
def cliente_confirmar_itens():
    next_url = request.form.get("next") or url_for("cliente_carrinho")
    cart = get_cart()

    for campo in request.form:
        if campo.startswith("qtd_"):
            produto_id = campo.replace("qtd_", "")
            try:
                qtd = int(request.form[campo])
            except ValueError:
                continue

            if qtd <= 0:
                continue

            con = get_db_connection()
            cur = con.cursor()
            cur.execute("SELECT id, nome, preco, imagem FROM produtos WHERE id = ?", (produto_id,))
            produto = cur.fetchone()
            if not produto:
                continue

            observacoes_texto = (request.form.get(f"observacoes_{produto_id}") or "").strip()

            acrescimos_texto = ""
            acrescimo_valor = 0.0
            acrescimos_selecionados = request.form.getlist(f"acrescimo_{produto_id}")
            if acrescimos_selecionados:
                nomes = []
                for item in acrescimos_selecionados:
                    try:
                        nome, preco_str = item.split("|", 1)
                        nomes.append(nome)
                        acrescimo_valor += float(preco_str)
                    except ValueError:
                        continue
                acrescimos_texto = ", ".join(nomes)
            else:
                acrescimos_texto = (request.form.get(f"acrescimos_{produto_id}") or "").strip()
                acrescimo_valor_raw = (request.form.get(f"acrescimo_valor_{produto_id}") or "").strip()
                if acrescimo_valor_raw:
                    try:
                        acrescimo_valor = float(acrescimo_valor_raw.replace(",", "."))
                    except ValueError:
                        acrescimo_valor = 0.0

            preco_final = max(0.0, float(produto["preco"]) + acrescimo_valor)

            chave = (
                int(produto_id),
                observacoes_texto,
                acrescimos_texto,
                round(acrescimo_valor, 2)
            )
            item_encontrado = False
            for item in cart:
                if (
                    item["produto_id"] == chave[0] and
                    (item.get("observacao") or "") == chave[1] and
                    item.get("acrescimos_texto", "") == chave[2] and
                    round(float(item.get("acrescimo_valor", 0.0)), 2) == chave[3]
                ):
                    item["qtd"] += qtd
                    item_encontrado = True
                    break

            if not item_encontrado:
                cart.append({
                    "produto_id": produto["id"],
                    "nome": produto["nome"],
                    "preco": preco_final,
                    "imagem": produto["imagem"],
                    "qtd": qtd,
                    "removidos": [],
                    "observacao": observacoes_texto,
                    "acrescimos_texto": acrescimos_texto,
                    "acrescimo_valor": acrescimo_valor
                })

    save_cart(cart)
    return redirect(next_url)


@app.route("/cliente/carrinho")
def cliente_carrinho():
    cart = get_cart()
    cart_enriquecido = enriquecer_cart_com_destaque(cart)
    total = calcular_total_cart(cart)
    cart_count = sum(item["qtd"] for item in cart)
    return render_template(
        "cliente_carrinho.html",
        cart=cart_enriquecido,
        total=total,
        cart_count=cart_count,
        taxa_entrega=app.config.get("TAXA_ENTREGA"),
        tempo_entrega=app.config.get("TEMPO_ENTREGA"),
        tempo_retirada=app.config.get("TEMPO_RETIRADA"),
        bairros=carregar_bairros_entrega()
    )


@app.route("/cliente/remover/<int:index>", methods=["POST"])
def cliente_remover(index):
    cart = get_cart()
    if 0 <= index < len(cart):
        cart.pop(index)
        save_cart(cart)
    return redirect(url_for("cliente_carrinho"))


@app.route("/cliente/finalizar", methods=["POST"])
def cliente_finalizar():
    return finalizar_pedido_publico(
        url_for("cliente_carrinho"),
        "cliente_carrinho.html",
        "cliente_sucesso.html"
    )


# ===============================
# PRODUTOS DA CATEGORIA
# ===============================
@app.route("/produtos/<int:id>/<int:categoria_id>")
@login_required_decorator
def produtos_categoria(id, categoria_id):

    con = get_db_connection()
    cur = con.cursor()

    cur.execute(
        "SELECT * FROM produtos WHERE categoria_id = ?",
        (categoria_id,)
    )
    produtos_raw = cur.fetchall()
    produtos = [dict(p) for p in produtos_raw]

    acrescimos_opcoes = [
        {"nome": "calabresa", "preco": 1.50},
        {"nome": "bacon", "preco": 2.50},
        {"nome": "hamburguer", "preco": 2.50},
        {"nome": "presunto", "preco": 0.50},
        {"nome": "ovo", "preco": 1.50},
        {"nome": "frango", "preco": 3.00},
        {"nome": "queijo", "preco": 1.00},
        {"nome": "cheddar", "preco": 0.50},
        {"nome": "catupiry", "preco": 0.50}
    ]

    return render_template(
        "produtos.html",
        produtos=produtos,
        id=id,
        acrescimos_opcoes=acrescimos_opcoes
    )


# ===============================
# ADICIONAR ITEM NA COMANDA
# ===============================
@app.route("/confirmar_itens/<int:comanda_id>", methods=["POST"])
@login_required_decorator
def confirmar_itens(comanda_id):

    con = get_db_connection()
    cur = con.cursor()

    for campo in request.form:
        if campo.startswith("qtd_"):
            produto_id = campo.replace("qtd_", "")
            qtd = int(request.form[campo])

            if qtd > 0:
                cur.execute(
                    "SELECT preco FROM produtos WHERE id = ?",
                    (produto_id,)
                )
                produto = cur.fetchone()

                if produto:
                    preco_base = produto["preco"]
                    observacoes_texto = (request.form.get(f"observacoes_{produto_id}") or "").strip()

                    acrescimos_texto = ""
                    acrescimo_valor = 0.0
                    acrescimos_selecionados = request.form.getlist(f"acrescimo_{produto_id}")
                    if acrescimos_selecionados:
                        nomes = []
                        for item in acrescimos_selecionados:
                            try:
                                nome, preco_str = item.split("|", 1)
                                nomes.append(nome)
                                acrescimo_valor += float(preco_str)
                            except ValueError:
                                continue
                        acrescimos_texto = ", ".join(nomes)
                    else:
                        acrescimos_texto = (request.form.get(f"acrescimos_{produto_id}") or "").strip()
                        acrescimo_valor_raw = (request.form.get(f"acrescimo_valor_{produto_id}") or "").strip()
                        if acrescimo_valor_raw:
                            try:
                                acrescimo_valor = float(acrescimo_valor_raw.replace(",", "."))
                            except ValueError:
                                acrescimo_valor = 0.0

                    preco_final = max(0.0, preco_base + acrescimo_valor)
                    tem_personalizacao = bool(acrescimos_texto or observacoes_texto or acrescimo_valor > 0)

                    total_itens = qtd if tem_personalizacao else 1
                    qtd_por_item = 1 if tem_personalizacao else qtd

                    for _ in range(total_itens):
                        cur.execute("""
                            INSERT INTO itens_comanda (comanda_id, produto_id, qtd, preco, acrescimos, observacoes)
                            VALUES (?, ?, ?, ?, ?, ?)
                        """, (comanda_id, produto_id, qtd_por_item, preco_final, acrescimos_texto, observacoes_texto))

    con.commit()

    return redirect(url_for("comanda", id=comanda_id))


# ===============================
# FECHAR COMANDA
# ===============================
@app.route("/fechar_comanda/<int:id>")
@login_required_decorator
def fechar_comanda(id):

    con = get_db_connection()
    cur = con.cursor()

    cur.execute(
        "UPDATE comandas SET status = 'Fechada' WHERE id = ?",
        (id,)
    )

    con.commit()

    return redirect(url_for("index"))


# ===============================
# PAGAMENTO
# ===============================


@app.route("/comanda/<int:id>/pagar")
@login_required_decorator
def pagar_comanda(id):

    con = get_db_connection()
    cur = con.cursor()

    cur.execute("SELECT * FROM comandas WHERE id = ?", (id,))
    comanda = cur.fetchone()

    if not comanda:
        return redirect(url_for("index"))

    subtotal, total = calcular_total_comanda(id)

    cur.execute("SELECT * FROM pagamentos WHERE comanda_id = ? ORDER BY data DESC", (id,))
    pagamentos = cur.fetchall()

    total_pago = sum(p['valor'] for p in pagamentos)
    restante_a_pagar = total - total_pago

    if comanda['status'] == 'Paga':
        # Now pass all required variables, even if comanda is paid
        return render_template(
            "pagamento.html",
            comanda=comanda,
            mensagem="Esta comanda já foi paga.",
            subtotal=subtotal,
            total=total,
            pagamentos=pagamentos,
            total_pago=total_pago,
            restante_a_pagar=restante_a_pagar,
            current_datetime=datetime.now().strftime("%Y-%m-%dT%H:%M")
        )

    return render_template(
        "pagamento.html",
        comanda=comanda,
        subtotal=subtotal,
        total=total,
        pagamentos=pagamentos,
        total_pago=total_pago,
        restante_a_pagar=restante_a_pagar,
        current_datetime=datetime.now().strftime("%Y-%m-%dT%H:%M")  # Para o campo datetime-local
    )


@app.route("/comanda/<int:id>/registrar_pagamento", methods=["POST"])
@login_required_decorator
def registrar_pagamento(id):

    con = get_db_connection()
    cur = con.cursor()

    valor_pago = float(request.form["valor"])
    metodo = request.form["metodo"]
    data_pagamento = request.form["data_pagamento"]

    cur.execute(
        "INSERT INTO pagamentos (comanda_id, valor, metodo, data) VALUES (?, ?, ?, ?)",
        (id, valor_pago, metodo, data_pagamento)
    )
    con.commit()

    # Verificar se a comanda foi totalmente paga
    subtotal, total = calcular_total_comanda(id)
    cur.execute("SELECT SUM(valor) FROM pagamentos WHERE comanda_id = ?", (id,))
    total_pago = cur.fetchone()[0] or 0.0

    if total_pago >= total:
        cur.execute("UPDATE comandas SET status = 'Paga' WHERE id = ?", (id,))
        con.commit()

    return redirect(url_for("index"))


# ===============================
# REMOVER ITEM DA COMANDA
# ===============================
@app.route("/remover_item/<int:item_id>/<int:comanda_id>")
@login_required_decorator
def remover_item(item_id, comanda_id):

    con = get_db_connection()
    cur = con.cursor()

    cur.execute("DELETE FROM item_acrescimos WHERE item_comanda_id = ?", (item_id,))
    cur.execute("DELETE FROM item_personalizacoes WHERE item_comanda_id = ?", (item_id,))
    cur.execute("DELETE FROM itens_comanda WHERE id = ?", (item_id,))
    con.commit()

    return redirect(url_for("comanda", id=comanda_id))


# ===============================
# PAINEL PEDIDOS ONLINE (INTERNO)
# ===============================
def carregar_pedidos_online():
    con = get_db_connection()
    cur = con.cursor()
    cur.execute("""
        SELECT id, comanda_id, nome, telefone, tipo, endereco, bairro, taxa_entrega,
               tempo_entrega, tempo_retirada, maps_url, status, criado_em, atualizado_em
        FROM pedidos_online
        ORDER BY id DESC
    """)
    pedidos_raw = cur.fetchall()
    pedidos = []
    for p in pedidos_raw:
        pedido = dict(p)
        cur.execute("""
            SELECT i.id, i.qtd, i.preco, pr.nome, pr.imagem
            FROM itens_comanda i
            JOIN produtos pr ON pr.id = i.produto_id
            WHERE i.comanda_id = ?
            ORDER BY i.id
        """, (p["comanda_id"],))
        itens_raw = cur.fetchall()
        itens = []
        for i in itens_raw:
            item = dict(i)
            cur.execute("""
                SELECT texto
                FROM item_personalizacoes
                WHERE item_comanda_id = ?
                ORDER BY id
            """, (i["id"],))
            item["personalizacoes"] = [r["texto"] for r in cur.fetchall()]
            itens.append(item)
        pedido["itens"] = itens
        pedidos.append(pedido)
    return pedidos


@app.route("/painel_pedidos")
@login_required_decorator
def painel_pedidos():
    pedidos = carregar_pedidos_online()
    ativos = sum(1 for p in pedidos if p["status"] != "Entregue")
    return render_template(
        "painel_pedidos.html",
        pedidos=pedidos,
        ativos=ativos
    )


@app.route("/painel_pedidos/dados")
@login_required_decorator
def painel_pedidos_dados():
    pedidos = carregar_pedidos_online()
    ativos = sum(1 for p in pedidos if p["status"] != "Entregue")
    return jsonify({"pedidos": pedidos, "ativos": ativos})


@app.route("/painel_pedidos/status/<int:pedido_id>", methods=["POST"])
@login_required_decorator
def painel_pedidos_status(pedido_id):
    status = (request.form.get("status") or "").strip()
    if status not in ["Recebido", "Em preparo", "Pronto", "Entregue"]:
        return redirect(url_for("painel_pedidos"))

    con = get_db_connection()
    cur = con.cursor()
    atualizado_em = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cur.execute(
        "UPDATE pedidos_online SET status = ?, atualizado_em = ? WHERE id = ?",
        (status, atualizado_em, pedido_id)
    )
    con.commit()
    return redirect(url_for("painel_pedidos"))


@app.route("/motoboy")
@motoboy_required_decorator
def motoboy():
    pedidos = carregar_pedidos_online()
    entregas = [p for p in pedidos if p.get("tipo") == "Entrega" and p.get("status") != "Entregue"]
    return render_template("motoboy.html", pedidos=entregas)


# JSON para atualizar tela do motoboy
@app.route("/motoboy/dados")
@motoboy_required_decorator
def motoboy_dados():
    pedidos = carregar_pedidos_online()
    entregas = [p for p in pedidos if p.get("tipo") == "Entrega" and p.get("status") != "Entregue"]
    return jsonify({"pedidos": entregas})



# ===============================
# GERENCIAR PRODUTOS
# ===============================
@app.route("/gerenciar_produtos")
@gerente_required_decorator
def gerenciar_produtos():

    con = get_db_connection()
    cur = con.cursor()

    cur.execute("""
        SELECT p.id, p.nome, p.preco, p.imagem, p.destaque, c.nome AS categoria
        FROM produtos p
        JOIN categorias c ON p.categoria_id = c.id
        ORDER BY p.nome
    """)
    produtos = cur.fetchall()
    return render_template("gerenciar_produtos.html", produtos=produtos)


@app.route("/gerenciar/destaques")
@gerente_required_decorator
def gerenciar_destaques():
    con = get_db_connection()
    cur = con.cursor()
    cur.execute("""
        SELECT p.id, p.nome, p.preco, p.imagem, p.destaque, c.nome AS categoria
        FROM produtos p
        JOIN categorias c ON c.id = p.categoria_id
        ORDER BY p.destaque DESC, p.nome
    """)
    produtos = cur.fetchall()
    return render_template("gerenciar_destaques.html", produtos=produtos)


@app.route("/gerenciar/destaques/salvar", methods=["POST"])
@gerente_required_decorator
def salvar_destaques():
    ids_destaque = set(request.form.getlist("destaque_ids"))
    con = get_db_connection()
    cur = con.cursor()
    cur.execute("SELECT id FROM produtos")
    todos = [str(row["id"]) for row in cur.fetchall()]

    for produto_id in todos:
        destaque = 1 if produto_id in ids_destaque else 0
        cur.execute(
            "UPDATE produtos SET destaque = ? WHERE id = ?",
            (destaque, produto_id)
        )

    con.commit()
    return redirect(url_for("gerenciar_destaques"))


@app.route("/gerenciar/produtos/adicionar", methods=["GET", "POST"])
@gerente_required_decorator
def adicionar_produto():

    con = get_db_connection()
    cur = con.cursor()

    if request.method == "POST":
        nome = request.form["nome"]
        preco = request.form["preco"]
        categoria_id = request.form["categoria_id"]
        destaque = 1 if request.form.get("destaque") == "on" else 0
        acrescimos = request.form.getlist("acrescimos")
        imagem = None

        if 'imagem' in request.files:
            file = request.files['imagem']
            if file and file.filename != '' and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                imagem = filename

        cur.execute(
            "INSERT INTO produtos (nome, preco, categoria_id, imagem, destaque) VALUES (?, ?, ?, ?, ?)",
            (nome, preco, categoria_id, imagem, destaque)
        )
        produto_id = cur.lastrowid

        for acrescimo_id in acrescimos:
            cur.execute(
                "INSERT INTO produto_acrescimos (produto_id, acrescimo_id) VALUES (?, ?)",
                (produto_id, acrescimo_id)
            )

        con.commit()
        return redirect(url_for("gerenciar_produtos"))

    # Se for GET
    cur.execute("SELECT * FROM categorias ORDER BY nome")
    categorias = cur.fetchall()
    cur.execute("SELECT * FROM acrescimos ORDER BY nome")
    acrescimos = cur.fetchall()
    return render_template("adicionar_produto.html", categorias=categorias, acrescimos=acrescimos)


@app.route("/gerenciar/produtos/editar/<int:id>", methods=["GET", "POST"])
@gerente_required_decorator
def editar_produto(id):

    con = get_db_connection()
    cur = con.cursor()

    if request.method == "POST":
        nome = request.form["nome"]
        preco = request.form["preco"]
        categoria_id = request.form["categoria_id"]
        destaque = 1 if request.form.get("destaque") == "on" else 0
        acrescimos = request.form.getlist("acrescimos")
        imagem = None

        cur.execute("SELECT imagem FROM produtos WHERE id = ?", (id,))
        imagem_antiga = cur.fetchone()['imagem']
        imagem = imagem_antiga

        if 'imagem' in request.files:
            file = request.files['imagem']
            if file and file.filename != '' and allowed_file(file.filename):
                # Apagar imagem antiga se existir
                if imagem_antiga:
                    try:
                        os.remove(os.path.join(app.config['UPLOAD_FOLDER'], imagem_antiga))
                    except OSError:
                        pass  # Ignora se o arquivo não existir

                filename = secure_filename(file.filename)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                imagem = filename

        cur.execute(
            "UPDATE produtos SET nome = ?, preco = ?, categoria_id = ?, imagem = ?, destaque = ? WHERE id = ?",
            (nome, preco, categoria_id, imagem, destaque, id)
        )

        # Atualizar acrescimos
        cur.execute("DELETE FROM produto_acrescimos WHERE produto_id = ?", (id,))
        for acrescimo_id in acrescimos:
            cur.execute(
                "INSERT INTO produto_acrescimos (produto_id, acrescimo_id) VALUES (?, ?)",
                (id, acrescimo_id)
            )

        con.commit()
        return redirect(url_for("gerenciar_produtos"))

    # Se for GET
    cur.execute("SELECT * FROM produtos WHERE id = ?", (id,))
    produto = cur.fetchone()
    cur.execute("SELECT * FROM categorias ORDER BY nome")
    categorias = cur.fetchall()
    cur.execute("SELECT * FROM acrescimos ORDER BY nome")
    acrescimos = cur.fetchall()
    cur.execute("SELECT acrescimo_id FROM produto_acrescimos WHERE produto_id = ?", (id,))
    produto_acrescimos = [row['acrescimo_id'] for row in cur.fetchall()]

    if not produto:
        return redirect(url_for("gerenciar_produtos"))

    return render_template("editar_produto.html", produto=produto, categorias=categorias, acrescimos=acrescimos, produto_acrescimos=produto_acrescimos)


@app.route("/gerenciar/produtos/excluir/<int:id>")
@gerente_required_decorator
def excluir_produto(id):

    con = get_db_connection()
    cur = con.cursor()

    # Primeiro, pegar o nome do arquivo da imagem para deletar
    cur.execute("SELECT imagem FROM produtos WHERE id = ?", (id,))
    produto = cur.fetchone()

    # Deletar o registro do banco
    cur.execute("DELETE FROM produtos WHERE id = ?", (id,))
    con.commit()

    # Se o produto tinha uma imagem, deletar o arquivo
    if produto and produto['imagem']:
        try:
            os.remove(os.path.join(app.config['UPLOAD_FOLDER'], produto['imagem']))
        except OSError:
            pass  # Ignora se o arquivo não existir

    return redirect(url_for("gerenciar_produtos"))


# ===============================
# GERENCIAR ACRÉSCIMOS
# ===============================
@app.route("/gerenciar_acrescimos")
@gerente_required_decorator
def gerenciar_acrescimos():

    con = get_db_connection()
    cur = con.cursor()

    cur.execute("SELECT * FROM acrescimos ORDER BY nome")
    acrescimos = cur.fetchall()
    return render_template("gerenciar_acrescimos.html", acrescimos=acrescimos)


@app.route("/gerenciar/acrescimos/adicionar", methods=["GET", "POST"])
@gerente_required_decorator
def adicionar_acrescimo():

    if request.method == "POST":
        nome = request.form["nome"]
        preco = request.form["preco"]

        con = get_db_connection()
        cur = con.cursor()
        cur.execute(
            "INSERT INTO acrescimos (nome, preco) VALUES (?, ?)",
            (nome, preco)
        )
        con.commit()
        return redirect(url_for("gerenciar_acrescimos"))

    return render_template("adicionar_acrescimo.html")


@app.route("/gerenciar/acrescimos/editar/<int:id>", methods=["GET", "POST"])
@gerente_required_decorator
def editar_acrescimo(id):

    con = get_db_connection()
    cur = con.cursor()

    if request.method == "POST":
        nome = request.form["nome"]
        preco = request.form["preco"]

        cur.execute(
            "UPDATE acrescimos SET nome = ?, preco = ? WHERE id = ?",
            (nome, preco, id)
        )
        con.commit()
        return redirect(url_for("gerenciar_acrescimos"))

    # Se for GET
    cur.execute("SELECT * FROM acrescimos WHERE id = ?", (id,))
    acrescimo = cur.fetchone()

    if not acrescimo:
        return redirect(url_for("gerenciar_acrescimos"))

    return render_template("editar_acrescimo.html", acrescimo=acrescimo)


@app.route("/gerenciar/acrescimos/excluir/<int:id>")
@gerente_required_decorator
def excluir_acrescimo(id):

    con = get_db_connection()
    cur = con.cursor()
    cur.execute("DELETE FROM acrescimos WHERE id = ?", (id,))
    con.commit()

    return redirect(url_for("gerenciar_acrescimos"))


@app.route("/relatorio/<tipo>")
@login_required_decorator
@gerente_required_decorator
def relatorio(tipo):

    from datetime import date
    hoje = date.today()

    if tipo == "dia":
        filtro = "c.data = ?"
        valor = hoje.strftime("%Y-%m-%d")
        titulo = "📅 Relatório de Hoje"
        filtro_pag = "date(p.data) = ?"

    elif tipo == "mes":
        filtro = "strftime('%Y-%m', c.data) = ?"
        valor = hoje.strftime("%Y-%m")
        titulo = "📆 Relatório do Mês"
        filtro_pag = "strftime('%Y-%m', p.data) = ?"

    elif tipo == "ano":
        filtro = "strftime('%Y', c.data) = ?"
        valor = hoje.strftime("%Y")
        titulo = "🗓 Relatório do Ano"
        filtro_pag = "strftime('%Y', p.data) = ?"

    else:
        return redirect("/")

    con = get_db_connection()
    cur = con.cursor()

    # 🔹 RESUMO
    cur.execute("""
        SELECT 
                        COUNT(DISTINCT c.id) AS total_comandas,
                        SUM(i.qtd * i.preco) AS faturamento
        FROM comandas c
        JOIN itens_comanda i ON i.comanda_id = c.id
                WHERE c.status != 'Aberta' AND """ + filtro, (valor,))
    resumo = cur.fetchone()

    # 🔹 PRODUTOS MAIS VENDIDOS
    cur.execute("""
        SELECT 
            p.nome,
            SUM(i.qtd) AS quantidade,
            SUM(i.qtd * i.preco) AS total
        FROM itens_comanda i
        JOIN produtos p ON p.id = i.produto_id
        JOIN comandas c ON c.id = i.comanda_id
        WHERE c.status != 'Aberta' AND """ + filtro + """
        GROUP BY p.id
        ORDER BY quantidade DESC
    """, (valor,))
    produtos = cur.fetchall()

    # 🔹 PAGAMENTOS POR METODO
    cur.execute("""
        SELECT p.metodo, SUM(p.valor) AS total
        FROM pagamentos p
        JOIN comandas c ON c.id = p.comanda_id
        WHERE c.status != 'Aberta' AND """ + filtro_pag + """
        GROUP BY p.metodo
    """, (valor,))
    pagamentos_raw = cur.fetchall()

    pagamentos_por_metodo = {"Dinheiro": 0.0, "Pix": 0.0, "Cartao": 0.0}
    for row in pagamentos_raw:
        metodo = row["metodo"]
        total_metodo = row["total"] or 0.0
        if metodo in pagamentos_por_metodo:
            pagamentos_por_metodo[metodo] = total_metodo

    # Preparar dados para o gráfico
    top_10_produtos = produtos[:10]
    nomes_produtos = [p["nome"] for p in top_10_produtos]
    quantidades_produtos = [p["quantidade"] for p in top_10_produtos]

    return render_template(
        "relatorio.html",
        titulo=titulo,
        resumo=resumo,
        produtos=produtos,
        pagamentos_por_metodo=pagamentos_por_metodo,
        nomes_produtos=nomes_produtos,
        quantidades_produtos=quantidades_produtos
    )


# ===============================
# EXECUÇÃO
# ===============================


if __name__ == "__main__":
    with app.app_context():
        inicializar_sistema()
        db_inicializado = True
    app.run(host="0.0.0.0", port=5000)
