<script lang="ts">
	import { onMount } from 'svelte';
	import { api } from '$lib/api-client';
	import { Button } from '$lib/components/ui/button';
	import * as Card from '$lib/components/ui/card';
	import Checkbox from '$lib/components/ui/checkbox/checkbox.svelte';
	import {
		ORIGEM_EXEMPLO_LABEL,
		ROTULO_EXEMPLO_LABEL,
		type OrigemExemplo,
		type ResumoExemplos,
		type RotuloExemplo
	} from '$lib/types';
	import { baixarArquivoDaApi } from '$lib/utils/download';
	import { mensagemDeErro } from '$lib/utils/erros';
	import Download from '@lucide/svelte/icons/download';
	import { toast } from 'svelte-sonner';

	// Banco de exemplos rotulados do DJEN (só admin): contagens e exportação.
	let resumo = $state<ResumoExemplos | null>(null);
	let erro = $state<string | null>(null);
	let incluirNaoRevisadas = $state(false);
	let exportando = $state(false);

	const ROTULOS: RotuloExemplo[] = ['pertinente', 'nao_pertinente', 'nao_revisada'];

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
		<Card.Title>Banco de exemplos</Card.Title>
		<Card.Description>
			Publicações rotuladas como pertinentes ou não, para treinar a sugestão automática.
			{#if resumo}
				O texto dos rotulados é apagado {resumo.retencao_dias} dias depois do rótulo; as não revisadas
				somem em {resumo.retencao_nao_revisadas_dias} dias.
			{/if}
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
					Incluir as não revisadas
				</label>
			</div>
		{/if}
	</Card.Content>
</Card.Root>
