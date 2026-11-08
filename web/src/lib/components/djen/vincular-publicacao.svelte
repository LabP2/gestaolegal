<script lang="ts">
	import { api } from '$lib/api-client';
	import { Button } from '$lib/components/ui/button';
	import * as Dialog from '$lib/components/ui/dialog';
	import { Input } from '$lib/components/ui/input';
	import { Label } from '$lib/components/ui/label';
	import type { ListProcesso, Paginated, Publicacao } from '$lib/types';
	import { mensagemDeErro } from '$lib/utils/erros';
	import Link from '@lucide/svelte/icons/link';
	import { toast } from 'svelte-sonner';

	let {
		publicacao,
		onVinculada
	}: { publicacao: Publicacao; onVinculada: (p: Publicacao) => void | Promise<void> } = $props();

	let open = $state(false);
	let casoId = $state('');
	let processos = $state<ListProcesso[]>([]);
	let processoId = $state<number | null>(null);
	let buscando = $state(false);
	let salvando = $state(false);
	let erroBusca = $state<string | null>(null);

	function abrir() {
		casoId = '';
		processos = [];
		processoId = null;
		erroBusca = null;
		open = true;
	}

	async function buscarProcessos() {
		const id = Number(casoId);
		if (!Number.isInteger(id) || id <= 0) {
			erroBusca = 'Informe o número do caso.';
			return;
		}
		buscando = true;
		erroBusca = null;
		processoId = null;
		try {
			const r = await api.get<Paginated<ListProcesso>>(`caso/${id}/processos?per_page=50`);
			processos = r.items;
			if (processos.length === 0) erroBusca = 'O caso não tem processos ativos.';
			if (processos.length === 1) processoId = processos[0].id;
		} catch (err) {
			processos = [];
			erroBusca = mensagemDeErro(err, 'Não foi possível carregar os processos do caso.');
		} finally {
			buscando = false;
		}
	}

	async function vincular() {
		if (processoId === null) return;
		salvando = true;
		try {
			const atualizada = await api.post<Publicacao>(`djen/publicacoes/${publicacao.id}/vincular`, {
				processo_id: processoId
			});
			toast.success('Publicação vinculada. O evento foi criado no caso.');
			open = false;
			await onVinculada(atualizada);
		} catch (err) {
			toast.error(mensagemDeErro(err, 'Não foi possível vincular a publicação.'));
		} finally {
			salvando = false;
		}
	}
</script>

<Button variant="outline" onclick={abrir}>
	<Link class="mr-2 h-4 w-4" />
	Vincular a processo
</Button>

<Dialog.Root bind:open>
	<Dialog.Content class="sm:max-w-md">
		<Dialog.Header>
			<Dialog.Title>Vincular a processo</Dialog.Title>
			<Dialog.Description>
				A publicação passa a constar do caso como evento, e a equipe do caso é notificada.
			</Dialog.Description>
		</Dialog.Header>

		<div class="space-y-4">
			<div class="space-y-1">
				<Label for="vincular-caso">Número do caso</Label>
				<div class="flex gap-2">
					<Input
						id="vincular-caso"
						inputmode="numeric"
						bind:value={casoId}
						placeholder="Ex.: 1234"
						onkeydown={(e) => e.key === 'Enter' && buscarProcessos()}
					/>
					<Button variant="secondary" onclick={buscarProcessos} disabled={buscando}>
						{buscando ? 'Buscando...' : 'Buscar'}
					</Button>
				</div>
				{#if erroBusca}
					<p class="text-sm text-destructive">{erroBusca}</p>
				{/if}
			</div>

			{#if processos.length > 0}
				<fieldset class="space-y-2">
					<legend class="text-sm font-medium">Processo</legend>
					{#each processos as p (p.id)}
						<label class="flex cursor-pointer items-center gap-2 text-sm">
							<input type="radio" name="vincular-processo" value={p.id} bind:group={processoId} />
							<span class="font-mono">{p.numero || `Processo #${p.id}`}</span>
							{#if p.especie}<span class="text-muted-foreground">· {p.especie}</span>{/if}
						</label>
					{/each}
				</fieldset>
			{/if}
		</div>

		<Dialog.Footer>
			<Button variant="outline" onclick={() => (open = false)} disabled={salvando}>Cancelar</Button>
			<Button onclick={vincular} disabled={salvando || processoId === null}>
				{salvando ? 'Vinculando...' : 'Vincular'}
			</Button>
		</Dialog.Footer>
	</Dialog.Content>
</Dialog.Root>
