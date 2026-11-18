<script lang="ts">
	import { Button } from '$lib/components/ui/button';
	import FiltroTribunais from './filtro-tribunais.svelte';
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
		per_page: string;
		q: string;
		nome_parte: string;
		polo: string;
		numero_processo: string;
		inicio: string;
		fim: string;
		tribunal: string[];
		tipo: string;
		oab: string;
		situacao: string;
	};

	function filtrosDaUrl(url: URL): Filtros {
		const p = url.searchParams;
		return {
			per_page: p.get('per_page') ?? '20',
			q: p.get('q') ?? '',
			nome_parte: p.get('nome_parte') ?? '',
			polo: p.get('polo') ?? TODOS,
			numero_processo: p.get('numero_processo') ?? '',
			inicio: p.get('inicio') ?? '',
			fim: p.get('fim') ?? '',
			tribunal: p
				.getAll('tribunal')
				.flatMap((t) => t.split(','))
				.filter(Boolean),
			tipo: p.get('tipo') ?? TODOS,
			oab: p.get('oab') ?? '',
			situacao: p.get('situacao') ?? TODOS
		};
	}

	const semTodos = (v: string) => (v === TODOS ? '' : v);

	const { filters, applyFilters, setFilters } = usePaginatedFilters<Filtros>({
		initialFilters: filtrosDaUrl(page.url),
		buildParams: (f) => ({
			per_page: f.per_page,
			q: f.q.trim(),
			nome_parte: f.nome_parte.trim(),
			polo: semTodos(f.polo),
			numero_processo: f.numero_processo.trim(),
			inicio: f.inicio,
			fim: f.fim,
			tribunal: f.tribunal.join(','),
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
		vinculada: { text: 'Importado', variant: 'default' as const },
		pendente: { text: 'Não analisado', variant: 'outline' as const },
		descartada: { text: 'Descartado', variant: 'secondary' as const },
		cancelada: { text: 'Cancelada no DJEN', variant: 'destructive' as const }
	};
</script>

<div class="space-y-6">
	<div>
		<h1 class="text-3xl font-bold tracking-tight">{titulo}</h1>
		{#if descricao}<p class="text-muted-foreground">{descricao}</p>{/if}
	</div>

	<StatusSincronizacao {status} podeRodar={urole === 'admin'} />

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
				<label for="djen-nome_parte" class="mb-1 block text-sm font-medium">Nome da parte</label
				><Input
					id="djen-nome_parte"
					bind:value={filters.nome_parte}
					ondebounceinput={() => applyFilters()}
					debounceMs={500}
					placeholder="Nome completo ou parte do nome"
				/>
			</div>
			<div class="w-full sm:w-40">
				<span class="mb-1 block text-sm font-medium">Polo da parte</span>
				<Select.Root type="single" bind:value={filters.polo} onValueChange={() => applyFilters()}>
					<Select.Trigger class="w-full" aria-label="Polo da parte"
						>{filters.polo === 'A'
							? 'Ativo'
							: filters.polo === 'P'
								? 'Passivo'
								: 'Todos'}</Select.Trigger
					>
					<Select.Content
						><Select.Item value={TODOS}>Todos</Select.Item><Select.Item value="A">Ativo</Select.Item
						><Select.Item value="P">Passivo</Select.Item></Select.Content
					>
				</Select.Root>
			</div>
			<div>
				<label for="djen-numero_processo" class="mb-1 block text-sm font-medium"
					>Número do processo</label
				><Input
					id="djen-numero_processo"
					bind:value={filters.numero_processo}
					ondebounceinput={() => applyFilters()}
					debounceMs={500}
					placeholder="Com ou sem máscara"
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
			<div class="w-full sm:w-56">
				<FiltroTribunais bind:value={filters.tribunal} onchange={() => applyFilters()} />
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

		<Button
			variant="ghost"
			class="mb-4"
			onclick={() => {
				setFilters({ ...filtrosDaUrl(new URL('/djen', page.url)), per_page: filters.per_page });
				applyFilters();
			}}>Limpar filtros</Button
		>
		<DataTable
			tamanhosPagina
			onPageSizeChange={(n) => {
				setFilters({ per_page: String(n) });
				applyFilters();
			}}
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
