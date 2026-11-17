"""
Controle de Estoque - Eletrônica
================================
Backend em Flask + SQLite.

Funcionalidades:
  - Cadastro e contagem de matéria-prima (componentes, estanho, placas etc.)
  - Cadastro de produtos com "receita" (lista de materiais por unidade)
  - Registro de produção: desconta automaticamente a matéria-prima
  - Alertas de estoque baixo e lista de compras sugerida
  - Histórico de movimentações (entradas, saídas, produção)

Como rodar (a partir da pasta raiz do projeto):
    pip install -r requirements.txt      # requirements.txt: Flask
    python backend/app.py

Acesse: http://127.0.0.1:5000  (serve o frontend/index.html)
API:    http://127.0.0.1:5000/api/...
"""

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime

from flask import Flask, jsonify, request, send_from_directory

# --------------------------------------------------------------------------
# Configuração
# --------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(BASE_DIR, "..", "frontend")
DB_PATH = os.path.join(BASE_DIR, "estoque.db")

# Quando o estoque fica <= mínimo, gera alerta.
# A sugestão de compra repõe até (mínimo * FATOR_REPOSICAO).
FATOR_REPOSICAO = 2

app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path="")


# --------------------------------------------------------------------------
# Banco de dados
# --------------------------------------------------------------------------
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def db():
    """Abre conexão, faz commit no sucesso e rollback em erro."""
    conn = get_conn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS materiais (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                nome           TEXT NOT NULL UNIQUE,
                unidade        TEXT NOT NULL DEFAULT 'un',
                quantidade     REAL NOT NULL DEFAULT 0 CHECK (quantidade >= 0),
                estoque_minimo REAL NOT NULL DEFAULT 0 CHECK (estoque_minimo >= 0),
                custo_unitario REAL NOT NULL DEFAULT 0 CHECK (custo_unitario >= 0),
                criado_em      TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS produtos (
                id                 INTEGER PRIMARY KEY AUTOINCREMENT,
                nome               TEXT NOT NULL UNIQUE,
                descricao          TEXT DEFAULT '',
                quantidade_estoque INTEGER NOT NULL DEFAULT 0 CHECK (quantidade_estoque >= 0),
                criado_em          TEXT NOT NULL
            );

            -- Receita: quanto de cada material é gasto para 1 unidade do produto
            CREATE TABLE IF NOT EXISTS receita (
                produto_id  INTEGER NOT NULL REFERENCES produtos(id) ON DELETE CASCADE,
                material_id INTEGER NOT NULL REFERENCES materiais(id) ON DELETE RESTRICT,
                quantidade  REAL NOT NULL CHECK (quantidade > 0),
                PRIMARY KEY (produto_id, material_id)
            );

            CREATE TABLE IF NOT EXISTS movimentacoes (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                tipo        TEXT NOT NULL,   -- entrada | saida | producao | ajuste
                material_id INTEGER REFERENCES materiais(id) ON DELETE SET NULL,
                produto_id  INTEGER REFERENCES produtos(id) ON DELETE SET NULL,
                quantidade  REAL NOT NULL,
                observacao  TEXT DEFAULT '',
                data        TEXT NOT NULL
            );
            """
        )


# --------------------------------------------------------------------------
# Utilitários
# --------------------------------------------------------------------------
def agora():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def erro(msg, status=400):
    return jsonify({"erro": msg}), status


def to_float(valor, campo, minimo=0.0, estrito=False):
    """Converte para float validando. Levanta ValueError com mensagem clara."""
    try:
        v = float(valor)
    except (TypeError, ValueError):
        raise ValueError(f"'{campo}' deve ser um número.")
    if estrito and v <= minimo:
        raise ValueError(f"'{campo}' deve ser maior que {minimo:g}.")
    if not estrito and v < minimo:
        raise ValueError(f"'{campo}' não pode ser menor que {minimo:g}.")
    return v


def material_status(qtd, minimo):
    if qtd <= 0:
        return "zerado"
    if qtd <= minimo:
        return "baixo"
    return "ok"


def row_material(r):
    d = dict(r)
    d["status"] = material_status(d["quantidade"], d["estoque_minimo"])
    return d


def registrar_mov(conn, tipo, quantidade, material_id=None, produto_id=None, obs=""):
    conn.execute(
        "INSERT INTO movimentacoes (tipo, material_id, produto_id, quantidade, observacao, data) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (tipo, material_id, produto_id, quantidade, obs, agora()),
    )


def buscar_receita(conn, produto_id):
    rows = conn.execute(
        """
        SELECT r.material_id, m.nome AS material, m.unidade, r.quantidade,
               m.quantidade AS estoque_atual
        FROM receita r
        JOIN materiais m ON m.id = r.material_id
        WHERE r.produto_id = ?
        ORDER BY m.nome
        """,
        (produto_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def capacidade_producao(itens):
    """Quantas unidades dá para produzir com o estoque atual."""
    if not itens:
        return 0
    return int(min(i["estoque_atual"] // i["quantidade"] for i in itens))


def lista_alertas(conn):
    rows = conn.execute(
        """
        SELECT * FROM materiais
        WHERE quantidade <= estoque_minimo
        ORDER BY (quantidade * 1.0 / CASE WHEN estoque_minimo = 0 THEN 1 ELSE estoque_minimo END), nome
        """
    ).fetchall()
    alertas = []
    for r in rows:
        d = row_material(r)
        d["mensagem"] = (
            f"⚠️ {d['nome']}: restam {d['quantidade']:g} {d['unidade']} "
            f"(mínimo {d['estoque_minimo']:g}). É preciso comprar mais."
        )
        alertas.append(d)
    return alertas


# --------------------------------------------------------------------------
# Frontend
# --------------------------------------------------------------------------
@app.route("/")
def index():
    return send_from_directory(FRONTEND_DIR, "index.html")


# --------------------------------------------------------------------------
# Matéria-prima
# --------------------------------------------------------------------------
@app.get("/api/materiais")
def listar_materiais():
    busca = request.args.get("q", "").strip()
    with db() as conn:
        if busca:
            rows = conn.execute(
                "SELECT * FROM materiais WHERE nome LIKE ? ORDER BY nome", (f"%{busca}%",)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM materiais ORDER BY nome").fetchall()
    return jsonify([row_material(r) for r in rows])


@app.post("/api/materiais")
def criar_material():
    dados = request.get_json(silent=True) or {}
    nome = (dados.get("nome") or "").strip()
    if not nome:
        return erro("O nome é obrigatório.")
    try:
        qtd = to_float(dados.get("quantidade", 0), "quantidade")
        minimo = to_float(dados.get("estoque_minimo", 0), "estoque_minimo")
        custo = to_float(dados.get("custo_unitario", 0), "custo_unitario")
    except ValueError as e:
        return erro(str(e))
    unidade = (dados.get("unidade") or "un").strip()

    try:
        with db() as conn:
            cur = conn.execute(
                "INSERT INTO materiais (nome, unidade, quantidade, estoque_minimo, custo_unitario, criado_em) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (nome, unidade, qtd, minimo, custo, agora()),
            )
            mid = cur.lastrowid
            if qtd > 0:
                registrar_mov(conn, "entrada", qtd, material_id=mid, obs="Estoque inicial")
            row = conn.execute("SELECT * FROM materiais WHERE id = ?", (mid,)).fetchone()
    except sqlite3.IntegrityError:
        return erro(f"Já existe um material chamado '{nome}'.", 409)
    return jsonify(row_material(row)), 201


@app.put("/api/materiais/<int:mid>")
def editar_material(mid):
    """Edita dados cadastrais. Para mexer na quantidade use entrada/saida/ajuste."""
    dados = request.get_json(silent=True) or {}
    with db() as conn:
        atual = conn.execute("SELECT * FROM materiais WHERE id = ?", (mid,)).fetchone()
        if not atual:
            return erro("Material não encontrado.", 404)
        try:
            nome = (dados.get("nome", atual["nome"]) or "").strip()
            if not nome:
                return erro("O nome é obrigatório.")
            unidade = (dados.get("unidade", atual["unidade"]) or "un").strip()
            minimo = to_float(dados.get("estoque_minimo", atual["estoque_minimo"]), "estoque_minimo")
            custo = to_float(dados.get("custo_unitario", atual["custo_unitario"]), "custo_unitario")
        except ValueError as e:
            return erro(str(e))
        try:
            conn.execute(
                "UPDATE materiais SET nome=?, unidade=?, estoque_minimo=?, custo_unitario=? WHERE id=?",
                (nome, unidade, minimo, custo, mid),
            )
        except sqlite3.IntegrityError:
            return erro(f"Já existe um material chamado '{nome}'.", 409)
        row = conn.execute("SELECT * FROM materiais WHERE id = ?", (mid,)).fetchone()
    return jsonify(row_material(row))


@app.delete("/api/materiais/<int:mid>")
def excluir_material(mid):
    try:
        with db() as conn:
            cur = conn.execute("DELETE FROM materiais WHERE id = ?", (mid,))
            if cur.rowcount == 0:
                return erro("Material não encontrado.", 404)
    except sqlite3.IntegrityError:
        return erro("Este material faz parte da receita de algum produto. Remova-o da receita antes.", 409)
    return jsonify({"ok": True})


@app.post("/api/materiais/<int:mid>/entrada")
def entrada_material(mid):
    """Registra compra/recebimento de material."""
    dados = request.get_json(silent=True) or {}
    try:
        qtd = to_float(dados.get("quantidade"), "quantidade", estrito=True)
    except ValueError as e:
        return erro(str(e))
    obs = (dados.get("observacao") or "Entrada de material").strip()
    with db() as conn:
        if not conn.execute("SELECT 1 FROM materiais WHERE id = ?", (mid,)).fetchone():
            return erro("Material não encontrado.", 404)
        conn.execute("UPDATE materiais SET quantidade = quantidade + ? WHERE id = ?", (qtd, mid))
        registrar_mov(conn, "entrada", qtd, material_id=mid, obs=obs)
        row = conn.execute("SELECT * FROM materiais WHERE id = ?", (mid,)).fetchone()
    return jsonify(row_material(row))


@app.post("/api/materiais/<int:mid>/saida")
def saida_material(mid):
    """Baixa manual (perda, uso avulso, descarte...)."""
    dados = request.get_json(silent=True) or {}
    try:
        qtd = to_float(dados.get("quantidade"), "quantidade", estrito=True)
    except ValueError as e:
        return erro(str(e))
    obs = (dados.get("observacao") or "Saída manual").strip()
    with db() as conn:
        row = conn.execute("SELECT * FROM materiais WHERE id = ?", (mid,)).fetchone()
        if not row:
            return erro("Material não encontrado.", 404)
        if row["quantidade"] < qtd:
            return erro(f"Estoque insuficiente: há apenas {row['quantidade']:g} {row['unidade']}.", 409)
        conn.execute("UPDATE materiais SET quantidade = quantidade - ? WHERE id = ?", (qtd, mid))
        registrar_mov(conn, "saida", qtd, material_id=mid, obs=obs)
        row = conn.execute("SELECT * FROM materiais WHERE id = ?", (mid,)).fetchone()
    return jsonify(row_material(row))


@app.post("/api/materiais/<int:mid>/ajuste")
def ajuste_material(mid):
    """Acerto de inventário: define a quantidade contada fisicamente."""
    dados = request.get_json(silent=True) or {}
    try:
        nova = to_float(dados.get("quantidade"), "quantidade")
    except ValueError as e:
        return erro(str(e))
    obs = (dados.get("observacao") or "Ajuste de inventário").strip()
    with db() as conn:
        row = conn.execute("SELECT * FROM materiais WHERE id = ?", (mid,)).fetchone()
        if not row:
            return erro("Material não encontrado.", 404)
        diferenca = nova - row["quantidade"]
        conn.execute("UPDATE materiais SET quantidade = ? WHERE id = ?", (nova, mid))
        registrar_mov(conn, "ajuste", diferenca, material_id=mid,
                      obs=f"{obs} (de {row['quantidade']:g} para {nova:g})")
        row = conn.execute("SELECT * FROM materiais WHERE id = ?", (mid,)).fetchone()
    return jsonify(row_material(row))


# --------------------------------------------------------------------------
# Produtos e receitas
# --------------------------------------------------------------------------
def validar_itens(itens):
    """Valida a lista de itens da receita. Retorna lista limpa."""
    if not isinstance(itens, list) or not itens:
        raise ValueError("Informe ao menos um material na receita.")
    limpos, vistos = [], set()
    for i in itens:
        try:
            mid = int(i.get("material_id"))
        except (TypeError, ValueError, AttributeError):
            raise ValueError("Cada item da receita precisa de 'material_id'.")
        if mid in vistos:
            raise ValueError("Material repetido na receita.")
        vistos.add(mid)
        qtd = to_float(i.get("quantidade"), "quantidade do item", estrito=True)
        limpos.append((mid, qtd))
    return limpos


def salvar_receita(conn, produto_id, itens):
    conn.execute("DELETE FROM receita WHERE produto_id = ?", (produto_id,))
    for mid, qtd in itens:
        if not conn.execute("SELECT 1 FROM materiais WHERE id = ?", (mid,)).fetchone():
            raise ValueError(f"Material id {mid} não existe.")
        conn.execute(
            "INSERT INTO receita (produto_id, material_id, quantidade) VALUES (?, ?, ?)",
            (produto_id, mid, qtd),
        )


def produto_completo(conn, row):
    d = dict(row)
    d["receita"] = buscar_receita(conn, d["id"])
    d["pode_produzir"] = capacidade_producao(d["receita"])
    d["custo_unitario"] = round(
        sum(
            i["quantidade"] * conn.execute(
                "SELECT custo_unitario FROM materiais WHERE id = ?", (i["material_id"],)
            ).fetchone()["custo_unitario"]
            for i in d["receita"]
        ),
        2,
    )
    return d


@app.get("/api/produtos")
def listar_produtos():
    with db() as conn:
        rows = conn.execute("SELECT * FROM produtos ORDER BY nome").fetchall()
        return jsonify([produto_completo(conn, r) for r in rows])


@app.post("/api/produtos")
def criar_produto():
    dados = request.get_json(silent=True) or {}
    nome = (dados.get("nome") or "").strip()
    if not nome:
        return erro("O nome é obrigatório.")
    try:
        itens = validar_itens(dados.get("receita"))
    except ValueError as e:
        return erro(str(e))
    try:
        with db() as conn:
            cur = conn.execute(
                "INSERT INTO produtos (nome, descricao, criado_em) VALUES (?, ?, ?)",
                (nome, (dados.get("descricao") or "").strip(), agora()),
            )
            pid = cur.lastrowid
            salvar_receita(conn, pid, itens)
            row = conn.execute("SELECT * FROM produtos WHERE id = ?", (pid,)).fetchone()
            return jsonify(produto_completo(conn, row)), 201
    except sqlite3.IntegrityError:
        return erro(f"Já existe um produto chamado '{nome}'.", 409)
    except ValueError as e:
        return erro(str(e))


@app.put("/api/produtos/<int:pid>")
def editar_produto(pid):
    dados = request.get_json(silent=True) or {}
    with db() as conn:
        atual = conn.execute("SELECT * FROM produtos WHERE id = ?", (pid,)).fetchone()
        if not atual:
            return erro("Produto não encontrado.", 404)
        nome = (dados.get("nome", atual["nome"]) or "").strip()
        if not nome:
            return erro("O nome é obrigatório.")
        try:
            conn.execute(
                "UPDATE produtos SET nome = ?, descricao = ? WHERE id = ?",
                (nome, (dados.get("descricao", atual["descricao"]) or "").strip(), pid),
            )
            if "receita" in dados:
                salvar_receita(conn, pid, validar_itens(dados["receita"]))
        except sqlite3.IntegrityError:
            return erro(f"Já existe um produto chamado '{nome}'.", 409)
        except ValueError as e:
            return erro(str(e))
        row = conn.execute("SELECT * FROM produtos WHERE id = ?", (pid,)).fetchone()
        return jsonify(produto_completo(conn, row))


@app.delete("/api/produtos/<int:pid>")
def excluir_produto(pid):
    with db() as conn:
        cur = conn.execute("DELETE FROM produtos WHERE id = ?", (pid,))
        if cur.rowcount == 0:
            return erro("Produto não encontrado.", 404)
    return jsonify({"ok": True})


# --------------------------------------------------------------------------
# Produção
# --------------------------------------------------------------------------
@app.post("/api/producao")
def produzir():
    """
    Registra produção de N unidades de um produto.
    Desconta a matéria-prima da receita (tudo ou nada) e devolve
    os alertas de estoque baixo gerados por essa produção.
    """
    dados = request.get_json(silent=True) or {}
    try:
        pid = int(dados.get("produto_id"))
        qtd = int(dados.get("quantidade"))
        if qtd <= 0:
            raise ValueError
    except (TypeError, ValueError):
        return erro("Informe 'produto_id' e 'quantidade' (inteiro maior que zero).")

    with db() as conn:
        produto = conn.execute("SELECT * FROM produtos WHERE id = ?", (pid,)).fetchone()
        if not produto:
            return erro("Produto não encontrado.", 404)

        itens = buscar_receita(conn, pid)
        if not itens:
            return erro("Este produto não tem receita cadastrada.", 409)

        # 1) Verifica se há material suficiente para TODOS os itens
        faltas = []
        for i in itens:
            necessario = i["quantidade"] * qtd
            if i["estoque_atual"] < necessario:
                faltas.append({
                    "material": i["material"],
                    "unidade": i["unidade"],
                    "necessario": necessario,
                    "disponivel": i["estoque_atual"],
                    "faltam": round(necessario - i["estoque_atual"], 4),
                })
        if faltas:
            return jsonify({
                "erro": "Matéria-prima insuficiente para esta produção.",
                "faltas": faltas,
                "max_possivel": capacidade_producao(itens),
            }), 409

        # 2) Desconta matéria-prima
        for i in itens:
            usado = i["quantidade"] * qtd
            conn.execute(
                "UPDATE materiais SET quantidade = quantidade - ? WHERE id = ?",
                (usado, i["material_id"]),
            )
            registrar_mov(
                conn, "producao", usado, material_id=i["material_id"], produto_id=pid,
                obs=f"Consumido na produção de {qtd}x {produto['nome']}",
            )

        # 3) Soma ao estoque do produto acabado
        conn.execute(
            "UPDATE produtos SET quantidade_estoque = quantidade_estoque + ? WHERE id = ?",
            (qtd, pid),
        )

        # 4) Alertas dos materiais usados que ficaram baixos
        ids = [i["material_id"] for i in itens]
        marcadores = ",".join("?" * len(ids))
        baixos = conn.execute(
            f"SELECT * FROM materiais WHERE id IN ({marcadores}) AND quantidade <= estoque_minimo",
            ids,
        ).fetchall()
        alertas = []
        for r in baixos:
            d = row_material(r)
            d["mensagem"] = (
                f"⚠️ {d['nome']}: restam {d['quantidade']:g} {d['unidade']} "
                f"(mínimo {d['estoque_minimo']:g}). É preciso comprar mais."
            )
            alertas.append(d)

        produto = conn.execute("SELECT * FROM produtos WHERE id = ?", (pid,)).fetchone()
        return jsonify({
            "mensagem": f"{qtd} unidade(s) de '{produto['nome']}' produzida(s) com sucesso.",
            "produto": produto_completo(conn, produto),
            "alertas": alertas,
        })


@app.get("/api/producao/simular")
def simular_producao():
    """Simula: dá para produzir N unidades? O que faltaria?"""
    try:
        pid = int(request.args.get("produto_id"))
        qtd = int(request.args.get("quantidade", 1))
        if qtd <= 0:
            raise ValueError
    except (TypeError, ValueError):
        return erro("Informe 'produto_id' e 'quantidade' válidos.")
    with db() as conn:
        if not conn.execute("SELECT 1 FROM produtos WHERE id = ?", (pid,)).fetchone():
            return erro("Produto não encontrado.", 404)
        itens = buscar_receita(conn, pid)
        faltas = []
        for i in itens:
            necessario = i["quantidade"] * qtd
            if i["estoque_atual"] < necessario:
                faltas.append({
                    "material": i["material"],
                    "unidade": i["unidade"],
                    "necessario": necessario,
                    "disponivel": i["estoque_atual"],
                    "faltam": round(necessario - i["estoque_atual"], 4),
                })
        return jsonify({
            "possivel": not faltas and bool(itens),
            "max_possivel": capacidade_producao(itens),
            "faltas": faltas,
        })


# --------------------------------------------------------------------------
# Alertas, compras, histórico, dashboard
# --------------------------------------------------------------------------
@app.get("/api/alertas")
def alertas():
    with db() as conn:
        return jsonify(lista_alertas(conn))


@app.get("/api/compras")
def lista_compras():
    """Lista de compras sugerida: repõe até (mínimo * FATOR_REPOSICAO)."""
    try:
        fator = float(request.args.get("fator", FATOR_REPOSICAO))
    except ValueError:
        fator = FATOR_REPOSICAO
    itens, total = [], 0.0
    with db() as conn:
        for a in lista_alertas(conn):
            alvo = max(a["estoque_minimo"] * fator, a["estoque_minimo"])
            comprar = round(alvo - a["quantidade"], 4)
            if comprar <= 0:
                continue
            custo = round(comprar * a["custo_unitario"], 2)
            total += custo
            itens.append({
                "material_id": a["id"],
                "material": a["nome"],
                "unidade": a["unidade"],
                "estoque_atual": a["quantidade"],
                "estoque_minimo": a["estoque_minimo"],
                "comprar": comprar,
                "custo_estimado": custo,
            })
    return jsonify({"itens": itens, "total_estimado": round(total, 2)})


@app.get("/api/movimentacoes")
def movimentacoes():
    limite = min(request.args.get("limite", default=100, type=int), 1000)
    with db() as conn:
        rows = conn.execute(
            """
            SELECT mv.*, m.nome AS material, p.nome AS produto, m.unidade
            FROM movimentacoes mv
            LEFT JOIN materiais m ON m.id = mv.material_id
            LEFT JOIN produtos  p ON p.id = mv.produto_id
            ORDER BY mv.id DESC LIMIT ?
            """,
            (limite,),
        ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.get("/api/dashboard")
def dashboard():
    with db() as conn:
        total_mat = conn.execute("SELECT COUNT(*) c FROM materiais").fetchone()["c"]
        total_prod = conn.execute("SELECT COUNT(*) c FROM produtos").fetchone()["c"]
        valor = conn.execute(
            "SELECT COALESCE(SUM(quantidade * custo_unitario), 0) v FROM materiais"
        ).fetchone()["v"]
        acabados = conn.execute(
            "SELECT COALESCE(SUM(quantidade_estoque), 0) s FROM produtos"
        ).fetchone()["s"]
        al = lista_alertas(conn)
    return jsonify({
        "total_materiais": total_mat,
        "total_produtos": total_prod,
        "valor_estoque": round(valor, 2),
        "produtos_acabados": acabados,
        "qtd_alertas": len(al),
        "alertas": al,
    })


# --------------------------------------------------------------------------
# Tratamento de erros
# --------------------------------------------------------------------------
@app.errorhandler(404)
def nao_encontrado(_):
    if request.path.startswith("/api/"):
        return erro("Rota não encontrada.", 404)
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.errorhandler(500)
def erro_interno(_):
    return erro("Erro interno no servidor.", 500)


# --------------------------------------------------------------------------
# Execução
# --------------------------------------------------------------------------
init_db()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
