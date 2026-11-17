<script lang="ts">
	import { api } from '$lib/api-client';
	import { invalidateAll } from '$app/navigation';
	import { Button } from '$lib/components/ui/button';
	import * as Dialog from '$lib/components/ui/dialog';
	import { Input } from '$lib/components/ui/input';
	import { Label } from '$lib/components/ui/label';
	import type { ListCaso, Paginated } from '$lib/types';
	import { mensagemDeErro } from '$lib/utils/erros';
	import { toast } from 'svelte-sonner';

	let { processoId }: { processoId: number } = $props();
	let open = $state(false);
	let busca = $state('');
	let casos = $state<ListCaso[]>([]);
	let selecionado = $state<number | null>(null);
	let buscando = $state(false);
	let salvando = $state(false);
	let erro = $state('');
	let consultou = $state(false);

	async function buscar() {
		buscando = true;
		erro = '';
		selecionado = null;
		try {
			const params = new URLSearchParams({ per_page: '50' });
			if (/^\d+$/.test(busca.trim())) params.set('numero_caso', busca.trim());
			else params.set('search', busca.trim());
			const resultado = await api.get<Paginated<ListCaso>>(`caso/?${params}`);
			casos = resultado.items;
			consultou = true;
		} catch (e) {
			casos = [];
			erro = mensagemDeErro(e, 'Não foi possível buscar os casos.');
		} finally {
			buscando = false;
		}
	}

	async function vincular() {
		if (selecionado === null || salvando) return;
		salvando = true;
		try {
			const resultado = await api.post<{ eventos_criados: number }>(
				`processos/${processoId}/vincular-caso`,
				{ caso_id: selecionado }
			);
			toast.success(
				`Processo vinculado. ${resultado.eventos_criados} evento(s) criado(s) no caso.`
			);
			open = false;
			await invalidateAll();
		} catch (e) {
			erro = mensagemDeErro(e, 'Não foi possível vincular o processo.');
		} finally {
			salvando = false;
		}
	}
</script>

<Button
	variant="outline"
	onclick={() => {
		open = true;
		busca = '';
		casos = [];
		selecionado = null;
		erro = '';
		consultou = false;
	}}>Vincular a caso</Button
>
<Dialog.Root bind:open>
	<Dialog.Content class="sm:max-w-xl">
		<Dialog.Header>
			<Dialog.Title>Vincular processo a um caso</Dialog.Title>
			<Dialog.Description>
				Selecione um caso ativo desta unidade. As partes atuais serão mantidas. As publicações já
				vinculadas aparecerão como eventos no caso, com suas datas originais, e a equipe será
				notificada.
			</Dialog.Description>
		</Dialog.Header>
		<form
			class="flex items-end gap-2"
			onsubmit={(e) => {
				e.preventDefault();
				buscar();
			}}
		>
			<div class="flex-1 space-y-2">
				<Label for="buscar-caso-processo">Número do caso ou texto da busca</Label>
				<Input
					id="buscar-caso-processo"
					bind:value={busca}
					disabled={salvando || buscando}
					placeholder="Ex.: 1234"
				/>
			</div>
			<Button type="submit" variant="secondary" disabled={buscando || salvando}
				>{buscando ? 'Buscando...' : 'Buscar'}</Button
			>
		</form>
		{#if erro}<p role="alert" class="text-sm text-destructive">{erro}</p>{/if}
		{#if casos.length}
			<fieldset class="max-h-64 space-y-2 overflow-y-auto" disabled={salvando || buscando}>
				<legend class="mb-2 text-sm font-medium"
					>Selecione o caso (até 50 resultados; refine a busca)</legend
				>
				{#each casos as caso (caso.id)}
					<label class="flex cursor-pointer items-start gap-3 rounded-md border p-3 text-sm">
						<input
							type="radio"
							name="caso-do-processo"
							value={caso.id}
							bind:group={selecionado}
							class="mt-1"
						/>
						<span
							><strong>Caso #{caso.id} · {caso.area_direito}</strong><span
								class="block text-muted-foreground">{caso.descricao || 'Sem descrição'}</span
							></span
						>
					</label>
				{/each}
			</fieldset>
		{:else if consultou && !buscando}
			<p class="text-sm text-muted-foreground">
				Nenhum caso encontrado. Crie o caso em Casos e volte aqui para vinculá-lo.
			</p>
		{/if}
		<Dialog.Footer>
			<Button variant="outline" disabled={salvando} onclick={() => (open = false)}>Cancelar</Button>
			<Button disabled={selecionado === null || salvando || buscando} onclick={vincular}
				>{salvando ? 'Vinculando...' : 'Confirmar vínculo'}</Button
			>
		</Dialog.Footer>
	</Dialog.Content>
</Dialog.Root>
