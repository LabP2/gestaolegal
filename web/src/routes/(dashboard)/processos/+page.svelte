<script lang="ts">
	import { Button } from '#lib/components/ui/button/index.ts';
	import DataTable from '#lib/components/data-table.svelte';
	import Input from '#lib/components/ui/input/input.svelte';
	import * as Select from '#lib/components/ui/select/index.ts';
	import { page } from '$app/state';
	import { afterNavigate } from '$app/navigation';
	import { usePaginatedFilters } from '#lib';
	import { PROCESSO_PAPEIS_SEM_CASO, type Paginated } from '#lib/types/index.ts';
	import Eye from '@lucide/svelte/icons/eye';
	import Briefcase from '@lucide/svelte/icons/briefcase';
	import Plus from '@lucide/svelte/icons/plus';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
	const { processos, me } = $derived(data);
	const podeCadastrar = $derived(PROCESSO_PAPEIS_SEM_CASO.includes(me.urole));

	type Filtros = {
		parte: string;
		numero: string;
		distribuicao_de: string;
		distribuicao_ate: string;
		status: string;
		com_caso: string;
	};

	const STATUS = [
		{ value: 'ativo', label: 'Ativos' },
		{ value: 'inativo', label: 'Inativos' },
		{ value: 'todos', label: 'Todos' }
	];
	const COM_CASO = [
		{ value: 'todos', label: 'Com e sem caso' },
		{ value: 'sim', label: 'Com caso' },
		{ value: 'nao', label: 'Sem caso' }
	];

	function filtrosDaUrl(url: URL): Filtros {
		const p = url.searchParams;
		return {
			parte: p.get('parte') ?? '',
			numero: p.get('numero') ?? '',
			distribuicao_de: p.get('distribuicao_de') ?? '',
			distribuicao_ate: p.get('distribuicao_ate') ?? '',
			status: p.get('status') ?? 'ativo',
			com_caso: p.get('com_caso') ?? 'todos'
		};
	}

	const { filters, applyFilters, setFilters } = usePaginatedFilters<Filtros>({
		initialFilters: filtrosDaUrl(new URL(page.url.href)),
		buildParams: (f) => ({
			parte: f.parte.trim(),
			numero: f.numero.trim(),
			distribuicao_de: f.distribuicao_de,
			distribuicao_ate: f.distribuicao_ate,
			status: f.status === 'ativo' ? '' : f.status,
			com_caso: f.com_caso === 'todos' ? '' : f.com_caso
		})
	});

	// Voltar/avançar no navegador ou clicar no menu: os filtros seguem a URL.
	afterNavigate((nav) => {
		if (nav.type !== 'goto') setFilters(filtrosDaUrl(new URL(page.url.href)));
	});

	const linhas = $derived.by(() => {
		const items = processos.items.map((p) => ({
			...p,
			numero_exibido: p.numero || `Processo #${p.id}`,
			caso: p.id_caso ? `#${p.id_caso}` : 'Sem caso'
		}));
		// A API devolve a paginação plana (PaginaProcessos), que é o que o
		// DataTable lê de fato; o tipo `Paginated` do front declara outro formato.
		return { ...processos, items } as unknown as Paginated<(typeof items)[number]>;
	});
</script>

<div class="space-y-6">
	<div class="flex flex-wrap items-center justify-between gap-4">
		<div>
			<h1 class="text-3xl font-bold tracking-tight">Processos</h1>
			<p class="text-muted-foreground">Processos dos casos e processos acompanhados sem caso.</p>
		</div>
		{#if podeCadastrar}
			<Button href="/processos/novo">
				<Plus class="mr-2 h-4 w-4" />
				Novo processo sem caso
			</Button>
		{/if}
	</div>

	<div class="rounded-lg border bg-card p-6">
		<div class="mb-4 flex flex-wrap items-end gap-3">
			<div class="w-full min-w-0 flex-1 sm:min-w-72">
				<label for="processos-parte" class="mb-1 block text-sm font-medium">Nome da parte</label>
				<Input
					id="processos-parte"
					bind:value={filters.parte}
					ondebounceinput={() => applyFilters()}
					debounceMs={500}
					placeholder="Nome, ou variação do nome, de uma parte"
				/>
			</div>
			<div class="w-56">
				<label for="processos-numero" class="mb-1 block text-sm font-medium">Número</label>
				<Input
					id="processos-numero"
					bind:value={filters.numero}
					ondebounceinput={() => applyFilters()}
					debounceMs={500}
					placeholder="Com ou sem máscara"
				/>
			</div>
			<div>
				<label for="processos-de" class="mb-1 block text-sm font-medium">Distribuição de</label>
				<Input
					id="processos-de"
					type="date"
					bind:value={filters.distribuicao_de}
					onchange={() => applyFilters()}
				/>
			</div>
			<div>
				<label for="processos-ate" class="mb-1 block text-sm font-medium">até</label>
				<Input
					id="processos-ate"
					type="date"
					bind:value={filters.distribuicao_ate}
					onchange={() => applyFilters()}
				/>
			</div>
			<div>
				<span class="mb-1 block text-sm font-medium">Status</span>
				<Select.Root type="single" bind:value={filters.status} onValueChange={() => applyFilters()}>
					<Select.Trigger class="w-[130px]" aria-label="Status">
						{STATUS.find((s) => s.value === filters.status)?.label ?? 'Ativos'}
					</Select.Trigger>
					<Select.Content>
						{#each STATUS as s (s.value)}
							<Select.Item value={s.value}>{s.label}</Select.Item>
						{/each}
					</Select.Content>
				</Select.Root>
			</div>
			<div>
				<span class="mb-1 block text-sm font-medium">Caso</span>
				<Select.Root
					type="single"
					bind:value={filters.com_caso}
					onValueChange={() => applyFilters()}
				>
					<Select.Trigger class="w-[160px]" aria-label="Com ou sem caso">
						{COM_CASO.find((s) => s.value === filters.com_caso)?.label ?? 'Com e sem caso'}
					</Select.Trigger>
					<Select.Content>
						{#each COM_CASO as s (s.value)}
							<Select.Item value={s.value}>{s.label}</Select.Item>
						{/each}
					</Select.Content>
				</Select.Root>
			</div>
		</div>

		<DataTable
			data={linhas}
			emptyText="Nenhum processo encontrado."
			onPageChange={(p) => applyFilters({ page: p })}
			columns={[
				{ header: 'Número', key: 'numero_exibido', type: 'mono', class: 'w-[230px]' },
				{ header: 'Partes', key: 'partes', type: 'array', class: 'w-[240px]' },
				{ header: 'Espécie', key: 'especie', class: 'w-[120px]' },
				{ header: 'Vara', key: 'vara', type: 'preview', previewClass: 'max-w-[220px]' },
				{ header: 'Distribuição', key: 'data_distribuicao', type: 'date', class: 'w-[120px]' },
				{ header: 'Caso', key: 'caso', class: 'w-[90px]' },
				{ header: 'DJEN', key: 'total_publicacoes', class: 'w-[70px]' },
				{ header: 'Ativo', key: 'status', type: 'status', class: 'w-[80px]' }
			]}
			actions={{
				class: 'w-[110px] text-right',
				buttons: [
					{ title: 'Ver processo', href: (p) => `/processos/${p.id}`, icon: Eye },
					{
						title: 'Abrir caso',
						href: (p) => `/casos/${p.id_caso}`,
						icon: Briefcase,
						show: (p) => p.id_caso !== null
					}
				]
			}}
		/>
	</div>
</div>
