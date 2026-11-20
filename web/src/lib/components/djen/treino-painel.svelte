<script lang="ts">
	import { api } from '#lib/api-client.ts';
	import { Button } from '#lib/components/ui/button/index.ts';
	import { mensagemDeErro } from '#lib/utils/erros.ts';
	import type { ContextoDjen, TreinoDjen, MetricasTreino } from '#lib/types/djen.ts';
	let { contexto }: { contexto: ContextoDjen } = $props();
	let historico = $state<{ items: TreinoDjen[]; total: number }>({ items: [], total: 0 });
	let pagina = $state(1);
	let erro = $state('');
	let carregando = $state(false);
	let recarregar = $state(0);
	let agora = $state(Date.now());
	const emTreino = $derived(['na_fila', 'executando'].includes(contexto.treino_status ?? ''));
	$effect(() => {
		const cid = contexto.id,
			p = pagina,
			status = contexto.treino_status;
		recarregar;
		const controller = new AbortController();
		let consultando = false;
		async function buscar() {
			if (consultando) return;
			consultando = true;
			carregando = true;
			try {
				const resposta = await api.get<{ items: TreinoDjen[]; total: number }>(
					`djen/contextos/${cid}/treinos?page=${p}`,
					{ signal: controller.signal }
				);
				if (!controller.signal.aborted) {
					historico = resposta;
					erro = '';
				}
			} catch (e) {
				if (!controller.signal.aborted)
					erro = mensagemDeErro(e, 'Não foi possível carregar o histórico de treinamento.');
			} finally {
				consultando = false;
				if (!controller.signal.aborted) carregando = false;
			}
		}
		buscar();
		const timer = setInterval(() => {
			agora = Date.now();
			if (status === 'na_fila' || status === 'executando') buscar();
		}, 3000);
		return () => {
			controller.abort();
			clearInterval(timer);
		};
	});
	function data(valor: string | null) {
		return valor ? new Date(valor).toLocaleString('pt-BR') : '—';
	}
	function duracao(execucao: TreinoDjen) {
		if (!execucao.iniciado_em) return 'Aguardando início';
		const segundos = Math.max(
			0,
			Math.round(
				((execucao.finalizado_em ? new Date(execucao.finalizado_em).getTime() : agora) -
					new Date(execucao.iniciado_em).getTime()) /
					1000
			)
		);
		return `${Math.floor(segundos / 60)} min ${segundos % 60} s`;
	}
	const percentual = (n: number | undefined) =>
		n === undefined ? '—' : `${(n * 100).toFixed(1)}%`;
	const origens: Record<string, string> = {
		classificacao: 'Avaliação manual',
		busca_parte: 'Importação',
		importacao: 'Importação',
		descarte: 'Descarte',
		vinculo_manual: 'Vínculo manual',
		vinculo_automatico: 'Vínculo automático'
	};
</script>

{#snippet metricas(m: Partial<MetricasTreino>)}
	<div class="space-y-3 text-sm">
		<p>
			<strong>Algoritmo:</strong>
			{m.algoritmo ?? 'TF-IDF + regressão logística'} · {m.algoritmo_versao ?? 'tfidf-logistic-v1'}
		</p>
		<p>
			<strong>Exemplos utilizados:</strong>
			{m.total ?? '—'} · Relevantes: {m.classes?.relevante ?? '—'} · Irrelevantes: {m.classes
				?.irrelevante ?? '—'} · Processos distintos: {m.processos ?? '—'}
		</p>
		{#if m.excluidos}<p>
				Excluídos por falta de texto: {m.excluidos.sem_texto ?? 0} · Sem identificação do processo: {m
					.excluidos.sem_processo ?? 0}
			</p>{/if}
		{#if m.origens}<p>
				<strong>Origem dos rótulos:</strong>
				{Object.entries(m.origens)
					.map(([origem, n]) => `${origens[origem] ?? origem}: ${n}`)
					.join(' · ')}
			</p>{/if}
		{#if m.bases}
			<div class="overflow-x-auto">
				<table class="w-full text-left" aria-label="Divisão dos exemplos">
					<thead>
						<tr>
							<th class="p-2">Base</th><th class="p-2">Exemplos</th><th class="p-2">
								Proporção
							</th><th class="p-2">Processos</th><th class="p-2">Relevantes</th><th class="p-2">
								Irrelevantes
							</th>
						</tr>
					</thead>
					<tbody>
						{#each ['treino', 'validacao'] as chave}{@const base =
								m.bases[chave as 'treino' | 'validacao']}<tr>
								<td class="p-2">{chave === 'treino' ? 'Treino' : 'Validação'}</td><td class="p-2">
									{base.exemplos}
								</td><td class="p-2">
									{percentual(m.total ? base.exemplos / m.total : undefined)}
								</td><td class="p-2">{base.processos}</td><td class="p-2">{base.relevantes}</td><td
									class="p-2"
								>
									{base.irrelevantes}
								</td>
							</tr>{/each}
					</tbody>
				</table>
			</div>
		{:else if m.treino !== undefined}<p>Treino: {m.treino} · Validação: {m.teste}</p>{/if}
		<p class="text-muted-foreground">
			A divisão reserva aproximadamente 25% dos processos para validação. Publicações do mesmo
			processo ficam na mesma base. As métricas são calculadas na validação; depois, o modelo final
			aprende com todos os exemplos utilizados.
		</p>
		<dl class="grid gap-3 sm:grid-cols-3">
			<div>
				<dt>Precisão</dt>
				<dd class="text-xl font-semibold">{percentual(m.precisao)}</dd>
				<dd class="text-xs text-muted-foreground">
					Entre as apontadas como relevantes, quantas estavam corretas.
				</dd>
			</div>
			<div>
				<dt>Revocação</dt>
				<dd class="text-xl font-semibold">{percentual(m.revocacao)}</dd>
				<dd class="text-xs text-muted-foreground">
					Entre as realmente relevantes, quantas foram encontradas.
				</dd>
			</div>
			<div>
				<dt>F1</dt>
				<dd class="text-xl font-semibold">{m.f1?.toFixed(2) ?? '—'}</dd>
				<dd class="text-xs text-muted-foreground">Medida que combina precisão e revocação.</dd>
			</div>
		</dl>
		{#if m.matriz_confusao}<div class="overflow-x-auto">
				<table class="w-full text-left" aria-label="Matriz de confusão">
					<thead>
						<tr>
							<th class="p-2">Classificação real</th><th class="p-2">Prevista irrelevante</th><th
								class="p-2"
							>
								Prevista relevante
							</th>
						</tr>
					</thead><tbody>
						<tr>
							<th class="p-2">Irrelevante</th><td class="p-2">
								{m.matriz_confusao[0][0]} acertos
							</td><td class="p-2">{m.matriz_confusao[0][1]} falsos positivos</td>
						</tr><tr>
							<th class="p-2">Relevante</th><td class="p-2">
								{m.matriz_confusao[1][0]} não identificadas
							</td><td class="p-2">{m.matriz_confusao[1][1]} acertos</td>
						</tr>
					</tbody>
				</table>
			</div>{/if}
		{#if m.parametros}<details>
				<summary class="cursor-pointer">Parâmetros do algoritmo</summary>
				<dl class="mt-2 grid gap-1 sm:grid-cols-2">
					{#each Object.entries(m.parametros) as [nome, valor]}<div>
							<dt class="font-medium">{nome}</dt>
							<dd>{String(valor)}</dd>
						</div>{/each}
				</dl>
			</details>{/if}
		{#each m.avisos ?? [] as aviso}<p class="text-amber-700 dark:text-amber-300">
				Aviso: {aviso}
			</p>{/each}
	</div>
{/snippet}
<section class="space-y-4 border-t pt-4" aria-label="Histórico de treinamentos">
	<h3 class="font-semibold">Treinamento e histórico</h3>
	{#if contexto.modelo_desatualizado}<p class="text-sm text-amber-700 dark:text-amber-300">
			Há alterações no contexto ou nas avaliações ainda não incorporadas ao modelo. Treine novamente
			para atualizá-lo.
		</p>{/if}
	{#if erro}<p role="alert" class="text-sm text-destructive">{erro}</p>
		<Button variant="outline" onclick={() => recarregar++}>Tentar novamente</Button>{/if}
	{#each historico.items as execucao, indice (execucao.id)}
		<details class="space-y-3 rounded-md border p-3" open={indice === 0}>
			<summary class="cursor-pointer font-medium">
				Treino #{execucao.id} · {execucao.status} · {data(
					execucao.solicitado_em
				)}{execucao.modelo_id ? ` · Modelo #${execucao.modelo_id}` : ''}
			</summary>
			<p class="text-sm">
				{execucao.contexto_snapshot.nome} · Contexto versão {execucao.contexto_snapshot.versao ?? 1}
				· Avaliações versão {execucao.contexto_snapshot.avaliacoes_versao ?? 0}
			</p>
			<p class="text-sm">
				Início: {data(execucao.iniciado_em)} · Fim: {data(execucao.finalizado_em)} · Duração: {duracao(
					execucao
				)}
			</p>
			<div class="space-y-1">
				<label for={`treino-progresso-${execucao.id}`} class="text-sm">
					{execucao.etapa} · {execucao.etapas_concluidas} de 7 etapas concluídas
				</label><progress
					id={`treino-progresso-${execucao.id}`}
					class="h-3 w-full accent-primary"
					value={execucao.etapas_concluidas}
					max="7"
				></progress>
			</div>
			{#if execucao.status === 'executando'}<p class="text-xs text-muted-foreground">
					Etapa em execução. A barra avança quando uma etapa termina; não é uma estimativa de tempo.
				</p>{/if}
			{#if execucao.erro}<p role="alert" class="text-sm text-destructive">{execucao.erro}</p>{/if}
			<details>
				<summary class="cursor-pointer text-sm">Critérios e objetivo usados nesta execução</summary>
				<p class="my-2 text-sm">
					{execucao.contexto_snapshot.descricao || 'Objetivo não informado.'}
				</p>
				<ul class="space-y-1 text-sm">
					{#each Object.entries(execucao.contexto_snapshot.criterios ?? { nomes: execucao.contexto_snapshot.nomes, tribunal: execucao.contexto_snapshot.tribunais }) as [criterio, valor]}{#if valor && String(valor)}<li>
								{criterio}: {Array.isArray(valor) ? valor.join(', ') : valor}
							</li>{/if}{/each}
				</ul>
			</details>
			{#if execucao.metricas.total !== undefined}{@render metricas(execucao.metricas)}{/if}
			<div class="max-h-64 overflow-auto rounded-md bg-muted p-3">
				<h4 class="mb-2 text-sm font-medium">Log da execução</h4>
				<ol class="space-y-2 text-xs">
					{#each execucao.logs as log}<li>
							<time>{data(log.horario)}</time> · <strong>{log.etapa}</strong>: {log.mensagem}
						</li>{/each}
				</ol>
			</div>
		</details>
	{:else}
		<p class="text-sm text-muted-foreground">
			{carregando
				? 'Carregando histórico…'
				: emTreino
					? 'Aguardando registro da execução.'
					: 'Nenhum treinamento registrado neste histórico.'}
		</p>
		{#if contexto.modelo}<div class="space-y-3 rounded-md border p-3">
				<p class="text-sm">
					Modelo anterior #{contexto.modelo.id}. Logs detalhados não estavam disponíveis nesta
					versão.
				</p>
				{@render metricas(contexto.modelo.metricas)}
			</div>{/if}
	{/each}
	{#if historico.total > 20}<div class="flex items-center gap-3">
			<Button variant="outline" disabled={pagina === 1 || carregando} onclick={() => pagina--}>
				Anteriores
			</Button><span class="text-sm">Página {pagina}</span><Button
				variant="outline"
				disabled={pagina * 20 >= historico.total || carregando}
				onclick={() => pagina++}
			>
				Próximos
			</Button>
		</div>{/if}
</section>
