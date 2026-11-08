<script lang="ts">
	import { api } from '$lib/api-client';
	import ConfirmAction from '$lib/components/confirm-action.svelte';
	import { Badge } from '$lib/components/ui/badge';
	import { Button, buttonVariants } from '$lib/components/ui/button';
	import * as Dialog from '$lib/components/ui/dialog';
	import { Input } from '$lib/components/ui/input';
	import { Label } from '$lib/components/ui/label';
	import * as Table from '$lib/components/ui/table';
	import type { OabMonitorada, OabMonitoradaInput, SugestaoOab } from '$lib/types';
	import { formatDateTime } from '$lib/utils/date';
	import { mensagemDeErro } from '$lib/utils/erros';
	import { invalidateAll } from '$app/navigation';
	import Trash from '@lucide/svelte/icons/trash-2';
	import { toast } from 'svelte-sonner';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
	const oabs = $derived(data.oabs);
	const sugestoesLivres = $derived(data.sugestoes.filter((s) => !s.cadastrada));

	const UFS =
		'AC AL AM AP BA CE DF ES GO MA MG MS MT PA PB PE PI PR RJ RN RO RR RS SC SE SP TO'.split(' ');

	let open = $state(false);
	let numero = $state('');
	let uf = $state('MG');
	let idUsuario = $state<number | null>(null);
	let donoNome = $state<string | null>(null);
	let salvando = $state(false);
	let alterando = $state<number | null>(null);

	function abrir(sugestao?: SugestaoOab) {
		numero = sugestao?.numero_oab ?? '';
		uf = sugestao?.uf_oab ?? 'MG';
		idUsuario = sugestao?.id_usuario ?? null;
		donoNome = sugestao?.nome ?? null;
		open = true;
	}

	async function salvar() {
		if (!numero.trim()) {
			toast.error('Informe o número da OAB');
			return;
		}
		salvando = true;
		try {
			const corpo: OabMonitoradaInput = { numero_oab: numero.trim(), uf_oab: uf };
			if (idUsuario !== null) corpo.id_usuario = idUsuario;
			await api.post('djen/oabs', corpo);
			toast.success('OAB cadastrada. A rotina passa a consultá-la na próxima execução.');
			open = false;
			await invalidateAll();
		} catch (err) {
			toast.error(mensagemDeErro(err, 'Erro ao cadastrar a OAB'));
		} finally {
			salvando = false;
		}
	}

	async function alternar(oab: OabMonitorada) {
		alterando = oab.id;
		try {
			await api.put(`djen/oabs/${oab.id}`, { ativo: !oab.ativo });
			toast.success(oab.ativo ? 'OAB pausada' : 'OAB reativada');
			await invalidateAll();
		} catch (err) {
			toast.error(mensagemDeErro(err, 'Erro ao alterar a OAB'));
		} finally {
			alterando = null;
		}
	}

	async function remover(oab: OabMonitorada) {
		try {
			await api.delete(`djen/oabs/${oab.id}`);
			toast.success('OAB removida');
			await invalidateAll();
		} catch (err) {
			toast.error(mensagemDeErro(err, 'Erro ao remover a OAB'));
		}
	}
</script>

<svelte:head>
	<title>OABs monitoradas - Gestão Legal</title>
</svelte:head>

<div class="w-full min-w-0 space-y-6">
	<div class="flex flex-wrap items-start justify-between gap-4">
		<div>
			<h1 class="text-3xl font-bold tracking-tight">OABs monitoradas</h1>
			<p class="mt-2 max-w-3xl text-muted-foreground">
				A rotina do DJEN busca, em cada execução, as publicações dos últimos dias destas OABs. A
				publicação que casar com um processo cadastrado vira evento do caso; as demais ficam em "Sem
				caso", na unidade da OAB. Esta lista mostra as OABs da unidade ativa.
			</p>
		</div>
		<Button onclick={() => abrir()}>Nova OAB</Button>
	</div>

	<div class="rounded-lg border bg-card">
		<Table.Root>
			<Table.Header>
				<Table.Row>
					<Table.Head class="w-[140px]">OAB</Table.Head>
					<Table.Head>Dono</Table.Head>
					<Table.Head class="w-[110px]">Situação</Table.Head>
					<Table.Head class="w-[170px]">Cadastrada em</Table.Head>
					<Table.Head class="w-[180px] text-right">Ações</Table.Head>
				</Table.Row>
			</Table.Header>
			<Table.Body>
				{#each oabs as oab (oab.id)}
					<Table.Row class={oab.ativo ? undefined : 'text-muted-foreground'}>
						<Table.Cell class="font-mono font-medium">{oab.rotulo}</Table.Cell>
						<Table.Cell>{oab.usuario_nome ?? '—'}</Table.Cell>
						<Table.Cell>
							<Badge variant={oab.ativo ? 'default' : 'secondary'}>
								{oab.ativo ? 'Ativa' : 'Pausada'}
							</Badge>
						</Table.Cell>
						<Table.Cell>{formatDateTime(oab.criado_em)}</Table.Cell>
						<Table.Cell class="text-right">
							<div class="flex justify-end gap-1">
								<Button
									variant="ghost"
									size="sm"
									disabled={alterando === oab.id}
									onclick={() => alternar(oab)}
								>
									{oab.ativo ? 'Pausar' : 'Reativar'}
								</Button>
								<ConfirmAction
									title="Remover esta OAB?"
									description={`A rotina deixa de consultar a OAB ${oab.rotulo}. As publicações já capturadas continuam.`}
									confirmText="Remover"
									cancelText="Voltar"
									triggerClass={`${buttonVariants({ variant: 'ghost', size: 'sm' })} h-8 w-8 p-0 text-destructive hover:text-destructive`}
									onConfirm={() => remover(oab)}
								>
									{#snippet trigger()}
										<Trash class="h-4 w-4" />
										<span class="sr-only">Remover</span>
									{/snippet}
								</ConfirmAction>
							</div>
						</Table.Cell>
					</Table.Row>
				{:else}
					<Table.Row>
						<Table.Cell colspan={5} class="py-8 text-center text-muted-foreground">
							Nenhuma OAB monitorada nesta unidade.
						</Table.Cell>
					</Table.Row>
				{/each}
			</Table.Body>
		</Table.Root>
	</div>

	{#if sugestoesLivres.length > 0}
		<div class="space-y-2">
			<h2 class="text-lg font-semibold">Sugestões do cadastro de usuários</h2>
			<p class="text-sm text-muted-foreground">
				OABs informadas no cadastro de orientadores, professores e administradores desta unidade. O
				campo é texto livre: confira antes de adicionar.
			</p>
			<div class="flex flex-wrap gap-2">
				{#each sugestoesLivres as s (s.id_usuario)}
					<Button variant="outline" size="sm" onclick={() => abrir(s)}>
						{s.nome} · <span class="font-mono">{s.numero_oab}/{s.uf_oab}</span>
					</Button>
				{/each}
			</div>
		</div>
	{/if}
</div>

<Dialog.Root bind:open>
	<Dialog.Content class="sm:max-w-md">
		<Dialog.Header>
			<Dialog.Title>Nova OAB monitorada</Dialog.Title>
			<Dialog.Description>
				As publicações que chegarem por ela sem casar com um processo ficam na unidade ativa.
			</Dialog.Description>
		</Dialog.Header>

		<div class="space-y-4">
			<div class="grid grid-cols-[1fr_100px] gap-3">
				<div class="space-y-1">
					<Label for="oab-numero">Número</Label>
					<Input id="oab-numero" inputmode="numeric" bind:value={numero} placeholder="123456" />
				</div>
				<div class="space-y-1">
					<Label for="oab-uf">UF</Label>
					<select
						id="oab-uf"
						bind:value={uf}
						class="h-9 w-full rounded-md border border-input bg-transparent px-2 text-sm"
					>
						{#each UFS as sigla (sigla)}<option value={sigla}>{sigla}</option>{/each}
					</select>
				</div>
			</div>
			{#if donoNome}
				<p class="text-sm">
					Dono: <span class="font-medium">{donoNome}</span>
					<Button
						variant="link"
						size="sm"
						class="h-auto p-0 pl-2"
						onclick={() => {
							idUsuario = null;
							donoNome = null;
						}}
					>
						remover
					</Button>
				</p>
			{/if}
		</div>

		<Dialog.Footer>
			<Button variant="outline" onclick={() => (open = false)} disabled={salvando}>Cancelar</Button>
			<Button onclick={salvar} disabled={salvando}>
				{salvando ? 'Salvando...' : 'Cadastrar'}
			</Button>
		</Dialog.Footer>
	</Dialog.Content>
</Dialog.Root>
