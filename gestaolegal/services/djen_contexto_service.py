"""Treino e inferência contextual; SQL restrito ao repositório."""

from gestaolegal.exceptions import ValidationException
from gestaolegal.repositories.djen_contexto_repository import DjenContextoRepository
from gestaolegal.utils.tempo import agora_utc


class DjenContextoService(DjenContextoRepository):
    def treinar(self, cid, unidade, token=None):
        """Holdout por CNJ; vocabulário aprendido apenas no treino da avaliação."""
        from collections import Counter
        import warnings
        from sklearn.exceptions import ConvergenceWarning

        ctx = self.obter(cid, unidade)
        self.registrar_etapa(cid, token, 'Preparar exemplos', 0, 'Conferindo textos e rótulos do contexto.')
        candidatas = self.amostras(cid)
        rows = [x for x in candidatas if (x['texto_plano'] or '').strip() and (x['numero_processo'] or '').strip()]
        excluidos = dict(sem_texto=sum(not (x['texto_plano'] or '').strip() for x in candidatas), sem_processo=sum(bool((x['texto_plano'] or '').strip()) and not (x['numero_processo'] or '').strip() for x in candidatas))
        self.registrar_etapa(cid, token, 'Separar treino e validação', 1, f'{len(rows)} exemplos utilizáveis; {len(candidatas) - len(rows)} excluídos.', contexto_snapshot=self.snapshot(ctx))
        if (
            len(rows) < 200
            or min(
                sum(x["rotulo"] == k for x in rows)
                for k in ("relevante", "irrelevante")
            )
            < 50
        ):
            raise ValidationException(
                "Treino exige 200 rótulos, com pelo menos 50 de cada classe"
            )
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.linear_model import LogisticRegression
        from sklearn.model_selection import GroupShuffleSplit
        from sklearn.metrics import precision_score, recall_score, f1_score, confusion_matrix
        import numpy as np

        textos = [x["texto_plano"] or "" for x in rows]
        y = np.array([int(x["rotulo"] == "relevante") for x in rows])
        grupos = [x["numero_processo"] for x in rows]
        if len(set(grupos)) < 10:
            raise ValidationException(
                "São necessários pelo menos 10 processos distintos para avaliar o modelo"
            )
        treino, teste = next(
            GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=42).split(
                textos, y, grupos
            )
        )
        if any(len(set(y[i])) < 2 for i in (treino, teste)):
            raise ValidationException(
                "A separação por processo não contém as duas classes; rotule mais processos"
            )
        def conjunto(indices):
            return dict(exemplos=len(indices), processos=len({grupos[i] for i in indices}), relevantes=sum(int(y[i]) for i in indices), irrelevantes=sum(1 - int(y[i]) for i in indices))

        self.registrar_etapa(cid, token, 'Processar textos', 2, f'{len(treino)} exemplos de treino e {len(teste)} de validação, separados por processo.')
        vet = TfidfVectorizer(
            strip_accents="unicode",
            lowercase=True,
            ngram_range=(1, 2),
            max_features=20000,
            sublinear_tf=True,
        )
        try:
            x = vet.fit_transform([textos[i] for i in treino])
        except ValueError:
            raise ValidationException("Textos insuficientes para treinar")
        self.registrar_etapa(cid, token, 'Treinar modelo de avaliação', 3, f'TF-IDF preparado com {len(vet.vocabulary_)} atributos.')
        modelo = LogisticRegression(
            max_iter=1000, class_weight="balanced", random_state=42
        )
        with warnings.catch_warnings(record=True) as avisos:
            warnings.simplefilter('always', ConvergenceWarning)
            modelo.fit(x, y[treino])
        alertas = [str(aviso.message) for aviso in avisos if issubclass(aviso.category, ConvergenceWarning)]
        self.registrar_etapa(cid, token, 'Avaliar modelo', 4, 'Treino concluído. Avaliando somente os exemplos reservados.' + (' Aviso: limite de iterações atingido.' if alertas else ''))
        previsto = modelo.predict(vet.transform([textos[i] for i in teste]))
        metricas = dict(
            algoritmo='TF-IDF + regressão logística',
            algoritmo_versao='tfidf-logistic-v1',
            parametros=dict(ngram_range=[1, 2], max_features=20000, sublinear_tf=True, max_iter=1000, class_weight='balanced', random_state=42, validacao_fracao_grupos=0.25),
            contexto_versao=ctx['versao'], avaliacoes_versao=ctx['avaliacoes_versao'],
            contexto_snapshot=self.snapshot(ctx),
            candidatos=len(candidatas), excluidos=excluidos,
            classes=dict(Counter(x['rotulo'] for x in rows)),
            origens=dict(Counter(x['origem'] for x in rows)),
            bases=dict(treino=conjunto(treino), validacao=conjunto(teste)),
            matriz_confusao=confusion_matrix(y[teste], previsto, labels=[0, 1]).tolist(),
            avisos=alertas,
            total=len(rows),
            treino=len(treino),
            teste=len(teste),
            processos=len(set(grupos)),
            precisao=float(precision_score(y[teste], previsto, zero_division=0)),
            revocacao=float(recall_score(y[teste], previsto, zero_division=0)),
            f1=float(f1_score(y[teste], previsto, zero_division=0)),
            avaliacao="holdout por processo; rótulos manuais e operacionais",
            experimental=True,
            ids_teste=[rows[i]["id"] for i in teste],
            ids_treino=[rows[i]["id"] for i in treino],
            amostra=[
                dict(id=x["id"], rotulo=x["rotulo"], origem=x["origem"]) for x in rows
            ],
        )
        # O artefato final aprende com todos os rótulos; métricas acima são só do holdout.
        self.registrar_etapa(cid, token, 'Treinar modelo final', 5, 'Validação concluída. Treinando o modelo final com todos os exemplos utilizáveis.', metricas=metricas)
        x = vet.fit_transform(textos)
        with warnings.catch_warnings(record=True) as avisos_finais:
            warnings.simplefilter('always', ConvergenceWarning)
            modelo.fit(x, y)
        metricas['avisos'] += [str(aviso.message) for aviso in avisos_finais if issubclass(aviso.category, ConvergenceWarning)]
        self.registrar_etapa(cid, token, 'Salvar modelo', 6, 'Modelo final pronto; salvando artefato e métricas.', metricas=metricas)
        artefato = dict(
            vocabulario={k: int(v) for k, v in vet.vocabulary_.items()},
            idf=vet.idf_.tolist(),
            coef=modelo.coef_[0].tolist(),
            intercept=float(modelo.intercept_[0]),
            algoritmo="tfidf-logistic-v1",
        )
        if token is not None:
            self.concluir_treino(cid, token)
        mid = self.salvar_modelo(cid, artefato, metricas)
        if token is not None:
            self.atualizar_execucao(cid, token, 'Concluído', 7, f'Modelo #{mid} salvo. As sugestões serão atualizadas pelo worker.', status='concluido', finalizado_em=agora_utc(), modelo_id=mid, metricas=metricas)
        self.session.commit()
        return {"id": mid, "metricas": metricas}

    def prever(self, relacoes):
        """Persiste a sugestão por versão, sem alterar rótulo nem operação."""
        for cid in {x["contexto_id"] for x in relacoes}:
            modelo = self.ultimo_modelo(cid)
            if not modelo:
                continue
            alvos = [
                x
                for x in relacoes
                if x["contexto_id"] == cid
                and x["modelo_id"] != modelo["id"]
                and x["rotulo"] == "nao_classificado"
            ]
            if not alvos:
                continue
            import numpy as np
            from sklearn.feature_extraction.text import TfidfVectorizer
            from scipy.special import expit

            a = modelo["artefato"]
            vet = TfidfVectorizer(
                strip_accents="unicode",
                lowercase=True,
                ngram_range=(1, 2),
                vocabulary=a["vocabulario"],
                sublinear_tf=True,
            )
            vet.idf_ = np.array(a["idf"])
            textos = self.textos(alvos)
            for row in alvos:
                if not (textos.get(row["id_publicacao"]) or "").strip():
                    self.salvar_previsao(
                        row["id"],
                        dict(modelo_id=modelo["id"], sugestao=None, probabilidade=None),
                    )
            alvos = [x for x in alvos if (textos.get(x["id_publicacao"]) or "").strip()]
            if not alvos:
                continue
            prob = expit(
                vet.transform([textos[x["id_publicacao"]] or "" for x in alvos])
                @ np.array(a["coef"])
                + a["intercept"]
            )
            for row, chance in zip(alvos, prob):
                dados = dict(
                    modelo_id=modelo["id"],
                    sugestao="relevante" if chance >= 0.5 else "irrelevante",
                    probabilidade=str(float(chance)),
                )
                self.salvar_previsao(row["id"], dados)
                row.update(dados)
        self.session.commit()
        return relacoes

    def processar_previsoes(self, cid, unidade, limite=200):
        ctx = self.obter(cid, unidade)
        modelo = self.ultimo_modelo(cid)
        if not modelo or modelo["metricas"].get("contexto_versao", 1) != ctx["versao"]:
            return 0
        lote = self.lote_previsoes(cid, modelo["id"], limite)
        self.prever(lote)
        return len(lote)

    def executar_treino(self, cid, unidade, token):
        import logging

        self.obter(cid, unidade)
        if not self.iniciar_treino(cid, token):
            return None
        try:
            return self.treinar(cid, unidade, token=token)
        except ValidationException as exc:
            self.falhar_treino(cid, token, str(exc))
        except Exception:
            logging.getLogger(__name__).exception("Falha no treino do contexto %s", cid)
            self.falhar_treino(
                cid,
                token,
                "Falha interna no treinamento. Tente novamente ou consulte o administrador.",
            )
        return None
