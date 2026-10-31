#!/usr/bin/env bash
# Copia banco e anexos da produção (já fundida) para ./dumps e restaura na
# stack local de desenvolvimento (docker-compose.dev.yml). Não refaz a fusão.
#
# Uso:
#   scripts/producao_para_local.sh tudo
#   scripts/producao_para_local.sh dump
#   scripts/producao_para_local.sh restaurar dumps/producao-AAAAMMDD-HHMMSS.tar
#
# --host     alias SSH do servidor (ou PROD_SSH_HOST, no ambiente ou no .env).
#            "local" usa o Docker desta máquina, para testar o dump.
# --projeto  projeto Compose em produção (ou PROD_COMPOSE_PROJECT; padrão
#            gestaolegal), o rótulo com.docker.compose.project dos containers.
# --sudo     usa "sudo -n docker" no servidor (ou PROD_DOCKER="sudo -n docker").
# --sim      confirma a restauração sem pergunta (para uso não interativo).
#
# O dump só lê a produção: mysqldump com --single-transaction (retrato
# consistente do banco, sem travar a aplicação) e tar dos anexos pelo container
# da API. Os anexos são lidos logo depois do banco; um upload feito entre os
# dois pode aparecer só nos arquivos.
#
# A restauração APAGA o banco local DB_NAME e troca DEV_UPLOADS_PATH. Antes,
# guarda dumps/local-antes-*.sql.gz e move os anexos para dumps/uploads-antes-*.
# O pacote contém dados pessoais reais: fica em dumps/ (ignorado pelo Git), 0600.
set -euo pipefail
umask 077
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."

falha() { echo "producao-para-local: $*" >&2; exit 1; }
info() { echo "producao-para-local: $*" >&2; }

# Variável do ambiente tem prioridade sobre o .env, como no Docker Compose.
env_local() {
    local chave=$1 padrao=${2-}
    if [[ -n ${!chave+x} ]]; then printf '%s' "${!chave}"; return; fi
    local linha
    linha=$(grep -E "^${chave}=" .env 2>/dev/null | tail -n 1 || true)
    if [[ -z $linha ]]; then printf '%s' "$padrao"; return; fi
    linha=${linha#*=}
    linha=${linha%\"}; linha=${linha#\"}; linha=${linha%\'}; linha=${linha#\'}
    printf '%s' "$linha"
}

acao=${1-}
[[ $acao =~ ^(dump|restaurar|tudo)$ ]] || {
    sed -n '2,/^set /{/^set /!p}' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
    exit 2
}
shift
host=$(env_local PROD_SSH_HOST)
projeto=$(env_local PROD_COMPOSE_PROJECT gestaolegal)
docker_remoto=$(env_local PROD_DOCKER docker)
confirmado=0
pacote=
while (($#)); do
    case $1 in
        --host) host=${2-}; shift 2 ;;
        --projeto) projeto=${2-}; shift 2 ;;
        --sudo) docker_remoto="sudo -n docker"; shift ;;
        --sim) confirmado=1; shift ;;
        -*) falha "opção desconhecida: $1" ;;
        *) [[ -z $pacote ]] || falha "argumento a mais: $1"; pacote=$1; shift ;;
    esac
done

mkdir -p dumps
exec 9>dumps/.producao-para-local.lock
flock -n 9 || falha "outra execução está em andamento."

# Roda no servidor (ou local) com sh. Encontra o container pelo rótulo do
# Compose e escreve o conteúdo pedido na saída padrão. Senhas ficam dentro do
# container: nada passa pela linha de comando nem chega a este host.
read -r -d '' SCRIPT_REMOTO <<'REMOTO' || true
set -eu
modo=$1; projeto=$2; shift 2
# $servico lista nomes aceitos: o Compose atual usa db/api; a instalação de
# produção ainda usa gl_db/gl_backend. Usa o primeiro com 1 container ativo.
container() {
    for s in $servico; do
        ids=$("$@" ps -q --filter "label=com.docker.compose.project=$projeto" \
            --filter "label=com.docker.compose.service=$s")
        n=$(printf '%s\n' "$ids" | grep -c . || true)
        [ "$n" = 1 ] && { printf '%s' "$ids"; return; }
        [ "$n" = 0 ] || { echo "há $n containers '$s' em '$projeto'" >&2; exit 3; }
    done
    echo "nenhum container ativo ($servico) no projeto '$projeto'" >&2
    exit 3
}
SERVICOS_DB="db gl_db"
SERVICOS_API="api gl_backend"
case $modo in
sql)
    # O banco é o que a API usa; o MYSQL_DATABASE do MySQL pode ser outro.
    servico=$SERVICOS_API; api=$(container "$@")
    banco=$("$@" exec "$api" printenv DB_NAME) || banco=
    servico=$SERVICOS_DB; c=$(container "$@")
    exec "$@" exec -e "BANCO=$banco" "$c" sh -c '
        set -eu
        banco=${BANCO:-${MYSQL_DATABASE:-gestaolegal}}
        if [ -n "${MYSQL_ROOT_PASSWORD:-}" ] &&
            MYSQL_PWD=$MYSQL_ROOT_PASSWORD mysql -uroot -e "SELECT 1" >/dev/null 2>&1; then
            usuario=root; senha=$MYSQL_ROOT_PASSWORD
        else
            usuario=${MYSQL_USER:?sem credencial no container}; senha=${MYSQL_PASSWORD:?}
        fi
        MYSQL_PWD=$senha exec mysqldump -u"$usuario" --single-transaction --quick \
            --routines --triggers --events --no-tablespaces --set-gtid-purged=OFF \
            --hex-blob --default-character-set=utf8mb4 "$banco"'
    ;;
uploads)
    servico=$SERVICOS_API; c=$(container "$@")
    exec "$@" exec "$c" sh -c '
        raiz=${PRIVATE_FILES_ROOT:-/data/gestaolegal/uploads}
        cd "$raiz" && exec tar -cf - .'
    ;;
esac
echo "modo inválido" >&2; exit 2
REMOTO

remoto() {
    if [[ $host == local ]]; then
        sh -c "$SCRIPT_REMOTO" sh "$@"
    else
        # Argumentos já validados: o shell remoto não precisa de aspas extras.
        ssh -o BatchMode=yes "$host" sh -s -- "$@" <<<"$SCRIPT_REMOTO"
    fi
}

fazer_dump() {
    [[ -n $host ]] || falha "informe --host (alias SSH da produção)."
    [[ -n $projeto ]] || falha "informe --projeto (projeto Compose da produção)."
    [[ $host =~ ^[A-Za-z0-9_.@-]+$ ]] || falha "host inválido: $host"
    [[ $projeto =~ ^[A-Za-z0-9_.-]+$ ]] || falha "projeto inválido: $projeto"
    case $docker_remoto in
        docker | "sudo docker" | "sudo -n docker") ;;
        *) falha "PROD_DOCKER deve ser docker, 'sudo docker' ou 'sudo -n docker'." ;;
    esac
    local carimbo nome tmp
    carimbo=$(date +%Y%m%d-%H%M%S)
    nome=producao-$carimbo
    tmp=$(mktemp -d "dumps/.$nome.XXXXXX")
    trap 'rm -rf -- "$tmp"' EXIT
    # shellcheck disable=SC2086  # docker_remoto é "docker" ou "sudo ... docker"
    {
        info "exportando o banco de $host ($projeto)..."
        remoto sql "$projeto" $docker_remoto | gzip -6 >"$tmp/gestaolegal.sql.gz"
        info "copiando os anexos..."
        remoto uploads "$projeto" $docker_remoto >"$tmp/uploads.tar"
    }
    gzip -t "$tmp/gestaolegal.sql.gz"
    gzip -dc "$tmp/gestaolegal.sql.gz" | tail -n 1 | grep -q '^-- Dump completed' ||
        falha "o mysqldump não terminou (sem '-- Dump completed')."
    tar -tf "$tmp/uploads.tar" >/dev/null || falha "tar de anexos corrompido."
    local revisao arquivos
    revisao=$(gzip -dc "$tmp/gestaolegal.sql.gz" |
        grep -oE "INSERT INTO \`alembic_version\` VALUES \('[0-9a-f]+'\)" |
        grep -oE "[0-9a-f]{6,}" | head -n 1 || true)
    arquivos=$(tar -tf "$tmp/uploads.tar" | grep -vc '/$' || true)
    cat >"$tmp/info.txt" <<INFO
origem: $host
projeto: $projeto
data: $(date -Iseconds)
alembic: ${revisao:-desconhecida}
anexos: $arquivos
INFO
    (cd "$tmp" && sha256sum gestaolegal.sql.gz uploads.tar info.txt >SHA256SUMS)
    tar -cf "dumps/$nome.tar.parcial" -C "$tmp" \
        gestaolegal.sql.gz uploads.tar info.txt SHA256SUMS
    mv "dumps/$nome.tar.parcial" "dumps/$nome.tar"
    chmod 600 "dumps/$nome.tar"
    rm -rf -- "$tmp"; trap - EXIT
    info "pacote: dumps/$nome.tar (alembic ${revisao:-?}, $arquivos anexos)"
    pacote=dumps/$nome.tar
}

restaurar() {
    [[ -f $pacote ]] || falha "pacote não encontrado: ${pacote:-(vazio)}"
    local compose_file banco usuario uploads flask_env
    compose_file=$(env_local LOCAL_COMPOSE_FILE docker-compose.dev.yml)
    banco=$(env_local DB_NAME)
    usuario=$(env_local DB_USER)
    uploads=$(env_local DEV_UPLOADS_PATH ./uploads)
    flask_env=$(env_local FLASK_ENV)
    [[ $flask_env == development ]] ||
        falha "FLASK_ENV=$flask_env; a restauração só roda no ambiente local de desenvolvimento."
    [[ $banco =~ ^[A-Za-z0-9_]+$ ]] || falha "DB_NAME inválido: $banco"
    [[ $usuario =~ ^[A-Za-z0-9_]+$ ]] || falha "DB_USER inválido: $usuario"
    case $banco in mysql | sys | information_schema | performance_schema)
        falha "DB_NAME não pode ser banco do sistema." ;;
    esac
    local compose=(docker compose -f "$compose_file")

    local tmp
    tmp=$(mktemp -d "dumps/.restaurar.XXXXXX")
    trap 'rm -rf -- "$tmp"' EXIT
    tar -xf "$pacote" -C "$tmp"
    (cd "$tmp" && sha256sum -c --quiet SHA256SUMS) || falha "hashes do pacote não conferem."
    gzip -t "$tmp/gestaolegal.sql.gz"
    sed 's/^/  /' "$tmp/info.txt" >&2

    if ((!confirmado)); then
        [[ -t 0 ]] || falha "sem terminal para confirmar; use --sim."
        echo "Isto APAGA o banco local '$banco' e substitui '$uploads'." >&2
        read -r -p "Digite o nome do banco para continuar: " resposta
        [[ $resposta == "$banco" ]] || falha "cancelado."
    fi

    local carimbo
    carimbo=$(date +%Y%m%d-%H%M%S)
    info "parando API e frontend locais..."
    "${compose[@]}" stop api web
    "${compose[@]}" up -d --wait db

    # O SQL não tem CREATE DATABASE/USE: entra no banco definido no .env local.
    local root='MYSQL_PWD=$MYSQL_ROOT_PASSWORD exec mysql -uroot'
    local existe
    existe=$("${compose[@]}" exec -T db sh -c "$root -N -e \"SHOW DATABASES LIKE '$banco'\"")
    if [[ -n $existe ]]; then
        info "guardando o banco local atual em dumps/local-antes-$carimbo.sql.gz..."
        "${compose[@]}" exec -T db sh -c "MYSQL_PWD=\$MYSQL_ROOT_PASSWORD exec mysqldump \
            -uroot --single-transaction --routines --triggers --events \
            --no-tablespaces --set-gtid-purged=OFF $banco" |
            gzip -6 >"dumps/local-antes-$carimbo.sql.gz"
    fi
    info "recriando '$banco' e carregando o SQL..."
    "${compose[@]}" exec -T db sh -c "$root -e \"DROP DATABASE IF EXISTS \\\`$banco\\\`;
        CREATE DATABASE \\\`$banco\\\` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
        GRANT ALL PRIVILEGES ON \\\`$banco\\\`.* TO '$usuario'@'%';\""
    gzip -dc "$tmp/gestaolegal.sql.gz" | "${compose[@]}" exec -T db sh -c "$root $banco"

    info "trocando os anexos em $uploads..."
    if [[ -e $uploads ]]; then
        mv -- "$uploads" "dumps/uploads-antes-$carimbo"
        info "anexos anteriores: dumps/uploads-antes-$carimbo"
    fi
    mkdir -p -- "$uploads"
    tar -xf "$tmp/uploads.tar" -C "$uploads" --no-same-owner

    info "aplicando migrations do checkout e subindo a stack..."
    "${compose[@]}" run --rm --no-deps migrate
    "${compose[@]}" up -d
    rm -rf -- "$tmp"; trap - EXIT
    info "pronto. E-mails locais vão para o Mailpit; as senhas são as da produção."
}

case $acao in
    dump) fazer_dump ;;
    restaurar) restaurar ;;
    tudo) fazer_dump; restaurar ;;
esac
