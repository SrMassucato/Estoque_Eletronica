# 📦 Estoque Eletrônica

Aplicativo web de controle de estoque para produção de peças eletrônicas. Controla a contagem de matéria-prima, registra a produção (descontando automaticamente os materiais usados) e avisa quando é preciso comprar mais.

## ✨ Funcionalidades

- **Matéria-prima:** cadastro com unidade, quantidade, estoque mínimo e custo unitário.
- **Movimentações:** entrada (compra), saída manual (perda/uso avulso) e ajuste de inventário (contagem física).
- **Produtos com receita:** define quanto de cada material é gasto para produzir 1 unidade.
- **Produção:** ao produzir, desconta a matéria-prima da receita (tudo ou nada) e soma ao estoque de produtos acabados.
- **Alertas de estoque baixo:** avisa quando um material chega ao mínimo ou zera.
- **Lista de compras sugerida:** calcula o que comprar e o custo estimado.
- **Simulação de produção:** mostra quantas unidades dá para produzir e o que faltaria.
- **Histórico:** registro de todas as movimentações.
- **Dashboard:** totais, valor do estoque e alertas ativos.

## 🛠️ Tecnologias

- **Backend:** Python 3 + Flask
- **Banco de dados:** SQLite (criado automaticamente)
- **Frontend:** HTML, CSS e JavaScript puro

## 📁 Estrutura do projeto

```
ESTOQUE-ELETRONICA/
├── .gitignore
├── README.md
├── requirements.txt
├── backend/
│   ├── __init__.py
│   └── app.py            # API Flask + regras de negócio
├── frontend/
│   ├── index.html
│   ├── css/
│   │   └── style.css
│   └── js/
│       └── script.js
└── notebooks/
    └── rascunhos.ipynb   # testes e rascunhos
```

## 🚀 Como executar

**Pré-requisito:** Python 3.9 ou superior.

1. Clone ou baixe o projeto e entre na pasta:

   ```bash
   cd ESTOQUE-ELETRONICA
   ```

2. (Opcional) Crie e ative um ambiente virtual:

   ```bash
   python -m venv venv

   # Windows
   venv\Scripts\activate

   # Linux / macOS
   source venv/bin/activate
   ```

3. Instale as dependências:

   ```bash
   pip install -r requirements.txt
   ```

4. Inicie o servidor:

   ```bash
   python backend/app.py
   ```

5. Abra no navegador: **http://127.0.0.1:5000**

O banco `backend/estoque.db` é criado automaticamente na primeira execução.

## 🔌 Endpoints da API

### Matéria-prima

| Método | Rota | Descrição |
|--------|------|-----------|
| GET | `/api/materiais` | Lista materiais (aceita `?q=busca`) |
| POST | `/api/materiais` | Cria material |
| PUT | `/api/materiais/<id>` | Edita dados cadastrais |
| DELETE | `/api/materiais/<id>` | Exclui material |
| POST | `/api/materiais/<id>/entrada` | Registra entrada (compra) |
| POST | `/api/materiais/<id>/saida` | Registra saída manual |
| POST | `/api/materiais/<id>/ajuste` | Ajuste de inventário |

### Produtos e produção

| Método | Rota | Descrição |
|--------|------|-----------|
| GET | `/api/produtos` | Lista produtos com receita e capacidade de produção |
| POST | `/api/produtos` | Cria produto com receita |
| PUT | `/api/produtos/<id>` | Edita produto/receita |
| DELETE | `/api/produtos/<id>` | Exclui produto |
| POST | `/api/producao` | Registra produção e desconta materiais |
| GET | `/api/producao/simular` | Simula uma produção (`?produto_id=1&quantidade=10`) |

### Consultas

| Método | Rota | Descrição |
|--------|------|-----------|
| GET | `/api/alertas` | Materiais com estoque baixo ou zerado |
| GET | `/api/compras` | Lista de compras sugerida (`?fator=2`) |
| GET | `/api/movimentacoes` | Histórico (`?limite=100`) |
| GET | `/api/dashboard` | Resumo geral |

## 📝 Exemplos de uso

**Cadastrar material:**

```bash
curl -X POST http://127.0.0.1:5000/api/materiais \
  -H "Content-Type: application/json" \
  -d '{"nome": "Resistor 10k", "unidade": "un", "quantidade": 500, "estoque_minimo": 100, "custo_unitario": 0.05}'
```

**Cadastrar produto com receita:**

```bash
curl -X POST http://127.0.0.1:5000/api/produtos \
  -H "Content-Type: application/json" \
  -d '{"nome": "Placa Controladora", "receita": [{"material_id": 1, "quantidade": 12}]}'
```

**Registrar produção de 10 unidades:**

```bash
curl -X POST http://127.0.0.1:5000/api/producao \
  -H "Content-Type: application/json" \
  -d '{"produto_id": 1, "quantidade": 10}'
```

Se faltar material, a API retorna erro `409` com a lista do que falta e o máximo possível de produzir, sem descontar nada. Se algum material ficar abaixo do mínimo, a resposta traz os alertas.

## ⚙️ Configuração

No início do `backend/app.py`:

- `FATOR_REPOSICAO` (padrão `2`): a lista de compras sugere repor até `estoque_minimo × FATOR_REPOSICAO`.

## 🗺️ Próximos passos

- [ ] Interface web (frontend)
- [ ] Exportar lista de compras em PDF/Excel
- [ ] Controle de fornecedores
- [ ] Login de usuários

## 👤 Autor

**Bruno Felipe Silva Massucato**
