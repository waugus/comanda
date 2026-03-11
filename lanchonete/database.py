import sqlite3
from flask import g
from werkzeug.security import generate_password_hash
from datetime import datetime
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "database.db")


def get_db_connection():
    # Adiciona um timeout de 10 segundos para evitar "database is locked"
    if 'db' not in g:
        g.db = sqlite3.connect(DB_PATH, timeout=10)
        g.db.row_factory = sqlite3.Row
    return g.db

def close_connection(exception):
    db = getattr(g, 'db', None)
    if db is not None:
        db.close()


def migrar_db_imagem():
    con = get_db_connection()
    cur = con.cursor()
    try:
        cur.execute("PRAGMA table_info(produtos)")
        columns = [row[1] for row in cur.fetchall()]
        if 'imagem' not in columns:
            cur.execute("ALTER TABLE produtos ADD COLUMN imagem TEXT")
            con.commit()
            print("Coluna 'imagem' adicionada à tabela 'produtos'.")
    except Exception as e:
        print(f"Erro ao migrar o banco de dados para imagens: {e}")


def migrar_db_destaque_produto():
    con = get_db_connection()
    cur = con.cursor()
    try:
        cur.execute("PRAGMA table_info(produtos)")
        columns = [row[1] for row in cur.fetchall()]
        if 'destaque' not in columns:
            cur.execute("ALTER TABLE produtos ADD COLUMN destaque INTEGER DEFAULT 0")
            con.commit()
            print("Coluna 'destaque' adicionada à tabela 'produtos'.")
    except Exception as e:
        print(f"Erro ao migrar o banco de dados para destaque de produto: {e}")


def migrar_db_status_comanda():
    con = get_db_connection()
    cur = con.cursor()
    try:
        cur.execute("PRAGMA table_info(comandas)")
        columns = [row[1] for row in cur.fetchall()]
        if 'status' not in columns:
            cur.execute("ALTER TABLE comandas ADD COLUMN status TEXT DEFAULT 'Aberta'")
            # Update existing 'aberta' to 'status'
            cur.execute("UPDATE comandas SET status = 'Fechada' WHERE aberta = 0")
            cur.execute("UPDATE comandas SET status = 'Aberta' WHERE aberta = 1")  # Should already be default
            con.commit()
            print("Coluna 'status' adicionada e migrada na tabela 'comandas'.")
    except Exception as e:
        print(f"Erro ao migrar o banco de dados para o status da comanda: {e}")


def migrar_db_imagem_categoria():
    con = get_db_connection()
    cur = con.cursor()
    try:
        cur.execute("PRAGMA table_info(categorias)")
        columns = [row[1] for row in cur.fetchall()]
        if 'imagem' not in columns:
            cur.execute("ALTER TABLE categorias ADD COLUMN imagem TEXT")
            con.commit()
            print("Coluna 'imagem' adicionada à tabela 'categorias'.")
    except Exception as e:
        print(f"Erro ao migrar o banco de dados para imagem de categoria: {e}")


def migrar_db_pagamentos():
    con = get_db_connection()
    cur = con.cursor()
    try:
        cur.execute("""
        CREATE TABLE IF NOT EXISTS pagamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            comanda_id INTEGER,
            valor REAL,
            metodo TEXT,
            data TEXT,
            FOREIGN KEY (comanda_id) REFERENCES comandas (id)
        )
        """)
        con.commit()
        print("Tabela 'pagamentos' criada ou já existente.")
    except Exception as e:
        print(f"Erro ao criar a tabela 'pagamentos': {e}")


def migrar_db_personalizacoes():
    con = get_db_connection()
    cur = con.cursor()
    try:
        cur.execute("""
        CREATE TABLE IF NOT EXISTS item_personalizacoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_comanda_id INTEGER,
            tipo TEXT,
            texto TEXT,
            FOREIGN KEY (item_comanda_id) REFERENCES itens_comanda (id)
        )
        """)
        con.commit()
        print("Tabela 'item_personalizacoes' criada ou já existente.")
    except Exception as e:
        print(f"Erro ao criar a tabela 'item_personalizacoes': {e}")


def migrar_db_pedidos_online():
    con = get_db_connection()
    cur = con.cursor()
    try:
        cur.execute("""
        CREATE TABLE IF NOT EXISTS pedidos_online (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            comanda_id INTEGER,
            nome TEXT,
            telefone TEXT,
            tipo TEXT,
            endereco TEXT,
            status TEXT DEFAULT 'Recebido',
            criado_em TEXT,
            atualizado_em TEXT,
            FOREIGN KEY (comanda_id) REFERENCES comandas (id)
        )
        """)
        con.commit()
        print("Tabela 'pedidos_online' criada ou já existente.")
    except Exception as e:
        print(f"Erro ao criar a tabela 'pedidos_online': {e}")


def migrar_db_bairros_entrega():
    con = get_db_connection()
    cur = con.cursor()
    try:
        cur.execute("""
        CREATE TABLE IF NOT EXISTS bairros_entrega (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT,
            taxa REAL,
            tempo_entrega TEXT,
            tempo_retirada TEXT,
            ativo INTEGER DEFAULT 1
        )
        """)

        cur.execute("PRAGMA table_info(pedidos_online)")
        columns = [row[1] for row in cur.fetchall()]
        if 'bairro' not in columns:
            cur.execute("ALTER TABLE pedidos_online ADD COLUMN bairro TEXT")
        if 'taxa_entrega' not in columns:
            cur.execute("ALTER TABLE pedidos_online ADD COLUMN taxa_entrega REAL")
        if 'tempo_entrega' not in columns:
            cur.execute("ALTER TABLE pedidos_online ADD COLUMN tempo_entrega TEXT")
        if 'tempo_retirada' not in columns:
            cur.execute("ALTER TABLE pedidos_online ADD COLUMN tempo_retirada TEXT")
        if 'maps_url' not in columns:
            cur.execute("ALTER TABLE pedidos_online ADD COLUMN maps_url TEXT")
        if 'latitude' not in columns:
            cur.execute("ALTER TABLE pedidos_online ADD COLUMN latitude REAL")
        if 'longitude' not in columns:
            cur.execute("ALTER TABLE pedidos_online ADD COLUMN longitude REAL")

        con.commit()
        print("Tabela 'bairros_entrega' criada ou já existente e colunas de pedidos_online atualizadas.")
    except Exception as e:
        print(f"Erro ao migrar o banco de dados para bairros de entrega: {e}")


def migrar_db_itens_comanda_texto():
    con = get_db_connection()
    cur = con.cursor()
    try:
        cur.execute("PRAGMA table_info(itens_comanda)")
        columns = [row[1] for row in cur.fetchall()]
        if 'acrescimos' not in columns:
            cur.execute("ALTER TABLE itens_comanda ADD COLUMN acrescimos TEXT")
        if 'observacoes' not in columns:
            cur.execute("ALTER TABLE itens_comanda ADD COLUMN observacoes TEXT")
        con.commit()
        print("Colunas 'acrescimos' e 'observacoes' adicionadas à tabela 'itens_comanda' (se necessário).")
    except Exception as e:
        print(f"Erro ao migrar o banco de dados para acrescimos/observacoes: {e}")


def criar_tabelas():
    con = get_db_connection()
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
        data TEXT,
        status TEXT DEFAULT 'Aberta'
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS categorias (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT,
        imagem TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS produtos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT,
        preco REAL,
        categoria_id INTEGER,
        imagem TEXT,
        destaque INTEGER DEFAULT 0
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS acrescimos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT,
        preco REAL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS produto_acrescimos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        produto_id INTEGER,
        acrescimo_id INTEGER
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS itens_comanda (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        comanda_id INTEGER,
        produto_id INTEGER,
        qtd INTEGER,
        preco REAL,
        acrescimos TEXT,
        observacoes TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS item_acrescimos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        item_comanda_id INTEGER,
        acrescimo_id INTEGER
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS item_personalizacoes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        item_comanda_id INTEGER,
        tipo TEXT,
        texto TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS pedidos_online (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        comanda_id INTEGER,
        nome TEXT,
        telefone TEXT,
        tipo TEXT,
        endereco TEXT,
        bairro TEXT,
        taxa_entrega REAL,
        tempo_entrega TEXT,
        tempo_retirada TEXT,
        maps_url TEXT,
        latitude REAL,
        longitude REAL,
        status TEXT DEFAULT 'Recebido',
        criado_em TEXT,
        atualizado_em TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS bairros_entrega (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT,
        taxa REAL,
        tempo_entrega TEXT,
        tempo_retirada TEXT,
        ativo INTEGER DEFAULT 1
    )
    """)

    con.commit()


def criar_usuario_padrao():
    con = get_db_connection()
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


def criar_garcom_padrao():
    con = get_db_connection()
    cur = con.cursor()

    cur.execute("SELECT * FROM usuarios WHERE usuario = 'garcom'")
    existe = cur.fetchone()

    if not existe:
        senha_hash = generate_password_hash("123")
        cur.execute(
            "INSERT INTO usuarios (usuario, senha, tipo) VALUES (?, ?, ?)",
            ("garcom", senha_hash, "garcom")
        )
        con.commit()


def criar_motoboy_padrao():
    con = get_db_connection()
    cur = con.cursor()

    cur.execute("SELECT * FROM usuarios WHERE usuario = 'motoboy'")
    existe = cur.fetchone()

    if not existe:
        senha_hash = generate_password_hash("123")
        cur.execute(
            "INSERT INTO usuarios (usuario, senha, tipo) VALUES (?, ?, ?)",
            ("motoboy", senha_hash, "motoboy")
        )
        con.commit()


def criar_categorias_padrao():
    con = get_db_connection()
    cur = con.cursor()

    categorias = ["Lanches", "Bebidas", "Porções", "Sobremesas"]

    for c in categorias:
        cur.execute(
            "INSERT INTO categorias (nome) SELECT ? WHERE NOT EXISTS (SELECT 1 FROM categorias WHERE nome = ?)",
            (c, c)
        )

    con.commit()


def criar_produtos_padrao():
    con = get_db_connection()
    cur = con.cursor()

    # Buscar IDs das categorias
    cur.execute("SELECT id, nome FROM categorias")
    categorias = {c["nome"]: c["id"] for c in cur.fetchall()}

    produtos = [
        ("X-Burger", 15.00, "Lanches", None),
        ("X-Salada", 18.00, "Lanches", None),
        ("X-Bacon", 20.00, "Lanches", None),

        ("Coca-Cola", 6.00, "Bebidas", None),
        ("Guaraná", 5.00, "Bebidas", None),
        ("Suco", 7.00, "Bebidas", None),

        ("Batata Frita", 12.00, "Porções", None),
        ("Calabresa", 18.00, "Porções", None),

        ("Pudim", 8.00, "Sobremesas", None),
        ("Sorvete", 7.00, "Sobremesas", None),
    ]

    for nome, preco, categoria, imagem in produtos:
        cur.execute("""
            INSERT INTO produtos (nome, preco, categoria_id, imagem, destaque)
            SELECT ?, ?, ?, ?, 0
            WHERE NOT EXISTS (
                SELECT 1 FROM produtos WHERE nome = ?
            )
        """, (nome, preco, categorias[categoria], imagem, nome))

    con.commit()
