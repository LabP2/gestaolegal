<script lang="ts" module>
	import type { PoloParte } from '#lib/types/index.ts';

	/** Parte escolhida no formulário do processo sem caso. */
	export type ParteEditavel = {
		id_atendido: number;
		nome: string;
		polo: PoloParte | null;
		sem_triagem?: boolean;
	};
</script>

<script lang="ts">
	import { Button } from '#lib/components/ui/button/index.ts';
	import { Badge } from '#lib/components/ui/badge/index.ts';
	import { Input } from '#lib/components/ui/input/index.ts';
	import * as Dialog from '#lib/components/ui/dialog/index.ts';
	import * as Select from '#lib/components/ui/select/index.ts';
	import AtendidoSelectorDialog from '#lib/components/atendido-selector-dialog.svelte';
	import { api } from '#lib/api-client.ts';
	import { mensagemDeErro } from '#lib/utils/erros.ts';
	import { toast } from 'svelte-sonner';
	import {
		POLO_PARTE_LABEL,
		type Atendido,
		type AtendidoSimplificadoInput
	} from '#lib/types/index.ts';
	import Trash2 from '@lucide/svelte/icons/trash-2';
	import UserPlus from '@lucide/svelte/icons/user-plus';

	let { partes = $bindable([]) }: { partes?: ParteEditavel[] } = $props();

	const POLOS = Object.entries(POLO_PARTE_LABEL) as [PoloParte, string][];

	let selecionados = $state<number[]>(partes.map((p) => p.id_atendido));

	function adicionar(atendidos: Atendido[]) {
		// O diálogo já atualizou `selecionados`; as partes cadastradas aqui não
		// vêm em `atendidos` (o diálogo não as carregou), então se preserva pelo id.
		const mantidas = partes.filter((p) => selecionados.includes(p.id_atendido));
		const ids = new Set(mantidas.map((p) => p.id_atendido));
		partes = [
			...mantidas,
			...atendidos
				.filter((a) => !ids.has(a.id))
				.map((a) => ({
					id_atendido: a.id,
					nome: a.nome,
					polo: null,
					sem_triagem: a.sem_triagem
				}))
		];
	}

	function remover(id: number) {
		partes = partes.filter((p) => p.id_atendido !== id);
		selecionados = selecionados.filter((s) => s !== id);
	}

	let aberto = $state(false);
	let enviando = $state(false);
	let nova = $state<AtendidoSimplificadoInput>({ nome: '', cpf: '', cnpj: '', obs: '' });

	async function cadastrar(event: SubmitEvent) {
		event.preventDefault();
		if (!nova.nome.trim()) {
			toast.error('Informe o nome da parte');
			return;
		}
		enviando = true;
		try {
			const criado = await api.post<Atendido>('atendido/simplificado', {
				nome: nova.nome,
				cpf: nova.cpf || null,
				cnpj: nova.cnpj || null,
				obs: nova.obs || null
			});
			partes = [
				...partes,
				{ id_atendido: criado.id, nome: criado.nome, polo: null, sem_triagem: true }
			];
			selecionados = [...selecionados, criado.id];
			toast.success('Parte cadastrada sem triagem');
			nova = { nome: '', cpf: '', cnpj: '', obs: '' };
			aberto = false;
		} catch (err) {
			toast.error(mensagemDeErro(err, 'Não foi possível cadastrar a parte.'));
		} finally {
			enviando = false;
		}
	}
</script>

<div class="space-y-4 rounded-lg border bg-card p-6">
	<div>
		<h2 class="text-lg font-semibold">Partes</h2>
		<p class="text-sm text-muted-foreground">
			Pelo menos uma parte. Busque um atendido ou cadastre a parte sem triagem (só nome e
			documento).
		</p>
	</div>

	<div class="flex flex-wrap gap-2">
		<AtendidoSelectorDialog bind:selectedAtendidosIds={selecionados} onSelect={adicionar} />
		<Button type="button" variant="outline" onclick={() => (aberto = true)}>
			<UserPlus class="mr-2 h-4 w-4" />
			Cadastrar parte sem triagem
		</Button>
	</div>

	{#if partes.length === 0}
		<p class="text-sm text-muted-foreground">Nenhuma parte escolhida.</p>
	{:else}
		<ul class="divide-y rounded-md border">
			{#each partes as parte (parte.id_atendido)}
				<li class="flex flex-wrap items-center gap-3 p-3">
					<span class="min-w-0 flex-1 font-medium">
						{parte.nome}
						{#if parte.sem_triagem}
							<Badge variant="secondary" class="ml-2">Sem triagem</Badge>
						{/if}
					</span>
					<Select.Root
						type="single"
						value={parte.polo ?? ''}
						onValueChange={(v) => (parte.polo = (v || null) as PoloParte | null)}
					>
						<Select.Trigger class="w-[150px]" aria-label="Polo de {parte.nome}">
							{parte.polo ? POLO_PARTE_LABEL[parte.polo] : 'Polo (opcional)'}
						</Select.Trigger>
						<Select.Content>
							<Select.Item value="">Sem polo</Select.Item>
							{#each POLOS as [valor, rotulo] (valor)}
								<Select.Item value={valor}>{rotulo}</Select.Item>
							{/each}
						</Select.Content>
					</Select.Root>
					<Button
						type="button"
						variant="ghost"
						size="icon"
						title="Remover parte"
						onclick={() => remover(parte.id_atendido)}
					>
						<Trash2 class="h-4 w-4" />
					</Button>
				</li>
			{/each}
		</ul>
	{/if}
</div>

<Dialog.Root bind:open={aberto}>
	<Dialog.Content class="sm:max-w-lg">
		<Dialog.Header>
			<Dialog.Title>Cadastrar parte sem triagem</Dialog.Title>
			<Dialog.Description>
				Para partes que não passam pela triagem socioeconômica (órgão público, empresa, parte
				contrária). Fica marcada como “sem triagem” e pode ser completada depois.
			</Dialog.Description>
		</Dialog.Header>
		<form class="space-y-4" onsubmit={cadastrar}>
			<div>
				<label for="parte-nome" class="mb-1 block text-sm font-medium">Nome</label>
				<Input id="parte-nome" bind:value={nova.nome} maxlength={80} required />
			</div>
			<div class="grid gap-4 sm:grid-cols-2">
				<div>
					<label for="parte-cpf" class="mb-1 block text-sm font-medium">CPF</label>
					<Input id="parte-cpf" bind:value={nova.cpf} placeholder="Opcional" />
				</div>
				<div>
					<label for="parte-cnpj" class="mb-1 block text-sm font-medium">CNPJ</label>
					<Input id="parte-cnpj" bind:value={nova.cnpj} placeholder="Opcional" />
				</div>
			</div>
			<div>
				<label for="parte-obs" class="mb-1 block text-sm font-medium">Observações</label>
				<Input id="parte-obs" bind:value={nova.obs} placeholder="Opcional" />
			</div>
			<Dialog.Footer>
				<Button type="button" variant="outline" onclick={() => (aberto = false)}>Cancelar</Button>
				<Button type="submit" disabled={enviando}>Cadastrar</Button>
			</Dialog.Footer>
		</form>
	</Dialog.Content>
</Dialog.Root>
