"""Acervo persistente DJEN, classificação auditada e consultas, por NPJ."""

from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import insert, select, update, func, exists

from gestaolegal.database.tables import (
    djen_publicacoes as p,
    djen_publicacao_unidades as acesso,
    djen_classificacoes as c,
    djen_classificacao_historico as h,
    djen_consultas as q,
    djen_consulta_resultados as r,
    djen_comunicacoes as o,
)
from gestaolegal.repositories.repository import BaseRepository
from gestaolegal.repositories.djen_filtros import filtrar_identificacao


class DjenAcervoRepository(BaseRepository):
    def guardar(self, dados):
        """Upsert concorrente sem sobrescrever decisões. Chamador controla commit."""
        valores = {
            k: v for k, v in dados.items() if k in p.c and k not in ("id", "tenant_id")
        }
        agora = datetime.now()
        from sqlalchemy.dialects.mysql import insert as mysql_insert
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert

        dialect = self.session.get_bind().dialect.name
        dados_novos = self.valores({**valores, "capturada_em": agora})
        if dialect == "mysql":
            stmt = (
                mysql_insert(p).values(**dados_novos).on_duplicate_key_update(id=p.c.id)
            )
        else:
            stmt = (
                sqlite_insert(p)
                .values(**dados_novos)
                .on_conflict_do_nothing(index_elements=["tenant_id", "id_djen"])
            )
        self.session.execute(stmt)
        row = (
            self.session.execute(
                self.escopo(
                    select(p).where(p.c.id_djen == dados["id_djen"]), p
                ).with_for_update()
            )
            .mappings()
            .one()
        )
        inicial = self.valores(
            dict(id_publicacao=row["id"], rotulo="nao_classificado", origem="captura")
        )
        if dialect == "mysql":
            stmt = mysql_insert(c).values(**inicial).on_duplicate_key_update(id=c.c.id)
        else:
            stmt = (
                sqlite_insert(c)
                .values(**inicial)
                .on_conflict_do_nothing(index_elements=["tenant_id", "id_publicacao"])
            )
        self.session.execute(stmt)
        pid = row["id"]
        valores.pop("capturada_em", None)
        self.session.execute(
            self.escopo(update(p).where(p.c.id == pid), p).values(
                **valores, atualizada_em=agora
            )
        )
        return pid

    def classificar(self, pid, rotulo, origem, usuario, automatico=False):
        atual = (
            self.session.execute(
                self.escopo(
                    select(c).where(c.c.id_publicacao == pid), c
                ).with_for_update()
            )
            .mappings()
            .one()
        )
        # Uma consulta nunca constitui nova avaliação, nem remove decisão humana.
        if automatico and atual["origem"] != "captura":
            return False
        if (
            atual["rotulo"] == rotulo
            and atual["origem"] == origem
            and atual["id_rotulado_por"] == usuario
        ):
            return False
        valores = dict(
            rotulo=rotulo,
            origem=origem,
            id_rotulado_por=usuario,
            rotulado_em=datetime.now(),
        )
        self.session.execute(
            insert(h).values(
                **self.valores(
                    dict(id_publicacao=pid, rotulo_anterior=atual["rotulo"], **valores)
                )
            )
        )
        self.session.execute(
            self.escopo(update(c).where(c.c.id_publicacao == pid), c).values(**valores)
        )
        return True

    def _select(self):
        return self.escopo(
            select(
                p, c.c.rotulo, c.c.origem, c.c.id_rotulado_por, c.c.rotulado_em
            ).select_from(
                p.join(
                    c, (c.c.id_publicacao == p.c.id) & (c.c.tenant_id == p.c.tenant_id)
                )
            ),
            p,
            c,
        )

    def por_ids_djen(self, ids):
        return (
            {
                row["id_djen"]: dict(row)
                for row in self.session.execute(
                    self._select().where(p.c.id_djen.in_(ids))
                ).mappings()
            }
            if ids
            else {}
        )

    def acessivel(self, unidade):
        consultas = self.escopo(
            select(acesso.c.id).where(acesso.c.id_publicacao == p.c.id, acesso.c.unidade_id == unidade), acesso
        )
        operacional = self.escopo(
            select(o.c.id).where(
                o.c.id_publicacao == p.c.id, o.c.unidade_id == unidade
            ),
            o,
        )
        return exists(consultas) | exists(operacional)

    def selecionadas(self, ids, unidade):
        stmt = (
            self._select()
            .where(p.c.id_djen.in_(ids), self.acessivel(unidade))
            .order_by(p.c.id)
            .with_for_update()
        )
        return [dict(row) for row in self.session.execute(stmt).mappings()]

    def listar(self, unidade, filtros, page, per_page):
        stmt = self._select().where(self.acessivel(unidade))
        stmt = filtrar_identificacao(stmt, p, self.session.get_bind().dialect.name,
            filtros.get('nome_parte'), filtros.get('numero_processo'), filtros.get('oab'))
        for chave, col in [
            ("rotulo", c.c.rotulo),
            ("tribunal", p.c.sigla_tribunal),
            ("origem", c.c.origem),
        ]:
            if filtros.get(chave):
                stmt = stmt.where(col == filtros[chave])
        if filtros.get("inicio"):
            stmt = stmt.where(p.c.data_disponibilizacao >= filtros["inicio"])
        if filtros.get("fim"):
            stmt = stmt.where(p.c.data_disponibilizacao <= filtros["fim"])
        if filtros.get("situacao"):
            op = self.escopo(select(o.c.id).where(o.c.id_publicacao == p.c.id), o)
            stmt = stmt.where(
                ~exists(op)
                if filtros["situacao"] == "nao_importada"
                else exists(op.where(o.c.situacao == filtros["situacao"]))
            )
        if filtros.get("fonte"):
            fonte = self.escopo(
                select(acesso.c.id).where(acesso.c.id_publicacao == p.c.id,
                    acesso.c.unidade_id == unidade, acesso.c.origem == filtros["fonte"]), acesso
            )
            stmt = stmt.where(exists(fonte))
        total = self.session.execute(
            select(func.count()).select_from(stmt.subquery())
        ).scalar_one()
        # Listas não transportam o texto integral.
        stmt = stmt.with_only_columns(
            p.c.id,
            p.c.id_djen,
            p.c.numero_processo,
            p.c.data_disponibilizacao,
            p.c.sigla_tribunal,
            p.c.nome_orgao,
            c.c.rotulo,
            c.c.origem,
            func.substr(p.c.texto_plano, 1, 240).label("resumo"),
        )
        itens = [
            dict(x)
            for x in self.session.execute(
                stmt.order_by(p.c.data_disponibilizacao.desc(), p.c.id.desc())
                .offset((page - 1) * per_page)
                .limit(per_page)
            ).mappings()
        ]
        ops = self.escopo(
            select(o).where(
                o.c.id_publicacao.in_([x["id"] for x in itens]),
                o.c.unidade_id == unidade,
            ),
            o,
        )
        operacoes = {
            x["id_publicacao"]: dict(x) for x in self.session.execute(ops).mappings()
        }
        for item in itens:
            operacional = operacoes.get(item["id"], {})
            item.update(
                situacao=operacional.get("situacao", "nao_importada"),
                comunicacao_id=operacional.get("id"),
                id_processo=operacional.get("id_processo"),
                id_caso=operacional.get("id_caso"),
            )
        return dict(items=itens, total=total, page=page, per_page=per_page)

    def detalhe(self, pid, unidade):
        row = (
            self.session.execute(
                self._select().where(p.c.id == pid, self.acessivel(unidade))
            )
            .mappings()
            .first()
        )
        if not row:
            return None
        dados = dict(row)
        dados.pop("texto_html", None)
        operacao = self.session.execute(
            self.escopo(
                select(o).where(o.c.id_publicacao == pid, o.c.unidade_id == unidade), o
            )
        ).mappings().first()
        dados.update(
            situacao=operacao["situacao"] if operacao else "nao_importada",
            comunicacao_id=operacao["id"] if operacao else None,
            id_processo=operacao["id_processo"] if operacao else None,
            id_caso=operacao["id_caso"] if operacao else None,
        )
        dados["historico"] = [
            dict(x)
            for x in self.session.execute(
                self.escopo(
                    select(h).where(h.c.id_publicacao == pid).order_by(h.c.id.desc()), h
                )
            ).mappings()
        ]
        return dados

    def iniciar_consulta(self, origem, parametros, unidade, executor):
        return self.session.execute(
            insert(q).values(
                **self.valores(
                    dict(
                        origem=origem,
                        parametros=parametros,
                        unidade_id=unidade,
                        id_executor=executor,
                        inicio=datetime.now(ZoneInfo("America/Sao_Paulo")).replace(tzinfo=None),
                        status="executando",
                    )
                )
            )
        ).lastrowid

    def dar_acesso(self, pid, unidade, origem):
        from sqlalchemy.dialects.mysql import insert as mi
        from sqlalchemy.dialects.sqlite import insert as si
        valores = self.valores(dict(id_publicacao=pid, unidade_id=unidade, origem=origem))
        if self.session.get_bind().dialect.name == "mysql":
            stmt = mi(acesso).values(**valores).on_duplicate_key_update(id=acesso.c.id)
        else:
            stmt = si(acesso).values(**valores).on_conflict_do_nothing()
        self.session.execute(stmt)

    def resultado(self, consulta, pid):
        query = self.session.execute(self.escopo(select(q).where(q.c.id == consulta), q)).mappings().one()
        self.dar_acesso(pid, query["unidade_id"], query["origem"])
        stmt = self.escopo(
            select(r.c.id).where(r.c.id_consulta == consulta, r.c.id_publicacao == pid),
            r,
        )
        if self.session.execute(stmt).first() is None:
            self.session.execute(
                insert(r).values(
                    **self.valores(dict(id_consulta=consulta, id_publicacao=pid))
                )
            )

    def atualizar_consulta(self, consulta, **valores):
        self.session.execute(self.escopo(update(q).where(q.c.id == consulta), q).values(**valores))

    def finalizar_consulta(self, consulta, status):
        self.session.execute(
            self.escopo(update(q).where(q.c.id == consulta), q).values(
                status=status, fim=datetime.now(ZoneInfo("America/Sao_Paulo")).replace(tzinfo=None)
            )
        )

    def contagens(self):
        stmt = self.escopo(
            select(
                c.c.rotulo,
                c.c.origem,
                func.count().label("total"),
                func.count(p.c.texto_plano).label("com_texto"),
            )
            .select_from(
                p.join(
                    c, (c.c.id_publicacao == p.c.id) & (c.c.tenant_id == p.c.tenant_id)
                )
            )
            .group_by(c.c.rotulo, c.c.origem),
            p,
            c,
        )
        return [dict(row) for row in self.session.execute(stmt).mappings()]

    def para_exportar(self, rotulos):
        ultimo = 0
        while True:
            rows = (
                self.session.execute(
                    self._select()
                    .where(c.c.rotulo.in_(rotulos), p.c.id > ultimo)
                    .order_by(p.c.id)
                    .limit(500)
                )
                .mappings()
                .all()
            )
            if not rows:
                return
            for row in rows:
                yield dict(row)
            ultimo = rows[-1]["id"]
