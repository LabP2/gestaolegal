<script lang="ts">
	import { SimpleInput, SimpleSelect } from '$lib/components/forms';
	import * as Card from '$lib/components/ui/card';
	import type { AssistidoCreateFormData } from './schemas/assistido-schema';
	import type { SuperForm } from 'sveltekit-superforms';

	let {
		form,
		dados = $bindable()
	}: {
		form: SuperForm<AssistidoCreateFormData>;
		dados: NonNullable<AssistidoCreateFormData['assistido_pessoa_juridica']>;
	} = $props();

	const errors = $derived(form.errors);

	function mudarEnquadramento(enquadramento: typeof dados.enquadramento) {
		dados = {
			...dados,
			enquadramento,
			socios: enquadramento === 'mei' ? [] : dados.socios.length ? dados.socios : [''],
			especificacao_enquadramento:
				enquadramento === 'outros' ? dados.especificacao_enquadramento : null
		};
	}

	function alterarSocio(index: number, nome: string) {
		dados = { ...dados, socios: dados.socios.map((atual, i) => (i === index ? nome : atual)) };
	}

	function ajustarQuantidade(event: Event) {
		const input = event.currentTarget as HTMLInputElement;
		const quantidade = Number(input.value);
		if (!Number.isInteger(quantidade) || quantidade < 1 || quantidade > 20) {
			input.value = String(dados.socios.length);
			return;
		}
		dados = {
			...dados,
			socios: Array.from({ length: quantidade }, (_, i) => dados.socios[i] ?? '')
		};
	}
</script>

<Card.Root>
	<Card.Header><Card.Title>Dados Jurídicos</Card.Title></Card.Header>
	<Card.Content class="grid gap-4">
		<SimpleSelect
			{form}
			name="assistido_pessoa_juridica.enquadramento"
			label="Enquadramento"
			bind:value={() => dados.enquadramento, mudarEnquadramento}
			placeholder="Selecione"
			options={[
				{ value: 'mei', label: 'Microempreendedor Individual' },
				{ value: 'microempresa', label: 'Microempresa' },
				{ value: 'pequeno_porte', label: 'Empresa de pequeno porte' },
				{ value: 'outros', label: 'Outros' }
			]}
		/>
		{#if dados.enquadramento === 'outros'}
			<SimpleInput
				{form}
				name="assistido_pessoa_juridica.especificacao_enquadramento"
				label="Especifique o enquadramento da PJ"
				bind:value={
					() => dados.especificacao_enquadramento ?? '',
					(value: string) => (dados = { ...dados, especificacao_enquadramento: value })
				}
			/>
		{/if}
		{#if dados.enquadramento && dados.enquadramento !== 'mei'}
			<div class="space-y-2">
				<label for="quantidade-socios" class="text-sm font-medium"
					>Quantos sócios tem a Pessoa Jurídica?</label
				>
				<input
					id="quantidade-socios"
					type="number"
					min="1"
					max="20"
					step="1"
					required
					class="h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm"
					value={dados.socios.length}
					oninput={ajustarQuantidade}
				/>
				<p class="text-sm text-muted-foreground">Até 20 sócios, com até 80 caracteres por nome.</p>
			</div>
			{#each dados.socios as _, index}
				<SimpleInput
					{form}
					name={`assistido_pessoa_juridica.socios[${index}]`}
					label={`Qual o nome do sócio ${index + 1}?`}
					bind:value={() => dados.socios[index], (value: string) => alterarSocio(index, value)}
				/>
			{/each}
			{#if $errors.assistido_pessoa_juridica?.socios?._errors}
				<p class="text-sm text-destructive" role="alert">
					{$errors.assistido_pessoa_juridica.socios._errors.join(' ')}
				</p>
			{/if}
		{/if}
		<SimpleSelect
			{form}
			name="assistido_pessoa_juridica.situacao_receita"
			label="Situação perante a Receita Federal"
			bind:value={
				() => dados.situacao_receita,
				(value: typeof dados.situacao_receita) => (dados = { ...dados, situacao_receita: value })
			}
			placeholder="Não informada"
			options={[
				{ value: 'Ativa', label: 'Ativa' },
				{ value: 'Baixada', label: 'Baixada' },
				{ value: 'Outras', label: 'Outras' }
			]}
		/>
	</Card.Content>
</Card.Root>
