from flask import Flask, render_template, request, redirect, url_for, session
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime


app = Flask(__name__)
app.secret_key = "segredo_comanda"

# ===============================
# CONEXÃO COM BANCO
# ===============================
def conectar():
    con = sqlite3.connect("database.db")
    con.row_factory = sqlite3.Row
    return con


# ===============================
# CRIA TABELAS
# ===============================
def criar_tabelas():
    con = conectar()
    cur = con.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        usuario TEXT UNIQUE,
        senha TEXT,
        tipo TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS comandas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cliente TEXT,
        cpf TEXT,
        aberta INTEGER,
        data TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS categorias (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS produtos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT,
        preco REAL,
        categoria_id INTEGER
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS itens_comanda (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        comanda_id INTEGER,
        produto_id INTEGER,
        qtd INTEGER,
        preco REAL
    )
    """)

    con.commit()
    con.close()


# ===============================
# CRIAR USUÁRIO PADRÃO
# ===============================
def criar_usuario_padrao():
    con = conectar()
    cur = con.cursor()

    cur.execute("SELECT * FROM usuarios WHERE usuario = 'admin'")
    existe = cur.fetchone()

    if not existe:
        senha_hash = generate_password_hash("123")
        cur.execute(
            "INSERT INTO usuarios (usuario, senha, tipo) VALUES (?, ?, ?)",
            ("admin", senha_hash, "gerente")
        )
        con.commit()

    con.close()


# ===============================
# LOGIN REQUIRED
# ===============================
def login_required():
    return session.get("logado") is True
def gerente_required():
    return session.get("tipo") == "gerente"



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

    con = conectar()
    cur = con.cursor()

    cur.execute("SELECT * FROM usuarios WHERE usuario = ?", (usuario,))
    user = cur.fetchone()
    con.close()

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
def index():
    if not login_required():
        return redirect("/login")

    con = conectar()
    cur = con.cursor()

    cur.execute("SELECT * FROM comandas WHERE aberta = 1 ORDER BY id DESC")
    comandas = cur.fetchall()

    con.close()
    return render_template("index.html", comandas=comandas)


# ===============================
# NOVA COMANDA
# ===============================
@app.route("/nova")
def nova():
    if not login_required():
        return redirect("/login")

    return render_template("nova_comanda.html")


@app.route("/criar_comanda", methods=["POST"])
def criar_comanda():
    if not login_required():
        return redirect("/login")

    nome = request.form["nome"]
    cpf = request.form["cpf"]

    con = conectar()
    cur = con.cursor()

    cur.execute(
        "INSERT INTO comandas (cliente, cpf, aberta, data) VALUES (?, ?, 1, ?)",
        (nome, cpf, datetime.now().strftime("%Y-%m-%d"))
    )

    con.commit()
    comanda_id = cur.lastrowid
    con.close()

    return redirect(url_for("comanda", id=comanda_id))


# ===============================
# VER COMANDA
# ===============================
@app.route("/comanda/<int:id>")
def comanda(id):
    if not login_required():
        return redirect("/login")

    con = conectar()
    cur = con.cursor()

    cur.execute("SELECT * FROM comandas WHERE id = ?", (id,))
    comanda = cur.fetchone()

    cur.execute("""
        SELECT i.id, p.nome, i.qtd, i.preco
        FROM itens_comanda i
        JOIN produtos p ON p.id = i.produto_id
        WHERE i.comanda_id = ?
    """, (id,))
    itens = cur.fetchall()

    # Buscar produtos para o select
    cur.execute("SELECT * FROM produtos")
    produtos = cur.fetchall()

    con.close()

    total = sum(item["qtd"] * item["preco"] for item in itens)

    return render_template(
        "comanda.html",
        comanda=comanda,
        itens=itens,
        produtos=produtos,
        total=total
    )
# ===============================
# LISTAR CATEGORIAS
# ===============================
@app.route("/categorias/<int:id>")
def categorias(id):
    if not login_required():
        return redirect("/login")

    con = conectar()
    cur = con.cursor()

    cur.execute("SELECT * FROM categorias")
    categorias = cur.fetchall()

    con.close()

    return render_template(
        "categorias.html",
        categorias=categorias,
        id=id
    )
# ===============================
# PRODUTOS DA CATEGORIA
# ===============================
@app.route("/produtos/<int:id>/<int:categoria_id>")
def produtos_categoria(id, categoria_id):
    if not login_required():
        return redirect("/login")

    con = conectar()
    cur = con.cursor()

    cur.execute(
        "SELECT * FROM produtos WHERE categoria_id = ?",
        (categoria_id,)
    )
    produtos = cur.fetchall()

    con.close()

    return render_template(
        "produtos.html",
        produtos=produtos,
        id=id
    )


# ===============================
# ADICIONAR ITEM NA COMANDA
# ===============================
@app.route("/confirmar_itens/<int:comanda_id>", methods=["POST"])
def confirmar_itens(comanda_id):
    if not login_required():
        return redirect("/login")

    con = conectar()
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
                    preco = produto["preco"]

                    cur.execute("""
                        INSERT INTO itens_comanda (comanda_id, produto_id, qtd, preco)
                        VALUES (?, ?, ?, ?)
                    """, (comanda_id, produto_id, qtd, preco))

    con.commit()
    con.close()

    return redirect(url_for("comanda", id=comanda_id))
@app.route("/fechar_comanda/<int:id>")
def fechar_comanda(id):
    if not login_required():
        return redirect("/login")

    con = conectar()
    cur = con.cursor()

    cur.execute(
        "UPDATE comandas SET aberta = 0 WHERE id = ?",
        (id,)
    )

    con.commit()
    con.close()

    return redirect(url_for("index"))


# ===============================
# REMOVER ITEM DA COMANDA
# ===============================
@app.route("/remover_item/<int:item_id>/<int:comanda_id>")
def remover_item(item_id, comanda_id):
    if not login_required():
        return redirect("/login")

    con = conectar()
    cur = con.cursor()

    cur.execute("DELETE FROM itens_comanda WHERE id = ?", (item_id,))
    con.commit()
    con.close()

    return redirect(url_for("comanda", id=comanda_id))
def criar_categorias_padrao():
    con = conectar()
    cur = con.cursor()

    categorias = ["Lanches", "Bebidas", "Porções", "Sobremesas"]

    for c in categorias:
        cur.execute(
            "INSERT INTO categorias (nome) SELECT ? WHERE NOT EXISTS (SELECT 1 FROM categorias WHERE nome = ?)",
            (c, c)
        )

    con.commit()
    con.close()
def criar_produtos_padrao():
    con = conectar()
    cur = con.cursor()

    # Buscar IDs das categorias
    cur.execute("SELECT id, nome FROM categorias")
    categorias = {c["nome"]: c["id"] for c in cur.fetchall()}

    produtos = [
        ("X-Burger", 15.00, "Lanches"),
        ("X-Salada", 18.00, "Lanches"),
        ("X-Bacon", 20.00, "Lanches"),

        ("Coca-Cola", 6.00, "Bebidas"),
        ("Catuaba Selvagem", 10.00, "Bebidas"),
        ("Guaraná", 5.00, "Bebidas"),
        ("Suco", 7.00, "Bebidas"),

        ("Batata Frita", 12.00, "Porções"),
        ("Calabresa", 18.00, "Porções"),

        ("Pudim", 8.00, "Sobremesas"),
        ("Sorvete", 7.00, "Sobremesas"),
    ]

    for nome, preco, categoria in produtos:
        cur.execute("""
            INSERT INTO produtos (nome, preco, categoria_id)
            SELECT ?, ?, ?
            WHERE NOT EXISTS (
                SELECT 1 FROM produtos WHERE nome = ?
            )
        """, (nome, preco, categorias[categoria], nome))

    con.commit()
    con.close()
@app.route("/relatorio/<tipo>")
def relatorio(tipo):
    if not login_required():
        return redirect("/login")

    if not gerente_required():
        return redirect("/")

    from datetime import date
    hoje = date.today()

    if tipo == "dia":
        filtro = "c.data = ?"
        valor = hoje.strftime("%Y-%m-%d")
        titulo = "📅 Relatório de Hoje"

    elif tipo == "mes":
        filtro = "strftime('%Y-%m', c.data) = ?"
        valor = hoje.strftime("%Y-%m")
        titulo = "📆 Relatório do Mês"

    elif tipo == "ano":
        filtro = "strftime('%Y', c.data) = ?"
        valor = hoje.strftime("%Y")
        titulo = "🗓 Relatório do Ano"

    else:
        return redirect("/")

    con = conectar()
    cur = con.cursor()

    # 🔹 RESUMO
    cur.execute(f"""
        SELECT 
            COUNT(DISTINCT c.id) AS total_comandas,
            SUM(i.qtd * i.preco) AS faturamento
        FROM comandas c
        JOIN itens_comanda i ON i.comanda_id = c.id
        WHERE c.aberta = 0 AND {filtro}
    """, (valor,))
    resumo = cur.fetchone()

    # 🔹 PRODUTOS MAIS VENDIDOS
    cur.execute(f"""
        SELECT 
            p.nome,
            SUM(i.qtd) AS quantidade,
            SUM(i.qtd * i.preco) AS total
        FROM itens_comanda i
        JOIN produtos p ON p.id = i.produto_id
        JOIN comandas c ON c.id = i.comanda_id
        WHERE c.aberta = 0 AND {filtro}
        GROUP BY p.id
        ORDER BY quantidade DESC
    """, (valor,))
    produtos = cur.fetchall()

    con.close()

    # Preparar dados para o gráfico
    top_10_produtos = produtos[:10]
    nomes_produtos = [p["nome"] for p in top_10_produtos]
    quantidades_produtos = [p["quantidade"] for p in top_10_produtos]

    return render_template(
        "relatorio.html",
        titulo=titulo,
        resumo=resumo,
        produtos=produtos,
        nomes_produtos=nomes_produtos,
        quantidades_produtos=quantidades_produtos
    )

# ===============================
# EXECUÇÃO
# ===============================
if __name__ == "__main__":
    criar_tabelas()
    criar_usuario_padrao()
    criar_categorias_padrao()
    criar_produtos_padrao()
    app.run(host="0.0.0.0", port=5000)
