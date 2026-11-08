<script lang="ts">
	import DataTable from '$lib/components/data-table.svelte';
	import Input from '$lib/components/ui/input/input.svelte';
	import * as Select from '$lib/components/ui/select';
	import StatusSincronizacao from './status-sincronizacao.svelte';
	import { page } from '$app/state';
	import { afterNavigate } from '$app/navigation';
	import { usePaginatedFilters } from '$lib';
	import {
		DJEN_PAPEIS_GESTAO,
		SITUACAO_PUBLICACAO_LABEL,
		type Paginated,
		type PublicacaoListItem,
		type StatusDjen
	} from '$lib/types';
	import Eye from '@lucide/svelte/icons/eye';
	import Briefcase from '@lucide/svelte/icons/briefcase';

	let {
		titulo,
		descricao,
		publicacoes,
		status,
		urole,
		situacaoFixa
	}: {
		titulo: string;
		descricao?: string;
		publicacoes: Paginated<PublicacaoListItem>;
		status: StatusDjen;
		urole: string;
		/** Caixa "Sem caso": a situação não é filtro, é a própria página. */
		situacaoFixa?: string;
	} = $props();

	const TODOS = 'todos';
	const podeVerSemCaso = $derived(DJEN_PAPEIS_GESTAO.includes(urole));

	type Filtros = {
		q: string;
		inicio: string;
		fim: string;
		tribunal: string;
		tipo: string;
		oab: string;
		situacao: string;
	};

	function filtrosDaUrl(url: URL): Filtros {
		const p = url.searchParams;
		return {
			q: p.get('q') ?? '',
			inicio: p.get('inicio') ?? '',
			fim: p.get('fim') ?? '',
			tribunal: p.get('tribunal') ?? TODOS,
			tipo: p.get('tipo') ?? TODOS,
			oab: p.get('oab') ?? '',
			situacao: p.get('situacao') ?? TODOS
		};
	}

	const semTodos = (v: string) => (v === TODOS ? '' : v);

	const { filters, applyFilters, setFilters } = usePaginatedFilters<Filtros>({
		initialFilters: filtrosDaUrl(page.url),
		buildParams: (f) => ({
			q: f.q.trim(),
			inicio: f.inicio,
			fim: f.fim,
			tribunal: semTodos(f.tribunal),
			tipo: semTodos(f.tipo),
			oab: f.oab.trim(),
			situacao: situacaoFixa ?? semTodos(f.situacao)
		})
	});

	// Voltar/avançar no navegador ou clicar no menu: os filtros seguem a URL.
	afterNavigate((nav) => {
		if (nav.type !== 'goto') setFilters(filtrosDaUrl(page.url));
	});

	const situacoes = $derived([
		{ value: TODOS, label: 'Todas' },
		{ value: 'vinculada', label: SITUACAO_PUBLICACAO_LABEL.vinculada },
		...(podeVerSemCaso
			? [
					{ value: 'pendente', label: SITUACAO_PUBLICACAO_LABEL.pendente },
					{ value: 'descartada', label: SITUACAO_PUBLICACAO_LABEL.descartada }
				]
			: [])
	]);

	const linhas = $derived({
		...publicacoes,
		items: publicacoes.items.map((p) => ({
			...p,
			processo: p.numero_processo_mascara ?? p.numero_processo,
			caso: p.id_caso ? `#${p.id_caso}` : '—',
			situacao_exibida: p.ativo ? p.situacao : 'cancelada'
		}))
	});

	const situacaoBadge = {
		vinculada: { text: 'Vinculada', variant: 'default' as const },
		pendente: { text: 'Sem caso', variant: 'outline' as const },
		descartada: { text: 'Descartada', variant: 'secondary' as const },
		cancelada: { text: 'Cancelada no DJEN', variant: 'destructive' as const }
	};
</script>

<div class="space-y-6">
	<div>
		<h1 class="text-3xl font-bold tracking-tight">{titulo}</h1>
		{#if descricao}<p class="text-muted-foreground">{descricao}</p>{/if}
	</div>

	<StatusSincronizacao {status} />

	<div class="rounded-lg border bg-card p-6">
		<div class="mb-4 flex flex-wrap items-end gap-3">
			<div class="w-full min-w-0 flex-1 sm:min-w-72">
				<label for="djen-q" class="mb-1 block text-sm font-medium">Texto ou número</label>
				<Input
					id="djen-q"
					bind:value={filters.q}
					ondebounceinput={() => applyFilters()}
					debounceMs={500}
					placeholder="Buscar no texto, vara, classe ou número do processo"
				/>
			</div>
			<div>
				<label for="djen-inicio" class="mb-1 block text-sm font-medium">De</label>
				<Input
					id="djen-inicio"
					type="date"
					bind:value={filters.inicio}
					onchange={() => applyFilters()}
				/>
			</div>
			<div>
				<label for="djen-fim" class="mb-1 block text-sm font-medium">Até</label>
				<Input id="djen-fim" type="date" bind:value={filters.fim} onchange={() => applyFilters()} />
			</div>
			<div>
				<span class="mb-1 block text-sm font-medium">Tribunal</span>
				<Select.Root
					type="single"
					bind:value={filters.tribunal}
					onValueChange={() => applyFilters()}
				>
					<Select.Trigger class="w-[140px]" aria-label="Tribunal">
						{filters.tribunal === TODOS ? 'Todos' : filters.tribunal}
					</Select.Trigger>
					<Select.Content>
						<Select.Item value={TODOS}>Todos</Select.Item>
						{#each status.filtros.tribunais as t (t)}
							<Select.Item value={t}>{t}</Select.Item>
						{/each}
					</Select.Content>
				</Select.Root>
			</div>
			<div>
				<span class="mb-1 block text-sm font-medium">Tipo</span>
				<Select.Root type="single" bind:value={filters.tipo} onValueChange={() => applyFilters()}>
					<Select.Trigger class="w-[180px]" aria-label="Tipo">
						{filters.tipo === TODOS ? 'Todos' : filters.tipo}
					</Select.Trigger>
					<Select.Content>
						<Select.Item value={TODOS}>Todos</Select.Item>
						{#each status.filtros.tipos as t (t)}
							<Select.Item value={t}>{t}</Select.Item>
						{/each}
					</Select.Content>
				</Select.Root>
			</div>
			<div class="w-36">
				<label for="djen-oab" class="mb-1 block text-sm font-medium">OAB</label>
				<Input
					id="djen-oab"
					bind:value={filters.oab}
					ondebounceinput={() => applyFilters()}
					debounceMs={700}
					placeholder="123456/MG"
				/>
			</div>
			{#if !situacaoFixa}
				<div>
					<span class="mb-1 block text-sm font-medium">Situação</span>
					<Select.Root
						type="single"
						bind:value={filters.situacao}
						onValueChange={() => applyFilters()}
					>
						<Select.Trigger class="w-[150px]" aria-label="Situação">
							{situacoes.find((s) => s.value === filters.situacao)?.label ?? 'Todas'}
						</Select.Trigger>
						<Select.Content>
							{#each situacoes as s (s.value)}
								<Select.Item value={s.value}>{s.label}</Select.Item>
							{/each}
						</Select.Content>
					</Select.Root>
				</div>
			{/if}
		</div>

		<DataTable
			data={linhas}
			emptyText="Nenhuma publicação encontrada."
			onPageChange={(p) => applyFilters({ page: p })}
			columns={[
				{ header: 'Data', key: 'data_disponibilizacao', type: 'date', class: 'w-[110px]' },
				{ header: 'Tribunal', key: 'sigla_tribunal', class: 'w-[90px]' },
				{ header: 'Vara', key: 'nome_orgao', type: 'preview', previewClass: 'max-w-[220px]' },
				{ header: 'Tipo', key: 'tipo_comunicacao', class: 'w-[140px]' },
				{ header: 'Processo', key: 'processo', type: 'mono', class: 'w-[220px]' },
				{ header: 'Caso', key: 'caso', class: 'w-[80px]' },
				{
					header: 'Situação',
					key: 'situacao_exibida',
					type: 'badge',
					badgeMap: situacaoBadge,
					class: 'w-[130px]'
				}
			]}
			actions={{
				class: 'w-[110px] text-right',
				buttons: [
					{ title: 'Ver publicação', href: (p) => `/djen/publicacoes/${p.id}`, icon: Eye },
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
