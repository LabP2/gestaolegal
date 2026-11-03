<script lang="ts">
	import { Button } from '$lib/components/ui/button';
	import DataTable from '$lib/components/data-table.svelte';
	import type { PageProps } from './$types';
	import Eye from '@lucide/svelte/icons/eye';
	import Edit from '@lucide/svelte/icons/edit';
	import Trash2 from '@lucide/svelte/icons/trash-2';
	import {
		SITUACAO_DEFERIMENTO_BADGE_MAP,
		SITUACAO_DEFERIMENTO_OPTIONS
	} from '$lib/constants/situacao-deferimento';
	import { AREA_BADGE_MAP } from '$lib/constants';
	import { api } from '$lib/api-client';
	import Input from '$lib/components/ui/input/input.svelte';
	import { page } from '$app/state';
	import { afterNavigate } from '$app/navigation';
	import * as Select from '$lib/components/ui/select';
	import Checkbox from '$lib/components/ui/checkbox/checkbox.svelte';
	import { usePaginatedFilters } from '$lib';

	let { data }: PageProps = $props();
	const { data: casos, me } = $derived(data);
	// A coluna "Assistido" usa os nomes das partes; o DataTable formata a lista.
	const casosListados = $derived({
		...casos,
		items: casos.items.map((c) => ({ ...c, nomes_assistidos: c.clientes.map((a) => a.nome) }))
	});

	const situacaoFilterOptions = [
		{ value: 'todos', label: 'Todos' },
		...SITUACAO_DEFERIMENTO_OPTIONS
	];

	type CasoFilters = {
		search: string;
		numero_caso: string;
		show_inactive: boolean;
		situacao_deferimento: string;
		participante: string;
		criado_por: string;
	};

	function filtrosDaUrl(url: URL): CasoFilters {
		const q = url.searchParams;
		return {
			search: q.get('search') ?? '',
			numero_caso: q.get('numero_caso') ?? '',
			show_inactive: q.get('show_inactive') === 'true',
			situacao_deferimento: q.get('situacao_deferimento') ?? 'todos',
			// Links antigos usavam ?user=me (só o responsável).
			participante: q.get('participante') ?? (q.get('user') === 'me' ? 'me' : ''),
			criado_por: q.get('criado_por') ?? ''
		};
	}

	const { filters, applyFilters, setFilters } = usePaginatedFilters<CasoFilters>({
		initialFilters: filtrosDaUrl(page.url),
		buildParams: (f) => ({
			search: f.search,
			numero_caso: f.numero_caso,
			show_inactive: f.show_inactive ? 'true' : 'false',
			situacao_deferimento: f.situacao_deferimento,
			participante: f.participante,
			criado_por: f.criado_por
		})
	});

	// Clicar em "Gestão de casos" estando em "Meus casos" (ou voltar no navegador)
	// mantém o mesmo componente; os filtros precisam seguir a nova URL. As
	// navegações do próprio applyFilters (goto) já partem dos filtros atuais.
	afterNavigate((nav) => {
		if (nav.type !== 'goto') setFilters(filtrosDaUrl(page.url));
	});

	const isAdmin = $derived(me.urole === 'admin');

	async function handleDelete(id: number) {
		if (!isAdmin) return;

		await api.delete(`caso/${id}`);

		applyFilters();
	}
</script>

<div class="space-y-6">
	<div class="flex items-center justify-between">
		<h1 class="text-3xl font-bold tracking-tight">
			{filters.participante === 'me' ? 'Meus Casos' : 'Casos'}
		</h1>
		<Button variant="default" href="/casos/cadastrar-novo-caso">Novo Caso</Button>
	</div>

	<div class="grid gap-6">
		<div class="rounded-lg border bg-card p-6">
			<div class="mb-4 flex items-center justify-between">
				<div class="flex w-full flex-wrap items-center justify-between gap-4">
					<div class="flex flex-wrap items-end gap-2">
						<div class="w-40">
							<label for="numero-caso" class="mb-1 block text-sm font-medium">Número do caso</label>
							<Input
								id="numero-caso"
								inputmode="numeric"
								maxlength={10}
								bind:value={filters.numero_caso}
								ondebounceinput={() => {
									setFilters({ numero_caso: filters.numero_caso.replace(/\D/g, '') });
									applyFilters();
								}}
								debounceMs={500}
								placeholder="Número exato"
							/>
						</div>
						<div class="w-full min-w-0 flex-1 sm:min-w-80">
							<label for="busca-casos" class="mb-1 block text-sm font-medium"
								>Descrição ou parte envolvida</label
							>
							<Input
								id="busca-casos"
								bind:value={filters.search}
								ondebounceinput={() => {
									setFilters({ search: filters.search });
									applyFilters();
								}}
								debounceMs={500}
								placeholder="Buscar descrição ou nome..."
							/>
						</div>
						<div>
							<span class="mb-1 block text-sm font-medium">Deferimento</span>
							<Select.Root
								bind:value={filters.situacao_deferimento}
								name="situacao_deferimento"
								type="single"
								onValueChange={() => applyFilters()}
							>
								<Select.Trigger
									class="w-[200px] data-[placeholder]:text-foreground"
									aria-label="Deferimento"
								>
									{situacaoFilterOptions.find(
										(option) => option.value === filters.situacao_deferimento
									)?.label}
								</Select.Trigger>
								<Select.Content>
									{#each situacaoFilterOptions as option}
										<Select.Item value={option.value}>{option.label}</Select.Item>
									{/each}
								</Select.Content>
							</Select.Root>
						</div>
					</div>
					<div class="flex flex-wrap items-center gap-4">
						<label class="flex cursor-pointer items-center gap-2">
							<Checkbox
								checked={filters.participante === 'me'}
								onCheckedChange={(checked) => {
									setFilters({ participante: checked ? 'me' : '' });
									applyFilters();
								}}
							/>
							<span class="text-sm">Apenas meus casos</span>
						</label>
						<label class="flex cursor-pointer items-center gap-2">
							<Checkbox
								checked={filters.criado_por === 'me'}
								onCheckedChange={(checked) => {
									setFilters({ criado_por: checked ? 'me' : '' });
									applyFilters();
								}}
							/>
							<span class="text-sm">Cadastrados por mim</span>
						</label>
						<label class="flex cursor-pointer items-center gap-2">
							<Checkbox
								bind:checked={filters.show_inactive}
								onCheckedChange={() => applyFilters()}
							/>
							<span class="text-sm">Incluir inativos</span>
						</label>
					</div>
				</div>
			</div>

			<DataTable
				data={casosListados}
				onPageChange={(page) => applyFilters({ page })}
				columns={[
					{ header: 'ID', key: 'id', class: 'w-[100px]' },
					{
						header: 'Área do Direito',
						key: 'area_direito',
						type: 'badge',
						class: 'w-[200px]',
						badgeMap: AREA_BADGE_MAP
					},
					{ header: 'Estagiário', key: 'estagiario.nome', class: 'w-[200px]' },
					{ header: 'Assistido', key: 'nomes_assistidos', type: 'array', class: 'w-[220px]' },
					{
						header: 'Deferimento',
						key: 'situacao_deferimento',
						class: 'w-[150px]',
						badgeMap: SITUACAO_DEFERIMENTO_BADGE_MAP,
						type: 'badge'
					},
					{ header: 'Data', key: 'data_criacao', type: 'datetime', class: 'w-[150px]' },
					{ header: 'Ativo', key: 'status', type: 'status', class: 'w-[100px]' }
				]}
				actions={{
					class: 'w-[180px] text-right',
					buttons: [
						{ title: 'Visualizar', href: (c) => `/casos/${c.id}`, icon: Eye },
						{ title: 'Editar', href: (c) => `/casos/${c.id}/editar`, icon: Edit },
						{
							title: 'Desativar',
							icon: Trash2,
							show: (c) => c.status && isAdmin,
							onClick: async (c) => {
								await handleDelete(c.id);
							},
							confirm: {
								title: 'Desativar caso?',
								description:
									'O caso será inativado. Você poderá reativá-lo depois exibindo os registros inativos.',
								confirmText: 'Desativar'
							},
							class: 'h-8 w-8 p-0 text-destructive hover:text-destructive'
						}
					]
				}}
			/>
		</div>
	</div>
</div>
