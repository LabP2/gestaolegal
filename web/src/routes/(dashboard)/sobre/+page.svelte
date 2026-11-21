<script lang="ts">
	import * as Card from '#lib/components/ui/card/index.ts';

	const versao = __VERSAO__;
	const repositorio = 'https://github.com/LabP2/gestaolegal';
	const laboratorio = 'https://labp2.direito.ufmg.br/';
</script>

<svelte:head>
	<title>Sobre - Gestão Legal</title>
</svelte:head>

<div class="w-full min-w-0 space-y-6">
	<div>
		<h1 class="text-3xl font-bold tracking-tight">Sobre</h1>
		<p class="mt-2 text-muted-foreground">Gestão Legal, versão {versao}.</p>
	</div>

	<Card.Root>
		<Card.Header>
			<Card.Title>Gestão Legal {versao}</Card.Title>
		</Card.Header>
		<Card.Content class="space-y-4 text-sm leading-relaxed">
			<p>
				O Gestão Legal é software livre, distribuído sob a licença
				<a
					class="font-medium underline underline-offset-4"
					href="https://www.gnu.org/licenses/agpl-3.0.html"
					target="_blank"
					rel="noopener noreferrer"
				>
					GNU AGPL 3.0
				</a>. O código-fonte está disponível em
				<a
					class="font-medium underline underline-offset-4"
					href={repositorio}
					target="_blank"
					rel="noopener noreferrer"
				>
					{repositorio}
				</a>.
			</p>
			<p>
				É um produto do
				<a
					class="font-medium underline underline-offset-4"
					href={laboratorio}
					target="_blank"
					rel="noopener noreferrer"
				>
					LabP2
				</a>, da Faculdade de Direito da Universidade Federal de Minas Gerais (UFMG).
			</p>
		</Card.Content>
	</Card.Root>
</div>
