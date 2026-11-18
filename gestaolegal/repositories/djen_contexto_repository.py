"""Classificação contextual independente da operação; artefatos JSON, nunca pickle."""

from datetime import datetime
import unicodedata
from sqlalchemy import select, insert, update, func
from gestaolegal.repositories.repository import BaseRepository
from gestaolegal.database.tables import (
    djen_contextos as c,
    djen_publicacao_contextos as r,
    djen_contexto_historico as h,
    djen_publicacoes as p,
    djen_comunicacoes as o,
    djen_modelos as m,
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
        nomes = corpo.get("nomes")
        tribunais = corpo.get("tribunais", [])
        if not isinstance(nome, str) or not 3 <= len(nome.strip()) <= 150:
            raise ValidationException("Dê ao contexto um nome de 3 a 150 caracteres")
        if (
            not isinstance(nomes, list)
            or not 1 <= len(nomes) <= 20
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

    def sincronizar(self, ctx, pid=None):
        from gestaolegal.repositories.djen_acervo_repository import DjenAcervoRepository

        stmt = self.escopo(
            select(p.c.id, p.c.sigla_tribunal, p.c.destinatarios).where(
                DjenAcervoRepository().acessivel(ctx["unidade_id"])
            ),
            p,
        )
        if pid is not None:
            stmt = stmt.where(p.c.id == pid)
        if ctx["tribunais"]:
            stmt = stmt.where(p.c.sigla_tribunal.in_(ctx["tribunais"]))
        # A associação examina somente metadados, sem carregar os textos integrais.
        for pub in self.session.execute(stmt).mappings():
            if not self.corresponde(ctx, pub):
                continue
            existente = self.session.execute(
                self.escopo(
                    select(r.c.id).where(
                        r.c.id_publicacao == pub["id"], r.c.contexto_id == ctx["id"]
                    ),
                    r,
                )
            ).first()
            valores = self.valores(
                dict(
                    id_publicacao=pub["id"],
                    contexto_id=ctx["id"],
                    rotulo="nao_classificado",
                    origem="captura",
                )
            )
            if self.session.get_bind().dialect.name == "mysql":
                from sqlalchemy.dialects.mysql import insert as ins

                stmt_insert = (
                    ins(r).values(**valores).on_duplicate_key_update(id=r.c.id)
                )
            else:
                from sqlalchemy.dialects.sqlite import insert as ins

                stmt_insert = ins(r).values(**valores).on_conflict_do_nothing()
            self.session.execute(stmt_insert)
            op = (
                self.session.execute(
                    self.escopo(
                        select(o).where(
                            o.c.id_publicacao == pub["id"],
                            o.c.unidade_id == ctx["unidade_id"],
                        ),
                        o,
                    )
                )
                .mappings()
                .first()
            )
            if not existente and op and op["situacao"] in ("vinculada", "descartada"):
                self.rotular(
                    pub["id"],
                    ctx["id"],
                    "relevante" if op["situacao"] == "vinculada" else "irrelevante",
                    "importacao" if op["situacao"] == "vinculada" else "descarte",
                    op["id_vinculado_por"],
                    inicial=True,
                )

    def sincronizar_publicacao(self, pid):
        for ctx in self.session.execute(self.escopo(select(c), c)).mappings().all():
            self.sincronizar(dict(ctx), pid)

    def rotular(self, pid, cid, rotulo, origem, usuario, inicial=False):
        atual = (
            self.session.execute(
                self.escopo(
                    select(r).where(r.c.id_publicacao == pid, r.c.contexto_id == cid), r
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

    def relacoes(self, pids, unidade, contexto=None):
        stmt = self.escopo(
            select(r, c.c.nome)
            .select_from(
                r.join(
                    c, (r.c.contexto_id == c.c.id) & (r.c.tenant_id == c.c.tenant_id)
                )
            )
            .where(r.c.id_publicacao.in_(pids), c.c.unidade_id == unidade),
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
        stmt = self.escopo(select(r).where(r.c.id_publicacao == pid), r)
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
                        .where(r.c.contexto_id == ctx["id"])
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
                    for k, v in modelo["metricas"].items()
                    if k not in ("amostra", "ids_teste")
                }
            ctx["pode_treinar"] = (
                sum(contagens.get(k, 0) for k in ("relevante", "irrelevante")) >= 200
                and min(contagens.get(k, 0) for k in ("relevante", "irrelevante")) >= 50
            )
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
                        r.c.contexto_id == cid,
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
                    r.c.id == relacao_id,
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
                        .where(r.c.contexto_id == cid)
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
            self.session.execute(
                self.escopo(update(c).where(c.c.id == cid), c).values(
                    treino_status="na_fila",
                    treino_token=str(uuid4()),
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
        self.session.commit()
        return result.rowcount == 1

    def falhar_treino(self, cid, token, mensagem):
        self.session.rollback()
        self.session.execute(
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
                        r.c.contexto_id == cid,
                        r.c.rotulo == "nao_classificado",
                        (r.c.modelo_id.is_(None) | (r.c.modelo_id < modelo_id)),
                    )
                    .order_by(r.c.id)
                    .limit(limite),
                    r,
                )
            ).mappings()
        ]
