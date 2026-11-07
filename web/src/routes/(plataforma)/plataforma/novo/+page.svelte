<script lang="ts">
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import { Label } from '$lib/components/ui/label';
	import * as Card from '$lib/components/ui/card';
	import { plataforma } from '$lib/plataforma-client';
	import { ApiException, type TenantCriacaoInput, type TenantCriado } from '$lib/types';
	import { toast } from 'svelte-sonner';

	type Campo = keyof TenantCriacaoInput;

	let dados = $state<Record<Campo, string>>({
		nome: '',
		sigla: '',
		slug: '',
		instituicao: '',
		unidade_nome: 'Sede',
		unidade_sigla: 'SD',
		admin_nome: '',
		admin_email: ''
	});
	let slugEditado = $state(false);
	let erros = $state<Partial<Record<Campo, string>>>({});
	let erroGeral = $state<string | null>(null);
	let enviando = $state(false);
	let criado = $state<TenantCriado | null>(null);

	/** Sugestão de identificador a partir da sigla, até o usuário editar. */
	function sugerirSlug(valor: string): string {
		return valor
			.normalize('NFD')
			.replace(/[̀-ͯ]/g, '')
			.toLowerCase()
			.replace(/[^a-z0-9]+/g, '-')
			.replace(/^-+|-+$/g, '');
	}

	$effect(() => {
		if (!slugEditado) dados.slug = sugerirSlug(dados.sigla);
	});

	const secoes: { titulo: string; campos: { campo: Campo; rotulo: string; ajuda?: string }[] }[] = [
		{
			titulo: 'NPJ',
			campos: [
				{ campo: 'nome', rotulo: 'Nome' },
				{ campo: 'sigla', rotulo: 'Sigla' },
				{
					campo: 'slug',
					rotulo: 'Identificador',
					ajuda: 'Usado em scripts (--tenant). Minúsculas, números e hífens. Não muda depois.'
				},
				{ campo: 'instituicao', rotulo: 'Instituição (opcional)' }
			]
		},
		{
			titulo: 'Unidade inicial',
			campos: [
				{ campo: 'unidade_nome', rotulo: 'Nome da unidade' },
				{ campo: 'unidade_sigla', rotulo: 'Sigla da unidade' }
			]
		},
		{
			titulo: 'Primeiro administrador do NPJ',
			campos: [
				{ campo: 'admin_nome', rotulo: 'Nome' },
				{
					campo: 'admin_email',
					rotulo: 'E-mail',
					ajuda: 'Não pode ser usado por nenhuma outra conta da plataforma.'
				}
			]
		}
	];

	async function criar(event: SubmitEvent) {
		event.preventDefault();
		erros = {};
		erroGeral = null;
		enviando = true;
		try {
			criado = await plataforma.post<TenantCriado>('tenants', {
				...dados,
				instituicao: dados.instituicao.trim() || null
			});
			toast.success('NPJ criado');
		} catch (err) {
			if (err instanceof ApiException && err.details?.field) {
				erros = { [err.details.field as Campo]: err.message };
			} else {
				erroGeral = err instanceof ApiException ? err.message : 'Erro ao criar o NPJ.';
			}
		} finally {
			enviando = false;
		}
	}

	async function copiarLink() {
		if (!criado) return;
		try {
			await navigator.clipboard.writeText(criado.link_primeiro_acesso);
			toast.success('Link copiado');
		} catch {
			toast.error('Não foi possível copiar; selecione o link manualmente.');
		}
	}
</script>

<div class="space-y-6">
	<div>
		<a href="/plataforma" class="text-sm text-muted-foreground hover:underline">← NPJs</a>
		<h1 class="text-2xl font-semibold">Novo NPJ</h1>
	</div>

	{#if criado}
		<Card.Root>
			<Card.Header>
				<Card.Title>{criado.tenant.sigla} criado</Card.Title>
				<Card.Description>
					Envie este link a {criado.admin.nome} ({criado.admin.email}) para que defina a senha e
					entre pela primeira vez. Ele vale por 3 dias e só funciona uma vez. Se expirar, a pessoa
					pode usar “Esqueci minha senha” no login.
				</Card.Description>
			</Card.Header>
			<Card.Content class="space-y-3">
				<Input
					readonly
					value={criado.link_primeiro_acesso}
					onfocus={(e) => e.currentTarget.select()}
				/>
				<div class="flex flex-wrap gap-2">
					<Button onclick={copiarLink}>Copiar link</Button>
					<Button variant="outline" href="/plataforma/{criado.tenant.id}">Ver NPJ</Button>
					<Button variant="ghost" href="/plataforma">Voltar à lista</Button>
				</div>
			</Card.Content>
		</Card.Root>
	{:else}
		<form class="space-y-6" onsubmit={criar}>
			{#each secoes as secao (secao.titulo)}
				<Card.Root>
					<Card.Header>
						<Card.Title class="text-base">{secao.titulo}</Card.Title>
					</Card.Header>
					<Card.Content class="grid gap-4 sm:grid-cols-2">
						{#each secao.campos as { campo, rotulo, ajuda } (campo)}
							<div class="space-y-1">
								<Label for={campo}>{rotulo}</Label>
								<Input
									id={campo}
									bind:value={dados[campo]}
									oninput={() => {
										if (campo === 'slug') slugEditado = true;
									}}
									aria-invalid={erros[campo] ? 'true' : undefined}
									type={campo === 'admin_email' ? 'email' : 'text'}
									required={campo !== 'instituicao'}
								/>
								{#if erros[campo]}
									<p class="text-sm text-destructive">{erros[campo]}</p>
								{:else if ajuda}
									<p class="text-xs text-muted-foreground">{ajuda}</p>
								{/if}
							</div>
						{/each}
					</Card.Content>
				</Card.Root>
			{/each}

			{#if erroGeral}
				<p role="alert" class="text-sm text-destructive">{erroGeral}</p>
			{/if}
			<Button type="submit" disabled={enviando}>{enviando ? 'Criando…' : 'Criar NPJ'}</Button>
		</form>
	{/if}
</div>
