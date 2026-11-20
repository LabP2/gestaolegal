<script lang="ts">
	import { api } from '#lib/api-client.ts';
	import { Button } from '#lib/components/ui/button/index.ts';
	import type { AcervoItem, AcervoDetalhe } from '#lib/types/djen.ts';
	import { formatDateTime } from '#lib/utils/date.ts';
	import { mensagemDeErro } from '#lib/utils/erros.ts';
	let { item }: { item: AcervoItem } = $props();
	let aberto = $state(false);
	let detalhe = $state<AcervoDetalhe | null>(null);
	let carregando = $state(false);
	let erro = $state('');
	let tentativa = $state(0);
	$effect(() => {
		const id = item.id;
		tentativa;
		if (!aberto) return;
		const controller = new AbortController();
		carregando = true;
		detalhe = null;
		erro = '';
		api
			.get<AcervoDetalhe>(`djen/acervo/${id}`, { signal: controller.signal })
			.then((resultado) => {
				if (!controller.signal.aborted) detalhe = resultado;
			})
			.catch((e) => {
				if (!controller.signal.aborted)
					erro = mensagemDeErro(e, 'Não foi possível carregar os detalhes.');
			})
			.finally(() => {
				if (!controller.signal.aborted) carregando = false;
			});
		return () => controller.abort();
	});
	function linkSeguro(valor?: string | null) {
		try {
			const url = new URL(valor ?? '');
			return ['http:', 'https:'].includes(url.protocol) ? url.href : null;
		} catch {
			return null;
		}
	}
	const original = $derived(linkSeguro(detalhe?.link));
	const certidao = $derived(linkSeguro(detalhe?.link_certidao));
	const rotulos = {
		relevante: 'Relevante',
		irrelevante: 'Irrelevante',
		nao_classificado: 'Não avaliada'
	};
</script>

<details bind:open={aberto} class="border-t pt-3 text-sm">
	<summary class="cursor-pointer font-medium">Detalhes e histórico</summary>
	<div class="mt-3 space-y-4 break-words">
		{#if carregando}<p role="status">Carregando detalhes…</p>
		{:else if erro}<p role="alert">{erro}</p>
			<Button variant="outline" onclick={() => tentativa++}>Tentar novamente</Button>
		{:else if detalhe}
			<div class="flex flex-wrap gap-3">
				{#if original}<a
						href={original}
						target="_blank"
						rel="noopener noreferrer"
						class="text-primary underline"
					>
						Documento no tribunal
					</a>{/if}
				{#if certidao}<a
						href={certidao}
						target="_blank"
						rel="noopener noreferrer"
						class="text-primary underline"
					>
						Certidão do DJEN (PDF)
					</a>{/if}
				{#if item.comunicacao_id}<a
						class="text-primary underline"
						href={`/djen/publicacoes/${item.comunicacao_id}`}
					>
						Abrir operação
					</a>{/if}
				{#if item.id_processo}<a
						class="text-primary underline"
						href={`/processos/${item.id_processo}`}
					>
						Processo #{item.id_processo}
					</a>{/if}
				{#if item.id_caso}<a class="text-primary underline" href={`/casos/${item.id_caso}`}>
						Caso #{item.id_caso}
					</a>{/if}
			</div>
			<dl class="grid gap-2 sm:grid-cols-2">
				<div>
					<dt class="text-muted-foreground">Identificador DJEN</dt>
					<dd>{detalhe.id_djen}</dd>
				</div>
				<div>
					<dt class="text-muted-foreground">Capturada em</dt>
					<dd>{detalhe.capturada_em ? formatDateTime(detalhe.capturada_em) : 'Não informado'}</dd>
				</div>
				{#if detalhe.atualizada_em}<div>
						<dt class="text-muted-foreground">Atualizada em</dt>
						<dd>{formatDateTime(detalhe.atualizada_em)}</dd>
					</div>{/if}
				{#if detalhe.oab_origem}<div>
						<dt class="text-muted-foreground">OAB de captura</dt>
						<dd>{detalhe.oab_origem}</dd>
					</div>{/if}
				{#if detalhe.tipo_comunicacao}<div>
						<dt class="text-muted-foreground">Comunicação</dt>
						<dd>{detalhe.tipo_comunicacao}</dd>
					</div>{/if}
				{#if detalhe.tipo_documento}<div>
						<dt class="text-muted-foreground">Documento</dt>
						<dd>{detalhe.tipo_documento}</dd>
					</div>{/if}
				{#if detalhe.nome_classe}<div>
						<dt class="text-muted-foreground">Classe processual</dt>
						<dd>{detalhe.nome_classe}</dd>
					</div>{/if}
			</dl>
			{#if detalhe.ativo === false}<p>
					Cancelada no DJEN. {detalhe.motivo_cancelamento ?? ''}
				</p>{/if}
			{#if detalhe.advogados?.length}<div>
					<h3 class="font-medium">Advogados</h3>
					<ul>
						{#each detalhe.advogados as adv}<li>
								{adv.nome ?? 'Nome não informado'}{#if adv.numero_oab}
									· OAB {adv.numero_oab}/{adv.uf_oab ?? '—'}{/if}
							</li>{/each}
					</ul>
				</div>{/if}
			<div>
				<h3 class="font-medium">Histórico da classificação</h3>
				<ul class="mt-2 space-y-2">
					{#each detalhe.historico ?? [] as h}<li>
							{h.contexto_nome ? `${h.contexto_nome} · ` : ''}{formatDateTime(h.rotulado_em)}: {rotulos[
								h.rotulo_anterior
							]} → {rotulos[h.rotulo]} · {h.origem === 'reversao' ? 'Reversão' : h.origem} · {h.id_rotulado_por
								? `Usuário #${h.id_rotulado_por}`
								: 'Automático'}
						</li>{:else}<li>Nenhuma avaliação registrada.</li>{/each}
				</ul>
			</div>
		{/if}
	</div>
</details>
