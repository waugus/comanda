function alterarQtd(id, valor) {
    const input = document.getElementById("qtd_" + id);
    if (!input) return;
    let atual = parseInt(input.value, 10) || 0;
    atual += valor;
    if (atual < 1) atual = 1;
    input.value = atual;
}

function atualizarTotal(id) {
    const input = document.getElementById("acrescimo_valor_" + id);
    if (!input) return;
    const base = parseFloat(input.dataset.base) || 0;
    const extra = parseFloat(input.value || "0") || 0;
    const total = Math.max(0, base + extra);
    const alvo = document.getElementById("total_" + id);
    if (alvo) {
        alvo.textContent = total.toFixed(2);
    }
}

function formatarMoeda(valor) {
    return `R$ ${Number(valor || 0).toFixed(2)}`.replace(".", ",");
}

// Atualiza o carrinho lateral com dados do backend sem recarregar a pagina.
async function atualizarCarrinhoLateral() {
    const body = document.getElementById("pedidoCartBody");
    const totalEl = document.getElementById("pedidoCartTotal");
    const root = document.body;
    if (!body || !totalEl || !root) return;

    const cartUrl = root.dataset.cartUrl;
    const uploadsUrl = root.dataset.uploadsUrl || "";
    if (!cartUrl) return;

    try {
        const resp = await fetch(cartUrl, { cache: "no-store" });
        if (!resp.ok) return;
        const data = await resp.json();
        const countEl = document.querySelector(".pedido-cart-header p");
        if (countEl) countEl.textContent = `${data.count} itens`;
        totalEl.textContent = formatarMoeda(data.total);

        if (!data.items || data.items.length === 0) {
            body.innerHTML = `
                <div class="pedido-cart-empty">
                    <p>Seu carrinho está vazio.</p>
                    <span>Adicione itens para continuar.</span>
                </div>
            `;
            return;
        }

        body.innerHTML = data.items
            .map((item) => {
                const img = item.imagem
                    ? `<img src="${uploadsUrl}${item.imagem}" alt="${item.nome}">`
                    : `<div class="pedido-imagem-placeholder pequeno"></div>`;
                const extras = item.acrescimos_texto
                    ? `<small>Extras: ${item.acrescimos_texto}</small>`
                    : "";
                return `
                    <div class="pedido-cart-item">
                        ${img}
                        <div class="pedido-cart-info">
                            <strong>${item.nome}</strong>
                            <span>${item.qtd} x ${formatarMoeda(item.preco)}</span>
                            ${extras}
                        </div>
                        <form method="post" action="${item.remove_url}">
                            <button class="pedido-remover" type="submit">✕</button>
                        </form>
                    </div>
                `;
            })
            .join("");
    } catch (err) {
        return;
    }
}

document.addEventListener("DOMContentLoaded", () => {
    // Mantem o total do produto coerente com acrescimos selecionados.
    const listas = document.querySelectorAll(".acrescimos-lista");
    listas.forEach((lista) => {
        const id = lista.dataset.produto;
        const texto = document.getElementById("acrescimos_texto_" + id);
        const valor = document.getElementById("acrescimo_valor_" + id);
        const checkboxes = lista.querySelectorAll("input[type='checkbox']");
        const atualizar = () => {
            let total = 0;
            const nomes = [];
            checkboxes.forEach((cb) => {
                if (cb.checked) {
                    const partes = cb.value.split("|");
                    const nome = partes[0] || "";
                    const preco = parseFloat(partes[1] || "0") || 0;
                    if (nome) nomes.push(nome);
                    total += preco;
                }
            });
            if (texto) texto.value = nomes.join(", ");
            if (valor) valor.value = total.toFixed(2);
            atualizarTotal(id);
        };
        checkboxes.forEach((cb) => cb.addEventListener("change", atualizar));
        atualizar();
    });

    const forms = document.querySelectorAll(".pedido-card-form");
    forms.forEach((form) => {
        form.addEventListener("submit", () => {
            setTimeout(atualizarCarrinhoLateral, 400);
        });
    });

    const cartBody = document.getElementById("pedidoCartBody");
    if (cartBody) {
        cartBody.addEventListener("submit", async (event) => {
            const form = event.target;
            if (!(form instanceof HTMLFormElement)) return;
            event.preventDefault();
            try {
                await fetch(form.action, { method: "POST" });
            } catch (err) {
                return;
            }
            atualizarCarrinhoLateral();
        });
    }
    atualizarCarrinhoLateral();
});
