"""Persistência tenant-scoped do monitoramento e dos logs DJEN."""

from datetime import datetime, timedelta
from sqlalchemy import select, update, delete, func
from gestaolegal.config import Config
from gestaolegal.database.tables import (
    djen_monitoramentos as m,
    djen_consultas as q,
    djen_consulta_resultados as r,
    djen_sincronizacoes as s,
    processos as p,
    unidades as u,
    djen_oabs as oabs,
)
from gestaolegal.repositories.repository import BaseRepository
from gestaolegal.exceptions import ValidationException
from zoneinfo import ZoneInfo


def agora():
    return datetime.now(ZoneInfo("America/Sao_Paulo")).replace(tzinfo=None)


class DjenMonitoramentoRepository(BaseRepository):
    def _inserir(self, valores):
        from sqlalchemy.dialects.mysql import insert as mi
        from sqlalchemy.dialects.sqlite import insert as si

        valores = self.valores(valores)
        if self.session.get_bind().dialect.name == "mysql":
            stmt = mi(m).values(**valores).on_duplicate_key_update(id=m.c.id)
        else:
            stmt = si(m).values(**valores).on_conflict_do_nothing()
        self.session.execute(stmt)

    def _visibilidade(self, stmt, tabela, user):
        stmt = self.escopo(stmt, tabela)
        if user.urole != "admin":
            stmt = stmt.where(tabela.c.unidade_id.in_([un.id for un in user.unidades]))
        return stmt

    def limpar_logs(self):
        limite = agora() - timedelta(days=max(1, Config.DJEN_LOG_RETENCAO_DIAS))
        velhas = self.escopo(
            select(q.c.id).where(
                q.c.inicio < limite, q.c.status.not_in(["executando", "aguardando"])
            ),
            q,
        )
        self.session.execute(
            self.escopo(delete(r).where(r.c.id_consulta.in_(velhas)), r)
        )
        self.session.execute(
            self.escopo(
                delete(q).where(
                    q.c.inicio < limite, q.c.status.not_in(["executando", "aguardando"])
                ),
                q,
            )
        )
        self.session.execute(
            self.escopo(delete(s).where(s.c.inicio < limite, s.c.fim.is_not(None)), s)
        )
        self.session.commit()

    def execucoes(self, user, filtros):
        """Execuções da rotina automática do NPJ, mais recentes primeiro.

        A execução cobre todas as unidades do NPJ. Quem não é admin vê só as
        consultas das próprias unidades e não vê a mensagem consolidada, que
        pode citar itens monitorados de outras unidades.
        """
        stmt = self.escopo(select(s), s)
        if filtros.get("status"):
            stmt = stmt.where(s.c.status == filtros["status"])
        try:
            if filtros.get("de"):
                stmt = stmt.where(s.c.inicio >= datetime.fromisoformat(filtros["de"]))
            if filtros.get("ate"):
                stmt = stmt.where(
                    s.c.inicio
                    < datetime.fromisoformat(filtros["ate"]) + timedelta(days=1)
                )
            page = max(1, int(filtros.get("page", 1)))
        except (ValueError, TypeError):
            raise ValidationException("Filtro de data ou página inválido")
        total = self.session.execute(
            select(func.count()).select_from(stmt.subquery())
        ).scalar()
        rows = list(
            self.session.execute(
                stmt.order_by(s.c.inicio.desc(), s.c.id.desc())
                .limit(30)
                .offset((page - 1) * 30)
            ).mappings()
        )
        ids = [row["id"] for row in rows]
        por_execucao = {}
        if ids:
            consultas = self._visibilidade(
                select(q.c.execucao_id, q.c.status, func.count().label("total"))
                .where(q.c.execucao_id.in_(ids))
                .group_by(q.c.execucao_id, q.c.status),
                q,
                user,
            )
            for linha in self.session.execute(consultas).mappings():
                contagem = por_execucao.setdefault(linha["execucao_id"], {})
                contagem[linha["status"]] = linha["total"]
        items = []
        for row in rows:
            parametros = row["parametros"] or {}
            items.append(
                dict(
                    id=row["id"],
                    inicio=row["inicio"].isoformat(),
                    fim=row["fim"].isoformat() if row["fim"] else None,
                    duracao_segundos=(
                        max(0, int((row["fim"] - row["inicio"]).total_seconds()))
                        if row["fim"]
                        else None
                    ),
                    status=row["status"],
                    janela_dias=parametros.get("janela_dias"),
                    novas=row["novas"],
                    atualizadas=row["atualizadas"],
                    vinculadas=row["vinculadas"],
                    consultas=por_execucao.get(row["id"], {}),
                    mensagem=row["mensagem"] if user.urole == "admin" else None,
                )
            )
        return dict(
            items=items,
            total=total,
            page=page,
            per_page=30,
            retencao_dias=Config.DJEN_LOG_RETENCAO_DIAS,
        )

    def logs(self, user, filtros):
        stmt = self._visibilidade(select(q), q, user)
        for chave in ("origem", "status", "modo", "unidade_id", "execucao_id"):
            if filtros.get(chave):
                stmt = stmt.where(q.c[chave] == filtros[chave])
        try:
            for campo, op in (("de", "inicio"), ("ate", "fim")):
                if filtros.get(campo):
                    data = datetime.fromisoformat(filtros[campo])
                    stmt = (
                        stmt.where(q.c.inicio >= data)
                        if op == "inicio"
                        else stmt.where(q.c.inicio < data + timedelta(days=1))
                    )
            page = max(1, int(filtros.get("page", 1)))
        except (ValueError, TypeError):
            raise ValidationException("Filtro de data ou página inválido")
        total = self.session.execute(
            select(func.count()).select_from(stmt.subquery())
        ).scalar()
        rows = self.session.execute(
            stmt.order_by(q.c.inicio.desc(), q.c.id.desc())
            .limit(30)
            .offset((page - 1) * 30)
        ).mappings()
        items = []
        for row in rows:
            item = dict(row)
            item["inicio"] = row["inicio"].isoformat()
            item["fim"] = row["fim"].isoformat() if row["fim"] else None
            item["duracao_segundos"] = (
                max(0, int((row["fim"] - row["inicio"]).total_seconds()))
                if row["fim"]
                else None
            )
            items.append(item)
        return dict(
            items=items,
            total=total,
            page=page,
            per_page=30,
            retencao_dias=Config.DJEN_LOG_RETENCAO_DIAS,
            agendamento=dict(
                habilitado=Config.DJEN_SYNC_ENABLED,
                janela_dias=Config.DJEN_JANELA_DIAS,
                janela_diurna_dias=Config.DJEN_JANELA_DIURNA_DIAS,
            ),
        )

    def oabs_legadas(self):
        return self.session.execute(self.escopo(select(oabs), oabs)).mappings().all()

    def processos_ativos(self):
        return self.session.execute(
            self.escopo(
                select(p.c.numero_cnj, p.c.unidade_id).where(
                    p.c.status.is_(True), p.c.numero_cnj.is_not(None)
                ),
                p,
            )
        ).all()

    def monitores_visiveis(self, user):
        # Não escolhe arbitrariamente entre CNJs duplicados com máscaras distintas.
        processo_id = (
            select(func.min(p.c.id))
            .where(
                self.no_tenant(p), p.c.tenant_id == m.c.tenant_id,
                p.c.numero_cnj == m.c.valor, p.c.unidade_id == m.c.unidade_id,
                m.c.tipo == "processo",
            )
            .having(func.count(p.c.id) == 1)
            .correlate(m).scalar_subquery()
        )
        return (
            self.session.execute(
                self._visibilidade(
                    select(m, processo_id.label("processo_id"))
                    .where(m.c.removido.is_(False))
                    .order_by(m.c.tipo, m.c.valor, m.c.id),
                    m,
                    user,
                )
            )
            .mappings()
            .all()
        )

    def unidade_existe(self, unidade):
        return self.session.execute(
            self.escopo(select(u.c.id).where(u.c.id == unidade), u)
        ).scalar()

    def reativar(self, tipo, valor, unidade, tribunais):
        self.session.execute(
            self.escopo(
                update(m).where(
                    m.c.tipo == tipo, m.c.valor == valor, m.c.unidade_id == unidade
                ),
                m,
            ).values(ativo=True, removido=False, tribunais=tribunais, automatico=False)
        )

    def monitor_visivel(self, id, user):
        return (
            self.session.execute(
                self._visibilidade(select(m).where(m.c.id == id), m, user)
            )
            .mappings()
            .first()
        )

    def mudar_monitor(self, id, **valores):
        self.session.execute(
            self.escopo(update(m).where(m.c.id == id), m).values(**valores)
        )

    def mudar_consultas(self, ids, **valores):
        self.session.execute(
            self.escopo(update(q).where(q.c.id.in_(ids)), q).values(**valores)
        )

    def interromper_anteriores(self):
        self.session.execute(
            self.escopo(
                update(q).where(
                    q.c.modo == "automatico",
                    q.c.status.in_(["executando", "aguardando"]),
                ),
                q,
            ).values(
                status="interrompida",
                fim=agora(),
                mensagem="Execução anterior interrompida",
            )
        )
        self.session.execute(
            self.escopo(update(s).where(s.c.fim.is_(None)), s).values(
                status="erro", fim=agora(), mensagem="Execução anterior interrompida"
            )
        )

    def monitores_ativos(self):
        return (
            self.session.execute(
                self.escopo(
                    select(m).where(m.c.ativo.is_(True), m.c.removido.is_(False)), m
                )
            )
            .mappings()
            .all()
        )

    def concluir_processo(self, item):
        self.session.execute(
            self.escopo(
                update(p).where(
                    p.c.numero_cnj == item["valor"],
                    p.c.unidade_id == item["unidade_id"],
                    p.c.status.is_(True),
                ),
                p,
            ).values(djen_pendente=False, djen_consultado_em=agora())
        )

    def concluir_execucao(self, id, registro):
        self.session.execute(
            self.escopo(update(s).where(s.c.id == id), s).values(**registro)
        )
