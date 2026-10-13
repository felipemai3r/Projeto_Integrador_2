# Publicação e operação

Como colocar o sistema no ar em um servidor (itens 25 e 26 do cronograma, RNF13) e como mantê-lo. Tudo roda com Docker Compose; o mesmo comando sobe em qualquer máquina com Docker.

## 1. Requisitos do servidor

- Linux com Docker e Docker Compose v2.
- Ligado 24 horas por dia. **A coleta de dados não pode ter lacunas**: cada hora sem coleta é dado perdido.
- Portas 80 e 443 liberadas (ou apenas 80, se o proxy da UDESC fizer o HTTPS).
- Um nome de domínio apontando para o servidor, se for usar o HTTPS automático. O push (notificação no celular) **exige HTTPS**.

## 2. Primeira publicação

```bash
git clone <url-do-repositorio>
cd Projeto_Integrador_2/desenvolvimento
cp .env.example .env
```

Edite o `.env`:

| Variável | O que colocar |
|---|---|
| `POSTGRES_PASSWORD` e `DATABASE_URL` | Senha forte (a mesma nos dois) |
| `JWT_SECRET` | `python3 -c "import secrets;print(secrets.token_urlsafe(48))"` |
| `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY` | `docker compose run --rm api python -m api.gerar_vapid` |
| `VAPID_SUBJECT` | `mailto:` com o e-mail da equipe |
| `URL_PUBLICA` | Endereço público, com `https://` (ex.: `https://rios.exemplo.br`) |
| `DOMINIO` | Só para o HTTPS automático com Caddy |

Suba:

```bash
# sem HTTPS próprio (o proxy da UDESC termina o HTTPS e repassa para a porta 8080)
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

# com HTTPS automático (Let's Encrypt), exige DOMINIO no .env
docker compose -f docker-compose.yml -f docker-compose.prod.yml --profile https up -d --build
```

Depois do primeiro `up`:

```bash
# histórico disponível na API REST (a janela é deslizante: faça no primeiro dia)
docker compose exec ingestor python -m ingestor.carga_inicial --dias 82
# chuva histórica longa (ERA5)
docker compose exec ingestor python -m ingestor.carga_era5 --inicio 2020-11-01
# usuário de moderação (a senha é pedida no terminal)
docker compose exec api python -m api.criar_usuario --email fulano@exemplo.br --nome "Fulano" --papel moderador
```

## 3. O que sobe em produção

| Serviço | Função | Porta pública |
|---|---|---|
| `web` | Nginx: estáticos do PWA, proxy de `/api`, cabeçalhos de segurança | 8080 (ou 80/443 via Caddy) |
| `api` | API FastAPI e avaliador de alertas | nenhuma (só pelo `web`) |
| `ingestor` | Coleta contínua das fontes | nenhuma |
| `db` | PostgreSQL | nenhuma |
| `backup` | `pg_dump` diário, mantém 14 dias no volume `backups` | nenhuma |
| `caddy` (opcional) | HTTPS automático | 80 e 443 |

## 4. Backup e restauração

A base coletada é o ativo mais valioso do projeto e **não é reconstituível** (a API de origem só guarda cerca de 80 dias).

- O serviço `backup` grava um arquivo `.sql.gz` por dia no volume `backups`, mantendo 14 dias. Isso protege contra erro, **não contra perda do servidor**.
- **Copie para fora do servidor.** Exemplo com cron diário:
  ```bash
  # crontab -e
  15 4 * * * cd /caminho/desenvolvimento && DESTINO_REMOTO=usuario@outro-servidor:/backups/pgetulio scripts/backup.sh
  ```
- **Teste a restauração** a cada marco, em um banco novo (nunca sobrescreve o banco em uso):
  ```bash
  scripts/restaurar.sh backups/pgetulio-AAAAMMDD-HHMM.sql.gz
  ```
  O script mostra as contagens de leituras, estações, alertas e ocorrências restauradas.

## 5. Monitoramento

| O que olhar | Como |
|---|---|
| A coleta está viva? | `docker compose logs ingestor` e a tela **Qualidade dos dados** (`/qualidade`). O ingestor registra `COLETA EM SILENCIO` no log quando passa 15 minutos sem leitura nova |
| Alguma fonte quebrou o contrato? | O canário diário (09:00 UTC) registra `canario de contrato` com `ok: false` |
| A API responde? | `curl https://SEU_DOMINIO/api/saude` |
| Há alerta vigente? | `curl https://SEU_DOMINIO/api/alertas?vigentes=true` |

Configure um verificador externo (UptimeRobot ou similar) em `/api/saude`.

## 6. Atualizar

```bash
git pull
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

As migrações do banco rodam sozinhas no serviço `migrate`. O app instalado no celular atualiza na próxima abertura (service worker).

## 7. Segurança: lista de conferência antes de abrir ao público

- [ ] `.env` fora do Git, com senhas e `JWT_SECRET` próprios (nunca os de exemplo).
- [ ] HTTPS ativo e `URL_PUBLICA` com `https://`.
- [ ] Portas do banco e da API **não** publicadas (o arquivo de produção já remove).
- [ ] Usuários de moderação criados com senha de pelo menos 10 caracteres; nenhum usuário de teste.
- [ ] Backup diário funcionando e **restauração testada**.
- [ ] Cópia do backup fora do servidor.
- [ ] Texto da política de privacidade publicado (LGPD): o sistema guarda só o endpoint de notificação, as chaves do navegador e os registros anônimos de alagamento.
- [ ] Limiares conferidos com a Defesa Civil (pendência PE05) antes de divulgar.
