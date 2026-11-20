<script lang="ts">
	import * as AlertDialog from '#lib/components/ui/alert-dialog/index.ts';
	import { page } from '$app/state';
	import { api } from '#lib/api-client.ts';
	import { Button } from '#lib/components/ui/button/index.ts';
	import { Input } from '#lib/components/ui/input/index.ts';
	import FiltroTribunais from './filtro-tribunais.svelte';
	import type { ContextoDjen, CriteriosContexto } from '#lib/types/djen.ts';
	import { mensagemDeErro } from '#lib/utils/erros.ts';
	let {
		contexto = null,
		salvar,
		excluido
	}: {
		contexto?: ContextoDjen | null;
		salvar: (contexto: ContextoDjen) => Promise<void>;
		excluido?: () => Promise<void>;
	} = $props();
	function filtrosAtuais(): CriteriosContexto {
		const p = page.url.searchParams;
		return {
			nome_parte: p.get('nome_parte') || '',
			...(p.getAll('nomes').length
				? {
						nomes: [
							...new Set(
								[p.get('nome_parte'), ...p.getAll('nomes')].filter((n): n is string => !!n)
							)
						]
					}
				: {}),
			polo: p.get('polo') || '',
			numero_processo: p.get('numero_processo') || '',
			oab: p.get('oab') || '',
			tribunal: p
				.getAll('tribunal')
				.flatMap((t) => t.split(','))
				.filter(Boolean),
			inicio: p.get('inicio') || '',
			fim: p.get('fim') || '',
			fonte: p.get('fonte') || ''
		};
	}
	let confirmarExclusao = $state(false);
	let erroExclusao = $state('');
	async function excluirContexto() {
		if (!contexto || ocupado) return;
		ocupado = true;
		erroExclusao = '';
		try {
			await api.delete(`djen/contextos/${contexto.id}`);
			confirmarExclusao = false;
			await excluido?.();
		} catch (e) {
			erroExclusao = mensagemDeErro(e, 'Não foi possível excluir o contexto.');
		} finally {
			ocupado = false;
		}
	}
	let nome = $state('');
	let descricao = $state('');
	let nomes = $state('');
	let criterios = $state<CriteriosContexto>({});
	let tribunais = $state<string[]>([]);
	let ocupado = $state(false);
	let erro = $state('');
	let previa = $state<{ total: number; entram: number; saem: number; permanecem: number } | null>(
		null
	);
	let conferido = $state('');
	$effect(() => {
		nome = contexto?.nome ?? '';
		descricao = contexto?.descricao ?? '';
		const base = contexto
			? (contexto.criterios ?? { nomes: contexto.nomes, tribunal: contexto.tribunais })
			: filtrosAtuais();
		criterios = { ...base };
		nomes = (base.nomes ?? (base.nome_parte ? [base.nome_parte] : [])).join('; ');
		tribunais = [...(base.tribunal ?? [])];
		previa = null;
	});
	const corpo = $derived({
		nome,
		descricao,
		versao: contexto?.versao ?? 1,
		nomes: nomes
			.split(';')
			.map((n) => n.trim())
			.filter(Boolean),
		tribunais,
		criterios: {
			...criterios,
			nome_parte: '',
			nomes: nomes
				.split(';')
				.map((n) => n.trim())
				.filter(Boolean),
			tribunal: tribunais
		}
	});
	const pronto = $derived(previa !== null && conferido === JSON.stringify(corpo));
	async function conferir() {
		ocupado = true;
		erro = '';
		try {
			previa = await api.post(`djen/contextos${contexto ? `/${contexto.id}` : ''}/previa`, corpo);
			conferido = JSON.stringify(corpo);
		} catch (e) {
			erro = mensagemDeErro(e, 'Não foi possível conferir os critérios.');
		} finally {
			ocupado = false;
		}
	}
	async function gravar(e: SubmitEvent) {
		e.preventDefault();
		if (!pronto) {
			await conferir();
			return;
		}
		ocupado = true;
		erro = '';
		try {
			const resultado = contexto
				? await api.put<ContextoDjen>(`djen/contextos/${contexto.id}`, corpo)
				: await api.post<ContextoDjen>('djen/contextos', corpo);
			await salvar(resultado);
		} catch (e) {
			erro = mensagemDeErro(e, 'Não foi possível salvar o contexto.');
		} finally {
			ocupado = false;
		}
	}
</script>

<form
	class="space-y-4 rounded-md border p-4"
	onsubmit={gravar}
	aria-label={contexto ? 'Editar contexto' : 'Novo contexto'}
>
	<fieldset disabled={ocupado} class="space-y-4">
		<label class="block text-sm">
			Nome do contexto<Input
				bind:value={nome}
				required
				minlength={3}
				maxlength={150}
				placeholder="Publicações do TRF6"
			/>
		</label>
		<label class="block text-sm">
			O que é relevante neste contexto?<textarea
				class="mt-1 block w-full rounded-md border bg-background p-2"
				bind:value={descricao}
				maxlength={2000}
				placeholder="Descreva o objetivo para orientar a classificação."></textarea>
		</label>
		<p class="text-sm text-muted-foreground">
			Novas publicações que atenderem aos critérios entram automaticamente. Situação, classificação
			e sugestões são filtros de revisão e não definem o contexto. Datas preenchidas delimitam um
			período fixo.
		</p>
		<Button
			type="button"
			variant="outline"
			onclick={() => {
				criterios = filtrosAtuais();
				nomes = (criterios.nomes ?? (criterios.nome_parte ? [criterios.nome_parte] : [])).join(
					'; '
				);
				tribunais = criterios.tribunal ?? [];
			}}
		>
			Usar filtros atuais
		</Button>
		<div class="grid gap-4 sm:grid-cols-2">
			<label class="block text-sm">
				Nomes da parte (separe variações por ponto e vírgula)<Input
					bind:value={nomes}
					placeholder="Opcional"
				/>
			</label>
			<label class="block text-sm">
				Polo da parte<select
					class="block w-full rounded-md border bg-background p-2"
					bind:value={criterios.polo}
				>
					<option value="">Todos</option><option value="A">Ativo</option><option value="P">
						Passivo
					</option>
				</select>
			</label>
			<label class="block text-sm">
				Número do processo<Input bind:value={criterios.numero_processo} />
			</label>
			<label class="block text-sm">OAB<Input bind:value={criterios.oab} /></label>
			<div>
				<span class="mb-1 block text-sm">Tribunais do contexto</span><FiltroTribunais
					bind:value={tribunais}
					disabled={ocupado}
					onchange={() => {}}
				/>
			</div>
			<label class="block text-sm">
				Origem da consulta<select
					class="block w-full rounded-md border bg-background p-2"
					bind:value={criterios.fonte}
				>
					<option value="">Todas</option><option value="parte">Nome da parte</option><option
						value="oab"
					>
						OAB
					</option><option value="processo">Número do processo</option>
				</select>
			</label>
			<label class="block text-sm">De<Input type="date" bind:value={criterios.inicio} /></label>
			<label class="block text-sm">Até<Input type="date" bind:value={criterios.fim} /></label>
		</div>
		{#if pronto && previa}<p role="status" class="text-sm">
				{previa.total} publicações no contexto: {previa.entram} entram, {previa.saem} saem, {previa.permanecem}
				permanecem. Classificações e histórico serão preservados.
			</p>{/if}
		{#if erro}<p role="alert" class="text-sm text-destructive">{erro}</p>{/if}
		<Button type="submit">
			{ocupado ? 'Aguarde…' : pronto ? 'Salvar contexto' : 'Conferir contexto'}
		</Button>
	</fieldset>
</form>

{#if contexto}
	<AlertDialog.Root bind:open={confirmarExclusao}>
		<AlertDialog.Trigger
			disabled={ocupado ||
				contexto.treino_status === 'na_fila' ||
				contexto.treino_status === 'executando'}
			class="rounded-md bg-destructive px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
			onclick={() => (erroExclusao = '')}
		>
			Excluir contexto
		</AlertDialog.Trigger>
		<AlertDialog.Content>
			<AlertDialog.Header>
				<AlertDialog.Title>Excluir o contexto “{contexto.nome}”?</AlertDialog.Title>
				<AlertDialog.Description>
					Cuidado: esta operação não pode ser desfeita. Serão excluídos o contexto, seus vínculos
					com as publicações, avaliações, histórico, modelos e registros de treinamento. As
					publicações, processos, casos e os demais contextos serão preservados.
				</AlertDialog.Description>
			</AlertDialog.Header>
			{#if erroExclusao}<p role="alert" class="text-sm text-destructive">{erroExclusao}</p>{/if}
			<AlertDialog.Footer>
				<AlertDialog.Cancel disabled={ocupado}>Cancelar</AlertDialog.Cancel>
				<Button variant="destructive" disabled={ocupado} onclick={excluirContexto}>
					{ocupado ? 'Excluindo…' : 'Excluir definitivamente'}
				</Button>
			</AlertDialog.Footer>
		</AlertDialog.Content>
	</AlertDialog.Root>
{/if}
