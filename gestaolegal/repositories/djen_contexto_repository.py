"""Classificação contextual independente da operação; artefatos JSON, nunca pickle."""

from datetime import datetime
import unicodedata
from sqlalchemy import select, insert, update, func, exists
from gestaolegal.repositories.repository import BaseRepository
from gestaolegal.database.tables import (
    djen_contextos as c,
    djen_publicacao_contextos as r,
    djen_contexto_historico as h,
    djen_publicacoes as p,
    djen_comunicacoes as o,
    djen_modelos as m,
    djen_treinos as t,
)
from gestaolegal.exceptions import ValidationException, NotFoundException


def normalizar(texto):
    return " ".join(
        "".join(
            x
            for x in unicodedata.normalize("NFKD", texto or "")
            if not unicodedata.combining(x)
        )
        .casefold()
        .split()
    )


class DjenContextoRepository(BaseRepository):
    def obter(self, cid, unidade):
        row = (
            self.session.execute(
                self.escopo(
                    select(c).where(c.c.id == cid, c.c.unidade_id == unidade), c
                )
            )
            .mappings()
            .first()
        )
        if not row:
            raise NotFoundException("Contexto", cid)
        return dict(row)

    def criar(self, corpo, unidade):
        nome = corpo.get("nome")
        nomes = corpo.get("nomes", [])
        criterios = self.validar_criterios(corpo["criterios"]) if "criterios" in corpo else None
        descricao = self.validar_descricao(corpo.get("descricao", ""))
        tribunais = corpo.get("tribunais", [])
        if not isinstance(nome, str) or not 3 <= len(nome.strip()) <= 150:
            raise ValidationException("Dê ao contexto um nome de 3 a 150 caracteres")
        if (
            not isinstance(nomes, list)
            or not (0 if criterios is not None else 1) <= len(nomes) <= 20
            or any(
                not isinstance(n, str) or not 3 <= len(n.strip()) <= 150 for n in nomes
            )
        ):
            raise ValidationException("Informe de 1 a 20 nomes ou variações da parte")
        if (
            not isinstance(tribunais, list)
            or len(tribunais) > 100
            or any(
                not isinstance(t, str) or not t.isalnum() or len(t) > 15
                for t in tribunais
            )
        ):
            raise ValidationException("Tribunais inválidos")
        cid = self.session.execute(
            insert(c).values(
                **self.valores(
                    dict(
                        nome=nome.strip(),
                        descricao=descricao, criterios=criterios,
                        nomes=list(dict.fromkeys(n.strip() for n in nomes)),
                        tribunais=list(dict.fromkeys(t.upper() for t in tribunais)),
                        unidade_id=unidade,
                        criado_em=datetime.now(),
                    )
                )
            )
        ).lastrowid
        self.sincronizar(self.obter(cid, unidade))
        self.session.commit()
        return self.obter(cid, unidade)

    def corresponde(self, ctx, pub):
        if ctx["tribunais"] and pub["sigla_tribunal"] not in ctx["tribunais"]:
            return False
        nomes = [normalizar(d.get("nome")) for d in pub["destinatarios"] or []]
        return any(normalizar(n) in nome for n in ctx["nomes"] for nome in nomes)

    def ids_correspondentes(self, ctx, pid=None):
        from gestaolegal.repositories.djen_acervo_repository import DjenAcervoRepository
        repo = DjenAcervoRepository()
        if ctx.get("criterios") is not None:
            criterios = dict(ctx["criterios"])
            nomes = criterios.pop('nomes', [])
            if nomes:
                resultado = set()
                for nome in nomes:
                    resultado.update(self.ids_correspondentes(dict(ctx, criterios={**criterios, 'nome_parte': nome}), pid))
                return resultado
            stmt = repo.consulta_filtrada(ctx["unidade_id"], criterios).with_only_columns(p.c.id)
            if pid is not None:
                stmt = stmt.where(p.c.id == pid)
            return set(self.session.execute(stmt).scalars())
        stmt = self.escopo(select(p.c.id, p.c.sigla_tribunal, p.c.destinatarios)
                           .where(repo.acessivel(ctx["unidade_id"])), p)
        if pid is not None:
            stmt = stmt.where(p.c.id == pid)
        return {pub["id"] for pub in self.session.execute(stmt).mappings() if self.corresponde(ctx, pub)}

    def sincronizar(self, ctx, pid=None):
        correspondentes = self.ids_correspondentes(ctx, pid)
        stmt = self.escopo(select(r).where(r.c.contexto_id == ctx["id"]), r)
        if pid is not None:
            stmt = stmt.where(r.c.id_publicacao == pid)
        existentes = {x["id_publicacao"]: x for x in self.session.execute(stmt).mappings()}
        # As linhas que saem ficam inativas: rótulos e histórico nunca são apagados.
        for ativo in (True, False):
            ids = [x["id"] for pub, x in existentes.items() if (pub in correspondentes) == ativo and bool(x["ativo"]) != ativo]
            for inicio in range(0, len(ids), 500):
                self.session.execute(self.escopo(update(r).where(r.c.id.in_(ids[inicio:inicio + 500])), r).values(ativo=ativo))
        novos = list(correspondentes - existentes.keys())
        if self.session.get_bind().dialect.name == "mysql":
            from sqlalchemy.dialects.mysql import insert as ins
        else:
            from sqlalchemy.dialects.sqlite import insert as ins
        for inicio in range(0, len(novos), 100):
            stmt_insert = ins(r).values([self.valores(dict(id_publicacao=pub, contexto_id=ctx["id"], rotulo="nao_classificado", origem="captura", ativo=True)) for pub in novos[inicio:inicio + 100]])
            if self.session.get_bind().dialect.name == "mysql":
                stmt_insert = stmt_insert.on_duplicate_key_update(id=r.c.id)
            else:
                stmt_insert = stmt_insert.on_conflict_do_nothing()
            self.session.execute(stmt_insert)
        # Compatibilidade dos contextos antigos; contextos por critérios começam sem avaliação.
        if novos and ctx.get("criterios") is None:
            for op in self.session.execute(self.escopo(select(o).where(o.c.id_publicacao.in_(novos), o.c.unidade_id == ctx["unidade_id"], o.c.situacao.in_(["vinculada", "descartada"])), o)).mappings():
                self.rotular(op["id_publicacao"], ctx["id"], "relevante" if op["situacao"] == "vinculada" else "irrelevante", "importacao" if op["situacao"] == "vinculada" else "descarte", op["id_vinculado_por"], inicial=True)

    def sincronizar_publicacao(self, pid):
        for ctx in self.session.execute(self.escopo(select(c), c)).mappings().all():
            self.sincronizar(dict(ctx), pid)

    def rotular(self, pid, cid, rotulo, origem, usuario, inicial=False):
        atual = (
            self.session.execute(
                self.escopo(
                    select(r).where(r.c.ativo.is_(True),r.c.id_publicacao == pid, r.c.contexto_id == cid), r
                ).with_for_update()
            )
            .mappings()
            .first()
        )
        if not atual:
            raise ValidationException("Publicação não pertence ao contexto")
        if inicial and atual["origem"] != "captura":
            return
        if origem != "classificacao" and atual["origem"] == "classificacao":
            return
        if atual["rotulo"] == rotulo and atual["origem"] == origem:
            return
        valores = dict(
            rotulo=rotulo,
            origem=origem,
            id_rotulado_por=usuario,
            rotulado_em=datetime.now(),
        )
        self.session.execute(
            insert(h).values(
                **self.valores(
                    dict(
                        relacao_id=atual["id"],
                        rotulo_anterior=atual["rotulo"],
                        modelo_id=atual["modelo_id"],
                        sugestao=atual["sugestao"],
                        **valores,
                    )
                )
            )
        )
        self.session.execute(
            self.escopo(update(r).where(r.c.id == atual["id"]), r).values(**valores)
        )
        self.session.execute(self.escopo(update(c).where(c.c.id == cid), c).values(avaliacoes_versao=c.c.avaliacoes_versao + 1))

    def relacoes(self, pids, unidade, contexto=None):
        stmt = self.escopo(
            select(r, c.c.nome)
            .select_from(
                r.join(
                    c, (r.c.contexto_id == c.c.id) & (r.c.tenant_id == c.c.tenant_id)
                )
            )
            .where(r.c.ativo.is_(True), r.c.id_publicacao.in_(pids), c.c.unidade_id == unidade),
            r,
            c,
        )
        if contexto:
            stmt = stmt.where(c.c.id == contexto)
        return [dict(x) for x in self.session.execute(stmt).mappings()]

    def preparar_operacao(self, registros, corpo, unidade):
        escolhidos = corpo.get("contexto_ids")
        if escolhidos is not None:
            if not isinstance(escolhidos, list) or any(
                type(i) is not int for i in escolhidos
            ):
                raise ValidationException("Contextos inválidos")
            for cid in escolhidos:
                self.obter(cid, unidade)
            if not escolhidos:
                return {pub["id"]: [] for pub in registros}
        relacoes = self.relacoes([p["id"] for p in registros], unidade)
        resultado = {}
        for pub in registros:
            cids = [
                x["contexto_id"] for x in relacoes if x["id_publicacao"] == pub["id"]
            ]
            if escolhidos is None and len(cids) > 1:
                raise ValidationException(
                    "Escolha os contextos que receberão a avaliação ou somente a operação"
                )
            resultado[pub["id"]] = (
                cids if escolhidos is None else [i for i in cids if i in escolhidos]
            )
        return resultado

    def propagar(self, pid, rotulo, origem, usuario, destinos=None):
        # Capturas/vínculos automáticos alcançam todos os contextos compatíveis.
        # Operações manuais usam o mapa de escolhas validado antes da transação.
        if destinos is not None and not destinos.get(pid):
            return
        if destinos is None:
            self.sincronizar_publicacao(pid)
        stmt = self.escopo(select(r).where(r.c.ativo.is_(True),r.c.id_publicacao == pid), r)
        if destinos is not None:
            stmt = stmt.where(r.c.contexto_id.in_(destinos.get(pid, [])))
        for row in self.session.execute(stmt).mappings().all():
            self.rotular(pid, row["contexto_id"], rotulo, origem, usuario)

    def listar(self, unidade):
        items = []
        for row in self.session.execute(
            self.escopo(select(c).where(c.c.unidade_id == unidade), c)
        ).mappings():
            ctx = dict(row)
            contagens = dict(
                self.session.execute(
                    self.escopo(
                        select(r.c.rotulo, func.count())
                        .where(r.c.contexto_id == ctx["id"], r.c.ativo.is_(True))
                        .group_by(r.c.rotulo),
                        r,
                    )
                ).all()
            )
            ctx["contagens"] = contagens
            modelo = (
                self.session.execute(
                    self.escopo(
                        select(m.c.id, m.c.criado_em, m.c.metricas)
                        .where(m.c.contexto_id == ctx["id"])
                        .order_by(m.c.id.desc())
                        .limit(1),
                        m,
                    )
                )
                .mappings()
                .first()
            )
            ctx["modelo"] = dict(modelo) if modelo else None
            if ctx["modelo"]:
                ctx["modelo"]["metricas"] = {
                    k: v
                    for k, v in self.metricas_publicas(modelo["metricas"]).items()
                }
            ctx["pode_treinar"] = (
                sum(contagens.get(k, 0) for k in ("relevante", "irrelevante")) >= 200
                and min(contagens.get(k, 0) for k in ("relevante", "irrelevante")) >= 50
            )
            ctx["modelo_desatualizado"] = bool(modelo and (modelo["metricas"].get("contexto_versao", 1) != ctx["versao"] or modelo["metricas"].get("avaliacoes_versao", -1) != ctx["avaliacoes_versao"]))
            items.append(ctx)
        return items

    def classificar(self, cid, corpo, unidade, usuario):
        self.obter(cid, unidade)
        from gestaolegal.services.djen_service import DJENService
        from gestaolegal.repositories.djen_acervo_repository import DjenAcervoRepository

        ids = DJENService._ids_selecionados(corpo)
        rotulo = corpo.get("rotulo")
        if rotulo not in ("relevante", "irrelevante", "nao_classificado"):
            raise ValidationException("Rótulo inválido")
        pubs = DjenAcervoRepository().selecionadas(ids, unidade)
        if len(pubs) != len(ids):
            raise ValidationException("Publicação não encontrada")
        try:
            for pub in pubs:
                self.rotular(pub["id"], cid, rotulo, "classificacao", usuario)
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        return {"classificadas": len(pubs)}

    def amostras(self, cid):
        rows = (
            self.session.execute(
                self.escopo(
                    select(
                        p.c.id,
                        p.c.texto_plano,
                        p.c.numero_processo,
                        r.c.rotulo,
                        r.c.origem,
                    )
                    .select_from(
                        p.join(
                            r,
                            (p.c.id == r.c.id_publicacao)
                            & (p.c.tenant_id == r.c.tenant_id),
                        )
                    )
                    .where(
                        r.c.contexto_id == cid, r.c.ativo.is_(True),
                        r.c.rotulo.in_(["relevante", "irrelevante"]),
                    ),
                    p,
                    r,
                )
            )
            .mappings()
            .all()
        )
        return rows

    def salvar_modelo(self, cid, artefato, metricas):
        mid = self.session.execute(
            insert(m).values(
                **self.valores(
                    dict(
                        contexto_id=cid,
                        criado_em=datetime.now(),
                        artefato=artefato,
                        metricas=metricas,
                    )
                )
            )
        ).lastrowid
        return mid

    def ultimo_modelo(self, cid):
        modelo = (
            self.session.execute(
                self.escopo(
                    select(m)
                    .where(m.c.contexto_id == cid)
                    .order_by(m.c.id.desc())
                    .limit(1),
                    m,
                )
            )
            .mappings()
            .first()
        )
        return modelo

    def textos(self, alvos):
        textos = dict(
            self.session.execute(
                self.escopo(
                    select(p.c.id, p.c.texto_plano).where(
                        p.c.id.in_([x["id_publicacao"] for x in alvos])
                    ),
                    p,
                )
            ).all()
        )
        return textos

    def salvar_previsao(self, relacao_id, dados):
        self.session.execute(
            self.escopo(
                update(r).where(
                    r.c.id == relacao_id, r.c.ativo.is_(True),
                    exists(self.escopo(select(c.c.id).select_from(c.join(m, (m.c.contexto_id == c.c.id) & (m.c.tenant_id == c.c.tenant_id))).where(c.c.id == r.c.contexto_id, m.c.id == dados['modelo_id'], func.coalesce(m.c.metricas['contexto_versao'].as_integer(), 1) == c.c.versao), c, m)),
                    r.c.rotulo == "nao_classificado",
                    r.c.modelo_id.is_(None) | (r.c.modelo_id < dados["modelo_id"]),
                ),
                r,
            ).values(**dados)
        )

    def solicitar_treino(self, cid, unidade):
        from uuid import uuid4

        self.obter(cid, unidade)
        # Serialize pedidos do mesmo contexto sem carregar textos na requisição.
        atual = (
            self.session.execute(
                self.escopo(
                    select(c).where(c.c.id == cid, c.c.unidade_id == unidade), c
                ).with_for_update()
            )
            .mappings()
            .one()
        )
        if atual["treino_status"] not in ("na_fila", "executando"):
            contagens = dict(
                self.session.execute(
                    self.escopo(
                        select(r.c.rotulo, func.count())
                        .where(r.c.contexto_id == cid, r.c.ativo.is_(True))
                        .group_by(r.c.rotulo),
                        r,
                    )
                ).all()
            )
            if (
                sum(contagens.get(k, 0) for k in ("relevante", "irrelevante")) < 200
                or min(contagens.get(k, 0) for k in ("relevante", "irrelevante")) < 50
            ):
                raise ValidationException(
                    "Treino exige 200 rótulos, com pelo menos 50 de cada classe"
                )
            token = str(uuid4())
            self.session.execute(insert(t).values(**self.valores(dict(contexto_id=cid, token=token, status="na_fila", etapa="Na fila", solicitado_em=datetime.now(), contexto_snapshot=self.snapshot(atual), logs=[dict(horario=datetime.now().isoformat(), etapa="Na fila", mensagem="Treinamento solicitado; aguardando worker.")]))))
            self.session.execute(
                self.escopo(update(c).where(c.c.id == cid), c).values(
                    treino_status="na_fila",
                    treino_token=token,
                    treino_erro=None,
                    treino_solicitado_em=datetime.now(),
                    treino_iniciado_em=None,
                    treino_finalizado_em=None,
                )
            )
        self.session.commit()
        return self.obter(cid, unidade)

    def iniciar_treino(self, cid, token):
        result = self.session.execute(
            self.escopo(
                update(c).where(
                    c.c.id == cid,
                    c.c.treino_token == token,
                    c.c.treino_status == "na_fila",
                ),
                c,
            ).values(treino_status="executando", treino_iniciado_em=datetime.now())
        )
        if result.rowcount == 1:
            self.atualizar_execucao(cid, token, "Preparar exemplos", 0, "Execução iniciada.", status="executando", iniciado_em=datetime.now())
        self.session.commit()
        return result.rowcount == 1

    def falhar_treino(self, cid, token, mensagem):
        self.session.rollback()
        result = self.session.execute(
            self.escopo(
                update(c).where(
                    c.c.id == cid,
                    c.c.treino_token == token,
                    c.c.treino_status.in_(["na_fila", "executando"]),
                ),
                c,
            ).values(
                treino_status="erro",
                treino_erro=mensagem[:500],
                treino_finalizado_em=datetime.now(),
            )
        )
        if result.rowcount == 1:
            row = self.session.execute(self.escopo(select(t.c.etapas_concluidas).where(t.c.contexto_id == cid, t.c.token == token), t)).first()
            self.atualizar_execucao(cid, token, "Falhou", row[0] if row else 0, mensagem[:500], status="erro", erro=mensagem[:500], finalizado_em=datetime.now())
        self.session.commit()

    def concluir_treino(self, cid, token):
        # Mesmo lock/commit do artefato: um processo cujo prazo expirou não publica.
        atual = self.session.execute(
            self.escopo(
                select(c.c.id).where(
                    c.c.id == cid,
                    c.c.treino_token == token,
                    c.c.treino_status == "executando",
                ),
                c,
            ).with_for_update()
        ).first()
        if not atual:
            raise ValidationException("A execução do treino expirou ou foi substituída")
        self.session.execute(
            self.escopo(update(c).where(c.c.id == cid), c).values(
                treino_status="concluido",
                treino_finalizado_em=datetime.now(),
                treino_erro=None,
            )
        )

    def contextos_do_worker(self):
        return [
            dict(x)
            for x in self.session.execute(
                self.escopo(select(c).order_by(c.c.id), c)
            ).mappings()
        ]

    def lote_previsoes(self, cid, modelo_id, limite=200):
        return [
            dict(x)
            for x in self.session.execute(
                self.escopo(
                    select(r)
                    .where(
                        r.c.contexto_id == cid, r.c.ativo.is_(True),
                        exists(self.escopo(select(c.c.id).select_from(c.join(m, (m.c.contexto_id == c.c.id) & (m.c.tenant_id == c.c.tenant_id))).where(c.c.id == cid, m.c.id == modelo_id, func.coalesce(m.c.metricas['contexto_versao'].as_integer(), 1) == c.c.versao), c, m)),
                        r.c.rotulo == "nao_classificado",
                        (r.c.modelo_id.is_(None) | (r.c.modelo_id < modelo_id)),
                    )
                    .order_by(r.c.id)
                    .limit(limite),
                    r,
                )
            ).mappings()
        ]

    @staticmethod
    def validar_descricao(valor):
        if not isinstance(valor, str) or len(valor) > 2000:
            raise ValidationException('Descrição deve ter até 2000 caracteres')
        return valor.strip()

    @staticmethod
    def validar_criterios(criterios):
        from datetime import date
        permitidos = {'nomes', 'nome_parte', 'polo', 'numero_processo', 'oab', 'tribunal', 'inicio', 'fim', 'fonte'}
        if not isinstance(criterios, dict) or set(criterios) - permitidos:
            raise ValidationException('Critérios inválidos. Situação, classificação e sugestão são filtros de revisão.')
        saida = {}
        for chave, valor in criterios.items():
            if chave == 'nomes':
                if not isinstance(valor, list) or len(valor) > 20 or any(not isinstance(v, str) or not 3 <= len(v.strip()) <= 150 for v in valor):
                    raise ValidationException('Informe até 20 nomes ou variações da parte')
                if valor:
                    saida[chave] = list(dict.fromkeys(v.strip() for v in valor))
            elif chave == 'tribunal':
                if not isinstance(valor, list) or len(valor) > 100 or any(not isinstance(v, str) or not v.isalnum() or len(v) > 15 for v in valor):
                    raise ValidationException('Tribunais inválidos')
                if valor:
                    saida[chave] = sorted(set(v.upper() for v in valor))
            else:
                if not isinstance(valor, str) or len(valor) > 200:
                    raise ValidationException('Valor de filtro inválido')
                if valor.strip():
                    saida[chave] = valor.strip()
        if saida.get('polo') not in (None, 'A', 'P') or (saida.get('polo') and not (saida.get('nome_parte') or saida.get('nomes'))):
            raise ValidationException('Polo exige nome da parte e deve ser ativo ou passivo')
        if saida.get('fonte') not in (None, 'parte', 'oab', 'processo'):
            raise ValidationException('Origem da consulta inválida')
        try:
            for chave in ('inicio', 'fim'):
                if chave in saida:
                    date.fromisoformat(saida[chave])
        except ValueError:
            raise ValidationException('Data inválida')
        if saida.get('inicio') and saida.get('fim') and saida['inicio'] > saida['fim']:
            raise ValidationException('Data inicial deve ser anterior à final')
        return saida

    @staticmethod
    def snapshot(ctx):
        return {k: ctx.get(k) for k in ('nome', 'descricao', 'nomes', 'tribunais', 'criterios', 'versao', 'avaliacoes_versao')}

    def dados_edicao(self, atual, corpo):
        nome = corpo.get('nome', atual['nome'])
        if not isinstance(nome, str) or not 3 <= len(nome.strip()) <= 150:
            raise ValidationException('Dê ao contexto um nome de 3 a 150 caracteres')
        criterios = corpo.get('criterios', atual.get('criterios'))
        if criterios is not None:
            criterios = self.validar_criterios(criterios)
        return dict(atual, nome=nome.strip(), descricao=self.validar_descricao(corpo.get('descricao', atual.get('descricao') or '')), criterios=criterios)

    def previa(self, corpo, unidade, cid=None):
        atual = self.obter(cid, unidade) if cid else dict(nome='Novo contexto', unidade_id=unidade, nomes=[], tribunais=[], criterios={})
        novo = self.dados_edicao(atual, corpo)
        candidatos = self.ids_correspondentes(novo)
        anteriores = set(self.session.execute(self.escopo(select(r.c.id_publicacao).where(r.c.contexto_id == cid, r.c.ativo.is_(True)), r)).scalars()) if cid else set()
        return dict(total=len(candidatos), entram=len(candidatos - anteriores), saem=len(anteriores - candidatos), permanecem=len(candidatos & anteriores))

    def editar(self, cid, corpo, unidade):
        self.obter(cid, unidade)
        atual = dict(self.session.execute(self.escopo(select(c).where(c.c.id == cid), c).with_for_update()).mappings().one())
        if atual['treino_status'] in ('na_fila', 'executando'):
            raise ValidationException('Aguarde o treinamento terminar antes de editar o contexto')
        if corpo.get('versao') != atual['versao']:
            raise ValidationException('O contexto foi alterado. Reabra a edição para conferir a versão atual')
        novo = self.dados_edicao(atual, corpo)
        revisoes = list(atual.get('revisoes') or []) + [dict(self.snapshot(atual), alterado_em=datetime.now().isoformat())]
        self.session.execute(self.escopo(update(c).where(c.c.id == cid), c).values(nome=novo['nome'], descricao=novo['descricao'], criterios=novo['criterios'], versao=atual['versao'] + 1, revisoes=revisoes))
        self.sincronizar(novo)
        self.session.execute(self.escopo(update(r).where(r.c.contexto_id == cid), r).values(modelo_id=None, sugestao=None, probabilidade=None))
        self.session.commit()
        return self.obter(cid, unidade)

    @staticmethod
    def metricas_publicas(metricas):
        return {k: v for k, v in (metricas or {}).items() if k not in ('amostra', 'ids_teste', 'ids_treino')}

    def historico_treinos(self, cid, unidade, pagina=1):
        self.obter(cid, unidade)
        stmt = self.escopo(select(t).where(t.c.contexto_id == cid), t)
        total = self.session.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
        itens = []
        for row in self.session.execute(stmt.order_by(t.c.id.desc()).limit(20).offset((pagina - 1) * 20)).mappings():
            item = dict(row)
            item.pop('token', None)
            item['metricas'] = self.metricas_publicas(item['metricas'])
            itens.append(item)
        return dict(items=itens, total=total, page=pagina, per_page=20)

    def registrar_etapa(self, cid, token, etapa, concluidas, mensagem, **extras):
        if token is None:
            return
        # Fencing: uma execução expirada não pode atualizar o log nem publicar artefato.
        valido = self.session.execute(self.escopo(select(c.c.id).where(c.c.id == cid, c.c.treino_token == token, c.c.treino_status == 'executando'), c).with_for_update()).first()
        if not valido:
            raise ValidationException('A execução do treino expirou ou foi substituída')
        self.atualizar_execucao(cid, token, etapa, concluidas, mensagem, **extras)
        self.session.commit()

    def atualizar_execucao(self, cid, token, etapa, concluidas, mensagem, **extras):
        row = self.session.execute(self.escopo(select(t).where(t.c.contexto_id == cid, t.c.token == token), t).with_for_update()).mappings().first()
        if row:
            logs = list(row['logs']) + [dict(horario=datetime.now().isoformat(), etapa=etapa, mensagem=mensagem)]
            self.session.execute(self.escopo(update(t).where(t.c.id == row['id']), t).values(etapa=etapa, etapas_concluidas=concluidas, logs=logs, **extras))
