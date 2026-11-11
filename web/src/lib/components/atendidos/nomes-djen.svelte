<script lang="ts">
	import * as Card from '$lib/components/ui/card';
	import { Button } from '$lib/components/ui/button';
	import { Badge } from '$lib/components/ui/badge';
	import { Input } from '$lib/components/ui/input';
	import { api } from '$lib/api-client';
	import { mensagemDeErro } from '$lib/utils/erros';
	import { toast } from 'svelte-sonner';
	import { onMount } from 'svelte';
	import { PROCESSO_PAPEIS_SEM_CASO, type AtendidoNome } from '$lib/types';
	import X from '@lucide/svelte/icons/x';

	/**
	 * Variações do nome da parte (siglas, grafias antigas), usadas na busca por
	 * parte no DJEN (docs/plano-processos-avulsos.md).
	 */
	let { atendidoId, urole }: { atendidoId: number; urole: string } = $props();

	const podeEditar = $derived(PROCESSO_PAPEIS_SEM_CASO.includes(urole));

	let nomes = $state<AtendidoNome[]>([]);
	let carregado = $state(false);
	let novo = $state('');
	let enviando = $state(false);

	onMount(async () => {
		try {
			nomes = await api.get<AtendidoNome[]>(`atendido/${atendidoId}/nomes`);
		} catch (err) {
			toast.error(mensagemDeErro(err, 'Não foi possível carregar as variações do nome.'));
		} finally {
			carregado = true;
		}
	});

	async function adicionar(event: SubmitEvent) {
		event.preventDefault();
		if (!novo.trim()) return;
		enviando = true;
		try {
			nomes = await api.post<AtendidoNome[]>(`atendido/${atendidoId}/nomes`, { nome: novo });
			novo = '';
		} catch (err) {
			toast.error(mensagemDeErro(err, 'Não foi possível adicionar o nome.'));
		} finally {
			enviando = false;
		}
	}

	async function remover(nome: AtendidoNome) {
		try {
			await api.delete(`atendido/${atendidoId}/nomes/${nome.id}`);
			nomes = nomes.filter((n) => n.id !== nome.id);
		} catch (err) {
			toast.error(mensagemDeErro(err, 'Não foi possível remover o nome.'));
		}
	}
</script>

<Card.Root>
	<Card.Header>
		<Card.Title>Nomes para o DJEN</Card.Title>
		<Card.Description>
			Outras formas como a parte aparece nas publicações (sigla, grafia antiga). Entram na busca por
			parte e no filtro da lista de processos.
		</Card.Description>
	</Card.Header>
	<Card.Content class="space-y-4">
		{#if !carregado}
			<p class="text-sm text-muted-foreground">Carregando…</p>
		{:else if nomes.length === 0}
			<p class="text-sm text-muted-foreground">Nenhuma variação cadastrada.</p>
		{:else}
			<div class="flex flex-wrap gap-2">
				{#each nomes as nome (nome.id)}
					<Badge variant="secondary" class="gap-1">
						{nome.nome}
						{#if podeEditar}
							<button
								type="button"
								class="ml-1 rounded-sm hover:text-destructive"
								title="Remover {nome.nome}"
								onclick={() => remover(nome)}
							>
								<X class="h-3 w-3" />
							</button>
						{/if}
					</Badge>
				{/each}
			</div>
		{/if}
		{#if podeEditar}
			<form class="flex max-w-xl gap-2" onsubmit={adicionar}>
				<Input
					bind:value={novo}
					maxlength={150}
					placeholder="Nova variação do nome"
					aria-label="Nova variação do nome"
				/>
				<Button type="submit" variant="outline" disabled={enviando || !novo.trim()}>
					Adicionar
				</Button>
			</form>
		{/if}
	</Card.Content>
</Card.Root>
