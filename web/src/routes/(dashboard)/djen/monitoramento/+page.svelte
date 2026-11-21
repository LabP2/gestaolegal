<script lang="ts">
	import ProgressoBusca from '#lib/components/djen/progresso-busca.svelte';
	import { api } from '#lib/api-client.ts';
	import { definirUnidadeAtiva } from '#lib/stores/unidade.ts';
	import { goto, refreshAll } from '$app/navigation';
	import { page } from '$app/state';
	import { Button } from '#lib/components/ui/button/index.ts';
	import { Input } from '#lib/components/ui/input/index.ts';
	import * as Select from '#lib/components/ui/select/index.ts';
	import FiltrosBusca from '#lib/components/djen/filtros-busca.svelte';
	import Search from '@lucide/svelte/icons/search';
	import CircleHelp from '@lucide/svelte/icons/circle-help';
	import History from '@lucide/svelte/icons/history';
	import * as Dialog from '#lib/components/ui/dialog/index.ts';
	import { BUSCA_PARTE_MAX_DIAS } from '#lib/types/index.ts';
	import BuscaParte from '#lib/components/djen/busca-parte.svelte';
	import { MAX_TRIBUNAIS } from '#lib/utils/tribunais-djen.ts';
	import { mensagemDeErro } from '#lib/utils/erros.ts';
	import { toast } from 'svelte-sonner';
	import type { Monitoramento, LogsMonitoramento } from '#lib/types/djen.ts';
	import type { PageProps } from './$types';
	let { data }: PageProps = $props();
	const abas = [
		{ id: 'oab', nome: 'OAB' },
		{ id: 'parte', nome: 'Nome da Parte' },
		{ id: 'processo', nome: 'Número do Processo' },
		{ id: 'logs', nome: 'Logs de varredura' }
	];
	const aba = $derived(page.url.searchParams.get('aba') || 'oab');
	let valor = $state('');
	let tribunais = $state<string[]>([]);
	let ocupado = $state(false);
	let ajudaAberta = $state(false);
	let parteOcupada = $state(false);
	const bloqueado = $derived(ocupado || parteOcupada);
	let buscaEmAndamento = $state<string | null>(null);
	let de = $state(new Date(Date.now() - 6 * 86400000).toLocaleDateString('en-CA'));
	let ate = $state(new Date().toLocaleDateString('en-CA'));
	let logs = $state<LogsMonitoramento>({
		items: [],
		total: 0,
		page: 1,
		per_page: 30,
		retencao_dias: 90
	});
	let status = $state('todos');
	let origem = $state('todos');
	let modo = $state('todos');
	let logDe = $state('');
	let logAte = $state('');
	let logUnidade = $state<number | undefined>(undefined);
	$effect(() => {
		logs = data.logs;
	});
	const itens = $derived(data.monitoramentos.filter((m) => m.tipo === aba));
	const ativos = $derived(itens.filter((m) => m.ativo));
	function corpo(item?: Monitoramento) {
		return {
			tipo: item?.tipo || aba,
			valor: item?.valor || valor,
			tribunais,
			de,
			ate,
			...(item ? { unidade_id: item.unidade_id } : {})
		};
	}
	async function cadastrar() {
		ocupado = true;
		try {
			await api.post('djen/monitoramentos', corpo());
			toast.success('Item adicionado ao monitoramento');
			valor = '';
			await refreshAll();
		} catch (e) {
			toast.error(mensagemDeErro(e, 'Não foi possível cadastrar'));
		} finally {
			ocupado = false;
		}
	}
	async function buscar(item?: Monitoramento, historico = false) {
		if (bloqueado) return;
		const tipoConsultado = item?.tipo || aba;
		const numeroConsultado = (item?.valor || valor).replace(/\D/g, '');
		ocupado = true;
		buscaEmAndamento = (historico ? 'todo o histórico de ' : '') + (item?.valor || valor);
		try {
			const resultado = await api.post<
				{ status: string; encontradas: number; vinculadas: number }[]
			>(
				'djen/monitoramentos/buscar',
				historico
					? {
							tipo: 'processo',
							valor: item?.valor || valor,
							historico_completo: true,
							...(item ? { unidade_id: item.unidade_id } : {})
						}
					: corpo(item)
			);
			const n = resultado.reduce((total, r) => total + r.encontradas, 0);
			const vinculadas = resultado.reduce((total, r) => total + (r.vinculadas ?? 0), 0);
			if (resultado.some((r) => r.status !== 'ok'))
				toast.warning(`Busca incompleta. ${n} resultados recebidos. Consulte os logs.`);
			else
				toast.success(
					`Busca concluída: ${n} resultados salvos; ${vinculadas} publicação(ões) vinculada(s) automaticamente.`
				);
			if (tipoConsultado === 'processo' && resultado.every((r) => r.status === 'ok')) {
				if (item) definirUnidadeAtiva(item.unidade_id);
				await goto(`/djen?numero_processo=${encodeURIComponent(numeroConsultado)}`, {
					refreshAll: true
				});
			} else {
				await refreshAll();
			}
		} catch (e) {
			toast.error(mensagemDeErro(e, 'Não foi possível consultar'));
		} finally {
			ocupado = false;
			buscaEmAndamento = null;
		}
	}
	async function buscarTodos() {
		if (bloqueado || !ativos.length) return;
		// Congela a lista e os filtros: mudanças na tela não alteram o lote em curso.
		const fila = ativos.map((item) => ({ ...corpo(item), tribunais: [...tribunais] }));
		ocupado = true;
		let encontradas = 0;
		let vinculadas = 0;
		let falhas = 0;
		try {
			for (const [indice, pedido] of fila.entries()) {
				buscaEmAndamento = `item ${indice + 1} de ${fila.length}: ${pedido.valor}`;
				try {
					const resultados = await api.post<
						{ status: string; encontradas: number; vinculadas: number }[]
					>('djen/monitoramentos/buscar', pedido);
					encontradas += resultados.reduce((n, r) => n + r.encontradas, 0);
					vinculadas += resultados.reduce((n, r) => n + (r.vinculadas ?? 0), 0);
					if (resultados.some((r) => r.status !== 'ok')) falhas++;
				} catch {
					falhas++;
				}
			}
			const resumo = `${fila.length} itens consultados: ${encontradas} resultados recebidos; ${vinculadas} publicações vinculadas automaticamente.`;
			if (falhas)
				toast.warning(
					`${resumo} ${falhas} item(ns) com falha ou consulta incompleta. Consulte os logs e tente novamente.`
				);
			else toast.success(resumo);
			await refreshAll();
		} catch (e) {
			toast.error(mensagemDeErro(e, 'Não foi possível atualizar a lista após a busca'));
		} finally {
			ocupado = false;
			buscaEmAndamento = null;
		}
	}

	async function alterar(item: Monitoramento, remover = false) {
		ocupado = true;
		try {
			if (remover) await api.delete(`djen/monitoramentos/${item.id}`);
			else await api.patch(`djen/monitoramentos/${item.id}`, { ativo: !item.ativo });
			toast.success(
				remover ? 'Monitoramento removido; publicações preservadas' : 'Monitoramento atualizado'
			);
			await refreshAll();
		} catch (e) {
			toast.error(mensagemDeErro(e, 'Não foi possível atualizar'));
		} finally {
			ocupado = false;
		}
	}
	async function filtrarLogs(pagina = 1) {
		ocupado = true;
		try {
			const p = new URLSearchParams({ page: String(pagina) });
			for (const [k, v] of Object.entries({
				status,
				origem,
				modo,
				de: logDe,
				ate: logAte,
				unidade_id: logUnidade ? String(logUnidade) : ''
			}))
				if (v && v !== 'todos') p.set(k, v);
			logs = await api.get<LogsMonitoramento>(`djen/monitoramentos/logs?${p}`);
		} catch (e) {
			toast.error(mensagemDeErro(e, 'Não foi possível carregar os logs'));
		} finally {
			ocupado = false;
		}
	}
	function unidadeNome(id: number) {
		return data.me.unidades?.find((u) => u.id === id)?.nome || `Unidade ${id}`;
	}
	function horario(s: string | null) {
		return s ? s.replace('T', ' ').slice(0, 19) : '—';
	}
</script>

{#if buscaEmAndamento !== null}
	<ProgressoBusca detalhe={`Consultando ${buscaEmAndamento} e salvando as publicações.`} />
{/if}

<div class="space-y-6">
	<div>
		<div class="flex items-center gap-2">
			<h1 class="text-2xl font-semibold">Monitoramento do DJEN</h1>
			<Button
				variant="ghost"
				size="icon"
				aria-label="Ajuda sobre o monitoramento"
				title="Ajuda"
				onclick={() => (ajudaAberta = true)}
			>
				<CircleHelp class="size-5" />
			</Button>
			<Button variant="outline" size="sm" href="/djen/monitoramento/execucoes" class="ml-auto">
				<History /> Ver execuções
			</Button>
		</div>
		<p class="text-muted-foreground">
			Rotina diária: 04h ({data.logs.agendamento?.janela_dias ?? 7} dias), 10h e 16h ({data.logs
				.agendamento?.janela_diurna_dias ?? 3} dias), horário de Brasília. As buscas preservam as decisões
			anteriores.
		</p>
	</div>
	{#if data.logs.agendamento?.habilitado === false}
		<p class="rounded-lg border bg-muted p-3 text-sm">
			O monitoramento automático está desligado neste ambiente. As buscas manuais continuam
			disponíveis.
		</p>
	{/if}

	<nav aria-label="Tipos de monitoramento" class="flex flex-wrap gap-2 border-b pb-3">
		{#each abas as item}<Button
				variant={aba === item.id ? 'default' : 'outline'}
				href={`/djen/monitoramento?aba=${item.id}`}
			>
				{item.nome}
			</Button>{/each}
	</nav>
	{#if aba !== 'logs'}
		{#if aba === 'parte'}<BuscaParte
				data={{ me: data.me }}
				monitoramento
				{buscarTodos}
				semItensAtivos={ativos.length === 0}
				ocupadoExterno={ocupado}
				onOcupado={(valor) => (parteOcupada = valor)}
				onFiltros={(f) => {
					de = f.de;
					ate = f.ate;
					tribunais = f.tribunais;
				}}
			/>{:else}
			<div class="space-y-6">
				<div>
					<p class="text-muted-foreground">
						Todas as publicações recebidas são salvas no acervo, mesmo sem importação ou
						classificação.
					</p>
				</div>
				<form
					class="space-y-4 rounded-lg border bg-card p-6"
					onsubmit={(event) => {
						event.preventDefault();
						if (valor.trim()) void buscar();
					}}
				>
					<div class="flex flex-wrap items-end gap-3">
						<div class="w-full min-w-0 flex-1 sm:min-w-72">
							<label for="monitoramento-item" class="mb-1 block text-sm font-medium">
								{aba === 'oab' ? 'OAB (número/UF)' : 'Número CNJ'}
							</label>
							<Input
								id="monitoramento-item"
								bind:value={valor}
								placeholder={aba === 'oab' ? '123456/MG' : '0000000-00.0000.0.00.0000'}
							/>
						</div>
					</div>
					<div class="flex flex-wrap items-end gap-3">
						<FiltrosBusca bind:de bind:ate bind:tribunais unidades={data.me.unidades} />
						<Button
							type="button"
							variant="outline"
							disabled={bloqueado || !valor.trim()}
							onclick={cadastrar}
						>
							Adicionar ao monitoramento
						</Button>
						<Button type="submit" disabled={bloqueado || !valor.trim()}>
							<Search class="mr-2 h-4 w-4" />{buscaEmAndamento ? 'Consultando…' : 'Buscar agora'}
						</Button>
						{#if aba === 'processo'}
							<Button
								type="button"
								variant="outline"
								disabled={bloqueado || !valor.trim()}
								onclick={() => buscar(undefined, true)}
							>
								Buscar todas as publicações
							</Button>
						{/if}
						<Button
							type="button"
							variant="outline"
							disabled={bloqueado || !ativos.length}
							onclick={buscarTodos}
						>
							Buscar todos
						</Button>
					</div>
					<p class="text-xs text-muted-foreground">
						Período de até {BUSCA_PARTE_MAX_DIAS} dias e até {MAX_TRIBUNAIS} tribunais por busca. Sem
						tribunal marcado, busca em todos. Na rotina automática, {aba === 'oab'
							? 'OABs'
							: 'processos'} consultam todos os tribunais.
					</p>
				</form>
			</div>
		{/if}
		<section class="space-y-3 rounded-lg border bg-card p-6">
			<h2 class="text-lg font-semibold">Itens monitorados</h2>
			<p class="text-sm text-muted-foreground">
				“Buscar agora” usa o período e os tribunais do formulário acima. “Buscar todos” consulta os
				itens ativos desta aba, nas unidades listadas, com os mesmos filtros. Pausar ou remover
				mantém as publicações.
			</p>
			{#if aba === 'processo'}<p class="text-sm text-muted-foreground">
					“Buscar todas as publicações” consulta todo o histórico disponível no DJEN, em todos os
					tribunais, sem usar os filtros de período. O CNJ abre os detalhes quando há um processo
					cadastrado na mesma unidade.
				</p>{/if}
			{#each itens as item}<div
					class="flex flex-wrap items-center justify-between gap-3 border-b py-3"
				>
					<div>
						{#if item.tipo === 'processo' && item.processo_id}
							<a
								class="font-semibold text-primary underline-offset-4 hover:underline"
								href={`/processos/${item.processo_id}`}
								onclick={() => definirUnidadeAtiva(item.unidade_id)}
							>
								{item.valor}
							</a>
						{:else}<strong>{item.valor}</strong>{/if}
						<p class="text-sm text-muted-foreground">
							{unidadeNome(item.unidade_id)} · {item.ativo ? 'Ativo' : 'Pausado'}{item.automatico
								? ' · Cadastro automático'
								: ''}
						</p>
						<p class="text-sm">
							{item.tribunais.join(', ') || 'Todos os tribunais'} · Último sucesso: {item.ultimo_sucesso ||
								'Ainda não consultado'}
						</p>
					</div>
					<div class="flex flex-wrap gap-2">
						{#if item.tipo === 'processo'}
							<Button
								size="sm"
								variant="outline"
								disabled={bloqueado}
								onclick={() => buscar(item, true)}
							>
								Buscar todas as publicações
							</Button>
						{/if}
						<Button size="sm" variant="outline" disabled={bloqueado} onclick={() => buscar(item)}>
							Buscar agora
						</Button><Button
							size="sm"
							variant="outline"
							disabled={bloqueado}
							onclick={() => alterar(item)}
						>
							{item.ativo ? 'Pausar' : 'Retomar'}
						</Button><Button
							size="sm"
							variant="ghost"
							disabled={bloqueado}
							onclick={() => alterar(item, true)}
						>
							Remover
						</Button>
					</div>
				</div>{:else}<p class="text-muted-foreground">Nenhum item monitorado nesta aba.</p>{/each}
		</section>
	{:else}
		<section class="space-y-4 rounded-lg border bg-card p-6">
			<h2 class="text-lg font-semibold">Logs de varredura</h2>
			<p class="text-muted-foreground">
				Histórico mantido por {logs.retencao_dias} dias. Horários de Brasília.
			</p>
			<div class="flex flex-wrap items-end gap-3">
				<label>De<Input type="date" bind:value={logDe} /></label><label>
					Até<Input type="date" bind:value={logAte} />
				</label>
				<Select.Root type="single" bind:value={status}>
					<Select.Trigger aria-label="Status">
						{status === 'todos' ? 'Todos os status' : status}
					</Select.Trigger><Select.Content>
						{#each ['todos', 'aguardando', 'executando', 'ok', 'parcial', 'erro', 'interrompida'] as v}<Select.Item
								value={v}
							>
								{v}
							</Select.Item>{/each}
					</Select.Content>
				</Select.Root>
				<Select.Root type="single" bind:value={origem}>
					<Select.Trigger aria-label="Tipo">
						{origem === 'todos' ? 'Todos os tipos' : origem}
					</Select.Trigger><Select.Content>
						{#each ['todos', 'oab', 'parte', 'processo'] as v}<Select.Item value={v}>
								{v}
							</Select.Item>{/each}
					</Select.Content>
				</Select.Root>
				<Select.Root type="single" bind:value={modo}>
					<Select.Trigger aria-label="Execução">
						{modo === 'todos' ? 'Manual e automática' : modo}
					</Select.Trigger><Select.Content>
						{#each ['todos', 'manual', 'automatico'] as v}<Select.Item value={v}>
								{v}
							</Select.Item>{/each}
					</Select.Content>
				</Select.Root>
				<Input
					aria-label="ID da unidade"
					placeholder="ID da unidade"
					type="number"
					bind:value={logUnidade}
					class="w-40"
				/>
				<Button disabled={bloqueado} onclick={() => filtrarLogs()}>Filtrar / atualizar</Button>
			</div>
			{#each logs.items as log}<details class="rounded border p-3">
					<summary class="cursor-pointer">
						{horario(log.inicio)} · {log.origem} · {log.modo} · {log.status} · {log.encontradas} encontradas
						/ {log.novas} novas
					</summary>
					<div class="mt-3 space-y-1 text-sm">
						<p>{unidadeNome(log.unidade_id)} · Execução: {log.execucao_id || 'Avulsa'}</p>
						<p>
							Fim: {horario(log.fim)} · Duração: {log.duracao_segundos === null
								? 'Em andamento'
								: `${log.duracao_segundos}s`}
						</p>
						{#each Object.entries(log.parametros) as [chave, valor]}<p>
								{chave}: {valor ?? 'Todos'}
							</p>{/each}{#if log.mensagem}<p class="text-destructive">{log.mensagem}</p>{/if}
					</div>
				</details>{:else}<p>Nenhuma consulta encontrada.</p>{/each}
			<div class="flex items-center gap-3">
				<Button
					variant="outline"
					disabled={bloqueado || logs.page <= 1}
					onclick={() => filtrarLogs(logs.page - 1)}
				>
					Anterior
				</Button><span>{logs.total} consultas · Página {logs.page}</span><Button
					variant="outline"
					disabled={bloqueado || logs.page * logs.per_page >= logs.total}
					onclick={() => filtrarLogs(logs.page + 1)}
				>
					Próxima
				</Button>
			</div>
		</section>
	{/if}
</div>

<Dialog.Root bind:open={ajudaAberta}>
	<Dialog.Content class="sm:max-w-lg">
		<Dialog.Header>
			<Dialog.Title>Como funciona o monitoramento</Dialog.Title>
			<Dialog.Description>
				O que cada tipo consulta no DJEN e em quais tribunais.
			</Dialog.Description>
		</Dialog.Header>
		<div class="space-y-3 text-sm">
			<p>
				<strong>Nome da parte:</strong> a consulta é feita apenas nos tribunais selecionados, e selecionar
				ao menos um é obrigatório. Cada tribunal gera uma consulta separada: marcar TJMG e TRT3 faz duas
				consultas. Isso evita trazer publicações de homônimos do país inteiro e estourar o limite de
				páginas da API.
			</p>
			<p>
				Se o mesmo nome for monitorado mais de uma vez com tribunais diferentes (por exemplo, em
				unidades diferentes), a rotina consulta a união desses tribunais.
			</p>
			<p>
				<strong>OAB e número do processo:</strong> não usam filtro de tribunal; a consulta abrange todos
				os tribunais.
			</p>
			<p>
				<strong>Rotina automática:</strong> às 04h (últimos {data.logs.agendamento?.janela_dias ??
					7}
				dias), 10h e 16h (últimos {data.logs.agendamento?.janela_diurna_dias ?? 3} dias), horário de
				Brasília. Processos ativos dos casos entram no monitoramento automaticamente.
			</p>
		</div>
		<Dialog.Footer>
			<Button onclick={() => (ajudaAberta = false)}>Entendi</Button>
		</Dialog.Footer>
	</Dialog.Content>
</Dialog.Root>
