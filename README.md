# Comanda - acesso remoto

Este projeto roda com Flask e ja esta configurado para aceitar conexoes externas quando iniciado pelo `python app.py`.

Para subir o site:
1. Entre na pasta do app: `cd lanchonete`
2. Inicie o servidor: `python app.py`

Para acessar de outra maquina na mesma rede:
1. Descubra o IP da maquina que esta rodando o servidor (por exemplo, `hostname -I` no Linux ou `ipconfig` no Windows).
2. Acesse `http://SEU_IP:5000`.

Para acesso fora da sua rede, voce precisa liberar a porta 5000 no firewall e no roteador (redirecionamento de porta) ou usar um tunel HTTP.

Variaveis de ambiente disponiveis:
- `COMANDA_HOST` (padrao `0.0.0.0`)
- `COMANDA_PORT` (padrao `5000`)
- `PORT` (sobrescreve `COMANDA_PORT`)
- `COMANDA_SECRET_KEY` (use um valor forte para acesso publico)
- `COMANDA_DEBUG` (`true`/`false`)
- `COMANDA_USE_RELOADER` (`true`/`false`)
