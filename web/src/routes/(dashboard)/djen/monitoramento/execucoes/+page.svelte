<script lang="ts">
	import { api } from '#lib/api-client.ts';
	import { Button } from '#lib/components/ui/button/index.ts';
	import { Input } from '#lib/components/ui/input/index.ts';
	import { Badge, type BadgeVariant } from '#lib/components/ui/badge/index.ts';
	import * as Select from '#lib/components/ui/select/index.ts';
	import ArrowLeft from '@lucide/svelte/icons/arrow-left';
	import { mensagemDeErro } from '#lib/utils/erros.ts';
	import { toast } from 'svelte-sonner';
	import type {
		ExecucoesMonitoramento,
		LogMonitoramento,
		LogsMonitoramento
	} from '#lib/types/djen.ts';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
	let execucoes = $state<ExecucoesMonitoramento>({
		items: [],
		total: 0,
		page: 1,
		per_page: 30,
		retencao_dias: 90
	});
	$effect(() => {
		execucoes = data.execucoes;
	});
	let status = $state('todos');
	let de = $state('');
	let ate = $state('');
	let ocupado = $state(false);
	let abertas = $state<Record<number, { itens: LogMonitoramento[]; total: number; page: number }>>(
		{}
	);
	let carregando = $state<number | null>(null);

	const STATUS: Record<string, { rotulo: string; variante: BadgeVariant }> = {
		ok: { rotulo: 'OK', variante: 'secondary' },
		parcial: { rotulo: 'Parcial', variante: 'outline' },
		erro: { rotulo: 'Erro', variante: 'destructive' },
		executando: { rotulo: 'Executando', variante: 'default' },
		aguardando: { rotulo: 'Aguardando', variante: 'outline' },
		interrompida: { rotulo: 'Interrompida', variante: 'destructive' }
	};
	const TIPOS: Record<string, string> = {
		oab: 'OAB',
		parte: 'Nome da parte',
		processo: 'Processo'
	};

	function rotulo(s: string) {
		return STATUS[s]?.rotulo ?? s;
	}
	function variante(s: string): BadgeVariant {
		return STATUS[s]?.variante ?? 'outline';
	}
	function horario(s: string | null) {
		return s ? s.replace('T', ' ').slice(0, 16) : '—';
	}
	function duracao(segundos: number | null) {
		if (segundos === null) return 'Em andamento';
		if (segundos < 60) return `${segundos}s`;
		const m = Math.floor(segundos / 60);
		return m < 60 ? `${m}min ${segundos % 60}s` : `${Math.floor(m / 60)}h ${m % 60}min`;
	}
	function resumoConsultas(c: Record<string, number>) {
		const total = Object.values(c).reduce((a, b) => a + b, 0);
		if (!total) return 'Nenhuma consulta visível';
		const falhas = total - (c.ok ?? 0);
		return falhas
			? `${total} consultas · ${falhas} com falha ou incompletas`
			: `${total} consultas, todas OK`;
	}
	function item(log: LogMonitoramento) {
		const p = log.parametros;
		const tipo = TIPOS[log.origem] ?? log.origem;
		const tribunal = p.tribunal ? ` · ${p.tribunal}` : '';
		return `${tipo}: ${p.valor ?? '—'}${tribunal}`;
	}
	function unidadeNome(id: number) {
		return data.me.unidades?.find((u) => u.id === id)?.nome || `Unidade ${id}`;
	}

	async function filtrar(pagina = 1) {
		ocupado = true;
		try {
			const p = new URLSearchParams({ page: String(pagina) });
			if (status !== 'todos') p.set('status', status);
			if (de) p.set('de', de);
			if (ate) p.set('ate', ate);
			execucoes = await api.get<ExecucoesMonitoramento>(`djen/monitoramentos/execucoes?${p}`);
			abertas = {};
		} catch (e) {
			toast.error(mensagemDeErro(e, 'Não foi possível carregar as execuções'));
		} finally {
			ocupado = false;
		}
	}

	async function carregarConsultas(id: number, pagina = 1) {
		carregando = id;
		try {
			const r = await api.get<LogsMonitoramento>(
				`djen/monitoramentos/logs?execucao_id=${id}&page=${pagina}`
			);
			const anteriores = pagina > 1 ? (abertas[id]?.itens ?? []) : [];
			abertas = {
				...abertas,
				[id]: { itens: [...anteriores, ...r.items], total: r.total, page: pagina }
			};
		} catch (e) {
			toast.error(mensagemDeErro(e, 'Não foi possível carregar as consultas'));
		} finally {
			carregando = null;
		}
	}

	function alternar(evento: Event, id: number) {
		const aberto = (evento.currentTarget as HTMLDetailsElement).open;
		if (aberto && !abertas[id]) carregarConsultas(id);
	}
</script>

<div class="space-y-6">
	<div class="space-y-2">
		<Button variant="ghost" size="sm" href="/djen/monitoramento" class="-ml-2">
			<ArrowLeft /> Monitoramento do DJEN
		</Button>
		<h1 class="text-2xl font-semibold">Execuções do monitoramento</h1>
		<p class="text-muted-foreground">
			Cada execução da rotina automática (04h, 10h e 16h) e o resultado das consultas que ela fez.
			Histórico mantido por {execucoes.retencao_dias} dias. Horários de Brasília.
		</p>
	</div>

	<section class="space-y-4 rounded-lg border bg-card p-6">
		<div class="flex flex-wrap items-end gap-3">
			<label class="text-sm">De<Input type="date" bind:value={de} /></label>
			<label class="text-sm">Até<Input type="date" bind:value={ate} /></label>
			<Select.Root type="single" bind:value={status}>
				<Select.Trigger aria-label="Status" class="w-44">
					{status === 'todos' ? 'Todos os status' : rotulo(status)}
				</Select.Trigger>
				<Select.Content>
					{#each ['todos', 'ok', 'parcial', 'erro', 'executando', 'interrompida'] as v}
						<Select.Item value={v}>{v === 'todos' ? 'Todos os status' : rotulo(v)}</Select.Item>
					{/each}
				</Select.Content>
			</Select.Root>
			<Button disabled={ocupado} onclick={() => filtrar()}>Filtrar / atualizar</Button>
		</div>

		{#each execucoes.items as execucao (execucao.id)}
			<details class="rounded border p-3" ontoggle={(e) => alternar(e, execucao.id)}>
				<summary class="flex cursor-pointer flex-wrap items-center gap-x-3 gap-y-1">
					<Badge variant={variante(execucao.status)}>{rotulo(execucao.status)}</Badge>
					<span class="font-medium">{horario(execucao.inicio)}</span>
					<span class="text-sm text-muted-foreground">
						Execução {execucao.id} · {duracao(execucao.duracao_segundos)}
						{#if execucao.janela_dias}· janela de {execucao.janela_dias} dias{/if}
					</span>
					<span class="text-sm">
						{execucao.novas} novas · {execucao.atualizadas} atualizadas · {execucao.vinculadas} vinculadas
					</span>
					<span class="text-sm text-muted-foreground">{resumoConsultas(execucao.consultas)}</span>
				</summary>
				<div class="mt-3 space-y-3 text-sm">
					{#if execucao.mensagem}
						<pre
							class="rounded bg-muted p-3 whitespace-pre-wrap text-destructive">{execucao.mensagem}</pre>
					{/if}
					{#if carregando === execucao.id && !abertas[execucao.id]}
						<p class="text-muted-foreground">Carregando consultas…</p>
					{:else if abertas[execucao.id]}
						{@const aberta = abertas[execucao.id]}
						{#if aberta.itens.length}
							<div class="overflow-x-auto">
								<table class="w-full text-left">
									<thead class="text-muted-foreground">
										<tr>
											<th class="py-1 pr-3 font-medium">Item</th>
											<th class="py-1 pr-3 font-medium">Período</th>
											<th class="py-1 pr-3 font-medium">Unidade</th>
											<th class="py-1 pr-3 font-medium">Status</th>
											<th class="py-1 pr-3 font-medium">Encontradas / novas</th>
											<th class="py-1 font-medium">Duração</th>
										</tr>
									</thead>
									<tbody>
										{#each aberta.itens as log (log.id)}
											<tr class="border-t align-top">
												<td class="py-1 pr-3">
													{item(log)}
													{#if log.mensagem}
														<p class="text-destructive">{log.mensagem}</p>
													{/if}
												</td>
												<td class="py-1 pr-3 whitespace-nowrap">
													{log.parametros.de ?? '—'} a {log.parametros.ate ?? '—'}
												</td>
												<td class="py-1 pr-3">{unidadeNome(log.unidade_id)}</td>
												<td class="py-1 pr-3">
													<Badge variant={variante(log.status)}>{rotulo(log.status)}</Badge>
												</td>
												<td class="py-1 pr-3">{log.encontradas} / {log.novas}</td>
												<td class="py-1">{duracao(log.duracao_segundos)}</td>
											</tr>
										{/each}
									</tbody>
								</table>
							</div>
							{#if aberta.itens.length < aberta.total}
								<Button
									variant="outline"
									size="sm"
									disabled={carregando === execucao.id}
									onclick={() => carregarConsultas(execucao.id, aberta.page + 1)}
								>
									Carregar mais ({aberta.itens.length} de {aberta.total})
								</Button>
							{/if}
						{:else}
							<p class="text-muted-foreground">
								Nenhuma consulta desta execução nas suas unidades.
							</p>
						{/if}
					{/if}
				</div>
			</details>
		{:else}
			<p>Nenhuma execução encontrada.</p>
		{/each}

		<div class="flex items-center gap-3">
			<Button
				variant="outline"
				disabled={ocupado || execucoes.page <= 1}
				onclick={() => filtrar(execucoes.page - 1)}
			>
				Anterior
			</Button>
			<span>{execucoes.total} execuções · Página {execucoes.page}</span>
			<Button
				variant="outline"
				disabled={ocupado || execucoes.page * execucoes.per_page >= execucoes.total}
				onclick={() => filtrar(execucoes.page + 1)}
			>
				Próxima
			</Button>
		</div>
	</section>
</div>
