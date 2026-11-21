"""Monitoramento por unidade, consultas compartilhadas e logs com retenção."""

from collections import defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from gestaolegal.config import Config
from gestaolegal.repositories.djen_monitoramento_repository import (
    DjenMonitoramentoRepository,
)
from gestaolegal.exceptions import (
    ValidationException,
    NotFoundException,
    BusinessLogicException,
)
from gestaolegal.utils.cnj import normalizar_cnj


def agora():
    return datetime.now(ZoneInfo("America/Sao_Paulo")).replace(tzinfo=None)


class DjenMonitoramentoService(DjenMonitoramentoRepository):
    def __init__(self, djen=None):
        super().__init__()
        if djen is None:
            from gestaolegal.services.djen_service import DJENService

            djen = DJENService()
        self.djen = djen

    def reconciliar_processos(self):
        for oab in self.oabs_legadas():
            self._inserir(
                dict(
                    tipo="oab",
                    valor=f"{oab['numero_oab']}/{oab['uf_oab']}",
                    unidade_id=oab["unidade_id"],
                    tribunais=[],
                    ativo=oab["ativo"],
                    criado_em=agora(),
                )
            )
        # Tombstones preservam pausa/remoção mesmo quando o processo segue ativo.
        rows = self.processos_ativos()
        for numero, unidade in set(rows):
            if normalizar_cnj(numero):
                self._inserir(
                    dict(
                        tipo="processo",
                        valor=numero,
                        unidade_id=unidade,
                        tribunais=[],
                        automatico=True,
                        criado_em=agora(),
                    )
                )
        self.session.commit()

    def listar(self, user):
        self.reconciliar_processos()
        rows = self.monitores_visiveis(user)
        resultado = []
        for row in rows:
            item = dict(row)
            item["criado_em"] = row["criado_em"].isoformat()
            item["ultimo_sucesso"] = (
                row["ultimo_sucesso"].isoformat() if row["ultimo_sucesso"] else None
            )
            resultado.append(item)
        return resultado

    def normalizar(self, corpo):
        tipo = corpo.get("tipo")
        valor = corpo.get("valor")
        if tipo not in ("oab", "parte", "processo") or not isinstance(valor, str):
            raise ValidationException("Informe o tipo e o item para consulta")
        valor = " ".join(valor.split())
        if tipo == "oab":
            partes = valor.split("/")
            if len(partes) != 2:
                raise ValidationException("Informe a OAB no formato 123456/MG")
            numero, uf = self.djen._numero_uf(
                dict(numero_oab=partes[0], uf_oab=partes[1])
            )
            valor = f"{numero}/{uf}"
        elif tipo == "processo":
            valor = normalizar_cnj(valor)
            if not valor:
                raise ValidationException("Informe um número CNJ com 20 dígitos")
        elif not 3 <= len(valor) <= 150:
            raise ValidationException("O nome deve ter entre 3 e 150 caracteres")
        else:
            valor = valor.upper()
        return tipo, valor

    def criar(self, corpo, user, unidade):
        tipo, valor = self.normalizar(corpo)
        unidade = corpo.get("unidade_id", unidade)
        if isinstance(unidade, bool) or not isinstance(unidade, int):
            raise ValidationException("Unidade inválida")
        permitida = self.unidade_existe(unidade)
        if not permitida or (
            user.urole != "admin" and unidade not in [un.id for un in user.unidades]
        ):
            raise ValidationException("Unidade não encontrada")
        tribunais = self.djen._parametros_busca(
            ["validar"], agora().date(), agora().date(), corpo.get("tribunais")
        )[3]
        if tipo == "parte" and not tribunais:
            raise ValidationException(
                "Selecione ao menos um tribunal para monitorar o nome"
            )
        if tipo != "parte":
            tribunais = []
        self._inserir(
            dict(
                tipo=tipo,
                valor=valor,
                unidade_id=unidade,
                tribunais=tribunais,
                criado_em=agora(),
            )
        )
        self.reativar(tipo, valor, unidade, tribunais)
        self.session.commit()
        return self.listar(user)

    def alterar(self, id, corpo, user, remover=False):
        row = self.monitor_visivel(id, user)
        if not row:
            raise NotFoundException(resource="Monitoramento", resource_id=id)
        if not remover and not isinstance(corpo.get("ativo"), bool):
            raise ValidationException("Informe se o monitoramento está ativo")
        self.mudar_monitor(
            id, ativo=False if remover else corpo["ativo"], removido=remover
        )
        self.session.commit()

    def _preparar(
        self,
        tipo,
        valor,
        inicio,
        fim,
        tribunal,
        unidades,
        executor,
        modo,
        execucao=None,
    ):
        parametros = dict(
            valor=valor, de=inicio.isoformat() if inicio else None,
            ate=fim.isoformat() if fim else None, tribunal=tribunal
        )
        if inicio is None:
            parametros["historico_completo"] = True
        consultas = []
        for unidade in unidades:
            id = self.djen.acervo.iniciar_consulta(tipo, parametros, unidade, executor)
            self.mudar_consultas(
                [id], modo=modo, execucao_id=execucao, status="aguardando"
            )
            consultas.append(id)
        self.session.commit()
        return consultas

    def _capturar(
        self,
        tipo,
        valor,
        inicio,
        fim,
        tribunal,
        unidades,
        executor,
        modo,
        execucao=None,
        consultas=None,
    ):
        consultas = consultas or self._preparar(
            tipo, valor, inicio, fim, tribunal, unidades, executor, modo, execucao
        )
        self.mudar_consultas(consultas, status="executando", inicio=agora())
        self.session.commit()
        cliente = self.djen.client
        limite_anterior = cliente.max_paginas
        cliente.max_paginas = None
        anterior = cliente.ao_receber_pagina
        from gestaolegal.models.djen import ResultadoCaptura

        operacional = ResultadoCaptura()
        encontradas = novas = 0

        def pagina(itens):
            nonlocal encontradas, novas
            existentes = self.djen.acervo.por_ids_djen([i.id_djen for i in itens])
            self.djen._recebidas_antes.update(existentes)
            for item in itens:
                anterior_item = self.djen.repo.find_by_id_djen(item.id_djen)
                if anterior_item and (
                    anterior_item.ativo != item.ativo
                    or anterior_item.motivo_cancelamento != item.motivo_cancelamento
                ):
                    self.djen._alteracoes_captura.add(item.id_djen)
                if (
                    anterior_item
                    and anterior_item.ativo
                    and not item.ativo
                    and anterior_item.id_caso
                ):
                    self.djen._ao_cancelar(anterior_item, executor)
                pid = self.djen.acervo.guardar(self.djen._dados_publicacao(item))
                for consulta in consultas:
                    self.djen.acervo.resultado(consulta, pid)
                self.djen.registrar(
                    item,
                    operacional,
                    unidade_padrao=unidades[0],
                    oab_origem=valor if tipo == "oab" else None,
                    executor_id=executor,
                    somente_com_processo=modo != "automatico" or tipo == "parte",
                )
            self.djen._depois_da_fonte()
            # Counters describe committed pages even if a later page fails.
            count = len(itens)
            new = sum(i.id_djen not in existentes for i in itens)
            for consulta in consultas:
                self.mudar_consultas(
                    [consulta], encontradas=encontradas + count, novas=novas + new
                )
            self.session.commit()
            encontradas += count
            novas += new

        cliente.ao_receber_pagina = pagina
        status, mensagem = "ok", None
        try:
            filtros = {}
            if inicio is not None and fim is not None:
                filtros.update(
                    dataDisponibilizacaoInicio=inicio.isoformat(),
                    dataDisponibilizacaoFim=fim.isoformat(),
                )
            if tribunal:
                filtros["siglaTribunal"] = tribunal
            if tipo == "oab":
                filtros["numeroOab"], filtros["ufOab"] = valor.split("/")
            elif tipo == "parte":
                filtros["nomeParte"] = valor
            else:
                filtros["numeroProcesso"] = valor
            cliente._paginar(filtros)
            if cliente.truncado:
                status, mensagem = (
                    "parcial",
                    "Limite de páginas atingido; o período será repetido.",
                )
        except Exception as erro:
            self.session.rollback()
            self.djen._descartar_pendencias()
            status, mensagem = "erro", str(erro)[:2000]
        finally:
            cliente.ao_receber_pagina = anterior
            cliente.max_paginas = limite_anterior
        for consulta in consultas:
            self.mudar_consultas(
                [consulta], fim=agora(), status=status, mensagem=mensagem
            )
        self.session.commit()
        return dict(
            status=status,
            encontradas=encontradas,
            novas=novas,
            vinculadas=operacional.vinculadas,
            atualizadas=operacional.atualizadas,
            mensagem=mensagem,
        )

    def buscar(self, corpo, user, unidade):
        tipo, valor = self.normalizar(corpo)
        historico = corpo.get("historico_completo", False)
        if not isinstance(historico, bool) or (historico and tipo != "processo"):
            raise ValidationException("Histórico completo disponível apenas para processos")
        if historico:
            inicio = fim = None
            tribunais = []
        else:
            _, inicio, fim, tribunais = self.djen._parametros_busca(
                ["validar"], corpo.get("de"), corpo.get("ate"), corpo.get("tribunais")
            )
        unidade = corpo.get("unidade_id", unidade)
        if not isinstance(unidade, int) or isinstance(unidade, bool):
            raise ValidationException("Unidade inválida")
        unidade_existe = self.unidade_existe(unidade)
        if not unidade_existe or (
            user.urole != "admin" and unidade not in [un.id for un in user.unidades]
        ):
            raise ValidationException("Unidade não encontrada")
        with self.djen.sincronizacoes.trava_da_rotina() as livre:
            if not livre:
                raise BusinessLogicException(
                    "Há uma consulta DJEN em execução neste NPJ. Tente novamente.",
                    "DJEN_EM_EXECUCAO",
                )
            return [
                self._capturar(
                    tipo, valor, inicio, fim, tribunal, [unidade], user.id, "manual"
                )
                for tribunal in tribunais or [None]
            ]

    def executar(self, janela=None):
        self.reconciliar_processos()
        janela = max(1, janela or Config.DJEN_JANELA_DIAS)
        hoje = agora().date()
        # Caller owns the tenant lock: old unfinished executions cannot still run.
        self.interromper_anteriores()
        inicio = agora()
        id = self.djen.sincronizacoes.registrar(
            dict(
                inicio=inicio,
                status="executando",
                parametros=dict(janela_dias=janela),
                novas=0,
                atualizadas=0,
                vinculadas=0,
            )
        )
        self.session.commit()
        grupos = defaultdict(list)
        rows = self.monitores_ativos()
        ativos = set(self.processos_ativos())
        for row in rows:
            if row["automatico"] and (row["valor"], row["unidade_id"]) not in ativos:
                continue
            for tribunal in row["tribunais"] or [None]:
                grupos[(row["tipo"], row["valor"], tribunal)].append(dict(row))
        resultados, sucessos = [], defaultdict(lambda: True)
        erros = []
        trabalhos = []
        for (tipo, valor, tribunal), itens in grupos.items():
            unidades = sorted({it["unidade_id"] for it in itens})
            if tipo == "processo":
                # `numeroProcesso` devolve o histórico inteiro sem datas, ao custo
                # de uma requisição, igual a uma janela: não há o que fatiar, e
                # consultar tudo cobre o que veio antes do cadastro.
                consultas = self._preparar(
                    tipo, valor, None, None, tribunal, unidades, None, "automatico", id
                )
                trabalhos.append(
                    (tipo, valor, None, None, tribunal, unidades, itens, consultas)
                )
                continue
            inicio_periodo = hoje - timedelta(days=janela - 1)
            for item in itens:
                referencia = item["ultimo_sucesso"] or item["criado_em"].date()
                inicio_periodo = min(inicio_periodo, referencia - timedelta(days=1))
            # OAB e parte só filtram por período: janelas de até 30 dias.
            cursor = inicio_periodo
            while cursor <= hoje:
                fim = min(hoje, cursor + timedelta(days=29))
                consultas = self._preparar(
                    tipo, valor, cursor, fim, tribunal, unidades, None, "automatico", id
                )
                trabalhos.append(
                    (tipo, valor, cursor, fim, tribunal, unidades, itens, consultas)
                )
                cursor = fim + timedelta(days=1)
        for tipo, valor, de, ate, tribunal, unidades, itens, consultas in trabalhos:
            res = self._capturar(
                tipo,
                valor,
                de,
                ate,
                tribunal,
                unidades,
                None,
                "automatico",
                id,
                consultas,
            )
            resultados.append(res)
            if res["status"] != "ok":
                erros.append(
                    f"{'OAB' if tipo == 'oab' else tipo} {valor}: {res['mensagem']}"
                )
            for item in itens:
                sucessos[item["id"]] &= res["status"] == "ok"
        for mid, sucesso in sucessos.items():
            if sucesso:
                self.mudar_monitor(mid, ultimo_sucesso=hoje)
                item = next(row for row in rows if row["id"] == mid)
                if item["tipo"] == "processo":
                    self.concluir_processo(item)
        falhas = sum(res["status"] != "ok" for res in resultados)
        status = (
            "ok"
            if not falhas
            else (
                "erro"
                if all(res["status"] == "erro" for res in resultados)
                else "parcial"
            )
        )
        registro = dict(
            inicio=inicio,
            fim=agora(),
            status=status,
            novas=sum(res["novas"] for res in resultados),
            atualizadas=sum(res["atualizadas"] for res in resultados),
            vinculadas=sum(res["vinculadas"] for res in resultados),
            parametros=dict(janela_dias=janela, consultas=len(resultados)),
            mensagem="\n".join(erros)[:4000] or None,
        )
        self.concluir_execucao(id, registro)
        self.session.commit()
        self.limpar_logs()
        return registro
