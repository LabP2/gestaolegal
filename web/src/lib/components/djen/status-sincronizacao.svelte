<script lang="ts">
	import { invalidateAll } from '$app/navigation';
	import { api } from '$lib/api-client';
	import ConfirmAction from '$lib/components/confirm-action.svelte';
	import { buttonVariants } from '$lib/components/ui/button';
	import { ApiException, type SincronizacaoDjen, type StatusDjen } from '$lib/types';
	import { formatDateTime } from '$lib/utils/date';
	import RefreshCw from '@lucide/svelte/icons/refresh-cw';
	import TriangleAlert from '@lucide/svelte/icons/triangle-alert';
	import { toast } from 'svelte-sonner';

	let { status, podeRodar = false }: { status: StatusDjen; podeRodar?: boolean } = $props();

	let rodando = $state(false);

	const explicacao = $derived(
		`Consulta todos os itens ativos de OAB, parte e processo do NPJ nos últimos ${status.rotina.janela_dias} dias. ` +
			`A rotina automática roda todos os dias às 04h, 10h e 16h, horário de Brasília. Pode levar alguns minutos.`
	);

	async function rodar() {
		rodando = true;
		try {
			const r = await api.post<SincronizacaoDjen>('djen/sincronizar');
			const resumo = `${r.novas} nova(s), ${r.vinculadas} vinculada(s), ${r.atualizadas} atualizada(s).`;
			if (r.status === 'ok') toast.success(`Rotina concluída: ${resumo}`);
			else toast.warning(`Rotina ${r.status === 'parcial' ? 'parcial' : 'com erro'}: ${resumo}`);
			await invalidateAll();
		} catch (err) {
			toast.error(err instanceof ApiException ? err.message : 'Erro ao rodar a rotina do DJEN.');
		} finally {
			rodando = false;
		}
	}
</script>

<div
	class="flex flex-wrap items-center gap-2 rounded-md border px-4 py-2 text-sm {status.atrasada
		? 'border-amber-300 bg-amber-50 text-amber-900 dark:border-amber-700 dark:bg-amber-950 dark:text-amber-100'
		: 'bg-muted/40 text-muted-foreground'}"
	role="status"
>
	{#if status.atrasada}
		<TriangleAlert class="h-4 w-4" />
	{/if}
	{#if status.ultima}
		<span>
			Última sincronização: {formatDateTime(status.ultima.fim ?? status.ultima.inicio)}
			{#if status.ultima.status !== 'ok'}
				({status.ultima.status === 'parcial' ? 'parcial' : 'com erro'})
			{/if}
		</span>
		{#if status.atrasada}
			<span>— mais de 2 dias úteis sem sincronizar; a rotina pode ter parado.</span>
		{/if}
	{:else}
		<span>A rotina do DJEN ainda não rodou para este NPJ.</span>
	{/if}

	{#if podeRodar}
		<div class="ml-auto">
			{#if rodando}
				<span
					class="{buttonVariants({
						variant: 'outline',
						size: 'sm'
					})} pointer-events-none opacity-70"
				>
					<RefreshCw class="mr-2 h-4 w-4 animate-spin" />
					Rodando a rotina…
				</span>
			{:else}
				<ConfirmAction
					title="Rodar a rotina do DJEN agora?"
					description={explicacao}
					confirmText="Rodar agora"
					buttonVariant="default"
					onConfirm={() => {
						void rodar();
					}}
					triggerClass={buttonVariants({ variant: 'outline', size: 'sm' })}
				>
					{#snippet trigger()}
						<RefreshCw class="mr-2 h-4 w-4" />
						Rodar rotina agora
					{/snippet}
				</ConfirmAction>
			{/if}
		</div>
	{/if}
</div>
