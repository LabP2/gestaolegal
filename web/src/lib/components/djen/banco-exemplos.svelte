<script lang="ts">
	import { onMount } from 'svelte';
	import { api } from '#lib/api-client.ts';
	import { Button } from '#lib/components/ui/button/index.ts';
	import * as Card from '#lib/components/ui/card/index.ts';
	import Checkbox from '#lib/components/ui/checkbox/checkbox.svelte';
	import {
		ORIGEM_EXEMPLO_LABEL,
		ROTULO_EXEMPLO_LABEL,
		type OrigemExemplo,
		type ResumoExemplos,
		type RotuloExemplo
	} from '#lib/types/index.ts';
	import { baixarArquivoDaApi } from '#lib/utils/download.ts';
	import { mensagemDeErro } from '#lib/utils/erros.ts';
	import Download from '@lucide/svelte/icons/download';
	import { toast } from 'svelte-sonner';

	// Acervo para treinamento rotulados do DJEN (só admin): contagens e exportação.
	let resumo = $state<ResumoExemplos | null>(null);
	let erro = $state<string | null>(null);
	let incluirNaoRevisadas = $state(false);
	let exportando = $state(false);

	const ROTULOS: RotuloExemplo[] = ['relevante', 'irrelevante', 'nao_classificado'];

	async function carregar() {
		try {
			resumo = await api.get<ResumoExemplos>('djen/exemplos/resumo');
			erro = null;
		} catch (err) {
			erro = mensagemDeErro(err, 'Não foi possível ler o banco de exemplos.');
		}
	}

	onMount(carregar);

	async function exportar() {
		exportando = true;
		try {
			const hoje = new Date().toISOString().slice(0, 10);
			const query = incluirNaoRevisadas ? '?incluir_nao_revisadas=1' : '';
			await baixarArquivoDaApi(`djen/exemplos/exportar${query}`, `djen-exemplos-${hoje}.jsonl`);
		} catch (err) {
			toast.error(mensagemDeErro(err, 'Não foi possível exportar os exemplos.'));
		} finally {
			exportando = false;
		}
	}
</script>

<Card.Root>
	<Card.Header>
		<Card.Title>Acervo para treinamento</Card.Title>
		<Card.Description>
			Publicações classificadas para treinamento. O acervo permanece salvo para avaliação posterior.
		</Card.Description>
	</Card.Header>
	<Card.Content class="space-y-4">
		{#if erro}
			<p class="text-sm text-destructive">{erro}</p>
		{:else if !resumo}
			<p class="text-sm text-muted-foreground">Carregando…</p>
		{:else}
			<dl class="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
				{#each ROTULOS as rotulo (rotulo)}
					<div class="rounded-md border p-3">
						<dt class="text-muted-foreground">{ROTULO_EXEMPLO_LABEL[rotulo]}</dt>
						<dd class="text-2xl font-semibold tabular-nums">{resumo.por_rotulo[rotulo] ?? 0}</dd>
					</div>
				{/each}
				<div class="rounded-md border p-3">
					<dt class="text-muted-foreground">Ainda com texto</dt>
					<dd class="text-2xl font-semibold tabular-nums">
						{resumo.com_texto}
						<span class="text-sm font-normal text-muted-foreground">de {resumo.total}</span>
					</dd>
				</div>
			</dl>
			{#if Object.keys(resumo.por_origem).length}
				<p class="text-xs text-muted-foreground">
					Por origem:
					{Object.entries(resumo.por_origem)
						.map(
							([origem, n]) => `${ORIGEM_EXEMPLO_LABEL[origem as OrigemExemplo] ?? origem}: ${n}`
						)
						.join(' · ')}
				</p>
			{/if}
			<div class="flex flex-wrap items-center gap-3">
				<Button
					type="button"
					variant="outline"
					disabled={exportando || resumo.total === 0}
					onclick={exportar}
				>
					<Download class="mr-2 h-4 w-4" />
					{exportando ? 'Exportando…' : 'Exportar (JSONL)'}
				</Button>
				<label class="flex items-center gap-2 text-sm">
					<Checkbox
						checked={incluirNaoRevisadas}
						onCheckedChange={(v) => (incluirNaoRevisadas = v === true)}
					/>
					Incluir as não classificadas
				</label>
			</div>
		{/if}
	</Card.Content>
</Card.Root>
