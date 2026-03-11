import sqlite3
from werkzeug.security import generate_password_hash

con = sqlite3.connect("database.db")
cur = con.cursor()

usuario = "admin"
senha = generate_password_hash("1234")

# Check if user already exists
cur.execute("SELECT * FROM usuarios WHERE usuario = ?", (usuario,))
existe = cur.fetchone()

if not existe:
    cur.execute("""
    INSERT INTO usuarios (usuario, senha, tipo)
    VALUES (?, ?, ?)
    """, (usuario, senha, "admin"))
    con.commit()
    print("Usuário criado com sucesso!")
else:
    print(f"Usuário '{usuario}' já existe no banco de dados. Nenhuma ação realizada.")

con.close()
