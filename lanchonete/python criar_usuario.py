import sqlite3
from werkzeug.security import generate_password_hash

con = sqlite3.connect("database.db")
cur = con.cursor()

usuario = "admin"
senha = generate_password_hash("1234")

cur.execute("""
INSERT INTO usuarios (usuario, senha, tipo)
VALUES (?, ?, ?)
""", (usuario, senha, "admin"))

con.commit()
con.close()

print("Usuário criado com sucesso!")
