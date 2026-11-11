<script lang="ts">
	import { RangeCalendar } from 'bits-ui';
	import * as Popover from '$lib/components/ui/popover';
	import { Button, buttonVariants } from '$lib/components/ui/button';
	import { cn } from '$lib/utils.js';
	import CalendarIcon from '@lucide/svelte/icons/calendar';
	import ChevronLeft from '@lucide/svelte/icons/chevron-left';
	import ChevronRight from '@lucide/svelte/icons/chevron-right';
	import {
		CalendarDate,
		DateFormatter,
		getLocalTimeZone,
		parseDate,
		today,
		type DateValue
	} from '@internationalized/date';

	// Período "de–até" num só campo. `de` e `ate` são "AAAA-MM-DD".
	let {
		id,
		de = $bindable(''),
		ate = $bindable(''),
		maxDias,
		atalhos = [7, 15, 30]
	}: {
		id: string;
		de: string;
		ate: string;
		/** Tamanho máximo do período, em dias. */
		maxDias?: number;
		/** Botões "Últimos N dias". */
		atalhos?: number[];
	} = $props();

	let open = $state(false);
	const hoje = today(getLocalTimeZone());
	const formato = new DateFormatter('pt-BR', { dateStyle: 'medium' });

	function ler(iso: string): CalendarDate | undefined {
		try {
			return iso ? parseDate(iso) : undefined;
		} catch {
			return undefined;
		}
	}

	// Estado do calendário; só volta para `de`/`ate` quando o período fecha.
	let faixa = $state<{ start: DateValue | undefined; end: DateValue | undefined }>({
		start: ler(de),
		end: ler(ate)
	});

	$effect(() => {
		if (!open) faixa = { start: ler(de), end: ler(ate) };
	});

	function aplicar(v: { start: DateValue | undefined; end: DateValue | undefined }) {
		faixa = v;
		if (v.start && v.end) {
			de = v.start.toString();
			ate = v.end.toString();
			open = false;
		}
	}

	function ultimos(dias: number) {
		aplicar({ start: hoje.subtract({ days: dias - 1 }), end: hoje });
	}

	const rotulo = $derived.by(() => {
		const i = ler(de);
		const f = ler(ate);
		if (!i || !f) return 'Escolha o período';
		const tz = getLocalTimeZone();
		return `${formato.format(i.toDate(tz))} – ${formato.format(f.toDate(tz))}`;
	});
</script>

<Popover.Root bind:open>
	<Popover.Trigger {id}>
		{#snippet child({ props })}
			<Button {...props} variant="outline" class="min-w-64 justify-start font-normal">
				<CalendarIcon class="mr-2 h-4 w-4" />
				{rotulo}
			</Button>
		{/snippet}
	</Popover.Trigger>
	<Popover.Content class="w-auto p-0" align="start">
		<div class="flex flex-col sm:flex-row">
			<div class="flex flex-row flex-wrap gap-1 border-b p-2 sm:flex-col sm:border-r sm:border-b-0">
				{#each atalhos.filter((n) => !maxDias || n <= maxDias) as n (n)}
					<Button type="button" variant="ghost" size="sm" onclick={() => ultimos(n)}>
						Últimos {n} dias
					</Button>
				{/each}
			</div>
			<RangeCalendar.Root
				value={faixa}
				onValueChange={aplicar}
				locale="pt-BR"
				weekdayFormat="short"
				numberOfMonths={2}
				maxDays={maxDias}
				maxValue={hoje}
				placeholder={ler(ate) ?? hoje}
				class="p-3"
			>
				{#snippet children({ months, weekdays })}
					<RangeCalendar.Header class="relative flex items-center justify-between pb-2">
						<RangeCalendar.PrevButton
							class={cn(buttonVariants({ variant: 'ghost', size: 'icon' }), 'h-8 w-8')}
						>
							<ChevronLeft class="h-4 w-4" />
						</RangeCalendar.PrevButton>
						<RangeCalendar.Heading class="text-sm font-medium capitalize" />
						<RangeCalendar.NextButton
							class={cn(buttonVariants({ variant: 'ghost', size: 'icon' }), 'h-8 w-8')}
						>
							<ChevronRight class="h-4 w-4" />
						</RangeCalendar.NextButton>
					</RangeCalendar.Header>
					<div class="flex flex-col gap-4 sm:flex-row">
						{#each months as month (month.value)}
							<RangeCalendar.Grid class="border-collapse select-none">
								<RangeCalendar.GridHead>
									<RangeCalendar.GridRow class="flex">
										{#each weekdays as dia (dia)}
											<RangeCalendar.HeadCell
												class="w-9 text-center text-xs font-normal text-muted-foreground"
											>
												{dia.slice(0, 3)}
											</RangeCalendar.HeadCell>
										{/each}
									</RangeCalendar.GridRow>
								</RangeCalendar.GridHead>
								<RangeCalendar.GridBody>
									{#each month.weeks as semana (semana)}
										<RangeCalendar.GridRow class="mt-1 flex">
											{#each semana as data (data)}
												<RangeCalendar.Cell
													date={data}
													month={month.value}
													class="relative h-9 w-9 p-0 text-center text-sm"
												>
													<RangeCalendar.Day
														class={cn(
															'inline-flex h-9 w-9 items-center justify-center rounded-md text-sm hover:bg-accent',
															'data-[today]:font-semibold data-[today]:underline',
															'data-[highlighted]:rounded-none data-[highlighted]:bg-accent',
															'data-[selected]:rounded-none data-[selected]:bg-accent data-[selected]:text-accent-foreground',
															'data-[selection-start]:rounded-l-md data-[selection-start]:bg-primary data-[selection-start]:text-primary-foreground',
															'data-[selection-end]:rounded-r-md data-[selection-end]:bg-primary data-[selection-end]:text-primary-foreground',
															'data-[outside-month]:pointer-events-none data-[outside-month]:opacity-0',
															'data-[disabled]:pointer-events-none data-[disabled]:text-muted-foreground data-[disabled]:opacity-40',
															'data-[unavailable]:text-muted-foreground data-[unavailable]:line-through'
														)}
													/>
												</RangeCalendar.Cell>
											{/each}
										</RangeCalendar.GridRow>
									{/each}
								</RangeCalendar.GridBody>
							</RangeCalendar.Grid>
						{/each}
					</div>
				{/snippet}
			</RangeCalendar.Root>
		</div>
		{#if maxDias}
			<p class="border-t px-3 py-2 text-xs text-muted-foreground">
				Clique no início e no fim. Até {maxDias} dias.
			</p>
		{/if}
	</Popover.Content>
</Popover.Root>
